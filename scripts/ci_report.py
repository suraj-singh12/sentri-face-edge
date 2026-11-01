"""Small stdlib-only CI adapter. Raw outputs are runner-local; publication is allowlisted."""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'qa-fixtures' / 'ci'
PUBLIC = ROOT / 'qa-fixtures' / 'ci-public'
STAGES = {
    'checkout': ('Check out source', 'environment/setup'),
    'python-toolchain': ('Prepare Python 3.12', 'environment/setup'),
    'node-toolchain': ('Prepare Node 22', 'environment/setup'),
    'install': ('Install Python dependencies', 'environment/setup'),
    'pip-check': ('Check Python dependencies', 'environment/setup'),
    'npm-install': ('Install frontend dependencies', 'environment/setup'),
    'inno': ('Install Inno Setup 7 x64', 'environment/setup'),
    'tests': ('Backend tests', 'unknown'),
    'node-tests': ('Frontend tests', 'unknown'),
    'build': ('Frontend production build', 'unknown'),
    'assets': ('Generated frontend consistency', 'unknown'),
    'package': ('Unsigned Windows installer build', 'unknown'),
}
OMITTED = 'Details withheld: not on the public diagnostic allowlist. Inspect the failing step log.'


def diagnostics(text):
    """Never publish arbitrary exception messages, paths, values or XML properties.

    Only known exception classes and entire numeric/bool/null comparisons are
    allowed. Numeric values are bounded to avoid copying encoded credentials.
    Hash raw signatures locally to group exact repeats without disclosing text.
    """
    error = next((x for x in ('AssertionError', 'ModuleNotFoundError', 'ImportError', 'TypeError', 'ValueError', 'RuntimeError', 'ERR_ASSERTION') if re.search(r'\b' + x + r'\b', text)), None)
    if re.search(r'password|token|secret|credential|authorization|biometric|email|bearer', text, re.I):
        return {'error': error or OMITTED, 'comparison': None, 'expected': None, 'actual': None}
    atom = r'(?:True|False|None|true|false|null|-?\d{1,6}(?:\.\d{1,4})?)'
    match = re.search(r'^\s*(?:E\s+)?assert (' + atom + r') == (' + atom + r')\s*$', text, re.M)
    # pytest renders actual == expected; do not guess orientation.
    comparison = f'Assertion comparison: {match[1]} == {match[2]}' if match else None
    explicit = re.search(r'^expected: (' + atom + r')\nactual: (' + atom + r')$', text, re.M)
    node = re.search(r'^\s+actual: (' + atom + r'),\n\s+expected: (' + atom + r'),$', text, re.M)
    if node and not explicit:
        return {'error': error or OMITTED, 'comparison': None, 'expected': node[2], 'actual': node[1]}
    return {'error': error or OMITTED, 'comparison': comparison,
            'expected': explicit[1] if explicit else None, 'actual': explicit[2] if explicit else None}


def source_tests(root):
    """Public test identity/location allowlist from tracked source, not result text."""
    result = {}
    duplicate_titles = set()
    tracked = subprocess.check_output(['git', 'ls-files', 'tests/*.py', 'frontend/tests/*.mjs'], cwd=root, text=True).splitlines()
    for name in tracked:
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf8')
        if path.suffix == '.py':
            tree = ast.parse(text)
            def visit(node, classes=()):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.ClassDef):
                        visit(child, classes + (child.name,))
                    elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith('test_'):
                        classname = '.'.join((name[:-3].replace('/', '.'), *classes))
                        result[(classname, child.name)] = (name, child.lineno, '::'.join((name, *classes, child.name)))
            visit(tree)
        else:
            for match in re.finditer(r'\btest\(\s*([\'\"])([^\n]+?)\1\s*,', text):
                title = match[2]
                if ('', title) in result:
                    duplicate_titles.add(title)
                result[('', title)] = (name, text[:match.start()].count('\n') + 1, name + '::' + title)
    for title in duplicate_titles:
        result.pop(('', title), None) # Never invent a location for an ambiguous title.
    return result


