"""Provenance invariants through supported review writes, not media-count exceptions."""
import uuid
from pathlib import Path
import sqlite3
import pytest

from sentriface.models import InitFace, DetectedFace, FaceBox, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.backup_service import BackupService, BackupError


def multi_photo(store, root, people, prefix):
    session = store.create_init_session(str(root))
    paths = []
    faces = []
    for index in range(3):
        path = root / f'{prefix}-{index}.jpg'
        path.write_bytes(f'registered independent source {prefix}-{index}'.encode())
        paths.append(str(path))
        for position in range(2):
            faces.append(InitFace(init_face_id=f'{prefix}-{index}-{position}', session_id=session.session_id,
                group_id=f'{prefix}-person-{position}', source_image=str(path),
                face=DetectedFace(FaceBox(position * 20, 1, 10, 10, .99), .9),
                vector=(1., 0.) if position == 0 else (0., 1.), quality=QualityReport(QualityStatus.GOOD, .9)))
    store.save_init_session_media(session.session_id, paths)
    store.save_init_faces(faces)
    review = store.plan_init_session_encounters(session.session_id,
        [[row['media_id'] for row in store.list_init_session_media(session.session_id)]])[0]
    rid = review['review_id']
    store.save_encounter_review_event(rid, {'date':'2026-10-03','place_seen':'Fixture','event_context':'ordinary'})
    for face in review['faces']:
        store.set_photo_review_face_decision(rid, face['face_id'], 'ACCEPT_EXISTING_PERSON',
            person_id=people[int(face['face_id'][-1])].person_id)
    review = store.complete_encounter_identity_review(rid)
    for pair in review['relation_candidates']:
        store.set_encounter_relation_decision(rid, pair['first_ref'], pair['second_ref'], 'INCLUDE')
    return store.complete_photo_review(rid, prefix+'-complete')['observation_id']


def authority(tmp_path):
    store = SQLiteIdentityStore(tmp_path/'sentriface.db', embedding_dim=2)
    store.initialize()
    people = [store.create_person(name) for name in ('First','Second')]
    oid = multi_photo(store, tmp_path, people, 'first')
    return store, people, oid


def test_reused_samples_and_multi_photo_provenance_survive_rebuild_restore(tmp_path):
    store, people, oid = authority(tmp_path)
    second = multi_photo(store, tmp_path, people, 'second')
    assert len(store.list_embeddings()) == 2  # vectors reused; six source photos remain valid
    assert ReadOnlyIntegrityChecker(store.db_path).run().status == 'PASS'
    before = store.get_encounter_read(oid)
    GlobalIdentityGraphService(store).rebuild_projection('multi-rebuild')
    assert store.get_encounter_read(oid) == before
    service = BackupService(store.db_path, tmp_path/'backups')
    backup = service.create_backup()
    assert backup.restorable and backup.complete
    service.restore_backup(backup.backup_id, str(uuid.uuid4()))
    restored = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    restored.initialize()
    assert set(restored.get_encounter_read(oid)['participant_ids']) == set(before['participant_ids'])
    assert len(restored.list_observation_media(oid)) == 3
    assert len(restored.list_observation_media(second)) == 3
    assert ReadOnlyIntegrityChecker(store.db_path).run().status == 'PASS'


def test_registered_media_cannot_prove_an_unrelated_face_binding(tmp_path):
    store, people, oid = authority(tmp_path)
    other = multi_photo(store, tmp_path, people, 'other')
    wrong_id = store.list_observation_media(other)[0].media_id
    # Isolated malformed fixture only: retain real rows, break immutable binding.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute('DROP TRIGGER completed_photo_review_faces_immutable')
        conn.execute("UPDATE photo_review_faces SET recognition_detail=json_set(recognition_detail,'$.encounter_media_id',?) WHERE review_id IN (SELECT review_id FROM photo_reviews WHERE observation_id=?)", (wrong_id,oid))
    findings = ReadOnlyIntegrityChecker(store.db_path).run().findings
    assert any(f.invariant_id == 'P11-OBSERVATION-003' for f in findings)
    with pytest.raises(Exception, match='refused'):
        GlobalIdentityGraphService(store).rebuild_projection('invalid-rebuild')


def test_missing_registered_file_prevents_restorable_backup(tmp_path):
    store, _, oid = authority(tmp_path)
    Path(store.list_observation_media(oid)[1].media_path).unlink()
    service = BackupService(store.db_path, tmp_path/'backups')
    backup = service.create_backup()
    assert not backup.complete and not backup.restorable
    with pytest.raises(BackupError):
        service.restore_backup(backup.backup_id, str(uuid.uuid4()))
