from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from sentriface.models import utc_now
from sentriface.secure_storage import connect_database
from sentriface.storage.sqlite_store import SCHEMA_VERSION, _expected_graph_connections


class IntegritySeverity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class FutureIntegrityHandling(str, Enum):
    SAFE_REBUILD = "SAFE_REBUILD"
    STRUCTURED_REPAIR = "STRUCTURED_REPAIR"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    UNRECOVERABLE_FROM_LOCAL_STATE = "UNRECOVERABLE_FROM_LOCAL_STATE"


@dataclass(frozen=True)
class IntegrityInvariant:
    invariant_id: str
    domain: str
    severity: IntegritySeverity
    authoritative_source: str
    condition: str
    evidence_returned: str
    safely_rebuildable: bool
    human_intervention_required: bool
    future_handling: FutureIntegrityHandling


@dataclass(frozen=True)
class IntegrityFinding:
    invariant_id: str
    domain: str
    severity: IntegritySeverity
    message: str
    entity_ids: tuple[tuple[str, str], ...]
    evidence: tuple[tuple[str, str], ...] = ()
    future_handling: FutureIntegrityHandling = FutureIntegrityHandling.MANUAL_REVIEW


@dataclass(frozen=True)
class IntegrityReport:
    started_at: str
    completed_at: str
    schema_version: int
    graph_revision: str | None
    status: str
    checks_run: tuple[str, ...]
    findings: tuple[IntegrityFinding, ...]
    counts_by_severity: dict[str, int]
    findings_truncated: bool = False


def _invariant(
    invariant_id: str,
    domain: str,
    severity: IntegritySeverity,
    source: str,
    condition: str,
    evidence: str,
    handling: FutureIntegrityHandling,
) -> IntegrityInvariant:
    return IntegrityInvariant(
        invariant_id=invariant_id,
        domain=domain,
        severity=severity,
        authoritative_source=source,
        condition=condition,
        evidence_returned=evidence,
        safely_rebuildable=handling is FutureIntegrityHandling.SAFE_REBUILD,
        human_intervention_required=handling in {
            FutureIntegrityHandling.MANUAL_REVIEW,
            FutureIntegrityHandling.UNRECOVERABLE_FROM_LOCAL_STATE,
        },
        future_handling=handling,
    )


