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


@pytest.mark.parametrize('period', [7, 30, 90])
def test_locations_normalization_missing_values_and_suggestions(store, period):
    a,b = [store.create_person(n) for n in 'AB']
    for n,location in enumerate((' Delhi ', 'DELHI', 'New   Delhi', 'new delhi', None, '   ')):
        observe(store,f'loc-{n}',[a],location=location)
    observe(store,'single',[b],location='Delhi')
    result = read(store,C.MULTIPLE_LOCATIONS,discovery_period_days=period)
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


@pytest.mark.parametrize('collection', [C.MOST_FREQUENTLY_SEEN, C.MULTIPLE_LOCATIONS])
def test_discovery_pagination_fingerprints_and_stale_revisions(store, collection):
    people = [store.create_person(str(i)) for i in range(4)]
    observe(store,'all',people)
    observe(store,'all-other',people,location='Agra')
    req = Request(collection=collection,as_of=AS_OF,limits=Limits(people=2))
    first = store.get_world_graph_v2_read(req)
    again = store.get_world_graph_v2_read(req)
    assert first.discoveries == again.discoveries
    second = store.get_world_graph_v2_read(replace(req,cursor=first.next_cursor))
    assert not ({p.canonical_person_id for p in first.discoveries}&{p.canonical_person_id for p in second.discoveries})
    for changes in ({'discovery_period_days':7},{'include_below_threshold':True},{'collection':C.MOST_RECENTLY_SEEN},{'location_query':'changed'},{'filters':Filter(locations=('Delhi',))}):
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
    observe(store,'historical-unknown',[a,b],date='bad-date')
    note(store,a,b,'saved-note')
    store.create_manual_association(a.person_id,b.person_id,'manual')
    observe(store,'older-place',[a,b],date='2026-09-01T12:00:00Z',location='Jaipur')
    requests = [Request(collection=c,as_of=AS_OF,view='EXPLORE',discovery_period_days=days,filters=Filter(evidence_type=TYPES)) for days in (7,30,90) for c in (C.RELATIONSHIPS,C.CLUSTERS,C.MOST_FREQUENTLY_SEEN,C.MOST_RECENTLY_SEEN,C.MULTIPLE_LOCATIONS)]
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


@pytest.mark.parametrize('collection', [C.MOST_FREQUENTLY_SEEN, C.MULTIPLE_LOCATIONS])
def test_discovery_read_keeps_one_snapshot_during_correction(store,monkeypatch,collection):
    from sentriface.storage import sqlite_store as module
    a=store.create_person('A')
    observe(store,'original',[a])
    observe(store,'second-place',[a],location='Agra')
    before=read(store,collection,discovery_period_days=7)
    original=module._world_people_scope
    wrote=False
    def concurrent_write(conn,filters):
        nonlocal wrote
        result=original(conn,filters)
        if not wrote:
            wrote=True
            observe(store,'concurrent',[a],location='Jaipur')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(module,'_world_people_scope',concurrent_write)
        during=read(store,collection,discovery_period_days=7)
    assert during.graph_revision==before.graph_revision
    assert during.discoveries[0].count==2
    assert read(store,collection,discovery_period_days=7).discoveries[0].count==3


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


def test_discovery_offset_qa_reproduction(store):
    people = [store.create_person(name) for name in 'ABC']
    for person, stamp in zip(people, ('2026-09-27T13:00:00+02:00', '2026-09-27T11:30:00-02:00', '2026-10-27T11:30:00-02:00')):
        observe(store, 'offset-'+person.name, [person], date=stamp)
    for collection in (C.MOST_FREQUENTLY_SEEN, C.MOST_RECENTLY_SEEN):
        result = read(store, collection)
        assert {row.canonical_person_id for row in result.discoveries} == ({people[1].person_id} if collection == C.MOST_FREQUENTLY_SEEN else {people[0].person_id, people[1].person_id})
    recent = read(store, C.MOST_RECENTLY_SEEN, filters=Filter(date_from='2026-09-27T12:00:00Z'))
    assert [row.canonical_person_id for row in recent.discoveries] == [people[1].person_id]