def elapsed(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def read_junit(path, root=ROOT):
    counts = dict(passed=0, failed=0, skipped=0, blocked=0)
    failures, skipped, suites = [], [], set()
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError):
        return counts, failures, skipped, [], False, 0.0
    allowed = source_tests(root)
    registry = json.loads((root / 'tests/qa_coverage.json').read_text())['cases']
    seconds = 0.0
    for index, case in enumerate(tree.iter('testcase')):
        seconds += elapsed(case.get('time', '0'))
        classname, name = case.get('classname', ''), case.get('name', '')
        # Only accept complete source-declared IDs. Dynamic parameter values may be private.
        source = allowed.get((classname, name)) or allowed.get(('', name))
        location = {'file': source[0], 'line': source[1]} if source else None
        identifier = source[2] if source else f'unverified-test-{index + 1}'
        coverage = [r for r in registry if source and any(t == identifier or t == source[0] for t in r['tests'])]
        suites.update(r['id'] for r in coverage)
        skip = case.find('skipped')
        failure = case.find('failure')
        error = case.find('error')
        if skip is not None:
            counts['skipped'] += 1
            skipped.append({'test_id': identifier, 'reason': 'Skipped; reason withheld unless reviewed in step log.'})
        elif failure is not None or error is not None:
            counts['failed'] += 1
            element = error if error is not None else failure
            raw = element.get('message', '') + '\n' + (element.text or '')
            detail = diagnostics(raw)
            category = 'test infrastructure' if error is not None or "failureType: 'hookFailed'" in raw else ('test/product behavior' if detail['error'] in ('AssertionError', 'ERR_ASSERTION') or detail['comparison'] else 'unknown')
            failures.append(dict(test_id=identifier, location=location, category=category,
                description=name.removeprefix('test_').replace('_', ' ') if source else 'Test identity unavailable for safe publication',
                impact=('Coverage purpose: ' + coverage[0]['behavior']) if coverage and category == 'test/product behavior' else 'Impact requires investigation.',
                next_step='Inspect the failing test and reproduce it locally. Root cause not yet confirmed.',
                signature=hashlib.sha256((str(location or identifier) + category + raw).encode()).hexdigest(), **detail))
        else:
            counts['passed'] += 1
    return counts, failures, skipped, sorted(suites), True, round(seconds, 3)


def run(stage, command):
    """Persist start before command; return the original command exit code."""
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / (stage + '.json')
    record = {'stage': stage, 'outcome': 'running', 'seconds': 0}
    path.write_text(json.dumps(record))
    start = time.monotonic()
    # Keep original diagnostics in existing step logs only; retain a bounded tail locally.
    tail = ''
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace') as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                tail = (tail + line)[-16000:]
            code = process.wait()
    except OSError:
        code = 127
    record.update(outcome='success' if code == 0 else 'failure', exit_code=code,
                  seconds=round(time.monotonic() - start, 3), diagnostic=diagnostics(tail))
    path.write_text(json.dumps(record))
    return code


def make_report(check, status, steps, root=ROOT, private=PRIVATE):
    junit = private / 'junit.xml'
    counts, failures, skipped, suites, available, seconds = read_junit(junit, root)
    stages = []
    has_test_failures = bool(failures)
    for key in STAGES:
        path = private / (key + '.json')
        if path.exists():
            try:
                record = json.loads(path.read_text())
                if not isinstance(record, dict):
                    raise ValueError('Invalid stage record')
            except (OSError, ValueError):
                record = {}
            record['stage'] = key
            record['seconds'] = elapsed(record.get('seconds'))
            if record.get('outcome') not in ('running', 'success', 'failure'):
                record['outcome'] = 'running' # Interrupted/unreadable evidence cannot prove success.
            if not isinstance(record.get('exit_code'), int):
                record['exit_code'] = None
            stages.append(record)
        else:
            record = None
        step = steps.get(key, {})
        outcome = step.get('outcome', record['outcome'] if record else '')
        if outcome in ('failure', 'cancelled') or (record and record['outcome'] == 'running'):
            if key in ('tests', 'node-tests') and has_test_failures:
                continue
            label, category = STAGES[key]
            failures.append(dict(test_id=key, description=label, location=None, category=category,
                impact='Impact requires investigation.' if category == 'unknown' else 'This check could not complete reliably.',
                next_step='Inspect this step log; check installation and dependencies.' if category == 'environment/setup' else 'Inspect this step log and reproduce the command locally.',
                signature=key, **diagnostics(str(record.get('diagnostic', {}).get('error', '')) if record and isinstance(record.get('diagnostic'), dict) else '')))
    if status == 'failure' and not failures:
        failures.append(dict(test_id='unavailable', description='CI check failed; detailed diagnostics unavailable', location=None, category='unknown', impact='Impact requires investigation.', next_step='Open the failed step log in this run.', signature='unavailable', **diagnostics('')))
    actual_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    outcome = 'CANCELLED' if status == 'cancelled' else 'FAILED' if status == 'failure' or failures else 'PASS' if status == 'success' else 'BLOCKED'
    test_job = check in ('backend', 'frontend')
    if outcome == 'PASS' and test_job and (not available or not (counts['passed'] + counts['failed'])):
        outcome = 'BLOCKED'
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    # GitHub metadata is validated before publishing links.
    repo = repo if re.fullmatch(r'[\w.-]+/[\w.-]+', repo) else ''
    run_id = run_id if run_id.isdigit() else ''
    groups = {}
    for failure in failures:
        groups.setdefault(failure['signature'], f'failure-group-{len(groups) + 1}')
        failure['signature'] = groups[failure['signature']] # Never publish hashes of private error text.
    return dict(schema_version=1, repository=repo, commit=actual_sha,
        run_id=run_id, run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', '') if os.environ.get('GITHUB_RUN_ATTEMPT', '').isdigit() else '',
        run_url=f'https://github.com/{repo}/actions/runs/{run_id}' if repo and run_id else None,
        platform=sys.platform, check=check, suites=suites, counts=counts, outcome=outcome,
        seconds=round(sum(s['seconds'] for s in stages), 3), test_seconds=seconds,
        failures=failures, skipped=skipped,
        stages=[dict(stage=s['stage'], outcome=s['outcome'], seconds=s['seconds'], exit_code=s.get('exit_code')) for s in stages],
        availability={'junit': available, 'identities_complete': all(f['location'] for f in failures if f['test_id'] not in STAGES),
                      'diagnostics': 'Allowlisted only; raw JUnit and free text are never uploaded.'},
        evidence=['report.json', 'summary.md', 'Failing step logs in the linked run'],
        limitation='Fast synthetic/domain checks do not establish real ONNX or installer acceptance.' + (' Node totals count JUnit testcases; container tests are excluded.' if check == 'frontend' else ''))


