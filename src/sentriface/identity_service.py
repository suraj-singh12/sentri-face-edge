from __future__ import annotations

from sentriface.contracts import IdentityStore
from sentriface.models import Person


class IdentityService:
    """Production boundary for identity creation and lifecycle resolution."""

    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def create_identified_person(
        self,
        name: str,
        metadata: dict,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str = "identity-service",
    ) -> Person:
        return self.store.create_identified_person(
            name,
            metadata,
            operation_id,
            actor=actor,
            source=source,
        )
