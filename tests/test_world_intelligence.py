"""Issue #3: additive World reads over disposable authoritative fixtures."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import itertools
import json
import time
import uuid

import pytest

from sentriface.api_server import _world_graph_v2_request_from_query, _world_graph_v2_payload
from sentriface.backup_service import BackupService
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.merge_service import IdentityMergeService
from sentriface.models import WorldCollection as C, WorldDetailLevel as L, WorldGraphRequest as Request, WorldReadFilter as Filter, WorldReadLimits as Limits
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.models import InitFace, DetectedFace, FaceBox, QualityReport, QualityStatus
from tests import test_world_graph_v2 as world_helpers
from tests import test_identity_corrections as correction_helpers

AS_OF = '2026-10-27T12:00:00+00:00'
TYPES = ('CO_OBSERVED', 'NOTE_REFERENCE', 'MANUAL_ASSOCIATION')


@pytest.fixture
def store(tmp_path):
    result = SQLiteIdentityStore(tmp_path / 'identity.db', embedding_dim=2)
    result.initialize()
    return result


def observe(store, label, people, date='2026-10-22T10:00:00+00:00', location='Delhi', media=0):
    return world_helpers.WorldGraphV2Test()._observe(store, label, [p.person_id for p in people], observed_at=date, location=location, media_count=media)


def read(store, collection=C.RELATIONSHIPS, **kwargs):
    return store.get_world_graph_v2_read(Request(collection=collection, as_of=AS_OF, **kwargs))


def explore(store, types=TYPES, threshold=2, **kwargs):
    return read(store, view='EXPLORE', filters=Filter(evidence_type=types, min_relationship_strength=threshold), **kwargs)


def note(store, a, b, op):
    return GlobalIdentityGraphService(store).create_note(a.person_id, 'Selected mention', op, mentioned_person_ids=[b.person_id])


def test_all_evidence_combinations_and_current_explore_independence(store):
    a, b = [store.create_person(n) for n in ('A', 'B')]
    observe(store, 'pair', [a, b], media=5)
    note(store, a, b, 'note')
    store.create_manual_association(a.person_id, b.person_id, 'manual')
    current = read(store)
    assert current.effective_filters.min_relationship_strength is None
    assert current.effective_filters.evidence_type == ()
    assert current.relationships[0].evidence_count == 3
    for size in (1, 2, 3):
        for types in itertools.combinations(TYPES, size):
            for threshold in (1, 2, 4, 100):
                result = explore(store, types, threshold, include_below_threshold=True)
                edge = result.relationships[0]
                assert edge.selected_evidence_strength == size
                assert edge.evidence_type_counts == {t: 1 for t in types}
                assert edge.qualifies_for_cluster == (size >= threshold)
                assert result.scope_totals['clusters'] == int(size >= threshold)
                assert edge.encounter_recurrence['count'] == 1
                assert len(edge.encounter_recurrence['supporting_encounters']) == 1
    assert asdict(read(store)) | {'generated_at': ''} == asdict(current) | {'generated_at': ''}
    default = read(store, view='EXPLORE', filters=Filter(evidence_type=('CO_OBSERVED',)))
    assert default.effective_filters.min_relationship_strength == 2
    assert default.scope_totals['clusters'] == 0


@pytest.mark.parametrize('threshold', [0, -1, 1.5, True, '2'])
def test_invalid_thresholds(store, threshold):
    with pytest.raises(ValueError, match='positive integer'):
        explore(store, threshold=threshold)


@pytest.mark.parametrize('types', [(), ('BOGUS',), ('',)])
def test_invalid_evidence_selection(store, types):
    with pytest.raises(ValueError):
        explore(store, types=types)


def test_topologies_bridges_and_no_indirect_edges(store):
    a, b, c, d, e, f = [store.create_person(n) for n in 'ABCDEF']
    for index, (other, strength) in enumerate(((b, 5), (c, 4), (d, 6), (e, 20))):
        for occurrence in range(strength):
            observe(store, f'star-{index}-{occurrence}', [a, other])
    observe(store, 'weak', [e, f])
    result = explore(store, ('CO_OBSERVED',), 4, include_below_threshold=True)
    assert result.scope_totals['clusters'] == 1
    cluster_id = read(store, C.CLUSTERS, view='EXPLORE', filters=Filter(evidence_type=('CO_OBSERVED',), min_relationship_strength=4)).clusters[0].cluster_id
    assert result.scope_totals['relationships'] == 5
    assert sum(e.qualifies_for_cluster for e in result.relationships) == 4
    assert all(a.person_id in (r.source_person_id, r.target_person_id) or f.person_id in (r.source_person_id, r.target_person_id) for r in result.relationships)
    members = store.get_world_graph_v2_read(Request(detail_level=L.CLUSTER, focus_type='CLUSTER', focus_id=cluster_id, as_of=AS_OF, view='EXPLORE', include_below_threshold=True, filters=Filter(evidence_type=('CO_OBSERVED',), min_relationship_strength=4)))
    assert {p.canonical_person_id for p in members.people} == {p.person_id for p in (a,b,c,d,e)}
    assert cluster_id == read(store, C.CLUSTERS, view='EXPLORE', include_below_threshold=True, filters=Filter(evidence_type=('CO_OBSERVED',), min_relationship_strength=4)).clusters[0].cluster_id
    for i in range(3):
        observe(store, f'bridge-{i}', [e, f])
    assert read(store, C.CLUSTERS, view='EXPLORE', filters=Filter(evidence_type=('CO_OBSERVED',), min_relationship_strength=4)).clusters[0].member_count == 6


def test_two_components_chain_and_qualifying_bridge(store):
    a,b,c,d,e = [store.create_person(n) for n in 'ABCDE']
    for x,y in ((a,b),(b,c),(d,e)):
        for n in range(2):
            observe(store, f'{x.name}-{y.name}-{n}', [x,y])
    assert explore(store).scope_totals['clusters'] == 2
    observe(store, 'weak-bridge', [c,d])
    assert explore(store).scope_totals['clusters'] == 2
    observe(store, 'qualifying-bridge', [c,d])
    assert explore(store).scope_totals['clusters'] == 1
    assert len(explore(store).relationships) == 4


def test_recurrence_canonical_collapse_direction_and_retirement(store):
    a,b,c = [store.create_person(n) for n in 'ABC']
    oid = observe(store, 'same', [a,b,c], media=4)
    observe(store, 'independent', [a,b])
    saved = note(store, a,b,'forward')
    note(store, b,a,'reverse')
    manual = store.create_manual_association(a.person_id,b.person_id,'manual')
    IdentityMergeService(store).execute(c.person_id,b.person_id,'merge-c')
    edge = explore(store, threshold=1).relationships[0]
    assert edge.encounter_recurrence['count'] == 2
    assert edge.evidence_type_counts == {'CO_OBSERVED':3,'NOTE_REFERENCE':2,'MANUAL_ASSOCIATION':1}
    assert edge.direction_counts[f'{a.person_id}->{b.person_id}'] == 1
    assert edge.note_reference_direction_counts=={f'{a.person_id}->{b.person_id}':1,f'{b.person_id}->{a.person_id}':1}
    assert edge.direction_counts[f'{b.person_id}->{a.person_id}'] == 1
    assert len(explore(store, threshold=1).relationships) == 1
    GlobalIdentityGraphService(store).update_note(saved.note_id, 'Removed mention', 'edit', mentioned_person_ids=[])
    store.retire_manual_association(manual['evidence_id'], 'retire')
    edge = explore(store, threshold=1).relationships[0]
    assert edge.selected_evidence_strength == 4
    assert edge.encounter_recurrence['count'] == 2
    evidence = read(store, C.EVIDENCE, detail_level=L.EVIDENCE, focus_type='RELATIONSHIP', focus_id=edge.relationship_id, view='EXPLORE', filters=Filter(evidence_type=TYPES))
    assert any(e.raw_endpoints != e.effective_endpoints for e in evidence.evidence)
    assert {e.supporting_references[0]['source_entity_id'] for e in evidence.evidence if e.evidence_type == 'CO_OBSERVED'} >= {oid}


def test_latest_calendar_day_all_encounters_and_no_manufactured_results(store):
    assert read(store, C.MOST_RECENTLY_SEEN).discovery_context['latest_observed_day'] is None
    a,b,c,d = [store.create_person(n) for n in 'ABCD']
    observe(store,'old',[d],date='2026-10-20T23:00:00+00:00')
    ids = {observe(store,'morning',[a,b]), observe(store,'noon',[b,c],date='2026-10-22T12:00:00+00:00'), observe(store,'evening',[a],date='2026-10-22T20:00:00+00:00')}
    result = read(store,C.MOST_RECENTLY_SEEN)
    assert result.discovery_context['latest_observed_day'] == '2026-10-22'
    assert {p.canonical_person_id for p in result.discoveries} == {p.person_id for p in (a,b,c)}
    assert {e['event_id'] for p in result.discoveries for e in p.supporting_encounters} == ids
    scoped = read(store,C.MOST_RECENTLY_SEEN,filters=Filter(date_to='2026-10-20'))
    assert [p.canonical_person_id for p in scoped.discoveries] == [d.person_id]


@pytest.mark.parametrize('period', [7,30,90])
def test_frequency_rolling_boundaries_and_support_caps(store,period):
    a = store.create_person('A')
    boundary = datetime.fromisoformat(AS_OF)-timedelta(days=period)
    for n, delta in enumerate((-1,0,1)):
        observe(store, f'boundary-{n}',[a],date=(boundary+timedelta(seconds=delta)).isoformat())
    observe(store,'future',[a],date='2027-01-01T00:00:00+00:00')
    result = read(store,C.MOST_FREQUENTLY_SEEN,discovery_period_days=period,limits=Limits(events=1))
    assert result.discoveries[0].count == 2
    assert len(result.discoveries[0].supporting_encounters) == 1
    assert result.discoveries[0].supporting_encounters_state['truncated']
    assert result.discovery_context['period_days'] == period


def test_locations_normalization_missing_values_and_suggestions(store):
    a,b = [store.create_person(n) for n in 'AB']
    for n,location in enumerate((' Delhi ', 'DELHI', 'New   Delhi', 'new delhi', None, '   ')):
        observe(store,f'loc-{n}',[a],location=location)
    observe(store,'single',[b],location='Delhi')
    result = read(store,C.MULTIPLE_LOCATIONS)
    assert len(result.discoveries) == 1
    row = result.discoveries[0]
    assert row.canonical_person_id == a.person_id
    assert row.count == 2 and row.missing_location_count == 2
    assert len(row.locations) == 2
    assert len(row.supporting_encounters) == 6
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='de').available_facets['locations'] == []
    suggestions = read(store,C.LOCATION_SUGGESTIONS,location_query=' DEL ').available_facets['locations']
    assert len(suggestions) == 2
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='new   d').available_facets['locations'][0]['value'] == 'New Delhi'
    paged = read(store,C.LOCATION_SUGGESTIONS,location_query='del',limits=Limits(facets=1))
    assert paged.has_more
    second = read(store,C.LOCATION_SUGGESTIONS,location_query='del',limits=Limits(facets=1),cursor=paged.next_cursor)
    assert not second.has_more
    assert second.available_facets['locations'] != paged.available_facets['locations']


def test_discovery_pagination_fingerprints_and_stale_revisions(store):
    people = [store.create_person(str(i)) for i in range(4)]
    observe(store,'all',people)
    req = Request(collection=C.MOST_FREQUENTLY_SEEN,as_of=AS_OF,limits=Limits(people=2))
    first = store.get_world_graph_v2_read(req)
    again = store.get_world_graph_v2_read(req)
    assert first.discoveries == again.discoveries
    second = store.get_world_graph_v2_read(replace(req,cursor=first.next_cursor))
    assert not ({p.canonical_person_id for p in first.discoveries}&{p.canonical_person_id for p in second.discoveries})
    for changes in ({'discovery_period_days':7},{'include_below_threshold':True},{'collection':C.MULTIPLE_LOCATIONS},{'location_query':'changed'}):
        with pytest.raises(ValueError,match='cursor'):
            store.get_world_graph_v2_read(replace(req,cursor=first.next_cursor,**changes))
    observe(store,'new',people[:2])
    with pytest.raises(ValueError,match='stale'):
        store.get_world_graph_v2_read(replace(req,revision=first.graph_revision))
    with pytest.raises(ValueError):
        store.get_world_graph_v2_read(replace(req,cursor=first.next_cursor))


def test_query_validation_and_additive_payload(store):
    request = _world_graph_v2_request_from_query('view=EXPLORE&evidence_type=CO_OBSERVED,NOTE_REFERENCE&include_below_threshold=true&collection=MOST_FREQUENTLY_SEEN&discovery_period_days=7')
    assert request.view == 'EXPLORE' and request.include_below_threshold
    assert request.filters.evidence_type == TYPES[:2]
    payload = _world_graph_v2_payload(store.get_world_graph_v2_read(request))
    assert payload['discoveries'] == []
    for query in ('min_relationship_strength=2.5','include_below_threshold=yes','discovery_period_days=x'):
        with pytest.raises(ValueError):
            _world_graph_v2_request_from_query(query)
    for days in (0,8,31,True):
        with pytest.raises(ValueError):
            read(store,C.MOST_FREQUENTLY_SEEN,discovery_period_days=days)


def test_corrections_exclusions_history_and_reference_only(store):
    a,b,c,d = [store.create_person(n) for n in 'ABCD']
    oid = correction_helpers.IdentityCorrectionTest()._finalize(store,'corrected',[a,b])['observation_id']
    def correct(op, **values):
        return store.correct_encounter(oid,op,expected_revision=store.get_encounter_read(oid)['revision'],**values)
    correct('metadata',event_details={'date':'2026-10-22','place_seen':'Delhi','event_mentioned_person_ids':[d.person_id]})
    assert explore(store, threshold=1).relationships[0].encounter_recurrence['count'] == 1
    proof = explore(store,threshold=1).relationships[0]
    evidence = read(store,C.EVIDENCE,detail_level=L.EVIDENCE,focus_type='RELATIONSHIP',focus_id=proof.relationship_id,view='EXPLORE',filters=Filter(evidence_type=TYPES))
    assert evidence.evidence[0].provenance['encounter_support'] == 'SAME_ENCOUNTER_ONLY'
    pair = {'first_person_id':a.person_id,'second_person_id':b.person_id,'disposition':'EXCLUDE'}
    correct('exclude',relations=[pair])
    assert not explore(store,threshold=1).relationships
    assert len(read(store,C.MOST_RECENTLY_SEEN).discoveries) == 2
    correct('include',relations=[{**pair,'disposition':'INCLUDE'}])
    store.correct_observation_identity(oid,b.person_id,c.person_id,'reassign')
    edge = explore(store,threshold=1).relationships[0]
    assert {edge.source_person_id,edge.target_person_id} == {a.person_id,c.person_id}
    correct('remove-c',participant_correction={'action':'REMOVE','person_id':c.person_id},relations=[])
    assert not explore(store,threshold=1).relationships
    store.rebuild_graph_projection('rebuild-after-removal')
    store.initialize()
    assert {p.canonical_person_id for p in read(store,C.MOST_RECENTLY_SEEN).discoveries} == {a.person_id}
    # A standalone biometric/Reference source is not Encounter presence.
    store.add_embedding(d.person_id,(0.1,0.9),0.9)
    store.archive_person(a.person_id,'archive-a')
    assert read(store,C.MOST_RECENTLY_SEEN).discoveries[0].canonical_person_id == a.person_id
    store.permanently_delete_person(a.person_id,'delete-a')
    assert read(store,C.MOST_RECENTLY_SEEN).discoveries[0].canonical_person_id == a.person_id
    assert not read(store,C.MOST_RECENTLY_SEEN,filters=Filter(lifecycle=('ACTIVE',))).discoveries


def test_saved_location_authority_cancellation_failure_and_correction(store):
    a = store.create_person('A')
    oid = correction_helpers.IdentityCorrectionTest()._finalize(store,'saved',[a])['observation_id']
    revision = store.get_encounter_read(oid)['revision']
    with pytest.raises(ValueError):
        store.correct_encounter(oid,'failed',expected_revision='stale',event_details={'place_seen':'Failed place'})
    assert not read(store,C.LOCATION_SUGGESTIONS,location_query='Failed').available_facets['locations']
    store.correct_encounter(oid,'save-place',expected_revision=revision,event_details={'date':'2026-10-22','place_seen':'Saved place'})
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='Saved').available_facets['locations'] == [{'value':'Saved place','count':1}]
    session = store.create_init_session('/managed/draft')
    store.save_init_session_media(session.session_id,['/managed/draft.jpg'])
    store.save_init_faces([InitFace(init_face_id='draft-face',session_id=session.session_id,group_id='draft-group',source_image='/managed/draft.jpg',face=DetectedFace(FaceBox(1,1,10,10,.9),.9),vector=(.3,.7),quality=QualityReport(QualityStatus.GOOD,.9))])
    media = store.list_init_session_media(session.session_id)[0]['media_id']
    review = store.plan_init_session_encounters(session.session_id,[[media]])[0]['review_id']
    store.save_encounter_review_event(review,{'date':'2026-10-22','place_seen':'Cancelled place'})
    assert not read(store,C.LOCATION_SUGGESTIONS,location_query='Cancelled').available_facets['locations']
    store.cancel_photo_review(review)
    assert not read(store,C.LOCATION_SUGGESTIONS,location_query='Cancelled').available_facets['locations']
    store.correct_encounter(oid,'correct-place',expected_revision=store.get_encounter_read(oid)['revision'],event_details={'place_seen':'Correct place'})
    assert not read(store,C.LOCATION_SUGGESTIONS,location_query='Saved').available_facets['locations']
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='Correct').available_facets['locations']
    with store._connect() as conn:
        assert conn.execute('SELECT location FROM observations WHERE observation_id=?',(oid,)).fetchone()[0] != 'Correct place'
    assert not read(store,C.MULTIPLE_LOCATIONS).discoveries


def test_rebuild_restart_encrypted_backup_restore_equivalence(tmp_path):
    key = bytes(range(32))
    store = SQLiteIdentityStore(tmp_path/'data'/'identity.db',embedding_dim=2,database_key=key)
    store.initialize()
    a,b = [store.create_person(n) for n in 'AB']
    observe(store,'first',[a,b])
    observe(store,'second',[a,b],location='Agra')
    note(store,a,b,'saved-note')
    store.create_manual_association(a.person_id,b.person_id,'manual')
    requests = [Request(collection=c,as_of=AS_OF,view='EXPLORE',filters=Filter(evidence_type=TYPES)) for c in (C.RELATIONSHIPS,C.CLUSTERS,C.MOST_FREQUENTLY_SEEN,C.MOST_RECENTLY_SEEN,C.MULTIPLE_LOCATIONS)]
    def projection():
        result=[]
        for request in requests:
            model=store.get_world_graph_v2_read(request)
            result.append((model.relationships,model.clusters,model.discoveries,model.discovery_context))
        return result
    before=projection()
    GlobalIdentityGraphService(store).rebuild_projection('rebuild')
    assert projection()==before
    store=SQLiteIdentityStore(store.db_path,embedding_dim=2,database_key=key)
    store.initialize()
    assert projection()==before
    service=BackupService(store.db_path,store.backup_dir,database_key=key)
    backup=service.create_backup(reason='World intelligence fixture')
    encrypted=service.export_encrypted_backup(backup.backup_id,tmp_path/'world.sfbackup.enc','world fixture passphrase')
    imported=service.import_encrypted_backup(encrypted,'world fixture passphrase')
    store.create_person('After backup')
    service.restore_backup(imported.backup_id,str(uuid.uuid4()))
    store.initialize()
    assert projection()==before


@pytest.mark.parametrize('people_count,events',[(100,1000),(10000,100000)])
def test_discovery_scale_bounds_and_determinism(tmp_path,people_count,events):
    from scripts.benchmark_world_v2 import _seed
    store=SQLiteIdentityStore(tmp_path/'scale.db',embedding_dim=2)
    store.initialize()
    _seed(store,people_count,events,participants_per_event=2,relationship_events=min(events,20000))
    for collection in (C.MOST_FREQUENTLY_SEEN,C.MOST_RECENTLY_SEEN,C.MULTIPLE_LOCATIONS,C.LOCATION_SUGGESTIONS,C.RELATIONSHIPS,C.CLUSTERS):
        request=Request(collection=collection,as_of='2026-08-02T00:00:00+00:00',view='EXPLORE',filters=Filter(evidence_type=('CO_OBSERVED',)),include_below_threshold=True,location_query='fie',limits=Limits(people=10,events=3,relationships=10,facets=2))
        started=time.perf_counter()
        with store._connect() as conn:
            statements=[]
            conn.set_trace_callback(statements.append)
            from sentriface.storage.sqlite_store import _world_graph_v2_read
            first=_world_graph_v2_read(conn,request)
        elapsed=time.perf_counter()-started
        assert len(first.discoveries)<=10 and len(first.relationships)<=10
        assert all(len(d.supporting_encounters)<=3 and len(d.locations)<=2 for d in first.discoveries)
        assert first.discoveries==store.get_world_graph_v2_read(request).discoveries
        print(f'{people_count} people/{events} events {collection.value}: {elapsed:.3f}s, {len(statements)} statements, {len(json.dumps(_world_graph_v2_payload(first)))} bytes')
        assert len(statements)<=25
        assert elapsed<30


def test_shared_frame_support_reuses_corrected_encounter_media(store):
    from tests import test_encounter_management as management_helpers
    helper=management_helpers.EncounterManagementTest()
    helper.store=store
    helper.a,helper.b=[store.create_person(n) for n in 'AB']
    helper.oid=correction_helpers.IdentityCorrectionTest()._finalize(store,'original',[helper.a,helper.b])['observation_id']
    review=helper.amendment([helper.a,helper.b],'/managed/shared-new-frame.jpg')
    store.complete_encounter_identity_review(review)
    store.complete_photo_review(review,'shared-attach')
    edge=explore(store,threshold=1).relationships[0]
    assert edge.encounter_recurrence['count']==1
    evidence=read(store,C.EVIDENCE,detail_level=L.EVIDENCE,focus_type='RELATIONSHIP',focus_id=edge.relationship_id,view='EXPLORE',filters=Filter(evidence_type=TYPES))
    assert evidence.evidence[0].provenance['encounter_support']=='SHARED_FRAME'


def test_discovery_read_keeps_one_snapshot_during_correction(store,monkeypatch):
    from sentriface.storage import sqlite_store as module
    a=store.create_person('A')
    observe(store,'original',[a])
    before=read(store,C.MOST_FREQUENTLY_SEEN)
    original=module._world_people_scope
    wrote=False
    def concurrent_write(conn,filters):
        nonlocal wrote
        result=original(conn,filters)
        if not wrote:
            wrote=True
            observe(store,'concurrent',[a])
        return result
    with monkeypatch.context() as patch:
        patch.setattr(module,'_world_people_scope',concurrent_write)
        during=read(store,C.MOST_FREQUENTLY_SEEN)
    assert during.graph_revision==before.graph_revision
    assert during.discoveries[0].count==1
    assert read(store,C.MOST_FREQUENTLY_SEEN).discoveries[0].count==2


def test_new_collections_use_existing_view_authorization_and_local_api(tmp_path):
    import http.client
    import threading
    from sentriface.api_server import create_server
    from sentriface.auth import AUTH_COOKIE_NAME
    server=create_server(port=0,data_dir=tmp_path/'api',runtime='dev',debug=False)
    admin,token=server.auth.signup_initial('world-admin','Administrator','world administrator password')
    server.auth.create_user(admin,'world-viewer','Viewer','world viewer password secure',['viewer'])
    _,viewer=server.auth.login('world-viewer','world viewer password secure')
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    def get(query,cookie=None,host=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=20)
        headers={'X-SentriFace-Session':server.session_token}
        if cookie:
            headers['Cookie']=f'{AUTH_COOKIE_NAME}={cookie}'
        if host:
            headers['Host']=host
        connection.request('GET',f'/api/world-graph?version=2&{query}',headers=headers)
        response=connection.getresponse()
        status=response.status
        body=json.loads(response.read())
        connection.close()
        return status,body
    try:
        for collection in (C.MOST_FREQUENTLY_SEEN,C.MOST_RECENTLY_SEEN,C.MULTIPLE_LOCATIONS,C.LOCATION_SUGGESTIONS):
            query=f'collection={collection.value}&location_query=Delhi'
            assert get(query)[0]==401
            assert get(query,viewer)[0]==200
            assert get(query,token)[0]==200
            assert get(query,viewer,'untrusted.example')[0] in (400,403)
        assert get('view=EXPLORE&evidence_type=&collection=CLUSTERS',viewer)[0]==400
        assert get('view=EXPLORE&evidence_type=CO_OBSERVED&min_relationship_strength=2&include_below_threshold=true',viewer)[0]==200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_failed_location_transaction_is_not_a_suggestion(store,monkeypatch):
    from sentriface.storage import sqlite_store as module
    a=store.create_person('A')
    oid=correction_helpers.IdentityCorrectionTest()._finalize(store,'transaction',[a])['observation_id']
    before=store.get_encounter_read(oid)
    def fail_projection(conn):
        raise RuntimeError('fixture failure after metadata insert')
    with monkeypatch.context() as patch:
        patch.setattr(module,'_replace_graph_projection',fail_projection)
        with pytest.raises(RuntimeError,match='fixture failure'):
            store.correct_encounter(oid,'failed-transaction',expected_revision=before['revision'],event_details={'place_seen':'Rollback place'})
    assert store.get_encounter_read(oid)['revision']==before['revision']
    assert not read(store,C.LOCATION_SUGGESTIONS,location_query='Rollback').available_facets['locations']
    assert store.get_operation('failed-transaction') is None


def test_discoveries_apply_canonical_and_person_scope_without_cluster_authority(store):
    a,b,c=[store.create_person(n) for n in 'ABC']
    observe(store,'old-alias',[a,b],location='Delhi')
    observe(store,'other-location',[a],location='Agra')
    observe(store,'third-person',[c],location='Delhi')
    IdentityMergeService(store).execute(b.person_id,a.person_id,'merge-presence')
    frequent=read(store,C.MOST_FREQUENTLY_SEEN)
    assert {p.canonical_person_id:p.count for p in frequent.discoveries}=={a.person_id:2,c.person_id:1}
    assert read(store,C.MULTIPLE_LOCATIONS).discoveries[0].canonical_person_id==a.person_id
    assert not explore(store,threshold=1).relationships
    assert explore(store,threshold=1).scope_totals['clusters']==0
    scoped=read(store,C.MOST_FREQUENTLY_SEEN,filters=Filter(locations=('Delhi',)))
    assert all(p.count==1 for p in scoped.discoveries)
    store.archive_person(a.person_id,'archive')
    assert {p.canonical_person_id for p in read(store,C.MOST_FREQUENTLY_SEEN,filters=Filter(lifecycle=('ACTIVE',))).discoveries}=={c.person_id}


@pytest.mark.parametrize('view',['CURRENT','EXPLORE'])
def test_activity_scoped_discovery_person_and_cluster_navigation_agree(store,view):
    a,b,c=[store.create_person(n) for n in 'ABC']
    observe(store,'low-activity',[a,b])
    store.create_manual_association(b.person_id,c.person_id,'manual-inactive')
    request=Request(as_of=AS_OF,view=view,filters=Filter(evidence_type=TYPES,min_relationship_strength=1,activity=('LOW',)))
    overview=store.get_world_graph_v2_read(replace(request,collection=C.CLUSTERS))
    assert overview.clusters[0].member_count==2
    selected=store.get_world_graph_v2_read(replace(request,detail_level=L.CLUSTER,focus_type='CLUSTER',focus_id=overview.clusters[0].cluster_id))
    assert {p.canonical_person_id for p in selected.people}=={a.person_id,b.person_id}
    person=store.get_world_graph_v2_read(replace(request,detail_level=L.PERSON,focus_type='PERSON',focus_id=b.person_id))
    assert person.people[0].cluster_memberships[0]['cluster_id']==overview.clusters[0].cluster_id
    frequent=store.get_world_graph_v2_read(replace(request,collection=C.MOST_FREQUENTLY_SEEN))
    assert {p.canonical_person_id for p in frequent.discoveries}=={a.person_id,b.person_id}
    with pytest.raises(KeyError):
        store.get_world_graph_v2_read(replace(request,detail_level=L.PERSON,focus_type='PERSON',focus_id=c.person_id))


def test_location_query_length_precedes_unicode_casefold_expansion(store):
    person=store.create_person('A')
    observe(store,'unicode-location',[person],location='SSEN city')
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='ße').available_facets['locations']==[]
    assert read(store,C.LOCATION_SUGGESTIONS,location_query='ßen').available_facets['locations']==[{'value':'SSEN city','count':1}]
