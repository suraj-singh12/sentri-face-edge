import json

import scripts.create_synthetic_installation_fixture as fixture
from scripts.capture_installation_state import capture


def test_fixture_is_populated_and_capturable(tmp_path, monkeypatch):
    key = b"k" * 32
    monkeypatch.setattr(fixture, "load_or_create_master_key", lambda data_dir: key)
    monkeypatch.setattr("scripts.capture_installation_state._load_existing_key", lambda data_dir: key)
    data_dir = tmp_path / "data"
    result = fixture.create_fixture(data_dir)
    assert result["people"] == 5
    state = capture(data_dir)
    assert state["tables"]["persons"]["row_count"] >= 5
    assert state["tables"]["observations"]["row_count"] >= 1
    assert state["tables"]["app_users"]["row_count"] == 1
    assert state["files"]
    assert any(path.startswith("backups/") for path in state["files"])
