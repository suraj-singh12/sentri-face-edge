"""Run one A / B / B' differential experiment.

    python -m experiments.issue89.run_scenario S1 [--mechanism hard|logical]

Steps (all against real application authorities):
  1. Build Database A (control) and measure it.
  2. Apply the experimental schema extension to A (schema parity with B') and
     re-measure (A*). A vs A* isolates the effect of the migration itself.
  3. Build Database B (experimental) and measure it.
  4. H0: probe the unmodified-schema delete plan (rolled back) -> blockers.
  5. Delete Event X through POST /api/experimental/event-delete (real auth,
     pre-delete safety backup, index rebuild) -> Database B'.
  6. Measure B' and compare with A*.
  7. Subsequent normal operations on both A* and B' (identical steps), restart,
     graph rebuild, integrity check, backup + restore; re-compare.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from .build import RUNS, authority, build, save
from .harness import compare, experimental_api, hard_delete, logical_delete, measure, read_fixes
from .harness.app import App
from .harness.env import DET
from .harness.workflows import EventSpec, Operator
from .scenarios import PROBES, SCENARIOS

EVIDENCE = Path(__file__).resolve().parent / "evidence"


def _schema(app, mechanism):
    with app.store._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = (hard_delete.install_guarded_erasure_schema(conn) if mechanism == "hard"
                   else logical_delete.install_schema(conn))
        conn.execute("COMMIT")
    if mechanism == "logical":
        logical_delete.activate_read_filter(app.store)
    return changed


def delete_via_api(app: App, oid: str, operation_id: str | None = None, *, expected_revision="current", cookie=True):
    if expected_revision == "current":
        status, read = app.request("GET", f"/api/encounter?observation_id={oid}", expect=None, cookie=cookie)
        revision = read.get("revision") if isinstance(read, dict) else None
    else:
        revision = expected_revision
    with DET.step("delete", "2026-05-30T12:00:00+00:00"):
        return app.request("POST", experimental_api.PATH, {"observation_id": oid, "operation_id": operation_id or str(uuid.uuid4()),
                                                          "expected_revision": revision}, expect=None, cookie=cookie)


def later_operations(op: Operator, label: str):
    """Identical subsequent normal operations, applied to A* and B'."""
    with DET.step(f"{label}.later-event", "2026-06-02T09:00:00+00:00"):
        op.create_event(EventSpec(f"{label}.later", ["alder-5", "iris-6"], "2026-05-28", "Delhi", f"Later-{label}"))
    with DET.step(f"{label}.later-note", "2026-06-02T10:00:00+00:00"):
        op.person_note("Iris", f"Later note ({label}) about @Birch", ["Birch"])


VARIANTS = {  # mechanism, journal policy, candidate read/proposal fixes
    "H1": ("hard", "retain", False),
    "H1b": ("hard", "revert", False),
    "H2": ("hard", "revert", True),
    "L": ("logical", None, True),
}


