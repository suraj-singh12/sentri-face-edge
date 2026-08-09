from __future__ import annotations

from typing import Callable

from sentriface.contracts import IdentityStore
from sentriface.models import EmbeddingRecord


class IdentityMergeService:
    """The sole application boundary for previewing and executing identity merges."""

    def __init__(
        self,
        store: IdentityStore,
        publish_index: Callable[[list[EmbeddingRecord]], None] | None = None,
        reconcile_index: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.publish_index = publish_index
        self.reconcile_index = reconcile_index

    def preview(
        self,
        source_person_id: str,
        target_person_id: str,
    ) -> dict:
        return self.store.preview_identity_merge(source_person_id, target_person_id)

    def execute(
        self,
        source_person_id: str,
        target_person_id: str,
        operation_id: str,
        *,
        conflict_resolutions: list[dict] | dict[str, dict | str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
        reason: str | None = None,
        context: dict | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        try:
            return self.store.execute_identity_merge(
                source_person_id,
                target_person_id,
                operation_id,
                conflict_resolutions=conflict_resolutions,
                actor=actor,
                source=source,
                reason=reason,
                context=context,
                publish_index=self.publish_index,
                failure_injector=failure_injector,
            )
        except Exception:
            # Publication happens before the SQLite commit so readers can never see
            # committed canonical state paired with an old index. If publication or
            # commit fails, restore the index from the rolled-back database.
            if self.reconcile_index is not None:
                try:
                    self.reconcile_index()
                except Exception:
                    # Preserve the authoritative merge failure. The engine's index
                    # remains on its prior generation when safe rebuilds fail.
                    pass
            raise