@pytest.mark.parametrize('days', [7, 30, 90])
@pytest.mark.parametrize('collection', [C.MOST_FREQUENTLY_SEEN, C.MULTIPLE_LOCATIONS])
def test_timestamp_instants_boundaries_and_order(store, days, collection):
    from sentriface.graph_read_service import GraphReadService
    end = datetime.fromisoformat(AS_OF)
    start = end - timedelta(days=days)
    person = store.create_person('Boundary')
    stamps = [(start-timedelta(microseconds=1)).isoformat(), start.isoformat().replace('+00:00','Z'), start.astimezone(timezone(timedelta(hours=-2))).isoformat(), end.replace(tzinfo=None).isoformat(), end.astimezone(timezone(timedelta(hours=2))).isoformat(), (end+timedelta(microseconds=1)).isoformat()]
    ids = [observe(store, 'instant-'+str(i), [person], date=stamp, location='Delhi' if i%2 else 'Agra') for i,stamp in enumerate(stamps)]
    request = Request(collection=collection, as_of=AS_OF, discovery_period_days=days)
    service = GraphReadService(store)
    result = service.world_graph_v2(request)
    assert result.discoveries[0].count == (2 if collection == C.MULTIPLE_LOCATIONS else 4)
    assert {e['event_id'] for e in result.discoveries[0].supporting_encounters} == set(ids[1:5])
    assert {e['occurred_at'] for e in result.discoveries[0].supporting_encounters} == set(stamps[1:5])
    assert result.discoveries == service.world_graph_v2(request).discoveries
    filters = Filter(date_from=start.isoformat(), date_to=AS_OF)
    recent = service.world_graph_v2(replace(request, collection=C.MOST_RECENTLY_SEEN, filters=filters))
    assert recent.discovery_context['latest_observed_day'] == '2026-10-27'
    assert {e['event_id'] for e in recent.discoveries[0].supporting_encounters} == set(ids[3:5])
    events = service.world_graph_v2(Request(detail_level=L.PERSON, focus_type='PERSON', focus_id=person.person_id, collection=C.EVENTS, as_of=AS_OF, filters=filters))
    assert {e.event_id for e in events.events} == set(ids[1:5])
    assert [datetime.fromisoformat(e.occurred_at.replace('Z','+00:00')).replace(tzinfo=timezone.utc) if '+' not in e.occurred_at and '-' not in e.occurred_at[10:] else datetime.fromisoformat(e.occurred_at.replace('Z','+00:00')).astimezone(timezone.utc) for e in events.events][:2] == [end,end]


def test_offset_relationship_proof_and_multiple_places(store):
    a,b = [store.create_person(name) for name in 'AB']
    stamps = ['2026-10-26T23:59:59.999999Z','2026-10-27T02:00:00+02:00','2026-10-27T11:59:59.999999Z','2026-10-27T10:00:00-02:00','2026-10-27T12:00:00.000001Z']
    ids = [observe(store,'proof-'+str(i),[a,b],date=stamp,location='Delhi' if i%2 else 'Agra') for i,stamp in enumerate(stamps)]
    scoped = Filter(date_to=AS_OF)
    edge = read(store,filters=scoped).relationships[0]
    assert edge.first_occurrence_at == stamps[0]
    assert edge.last_occurrence_at == stamps[3]
    assert edge.encounter_recurrence['count'] == 4
    assert [r['event_id'] for r in edge.encounter_recurrence['supporting_encounters']] == list(reversed(ids[:4]))
    proof = read(store,C.EVIDENCE,detail_level=L.EVIDENCE,focus_type='RELATIONSHIP',focus_id=edge.relationship_id,filters=scoped)
    assert [r.occurred_at for r in proof.evidence] == list(reversed(stamps[:4]))
    places = read(store,C.MULTIPLE_LOCATIONS)
    assert all(r.count==2 and len(r.supporting_encounters)==4 for r in places.discoveries)
    recent = read(store,C.MOST_RECENTLY_SEEN)
    assert recent.discovery_context['latest_observed_day']=='2026-10-27'
    assert all({e['event_id'] for e in r.supporting_encounters}==set(ids[1:4]) for r in recent.discoveries)
    restarted=SQLiteIdentityStore(store.db_path,embedding_dim=2)
    restarted.initialize()
    assert read(restarted,filters=scoped).relationships==read(store,filters=scoped).relationships


