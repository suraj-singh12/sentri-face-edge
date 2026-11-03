"""Advanced domain execution; no deterministic vector is biometric evidence."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import qa_advanced as a
import qa_foundation as qa
from sentriface.storage.sqlite_store import SQLiteIdentityStore

DATE='2026-11-03'

@pytest.fixture
def authority(tmp_path):
    s=SQLiteIdentityStore(tmp_path/'advanced.db',embedding_dim=2); s.initialize()
    return s

@pytest.mark.parametrize('journey',['H01','H02'])
def test_connected_history(authority,request,journey):
    proofs=[]
    final=(a.h01 if journey=='H01' else a.h02)(authority,DATE,proofs)
    before=a.audit(authority)
    s=SQLiteIdentityStore(authority.db_path,embedding_dim=2); s.initialize()
    qa.assert_expected(before,a.audit(s),'Advanced.reopen.raw_authority')
    observed=a.verify(s,final['people'],final['events'],final['edges'],final['canonical'],final['raw'],DATE)
    a.m.record(proofs,'Reopened SQLite authority',dict(events=final['events'],canonical=final['canonical']),observed)
    request.node.user_properties.append(('historical_proofs',json.dumps(proofs)))
    request.node.user_properties.append(('dataset',json.dumps(dict(profile=journey,
        requested=dict(people=3 if journey=='H01' else 2,photos=0,encounters=3 if journey=='H01' else 1),
        independently_verified=dict(people=3 if journey=='H01' else 2,photos=0,encounters=len(final['events'])),inference_executed=False))))

@pytest.mark.parametrize('mutation',['canonical','duplicate','evidence','provenance'])
def test_mutations_rejected(authority,mutation):
    final=a.h01(authority,DATE,[])
    args=deepcopy(final)
    if mutation=='canonical': args['canonical'][args['source']]=args['third']
    elif mutation=='duplicate': next(iter(args['events'].values()))['participant_ids'] *= 2
    elif mutation=='evidence': next(iter(args['edges'].values()))['MANUAL_ASSOCIATION']=0
    else: next(iter(args['raw'].values()))['original_review_decisions'][0]['person_id']=args['third']
    expected_path={'canonical':'Advanced.canonical','duplicate':'Moderate.Events.record.participant_ids',
        'evidence':'Moderate.PersonGraph.evidence','provenance':'Advanced.provenance'}[mutation]
    with pytest.raises(AssertionError,match=expected_path):
        a.verify(authority,args['people'],args['events'],args['edges'],args['canonical'],args['raw'],DATE)


def test_regular_correct_merge_reconstruct(authority,request):
    """One Regular nonbiometric history, exact pagination after correction/merge.
    Uses the existing efficient media-free fixture. No Dense escalation warranted.
    """
    from tests.test_world_graph_v2 import WorldGraphV2Test
    from sentriface.models import WorldGraphRequest,WorldCollection,WorldReadFilter,WorldReadLimits
    from dataclasses import replace
    import time
    s=authority
    persons=[s.create_person('Regular '+str(i)) for i in range(25)]
    ids=[p.person_id for p in persons]
    expected={}
    for i in range(30):
        truth=a.event([ids[i%25]],'X' if i%2==0 else 'Y',0)
        oid=WorldGraphV2Test()._observe(s,'advanced-regular-'+str(i),truth['participant_ids'],observed_at=DATE+'T12:00:00+00:00',location=truth['location'])
        expected[oid]=truth
    first=next(iter(expected)); expected[first]['participant_ids']=[ids[1]]
    s.correct_observation_identity(first,ids[0],ids[1],'regular-correct')
    # Only A's other occurrence migrates through the canonical merge.
    other=list(expected)[25]; expected[other]['participant_ids']=[ids[1]]
    s.execute_identity_merge(ids[0],ids[1],'regular-merge')
    timings={}
    for phase in ('corrected','reopened','rebuilt','rebuilt-again'):
        start=time.monotonic()
        if phase=='reopened': s=SQLiteIdentityStore(s.db_path,embedding_dim=2); s.initialize()
        if phase.startswith('rebuilt'): s.rebuild_graph_projection('regular-'+phase)
        found={}; cursor=''
        while True:
            page=s.query_encounters(limit=7,cursor=cursor)
            for row in page['events']:
                oid=row['observation_id']; assert oid not in found
                qa.assert_expected(expected[oid],row,'Advanced.Regular.Events'); found[oid]=True
            cursor=page['next_cursor']
            if not cursor: break
        qa.assert_expected(sorted(expected),sorted(found),'Advanced.Regular.complete')
        query=WorldGraphRequest(collection=WorldCollection.MOST_FREQUENTLY_SEEN,view='EXPLORE',as_of=DATE+'T23:59:59+00:00',filters=WorldReadFilter(evidence_type=('CO_OBSERVED',)),limits=WorldReadLimits(people=7))
        discoveries={}
        while True:
            result=s.get_world_graph_v2_read(query)
            for row in result.discoveries:
                pid=row.canonical_person_id; assert pid not in discoveries
                occurrences=sorted(k for k,e in expected.items() if pid in e['participant_ids'])
                qa.assert_expected(occurrences,sorted(e['event_id'] for e in row.supporting_encounters),'Advanced.Regular.proof')
                qa.assert_expected(len(occurrences),row.count,'Advanced.Regular.count')
                discoveries[pid]=row.count
            if not result.next_cursor: break
            query=replace(query,cursor=result.next_cursor)
        qa.assert_expected(sorted(ids[1:]),sorted(discoveries),'Advanced.Regular.canonical_completeness')
        qa.assert_expected(4,discoveries[ids[1]],'Advanced.Regular.survivor_union')
        timings[phase]=round(time.monotonic()-start,6)
    request.node.user_properties.append(('dataset',json.dumps(dict(profile='Regular',requested=dict(people=25,photos=80,encounters=30),created=dict(people=25,photos=0,encounters=30),independently_verified=dict(raw_people=25,canonical_people=24,photos=0,encounters=30),timings=timings,limitation='Nonbiometric media-free history; Dense and photographic profiles NOT RUN'))))


def test_archived_source_and_invalid_merges(authority):
    s=authority
    source,target=[s.create_person(n) for n in ('Archived source','Target')]
    s.archive_person(source.person_id,'archive')
    s.execute_identity_merge(source.person_id,target.person_id,'archived-merge')
    qa.assert_expected(target.person_id,s.get_effective_person(source.person_id).person_id)
    before=a.audit(s)
    for left,right in ((target.person_id,target.person_id),('missing',target.person_id),(target.person_id,'missing')):
        with pytest.raises((KeyError,ValueError)): s.execute_identity_merge(left,right,'invalid-'+left+right)
    qa.assert_expected(before,a.audit(s),'Advanced.invalid.no_mutation')
    tomb=s.create_person('Tombstone'); s.soft_delete_person(tomb.person_id,'tombstone')
    with pytest.raises((KeyError,ValueError)): s.execute_identity_merge(tomb.person_id,target.person_id,'deleted-source')


def test_advanced_scope_and_preflight(tmp_path,monkeypatch,capsys):
    registry=json.loads((ROOT/'tests/qa_coverage.json').read_text())
    assert [r['id'] for r in registry['advanced_acceptance']]==[f'A{i:02}' for i in range(1,9)]+['H01','H02']
    (tmp_path/'tests').mkdir(); (tmp_path/'tests/qa_coverage.json').write_text(json.dumps(registry))
    monkeypatch.setattr(qa,'ROOT',tmp_path)
    monkeypatch.setattr(qa.platform,'platform',lambda:'QA test environment')
    monkeypatch.setattr(qa.subprocess,'check_output',lambda cmd,**k:'a'*40 if 'rev-parse' in cmd else ' M dirty')
    assert qa.main(['--phase','Advanced','--test','Advanced','--disposable'])==2
    report=json.loads(capsys.readouterr().out)
    assert {r['status'] for r in report['acceptance']}=={'NOT RUN'}


def test_unauthorized_merge_cannot_mutate_authority():
    # Reuse the established HTTP fixture/auth/request helpers, no parallel server.
    from tests import test_auth_api as api
    helper=api.AuthenticationApiTest()
    with helper._running_server() as server:
        admin,_=server.auth.signup_initial('advanced-owner','Owner',api.PASSWORD)
        server.auth.create_user(admin,'advanced-viewer','Viewer','advanced viewer password',['viewer'])
        cookie=helper._login_cookie(server,'advanced-viewer','advanced viewer password')
        s=server.engine.store
        first,second=[s.create_person(n) for n in ('First','Second')]
        payload=dict(source_person_id=first.person_id,target_person_id=second.person_id,operation_id='11111111-1111-4111-8111-111111111111')
        before=a.audit(s)
        for endpoint in ('/api/person-merge-preview','/api/person-merge'):
            status,_,_=helper._request(server,'POST',endpoint,payload,cookie=cookie)
            assert status==403
        qa.assert_expected(before,a.audit(s),'Advanced.unauthorized.merge')
        assert s.get_operation(payload['operation_id']) is None
