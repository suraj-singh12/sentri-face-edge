"""Offline QA primitives. No application/biometric acceptance is implied by these checks."""
from __future__ import annotations
import argparse
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
    def __init__(self, data_dir, evidence):
        self.data_dir, self.evidence, self.process, self.stream = data_dir, evidence, None, None
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'

    def start(self):
        self.stream = (self.evidence / 'application.log').open('ab')
        self.process = subprocess.Popen([sys.executable, '-m', 'sentriface.ui', '--runtime', 'onnx',
            '--allow-unpackaged-source-onnx', '--data-dir', str(self.data_dir), '--port', str(self.port)],
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


def execute(args, config, pair, evidence, report):
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
                    assert_expected({'events': []}, ui.get(context, '/api/encounters'), 'ReferenceOnly.no_presence')
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
                    report['verified'] = after
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


def write_report(evidence, report):
    (evidence / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    suite = ET.Element('testsuite', name='QA-J01', tests='1', failures=str(int(report['outcome'] == 'FAIL')),
                       skipped=str(int(report['outcome'] == 'BLOCKED')), time=str(report['seconds']))
    case = ET.SubElement(suite, 'testcase', name='QA-J01', classname='sentriface.qa', time=str(report['seconds']))
    if report['outcome'] != 'PASS':
        ET.SubElement(case, 'skipped' if report['outcome'] == 'BLOCKED' else 'failure', message=report['reason']).text = report['reason']
    ET.ElementTree(suite).write(evidence / 'junit.xml', encoding='utf-8', xml_declaration=True)


def require_browser():
    import playwright.sync_api


def main(argv=None):
    parser = argparse.ArgumentParser(description='QA-J01 real browser / ONNX journey. Assets and evidence stay local.')
    parser.add_argument('--test', default='QA-J01', choices=['QA-J01'])
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
    evidence = ROOT / 'qa-fixtures' / 'runs' / uuid.uuid4().hex
    evidence.mkdir(parents=True, mode=0o700)
    report = {'test_id': args.test, 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)),
              'outcome': 'BLOCKED', 'model_hashes': {}, 'fixture_hashes': [], 'inference_executed': False,
              'evidence': str(evidence), 'reason': ''}
    try:
        if not args.disposable:
            raise ValueError('Explicit --disposable selection required; no existing user authority may be used')
        from datetime import date
        date.fromisoformat(args.date)
        if not args.location.strip():
            raise ValueError('Known location required')
        pair = verified_pair(args.fixtures, args.actor)
        report['fixture_hashes'] = [r['sha256'] for r in pair]
        config = model_inputs(args.models_config)
        report['model_hashes'] = {k: config[k + '_sha256'] for k in ('detector', 'recognizer')}
        report['model_names'] = {k: Path(config[k + '_source']).name for k in ('detector', 'recognizer')}
        require_browser()
    except (ValueError, KeyError, OSError, ImportError) as exc:
        report['reason'] = str(exc)
    else:
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
    report['foundation'] = 'COMPLETE' if report['outcome'] == 'PASS' and args.repeat == 2 else 'PARTIAL'
    report['seconds'] = round(time.monotonic() - started, 3)
    write_report(evidence, report)
    print(json.dumps(report, indent=2))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[report['outcome']]


if __name__ == '__main__':
    raise SystemExit(main())
