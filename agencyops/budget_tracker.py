"""Budget tracker for Azure spend.

Tracks estimated cloud spend in a local JSON file. Hard-stops new provisioning
when budget is exhausted.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agencyops.models import BudgetStatus, ProviderBudget

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when the budget is fully consumed."""


class BudgetTracker:
    """Tracks Azure spending against a monthly limit."""

    def __init__(self, data_dir: Path, azure_limit: float = 150.0) -> None:
        self._data_dir = data_dir
        self._budget_file = data_dir / "budget.json"
        self._limit = azure_limit

    def _ensure_dir(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        if self._budget_file.exists():
            try:
                return json.loads(self._budget_file.read_text())
            except (json.JSONDecodeError, KeyError):
                pass
        return {"azure": {"spent": 0.0}}

    def _write_state(self, state: dict) -> None:
        self._ensure_dir()
        self._budget_file.write_text(json.dumps(state, indent=2))

    def _compute_budget(self, spent: float) -> ProviderBudget:
        remaining = max(0.0, self._limit - spent)

        now = datetime.now(UTC)
        day_of_month = now.day
        days_in_month = 30
        if day_of_month > 0:
            projected = (spent / day_of_month) * days_in_month
        else:
            projected = 0.0

        if remaining <= 0:
            status = "EXHAUSTED"
        elif remaining < self._limit * 0.2:
            status = "WARNING"
        else:
            status = "OK"

        return ProviderBudget(
            limit=self._limit,
            spent=round(spent, 2),
            remaining=round(remaining, 2),
            projected_month_end=round(projected, 2),
            status=status,
        )

    def get_status(self) -> BudgetStatus:
        """Return current budget status."""
        state = self._read_state()
        return BudgetStatus(
            azure=self._compute_budget(state["azure"]["spent"]),
        )

    def add_cost(self, amount: float) -> None:
        """Record a cost against the budget."""
        state = self._read_state()
        state["azure"]["spent"] = state["azure"].get("spent", 0.0) + amount
        self._write_state(state)
        logger.info("Added $%.2f to Azure (total: $%.2f)", amount, state["azure"]["spent"])

    def remove_cost(self, amount: float) -> None:
        """Remove a cost (e.g. when deleting a resource)."""
        state = self._read_state()
        state["azure"]["spent"] = max(0.0, state["azure"].get("spent", 0.0) - amount)
        self._write_state(state)
        logger.info("Removed $%.2f from Azure (total: $%.2f)", amount, state["azure"]["spent"])

    def check_budget(self, estimated_cost: float) -> bool:
        """Return True if there is enough budget remaining."""
        state = self._read_state()
        spent = state["azure"].get("spent", 0.0)
        remaining = self._limit - spent
        return estimated_cost <= remaining
