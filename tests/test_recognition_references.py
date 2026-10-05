"""Source identity is independent of exact-vector storage deduplication."""
import sqlite3
from unittest.mock import patch

import pytest

from sentriface.models import DetectedFace, FaceBox, MatchDecision, PendingAddition, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore, _source_sample_authority


@pytest.fixture
def store(tmp_path):
    result = SQLiteIdentityStore(tmp_path / 'identity.db', embedding_dim=2)
    result.initialize()
    return result


def stage(store, person, key, vector=(1., 0.), quality='GOOD', source='reference-only', count=1):
    image = store.db_path.parent / f'{key}.jpg'
    image.write_bytes(key.encode())
    faces = []
    for i in range(count):
        pid = f'{key}-{i}'
        store.save_pending_addition(PendingAddition(pending_id=pid, source_image=str(image),
            face=DetectedFace(FaceBox(1, 1, 10, 10, .99), .9), vector=vector,
            matches=[], decision=MatchDecision.UNKNOWN,
            quality=QualityReport(QualityStatus.GOOD if quality=='GOOD' else QualityStatus.BAD, .9)))
        faces.append(dict(face_id=f'face-{i}', staged_face_type='PENDING_ADDITION', staged_face_id=pid))
    store.create_photo_review(key, image.name, faces, media_path=str(image), source=source)
    for face in faces:
        store.set_photo_review_face_decision(key, face['face_id'], 'ACCEPT_EXISTING_PERSON',
            person_id=person.person_id, recognition_detail={'embedding_state': quality})
    return image


def add(store, person, key, vector=(1., 0.), quality='GOOD'):
    stage(store, person, key, vector, quality)
    return store.add_face_to_person(key, person.person_id, f'add-{key}', no_context_acknowledged=True)


def catalog(store, person):
    return store.list_recognition_references(person.person_id)


def lifecycle(store, person, ref, active, op):
    return store.set_reference_active(ref['reference_id'], person.person_id, active, op)


def test_bootstrap_and_enrolled_use_one_source_contract_and_independent_vectors(store):
    a = store.create_person('Alice')
    assert store.get_person(a.person_id).biometric_status == 'NO_FACE'
    first = add(store, a, 'portrait', (1., 0.))
    assert store.get_person(a.person_id).biometric_status == 'ENROLLED'
    second = add(store, a, 'other-portrait', (.7, .3))
    assert first['embedding_ids'] != second['embedding_ids']
    refs = catalog(store, a)
    assert refs['active_count'] == 2
    assert all(r['origin']=='STANDALONE_ENROLLMENT' and r['no_context_declared']==1 for r in refs['references'])
    assert len(store.list_embeddings())==2
    assert store.query_encounters()['events']==[]
    assert store.get_global_graph_projection().connections==()


@pytest.mark.parametrize('count', [0, 2])
def test_store_cannot_confirm_non_single_face_admission(store, count):
    a=store.create_person('Alice')
    if count == 0:
        with pytest.raises(ValueError): stage(store,a,'invalid',count=count)
        assert catalog(store,a)['active_count']==0
        return
    stage(store,a,'invalid',count=count)
    with pytest.raises(ValueError, match='exactly one'):
        store.add_face_to_person('invalid',a.person_id,'invalid-op',no_context_acknowledged=True)
    assert catalog(store,a)['active_count']==0
    assert store.get_operation('invalid-op') is None


def test_ack_and_legacy_controller_cannot_bypass_admission(store):
    a=store.create_person('Alice'); stage(store,a,'missing-declaration')
    with pytest.raises(ValueError,match='Encounter context'):
        store.add_face_to_person('missing-declaration',a.person_id,'missing-ack')
    with pytest.raises(ValueError,match='without creating an Encounter'):
        store.complete_photo_review('missing-declaration','wrong-workflow')
    stage(store,a,'legacy',source='check-photo')
    with pytest.raises(ValueError,match='admission flow'):
        store.add_face_to_person('legacy',a.person_id,'legacy-bypass',no_context_acknowledged=True)


