"""Structured repair (P11-C R01/R02) and merge-revert (P11-D) transaction helpers."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from sentriface.secure_storage import INTEGRITY_ERRORS
import uuid

from dataclasses import asdict
from typing import Callable
from sentriface.errors import (
    StructuredRepairRefused,
    OperationRevertRefused,
)
from sentriface.models import (
    ArchivedCanonicalSurvivorRepairPrecondition,
    NoteReferenceReconciliationPrecondition,
    NoteReferenceRepairPlan,
    OperationRevertPrecondition,
    MergeOperation,
    utc_now,
)
from sentriface.storage.sqlite_constants import SCHEMA_VERSION
from sentriface.storage.sqlite_helpers import (
    _normalize_evidence_endpoints,
    _insert_relationship_evidence,
    _graph_revision_token,
    _get_merge_operation,
    _placeholder_name_conflict,
    _get_journal_operation,
)


_R01_REPAIR_ID = "P11C-R01-RESTORE-ARCHIVED-CANONICAL-SURVIVOR"
_R01_SPEC_VERSION = 1
_R01_INVARIANT_ID = "P11-IDENTITY-003"
_R01_FINGERPRINT_VERSION = "p11-a-schema28-repair-fingerprint-v1"
_R01_OPERATION_TYPE = "integrity.repair.canonical-survivor.restore"


def _r01_hash(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _r01_table_fingerprint(conn: sqlite3.Connection, table: str) -> str:
    allowed = {
        "graph_connections", "merge_operations", "merge_affected_items",
        "merge_conflict_resolutions",
    }
    if table not in allowed:
        raise ValueError("Unsupported R01 fingerprint table")
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    return _r01_hash([dict(row) for row in rows])


def _r01_canonical_fingerprint(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT person_id, canonical_person_id FROM persons ORDER BY person_id"
    ).fetchall()
    return _r01_hash([tuple(row) for row in rows])


def _r01_resolve_paths(
    conn: sqlite3.Connection, survivor_person_id: str,
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    people = {
        str(row["person_id"]): (str(row["lifecycle_status"]), row["canonical_person_id"])
        for row in conn.execute(
            "SELECT person_id, lifecycle_status, canonical_person_id FROM persons"
        )
    }
    paths: list[tuple[str, ...]] = []
    sources: list[str] = []
    for source_id, (lifecycle, target) in sorted(people.items()):
        if lifecycle != "MERGED":
            continue
        if not target:
            raise StructuredRepairRefused("R01 refused because a merged identity has no target")
        current = source_id
        path: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise StructuredRepairRefused("R01 refused because a canonical cycle exists")
            seen.add(current)
            path.append(current)
            state = people.get(current)
            if state is None:
                raise StructuredRepairRefused("R01 refused because a canonical target is dangling")
            current_lifecycle, current_target = state
            if current_lifecycle != "MERGED":
                if current_target is not None:
                    raise StructuredRepairRefused(
                        "R01 refused because a non-merged identity has a canonical target"
                    )
                break
            if not current_target:
                raise StructuredRepairRefused("R01 refused because a canonical path is malformed")
            current = str(current_target)
        if current == survivor_person_id:
            sources.append(source_id)
            paths.append(tuple(path))
    return tuple(sources), tuple(paths)


def _r01_merge_snapshot(
    conn: sqlite3.Connection,
    sources: tuple[str, ...],
) -> tuple[tuple[str, ...], str]:
    operation_ids: list[str] = []
    for source_id in sources:
        direct_target = conn.execute(
            "SELECT canonical_person_id FROM persons WHERE person_id = ?",
            (source_id,),
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT m.*, j.operation_type, j.status, j.actor AS journal_actor
            FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.source_person_id = ? AND m.target_person_id = ?
            ORDER BY m.created_at, m.merge_operation_id
            """,
            (source_id, direct_target),
        ).fetchall()
        if len(rows) != 1:
            raise StructuredRepairRefused(
                "R01 refused because merge history does not uniquely support the path"
            )
        row = rows[0]
        if (
            row["operation_type"] != "identity.merge"
            or row["status"] != "COMMITTED"
            or row["actor"] != row["journal_actor"]
            or row["operation_journal_id"] != row["merge_operation_id"]
        ):
            raise StructuredRepairRefused(
                "R01 refused because merge manifest and journal history disagree"
            )
        operation_ids.append(str(row["merge_operation_id"]))
    ids = tuple(sorted(operation_ids))
    if not ids:
        raise StructuredRepairRefused("R01 requires at least one preserved merge manifest")
    placeholders = ",".join("?" for _ in ids)
    snapshot = {
        "operations": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_operations WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id",
            ids,
        )],
        "items": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_affected_items WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id, item_type, item_id",
            ids,
        )],
        "conflicts": [dict(row) for row in conn.execute(
            f"SELECT * FROM merge_conflict_resolutions WHERE merge_operation_id IN ({placeholders}) ORDER BY merge_operation_id, conflict_id",
            ids,
        )],
    }
    return ids, _r01_hash(snapshot)


