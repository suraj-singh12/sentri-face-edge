from __future__ import annotations

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.models import IdentityCorrection


class IdentityCorrectionService:
    """Central P7 boundary for post-finalisation identity corrections."""

    def __init__(self, graph: GlobalIdentityGraphService) -> None:
        self.graph = graph

    def correct_observation_identity(
        self,
        observation_id: str,
        from_person_id: str,
        to_person_id: str,
        operation_id: str,
        **values,
    ) -> dict:
        try:
            return self.graph.correct_observation_identity(
                observation_id, from_person_id, to_person_id, operation_id, **values,
            )
        except Exception as exc:
            self._record_failure(
                operation_id, "identity.observation.correct", exc, values,
                [
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "person", "entity_id": from_person_id},
                    {"entity_type": "person", "entity_id": to_person_id},
                ],
            )
            raise

    def move_face(
        self, embedding_id: str, to_person_id: str, operation_id: str, **values,
    ) -> dict:
        try:
            return self.graph.move_face(
                embedding_id, to_person_id, operation_id, **values,
            )
        except Exception as exc:
            self._record_failure(
                operation_id, "identity.face.move", exc, values,
                [
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": to_person_id},
                ],
            )
            raise

    def add_face_to_person(
        self, review_id: str, person_id: str, operation_id: str, **values,
    ) -> dict:
        try:
            return self.graph.add_face_to_person(
                review_id, person_id, operation_id, **values,
            )
        except Exception as exc:
            self._record_failure(
                operation_id, "identity.face.add", exc, values,
                [
                    {"entity_type": "review", "entity_id": review_id},
                    {"entity_type": "person", "entity_id": person_id},
                ],
            )
            raise

    def list_corrections_for_observation(
        self, observation_id: str,
    ) -> list[IdentityCorrection]:
        return self.graph.list_corrections_for_observation(observation_id)

    def list_corrections_for_embedding(
        self, embedding_id: str,
    ) -> list[IdentityCorrection]:
        return self.graph.list_corrections_for_embedding(embedding_id)

    def _record_failure(
        self,
        operation_id: str,
        operation_type: str,
        error: Exception,
        values: dict,
        affected_entities: list[dict],
    ) -> None:
        if self.graph.store.get_operation(operation_id) is not None:
            return
        self.graph.store.begin_operation(
            operation_type,
            operation_id=operation_id,
            actor=values.get("actor"),
            source=values.get("source") or "identity-correction-service",
            affected_entities=affected_entities,
            details={"attempt_failed": True},
        )
        self.graph.store.mark_operation_failed(
            operation_id,
            {"error_type": type(error).__name__, "message": str(error)},
        )
