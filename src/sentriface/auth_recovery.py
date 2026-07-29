from __future__ import annotations

import argparse
from dataclasses import replace
from getpass import getpass
from pathlib import Path

from sentriface.auth import AuthError, AuthService
from sentriface.config import config_for_hardware
from sentriface.hardware import assess_hardware
from sentriface.offline_guard import install_offline_guard, require_local_path
from sentriface.paths import default_data_dir
from sentriface.secure_storage import StorageSecurityError, load_or_create_master_key
from sentriface.storage.sqlite_store import SQLiteIdentityStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a SentriFace administrator password as the local OS custodian")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    install_offline_guard()
    try:
        data_dir = require_local_path(args.data_dir)
        key = load_or_create_master_key(data_dir)
        config = replace(config_for_hardware(assess_hardware(), data_dir=data_dir), storage_key=key)
        SQLiteIdentityStore(
            config.db_path,
            config.embedding_dim,
            backup_dir=config.backup_dir,
            backup_retention_limit=config.backup_retention_limit,
            database_key=key,
        ).initialize()
        first = getpass("New administrator password: ")
        second = getpass("Confirm new password: ")
        if first != second:
            print("Passwords do not match")
            return 2
        user = AuthService(config.db_path, key).emergency_reset_administrator(args.username, first)
        print(f"Password reset for administrator {user.username}. Existing sessions were revoked.")
        return 0
    except (AuthError, StorageSecurityError, OSError, ValueError) as exc:
        print(f"Administrator password could not be reset: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())