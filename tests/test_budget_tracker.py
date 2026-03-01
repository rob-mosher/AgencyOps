"""Tests for budget tracking."""

import pytest

from agencyops.budget_tracker import BudgetTracker


@pytest.fixture()
def tracker(tmp_path):
    return BudgetTracker(tmp_path, aws_limit=150.0, azure_limit=150.0)


class TestBudgetTracker:
    def test_initial_status(self, tracker):
        status = tracker.get_status()
        assert status.aws.limit == 150.0
        assert status.aws.spent == 0.0
        assert status.aws.remaining == 150.0
        assert status.aws.status == "OK"
        assert status.azure.limit == 150.0
        assert status.azure.spent == 0.0

    def test_add_cost(self, tracker):
        tracker.add_cost("aws", 25.0)
        status = tracker.get_status()
        assert status.aws.spent == 25.0
        assert status.aws.remaining == 125.0

    def test_add_cost_cumulative(self, tracker):
        tracker.add_cost("aws", 10.0)
        tracker.add_cost("aws", 15.0)
        status = tracker.get_status()
        assert status.aws.spent == 25.0

    def test_remove_cost(self, tracker):
        tracker.add_cost("azure", 50.0)
        tracker.remove_cost("azure", 20.0)
        status = tracker.get_status()
        assert status.azure.spent == 30.0

    def test_remove_cost_does_not_go_negative(self, tracker):
        tracker.remove_cost("aws", 100.0)
        status = tracker.get_status()
        assert status.aws.spent == 0.0

    def test_check_budget_passes(self, tracker):
        assert tracker.check_budget("aws", 100.0) is True

    def test_check_budget_fails_when_exhausted(self, tracker):
        tracker.add_cost("aws", 140.0)
        assert tracker.check_budget("aws", 20.0) is False

    def test_check_budget_exact_limit(self, tracker):
        assert tracker.check_budget("aws", 150.0) is True
        assert tracker.check_budget("aws", 150.01) is False

    def test_exhausted_status(self, tracker):
        tracker.add_cost("aws", 150.0)
        status = tracker.get_status()
        assert status.aws.status == "EXHAUSTED"
        assert status.aws.remaining == 0.0

    def test_warning_status(self, tracker):
        tracker.add_cost("aws", 125.0)  # 25 remaining = ~17% < 20%
        status = tracker.get_status()
        assert status.aws.status == "WARNING"

    def test_persistence_across_instances(self, tmp_path):
        tracker1 = BudgetTracker(tmp_path, aws_limit=150.0, azure_limit=150.0)
        tracker1.add_cost("aws", 42.0)

        tracker2 = BudgetTracker(tmp_path, aws_limit=150.0, azure_limit=150.0)
        status = tracker2.get_status()
        assert status.aws.spent == 42.0

    def test_providers_independent(self, tracker):
        tracker.add_cost("aws", 50.0)
        status = tracker.get_status()
        assert status.aws.spent == 50.0
        assert status.azure.spent == 0.0
