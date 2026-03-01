"""Tests for MCP tool logic.

These test the tool functions directly with mocked subsystems,
validating policy checks and response shapes.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestQueryBackplane:
    def test_returns_expected_shape(self):
        from agencyops.mcp_server import query_backplane

        result = query_backplane()
        assert "physical" in result
        assert "cloud_budgets" in result
        assert "z230" in result["physical"]
        z230 = result["physical"]["z230"]
        assert "cpu" in z230
        assert "ram_gb" in z230
        assert "gpu" in z230
        assert "currently_locked" in z230["gpu"]

    def test_budget_fields(self):
        from agencyops.mcp_server import query_backplane

        result = query_backplane()
        for provider in ["aws", "azure"]:
            budget = result["cloud_budgets"][provider]
            assert "monthly_limit" in budget
            assert "current_spend" in budget
            assert "currency" in budget


class TestPlanResource:
    @patch("agencyops.mcp_server.terraform")
    def test_purpose_required(self, mock_tf):
        from agencyops.mcp_server import plan_resource

        mock_tf.plan.side_effect = Exception("should not reach terraform")
        result = plan_resource(
            image="nginx",
            memory_gb=4,
            namespace="test",
            purpose="",  # empty purpose
        )
        assert result["policy_validation"]["purpose_check"] == "FAIL"
        assert result["can_apply"] is False

    @patch("agencyops.mcp_server.terraform")
    def test_gpu_check_fails_when_locked(self, mock_tf):
        from agencyops.mcp_server import gpu, plan_resource

        mock_tf.plan.return_value = {"changes": {"to_create": [], "to_modify": [], "to_destroy": []}}

        gpu.lock(holder="other", purpose="testing")
        try:
            result = plan_resource(
                image="ollama/ollama",
                memory_gb=8,
                namespace="test",
                purpose="inference",
                gpu_required=True,
            )
            assert result["policy_validation"]["gpu_check"] == "FAIL"
            assert result["can_apply"] is False
        finally:
            gpu.unlock()

    @patch("agencyops.mcp_server.terraform")
    def test_valid_plan_can_apply(self, mock_tf):
        from agencyops.mcp_server import plan_resource

        mock_tf.plan.return_value = {
            "changes": {"to_create": ["docker_container.workload"], "to_modify": [], "to_destroy": []}
        }

        result = plan_resource(
            image="nginx",
            memory_gb=4,
            namespace="test",
            purpose="web server for testing",
        )
        assert result["policy_validation"]["purpose_check"] == "PASS"
        assert result["policy_validation"]["budget_check"] == "PASS"
        assert result["policy_validation"]["gpu_check"] == "PASS"
        assert result["can_apply"] is True
        assert result["plan_id"].startswith("plan_")


class TestGetBudgetStatus:
    def test_returns_both_providers(self):
        from agencyops.mcp_server import get_budget_status

        result = get_budget_status()
        assert "aws" in result
        assert "azure" in result
        assert result["aws"]["limit"] == 150.0
        assert result["azure"]["limit"] == 150.0


class TestDeleteResource:
    @patch("agencyops.mcp_server.terraform")
    def test_reason_required(self, mock_tf):
        from agencyops.mcp_server import delete_resource

        result = delete_resource(resource_id="some_id", reason="")
        assert result["status"] == "failed"
        assert "reason" in result["message"].lower()
        mock_tf.destroy.assert_not_called()

    @patch("agencyops.mcp_server.terraform")
    def test_successful_deletion(self, mock_tf):
        from agencyops.mcp_server import delete_resource

        mock_tf.destroy.return_value = {"status": "success"}
        result = delete_resource(resource_id="docker_container.test", reason="no longer needed")
        assert result["status"] == "success"
        assert result["reason"] == "no longer needed"