@pytest.mark.parametrize('view', ['CURRENT', 'EXPLORE'])
@pytest.mark.parametrize('valid', [False, True])
def test_historical_unknown_time_contract(store, view, valid):
    from sentriface.graph_read_service import GraphReadService
    service = GraphReadService(store)
    a, b = [store.create_person(n) for n in 'AB']
    invalid = ['bad-date', 'not-a-time', '2026-99-99', '0001-01-01T00:00:00+02:00']
    ids = [observe(store, 'unknown-'+str(i), [a,b], date=stamp, location='Unknown '+str(i)) for i,stamp in enumerate(invalid)]
    stamps = ['2026-10-26T23:59:59.999999Z', '2026-10-27T02:00:00+02:00', '2026-10-26T22:00:00-02:00'] if valid else []
    known_ids = [observe(store, 'known-'+str(i), [a,b], date=stamp, location='Delhi' if i else 'Agra') for i,stamp in enumerate(stamps)]
    filters = Filter(evidence_type=('CO_OBSERVED',), min_relationship_strength=1) if view == 'EXPLORE' else Filter()
    request = Request(collection=C.RELATIONSHIPS, as_of=AS_OF, view=view, filters=filters)
    def query(**values):
        return service.world_graph_v2(replace(request, **values))
    edge = query().relationships[0]
    assert edge.evidence_count == len(ids)+len(known_ids)
    assert edge.encounter_recurrence['count'] == len(ids)+len(known_ids)
    assert edge.first_occurrence_at == (stamps[0] if valid else None)
    assert edge.last_occurrence_at in (stamps[1:] if valid else [None])
    assert edge.encounter_recurrence['first_occurrence_at'] == (stamps[0] if valid else None)
    assert edge.encounter_recurrence['latest_occurrence_at'] in (stamps[1:] if valid else [None])
    supports = edge.encounter_recurrence['supporting_encounters']
    assert [s['event_id'] for s in supports] == sorted(known_ids[1:]) + known_ids[:1] + sorted(ids)
    assert {s['occurred_at'] for s in supports} == set(invalid+stamps)
    assert query().relationships == query().relationships
    # Walk single-record pages: valid instants descending, unknowns last, stable IDs.
    event_request = dict(collection=C.EVENTS, detail_level=L.PERSON, focus_type='PERSON', focus_id=a.person_id, limits=Limits(events=1))
    events, cursor = [], None
    while True:
        page = query(**event_request, cursor=cursor)
        events.extend(page.events)
        if not page.has_more:
            break
        cursor = page.next_cursor
    assert [e.event_id for e in events] == [s['event_id'] for s in supports]
    for e in events:
        if e.event_id in ids:
            assert e.occurred_at == invalid[ids.index(e.event_id)]
            assert e.explanation.first_occurrence_at is None
            assert e.explanation.last_occurrence_at is None
    proof_args = dict(collection=C.EVIDENCE, detail_level=L.EVIDENCE, focus_type='RELATIONSHIP', focus_id=edge.relationship_id)
    proof = query(**proof_args).evidence
    assert len(proof) == len(ids)+len(known_ids)
    proof_ids, cursor = [], None
    while True:
        page = query(**proof_args, limits=Limits(evidence=1), cursor=cursor)
        proof_ids.extend(e.evidence_id for e in page.evidence)
        if not page.has_more:
            break
        cursor = page.next_cursor
    assert proof_ids == [e.evidence_id for e in proof]
    assert {e.occurred_at for e in proof} == set(invalid+stamps)
    assert [e.evidence_id for e in proof] == [e.evidence_id for e in query(**proof_args).evidence]
    for e in proof:
        if e.occurred_at in invalid:
            assert e.occurrence_bounds == {'first': None, 'last': None}
            assert e.explanation.first_occurrence_at is None
    scoped = replace(filters, date_from='2026-10-26T00:00:00Z', date_to=AS_OF)
    edges = query(filters=scoped).relationships
    assert len(edges) == int(valid)
    if valid:
        assert edges[0].evidence_count == 3
        assert len(query(**proof_args, filters=scoped).evidence) == 3
    assert {e.event_id for e in query(**{**event_request, 'limits': Limits(events=20)}, filters=scoped).events} == set(known_ids)
    for days in (7,30,90):
        frequent = query(collection=C.MOST_FREQUENTLY_SEEN, discovery_period_days=days).discoveries
        assert {d.canonical_person_id:d.count for d in frequent} == ({a.person_id:3,b.person_id:3} if valid else {})
    recent = query(collection=C.MOST_RECENTLY_SEEN)
    assert recent.discovery_context['latest_observed_day'] == ('2026-10-27' if valid else None)
    assert {e['event_id'] for d in recent.discoveries for e in d.supporting_encounters} == set(known_ids[1:])
    places = query(collection=C.MULTIPLE_LOCATIONS).discoveries
    assert {d.canonical_person_id:d.count for d in places} == ({a.person_id:2,b.person_id:2} if valid else {})
    clusters = query(collection=C.CLUSTERS).clusters
    assert clusters[0].explanation.first_occurrence_at == (stamps[0] if valid else None)
    frozen = query()
    before = frozen.relationships
    store.rebuild_graph_projection('unknown-time-rebuild')
    restarted = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    restarted.initialize()
    assert restarted.get_world_graph_v2_read(request).relationships == before
    # Correct canonical identity without changing historical timestamp provenance.
    c = store.create_person('C')
    store.correct_observation_identity(ids[0], b.person_id, c.person_id, 'unknown-correction')
    with pytest.raises(ValueError, match='stale'):
        query(revision=frozen.graph_revision)
    corrected = query().relationships
    assert sum(e.evidence_count for e in corrected) == len(ids)+len(known_ids)
    unknown_edge = next(e for e in corrected if c.person_id in (e.source_person_id,e.target_person_id))
    assert unknown_edge.first_occurrence_at is None and unknown_edge.last_occurrence_at is None


