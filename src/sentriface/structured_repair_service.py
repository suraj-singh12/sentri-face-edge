from __future__ import annotations

from typing import Callable

from sentriface.contracts import IdentityStore
from sentriface.errors import StructuredRepairPostcheckError
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import ArchivedCanonicalSurvivorRepairPrecondition


class StructuredRepairService:
    """Explicit service surface for the single implemented P11-C repair, R01."""

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
