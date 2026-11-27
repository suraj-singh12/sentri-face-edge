#!/usr/bin/env python3
"""Conservative Issue #6 source-to-capture candidate reconciliation.

Reads private accessibility snapshots; never exports their text or private paths.
An exact role/name match proves only accessibility-tree presence. Every automatic
match remains PARTIAL: ordered execution, viewport visibility, source attribution,
role enforcement, and branch outcome require separate human/semantic review.

Run from any directory:
  python3 audit-results/issue-6/tooling/reconcile.py
Optional --private-root points at another authorized capture directory.
The default writes coverage.csv, evidence-candidates.csv and coverage-summary.json.
Source task/branch ledgers are deliberately not mutated by this candidate tool.
"""
from __future__ import annotations
import argparse
import ast
import collections
import csv
import hashlib
import html
import json
from pathlib import Path
import re

BASE_SHA = 'b457f0a723e845dd1a92a07a577072c85146c89a'
COUNTED_KINDS = {'control-definition', 'overlay-definition', 'transition'}
ROLES = {
    'Button': {'button'}, 'ActionIcon': {'button'}, 'UnstyledButton': {'button'},
    'TextInput': {'textbox', 'spinbutton'}, 'PasswordInput': {'textbox'},
    'NumberInput': {'textbox', 'spinbutton'}, 'Textarea': {'textbox'},
    'Select': {'textbox', 'combobox'}, 'MultiSelect': {'textbox', 'combobox'},
    'TagsInput': {'textbox', 'combobox'}, 'Checkbox': {'checkbox'},
    'Switch': {'switch', 'checkbox'}, 'Radio': {'radio'},
    'Menu.Item': {'menuitem'}, 'Tabs.Tab': {'tab'}, 'Modal': {'dialog'},
    'Drawer': {'dialog'}, 'Tooltip': {'tooltip'}, 'button': {'button'},
    'a': {'link'}, 'summary': {'button'},
}
SNAPSHOT_NAME = re.compile(r'^\s*-\s+(?P<role>[a-z][a-z0-9-]*)\s+(?P<name>"(?:[^"\\]|\\.)*")(?=\s*(?:\[|:|$))')
SAFE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.png$')

