"""Tests for MCP tool logic.

These test the tool functions directly with mocked subsystems,
validating policy checks and response shapes. Azure-focused.
"""

from unittest.mock import patch


class TestQueryBackplane:
    def test_returns_expected_shape(self):
        from agencyops.server import query_backplane

        result = query_backplane()
        assert "azure" in result
        azure = result["azure"]
        assert "subscription_id" in azure
        assert "location" in azure
        assert "resource_group" in azure
        assert "budget" in azure
        assert "available_resources" in azure

    def test_budget_fields(self):
        from agencyops.server import query_backplane

        result = query_backplane()
        budget = result["azure"]["budget"]
        assert "monthly_limit" in budget
        assert "current_spend" in budget
        assert "remaining" in budget
        assert "currency" in budget


class TestPlanResource:
    @patch("agencyops.server.terraform")
    def test_purpose_required(self, mock_tf):
        from agencyops.server import plan_resource

        mock_tf.plan.side_effect = Exception("should not reach terraform")
        result = plan_resource(
            image="nginx",
            namespace="test",
            purpose="",
        )
        assert result["policy_validation"]["purpose_check"] == "FAIL"
        assert result["can_apply"] is False

    @patch("agencyops.server.terraform")
    def test_budget_check_fails_when_exhausted(self, mock_tf):
        from agencyops.server import budget, plan_resource

        # Exhaust the budget
        budget.add_cost(150.0)
        try:
            result = plan_resource(
                image="nginx",
                namespace="test",
                purpose="testing budget exhaustion",
            )
            assert result["policy_validation"]["budget_check"] == "FAIL"
            assert result["can_apply"] is False
        finally:
            budget.remove_cost(150.0)

    @patch("agencyops.server.terraform")
    def test_valid_plan_can_apply(self, mock_tf):
        from agencyops.server import plan_resource

        mock_tf.plan.return_value = {
            "changes": {"to_create": ["azurerm_container_group.workload"], "to_modify": [], "to_destroy": []}
        }

        result = plan_resource(
            image="nginx",
            namespace="test",
            purpose="web server for testing",
        )
        assert result["policy_validation"]["purpose_check"] == "PASS"
        assert result["policy_validation"]["budget_check"] == "PASS"
        assert result["policy_validation"]["quota_check"] == "PASS"
        assert result["can_apply"] is True
        assert result["plan_id"].startswith("plan_")

    @patch("agencyops.server.terraform")
    def test_cost_estimation_included(self, mock_tf):
        from agencyops.server import plan_resource

        mock_tf.plan.return_value = {"changes": {"to_create": [], "to_modify": [], "to_destroy": []}}

        result = plan_resource(
            image="nginx",
            cpu=2.0,
            memory_gb=4.0,
            namespace="test",
            purpose="testing cost estimation",
        )
        cost = result["estimated_cost"]
        assert "monthly" in cost
        assert cost["monthly"] > 0
        assert "breakdown" in cost


class TestGetBudgetStatus:
    def test_returns_azure(self):
        from agencyops.server import get_budget_status

        result = get_budget_status()
        assert "azure" in result
        assert result["azure"]["limit"] == 150.0


class TestDeleteResource:
    @patch("agencyops.server.terraform")
    def test_reason_required(self, mock_tf):
        from agencyops.server import delete_resource

        result = delete_resource(resource_id="some_id", reason="")
        assert result["status"] == "failed"
        assert "reason" in result["message"].lower()
        mock_tf.destroy.assert_not_called()

    @patch("agencyops.server.terraform")
    def test_successful_deletion(self, mock_tf):
        from agencyops.server import delete_resource

        mock_tf.destroy.return_value = {"status": "success"}
        result = delete_resource(
            resource_id="azurerm_container_group.workload[\"test\"]",
            reason="no longer needed",
        )
        assert result["status"] == "success"
        assert result["reason"] == "no longer needed"
