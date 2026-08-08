from __future__ import annotations

from sentriface.contracts import IdentityStore
from sentriface.models import (
    GlobalGraphProjection,
    GraphConnection,
    RelationshipEvidence,
)


class GlobalIdentityGraphService:
    """Single application boundary for normalized evidence and derived graph state."""

    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def record_observation_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        return self.store.record_observation_evidence(
            observation_id, operation_id, source=source, actor=actor,
        )

    def deactivate_evidence(
        self,
        evidence_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> RelationshipEvidence:
        return self.store.deactivate_relationship_evidence(
            evidence_id, operation_id, source=source, actor=actor,
        )

    def deactivate_source_evidence(
        self,
        evidence_type: str,
        source_entity_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        return self.store.deactivate_relationship_evidence_for_source(
            evidence_type,
            source_entity_id,
            operation_id,
            source=source,
            actor=actor,
        )

    def get_person_neighbors(self, person_id: str) -> list[GraphConnection]:
        return self.store.get_person_neighbors(person_id)

    def get_connection_evidence(
        self,
        source_person_id: str,
        target_person_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[RelationshipEvidence]:
        return self.store.get_connection_evidence(
            source_person_id,
            target_person_id,
            include_inactive=include_inactive,
        )

    def get_global_projection(self) -> GlobalGraphProjection:
        return self.store.get_global_graph_projection()

    def rebuild_projection(
        self,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        return self.store.rebuild_graph_projection(
            operation_id, source=source, actor=actor,
        )

    def validate_projection(self) -> dict:
        return self.store.validate_graph_projection()