@pytest.mark.parametrize('quality',['GOOD','POOR_ACCEPTED','PROOF_ONLY'])
def test_quality_cap_retire_restore_and_exact_retry(store, quality):
    a=store.create_person('Alice')
    for i in range(4): add(store,a,f'r{i}',(1.,i*.1),quality)
    assert catalog(store,a)['active_count']==4
    assert store.get_person(a.person_id).biometric_status==('NO_FACE' if quality=='PROOF_ONLY' else 'ENROLLED')
    stage(store,a,'fifth',(.5,.5),quality)
    with pytest.raises(ValueError,match='Four active'):
        store.add_face_to_person('fifth',a.person_id,'fifth-op',no_context_acknowledged=True)
    ref=catalog(store,a)['references'][0]
    before=ref.copy()
    result=lifecycle(store,a,ref,False,'retire')
    assert result==lifecycle(store,a,ref,False,'retire')
    assert catalog(store,a)['active_count']==3
    assert ref['source_image'] in store.list_all_file_references()
    assert lifecycle(store,a,ref,True,'restore')['active']
    assert catalog(store,a)['active_count']==4
    with pytest.raises(ValueError,match='another Reference command'):
        lifecycle(store,a,ref,False,'restore')
    current=next(r for r in catalog(store,a)['references'] if r['reference_id']==ref['reference_id'])
    assert all(current[k]==before[k] for k in ('source_media_id','person_id','embedding_id','recognition_state'))


def test_duplicate_exact_vector_no_new_source_and_cross_person_block(store):
    a,b=[store.create_person(n) for n in ('A','B')]
    first=add(store,a,'original')
    duplicate=add(store,a,'different-bytes-same-vector')
    assert duplicate['embedding_ids']==first['embedding_ids']
    assert duplicate['created_reference_ids']==[]
    assert catalog(store,a)['active_count']==1
    assert store.get_photo_review('different-bytes-same-vector').media_path is None
    stage(store,b,'other-person')
    with pytest.raises(ValueError,match='another Person'):
        store.add_face_to_person('other-person',b.person_id,'conflict',no_context_acknowledged=True)


def test_retire_final_sample_status_and_encounter_samples_independent(store):
    a=store.create_person('Alice'); add(store,a,'reference')
    ref=catalog(store,a)['references'][0]
    lifecycle(store,a,ref,False,'retire')
    assert store.get_person(a.person_id).biometric_status=='NO_FACE'
    stage(store,a,'encounter',(.2,.8),source='check-photo')
    store.complete_photo_review('encounter','finalize')
    assert store.get_person(a.person_id).biometric_status=='ENROLLED'
    lifecycle(store,a,ref,True,'restore'); lifecycle(store,a,ref,False,'retire-again')
    assert store.get_person(a.person_id).biometric_status=='ENROLLED'
    assert catalog(store,a)['active_count']==0


def test_reference_and_encounter_exact_media_roles_and_targeted_attach(store):
    a=store.create_person('Alice'); add(store,a,'reference')
    ref=catalog(store,a)['references'][0]
    with pytest.raises(ValueError,match='Reference Only'):
        store.validate_encounter_media(ref['source_image'])
    lifecycle(store,a,ref,False,'retire')
    with pytest.raises(ValueError,match='Reference Only'):
        store.save_init_session_media(store.create_init_session('/staged').session_id,[ref['source_image']])
    image=stage(store,a,'occurrence',(.2,.8),source='check-photo')
    oid=store.complete_photo_review('occurrence','finalize')['observation_id']
    with pytest.raises(ValueError,match='Encounter media'):
        store.validate_reference_media(str(image),a.person_id)
    session=store.create_init_session('/attach',target_observation_id=oid,expected_revision=store.get_encounter_read(oid)['revision'])
    with pytest.raises(ValueError,match='Reference Only'):
        store.save_init_session_media(session.session_id,[ref['source_image']])
    assert store.get_init_session(session.session_id).target_observation_id==oid