@pytest.mark.parametrize('field', ['as_of', 'date_from', 'date_to'])
@pytest.mark.parametrize('invalid_date', ['bad-date', '0001-01-01T00:00:00+02:00'])
def test_unknown_history_does_not_relax_request_dates(store, field, invalid_date):
    from sentriface.graph_read_service import GraphReadService
    a,b = [store.create_person(n) for n in 'AB']
    observe(store,'invalid-request-fixture',[a,b],date='bad-date')
    request = Request(as_of=invalid_date) if field == 'as_of' else Request(as_of=AS_OF, filters=Filter(**{field:invalid_date}))
    with pytest.raises(ValueError, match='Invalid World '+field):
        GraphReadService(store).world_graph_v2(request)


def test_historical_bad_date_and_valid_qa_reproduction(store):
    from sentriface.graph_read_service import GraphReadService
    a,b = [store.create_person(n) for n in 'AB']
    observe(store,'qa-bad',[a,b],date='bad-date')
    valid = observe(store,'qa-valid',[a,b])
    service = GraphReadService(store)
    edge = service.world_graph_v2(Request(collection=C.RELATIONSHIPS, as_of=AS_OF)).relationships[0]
    assert edge.evidence_count == edge.encounter_recurrence['count'] == 2
    assert edge.first_occurrence_at == edge.last_occurrence_at == '2026-10-22T10:00:00+00:00'
    scoped = service.world_graph_v2(Request(collection=C.RELATIONSHIPS, as_of=AS_OF, filters=Filter(date_to=AS_OF))).relationships[0]
    assert scoped.evidence_count == scoped.encounter_recurrence['count'] == 1
    for collection in (C.MOST_FREQUENTLY_SEEN,C.MOST_RECENTLY_SEEN):
        result = service.world_graph_v2(Request(as_of=AS_OF, collection=collection))
        assert {d.canonical_person_id:d.count for d in result.discoveries} == {a.person_id:1,b.person_id:1}
        assert {e['event_id'] for d in result.discoveries for e in d.supporting_encounters} == {valid}

@pytest.mark.parametrize('collection', [C.MOST_FREQUENTLY_SEEN, C.MOST_RECENTLY_SEEN, C.MULTIPLE_LOCATIONS])
@pytest.mark.parametrize('period', [7, 30, 90])
def test_face_reassignment_independent_history(store, collection, period):
    as_of = '2026-10-29T12:00:00+00:00'
    a, b = [store.create_person(n) for n in 'AB']
    helper = correction_helpers.IdentityCorrectionTest()
    e1 = helper._finalize(store, 'integrity-e1', [b])['observation_id']
    e2 = helper._finalize(store, 'integrity-e2', [a])['observation_id']
    for oid, date, location in ((e1, '2026-10-27', 'Delhi'), (e2, '2026-10-28', 'Agra')):
        store.correct_encounter(oid, 'date-' + oid, expected_revision=store.get_encounter_read(oid)['revision'],
                                event_details={'date': date, 'time': '12:00', 'time_precision': 'exact', 'place_seen': location})
    def rows():
        return store.get_world_graph_v2_read(Request(collection=collection, as_of=as_of, discovery_period_days=period)).discoveries
    assert store.get_encounter_read(e1)['participant_ids'] == [b.person_id]
    assert store.get_encounter_read(e2)['participant_ids'] == [a.person_id]
    if collection == C.MULTIPLE_LOCATIONS:
        assert not rows()
    elif collection == C.MOST_FREQUENTLY_SEEN:
        assert {r.canonical_person_id: r.count for r in rows()} == {a.person_id: 1, b.person_id: 1}
    with store._connect() as conn:
        embedding_id = conn.execute('SELECT embedding_id FROM observation_face_assignments WHERE observation_id = ?', (e2,)).fetchone()[0]
    store.move_face(embedding_id, b.person_id, 'integrity-reassign', actor={'username': 'operator'})
    assert store.get_encounter_read(e2)['participant_ids'] == [b.person_id]
    assert not store.list_observations_for_person(a.person_id)
    assert not store.list_person_sightings(a.person_id)
    assert {x.observation_id for x in store.list_person_sightings(b.person_id)} == {e1, e2}
    assert {o.observation_id for o in store.list_observations_for_person(b.person_id)} == {e1, e2}
    for phase in ('first', 'repeat', 'restart', 'rebuild'):
        if phase == 'restart':
            store.initialize()
        if phase == 'rebuild':
            store.rebuild_graph_projection('integrity-rebuild')
        result = rows()
        assert {r.canonical_person_id for r in result} == {b.person_id}, phase
        expected_events = {e2} if collection == C.MOST_RECENTLY_SEEN else {e1, e2}
        assert {s['event_id'] for s in result[0].supporting_encounters} == expected_events
        assert result[0].count == (2 if collection != C.MOST_RECENTLY_SEEN else 1)

