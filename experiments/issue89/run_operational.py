"""S9 operational edge cases for the experimental hard deletion (H2), on the S1 world.

    python -m experiments.issue89.run_operational

Each probe is executed against a real application authority; outcomes are
recorded as measured (status codes, row/file comparisons), never assumed.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from .build import authority, build
from .harness import compare, experimental_api, hard_delete, measure, read_fixes
from .harness.app import App
from .harness.env import DET
from .harness.workflows import EventSpec, Operator
from .run_scenario import EVIDENCE, _schema, delete_via_api
from .scenarios import PROBES

SID = "S1"


def _user_cookie(app: App, username: str, role: str) -> str:
    from sentriface.auth import AUTH_COOKIE_NAME
    auth = app.server.auth
    admin = auth.authenticate(app.cookie.split("=", 1)[1], app.window)
    auth.create_user(admin, username, username.title(), f"{username} password 8989", [role])
    with auth._connect() as conn:  # same seam as tests/api_auth_helpers.clear_required_password
        conn.execute("UPDATE app_users SET must_change_password = 0 WHERE username = ?", (username,))
    _, token = auth.login(username, f"{username} password 8989", window_id=app.window)
    return f"{AUTH_COOKIE_NAME}={token}"


def run() -> dict:
    experimental_api.install("hard", fixes=True)
    hard_delete.JOURNAL_POLICY["value"] = "revert"
    read_fixes.install()
    out: dict = {}
    build(SID, "A")
    a = App(authority(SID, "A")).start()
    _schema(a, "hard")
    m_a = measure.measure_all(a, PROBES)
    a.stop()
    build(SID, "B")
    b = App(authority(SID, "B")).start()
    _schema(b, "hard")
    op = Operator(b)
    oid = op.event_id("Event-X")
    m_b0 = measure.measure_all(b, PROBES)

    # 1. Pending Attach Media blocks deletion; discarding the draft unblocks it.
    with DET.step("S9.attach", "2026-05-21T09:00:00+00:00"):
        pending = op.create_event(EventSpec("S9.attach", ["hazel-3"], "", "", ""), attach_to=oid, finish=False)
    status, body = delete_via_api(b, oid)
    out["pending_attach"] = {"status": status, "code": body.get("code")}
    with DET.step("S9.attach-discard", "2026-05-21T10:00:00+00:00"):
        b.request("DELETE", f"/api/queue-session?session_id={pending['session_id']}")
    m_after_discard = measure.measure_all(b, PROBES)
    out["attach_discard_restores_B"] = compare.summary(compare.compare(m_b0, m_after_discard))

    # 2. Unauthorized roles (server-side capability check).
    for role in ("viewer", "operator", "technician"):
        cookie = _user_cookie(b, f"probe{role}", role)
        status, body = delete_via_api(b, oid, cookie=cookie)
        out[f"unauthorized_{role}"] = {"status": status, "code": body.get("code") if isinstance(body, dict) else body}
        b._sign_in()  # SentriFace allows one signed-in window: sign the custodian back in
    status, body = delete_via_api(b, oid, cookie=False)
    out["unauthenticated"] = {"status": status, "code": body.get("code") if isinstance(body, dict) else None}

    # 3. Stale request: revision read, Event changes, then delete with the old revision.
    stale_revision = b.get(f"/api/encounter?observation_id={oid}")["revision"]
    with DET.step("S9.amend", "2026-05-21T11:00:00+00:00"):
        op.amend_location("Event-X", "Goa North")
    status, body = delete_via_api(b, oid, expected_revision=stale_revision)
    out["stale_revision"] = {"status": status, "code": body.get("code")}
    m_b1 = measure.measure_all(b, PROBES)

    # 4. Transaction failure mid-plan: everything rolls back, no file touched.
    failures = {}
    for table in ("observation_media", "observations", "persons"):
        with b.store._connect() as conn:
            try:
                hard_delete.hard_delete_event(conn, oid, str(uuid.uuid4()), expected_revision=None, fail_after=table)
            except RuntimeError as exc:
                failures[table] = str(exc)
        failures[f"{table}.equal_after_rollback"] = compare.summary(compare.compare(m_b1, measure.measure_all(b, PROBES)))
    out["transaction_failure"] = failures

    # 5. Interruption after COMMIT, before file cleanup and before index rebuild.
    with b.store._connect() as conn:
        journal = b.engine.cleanup.schedule(hard_delete.cleanup_targets(conn, oid, b.engine.config), "event-erase-crash")
    crash_op = str(uuid.uuid4())
    with DET.step("delete", "2026-05-30T12:00:00+00:00"), b.store._connect() as conn:
        out["crash_delete_result_keys"] = sorted(hard_delete.hard_delete_event(conn, oid, crash_op, expected_revision=None))
    # Query the live in-memory index directly (measure.recognition would rebuild it).
    probe_dir = b.data_dir.parent / measure.PROBE_DIR_NAME
    stale = b.post("/api/recognize-batch", {"path": str(probe_dir), "quality_only": True})
    out["stale_index_recognition"] = [{"probe": Path(i["image"]).stem, "matches": [(m["name"], round(m["score"], 4)) for m in f["matches"][:2]]}
                                      for i in stale["batch"] for f in i["faces"]]
    out["stale_index_has_erased_people"] = sorted({m[0] for r in out["stale_index_recognition"] for m in r["matches"]} & {"Fir", "Ginkgo", "Kauri", "unknown"})
    with b.store._connect() as conn:
        out["index_vs_db"] = {"index_backend": b.engine.index_status, "db_embeddings": conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]}
    m_crash = measure.measure_all(b, PROBES)
    out["after_crash_vs_A"] = compare.summary(compare.compare(m_a, m_crash))
    out["cleanup_journal_pending"] = bool(journal and journal.exists())
    b.restart()  # startup runs CleanupService.retry_all and rebuilds the index
    m_restart = measure.measure_all(b, PROBES)
    out["after_restart_vs_A"] = compare.summary(compare.compare(m_a, m_restart))
    out["cleanup_journal_after_restart"] = bool(journal and journal.exists())

    # 6. Repeated requests.
    status, body = delete_via_api(b, oid, operation_id=crash_op)
    out["replay_same_operation"] = {"status": status, "replayed": body.get("replayed")}
    status, body = delete_via_api(b, oid, expected_revision=None)
    out["repeat_new_operation"] = {"status": status, "code": body.get("code")}

    # 7. Older backup: the pre-delete safety backup still contains X (by design).
    backups = b.get("/api/backups")["backups"]
    out["backups"] = [(x["backup_id"], x.get("reason")) for x in backups]
    older = next((x for x in backups if "before" in str(x.get("reason") or x["backup_id"])), backups[-1])
    with DET.step("S9.restore-old", "2026-06-05T09:00:00+00:00"):
        status, body = b.request("POST", "/api/backups/restore", {"backup_id": older["backup_id"], "operation_id": str(uuid.uuid4()),
                                                                 "reason": "S9 older backup"}, expect=None)
    b.restart()
    m_old = measure.measure_all(b, PROBES)
    out["restore_older_backup"] = {"status": status, "x_present": any("Event-X" in k for k in m_old["api"]),
                                   "vs_A": compare.summary(compare.compare(m_a, m_old))}
    b.stop()
    path = EVIDENCE / "S9-operational"
    path.mkdir(parents=True, exist_ok=True)
    (path / "report.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str)[:20000])
