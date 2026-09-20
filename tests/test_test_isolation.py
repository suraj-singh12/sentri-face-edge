from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sentriface import cli
from sentriface.paths import default_data_dir, default_model_dir
from sentriface.secure_storage import KEYRING_SERVICE, load_or_create_master_key


def test_implicit_runtime_paths_are_pytest_owned(sentriface_test_data_dir: Path) -> None:
    assert default_data_dir() == sentriface_test_data_dir
    assert default_model_dir() == sentriface_test_data_dir / "models"


def test_master_keys_use_the_in_memory_keyring_and_remain_installation_scoped(
    tmp_path: Path,
    test_keyring,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first_key = load_or_create_master_key(first_dir)
    assert load_or_create_master_key(first_dir) == first_key
    assert load_or_create_master_key(second_dir) != first_key

    writes = [call for call in test_keyring.calls if call[0] == "set"]
    assert len(writes) == 2
    assert {call[1] for call in writes} == {KEYRING_SERVICE}


def test_production_data_root_tripwire_rejects_storage_bootstrap(
    production_sentriface_data_dir: Path,
) -> None:
    from sentriface import secure_storage

    with pytest.raises(AssertionError, match="production data directory"):
        secure_storage.load_or_create_master_key(production_sentriface_data_dir)


def test_cli_without_data_dir_uses_the_isolated_default(
    sentriface_test_data_dir: Path,
    test_keyring,
) -> None:
    initialized_database_paths: list[Path] = []

    class _Store:
        def initialize(self) -> None:
            return None

    def isolated_store(config):
        initialized_database_paths.append(config.db_path)
        return _Store()

    with (
        patch("sentriface.cli._authorize_cli"),
        patch("sentriface.cli._identity_store", isolated_store),
        patch("sys.argv", ["sentriface", "--profile", "low", "profile"]),
    ):
        assert cli.main() == 0

    assert any(call[0] == "set" and call[1] == KEYRING_SERVICE for call in test_keyring.calls)
    assert initialized_database_paths == [sentriface_test_data_dir / "sentriface.db"]
