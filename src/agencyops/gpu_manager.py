"""GPU atomic locking manager.

Uses fcntl.flock for mutual exclusion and a companion JSON metadata file
to track who holds the lock and why.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from agencyops.models import GpuStatus

logger = logging.getLogger(__name__)


class GpuLockError(Exception):
    """Raised when the GPU cannot be locked (already in use)."""


class GpuManager:
    """Manages atomic GPU locking via file-based locks."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._lock_file = data_dir / "gpu.lock"
        self._meta_file = data_dir / "gpu_meta.json"
        self._fd: int | None = None

    def _ensure_dir(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def lock(self, holder: str, purpose: str) -> None:
        """Acquire exclusive GPU lock. Raises GpuLockError if already locked."""
        self._ensure_dir()
        fd = os.open(str(self._lock_file), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise GpuLockError("GPU is already locked by another process")

        self._fd = fd
        meta = {
            "holder": holder,
            "purpose": purpose,
            "locked_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
        }
        self._meta_file.write_text(json.dumps(meta, indent=2))
        logger.info("GPU locked by %s: %s", holder, purpose)

    def unlock(self) -> None:
        """Release GPU lock and clean up metadata."""
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

        if self._meta_file.exists():
            self._meta_file.unlink()
        logger.info("GPU unlocked")

    def is_locked(self) -> bool:
        """Check if GPU is currently locked by any process."""
        self._ensure_dir()
        try:
            fd = os.open(str(self._lock_file), os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # We got the lock — GPU is free. Release immediately.
                fcntl.flock(fd, fcntl.LOCK_UN)
                return False
            except BlockingIOError:
                return True
            finally:
                os.close(fd)
        except OSError:
            return False

    def get_status(self) -> GpuStatus:
        """Return current GPU lock status with metadata."""
        locked = self.is_locked()
        if locked and self._meta_file.exists():
            try:
                meta = json.loads(self._meta_file.read_text())
                return GpuStatus(
                    locked=True,
                    holder=meta.get("holder"),
                    purpose=meta.get("purpose"),
                    locked_at=meta.get("locked_at"),
                )
            except (json.JSONDecodeError, KeyError):
                return GpuStatus(locked=True)
        return GpuStatus(locked=locked)