@pytest.mark.parametrize('consumer', ['activity', 'scoped', 'overview', 'focused', 'inspector'])
def test_face_assignment_world_consumers(store, consumer):
    from sentriface.storage import sqlite_store as sql
    a, b = [store.create_person(n) for n in 'AB']
    finalized = correction_helpers.IdentityCorrectionTest()._finalize(store, 'audit-face', [a])
    oid = finalized['observation_id']
    store.move_face(finalized['embedding_assignments']['face-0'], b.person_id, 'audit-move')
    with store._connect() as conn:
        canonical = sql._world_canonical_map(conn)
        if consumer == 'activity':
            actual = {p for p, count in sql._world_activity_counts(conn, set(canonical), Filter()).items() if count}
        elif consumer == 'scoped':
            actual = sql._world_scoped_event_people(conn, Filter())
        elif consumer == 'overview':
            actual = {p for p, count in sql._world_event_statistics(conn, Filter(), set(canonical), canonical_map=canonical)['activity'].items() if count}
        elif consumer == 'focused':
            actual = {p for p in canonical if sql._world_person_event_count(conn, p, Filter(), canonical_map=canonical)}
        else:
            actual = {p['person_id'] for p in sql._world_event_participant_mapping(conn, oid)[0]}
    assert actual == {b.person_id}

@pytest.mark.parametrize('initial', ['single', 'multi', 'independent'])
def test_face_chain_reversal_revision_merge_and_lifecycle(store, initial):
    from sentriface.storage import sqlite_store as sql
    a, b, c, d = [store.create_person(n) for n in 'ABCD']
    people = {'single': [a], 'multi': [a, b], 'independent': [a, b, a]}[initial]
    finalized = correction_helpers.IdentityCorrectionTest()._finalize(store, 'chain', people)
    oid = finalized['observation_id']
    def check(expected):
        ids = {p.person_id for p in expected}
        assert set(store.get_encounter_read(oid)['participant_ids']) == ids
        assert {p.person_id for p in (a,b,c,d) if store.list_observations_for_person(p.person_id)} == ids
        with store._connect() as conn:
            canonical = sql._world_canonical_map(conn)
            assert sql._world_scoped_event_people(conn, Filter()) == ids
            assert {pid for pid, count in sql._world_activity_counts(conn, set(canonical), Filter()).items() if count} == ids
            assert {pid for pid in canonical if sql._world_person_event_count(conn, pid, Filter(), canonical_map=canonical)} == ids
            sql._world_graph_v2_read(conn, Request())
            relationships = sql._world_relationship_scope(conn, Filter(), ids, canonical_map=canonical)
            assert {frozenset((r['source_person_id'], r['target_person_id'])) for r in relationships} == {
                frozenset(pair) for pair in itertools.combinations(ids, 2)}
            for relationship in relationships:
                evidence = store.get_connection_evidence(relationship['source_person_id'], relationship['target_person_id'])
                assert len(evidence) == 1 and evidence[0].source_entity_id == oid
        assert store.validate_graph_projection()['valid']
    check(list({p.person_id: p for p in people}.values()))
    embedding = finalized['embedding_assignments']['face-0']
    store.move_face(embedding, c.person_id, 'chain-a-c')
    expected = {'single': [c], 'multi': [b,c], 'independent': [a,b,c]}[initial]
    check(expected)
    store.move_face(embedding, d.person_id, 'chain-c-d')
    check([d if p == c else p for p in expected])
    store.move_face(embedding, a.person_id, 'chain-d-a')
    check(list({p.person_id: p for p in people}.values()))
    assert len(store.list_corrections_for_observation(oid)) >= 3
    # Explicit PRESENT/REMOVED interpretation takes precedence over face assignment.
    store.correct_encounter(oid, 'chain-add-c', expected_revision=store.get_encounter_read(oid)['revision'],
        participant_correction={'action': 'ADD', 'person_id': c.person_id},
        relations=[{'first_person_id': p.person_id, 'second_person_id': c.person_id, 'disposition': 'INCLUDE'} for p in list({p.person_id: p for p in people}.values())])
    check([*list({p.person_id: p for p in people}.values()), c])
    store.correct_encounter(oid, 'chain-remove-a', expected_revision=store.get_encounter_read(oid)['revision'],
        participant_correction={'action': 'REMOVE', 'person_id': a.person_id})
    remaining = [p for p in list({p.person_id: p for p in people}.values()) if p != a] + [c]
    check(remaining)
    store.rebuild_graph_projection('chain-rebuild')
    reopened = SQLiteIdentityStore(store.db_path, embedding_dim=2)
    reopened.initialize()
    assert set(reopened.get_encounter_read(oid)['participant_ids']) == {p.person_id for p in remaining}
    store.archive_person(c.person_id, 'chain-archive')
    check(remaining)
    store.permanently_delete_person(c.person_id, 'chain-delete')
    check(remaining)