@pytest.mark.parametrize('resolution',['correct-back','retire','merge'])
def test_shared_sample_correction_never_transfers_reference_and_conflict_is_derived(store,resolution):
    a,b=[store.create_person(n) for n in ('Alice','Bob')]
    added=add(store,a,'reference'); eid=added['embedding_ids'][0]
    stage(store,a,'occurrence',source='check-photo')
    finalized=store.complete_photo_review('occurrence','finalize')
    assert finalized['embedding_assignments']=={'face-0':eid}
    assert len(store.list_embeddings())==1
    oid=finalized['observation_id']; ref=catalog(store,a)['references'][0]
    store.correct_encounter(oid,'reassign',expected_revision=store.get_encounter_read(oid)['revision'],
        participant_correction={'action':'REASSIGN','person_id':a.person_id,'to_person_id':b.person_id})
    assert store.get_encounter_read(oid)['participant_ids']==[b.person_id]
    current=catalog(store,a)
    assert current['active_count']==1 and current['references'][0]['person_id']==a.person_id
    assert current['references'][0]['recognition_conflict']
    assert store.current_embedding_person_ids([eid],quality_only=False)=={}
    before=current
    store.rebuild_graph_projection('rebuild')
    reopened=SQLiteIdentityStore(store.db_path,embedding_dim=2); reopened.initialize()
    assert catalog(reopened,a)==before
    if resolution=='correct-back':
        store.correct_encounter(oid,'correct-back',expected_revision=store.get_encounter_read(oid)['revision'],
            participant_correction={'action':'REASSIGN','person_id':b.person_id,'to_person_id':a.person_id})
        expected=a.person_id
    elif resolution=='retire':
        lifecycle(store,a,ref,False,'retire'); expected=b.person_id
        assert catalog(store,a)['active_count']==0
    else:
        store.execute_identity_merge(b.person_id,a.person_id,'merge'); expected=a.person_id
    assert store.current_embedding_person_ids([eid],quality_only=False)=={eid:expected}
    assert not catalog(store,a)['references'][0]['recognition_conflict']


def test_lifecycle_failure_rolls_back_source_status_and_journal(store):
    a=store.create_person('Alice'); add(store,a,'reference'); ref=catalog(store,a)['references'][0]
    before=catalog(store,a)
    def fail(_): raise RuntimeError('injected lifecycle failure')
    with pytest.raises(RuntimeError):
        store.set_reference_active(ref['reference_id'],a.person_id,False,'failed',failure_injector=fail)
    assert catalog(store,a)==before and store.get_operation('failed') is None
    with patch('sentriface.storage.sqlite_store._mark_person_enrolled',side_effect=RuntimeError('injected add failure')):
        stage(store,a,'second',(.3,.7))
        with pytest.raises(RuntimeError):
            store.add_face_to_person('second',a.person_id,'failed-add',no_context_acknowledged=True)
    assert catalog(store,a)['active_count']==1 and store.get_operation('failed-add') is None


@pytest.mark.parametrize('combined',[4,5])
@pytest.mark.parametrize('reverse',[False,True])
def test_canonical_merge_cap_is_source_based_and_preflight_safe(store,combined,reverse):
    a,b=[store.create_person(n) for n in ('Alice','Alias')]
    for i in range(combined): add(store,a if i<2 else b,f'r{i}',(.1+i*.1,.9-i*.1))
    source,target=(b,a) if not reverse else (a,b)
    if combined>4:
        with pytest.raises(ValueError,match='four|4'):
            store.execute_identity_merge(source.person_id,target.person_id,'merge')
        assert store.get_person(source.person_id).lifecycle_status=='ACTIVE'
        assert catalog(store,a)['active_count']==2
    else:
        store.execute_identity_merge(source.person_id,target.person_id,'merge')
        assert catalog(store,target)['active_count']==4
        assert len(store.list_embeddings())==4
        with pytest.raises(ValueError,match='canonical Person'):
            store.validate_reference_media('/new.jpg',source.person_id)


def test_archive_restore_and_tombstone_preserve_reference_lifecycle(store):
    a=store.create_person('Alice'); add(store,a,'reference'); before=catalog(store,a)['references'][0]
    store.archive_person(a.person_id,'archive')
    assert catalog(store,a)['active_count']==1 and store.list_embeddings()==[]
    store.restore_person(a.person_id,'restore-person')
    assert len(store.list_embeddings())==1
    store.permanently_delete_person(a.person_id,'delete')
    after=catalog(store,a)['references'][0]
    assert after['active'] and after['person_id']==before['person_id']
    assert after['source_image'] in store.list_all_file_references()
    assert store.list_embeddings()==[]


