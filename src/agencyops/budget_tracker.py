"""Mock budget tracker for MVP.

Tracks estimated cloud spend in a local JSON file. Hard-stops new provisioning
when a provider's budget is exhausted.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agencyops.models import BudgetStatus, ProviderBudget

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when a provider's budget is fully consumed."""


class BudgetTracker:
    """Tracks mock cloud spending against monthly limits."""

    def __init__(
        self,
        data_dir: Path,
        aws_limit: float = 150.0,
        azure_limit: float = 150.0,
    ) -> None:
        self._data_dir = data_dir
        self._budget_file = data_dir / "budget.json"
        self._limits = {"aws": aws_limit, "azure": azure_limit}

    def _ensure_dir(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        if self._budget_file.exists():
            try:
                return json.loads(self._budget_file.read_text())
            except (json.JSONDecodeError, KeyError):
                pass
        return {"aws": {"spent": 0.0}, "azure": {"spent": 0.0}}

    def _write_state(self, state: dict) -> None:
        self._ensure_dir()
        self._budget_file.write_text(json.dumps(state, indent=2))

    def _compute_provider_budget(self, provider: str, spent: float) -> ProviderBudget:
        limit = self._limits[provider]
        remaining = max(0.0, limit - spent)

        # Naive month-end projection: linear extrapolation from spend so far
        now = datetime.now(UTC)
        day_of_month = now.day
        days_in_month = 30  # simplification for MVP
        if day_of_month > 0:
            projected = (spent / day_of_month) * days_in_month
        else:
            projected = 0.0

        if remaining <= 0:
            status = "EXHAUSTED"
        elif remaining < limit * 0.2:
            status = "WARNING"
        else:
            status = "OK"

        return ProviderBudget(
            limit=limit,
            spent=round(spent, 2),
            remaining=round(remaining, 2),
            projected_month_end=round(projected, 2),
            status=status,
        )

    def get_status(self) -> BudgetStatus:
        """Return current budget status for all providers."""
        state = self._read_state()
        return BudgetStatus(
            aws=self._compute_provider_budget("aws", state["aws"]["spent"]),
            azure=self._compute_provider_budget("azure", state["azure"]["spent"]),
        )

    def add_cost(self, provider: str, amount: float) -> None:
        """Record a cost against a provider's budget."""
        state = self._read_state()
        state[provider]["spent"] = state[provider].get("spent", 0.0) + amount
        self._write_state(state)
        logger.info("Added $%.2f to %s (total: $%.2f)", amount, provider, state[provider]["spent"])

    def remove_cost(self, provider: str, amount: float) -> None:
        """Remove a cost (e.g. when deleting a resource)."""
        state = self._read_state()
        state[provider]["spent"] = max(0.0, state[provider].get("spent", 0.0) - amount)
        self._write_state(state)
        logger.info("Removed $%.2f from %s (total: $%.2f)", amount, provider, state[provider]["spent"])

    def check_budget(self, provider: str, estimated_cost: float) -> bool:
        """Return True if the provider has enough budget remaining."""
        state = self._read_state()
        spent = state[provider].get("spent", 0.0)
        remaining = self._limits[provider] - spent
        return estimated_cost <= remaining