def markdown(report):
    def safe(value):
        return html.escape(str(value)).replace('`', '&#96;').replace('\n', ' ')
    c = report['counts']
    totals = f"{c['passed']} passed · {c['failed']} failed · {c['skipped']} skipped · {c['blocked']} blocked" if report['availability']['junit'] else ('Test totals not applicable' if report['check'] == 'windows-package' else 'Test totals unavailable')
    sections = [f"## {report['outcome']} — {report['check']} ({report['platform']})",
                f"{totals} | {report['seconds']}s (recorded commands)  \nSHA: `{report['commit']}`"]
    groups = {}
    for failure in report['failures']:
        groups.setdefault(failure['signature'], []).append(failure)
    for group in list(groups.values())[:3]:
        f = group[0]
        lines = [f"**What failed:** {safe(f['description'])} ({f['category']})" + (f' — {len(group)} repeated failures' if len(group) > 1 else ''),
                 f"**Where:** `{safe(f['test_id'])}`" + (f" — {f['location']['file']}:{f['location']['line']}" if f['location'] else ' — source location unavailable'),
                 f"**Error:** {safe(f['error'])}"]
        if f['expected'] is not None:
            lines += [f"**Expected:** {safe(f['expected'])} · **Actual:** {safe(f['actual'])}"]
        elif f['comparison']:
            lines += [safe(f['comparison']) + ' (operand roles not supplied)']
        lines += [f"**Why it matters:** {safe(f['impact'])}", f"**Next step:** {safe(f['next_step'])}"]
        sections.append('  \n'.join(lines))
    remaining = sum(len(g) for g in list(groups.values())[3:])
    if remaining:
        sections.append(f'{remaining} additional failures: see report.json.')
    if not report['availability']['junit']:
        sections.append('Test diagnostics unavailable: no complete JUnit report.' if report['check'] != 'windows-package' else 'Packaging check; no test suite.')
    if report['outcome'] == 'CANCELLED':
        sections.append('Execution cancelled; results may be partial.')
    evidence = ['**Evidence:** sanitized report.json and summary.md in the job artifact (7 days); all failures and available IDs in JSON.',
                f"[Run and step logs]({report['run_url']})" if report['run_url'] else 'Run link unavailable.',
                report['availability']['diagnostics']]
    sections.append('<details><summary>Technical evidence</summary>\n\n' + '\n\n'.join(evidence) + '\n\n</details>')
    sections.append(report['limitation'])
    return '\n\n'.join(sections) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    runner = sub.add_parser('run')
    runner.add_argument('stage', choices=STAGES)
    runner.add_argument('command', nargs=argparse.REMAINDER)
    summary = sub.add_parser('summary')
    summary.add_argument('--check', choices=('backend', 'frontend', 'windows-package'), required=True)
    summary.add_argument('--status', choices=('success', 'failure', 'cancelled', 'skipped'), required=True)
    args = parser.parse_args(argv)
    if args.action == 'run':
        return run(args.stage, args.command[1:] if args.command[:1] == ['--'] else args.command)
    report = make_report(args.check, args.status, json.loads(os.environ.get('CI_STEPS', '{}')))
    PUBLIC.mkdir(parents=True, exist_ok=True)
    rendered = markdown(report)
    (PUBLIC / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    (PUBLIC / 'summary.md').write_text(rendered, encoding='utf8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf8') as stream:
            stream.write(rendered)
    distinct = {f['signature']: f for f in reversed(report['failures'])}
    # The same allowlisted payload is inspectable through native step logs too.
    print(rendered)
    print('Sanitized CI report JSON: ' + json.dumps(report, sort_keys=True))
    for f in list(distinct.values())[-3:]:
        if f['location']:
            # Source-derived labels only. Escape workflow command delimiters.
            message = f['description'].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print(f"::error file={f['location']['file']},line={f['location']['line']}::{message}. Inspect job summary.")
    return 1 if report['outcome'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
