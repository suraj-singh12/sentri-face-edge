"""Issue #20: hand-specified correction histories; no biometric acceptance."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_moderate as m
import qa_foundation as qa
from sentriface.storage.sqlite_store import SQLiteIdentityStore

DATE = '2026-11-03'


@pytest.fixture
def authority(tmp_path):
    store = SQLiteIdentityStore(tmp_path / 'identity.db', embedding_dim=2)
    store.initialize()
    return store


def event(people, location, media_count=1):
    return dict(participant_ids=sorted(people), location=location, media_count=media_count,
                observed_at=DATE + 'T12:00:00')


def check(store, people, events, edges=None):
    return m.snapshot(m.store_reader(store), people, events, edges or {}, DATE)


def test_c01_face_assignment_history(authority, request):
    s = authority
    a, b = [s.create_person(n) for n in ('A', 'B')]
    people = [a.person_id, b.person_id]
    e1 = m.finalize(s, 'c01-first', [b], DATE, 'X')
    e2 = m.finalize(s, 'c01-second', [a], DATE, 'Y')
    expected = {e1: event([b.person_id], 'X'), e2: event([a.person_id], 'Y')}
    original = check(s, people, expected)
    raw = m.history(s, e2)
    request.node.user_properties.append(('provenance', json.dumps(raw)))
    proofs = []
    m.record(proofs, 'Original accepted A at Y; independently accepted B at X', expected, original)
    # A pure FACE_ASSIGNMENT path (without participant revisions) is essential:
    # a REASSIGN presence revision alone could mask the original #22 regression.
    embedding = raw['observation_face_assignments'][0]['embedding_id']
    expected[e2] = event([b.person_id], 'Y')
    from sentriface.correction_service import IdentityCorrectionService
    from sentriface.graph_service import GlobalIdentityGraphService
    IdentityCorrectionService(GlobalIdentityGraphService(s)).move_face(embedding, b.person_id, 'c01-a-to-b')
    m.record(proofs, 'FACE_ASSIGNMENT A -> B', expected, check(s, people, expected))
    qa.assert_expected(raw, m.history(s, e2), 'C01.immutable_provenance')
    changes = s.list_corrections_for_observation(e2)
    assert any(c.correction_type == 'FACE_ASSIGNMENT' and c.from_person_id == a.person_id and c.to_person_id == b.person_id for c in changes)
    for phase in ('refresh', 'reopen', 'rebuild'):
        if phase == 'reopen':
            s = SQLiteIdentityStore(s.db_path, embedding_dim=2); s.initialize()
        if phase == 'rebuild':
            s.rebuild_graph_projection('c01-rebuild')
        m.record(proofs, phase, expected, check(s, people, expected))
        qa.assert_expected(raw, m.history(s, e2), 'C01.persisted_provenance')
    request.node.user_properties.append(('historical_proofs', json.dumps(proofs)))
    request.node.user_properties.append(('dataset', json.dumps(dict(profile='Sparse-like correction',
        requested=dict(people=2, photos=0, encounters=2), created=dict(people=2, photos=0, encounters=2),
        independently_verified=dict(people=2, photos=0, encounters=2), domain_media_records=2, inference_executed=False))))


def test_metadata_participants_rejections(authority, request):
    s = authority
    a, b = [s.create_person(n) for n in ('A', 'B')]
    people = [a.person_id, b.person_id]
    oid = m.finalize(s, 'focused', [a], '2026-11-02', 'X')
    events = {oid: dict(event([a.person_id], 'X'), observed_at='2026-11-02T12:00:00')}
    proofs = []
    def verify(action):
        m.record(proofs, action, events, check(s, people, events))
    verify('original')
    original = s.get_encounter_read(oid)
    events[oid].update(location='Y', observed_at=DATE + 'T15:45:00')
    result = m.correction(s, oid, 'metadata-change', event_details=dict(date=DATE, time='15:45', place_seen='Y'))
    verify('date/time/location revision')
    qa.assert_expected(original['location'], result['historical_value']['location'])
    assert s.correct_encounter(oid, 'metadata-change', expected_revision=original['revision']) == result
    before = s.get_encounter_read(oid)
    for op, values in [('stale', {}), ('missing-target', dict(participant_correction=dict(action='REASSIGN', person_id=a.person_id, to_person_id='missing'))),
                       ('last-participant', dict(participant_correction=dict(action='REMOVE', person_id=a.person_id))),
                       ('invalid-time', dict(event_details=dict(time='99:99')))]:
        with pytest.raises((ValueError, KeyError)):
            s.correct_encounter(oid, op, expected_revision=original['revision'] if op == 'stale' else before['revision'], **values)
        assert s.get_operation(op) is None
        qa.assert_expected(before, s.get_encounter_read(oid), 'rejection.atomic')
        verify('rejected ' + op)
    # A participant without a face requires an explicit pair decision.
    events[oid]['participant_ids'] = sorted(people)
    m.correction(s, oid, 'add-b', participant_correction=dict(action='ADD', person_id=b.person_id),
                 relations=[m.relation(*people, 'EXCLUDE')])
    verify('ADD B with explicitly excluded pair')
    events[oid]['participant_ids'] = [a.person_id]
    m.correction(s, oid, 'remove-b', participant_correction=dict(action='REMOVE', person_id=b.person_id))
    verify('REMOVE B retains original occurrence')
    request.node.user_properties.append(('historical_proofs', json.dumps(proofs)))


def test_c02_independent_evidence_history(authority, request):
    s = authority
    a, b = [s.create_person(n) for n in ('A', 'B')]
    people = [a.person_id, b.person_id]
    pair = tuple(sorted(people))
    oid = m.finalize(s, 'evidence', [a, b], DATE, 'X')
    events = {oid: event(people, 'X', 2)}
    counts = {'CO_OBSERVED': 1}
    proofs = []
    def verify(action):
        edges = {pair: dict(counts)} if counts else {}
        m.record(proofs, action, dict(events=events, evidence=counts), check(s, people, events, edges))
    verify('original legitimate co-observation')
    manual = s.create_manual_association(*people, 'manual-create')
    counts['MANUAL_ASSOCIATION'] = 1
    verify('independent standing manual evidence')
    m.correction(s, oid, 'exclude', relations=[m.relation(*people, 'EXCLUDE')])
    del counts['CO_OBSERVED']
    verify('EXCLUDE removes only Encounter evidence')
    # Event-selected mentions are searchable, not relationship authority.
    events[oid]['mentioned_person_ids'] = [b.person_id]
    m.correction(s, oid, 'event-note', event_details=dict(event_notes='Selected @B and literal @A', event_mentioned_person_ids=[b.person_id]))
    verify('Event selected mention has no relationship effect')
    s.update_person_notes(a.person_id, 'Literal @B', '', 'QA', 'literal')
    verify('literal Person mention is inert')
    s.update_person_notes(a.person_id, 'Selected @B', 'Literal @B', 'QA', 'selected', [b.person_id])
    counts['NOTE_REFERENCE'] = 1
    verify('selected Person mention adds directed independent support')
    s.retire_manual_association(manual['evidence_id'], 'manual-remove')
    del counts['MANUAL_ASSOCIATION']
    verify('manual retirement retains selected Note evidence')
    m.correction(s, oid, 'include', relations=[m.relation(*people, 'INCLUDE')])
    counts['CO_OBSERVED'] = 1
    verify('INCLUDE restores only co-observation support')
    s.update_person_notes(a.person_id, 'Literal @B again', 'Selected @B', 'QA', 'clear-selected', [])
    del counts['NOTE_REFERENCE']
    verify('mention removal retains legitimate co-observation')
    # Accepted no-face attachment: more media, same Encounter, same evidence.
    session = s.create_init_session('/managed/c02-attach', target_observation_id=oid, expected_revision=s.get_encounter_read(oid)['revision'])
    s.save_init_session_media(session.session_id, ['/managed/c02-extra.jpg'])
    mid = s.list_init_session_media(session.session_id)[0]['media_id']
    rid = s.plan_init_session_encounters(session.session_id, [[mid]], target_observation_id=oid,
        expected_revision=s.get_encounter_read(oid)['revision'])[0]['review_id']
    s.complete_encounter_identity_review(rid)
    s.complete_photo_review(rid, 'attach-media')
    events[oid]['media_count'] = 3
    verify('attachment preserves Encounter ownership and occurrence count')
    assert [x.media_id for x in s.list_observation_media(oid)].count(mid) == 1
    s.create_manual_association(*people, 'manual-independent-again')
    counts['MANUAL_ASSOCIATION'] = 1
    verify('new independent manual source before participation removal')
    events[oid]['participant_ids'] = [a.person_id]
    m.correction(s, oid, 'remove-b-with-independent-evidence', participant_correction=dict(action='REMOVE', person_id=b.person_id))
    del counts['CO_OBSERVED']
    verify('REMOVE B loses only this occurrence; manual and Event mention remain')
    assert [x.media_id for x in s.list_observation_media(oid)].count(mid) == 1
    for phase in ('reopen', 'rebuild'):
        if phase == 'reopen':
            s = SQLiteIdentityStore(s.db_path, embedding_dim=2); s.initialize()
        else:
            s.rebuild_graph_projection('c02-rebuild')
        verify(phase)
    all_evidence = s.get_connection_evidence(*people, include_inactive=True)
    assert any(not e.active and e.evidence_id == manual['evidence_id'] for e in all_evidence)
    assert any(not e.active and e.evidence_type == 'NOTE_REFERENCE' for e in all_evidence)
    request.node.user_properties.append(('historical_proofs', json.dumps(proofs)))


def test_archive_restore_preserves_corrected_history(authority):
    s = authority
    a = s.create_person('A')
    oid = m.finalize(s, 'lifecycle', [a], DATE, 'X')
    expected = {oid: event([a.person_id], 'Y')}
    m.correction(s, oid, 'location', event_details=dict(place_seen='Y'))
    check(s, [a.person_id], expected)
    s.archive_person(a.person_id, 'archive')
    graph = m.store_reader(s)('/api/person-graph?person_id=' + a.person_id)
    qa.assert_expected('ARCHIVED', graph['root_requested_state'])
    assert 'OPEN' not in graph['nodes'][0]['allowed_actions']
    qa.assert_expected(expected[oid], s.get_encounter_read(oid))
    assert len(s.list_person_sightings(a.person_id)) == 1
    s.restore_person(a.person_id, 'restore')
    check(s, [a.person_id], expected)


@pytest.mark.parametrize('mutation', ['participant', 'location', 'occurrence', 'evidence'])
def test_oracle_rejects_wrong_historical_expectations(authority, mutation):
    s = authority
    a, b = [s.create_person(n) for n in ('A', 'B')]
    oid = m.finalize(s, 'oracle', [a], DATE, 'X')
    events = {oid: event([a.person_id], 'X')}
    edges = {}
    check(s, [a.person_id, b.person_id], events)
    if mutation == 'participant':
        events[oid]['participant_ids'] = [b.person_id]
    elif mutation == 'location':
        events[oid]['location'] = 'WRONG'
    elif mutation == 'occurrence':
        events['phantom'] = deepcopy(events[oid])
    else:
        edges[tuple(sorted((a.person_id, b.person_id)))] = {'MANUAL_ASSOCIATION': 1}
    with pytest.raises(AssertionError, match='Moderate'):
        check(s, [a.person_id, b.person_id], events, edges)


def test_sighting_selected_and_literal_mentions(authority, request):
    from tests import test_identity_corrections as fixtures
    s = authority
    a, b = [s.create_person(n) for n in ('A', 'B')]
    # Existing P6 review write: a Sighting Note belongs to the accepted face's
    # recognition detail, not to the Encounter-level Event Note.
    fixtures.IdentityCorrectionTest()._pending(s, 'sighting', (1.0, 0.0))
    s.create_photo_review('sighting-review', 'sighting.jpg', [dict(face_id='face', staged_face_type='PENDING_ADDITION', staged_face_id='sighting')], media_path='/managed/sighting.jpg')
    s.set_photo_review_face_decision('sighting-review', 'face', 'ACCEPT_EXISTING_PERSON', person_id=a.person_id,
                                    notes='Literal @B', mentioned_person_ids=[])
    oid = s.complete_photo_review('sighting-review', 'sighting-complete')['observation_id']
    m.correction(s, oid, 'sighting-metadata', event_details=dict(date=DATE, time='12:00', time_precision='exact', place_seen='X'))
    events = {oid: event([a.person_id], 'X')}
    people = [a.person_id, b.person_id]
    proofs = []
    m.record(proofs, 'Sighting literal text creates no edge or B occurrence', events, check(s, people, events))
    notes = s.list_person_notes(a.person_id)
    note = next(n for n in notes if n.content == 'Literal @B')
    expected_edges = {tuple(sorted(people)): {'NOTE_REFERENCE':1}}
    s.update_note(note.note_id, 'Selected @B', 'sighting-selected', mentioned_person_ids=[b.person_id], expected_revision_number=note.revision_number)
    m.record(proofs, 'Sighting selected mention adds one directed Note source only', dict(events=events, evidence='NOTE_REFERENCE A -> B'), check(s, people, events, expected_edges))
    before = s.get_note(note.note_id)
    with pytest.raises(KeyError, match='changed'):
        s.update_note(note.note_id, 'Stale', 'sighting-stale', expected_revision_number=note.revision_number)
    assert s.get_note(note.note_id) == before
    s.update_note(note.note_id, 'Literal @B again', 'sighting-clear', mentioned_person_ids=[], expected_revision_number=before.revision_number)
    m.record(proofs, 'Sighting mention removal preserves literal history', events, check(s, people, events))
    assert len(s.list_note_revisions(note.note_id)) == 3
    request.node.user_properties.append(('historical_proofs', json.dumps(proofs)))


def test_moderate_registry_exact_scope_and_executable_targets():
    rows = json.loads((ROOT / 'tests/qa_coverage.json').read_text())['moderate_acceptance']
    assert [r['id'] for r in rows] == [f'M{i:02}' for i in range(1,9)] + ['C01','C02']
    for row in rows:
        assert row['tests'] or row['journeys']
        assert set(row['journeys']) <= {'C01','C02'}
        for target in row['tests']:
            assert (ROOT / target.split('::')[0]).is_file()


def test_moderate_dirty_preflight_reports_no_acceptance(tmp_path, monkeypatch, capsys):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/qa_coverage.json').write_text((ROOT / 'tests/qa_coverage.json').read_text())
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.platform, 'platform', lambda: 'QA test environment')
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda cmd, **k: 'a'*40 if 'rev-parse' in cmd else ' M scripts/qa_foundation.py')
    assert qa.main(['--phase','Moderate','--test','Moderate','--disposable']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['outcome'] == 'BLOCKED'
    assert len(report['acceptance']) == 10
    assert {r['status'] for r in report['acceptance']} == {'NOT RUN'}
    assert report['inference_executed'] is False


@pytest.mark.parametrize('condition,outcome', [('complete','PASS'), ('missing','BLOCKED'), ('skipped','BLOCKED'), ('failure','FAIL'), ('exit','FAIL')])
def test_moderate_reporting_never_substitutes_missing_execution(tmp_path, monkeypatch, condition, outcome):
    """Mechanism test only; fabricated outcomes cannot be acceptance evidence."""
    import time
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace
    rows = json.loads((ROOT / 'tests/qa_coverage.json').read_text())['moderate_acceptance']
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/qa_coverage.json').write_text(json.dumps(dict(moderate_acceptance=rows)))
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    targets = sorted({t for r in rows for t in r['tests']})
    chosen = rows[-2]['tests'][0]
    def focused(*args, **kwargs):
        suite = ET.Element('testsuite')
        for target in targets:
            if condition == 'missing' and target == chosen: continue
            parts = target.split('::')
            name = parts[-1]
            classname = parts[0][:-3].replace('/', '.') + ('.' + '.'.join(parts[1:-1]) if len(parts)>2 else '')
            case = ET.SubElement(suite, 'testcase', classname=classname, name=name)
            if target == chosen and condition in ('skipped','failure'):
                ET.SubElement(case, condition)
        ET.ElementTree(suite).write(evidence / 'focused.xml')
        return SimpleNamespace(returncode=1 if condition in ('failure','exit') else 0)
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'run', focused)
    monkeypatch.setattr(qa, 'require_browser', lambda: None)
    monkeypatch.setattr(m, 'execute', lambda args, directory, run, journey: run.update(
        browser_executed=True, domain_verified=True, rebuild_verified=True, restart_verified=True, cleanup_completed=True, browser_errors=[]))
    def missing(*args): raise ValueError('No authorized pair')
    monkeypatch.setattr(qa, 'verified_pair', missing)
    report = dict(test_id='Moderate', phase='Moderate', commit='a'*40, platform='Mechanism test')
    args = SimpleNamespace(test='Moderate', phase='Moderate', fixtures=tmp_path, actor='QA')
    assert qa.normal_campaign(args, evidence, report, time.monotonic()) == {'PASS':0,'FAIL':1,'BLOCKED':2}[outcome]
    assert report['outcome'] == outcome
    assert len(report['acceptance']) == 10
    if condition in ('missing','skipped'): assert report['acceptance'][-2]['status'] == 'PARTIAL'
    assert report['biometric_status'] == 'BLOCKED'
    assert report['inference_executed'] is False
    assert report['model_hashes'] == {}
    assert ET.parse(evidence / 'junit.xml').getroot().get('tests') == '11'


def test_saved_operator_identity_outranks_proposal(authority):
    from tests import test_identity_corrections as fixtures
    from sentriface.models import PersonMatch
    s = authority
    a, b = [s.create_person(n) for n in ('Accepted A', 'Proposed B')]
    # Deliberately conflicting deterministic proposal. This is domain evidence,
    # not recognition accuracy or genuine biometric acceptance.
    fixtures.IdentityCorrectionTest()._pending(s, 'proposed-b', (1.0,0.0),
        matches=[PersonMatch(b.person_id, .99, (), 0)])
    s.create_photo_review('operator-review', 'operator.jpg', [dict(face_id='face', staged_face_type='PENDING_ADDITION', staged_face_id='proposed-b')], media_path='/managed/proposed-b.jpg')
    s.set_photo_review_face_decision('operator-review', 'face', 'ACCEPT_EXISTING_PERSON', person_id=a.person_id)
    s = SQLiteIdentityStore(s.db_path, embedding_dim=2); s.initialize()
    oid = s.complete_photo_review('operator-review', 'operator-complete')['observation_id']
    m.correction(s, oid, 'operator-metadata', event_details=dict(date=DATE, time='12:00', time_precision='exact', place_seen='X'))
    expected = {oid:event([a.person_id], 'X')}
    check(s, [a.person_id,b.person_id], expected)
    raw = m.history(s, oid)
    qa.assert_expected(a.person_id, raw['original_review_decisions'][0]['person_id'], 'operator.saved_identity')
    s.rebuild_graph_projection('operator-rebuild')
    check(s, [a.person_id,b.person_id], expected)