def test_backup_restore_and_restart_preserve_sources_retirement_and_shared_conflict(store,tmp_path):
    from sentriface.backup_service import BackupService
    a,b=[store.create_person(n) for n in ('Alice','Bob')]
    add(store,a,'bootstrap'); add(store,a,'later',(.3,.7),'PROOF_ONLY')
    refs=catalog(store,a)['references']; lifecycle(store,a,refs[1],False,'retire')
    stage(store,a,'occurrence',source='check-photo')
    oid=store.complete_photo_review('occurrence','finalize')['observation_id']
    store.correct_observation_identity(oid,a.person_id,b.person_id,'correct')
    expected=catalog(store,a)
    service=BackupService(store.db_path,tmp_path/'backups')
    backup=service.create_backup()
    assert backup.complete and backup.restorable and service.verify_backup(backup.backup_id)
    result=service.restore_backup(backup.backup_id,str(__import__('uuid').uuid4()))
    assert result
    restarted=SQLiteIdentityStore(store.db_path,embedding_dim=2); restarted.initialize()
    actual=catalog(restarted,a)
    for reference in actual['references']:
        assert __import__('pathlib').Path(reference['source_image']).is_file()
    def meaning(data):
        return {**data,'references':[{k:v for k,v in r.items() if k not in ('source_image','crop_path')} for r in data['references']]}
    assert meaning(actual)==meaning(expected)
    assert restarted.current_embedding_person_ids([refs[0]['embedding_id']],quality_only=False)=={}


