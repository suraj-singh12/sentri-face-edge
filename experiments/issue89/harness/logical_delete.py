"""EXPERIMENTAL logical Event deletion (Issue #89 alternative). Not production code.

Authority (real writes, one transaction, journaled):
  * ``experimental_deleted_events`` row (additive table; would be migration v38)
  * X's active CO_OBSERVED evidence and Sighting-Note NOTE_REFERENCE evidence
    deactivated with the existing deactivate-only transition
  * X's Sighting Notes retired / mentions deactivated (existing transitions)
  * Persons created by X without independent dependencies -> lifecycle
    DELETED (Issue #89 "Event Deleted Profiles"), same columns the existing
    Delete Person transition writes
  * biometric status refresh + graph projection rebuild (production helpers)

Current-state reads are NOT modified: the experiment measures how far the
existing evidence/lifecycle machinery already carries a logical deletion, and
lists every read surface that still exposes X (those need new filters).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta

from sentriface.models import utc_now
from sentriface.storage.sqlite_helpers import (
    _begin_journal_operation,
    _encounter_revision,
    _refresh_source_biometric_status,
    _transition_journal_operation,
)
from sentriface.storage.sqlite_store import _replace_graph_projection

from .hard_delete import EventDeletionRefused, _ids, _in, build_plan

TABLE = "experimental_deleted_events"
OPERATION_TYPE = "event.delete.logical"
def install_schema(conn) -> list[str]:
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        observation_id TEXT PRIMARY KEY REFERENCES observations(observation_id) ON DELETE RESTRICT,
        operation_id TEXT NOT NULL REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
        deleted_at TEXT NOT NULL, restore_until TEXT NOT NULL,
        linked_person_ids TEXT NOT NULL DEFAULT '[]')""")
    return [TABLE]


def activate_read_filter(store) -> None:
    """Intentionally a no-op: production read paths are measured unmodified.

    (An earlier iteration shadowed Event tables with per-connection TEMP views;
    it was abandoned because production queries rely on ``rowid`` ordering and
    ``SELECT *`` row shapes that views cannot reproduce faithfully, and because
    validators/graph rebuild share helpers with current-state reads.)"""


def delete_event(conn, oid, operation_id, *, expected_revision=None, actor=None) -> dict:
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute("SELECT operation_type FROM operation_journal WHERE operation_id = ?", (operation_id,)).fetchone()
        if existing is not None:
            row = conn.execute("SELECT details FROM operation_journal_status_history WHERE operation_id = ? AND to_status = 'COMMITTED'", (operation_id,)).fetchone()
            conn.execute("ROLLBACK")
            return {"replayed": True, **json.loads(row[0])}
        if conn.execute(f"SELECT 1 FROM {TABLE} WHERE observation_id = ?", (oid,)).fetchone():
            raise EventDeletionRefused("already_deleted", "Event is already in Deleted Events")
        row = conn.execute("SELECT status FROM observations WHERE observation_id = ?", (oid,)).fetchone()
        if row is None or row[0] != "FINALIZED":
            raise EventDeletionRefused("event_not_found", "Only finalized Events can be deleted")
        if expected_revision is not None and expected_revision != _encounter_revision(conn, oid):
            raise EventDeletionRefused("stale_revision", "Event changed; reload before deleting")
        if _ids(conn, "SELECT session_id FROM init_sessions WHERE target_observation_id = ? AND status <> 'closed'", (oid,)):
            raise EventDeletionRefused("pending_attach_media", "Finish or discard the pending Attach Media review first")
        plan = build_plan(conn, oid)
        now = utc_now()
        restore_until = (datetime.fromisoformat(now) + timedelta(days=30)).isoformat()
        _begin_journal_operation(conn, OPERATION_TYPE, operation_id=operation_id, actor=actor, source="experimental/issue-89",
                                 affected_entities=[{"entity_type": "observation", "entity_id": oid}]
                                 + [{"entity_type": "person", "entity_id": p} for p in plan.persons_erased],
                                 details={"restore_until": restore_until})
        conn.execute(f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?)", (oid, operation_id, now, restore_until, json.dumps(plan.persons_erased)))
        evidence = plan.rows.get("relationship_evidence", [])
        q, v = _in(evidence)
        deactivated = conn.execute(f"UPDATE relationship_evidence SET active = 0, deactivated_operation_id = ?, deactivated_at = ? "
                                   f"WHERE active = 1 AND evidence_id IN ({q})", (operation_id, now, *v)).rowcount
        notes = plan.rows.get("notes", [])
        mentions = retired = 0
        for note_id in notes:
            latest = conn.execute("SELECT revision_number, content, author_name FROM note_revisions WHERE note_id = ? "
                                  "ORDER BY revision_number DESC LIMIT 1", (note_id,)).fetchone()
            revision_id = str(__import__("uuid").uuid4())
            # Retirement revision (append-only) keeps the text for a possible restore but
            # carries no mention rows, so retired mentions have same-note provenance.
            conn.execute("INSERT INTO note_revisions (revision_id, note_id, revision_number, content, actor, author_name, operation_id, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (revision_id, note_id, latest[0] + 1, latest[1], json.dumps(actor or {}),
                                                             latest[2], operation_id, now))
            mentions += conn.execute("UPDATE note_mentions SET active = 0, retired_revision_id = ?, retired_operation_id = ?, retired_at = ? "
                                     "WHERE active = 1 AND note_id = ?", (revision_id, operation_id, now, note_id)).rowcount
            retired += conn.execute("UPDATE notes SET status = 'RETIRED', retired_operation_id = ?, retired_at = ? WHERE status = 'ACTIVE' AND note_id = ?",
                                    (operation_id, now, note_id)).rowcount
        people = 0
        for pid in plan.persons_erased:
            people += conn.execute("UPDATE persons SET lifecycle_status = 'DELETED', deleted_at = ?, lifecycle_changed_at = ?, restore_until = ? "
                                   "WHERE person_id = ? AND lifecycle_status = 'ACTIVE'", (now, now, restore_until, pid)).rowcount
        _refresh_source_biometric_status(conn)
        _replace_graph_projection(conn)
        result = {"observation_id": oid, "deactivated_evidence": deactivated, "retired_notes": retired, "deactivated_mentions": mentions,
                  "persons_event_deleted": plan.persons_erased, "persons_retained": plan.persons_retained,
                  "restore_until": restore_until, "physical_rows_retained": {t: len(k) for t, k in plan.rows.items()}}
        _transition_journal_operation(conn, operation_id, "COMMITTED", result)
        conn.execute("COMMIT")
        return result
    except Exception:
        conn.execute("ROLLBACK")
        raise
