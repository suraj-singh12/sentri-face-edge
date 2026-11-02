"""Normal QA: deterministic domain fixtures are NOT photographic/ONNX evidence."""
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_foundation as qa
import qa_browser as ui
from sentriface.models import WorldCollection, WorldGraphRequest, WorldReadLimits, WorldReadFilter
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from tests import test_world_graph_v2 as fixtures
from tests.test_qa_journey import context_for, read_fixture


def test_reference_oracle_rejects_wrong_owner_and_eligibility():
    truth, payloads = read_fixture()
    reference = dict(person_id='p1', canonical_person_id='p1', active=True, recognition_conflict=False,
                     recognition_eligible=True, origin='STANDALONE_ENROLLMENT')
    payloads['/api/person']['recognition_references'] = dict(active_count=1, drafts=[], references=[reference])
    context = context_for(payloads)
    assert ui.reference_snapshot(context, 'p1')['eligible'] is True
    for field, wrong in [('person_id', 'p2'), ('recognition_eligible', False), ('recognition_conflict', True)]:
        saved = reference[field]
        reference[field] = wrong
        with pytest.raises(AssertionError, match='Reference.owner.' + field):
            ui.reference_snapshot(context, 'p1')
        reference[field] = saved


@pytest.mark.parametrize('profile,people_count,event_count', [('Regular', 25, 30), ('Dense', 100, 120)])
def test_bounded_domain_reads(tmp_path, request, profile, people_count, event_count):
    """Exactly two scale-sensitive operations: Event pagination and World discovery.

    Known input assigns occurrence i to person i % n. Expected truth is authored
    here, independently of the production participant/World calculations.
    """
    store = SQLiteIdentityStore(tmp_path / 'identity.db', embedding_dim=2)
    store.initialize()
    people = [store.create_person(f'Normal fixture {i}') for i in range(people_count)]
    expected = {}
    counts = {p.person_id: 0 for p in people}
    for index in range(event_count):
        pid = people[index % people_count].person_id
        location = f'Fixture site {index % 2}'
        oid = fixtures.WorldGraphV2Test()._observe(store, f'normal-{index}', [pid],
            observed_at='2026-11-02T12:00:00+00:00', location=location)
        expected[oid] = dict(participant_ids=[pid], location=location, media_count=0)
        counts[pid] += 1
    def authority():
        # Read-only SQL audit, never used to calculate expected participants/counts.
        with store._connect() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {name: sorted((tuple(r) for r in conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"')), key=repr) for name in tables}
    before = authority()
    timings = {}
    for cycle in ('first', 'repeat', 'reopen'):
        if cycle == 'reopen':
            store = SQLiteIdentityStore(store.db_path, embedding_dim=2)
        start = time.monotonic()
        observed, cursor = {}, ''
        while True:
            page = store.query_encounters(limit=25, cursor=cursor)
            for event in page['events']:
                oid = event['observation_id']
                assert oid not in observed, 'Duplicate occurrence across pages'
                qa.assert_expected(expected[oid], event, 'Event.page')
                observed[oid] = True
            cursor = page['next_cursor']
            if not cursor:
                break
        qa.assert_expected(sorted(expected), sorted(observed), 'Events.complete')
        timings[cycle + '_events_seconds'] = round(time.monotonic() - start, 6)
        start = time.monotonic()
        query = WorldGraphRequest(collection=WorldCollection.MOST_FREQUENTLY_SEEN, view='EXPLORE',
            as_of='2026-11-02T23:59:59+00:00', filters=WorldReadFilter(evidence_type=('CO_OBSERVED',)), limits=WorldReadLimits(people=25))
        found = {}
        while True:
            result = store.get_world_graph_v2_read(query)
            for discovery in result.discoveries:
                pid = discovery.canonical_person_id
                assert pid not in found, 'Duplicate Person across discovery pages'
                found[pid] = discovery.count
                qa.assert_expected(sorted(oid for oid, e in expected.items() if pid in e['participant_ids']),
                    sorted(e['event_id'] for e in discovery.supporting_encounters), 'World.support')
            if not result.next_cursor:
                break
            query = replace(query, cursor=result.next_cursor)
        qa.assert_expected(sorted(counts.items()), sorted(found.items()), 'World.independent_counts')
        timings[cycle + '_world_seconds'] = round(time.monotonic() - start, 6)
    qa.assert_expected(before, authority(), 'read_only.authority')
    with pytest.raises(AssertionError, match='wrong_expectation'):
        qa.assert_expected(event_count + 1, len(observed), 'wrong_expectation')
    request.node.user_properties.append(('dataset', json.dumps(dict(profile=profile,
        requested=dict(people=people_count, verified_photos=80 if profile == 'Regular' else 350, encounters=event_count),
        created=dict(people=people_count, verified_photos=0, encounters=event_count),
        independently_verified=dict(people=len(found), verified_photos=0, encounters=len(observed)),
        genuine_photos_available=0, operations=['Event pagination', 'World discovery'], timings=timings,
        limitation='Non-biometric domain fixtures only; photographic targets not attempted'))))


def test_normal_registry_has_exact_scope_and_executable_evidence():
    rows = json.loads((ROOT / 'tests/qa_coverage.json').read_text())['normal_acceptance']
    assert [r['id'] for r in rows] == [f'N{i:02}' for i in range(1, 11)] + ['J01', 'J02']
    for row in rows:
        assert row['tests'] or row['journeys']
        for target in row['tests']:
            assert (ROOT / target.split('::')[0]).is_file()


@pytest.mark.parametrize('states,expected', [([], 'NOT RUN'), (['BLOCKED'], 'NOT RUN'),
    (['NOT RUN'], 'NOT RUN'), (['PASS', 'BLOCKED'], 'PARTIAL'),
    (['PASS', 'NOT RUN'], 'PARTIAL'), (['FAIL', 'PASS'], 'FAIL'),
    (['PASS', 'PASS'], 'PASS')])
def test_missing_skipped_or_blocked_evidence_cannot_pass(states, expected):
    assert qa.normal_status(states) == expected


def test_normal_campaign_preserves_missing_biometric_acceptance(tmp_path, monkeypatch, capsys):
    """Reporting mechanism only: hand-authored test outcomes, no acceptance claim."""
    from types import SimpleNamespace
    import xml.etree.ElementTree as ET
    registry = json.loads((ROOT / 'tests/qa_coverage.json').read_text())
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/qa_coverage.json').write_text(json.dumps(registry))
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    def focused(command, **kwargs):
        suite = ET.Element('testsuite')
        for target in sorted({t for r in registry['normal_acceptance'] for t in r['tests']}):
            parts = target.split('::')
            classname = parts[0][:-3].replace('/', '.') + ('.' + '.'.join(parts[1:-1]) if len(parts) > 2 else '')
            ET.SubElement(suite, 'testcase', classname=classname, name=parts[-1])
        ET.ElementTree(suite).write(evidence / 'focused.xml')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'run', focused)
    monkeypatch.setattr(qa, 'require_browser', lambda: None)
    monkeypatch.setattr(qa, 'execute_ordinary', lambda args, directory, run: run.update(
        restart_verified=True, cleanup_completed=True, browser_errors=[]))
    def missing(*args):
        raise ValueError('No reviewed authorized photographs')
    monkeypatch.setattr(qa, 'verified_pair', missing)
    args = SimpleNamespace(test='Normal', fixtures=tmp_path, actor='Private fixture', models_config=None)
    report = dict(test_id='Normal')
    assert qa.normal_campaign(args, evidence, report, time.monotonic()) == 2
    assert report['inference_executed'] is False
    assert report['model_hashes'] == {}
    assert [(r['test_id'], r['outcome']) for r in report['runs']] == [('QA-J02', 'PASS'), ('QA-J01', 'BLOCKED')]
    states = {r['id']: r['status'] for r in report['acceptance']}
    assert states['J02'] == 'PASS'
    assert states['J01'] == states['N04'] == 'NOT RUN'
    assert states['N03'] == 'PARTIAL'


@pytest.mark.parametrize('mutation', ['identity', 'participants', 'location', 'occurrence', 'discovery', 'support'])
def test_ordinary_oracle_rejects_independent_mismatches(mutation):
    truth, payloads = read_fixture()
    payloads['/api/person']['person']['biometric_status'] = 'NO_FACE'
    payloads['/api/encounter']['media'] = []
    payloads['/api/encounter']['media_count'] = 0
    payloads['/api/encounters']['events'][0]['media_count'] = 0
    payloads['/api/world-graph']['graph_revision'] = 'fixture-revision'
    expected = {'e1': dict(participant_ids=['p1'], location='London', media_count=0)}
    context = context_for(payloads)
    ui.ordinary_snapshot(context, {'p1': 'Known Actor'}, expected, truth['date'])
    if mutation == 'identity':
        payloads['/api/person']['person']['name'] = 'Wrong identity'
    elif mutation == 'participants':
        payloads['/api/encounter']['participant_ids'] = ['p2']
    elif mutation == 'location':
        payloads['/api/encounter']['location'] = 'Wrong location'
    elif mutation == 'occurrence':
        payloads['/api/encounters']['events'] *= 2
    elif mutation == 'discovery':
        payloads['/api/world-graph']['discoveries'].append(dict(canonical_person_id='p2', count=1))
    else:
        payloads['/api/world-graph']['discoveries'][0]['supporting_encounters'] = []
    with pytest.raises(AssertionError, match='J02'):
        ui.ordinary_snapshot(context, {'p1': 'Known Actor'}, expected, truth['date'])


def test_normal_preflight_refusal_records_all_entries_not_run(tmp_path, monkeypatch, capsys):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/qa_coverage.json').write_text((ROOT / 'tests/qa_coverage.json').read_text())
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda *a, **k: '')
    assert qa.main(['--phase', 'Normal', '--test', 'Normal']) == 2
    report = json.loads(capsys.readouterr().out)
    assert len(report['acceptance']) == 12
    assert {r['status'] for r in report['acceptance']} == {'NOT RUN'}
    assert '--disposable' in report['reason']
