from __future__ import annotations

from typing import Callable

from sentriface.contracts import IdentityStore
from sentriface.errors import OperationRevertPostcheckError
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import OperationRevertPrecondition


class GuardedOperationRevertService:
    """Explicit P11-D surface; the whitelist currently contains safe merges only."""

    def __init__(
        self,
        store: IdentityStore,
        *,
        refresh_index: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.refresh_index = refresh_index

    def prepare_revert(self, operation_id: str) -> OperationRevertPrecondition:
        return self.store.prepare_operation_revert(operation_id)

    def execute_revert(
        self,
        precondition: OperationRevertPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        result = self.store.execute_operation_revert(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
            failure_injector=failure_injector,
        )
        if self.refresh_index is not None:
            self.refresh_index()
        report = ReadOnlyIntegrityChecker(
            self.store.db_path, database_key=getattr(self.store, "database_key", None),
        ).run()
        blocking = tuple(
            finding for finding in report.findings
            if finding.severity.value in {"CRITICAL", "ERROR"}
        )
        if report.findings_truncated or blocking:
            raise OperationRevertPostcheckError(result, report)
        return {**result, "postcheck_status": "PASS"}
