from __future__ import annotations

from sentriface.contracts import IdentityStore
from sentriface.models import PersonIntelligence, Sighting


class IntelligenceReadService:
    """Read-only P9 boundary over normalized authoritative records."""

    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def list_sightings(self, person_id: str) -> list[Sighting]:
        return self.store.list_person_sightings(person_id)

    def get_person_intelligence(self, person_id: str) -> PersonIntelligence:
        return self.store.get_person_intelligence(person_id)
