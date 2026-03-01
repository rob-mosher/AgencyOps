"""Data models for AgencyOps.

All Pydantic models used across the system — configuration, resource planning,
state tracking, budgets, GPU status, and drift reconciliation.
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

class BackplaneConfig(BaseModel):
    """Hardware specs and cloud budgets for the Z230 backplane."""

    cpu: str = Field(default="Intel Xeon (4 cores, 8 threads)")
    ram_gb: int = Field(default=32)
    gpu_model: str = Field(default="NVIDIA GTX 1060")
    gpu_vram_gb: int = Field(default=6)
    storage_gb: int = Field(default=1000)
    os: str = Field(default="Ubuntu 24.04 LTS")
    aws_monthly_limit: float = Field(default=150.0)
    azure_monthly_limit: float = Field(default=150.0)


class AgencyOpsConfig(BaseModel):
    """Top-level configuration for the AgencyOps server."""

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".agencyops")
    terraform_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2] / "terraform")
    backplane: BackplaneConfig = Field(default_factory=BackplaneConfig)

    @classmethod
    def from_env(cls) -> AgencyOpsConfig:
        """Build config from environment variables with sensible defaults."""
        kwargs: dict = {}
        if data_dir := os.environ.get("AGENCYOPS_DATA_DIR"):
            kwargs["data_dir"] = Path(data_dir)
        if terraform_dir := os.environ.get("AGENCYOPS_TERRAFORM_DIR"):
            kwargs["terraform_dir"] = Path(terraform_dir)

        bp_kwargs: dict = {}
        if v := os.environ.get("AGENCYOPS_AWS_MONTHLY_LIMIT"):
            bp_kwargs["aws_monthly_limit"] = float(v)
        if v := os.environ.get("AGENCYOPS_AZURE_MONTHLY_LIMIT"):
            bp_kwargs["azure_monthly_limit"] = float(v)
        if bp_kwargs:
            kwargs["backplane"] = BackplaneConfig(**bp_kwargs)

        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Resource planning
# ---------------------------------------------------------------------------

class ResourceRequest(BaseModel):
    """Input to the plan_resource tool."""

    type: Literal["docker_container"] = "docker_container"
    image: str
    gpu: bool = False
    memory_gb: int
    namespace: str
    purpose: str = Field(min_length=1, description="All infrastructure must justify its existence")


class PolicyValidation(BaseModel):
    """Results of pre-apply policy checks."""

    budget_check: Literal["PASS", "FAIL"]
    gpu_check: Literal["PASS", "FAIL"]
    purpose_check: Literal["PASS", "FAIL"]


class ResourcePlan(BaseModel):
    """Output of the plan_resource tool."""

    plan_id: str
    resource_diff: dict
    estimated_cost: dict
    resource_impact: dict
    gpu_available: bool
    policy_validation: PolicyValidation
    can_apply: bool


# ---------------------------------------------------------------------------
# Infrastructure state
# ---------------------------------------------------------------------------

class ResourceState(BaseModel):
    """A single managed resource."""

    id: str
    type: str
    image: str
    status: str
    gpu_locked: bool
    memory_gb: int
    created_at: datetime
    purpose: str


class InfraState(BaseModel):
    """Output of the get_state tool."""

    resources: list[ResourceState]
    total_resources: int
    gpu_available: bool


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class ProviderBudget(BaseModel):
    """Budget status for a single cloud provider."""

    limit: float
    spent: float
    remaining: float
    projected_month_end: float
    status: Literal["OK", "WARNING", "EXHAUSTED"]


class BudgetStatus(BaseModel):
    """Output of the get_budget_status tool."""

    aws: ProviderBudget
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
# GPU status
# ---------------------------------------------------------------------------

class GpuStatus(BaseModel):
    """Current state of the GPU lock."""

    locked: bool
    holder: str | None = None
    purpose: str | None = None
    locked_at: datetime | None = None