def run(sid: str, variant: str = "H2", *, post_ops=True) -> dict:
    scenario = SCENARIOS[sid]
    mechanism, journal_policy, fixes = VARIANTS[variant]
    experimental_api.install(mechanism, fixes)
    if journal_policy:
        hard_delete.JOURNAL_POLICY["value"] = journal_policy
    if fixes:
        read_fixes.install()
    tag = f"{sid}-{variant}"
    report = {"scenario": sid, "title": scenario.title, "mechanism": mechanism, "variant": variant, "covers": scenario.covers,
              "counterfactual": scenario.counterfactual, "timings": {}}
    t0 = time.time()
    build(sid, "A")
    a = App(authority(sid, "A")).start()
    report["timings"]["build_A"] = round(time.time() - t0, 1)
    m_a_raw = measure.measure_all(a, PROBES)
    report["schema_changes"] = _schema(a, mechanism)
    m_a = measure.measure_all(a, PROBES)
    report["A_vs_Astar"] = compare.summary(compare.compare(m_a_raw, m_a))
    t0 = time.time()
    build(sid, "B")
    b = App(authority(sid, "B")).start()
    report["timings"]["build_B"] = round(time.time() - t0, 1)
    op_b = Operator(b)
    m_b = measure.measure_all(b, PROBES)
    oid = op_b.event_id(scenario.x_occasion)
    report["x_observation_id"] = oid
    for db in ("A", "B"):
        probe_file = authority(sid, db).parent / "probes.json"
        report[f"probes_{db}"] = json.loads(probe_file.read_text()) if probe_file.exists() else {}
    with b.store._connect() as conn:
        report["H0_unmodified_schema_probe"] = hard_delete.probe_constraints(conn, oid)
    tokens = x_tokens(b, oid)
    report["x_tokens"] = {k: len(v) for k, v in tokens.items()}
    _schema(b, mechanism)
    if scenario.before_delete:
        report["before_delete"] = scenario.before_delete(b, Operator(b), oid)
    status, result = delete_via_api(b, oid)
    report["delete_status"], report["delete_result"] = status, result
    m_b2 = measure.measure_all(b, PROBES)
    report["residual_x_content"] = residual_scan(b, tokens)
    report["backups_after_delete"] = [x.get("backup_id") for x in b.get("/api/backups")["backups"]]
    report["A_vs_B"] = compare.summary(compare.compare(m_a, m_b))
    full = compare.compare(m_a, m_b2)
    report["A_vs_Bprime"] = compare.summary(full)
    report["A_vs_Bprime_detail"] = full
    report["B_vs_Bprime"] = compare.summary(compare.compare(m_b, m_b2))
    save(RUNS / sid / f"measure-{variant}.pkl", {"A": m_a, "A_raw": m_a_raw, "B": m_b, "Bprime": m_b2})
    out = EVIDENCE / tag
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    if post_ops:
        try:
            report["post"] = post_deletion_checks(a, b, sid, mechanism)
        except Exception as exc:  # recorded as an experimental failure, never hidden
            import traceback
            report["post_error"] = traceback.format_exc()[-3000:]
    a.stop(), b.stop()
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


def x_tokens(app: App, oid: str) -> dict:
    """Identifiers and content that exist only because of Event X (from B before deletion)."""
    with app.store._connect() as conn:
        ctx = json.loads(conn.execute("SELECT context FROM observations WHERE observation_id=?", (oid,)).fetchone()[0] or "{}")
        q = lambda sql, *p: [r[0] for r in conn.execute(sql, p).fetchall() if r[0]]  # noqa: E731
        reviews = q("SELECT review_id FROM photo_reviews WHERE observation_id=? OR target_observation_id=?", oid, oid)
        details = q("SELECT detail_id FROM recognition_details WHERE observation_id=?", oid)
        tokens = {
            "observation_id": [oid], "review_ids": reviews,
            "media_ids": q("SELECT media_id FROM observation_media WHERE observation_id=?", oid),
            "embedding_ids": q("SELECT embedding_id FROM observation_face_assignments WHERE observation_id=?", oid),
            "event_text": [v for v in (ctx.get("event_notes"),) if v and len(v) > 6],
            "sighting_note_text": q(f"SELECT r.content FROM note_revisions r JOIN notes n ON n.note_id=r.note_id WHERE n.subject_type='RECOGNITION_DETAIL' AND n.subject_id IN ({','.join('?'*len(details)) or 'NULL'})", *details),
        }
    return tokens


def residual_scan(app: App, tokens: dict) -> dict:
    """Where do X-only identifiers/content still occur in B' (table.column -> count)?"""
    found = {}
    with app.store._connect() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            columns = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            for row in conn.execute(f"SELECT * FROM {table}"):
                for column, value in zip(columns, row):
                    if not isinstance(value, str):
                        continue
                    for kind, values in tokens.items():
                        if any(v in value for v in values):
                            key = f"{kind} @ {table}.{column}"
                            found[key] = found.get(key, 0) + 1
    return found


