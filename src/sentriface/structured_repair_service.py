from __future__ import annotations

from typing import Callable

from sentriface.contracts import IdentityStore
from sentriface.errors import StructuredRepairPostcheckError
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import (
    ArchivedCanonicalSurvivorRepairPrecondition,
    NoteReferenceReconciliationPrecondition,
)


class StructuredRepairService:
    """Explicit service surface for the frozen two-command P11-C whitelist."""

    def __init__(
        self,
        store: IdentityStore,
        *,
        refresh_index: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.refresh_index = refresh_index

    def prepare_restore_archived_canonical_survivor(
        self, survivor_person_id: str,
    ) -> ArchivedCanonicalSurvivorRepairPrecondition:
        return self.store.prepare_restore_archived_canonical_survivor(survivor_person_id)

    def restore_archived_canonical_survivor(
        self,
        precondition: ArchivedCanonicalSurvivorRepairPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        result = self.store.execute_restore_archived_canonical_survivor(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
        )
        if self.refresh_index is not None:
            self.refresh_index()
        checker = ReadOnlyIntegrityChecker(
            self.store.db_path, database_key=getattr(self.store, "database_key", None),
        )
        report = checker.run()
        blocking = tuple(
            item for item in report.findings
            if item.severity.value in {"CRITICAL", "ERROR"}
        )
        targeted = tuple(
            item for item in report.findings
            if item.invariant_id == "P11-IDENTITY-003"
            and dict(item.entity_ids).get("terminal_person_id")
            == precondition.survivor_person_id
        )
        if report.findings_truncated or targeted or blocking:
            raise StructuredRepairPostcheckError(result, report)
        return {**result, "postcheck_status": "PASS"}

    def prepare_note_reference_reconciliation(
        self, note_id: str, referenced_person_id: str,
    ) -> NoteReferenceReconciliationPrecondition:
        return self.store.prepare_note_reference_reconciliation(
            note_id, referenced_person_id,
        )

    def reconcile_note_reference_state(
        self,
        precondition: NoteReferenceReconciliationPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        result = self.store.execute_note_reference_reconciliation(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
        )
        checker = ReadOnlyIntegrityChecker(
            self.store.db_path, database_key=getattr(self.store, "database_key", None),
        )
        report = checker.run()
        blocking = tuple(
            item for item in report.findings
            if item.severity.value in {"CRITICAL", "ERROR"}
        )
        targeted = tuple(
            item for item in report.findings
            if (
                dict(item.entity_ids).get("note_id") == precondition.note_id
                and dict(item.entity_ids).get("person_id")
                == precondition.referenced_person_id
                and item.invariant_id in {"P11-NOTE-002", "P11-NOTE-003"}
            ) or (
                item.invariant_id == "P11-EVIDENCE-001"
                and dict(item.entity_ids).get("evidence_id")
                in precondition.active_evidence_ids
            )
        )
        if report.findings_truncated or targeted or blocking:
            raise StructuredRepairPostcheckError(result, report)
        return {**result, "postcheck_status": "PASS"}