def _r01_relevant_operation_fingerprint(
    conn: sqlite3.Connection, entity_ids: tuple[str, ...],
) -> str:
    selected: list[dict] = []
    wanted = set(entity_ids)
    for row in conn.execute(
        "SELECT operation_id, operation_type, status, affected_entities, created_at, completed_at FROM operation_journal ORDER BY rowid"
    ):
        try:
            affected = json.loads(row["affected_entities"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StructuredRepairRefused("R01 refused because journal metadata is malformed") from exc
        if any(
            isinstance(item, dict) and str(item.get("entity_id")) in wanted
            for item in affected
        ):
            selected.append(dict(row))
    return _r01_hash(selected)


def _r01_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    survivor_person_id: str,
) -> ArchivedCanonicalSurvivorRepairPrecondition:
    if report.schema_version != SCHEMA_VERSION or SCHEMA_VERSION < 28:
        raise StructuredRepairRefused("R01 requires schema version 28 or later", report=report)
    if report.findings_truncated:
        raise StructuredRepairRefused("R01 requires an untruncated P11-A report", report=report)
    blocking = [
        item for item in report.findings
        if item.severity.value in {"CRITICAL", "ERROR"}
    ]
    selected = []
    for item in blocking:
        entities = dict(item.entity_ids)
        if (
            item.invariant_id != _R01_INVARIANT_ID
            or entities.get("terminal_person_id") != survivor_person_id
        ):
            raise StructuredRepairRefused(
                "R01 refused because another critical/error finding makes identity interpretation ambiguous",
                report=report,
            )
        selected.append(item)
    if not selected:
        raise StructuredRepairRefused(
            "R01 refused because the selected P11-IDENTITY-003 finding is absent",
            report=report,
        )
    graph_revision = _graph_revision_token(conn)
    if graph_revision != report.graph_revision:
        raise StructuredRepairRefused(
            "R01 refused because the graph revision changed after diagnosis", report=report,
        )
    row = conn.execute(
        """
        SELECT lifecycle_status, deleted_at, lifecycle_changed_at, canonical_person_id
        FROM persons WHERE person_id = ?
        """,
        (survivor_person_id,),
    ).fetchone()
    if row is None:
        raise StructuredRepairRefused("R01 survivor no longer exists", report=report)
    if (
        row["lifecycle_status"] != "ARCHIVED"
        or row["deleted_at"] is None
        or row["lifecycle_changed_at"] is None
        or row["canonical_person_id"] is not None
    ):
        raise StructuredRepairRefused(
            "R01 survivor is not the exact supported archived terminal state", report=report,
        )
    sources, paths = _r01_resolve_paths(conn, survivor_person_id)
    selected_sources = tuple(sorted(dict(item.entity_ids)["person_id"] for item in selected))
    if sources != selected_sources:
        raise StructuredRepairRefused(
            "R01 finding set does not cover every canonical path to the survivor", report=report,
        )
    merge_ids, merge_fingerprint = _r01_merge_snapshot(conn, sources)
    affected = tuple(sorted({survivor_person_id, *sources}))
    relevant_fingerprint = _r01_relevant_operation_fingerprint(conn, affected)
    finding_payload = [
        {
            "invariant_id": item.invariant_id,
            "message": item.message,
            "entity_ids": list(item.entity_ids),
            "evidence": list(item.evidence),
        }
        for item in sorted(selected, key=lambda value: value.entity_ids)
    ]
    state = {
        "survivor_person_id": survivor_person_id,
        "lifecycle_status": row["lifecycle_status"],
        "deleted_at": row["deleted_at"],
        "lifecycle_changed_at": row["lifecycle_changed_at"],
        "canonical_person_id": row["canonical_person_id"],
        "merge_sources": sources,
        "merge_paths": paths,
        "merge_operation_ids": merge_ids,
        "merge_state_fingerprint": merge_fingerprint,
        "relevant_operation_fingerprint": relevant_fingerprint,
    }
    fingerprint = _r01_hash({
        "checker_contract": _R01_FINGERPRINT_VERSION,
        "repair_id": _R01_REPAIR_ID,
        "repair_spec_version": _R01_SPEC_VERSION,
        "findings": finding_payload,
        "schema_version": report.schema_version,
        "graph_revision": graph_revision,
        "state": state,
    })
    return ArchivedCanonicalSurvivorRepairPrecondition(
        repair_id=_R01_REPAIR_ID,
        repair_spec_version=_R01_SPEC_VERSION,
        invariant_ids=(_R01_INVARIANT_ID,),
        affected_entity_ids=affected,
        survivor_person_id=survivor_person_id,
        finding_fingerprint_version=_R01_FINGERPRINT_VERSION,
        finding_fingerprint=fingerprint,
        schema_version=SCHEMA_VERSION,
        graph_revision=graph_revision,
        expected_lifecycle_status=str(row["lifecycle_status"]),
        expected_deleted_at=str(row["deleted_at"]),
        expected_lifecycle_changed_at=str(row["lifecycle_changed_at"]),
        expected_canonical_person_id=row["canonical_person_id"],
        merge_source_person_ids=sources,
        merge_paths=paths,
        merge_operation_ids=merge_ids,
        merge_state_fingerprint=merge_fingerprint,
        relevant_operation_fingerprint=relevant_fingerprint,
    )


def _validate_r01_request_shape(
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
) -> None:
    if not isinstance(precondition, ArchivedCanonicalSurvivorRepairPrecondition):
        raise ValueError("R01 requires its typed finding precondition")
    if (
        precondition.repair_id != _R01_REPAIR_ID
        or precondition.repair_spec_version != _R01_SPEC_VERSION
        or precondition.invariant_ids != (_R01_INVARIANT_ID,)
        or precondition.finding_fingerprint_version != _R01_FINGERPRINT_VERSION
        or precondition.schema_version != SCHEMA_VERSION
    ):
        raise StructuredRepairRefused("R01 request does not match the frozen repair specification")


def _r01_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _R01_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    details = operation["details"]
    if (
        details.get("finding_fingerprint") != precondition.finding_fingerprint
        or details.get("repair_id") != precondition.repair_id
        or details.get("survivor_person_id") != precondition.survivor_person_id
    ):
        raise KeyError("Operation ID was already used for a different R01 diagnosis")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    return dict(operation["status_history"][-1]["details"])


def _restore_archived_person_in_transaction(
    conn: sqlite3.Connection, person_id: str,
    allowed_statuses: tuple[str, ...] = ("ARCHIVED",),
) -> sqlite3.Cursor:
    row = conn.execute(
        "SELECT lifecycle_status FROM persons WHERE person_id = ?", (person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    if row["lifecycle_status"] not in allowed_statuses:
        raise KeyError(f"Only archived or deleted people can be restored: {person_id}")
    try:
        cursor = conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = 'ACTIVE', deleted_at = NULL, lifecycle_changed_at = ?
            WHERE person_id = ? AND lifecycle_status = ?
            """,
            (utc_now(), person_id, row["lifecycle_status"]),
        )
    except INTEGRITY_ERRORS as exc:
        raise _placeholder_name_conflict(exc) from exc
    if cursor.rowcount != 1:
        raise RuntimeError("Person lifecycle changed concurrently")
    return cursor


_R02_REPAIR_ID = "P11C-R02-RECONCILE-NOTE-REFERENCE-STATE"
_R02_SPEC_VERSION = 1
_R02_FINGERPRINT_VERSION = "p11-a-schema28-repair-fingerprint-v1"
_R02_OPERATION_TYPE = "integrity.repair.note-reference.reconcile"
_R02_ALLOWED_INVARIANTS = {
    "P11-NOTE-002", "P11-NOTE-003", "P11-EVIDENCE-001", "P11-GRAPH-001",
}
_R02_STALE_EVIDENCE_MESSAGE = (
    "active evidence has no current active note mention source"
)


def _r02_failure_checkpoint(_phase: str) -> None:
    """Patchable transaction checkpoint used only by focused rollback tests."""


def _r02_rows_fingerprint(rows: list[sqlite3.Row]) -> str:
    return _r01_hash([dict(row) for row in rows])


def _r02_revision_snapshot(
    conn: sqlite3.Connection, note_id: str,
) -> tuple[sqlite3.Row, tuple[str, ...], str]:
    note = conn.execute(
        "SELECT * FROM notes WHERE note_id = ?", (note_id,),
    ).fetchone()
    if note is None:
        raise StructuredRepairRefused("R02 refused because the selected note does not exist")
    revisions = conn.execute(
        "SELECT * FROM note_revisions WHERE note_id = ? ORDER BY revision_number",
        (note_id,),
    ).fetchall()
    if not revisions or tuple(int(row["revision_number"]) for row in revisions) != tuple(
        range(1, len(revisions) + 1)
    ):
        raise StructuredRepairRefused(
            "R02 refused because immutable note revision history is malformed"
        )
    latest = revisions[-1]
    mentions = tuple(str(row["referenced_person_id"]) for row in conn.execute(
        """
        SELECT referenced_person_id FROM note_revision_mentions
        WHERE revision_id = ? ORDER BY referenced_person_id
        """,
        (latest["revision_id"],),
    ))
    all_mentions = conn.execute(
        """
        SELECT rm.* FROM note_revision_mentions rm
        JOIN note_revisions r ON r.revision_id = rm.revision_id
        WHERE r.note_id = ? ORDER BY r.revision_number, rm.referenced_person_id
        """,
        (note_id,),
    ).fetchall()
    fingerprint = _r01_hash({
        "note": dict(note),
        "revisions": [dict(row) for row in revisions],
        "mentions": [dict(row) for row in all_mentions],
    })
    return latest, mentions, fingerprint


def _r02_group_rows(
    conn: sqlite3.Connection, note_id: str, referenced_person_id: str,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    occurrences = conn.execute(
        """
        SELECT m.*, created.note_id AS created_note_id,
               created.revision_number AS created_revision_number,
               retired.note_id AS retired_note_id,
               retired.revision_number AS retired_revision_number
        FROM note_mentions m
        LEFT JOIN note_revisions created ON created.revision_id=m.created_revision_id
        LEFT JOIN note_revisions retired ON retired.revision_id=m.retired_revision_id
        WHERE m.note_id=? AND m.referenced_person_id=?
        ORDER BY m.created_at, m.mention_id
        """,
        (note_id, referenced_person_id),
    ).fetchall()
    if not occurrences:
        raise StructuredRepairRefused(
            "R02 refused because a wholly missing occurrence group is outside P11-A coverage"
        )
    occurrence_ids = tuple(str(row["mention_id"]) for row in occurrences)
    placeholders = ",".join("?" for _ in occurrence_ids)
    evidence = conn.execute(
        f"""
        SELECT * FROM relationship_evidence
        WHERE evidence_type='NOTE_REFERENCE'
          AND source_entity_id IN ({placeholders})
        ORDER BY created_at, evidence_id
        """,
        occurrence_ids,
    ).fetchall()
    return occurrences, evidence


def _r02_validate_history(
    conn: sqlite3.Connection,
    note: sqlite3.Row,
    occurrences: list[sqlite3.Row],
    evidence: list[sqlite3.Row],
    *,
    allowed_started_operation_id: str | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    operation_ids: set[str] = set()
    note_active_shape = (
        note["status"] == "ACTIVE"
        and note["retired_operation_id"] is None
        and note["retired_at"] is None
    )
    note_retired_shape = (
        note["status"] == "RETIRED"
        and note["retired_operation_id"] is not None
        and note["retired_at"] is not None
    )
    if not (note_active_shape or note_retired_shape):
        raise StructuredRepairRefused(
            "R02 refused because note retirement provenance is malformed"
        )
    if note["created_operation_id"]:
        operation_ids.add(str(note["created_operation_id"]))
    if note["retired_operation_id"]:
        operation_ids.add(str(note["retired_operation_id"]))
    operation_ids.update(
        str(row["operation_id"])
        for row in conn.execute(
            """
            SELECT operation_id FROM note_revisions
            WHERE note_id=? AND operation_id IS NOT NULL
            """,
            (note["note_id"],),
        )
    )
    for row in occurrences:
        active_shape = (
            bool(row["active"])
            and row["retired_revision_id"] is None
            and row["retired_operation_id"] is None
            and row["retired_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["retired_revision_id"] is not None
            and row["retired_operation_id"] is not None
            and row["retired_at"] is not None
            and row["created_note_id"] == row["note_id"]
            and row["retired_note_id"] == row["note_id"]
            and int(row["retired_revision_number"] or 0)
                >= int(row["created_revision_number"] or 0)
        )
        if not (active_shape or retired_shape):
            raise StructuredRepairRefused(
                "R02 refused because occurrence retirement provenance is malformed"
            )
        operation_ids.add(str(row["created_operation_id"]))
        if row["retired_operation_id"]:
            operation_ids.add(str(row["retired_operation_id"]))
    occurrence_by_id = {
        str(row["mention_id"]): row for row in occurrences
    }
    for row in evidence:
        source_occurrence = occurrence_by_id.get(str(row["source_entity_id"]))
        active_shape = (
            bool(row["active"])
            and row["deactivated_operation_id"] is None
            and row["deactivated_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["deactivated_operation_id"] is not None
            and row["deactivated_at"] is not None
        )
        coherent = (
            source_occurrence is not None
            and row["evidence_type"] == "NOTE_REFERENCE"
            and row["source_entity_type"] == "NOTE"
            and row["source_person_id"] == note["owner_person_id"]
            and row["target_person_id"] == source_occurrence["referenced_person_id"]
            and row["relationship_type"] == "REFERENCES"
            and row["directionality"] == "DIRECTED"
            and row["source_person_id"] != row["target_person_id"]
        )
        if not coherent:
            raise StructuredRepairRefused(
                "R02 refused because NOTE_REFERENCE provenance, endpoints, or direction are malformed"
            )
        if not (active_shape or retired_shape):
            raise StructuredRepairRefused(
                "R02 refused because evidence retirement provenance is malformed"
            )
        operation_ids.add(str(row["created_operation_id"]))
        if row["deactivated_operation_id"]:
            operation_ids.add(str(row["deactivated_operation_id"]))
    linked_operation_ids = set(operation_ids)
    relevant_entity_ids = {
        str(note["note_id"]),
        str(note["owner_person_id"]),
        *[str(row["referenced_person_id"]) for row in occurrences],
        *[str(row["mention_id"]) for row in occurrences],
        *[str(row["evidence_id"]) for row in evidence],
    }
    for row in conn.execute(
        "SELECT operation_id, affected_entities FROM operation_journal ORDER BY rowid"
    ):
        try:
            affected_entities = json.loads(row["affected_entities"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise StructuredRepairRefused(
                "R02 refused because relevant journal metadata is malformed"
            ) from exc
        if any(
            isinstance(item, dict)
            and str(item.get("entity_id")) in relevant_entity_ids
            for item in affected_entities
        ):
            operation_ids.add(str(row["operation_id"]))
    operation_snapshot: list[dict] = []
    for operation_id in sorted(operation_ids):
        operation = _get_journal_operation(conn, operation_id)
        allowed_statuses = (
            {"COMMITTED", "REVERTED"}
            if operation_id in linked_operation_ids
            else {"COMMITTED", "REVERTED", "FAILED", "ROLLED_BACK"}
        )
        if operation_id == allowed_started_operation_id:
            allowed_statuses.add("STARTED")
        if operation is None or operation["status"] not in allowed_statuses:
            raise StructuredRepairRefused(
                "R02 refused because occurrence/evidence operation history is incomplete"
            )
        operation_snapshot.append(operation)
    retirement = {
        "occurrences": [
            {
                key: row[key] for key in (
                    "mention_id", "active", "retired_revision_id",
                    "retired_operation_id", "retired_at",
                )
            }
            for row in occurrences
        ],
        "evidence": [
            {
                key: row[key] for key in (
                    "evidence_id", "active", "deactivated_operation_id",
                    "deactivated_at",
                )
            }
            for row in evidence
        ],
    }
    return (
        _r01_hash(retirement),
        _r01_hash(operation_snapshot),
        tuple(sorted(operation_ids)),
    )


def _r02_canonical_snapshot(
    conn: sqlite3.Connection, person_ids: tuple[str, ...],
) -> tuple[str, dict[str, str]]:
    people = {
        str(row["person_id"]): {
            "lifecycle_status": str(row["lifecycle_status"]),
            "deleted_at": row["deleted_at"],
            "canonical_person_id": (
                str(row["canonical_person_id"])
                if row["canonical_person_id"] is not None else None
            ),
        }
        for row in conn.execute(
            """
            SELECT person_id, lifecycle_status, deleted_at, canonical_person_id
            FROM persons ORDER BY person_id
            """
        )
    }
    paths: dict[str, tuple[str, ...]] = {}
    terminals: dict[str, str] = {}
    relevant: set[str] = set()
    for person_id in person_ids:
        current = person_id
        path: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise StructuredRepairRefused(
                    "R02 refused because a canonical cycle exists"
                )
            seen.add(current)
            path.append(current)
            relevant.add(current)
            row = people.get(current)
            if row is None:
                raise StructuredRepairRefused(
                    "R02 refused because a canonical target is dangling"
                )
            target = row["canonical_person_id"]
            if row["lifecycle_status"] != "MERGED":
                if target is not None:
                    raise StructuredRepairRefused(
                        "R02 refused because a correction/canonical chain is invalid"
                    )
                terminals[person_id] = current
                paths[person_id] = tuple(path)
                break
            if target is None:
                raise StructuredRepairRefused(
                    "R02 refused because a merged canonical chain is incomplete"
                )
            current = str(target)
    snapshot = {
        "paths": paths,
        "people": {person_id: people[person_id] for person_id in sorted(relevant)},
    }
    return _r01_hash(snapshot), terminals


def _r02_plan_for_state(
    *,
    note: sqlite3.Row,
    latest_mentions: tuple[str, ...],
    referenced_person_id: str,
    occurrences: list[sqlite3.Row],
    evidence: list[sqlite3.Row],
) -> NoteReferenceRepairPlan:
    expected_occurrence = (
        note["status"] == "ACTIVE"
        and referenced_person_id in latest_mentions
        and referenced_person_id != note["owner_person_id"]
    )
    active_occurrences = [row for row in occurrences if bool(row["active"])]
    if len(active_occurrences) > 1:
        raise StructuredRepairRefused(
            "R02 refused because duplicate active occurrences make the plan ambiguous"
        )
    active_evidence = [row for row in evidence if bool(row["active"])]
    active_occurrence_ids = {
        str(row["mention_id"]) for row in active_occurrences
    }
    active_on_current = [
        row for row in active_evidence
        if str(row["source_entity_id"]) in active_occurrence_ids
    ]
    active_on_inactive = [
        row for row in active_evidence
        if str(row["source_entity_id"]) not in active_occurrence_ids
    ]
    if expected_occurrence:
        if not active_occurrences:
            if active_evidence:
                raise StructuredRepairRefused(
                    "R02 refused because occurrence append and stale-evidence retirement are both required"
                )
            return NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE
        if active_on_inactive:
            raise StructuredRepairRefused(
                "R02 refused because more than one repair plan applies"
            )
        if not active_on_current:
            return NoteReferenceRepairPlan.APPEND_EVIDENCE
        if len(active_on_current) > 1:
            return NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE
        raise StructuredRepairRefused(
            "R02 refused because the selected occurrence/evidence state is already healthy"
        )
    if active_occurrences:
        if active_on_inactive:
            raise StructuredRepairRefused(
                "R02 refused because occurrence and unrelated stale-evidence plans conflict"
            )
        return NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE
    if active_evidence:
        return NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE
    raise StructuredRepairRefused(
        "R02 refused because the selected occurrence/evidence state is already healthy"
    )


def _r02_graph_key(
    terminals: dict[str, str], owner_person_id: str, referenced_person_id: str,
) -> tuple[str, str, str, str] | None:
    source = terminals[owner_person_id]
    target = terminals[referenced_person_id]
    if source == target:
        return None
    return (source, target, "REFERENCES", "DIRECTED")


def _r02_classify_findings(
    report: object,
    *,
    note_id: str,
    referenced_person_id: str,
    occurrence_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    plan: NoteReferenceRepairPlan,
    graph_key: tuple[str, str, str, str] | None,
    active_evidence_changes: bool,
) -> tuple[object, ...]:
    selected: list[object] = []
    saw_note002 = False
    saw_note003 = False
    saw_stale_evidence = False
    for item in report.findings:
        if item.severity.value not in {"CRITICAL", "ERROR"}:
            continue
        entities = dict(item.entity_ids)
        if item.invariant_id not in _R02_ALLOWED_INVARIANTS:
            raise StructuredRepairRefused(
                "R02 refused because an unrelated critical/error finding blocks deterministic repair",
                report=report,
            )
        if item.invariant_id == "P11-NOTE-002":
            if (
                item.message
                != "Current note mention occurrence cardinality disagrees with the latest authoritative revision"
                or entities.get("note_id") != note_id
                or entities.get("person_id") != referenced_person_id
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-NOTE-002 is not the admitted current-cardinality shape",
                    report=report,
                )
            saw_note002 = True
        elif item.invariant_id == "P11-NOTE-003":
            if (
                item.message
                != "NOTE_REFERENCE active evidence does not match authoritative mention state"
                or entities.get("note_id") != note_id
                or entities.get("person_id") != referenced_person_id
                or entities.get("mention_id") not in occurrence_ids
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-NOTE-003 is outside the selected occurrence group",
                    report=report,
                )
            saw_note003 = True
        elif item.invariant_id == "P11-EVIDENCE-001":
            if (
                item.message != _R02_STALE_EVIDENCE_MESSAGE
                or entities.get("evidence_id") not in evidence_ids
            ):
                raise StructuredRepairRefused(
                    "R02 refused because P11-EVIDENCE-001 is not the exact admitted stale-active-source shape",
                    report=report,
                )
            saw_stale_evidence = True
        else:
            evidence = dict(item.evidence)
            finding_key = (
                entities.get("source_person_id"),
                entities.get("target_person_id"),
                evidence.get("relationship_type"),
                evidence.get("directionality"),
            )
            if not active_evidence_changes or graph_key is None or finding_key != graph_key:
                raise StructuredRepairRefused(
                    "R02 refused because graph drift is not caused by the selected note-reference scope",
                    report=report,
                )
        selected.append(item)
    if plan in {
        NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE,
        NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE,
    } and not saw_note002:
        raise StructuredRepairRefused(
            "R02 refused because the required P11-NOTE-002 finding is absent",
            report=report,
        )
    if plan in {
        NoteReferenceRepairPlan.APPEND_EVIDENCE,
        NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE,
    } and not saw_note003:
        raise StructuredRepairRefused(
            "R02 refused because the required P11-NOTE-003 finding is absent",
            report=report,
        )
    if plan is NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE and not (
        saw_note003 and saw_stale_evidence
    ):
        raise StructuredRepairRefused(
            "R02 refused because the exact stale active evidence findings are absent",
            report=report,
        )
    return tuple(selected)


def _r02_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    note_id: str,
    referenced_person_id: str,
) -> NoteReferenceReconciliationPrecondition:
    if report.schema_version != SCHEMA_VERSION or SCHEMA_VERSION < 28:
        raise StructuredRepairRefused("R02 requires schema version 28 or later", report=report)
    if report.findings_truncated:
        raise StructuredRepairRefused("R02 requires an untruncated P11-A report", report=report)
    graph_revision = _graph_revision_token(conn)
    if graph_revision != report.graph_revision:
        raise StructuredRepairRefused(
            "R02 refused because graph authority changed after diagnosis", report=report,
        )
    note = conn.execute(
        "SELECT * FROM notes WHERE note_id=?", (note_id,),
    ).fetchone()
    if note is None:
        raise StructuredRepairRefused("R02 selected note no longer exists", report=report)
    latest, latest_mentions, revision_fingerprint = _r02_revision_snapshot(conn, note_id)
    occurrences, evidence = _r02_group_rows(conn, note_id, referenced_person_id)
    retirement_fingerprint, operation_fingerprint, _operation_ids = _r02_validate_history(
        conn, note, occurrences, evidence,
    )
    canonical_fingerprint, terminals = _r02_canonical_snapshot(
        conn, (str(note["owner_person_id"]), referenced_person_id),
    )
    plan = _r02_plan_for_state(
        note=note,
        latest_mentions=latest_mentions,
        referenced_person_id=referenced_person_id,
        occurrences=occurrences,
        evidence=evidence,
    )
    active_evidence_changes = (
        plan is not NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE
        or any(bool(row["active"]) for row in evidence)
    )
    occurrence_ids = tuple(str(row["mention_id"]) for row in occurrences)
    evidence_ids = tuple(str(row["evidence_id"]) for row in evidence)
    selected = _r02_classify_findings(
        report,
        note_id=note_id,
        referenced_person_id=referenced_person_id,
        occurrence_ids=occurrence_ids,
        evidence_ids=evidence_ids,
        plan=plan,
        graph_key=_r02_graph_key(
            terminals, str(note["owner_person_id"]), referenced_person_id,
        ),
        active_evidence_changes=active_evidence_changes,
    )
    finding_payload = [
        {
            "invariant_id": item.invariant_id,
            "message": item.message,
            "entity_ids": list(item.entity_ids),
            "evidence": list(item.evidence),
        }
        for item in sorted(
            selected,
            key=lambda item: (item.invariant_id, item.entity_ids, item.message),
        )
    ]
    occurrence_fingerprint = _r02_rows_fingerprint(occurrences)
    evidence_fingerprint = _r02_rows_fingerprint(evidence)
    graph_projection_fingerprint = _r01_hash([
        dict(row) for row in conn.execute(
            "SELECT * FROM graph_connections ORDER BY rowid"
        )
    ])
    active_occurrence_ids = tuple(
        str(row["mention_id"]) for row in occurrences if bool(row["active"])
    )
    active_evidence_ids = tuple(
        str(row["evidence_id"]) for row in evidence if bool(row["active"])
    )
    affected = tuple(sorted({
        note_id,
        str(note["owner_person_id"]),
        referenced_person_id,
        *occurrence_ids,
        *evidence_ids,
    }))
    state = {
        "plan": plan.value,
        "note_id": note_id,
        "referenced_person_id": referenced_person_id,
        "owner_person_id": note["owner_person_id"],
        "note_status": note["status"],
        "latest_revision_id": latest["revision_id"],
        "latest_revision_number": latest["revision_number"],
        "latest_revision_mentions": latest_mentions,
        "revision_history_fingerprint": revision_fingerprint,
        "occurrence_group_fingerprint": occurrence_fingerprint,
        "evidence_history_fingerprint": evidence_fingerprint,
        "retirement_provenance_fingerprint": retirement_fingerprint,
        "canonical_state_fingerprint": canonical_fingerprint,
        "graph_projection_fingerprint": graph_projection_fingerprint,
        "relevant_operation_fingerprint": operation_fingerprint,
    }
    fingerprint = _r01_hash({
        "checker_contract": _R02_FINGERPRINT_VERSION,
        "repair_id": _R02_REPAIR_ID,
        "repair_spec_version": _R02_SPEC_VERSION,
        "findings": finding_payload,
        "schema_version": report.schema_version,
        "graph_revision": graph_revision,
        "state": state,
    })
    return NoteReferenceReconciliationPrecondition(
        repair_id=_R02_REPAIR_ID,
        repair_spec_version=_R02_SPEC_VERSION,
        invariant_ids=tuple(sorted({item.invariant_id for item in selected})),
        affected_entity_ids=affected,
        finding_entity_ids=tuple(sorted({
            value for item in selected for _key, value in item.entity_ids
        })),
        plan=plan,
        finding_fingerprint_version=_R02_FINGERPRINT_VERSION,
        finding_fingerprint=fingerprint,
        schema_version=SCHEMA_VERSION,
        graph_revision=graph_revision,
        note_id=note_id,
        referenced_person_id=referenced_person_id,
        owner_person_id=str(note["owner_person_id"]),
        note_status=str(note["status"]),
        latest_revision_id=str(latest["revision_id"]),
        latest_revision_number=int(latest["revision_number"]),
        latest_revision_mentions=latest_mentions,
        revision_history_fingerprint=revision_fingerprint,
        occurrence_ids=occurrence_ids,
        active_occurrence_ids=active_occurrence_ids,
        occurrence_group_fingerprint=occurrence_fingerprint,
        evidence_ids=evidence_ids,
        active_evidence_ids=active_evidence_ids,
        evidence_history_fingerprint=evidence_fingerprint,
        retirement_provenance_fingerprint=retirement_fingerprint,
        canonical_state_fingerprint=canonical_fingerprint,
        graph_projection_fingerprint=graph_projection_fingerprint,
        relevant_operation_fingerprint=operation_fingerprint,
    )


def _validate_r02_request_shape(
    precondition: NoteReferenceReconciliationPrecondition,
) -> None:
    if not isinstance(precondition, NoteReferenceReconciliationPrecondition):
        raise ValueError("R02 requires its typed finding precondition")
    if (
        precondition.repair_id != _R02_REPAIR_ID
        or precondition.repair_spec_version != _R02_SPEC_VERSION
        or precondition.finding_fingerprint_version != _R02_FINGERPRINT_VERSION
        or precondition.schema_version != SCHEMA_VERSION
        or not isinstance(precondition.plan, NoteReferenceRepairPlan)
        or not precondition.invariant_ids
        or not set(precondition.invariant_ids).issubset(_R02_ALLOWED_INVARIANTS)
    ):
        raise StructuredRepairRefused(
            "R02 request does not match the frozen repair specification"
        )


def _r02_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: NoteReferenceReconciliationPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _R02_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    details = operation["details"]
    if (
        details.get("finding_fingerprint") != precondition.finding_fingerprint
        or details.get("repair_id") != precondition.repair_id
        or details.get("note_id") != precondition.note_id
        or details.get("referenced_person_id") != precondition.referenced_person_id
        or details.get("plan_type") != precondition.plan.value
    ):
        raise KeyError("Operation ID was already used for a different R02 diagnosis")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    return dict(operation["status_history"][-1]["details"])


def _r02_affected_entities(
    precondition: NoteReferenceReconciliationPrecondition,
    *,
    planned_occurrence_id: str | None,
    planned_evidence_id: str | None,
) -> list[dict]:
    entities = [
        {"entity_type": "note", "entity_id": precondition.note_id},
        {"entity_type": "person", "entity_id": precondition.owner_person_id},
        {"entity_type": "person", "entity_id": precondition.referenced_person_id},
    ]
    if planned_occurrence_id is not None:
        entities.append({
            "entity_type": "note_mention", "entity_id": planned_occurrence_id,
        })
    if planned_evidence_id is not None:
        entities.append({
            "entity_type": "relationship_evidence", "entity_id": planned_evidence_id,
        })
    entities.extend(
        {"entity_type": "note_mention", "entity_id": item}
        for item in precondition.occurrence_ids[:24]
    )
    entities.extend(
        {"entity_type": "relationship_evidence", "entity_id": item}
        for item in precondition.evidence_ids[:23]
    )
    return entities[:50]


def _r02_planned_append_ids(
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
) -> tuple[str | None, str | None]:
    occurrence_id: str | None = None
    if precondition.plan is NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE:
        occurrence_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join((
                "sentriface", _R02_REPAIR_ID, operation_id, "note-mention",
                precondition.note_id, precondition.referenced_person_id,
            )),
        ))
    source_occurrence_id = occurrence_id
    if precondition.plan in {
        NoteReferenceRepairPlan.APPEND_EVIDENCE,
        NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE,
    }:
        source_occurrence_id = precondition.active_occurrence_ids[0]
    evidence_id: str | None = None
    if source_occurrence_id is not None:
        normalized_source, normalized_target = _normalize_evidence_endpoints(
            precondition.owner_person_id,
            precondition.referenced_person_id,
            "DIRECTED",
        )
        evidence_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join((
                "sentriface", "NOTE_REFERENCE", source_occurrence_id, operation_id,
                normalized_source, normalized_target, "REFERENCES", "DIRECTED",
            )),
        ))
    return occurrence_id, evidence_id


def _r02_append_evidence(
    conn: sqlite3.Connection,
    *,
    mention_id: str,
    owner_person_id: str,
    referenced_person_id: str,
    operation_id: str,
    source: str | None,
    created_at: str,
) -> str:
    evidence_id = _insert_relationship_evidence(
        conn,
        evidence_type="NOTE_REFERENCE",
        source_entity_type="NOTE",
        source_entity_id=mention_id,
        evidence_revision_id=operation_id,
        source_person_id=owner_person_id,
        target_person_id=referenced_person_id,
        relationship_type="REFERENCES",
        directionality="DIRECTED",
        source=source,
        created_operation_id=operation_id,
        created_at=created_at,
    )
    row = conn.execute(
        """
        SELECT active, created_operation_id FROM relationship_evidence
        WHERE evidence_id=?
        """,
        (evidence_id,),
    ).fetchone()
    if row is None or not bool(row["active"]) or row["created_operation_id"] != operation_id:
        raise RuntimeError("R02 failed to append a repair-owned evidence revision")
    return evidence_id


def _r02_immutable_fingerprint(conn: sqlite3.Connection) -> str:
    tables = ("notes", "note_revisions", "note_revision_mentions")
    return _r01_hash({
        table: [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} ORDER BY rowid"
        )]
        for table in tables
    })


def _r02_unrelated_fingerprint(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
) -> str:
    tables = (
        "persons", "embeddings", "biometric_enrollment_history", "observations",
        "observation_media", "observation_participants", "observation_face_assignments",
        "identity_corrections", "merge_operations", "merge_affected_items",
        "merge_conflict_resolutions",
    )
    snapshot: dict[str, object] = {
        table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }
    snapshot["unrelated_occurrences"] = [dict(row) for row in conn.execute(
        """
        SELECT * FROM note_mentions
        WHERE NOT (note_id=? AND referenced_person_id=?) ORDER BY rowid
        """,
        (precondition.note_id, precondition.referenced_person_id),
    )]
    snapshot["unrelated_evidence"] = [dict(row) for row in conn.execute(
        """
        SELECT e.* FROM relationship_evidence e
        WHERE NOT (
          e.evidence_type='NOTE_REFERENCE' AND EXISTS (
            SELECT 1 FROM note_mentions m
            WHERE m.mention_id=e.source_entity_id
              AND m.note_id=? AND m.referenced_person_id=?
          )
        )
        ORDER BY e.rowid
        """,
        (precondition.note_id, precondition.referenced_person_id),
    )]
    snapshot["prior_journal"] = [dict(row) for row in conn.execute(
        "SELECT * FROM operation_journal WHERE operation_id<>? ORDER BY rowid",
        (operation_id,),
    )]
    snapshot["prior_journal_history"] = [dict(row) for row in conn.execute(
        """
        SELECT * FROM operation_journal_status_history
        WHERE operation_id<>? ORDER BY rowid
        """,
        (operation_id,),
    )]
    return _r01_hash(snapshot)


def _r02_retired_history_fingerprint(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
) -> str:
    retired_occurrence_ids = tuple(
        item for item in precondition.occurrence_ids
        if item not in precondition.active_occurrence_ids
    )
    retired_evidence_ids = tuple(
        item for item in precondition.evidence_ids
        if item not in precondition.active_evidence_ids
    )

    def selected(table: str, column: str, ids: tuple[str, ...]) -> list[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} WHERE {column} IN ({placeholders}) ORDER BY rowid",
            ids,
        )]

    return _r01_hash({
        "occurrences": selected("note_mentions", "mention_id", retired_occurrence_ids),
        "evidence": selected("relationship_evidence", "evidence_id", retired_evidence_ids),
    })


_P11D_REVERT_SPEC_VERSION = 1
_P11D_FINGERPRINT_VERSION = "p11-d-schema28-merge-revert-v1"
_P11D_REVERT_OPERATION_TYPE = "identity.merge.revert"


def _p11d_checkpoint(
    failure_injector: Callable[[str], None] | None, seam: str,
) -> None:
    if failure_injector is not None:
        failure_injector(seam)


def _p11d_person_fingerprint(conn: sqlite3.Connection, person_id: str) -> str:
    row = conn.execute(
        "SELECT * FROM persons WHERE person_id=?", (person_id,),
    ).fetchone()
    if row is None:
        raise OperationRevertRefused(f"Affected person is missing: {person_id}")
    return _r01_hash(dict(row))


def _p11d_person_stable_fingerprint(conn: sqlite3.Connection, person_id: str) -> str:
    row = conn.execute(
        "SELECT * FROM persons WHERE person_id=?", (person_id,),
    ).fetchone()
    if row is None:
        raise OperationRevertRefused(f"Affected person is missing: {person_id}")
    value = dict(row)
    for field in (
        "lifecycle_status", "canonical_person_id", "deleted_at",
        "lifecycle_changed_at",
    ):
        value.pop(field, None)
    return _r01_hash(value)


def _p11d_merge_state_fingerprint(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> str:
    return _r01_hash({
        "operation": [dict(row) for row in conn.execute(
            "SELECT * FROM merge_operations WHERE merge_operation_id=?",
            (merge_operation_id,),
        )],
        "items": [dict(row) for row in conn.execute(
            """
            SELECT * FROM merge_affected_items
            WHERE merge_operation_id=? ORDER BY item_type, item_id
            """,
            (merge_operation_id,),
        )],
        "conflicts": [dict(row) for row in conn.execute(
            """
            SELECT * FROM merge_conflict_resolutions
            WHERE merge_operation_id=? ORDER BY category, field_name, conflict_id
            """,
            (merge_operation_id,),
        )],
    })


def _p11d_immutable_fingerprint(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> str:
    return _p11d_merge_state_fingerprint(conn, merge_operation_id)


def _p11d_affected_entities(
    operation: dict, manifest: MergeOperation,
) -> tuple[tuple[str, str], ...]:
    entities: set[tuple[str, str]] = {
        ("person", manifest.source_person_id),
        ("person", manifest.target_person_id),
        ("operation", manifest.merge_operation_id),
    }
    for item in operation.get("affected_entities") or []:
        if isinstance(item, dict) and str(item.get("entity_id") or "").strip():
            entities.add((
                str(item.get("entity_type") or "entity").strip().lower(),
                str(item["entity_id"]),
            ))
    for item in manifest.affected_items:
        entities.add((item.item_type.lower(), item.item_id))
    return tuple(sorted(entities))


def _p11d_later_dependencies(
    conn: sqlite3.Connection,
    operation_id: str,
    affected_entities: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    original = conn.execute(
        "SELECT rowid FROM operation_journal WHERE operation_id=?", (operation_id,),
    ).fetchone()
    if original is None:
        raise OperationRevertRefused("Operation history is incomplete")
    affected_ids = {entity_id for _, entity_id in affected_entities}
    dependencies: list[str] = []
    rows = conn.execute(
        """
        SELECT operation_id, operation_type, status, affected_entities
        FROM operation_journal
        WHERE rowid>? AND status IN ('STARTED','COMMITTED','REVERTED')
        ORDER BY rowid
        """,
        (original["rowid"],),
    ).fetchall()
    for row in rows:
        if row["operation_type"] == "graph.projection.rebuild":
            continue
        try:
            entities = json.loads(row["affected_entities"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OperationRevertRefused("Later operation history is malformed") from exc
        later_ids = {
            str(item.get("entity_id"))
            for item in entities if isinstance(item, dict) and item.get("entity_id") is not None
        }
        if affected_ids & later_ids:
            dependencies.append(str(row["operation_id"]))
    return tuple(dependencies)


def _p11d_precondition_from_report(
    conn: sqlite3.Connection,
    report: object,
    operation_id: str,
) -> OperationRevertPrecondition:
    if getattr(report, "schema_version", None) != SCHEMA_VERSION:
        raise OperationRevertRefused("Revert requires the current schema")
    if getattr(report, "findings_truncated", True):
        raise OperationRevertRefused("Revert requires an untruncated P11-A report", report=report)
    blocking = tuple(
        finding for finding in getattr(report, "findings", ())
        if finding.severity.value in {"CRITICAL", "ERROR"}
    )
    if blocking:
        raise OperationRevertRefused(
            "Revert requires a clean authoritative P11-A preflight", report=report,
        )
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        raise OperationRevertRefused("Operation history is incomplete")
    if operation["operation_type"] != "identity.merge":
        raise OperationRevertRefused(
            f"Operation type is not in the revert whitelist: {operation['operation_type']}"
        )
    if operation["status"] == "REVERTED":
        raise OperationRevertRefused("Operation has already been reverted")
    if operation["status"] != "COMMITTED":
        raise OperationRevertRefused("Only a committed operation can be reverted")
    statuses = tuple(item["to_status"] for item in operation["status_history"])
    if statuses != ("STARTED", "COMMITTED"):
        raise OperationRevertRefused("Operation journal history is incomplete or ambiguous")
    if conn.execute("SELECT 1 FROM relationship_evidence WHERE source_entity_type = 'OBSERVATION' AND (created_operation_id = ? OR deactivated_operation_id = ?) LIMIT 1", (operation_id, operation_id)).fetchone():
        raise OperationRevertRefused("Merge changed Event Relations and is outside the safe revert subset")
    if conn.execute("SELECT 1 FROM relationship_evidence WHERE source_entity_type = 'MANUAL_ASSERTION' AND deactivated_operation_id = ? LIMIT 1", (operation_id,)).fetchone():
        raise OperationRevertRefused("Merge retired standing Manual Associations and is outside the safe revert subset")
    manifest = _get_merge_operation(conn, operation_id)
    if manifest is None or manifest.operation_journal_id != operation_id:
        raise OperationRevertRefused("Merge manifest history is incomplete")
    if (
        manifest.previous_source_lifecycle_status != "ACTIVE"
        or manifest.previous_source_canonical_person_id is not None
        or manifest.previous_target_lifecycle_status != "ACTIVE"
        or manifest.previous_target_canonical_person_id is not None
    ):
        raise OperationRevertRefused(
            "Merge previous lifecycle/canonical state is not safely reversible"
        )
    if manifest.conflicts:
        raise OperationRevertRefused(
            "Merge changed survivor profile or note state and is not safely reversible"
        )
    if any(
        item.item_type in {"CURRENT_STATE", "PROFILE_FIELD"}
        for item in manifest.affected_items
    ):
        raise OperationRevertRefused(
            "Merge changed survivor current state and is not safely reversible"
        )
    person_items = tuple(
        item for item in manifest.affected_items
        if item.item_type == "PERSON" and item.item_id == manifest.source_person_id
    )
    if len(person_items) != 1 or person_items[0].before_state != {
        "lifecycle_status": "ACTIVE", "canonical_person_id": None,
    } or person_items[0].after_state != {
        "lifecycle_status": "MERGED", "canonical_person_id": manifest.target_person_id,
    }:
        raise OperationRevertRefused("Merge inverse manifest is incomplete or ambiguous")
    source_row = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at, lifecycle_changed_at
        FROM persons WHERE person_id=?
        """,
        (manifest.source_person_id,),
    ).fetchone()
    target_row = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at, lifecycle_changed_at
        FROM persons WHERE person_id=?
        """,
        (manifest.target_person_id,),
    ).fetchone()
    if (
        source_row is None
        or source_row["lifecycle_status"] != "MERGED"
        or source_row["canonical_person_id"] != manifest.target_person_id
        or source_row["deleted_at"] is None
        or not source_row["lifecycle_changed_at"]
    ):
        raise OperationRevertRefused("Current merge source state differs from the expected result")
    if (
        target_row is None
        or target_row["lifecycle_status"] != "ACTIVE"
        or target_row["canonical_person_id"] is not None
        or target_row["deleted_at"] is not None
    ):
        raise OperationRevertRefused("Merge survivor is no longer terminal and active")
    affected_entities = _p11d_affected_entities(operation, manifest)
    dependencies = _p11d_later_dependencies(conn, operation_id, affected_entities)
    dependency_state_fingerprint = _r01_hash({
        "operation_id": operation_id,
        "affected_entities": affected_entities,
        "later_dependency_operation_ids": dependencies,
    })
    if dependencies:
        raise OperationRevertRefused(
            "Later dependent operations prevent safe revert: " + ", ".join(dependencies)
        )
    graph_revision = _graph_revision_token(conn)
    if getattr(report, "graph_revision", None) != graph_revision:
        raise OperationRevertRefused("P11-A preflight is stale")
    journal_history_fingerprint = _r01_hash(operation)
    merge_state_fingerprint = _p11d_merge_state_fingerprint(conn, operation_id)
    graph_projection_fingerprint = _r01_table_fingerprint(conn, "graph_connections")
    target_state_fingerprint = _p11d_person_fingerprint(conn, manifest.target_person_id)
    relevant_revisions = (
        ("graph_revision", graph_revision),
        ("source_lifecycle_changed_at", str(source_row["lifecycle_changed_at"])),
        ("target_lifecycle_changed_at", str(target_row["lifecycle_changed_at"] or "")),
        ("operation_completed_at", str(operation["completed_at"] or "")),
    )
    payload = {
        "revert_spec_version": _P11D_REVERT_SPEC_VERSION,
        "fingerprint_version": _P11D_FINGERPRINT_VERSION,
        "operation_id": operation_id,
        "operation_type": operation["operation_type"],
        "journal_state": operation["status"],
        "journal_history_fingerprint": journal_history_fingerprint,
        "affected_entities": affected_entities,
        "relevant_revisions": relevant_revisions,
        "graph_revision": graph_revision,
        "graph_projection_fingerprint": graph_projection_fingerprint,
        "dependency_operation_ids": dependencies,
        "dependency_state_fingerprint": dependency_state_fingerprint,
        "merge_state_fingerprint": merge_state_fingerprint,
        "source_person_id": manifest.source_person_id,
        "target_person_id": manifest.target_person_id,
        "expected_source_lifecycle_status": "MERGED",
        "expected_source_canonical_person_id": manifest.target_person_id,
        "expected_source_lifecycle_changed_at": str(source_row["lifecycle_changed_at"]),
        "expected_target_state_fingerprint": target_state_fingerprint,
    }
    return OperationRevertPrecondition(
        **payload,
        fingerprint=_r01_hash(payload),
    )


def _validate_p11d_request_shape(precondition: OperationRevertPrecondition) -> None:
    if not isinstance(precondition, OperationRevertPrecondition):
        raise OperationRevertRefused("A typed P11-D revert precondition is required")
    if (
        precondition.revert_spec_version != _P11D_REVERT_SPEC_VERSION
        or precondition.fingerprint_version != _P11D_FINGERPRINT_VERSION
        or precondition.operation_type != "identity.merge"
        or precondition.journal_state != "COMMITTED"
        or precondition.dependency_operation_ids
    ):
        raise OperationRevertRefused("Unsupported or unsafe revert precondition")
    payload = asdict(precondition)
    fingerprint = payload.pop("fingerprint")
    if _r01_hash(payload) != fingerprint:
        raise OperationRevertRefused("Revert precondition fingerprint is invalid")


def _p11d_existing_result(
    conn: sqlite3.Connection,
    operation_id: str,
    precondition: OperationRevertPrecondition,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != _P11D_REVERT_OPERATION_TYPE:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    if operation.get("details", {}).get("fingerprint") != precondition.fingerprint:
        raise ValueError("Revert operation ID belongs to a different request")
    if operation["status"] != "COMMITTED":
        raise ValueError(
            "A failed or incomplete revert operation ID cannot be reused"
        )
    history = operation.get("status_history") or []
    return dict(history[-1]["details"]) if history else {}
