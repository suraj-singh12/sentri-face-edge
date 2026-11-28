import json

from scripts.compare_installation_snapshots import compare


def snapshot(row_value="same", table=True, file_hash="a"):
    tables = {}
    if table:
        tables["persons"] = {
            "columns": ["person_id", "name"],
            "primary_key": ["person_id"],
            "row_count": 1,
            "rows": [{"rowid": 1, "values": {"person_id": "p1", "name": row_value}}],
        }
    return {"schema_version": 37, "tables": tables, "files": {"faces/a.enc": {"size": 1, "sha256": file_hash}}}


def test_compare_preserves_shared_rows_against_additive_schema():
    before = snapshot()
    after = snapshot()
    after["schema_version"] = 38
    after["tables"]["persons"]["columns"].append("new_column")
    after["tables"]["persons"]["rows"][0]["values"]["new_column"] = "default"
    after["tables"]["new_table"] = {"columns": [], "primary_key": [], "row_count": 0, "rows": []}
    after["files"]["backups/new.sfbackup"] = {"size": 2, "sha256": "b"}
    after["tables"]["persons"]["row_count"] = 2
    after["tables"]["persons"]["rows"].append({"rowid": 2, "values": {"person_id": "p2", "name": "added", "new_column": "x"}})
    result = compare(before, after)
    assert result["status"] == "PASS"
    assert result["added_tables"] == ["new_table"]


def test_compare_refuses_changed_or_missing_authority():
    result = compare(snapshot(), snapshot(row_value="changed"))
    assert result["status"] == "FAIL"
    assert any("row values changed" in error for error in result["errors"])
    result = compare(snapshot(), snapshot(file_hash="different"))
    assert any("file changed" in error for error in result["errors"])
    result = compare(snapshot(), snapshot(table=False))
    assert any("table missing" in error for error in result["errors"])


def test_compare_allows_only_operational_login_bookkeeping():
    before = snapshot()
    before["tables"]["app_users"] = {
        "columns": ["user_id", "username", "password_hash", "failed_attempts", "locked_until", "last_login_at", "updated_at"],
        "primary_key": ["user_id"],
        "row_count": 1,
        "rows": [{"rowid": 1, "values": {
            "user_id": "u1", "username": "owner", "password_hash": "hash",
            "failed_attempts": 2, "locked_until": "expired",
            "last_login_at": None, "updated_at": "before",
        }}],
    }
    after = json.loads(json.dumps(before))
    after["tables"]["app_users"]["rows"][0]["values"]["failed_attempts"] = 0
    after["tables"]["app_users"]["rows"][0]["values"]["locked_until"] = None
    after["tables"]["app_users"]["rows"][0]["values"]["last_login_at"] = "after"
    after["tables"]["app_users"]["rows"][0]["values"]["updated_at"] = "after"
    assert compare(before, after)["status"] == "PASS"
    after["tables"]["app_users"]["rows"][0]["values"]["password_hash"] = "changed"
    result = compare(before, after)
    assert result["status"] == "FAIL"
    assert any("password_hash" in error for error in result["errors"])


def test_transient_model_uploads_are_outside_preservation_scope():
    from scripts.capture_installation_state import _file_in_snapshot_scope

    assert not _file_in_snapshot_scope("models/.model-authority/uploads/upload-id/content")
    assert not _file_in_snapshot_scope("models/.model-authority/bundles/.staging-temp/detector.onnx")
    assert _file_in_snapshot_scope("models/.model-authority/bundles/bundle-id/detector.onnx")
