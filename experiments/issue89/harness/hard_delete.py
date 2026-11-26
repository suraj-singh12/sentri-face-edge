"""EXPERIMENTAL permanent Event deletion (Issue #89). Not production code.

Two mechanisms are evaluated:

H0  ``probe_constraints``: run the dependency-ordered DELETE plan against the
    unmodified v37 schema, one SAVEPOINT per statement, and record exactly
    which trigger / foreign key aborts each statement. Always rolled back.

H1  ``hard_delete_event``: the minimal guarded alternative. An experimental
    additive schema extension (would be migration v38) adds
    ``experimental_event_erasure_rows`` and re-creates each append-only
    *no-delete* trigger with one extra condition: the delete is permitted only
    for a row that was enumerated for an ``event.erase`` operation whose
    journal entry is STARTED in the same transaction. Every other delete keeps
    aborting exactly as before; foreign keys stay ON; nothing is disabled or
    dropped for the duration of the operation. The plan rows are removed
    again before COMMIT.

The planner derives everything from authoritative records of Event X (never
from Database A): its reviews, face assignments, revisions, corrections,
evidence, Sighting Notes, staged sessions and immutable ACCEPT_NEW_PERSON
decisions (creation provenance). Production helpers are reused read-only or
as normal write helpers: eligibility/biometric refresh, graph projection,
journal begin/transition.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from sentriface.media_registry import MEDIA_AUTHORITY_REGISTRY
from sentriface.storage.sqlite_helpers import (
    _begin_journal_operation,
    _encounter_revision,
    _refresh_source_biometric_status,
    _transition_journal_operation,
    _validate_graph_projection,
)
from sentriface.storage.sqlite_store import _replace_graph_projection

ERASURE_TABLE = "experimental_event_erasure_rows"
OPERATION_TYPE = "event.erase"

# table -> (no-delete trigger name, SQL expression naming the OLD row key)
GUARDED_TRIGGERS = {
    "observations": ("observations_no_delete", "OLD.observation_id"),
    "observation_media": ("observation_media_draft_delete", "OLD.observation_id || '|' || OLD.media_id"),
    "observation_participants": ("observation_participants_draft_delete", "OLD.observation_id || '|' || OLD.person_id"),
    "observation_face_assignments": ("observation_face_assignments_no_delete", "OLD.assignment_id"),
    "encounter_metadata_revisions": ("encounter_metadata_no_delete", "OLD.revision_id"),
    "encounter_participant_revisions": ("encounter_participant_revision_no_delete", "OLD.revision_id"),
    "identity_corrections": ("identity_corrections_no_delete", "OLD.correction_id"),
    "relationship_evidence": ("relationship_evidence_no_delete", "OLD.evidence_id"),
    "notes": ("notes_no_delete", "OLD.note_id"),
    "note_revisions": ("note_revisions_no_delete", "OLD.revision_id"),
    "note_revision_mentions": ("note_revision_mentions_no_delete", "OLD.revision_id || '|' || OLD.referenced_person_id"),
    "note_mentions": ("note_mentions_no_delete", "OLD.mention_id"),
}

KEY_SQL = {  # same keys, as SELECT expressions (no OLD.)
    table: expr.replace("OLD.", "") for table, (_, expr) in GUARDED_TRIGGERS.items()
}


class EventDeletionRefused(RuntimeError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code, self.details = code, details


# ------------------------------------------------------------------ schema
def install_guarded_erasure_schema(conn: sqlite3.Connection) -> list[str]:
    """Experimental additive migration (v38-exp). Idempotent. Returns changed triggers."""
    changed = []
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {ERASURE_TABLE} (
        operation_id TEXT NOT NULL REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
        table_name TEXT NOT NULL, row_key TEXT NOT NULL,
        PRIMARY KEY (operation_id, table_name, row_key))""")
    conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {ERASURE_TABLE}_require_started_journal
        BEFORE INSERT ON {ERASURE_TABLE}
        WHEN NOT EXISTS (SELECT 1 FROM operation_journal j WHERE j.operation_id = NEW.operation_id
                         AND j.operation_type = '{OPERATION_TYPE}' AND j.status = 'STARTED')
        BEGIN SELECT RAISE(ABORT, 'event erasure rows require a STARTED event.erase journal'); END""")
    for table, (trigger, key) in GUARDED_TRIGGERS.items():
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (trigger,)).fetchone()[0]
        if ERASURE_TABLE in sql:
            continue
        guard = (f"NOT EXISTS (SELECT 1 FROM {ERASURE_TABLE} e JOIN operation_journal j ON j.operation_id = e.operation_id "
                 f"WHERE j.status = 'STARTED' AND e.table_name = '{table}' AND e.row_key = {key})")
        head, body = sql.split("BEGIN", 1)
        if " WHEN " in head.upper().replace("\n", " "):
            index = head.upper().index("WHEN")
            head = head[:index] + "WHEN (" + head[index + 4:].strip() + f") AND {guard} "
        else:
            head = head.rstrip() + f" WHEN {guard} "
        conn.execute(f"DROP TRIGGER {trigger}")
        conn.execute(head + "BEGIN" + body)
        changed.append(trigger)
    return changed


# ------------------------------------------------------------------- plan
@dataclass
class Plan:
    observation_id: str
    rows: dict[str, list[str]] = field(default_factory=dict)     # table -> keys (guarded or plain)
    persons_erased: list[str] = field(default_factory=list)
    persons_retained: dict[str, list[str]] = field(default_factory=dict)  # person -> reasons
    embeddings_erased: list[str] = field(default_factory=list)
    embeddings_retained: dict[str, list[str]] = field(default_factory=dict)
    candidate_files: list[str] = field(default_factory=list)

    def add(self, table, keys):
        bucket = self.rows.setdefault(table, [])
        for key in keys:
            if key is not None and key not in bucket:
                bucket.append(str(key))


def _ids(conn, sql, params=()):
    return [r[0] for r in conn.execute(sql, params).fetchall()]


def _in(values):
    values = list(values)
    return ",".join("?" * len(values)) or "NULL", values


def created_persons(conn, oid: str) -> list[str]:
    """Persons created by X: immutable ACCEPT_NEW_PERSON decisions of X's reviews,
    resolved through X's own face assignment (original_person_id)."""
    return sorted(set(_ids(conn, """
        SELECT a.original_person_id FROM observation_face_assignments a
        JOIN photo_review_faces f ON f.review_id = a.review_id AND f.face_id = a.face_id
        WHERE a.observation_id = ? AND f.decision = 'ACCEPT_NEW_PERSON'""", (oid,))))


