"""Effective frame authority must converge across mutation order and history."""
from pathlib import Path
import pytest
from sentriface.models import DetectedFace, FaceBox, InitFace, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore


def encounter(store, people, frames):
    session = store.create_init_session('/managed/batch35')
    paths = sorted(set(frames))
    store.save_init_session_media(session.session_id, paths)
    faces = [InitFace(init_face_id=f'{session.session_id}-{i}', session_id=session.session_id,
        group_id=f'g{i}', source_image=frame, face=DetectedFace(FaceBox(1, 1, 10, 10, .99), .9),
        vector=(.1+i*.13, .9-i*.13), quality=QualityReport(QualityStatus.GOOD, .9))
        for i, frame in enumerate(frames)]
    store.save_init_faces(faces)
    review = store.plan_init_session_encounters(session.session_id, [[m['media_id'] for m in store.list_init_session_media(session.session_id)]])[0]
    rid = review['review_id']
    store.save_encounter_review_event(rid, {'date': '2026-10-01', 'time_precision': 'unknown', 'event_context': 'ordinary'})
    for face, person in zip(faces, people):
        store.set_photo_review_face_decision(rid, face.init_face_id, 'ACCEPT_EXISTING_PERSON', person_id=person.person_id)
    ready = store.complete_encounter_identity_review(rid)
    for pair in ready['relation_candidates']:
        store.set_encounter_relation_decision(rid, pair['first_ref'], pair['second_ref'], 'INCLUDE')
    return store.complete_photo_review(rid, f'complete-{rid}')['observation_id']


@pytest.mark.parametrize('reverse_rows', [False, True])
@pytest.mark.parametrize('reverse_merge', [False, True])
@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('correction_order', ['none', 'before', 'after', 'participant-before', 'participant-after'])
def test_pair_support_converges(tmp_path, reverse_rows, reverse_merge, shared, correction_order):
    path = tmp_path / 'authority.db'
    store = SQLiteIdentityStore(path, embedding_dim=2); store.initialize()
    a, alias, c = [store.create_person(n) for n in ('A', 'Alias A', 'C')]
    people = [a, c, alias, a]
    frames = ['/managed/shared.jpg', '/managed/shared.jpg' if shared else '/managed/c.jpg', '/managed/alias.jpg', '/managed/shared.jpg']
    if reverse_rows:
        people.reverse(); frames.reverse()
    oid = encounter(store, people, frames)
    def correct(op):
        current = store.get_encounter_read(oid)
        store.correct_encounter(oid, op, expected_revision=current['revision'],
            relations=[{k:v for k,v in pair.items() if k != 'support'} for pair in current['relations']])
    def reassign():
        nonlocal c
        replacement=store.create_person('Corrected C')
        current=store.get_encounter_read(oid)
        store.correct_encounter(oid,'participant-correction',expected_revision=current['revision'],participant_correction={'action':'REASSIGN','person_id':c.person_id,'to_person_id':replacement.person_id})
        c=replacement
    if correction_order=='participant-before': reassign()
    if correction_order == 'before': correct('before')
    source, target = (a, alias) if reverse_merge else (alias, a)
    store.execute_identity_merge(source.person_id, target.person_id, 'merge')
    def support():
        pairs = store.get_encounter_read(oid)['relations']
        assert len(pairs) == 1
        assert pairs[0]['support'] == ('SHARED_FRAME' if shared else 'SAME_ENCOUNTER_ONLY')
        assert pairs[0]['disposition'] == 'INCLUDE'
        assert len(store.get_connection_evidence(target.person_id, c.person_id)) == 1
    support()
    # Restart/rebuild happen before any corrective recomputation.
    store = SQLiteIdentityStore(path, embedding_dim=2); store.initialize(); support()
    store.rebuild_graph_projection('immediate-rebuild'); support()
    if correction_order == 'after': correct('after'); support()
    if correction_order=='participant-after': reassign(); support()
    for i in range(6):
        current = store.get_encounter_read(oid)
        disposition = 'EXCLUDE' if i % 2 == 0 else 'INCLUDE'
        store.correct_encounter(oid, f'correction-{i}', expected_revision=current['revision'], relations=[{**{k:v for k,v in current['relations'][0].items() if k != 'support'}, 'disposition': disposition}])
        current_count = int(disposition == 'INCLUDE')
        assert len(store.get_connection_evidence(target.person_id, c.person_id)) == current_count
        assert len(store.get_person_intelligence(target.person_id).relationships) == current_count
        assert len(store.get_person_graph_read(target.person_id).edges) == current_count
        assert len(store.get_world_graph_read().edges) == current_count
        from sentriface.models import WorldGraphRequest, WorldDetailLevel
        world = store.get_world_graph_v2_read(WorldGraphRequest(detail_level=WorldDetailLevel.PERSON, focus_type='PERSON', focus_id=target.person_id, as_of='2026-10-03T00:00:00+00:00'))
        assert len(world.relationships) == current_count
        store.rebuild_graph_projection(f'rebuild-{i}')
        assert len(store.get_connection_evidence(target.person_id, c.person_id)) == (disposition == 'INCLUDE')
    support()
    assert any(not item.active for item in store.get_connection_evidence(target.person_id, c.person_id, include_inactive=True))
    assert store.validate_graph_projection()['valid']


