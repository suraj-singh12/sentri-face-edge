from __future__ import annotations

from sentriface.contracts import IdentityStore
from sentriface.models import GraphReadFilter, PersonGraphReadModel, WorldGraphReadModel


class GraphReadService:
    """P10-A read-only boundary for Person Graph and World Graph contracts."""

    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def revision(self) -> str:
        return self.store.get_graph_revision()

    def person_graph(
        self, person_id: str, filters: GraphReadFilter | None = None,
    ) -> PersonGraphReadModel:
        return self.store.get_person_graph_read(person_id, filters)

    def world_graph(
        self, filters: GraphReadFilter | None = None,
    ) -> WorldGraphReadModel:
        return self.store.get_world_graph_read(filters)