def test_single_face_engine_admission_runs_inference_and_rejection_cleanup(store,tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from sentriface.engine import FaceEngine
    from sentriface.graph_service import GlobalIdentityGraphService
    a=store.create_person('Alice')
    engine=object.__new__(FaceEngine); engine.store=store
    engine.graph=GlobalIdentityGraphService(store)
    engine.cleanup=Mock()
    for count in (0,2):
        pending=[PendingAddition(pending_id=f'p{i}',source_image=str(tmp_path/'upload.jpg'),
            face=DetectedFace(FaceBox(1,1,10,10,.99),.9),vector=(1.,0.),matches=[],decision=MatchDecision.UNKNOWN,
            quality=QualityReport(QualityStatus.GOOD,.9)) for i in range(count)]
        engine._process_additions=Mock(return_value=SimpleNamespace(accepted=pending))
        with pytest.raises(ValueError,match='No usable|Multiple faces'):
            engine.prepare_reference_review(tmp_path/'upload.jpg',a.person_id)
        engine._process_additions.assert_called_once_with(tmp_path/'upload.jpg',allow_bad_quality=True)
        assert catalog(store,a)['active_count']==0 and store.list_pending_additions()==[]
    assert engine.cleanup.run.call_count==2


def test_reference_cancel_removes_staging_and_retains_no_ordinary_work(store):
    a=store.create_person('Alice'); stage(store,a,'cancel')
    store.cancel_reference_review('cancel')
    assert catalog(store,a)['active_count']==0 and catalog(store,a)['drafts']==[]
    assert store.list_pending_additions()==[]
    assert store.get_photo_review('cancel').media_path is None
    assert store.query_encounters()['events']==[]


def downgrade_reference_fixture_to_v33(path):
    """Remove only v34 structures in a disposable migration fixture."""
    with sqlite3.connect(path) as conn:
        conn.execute('DROP TABLE recognition_reference_revisions')
        conn.execute('DROP TRIGGER biometric_enrollment_history_no_update')
        for column in ('source_media_id','source_image','crop_path','recognition_state','no_context_declared'):
            conn.execute(f'ALTER TABLE biometric_enrollment_history DROP COLUMN {column}')
        conn.execute("CREATE TRIGGER biometric_enrollment_history_no_update BEFORE UPDATE ON biometric_enrollment_history BEGIN SELECT RAISE(ABORT,'Enrollment history is immutable'); END")
        conn.execute('PRAGMA user_version=33')


def test_legacy_backup_migration_restores_authenticated_backfilled_source_bindings(store,tmp_path):
    from sentriface.backup_service import BackupService
    a=store.create_person('Alice'); add(store,a,'legacy')
    downgrade_reference_fixture_to_v33(store.db_path)
    service=BackupService(store.db_path,tmp_path/'backups')
    backup=service.create_backup()
    assert backup.database_version==33 and backup.restorable
    service.restore_backup(backup.backup_id,str(__import__('uuid').uuid4()))
    upgraded=SQLiteIdentityStore(store.db_path,embedding_dim=2);upgraded.initialize()
    ref=catalog(upgraded,a)['references'][0]
    assert ref['no_context_declared']==0 and ref['person_id']==a.person_id
    assert __import__('pathlib').Path(ref['source_image']).is_file()


def test_v34_migration_is_atomic_repeatable_and_preserves_legacy_owner(store):
    a=store.create_person('Alice'); add(store,a,'legacy')
    eid=catalog(store,a)['references'][0]['embedding_id']
    downgrade_reference_fixture_to_v33(store.db_path)
    def fail(_): raise RuntimeError('injected migration failure')
    with patch('sentriface.storage.sqlite_store._refresh_source_biometric_status',side_effect=fail):
        with pytest.raises(Exception,match='injected migration failure'):
            SQLiteIdentityStore(store.db_path,embedding_dim=2).initialize()
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==33
        assert 'source_image' not in {r[1] for r in conn.execute('PRAGMA table_info(biometric_enrollment_history)')}
    store.initialize();store.initialize()
    ref=catalog(store,a)['references'][0]
    assert ref['person_id']==a.person_id and ref['embedding_id']==eid and ref['no_context_declared']==0


def test_new_provenance_malformed_binding_fails_closed(store):
    from sentriface.integrity import ReadOnlyIntegrityChecker
    a=store.create_person('Alice');add(store,a,'reference')
    # Deliberately corrupt only this isolated test database, never live authority.
    with store._connect() as conn:
        conn.execute('DROP TRIGGER biometric_enrollment_history_no_update')
        conn.execute('UPDATE biometric_enrollment_history SET source_image=NULL')
    report=ReadOnlyIntegrityChecker(store.db_path).run()
    assert any(f.invariant_id=='P11-REVIEW-001' for f in report.findings)


def test_reference_backend_uses_same_enrollment_permission_for_all_mutations():
    from sentriface.api_server import _required_capability
    for path in ('/api/reference-prepare','/api/reference-confirm','/api/reference-lifecycle','/api/reference-cancel'):
        assert _required_capability('POST',path)=='add'


def test_legacy_over_cap_restore_preserves_truth_and_blocks_new_activation(store,tmp_path):
    from sentriface.backup_service import BackupService
    a,b=[store.create_person(n) for n in ('A','Alias')]
    for i in range(6):add(store,a if i<3 else b,f'legacy-{i}',(.1+i*.1,.9-i*.1))
    # Existing historical authority could have merged before the cap existed.
    store._set_canonical_person_id_for_merge(b.person_id,a.person_id,'legacy-canonical-map')
    assert catalog(store,a)['active_count']==6
    service=BackupService(store.db_path,tmp_path/'backups');backup=service.create_backup()
    service.restore_backup(backup.backup_id,str(__import__('uuid').uuid4()))
    restarted=SQLiteIdentityStore(store.db_path,embedding_dim=2);restarted.initialize()
    assert catalog(restarted,a)['active_count']==6
    stage(restarted,a,'new',(.9,.1))
    with pytest.raises(ValueError,match='Four active'):
        restarted.add_face_to_person('new',a.person_id,'new-op',no_context_acknowledged=True)
    assert catalog(restarted,a)['active_count']==6


def test_shared_sample_profile_media_and_origins_follow_semantic_source(store):
    a,b=[store.create_person(n) for n in ('Alice','Bob')];add(store,a,'portrait')
    reference=catalog(store,a)['references'][0];eid=reference['embedding_id']
    occurrence=stage(store,a,'scene',source='check-photo')
    oid=store.complete_photo_review('scene','finalize')['observation_id']
    store.correct_observation_identity(oid,a.person_id,b.person_id,'correct')
    alice=store.list_embeddings_for_person(a.person_id)[0]
    bob=store.list_embeddings_for_person(b.person_id)[0]
    assert alice.source_image==reference['source_image'] and alice.person_id==a.person_id
    assert bob.source_image==str(occurrence) and bob.canonical_person_id==b.person_id
    assert [r['face_origin'] for r in store.face_origins_for_embeddings([eid],person_id=a.person_id)[eid]]==['STANDALONE_ENROLLMENT']
    assert [r['face_origin'] for r in store.face_origins_for_embeddings([eid],person_id=b.person_id)[eid]]==['ENCOUNTER']


def test_legacy_deleted_reference_is_never_purged_by_timed_retention(store):
    a=store.create_person('Alice');added=add(store,a,'legacy');eid=added['embedding_ids'][0]
    with store._connect() as conn:
        conn.execute("UPDATE embeddings SET deleted_at='2020-01-01',purge_after='2020-01-02' WHERE embedding_id=?",(eid,))
    assert store.list_expired_deleted_embedding_ids()==[]
    assert store.purge_expired_deleted_embeddings([eid],'legacy-retention')['purged']==0
    with pytest.raises(ValueError,match='history is retained'):
        store.permanently_delete_embedding(eid,'purge')
    assert catalog(store,a)['references'][0]['recognition_eligible'] is False


def test_media_relocation_does_not_change_encounter_or_attachment_precondition(store,tmp_path):
    from sentriface.backup_service import BackupService
    a=store.create_person('Alice');stage(store,a,'event',source='check-photo')
    oid=store.complete_photo_review('event','finalize')['observation_id']
    revision=store.get_encounter_read(oid)['revision']
    session=store.create_init_session('/attach',target_observation_id=oid,expected_revision=revision)
    image=tmp_path/'attachment.jpg';image.write_bytes(b'attachment')
    store.save_init_session_media(session.session_id,[str(image)])
    rid=store.plan_init_session_encounters(session.session_id,[[store.list_init_session_media(session.session_id)[0]['media_id']]],target_observation_id=oid,expected_revision=revision)[0]['review_id']
    service=BackupService(store.db_path,tmp_path/'backups');backup=service.create_backup()
    service.restore_backup(backup.backup_id,str(__import__('uuid').uuid4()))
    restored=SQLiteIdentityStore(store.db_path,embedding_dim=2);restored.initialize()
    assert restored.get_encounter_read(oid)['revision']==revision
    restored.complete_encounter_identity_review(rid)
    assert restored.complete_photo_review(rid,'finish-restored-attach')['observation_id']==oid


def test_v34_preserves_valid_and_stale_legacy_attachment_preconditions(store):
    from sentriface.storage.sqlite_store import _encounter_revision
    a=store.create_person('Alice');stage(store,a,'event',source='check-photo')
    oid=store.complete_photo_review('event','finalize')['observation_id']
    new=store.get_encounter_read(oid)['revision']
    with store._connect() as conn:old=_encounter_revision(conn,oid,include_media_locations=True)
    valid=store.create_init_session('/valid',target_observation_id=oid,expected_revision=new)
    stale=store.create_init_session('/stale',target_observation_id=oid,expected_revision=new)
    with store._connect() as conn:
        conn.execute('UPDATE init_sessions SET expected_encounter_revision=? WHERE session_id=?',(old,valid.session_id))
        conn.execute('UPDATE init_sessions SET expected_encounter_revision=? WHERE session_id=?',('genuinely-stale',stale.session_id))
    downgrade_reference_fixture_to_v33(store.db_path)
    store.initialize()
    assert store.get_init_session(valid.session_id).expected_encounter_revision==new
    assert store.get_init_session(stale.session_id).expected_encounter_revision=='genuinely-stale'


def test_legacy_exact_reference_aliases_count_and_contribute_once_without_erasing_history(store):
    a,b=[store.create_person(n) for n in ('Alice','Alias')]
    add(store,a,'a-source');add(store,b,'b-source',(.2,.8))
    first=catalog(store,a)['references'][0];second=catalog(store,b)['references'][0]
    # Reproduce only a retained pre-admission-guard duplicate, in this test store.
    with store._connect() as conn:
        conn.execute('DROP TRIGGER biometric_enrollment_history_no_update')
        conn.execute('UPDATE biometric_enrollment_history SET source_media_id=?,source_image=?,no_context_declared=0 WHERE enrollment_id=?',
                     (first['source_media_id'],first['source_image'],second['reference_id']))
        conn.execute('UPDATE embeddings SET vector=(SELECT vector FROM embeddings WHERE embedding_id=?) WHERE embedding_id=?',
                     (first['embedding_id'],second['embedding_id']))
    store.execute_identity_merge(b.person_id,a.person_id,'merge')
    assert catalog(store,a)['active_count']==1
    assert len(catalog(store,a)['references'])==2  # raw source history is inspectable
    assert len(store.list_embeddings())==1
    lifecycle(store,a,first,False,'retire-a')
    assert catalog(store,a)['active_count']==1 and len(store.list_embeddings())==1
    lifecycle(store,a,second,False,'retire-b')
    assert catalog(store,a)['active_count']==0 and store.list_embeddings()==[]
    assert len(catalog(store,a)['references'])==2


def test_reference_lifecycle_provenance_rejects_wrong_journal_meaning(store):
    from sentriface.integrity import ReadOnlyIntegrityChecker
    a=store.create_person('Alice');add(store,a,'reference');ref=catalog(store,a)['references'][0]
    with store._connect() as conn:
        conn.execute('INSERT INTO recognition_reference_revisions VALUES(?,?,?,?,?)',
                     ('malformed',ref['reference_id'],0,'add-reference','2026-10-01'))
    report=ReadOnlyIntegrityChecker(store.db_path).run()
    assert any(f.invariant_id=='P11-REVIEW-001' for f in report.findings)
