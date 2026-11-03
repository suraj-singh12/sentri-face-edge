"""Offline QA primitives. No application/biometric acceptance is implied by these checks."""
from __future__ import annotations
import argparse
import platform
import hashlib
import json
import subprocess
import tempfile
import os
import socket
import sys
import time
import secrets
import uuid
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT)) # Existing deterministic fixtures are imported by J02.


def assert_expected(expected, actual, path="result"):
    """Compare independently supplied truth; never calculate truth from actual output.

    Objects select fields; arrays are exact and ordered. Missing and extra list
    entries fail. Domain adapters must supply full participant/evidence lists.
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"{path}: expected object, actual {type(actual).__name__}")
        for key, value in expected.items():
            if key not in actual:
                raise AssertionError(f"{path}.{key}: missing; expected {value!r}")
            assert_expected(value, actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise AssertionError(f"{path}: expected {expected!r}, actual {actual!r}")
        for index, value in enumerate(expected):
            assert_expected(value, actual[index], f"{path}[{index}]")
    elif type(expected) is not type(actual) or expected != actual:
        raise AssertionError(f"{path}: expected {expected!r}, actual {actual!r}")


@contextmanager
def disposable_data():
    # No caller-selected reset target: cannot delete a user's existing authority.
    root = None
    try:
        with tempfile.TemporaryDirectory(prefix="sentriface-qa-", ignore_cleanup_errors=False) as directory:
            root = Path(directory)
            root.chmod(0o700)
            yield root
    finally:
        if root is not None and not root.exists() and sys.platform != 'linux':
            cleanup_qa_credentials(root)


def verified_pair(root: Path, actor: str):
    from fetch_marvel_photos import load_manifest, photo_path, image_valid
    manifest = load_manifest(root / "manifest.json")
    rows = []
    for row in manifest["photos"]:
        if row.get("actor") != actor or row.get("reviewed") is not True:
            continue
        if not row.get("reviewer") or not row.get("review_notes"):
            raise ValueError("Verified labels require reviewer and review notes")
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("license", "author")) or not (row.get("page") or row.get("source_record")):
            raise ValueError("Verified photos require license, author and source page or operator permission record")
        if row.get("split") == "enrollment" and row.get("reference_no_context") is not True:
            raise ValueError("Enrollment requires a reviewed cropped Reference with no reliable Encounter context")
        content = photo_path(root, row["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != row.get("sha256") or not image_valid(content, Path(row["file"]).suffix):
            raise ValueError("Verified photograph is invalid or changed")
        rows.append(row)
    enrollment = [r for r in rows if r.get("split") == "enrollment"]
    queries = [r for r in rows if r.get("split") == "query"]
    if not enrollment or not queries or enrollment[0]["sha256"] == queries[0]["sha256"]:
        raise ValueError("Need distinct visually verified enrollment and query photographs")
    return enrollment[0], queries[0]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def model_inputs(path):
    """Read explicit operator declarations, never infer model-use authorization."""
    if path is None:
        raise ValueError('Supply --models-config with authorized local model paths, hashes and usage declaration')
    config = json.loads(path.read_text(encoding='utf8'))
    if config.get('accept_model_responsibility') is not True:
        raise ValueError('Explicit accept_model_responsibility: true required')
    for field in ('usage_basis', 'authorized_by'):
        if not config.get(field):
            raise ValueError(f'Model declaration missing {field}')
    for kind in ('detector', 'recognizer', 'calibration'):
        field = kind + '_source'
        if kind == 'calibration' and not config.get(field):
            continue
        source = Path(config[field]).expanduser()
        source = source if source.is_absolute() else path.parent / source
        config[field] = str(source.resolve(strict=True))
        if sha256(source) != config.get(kind + '_sha256'):
            raise ValueError(f'{kind} SHA-256 mismatch')
    return config


def source_environment():
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(ROOT / 'src') + os.pathsep + environment.get('PYTHONPATH', '')
    return environment


def admit_models(config, data_dir, log):
    command = [sys.executable, '-m', 'sentriface.model_setup', '--models-dir', str(data_dir / 'models'), '--accept-model-responsibility']
    fields = ('detector_source', 'detector_sha256', 'recognizer_source', 'recognizer_sha256',
              'calibration_source', 'calibration_sha256', 'usage_basis', 'authorized_by',
              'organization', 'licensor', 'license_reference', 'license_name')
    for field in fields:
        if config.get(field):
            command += ['--' + field.replace('_', '-'), str(config[field])]
    with log.open('wb') as stream:
        result = subprocess.run(command, cwd=ROOT, env=source_environment(), stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        from qa_browser import Blocked
        raise Blocked('Normal model admission refused inputs; see private model-admission.log')


class Application:
    """Existing source entry point, fresh authority, loopback only, normal auth."""
    def __init__(self, data_dir, evidence, runtime="onnx"):
        self.runtime = runtime
        self.data_dir, self.evidence, self.process, self.stream = data_dir, evidence, None, None
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'

    def start(self):
        self.stream = (self.evidence / 'application.log').open('ab')
        self.process = subprocess.Popen([sys.executable, '-m', 'sentriface.ui', '--runtime', self.runtime,
            *(['--allow-unpackaged-source-onnx'] if self.runtime == 'onnx' else []), '--data-dir', str(self.data_dir), '--port', str(self.port)],
            cwd=ROOT, env=source_environment(), stdout=self.stream, stderr=subprocess.STDOUT)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) # Loopback only.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Source application exited; see private application.log')
            try:
                with opener.open(self.url, timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError('Source application did not become ready within 90s')

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                if os.name == 'nt':
                    subprocess.run([sys.executable, '-m', 'sentriface.ui', '--request-shutdown', '--data-dir', str(self.data_dir)], cwd=ROOT, env=source_environment(), timeout=15, capture_output=True)
                else:
                    import signal
                    self.process.send_signal(signal.SIGINT)
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
            self.process = None
        if self.stream:
            self.stream.close()
            self.stream = None


def browser_context(browser, url, errors=None):
    context = browser.new_context(base_url=url, viewport={'width': 1440, 'height': 1000})
    context.set_default_timeout(30000)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    if errors is not None:
        page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    token = page.locator('meta[name="sentriface-session-token"]').get_attribute('content')
    if not token:
        raise AssertionError('Source frontend missing session authorization')
    context.set_extra_http_headers({'X-SentriFace-Session': token})
    return context, page


def execute(args, config, pair, evidence, report, after_verified=None):
    from playwright.sync_api import sync_playwright
    import qa_browser as ui
    truth = {'actor': args.actor, 'date': args.date, 'location': args.location, 'occasion': 'QA-J01 smoke'}
    report['expected'] = dict(truth, people=1, encounters=1, occurrence_media=1, world_count=1)
    password = secrets.token_urlsafe(24) # Local ephemeral owner; never ordinary credentials.
    with disposable_data() as data_dir:
        admit_models(config, data_dir, evidence / 'model-admission.log')
        app = Application(data_dir, evidence)
        context = page = browser = None
        report['browser_errors'] = []
        try:
            app.start()
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(executable_path=args.chromium, headless=not args.headed)
                except Exception as exc:
                    raise ui.Blocked(f'Chromium unavailable: {exc}') from exc
                try:
                    context, page = browser_context(browser, app.url, report['browser_errors'])
                    report['step'] = 'owner signup and recovery acknowledgment'
                    ui.authenticate(page, password, first=True)
                    report['runtime'] = ui.attest(context, data_dir, report['model_hashes'])
                    report['step'] = 'create Person through UI'
                    person_id = ui.create_person(page, truth)
                    report['step'] = 'enroll Reference through UI'
                    ui.enroll(page, args.fixtures, pair[0], args.actor)
                    report['reference_verified'] = ui.reference_snapshot(context, person_id)
                    assert_expected({'events': []}, ui.get(context, '/api/encounters'), 'ReferenceOnly.no_presence')
                    assert_expected({'sightings': []}, ui.get(context, '/api/person-sightings?person_id=' + person_id), 'ReferenceOnly.no_sighting')
                    assert_expected({'discoveries': []}, ui.get(context, '/api/world-graph?version=2&collection=MOST_RECENTLY_SEEN'), 'ReferenceOnly.no_world_presence')
                    report['step'] = 'recognize, operator confirmation and finalize'
                    inference, _ = ui.recognize_and_finalize(page, context, args.fixtures, pair[1], truth, person_id, report)
                    report['inference_executed'] = True
                    report['inference'] = inference
                    report['step'] = 'independent People/Events/World verification'
                    before = ui.snapshot(context, truth, person_id, pair[1]['sha256'])
                    # Deliberately wrong fixture truth, applied only to the verifier.
                    wrong = dict(truth, location=truth['location'] + ' (deliberately incorrect)')
                    try:
                        ui.snapshot(context, wrong, person_id, pair[1]['sha256'])
                    except AssertionError as exc:
                        if 'Events.event.location:' not in str(exc):
                            raise
                        report['negative_control'] = {'outcome': 'FAIL_EXPECTED', 'mismatch': str(exc)}
                    else:
                        raise AssertionError('Verifier accepted deliberately incorrect location')
                    ui.single_person_graph(context, person_id)
                    ui.browse_ordinary(page, truth['actor'], truth['location'], person_id, before['observation_id'])
                    page.reload()
                    ui.snapshot(context, truth, person_id, pair[1]['sha256'])
                    page.screenshot(path=str(evidence / 'finalized.png'))
                    context.tracing.stop(path=str(evidence / 'journey.zip'))
                    context.close(); context = None
                    app.stop()
                    report['step'] = 'restart and persistence verification'
                    app.start()
                    context, page = browser_context(browser, app.url, report['browser_errors'])
                    ui.authenticate(page, password, first=False)
                    ui.attest(context, data_dir, report['model_hashes'])
                    after = ui.snapshot(context, truth, person_id, pair[1]['sha256'])
                    assert_expected(before, after, 'restart')
                    ui.reference_snapshot(context, person_id)
                    ui.single_person_graph(context, person_id)
                    report['verified'] = after
                    if after_verified is not None:
                        corrected_truth = after_verified(context, page, truth, person_id, pair[1]['sha256'], report)
                        context.tracing.stop(path=str(evidence / 'correction.zip'))
                        context.close(); context = None
                        app.stop(); app.start()
                        context, page = browser_context(browser, app.url, report['browser_errors'])
                        ui.authenticate(page, password, first=False)
                        report['correction']['after_restart'] = ui.snapshot(context, corrected_truth, person_id, pair[1]['sha256'])
                        assert_expected(report['correction']['observed'], report['correction']['after_restart'], 'Moderate.genuine.restart')
                    report['restart_verified'] = True
                    if report['browser_errors']:
                        raise AssertionError(f"Browser page errors: {report['browser_errors']}")
                    context.tracing.stop(path=str(evidence / 'restart.zip'))
                except Exception:
                    try:
                        if page and not page.is_closed():
                            page.screenshot(path=str(evidence / 'failure.png'))
                        if context:
                            context.tracing.stop(path=str(evidence / 'failure.zip'))
                    except Exception as capture_error:
                        report['evidence_error'] = str(capture_error)
                    raise
                finally:
                    if context:
                        context.close()
                    if browser:
                        browser.close()
        finally:
            app.stop()
    # TemporaryDirectory cleanup completed before returning success.
    report['cleanup_completed'] = True


def execute_ordinary(args, evidence, report):
    """J02 uses dev source mode without calling its synthetic detector/embedder.

    People writes are UI actions. Two media-free occurrences are deterministic
    domain fixture setup, using the existing World fixture utility while stopped.
    They are never labeled photographic or biometric evidence.
    """
    from playwright.sync_api import sync_playwright, expect
    import qa_browser as ui
    from sentriface.secure_storage import load_or_create_master_key
    from sentriface.storage.sqlite_store import SQLiteIdentityStore
    from tests.test_world_graph_v2 import WorldGraphV2Test
    password = secrets.token_urlsafe(24)
    report.update(browser_errors=[], inference_executed=False, fixture_setup='Existing World domain fixture; two media-free occurrences; no inference')
    with disposable_data() as data:
        app = Application(data, evidence, runtime='dev')
        context = browser = page = None
        try:
            app.start()
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(executable_path=args.chromium, headless=not args.headed)
                except Exception as exc:
                    raise ui.Blocked(f'Chromium unavailable: {exc}') from exc
                try:
                    context, page = browser_context(browser, app.url, report['browser_errors'])
                    ui.authenticate(page, password, first=True)
                    first = ui.create_person(page, dict(actor='Normal Alpha', date=args.date, location=args.location))
                    ui.edit_person(page, 'Cancelled identity', cancel=True)
                    assert_expected('Normal Alpha', ui.get(context, '/api/person?person_id=' + first)['person']['name'], 'J02.cancel_edit')
                    ui.edit_person(page, 'Normal Alpha Edited')
                    second = ui.create_person(page, dict(actor='Normal Beta', date=args.date, location=args.location))
                    names = {first: 'Normal Alpha Edited', second: 'Normal Beta'}
                    # Session lock/unlock in the available UI is Sign out/Sign in.
                    page.get_by_role('button', name='Open account menu').click()
                    ui.action(page, '/api/auth/logout', lambda: page.get_by_role('menuitem', name='Sign out').click())
                    rejected = context.request.post('/api/person-update', data={'person_id': first, 'name': 'Unauthorized'})
                    assert_expected(401, rejected.status, 'J02.unauthorized_write')
                    ui.authenticate(page, password, first=False, recovery=False)
                    context.tracing.stop(path=str(evidence / 'people.zip'))
                    context.close(); context = None
                    app.stop()
                    # Exact disposable authority only. Existing domain helper; no SQL writes.
                    store = SQLiteIdentityStore(data / 'sentriface.db', database_key=load_or_create_master_key(data))
                    store.initialize()
                    expected = {}
                    for index, pid in enumerate(names):
                        location = f'{args.location} {index + 1}'
                        oid = WorldGraphV2Test()._observe(store, f'normal-{index}', [pid],
                            observed_at=args.date + 'T12:00:00+00:00', location=location)
                        expected[oid] = dict(participant_ids=[pid], location=location, media_count=0)
                    report['requested_size'] = dict(people=2, photos=0, encounters=2)
                    app.start()
                    for cycle in ('fixture', 'refresh', 'restart'):
                        if cycle == 'restart':
                            context.tracing.stop(path=str(evidence / 'navigation.zip'))
                            context.close(); context = None
                            app.stop(); app.start()
                        if cycle != 'refresh':
                            context, page = browser_context(browser, app.url, report['browser_errors'])
                            ui.authenticate(page, password, first=False, recovery=False)
                        else:
                            page.reload()
                        before = ui.ordinary_snapshot(context, names, expected, args.date)
                        page.get_by_role('tab', name='People', exact=True).click()
                        search = page.get_by_placeholder('Search by name, ID or tag...')
                        search.fill('no-such-normal-person')
                        expect(page.get_by_role('button', name='Open Normal Beta', exact=True)).to_have_count(0)
                        search.fill('Normal Alpha Edited')
                        page.get_by_role('button', name='Open Normal Alpha Edited', exact=True).click()
                        ui.browse_ordinary(page, names[first], args.location + ' 1', first, next(oid for oid, e in expected.items() if e['participant_ids'] == [first]))
                        after = ui.ordinary_snapshot(context, names, expected, args.date)
                        assert_expected(before, after, 'J02.read_only')
                    report['verified'] = after
                    report['achieved_size'] = dict(report['requested_size'])
                    report['restart_verified'] = True
                    assert_expected([], report['browser_errors'], 'J02.browser_errors')
                    context.tracing.stop(path=str(evidence / 'restart.zip'))
                except Exception:
                    try:
                        if page and not page.is_closed():
                            page.screenshot(path=str(evidence / 'failure.png'))
                        if context:
                            context.tracing.stop(path=str(evidence / 'failure.zip'))
                    except Exception as capture_error:
                        report['evidence_error'] = str(capture_error)
                    raise
                finally:
                    if context:
                        context.close()
                    browser.close()
        finally:
            app.stop()
    report['cleanup_completed'] = True


def normal_status(states):
    if 'FAIL' in states:
        return 'FAIL'
    if states and all(s == 'PASS' for s in states):
        return 'PASS'
    return 'PARTIAL' if 'PASS' in states else 'NOT RUN'


def normal_campaign(args, evidence, report, started):
    """Extend the Foundation report, not a second runner/reporting format.

    Registry links select focused tests. Only completed testcase results and
    journey proofs count; declaration, collection and skips never become PASS.
    """
    import qa_browser as ui
    moderate = getattr(args, 'phase', 'Normal') == 'Moderate'
    registry_key = 'moderate_acceptance' if moderate else 'normal_acceptance'
    registry = json.loads((ROOT / 'tests/qa_coverage.json').read_text())[registry_key]
    selected = registry if args.test in ('Normal', 'Moderate') else [r for r in registry if r['id'] == args.test]
    report.update(runs=[], acceptance=[], inference_executed=False, model_hashes={}, dataset_scope='Per fresh authority; see runs and datasets, never cumulative biometric volume')
    report.pop('requested_size', None)
    report.pop('achieved_size', None)
    focused = {}
    if args.test == 'Normal' or moderate:
        targets = sorted({target for row in selected for target in row.get('tests', [])})
        with (evidence / 'focused.log').open('wb') as stream:
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *targets,
                '--junitxml=' + str(evidence / 'focused.xml')], cwd=ROOT, env=source_environment(),
                stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        result_states = {}
        for case in ET.parse(evidence / 'focused.xml').iter('testcase'):
            for target in targets:
                parts = target.split('::')
                classname = parts[0][:-3].replace('/', '.') + ('.' + '.'.join(parts[1:-1]) if len(parts) > 2 else '')
                if case.get('classname') == classname and case.get('name', '').split('[')[0] == parts[-1]:
                    state = 'FAIL' if any(case.find(t) is not None for t in ('failure', 'error')) else 'NOT RUN' if case.find('skipped') is not None else 'PASS'
                    result_states.setdefault(target, []).append(state)
        for target, states in result_states.items():
            focused[target] = 'FAIL' if 'FAIL' in states else 'PASS' if all(s == 'PASS' for s in states) else 'NOT RUN'
        report['focused_exit_code'] = result.returncode
        report['focused_results'] = focused
        report['datasets'] = [json.loads(prop.get('value')) for prop in ET.parse(evidence / 'focused.xml').iter('property') if prop.get('name') == 'dataset']
    journey_ids = sorted({j for row in selected for j in row.get('journeys', [])}) if moderate else (['QA-J02', 'QA-J01'] if args.test == 'Normal' else ['QA-J02'])
    for journey in journey_ids:
        run = dict(test_id=journey, outcome='BLOCKED', inference_executed=False, model_hashes={})
        report['runs'].append(run)
        directory = evidence / journey
        directory.mkdir(mode=0o700)
        start = time.monotonic()
        try:
            try:
                require_browser()
            except ImportError as exc:
                raise ui.Blocked('Install the optional Playwright QA dependency') from exc
            if moderate:
                import qa_moderate
                qa_moderate.execute(args, directory, run, journey)
                assert_expected({'browser_executed': True, 'domain_verified': True, 'rebuild_verified': True}, run, 'Moderate.proofs')
            elif journey == 'QA-J01':
                try:
                    pair = verified_pair(args.fixtures, args.actor)
                    config = model_inputs(args.models_config)
                except (OSError, ValueError, KeyError) as exc:
                    raise ui.Blocked(str(exc)) from exc
                run['model_hashes'] = {k: config[k + '_sha256'] for k in ('detector', 'recognizer')}
                execute(args, config, pair, directory, run)
                assert_expected({'reference_verified': {'owner': run['verified']['person_id'], 'eligible': True, 'count': 1},
                    'inference_executed': True, 'negative_control': {'outcome': 'FAIL_EXPECTED'}}, run, 'J01.proofs')
            else:
                execute_ordinary(args, directory, run)
            assert_expected({'restart_verified': True, 'cleanup_completed': True, 'browser_errors': []}, run, 'journey.proofs')
            run['outcome'] = 'PASS'
            if journey == 'QA-J01':
                run['requested_size'] = dict(people=1, photos=2, encounters=1)
                run['achieved_size'] = dict(run['requested_size'])
                run['created_size'] = dict(run['requested_size'])
                run['independently_verified_size'] = dict(run['requested_size'])
        except ui.Blocked as exc:
            run.update(outcome='BLOCKED', reason=str(exc), category='environment blocker')
        except Exception as exc:
            run.update(outcome='FAIL', reason=f'{type(exc).__name__}: {exc}',
                       category='uncertain observation; investigate private evidence')
        run['seconds'] = round(time.monotonic() - start, 3)
        if not run['inference_executed']:
            run['model_hashes'] = {}
    if moderate and args.test == 'Moderate':
        # Supplemental genuine saved-Encounter correction, never historical #19 proof.
        run = dict(test_id='Moderate-biometric', outcome='BLOCKED', inference_executed=False, model_hashes={})
        report['runs'].append(run)
        directory = evidence / 'biometric'; directory.mkdir(mode=0o700)
        try:
            try:
                pair = verified_pair(args.fixtures, args.actor)
                config = model_inputs(args.models_config)
                require_browser()
            except (OSError, ValueError, KeyError, ImportError) as exc:
                raise ui.Blocked(str(exc)) from exc
            run['model_hashes'] = {k: config[k + '_sha256'] for k in ('detector', 'recognizer')}
            def correct_saved(context, page, truth, pid, query_hash, run):
                before = ui.get(context, '/api/encounters')['events'][0]
                detail = ui.get(context, '/api/encounter?observation_id=' + before['observation_id'])
                expected = dict(truth, location='Moderate corrected genuine location')
                response = context.request.post('/api/encounter-correct', data=dict(observation_id=before['observation_id'],
                    expected_revision=detail['revision'], operation_id=str(uuid.uuid4()), event_details=dict(place_seen=expected['location'])))
                if not response.ok:
                    raise AssertionError('Genuine saved-Encounter correction rejected: ' + str(response.status))
                run['correction'] = dict(original=before, expected=expected, observed=ui.snapshot(context, expected, pid, query_hash))
                return expected
            execute(args, config, pair, directory, run, after_verified=correct_saved)
            assert_expected({'inference_executed': True, 'restart_verified': True, 'cleanup_completed': True, 'browser_errors': []}, run, 'Moderate.biometric.proofs')
            run['outcome'] = 'PASS'
            run['requested_size'] = dict(people=1, photos=2, encounters=1)
            run['achieved_size'] = dict(run['requested_size'])
            run['created_size'] = dict(run['requested_size'])
            run['independently_verified_size'] = dict(run['requested_size'])
        except ui.Blocked as exc:
            run.update(outcome='BLOCKED', reason=str(exc), category='environment blocker')
        except Exception as exc:
            run.update(outcome='FAIL', reason=str(exc), category='uncertain observation; investigate private evidence')
        if not run['inference_executed']: run['model_hashes'] = {}
    journeys = {r['test_id']: r for r in report['runs']}
    for row in registry:
        evidence_states = [focused.get(t, 'NOT RUN') for t in row.get('tests', [])]
        evidence_states += [journeys.get(j, {}).get('outcome', 'NOT RUN') for j in row.get('journeys', [])]
        status = normal_status(evidence_states)
        report['acceptance'].append(dict(id=row['id'], status=status, tests={t: focused.get(t, 'NOT RUN') for t in row.get('tests', [])},
            journeys={j: journeys.get(j, {}).get('outcome', 'NOT RUN') for j in row.get('journeys', [])}, limitation=row.get('limitation', '')))
    report['inference_executed'] = any(r['inference_executed'] for r in report['runs'])
    states = [r['status'] for r in report['acceptance']]
    report['outcome'] = 'FAIL' if 'FAIL' in states or report.get('focused_exit_code', 0) else 'PASS' if all(s == 'PASS' for s in states) else 'BLOCKED'
    if args.test == 'QA-J02':
        report['outcome'] = journeys['QA-J02']['outcome']
    if moderate:
        report['historical_proofs'] = [dict(test=case.get('classname') + '::' + case.get('name'),
            **{p.get('name'): json.loads(p.get('value')) for p in case.iter('property') if p.get('name') in ('historical_proofs', 'provenance')})
            for case in ET.parse(evidence / 'focused.xml').iter('testcase') if any(p.get('name') == 'historical_proofs' for p in case.iter('property'))]
        report['outcome'] = 'FAIL' if report['outcome'] == 'FAIL' or any(r['outcome'] == 'FAIL' for r in report['runs']) else report['outcome']
        report['biometric_status'] = journeys.get('Moderate-biometric', {}).get('outcome', 'NOT RUN')
        for row in report['acceptance']:
            row.update(commit=report.get('commit'), environment=report.get('platform'), evidence=str(evidence),
                       domain_verification=bool(row['tests']) and all(v == 'PASS' for v in row['tests'].values()),
                       browser_verification=bool(row['journeys']) and all(v == 'PASS' for v in row['journeys'].values()))
    report['reason'] = ('Moderate' if moderate else 'Normal') + ' campaign evidence; operator acceptance and subsequent phases remain separate gates.'
    report['seconds'] = round(time.monotonic() - started, 3)
    write_report(evidence, report)
    print(json.dumps(report, indent=2))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[report['outcome']]


def cleanup_qa_credentials(data_dir):
    # Only called for this execution's random, already removed QA directory.
    # Preserve the key if filesystem cleanup failed, just like source-dev reset.
    if data_dir.exists():
        raise RuntimeError('Refusing vault cleanup while QA database still exists')
    import keyring
    from keyring.errors import PasswordDeleteError
    from sentriface.secure_storage import KEYRING_SERVICE, _keyring_account
    from sentriface.recovery import RECOVERY_SERVICE, _account
    for service, account in ((KEYRING_SERVICE, _keyring_account(data_dir)), (RECOVERY_SERVICE, _account(data_dir))):
        try:
            keyring.delete_password(service, account)
        except PasswordDeleteError:
            pass
        if keyring.get_password(service, account) is not None:
            raise RuntimeError('Disposable credential cleanup did not remove exact QA entry')


def write_report(evidence, report):
    (evidence / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    suite = ET.Element('testsuite', name=report['test_id'], tests='1', failures=str(int(report['outcome'] == 'FAIL')),
                       skipped=str(int(report['outcome'] == 'BLOCKED')), time=str(report['seconds']))
    case = ET.SubElement(suite, 'testcase', name=report['test_id'], classname='sentriface.qa', time=str(report['seconds']))
    if report['outcome'] != 'PASS':
        ET.SubElement(case, 'skipped' if report['outcome'] == 'BLOCKED' else 'failure', message=report['reason']).text = report['reason']
    if report.get('phase') == 'Moderate':
        rows = report.get('acceptance', [])
        for row in rows:
            item = ET.SubElement(suite, 'testcase', name=row['id'], classname='sentriface.qa.Moderate')
            if row['status'] != 'PASS':
                ET.SubElement(item, 'failure' if row['status'] == 'FAIL' else 'skipped', message=row.get('reason', row.get('limitation') or row['status']))
        suite.set('tests', str(1 + len(rows)))
        suite.set('failures', str(int(report['outcome'] == 'FAIL') + sum(r['status'] == 'FAIL' for r in rows)))
        suite.set('skipped', str(int(report['outcome'] == 'BLOCKED') + sum(r['status'] in ('NOT RUN', 'PARTIAL') for r in rows)))
    ET.ElementTree(suite).write(evidence / 'junit.xml', encoding='utf-8', xml_declaration=True)


def require_browser():
    import playwright.sync_api


def main(argv=None):
    parser = argparse.ArgumentParser(description='Foundation J01 and bounded Normal/Moderate User QA. Assets and evidence stay local.')
    parser.add_argument('--expected-sha', help='Exact full checked-out commit; mismatch refuses execution')
    parser.add_argument('--phase', choices=['Foundation', 'Normal', 'Moderate'], default='Foundation')
    parser.add_argument('--density', choices=['journey-only'], default='journey-only', help='One Person, two distinct photos, one Encounter per fresh run; full profiles unavailable')
    parser.add_argument('--evidence-output', type=Path, help='Local parent directory beneath ignored qa-fixtures/')
    parser.add_argument('--test', default='QA-J01', choices=['QA-J01', 'QA-J02', 'Normal', 'Moderate', 'C01', 'C02'] + [f'M{i:02}' for i in range(1, 9)])
    parser.add_argument('--disposable', action='store_true', help='Explicitly authorize a fresh disposable QA authority, never an existing database')
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'qa-fixtures/marvel-actors')
    parser.add_argument('--actor', default='Chris Evans')
    parser.add_argument('--models-config', type=Path)
    parser.add_argument('--chromium', help='Optional installed Chromium executable; otherwise Playwright-managed browser')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--repeat', type=int, choices=(1, 2), default=2, help='Fresh isolated runs; default 2 for repeatability')
    parser.add_argument('--date', default='2026-10-29')
    parser.add_argument('--location', default='QA London')
    args = parser.parse_args(argv)
    started = time.monotonic()
    evidence_parent = (args.evidence_output or ROOT / 'qa-fixtures' / 'runs').resolve()
    if not evidence_parent.is_relative_to((ROOT / 'qa-fixtures').resolve()):
        parser.error('--evidence-output must remain beneath ignored qa-fixtures/ for privacy')
    evidence = evidence_parent / uuid.uuid4().hex
    evidence.mkdir(parents=True, mode=0o700)
    report = {'test_id': args.test, 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)),
              'platform': platform.platform(), 'outcome': 'BLOCKED', 'model_hashes': {}, 'fixture_hashes': [], 'inference_executed': False,
              'evidence': str(evidence), 'reason': ''}
    report.update(phase=args.phase, density=args.density, requested_size={'people': 1, 'photos': 2, 'encounters': 1}, achieved_size={'people': 0, 'photos': 0, 'encounters': 0})
    try:
        if args.phase == 'Moderate' and args.test in ('QA-J01', 'QA-J02', 'Normal'):
            raise ValueError('Moderate requires --test Moderate, M01-M08 or C01-C02')
        if args.expected_sha is not None and (len(args.expected_sha) != 40 or args.expected_sha != report['commit']):
            raise ValueError('Expected SHA differs from checked-out HEAD; execution refused')
        if report['dirty']:
            raise ValueError('Tracked source is dirty; execution refused')
        if not args.disposable:
            raise ValueError('Explicit --disposable selection required; no existing user authority may be used')
        from datetime import date
        date.fromisoformat(args.date)
        if not args.location.strip():
            raise ValueError('Known location required')
        if args.test != 'QA-J01':
            expected_phase = 'Normal' if args.test in ('QA-J02', 'Normal') else 'Moderate'
            if args.phase != expected_phase:
                raise ValueError(args.test + ' requires --phase ' + expected_phase)
        else:
            pair = verified_pair(args.fixtures, args.actor)
            report['fixture_hashes'] = [r['sha256'] for r in pair]
            config = model_inputs(args.models_config)
            report['model_hashes'] = {k: config[k + '_sha256'] for k in ('detector', 'recognizer')}
            report['model_names'] = {k: Path(config[k + '_source']).name for k in ('detector', 'recognizer')}
            require_browser()
    except (ValueError, KeyError, OSError, ImportError) as exc:
        report['reason'] = str(exc)
    else:
        if args.test != 'QA-J01':
            try:
                return normal_campaign(args, evidence, report, started)
            except Exception as exc:
                report.update(outcome='FAIL', reason=f'QA campaign infrastructure: {type(exc).__name__}: {exc}', seconds=round(time.monotonic() - started, 3))
                if args.phase == 'Moderate' and not report.get('acceptance'):
                    rows = json.loads((ROOT / 'tests/qa_coverage.json').read_text())['moderate_acceptance']
                    report['acceptance'] = [dict(id=r['id'], status='NOT RUN', reason=report['reason']) for r in rows]
                write_report(evidence, report)
                print(json.dumps(report, indent=2))
                return 1
        from qa_browser import Blocked
        try:
            report['runs'] = []
            for index in range(args.repeat):
                run_evidence = evidence / f'run-{index + 1}'
                run_evidence.mkdir(mode=0o700)
                run = {'model_hashes': report['model_hashes'], 'inference_executed': False}
                report['runs'].append(run)
                run_started = time.monotonic()
                try:
                    execute(args, config, pair, run_evidence, run)
                    assert_expected({'inference_executed': True, 'restart_verified': True, 'cleanup_completed': True,
                                     'negative_control': {'outcome': 'FAIL_EXPECTED'}, 'browser_errors': []}, run, 'run.proofs')
                    run['outcome'] = 'PASS'
                except Exception as exc:
                    run['outcome'] = 'BLOCKED' if isinstance(exc, Blocked) else 'FAIL'
                    run['reason'] = str(exc)
                    raise
                finally:
                    run['seconds'] = round(time.monotonic() - run_started, 3)
                    report['inference_executed'] = any(r['inference_executed'] for r in report['runs'])
        except Blocked as exc:
            report['reason'] = str(exc)
        except Exception as exc:
            report.update(outcome='FAIL', reason=f'{type(exc).__name__}: {exc}')
        else:
            report.update(outcome='PASS', reason=f'{args.repeat} fresh run(s): independent domain reads, negative control and restart verified')
    if (args.test != 'QA-J01' or args.phase == 'Moderate') and 'acceptance' not in report:
        rows = json.loads((ROOT / 'tests/qa_coverage.json').read_text())['moderate_acceptance' if args.phase == 'Moderate' else 'normal_acceptance']
        report['acceptance'] = [dict(id=r['id'], status='NOT RUN', reason=report['reason']) for r in rows]
    if report['outcome'] == 'PASS':
        report['achieved_size'] = dict(report['requested_size']) # independently verified by execute, per fresh authority
    if not report['inference_executed']:
        report['model_hashes'] = {}
    for run in report.get('runs', []):
        if not run['inference_executed']:
            run['model_hashes'] = {}
    report['foundation'] = 'COMPLETE' if report['outcome'] == 'PASS' and args.repeat == 2 else 'PARTIAL'
    report['seconds'] = round(time.monotonic() - started, 3)
    write_report(evidence, report)
    print(json.dumps(report, indent=2))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[report['outcome']]


if __name__ == '__main__':
    raise SystemExit(main())
