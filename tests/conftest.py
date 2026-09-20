from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sqlite3
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest


class _InMemoryKeyring:
    """Minimal keyring backend for ordinary tests; it never reaches the OS vault."""

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append(("get", service, username))
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.calls.append(("set", service, username))
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append(("delete", service, username))
        try:
            del self._passwords[(service, username)]
        except KeyError as exc:
            raise PasswordDeleteError(f"No password stored for {service}/{username}") from exc

    def clear(self) -> None:
        self._passwords.clear()
        self.calls.clear()


class KeyringError(Exception):
    """Test-compatible replacement for keyring.errors.KeyringError."""


class PasswordDeleteError(KeyringError):
    """Test-compatible replacement for keyring.errors.PasswordDeleteError."""


TEST_KEYRING = _InMemoryKeyring()


def _install_test_keyring() -> None:
    """Install before collection so dynamically imported application keyring uses it."""
    keyring = types.ModuleType("keyring")
    keyring.__spec__ = importlib.machinery.ModuleSpec("keyring", loader=None)
    errors = types.ModuleType("keyring.errors")
    errors.__spec__ = importlib.machinery.ModuleSpec("keyring.errors", loader=None)
    errors.KeyringError = KeyringError
    errors.PasswordDeleteError = PasswordDeleteError
    keyring.errors = errors
    keyring.get_password = TEST_KEYRING.get_password
    keyring.set_password = TEST_KEYRING.set_password
    keyring.delete_password = TEST_KEYRING.delete_password
    sys.modules["keyring"] = keyring
    sys.modules["keyring.errors"] = errors


_install_test_keyring()


def _normal_production_data_dir() -> Path:
    """Resolve the normal app root without following a developer's test override."""
    from sentriface.paths import default_data_dir

    override = os.environ.pop("SENTRIFACE_DATA_DIR", None)
    try:
        return default_data_dir().expanduser().resolve()
    finally:
        if override is not None:
            os.environ["SENTRIFACE_DATA_DIR"] = override


_PRODUCTION_DATA_DIR = _normal_production_data_dir()


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
    """Classify tests that require the optional SQLCipher runtime.

    Keyring is deliberately supplied by the in-memory test backend above; normal
    tests must not depend on, or mutate, the user's credential vault.
    """
    if importlib.util.find_spec("sqlcipher3") is not None:
        return
    marker = pytest.mark.skip(
        reason="environment: declared encrypted-storage runtime unavailable: sqlcipher3",
    )
    for item in items:
        if item.path.name in _ENCRYPTED_RUNTIME_TEST_MODULES:
            item.add_marker(marker)
        elif item.path.name == "test_v1_security.py":
            if any(token in item.name for token in (
                "sqlcipher", "plaintext_database_migrates", "recovery_code_unlocks",
            )):
                item.add_marker(marker)


@pytest.fixture
def sentriface_test_data_dir(tmp_path: Path) -> Path:
    """The only implicit SentriFace data root available to an ordinary test."""
    return tmp_path / "sentriface-data"


@pytest.fixture
def production_sentriface_data_dir() -> Path:
    """Expose the guarded path only for tripwire regression tests."""
    return _PRODUCTION_DATA_DIR


@pytest.fixture
def test_keyring() -> _InMemoryKeyring:
    return TEST_KEYRING


@pytest.fixture(autouse=True)
def isolate_sentriface_runtime(
    monkeypatch: pytest.MonkeyPatch,
    sentriface_test_data_dir: Path,
) -> Iterator[None]:
    """Contain every ordinary test to pytest storage and an in-memory vault."""
    from sentriface import api_server, auth_recovery, cli, secure_storage

    TEST_KEYRING.clear()
    model_dir = sentriface_test_data_dir / "models"
    monkeypatch.setenv("SENTRIFACE_DATA_DIR", str(sentriface_test_data_dir))
    monkeypatch.setenv("SENTRIFACE_MODEL_DIR", str(model_dir))

    original_load_master_key = secure_storage.load_or_create_master_key

    def reject_production_data_dir(data_dir: Path, *args, **kwargs):
        resolved = Path(data_dir).expanduser().resolve()
        if resolved == _PRODUCTION_DATA_DIR:
            raise AssertionError(
                "Tests must not bootstrap SentriFace using the production data directory; "
                "use sentriface_test_data_dir or an explicit pytest-owned path."
            )
        return original_load_master_key(data_dir, *args, **kwargs)

    monkeypatch.setattr(secure_storage, "load_or_create_master_key", reject_production_data_dir)
    monkeypatch.setattr(cli, "load_or_create_master_key", reject_production_data_dir)
    monkeypatch.setattr(api_server, "load_or_create_master_key", reject_production_data_dir)
    monkeypatch.setattr(auth_recovery, "load_or_create_master_key", reject_production_data_dir)
    try:
        yield
    finally:
        TEST_KEYRING.clear()
