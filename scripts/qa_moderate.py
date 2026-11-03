"""Moderate histories and read adapters for the existing Foundation runner.

Expected maps are operator scenario inputs. Production correction, canonical and
World functions are used only on the observed side. This is not an event reducer.
All records below live in an existing disposable QA authority; no inference.
"""
import uuid
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlencode, parse_qs, urlsplit

from qa_foundation import assert_expected
import qa_browser as ui


def finalize(store, label, people, date, location):
    # Reuse the legitimate completed-review fixture, padding its vectors for the
    # source app's embedding dimension. These are domain samples, never biometrics.
    from tests import test_identity_corrections as fixtures
    helper = fixtures.IdentityCorrectionTest()
    padded = SimpleNamespace(_pending=lambda s, pid, vector: helper._pending(
        s, pid, vector + (0.0,) * (s.embedding_dim - len(vector))))
    result = fixtures.IdentityCorrectionTest._finalize(padded, store, label, people)
    oid = result['observation_id']
    store.correct_encounter(oid, label + '-metadata', expected_revision=store.get_encounter_read(oid)['revision'],
        event_details=dict(date=date, time='12:00', time_precision='exact', place_seen=location))
    return oid


def correction(store, oid, op, **values):
    return store.correct_encounter(oid, op, expected_revision=store.get_encounter_read(oid)['revision'], **values)


def relation(a, b, disposition):
    return dict(first_person_id=a, second_person_id=b, disposition=disposition)


def store_reader(store):
    """Observed-side adapter to the same read contracts as the live HTTP oracle."""
    from sentriface.api_server import _sighting_record, _person_graph_read_payload, _world_graph_v2_payload, _world_graph_v2_request_from_query
    def read(path):
        url = urlsplit(path)
        q = parse_qs(url.query)
        if url.path == '/api/encounters':
            return store.query_encounters(**({'person_id': q['person_id'][0]} if 'person_id' in q else {}))
        if url.path == '/api/encounter':
            return store.get_encounter_read(q['observation_id'][0])
        if url.path == '/api/person-sightings':
            return dict(sightings=[_sighting_record(x) for x in store.list_person_sightings(q['person_id'][0])])
        if url.path == '/api/person-graph':
            return _person_graph_read_payload(store.get_person_graph_read(q['person_id'][0]))
        if url.path == '/api/world-graph':
            return _world_graph_v2_payload(store.get_world_graph_v2_read(_world_graph_v2_request_from_query(url.query)))
        raise ValueError(path)
    return read


