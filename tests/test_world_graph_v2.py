from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.api_server import (
    _world_graph_v2_payload,
    _world_graph_v2_request_from_query,
)
from sentriface.graph_read_service import GraphReadService
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.models import (
    WorldDetailLevel,
    WorldCollection,
    WorldGraphRequest,
    WorldReadFilter,
    WorldReadLimits,
)
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class WorldGraphV2Test(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _observe(
        self,
        store: SQLiteIdentityStore,
        prefix: str,
        person_ids: list[str],
        *,
        observed_at: str,
        location: str | None,
        media_count: int = 0,
    ) -> str:
        observation = store.create_observation(
            f"{prefix}-create", participant_ids=person_ids,
            observed_at=observed_at, location=location,
        )
        for index in range(media_count):
            media_id = f"{prefix}-media-{index}"
            media_path = f"/managed/{media_id}.jpg"
            embedding = store.add_embedding(
                person_ids[0], (1.0, 0.0), 0.9, source_image=media_path,
            )
            store.add_recognition_detail(
                embedding.embedding_id, person_ids[0], media_id, "Observed Person",
                "accepted", "2026-08-01", "10:00", location or "", 1,
                "World media fixture", image_path=media_path,
            )
            store.attach_observation_media(
                observation.observation_id, media_id,
                f"{prefix}-attach-{index}",
                media_path=media_path, source="TEST_FIXTURE",
            )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{prefix}-finalize",
        )
        GlobalIdentityGraphService(store).record_observation_evidence(
            observation.observation_id, f"{prefix}-evidence",
        )
        return observation.observation_id

    def test_contract_parser_validates_levels_filters_limits_and_focus(self) -> None:
        request = _world_graph_v2_request_from_query(
            "version=2&level=PERSON&focus_type=person&focus_id=p1"
            "&recent_activity=last_30_days&location=HQ&location=Field"
            "&missing_location=exclude&lifecycle=active&biometric_state=no_face"
            "&evidence_type=co_observed&activity=high&people_limit=999"
        )
        self.assertEqual(request.detail_level, WorldDetailLevel.PERSON)
        self.assertEqual(request.filters.locations, ("HQ", "Field"))
        self.assertEqual(request.limits.people, 999)  # hard cap is applied by backend

        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            service = GraphReadService(store)
            with self.assertRaisesRegex(ValueError, "typed focus"):
                service.world_graph_v2(WorldGraphRequest(detail_level=WorldDetailLevel.PERSON))
            with self.assertRaisesRegex(ValueError, "cannot be combined"):
                service.world_graph_v2(WorldGraphRequest(filters=WorldReadFilter(
                    date_from="2026-01-01", recent_activity="LAST_30_DAYS",
                )))
            with self.assertRaisesRegex(ValueError, "explicit recent or date scope"):
                service.world_graph_v2(WorldGraphRequest(ranking="RECENT_ACTIVITY"))
            for index in range(105):
                store.create_person(f"Bounded {index:03d}")
            model = service.world_graph_v2(WorldGraphRequest(limits=WorldReadLimits(people=999)))
            self.assertEqual(model.limits.people, 100)
            self.assertEqual(len(model.people), 100)
            self.assertTrue(model.has_more)

    def test_scope_is_bounded_cursor_is_revision_bound_and_effective_filters_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            for index, name in enumerate(("Charlie", "Bravo", "Alpha"), 1):
                person = store.create_person(name)
                self._observe(
                    store, f"page-{index}", [person.person_id],
                    observed_at=f"2026-08-0{index}T00:00:00+00:00", location="HQ",
                )
            service = GraphReadService(store)
            request = WorldGraphRequest(
                filters=WorldReadFilter(recent_activity="LAST_30_DAYS"),
                limits=WorldReadLimits(people=1), as_of="2026-08-09T00:00:00+00:00",
                ranking="DISPLAY_NAME",
            )
            first = service.world_graph_v2(request)
            self.assertEqual(len(first.people), 1)
            self.assertTrue(first.has_more)
            self.assertTrue(first.truncated)
            self.assertEqual(first.effective_filters.date_from, "2026-07-10T00:00:00+00:00")
            second = service.world_graph_v2(WorldGraphRequest(
                **{**request.__dict__, "cursor": first.next_cursor, "revision": first.graph_revision}
            ))
            self.assertNotEqual(first.people[0].canonical_person_id, second.people[0].canonical_person_id)
            with self.assertRaisesRegex(ValueError, "scope"):
                service.world_graph_v2(WorldGraphRequest(
                    **{
                        **request.__dict__, "ranking": "EVIDENCE_COUNT",
                        "cursor": first.next_cursor, "revision": first.graph_revision,
                    }
                ))

            store.create_person("Revision change")
            with self.assertRaisesRegex(ValueError, "stale"):
                service.world_graph_v2(WorldGraphRequest(
                    **{**request.__dict__, "cursor": first.next_cursor, "revision": first.graph_revision}
                ))

    def test_canonical_merge_cluster_and_relationship_explanations_are_evidence_based(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor", {"importance": "High"})
            third = store.create_person("Third")
            self._observe(
                store, "one", [source.person_id, third.person_id],
                observed_at="2026-07-01T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "two", [survivor.person_id, third.person_id],
                observed_at="2026-07-02T10:00:00+00:00", location="HQ",
            )
            GlobalIdentityGraphService(store).create_note(
                survivor.person_id, "Explicit reference", "world-note",
                mentioned_person_ids=[third.person_id],
            )
            store.execute_identity_merge(source.person_id, survivor.person_id, "world-merge")

            scope = GraphReadService(store).world_graph_v2()
            self.assertEqual(len(scope.clusters), 1)
            cluster = scope.clusters[0]
            self.assertEqual(cluster.member_count, 2)
            self.assertEqual(cluster.member_ids, ())  # overview never exposes full membership
            self.assertEqual(cluster.evidence_basis["evidence_count"], 3)
            self.assertEqual(
                cluster.evidence_basis["evidence_type_counts"],
                {"CO_OBSERVED": 2, "NOTE_REFERENCE": 1},
            )
            survivor_model = next(
                item for item in scope.people if item.canonical_person_id == survivor.person_id
            )
            self.assertIn(source.person_id, survivor_model.historical_person_ids)
            self.assertEqual(survivor_model.lifecycle_state, "ACTIVE")
            self.assertEqual(survivor_model.importance_indicators[0]["kind"], "OPERATOR_ASSERTED")

            detail = GraphReadService(store).world_graph_v2(WorldGraphRequest(
            detail_level=WorldDetailLevel.CLUSTER,
            focus_type="CLUSTER", focus_id=cluster.cluster_id,
            collection=WorldCollection.RELATIONSHIPS,
            ))
            self.assertEqual(len(detail.relationships), 1)
            relationship = detail.relationships[0]
            self.assertEqual(relationship.strength_basis, "EVIDENCE_COUNT_IN_SCOPE")
            self.assertEqual(relationship.explanation.evidence_count, 3)
            self.assertNotEqual(relationship.source_person_id, relationship.target_person_id)

    def test_finalized_event_and_evidence_detail_preserve_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            event_id = self._observe(
                store, "event", [first.person_id, second.person_id],
                observed_at="2026-06-01T10:00:00+00:00", location="Gate",
            )
            service = GraphReadService(store)
            event = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=event_id,
            ))
            self.assertEqual(len(event.events), 1)
            self.assertEqual(event.events[0].location, "Gate")
            self.assertEqual(len(event.events[0].participants), 2)
            self.assertEqual(event.events[0].evidence_summary["total_count"], 1)

            relationship_id = (
                f"relationship:{min(first.person_id, second.person_id)}:"
                f"{max(first.person_id, second.person_id)}"
            )
            evidence = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVIDENCE,
                focus_type="RELATIONSHIP", focus_id=relationship_id,
            ))
            self.assertEqual(len(evidence.evidence), 1)
            item = evidence.evidence[0]
            self.assertEqual(item.evidence_type, "CO_OBSERVED")
            self.assertEqual(item.supporting_references[0]["source_entity_id"], event_id)
            self.assertIn("created_operation_id", item.provenance)

    def test_missing_location_evidence_filter_and_non_speculative_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            self._observe(
                store, "missing", [first.person_id, second.person_id],
                observed_at="2026-05-01T10:00:00+00:00", location=None,
            )
            GlobalIdentityGraphService(store).create_note(
                first.person_id, "Reference", "filter-note",
                mentioned_person_ids=[second.person_id],
            )
            service = GraphReadService(store)
            missing = service.world_graph_v2(WorldGraphRequest(filters=WorldReadFilter(
                missing_location="ONLY", evidence_type=("CO_OBSERVED",),
            )))
            self.assertEqual(missing.scope_totals["relationships"], 1)
            self.assertEqual(missing.clusters[0].evidence_basis["evidence_type_counts"], {"CO_OBSERVED": 1})
            self.assertEqual([item.pattern_type for item in missing.patterns], ["DATA_QUALITY"])
            with self.assertRaisesRegex(ValueError, "pattern-type"):
                service.world_graph_v2(WorldGraphRequest(filters=WorldReadFilter(
                    pattern_type=("RISK",),
                )))

    def test_overview_location_aggregation_normalizes_after_counting_each_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            self._observe(
                store, "location-one", [first.person_id, second.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location=" HQ ",
            )
            self._observe(
                store, "location-two", [first.person_id, second.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location="hq",
            )

            model = GraphReadService(store).world_graph_v2()
            self.assertEqual(model.scope_totals["finalized_events"], 2)
            self.assertEqual(model.available_facets["locations"], [
                {"value": "HQ", "count": 2},
            ])
            self.assertEqual(
                next(item for item in model.people if item.canonical_person_id == first.person_id)
                .activity_summary["finalized_event_count"],
                2,
            )

    def test_overview_aggregation_preserves_corrections_merges_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            original = store.create_person("Original")
            corrected = store.create_person("Corrected")
            survivor = store.create_person("Survivor")
            companion = store.create_person("Companion")
            corrected_event = self._observe(
                store, "corrected-overview", [original.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location=" HQ ",
            )
            self._observe(
                store, "second-overview", [survivor.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location="hq",
            )
            self._observe(
                store, "missing-overview", [companion.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location=None,
            )
            store.correct_observation_identity(
                corrected_event, original.person_id, corrected.person_id,
                "correct-overview-participant",
            )
            store.execute_identity_merge(
                corrected.person_id, survivor.person_id, "merge-overview-participant",
            )

            service = GraphReadService(store)
            overview = service.world_graph_v2()
            by_person = {
                item.canonical_person_id: item.activity_summary["finalized_event_count"]
                for item in overview.people
            }
            self.assertEqual(by_person[survivor.person_id], 2)
            self.assertEqual(by_person[companion.person_id], 1)
            self.assertEqual(by_person[original.person_id], 0)
            self.assertNotIn(corrected.person_id, by_person)
            self.assertEqual(overview.scope_totals["finalized_events"], 3)
            self.assertEqual(overview.available_facets["locations"], [
                {"value": "HQ", "count": 2},
                {"value": "MISSING", "count": 1},
            ])

            hq = service.world_graph_v2(WorldGraphRequest(filters=WorldReadFilter(
                locations=("HQ",),
            )))
            self.assertEqual(hq.scope_totals["finalized_events"], 2)
            self.assertEqual(hq.available_facets["locations"], [
                {"value": "HQ", "count": 2},
            ])
            self.assertEqual(
                next(
                    item for item in hq.people
                    if item.canonical_person_id == survivor.person_id
                ).activity_summary["finalized_event_count"],
                2,
            )

            recent = service.world_graph_v2(WorldGraphRequest(filters=WorldReadFilter(
                date_from="2026-08-02T00:00:00+00:00",
                missing_location="EXCLUDE",
            )))
            self.assertEqual(recent.scope_totals["finalized_events"], 1)
            self.assertEqual(recent.available_facets["locations"], [
                {"value": "hq", "count": 1},
            ])

    def test_revision_advances_for_finalized_world_event_but_not_draft_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Only participant")
            observation = store.create_observation(
                "single-create", participant_ids=[person.person_id],
            )
            created_revision = store.get_graph_revision()
            store.update_observation(
                observation.observation_id, "single-update", location="HQ",
            )
            self.assertEqual(store.get_graph_revision(), created_revision)
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "single-finalize",
            )
            self.assertNotEqual(store.get_graph_revision(), created_revision)
            model = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=observation.observation_id,
            ))
            self.assertEqual(model.scope_totals["finalized_events"], 1)

            profile_revision = store.get_graph_revision()
            store.update_person_profile(
                person.person_id, person.name, None, None, None, "Operator",
                tags=["not-world-visible"], operation_id="tags-only",
            )
            self.assertEqual(store.get_graph_revision(), profile_revision)

    def test_merge_collapses_same_event_activity_ranking_and_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Merge source")
            survivor = store.create_person("Merge survivor")
            leader = store.create_person("Activity leader")
            self._observe(
                store, "collapsed", [source.person_id, survivor.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "leader-1", [leader.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "leader-2", [leader.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location="HQ",
            )
            store.execute_identity_merge(source.person_id, survivor.person_id, "collapse-merge")

            model = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                ranking="RECENT_ACTIVITY",
                filters=WorldReadFilter(recent_activity="LAST_30_DAYS"),
                as_of="2026-08-09T00:00:00+00:00",
            ))
            survivor_model = next(
                item for item in model.people if item.canonical_person_id == survivor.person_id
            )
            self.assertEqual(survivor_model.activity_summary["finalized_event_count"], 1)
            self.assertEqual(model.people[0].canonical_person_id, leader.person_id)
            self.assertEqual(model.people[0].ranking["metrics"]["finalized_events"], 2)
            self.assertEqual(model.scope_totals["finalized_events"], 3)
            self.assertEqual(model.scope_totals["relationships"], 0)

    def test_person_events_are_bounded_and_cursor_is_collection_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Event subject")
            for index in range(3):
                self._observe(
                    store, f"person-event-{index}", [person.person_id],
                    observed_at=f"2026-08-0{index + 1}T10:00:00+00:00", location="HQ",
                )
            service = GraphReadService(store)
            request = WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON, focus_type="PERSON",
                focus_id=person.person_id, collection=WorldCollection.EVENTS,
                limits=WorldReadLimits(events=2),
            )
            first = service.world_graph_v2(request)
            page = first.pagination["EVENTS"]
            self.assertEqual((page.total_count, page.returned_count), (3, 2))
            self.assertTrue(page.has_more)
            self.assertEqual(len(first.events), 2)
            second = service.world_graph_v2(WorldGraphRequest(
                **{**request.__dict__, "cursor": page.next_cursor, "revision": first.graph_revision}
            ))
            self.assertEqual(second.pagination["EVENTS"].returned_count, 1)
            self.assertFalse(second.pagination["EVENTS"].has_more)
            with self.assertRaisesRegex(ValueError, "scope"):
                service.world_graph_v2(WorldGraphRequest(
                    **{
                        **request.__dict__, "collection": WorldCollection.RELATIONSHIPS,
                        "cursor": page.next_cursor, "revision": first.graph_revision,
                    }
                ))

    def test_event_evidence_and_media_have_independent_bounded_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(f"Participant {index}") for index in range(3)]
            event_id = self._observe(
                store, "paged-event", [item.person_id for item in people],
                observed_at="2026-08-01T10:00:00+00:00", location="Gate",
                media_count=3,
            )
            service = GraphReadService(store)
            evidence_request = WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT, focus_type="EVENT", focus_id=event_id,
                collection=WorldCollection.EVIDENCE, limits=WorldReadLimits(evidence=1),
            )
            evidence = service.world_graph_v2(evidence_request)
            self.assertEqual(evidence.pagination["EVIDENCE"].total_count, 3)
            self.assertEqual(evidence.pagination["EVIDENCE"].returned_count, 1)
            self.assertTrue(evidence.pagination["EVIDENCE"].has_more)
            self.assertEqual(evidence.pagination["MEDIA"].returned_count, 0)
            self.assertEqual(evidence.pagination["MEDIA"].truncation_reason, "collection_not_requested")

            media_request = WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT, focus_type="EVENT", focus_id=event_id,
                collection=WorldCollection.MEDIA, limits=WorldReadLimits(media=2),
            )
            media = service.world_graph_v2(media_request)
            self.assertEqual((media.pagination["MEDIA"].total_count,
                              media.pagination["MEDIA"].returned_count), (3, 2))
            self.assertTrue(media.pagination["MEDIA"].has_more)
            self.assertEqual(len(media.media), 2)
            self.assertFalse(hasattr(media.media[0], "content"))

    def test_event_provenance_distinguishes_corrected_and_merged_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            original = store.create_person("Original")
            corrected = store.create_person("Corrected")
            survivor = store.create_person("Survivor")
            event_id = self._observe(
                store, "provenance", [original.person_id, survivor.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location="HQ",
            )
            store.correct_observation_identity(
                event_id, original.person_id, corrected.person_id, "correct-world-event",
            )
            store.execute_identity_merge(corrected.person_id, survivor.person_id, "merge-corrected")
            event = GraphReadService(store).world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT, focus_type="EVENT", focus_id=event_id,
            )).events[0]
            self.assertEqual(event.participants, ({"person_id": survivor.person_id},))
            by_raw = {item["raw_person_id"]: item for item in event.participant_provenance}
            self.assertEqual(
                by_raw[original.person_id]["relationship_to_effective_identity"],
                "CORRECTED_PARTICIPANT",
            )
            self.assertEqual(
                by_raw[survivor.person_id]["relationship_to_effective_identity"],
                "ORIGINAL_IDENTITY",
            )

    def test_explanations_are_semantic_and_focused_reads_skip_global_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            event_id = self._observe(
                store, "explain", [first.person_id, second.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location="HQ",
            )
            service = GraphReadService(store)
            scope = service.world_graph_v2()
            self.assertTrue(scope.clusters[0].explanation.method)
            self.assertTrue(scope.clusters[0].explanation.calculation_scope)
            self.assertTrue(scope.clusters[0].explanation.strongest_factors)
            self.assertTrue(scope.people[0].ranking["ranking_reason"])
            self.assertIn("deterministic_tie_break", scope.people[0].ranking)
            with patch(
                "sentriface.storage.sqlite_store._world_clusters",
                side_effect=AssertionError("global cluster computation executed"),
            ):
                event = service.world_graph_v2(WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVENT, focus_type="EVENT", focus_id=event_id,
                ))
                person = service.world_graph_v2(WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON, focus_type="PERSON",
                    focus_id=first.person_id, collection=WorldCollection.EVENTS,
                ))
            self.assertEqual(len(event.events), 1)
            self.assertEqual(len(person.events), 1)

    def test_payload_is_v2_typed_and_does_not_expose_storage_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("Person")
            second = store.create_person("Legacy only")
            with store._connect() as conn:
                conn.execute(
                    """INSERT INTO person_associations(
                           association_id, source_person_id, target_person_id,
                           relationship_type, created_at, updated_at, created_by
                       ) VALUES (?, ?, ?, 'ASSOCIATED_WITH', ?, ?, ?)""",
                    (
                        "legacy-association", min(first.person_id, second.person_id),
                        max(first.person_id, second.person_id),
                        "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
                        "legacy-test",
                    ),
                )
            payload = _world_graph_v2_payload(GraphReadService(store).world_graph_v2())
            self.assertEqual(payload["contract_version"], 2)
            self.assertEqual(payload["requested_detail_level"], "WORLD_SCOPE")
            self.assertIn("effective_filters", payload)
            self.assertIn("scope_totals", payload)
            serialized = str(payload)
            self.assertNotIn("person_associations", serialized)
            self.assertNotIn("recognition_details", serialized)
            self.assertNotIn("relationship_evidence", payload)
            self.assertEqual(payload["scope_totals"]["relationships"], 0)
            self.assertEqual(payload["clusters"], [])


if __name__ == "__main__":
    unittest.main()