def person_dependencies(conn, pid: str, oid: str, plan: Plan) -> list[str]:
    """Independent data that keeps a Person created by X (reasons; empty = erasable)."""
    reasons = []
    checks = {
        "participates in another Event": ("SELECT DISTINCT observation_id FROM observation_participants WHERE person_id = ? AND observation_id <> ?", (pid, oid)),
        "face assignment in another Event": ("SELECT assignment_id FROM observation_face_assignments WHERE original_person_id = ? AND observation_id <> ?", (pid, oid)),
        "correction target in another Event": ("SELECT correction_id FROM identity_corrections WHERE (to_person_id = ? OR from_person_id = ?) AND observation_id IS NOT ? AND observation_id <> ?", (pid, pid, oid, oid)),
        "participant revision in another Event": ("SELECT revision_id FROM encounter_participant_revisions WHERE person_id = ? AND observation_id <> ?", (pid, oid)),
        "Reference Only / enrollment sample": ("SELECT enrollment_id FROM biometric_enrollment_history WHERE person_id = ?", (pid,)),
        "owns notes outside X": ("SELECT note_id FROM notes WHERE owner_person_id = ? AND note_id NOT IN (%s)" % _in(plan.rows.get("notes", []))[0], (pid, *plan.rows.get("notes", []))),
        "mentioned in a note outside X": ("SELECT mention_id FROM note_mentions WHERE referenced_person_id = ? AND note_id NOT IN (%s)" % _in(plan.rows.get("notes", []))[0], (pid, *plan.rows.get("notes", []))),
        "Manual Association": ("SELECT evidence_id FROM relationship_evidence WHERE evidence_type = 'MANUAL_ASSERTION' AND (source_person_id = ? OR target_person_id = ?)", (pid, pid)),
        "merge history": ("SELECT merge_operation_id FROM merge_operations WHERE source_person_id = ? OR target_person_id = ?", (pid, pid)),
        "canonical target of another Person": ("SELECT person_id FROM persons WHERE canonical_person_id = ?", (pid,)),
        "profile edit history": ("SELECT change_id FROM person_change_history WHERE person_id = ?", (pid,)),
        "lifecycle operation history": ("SELECT operation_id FROM operation_journal WHERE operation_type LIKE 'identity.%' AND operation_type NOT IN ('identity.face.add') AND affected_entities LIKE ?", (f'%"{pid}"%',)),
        "embedding owned outside X": ("SELECT embedding_id FROM embeddings WHERE person_id = ? AND embedding_id NOT IN (SELECT embedding_id FROM observation_face_assignments WHERE observation_id = ?)", (pid, oid)),
        "staged in an unfinished review": ("SELECT review_id FROM photo_review_faces WHERE person_id = ? AND review_id IN (SELECT review_id FROM photo_reviews WHERE status = 'IN_PROGRESS')", (pid,)),
    }
    for reason, (sql, params) in checks.items():
        found = _ids(conn, sql, params)
        if found:
            reasons.append(f"{reason} ({len(found)})")
    for row in conn.execute("SELECT observation_id, context FROM observations WHERE observation_id <> ?", (oid,)):
        if pid in (json.loads(row[1] or "{}").get("event_mentioned_person_ids") or []):
            reasons.append("selected Event Note mention in another Event")
    for row in conn.execute("SELECT observation_id, context FROM encounter_metadata_revisions WHERE observation_id <> ?", (oid,)):
        if pid in (json.loads(row[1] or "{}").get("event_mentioned_person_ids") or []):
            reasons.append("selected Event Note mention in another Event revision")
    person = conn.execute("SELECT lifecycle_status FROM persons WHERE person_id = ?", (pid,)).fetchone()
    if person and person[0] != "ACTIVE":
        reasons.append(f"lifecycle {person[0]}")
    return reasons


