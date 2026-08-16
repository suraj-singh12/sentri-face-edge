from __future__ import annotations

import importlib.util
import sqlite3
import sys

import pytest


if sys.platform == "win32":
    _sqlite_connect = sqlite3.connect

    class _ClosingTestConnection(sqlite3.Connection):
        """Make test ``with sqlite3.connect`` blocks release Windows handles."""

        def __exit__(self, exc_type, exc_value, traceback):
            try:
                return super().__exit__(exc_type, exc_value, traceback)
            finally:
                self.close()

    def _connect_with_closing_context(*args, **kwargs):
        if len(args) < 6 and "factory" not in kwargs:
            kwargs["factory"] = _ClosingTestConnection
        return _sqlite_connect(*args, **kwargs)

    sqlite3.connect = _connect_with_closing_context


_ENCRYPTED_RUNTIME_TEST_MODULES = {
    "test_api_security.py",
    "test_auth_api.py",
    "test_backup_api.py",
    "test_cli.py",
    "test_cli_auth.py",
    "test_model_onboarding_api.py",
    "test_queue_cancellation_api.py",
}


def pytest_collection_modifyitems(items):
    """Classify tests that require optional native/OS runtime integration."""
    missing = [
        name for name in ("keyring", "sqlcipher3")
        if importlib.util.find_spec(name) is None
    ]
    if not missing:
        return
    marker = pytest.mark.skip(
        reason="environment: declared encrypted-storage runtime unavailable: "
        + ", ".join(missing),
    )
    for item in items:
        if item.path.name in _ENCRYPTED_RUNTIME_TEST_MODULES:
            item.add_marker(marker)
        elif item.path.name == "test_v1_security.py" and "sqlcipher3" in missing:
            if any(token in item.name for token in (
                "sqlcipher", "plaintext_database_migrates", "recovery_code_unlocks",
            )):
                item.add_marker(marker)
