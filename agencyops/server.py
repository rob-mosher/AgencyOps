"""AgencyOps MCP server.

Cloud-hosted MCP server enabling AI entities to provision Azure infrastructure
with bounded agency. Exposes 7 tools: query_backplane, get_state, plan_resource,
apply_plan, get_budget_status, delete_resource, reconcile.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from agencyops.budget_tracker import BudgetTracker
from agencyops.models import (
    AgencyOpsConfig,
    DriftIssue,
    InfraState,
    PolicyValidation,
    ReconcileResult,
    ResourcePlan,
    ResourceState,
    estimate_monthly_cost,
)
from agencyops.terraform_backend import (
    SubprocessTerraformBackend,
    TerraformError,
    generate_plan_id,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agencyops")

# ---------------------------------------------------------------------------
# Configuration & subsystem initialization
# ---------------------------------------------------------------------------
config = AgencyOpsConfig.from_env()
config.data_dir.mkdir(parents=True, exist_ok=True)

budget = BudgetTracker(config.data_dir, azure_limit=config.backplane.monthly_limit)
terraform = SubprocessTerraformBackend(config.terraform_dir, config.data_dir)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("agencyops")


@mcp.tool()
def query_backplane() -> dict[str, Any]:
    """Returns available Azure infrastructure: subscription info, available SKUs, and budget status.

    Use this to understand what resources are available before planning.
    """
    bp = config.backplane
    budget_status = budget.get_status()

    return {
        "azure": {
            "subscription_id": bp.subscription_id,
            "location": bp.location,
            "resource_group": bp.resource_group,
            "budget": {
                "monthly_limit": budget_status.azure.limit,
                "current_spend": budget_status.azure.spent,
                "remaining": budget_status.azure.remaining,
                "status": budget_status.azure.status,
                "currency": "USD",
            },
            "available_resources": {
                "container_instances": {
                    "cpu_options": [1, 2, 4],
                    "memory_gb_options": [1.5, 3.5, 7, 14],
                    "gpu_skus": ["K80", "V100"],
                },
            },
        },
    }


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Queries Terraform state and returns all currently provisioned Azure resources.

    Shows what infrastructure is currently running and managed by AgencyOps.
    """
    try:
        tf_state = terraform.show()
    except TerraformError as e:
        return {"error": str(e), "resources": [], "total_resources": 0}

    resources = []
    root_module = tf_state.get("values", {}).get("root_module", {})
    for res in root_module.get("resources", []):
        if res.get("type") == "azurerm_container_group":
            vals = res.get("values", {})
            tags = vals.get("tags", {})
            containers = vals.get("container", [])
            container = containers[0] if containers else {}
            gpu_info = container.get("gpu", [])
            resources.append(
                ResourceState(
                    id=vals.get("id", res.get("address", "")),
                    type="container_instance",
                    name=vals.get("name", ""),
                    image=container.get("image", ""),
                    status="running" if vals.get("ip_address") else "provisioning",
                    location=vals.get("location", ""),
                    cpu=container.get("cpu", 0),
                    memory_gb=container.get("memory", 0),
                    gpu_sku=gpu_info[0].get("sku") if gpu_info else None,
                    created_at=vals.get("created_at", "1970-01-01T00:00:00Z"),
                    purpose=tags.get("agencyops.purpose", ""),
                ).model_dump()
            )

    state = InfraState(resources=resources, total_resources=len(resources))
    return state.model_dump()


@mcp.tool()
def plan_resource(
    image: str,
    namespace: str,
    purpose: str,
    cpu: float = 1.0,
    memory_gb: float = 1.5,
    gpu_sku: str | None = None,
    gpu_count: int = 0,
    type: str = "container_instance",
) -> dict[str, Any]:
    """Generates a Terraform plan with policy validation for a new Azure resource.

    All infrastructure must justify its existence — a purpose is required.
    This creates a plan that must be explicitly applied via apply_plan().
    """
    # Cost estimation
    estimated_monthly = estimate_monthly_cost(cpu, memory_gb, gpu_sku, gpu_count)

    # Policy validation
    purpose_check = "PASS" if purpose.strip() else "FAIL"
    budget_check = "PASS" if budget.check_budget(estimated_monthly) else "FAIL"
    quota_check = "PASS"  # Placeholder — could validate against Azure quotas

    policy = PolicyValidation(
        budget_check=budget_check,
        purpose_check=purpose_check,
        quota_check=quota_check,
    )
    can_apply = all(v == "PASS" for v in [policy.budget_check, policy.purpose_check, policy.quota_check])

    plan_id = generate_plan_id()

    # Generate Terraform plan (skip if policy already failed)
    resource_name = f"{namespace}-{image.replace('/', '-').replace(':', '-')}"
    resource_diff = {"to_create": [], "to_modify": [], "to_destroy": []}
    if can_apply:
        try:
            tf_result = terraform.plan(
                plan_id,
                variables={
                    "container_instances": json.dumps({
                        resource_name: {
                            "image": image,
                            "cpu": cpu,
                            "memory_gb": memory_gb,
                            "gpu_sku": gpu_sku or "",
                            "gpu_count": gpu_count,
                            "purpose": purpose,
                            "namespace": namespace,
                            "location": config.backplane.location,
                        }
                    }),
                    "resource_group_name": config.backplane.resource_group,
                },
            )
            resource_diff = tf_result.get("changes", resource_diff)
        except TerraformError as e:
            logger.warning("Terraform plan failed: %s", e)
            resource_diff = {
                "to_create": [f"azurerm_container_group.workload[\"{resource_name}\"]"],
                "to_modify": [],
                "to_destroy": [],
                "terraform_error": str(e),
            }

    plan = ResourcePlan(
        plan_id=plan_id,
        resource_diff=resource_diff,
        estimated_cost={
            "monthly": estimated_monthly,
            "currency": "USD",
            "breakdown": {
                "cpu": round(cpu * 35.04, 2),
                "memory": round(memory_gb * 3.89, 2),
                "gpu": round(gpu_count * (648.0 if gpu_sku == "K80" else 1548.0 if gpu_sku == "V100" else 0), 2) if gpu_sku else 0,
            },
        },
        resource_impact={
            "cpu": cpu,
            "memory_gb": memory_gb,
            "gpu_sku": gpu_sku,
            "gpu_count": gpu_count,
            "location": config.backplane.location,
        },
        policy_validation=policy,
        can_apply=can_apply,
    )
    return plan.model_dump()