# This is the fixed P11-A registry. IDs are part of the diagnostic contract.
INTEGRITY_INVARIANTS: tuple[IntegrityInvariant, ...] = (
    _invariant("P11-SCHEMA-001", "SCHEMA", IntegritySeverity.CRITICAL, "SQLite schema and migration registry", "The database is structurally readable at the current supported schema and required P11 tables/columns exist.", "schema version and missing object names", FutureIntegrityHandling.UNRECOVERABLE_FROM_LOCAL_STATE),
    _invariant("P11-SCHEMA-002", "SCHEMA", IntegritySeverity.CRITICAL, "All authoritative tables", "SQLite integrity_check succeeds.", "SQLite diagnostic text", FutureIntegrityHandling.UNRECOVERABLE_FROM_LOCAL_STATE),
    _invariant("P11-SCHEMA-003", "SCHEMA", IntegritySeverity.ERROR, "Declared foreign keys", "Authoritative records have no foreign-key violations; projection FK drift is reported separately.", "table, rowid, parent and FK index", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-IDENTITY-001", "IDENTITY", IntegritySeverity.CRITICAL, "persons", "Lifecycle, identity, biometric, timestamp and canonical-field combinations are legal.", "person ID and conflicting fields", FutureIntegrityHandling.STRUCTURED_REPAIR),
    _invariant("P11-IDENTITY-002", "IDENTITY", IntegritySeverity.CRITICAL, "persons.canonical_person_id", "Every canonical target exists and every chain terminates without a cycle.", "source ID, path and missing/cyclic target", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-IDENTITY-003", "IDENTITY", IntegritySeverity.ERROR, "persons canonical mapping", "A merged chain terminates at an ACTIVE, non-deleted survivor with no canonical target.", "source ID and terminal ID/state", FutureIntegrityHandling.STRUCTURED_REPAIR),
    _invariant("P11-CORRECTION-001", "CORRECTION", IntegritySeverity.CRITICAL, "identity_corrections and original assignment/enrollment ownership", "Correction rows have the required typed scope and each ordered ownership/assignment chain is continuous.", "correction, subject and adjacent endpoint IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-CORRECTION-002", "CORRECTION", IntegritySeverity.ERROR, "identity_corrections then persons canonical mapping", "Correction-before-canonical resolution yields existing legal effective identities and observation transformations remain applicable.", "correction/observation and effective IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-OBSERVATION-001", "OBSERVATION", IntegritySeverity.ERROR, "observations and observation_participants", "Finalized observations have a finalization timestamp and at least one raw and effective participant; drafts have no finalization timestamp.", "observation ID, status and participant counts", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-OBSERVATION-002", "OBSERVATION", IntegritySeverity.ERROR, "observation_participants plus corrections/canonical mapping", "Raw participant keys are unique and current effective participants are unique existing identities.", "observation and duplicate/effective person IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-OBSERVATION-003", "OBSERVATION", IntegritySeverity.ERROR, "observation_media and durable media provenance", "Each observation media row retains a non-empty identifier and a durable database provenance reference.", "observation ID, media ID and path", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-REVIEW-001", "REVIEW", IntegritySeverity.CRITICAL, "photo_reviews, face decisions, observations and journal", "Completed reviews have complete decisions and agree with their committed operation and optional finalized observation; other reviews have no completion result.", "review, face, observation and operation IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-EVIDENCE-001", "GRAPH_EVIDENCE", IntegritySeverity.ERROR, "relationship_evidence and typed source records", "Evidence types, source kinds, directionality, endpoint ordering, lifecycle fields and source references are coherent; active NOTE_REFERENCE rows require a current active source occurrence, while fully retired rows remain historical provenance.", "evidence ID, raw endpoints and source ID", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-EVIDENCE-002", "GRAPH_EVIDENCE", IntegritySeverity.ERROR, "active relationship_evidence plus correction/canonical interpretation", "Active evidence resolves to legal effective endpoints; canonical self-links remain historical evidence but are not projected.", "evidence ID and effective endpoints", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-GRAPH-001", "GRAPH_PROJECTION", IntegritySeverity.ERROR, "active relationship_evidence", "graph_connections exactly equals the deterministic aggregate of active evidence after canonical resolution and self-edge suppression.", "edge key and expected/stored aggregate", FutureIntegrityHandling.SAFE_REBUILD),
    _invariant("P11-NOTE-001", "NOTE", IntegritySeverity.ERROR, "notes, note_revisions and note_revision_mentions", "Every note has contiguous immutable revisions and revision mention references belong to existing revisions and persons.", "note/revision/person IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-NOTE-002", "NOTE", IntegritySeverity.ERROR, "notes, latest note revision mentions, and existing note_mentions occurrence history", "For each existing note/person occurrence group, exactly one occurrence is active when the active latest revision requires that non-self person and none is active otherwise; inactive historical occurrences remain valid with complete same-note retirement provenance.", "note/person IDs, active occurrence IDs/count, latest revision ID, and malformed occurrence provenance", FutureIntegrityHandling.STRUCTURED_REPAIR),
    _invariant("P11-NOTE-003", "NOTE", IntegritySeverity.ERROR, "note_mentions and NOTE_REFERENCE evidence", "Each active non-self mention has exactly one matching active directed NOTE_REFERENCE evidence row, and inactive/retired state is not projected.", "mention and evidence IDs", FutureIntegrityHandling.STRUCTURED_REPAIR),
    _invariant("P11-MERGE-001", "MERGE", IntegritySeverity.CRITICAL, "merge_operations, persons and operation_journal", "Every committed merge manifest agrees with its journal identity/actor and the source resolves to its recorded survivor.", "merge, journal, source and survivor IDs", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-MERGE-002", "MERGE", IntegritySeverity.CRITICAL, "merge affected items/conflicts and inverse payloads", "Merge manifests retain structurally complete affected ownership/action state and conflict inverse data.", "merge/item/conflict IDs and missing fields", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-JOURNAL-001", "JOURNAL", IntegritySeverity.CRITICAL, "operation_journal_status_history", "Each operation history starts at STARTED, follows only allowed transitions, and ends at the row status.", "operation and transition IDs/statuses", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-JOURNAL-002", "JOURNAL", IntegritySeverity.ERROR, "operation_journal", "Journal JSON fields are structurally valid and completion timestamps agree with status.", "operation ID and invalid field", FutureIntegrityHandling.MANUAL_REVIEW),
    _invariant("P11-JOURNAL-003", "JOURNAL", IntegritySeverity.CRITICAL, "journal-linked authoritative result tables", "Committed domain operations have their expected result and non-committed operations did not leave visible authoritative result rows.", "operation ID/type and result entity IDs", FutureIntegrityHandling.MANUAL_REVIEW),
)

_INVARIANTS_BY_ID = {item.invariant_id: item for item in INTEGRITY_INVARIANTS}
_SEVERITY_ORDER = {
    IntegritySeverity.INFO: 0,
    IntegritySeverity.WARNING: 1,
    IntegritySeverity.ERROR: 2,
    IntegritySeverity.CRITICAL: 3,
}
_ALLOWED_TRANSITIONS = {
    "STARTED": {"COMMITTED", "FAILED", "ROLLED_BACK"},
    "FAILED": {"ROLLED_BACK"},
    "COMMITTED": {"REVERTED"},
    "ROLLED_BACK": set(),
    "REVERTED": set(),
}


class ReadOnlyIntegrityChecker:
    """Explicit, snapshot-consistent P11-A checker. It never initializes or mutates a store."""

    def __init__(
        self,
        db_path: Path,
        *,
        database_key: bytes | None = None,
        max_findings: int = 10_000,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if max_findings < 1:
            raise ValueError("max_findings must be positive")
        self.db_path = Path(db_path)
        self.database_key = database_key
        self.max_findings = max_findings
        self.clock = clock
        self._findings: list[IntegrityFinding] = []
        self._truncated = False
        self._people: dict[str, tuple[str, str | None, str | None]] = {}
        self._canonical_cache: dict[str, tuple[str | None, tuple[str, ...], str | None]] = {}

    def run(self) -> IntegrityReport:
        self._findings = []
        self._truncated = False
        self._people = {}
        self._canonical_cache = {}
        started_at = self.clock()
        checks_run: list[str] = []
        schema_version = -1
        graph_revision: str | None = None
        with closing(self._connect_read_only()) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN")
            schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            graph_row = self._safe_one(
                conn, "SELECT revision FROM graph_state WHERE singleton_id = 1"
            )
            if graph_row is not None:
                try:
                    graph_revision = f"g{int(graph_row[0])}"
                except (TypeError, ValueError):
                    self._add("P11-SCHEMA-001", "Graph revision value is invalid", evidence={"graph_revision": graph_row[0]})
            all_checks: tuple[tuple[str, Callable[[sqlite3.Connection], None]], ...] = (
                ("P11-SCHEMA-001", self._check_schema),
                ("P11-SCHEMA-002", self._check_sqlite_integrity),
                ("P11-SCHEMA-003", self._check_foreign_keys),
                ("P11-IDENTITY-001", self._check_person_state),
                ("P11-IDENTITY-002", self._check_canonical_chains),
                ("P11-IDENTITY-003", self._check_canonical_survivors),
                ("P11-CORRECTION-001", self._check_correction_shape_and_chains),
                ("P11-CORRECTION-002", self._check_correction_interpretation),
                ("P11-OBSERVATION-001", self._check_observation_finalization),
                ("P11-OBSERVATION-002", self._check_participant_uniqueness),
                ("P11-OBSERVATION-003", self._check_media_references),
                ("P11-REVIEW-001", self._check_reviews),
                ("P11-EVIDENCE-001", self._check_evidence_sources),
                ("P11-EVIDENCE-002", self._check_evidence_resolution),
                ("P11-GRAPH-001", self._check_graph_projection),
                ("P11-NOTE-001", self._check_note_revisions),
                ("P11-NOTE-002", self._check_note_mentions),
                ("P11-NOTE-003", self._check_note_evidence),
                ("P11-MERGE-001", self._check_merge_results),
                ("P11-MERGE-002", self._check_merge_inverse_data),
                ("P11-JOURNAL-001", self._check_journal_transitions),
                ("P11-JOURNAL-002", self._check_journal_structure),
                ("P11-JOURNAL-003", self._check_journal_results),
            )
            checks = all_checks if schema_version == SCHEMA_VERSION else all_checks[:3]
            for invariant_id, check in checks:
                checks_run.append(invariant_id)
                try:
                    check(conn)
                except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AssertionError) as exc:
                    self._add(
                        invariant_id,
                        "Check could not complete because required state was unreadable or malformed",
                        evidence={"check_error": str(exc)[:240]},
                    )
        findings = tuple(sorted(
            self._findings,
            key=lambda item: (item.invariant_id, item.entity_ids, item.message, item.evidence),
        ))
        counts = {severity.value: 0 for severity in IntegritySeverity}
        for finding in findings:
            counts[finding.severity.value] += 1
        worst = max(
            (finding.severity for finding in findings),
            key=lambda value: _SEVERITY_ORDER[value],
            default=None,
        )
        return IntegrityReport(
            started_at=started_at,
            completed_at=self.clock(),
            schema_version=schema_version,
            graph_revision=graph_revision,
            status=worst.value if worst is not None else "PASS",
            checks_run=tuple(checks_run),
            findings=findings,
            counts_by_severity=counts,
            findings_truncated=self._truncated,
        )

    def _connect_read_only(self):
        if self.database_key is None:
            uri = f"file:{quote(str(self.db_path.resolve()))}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=30)
            conn.row_factory = sqlite3.Row
            return conn
        conn = connect_database(
            self.db_path, self.database_key, timeout=30, row_factory=True,
        )
        return conn

    @staticmethod
    def _safe_one(conn: sqlite3.Connection, sql: str):
        try:
            return conn.execute(sql).fetchone()
        except sqlite3.DatabaseError:
            return None

    def _add(
        self,
        invariant_id: str,
        message: str,
        entities: dict[str, object] | None = None,
        evidence: dict[str, object] | None = None,
    ) -> None:
        if len(self._findings) >= self.max_findings:
            self._truncated = True
            return
        invariant = _INVARIANTS_BY_ID[invariant_id]
        self._findings.append(IntegrityFinding(
            invariant_id=invariant_id,
            domain=invariant.domain,
            severity=invariant.severity,
            message=message,
            entity_ids=tuple(sorted(
                (str(key), str(value)) for key, value in (entities or {}).items()
                if value is not None
            )),
            evidence=tuple(sorted(
                (str(key), str(value)) for key, value in (evidence or {}).items()
                if value is not None
            )),
            future_handling=invariant.future_handling,
        ))

    def _check_schema(self, conn: sqlite3.Connection) -> None:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            self._add("P11-SCHEMA-001", "Database schema version is not supported by this checker", evidence={"expected_version": SCHEMA_VERSION, "actual_version": version})
        required = {
            "persons", "observations", "observation_media", "observation_participants",
            "photo_reviews", "photo_review_faces", "observation_face_assignments",
            "identity_corrections", "relationship_evidence", "graph_connections",
            "graph_state", "notes", "note_revisions", "note_revision_mentions",
            "note_mentions", "merge_operations", "merge_affected_items",
            "merge_conflict_resolutions", "operation_journal",
            "operation_journal_status_history",
        }
        actual = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for name in sorted(required - actual):
            self._add("P11-SCHEMA-001", "Required table is missing", entities={"table": name})
        required_columns = {
            "persons": {"person_id", "lifecycle_status", "canonical_person_id", "identity_status", "biometric_status"},
            "observations": {"observation_id", "status", "finalized_at", "created_operation_id"},
            "identity_corrections": {"correction_id", "correction_type", "from_person_id", "to_person_id", "operation_id"},
            "relationship_evidence": {"evidence_id", "evidence_revision_id", "source_person_id", "target_person_id", "active"},
            "graph_connections": {"source_person_id", "target_person_id", "evidence_count", "evidence_types"},
            "operation_journal": {"operation_id", "operation_type", "status", "affected_entities", "details"},
            "merge_affected_items": {"raw_owner_person_id", "effective_owner_person_id", "action", "before_state", "after_state"},
        }
        for table, expected_columns in sorted(required_columns.items()):
            if table not in actual:
                continue
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
            for column in sorted(expected_columns - columns):
                self._add("P11-SCHEMA-001", "Required column is missing", entities={"table": table, "column": column})

    def _check_sqlite_integrity(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("PRAGMA integrity_check"):
            if str(row[0]).lower() != "ok":
                self._add("P11-SCHEMA-002", "SQLite reported physical/logical database damage", evidence={"diagnostic": str(row[0])[:400]})

    def _check_foreign_keys(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("PRAGMA foreign_key_check"):
            table = str(row[0])
            if table == "graph_connections":
                self._add("P11-GRAPH-001", "Derived graph row has a dangling person reference", entities={"table": table, "rowid": row[1]}, evidence={"parent": row[2], "fk_index": row[3]})
            else:
                self._add("P11-SCHEMA-003", "Authoritative row has a dangling foreign-key reference", entities={"table": table, "rowid": row[1]}, evidence={"parent": row[2], "fk_index": row[3]})

    def _load_people(self, conn: sqlite3.Connection) -> None:
        if self._people:
            return
        for row in conn.execute("SELECT person_id, lifecycle_status, canonical_person_id, deleted_at FROM persons ORDER BY person_id"):
            self._people[str(row[0])] = (str(row[1]), row[2], row[3])

    def _resolve(self, person_id: object) -> tuple[str | None, tuple[str, ...], str | None]:
        value = str(person_id)
        cached = self._canonical_cache.get(value)
        if cached is not None:
            return cached
        path: list[str] = []
        seen: set[str] = set()
        current = value
        while True:
            if current in seen:
                result = (None, tuple(path + [current]), "cycle")
                break
            seen.add(current)
            path.append(current)
            row = self._people.get(current)
            if row is None:
                result = (None, tuple(path), "missing")
                break
            lifecycle, target, _deleted_at = row
            if lifecycle != "MERGED":
                if target is not None:
                    result = (None, tuple(path), "non_merged_mapping")
                else:
                    result = (current, tuple(path), None)
                break
            if not target:
                result = (None, tuple(path), "merged_without_target")
                break
            current = str(target)
        self._canonical_cache[value] = result
        return result

    def _check_person_state(self, conn: sqlite3.Connection) -> None:
        valid_lifecycle = {"ACTIVE", "ARCHIVED", "DELETED", "MERGED"}
        valid_identity = {"IDENTIFIED", "UNIDENTIFIED"}
        valid_biometric = {"NO_FACE", "ENROLLED"}
        for row in conn.execute("SELECT person_id, lifecycle_status, canonical_person_id, deleted_at, identity_status, biometric_status FROM persons ORDER BY person_id"):
            pid, lifecycle, target, deleted_at, identity, biometric = row
            problems: list[str] = []
            if lifecycle not in valid_lifecycle:
                problems.append("invalid lifecycle")
            if identity not in valid_identity:
                problems.append("invalid identity status")
            if biometric not in valid_biometric:
                problems.append("invalid biometric status")
            if (lifecycle == "ACTIVE") != (deleted_at is None):
                problems.append("lifecycle/deleted_at disagreement")
            if (lifecycle == "MERGED") != (target is not None):
                problems.append("lifecycle/canonical mapping disagreement")
            if target == pid:
                problems.append("self canonical mapping")
            if problems:
                self._add("P11-IDENTITY-001", "; ".join(problems), entities={"person_id": pid}, evidence={"lifecycle": lifecycle, "canonical_person_id": target, "deleted_at": deleted_at, "identity_status": identity, "biometric_status": biometric})

    def _check_canonical_chains(self, conn: sqlite3.Connection) -> None:
        self._load_people(conn)
        reported_cycles: set[frozenset[str]] = set()
        for pid in sorted(self._people):
            terminal, path, error = self._resolve(pid)
            if error is None:
                continue
            if error == "cycle":
                cycle = frozenset(path[path.index(path[-1]):])
                if cycle in reported_cycles:
                    continue
                reported_cycles.add(cycle)
            self._add("P11-IDENTITY-002", "Canonical chain does not terminate legally", entities={"person_id": pid}, evidence={"path": " -> ".join(path), "reason": error, "terminal": terminal})

    def _check_canonical_survivors(self, conn: sqlite3.Connection) -> None:
        self._load_people(conn)
        for pid, (lifecycle, target, _deleted) in sorted(self._people.items()):
            if lifecycle != "MERGED" or not target:
                continue
            terminal, _path, error = self._resolve(pid)
            if error is not None or terminal is None:
                continue
            terminal_state = self._people[terminal]
            if terminal_state[0] != "ACTIVE" or terminal_state[2] is not None:
                self._add("P11-IDENTITY-003", "Merged identity does not terminate at an active canonical survivor", entities={"person_id": pid, "terminal_person_id": terminal}, evidence={"terminal_lifecycle": terminal_state[0], "terminal_deleted_at": terminal_state[2]})

    def _check_correction_shape_and_chains(self, conn: sqlite3.Connection) -> None:
        chains: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        sql = "SELECT rowid, * FROM identity_corrections ORDER BY created_at, rowid, correction_id"
        for row in conn.execute(sql):
            ctype = str(row["correction_type"])
            required = {
                "OBSERVATION_IDENTITY": ("observation_id",),
                "FACE_ASSIGNMENT": ("observation_id", "face_assignment_id", "embedding_id"),
                "FACE_OWNERSHIP": ("embedding_id",),
            }.get(ctype)
            if required is None or any(row[name] is None for name in required):
                self._add("P11-CORRECTION-001", "Correction has an invalid typed scope", entities={"correction_id": row["correction_id"]}, evidence={"correction_type": ctype, "observation_id": row["observation_id"], "face_assignment_id": row["face_assignment_id"], "embedding_id": row["embedding_id"]})
                continue
            if ctype == "FACE_ASSIGNMENT":
                chains[(ctype, str(row["face_assignment_id"]))].append(row)
            elif ctype == "FACE_OWNERSHIP":
                chains[(ctype, str(row["embedding_id"]))].append(row)
        for (ctype, subject), rows in sorted(chains.items()):
            previous_to: str | None = None
            for row in rows:
                current_from = str(row["from_person_id"])
                if previous_to is not None and current_from != previous_to:
                    self._add("P11-CORRECTION-001", "Correction chain is discontinuous", entities={"correction_id": row["correction_id"], "subject_id": subject}, evidence={"correction_type": ctype, "expected_from_person_id": previous_to, "actual_from_person_id": current_from})
                previous_to = str(row["to_person_id"])

    def _effective_participants(self, conn: sqlite3.Connection) -> dict[str, tuple[set[str], list[str]]]:
        self._load_people(conn)
        raw: dict[str, set[str]] = defaultdict(set)
        for row in conn.execute("SELECT observation_id, person_id FROM observation_participants ORDER BY observation_id, person_id"):
            raw[str(row[0])].add(str(row[1]))
        assignment_base: dict[str, dict[str, str]] = defaultdict(dict)
        assignment_observation: dict[str, str] = {}
        for row in conn.execute("SELECT assignment_id, observation_id, original_person_id FROM observation_face_assignments ORDER BY observation_id, assignment_id"):
            aid, oid, pid = map(str, row)
            assignment_base[oid][aid] = pid
            assignment_observation[aid] = oid
        for row in conn.execute("SELECT correction_type, observation_id, face_assignment_id, from_person_id, to_person_id FROM identity_corrections ORDER BY created_at, rowid, correction_id"):
            if row[0] == "FACE_ASSIGNMENT" and row[2] is not None:
                oid = assignment_observation.get(str(row[2]), str(row[1] or ""))
                if oid in assignment_base and str(row[2]) in assignment_base[oid]:
                    assignment_base[oid][str(row[2])] = str(row[4])
        result: dict[str, tuple[set[str], list[str]]] = {}
        observation_ids = {str(row[0]) for row in conn.execute("SELECT observation_id FROM observations")}
        observation_corrections: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in conn.execute("SELECT observation_id, from_person_id, to_person_id FROM identity_corrections WHERE correction_type = 'OBSERVATION_IDENTITY' ORDER BY created_at, rowid, correction_id"):
            observation_corrections[str(row[0])].append((str(row[1]), str(row[2])))
        originals_by_observation: dict[str, set[str]] = {
            oid: set(values.values()) for oid, values in assignment_base.items()
        }
        for oid in observation_ids:
            current = set(raw.get(oid, set())) - originals_by_observation.get(oid, set())
            current.update(assignment_base.get(oid, {}).values())
            problems: list[str] = []
            for from_pid, to_pid in observation_corrections.get(oid, []):
                if from_pid not in current:
                    problems.append(f"correction source {from_pid} is not current")
                else:
                    current.remove(from_pid)
                    current.add(to_pid)
            effective: set[str] = set()
            for pid in sorted(current):
                terminal, _path, error = self._resolve(pid)
                if error is not None or terminal is None:
                    problems.append(f"participant {pid} cannot resolve ({error})")
                else:
                    effective.add(pid)
            result[oid] = (effective, problems)
        for revision in conn.execute("SELECT observation_id, person_id, disposition FROM encounter_participant_revisions ORDER BY created_at, rowid"):
            oid = str(revision[0])
            terminal, _, error = self._resolve(str(revision[1]))
            if oid in result and terminal is not None and error is None:
                if revision[2] == "PRESENT":
                    result[oid][0].add(str(revision[1]))
                else:
                    result[oid][0].discard(str(revision[1]))
        return {oid: ({self._resolve(pid)[0] for pid in values[0]}, values[1]) for oid, values in result.items()}

    def _check_correction_interpretation(self, conn: sqlite3.Connection) -> None:
        self._load_people(conn)
        for row in conn.execute("SELECT correction_id, from_person_id, to_person_id FROM identity_corrections ORDER BY correction_id"):
            for label, pid in (("from", row[1]), ("to", row[2])):
                terminal, path, error = self._resolve(pid)
                if error is not None or terminal is None:
                    self._add("P11-CORRECTION-002", "Correction endpoint cannot resolve to a legal current identity", entities={"correction_id": row[0], f"{label}_person_id": pid}, evidence={"path": " -> ".join(path), "reason": error})
        for oid, (_effective, problems) in sorted(self._effective_participants(conn).items()):
            for problem in problems:
                self._add("P11-CORRECTION-002", "Observation correction sequence is not applicable", entities={"observation_id": oid}, evidence={"reason": problem})

    def _check_observation_finalization(self, conn: sqlite3.Connection) -> None:
        effective = self._effective_participants(conn)
        for row in conn.execute("SELECT o.observation_id, o.status, o.finalized_at, COUNT(p.person_id) raw_count FROM observations o LEFT JOIN observation_participants p USING(observation_id) GROUP BY o.observation_id ORDER BY o.observation_id"):
            oid, status, finalized_at, raw_count = row
            effective_count = len(effective.get(str(oid), (set(), []))[0])
            invalid = (status == "FINALIZED" and (finalized_at is None or raw_count < 1 or effective_count < 1)) or (status == "DRAFT" and finalized_at is not None) or status not in {"DRAFT", "FINALIZED"}
            if invalid:
                self._add("P11-OBSERVATION-001", "Observation finalization state is internally inconsistent", entities={"observation_id": oid}, evidence={"status": status, "finalized_at": finalized_at, "raw_participant_count": raw_count, "effective_participant_count": effective_count})

    def _check_participant_uniqueness(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("SELECT observation_id, person_id, COUNT(*) count FROM observation_participants GROUP BY observation_id, person_id HAVING COUNT(*) > 1"):
            self._add("P11-OBSERVATION-002", "Raw participant is duplicated", entities={"observation_id": row[0], "person_id": row[1]}, evidence={"count": row[2]})
        self._load_people(conn)
        for oid, (effective, _problems) in sorted(self._effective_participants(conn).items()):
            if any(pid not in self._people for pid in effective):
                self._add("P11-OBSERVATION-002", "Effective participant does not exist", entities={"observation_id": oid})

    def _check_media_references(self, conn: sqlite3.Connection) -> None:
        query = """
        SELECT m.observation_id, m.media_id, m.media_path
        FROM observation_media m
        WHERE trim(m.media_id) = '' OR NOT EXISTS (
            SELECT 1 FROM recognition_details r WHERE r.image_id = m.media_id OR r.image_path = m.media_id OR (m.media_path IS NOT NULL AND r.image_path = m.media_path)
            UNION ALL SELECT 1 FROM embeddings e WHERE e.source_image = m.media_id OR e.crop_path = m.media_id OR (m.media_path IS NOT NULL AND (e.source_image = m.media_path OR e.crop_path = m.media_path))
            UNION ALL SELECT 1 FROM pending_additions p WHERE p.source_image = m.media_id OR (m.media_path IS NOT NULL AND p.source_image = m.media_path)
            UNION ALL SELECT 1 FROM init_faces i WHERE i.source_image = m.media_id OR i.crop_path = m.media_id OR (m.media_path IS NOT NULL AND (i.source_image = m.media_path OR i.crop_path = m.media_path))
            UNION ALL SELECT 1 FROM photo_reviews pr WHERE pr.media_id = m.media_id OR (m.media_path IS NOT NULL AND pr.media_path = m.media_path)
        ) ORDER BY m.observation_id, m.media_id
        """
        for row in conn.execute(query):
            self._add("P11-OBSERVATION-003", "Observation media has no durable database provenance reference", entities={"observation_id": row[0], "media_id": row[1]}, evidence={"media_path": row[2]})

    def _check_reviews(self, conn: sqlite3.Connection) -> None:
        query = """
        SELECT r.review_id, r.status, r.observation_id, r.completed_operation_id, r.completed_at,
               SUM(CASE WHEN f.face_id IS NOT NULL AND f.decision IS NULL THEN 1 ELSE 0 END) undecided,
               COUNT(f.face_id) face_count, o.status observation_status, j.status operation_status
        FROM photo_reviews r LEFT JOIN photo_review_faces f USING(review_id)
        LEFT JOIN observations o ON o.observation_id = r.observation_id
        LEFT JOIN operation_journal j ON j.operation_id = r.completed_operation_id
        GROUP BY r.review_id ORDER BY r.review_id
        """
        for row in conn.execute(query):
            completed = row[1] == "COMPLETED"
            invalid = False
            if completed:
                invalid = row[3] is None or row[4] is None or int(row[5] or 0) > 0 or (int(row[6]) < 1 and conn.execute("SELECT target_observation_id FROM photo_reviews WHERE review_id = ?", (row[0],)).fetchone()[0] is None) or row[8] != "COMMITTED"
                if row[2] is not None and row[7] != "FINALIZED":
                    invalid = True
            elif row[3] is not None or row[4] is not None or row[2] is not None:
                invalid = True
            if invalid:
                self._add("P11-REVIEW-001", "Photo review state disagrees with decisions, observation, or operation result", entities={"review_id": row[0], "observation_id": row[2], "operation_id": row[3]}, evidence={"review_status": row[1], "completed_at": row[4], "undecided_faces": row[5], "face_count": row[6], "observation_status": row[7], "operation_status": row[8]})

    def _check_evidence_sources(self, conn: sqlite3.Connection) -> None:
        valid = {
            "CO_OBSERVED": ("OBSERVATION", "UNDIRECTED"),
            "NOTE_REFERENCE": ("NOTE", "DIRECTED"),
            "MANUAL_ASSOCIATION": ("MANUAL_ASSERTION", None),
        }
        evidence_query = """
        SELECT e.*, o.status AS source_observation_status,
               m.mention_id AS source_mention_id,
               m.referenced_person_id AS mention_person_id,
               m.active AS mention_active,
               n.owner_person_id AS note_owner_person_id,
               n.status AS note_status
        FROM relationship_evidence e
        LEFT JOIN observations o
          ON e.evidence_type='CO_OBSERVED' AND o.observation_id=e.source_entity_id
        LEFT JOIN note_mentions m
          ON e.evidence_type='NOTE_REFERENCE' AND m.mention_id=e.source_entity_id
        LEFT JOIN notes n ON n.note_id=m.note_id
        ORDER BY e.evidence_id
        """
        for row in conn.execute(evidence_query):
            problems: list[str] = []
            expected = valid.get(str(row["evidence_type"]))
            if expected is None or row["source_entity_type"] != expected[0]:
                problems.append("type/source mismatch")
            if expected is not None and expected[1] and row["directionality"] != expected[1]:
                problems.append("invalid directionality for evidence type")
            if row["directionality"] == "UNDIRECTED" and str(row["source_person_id"]) >= str(row["target_person_id"]):
                problems.append("unordered undirected endpoints")
            if row["source_person_id"] == row["target_person_id"]:
                problems.append("raw self endpoint")
            active_shape = bool(row["active"]) and row["deactivated_operation_id"] is None and row["deactivated_at"] is None
            inactive_shape = not bool(row["active"]) and row["deactivated_operation_id"] is not None and row["deactivated_at"] is not None
            if not (active_shape or inactive_shape):
                problems.append("invalid active/deactivation provenance")
            if row["evidence_type"] == "CO_OBSERVED":
                if row["source_observation_status"] != "FINALIZED":
                    problems.append("missing or non-finalized observation source")
            elif row["evidence_type"] == "NOTE_REFERENCE":
                if row["source_mention_id"] is None:
                    problems.append("missing note mention source")
                else:
                    if (
                        row["source_person_id"] != row["note_owner_person_id"]
                        or row["target_person_id"] != row["mention_person_id"]
                    ):
                        problems.append("endpoints do not match note mention")
                    if row["relationship_type"] != "REFERENCES":
                        problems.append("invalid relationship type for note reference")
                    if bool(row["active"]) and not (
                        bool(row["mention_active"])
                        and row["note_status"] == "ACTIVE"
                    ):
                        problems.append("active evidence has no current active note mention source")
            if problems:
                self._add("P11-EVIDENCE-001", "; ".join(problems), entities={"evidence_id": row["evidence_id"], "source_entity_id": row["source_entity_id"]}, evidence={"evidence_type": row["evidence_type"], "source_person_id": row["source_person_id"], "target_person_id": row["target_person_id"], "active": row["active"]})

    def _check_evidence_resolution(self, conn: sqlite3.Connection) -> None:
        self._load_people(conn)
        effective_participants = self._effective_participants(conn)
        for row in conn.execute("SELECT evidence_id, evidence_type, source_entity_id, source_person_id, target_person_id, active FROM relationship_evidence WHERE active = 1 ORDER BY evidence_id"):
            source, spath, serr = self._resolve(row[3])
            target, tpath, terr = self._resolve(row[4])
            if serr or terr or source is None or target is None:
                self._add("P11-EVIDENCE-002", "Active evidence endpoint cannot resolve", entities={"evidence_id": row[0]}, evidence={"source_path": " -> ".join(spath), "source_error": serr, "target_path": " -> ".join(tpath), "target_error": terr})
                continue
            if row[1] == "CO_OBSERVED":
                participants = effective_participants.get(str(row[2]), (set(), []))[0]
                if source not in participants or target not in participants:
                    self._add("P11-EVIDENCE-002", "Active co-observation evidence endpoints are not current effective participants", entities={"evidence_id": row[0], "observation_id": row[2]}, evidence={"effective_source_person_id": source, "effective_target_person_id": target})

    def _expected_graph(self, conn: sqlite3.Connection) -> dict[tuple[str, str, str, str], tuple[int, tuple[str, ...], str]]:
        connections, _authority_errors, _active_evidence_count = (
            _expected_graph_connections(conn)
        )
        return {
            (
                item.source_person_id,
                item.target_person_id,
                item.relationship_type,
                item.directionality,
            ): (
                item.evidence_count,
                item.evidence_types,
                item.last_evidence_at,
            )
            for item in connections
        }

    def _check_graph_projection(self, conn: sqlite3.Connection) -> None:
        expected = self._expected_graph(conn)
        actual: dict[tuple[str, str, str, str], tuple[int, tuple[str, ...], str]] = {}
        for row in conn.execute("SELECT * FROM graph_connections ORDER BY source_person_id, target_person_id, relationship_type, directionality"):
            key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            try:
                types = tuple(sorted(str(item) for item in json.loads(row[5])))
            except (TypeError, ValueError, json.JSONDecodeError):
                types = ("<invalid-json>",)
            actual[key] = (int(row[4]), types, str(row[6]))
            if key[0] == key[1]:
                self._add("P11-GRAPH-001", "Stored projection contains a self-edge", entities={"source_person_id": key[0], "target_person_id": key[1]}, evidence={"relationship_type": key[2], "directionality": key[3]})
        for key in sorted(expected.keys() - actual.keys()):
            self._add("P11-GRAPH-001", "Expected derived edge is missing", entities={"source_person_id": key[0], "target_person_id": key[1]}, evidence={"relationship_type": key[2], "directionality": key[3], "expected": expected[key]})
        for key in sorted(actual.keys() - expected.keys()):
            self._add("P11-GRAPH-001", "Stored derived edge has no active evidence support", entities={"source_person_id": key[0], "target_person_id": key[1]}, evidence={"relationship_type": key[2], "directionality": key[3], "stored": actual[key]})
        for key in sorted(expected.keys() & actual.keys()):
            if expected[key] != actual[key]:
                self._add("P11-GRAPH-001", "Stored derived edge aggregate disagrees with active evidence", entities={"source_person_id": key[0], "target_person_id": key[1]}, evidence={"relationship_type": key[2], "directionality": key[3], "expected": expected[key], "stored": actual[key]})

    def _check_note_revisions(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("SELECT n.note_id, COUNT(r.revision_id), MIN(r.revision_number), MAX(r.revision_number), COUNT(DISTINCT r.revision_number) FROM notes n LEFT JOIN note_revisions r USING(note_id) GROUP BY n.note_id ORDER BY n.note_id"):
            count = int(row[1])
            if count < 1 or int(row[2] or 0) != 1 or int(row[3] or 0) != count or int(row[4]) != count:
                self._add("P11-NOTE-001", "Note revision sequence is missing or non-contiguous", entities={"note_id": row[0]}, evidence={"revision_count": count, "minimum_revision": row[2], "maximum_revision": row[3]})

    def _check_note_mentions(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("SELECT note_id, status, retired_operation_id, retired_at FROM notes ORDER BY note_id"):
            active_shape = row[1] == "ACTIVE" and row[2] is None and row[3] is None
            retired_shape = row[1] == "RETIRED" and row[2] is not None and row[3] is not None
            if not (active_shape or retired_shape):
                self._add("P11-NOTE-002", "Note lifecycle and retirement provenance disagree", entities={"note_id": row[0]}, evidence={"status": row[1], "retired_operation_id": row[2], "retired_at": row[3]})
        query = """
        WITH latest AS (
          SELECT r.* FROM note_revisions r
          WHERE r.revision_number = (
            SELECT MAX(candidate.revision_number)
            FROM note_revisions candidate WHERE candidate.note_id=r.note_id
          )
        )
        SELECT n.note_id, n.status, n.owner_person_id,
               latest.revision_id AS latest_revision_id,
               m.mention_id, m.referenced_person_id, m.active,
               m.created_revision_id, created.note_id AS created_note_id,
               created.revision_number AS created_revision_number,
               m.retired_revision_id, retired.note_id AS retired_note_id,
               retired.revision_number AS retired_revision_number,
               m.retired_operation_id, m.retired_at,
               CASE WHEN latest_mention.referenced_person_id IS NULL THEN 0 ELSE 1 END in_latest
        FROM notes n
        JOIN latest ON latest.note_id=n.note_id
        JOIN note_mentions m ON m.note_id=n.note_id
        JOIN note_revisions created ON created.revision_id=m.created_revision_id
        LEFT JOIN note_revisions retired ON retired.revision_id=m.retired_revision_id
        LEFT JOIN note_revision_mentions latest_mention
          ON latest_mention.revision_id=latest.revision_id
         AND latest_mention.referenced_person_id=m.referenced_person_id
        ORDER BY n.note_id, m.referenced_person_id, m.mention_id
        """
        grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in conn.execute(query):
            grouped[(str(row["note_id"]), str(row["referenced_person_id"]))].append(row)
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
                self._add(
                    "P11-NOTE-002",
                    "Note mention occurrence has invalid active/retirement provenance",
                    entities={
                        "note_id": row["note_id"],
                        "mention_id": row["mention_id"],
                        "person_id": row["referenced_person_id"],
                    },
                    evidence={
                        "mention_active": row["active"],
                        "created_revision_id": row["created_revision_id"],
                        "retired_revision_id": row["retired_revision_id"],
                        "retired_operation_id": row["retired_operation_id"],
                        "retired_at": row["retired_at"],
                    },
                )
        for (_note_id, _person_id), rows in sorted(grouped.items()):
            sample = rows[0]
            active_ids = tuple(sorted(
                str(row["mention_id"]) for row in rows if bool(row["active"])
            ))
            expected_count = 1 if (
                sample["status"] == "ACTIVE"
                and bool(sample["in_latest"])
                and sample["referenced_person_id"] != sample["owner_person_id"]
            ) else 0
            if len(active_ids) != expected_count:
                self._add(
                    "P11-NOTE-002",
                    "Current note mention occurrence cardinality disagrees with the latest authoritative revision",
                    entities={
                        "note_id": sample["note_id"],
                        "person_id": sample["referenced_person_id"],
                    },
                    evidence={
                        "latest_revision_id": sample["latest_revision_id"],
                        "note_status": sample["status"],
                        "present_in_latest_revision": sample["in_latest"],
                        "expected_active_occurrences": expected_count,
                        "actual_active_occurrences": len(active_ids),
                        "active_mention_ids": ",".join(active_ids),
                        "historical_occurrence_count": len(rows) - len(active_ids),
                    },
                )

    def _check_note_evidence(self, conn: sqlite3.Connection) -> None:
        query = """
        SELECT m.mention_id, m.note_id, m.referenced_person_id, m.active, n.status, n.owner_person_id,
               SUM(CASE WHEN e.active=1 AND e.source_person_id=n.owner_person_id
                                      AND e.target_person_id=m.referenced_person_id
                                      AND e.directionality='DIRECTED'
                                      AND e.relationship_type='REFERENCES'
                        THEN 1 ELSE 0 END) matching_active_evidence,
               SUM(CASE WHEN e.active=1 THEN 1 ELSE 0 END) all_active_evidence,
               SUM(CASE WHEN e.active=0 THEN 1 ELSE 0 END) retired_evidence,
               GROUP_CONCAT(e.evidence_id)
        FROM note_mentions m JOIN notes n USING(note_id)
        LEFT JOIN relationship_evidence e ON e.evidence_type='NOTE_REFERENCE' AND e.source_entity_id=m.mention_id
        GROUP BY m.mention_id ORDER BY m.mention_id
        """
        for row in conn.execute(query):
            expected = 1 if bool(row[3]) and row[4] == "ACTIVE" and row[2] != row[5] else 0
            active_count = int(row[6] or 0)
            all_active_count = int(row[7] or 0)
            if active_count != expected or all_active_count != expected:
                self._add("P11-NOTE-003", "NOTE_REFERENCE active evidence does not match authoritative mention state", entities={"mention_id": row[0], "note_id": row[1], "person_id": row[2]}, evidence={"expected_active_evidence": expected, "actual_active_evidence": active_count, "all_active_evidence": all_active_count, "evidence_ids": row[9]})

    def _check_merge_results(self, conn: sqlite3.Connection) -> None:
        self._load_people(conn)
        for row in conn.execute("SELECT m.*, j.operation_type, j.status journal_status, j.actor journal_actor FROM merge_operations m LEFT JOIN operation_journal j ON j.operation_id=m.operation_journal_id ORDER BY m.merge_operation_id"):
            terminal, path, error = self._resolve(row["source_person_id"])
            target_terminal, target_path, target_error = self._resolve(row["target_person_id"])
            problems: list[str] = []
            if row["merge_operation_id"] != row["operation_journal_id"] or row["operation_type"] != "identity.merge" or row["journal_status"] not in {"COMMITTED", "REVERTED"}:
                problems.append("journal identity/status disagreement")
            if row["actor"] != row["journal_actor"]:
                problems.append("actor disagreement")
            if row["journal_status"] == "COMMITTED" and (
                error is not None or target_error is not None
                or terminal is None or terminal != target_terminal
            ):
                problems.append("source does not resolve to manifest survivor")
            if problems:
                self._add("P11-MERGE-001", "; ".join(problems), entities={"merge_operation_id": row["merge_operation_id"], "operation_id": row["operation_journal_id"], "source_person_id": row["source_person_id"], "target_person_id": row["target_person_id"]}, evidence={"journal_status": row["journal_status"], "resolved_terminal": terminal, "canonical_path": " -> ".join(path), "resolution_error": error, "target_terminal": target_terminal, "target_path": " -> ".join(target_path), "target_error": target_error})
        for row in conn.execute("SELECT operation_id, status FROM operation_journal WHERE operation_type='identity.merge' AND status='COMMITTED' AND NOT EXISTS (SELECT 1 FROM merge_operations m WHERE m.operation_journal_id=operation_id) ORDER BY operation_id"):
            self._add("P11-MERGE-001", "Committed identity.merge operation has no normalized merge manifest", entities={"operation_id": row[0]})

    def _check_merge_inverse_data(self, conn: sqlite3.Connection) -> None:
        valid_actions = {"PRESERVE", "REINTERPRET_CANONICAL_OWNER", "UNION_IN_CURRENT_VIEW", "SELECT_VALUE"}
        for row in conn.execute("SELECT merge_operation_id, item_type, item_id, raw_owner_person_id, effective_owner_person_id, action, before_state, after_state, context FROM merge_affected_items ORDER BY merge_operation_id, item_type, item_id"):
            problems: list[str] = []
            if not str(row[1]).strip() or not str(row[2]).strip() or row[5] not in valid_actions:
                problems.append("missing identity or invalid action")
            for index, label in ((6, "before_state"), (7, "after_state"), (8, "context")):
                if not self._is_json_object(row[index]):
                    problems.append(f"invalid {label}")
            if problems:
                self._add("P11-MERGE-002", "; ".join(problems), entities={"merge_operation_id": row[0], "item_type": row[1], "item_id": row[2]})
        for row in conn.execute("SELECT conflict_id, merge_operation_id, strategy, source_value, target_value, selected_value, inverse_data FROM merge_conflict_resolutions ORDER BY conflict_id"):
            problems: list[str] = []
            values: list[object] = []
            for value in row[3:6]:
                try:
                    values.append(json.loads(value))
                except (TypeError, ValueError, json.JSONDecodeError):
                    problems.append("invalid conflict JSON")
            inverse_value: dict | None = None
            try:
                loaded_inverse = json.loads(row[6])
                if isinstance(loaded_inverse, dict):
                    inverse_value = loaded_inverse
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            if inverse_value is None or not {"source_value", "target_value"} <= set(inverse_value):
                problems.append("missing/invalid inverse_data")
            if len(values) == 3 and row[2] == "KEEP_SOURCE" and values[2] != values[0]:
                problems.append("KEEP_SOURCE selected value mismatch")
            if len(values) == 3 and row[2] == "KEEP_TARGET" and values[2] != values[1]:
                problems.append("KEEP_TARGET selected value mismatch")
            if problems:
                self._add("P11-MERGE-002", "; ".join(problems), entities={"merge_operation_id": row[1], "conflict_id": row[0]})

    def _check_journal_transitions(self, conn: sqlite3.Connection) -> None:
        histories: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in conn.execute("SELECT rowid, * FROM operation_journal_status_history ORDER BY operation_id, created_at, rowid, transition_id"):
            histories[str(row["operation_id"])].append(row)
        for row in conn.execute("SELECT operation_id, status FROM operation_journal ORDER BY operation_id"):
            operation_id, final_status = str(row[0]), str(row[1])
            history = histories.get(operation_id, [])
            problems: list[str] = []
            previous: str | None = None
            if not history or history[0]["from_status"] is not None or history[0]["to_status"] != "STARTED":
                problems.append("history does not begin at STARTED")
            for transition in history:
                if transition["from_status"] != previous:
                    problems.append("from_status does not match preceding state")
                target = str(transition["to_status"])
                if previous is not None and target not in _ALLOWED_TRANSITIONS.get(previous, set()):
                    problems.append(f"invalid {previous}->{target} transition")
                previous = target
            if previous != final_status:
                problems.append("history terminal state disagrees with journal row")
            if problems:
                self._add("P11-JOURNAL-001", "; ".join(sorted(set(problems))), entities={"operation_id": operation_id}, evidence={"journal_status": final_status, "history_statuses": ",".join(str(item["to_status"]) for item in history)})

    def _check_journal_structure(self, conn: sqlite3.Connection) -> None:
        for row in conn.execute("SELECT operation_id, status, actor, context, affected_entities, details, completed_at FROM operation_journal ORDER BY operation_id"):
            problems: list[str] = []
            for index, label, expected in ((2, "actor", dict), (3, "context", dict), (4, "affected_entities", list), (5, "details", dict)):
                try:
                    value = json.loads(row[index])
                    if not isinstance(value, expected):
                        problems.append(f"{label} has wrong JSON shape")
                except (TypeError, ValueError, json.JSONDecodeError):
                    problems.append(f"{label} is invalid JSON")
            if (row[1] == "STARTED") != (row[6] is None):
                problems.append("status/completed_at disagreement")
            if problems:
                self._add("P11-JOURNAL-002", "; ".join(problems), entities={"operation_id": row[0]}, evidence={"status": row[1], "completed_at": row[6]})
        for row in conn.execute("SELECT transition_id, operation_id, details FROM operation_journal_status_history ORDER BY operation_id, created_at, transition_id"):
            if not self._is_json_object(row[2]):
                self._add("P11-JOURNAL-002", "Journal transition details are not a JSON object", entities={"operation_id": row[1], "transition_id": row[0]})

    def _check_journal_results(self, conn: sqlite3.Connection) -> None:
        linked_tables = (
            ("observations", "created_operation_id", "observation_id"),
            ("observation_media", "operation_id", "observation_id || ':' || media_id"),
            ("observation_participants", "operation_id", "observation_id || ':' || person_id"),
            ("observation_face_assignments", "created_operation_id", "assignment_id"),
            ("identity_corrections", "operation_id", "correction_id"),
            ("encounter_participant_revisions", "operation_id", "revision_id"),
            ("encounter_metadata_revisions", "operation_id", "revision_id"),
            ("relationship_evidence", "created_operation_id", "evidence_id"),
            ("relationship_evidence", "deactivated_operation_id", "evidence_id"),
            ("notes", "created_operation_id", "note_id"),
            ("notes", "retired_operation_id", "note_id"),
            ("note_revisions", "operation_id", "revision_id"),
            ("note_mentions", "created_operation_id", "mention_id"),
            ("note_mentions", "retired_operation_id", "mention_id"),
            ("biometric_enrollment_history", "operation_id", "enrollment_id"),
            ("merge_operations", "operation_journal_id", "merge_operation_id"),
        )
        for table, operation_column, entity_expression in linked_tables:
            sql = f"SELECT t.{operation_column}, j.status, {entity_expression} entity_id FROM {table} t JOIN operation_journal j ON j.operation_id=t.{operation_column} WHERE t.{operation_column} IS NOT NULL AND j.status NOT IN ('COMMITTED','REVERTED') ORDER BY t.{operation_column}, entity_id"
            for row in conn.execute(sql):
                self._add("P11-JOURNAL-003", "Visible authoritative result is linked to a non-committed operation", entities={"operation_id": row[0], "table": table, "entity_id": row[2]}, evidence={"operation_status": row[1]})
        result_expectations = (
            ("review.complete", "photo_reviews", "completed_operation_id"),
            ("identity.face.add", "photo_reviews", "completed_operation_id"),
            ("identity.merge", "merge_operations", "operation_journal_id"),
            ("identity.observation.correct", "identity_corrections", "operation_id"),
            ("identity.face.move", "identity_corrections", "operation_id"),
        )
        for operation_type, table, column in result_expectations:
            sql = f"SELECT operation_id FROM operation_journal j WHERE operation_type=? AND status='COMMITTED' AND NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{column}=j.operation_id) ORDER BY operation_id"
            for row in conn.execute(sql, (operation_type,)):
                self._add("P11-JOURNAL-003", "Committed operation is missing its expected authoritative result", entities={"operation_id": row[0], "expected_table": table}, evidence={"operation_type": operation_type})

    @staticmethod
    def _is_json_object(value: object) -> bool:
        try:
            return isinstance(json.loads(value), dict)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