def test_lifecycle_early_validation_and_transaction_revalidation(tmp_path):
    store = SQLiteIdentityStore(tmp_path/'state.db', embedding_dim=2); store.initialize()
    a = store.create_person('A')
    store.validate_person_lifecycle_operation(a.person_id, 'archive', 'archive-person')
    session = store.create_init_session('/managed/draft')
    store.save_init_session_media(session.session_id, ['/managed/draft.jpg'])
    face = InitFace(init_face_id='draft-face', session_id=session.session_id, group_id='draft-group', source_image='/managed/draft.jpg',
        face=DetectedFace(FaceBox(1, 1, 10, 10, .99), .9), vector=(.2,.8), quality=QualityReport(QualityStatus.GOOD,.9))
    store.save_init_faces([face])
    review = store.plan_init_session_encounters(session.session_id, [[store.list_init_session_media(session.session_id)[0]['media_id']]])[0]
    store.save_encounter_review_event(review['review_id'], {'time_precision': 'unknown'})
    store.set_photo_review_face_decision(review['review_id'], face.init_face_id, 'ACCEPT_EXISTING_PERSON', person_id=a.person_id)
    for action in (lambda: store.validate_person_lifecycle_operation(a.person_id, 'archive', 'archive-person'), lambda: store.archive_person(a.person_id, 'archive')):
        with pytest.raises(ValueError, match='active Encounter'): action()
    assert store.get_operation('archive') is None

@pytest.mark.parametrize('quality_state', ['GOOD', 'POOR_ACCEPTED', 'PROOF_ONLY'])
def test_no_face_standalone_enrollment_keeps_origin_and_restart(tmp_path, quality_state):
    from tests.test_photo_review_finalization import PhotoReviewFinalizationTest
    helper=PhotoReviewFinalizationTest()
    store=helper._store(tmp_path)
    person=store.create_person('Explicit target')
    assert store.get_person(person.person_id).biometric_status=='NO_FACE'
    quality=QualityStatus.GOOD if quality_state=='GOOD' else QualityStatus.BAD
    helper._pending(store,'incoming','/managed/enrollment.jpg',(.3,.7),quality)
    store.create_photo_review('enrollment','enrollment.jpg',[{'face_id':'face-1','staged_face_type':'PENDING_ADDITION','staged_face_id':'incoming'}],media_path='/managed/enrollment.jpg', source='reference-only')
    store.set_photo_review_face_decision('enrollment','face-1','ACCEPT_EXISTING_PERSON',person_id=person.person_id, recognition_detail={'embedding_state':quality_state})
    result=store.add_face_to_person('enrollment',person.person_id,'enroll',no_context_acknowledged=True)
    assert result==store.add_face_to_person('enrollment',person.person_id,'enroll',no_context_acknowledged=True)
    reopened=helper._store(tmp_path)
    assert reopened.get_person(person.person_id).biometric_status==('NO_FACE' if quality_state=='PROOF_ONLY' else 'ENROLLED')
    records=reopened.list_embeddings_for_person(person.person_id)
    assert len(records)==1 and records[0].recognition_state==quality_state
    origin=reopened.face_origins_for_embeddings([records[0].embedding_id])[records[0].embedding_id]
    assert origin[0]['face_origin']=='STANDALONE_ENROLLMENT'
    assert reopened.query_encounters()['events']==[]
    assert bool(reopened.current_embedding_person_ids([records[0].embedding_id],quality_only=False)) == (quality_state!='PROOF_ONLY')