def build_plan(conn, oid: str) -> Plan:
    plan = Plan(oid)
    reviews = _ids(conn, "SELECT review_id FROM photo_reviews WHERE observation_id = ? OR target_observation_id = ?", (oid, oid))
    rq, rv = _in(reviews)
    sessions = sorted(set(_ids(conn, f"SELECT session_id FROM photo_reviews WHERE review_id IN ({rq}) AND session_id IS NOT NULL", rv)
                          + _ids(conn, "SELECT session_id FROM init_sessions WHERE target_observation_id = ?", (oid,))))
    plan.add("observations", [oid])
    plan.add("observation_media", _ids(conn, f"SELECT {KEY_SQL['observation_media']} FROM observation_media WHERE observation_id = ?", (oid,)))
    plan.add("observation_participants", _ids(conn, f"SELECT {KEY_SQL['observation_participants']} FROM observation_participants WHERE observation_id = ?", (oid,)))
    plan.add("observation_face_assignments", _ids(conn, "SELECT assignment_id FROM observation_face_assignments WHERE observation_id = ?", (oid,)))
    plan.add("encounter_metadata_revisions", _ids(conn, "SELECT revision_id FROM encounter_metadata_revisions WHERE observation_id = ?", (oid,)))
    plan.add("encounter_participant_revisions", _ids(conn, "SELECT revision_id FROM encounter_participant_revisions WHERE observation_id = ?", (oid,)))
    plan.add("encounter_relation_decisions", _ids(conn, f"SELECT decision_id FROM encounter_relation_decisions WHERE observation_id = ? OR review_id IN ({rq})", (oid, *rv)))
    plan.add("identity_corrections", _ids(conn, "SELECT correction_id FROM identity_corrections WHERE observation_id = ?", (oid,)))
    details = _ids(conn, "SELECT detail_id FROM recognition_details WHERE observation_id = ?", (oid,))
    plan.add("recognition_details", details)
    dq, dv = _in(details)
    notes = _ids(conn, f"SELECT note_id FROM notes WHERE subject_type = 'RECOGNITION_DETAIL' AND subject_id IN ({dq})", dv)
    plan.add("notes", notes)
    nq, nv = _in(notes)
    revisions = _ids(conn, f"SELECT revision_id FROM note_revisions WHERE note_id IN ({nq})", nv)
    plan.add("note_revisions", revisions)
    vq, vv = _in(revisions)
    plan.add("note_revision_mentions", _ids(conn, f"SELECT {KEY_SQL['note_revision_mentions']} FROM note_revision_mentions WHERE revision_id IN ({vq})", vv))
    mentions = _ids(conn, f"SELECT mention_id FROM note_mentions WHERE note_id IN ({nq})", nv)
    plan.add("note_mentions", mentions)
    mq, mv = _in(mentions)
    plan.add("relationship_evidence", _ids(conn, "SELECT evidence_id FROM relationship_evidence WHERE evidence_type = 'CO_OBSERVED' AND source_entity_type = 'OBSERVATION' AND source_entity_id = ?", (oid,)))
    plan.add("relationship_evidence", _ids(conn, f"SELECT evidence_id FROM relationship_evidence WHERE evidence_type = 'NOTE_REFERENCE' AND source_entity_type = 'NOTE' AND source_entity_id IN ({mq})", mv))
    plan.add("photo_review_media", _ids(conn, f"SELECT review_id || '|' || media_id FROM photo_review_media WHERE review_id IN ({rq})", rv))
    plan.add("photo_review_faces", _ids(conn, f"SELECT review_id || '|' || face_id FROM photo_review_faces WHERE review_id IN ({rq})", rv))
    plan.add("photo_reviews", reviews)
    sq, sv = _in(sessions)
    plan.add("init_face_person_exclusions", _ids(conn, f"SELECT session_id || '|' || init_face_id || '|' || person_id FROM init_face_person_exclusions WHERE session_id IN ({sq})", sv))
    plan.add("init_faces", _ids(conn, f"SELECT init_face_id FROM init_faces WHERE session_id IN ({sq})", sv))
    plan.add("init_groups", _ids(conn, f"SELECT session_id || '|' || group_id FROM init_groups WHERE session_id IN ({sq})", sv))
    plan.add("init_session_media", _ids(conn, f"SELECT session_id || '|' || media_id FROM init_session_media WHERE session_id IN ({sq})", sv))
    plan.add("init_sessions", sessions)
    # Biometric samples: erase X's samples unless another authority still owns them.
    aq, av = _in(plan.rows["observation_face_assignments"])
    for eid in sorted(set(_ids(conn, f"SELECT embedding_id FROM observation_face_assignments WHERE assignment_id IN ({aq})", av))):
        reasons = []
        if _ids(conn, "SELECT 1 FROM observation_face_assignments WHERE embedding_id = ? AND observation_id <> ?", (eid, oid)):
            reasons.append("face assignment in another Event")
        if _ids(conn, "SELECT 1 FROM biometric_enrollment_history WHERE embedding_id = ?", (eid,)):
            reasons.append("Reference Only / enrollment source")
        if _ids(conn, "SELECT 1 FROM identity_corrections WHERE embedding_id = ? AND (observation_id IS NULL OR observation_id <> ?)", (eid, oid)):
            reasons.append("correction outside X")
        if _ids(conn, f"SELECT 1 FROM recognition_details WHERE embedding_id = ? AND detail_id NOT IN ({dq})", (eid, *dv)):
            reasons.append("historical recognition outside X")
        if reasons:
            plan.embeddings_retained[eid] = reasons
        else:
            plan.embeddings_erased.append(eid)
    plan.add("embeddings", plan.embeddings_erased)
    # Persons created by X.
    for pid in created_persons(conn, oid):
        reasons = person_dependencies(conn, pid, oid, plan)
        if reasons:
            plan.persons_retained[pid] = reasons
        else:
            plan.persons_erased.append(pid)
    pq, pv = _in(plan.persons_erased)
    plan.add("person_change_history", _ids(conn, f"SELECT change_id FROM person_change_history WHERE person_id IN ({pq})", pv))
    plan.add("persons", plan.persons_erased)
    # Physical candidates (decided after commit by live reference check).
    files = set(_ids(conn, "SELECT media_path FROM observation_media WHERE observation_id = ?", (oid,)))
    eq, ev = _in(plan.embeddings_erased)
    for column in ("source_image", "crop_path"):
        files.update(_ids(conn, f"SELECT {column} FROM embeddings WHERE embedding_id IN ({eq})", ev))
    for column in ("source_image", "crop_path"):
        files.update(_ids(conn, f"SELECT {column} FROM init_faces WHERE session_id IN ({sq})", sv))
    files.update(_ids(conn, f"SELECT image_path FROM recognition_details WHERE detail_id IN ({dq})", dv))
    files.update(_ids(conn, f"SELECT media_path FROM photo_review_media WHERE review_id IN ({rq})", rv))
    files.update(_ids(conn, f"SELECT media_path FROM init_session_media WHERE session_id IN ({sq})", sv))
    plan.candidate_files = sorted(f for f in files if f)
    plan.session_source_paths = _ids(conn, f"SELECT source_path FROM init_sessions WHERE session_id IN ({sq})", sv)
    return plan