def snapshot(read, people, events, evidence_counts, date):
    """Exact bounded collections, not subsets. Counts/locations/support derive
    only from supplied scenario maps; never from a production participant helper.
    evidence_counts explicitly specifies each unordered pair's independent types.
    """
    observed = {}
    listing = read('/api/encounters')
    assert_expected(None, listing['next_cursor'], 'Moderate.Events.cursor')
    assert_expected(sorted(events), sorted(e['observation_id'] for e in listing['events']), 'Moderate.Events.ids')
    for row in listing['events']:
        assert_expected(events[row['observation_id']], row, 'Moderate.Events.record')
    for oid, expected in events.items():
        detail = read('/api/encounter?' + urlencode(dict(observation_id=oid)))
        assert_expected(expected, detail, 'Moderate.Encounter')
        observed[oid] = {k: detail[k] for k in expected}
        assert_expected(len(set(detail['participant_ids'])), len(detail['participant_ids']), 'Moderate.no_duplicate_participants')
    for pid in people:
        ids = sorted(oid for oid, e in events.items() if pid in e['participant_ids'])
        mentions = sorted(oid for oid, e in events.items() if pid in e.get('mentioned_person_ids', []))
        rows = read('/api/person-sightings?' + urlencode(dict(person_id=pid)))['sightings']
        assert_expected(ids, sorted(s['observation_id'] for s in rows), 'Moderate.Sightings.ids')
        for row in rows:
            event = events[row['observation_id']]
            assert_expected(dict(canonical_person_id=pid, location=event['location'],
                effective_participant_person_ids=event['participant_ids']), row, 'Moderate.Sighting')
            if 'observed_at' in event:
                assert_expected(event['observed_at'], row['observed_at'], 'Moderate.Sighting.time')
        rows = read('/api/encounters?' + urlencode(dict(person_id=pid)))['events']
        assert_expected(sorted(set(ids + mentions)), sorted(r['observation_id'] for r in rows), 'Moderate.Person.Events')
        graph = read('/api/person-graph?' + urlencode(dict(person_id=pid, version=1)))
        assert_expected(pid, graph['root_person_id'], 'Moderate.canonical_root')
        roots = [n for n in graph['nodes'] if n['canonical_person_id'] == pid]
        assert_expected(1, len(roots), 'Moderate.PersonGraph.unique_root')
        summary = roots[0]['summary_intelligence']
        assert_expected(len(ids), summary['observation_count'], 'Moderate.PersonGraph.occurrences')
        expected_locations = sorted((location, sum(events[oid]['location'] == location for oid in ids))
                                    for location in {events[oid]['location'] for oid in ids})
        assert_expected(expected_locations, sorted((r['location'], r['count']) for r in summary['locations']), 'Moderate.PersonGraph.locations')
        expected_edges = {other: counts for pair, counts in evidence_counts.items() if pid in pair for other in pair if other != pid}
        assert_expected(sorted(expected_edges), sorted(e['connected_person_id'] for e in graph['edges']), 'Moderate.PersonGraph.neighbors')
        for edge in graph['edges']:
            assert_expected(sorted(expected_edges[edge['connected_person_id']].items()), sorted(edge['provenance_summary']['evidence_type_counts'].items()), 'Moderate.PersonGraph.evidence')
    # Deliberately bounded history: every event falls on date, every location is
    # distinct or exactly equal (normalization algorithms are not copied here).
    for period in (7, 30, 90):
        for collection in ('MOST_FREQUENTLY_SEEN', 'MOST_RECENTLY_SEEN', 'MULTIPLE_LOCATIONS'):
            params = dict(version=2, view='EXPLORE', evidence_type='CO_OBSERVED', collection=collection,
                          as_of=date + 'T23:59:59Z', discovery_period_days=period)
            world = read('/api/world-graph?' + urlencode(params))
            assert_expected(False, world['has_more'], 'Moderate.World.complete')
            expected_discoveries = {}
            for pid in people:
                ids = sorted(oid for oid, e in events.items() if pid in e['participant_ids'])
                locations = sorted({events[oid]['location'] for oid in ids})
                if ids and (collection != 'MULTIPLE_LOCATIONS' or len(locations) >= 2):
                    expected_discoveries[pid] = (ids, locations)
            assert_expected(sorted(expected_discoveries), sorted(d['canonical_person_id'] for d in world['discoveries']), 'Moderate.World.identities')
            for row in world['discoveries']:
                ids, locations = expected_discoveries[row['canonical_person_id']]
                assert_expected(len(locations) if collection == 'MULTIPLE_LOCATIONS' else len(ids), row['count'], 'Moderate.World.count')
                assert_expected(ids, sorted(e['event_id'] for e in row['supporting_encounters']), 'Moderate.World.proof')
                for support in row['supporting_encounters']:
                    assert_expected(events[support['event_id']]['location'], support['location'], 'Moderate.World.location')
                if collection == 'MULTIPLE_LOCATIONS':
                    assert_expected(locations, sorted(row['locations']), 'Moderate.World.locations')
    evidence_proof = []
    for view in ('CURRENT', 'EXPLORE'):
        world = read('/api/world-graph?' + urlencode(dict(version=2, view=view, collection='RELATIONSHIPS',
            evidence_type='CO_OBSERVED,NOTE_REFERENCE,MANUAL_ASSOCIATION', min_relationship_strength=1,
            as_of=date + 'T23:59:59Z')))
        actual = {tuple(sorted((r['source_person_id'], r['target_person_id']))): r['evidence_type_counts'] for r in world['relationships']}
        assert_expected(len(world['relationships']), len(actual), 'Moderate.World.no_duplicate_edges')
        assert_expected(sorted((pair, sorted(counts.items())) for pair, counts in evidence_counts.items()),
                        sorted((pair, sorted(counts.items())) for pair, counts in actual.items()), 'Moderate.World.relationships')
        for edge in world['relationships']:
            if view == 'CURRENT':
                proof = read('/api/world-graph?' + urlencode(dict(version=2, collection='EVIDENCE', level='EVIDENCE',
                    focus_type='RELATIONSHIP', focus_id=edge['relationship_id'], as_of=date + 'T23:59:59Z')))
                assert_expected(False, proof['has_more'], 'Moderate.evidence.complete')
                rows = proof['evidence']
                assert_expected(edge['evidence_count'], len(rows), 'Moderate.evidence.cardinality')
                pair = tuple(sorted((edge['source_person_id'], edge['target_person_id'])))
                co_ids = sorted(ref['source_entity_id'] for row in rows if row['evidence_type'] == 'CO_OBSERVED' for ref in row['supporting_references'])
                expected_co = sorted(oid for oid, e in events.items() if set(pair).issubset(e['participant_ids'])) if evidence_counts[pair].get('CO_OBSERVED', 0) else []
                assert_expected(expected_co, co_ids, 'Moderate.evidence.occurrence_sources')
                for row in rows:
                    assert_expected(True, row['active'], 'Moderate.evidence.active')
                    assert_expected(list(pair), sorted(row['effective_endpoints']), 'Moderate.evidence.endpoints')
                    if row['evidence_type'] == 'NOTE_REFERENCE':
                        assert_expected('DIRECTED', row['directionality'], 'Moderate.evidence.note_direction')
                        assert_expected(people[:2], row['effective_endpoints'], 'Moderate.evidence.note_owner')
                    assert row['provenance']['created_operation_id'], 'Missing evidence journal provenance'
                evidence_proof.extend(rows)
            count = evidence_counts[tuple(sorted((edge['source_person_id'], edge['target_person_id'])))].get('NOTE_REFERENCE', 0)
            directions = {people[0] + '->' + people[1]: count} if count else {}
            assert_expected(sorted(directions.items()), sorted(edge['note_reference_direction_counts'].items()), 'Moderate.World.note_direction')
        # Scenarios have either no pair, or a single legitimate pair. No invented cluster.
        assert_expected(int(bool(evidence_counts)), world['scope_totals']['clusters'], 'Moderate.World.clusters')
    return dict(events=observed, evidence_proof=evidence_proof, relationships=[dict(pair=list(pair), counts=counts) for pair, counts in sorted(actual.items())],
                verified_projections=['Encounter', 'Events', 'Person Events', 'Sightings', 'Person Graph',
                    'World Current relationships/clusters', 'Explore relationships/clusters',
                    'Frequent/Recent/Multiple Locations 7/30/90 and exact proof'])