def test_guarded_lifecycle_does_not_make_safety_copy_and_allowed_archive_does(tmp_path):
    from unittest.mock import Mock
    from sentriface.api_server import create_server
    server=create_server(data_dir=tmp_path/'authority',port=0,runtime='dev')
    try:
        store=server.engine.store; a=store.create_person('Guarded Person')
        session=store.create_init_session('/managed/draft'); store.save_init_session_media(session.session_id,['/managed/draft.jpg'])
        face=InitFace(init_face_id='draft-face',session_id=session.session_id,group_id='draft-group',source_image='/managed/draft.jpg',
            face=DetectedFace(FaceBox(1,1,10,10,.99),.9),vector=tuple([.1]*server.config.embedding_dim),quality=QualityReport(QualityStatus.GOOD,.9))
        store.save_init_faces([face])
        review=store.plan_init_session_encounters(session.session_id,[[store.list_init_session_media(session.session_id)[0]['media_id']]])[0]
        store.save_encounter_review_event(review['review_id'],{'time_precision':'unknown'})
        store.set_photo_review_face_decision(review['review_id'],face.init_face_id,'ACCEPT_EXISTING_PERSON',person_id=a.person_id)
        server.backups.create_backup=Mock(wraps=server.backups.create_backup)
        for operation_type,action in [('archive-person',lambda:store.archive_person(a.person_id,'archive')),('purge-person',lambda:store.permanently_delete_person(a.person_id,'delete'))]:
            with pytest.raises(ValueError,match='active Encounter'):
                server.backed_up_people_deletion(operation_type,operation_type,'guard',action,person_id=a.person_id)
        server.backups.create_backup.assert_not_called()
        store.cancel_photo_review(review['review_id'])
        result=server.backed_up_people_deletion('archive','archive-person','allowed',lambda:store.archive_person(a.person_id,'archive'),person_id=a.person_id)
        assert result['archived'] and result['backup']
        server.backups.create_backup.assert_called_once()
    finally: server.server_close()


def test_multiple_strong_alias_paths_are_one_current_pair(tmp_path):
    store=SQLiteIdentityStore(tmp_path/'authority.db',embedding_dim=2);store.initialize()
    a,alias,weak,c=[store.create_person(n) for n in ('A','Strong alias','Weak alias','C')]
    oid=encounter(store,[a,c,alias,c,weak],['/managed/frame-1.jpg','/managed/frame-1.jpg','/managed/frame-2.jpg','/managed/frame-2.jpg','/managed/frame-3.jpg'])
    for source in (alias,weak):
        store.execute_identity_merge(source.person_id,a.person_id,'merge-'+source.person_id)
        store.rebuild_graph_projection('rebuild-'+source.person_id)
        relations=store.get_encounter_read(oid)['relations']
        current=next(pair for pair in relations if {pair['first_person_id'],pair['second_person_id']}=={a.person_id,c.person_id})
        assert current['support']=='SHARED_FRAME'
    assert len(relations)==1 and len(store.get_connection_evidence(a.person_id,c.person_id))==1
    store.create_manual_association(a.person_id,c.person_id,'manual')
    store.create_note(a.person_id,'Selected C','note-a',mentioned_person_ids=[c.person_id])
    store.create_note(c.person_id,'Selected A','note-c',mentioned_person_ids=[a.person_id])
    intelligence=store.get_person_intelligence(a.person_id)
    from sentriface.api_server import _person_intelligence
    assert _person_intelligence(intelligence)['relationship_count']==1
    assert len(intelligence.relationships)>1


def test_restore_completed_review_relocates_media_without_changing_authority(tmp_path):
    from sentriface.backup_service import BackupService
    import uuid
    path=tmp_path/'source'/'sentriface.db';store=SQLiteIdentityStore(path,embedding_dim=2);store.initialize()
    frame=tmp_path/'frame.jpg';frame.write_bytes(b'qualification media')
    a,c=[store.create_person(n) for n in ('A','C')]
    oid=encounter(store,[a,c],[str(frame),str(frame)])
    source=BackupService(path,tmp_path/'source/backups',data_dir=path.parent)
    backup=source.create_backup()
    result=source.restore_backup(backup.backup_id,str(uuid.uuid4()))
    assert result['restored']
    reopened=SQLiteIdentityStore(path,embedding_dim=2);reopened.initialize()
    assert reopened.get_encounter_read(oid)['relations'][0]['support']=='SHARED_FRAME'
    with reopened._connect() as conn:
        row=conn.execute("SELECT review_id,media_path FROM photo_reviews WHERE status='COMPLETED'").fetchone()
        assert 'restored-media' in row['media_path']
        assert Path(row['media_path']).is_file()
        with pytest.raises(Exception,match='completed reviews are immutable'):
            conn.execute("UPDATE photo_reviews SET source='changed' WHERE review_id=?",(row['review_id'],))


