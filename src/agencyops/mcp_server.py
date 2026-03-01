"""AgencyOps MCP server.

Exposes 7 tools for bounded infrastructure provisioning:
query_backplane, get_state, plan_resource, apply_plan,
get_budget_status, delete_resource, reconcile.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from agencyops.budget_tracker import BudgetTracker
from agencyops.gpu_manager import GpuLockError, GpuManager
from agencyops.models import (
    AgencyOpsConfig,
    DriftIssue,
    InfraState,
    PolicyValidation,
    ReconcileResult,
    ResourcePlan,
    ResourceState,
)
from agencyops.terraform_backend import (
    SubprocessTerraformBackend,
    TerraformError,
    generate_plan_id,
)

# ---------------------------------------------------------------------------
# Logging — must go to stderr; stdout is the MCP JSON-RPC channel
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

gpu = GpuManager(config.data_dir)
budget = BudgetTracker(
    config.data_dir,
    aws_limit=config.backplane.aws_monthly_limit,
    azure_limit=config.backplane.azure_monthly_limit,
)
terraform = SubprocessTerraformBackend(config.terraform_dir, config.data_dir)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("agencyops")


@mcp.tool()
def query_backplane() -> dict[str, Any]:
    """Returns available infrastructure: Z230 hardware specs, GPU status, and cloud budgets.

    Use this to understand what resources are available before planning.
    """
    bp = config.backplane
    gpu_status = gpu.get_status()
    budget_status = budget.get_status()

    return {
        "physical": {
            "z230": {
                "cpu": bp.cpu,
                "ram_gb": bp.ram_gb,
                "gpu": {
                    "model": bp.gpu_model,
                    "vram_gb": bp.gpu_vram_gb,
                    "currently_locked": gpu_status.locked,
                    "locked_by": gpu_status.holder,
                    "lock_purpose": gpu_status.purpose,
                },
                "storage_gb": bp.storage_gb,
                "os": bp.os,
            }
        },
        "cloud_budgets": {
            "aws": {
                "monthly_limit": budget_status.aws.limit,
                "current_spend": budget_status.aws.spent,
                "remaining": budget_status.aws.remaining,
                "status": budget_status.aws.status,
                "currency": "USD",
            },
            "azure": {
                "monthly_limit": budget_status.azure.limit,
                "current_spend": budget_status.azure.spent,
                "remaining": budget_status.azure.remaining,
                "status": budget_status.azure.status,
                "currency": "USD",
            },
        },
    }


@mcp.tool()
def get_state() -> dict[str, Any]:
    """Queries Terraform state and returns all currently provisioned resources.

    Shows what infrastructure is currently running and managed by AgencyOps.
    """
    try:
        tf_state = terraform.show()
    except TerraformError as e:
        return {"error": str(e), "resources": [], "total_resources": 0, "gpu_available": not gpu.is_locked()}

    resources = []
    root_module = tf_state.get("values", {}).get("root_module", {})
    for res in root_module.get("resources", []):
        if res.get("type") == "docker_container":
            vals = res.get("values", {})
            labels = {l["label"]: l["value"] for l in vals.get("labels", [])}
            resources.append(
                ResourceState(
                    id=vals.get("id", res.get("address", "")),
                    type="docker_container",
                    image=vals.get("image", ""),
                    status="running" if vals.get("running", False) else "stopped",
                    gpu_locked=vals.get("runtime") == "nvidia",
                    memory_gb=vals.get("memory", 0) // 1024,
                    created_at=vals.get("created_at", "1970-01-01T00:00:00Z"),
                    purpose=labels.get("agencyops.purpose", ""),
                ).model_dump()
            )

    state = InfraState(
        resources=resources,
        total_resources=len(resources),
        gpu_available=not gpu.is_locked(),
    )
    return state.model_dump()


@mcp.tool()
def plan_resource(
    image: str,
    memory_gb: int,
    namespace: str,
    purpose: str,
    gpu_required: bool = False,
    type: str = "docker_container",
) -> dict[str, Any]:
    """Generates a Terraform plan with policy validation for a new resource.

    All infrastructure must justify its existence — a purpose is required.
    This creates a plan that must be explicitly applied via apply_plan().
    """
    # Policy validation
    purpose_check = "PASS" if purpose.strip() else "FAIL"
    gpu_check = "PASS" if (not gpu_required or not gpu.is_locked()) else "FAIL"

    # For MVP, local docker containers have zero cloud cost
    estimated_monthly = 0.0
    budget_check = "PASS"

    policy = PolicyValidation(
        budget_check=budget_check,
        gpu_check=gpu_check,
        purpose_check=purpose_check,
    )
    can_apply = all(v == "PASS" for v in [policy.budget_check, policy.gpu_check, policy.purpose_check])

    plan_id = generate_plan_id()

    # Generate actual Terraform plan (skip if policy already failed)
    container_name = f"{namespace}_{image.replace('/', '_').replace(':', '_')}"
    resource_diff = {"to_create": [], "to_modify": [], "to_destroy": []}
    if can_apply:
        try:
            tf_result = terraform.plan(
                plan_id,
                variables={
                    "containers": json.dumps({
                        container_name: {
                            "image": image,
                            "memory_mb": memory_gb * 1024,
                            "gpu_enabled": gpu_required,
                            "purpose": purpose,
                            "namespace": namespace,
                        }
                    })
                },
            )
            resource_diff = tf_result.get("changes", resource_diff)
        except TerraformError as e:
            logger.warning("Terraform plan failed: %s", e)
            resource_diff = {
                "to_create": [f"docker_container.workload[\"{container_name}\"]"],
                "to_modify": [],
                "to_destroy": [],
                "terraform_error": str(e),
            }

    plan = ResourcePlan(
        plan_id=plan_id,
        resource_diff=resource_diff,
        estimated_cost={
            "one_time": 0,
            "monthly": estimated_monthly,
            "notes": "Local resource, no cloud cost" if estimated_monthly == 0 else "",
        },
        resource_impact={
            "ram_gb": memory_gb,
            "gpu": gpu_required,
            "storage_gb": 10,
        },
        gpu_available=not gpu.is_locked(),
        policy_validation=policy,
        can_apply=can_apply,
    )
    return plan.model_dump()


@mcp.tool()
def apply_plan(plan_id: str) -> dict[str, Any]:
    """Executes a previously generated Terraform plan.

    Locks the GPU if the plan requires it. The plan must have been created
    by plan_resource() and must still be valid.
    """
    # Load plan metadata to check for GPU requirement
    meta_file = config.data_dir / "plans" / f"{plan_id}.json"
    gpu_requested = False
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            variables = meta.get("variables", {})
            containers_str = variables.get("containers", "{}")
            if isinstance(containers_str, str):
                containers = json.loads(containers_str)
            else:
                containers = containers_str
            gpu_requested = any(c.get("gpu_enabled", False) for c in containers.values())
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

    # Lock GPU if needed
    if gpu_requested:
        try:
            gpu.lock(holder="agencyops", purpose=f"Plan {plan_id}")
        except GpuLockError:
            return {"status": "failed", "message": "GPU is already locked", "plan_id": plan_id}

    # Apply the plan
    try:
        terraform.apply(plan_id)
    except TerraformError as e:
        if gpu_requested:
            gpu.unlock()
        return {"status": "failed", "message": str(e), "plan_id": plan_id}

    return {
        "status": "success",
        "plan_id": plan_id,
        "gpu_locked": gpu_requested,
        "message": "Infrastructure provisioned successfully",
    }


@mcp.tool()
def get_budget_status() -> dict[str, Any]:
    """Returns current budget tracking status for all cloud providers.

    Shows limits, spend, remaining budget, and projections.
    """
    return budget.get_status().model_dump()


@mcp.tool()
def delete_resource(resource_id: str, reason: str) -> dict[str, Any]:
    """Destroys a resource via Terraform and releases any associated GPU lock.

    Requires a reason — deletion decisions should be deliberate.
    """
    if not reason.strip():
        return {"status": "failed", "message": "A reason is required for resource deletion"}

    try:
        terraform.destroy(target=resource_id)
    except TerraformError as e:
        return {"status": "failed", "message": str(e)}

    # Release GPU if it was locked by this resource
    gpu_released = False
    if gpu.is_locked():
        gpu.unlock()
        gpu_released = True

    logger.info("Resource %s deleted. Reason: %s", resource_id, reason)

    return {
        "status": "success",
        "resource_id": resource_id,
        "gpu_released": gpu_released,
        "reason": reason,
        "message": "Resource deleted successfully",
    }


@mcp.tool()
def reconcile() -> dict[str, Any]:
    """Detects drift between Terraform state and actual infrastructure.

    Compares Terraform state vs running Docker containers and GPU lock state.
    Reports issues but does not auto-apply fixes.
    """
    issues: list[dict] = []

    # Get Terraform-managed containers
    tf_containers: dict[str, dict] = {}
    try:
        tf_state = terraform.show()
        root_module = tf_state.get("values", {}).get("root_module", {})
        for res in root_module.get("resources", []):
            if res.get("type") == "docker_container":
                vals = res.get("values", {})
                name = vals.get("name", "")
                tf_containers[name] = vals
    except TerraformError:
        issues.append(
            DriftIssue(
                type="terraform_error",
                details="Could not read Terraform state",
                recommended_action="Run terraform init or check backend configuration",
            ).model_dump()
        )

    # Get actual running Docker containers
    docker_containers: dict[str, dict] = {}
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "json", "--filter", "label=agencyops.managed=true"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            if line:
                try:
                    container = json.loads(line)
                    docker_containers[container.get("Names", "")] = container
                except json.JSONDecodeError:
                    continue
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append(
            DriftIssue(
                type="docker_error",
                details="Could not query Docker daemon",
                recommended_action="Ensure Docker is running and accessible",
            ).model_dump()
        )

    # Compare: containers in Docker but not in Terraform
    for name in docker_containers:
        if name not in tf_containers:
            issues.append(
                DriftIssue(
                    type="orphaned_container",
                    details=f"Container '{name}' running but not in Terraform state",
                    recommended_action="Import into state or terminate",
                ).model_dump()
            )

    # Compare: containers in Terraform but not in Docker
    for name in tf_containers:
        if name not in docker_containers:
            issues.append(
                DriftIssue(
                    type="missing_resource",
                    details=f"Terraform expects container '{name}' but it's not running",
                    recommended_action="Remove from state or re-provision",
                ).model_dump()
            )

    # Check GPU lock consistency
    gpu_status = gpu.get_status()
    gpu_containers = [n for n, v in tf_containers.items() if v.get("runtime") == "nvidia"]
    if gpu_status.locked and not gpu_containers:
        issues.append(
            DriftIssue(
                type="stale_gpu_lock",
                details="GPU is locked but no containers are using it",
                recommended_action="Release GPU lock",
            ).model_dump()
        )
    elif not gpu_status.locked and gpu_containers:
        issues.append(
            DriftIssue(
                type="missing_gpu_lock",
                details=f"Container(s) {gpu_containers} use GPU but lock is not held",
                recommended_action="Acquire GPU lock",
            ).model_dump()
        )

    result = ReconcileResult(drift_detected=len(issues) > 0, issues=issues)
    return result.model_dump()
