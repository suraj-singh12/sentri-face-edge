"""Controlled failing inputs validate publication without breaking production checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_report', ROOT / 'scripts/ci_report.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.fixture
def results(tmp_path, monkeypatch):
    allowed = {('tests.test_sample', f'test_case_{i}'): ('tests/test_sample.py', i + 1, f'tests/test_sample.py::test_case_{i}') for i in range(10)}
    monkeypatch.setattr(ci, 'source_tests', lambda root: allowed)
    def build(rows=(), status='failure', steps=None):
        suite = ET.Element('testsuite')
        for i, (kind, message) in enumerate(rows):
            case = ET.SubElement(suite, 'testcase', classname='tests.test_sample', name=f'test_case_{i}', time='0.1')
            if kind:
                ET.SubElement(case, kind, message=message).text = message
        ET.ElementTree(suite).write(tmp_path / 'junit.xml')
        return ci.make_report('backend', status, steps or {}, private=tmp_path)
    return build


def test_all_pass_and_skipped_not_passed(results):
    report = results([('', ''), ('skipped', 'private reason')], 'success')
    rendered = ci.markdown(report)
    assert 'PASS — backend' in rendered
    assert '1 passed · 0 failed · 1 skipped' in rendered
    assert 'test_case_0' not in rendered
    assert 'private reason' not in json.dumps(report)


def test_assertion_explanation_and_values(results):
    report = results([('failure', 'AssertionError\nexpected: 2\nactual: 1')])
    rendered = ci.markdown(report)
    assert 'test/product behavior' in rendered
    assert 'tests/test_sample.py::test_case_0' in rendered
    assert '**Expected:** 2 · **Actual:** 1' in rendered
    assert 'Root cause not yet confirmed' in rendered
    assert 'Impact requires investigation' in rendered


def test_numeric_comparison_does_not_invent_expected_role():
    detail = ci.diagnostics('E       assert 1 == 2')
    assert detail['comparison'] == 'Assertion comparison: 1 == 2'
    assert detail['expected'] is None


@pytest.mark.parametrize('stage', ['install', 'npm-install', 'python-toolchain', 'inno'])
def test_dependency_is_setup_failure(results, stage):
    report = results([], steps={stage: {'outcome': 'failure'}})
    assert report['failures'][0]['category'] == 'environment/setup'
    assert 'check installation and dependencies' in ci.markdown(report)


def test_harness_and_unknown_are_not_product_defects(results):
    report = results([('error', 'AssertionError in fixture'), ('failure', 'Unrecognized crash')])
    assert [f['category'] for f in report['failures']] == ['test infrastructure', 'unknown']
    assert all(f['impact'] == 'Impact requires investigation.' for f in report['failures'])


def test_related_grouping_preserves_every_failure(results):
    # Same source + exact raw error required. Different tests never guessed related.
    report = results([('failure', 'AssertionError repeated'), ('failure', 'AssertionError unrelated')])
    duplicate = dict(report['failures'][0])
    report['failures'].append(duplicate)
    rendered = ci.markdown(report)
    assert '2 repeated failures' in rendered
    assert rendered.count('**What failed:**') == 2
    assert len(report['failures']) == 3


def test_more_than_three_unrelated(results):
    report = results([('failure', f'AssertionError {i}') for i in range(6)])
    rendered = ci.markdown(report)
    assert rendered.count('**What failed:**') == 3
    assert '3 additional failures' in rendered
    assert len(report['failures']) == 6


@pytest.mark.parametrize('state,expected', [('success', 'BLOCKED'), ('failure', 'FAILED'), ('cancelled', 'CANCELLED')])
def test_missing_and_partial_report(tmp_path, state, expected):
    for content in (None, '<testsuite><testcase'):
        if content:
            (tmp_path / 'junit.xml').write_text(content)
        report = ci.make_report('backend', state, {}, private=tmp_path)
        assert report['outcome'] == expected
        assert not report['availability']['junit']
        assert 'diagnostics unavailable' in ci.markdown(report)


def test_cancelled_even_with_passing_results(results):
    assert results([('', '')], 'cancelled')['outcome'] == 'CANCELLED'


def test_sensitive_text_is_never_published(results):
    secret = 'token=ghp_123SECRET password=operator /Users/private/name Alice face.jpg <script>'
    report = results([('failure', secret + '\nAssertionError\nexpected: ' + secret + '\nactual: ' + secret)])
    rendered = json.dumps(report) + ci.markdown(report)
    for value in ('123SECRET', 'operator', '/Users', 'Alice', 'face.jpg', '<script>'):
        assert value not in rendered
    assert report['failures'][0]['expected'] is None


def test_unknown_identity_has_no_invented_location(results, monkeypatch):
    monkeypatch.setattr(ci, 'source_tests', lambda root: {})
    report = results([('failure', 'unknown private text')])
    f = report['failures'][0]
    assert f['location'] is None
    assert f['category'] == 'unknown'
    assert 'source location unavailable' in ci.markdown(report)
    assert not report['availability']['identities_complete']


def test_real_failing_pytest_and_exit_code(tmp_path, monkeypatch):
    source = tmp_path / 'test_control.py'
    source.write_text('def test_control():\n    assert 1 == 2\n')
    output = tmp_path / 'junit.xml'
    monkeypatch.setattr(ci, 'PRIVATE', tmp_path)
    code = ci.run('tests', [sys.executable, '-m', 'pytest', '-q', str(source), '--junitxml=' + str(output)])
    assert code == 1
    assert json.loads((tmp_path / 'tests.json').read_text())['exit_code'] == 1
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert report['outcome'] == 'FAILED'
    assert report['counts']['failed'] == 1
    assert report['failures'][0]['category'] == 'test/product behavior'
    assert '1 == 2' in ci.markdown(report)


def test_unstarted_and_interrupted_stages(tmp_path):
    (tmp_path / 'tests.json').write_text(json.dumps(dict(stage='tests', outcome='running', seconds=0)))
    report = ci.make_report('backend', 'cancelled', {}, private=tmp_path)
    assert report['outcome'] == 'CANCELLED'
    assert report['failures'][0]['category'] == 'unknown'


def test_workflow_preserves_checks_and_publication_allowlist():
    text = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'continue-on-error' not in text
    assert text.count('if: always()') == 6
    assert text.count('retention-days: 7') == 3
    assert text.count('python-version: "3.12"') == 2
    assert 'os: [ubuntu-latest, macos-latest, windows-latest]' in text
    assert 'exit $LASTEXITCODE' in text
    assert 'dist/windows-x64/2.0.0/*' not in text
    assert text.count('qa-fixtures/ci-public/report.json') == 3
    assert text.count('qa-fixtures/ci-public/summary.md') == 3
    assert '--junitxml=qa-fixtures/ci/junit.xml' in text


def test_real_source_allowlist_and_coverage():
    allowed = ci.source_tests(ROOT)
    assert ('tests.test_qa_foundation', 'test_qa_o01_correct_and_wrong_expectation') in allowed
    assert any('identity mutations invalidate' in key[1] for key in allowed)


def test_manual_sha_and_dirty_refused(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import qa_foundation as qa
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda cmd, **kw: 'a' * 40 if 'rev-parse' in cmd else '')
    monkeypatch.setattr(qa, 'verified_pair', lambda *a: pytest.fail('must refuse before fixtures'))
    assert qa.main(['--disposable', '--expected-sha', 'b' * 40]) == 2
    assert 'Expected SHA differs' in json.loads(capsys.readouterr().out)['reason']
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda cmd, **kw: 'a' * 40 if 'rev-parse' in cmd else ' M tracked.py')
    assert qa.main(['--disposable', '--expected-sha', 'a' * 40]) == 2
    assert 'Tracked source is dirty' in json.loads(capsys.readouterr().out)['reason']


def test_missing_assets_blocked_without_hash_claim(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import qa_foundation as qa
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    monkeypatch.setattr(qa.subprocess, 'check_output', lambda cmd, **kw: 'a' * 40 if 'rev-parse' in cmd else '')
    monkeypatch.setattr(qa, 'verified_pair', lambda *a: [{'sha256': 'a'}, {'sha256': 'b'}])
    monkeypatch.setattr(qa, 'model_inputs', lambda *a: (_ for _ in ()).throw(ValueError('Authorized ONNX assets missing')))
    assert qa.main(['--disposable', '--expected-sha', 'a' * 40]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['outcome'] == 'BLOCKED'
    assert result['model_hashes'] == {}
    assert result['achieved_size']['people'] == 0


@pytest.mark.parametrize('option,value', [('--phase', 'Normal'), ('--test', 'QA-J02'), ('--density', 'Sparse'), ('--repeat', '3')])
def test_manual_unavailable_selection(option, value):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import qa_foundation as qa
    with pytest.raises(SystemExit) as error:
        qa.main([option, value])
    assert error.value.code == 2


def test_node_22_numeric_assertion_format():
    detail = ci.diagnostics("AssertionError [ERR_ASSERTION]\n    actual: 1,\n    expected: 2,\n    operator: 'strictEqual',")
    assert detail['expected'] == '2'
    assert detail['actual'] == '1'


def test_sensitive_numeric_comparison_withheld():
    detail = ci.diagnostics('AssertionError password\nexpected: 1234\nactual: 5678')
    assert detail['expected'] is None
    assert detail['actual'] is None


def test_fallback_failure_is_actionable(tmp_path):
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert report['failures'][0]['category'] == 'unknown'
    assert 'Open the failed step log' in ci.markdown(report)


def test_grouping_requires_exact_raw_error_and_location(results, tmp_path):
    results([('failure', 'AssertionError common'), ('failure', 'AssertionError common'), ('failure', 'AssertionError different')])
    path = tmp_path / 'junit.xml'
    tree = ET.parse(path)
    cases = list(tree.iter('testcase'))
    cases[1].set('name', cases[0].get('name'))
    tree.write(path)
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert len(report['failures']) == 3
    assert len(set(f['signature'] for f in report['failures'])) == 2
    assert '2 repeated failures' in ci.markdown(report)
    assert ci.markdown(report).count('**What failed:**') == 2


def test_node_hook_failure_is_infrastructure(results):
    report = results([('failure', "failureType: 'hookFailed'\nAssertionError")])
    assert report['failures'][0]['category'] == 'test infrastructure'


def test_partial_ledger_and_private_diagnostic_are_not_published(tmp_path):
    (tmp_path / 'tests.json').write_text('{')
    (tmp_path / 'install.json').write_text(json.dumps(dict(stage='password=PRIVATE', outcome='failure', seconds='secret', diagnostic={'error': 'password=PRIVATE'})))
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert 'PRIVATE' not in json.dumps(report)
    assert report['outcome'] == 'FAILED'
    assert report['seconds'] == 0
    assert len(report['failures']) == 2


def test_all_skipped_is_blocked(results):
    report = results([('skipped', 'unavailable')], 'success')
    assert report['outcome'] == 'BLOCKED'
    assert report['counts']['passed'] == 0


def test_summary_cli_publishes_identical_safe_payload(results, tmp_path, monkeypatch, capsys):
    report = results([('', '')], 'success')
    monkeypatch.setattr(ci, 'make_report', lambda *args: report)
    monkeypatch.setattr(ci, 'PUBLIC', tmp_path / 'public')
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(tmp_path / 'step-summary.md'))
    monkeypatch.setenv('CI_STEPS', '{}')
    assert ci.main(['summary', '--check', 'backend', '--status', 'success']) == 0
    output = capsys.readouterr().out
    assert (tmp_path / 'step-summary.md').read_text(encoding='utf8') == ci.markdown(report)
    assert (tmp_path / 'public/summary.md').read_text(encoding='utf8') == ci.markdown(report)
    assert json.loads((tmp_path / 'public/report.json').read_text()) == report
    assert 'Sanitized CI report JSON: ' + json.dumps(report, sort_keys=True) in output
    assert ci.markdown(report) in output


def test_summary_explicitly_defers_later_cancellation_to_github(results):
    report = results([('', '')], 'success')
    assert 'GitHub final job conclusion takes precedence, including later cancellation.' in ci.markdown(report)
    assert report['status_scope'].startswith('Checks at publication')


def test_real_unittest_subtests_retain_all_failures(tmp_path):
    source = tmp_path / 'test_subtest_control.py'
    source.write_text("import unittest\nclass Controlled(unittest.TestCase):\n    def test_two(self):\n        for value in (1, 2):\n            with self.subTest(value=value):\n                self.assertEqual(value, 0)\n")
    output = tmp_path / 'junit.xml'
    process = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(source), '--junitxml=' + str(output)], capture_output=True)
    assert process.returncode == 1
    assert len(list(ET.parse(output).iter('failure'))) == 2
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert report['counts']['failed'] == 1
    assert len(report['failures']) == 2
    assert [f['failure_index'] for f in report['failures']] == [1, 2]
    assert len(set(f['signature'] for f in report['failures'])) == 2


def test_teardown_error_does_not_hide_assertion_or_skip(results, tmp_path):
    results([('failure', 'AssertionError')])
    path = tmp_path / 'junit.xml'
    tree = ET.parse(path)
    case = next(tree.iter('testcase'))
    ET.SubElement(case, 'error', message='RuntimeError in teardown')
    ET.SubElement(case, 'skipped', message='not meaningful after error')
    tree.write(path)
    report = ci.make_report('backend', 'failure', {}, private=tmp_path)
    assert report['counts'] == dict(passed=0, failed=1, skipped=0, blocked=0)
    assert [f['category'] for f in report['failures']] == ['test/product behavior', 'test infrastructure']


def node_rows(tmp_path, rows):
    (tmp_path / 'node.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')


def native_parent(**extra):
    return dict(event='test:fail', name='CI events retain parent assertions and distinguish skipped tests',
                file=str(ROOT / 'frontend/tests/ci-reporting.test.mjs'), kind='test', duration_ms=2,
                error='Error\nAssertionError [ERR_ASSERTION]', expected=2, actual=1, **extra)


def test_native_node_parent_assertion_and_skips(tmp_path):
    node_rows(tmp_path, [dict(event='test:pass', name='child', kind='test', duration_ms=1),
                         dict(event='test:pass', name='skipped', skipped=True, kind='test'), native_parent()])
    report = ci.make_report('frontend', 'failure', {}, private=tmp_path)
    assert report['counts'] == dict(passed=1, failed=1, skipped=1, blocked=0)
    assert report['availability']['structured_results']
    assert not report['availability']['junit']
    assert report['failures'][0]['test_id'].startswith('frontend/tests/ci-reporting.test.mjs::CI events')
    assert report['failures'][0]['category'] == 'test/product behavior'
    assert '**Expected:** 2 · **Actual:** 1' in ci.markdown(report)


def test_native_node_hook_and_parent_cancellation(tmp_path):
    node_rows(tmp_path, [native_parent(failure_type='hookFailed'), native_parent(failure_type='cancelledByParent')])
    report = ci.make_report('frontend', 'failure', {}, private=tmp_path)
    assert [f['category'] for f in report['failures']] == ['test infrastructure', 'blocked/skipped']
    assert len(set(f['signature'] for f in report['failures'])) == 2
    assert report['failures'][1]['error'] == 'Cancelled by parent test; this test did not complete.'
    assert report['counts']['blocked'] == 1
    assert report['counts']['passed'] == 0


def test_native_node_partial_data_never_passes(tmp_path):
    node_rows(tmp_path, [dict(event='test:pass', name='child', kind='test', duration_ms=1)])
    with (tmp_path / 'node.jsonl').open('a') as stream:
        stream.write('{partial')
    report = ci.make_report('frontend', 'success', {}, private=tmp_path)
    assert report['outcome'] == 'BLOCKED'
    assert not report['availability']['structured_results']


def test_native_node_untrusted_values_and_file_omitted(tmp_path):
    row = native_parent()
    row.update(error='AssertionError password=PRIVATE', expected='SECRET', actual='PRIVATE', file='/private/SECRET')
    node_rows(tmp_path, [row])
    report = ci.make_report('frontend', 'failure', {}, private=tmp_path)
    assert report['failures'][0]['location'] is None
    assert 'SECRET' not in json.dumps(report)
    assert 'PRIVATE' not in json.dumps(report)


def test_packaging_phase_and_original_exit_are_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, 'PRIVATE', tmp_path)
    code = ci.run('package', [sys.executable, '-c', "print('Run frontend regression suite failed with exit code 23.'); raise SystemExit(23)"])
    assert code == 23
    report = ci.make_report('windows-package', 'failure', {}, private=tmp_path)
    failure = report['failures'][0]
    assert 'Run frontend regression suite' in failure['description']
    assert failure['location']['file'] == 'build_release.ps1'
    line = (ROOT / failure['location']['file']).read_text().splitlines()[failure['location']['line'] - 1]
    assert 'Invoke-Checked "Run frontend regression suite"' in line
    assert failure['category'] == 'unknown'
    assert report['stages'][0]['exit_code'] == 23


def test_private_packaging_phase_is_not_published(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps(dict(stage='package', outcome='failure', seconds=1, exit_code=1, substage='password=SECRET')))
    report = ci.make_report('windows-package', 'failure', {}, private=tmp_path)
    assert 'SECRET' not in json.dumps(report)
    assert report['failures'][0]['location'] is None
