"""QA-J01 UI actions and independent reads; no application writes via API."""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlencode

from qa_foundation import assert_expected


class Blocked(RuntimeError):
    """Missing prerequisite or unsuitable photographic fixture, not a product PASS."""


def field(scope, label):
    # Mantine includes the required asterisk in the accessible label.
    return scope.get_by_label(re.compile(r'^' + re.escape(label) + r'\s*\*?$')).and_(scope.locator('input, textarea'))


def get(context, path):
    response = context.request.get(path)
    if not response.ok:
        raise AssertionError(f"GET {path}: HTTP {response.status}")
    return response.json()


def action(page, endpoint, invoke):
    with page.expect_response(lambda r: r.url.split('?')[0].endswith(endpoint) and r.request.method == 'POST') as pending:
        invoke()
    response = pending.value
    if not response.ok:
        raise AssertionError(f"{endpoint}: HTTP {response.status}: {response.text()[:500]}")
    return response.json()


def authenticate(page, password, *, first, recovery=True):
    field(page, 'Account name').fill('qa-owner')
    field(page, 'Password').fill(password)
    if first:
        field(page, 'Confirm password').fill(password)
    action(page, '/api/auth/signup' if first else '/api/auth/login',
           lambda: page.get_by_role('button', name='Create account' if first else 'Sign in', exact=True).click())
    if first and recovery:
        # Normal supported operator choice for data that will be destroyed.
        field(page, 'I understand that my data may not be recoverable without a safety copy.').check()
        action(page, '/api/recovery/acknowledge', lambda: page.get_by_role('button', name='Skip for now', exact=True).click())


def select(page, label, value):
    field(page, label).click()
    page.get_by_role('option', name=value, exact=True).click()


def create_person(page, truth):
    page.get_by_role('tab', name='People', exact=True).click()
    page.get_by_role('button', name='Add without photo', exact=True).click()
    dialog = page.get_by_role('dialog', name='Add person without a photograph')
    for label, value in [('Rank', 'QA fixture'), ('Name', truth['actor']), ('Date', truth['date']),
                         ('Time', '12:00'), ('Place Seen', truth['location']),
                         ('With how many individuals', '0'), ('Event/Occasion', 'QA identity record'), ('Added by', 'QA operator')]:
        field(dialog, label).fill(value)
    select(page, 'Country', 'United States')
    result = action(page, '/api/person-create', lambda: dialog.get_by_role('button', name='Create person', exact=True).click())
    page.get_by_role('button', name=f"Open {truth['actor']}", exact=True).click()
    page.get_by_role('button', name='Add Face', exact=True).wait_for()
    return result['person']['person_id']


def enroll(page, root, row, actor):
    from playwright.sync_api import expect
    page.get_by_role('button', name='Add Face', exact=True).click()
    dialog = page.get_by_role('dialog', name='Recognition References', exact=True)
    field(dialog, 'No reliable Encounter context is available').check()
    draft = action(page, '/api/reference-prepare', lambda: dialog.locator('input[type=file]').set_input_files(str(root / row['file'])))
    if str(draft['quality']).lower() == 'bad':
        raise Blocked('Enrollment photograph has poor quality; choose a suitable verified smoke fixture')
    result = action(page, '/api/reference-confirm', lambda: dialog.get_by_role('button', name='Confirm Reference Only', exact=True).click())
    if len(result.get('created_reference_ids', [])) != 1:
        raise AssertionError('Enrollment did not create exactly one Reference source')
    # The POST response precedes the UI's reference refresh. While that refresh
    # is busy, the normal modal close handler deliberately ignores clicks.
    expect(dialog.get_by_role('button', name='Add Reference Only', exact=True)).to_be_enabled()
    dialog.get_by_role('button', name='Close Recognition References', exact=True).click()
    dialog.wait_for(state='hidden')
    return draft


def recognize_and_finalize(page, context, root, row, truth, person_id, report):
    page.get_by_role('tab', name='Check a photo', exact=True).click()
    inference = action(page, '/api/recognize', lambda: page.locator('input[type=file]').set_input_files(str(root / row['file'])))
    report['inference_executed'] = True
    report['inference'] = inference
    faces = inference['faces']
    if len(faces) != 1:
        raise Blocked(f'Query fixture detected {len(faces)} faces; smoke needs exactly one')
    assert_expected({'counts': {'faces_detected': 1, 'faces_accepted': 1}}, inference['metrics'], 'inference.metrics')
    if not all(key in inference['metrics']['timings_ms'] for key in ('detect_ms', 'embed_ms', 'search_ms')):
        raise AssertionError('Inference omitted detection/embedding/search timings')
    face = faces[0]
    matches = face['matches']
    if face['quality']['status'] == 'bad' or face['decision'] == 'unknown' or not matches or not matches[0]['is_known']:
        raise Blocked('Real inference did not yield a usable known match; recognition limitation / unsuitable fixture')
    assert_expected({'person_id': person_id, 'name': truth['actor']}, matches[0], 'recognition.top_match')
    event = page.get_by_role('dialog', name='Event details', exact=True)
    for label, value in [('Event / occasion', truth['occasion']), ('Date', truth['date']), ('Location', truth['location'])]:
        field(event, label).fill(value)
    select(page, 'Context', 'Ordinary / small')
    event.get_by_role('button', name='Confirm Event', exact=True).click()
    # Proposals, metadata and Reference Only must not create a durable occurrence.
    assert_expected({'events': []}, get(context, '/api/encounters'), 'before_confirmation')
    page.locator('.recognize-action--accept').click()
    field(page, 'With how many individuals').fill('0')
    decision = action(page, '/api/photo-review-decision', lambda: page.get_by_role('button', name='Confirm', exact=True).click())
    assert_expected([{'decision': 'ACCEPT_EXISTING_PERSON', 'person_id': person_id}], decision['faces'], 'operator.faces')
    assert_expected({'events': []}, get(context, '/api/encounters'), 'before_finalization')
    completed = action(page, '/api/photo-review-complete', lambda: page.get_by_role('button', name='Complete Review', exact=True).click())
    return inference, completed