def post_deletion_checks(a: App, b: App, sid: str, mechanism: str) -> dict:
    results = {}
    op_a, op_b = Operator(a), Operator(b)
    # 1. Restart both applications (reload index from SQLite).
    a.restart(), b.restart()
    if mechanism == "logical":
        logical_delete.activate_read_filter(a.store), logical_delete.activate_read_filter(b.store)
    ma, mb = measure.measure_all(a, PROBES), measure.measure_all(b, PROBES)
    results["after_restart"] = compare.summary(compare.compare(ma, mb))
    # 2. Graph projection rebuild through the integrity recovery API, then compare.
    for app in (a, b):
        with DET.step("rebuild", "2026-06-01T08:00:00+00:00"):
            report = app.post("/api/integrity/check")
            action = next((x for x in report.get("actions", []) if "GRAPH" in json.dumps(x).upper()), None)
            results.setdefault("graph_rebuild_actions", []).append(action and action.get("action_id"))
            if action:
                prepared = app.post("/api/integrity/graph-rebuild/prepare", {"report_token": report["report_token"], "action_id": action["action_id"]})
                app.post("/api/integrity/graph-rebuild/execute", {"token": prepared["token"], "operation_id": str(uuid.uuid4()), "reason": "Issue 89 rebuild check"})
    # 2b. Explicit P11-B graph projection rebuild command (store API) on both.
    for app in (a, b):
        with DET.step("rebuild-cmd", "2026-06-01T08:30:00+00:00"):
            try:
                results.setdefault("graph_rebuild_command", []).append(app.store.rebuild_graph_projection(str(uuid.uuid4()), reason="Issue 89 rebuild check"))
            except Exception as exc:  # refusal is a measured outcome
                results.setdefault("graph_rebuild_command", []).append({"refused": type(exc).__name__, "message": str(exc)[:300]})
    ma, mb = measure.measure_all(a, PROBES), measure.measure_all(b, PROBES)
    results["after_graph_rebuild"] = compare.summary(compare.compare(ma, mb))
    # 3. Identical later normal operations on both.
    for op in (op_a, op_b):
        later_operations(op, "post")
    ma, mb = measure.measure_all(a, PROBES), measure.measure_all(b, PROBES)
    results["after_later_operations"] = compare.summary(compare.compare(ma, mb))
    # 4. Backup + restore of each, compare.
    for app in (a, b):
        with DET.step("backup", "2026-06-03T08:00:00+00:00"):
            backup = app.post("/api/backup-db", {})
        backup_id = (backup.get("backup") or backup).get("backup_id")
        with DET.step("restore", "2026-06-03T09:00:00+00:00"):
            restored = app.request("POST", "/api/backups/restore", {"backup_id": backup_id, "operation_id": str(uuid.uuid4()),
                                                                  "reason": "issue-89 restore check"}, expect=None)
        results.setdefault("restore_status", []).append(restored[0] if isinstance(restored, tuple) else restored)
        if isinstance(restored, tuple) and restored[0] != 200:
            results.setdefault("restore_errors", []).append(restored[1])
    if mechanism == "logical":
        logical_delete.activate_read_filter(a.store), logical_delete.activate_read_filter(b.store)
    a.restart(), b.restart()
    if mechanism == "logical":
        logical_delete.activate_read_filter(a.store), logical_delete.activate_read_filter(b.store)
    ma, mb = measure.measure_all(a, PROBES), measure.measure_all(b, PROBES)
    results["after_backup_restore"] = compare.summary(compare.compare(ma, mb))
    results["after_backup_restore_detail_api"] = {k: v for k, v in compare.compare(ma, mb)["api"].items() if not v["equal"]}
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sid")
    parser.add_argument("--variant", default="H2", choices=sorted(VARIANTS))
    parser.add_argument("--no-post", action="store_true")
    args = parser.parse_args()
    report = run(args.sid, args.variant, post_ops=not args.no_post)
    print(json.dumps({k: v for k, v in report.items() if k not in {"A_vs_Bprime_detail"}}, indent=1, default=str)[:20000])