# Deletion order (children before parents). Plain tables have no no-delete trigger.
ORDER = [
    ("relationship_evidence", "evidence_id"),
    ("note_revision_mentions", KEY_SQL["note_revision_mentions"]),
    ("note_mentions", "mention_id"),
    ("note_revisions", "revision_id"),
    ("notes", "note_id"),
    ("identity_corrections", "correction_id"),
    ("encounter_relation_decisions", "decision_id"),
    ("encounter_participant_revisions", "revision_id"),
    ("encounter_metadata_revisions", "revision_id"),
    ("observation_face_assignments", "assignment_id"),
    ("observation_participants", KEY_SQL["observation_participants"]),
    ("observation_media", KEY_SQL["observation_media"]),
    ("recognition_details", "detail_id"),
    ("photo_review_media", "review_id || '|' || media_id"),
    ("photo_review_faces", "review_id || '|' || face_id"),
    ("photo_reviews", "review_id"),
    ("init_face_person_exclusions", "session_id || '|' || init_face_id || '|' || person_id"),
    ("init_faces", "init_face_id"),
    ("init_groups", "session_id || '|' || group_id"),
    ("init_session_media", "session_id || '|' || media_id"),
    ("init_sessions", "session_id"),
    ("observations", "observation_id"),
    ("embeddings", "embedding_id"),
    ("person_change_history", "change_id"),
    ("graph_connections", None),
    ("persons", "person_id"),
]


