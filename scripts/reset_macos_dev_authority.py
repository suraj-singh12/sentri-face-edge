"""Remove the exact macOS source-development authority, including its OS keys."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def reset(data_dir: Path, *, linux_source: bool = False) -> None:
    if linux_source and (
        sys.platform != "linux" or getattr(sys, "frozen", False)
        or "__compiled__" in globals() or not (Path(__file__).resolve().parents[1] / ".git").exists()
    ):
        raise ValueError("Linux source reset requires an unpackaged checkout")
    home = Path.home()
    expected = home / "Library" / "Application Support" / "SentriFace-Dev"
    production = expected.with_name("SentriFace")
    if data_dir != expected or any(path.is_symlink() for path in (home, home / "Library", expected.parent, data_dir)):
        raise ValueError("Reset is limited to the exact default SentriFace-Dev authority")
    if expected.resolve() == production.resolve():
        raise ValueError("Development authority resolves to installed-product data")

    nodes: list[Path] = []
    if data_dir.exists():
        root_device = data_dir.lstat().st_dev
        for current, dirs, files in os.walk(data_dir, topdown=True, followlinks=False):
            for name in [*dirs, *files]:
                child = Path(current) / name
                mode = child.lstat()
                if mode.st_uid != os.getuid() or mode.st_dev != root_device:
                    raise ValueError(f"Reset refused a non-owned or mounted path: {child}")
                nodes.append(child)
        if data_dir.lstat().st_uid != os.getuid():
            raise ValueError("Reset refused a non-owned development authority")

    for path in [*reversed(nodes), data_dir] if data_dir.exists() else []:
        if path.is_symlink():
            continue
        if hasattr(os, "chflags"):
            os.chflags(path, 0, follow_symlinks=False)
        mode = path.lstat().st_mode
        path.chmod(0o700 if stat.S_ISDIR(mode) else 0o600)
    if data_dir.exists():
        shutil.rmtree(data_dir)

    # Linux source custody lives inside the removed authority, not the OS vault.
    if linux_source:
        return

    # Remove vault entries only after the database is gone. A filesystem
    # failure must never strand an existing encrypted database without its key.
    # If vault cleanup fails, rerunning reset is safe even when files are gone.
    import keyring
    from keyring.errors import PasswordDeleteError
    from sentriface.recovery import RECOVERY_SERVICE, _account
    from sentriface.secure_storage import KEYRING_SERVICE, _keyring_account

    for service, account in (
        (KEYRING_SERVICE, _keyring_account(data_dir)),
        (RECOVERY_SERVICE, _account(data_dir)),
    ):
        try:
            keyring.delete_password(service, account)
        except PasswordDeleteError:
            pass


if __name__ == "__main__":
    reset(Path(sys.argv[1]), linux_source="--linux-source" in sys.argv[2:])
