"""Tests for Azure budget tracking."""

import pytest

from agencyops.budget_tracker import BudgetTracker


@pytest.fixture()
def tracker(tmp_path):
    return BudgetTracker(tmp_path, azure_limit=150.0)


class TestBudgetTracker:
    def test_initial_status(self, tracker):
        status = tracker.get_status()
        assert status.azure.limit == 150.0
        assert status.azure.spent == 0.0
        assert status.azure.remaining == 150.0
        assert status.azure.status == "OK"

    def test_add_cost(self, tracker):
        tracker.add_cost(25.0)
        status = tracker.get_status()
        assert status.azure.spent == 25.0
        assert status.azure.remaining == 125.0

    def test_add_cost_cumulative(self, tracker):
        tracker.add_cost(10.0)
        tracker.add_cost(15.0)
        status = tracker.get_status()
        assert status.azure.spent == 25.0

    def test_remove_cost(self, tracker):
        tracker.add_cost(50.0)
        tracker.remove_cost(20.0)
        status = tracker.get_status()
        assert status.azure.spent == 30.0

    def test_remove_cost_does_not_go_negative(self, tracker):
        tracker.remove_cost(100.0)
        status = tracker.get_status()
        assert status.azure.spent == 0.0

    def test_check_budget_passes(self, tracker):
        assert tracker.check_budget(100.0) is True

    def test_check_budget_fails_when_exhausted(self, tracker):
        tracker.add_cost(140.0)
        assert tracker.check_budget(20.0) is False

    def test_check_budget_exact_limit(self, tracker):
        assert tracker.check_budget(150.0) is True
        assert tracker.check_budget(150.01) is False

    def test_exhausted_status(self, tracker):
        tracker.add_cost(150.0)
        status = tracker.get_status()
        assert status.azure.status == "EXHAUSTED"
        assert status.azure.remaining == 0.0

    def test_warning_status(self, tracker):
        tracker.add_cost(125.0)
        status = tracker.get_status()
        assert status.azure.status == "WARNING"

    def test_persistence_across_instances(self, tmp_path):
        tracker1 = BudgetTracker(tmp_path, azure_limit=150.0)
        tracker1.add_cost(42.0)

        tracker2 = BudgetTracker(tmp_path, azure_limit=150.0)
        status = tracker2.get_status()
        assert status.azure.spent == 42.0
