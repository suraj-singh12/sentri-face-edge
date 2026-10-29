"""QA machinery tests. Hand-authored read DTOs and browser mechanisms are NOT biometric acceptance."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_foundation as qa
import qa_browser as ui


def test_model_inputs_require_authorization_and_hash(tmp_path):
    path = tmp_path / 'models.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='responsibility'):
        qa.model_inputs(path)
    blob = tmp_path / 'local.onnx'
    blob.write_bytes(b'not a model; checksum mechanism only')
    config = dict(accept_model_responsibility=True, usage_basis='noncommercial-research', authorized_by='QA operator',
                  detector_source='local.onnx', detector_sha256='0' * 64)
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='detector SHA-256 mismatch'):
        qa.model_inputs(path)


@pytest.mark.parametrize('error,expected', [(ui.Blocked('missing browser'), 'BLOCKED'), (RuntimeError('browser crashed'), 'FAIL')])
def test_execution_errors_never_pass(tmp_path, monkeypatch, capsys, error, expected):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda *a, **k: 'revision' if 'rev-parse' in a[0] else '')
    monkeypatch.setattr(qa, 'verified_pair', lambda *a: [{'sha256': 'a'}, {'sha256': 'b'}])
    monkeypatch.setattr(qa, 'model_inputs', lambda *a: {'detector_sha256': 'd', 'recognizer_sha256': 'r', 'detector_source': 'det.onnx', 'recognizer_source': 'rec.onnx'})
    def fail(*args):
        raise error
    monkeypatch.setattr(qa, 'execute', fail)
    monkeypatch.setattr(qa, 'require_browser', lambda: None)
    assert qa.main(['--disposable']) == (2 if expected == 'BLOCKED' else 1)
    result = json.loads(capsys.readouterr().out)
    assert result['outcome'] == expected
    assert (Path(result['evidence']) / 'junit.xml').exists()


def test_no_disposable_selection_is_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda *a, **k: '')
    assert qa.main([]) == 2
    assert '--disposable' in json.loads(capsys.readouterr().out)['reason']


class Response:
    ok, status = True, 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload
    def body(self):
        return b'original-query-content'


def read_fixture():
    """Independent hand-authored domain truth, not SentriFace storage builders."""
    truth = dict(actor='Known Actor', date='2026-10-29', location='London', occasion='QA-J01 smoke')
    event = dict(observation_id='e1', participant_ids=['p1'], location='London', occasion='QA-J01 smoke', media_count=1, observed_at='2026-10-29T12:00:00Z')
    return truth, {
        '/api/persons': {'persons': [{'person_id': 'p1'}]},
        '/api/person': {'person': {'person_id': 'p1', 'name': 'Known Actor'}},
        '/api/encounters': {'events': [event], 'next_cursor': None},
        '/api/encounter': dict(event, event_details={'date': truth['date'], 'place_seen': 'London', 'event_occasion': truth['occasion']},
            finalized_at='2026-10-29T12:01:00Z', created_operation_id='op1', media=[{'media_id': 'm1', 'media_path': '/local/query.jpg'}]),
        '/api/person-sightings': {'sightings': [{'observation_id': 'e1', 'canonical_person_id': 'p1', 'date': truth['date'], 'location': 'London',
             'effective_participant_person_ids': ['p1'], 'media': [{'media_id': 'm1'}]}]},
        '/api/world-graph': {'has_more': False, 'discoveries': [{'canonical_person_id': 'p1', 'count': 1, 'supporting_encounters': [{'event_id': 'e1', 'location': 'London', 'occurred_at': event['observed_at']}]}]},
        '/media': {},
    }


def context_for(payloads):
    return SimpleNamespace(request=SimpleNamespace(get=lambda path: Response(payloads[path.split('?')[0]])))


def test_independent_reads_and_wrong_truth():
    truth, payloads = read_fixture()
    context = context_for(payloads)
    digest = __import__('hashlib').sha256(b'original-query-content').hexdigest()
    assert ui.snapshot(context, truth, 'p1', digest)['world_count'] == 1
    with pytest.raises(AssertionError, match="Events.event.location: expected 'Wrong', actual 'London'"):
        ui.snapshot(context, dict(truth, location='Wrong'), 'p1', digest)
    payloads['/api/encounters']['events'] *= 2
    with pytest.raises(AssertionError, match='Events.count'):
        ui.snapshot(context, truth, 'p1', digest)


@pytest.mark.parametrize('view', ['People', 'World', 'media'])
def test_cross_feature_mismatches_are_rejected(view):
    truth, payloads = read_fixture()
    if view == 'People':
        payloads['/api/person-sightings']['sightings'][0]['effective_participant_person_ids'] = ['wrong']
    elif view == 'World':
        payloads['/api/world-graph']['discoveries'][0]['count'] = 2
    digest = 'wrong' if view == 'media' else __import__('hashlib').sha256(b'original-query-content').hexdigest()
    with pytest.raises(AssertionError, match=view if view != 'media' else 'media_sha256'):
        ui.snapshot(context_for(payloads), truth, 'p1', digest)


@pytest.mark.skipif(not __import__('os').environ.get('SENTRIFACE_QA_CHROMIUM'), reason='Opt-in actual browser mechanism check; not biometric acceptance')
def test_actual_browser_person_creation_and_cleanup(tmp_path):
    """Actual frontend + API with existing dev runtime; NO inference or enrollment."""
    import os
    import threading
    from playwright.sync_api import sync_playwright
    from sentriface.api_server import create_server
    with qa.disposable_data() as data:
        server = create_server(port=0, data_dir=data, runtime='dev')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.environ['SENTRIFACE_QA_CHROMIUM'])
                context, page = qa.browser_context(browser, f'http://127.0.0.1:{server.server_port}')
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda e: errors.append(e.text) if e.type == 'error' else None)
                page.reload()
                try:
                    ui.authenticate(page, 'Qa-mechanism-password-123', first=True)
                except Exception:
                    page.screenshot(path='/tmp/qa-mechanism-failure.png')
                    print('Browser errors', errors, 'BODY', page.locator('body').inner_text())
                    raise
                pid = ui.create_person(page, dict(actor='QA mechanism person', date='2026-10-29', location='QA London'))
                people = ui.get(context, '/api/persons')['persons']
                assert [p['person_id'] for p in people] == [pid]
                assert ui.get(context, '/api/encounters')['events'] == []
                # Real dev runtime must fail ONNX attestation.
                with pytest.raises(AssertionError, match='runtime'):
                    ui.attest(context, data, {})
                context.close(); browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=10)
    assert not data.exists()


@pytest.mark.skipif(not __import__('os').environ.get('SENTRIFACE_QA_CHROMIUM'), reason='Opt-in source/browser prerequisites test; NO inference')
def test_actual_source_launch_restart_missing_models_is_blocked(tmp_path):
    import os
    from playwright.sync_api import sync_playwright
    with qa.disposable_data() as data:
        app = qa.Application(data, tmp_path)
        try:
            for first in (True, False):
                app.start()
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ['SENTRIFACE_QA_CHROMIUM'])
                    try:
                        context, page = qa.browser_context(browser, app.url)
                        ui.authenticate(page, 'Qa-source-password-123', first=first, recovery=False)
                        with pytest.raises(ui.Blocked, match='Real ONNX runtime unavailable'):
                            ui.attest(context, data, {})
                        context.close()
                    finally:
                        browser.close()
                app.stop()
        finally:
            app.stop()
    assert not data.exists()


def test_exception_cleans_disposable_data():
    with pytest.raises(RuntimeError, match='injected failure'):
        with qa.disposable_data() as data:
            (data / 'read-only-model').write_bytes(b'QA cleanup only')
            (data / 'read-only-model').chmod(0o444)
            raise RuntimeError('injected failure')
    assert not data.exists()


def test_operator_local_fixture_selection_and_provenance(tmp_path):
    import cv2
    import numpy as np
    # Decoder/manifest mechanism only. These bytes are NOT face fixtures.
    (tmp_path / 'actor').mkdir()
    rows = []
    for split, value in [('enrollment', 0), ('query', 200)]:
        path = tmp_path / 'actor' / (split + '.jpg')
        path.write_bytes(cv2.imencode('.jpg', np.full((120, 120, 3), value, dtype=np.uint8))[1].tobytes())
        rows.append(dict(actor='Known Actor', file=f'actor/{split}.jpg', sha256=qa.sha256(path), reviewed=True,
                         reviewer='QA mechanism', review_notes='Test metadata only', author='QA test', license='Test generated bytes',
                         source_record='Local test source; no identity claim', split=split, reference_no_context=True))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'version': 1, 'photos': rows}))
    pair = qa.verified_pair(tmp_path, 'Known Actor')
    assert [r['split'] for r in pair] == ['enrollment', 'query']
    del rows[0]['license']
    manifest.write_text(json.dumps({'version': 1, 'photos': rows}))
    with pytest.raises(ValueError, match='license, author'):
        qa.verified_pair(tmp_path, 'Known Actor')


def test_missing_local_archive_reports_actionable_error(tmp_path):
    import fetch_marvel_photos as photos
    with pytest.raises(ValueError, match='operator archive'):
        photos.download({'file': 'actor/missing.jpg'}, tmp_path, 2)


def test_missing_execution_proofs_cannot_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda *a, **k: '')
    monkeypatch.setattr(qa, 'verified_pair', lambda *a: [{'sha256': 'a'}, {'sha256': 'b'}])
    monkeypatch.setattr(qa, 'model_inputs', lambda *a: {'detector_sha256': 'd', 'recognizer_sha256': 'r', 'detector_source': 'det.onnx', 'recognizer_source': 'rec.onnx'})
    monkeypatch.setattr(qa, 'require_browser', lambda: None)
    monkeypatch.setattr(qa, 'execute', lambda *a: None)
    assert qa.main(['--disposable']) == 1
    assert json.loads(capsys.readouterr().out)['outcome'] == 'FAIL'
