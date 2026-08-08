from __future__ import annotations

from sentriface.contracts import IdentityStore
from sentriface.models import (
    GlobalGraphProjection,
    GraphConnection,
    Note,
    NoteRevision,
    Person,
    PersonChange,
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

    def create_note(
        self,
        owner_person_id: str,
        content: str,
        operation_id: str,
        **values,
    ) -> Note:
        return self.store.create_note(
            owner_person_id, content, operation_id, **values,
        )

    def update_person_notes(
        self,
        person_id: str,
        notes: str,
        expected_previous_notes: str,
        editor_name: str,
        operation_id: str,
        mentioned_person_ids: list[str] | None = None,
        **values,
    ) -> tuple[bool, Person, PersonChange | None]:
        return self.store.update_person_notes(
            person_id,
            notes,
            expected_previous_notes,
            editor_name,
            operation_id,
            mentioned_person_ids,
            **values,
        )

    def update_note(
        self, note_id: str, content: str, operation_id: str, **values,
    ) -> Note:
        return self.store.update_note(note_id, content, operation_id, **values)

    def get_note(self, note_id: str, include_retired: bool = False) -> Note | None:
        return self.store.get_note(note_id, include_retired)

    def get_person_note(
        self, person_id: str, include_retired: bool = False,
    ) -> Note | None:
        return self.store.get_person_note(person_id, include_retired)

    def list_note_revisions(self, note_id: str) -> list[NoteRevision]:
        return self.store.list_note_revisions(note_id)

    def retire_note(self, note_id: str, operation_id: str, **values) -> Note:
        return self.store.retire_note(note_id, operation_id, **values)

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