def _delete(conn, table, key_sql, keys):
    total = 0
    for start in range(0, len(keys), 200):
        chunk = keys[start:start + 200]
        q, v = _in(chunk)
        total += conn.execute(f"DELETE FROM {table} WHERE {key_sql} IN ({q})", v).rowcount
    return total


def _delete_projection_rows(conn, persons):
    q, v = _in(persons)
    return conn.execute(f"DELETE FROM graph_connections WHERE source_person_id IN ({q}) OR target_person_id IN ({q})", v + v).rowcount


def _remaining_children(conn, table, keys):
    """Which FK child tables still hold rows pointing at the planned parent keys."""
    found = {}
    pk = {"photo_reviews": "review_id", "init_sessions": "session_id", "embeddings": "embedding_id", "persons": "person_id",
          "observations": "observation_id", "notes": "note_id", "note_revisions": "revision_id",
          "observation_face_assignments": "assignment_id"}.get(table)
    if pk is None:
        return found
    for (child,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for fk in conn.execute(f"PRAGMA foreign_key_list({child})").fetchall():
            if fk[2] == table and (fk[4] or pk) == pk:
                q, v = _in(keys)
                count = conn.execute(f"SELECT COUNT(*) FROM {child} WHERE {fk[3]} IN ({q})", v).fetchone()[0]
                if count:
                    found[f"{child}.{fk[3]} ({fk[6]})"] = count
    return found


# ------------------------------------------------------------- mechanisms
def probe_constraints(conn, oid: str) -> list[dict]:
    """H0: unmodified schema. Every statement in its own savepoint; all rolled back."""
    plan = build_plan(conn, oid)
    results = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table, key_sql in ORDER:
            keys = plan.rows.get(table, [])
            if table == "graph_connections":
                keys = plan.persons_erased
            if not keys:
                continue
            conn.execute("SAVEPOINT probe")
            try:
                count = _delete_projection_rows(conn, keys) if table == "graph_connections" else _delete(conn, table, key_sql, keys)
                outcome = {"table": table, "planned": len(keys), "deleted": count, "error": None}
            except Exception as exc:  # sqlcipher3 errors are not sqlite3 subclasses
                outcome = {"table": table, "planned": len(keys), "deleted": 0, "error": str(exc)}
                conn.execute("ROLLBACK TO probe")
                outcome["blocked_by_remaining_children"] = _remaining_children(conn, table, keys)
            conn.execute("RELEASE probe")  # successful statements stay applied until the final ROLLBACK
            results.append(outcome)
    finally:
        conn.execute("ROLLBACK")
    return results


# Journal-linked result columns (mirrors P11-JOURNAL-003 + review completion).
JOURNAL_LINKS = (
    ("observations", "created_operation_id"), ("observation_media", "operation_id"),
    ("observation_participants", "operation_id"), ("observation_face_assignments", "created_operation_id"),
    ("identity_corrections", "operation_id"), ("encounter_participant_revisions", "operation_id"),
    ("encounter_metadata_revisions", "operation_id"), ("encounter_relation_decisions", "operation_id"),
    ("relationship_evidence", "created_operation_id"), ("relationship_evidence", "deactivated_operation_id"),
    ("notes", "created_operation_id"), ("notes", "retired_operation_id"), ("note_revisions", "operation_id"),
    ("note_mentions", "created_operation_id"), ("note_mentions", "retired_operation_id"),
    ("biometric_enrollment_history", "operation_id"), ("merge_operations", "operation_journal_id"),
    ("photo_reviews", "completed_operation_id"),
)
JOURNAL_POLICY = {"value": "revert"}


def _linked_operations(conn) -> set[str]:
    ops = set()
    for table, column in JOURNAL_LINKS:
        ops.update(_ids(conn, f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"))
    return ops


def hard_delete_event(conn, oid: str, operation_id: str, *, expected_revision: str | None, actor=None,
                      fail_after: str | None = None, journal_policy: str | None = None) -> dict:
    """H1. One IMMEDIATE transaction: guard checks, plan, journal, deletes, recompute, commit."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        journal = conn.execute("SELECT status, operation_type FROM operation_journal WHERE operation_id = ?", (operation_id,)).fetchone()
        if journal is not None:
            if journal[1] != OPERATION_TYPE:
                raise EventDeletionRefused("operation_conflict", "Operation ID belongs to another operation")
            row = conn.execute("SELECT details FROM operation_journal_status_history WHERE operation_id = ? AND to_status = 'COMMITTED'", (operation_id,)).fetchone()
            conn.execute("ROLLBACK")
            return {"replayed": True, **json.loads(row[0])}
        row = conn.execute("SELECT status FROM observations WHERE observation_id = ?", (oid,)).fetchone()
        if row is None:
            raise EventDeletionRefused("event_not_found", "Event does not exist (already erased?)")
        if row[0] != "FINALIZED":
            raise EventDeletionRefused("event_not_finalized", "Only finalized Events can be erased")
        if expected_revision is not None and expected_revision != _encounter_revision(conn, oid):
            raise EventDeletionRefused("stale_revision", "Event changed; reload before deleting")
        pending = _ids(conn, """SELECT s.session_id FROM init_sessions s WHERE s.target_observation_id = ? AND s.status <> 'closed'
                                UNION SELECT r.review_id FROM photo_reviews r WHERE r.target_observation_id = ? AND r.status = 'IN_PROGRESS'""", (oid, oid))
        if pending:
            raise EventDeletionRefused("pending_attach_media", "Finish or discard the pending Attach Media review first", pending=pending)
        plan = build_plan(conn, oid)
        affected = [{"entity_type": "observation", "entity_id": oid}] + [{"entity_type": "person", "entity_id": p} for p in plan.persons_erased]
        _begin_journal_operation(conn, OPERATION_TYPE, operation_id=operation_id, actor=actor, source="experimental/issue-89",
                                 affected_entities=affected, details={"row_counts": {t: len(k) for t, k in plan.rows.items()}})
        linked_before = _linked_operations(conn)
        guarded = [(operation_id, table, key) for table in GUARDED_TRIGGERS for key in plan.rows.get(table, [])]
        conn.executemany(f"INSERT INTO {ERASURE_TABLE}(operation_id, table_name, row_key) VALUES (?, ?, ?)", guarded)
        deleted = {}
        for table, key_sql in ORDER:
            if fail_after == table:
                raise RuntimeError(f"injected failure before deleting {table}")
            if table == "graph_connections":
                deleted[table] = _delete_projection_rows(conn, plan.persons_erased) if plan.persons_erased else 0
                continue
            keys = plan.rows.get(table, [])
            deleted[table] = _delete(conn, table, key_sql, keys) if keys else 0
            if deleted[table] != len(keys):
                raise RuntimeError(f"{table}: planned {len(keys)} deleted {deleted[table]}")
        # Journal policy. "retain": X's committed operations stay COMMITTED although
        # their results are gone (iteration H1). "revert": an operation whose
        # every linked result row was erased transitions COMMITTED -> REVERTED
        # (an existing allowed transition) with erasure provenance (H1b).
        policy = journal_policy or JOURNAL_POLICY["value"]
        orphaned = sorted(linked_before - _linked_operations(conn) - {operation_id})
        reverted = []
        if policy == "revert":
            for op_id in orphaned:
                status = conn.execute("SELECT status FROM operation_journal WHERE operation_id = ?", (op_id,)).fetchone()
                if status and status[0] == "COMMITTED":
                    _transition_journal_operation(conn, op_id, "REVERTED", {"erased_by_operation_id": operation_id, "reason": "event.erase"})
                    reverted.append(op_id)
        _refresh_source_biometric_status(conn)
        _replace_graph_projection(conn)
        validation = _validate_graph_projection(conn)
        conn.execute(f"DELETE FROM {ERASURE_TABLE} WHERE operation_id = ?", (operation_id,))
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"foreign key check failed: {[tuple(p) for p in problems][:5]}")
        result = {"observation_id": oid, "deleted": deleted, "persons_erased": plan.persons_erased,
                  "persons_retained": plan.persons_retained, "embeddings_erased": plan.embeddings_erased,
                  "embeddings_retained": plan.embeddings_retained, "candidate_files": plan.candidate_files,
                  "session_source_paths": plan.session_source_paths, "journal_policy": policy,
                  "orphaned_operations": orphaned, "reverted_operations": reverted,
                  "graph_validation_ok": not validation.get("errors") if isinstance(validation, dict) else True}
        _transition_journal_operation(conn, operation_id, "COMMITTED", result)
        conn.execute("COMMIT")
        return result
    except Exception:
        conn.execute("ROLLBACK")
        raise


def cleanup_targets(conn, oid: str, config) -> list[str]:
    """Physical candidates for the existing CleanupService (re-checked at run)."""
    plan = build_plan(conn, oid)
    targets = list(plan.candidate_files) + list(plan.session_source_paths)
    targets += [str(config.face_dir / "init" / sid) for sid in plan.rows.get("init_sessions", [])]
    return targets


def referenced_paths(conn) -> set[str]:
    paths = set()
    for spec in MEDIA_AUTHORITY_REGISTRY:
        paths.update(p for p in _ids(conn, f"SELECT {spec.path_column} FROM {spec.table} WHERE {spec.path_column} IS NOT NULL") if p)
    paths.update(p for p in _ids(conn, "SELECT source_path FROM init_sessions") if p)
    return paths


def cleanup_files(conn, result: dict, data_dir: Path) -> dict:
    """After COMMIT: unlink only candidates no live registry column still references."""
    live = referenced_paths(conn)
    removed, kept = [], []
    candidates = list(result["candidate_files"])
    for source in result.get("session_source_paths", []):
        path = Path(source)
        if path.is_dir() and str(path) not in live:
            candidates += [str(p) for p in path.iterdir()]
    for candidate in sorted(set(candidates)):
        path = Path(candidate)
        if candidate in live:
            kept.append(candidate)
        elif path.exists() and str(path).startswith(str(data_dir)):
            path.unlink()
            removed.append(candidate)
    for source in result.get("session_source_paths", []):
        path = Path(source)
        if path.is_dir() and not any(path.iterdir()) and str(path) not in live:
            path.rmdir()
            removed.append(source + "/")
    for crop_dir in {Path(c).parent for c in removed if "/faces/init/" in c}:
        if crop_dir.is_dir() and not any(crop_dir.iterdir()):
            crop_dir.rmdir()
            removed.append(str(crop_dir) + "/")
    return {"removed": removed, "kept_referenced": kept}
