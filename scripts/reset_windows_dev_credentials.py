from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


SERVICES = (
    "SentriFace Edge storage",
    "SentriFace Edge disaster recovery",
)


def _resolved(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove only the exact Windows source-development vault identities"
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows development credential reset is Windows-only")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        parser.error("LOCALAPPDATA is unavailable")
    expected = _resolved(Path(local_app_data) / "SentriFace-Dev")
    production = _resolved(Path(local_app_data) / "SentriFace")
    supplied = _resolved(args.data_dir)
    if supplied != expected or supplied == production:
        parser.error("refusing a non-default or production development credential target")

    try:
        import keyring
        from keyring.errors import KeyringError, PasswordDeleteError
    except ImportError as exc:
        raise SystemExit(f"Windows keyring support is unavailable: {exc}") from exc

    account = hashlib.sha256(str(supplied.resolve()).casefold().encode("utf-8")).hexdigest()
    try:
        for service in SERVICES:
            if keyring.get_password(service, account) is not None:
                try:
                    keyring.delete_password(service, account)
                except PasswordDeleteError as exc:
                    raise RuntimeError(
                        f"The exact development credential could not be deleted: {service}"
                    ) from exc
            if keyring.get_password(service, account) is not None:
                raise RuntimeError(
                    f"The exact development credential remains after deletion: {service}"
                )
    except KeyringError as exc:
        raise SystemExit(f"Windows keyring cleanup failed: {exc}") from exc
    print("Removed exact SentriFace-Dev vault identities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
