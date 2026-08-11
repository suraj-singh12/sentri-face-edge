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

    def _reference_world_aggregate(
        self,
        store: SQLiteIdentityStore,
        filters: WorldReadFilter = WorldReadFilter(),
    ) -> tuple[dict[str, int], int, list[dict[str, object]]]:
        """Small authoritative oracle: correction, then terminal canonical identity."""
        with store._connect() as conn:
            person_rows = conn.execute(
                "SELECT person_id, canonical_person_id FROM persons"
            ).fetchall()
            observation_rows = conn.execute(
                """SELECT observation_id, observed_at, created_at, location, status
                   FROM observations"""
            ).fetchall()
            participant_rows = conn.execute(
                "SELECT observation_id, person_id FROM observation_participants"
            ).fetchall()
            correction_rows = conn.execute(
                """SELECT observation_id, from_person_id, to_person_id
                   FROM identity_corrections
                   WHERE correction_type = 'OBSERVATION_IDENTITY'
                   ORDER BY created_at, correction_id"""
            ).fetchall()

        parent = {
            str(row["person_id"]): (
                str(row["canonical_person_id"])
                if row["canonical_person_id"] else None
            )
            for row in person_rows
        }

        def terminal(person_id: str) -> str:
            current = person_id
            seen: set[str] = set()
            while parent[current] is not None:
                if current in seen:
                    raise AssertionError("reference canonical cycle")
                seen.add(current)
                current = str(parent[current])
            return current

        corrections = {
            (str(row["observation_id"]), str(row["from_person_id"])):
                str(row["to_person_id"])
            for row in correction_rows
        }
        participants: dict[str, list[str]] = {}
        for row in participant_rows:
            participants.setdefault(str(row["observation_id"]), []).append(
                str(row["person_id"])
            )

        activity: dict[str, int] = {}
        locations: dict[str, dict[str, object]] = {}
        total = 0
        allowed_locations = {item.casefold() for item in filters.locations}
        for row in observation_rows:
            if str(row["status"]) != "FINALIZED":
                continue
            occurred_at = str(row["observed_at"] or row["created_at"])
            if filters.date_from and occurred_at < filters.date_from:
                continue
            if filters.date_to and occurred_at > filters.date_to:
                continue
            raw_location = str(row["location"] or "").strip()
            location_key = raw_location.casefold()
            if allowed_locations and location_key not in allowed_locations:
                continue
            if filters.missing_location == "EXCLUDE" and not raw_location:
                continue
            if filters.missing_location == "ONLY" and raw_location:
                continue

            event_id = str(row["observation_id"])
            effective: set[str] = set()
            for raw_person_id in participants.get(event_id, []):
                corrected = raw_person_id
                seen: set[str] = set()
                while (event_id, corrected) in corrections:
                    if corrected in seen:
                        raise AssertionError("reference correction cycle")
                    seen.add(corrected)
                    corrected = corrections[(event_id, corrected)]
                effective.add(terminal(corrected))
            if not effective:
                continue
            total += 1
            for person_id in effective:
                activity[person_id] = activity.get(person_id, 0) + 1
            item = locations.setdefault(
                location_key,
                {"value": raw_location or "MISSING", "count": 0},
            )
            item["count"] = int(item["count"]) + 1
            if raw_location and raw_location < str(item["value"]):
                item["value"] = raw_location
        ordered_locations = sorted(
            locations.values(),
            key=lambda item: (-int(item["count"]), str(item["value"]).casefold()),
        )
        return activity, total, ordered_locations

    def _reference_scoped_event_count(
        self,
        store: SQLiteIdentityStore,
        eligible_person_ids: set[str],
        filters: WorldReadFilter = WorldReadFilter(),
    ) -> int:
        """Brute-force cluster count using correction-before-canonical semantics."""
        with store._connect() as conn:
            person_rows = conn.execute(
                "SELECT person_id, canonical_person_id FROM persons"
            ).fetchall()
            observation_rows = conn.execute(
                """SELECT observation_id, observed_at, created_at, location, status
                   FROM observations"""
            ).fetchall()
            participant_rows = conn.execute(
                "SELECT observation_id, person_id FROM observation_participants"
            ).fetchall()
            correction_rows = conn.execute(
                """SELECT observation_id, from_person_id, to_person_id
                   FROM identity_corrections
                   WHERE correction_type = 'OBSERVATION_IDENTITY'
                   ORDER BY created_at, correction_id"""
            ).fetchall()
        parent = {
            str(row["person_id"]): (
                str(row["canonical_person_id"])
                if row["canonical_person_id"] else None
            )
            for row in person_rows
        }

        def terminal(person_id: str) -> str:
            seen: set[str] = set()
            current = person_id
            while parent[current] is not None:
                if current in seen:
                    raise AssertionError("reference canonical cycle")
                seen.add(current)
                current = str(parent[current])
            return current

        corrections = {
            (str(row["observation_id"]), str(row["from_person_id"])):
                str(row["to_person_id"])
            for row in correction_rows
        }
        participants: dict[str, list[str]] = {}
        for row in participant_rows:
            participants.setdefault(str(row["observation_id"]), []).append(
                str(row["person_id"])
            )
        allowed_locations = {item.casefold() for item in filters.locations}
        count = 0
        for row in observation_rows:
            if str(row["status"]) != "FINALIZED":
                continue
            occurred_at = str(row["observed_at"] or row["created_at"])
            if filters.date_from and occurred_at < filters.date_from:
                continue
            if filters.date_to and occurred_at > filters.date_to:
                continue
            location = str(row["location"] or "").strip()
            if allowed_locations and location.casefold() not in allowed_locations:
                continue
            if filters.missing_location == "EXCLUDE" and not location:
                continue
            if filters.missing_location == "ONLY" and location:
                continue
            observation_id = str(row["observation_id"])
            effective: set[str] = set()
            for raw_id in participants.get(observation_id, []):
                current = raw_id
                seen: set[str] = set()
                while (observation_id, current) in corrections:
                    if current in seen:
                        raise AssertionError("reference correction cycle")
                    seen.add(current)
                    current = corrections[(observation_id, current)]
                effective.add(terminal(current))
            if effective & eligible_person_ids:
                count += 1
        return count

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

    def test_cluster_scoped_event_count_matches_correction_canonical_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("Cluster first")
            second = store.create_person("Cluster second")
            direct_alias = store.create_person("Direct alias")
            chain_source = store.create_person("Chain source")
            chain_middle = store.create_person("Chain middle")
            correction_source = store.create_person("Correction source")
            correction_target = store.create_person("Correction target")
            outsider = store.create_person("Cluster outsider")

            for suffix, location, observed_at in (
                ("hq", "HQ", "2026-08-01T10:00:00+00:00"),
                ("missing", None, "2026-08-02T10:00:00+00:00"),
                ("recent", "HQ", "2026-08-09T10:00:00+00:00"),
            ):
                self._observe(
                    store, f"cluster-basis-{suffix}",
                    [first.person_id, second.person_id],
                    observed_at=observed_at, location=location,
                )
            self._observe(
                store, "cluster-direct-alias", [direct_alias.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "cluster-chain", [chain_source.person_id],
                observed_at="2026-08-04T10:00:00+00:00", location="HQ",
            )
            collapsed = self._observe(
                store, "cluster-collapsed", [direct_alias.person_id, first.person_id],
                observed_at="2026-08-05T10:00:00+00:00", location="HQ",
            )
            corrected_in = self._observe(
                store, "cluster-corrected-in", [correction_source.person_id],
                observed_at="2026-08-06T10:00:00+00:00", location="HQ",
            )
            corrected_out = self._observe(
                store, "cluster-corrected-out", [first.person_id],
                observed_at="2026-08-07T10:00:00+00:00", location="HQ",
            )
            merge_then_correction = self._observe(
                store, "cluster-merge-correction", [direct_alias.person_id],
                observed_at="2026-08-08T10:00:00+00:00", location="HQ",
            )

            store.correct_observation_identity(
                corrected_in, correction_source.person_id,
                correction_target.person_id, "cluster-correct-in",
            )
            store.correct_observation_identity(
                corrected_out, first.person_id, outsider.person_id,
                "cluster-correct-out",
            )
            store.execute_identity_merge(
                direct_alias.person_id, first.person_id, "cluster-direct-merge",
            )
            store.execute_identity_merge(
                chain_source.person_id, chain_middle.person_id, "cluster-chain-one",
            )
            store.execute_identity_merge(
                chain_middle.person_id, second.person_id, "cluster-chain-two",
            )
            store.execute_identity_merge(
                correction_target.person_id, first.person_id,
                "cluster-merge-after-correction",
            )
            store.correct_observation_identity(
                merge_then_correction, direct_alias.person_id, outsider.person_id,
                "cluster-correction-after-merge",
            )

            service = GraphReadService(store)
            expected_members = {first.person_id, second.person_id}
            scopes = (
                WorldReadFilter(),
                WorldReadFilter(date_from="2026-08-05T00:00:00+00:00"),
                WorldReadFilter(locations=("HQ",)),
                WorldReadFilter(missing_location="ONLY"),
            )
            for filters in scopes:
                with self.subTest(filters=filters):
                    overview = service.world_graph_v2(WorldGraphRequest(
                        collection=WorldCollection.CLUSTERS, filters=filters,
                    ))
                    self.assertEqual(len(overview.clusters), 1)
                    cluster = overview.clusters[0]
                    detail = service.world_graph_v2(WorldGraphRequest(
                        detail_level=WorldDetailLevel.CLUSTER,
                        focus_type="CLUSTER", focus_id=cluster.cluster_id,
                        collection=WorldCollection.MEMBERS, filters=filters,
                        limits=WorldReadLimits(people=100),
                    ))
                    member_ids = {
                        person.canonical_person_id for person in detail.people
                    }
                    self.assertEqual(member_ids, expected_members)
                    self.assertEqual(cluster.member_count, len(expected_members))
                    self.assertEqual(
                        detail.scope_totals["finalized_events"],
                        self._reference_scoped_event_count(
                            store, expected_members, filters,
                        ),
                    )
            self.assertIn(collapsed, {
                row.event_id
                for row in service.world_graph_v2(WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON,
                    focus_type="PERSON", focus_id=first.person_id,
                    collection=WorldCollection.EVENTS,
                    limits=WorldReadLimits(events=100),
                )).events
            })

    def test_large_cluster_scoped_event_count_counts_each_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            members = [store.create_person(f"Large cluster {index}") for index in range(30)]
            self._observe(
                store, "large-cluster-all",
                [person.person_id for person in members],
                observed_at="2026-08-01T10:00:00+00:00", location="HQ",
            )
            for index, person in enumerate(members):
                self._observe(
                    store, f"large-cluster-single-{index}", [person.person_id],
                    observed_at="2026-08-02T10:00:00+00:00", location="HQ",
                )
            service = GraphReadService(store)
            cluster = service.world_graph_v2(WorldGraphRequest(
                collection=WorldCollection.CLUSTERS,
            )).clusters[0]
            detail = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.CLUSTER,
                focus_type="CLUSTER", focus_id=cluster.cluster_id,
                collection=WorldCollection.MEMBERS,
                limits=WorldReadLimits(people=100),
            ))
            member_ids = {person.canonical_person_id for person in detail.people}
            self.assertEqual(member_ids, {person.person_id for person in members})
            self.assertEqual(detail.scope_totals["finalized_events"], 31)
            self.assertEqual(
                detail.scope_totals["finalized_events"],
                self._reference_scoped_event_count(store, member_ids),
            )

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

    def test_overview_adjustment_matches_correction_before_canonical_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            terminal = store.create_person("Terminal")
            other = store.create_person("Other")
            extra = store.create_person("Extra")

            self._observe(
                store, "adjust-plain", [terminal.person_id, other.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location=" HQ ",
            )
            plain_reference = self._reference_world_aggregate(store)
            plain = GraphReadService(store).world_graph_v2()
            self.assertEqual(plain.scope_totals["finalized_events"], plain_reference[1])
            self.assertEqual(plain.available_facets["locations"], plain_reference[2])

            direct = store.create_person("Direct merge source")
            self._observe(
                store, "adjust-direct", [direct.person_id, other.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location="hq",
            )
            store.execute_identity_merge(
                direct.person_id, terminal.person_id, "adjust-direct-merge",
            )

            chain_a = store.create_person("Chain A")
            chain_b = store.create_person("Chain B")
            self._observe(
                store, "adjust-chain", [chain_a.person_id, other.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location="Field",
            )
            store.execute_identity_merge(
                chain_a.person_id, chain_b.person_id, "adjust-chain-a-b",
            )
            store.execute_identity_merge(
                chain_b.person_id, terminal.person_id, "adjust-chain-b-terminal",
            )

            correction_source = store.create_person("Correction source")
            correction_target = store.create_person("Correction target")
            correction_event = self._observe(
                store, "adjust-correction", [correction_source.person_id, other.person_id],
                observed_at="2026-08-04T10:00:00+00:00", location="Field",
            )
            store.correct_observation_identity(
                correction_event, correction_source.person_id,
                correction_target.person_id, "adjust-correction-only",
            )

            correction_merge_source = store.create_person("Correction merge source")
            correction_merge_target = store.create_person("Correction merge target")
            correction_merge_event = self._observe(
                store, "adjust-correction-merge",
                [correction_merge_source.person_id, other.person_id, extra.person_id],
                observed_at="2026-08-05T10:00:00+00:00", location="Gate",
            )
            store.correct_observation_identity(
                correction_merge_event, correction_merge_source.person_id,
                correction_merge_target.person_id, "adjust-correction-before-merge",
            )
            store.execute_identity_merge(
                correction_merge_target.person_id, terminal.person_id,
                "adjust-merge-after-correction",
            )

            merge_first_source = store.create_person("Merge-first source")
            merge_first_survivor = store.create_person("Merge-first survivor")
            merge_first_event = self._observe(
                store, "adjust-merge-correction",
                [merge_first_source.person_id, other.person_id, extra.person_id],
                observed_at="2026-08-06T10:00:00+00:00", location=None,
            )
            store.execute_identity_merge(
                merge_first_source.person_id, merge_first_survivor.person_id,
                "adjust-merge-before-correction",
            )
            store.correct_observation_identity(
                merge_first_event, merge_first_survivor.person_id,
                terminal.person_id, "adjust-correction-after-merge",
            )

            collapsed_a = store.create_person("Collapsed A")
            collapsed_b = store.create_person("Collapsed B")
            self._observe(
                store, "adjust-collapsed",
                [collapsed_a.person_id, collapsed_b.person_id,
                 terminal.person_id, other.person_id],
                observed_at="2026-08-07T10:00:00+00:00", location="Gate",
            )
            store.execute_identity_merge(
                collapsed_a.person_id, terminal.person_id, "adjust-collapse-a",
            )
            store.execute_identity_merge(
                collapsed_b.person_id, terminal.person_id, "adjust-collapse-b",
            )
            store.create_observation(
                "adjust-draft", participant_ids=[terminal.person_id],
                observed_at="2026-08-08T10:00:00+00:00", location="Gate",
            )

            service = GraphReadService(store)
            scopes = (
                WorldReadFilter(),
                WorldReadFilter(date_from="2026-08-04T00:00:00+00:00"),
                WorldReadFilter(locations=("Gate",)),
                WorldReadFilter(missing_location="ONLY"),
                WorldReadFilter(missing_location="EXCLUDE"),
            )
            for filters in scopes:
                with self.subTest(filters=filters):
                    expected_activity, expected_total, expected_locations = (
                        self._reference_world_aggregate(store, filters)
                    )
                    model = service.world_graph_v2(WorldGraphRequest(filters=filters))
                    actual_activity = {
                        person.canonical_person_id:
                            person.activity_summary["finalized_event_count"]
                        for person in model.people
                    }
                    self.assertEqual(model.scope_totals["finalized_events"], expected_total)
                    self.assertEqual(model.available_facets["locations"], expected_locations)
                    self.assertEqual(
                        {
                            person_id: count for person_id, count in actual_activity.items()
                            if count
                        },
                        expected_activity,
                    )

    def test_location_facet_collection_matches_authoritative_overview_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            service = GraphReadService(store)
            empty = service.world_graph_v2(WorldGraphRequest(
                collection=WorldCollection.LOCATION_FACETS,
            ))
            self.assertEqual(empty.available_facets["locations"], [])
            self.assertEqual(empty.pagination["LOCATION_FACETS"].total_count, 0)

            first = store.create_person("Facet first")
            second = store.create_person("Facet second")
            raw = store.create_person("Facet raw")
            corrected = store.create_person("Facet corrected")
            survivor = store.create_person("Facet survivor")
            self._observe(
                store, "facet-hq", [first.person_id, second.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location="HQ",
            )
            one_location = service.world_graph_v2(WorldGraphRequest(
                collection=WorldCollection.LOCATION_FACETS,
            ))
            self.assertEqual(
                one_location.available_facets["locations"],
                [{"value": "HQ", "count": 1}],
            )
            corrected_event = self._observe(
                store, "facet-missing", [raw.person_id, second.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location=None,
            )
            store.correct_observation_identity(
                corrected_event, raw.person_id, corrected.person_id,
                "facet-correction-before-merge",
            )
            store.execute_identity_merge(
                corrected.person_id, survivor.person_id, "facet-merge-after-correction",
            )
            self._observe(
                store, "facet-field", [survivor.person_id, first.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location="Field",
            )

            scopes = (
                WorldReadFilter(),
                WorldReadFilter(missing_location="EXCLUDE"),
                WorldReadFilter(missing_location="ONLY"),
                WorldReadFilter(date_from="2026-08-02T00:00:00+00:00"),
                WorldReadFilter(locations=("HQ",)),
                WorldReadFilter(activity=("LOW",)),
            )
            for filters in scopes:
                with self.subTest(filters=filters):
                    limits = WorldReadLimits(facets=100)
                    authoritative = service.world_graph_v2(WorldGraphRequest(
                        filters=filters, limits=limits,
                    ))
                    focused = service.world_graph_v2(WorldGraphRequest(
                        collection=WorldCollection.LOCATION_FACETS,
                        filters=filters, limits=limits,
                    ))
                    self.assertEqual(
                        focused.available_facets["locations"],
                        authoritative.available_facets["locations"],
                    )
                    self.assertEqual(
                        focused.pagination["LOCATION_FACETS"].total_count,
                        authoritative.pagination["LOCATION_FACETS"].total_count,
                    )
                    self.assertEqual(
                        focused.scope_totals["finalized_events"],
                        authoritative.scope_totals["finalized_events"],
                    )

            from sentriface.storage import sqlite_store as module

            unrelated = (
                "_world_relationship_scope", "_world_rank_people", "_world_clusters",
                "_world_patterns", "_world_facets", "_world_person",
                "_world_event_statistics", "_world_full_scope_event_statistics",
            )
            patches = [
                patch.object(
                    module, name,
                    side_effect=AssertionError(f"unrelated location-facet work: {name}"),
                )
                for name in unrelated
            ]
            for active_patch in patches:
                active_patch.start()
            try:
                isolated = service.world_graph_v2(WorldGraphRequest(
                    collection=WorldCollection.LOCATION_FACETS,
                    limits=WorldReadLimits(facets=2),
                ))
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()
            self.assertEqual(len(isolated.available_facets["locations"]), 2)
            self.assertEqual(isolated.people, ())
            self.assertEqual(isolated.relationships, ())
            self.assertEqual(isolated.clusters, ())
            self.assertEqual(isolated.patterns, ())

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

    def test_person_event_count_and_pages_share_exact_effective_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            terminal = store.create_person("Terminal")

            plain_event = self._observe(
                store, "focused-plain", [terminal.person_id],
                observed_at="2026-08-01T10:00:00+00:00", location="Gate",
            )

            direct_source = store.create_person("Direct source")
            direct_event = self._observe(
                store, "focused-direct", [direct_source.person_id],
                observed_at="2026-08-02T10:00:00+00:00", location="Gate",
            )
            store.execute_identity_merge(
                direct_source.person_id, terminal.person_id, "focused-direct-merge",
            )

            chain_a = store.create_person("Chain A")
            chain_b = store.create_person("Chain B")
            chain_event = self._observe(
                store, "focused-chain", [chain_a.person_id],
                observed_at="2026-08-03T10:00:00+00:00", location="Gate",
            )
            store.execute_identity_merge(
                chain_a.person_id, chain_b.person_id, "focused-chain-a-b",
            )
            store.execute_identity_merge(
                chain_b.person_id, terminal.person_id, "focused-chain-b-terminal",
            )

            corrected_source = store.create_person("Corrected source")
            corrected_target = store.create_person("Corrected target")
            correction_then_merge_event = self._observe(
                store, "focused-correct-merge", [corrected_source.person_id],
                observed_at="2026-08-04T10:00:00+00:00", location="Annex",
            )
            store.correct_observation_identity(
                correction_then_merge_event, corrected_source.person_id,
                corrected_target.person_id, "focused-correct-before-merge",
            )
            store.execute_identity_merge(
                corrected_target.person_id, terminal.person_id,
                "focused-merge-after-correction",
            )

            merge_first_source = store.create_person("Merge-first source")
            merge_first_survivor = store.create_person("Merge-first survivor")
            merge_then_correction_event = self._observe(
                store, "focused-merge-correct", [merge_first_source.person_id],
                observed_at="2026-08-05T10:00:00+00:00", location=None,
            )
            store.execute_identity_merge(
                merge_first_source.person_id, merge_first_survivor.person_id,
                "focused-merge-before-correction",
            )
            store.correct_observation_identity(
                merge_then_correction_event, merge_first_survivor.person_id,
                terminal.person_id, "focused-correct-after-merge",
            )

            collapsed_a = store.create_person("Collapsed A")
            collapsed_b = store.create_person("Collapsed B")
            collapsed_event = self._observe(
                store, "focused-collapse",
                [collapsed_a.person_id, collapsed_b.person_id, terminal.person_id],
                observed_at="2026-08-06T10:00:00+00:00", location="Gate",
            )
            store.execute_identity_merge(
                collapsed_a.person_id, terminal.person_id, "focused-collapse-a",
            )
            store.execute_identity_merge(
                collapsed_b.person_id, terminal.person_id, "focused-collapse-b",
            )

            unrelated = store.create_person("Unrelated")
            self._observe(
                store, "focused-unrelated", [unrelated.person_id],
                observed_at="2026-08-07T10:00:00+00:00", location="Gate",
            )
            store.create_observation(
                "focused-draft", participant_ids=[terminal.person_id],
                observed_at="2026-08-08T10:00:00+00:00", location="Gate",
            )

            service = GraphReadService(store)
            request = WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON", focus_id=terminal.person_id,
                collection=WorldCollection.EVENTS,
                limits=WorldReadLimits(events=2),
                as_of="2026-08-09T00:00:00+00:00",
            )
            cursor = None
            revision = None
            walked: list[str] = []
            expected_total = None
            while True:
                page = service.world_graph_v2(WorldGraphRequest(**{
                    **request.__dict__, "cursor": cursor, "revision": revision,
                }))
                event_page = page.pagination["EVENTS"]
                expected_total = event_page.total_count if expected_total is None else expected_total
                self.assertEqual(event_page.total_count, expected_total)
                self.assertEqual(
                    page.people[0].activity_summary["finalized_event_count"],
                    event_page.total_count,
                )
                walked.extend(item.event_id for item in page.events)
                if not event_page.has_more:
                    break
                cursor = event_page.next_cursor
                revision = page.graph_revision

            expected = [
                collapsed_event, merge_then_correction_event,
                correction_then_merge_event, chain_event, direct_event, plain_event,
            ]
            self.assertEqual(walked, expected)
            self.assertEqual(expected_total, len(expected))
            self.assertEqual(len(set(walked)), len(walked))

            recent = service.world_graph_v2(WorldGraphRequest(
                **{
                    **request.__dict__, "cursor": None, "revision": None,
                    "filters": WorldReadFilter(
                        date_from="2026-08-04T00:00:00+00:00",
                    ),
                    "limits": WorldReadLimits(events=10),
                }
            ))
            self.assertEqual(
                [item.event_id for item in recent.events],
                [collapsed_event, merge_then_correction_event, correction_then_merge_event],
            )
            self.assertEqual(recent.pagination["EVENTS"].total_count, 3)

            gate = service.world_graph_v2(WorldGraphRequest(
                **{
                    **request.__dict__, "cursor": None, "revision": None,
                    "filters": WorldReadFilter(locations=("Gate",)),
                    "limits": WorldReadLimits(events=10),
                }
            ))
            self.assertEqual(
                [item.event_id for item in gate.events],
                [collapsed_event, chain_event, direct_event, plain_event],
            )
            self.assertEqual(gate.pagination["EVENTS"].total_count, 4)

            missing = service.world_graph_v2(WorldGraphRequest(
                **{
                    **request.__dict__, "cursor": None, "revision": None,
                    "filters": WorldReadFilter(missing_location="ONLY"),
                    "limits": WorldReadLimits(events=10),
                }
            ))
            self.assertEqual(
                [item.event_id for item in missing.events],
                [merge_then_correction_event],
            )
            self.assertEqual(missing.pagination["EVENTS"].total_count, 1)

            provenance = service.world_graph_v2(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=collapsed_event,
                collection=WorldCollection.PROVENANCE,
            )).events[0].participant_provenance
            self.assertEqual(
                {item["raw_person_id"] for item in provenance},
                {collapsed_a.person_id, collapsed_b.person_id, terminal.person_id},
            )

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
                collection=WorldCollection.PROVENANCE,
            )).events[0]
            self.assertEqual(event.participants, ())
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
            self.assertEqual(len(person.people[0].cluster_memberships), 1)

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