def read_csv(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_csv(path, fields, rows):
    # Atomic replacement prevents a reviewer from reading a partial output.
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def literal_label(value):
    """Accept a complete static string, never evaluate a JS expression."""
    value = value.strip()
    if not value or value.startswith('{') or value.startswith('('):
        return None
    if value[:1] in {'"', "'"}:
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(value, str) or any(char in value for char in '{}<>'):
        return None
    value = html.unescape(value).strip()
    if value.startswith('(dynamic') or not value:
        return None
    return value

def expected_roles(row):
    roles = ROLES.get(row['element'])
    if roles:
        return roles
    # Clickable Paper/Card/Box/native wrappers are button candidates only when
    # the source explicitly supplies component="button" or an equivalent role.
    try:
        action = json.loads(row.get('action') or '{}')
        state = json.loads(row.get('state_expressions') or '{}')
    except json.JSONDecodeError:
        return set()
    if action.get('component') == '"button"' or state.get('role') == '"button"':
        return {'button'}
    return set()

def tree_names(text):
    names = set()
    for line in text.splitlines():
        match = SNAPSHOT_NAME.match(line)
        if not match:
            continue
        try:
            name = json.loads(match['name'])
        except json.JSONDecodeError:
            continue
        names.add((match['role'], name.strip()))
    return names

def capture_candidates(private_root, source_sha):
    records = json.loads((private_root / 'capture-metadata.json').read_text())
    if not isinstance(records, list):
        raise ValueError('Capture metadata must be an array')
    accepted, rejected = [], collections.Counter()
    for record in records:
        if record.get('source_sha') != source_sha:
            rejected['source_sha_mismatch'] += 1
            continue
        original = record.get('file', '')
        sanitized = record.get('sanitized_file')
        if not SAFE_NAME.fullmatch(original):
            rejected['unsafe_original_basename'] += 1
            continue
        if sanitized:
            public_file = sanitized
            public_hash = record.get('sanitized_sha256')
        elif record.get('public_candidate') is True:
            public_file = original
            public_hash = record.get('sha256')
        else:
            rejected['private_without_public_derivative'] += 1
            continue
        if not SAFE_NAME.fullmatch(public_file) or not re.fullmatch(r'UX-\d{2}', record.get('ux', '')):
            rejected['unsafe_public_reference'] += 1
            continue
        image = private_root / 'captures' / original
        public_image = private_root / 'captures' / public_file
        snapshot = private_root / 'captures' / (original + '.txt')
        if not all(path.is_file() for path in (image, public_image, snapshot)):
            rejected['capture_or_snapshot_missing'] += 1
            continue
        if digest(image) != record.get('sha256') or digest(public_image) != public_hash:
            rejected['capture_hash_mismatch'] += 1
            continue
        accepted.append({**record, 'public_file': public_file, 'public_sha256': public_hash,
                         'is_sanitized': bool(sanitized), 'tree_names': tree_names(snapshot.read_text())})
    return accepted, dict(rejected)

def reconcile(audit_root, private_root, source_sha):
    inventory = read_csv(audit_root / 'source-inventory.csv')
    sites = [row for row in inventory if row.get('inventory_kind') in COUNTED_KINDS]
    if len({row['source_id'] for row in sites}) != len(sites):
        raise ValueError('Source definition IDs are not unique')
    if any(row.get('source_sha') != source_sha for row in sites):
        raise ValueError('Source inventory SHA differs from requested baseline')
    captures, rejected = capture_candidates(private_root, source_sha)
    label_sites = collections.Counter()
    for row in sites:
        label = literal_label(row.get('user_task', ''))
        for role in expected_roles(row):
            if label:
                label_sites[(row['ux_id'], role, label)] += 1
    coverage, candidates = [], []
    for row in sites:
        label, roles = literal_label(row.get('user_task', '')), expected_roles(row)
        matches = []
        if label and roles and row['inventory_kind'] != 'transition':
            for capture in captures:
                # Shell and shared presentation may be mounted across owner views.
                if row['ux_id'] not in {'UX-01', 'UX-14'} and row['ux_id'] != capture['ux']:
                    continue
                hit_roles = sorted(role for role in roles if (role, label) in capture['tree_names'])
                if hit_roles:
                    ambiguous = any(label_sites[(row['ux_id'], role, label)] > 1 for role in hit_roles)
                    evidence = f"screenshots/{capture['ux']}/{capture['public_file']}"
                    candidate = {
                        'source_id': row['source_id'], 'ux_id': row['ux_id'],
                        'journey_id': capture.get('journey', ''), 'step': capture.get('step', ''),
                        'visual_state': capture.get('state', ''), 'role': capture.get('role', ''),
                        'theme': capture.get('theme', ''),
                        'viewport': f"{capture.get('viewport', {}).get('width', '?')}x{capture.get('viewport', {}).get('height', '?')}",
                        'evidence': evidence, 'evidence_sha256': capture['public_sha256'],
                        'sanitized': str(capture['is_sanitized']).lower(),
                        'match_basis': 'exact accessible role and static name; same UX area or shared shell/component',
                        'ambiguous_source_label': str(ambiguous).lower(), 'result': 'PARTIAL',
                        'gap': 'Candidate accessibility-tree presence only; inspect screenshot viewport and source attribution; execute workflow/branch separately',
                    }
                    candidates.append(candidate)
                    matches.append(candidate)
        if matches:
            gap = 'Exact accessible role/name candidate; no click, outcome, visible viewport, or full branch proof. '
            if any(m['ambiguous_source_label'] == 'true' for m in matches):
                gap += 'Repeated source label needs manual disambiguation. '
            if any(m['sanitized'] == 'true' for m in matches):
                gap += 'Some public evidence is explicitly sanitized. '
            gap += 'All exact candidate links are in evidence-candidates.csv.'
            # Keep the main ledger navigable; complete candidate relations are in
            # the separate CSV. No candidate match is dropped from that CSV.
            sample = matches[:4]
            result = 'PARTIAL'
        else:
            sample, result = [], 'NOT RUN'
            if row['inventory_kind'] == 'transition':
                gap = 'Transition requires ordered semantic journey and return/refresh proof; no automatic label matching.'
            elif not label or not roles:
                gap = 'Dynamic/composite or unnamed source definition needs manual runtime attribution; no exact matching rule.'
            else:
                gap = 'No exact role/name candidate in eligible capture snapshots; runtime evidence remains unverified.'
        coverage.append({
            'source_id': row['source_id'], 'source_feature_control': row['source'],
            'inventory_kind': row['inventory_kind'], 'ux_id': row['ux_id'],
            'user_task': row['user_task'],
            'journey_id': '; '.join(dict.fromkeys(x['journey_id'] for x in sample)),
            'visual_state': '; '.join(dict.fromkeys(x['visual_state'] for x in sample)),
            'role_capability': row['role_capability'],
            'sampled_role_theme_viewport': '; '.join(dict.fromkeys(f"{x['role']} | {x['theme']} | {x['viewport']}" for x in sample)),
            'screenshot_evidence': '; '.join(x['evidence'] for x in sample),
            'candidate_count': len(matches), 'result': result, 'gap': gap,
            'source_sha': source_sha,
        })
    coverage_fields = ['source_id', 'source_feature_control', 'inventory_kind', 'ux_id', 'user_task',
                       'journey_id', 'visual_state', 'role_capability', 'sampled_role_theme_viewport',
                       'screenshot_evidence', 'candidate_count', 'result', 'gap', 'source_sha']
    candidate_fields = ['source_id', 'ux_id', 'journey_id', 'step', 'visual_state', 'role', 'theme', 'viewport',
                        'evidence', 'evidence_sha256', 'sanitized', 'match_basis', 'ambiguous_source_label', 'result', 'gap']
    write_csv(audit_root / 'coverage.csv', coverage_fields, coverage)
    write_csv(audit_root / 'evidence-candidates.csv', candidate_fields, candidates)
    counts = dict(collections.Counter(row['result'] for row in coverage))
    tasks = read_csv(audit_root / 'source-journeys.csv')
    branches = read_csv(audit_root / 'source-branches.csv')
    summary = {
        'source_sha': source_sha,
        'method': 'Exact static accessible role/name candidates only. No automatic PASS or semantic workflow assessment.',
        'counted_definition_kinds': sorted(COUNTED_KINDS),
        'definition_denominator': len(sites),
        'excluded_container_feedback_media_sites': len(inventory) - len(sites),
        'result_counts': counts,
        'automatic_pass_numerator': 0, 'automatic_pass_percent': 0.0,
        'partial_candidate_numerator': counts.get('PARTIAL', 0),
        'partial_candidate_percent': round(100 * counts.get('PARTIAL', 0) / len(sites), 2) if sites else None,
        'partial_candidate_percentage_is_not_completed_coverage': True,
        'source_task_denominator': len(tasks), 'source_branch_state_contract_denominator': len(branches),
        'semantic_workflows_assessed_by_this_tool': 0,
        'eligible_capture_records': len(captures), 'rejected_capture_counts': rejected,
        'candidate_evidence_relations': len(candidates),
        'privacy': 'Raw snapshots, local paths, account content and private originals are never exported. Sanitized derivatives explicitly marked.',
    }
    target = audit_root / 'coverage-summary.json'
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(summary, indent=2) + '\n')
    temporary.replace(target)
    return summary

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-root', type=Path)
    parser.add_argument('--source-sha', default=BASE_SHA)
    args = parser.parse_args()
    private_root = args.private_root or args.audit_root.resolve().parents[1] / 'qa-fixtures/runs/issue-6-audit'
    summary = reconcile(args.audit_root, private_root, args.source_sha)
    # Aggregate counts only: no private source locations or snapshot contents.
    print(json.dumps({key: summary[key] for key in ['definition_denominator', 'result_counts',
          'eligible_capture_records', 'rejected_capture_counts', 'candidate_evidence_relations']}))

if __name__ == '__main__':
    main()
