"""Tests for Terraform backend (mocked subprocess)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agencyops.terraform_backend import (
    SubprocessTerraformBackend,
    TerraformError,
    generate_plan_id,
)


@pytest.fixture()
def backend(tmp_path):
    tf_dir = tmp_path / "terraform"
    tf_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return SubprocessTerraformBackend(tf_dir, data_dir)


class TestGeneratePlanId:
    def test_format(self):
        plan_id = generate_plan_id()
        assert plan_id.startswith("plan_")
        assert len(plan_id) == 17  # "plan_" + 12 hex chars

    def test_uniqueness(self):
        ids = {generate_plan_id() for _ in range(100)}
        assert len(ids) == 100


class TestSubprocessTerraformBackend:
    @patch("agencyops.terraform_backend.subprocess.run")
    def test_init_calls_terraform(self, mock_run, backend):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        backend.init()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["terraform", "init", "-input=false"]

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_show_parses_json(self, mock_run, backend):
        state = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "type": "azurerm_container_group",
                            "values": {"name": "test", "id": "abc123"},
                        }
                    ]
                }
            }
        }
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(state), stderr=""
        )
        result = backend.show()
        assert result["values"]["root_module"]["resources"][0]["values"]["name"] == "test"

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_show_handles_empty_state(self, mock_run, backend):
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = backend.show()
        assert "values" not in result or result == {}

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_plan_creates_metadata_file(self, mock_run, backend, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = backend.plan("test_plan_001", variables={"foo": "bar"})
        assert result["plan_id"] == "test_plan_001"

        meta_file = tmp_path / "data" / "plans" / "test_plan_001.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert meta["variables"]["foo"] == "bar"

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_plan_parses_changes(self, mock_run, backend):
        plan_output = json.dumps({
            "type": "planned_change",
            "change": {
                "resource": {"addr": "azurerm_container_group.workload[\"test\"]"},
                "action": "create",
            },
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=plan_output, stderr="")
        result = backend.plan("test_plan_002")
        assert "azurerm_container_group.workload[\"test\"]" in result["changes"]["to_create"]

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_apply_requires_plan_file(self, mock_run, backend):
        with pytest.raises(TerraformError, match="Plan file not found"):
            backend.apply("nonexistent_plan")

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_apply_executes_plan(self, mock_run, backend, tmp_path):
        # Create a plan file
        plans_dir = tmp_path / "data" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "my_plan.tfplan").write_text("binary plan data")

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = backend.apply("my_plan")
        assert result["status"] == "success"

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_destroy_targets_resource(self, mock_run, backend):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = backend.destroy("azurerm_container_group.workload[\"test\"]")
        assert result["status"] == "success"
        args = mock_run.call_args[0][0]
        assert "-target=azurerm_container_group.workload[\"test\"]" in args

    @patch("agencyops.terraform_backend.subprocess.run")
    def test_terraform_error_raised_on_failure(self, mock_run, backend):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: something went wrong"
        )
        with pytest.raises(TerraformError):
            backend.init()
