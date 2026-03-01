"""Tests for GPU atomic locking."""

import os
import subprocess
import sys

import pytest

from agencyops.gpu_manager import GpuLockError, GpuManager


@pytest.fixture()
def gpu(tmp_path):
    return GpuManager(tmp_path)


class TestGpuManager:
    def test_initially_unlocked(self, gpu):
        assert not gpu.is_locked()

    def test_lock_and_unlock(self, gpu):
        gpu.lock(holder="test", purpose="unit test")
        assert gpu.is_locked()

        gpu.unlock()
        assert not gpu.is_locked()

    def test_get_status_when_unlocked(self, gpu):
        status = gpu.get_status()
        assert not status.locked
        assert status.holder is None
        assert status.purpose is None

    def test_get_status_when_locked(self, gpu):
        gpu.lock(holder="claude", purpose="running inference")
        status = gpu.get_status()
        assert status.locked
        assert status.holder == "claude"
        assert status.purpose == "running inference"
        assert status.locked_at is not None
        gpu.unlock()

    def test_unlock_is_idempotent(self, gpu):
        # Unlocking when not locked should not raise
        gpu.unlock()
        gpu.unlock()

    def test_double_lock_from_another_process(self, tmp_path):
        """Verify that a second process cannot acquire the lock."""
        gpu1 = GpuManager(tmp_path)
        gpu1.lock(holder="process1", purpose="holding lock")

        # Use subprocess instead of multiprocessing to avoid pickle issues on macOS
        script = f"""
import sys
sys.path.insert(0, "src")
from agencyops.gpu_manager import GpuLockError, GpuManager
from pathlib import Path
try:
    gpu = GpuManager(Path("{tmp_path}"))
    gpu.lock(holder="process2", purpose="competing")
    print("acquired")
except GpuLockError:
    print("blocked")
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.stdout.strip() == "blocked"

        gpu1.unlock()

    def test_metadata_cleaned_on_unlock(self, gpu, tmp_path):
        gpu.lock(holder="test", purpose="check cleanup")
        meta_file = tmp_path / "gpu_meta.json"
        assert meta_file.exists()

        gpu.unlock()
        assert not meta_file.exists()