def test_restore_media_relocation_failure_rolls_back_guard_and_paths(tmp_path,monkeypatch):
    from sentriface.backup_service import BackupService, BackupError
    from sentriface.media_registry import update_media_reference
    import shutil
    path=tmp_path/'source.db';store=SQLiteIdentityStore(path,embedding_dim=2);store.initialize()
    frame=tmp_path/'frame.jpg';frame.write_bytes(b'media')
    a,c=[store.create_person(n) for n in ('A','C')];encounter(store,[a,c],[str(frame),str(frame)])
    service=BackupService(path,tmp_path/'backups',data_dir=tmp_path)
    candidate=tmp_path/'candidate.db';shutil.copy2(path,candidate)
    with store._connect() as conn:
        review_id=conn.execute('SELECT review_id FROM photo_reviews').fetchone()['review_id']
    reference={'registry_id':'photo_reviews.media_path','row_identity':{'review_id':review_id},'archive_path':'files/frame.jpg'}
    def illegal_rewrite(conn,spec,identity,new_path):
        update_media_reference(conn,spec,identity,new_path)
        conn.execute("UPDATE photo_reviews SET source='illegal' WHERE review_id=?",identity)
    monkeypatch.setattr('sentriface.backup_service.update_media_reference',illegal_rewrite)
    with pytest.raises(BackupError,match='changed review authority'):
        service._rewrite_database_paths(candidate,{'format_version':3,'path_references':[reference]},{'files/frame.jpg':'/new/frame.jpg'})
    reopened=SQLiteIdentityStore(candidate,embedding_dim=2)
    with reopened._connect() as conn:
        assert conn.execute('SELECT media_path FROM photo_reviews').fetchone()['media_path']==str(frame)
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name='completed_photo_reviews_immutable'").fetchone()
    with pytest.raises(BackupError,match='disposable'):
        service._rewrite_database_paths(path,{}, {})


def test_dense_historical_generations_do_not_change_current_pair_or_world_authority(tmp_path,monkeypatch):
    from unittest.mock import Mock
    import sentriface.storage.sqlite_store as implementation
    store=SQLiteIdentityStore(tmp_path/'dense.db',embedding_dim=2);store.initialize()
    people=[store.create_person('P'+str(i)) for i in range(12)]
    alias=store.create_person('Alias P0')
    frames=['/managed/left.jpg']*6+['/managed/right.jpg']*6
    oid=encounter(store,[*people,alias],[*frames,'/managed/right.jpg'])
    store.execute_identity_merge(alias.person_id,people[0].person_id,'dense-merge')
    store.rebuild_graph_projection('dense-immediate-rebuild')
    original=implementation._encounter_person_media
    lookup=Mock(wraps=original);monkeypatch.setattr(implementation,'_encounter_person_media',lookup)
    current=store.get_encounter_read(oid)
    assert len(current['relations'])==66
    assert lookup.call_count==12  # one frame set per canonical Person, not per pair
    for relation in current['relations']:
        pair={relation['first_person_id'],relation['second_person_id']}
        indices=[i for i,p in enumerate(people) if p.person_id in pair]
        shared=0 in indices or all(i<6 for i in indices) or all(i>=6 for i in indices)
        assert relation['support']==('SHARED_FRAME' if shared else 'SAME_ENCOUNTER_ONLY')
    for i in range(6):
        current=store.get_encounter_read(oid)
        desired=[{k:v for k,v in r.items() if k!='support'} for r in current['relations']]
        desired[0]['disposition']='EXCLUDE' if i%2==0 else 'INCLUDE'
        store.correct_encounter(oid,'dense-correction-'+str(i),expected_revision=current['revision'],relations=desired)
        store.rebuild_graph_projection('dense-rebuild-'+str(i))
        assert len(store.get_world_graph_read().edges)==(65 if i%2==0 else 66)
    with store._connect() as conn:
        historical=conn.execute('SELECT COUNT(*) FROM relationship_evidence').fetchone()[0]
        active=conn.execute('SELECT COUNT(*) FROM relationship_evidence WHERE active=1').fetchone()[0]
    assert historical>active*5 and active==66
    assert len(store.get_person_intelligence(people[0].person_id).relationships)==11
    assert all(edge.relationship_strength==1 for edge in store.get_world_graph_read().edges)
    assert store.validate_graph_projection()['valid']