def history(store, oid):
    """Read-only audit of immutable provenance; never expected effective truth."""
    with store._connect() as conn:
        result = {table: [dict(r) for r in conn.execute('SELECT * FROM ' + table + ' WHERE observation_id = ?', (oid,))]
                for table in ('observation_face_assignments', 'observation_media')}
        result['original_observation'] = dict(conn.execute('SELECT observation_id, observed_at, location, context, created_operation_id FROM observations WHERE observation_id = ?', (oid,)).fetchone())
        result['original_review_decisions'] = [dict(r) for r in conn.execute('SELECT f.* FROM photo_review_faces f JOIN photo_reviews r ON r.review_id = f.review_id WHERE r.observation_id = ? ORDER BY f.review_id, f.face_id', (oid,))]
        return result


def record(proofs, action, expected, observed):
    proofs.append(dict(original=deepcopy(proofs[-1]['expected']) if proofs else deepcopy(expected),
                       operator_action=action, expected=deepcopy(expected), observed=deepcopy(observed),
                       expected_source='Explicit scenario map authored before the operation; generated IDs are record handles only'))


def execute(args, evidence, report, journey):
    """Live source UI + API, existing encrypted disposable authority and traces."""
    import secrets
    from playwright.sync_api import sync_playwright, expect
    import qa_foundation as qa
    from sentriface.secure_storage import load_or_create_master_key
    from sentriface.storage.sqlite_store import SQLiteIdentityStore
    password = secrets.token_urlsafe(24)
    report.update(browser_errors=[], inference_executed=False, historical_proofs=[],
                  browser_executed=False, domain_verified=False,
                  requested_size=dict(people=2, photos=0, encounters=2 if journey == 'C01' else 1))
    with qa.disposable_data() as data:
        app = qa.Application(data, evidence, runtime='dev')
        context = browser = page = None
        try:
            app.start()
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(executable_path=args.chromium, headless=not args.headed)
                except Exception as exc:
                    raise ui.Blocked('Chromium unavailable: ' + str(exc)) from exc
                try:
                    context, page = qa.browser_context(browser, app.url, report['browser_errors'])
                    ui.authenticate(page, password, first=True)
                    # People are operator UI writes. Completed-review domain
                    # setup is explicit and happens only while the app is stopped.
                    a = ui.create_person(page, dict(actor='Moderate A', date=args.date, location='Moderate Location X'))
                    b = ui.create_person(page, dict(actor='Moderate B', date=args.date, location='Moderate Location Y'))
                    context.tracing.stop(path=str(evidence / 'people.zip')); context.close(); context = None
                    app.stop()
                    s = SQLiteIdentityStore(data / 'sentriface.db', database_key=load_or_create_master_key(data))
                    s.initialize()
                    pa, pb = s.get_person(a), s.get_person(b)
                    e1 = finalize(s, journey + '-first', [pb] if journey == 'C01' else [pa, pb], args.date, 'Moderate Location X')
                    events = {e1: dict(participant_ids=[b] if journey == 'C01' else sorted([a,b]), location='Moderate Location X',
                        media_count=1 if journey == 'C01' else 2, observed_at=args.date + 'T12:00:00')}
                    if journey == 'C01':
                        e2 = finalize(s, journey + '-second', [pa], args.date, 'Moderate Location Y')
                        events[e2] = dict(participant_ids=[a], location='Moderate Location Y', media_count=1, observed_at=args.date + 'T12:00:00')
                    else:
                        e2 = e1
                    report['created_size'] = dict(people=2, photos=0, encounters=2 if journey == 'C01' else 1)
                    raw = history(s, e2)
                    report['original_provenance'] = raw
                    app.start()
                    context, page = qa.browser_context(browser, app.url, report['browser_errors'])
                    ui.authenticate(page, password, first=False, recovery=False)
                    pair = tuple(sorted([a,b]))
                    edges = {} if journey == 'C01' else {pair: {'CO_OBSERVED':1}}
                    def verify(action):
                        actual = snapshot(lambda path: ui.get(context, path), [a,b], events, edges, args.date)
                        record(report['historical_proofs'], action, dict(events=events, evidence=[dict(pair=list(k), counts=v) for k,v in edges.items()]), actual)
                        return actual
                    def post(endpoint, payload):
                        payload = dict(payload, operation_id=str(uuid.uuid4()))
                        response = context.request.post(endpoint, data=payload)
                        if not response.ok:
                            raise AssertionError(f'{endpoint}: HTTP {response.status}: {response.text()[:500]}')
                        return response.json()
                    verify('original')
                    page.get_by_role('tab', name='Events', exact=True).click()
                    page.locator('.encounter-list-row').filter(has_text='Moderate Location Y' if journey == 'C01' else 'Moderate Location X').first.click()
                    if journey == 'C01':
                        # Cancel a fully filled form, then perform the same UI action.
                        before = ui.get(context, '/api/encounter?observation_id=' + e2)
                        for cancel in (True, False):
                            page.get_by_role('button', name='Correct Participants', exact=True).click()
                            ui.select(page, 'Current participant', 'Moderate A')
                            ui.select(page, 'Correct Person', 'Moderate B')
                            dialog = page.get_by_role('dialog', name='Correct Participants')
                            if cancel:
                                dialog.get_by_role('button', name='Cancel', exact=True).click()
                                qa.assert_expected(before, ui.get(context, '/api/encounter?observation_id=' + e2), 'C01.cancel.no_write')
                            else:
                                events[e2]['participant_ids'] = [b]
                                ui.action(page, '/api/encounter-correct', lambda: dialog.get_by_role('button', name='Save correction', exact=True).click())
                                expect(dialog).to_have_count(0)
                        verify('UI FACE_ASSIGNMENT REASSIGN A -> B')
                        # Independent wrong expectation applied to actual persisted reads.
                        wrong = deepcopy(events); wrong[e2]['participant_ids'] = [a]
                        try:
                            snapshot(lambda path: ui.get(context,path), [a,b], wrong, {}, args.date)
                        except AssertionError as exc:
                            report['negative_control'] = dict(outcome='FAIL_EXPECTED', mismatch=str(exc))
                        else:
                            raise AssertionError('Wrong participant truth accepted')
                        page.get_by_role('button', name='Correct Encounter', exact=True).click()
                        dialog = page.get_by_role('dialog', name='Correct Encounter')
                        ui.field(dialog, 'Start time').fill('13:45')
                        ui.field(dialog, 'Location').fill('Moderate Location Y revised')
                        ui.field(dialog, 'Event Notes').fill('Selected @Moderate A; literal @Moderate B')
                        ui.field(dialog, 'Selected Event Note mentions').click()
                        page.get_by_role('option', name='Moderate A', exact=True).click()
                        # Close the multi-select without cancelling the dialog.
                        dialog.get_by_text('Correct the current Event details.', exact=False).click()
                        events[e2].update(location='Moderate Location Y revised', observed_at=args.date + 'T13:45:00', mentioned_person_ids=[a])
                        ui.action(page, '/api/encounter-correct', lambda: dialog.get_by_role('button', name='Save correction', exact=True).click())
                        expect(dialog).to_have_count(0)
                        verify('UI time/location and selected Event mention; no invented A presence')
                        page.get_by_role('button', name='Back to Events', exact=True).click()
                        ui.browse_ordinary(page, 'Moderate B', 'Moderate Location Y revised', b, e2)
                    else:
                        manual = post('/api/person-association', dict(first_person_id=a, second_person_id=b, operation_id='live-manual'))
                        edges[pair]['MANUAL_ASSOCIATION'] = 1
                        verify('manual evidence created')
                        # Exercise actual Relations form, not only its API.
                        for disposition in ('EXCLUDE', 'INCLUDE'):
                            page.get_by_role('button', name='Correct Relations', exact=True).click()
                            ui.select(page, 'Relation Moderate A and Moderate B' if a < b else 'Relation Moderate B and Moderate A', disposition)
                            dialog = page.get_by_role('dialog', name='Correct Relations')
                            if disposition == 'EXCLUDE': del edges[pair]['CO_OBSERVED']
                            else: edges[pair]['CO_OBSERVED'] = 1
                            ui.action(page, '/api/encounter-correct', lambda: dialog.get_by_role('button', name='Save correction', exact=True).click())
                            expect(dialog).to_have_count(0)
                            verify('UI Relations ' + disposition)
                        previous = ''
                        for index, selected in enumerate(([], [b], [])):
                            text = ('Literal @Moderate B', 'Selected @Moderate B', 'Literal @Moderate B again')[index]
                            post('/api/person-notes', dict(person_id=a, notes=text, expected_previous_notes=previous,
                                mentioned_person_ids=selected, operation_id=f'live-note-{index}'))
                            previous = text
                            if selected: edges[pair]['NOTE_REFERENCE'] = 1
                            else: edges[pair].pop('NOTE_REFERENCE', None)
                            verify('Person Note selected=' + str(bool(selected)))
                        post('/api/person-association-remove', dict(evidence_id=manual['evidence_id'], operation_id='live-retire'))
                        del edges[pair]['MANUAL_ASSOCIATION']
                        verify('manual retirement preserves co-observation')
                    report['browser_executed'] = True
                    for phase in ('refresh', 'restart', 'rebuild'):
                        if phase == 'refresh': page.reload()
                        else:
                            context.tracing.stop(path=str(evidence / (phase + '-before.zip'))); context.close(); context = None
                            app.stop()
                            s = SQLiteIdentityStore(data / 'sentriface.db', database_key=load_or_create_master_key(data)); s.initialize()
                            qa.assert_expected(raw, history(s, e2), 'live.immutable_provenance')
                            if phase == 'rebuild': s.rebuild_graph_projection(journey + '-live-rebuild')
                            app.start()
                            context, page = qa.browser_context(browser, app.url, report['browser_errors'])
                            ui.authenticate(page, password, first=False, recovery=False)
                        report['verified'] = verify(phase)
                    report.update(restart_verified=True, rebuild_verified=True, domain_verified=True,
                                  achieved_size=dict(report['requested_size']), independently_verified_size=dict(report['requested_size']), fixture_setup='Deterministic completed reviews; zero genuine photos and zero inference')
                    qa.assert_expected([], report['browser_errors'], 'Moderate.browser_errors')
                    context.tracing.stop(path=str(evidence / 'final.zip'))
                except Exception:
                    try:
                        if page and not page.is_closed(): page.screenshot(path=str(evidence / 'failure.png'))
                        if context: context.tracing.stop(path=str(evidence / 'failure.zip'))
                    except Exception as capture_error:
                        report['evidence_error'] = str(capture_error)
                    raise
                finally:
                    if context: context.close()
                    browser.close()
        finally:
            app.stop()
    report['cleanup_completed'] = True
