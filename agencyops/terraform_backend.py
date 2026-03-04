"""Terraform subprocess management.

Wraps the Terraform CLI with structured input/output. Uses a Protocol to
enable testing without real Terraform.
"""

from __future__ import annotations

import json
import logging
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class TerraformError(Exception):
    """Raised when a Terraform command fails."""

    def __init__(self, message: str, returncode: int = 1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@runtime_checkable
class TerraformBackend(Protocol):
    """Protocol for Terraform operations — enables testing without real Terraform."""

    def init(self) -> None: ...
    def show(self) -> dict: ...
    def plan(self, plan_id: str, variables: dict[str, Any] | None = None) -> dict: ...
    def apply(self, plan_id: str) -> dict: ...
    def destroy(self, target: str) -> dict: ...


class SubprocessTerraformBackend:
    """Real Terraform via subprocess."""

    def __init__(self, terraform_dir: Path, data_dir: Path, timeout: int = 300) -> None:
        self._tf_dir = terraform_dir
        self._plans_dir = data_dir / "plans"
        self._timeout = timeout

    def _ensure_dirs(self) -> None:
        self._plans_dir.mkdir(parents=True, exist_ok=True)

    def _run(self, args: list[str], *, json_output: bool = False) -> subprocess.CompletedProcess:
        cmd = ["terraform"] + args
        logger.info("Running: %s (cwd=%s)", " ".join(cmd), self._tf_dir)

        result = subprocess.run(
            cmd,
            cwd=str(self._tf_dir),
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )

        if result.returncode != 0:
            logger.error("Terraform failed: %s", result.stderr)
            raise TerraformError(
                f"terraform {args[0]} failed (exit {result.returncode})",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return result

    def init(self) -> None:
        """Run terraform init."""
        self._run(["init", "-input=false"])

    def show(self) -> dict:
        """Run terraform show -json and return parsed state."""
        result = self._run(["show", "-json"])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"values": {"root_module": {"resources": []}}}

    def plan(self, plan_id: str, variables: dict[str, Any] | None = None) -> dict:
        """Generate a Terraform plan and save it for later apply."""
        self._ensure_dirs()
        plan_file = self._plans_dir / f"{plan_id}.tfplan"

        args = ["plan", "-input=false", f"-out={plan_file}", "-json"]
        for key, value in (variables or {}).items():
            args.append(f"-var={key}={value}")

        result = self._run(args)

        # Save plan metadata
        meta = {
            "plan_id": plan_id,
            "plan_file": str(plan_file),
            "created_at": datetime.now(UTC).isoformat(),
            "variables": variables or {},
        }
        meta_file = self._plans_dir / f"{plan_id}.json"
        meta_file.write_text(json.dumps(meta, indent=2))

        # Parse terraform plan JSON output (line-delimited JSON)
        changes = {"to_create": [], "to_modify": [], "to_destroy": []}
        for line in result.stdout.strip().splitlines():
            try:
                entry = json.loads(line)
                if entry.get("type") == "resource_drift" or entry.get("type") == "planned_change":
                    change = entry.get("change", {})
                    resource = change.get("resource", {})
                    addr = resource.get("addr", "unknown")
                    action = change.get("action", "")
                    if action == "create":
                        changes["to_create"].append(addr)
                    elif action in ("update", "replace"):
                        changes["to_modify"].append(addr)
                    elif action == "delete":
                        changes["to_destroy"].append(addr)
            except json.JSONDecodeError:
                continue

        return {"plan_id": plan_id, "plan_file": str(plan_file), "changes": changes}

    def apply(self, plan_id: str) -> dict:
        """Apply a previously saved plan."""
        plan_file = self._plans_dir / f"{plan_id}.tfplan"
        if not plan_file.exists():
            raise TerraformError(f"Plan file not found: {plan_id}")

        self._run(["apply", "-input=false", "-json", str(plan_file)])
        return {"status": "success", "plan_id": plan_id}

    def destroy(self, target: str) -> dict:
        """Destroy a specific resource by its Terraform address."""
        self._run(["destroy", "-input=false", "-auto-approve", f"-target={target}"])
        return {"status": "success", "target": target}


def generate_plan_id() -> str:
    """Generate a unique plan ID."""
    return f"plan_{uuid.uuid4().hex[:12]}"
