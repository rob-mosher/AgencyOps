"""Data models for AgencyOps.

All Pydantic models used across the system — configuration, resource planning,
state tracking, budgets, and drift reconciliation. Azure-focused.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class AzureBackplaneConfig(BaseModel):
    """Azure subscription as the infrastructure backplane."""

    subscription_id: str = Field(default="")
    location: str = Field(default="eastus")
    resource_group: str = Field(default="agencyops-workloads")
    monthly_limit: float = Field(default=150.0)


class AgencyOpsConfig(BaseModel):
    """Top-level configuration for the AgencyOps server."""

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".agencyops")
    terraform_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "terraform" / "workloads")
    backplane: AzureBackplaneConfig = Field(default_factory=AzureBackplaneConfig)
    api_key: str = Field(default="")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    @classmethod
    def from_env(cls) -> AgencyOpsConfig:
        """Build config from environment variables with sensible defaults."""
        kwargs: dict = {}
        if data_dir := os.environ.get("AGENCYOPS_DATA_DIR"):
            kwargs["data_dir"] = Path(data_dir)
        if terraform_dir := os.environ.get("AGENCYOPS_TERRAFORM_DIR"):
            kwargs["terraform_dir"] = Path(terraform_dir)
        if api_key := os.environ.get("AGENCYOPS_API_KEY"):
            kwargs["api_key"] = api_key
        if host := os.environ.get("AGENCYOPS_HOST"):
            kwargs["host"] = host
        if port := os.environ.get("AGENCYOPS_PORT"):
            kwargs["port"] = int(port)

        bp_kwargs: dict = {}
        if v := os.environ.get("AGENCYOPS_AZURE_SUBSCRIPTION_ID"):
            bp_kwargs["subscription_id"] = v
        if v := os.environ.get("AGENCYOPS_AZURE_LOCATION"):
            bp_kwargs["location"] = v
        if v := os.environ.get("AGENCYOPS_AZURE_RESOURCE_GROUP"):
            bp_kwargs["resource_group"] = v
        if v := os.environ.get("AGENCYOPS_AZURE_MONTHLY_LIMIT"):
            bp_kwargs["monthly_limit"] = float(v)
        if bp_kwargs:
            kwargs["backplane"] = AzureBackplaneConfig(**bp_kwargs)

        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Resource planning
# ---------------------------------------------------------------------------

class ResourceRequest(BaseModel):
    """Input to the plan_resource tool."""

    type: Literal["container_instance"] = "container_instance"
    image: str
    cpu: float = Field(default=1.0, description="Number of vCPUs")
    memory_gb: float = Field(default=1.5, description="Memory in GB")
    gpu_sku: str | None = Field(default=None, description="GPU SKU (e.g., K80, V100)")
    gpu_count: int = Field(default=0, description="Number of GPUs")
    namespace: str
    purpose: str = Field(min_length=1, description="All infrastructure must justify its existence")


class PolicyValidation(BaseModel):
    """Results of pre-apply policy checks."""

    budget_check: Literal["PASS", "FAIL"]
    purpose_check: Literal["PASS", "FAIL"]
    quota_check: Literal["PASS", "FAIL"]


class ResourcePlan(BaseModel):
    """Output of the plan_resource tool."""

    plan_id: str
    resource_diff: dict
    estimated_cost: dict
    resource_impact: dict
    policy_validation: PolicyValidation
    can_apply: bool


# ---------------------------------------------------------------------------
# Infrastructure state
# ---------------------------------------------------------------------------

class ResourceState(BaseModel):
    """A single managed resource."""

    id: str
    type: str
    name: str
    image: str | None = None
    status: str
    location: str
    cpu: float | None = None
    memory_gb: float | None = None
    gpu_sku: str | None = None
    created_at: datetime
    purpose: str


class InfraState(BaseModel):
    """Output of the get_state tool."""

    resources: list[ResourceState]
    total_resources: int


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class ProviderBudget(BaseModel):
    """Budget status for a cloud provider."""

    limit: float
    spent: float
    remaining: float
    projected_month_end: float
    status: Literal["OK", "WARNING", "EXHAUSTED"]


class BudgetStatus(BaseModel):
    """Output of the get_budget_status tool."""

    azure: ProviderBudget


# ---------------------------------------------------------------------------
# Drift reconciliation
# ---------------------------------------------------------------------------

class DriftIssue(BaseModel):
    """A single drift issue detected during reconciliation."""

    type: str
    details: str
    recommended_action: str


class ReconcileResult(BaseModel):
    """Output of the reconcile tool."""

    drift_detected: bool
    issues: list[DriftIssue]


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

ACI_PRICING = {
    "cpu_per_vcpu_month": 35.04,
    "memory_per_gb_month": 3.89,
    "gpu_per_month": {
        "K80": 648.0,
        "V100": 1548.0,
    },
}


def estimate_monthly_cost(
    cpu: float,
    memory_gb: float,
    gpu_sku: str | None = None,
    gpu_count: int = 0,
) -> float:
    """Estimate monthly cost for an Azure Container Instance."""
    cost = cpu * ACI_PRICING["cpu_per_vcpu_month"]
    cost += memory_gb * ACI_PRICING["memory_per_gb_month"]
    if gpu_sku and gpu_count > 0:
        cost += gpu_count * ACI_PRICING["gpu_per_month"].get(gpu_sku, 0)
    return round(cost, 2)