def attest(context, data_dir, model_hashes):
    status = get(context, '/api/models/status')
    if status['runtime'] == 'onnx' and not status['ready']:
        raise Blocked('Real ONNX runtime unavailable; models/status reports not ready')
    profile = get(context, '/api/profile')
    if profile['runtime'] == 'onnx' and not profile['offline_enforcement']['real_model_running']:
        raise Blocked('Real ONNX runtime unavailable; inspect private application.log and model setup')
    assert_expected({'runtime': 'onnx', 'offline_enforcement': {'real_model_running': True, 'outbound_socket_guard': True,
                    'loopback_only': True, 'source_runtime_admitted': True}, 'storage_security': {'database_encrypted': True}}, profile, 'runtime')
    from pathlib import Path
    if Path(profile['data_dir']).resolve() != data_dir.resolve():
        raise AssertionError('Application connected to a different data authority')
    assert_expected({'ready': True, 'runtime': 'onnx'}, status, 'models')
    if not status.get('active_bundle'):
        raise AssertionError('No admitted active model bundle')
    from sentriface.model_bundle import ModelBundleAuthority
    bundle = ModelBundleAuthority(data_dir / 'models').read_bundle(status['active_bundle']['active_bundle_id'])
    assert_expected(bundle.fingerprint, status['active_bundle']['active_fingerprint'], 'models.active_fingerprint')
    for kind in ('detector', 'recognizer'):
        assert_expected({'sha256': model_hashes[kind]}, bundle.components[kind], f'models.{kind}')
    return {'models': profile['models'], 'bundle': bundle.dto(), 'offline_enforcement': profile['offline_enforcement']}


def snapshot(context, truth, person_id, query_hash):
    """Independent truth: one actor, one query, one Encounter; Reference is not presence.

    Opaque IDs are observed handles, never expected counts/identity/date/location.
    Every collection is bounded and must be complete for this tiny fixture.
    """
    people = get(context, '/api/persons')['persons']
    # Check collection without relying on its ordering.
    assert_expected([person_id], sorted(p['person_id'] for p in people), 'People.ids')
    person = get(context, '/api/person?' + urlencode({'person_id': person_id}))
    assert_expected({'person_id': person_id, 'name': truth['actor']}, person['person'], 'People.person')
    events = get(context, '/api/encounters')
    assert_expected(None, events['next_cursor'], 'Events.next_cursor')
    assert_expected(1, len(events['events']), 'Events.count')
    event = events['events'][0]
    oid = event['observation_id']
    common = {'participant_ids': [person_id], 'location': truth['location'], 'occasion': truth['occasion'], 'media_count': 1}
    assert_expected(common, event, 'Events.event')
    assert_expected(truth['date'], event['observed_at'][:10], 'Events.date')
    detail = get(context, '/api/encounter?' + urlencode({'observation_id': oid}))
    assert_expected(common, detail, 'Encounter')
    assert_expected({'date': truth['date'], 'place_seen': truth['location'], 'event_occasion': truth['occasion']}, detail['event_details'], 'Encounter.details')
    if not detail['finalized_at'] or not detail['created_operation_id']:
        raise AssertionError('Encounter missing finalization provenance')
    assert_expected(1, len(detail['media']), 'Encounter.media_count')
    media = detail['media'][0]
    response = context.request.get('/media?' + urlencode({'path': media['media_path']}))
    if not response.ok:
        raise AssertionError(f'Saved media not readable: HTTP {response.status}')
    assert_expected(query_hash, hashlib.sha256(response.body()).hexdigest(), 'Encounter.media_sha256')
    sightings = get(context, '/api/person-sightings?' + urlencode({'person_id': person_id}))['sightings']
    assert_expected(1, len(sightings), 'People.sightings_count')
    sighting = sightings[0]
    assert_expected({'observation_id': oid, 'canonical_person_id': person_id, 'date': truth['date'],
                     'location': truth['location'], 'effective_participant_person_ids': [person_id]}, sighting, 'People.sighting')
    assert_expected([media['media_id']], [m['media_id'] for m in sighting['media']], 'People.media')
    world = get(context, '/api/world-graph?' + urlencode({'version': 2, 'collection': 'MOST_FREQUENTLY_SEEN',
                      'as_of': truth['date'] + 'T23:59:59Z', 'event_limit': 25}))
    assert_expected(False, world['has_more'], 'World.has_more')
    assert_expected(1, len(world['discoveries']), 'World.discoveries_count')
    discovery = world['discoveries'][0]
    assert_expected({'canonical_person_id': person_id, 'count': 1}, discovery, 'World.discovery')
    assert_expected(1, len(discovery['supporting_encounters']), 'World.support_count')
    support = discovery['supporting_encounters'][0]
    assert_expected({'event_id': oid, 'location': truth['location']}, support, 'World.support')
    assert_expected(truth['date'], support['occurred_at'][:10], 'World.support_date')
    # One participant has no pair relationship; occurrence evidence remains in
    # finalized participation and World supporting Encounter, never a fake edge.
    return {'person_id': person_id, 'actor': person['person']['name'], 'observation_id': oid,
            'date': truth['date'], 'location': detail['location'], 'participant_ids': detail['participant_ids'],
            'media_id': media['media_id'], 'media_sha256': query_hash, 'world_count': discovery['count']}