def test_face_correction_canonical_merge_keeps_one_occurrence(store):
    from sentriface.storage import sqlite_store as sql
    a,b,c = [store.create_person(n) for n in 'ABC']
    finalized = correction_helpers.IdentityCorrectionTest()._finalize(store, 'collapse', [a,b])
    oid = finalized['observation_id']
    store.move_face(finalized['embedding_assignments']['face-0'], c.person_id, 'collapse-move')
    IdentityMergeService(store).execute(c.person_id, b.person_id, 'collapse-merge')
    assert store.get_encounter_read(oid)['participant_ids'] == [b.person_id]
    assert len(store.list_observations_for_person(b.person_id)) == 1
    with store._connect() as conn:
        canonical = sql._world_canonical_map(conn)
        assert sql._world_person_event_count(conn, b.person_id, Filter(), canonical_map=canonical) == 1
        assert sql._world_event_statistics(conn, Filter(), set(canonical.values()), canonical_map=canonical)['activity'].get(b.person_id) == 1
    assert not store.get_connection_evidence(b.person_id, b.person_id)
    assert store.validate_graph_projection()['valid']


def test_corrected_identity_encrypted_restore_provenance_and_read_only(tmp_path):
    from tests.test_batch35_coherence import encounter
    key = bytes(range(32))
    store = SQLiteIdentityStore(tmp_path/'data'/'identity.db', embedding_dim=2, database_key=key)
    store.initialize()
    a,b,c = [store.create_person(n) for n in 'ABC']
    frame = tmp_path/'frame.jpg'
    frame.write_bytes(b'private domain fixture media, no inference')
    oid = encounter(store, [a,c], [str(frame), str(frame)])
    store.correct_encounter(oid, 'restore-date', expected_revision=store.get_encounter_read(oid)['revision'],
        event_details={'date': '2026-10-28', 'place_seen': 'Agra'})
    store.correct_encounter(oid, 'restore-correction', expected_revision=store.get_encounter_read(oid)['revision'],
        participant_correction={'action': 'REASSIGN', 'person_id': a.person_id, 'to_person_id': b.person_id})
    def snapshot():
        assert set(store.get_encounter_read(oid)['participant_ids']) == {b.person_id,c.person_id}
        result = store.get_world_graph_v2_read(Request(collection=C.MOST_FREQUENTLY_SEEN, as_of='2026-10-29T12:00:00Z'))
        assert {p.canonical_person_id for p in result.discoveries} == {b.person_id,c.person_id}
        assert all(d.count == 1 and {e['event_id'] for e in d.supporting_encounters} == {oid} for d in result.discoveries)
        with store._connect() as conn:
            return ([dict(r) for r in conn.execute('SELECT * FROM identity_corrections ORDER BY correction_id')],
                    [dict(r) for r in conn.execute('SELECT * FROM relationship_evidence ORDER BY evidence_id')])
    before = snapshot()
    assert snapshot() == before
    store.rebuild_graph_projection('restore-rebuild')
    store.initialize()
    assert snapshot() == before
    service = BackupService(store.db_path, store.backup_dir, database_key=key, data_dir=store.db_path.parent)
    backup = service.create_backup(reason='Corrected identity regression')
    exported = service.export_encrypted_backup(backup.backup_id, tmp_path/'corrected.sfbackup.enc', 'private fixture passphrase')
    imported = service.import_encrypted_backup(exported, 'private fixture passphrase')
    service.restore_backup(imported.backup_id, str(uuid.uuid4()))
    store = SQLiteIdentityStore(store.db_path, embedding_dim=2, database_key=key)
    store.initialize()
    assert snapshot() == before

