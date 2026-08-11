from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.graph_read_service import GraphReadService
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.models import (
    WorldCollection,
    WorldDetailLevel,
    WorldGraphRequest,
    WorldReadLimits,
)
from sentriface.storage.sqlite_store import SQLiteIdentityStore, _world_graph_v2_read


class WorldGraphV2FreezeTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _observe(
        self,
        store: SQLiteIdentityStore,
        operation: str,
        person_ids: list[str],
        *,
        location: str | None = "HQ",
        media: int = 0,
    ) -> str:
        observation = store.create_observation(
            f"{operation}-create",
            participant_ids=person_ids,
            observed_at="2026-08-01T10:00:00+00:00",
            location=location,
        )
        for index in range(media):
            media_id = f"{operation}-media-{index}"
            media_path = f"/managed/{operation}-{index}.jpg"
            embedding = store.add_embedding(
                person_ids[0], (1.0, 0.0), 0.9, source_image=media_path,
            )
            store.add_recognition_detail(
                embedding.embedding_id, person_ids[0], media_id, "Observed Person",
                "accepted", "2026-08-01", "10:00", location or "", 1,
                "World freeze media fixture", image_path=media_path,
            )
            store.attach_observation_media(
                observation.observation_id,
                media_id,
                f"{operation}-attach-{index}",
                media_path=media_path,
                source="TEST_FIXTURE",
            )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{operation}-finalize",
        )
        GlobalIdentityGraphService(store).record_observation_evidence(
            observation.observation_id, f"{operation}-evidence",
        )
        return observation.observation_id

    def test_response_revision_and_data_share_one_sqlite_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            original = store.create_person("Original")
            entered_read = threading.Event()
            mutation_committed = threading.Event()
            result: list[object] = []
            failure: list[BaseException] = []

            from sentriface.storage import sqlite_store as module

            original_people_scope = module._world_people_scope

            def paused_people_scope(conn, filters, canonical_map=None):
                entered_read.set()
                self.assertTrue(mutation_committed.wait(10))
                return original_people_scope(conn, filters, canonical_map)

            def reader() -> None:
                try:
                    result.append(GraphReadService(store).world_graph_v2())
                except BaseException as exc:  # pragma: no cover - thread handoff
                    failure.append(exc)

            with patch.object(module, "_world_people_scope", paused_people_scope):
                thread = threading.Thread(target=reader)
                thread.start()
                self.assertTrue(entered_read.wait(10))
                added = store.create_person("Committed concurrently")
                mutation_committed.set()
                thread.join(10)

            self.assertFalse(thread.is_alive())
            self.assertEqual(failure, [])
            snapshot = result[0]
            self.assertEqual(
                [person.canonical_person_id for person in snapshot.people],
                [original.person_id],
            )
            self.assertNotEqual(snapshot.graph_revision, store.get_graph_revision())

            next_read = GraphReadService(store).world_graph_v2()
            self.assertEqual(next_read.graph_revision, store.get_graph_revision())
            self.assertEqual(
                {person.canonical_person_id for person in next_read.people},
                {original.person_id, added.person_id},
            )

    def test_merge_created_self_edge_never_leaks_into_surviving_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            third = store.create_person("Third")
            self_event = self._observe(
                store, "self-edge", [source.person_id, survivor.person_id],
            )
            supporting_event = self._observe(
                store, "surviving-edge", [source.person_id, third.person_id],
            )
            store.execute_identity_merge(
                source.person_id, survivor.person_id, "merge-self-edge-source",
            )

            service = GraphReadService(store)
            person = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON",
                focus_id=survivor.person_id,
            ))
            self.assertEqual(len(person.relationships), 1)
            relationship = person.relationships[0]
            self.assertEqual(relationship.evidence_count, 1)

            evidence = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="RELATIONSHIP",
                focus_id=relationship.relationship_id,
                limits=WorldReadLimits(evidence=1),
            ))
            self.assertEqual(evidence.pagination["EVIDENCE"].total_count, 1)
            self.assertEqual(len(evidence.evidence), 1)
            self.assertEqual(
                evidence.evidence[0].supporting_references[0]["source_entity_id"],
                supporting_event,
            )
            self.assertNotEqual(
                evidence.evidence[0].supporting_references[0]["source_entity_id"],
                self_event,
            )
            self.assertEqual(
                set(evidence.evidence[0].effective_endpoints),
                {survivor.person_id, third.person_id},
            )

    def test_chained_merges_collapse_multiple_raw_edges_without_losing_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            terminal = store.create_person("Terminal")
            other = store.create_person("Other")
            event_ids = [
                self._observe(store, "chain-a", [first.person_id, other.person_id]),
                self._observe(store, "chain-b", [second.person_id, other.person_id]),
                self._observe(store, "chain-c", [terminal.person_id, other.person_id]),
            ]
            store.execute_identity_merge(first.person_id, second.person_id, "chain-a-b")
            store.execute_identity_merge(second.person_id, terminal.person_id, "chain-b-c")

            service = GraphReadService(store)
            person = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON", focus_id=terminal.person_id,
            ))
            relationship = person.relationships[0]
            self.assertEqual(relationship.evidence_count, 3)
            evidence = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="RELATIONSHIP", focus_id=relationship.relationship_id,
                limits=WorldReadLimits(evidence=3),
            ))
            self.assertEqual(evidence.pagination["EVIDENCE"].total_count, 3)
            self.assertEqual(
                {item.supporting_references[0]["source_entity_id"] for item in evidence.evidence},
                set(event_ids),
            )
            self.assertEqual(
                {tuple(sorted(item.effective_endpoints)) for item in evidence.evidence},
                {tuple(sorted((terminal.person_id, other.person_id)))},
            )

    def test_correction_is_applied_before_canonical_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            raw = store.create_person("Raw")
            corrected = store.create_person("Corrected")
            survivor = store.create_person("Survivor")
            other = store.create_person("Other")
            event_id = self._observe(store, "correction-merge", [raw.person_id, other.person_id])
            store.correct_observation_identity(
                event_id, raw.person_id, corrected.person_id, "correct-before-merge",
            )
            store.execute_identity_merge(
                corrected.person_id, survivor.person_id, "merge-after-correction",
            )

            person = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON", focus_id=survivor.person_id,
            ))
            relationship = person.relationships[0]
            self.assertEqual(
                {relationship.source_person_id, relationship.target_person_id},
                {survivor.person_id, other.person_id},
            )
            detail = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="RELATIONSHIP", focus_id=relationship.relationship_id,
            )).evidence[0]
            self.assertEqual(
                set(detail.raw_endpoints), {corrected.person_id, other.person_id},
            )
            self.assertEqual(set(detail.effective_endpoints), {survivor.person_id, other.person_id})

    def test_evidence_to_media_is_authoritative_and_empty_for_note_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            self._observe(store, "evidence-media", [first.person_id, second.person_id], media=2)
            GlobalIdentityGraphService(store).create_note(
                first.person_id, "@Second", "note-media-boundary",
                mentioned_person_ids=[second.person_id],
            )
            relationship_id = f"relationship:{min(first.person_id, second.person_id)}:{max(first.person_id, second.person_id)}"
            evidence = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="RELATIONSHIP", focus_id=relationship_id,
                limits=WorldReadLimits(evidence=10),
            )).evidence
            co_observed = next(item for item in evidence if item.evidence_type == "CO_OBSERVED")
            note = next(item for item in evidence if item.evidence_type == "NOTE_REFERENCE")

            co_media = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="EVIDENCE", focus_id=co_observed.evidence_id,
                collection=WorldCollection.MEDIA,
                limits=WorldReadLimits(media=1),
            ))
            self.assertEqual(co_media.pagination["MEDIA"].total_count, 2)
            self.assertEqual(len(co_media.media), 1)
            self.assertEqual(co_media.media[0].supporting_evidence_id, co_observed.evidence_id)
            self.assertTrue(co_media.pagination["MEDIA"].has_more)

            note_media = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="EVIDENCE", focus_id=note.evidence_id,
                collection=WorldCollection.MEDIA,
            ))
            self.assertEqual(note_media.pagination["MEDIA"].total_count, 0)
            self.assertEqual(note_media.media, ())
            self.assertEqual(note_media.evidence[0].media_summary["availability"], "UNAVAILABLE")

    def test_event_children_and_raw_provenance_are_independently_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(f"Raw {index}") for index in range(5)]
            event_id = self._observe(store, "provenance-bounds", [item.person_id for item in people])
            for index, person in enumerate(people[:-1]):
                store.execute_identity_merge(
                    person.person_id, people[-1].person_id, f"provenance-merge-{index}",
                )
            service = GraphReadService(store)
            participants = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=event_id,
                collection=WorldCollection.PARTICIPANTS,
                limits=WorldReadLimits(people=1, provenance=2),
            ))
            self.assertEqual(len(participants.events[0].participants), 1)
            self.assertEqual(participants.events[0].participant_provenance, ())
            self.assertEqual(participants.pagination["PROVENANCE"].total_count, 5)
            self.assertEqual(participants.pagination["PROVENANCE"].returned_count, 0)

            provenance = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=event_id,
                collection=WorldCollection.PROVENANCE,
                limits=WorldReadLimits(provenance=2),
            ))
            self.assertEqual(len(provenance.events[0].participants), 0)
            self.assertEqual(len(provenance.events[0].participant_provenance), 2)
            page = provenance.pagination["PROVENANCE"]
            self.assertEqual((page.total_count, page.returned_count), (5, 2))
            self.assertTrue(page.has_more)

    def test_location_facets_are_truthfully_paginated_and_empty_patterns_are_not_advertised(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            empty = GraphReadService(store).world_graph_v2()
            self.assertEqual(empty.available_facets["pattern_type"], [])
            self.assertEqual(empty.patterns, ())

            person = store.create_person("Located")
            for index in range(105):
                self._observe(
                    store, f"location-{index}", [person.person_id],
                    location=f"Location {index:03d}",
                )
            request = WorldGraphRequest(
                collection=WorldCollection.LOCATION_FACETS,
                limits=WorldReadLimits(facets=100),
                as_of="2026-08-09T00:00:00+00:00",
            )
            first = GraphReadService(store).world_graph_v2(request)
            page = first.pagination["LOCATION_FACETS"]
            self.assertEqual((page.total_count, page.returned_count), (105, 100))
            self.assertTrue(page.has_more)
            self.assertTrue(page.truncated)
            second = GraphReadService(store).world_graph_v2(WorldGraphRequest(**{
                **request.__dict__,
                "cursor": page.next_cursor,
                "revision": first.graph_revision,
            }))
            self.assertEqual(second.pagination["LOCATION_FACETS"].returned_count, 5)
            self.assertFalse(second.pagination["LOCATION_FACETS"].has_more)
            walked = [
                *first.available_facets["locations"],
                *second.available_facets["locations"],
            ]
            self.assertEqual(len(walked), 105)
            self.assertEqual(len({str(item["value"]) for item in walked}), 105)

            store.create_person("Facet revision change")
            with self.assertRaisesRegex(ValueError, "stale"):
                GraphReadService(store).world_graph_v2(WorldGraphRequest(**{
                    **request.__dict__,
                    "cursor": page.next_cursor,
                    "revision": first.graph_revision,
                }))

    def test_overview_relationships_are_typed_and_partial_neighbors_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            self._observe(store, "overview-edge", [first.person_id, second.person_id])
            overview = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                collection=WorldCollection.RELATIONSHIPS,
            ))
            self.assertEqual(len(overview.relationships), 1)
            self.assertEqual(overview.relationships[0].strength_basis, "EVIDENCE_COUNT_IN_SCOPE")

            person = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON", focus_id=first.person_id,
            ))
            neighbor = next(item for item in person.people if item.canonical_person_id == second.person_id)
            self.assertEqual(neighbor.analytics_state, "NOT_LOADED")
            self.assertIsNone(neighbor.activity_summary["finalized_event_count"])
            self.assertIsNone(neighbor.intelligence_summary["relationship_count"])
            self.assertEqual(neighbor.ranking["metrics_state"], "NOT_LOADED")
            self.assertIsNone(neighbor.explanation.evidence_count)

    def test_evidence_query_counts_are_constant_for_bounded_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(f"Person {index}") for index in range(8)]
            event_id = self._observe(store, "query-count", [item.person_id for item in people])

            selects = 0

            def trace(statement: str) -> None:
                nonlocal selects
                if statement.lstrip().upper().startswith(("SELECT", "WITH")):
                    selects += 1

            with store._connect() as conn:
                conn.set_trace_callback(trace)
                model = _world_graph_v2_read(conn, WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVENT,
                    focus_type="EVENT", focus_id=event_id,
                    collection=WorldCollection.EVIDENCE,
                    limits=WorldReadLimits(evidence=25),
                ))
                conn.set_trace_callback(None)
            self.assertEqual(len(model.evidence), 25)
            # The fixed path is constant across page size; 17 includes event
            # summary/count reads as well as the evidence page itself.
            self.assertLessEqual(selects, 18)

            with tempfile.TemporaryDirectory() as empty_temp:
                empty_store = self._store(Path(empty_temp))
                for index in range(1000):
                    empty_store.create_person(f"Empty {index}")
                focus = empty_store.list_persons()[0].person.person_id
                selects = 0
                with empty_store._connect() as conn:
                    conn.set_trace_callback(trace)
                    model = _world_graph_v2_read(conn, WorldGraphRequest(
                        detail_level=WorldDetailLevel.EVIDENCE,
                        focus_type="PERSON", focus_id=focus,
                    ))
                    conn.set_trace_callback(None)
                self.assertEqual(model.evidence, ())
                self.assertLessEqual(selects, 6)

    def test_person_event_queries_are_participant_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Plan source")
            survivor = store.create_person("Plan survivor")
            self._observe(store, "participant-first-plan", [source.person_id])
            store.execute_identity_merge(
                source.person_id, survivor.person_id, "participant-first-plan-merge",
            )

            statements: list[str] = []
            with store._connect() as conn:
                conn.set_trace_callback(statements.append)
                _world_graph_v2_read(conn, WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON,
                    focus_type="PERSON", focus_id=survivor.person_id,
                    collection=WorldCollection.EVENTS,
                ))
                conn.set_trace_callback(None)

                focused_queries = [
                    statement for statement in statements
                    if statement.lstrip().upper().startswith((
                        "SELECT COUNT(DISTINCT P.OBSERVATION_ID)",
                        "SELECT DISTINCT O.",
                    ))
                ]
                self.assertEqual(len(focused_queries), 2)
                for statement in focused_queries:
                    self.assertIn(
                        "observation_participants p\n"
                        "               INDEXED BY idx_observation_participants_person\n"
                        "            CROSS JOIN observations o",
                        statement,
                    )
                    plan = conn.execute(
                        "EXPLAIN QUERY PLAN " + statement,
                    ).fetchall()
                    details = [str(row[3]) for row in plan]
                    participant_step = next(
                        index for index, detail in enumerate(details)
                        if "idx_observation_participants_person" in detail
                    )
                    observation_step = next(
                        index for index, detail in enumerate(details)
                        if "sqlite_autoindex_observations_1" in detail
                    )
                    self.assertLess(participant_step, observation_step)

    def test_cluster_scoped_event_count_is_participant_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("Cluster plan first")
            second = store.create_person("Cluster plan second")
            self._observe(
                store, "cluster-count-plan", [first.person_id, second.person_id],
            )
            service = GraphReadService(store)
            cluster = service.world_graph_v2(WorldGraphRequest(
                collection=WorldCollection.CLUSTERS,
            )).clusters[0]

            statements: list[str] = []
            with store._connect() as conn:
                conn.set_trace_callback(statements.append)
                _world_graph_v2_read(conn, WorldGraphRequest(
                    detail_level=WorldDetailLevel.CLUSTER,
                    focus_type="CLUSTER", focus_id=cluster.cluster_id,
                    collection=WorldCollection.MEMBERS,
                ))
                conn.set_trace_callback(None)
                scoped_queries = [
                    statement for statement in statements
                    if statement.lstrip().upper().startswith(
                        "SELECT COUNT(DISTINCT P.OBSERVATION_ID)"
                    ) and "world_effective_person_in_scope" in statement
                ]
                self.assertEqual(len(scoped_queries), 1)
                statement = scoped_queries[0]
                self.assertNotIn("WITH RECURSIVE identity_map", statement)
                plan = conn.execute("EXPLAIN QUERY PLAN " + statement).fetchall()
                details = [str(row[3]) for row in plan]
                participant_step = next(
                    index for index, detail in enumerate(details)
                    if "idx_observation_participants_person" in detail
                )
                observation_step = next(
                    index for index, detail in enumerate(details)
                    if "sqlite_autoindex_observations_1" in detail
                )
                self.assertLess(participant_step, observation_step)
                self.assertEqual(
                    sum("USE TEMP B-TREE" in detail for detail in details), 1,
                )

    def test_world_adjustment_affected_events_are_participant_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Adjustment plan source")
            survivor = store.create_person("Adjustment plan survivor")
            self._observe(store, "adjustment-plan", [source.person_id, survivor.person_id])
            store.execute_identity_merge(
                source.person_id, survivor.person_id, "adjustment-plan-merge",
            )

            statements: list[str] = []
            with store._connect() as conn:
                conn.set_trace_callback(statements.append)
                _world_graph_v2_read(conn, WorldGraphRequest())
                conn.set_trace_callback(None)
                adjustment = next(
                    statement for statement in statements
                    if statement.lstrip().upper().startswith(
                        "WITH AFFECTED_EVENTS AS MATERIALIZED"
                    )
                )
                self.assertIn(
                    "observation_participants p\n"
                    "                     INDEXED BY idx_observation_participants_person\n"
                    "                CROSS JOIN observations o",
                    adjustment,
                )
                plan = conn.execute(
                    "EXPLAIN QUERY PLAN " + adjustment,
                ).fetchall()
                details = [str(row[3]) for row in plan]
                participant_step = next(
                    index for index, detail in enumerate(details)
                    if "idx_observation_participants_person" in detail
                )
                observation_step = next(
                    index for index, detail in enumerate(details)
                    if "sqlite_autoindex_observations_1" in detail
                )
                self.assertLess(participant_step, observation_step)


if __name__ == "__main__":
    unittest.main()
