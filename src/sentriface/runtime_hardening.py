from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable


MINIMUM_STARTUP_FREE_BYTES = 64 * 1024 * 1024
TEMPORARY_RETENTION_SECONDS = 24 * 60 * 60


class RuntimeReadinessError(RuntimeError):
    """Raised when the local runtime cannot start without weakening safety."""


class InstanceLock:
    """A non-blocking operating-system lock for one data authority."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / ".sentriface.instance.lock"
        self._handle = None

    def acquire(self) -> "InstanceLock":
        _require_managed_path(self.path.parent, self.path.parent)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeReadinessError("The instance lock location is unsafe")
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeReadinessError(
                "Another SentriFace process already owns this data store"
            ) from exc
        self._handle = handle
        return self

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> "InstanceLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()


def validate_managed_storage(
    data_dir: Path,
    managed_directories: Iterable[Path],
    *,
    minimum_free_bytes: int = MINIMUM_STARTUP_FREE_BYTES,
    disk_usage: Callable[[Path], object] = shutil.disk_usage,
) -> dict[str, int | bool]:
    """Validate server-owned roots without following symbolic-link authority."""
    root = data_dir.expanduser().absolute()
    if root.exists() and root.is_symlink():
        raise RuntimeReadinessError("The managed data directory cannot be a symbolic link")
    root.mkdir(parents=True, exist_ok=True)
    _write_probe(root)
    for directory in managed_directories:
        candidate = directory.expanduser().absolute()
        _require_managed_path(root, candidate)
        _reject_symlink_chain(root, candidate)
        candidate.mkdir(parents=True, exist_ok=True)
        _write_probe(candidate)
    free = int(getattr(disk_usage(root), "free"))
    if free < minimum_free_bytes:
        raise RuntimeReadinessError("Insufficient free space for safe runtime operation")
    return {"writable": True, "free_bytes": free}


def cleanup_managed_temporaries(
    roots: Iterable[Path],
    *,
    now: float | None = None,
) -> int:
    """Remove only old, recognized server temporary names from managed roots."""
    cutoff = (now if now is not None else time.time()) - TEMPORARY_RETENTION_SECONDS
    removed = 0
    for root in roots:
        if not root.exists() or root.is_symlink():
            continue
        for item in root.iterdir():
            if item.is_symlink() or not _temporary_name(item.name):
                continue
            try:
                if item.stat().st_mtime >= cutoff:
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removed += 1
            except FileNotFoundError:
                continue
    return removed


def _temporary_name(name: str) -> bool:
    return (
        name.startswith(".staging-")
        or name.startswith(".restore-")
        or (name.startswith(".") and name.endswith((".tmp", ".protected", ".encrypted")))
    )


def _write_probe(directory: Path) -> None:
    try:
        descriptor, raw = tempfile.mkstemp(prefix=".readiness-", suffix=".tmp", dir=directory)
        try:
            os.write(descriptor, b"ready")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            Path(raw).unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeReadinessError("Managed storage is not writable") from exc


def _require_managed_path(root: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeReadinessError("A managed storage location escaped its authority root") from exc


def _reject_symlink_chain(root: Path, candidate: Path) -> None:
    relative = candidate.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RuntimeReadinessError("A managed storage location contains a symbolic link")