def test_multiple_location_period_windows_default_and_isolation(store):
    a, b = [store.create_person(n) for n in 'AB']
    end = datetime.fromisoformat(AS_OF)
    for n, age in enumerate((1, 2, 15, 60)):
        observe(store, f'window-{n}', [a, b],
                date=(end-timedelta(days=age)).isoformat(), location=f'Place {n}')
    observe(store, 'malformed-window', [a, b], date='bad-date', location='Unknown time')
    assert read(store, C.MULTIPLE_LOCATIONS).discoveries == read(
        store, C.MULTIPLE_LOCATIONS, discovery_period_days=30).discoveries
    for days, expected in ((7, 2), (30, 3), (90, 4)):
        request = _world_graph_v2_request_from_query(
            f'collection=MULTIPLE_LOCATIONS&as_of={AS_OF.replace("+00:00", "Z")}&discovery_period_days={days}')
        result = store.get_world_graph_v2_read(request)
        assert {d.count for d in result.discoveries} == {expected}
        assert result.discovery_context['period_days'] == days
        capped = read(store, C.MULTIPLE_LOCATIONS, discovery_period_days=days,
                      limits=Limits(events=1, facets=1))
        assert all(d.supporting_encounters_state['truncated'] and d.locations_state['truncated']
                   for d in capped.discoveries)
    edge = read(store).relationships[0]
    requests = [Request(collection=c, as_of=AS_OF) for c in
                (C.MOST_RECENTLY_SEEN, C.CLUSTERS, C.RELATIONSHIPS, C.PEOPLE)]
    requests += [Request(collection=C.EVIDENCE, detail_level=L.EVIDENCE,
                         focus_type='RELATIONSHIP', focus_id=edge.relationship_id, as_of=AS_OF),
                 Request(detail_level=L.PERSON, focus_type='PERSON', focus_id=a.person_id, as_of=AS_OF)]
    for request in requests:
        baseline = asdict(store.get_world_graph_v2_read(request)) | {'generated_at': ''}
        for days in (7, 90):
            assert asdict(store.get_world_graph_v2_read(
                replace(request, discovery_period_days=days))) | {'generated_at': ''} == baseline


def test_multiple_location_corrections_change_effective_windows_and_canonical_identity(store):
    a, b = [store.create_person(n) for n in 'AB']
    observe(store, 'current-place', [a], location='Delhi')
    oid = correction_helpers.IdentityCorrectionTest()._finalize(store, 'editable-place', [b])['observation_id']
    def correct(op, **details):
        store.correct_encounter(oid, op, expected_revision=store.get_encounter_read(oid)['revision'],
                                event_details=details)
    correct('old-place', date='2026-09-01', place_seen='Agra')
    IdentityMergeService(store).execute(b.person_id, a.person_id, 'period-merge')
    assert not read(store, C.MULTIPLE_LOCATIONS, discovery_period_days=7).discoveries
    assert read(store, C.MULTIPLE_LOCATIONS, discovery_period_days=90).discoveries[0].count == 2
    correct('move-time', date='2026-10-22')
    row = read(store, C.MULTIPLE_LOCATIONS, discovery_period_days=7).discoveries[0]
    assert row.canonical_person_id == a.person_id and row.count == 2
    correct('same-place', place_seen=' DELHI ')
    assert not read(store, C.MULTIPLE_LOCATIONS, discovery_period_days=90).discoveries


@pytest.mark.parametrize('period,expected', [(7, 2), (30, 3), (90, 4), (None, 3)])
def test_combined_fixed_oct29_corrected_period_locations(store, period, expected):
    a,b = [store.create_person(n) for n in 'AB']
    end = datetime.fromisoformat('2026-10-29T12:00:00+00:00')
    expected_events = set()
    for n, (age, place) in enumerate(((1,'Delhi'), (2,'Agra'), (15,'Jaipur'), (60,'Mumbai'))):
        oid = observe(store, f'combined-{n}', [b], date=(end-timedelta(days=age)).isoformat(), location=place)
        if age <= (period or 30):
            expected_events.add(oid)
    request = Request(collection=C.MULTIPLE_LOCATIONS, as_of=end.isoformat(), **({'discovery_period_days':period} if period else {}))
    plain = store.get_world_graph_v2_read(request)
    assert len(plain.discoveries) == 1 and plain.discoveries[0].count == expected
    # The corrected E2 supplies Agra independently; its raw participant never contains B.
    # Use a second independent store fixture identity pair to avoid duplicate support.
    c,d = [store.create_person(n) for n in 'CD']
    oid = correction_helpers.IdentityCorrectionTest()._finalize(store, 'combined-corrected-e2', [c])['observation_id']
    store.correct_encounter(oid, 'combined-e2-date', expected_revision=store.get_encounter_read(oid)['revision'],
        event_details={'date':'2026-10-28','time':'12:00','time_precision':'exact','place_seen':'Agra'})
    expected_corrected = {oid}
    for n, (age, place) in enumerate(((2,'Delhi'), (15,'Jaipur'), (60,'Mumbai'))):
        event = observe(store, f'combined-corrected-{n}', [d], date=(end-timedelta(days=age)).isoformat(), location=place)
        if age <= (period or 30):
            expected_corrected.add(event)
    with store._connect() as conn:
        embedding = conn.execute('SELECT embedding_id FROM observation_face_assignments WHERE observation_id = ?', (oid,)).fetchone()[0]
    store.move_face(embedding, d.person_id, 'combined-e2-correction')
    result = store.get_world_graph_v2_read(request)
    rows = {r.canonical_person_id:r for r in result.discoveries}
    assert c.person_id not in rows and rows[d.person_id].count == expected
    assert {s['event_id'] for s in rows[d.person_id].supporting_encounters} == expected_corrected
    assert {s['event_id'] for s in rows[b.person_id].supporting_encounters} == expected_events
    assert result.discovery_context['period_days'] == (period or 30)
    assert result.discovery_context['date_from'] == (end-timedelta(days=period or 30)).isoformat()
    assert result.discovery_context['date_to'] == end.isoformat()