@mcp.tool()
def apply_plan(plan_id: str) -> dict[str, Any]:
    """Executes a previously generated Terraform plan.

    The plan must have been created by plan_resource() and must still be valid.
    """
    # Load plan metadata to record cost
    meta_file = config.data_dir / "plans" / f"{plan_id}.json"
    estimated_monthly = 0.0
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            variables = meta.get("variables", {})
            ci_str = variables.get("container_instances", "{}")
            if isinstance(ci_str, str):
                containers = json.loads(ci_str)
            else:
                containers = ci_str
            for c in containers.values():
                estimated_monthly += estimate_monthly_cost(
                    c.get("cpu", 1.0),
                    c.get("memory_gb", 1.5),
                    c.get("gpu_sku") or None,
                    c.get("gpu_count", 0),
                )
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    # Apply the plan
    try:
        terraform.apply(plan_id)
    except TerraformError as e:
        return {"status": "failed", "message": str(e), "plan_id": plan_id}

    # Record cost to budget tracker
    if estimated_monthly > 0:
        budget.add_cost(estimated_monthly)

    return {
        "status": "success",
        "plan_id": plan_id,
        "estimated_monthly_cost": estimated_monthly,
        "message": "Azure infrastructure provisioned successfully",
    }


@mcp.tool()
def get_budget_status() -> dict[str, Any]:
    """Returns current Azure budget tracking status.

    Shows limit, spend, remaining budget, and month-end projection.
    """
    return budget.get_status().model_dump()


@mcp.tool()
def delete_resource(resource_id: str, reason: str) -> dict[str, Any]:
    """Destroys an Azure resource via Terraform.

    Requires a reason — deletion decisions should be deliberate.
    """
    if not reason.strip():
        return {"status": "failed", "message": "A reason is required for resource deletion"}

    try:
        terraform.destroy(target=resource_id)
    except TerraformError as e:
        return {"status": "failed", "message": str(e)}

    logger.info("Resource %s deleted. Reason: %s", resource_id, reason)

    return {
        "status": "success",
        "resource_id": resource_id,
        "reason": reason,
        "message": "Azure resource deleted successfully",
    }


@mcp.tool()
def reconcile() -> dict[str, Any]:
    """Detects drift between Terraform state and actual Azure infrastructure.

    Compares Terraform state vs Azure Container Instances reality.
    Reports issues but does not auto-apply fixes.
    """
    issues: list[dict] = []

    # Get Terraform-managed resources
    tf_resources: dict[str, dict] = {}
    try:
        tf_state = terraform.show()
        root_module = tf_state.get("values", {}).get("root_module", {})
        for res in root_module.get("resources", []):
            if res.get("type") == "azurerm_container_group":
                vals = res.get("values", {})
                name = vals.get("name", "")
                tf_resources[name] = vals
    except TerraformError:
        issues.append(
            DriftIssue(
                type="terraform_error",
                details="Could not read Terraform state",
                recommended_action="Run terraform init or check backend configuration",
            ).model_dump()
        )

    # Get actual Azure Container Instances
    azure_resources: dict[str, dict] = {}
    try:
        result = subprocess.run(
            [
                "az", "container", "list",
                "--resource-group", config.backplane.resource_group,
                "--query", "[?tags.\"agencyops.managed\"=='true']",
                "--output", "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            for container in json.loads(result.stdout):
                name = container.get("name", "")
                azure_resources[name] = container
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append(
            DriftIssue(
                type="azure_cli_error",
                details="Could not query Azure — az CLI not available or timed out",
                recommended_action="Ensure Azure CLI is installed and authenticated",
            ).model_dump()
        )

    # Compare: resources in Azure but not in Terraform
    for name in azure_resources:
        if name not in tf_resources:
            issues.append(
                DriftIssue(
                    type="orphaned_resource",
                    details=f"Container instance '{name}' exists in Azure but not in Terraform state",
                    recommended_action="Import into state or delete",
                ).model_dump()
            )

    # Compare: resources in Terraform but not in Azure
    for name in tf_resources:
        if name not in azure_resources:
            issues.append(
                DriftIssue(
                    type="missing_resource",
                    details=f"Terraform expects '{name}' but it doesn't exist in Azure",
                    recommended_action="Remove from state or re-provision",
                ).model_dump()
            )

    result = ReconcileResult(drift_detected=len(issues) > 0, issues=issues)
    return result.model_dump()
