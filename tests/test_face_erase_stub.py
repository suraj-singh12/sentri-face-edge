"""Erasing a face keeps a "face removed" stub when history references it (#49)."""
import sqlite3
import uuid

import pytest

from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.storage.sqlite_constants import SCHEMA_VERSION
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from test_recognition_references import stage, store  # noqa: F401 - pytest fixture


def op():
    return str(uuid.uuid4())


def event_face(store):
    alice = store.create_person('Alice')
    image = stage(store, alice, 'event', source='check-photo')
    observation_id = store.complete_photo_review('event', op())['observation_id']
    embedding_id = store.list_embeddings_for_person(alice.person_id)[0].embedding_id
    return alice, image, observation_id, embedding_id


def row(store, embedding_id):
    with store._connect() as conn:
        return conn.execute('SELECT * FROM embeddings WHERE embedding_id=?', (embedding_id,)).fetchone()


def expire(store):
    with store._connect() as conn:
        conn.execute("UPDATE embeddings SET purge_after='2000-01-01T00:00:00+00:00' WHERE deleted_at IS NOT NULL")


def test_event_face_erase_keeps_stub_and_event_photo(store):
    alice, image, observation_id, eid = event_face(store)
    with store._connect() as conn:
        conn.execute('UPDATE embeddings SET crop_path=? WHERE embedding_id=?', (str(image.parent / 'crop.jpg'), eid))
    store.delete_embedding(eid, op())
    revision = store.get_encounter_read(observation_id)['revision']
    operation_id = op()
    result = store.permanently_delete_embedding(eid, operation_id)
    assert result['stub_retained'] is True
    assert store.permanently_delete_embedding(eid, operation_id) == result
    stub = row(store, eid)
    assert stub['erased_at'] and stub['vector'] == b'' and stub['crop_path'] is None
    assert stub['purge_after'] is None and stub['person_id'] == alice.person_id
    assert stub['source_image'] == str(image)
    assert str(image) in store.list_all_file_references()
    assert str(image.parent / 'crop.jpg') not in store.list_all_file_references()
    assert store.get_encounter_read(observation_id)['revision'] == revision
    assert store.list_deleted_embeddings() == []
    assert eid not in {e.embedding_id for e in store.list_embeddings()}
    with pytest.raises(KeyError, match="can't be restored"):
        store.restore_deleted_embedding(eid, op())
    with pytest.raises(KeyError, match='already been erased'):
        store.permanently_delete_embedding(eid, op())
    assert store.get_operation(operation_id)['status'] == 'COMMITTED'


def test_moved_face_erase_keeps_stub_and_correction_history(store):
    alice, bob = store.create_person('Alice'), store.create_person('Bob')
    eid = store.add_embedding(alice.person_id, (1.0, 0.0), 0.9).embedding_id
    store.move_face(eid, bob.person_id, op())
    store.delete_embedding(eid, op())
    assert store.permanently_delete_embedding(eid, op())['stub_retained'] is True
    corrections = store.list_corrections_for_embedding(eid)
    assert len(corrections) == 1 and corrections[0].to_person_id == bob.person_id
    assert row(store, eid)['erased_at']


def test_unreferenced_face_is_still_fully_erased(store):
    alice = store.create_person('Alice')
    eid = store.add_embedding(alice.person_id, (1.0, 0.0), 0.9).embedding_id
    store.delete_embedding(eid, op())
    assert store.permanently_delete_embedding(eid, op())['stub_retained'] is False
    assert row(store, eid) is None


def test_retention_cleanup_erases_mixed_batch_in_one_pass(store):
    alice, _image, _oid, event_eid = event_face(store)
    bob = store.create_person('Bob')
    moved = store.add_embedding(alice.person_id, (0.0, 1.0), 0.9).embedding_id
    store.move_face(moved, bob.person_id, op())
    plain = store.add_embedding(bob.person_id, (0.6, 0.8), 0.9).embedding_id
    for eid in (event_eid, moved, plain):
        store.delete_embedding(eid, op())
    expire(store)
    ids = store.list_expired_deleted_embedding_ids()
    assert sorted(ids) == sorted([event_eid, moved, plain])
    result = store.purge_expired_deleted_embeddings(ids, op())
    assert result['purged'] == 3
    assert sorted(result['stub_embedding_ids']) == sorted([event_eid, moved])
    assert row(store, plain) is None
    assert store.list_expired_deleted_embedding_ids() == []
    assert store.purge_expired_deleted_embeddings(ids, op())['purged'] == 0


def test_stub_survives_backup_restore_and_passes_integrity(store, tmp_path):
    from sentriface.backup_service import BackupService
    _alice, _image, observation_id, eid = event_face(store)
    store.delete_embedding(eid, op())
    store.permanently_delete_embedding(eid, op())
    service = BackupService(store.db_path, tmp_path / 'backups')
    backup = service.create_backup()
    service.restore_backup(backup.backup_id, op())
    restored = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    restored.initialize()
    assert row(restored, eid)['erased_at']
    assert restored.get_encounter_read(observation_id)['observation_id'] == observation_id
    assert ReadOnlyIntegrityChecker(store.db_path).run().status == 'PASS'


def test_v34_database_upgrades_to_stub_schema_and_restarts_cleanly(store):
    _alice, _image, _oid, eid = event_face(store)
    with store._connect() as conn:
        conn.execute('ALTER TABLE embeddings DROP COLUMN erased_at')
        conn.execute('PRAGMA user_version = 34')
    for _ in range(2):
        upgraded = SQLiteIdentityStore(store.db_path, embedding_dim=2)
        upgraded.initialize()
        with upgraded._connect() as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION >= 35
            assert conn.execute('SELECT erased_at FROM embeddings WHERE embedding_id=?', (eid,)).fetchone()[0] is None
    upgraded.delete_embedding(eid, op())
    assert upgraded.permanently_delete_embedding(eid, op())['stub_retained'] is True


def test_backup_verified_by_v34_app_still_restores_after_upgrade(store, tmp_path, monkeypatch):
    import sentriface.integrity as integrity
    from sentriface.backup_service import BackupService
    store.create_person('Alice')
    with store._connect() as conn:
        conn.execute('ALTER TABLE embeddings DROP COLUMN erased_at')
        conn.execute('PRAGMA user_version = 34')
    with monkeypatch.context() as patch:
        patch.setattr(integrity, 'SCHEMA_VERSION', 34)
        old = BackupService(store.db_path, tmp_path / 'backups', supported_database_version=34)
        backup = old.create_backup()
    assert backup.database_version == 34 and backup.restorable
    upgraded = BackupService(store.db_path, tmp_path / 'backups', supported_database_version=SCHEMA_VERSION)
    assert upgraded.verify_backup(backup.backup_id)
    assert upgraded.restore_backup(backup.backup_id, op())['outcome'] == 'COMMITTED'
    restored = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    restored.initialize()
    with restored._connect() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
    assert len(restored.list_persons()) == 1