def test_world_face_provenance_preserves_independent_assignment_origins(store):
    from sentriface.storage import sqlite_store as sql
    a,b,c = [store.create_person(n) for n in 'ABC']
    finalized = correction_helpers.IdentityCorrectionTest()._finalize(store, 'origin-split', [a,a,b])
    oid = finalized['observation_id']
    store.move_face(finalized['embedding_assignments']['face-0'], c.person_id, 'origin-a-c')
    with store._connect() as conn:
        participants, provenance = sql._world_event_participant_mapping(conn, oid)
    assert {p['person_id'] for p in participants} == {a.person_id,b.person_id,c.person_id}
    assert {(p['raw_person_id'], p['effective_person_id']) for p in provenance} == {
        (a.person_id,a.person_id),(a.person_id,c.person_id),(b.person_id,b.person_id)}
    reassigned = next(p for p in provenance if p['effective_person_id'] == c.person_id)
    assert reassigned['correction_operation_ids'] == ['origin-a-c']
    assert reassigned['effective_participation'] is True
    d = store.create_person('D')
    store.correct_encounter(oid, 'origin-add-d', expected_revision=store.get_encounter_read(oid)['revision'],
        participant_correction={'action': 'ADD', 'person_id': d.person_id},
        relations=[{'first_person_id': p.person_id, 'second_person_id': d.person_id, 'disposition': 'INCLUDE'} for p in (a,b,c)])
    with store._connect() as conn:
        _, provenance = sql._world_event_participant_mapping(conn, oid)
    explicit = next(p for p in provenance if p.get('participant_revision_operation_ids') == ['origin-add-d'])
    assert explicit['raw_person_id'] == explicit['effective_person_id'] == d.person_id
    assert explicit['effective_participation'] is True
    assert explicit['correction_operation_ids'] == ['origin-add-d']


def test_explicit_identity_reversal_and_readdition_preserve_world_proof(store):
    a,b,c = [store.create_person(n) for n in 'ABC']
    oid = correction_helpers.IdentityCorrectionTest()._finalize(store, 'explicit-history', [c])['observation_id']
    as_of = '2026-10-29T12:00:00Z'
    store.correct_encounter(oid, 'explicit-date', expected_revision=store.get_encounter_read(oid)['revision'],
        event_details={'date':'2026-10-28','time':'12:00','time_precision':'exact'})
    def add(person, op, peers):
        store.correct_encounter(oid, op, expected_revision=store.get_encounter_read(oid)['revision'],
            participant_correction={'action':'ADD','person_id':person.person_id},
            relations=[{'first_person_id':person.person_id,'second_person_id':peer.person_id,'disposition':'INCLUDE'} for peer in peers])
    add(a, 'explicit-initial-a', [c])
    store.correct_observation_identity(oid, a.person_id, b.person_id, 'explicit-a-b')
    store.correct_observation_identity(oid, b.person_id, a.person_id, 'explicit-b-a')
    assert set(store.get_encounter_read(oid)['participant_ids']) == {a.person_id,c.person_id}
    assert len(store.get_world_graph_v2_read(Request(collection=C.RELATIONSHIPS,as_of=as_of)).relationships) == 1
    store.correct_observation_identity(oid, a.person_id, b.person_id, 'explicit-again-a-b')
    add(a, 'explicit-readd-a', [b,c])
    assert set(store.get_encounter_read(oid)['participant_ids']) == {a.person_id,b.person_id,c.person_id}
    assert len(store.get_person_neighbors(a.person_id)) == 2
    result = store.get_world_graph_v2_read(Request(collection=C.RELATIONSHIPS,as_of=as_of))
    assert {frozenset((r.source_person_id,r.target_person_id)) for r in result.relationships} == {
        frozenset(pair) for pair in itertools.combinations((a.person_id,b.person_id,c.person_id),2)}
    for edge in result.relationships:
        assert edge.evidence_count == edge.encounter_recurrence['count'] == 1
        proof = store.get_world_graph_v2_read(Request(collection=C.EVIDENCE,detail_level=L.EVIDENCE,
            focus_type='RELATIONSHIP',focus_id=edge.relationship_id,as_of=as_of))
        assert len(proof.evidence) == 1 and proof.evidence[0].supporting_references[0]['source_entity_id'] == oid
        assert set(proof.evidence[0].effective_endpoints) == {edge.source_person_id,edge.target_person_id}
