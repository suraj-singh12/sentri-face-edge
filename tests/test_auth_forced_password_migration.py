"""#54 schema v36: accounts gain must_change_password; existing accounts stay unflagged."""
import uuid

from sentriface.storage.sqlite_constants import SCHEMA_VERSION
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from test_recognition_references import store  # noqa: F401 - pytest fixture


def _add_account(store, user_id="u1"):
    with store._connect() as conn:
        conn.execute(
            """INSERT INTO app_users(user_id, username, username_norm, display_name, password_hash, roles,
            disabled, failed_attempts, locked_until, created_at, updated_at, last_login_at)
            VALUES (?, 'owner', 'owner', 'Owner', 'hash', '["administrator"]', 0, 0, NULL, 't', 't', NULL)""",
            (user_id,),
        )


def _downgrade_to_v35(store):
    with store._connect() as conn:
        conn.execute("ALTER TABLE app_users DROP COLUMN must_change_password")
        conn.execute("PRAGMA user_version = 35")


def test_fresh_database_has_the_flag_column_defaulting_to_unflagged(store):
    _add_account(store)
    with store._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 36
        assert conn.execute("SELECT must_change_password FROM app_users").fetchone()[0] == 0


def test_v35_accounts_upgrade_unflagged_and_restart_cleanly(store):
    _add_account(store)
    _downgrade_to_v35(store)
    for _ in range(2):
        upgraded = SQLiteIdentityStore(store.db_path, embedding_dim=2)
        upgraded.initialize()
        with upgraded._connect() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
            assert [tuple(r) for r in conn.execute("SELECT username, must_change_password FROM app_users").fetchall()] == [("owner", 0)]
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_backup_made_by_v35_app_restores_after_upgrade(store, tmp_path, monkeypatch):
    import sentriface.integrity as integrity
    from sentriface.backup_service import BackupService
    store.create_person("Alice")
    _add_account(store)
    _downgrade_to_v35(store)
    with monkeypatch.context() as patch:
        patch.setattr(integrity, "SCHEMA_VERSION", 35)
        backup = BackupService(store.db_path, tmp_path / "backups", supported_database_version=35).create_backup()
    assert backup.database_version == 35 and backup.restorable
    upgraded = BackupService(store.db_path, tmp_path / "backups", supported_database_version=SCHEMA_VERSION)
    assert upgraded.verify_backup(backup.backup_id)
    assert upgraded.restore_backup(backup.backup_id, str(uuid.uuid4()))["outcome"] == "COMMITTED"
    restored = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    restored.initialize()
    with restored._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT must_change_password FROM app_users").fetchone()[0] == 0
    assert len(restored.list_persons()) == 1
