from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class IntelligenceReadModelTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _finalize(
        self,
        store: SQLiteIdentityStore,
        prefix: str,
        person_ids: list[str],
        observed_at: str,
        location: str = "HQ",
    ) -> str:
        observation = store.create_observation(
            f"{prefix}-create",
            observed_at=observed_at,
            location=location,
            context={"occasion": prefix},
            participant_ids=person_ids,
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{prefix}-finalize",
        )
        return observation.observation_id

    def test_one_person_multiple_detections_is_one_observation_sighting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Repeated face")
            observation = store.create_observation(
                "repeat-create", observed_at="2026-08-01T09:00:00+00:00",
            )
            for index in range(3):
                store.add_observation_participant(
                    observation.observation_id,
                    person.person_id,
                    f"repeat-participant-{index}",
                )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "repeat-finalize",
            )

            sightings = store.list_person_sightings(person.person_id)
            self.assertEqual(len(sightings), 1)
            self.assertEqual(sightings[0].observation_id, observation.observation_id)
            self.assertEqual(store.list_persons()[0].sighting_count, 1)

    def test_presence_first_last_frequency_locations_and_multiple_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Traveler")
            self._finalize(
                store, "arrival", [person.person_id],
                "2026-06-01T08:00:00+00:00", "Gate A",
            )
            self._finalize(
                store, "return", [person.person_id],
                "2026-07-15T18:30:00+00:00", "Gate A",
            )

            presence = store.get_person_intelligence(person.person_id).presence
            self.assertEqual(presence.observation_count, 2)
            self.assertEqual(presence.first_seen_at, "2026-06-01T08:00:00+00:00")
            self.assertEqual(presence.last_seen_at, "2026-07-15T18:30:00+00:00")
            self.assertEqual([(item.period, item.count) for item in presence.timeline], [
                ("2026-06", 1), ("2026-07", 1),
            ])
            self.assertEqual((presence.locations[0].location, presence.locations[0].count), ("Gate A", 2))
            self.assertGreater(presence.frequency_per_30_days, 0)

    def test_merge_aggregates_historical_sightings_without_rewriting_raw_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            observation_id = self._finalize(
                store, "source-seen", [source.person_id],
                "2026-05-01T10:00:00+00:00",
            )
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "source-to-survivor",
            )

            sighting = store.list_person_sightings(survivor.person_id)[0]
            self.assertEqual(sighting.observation_id, observation_id)
            self.assertEqual(sighting.canonical_person_id, survivor.person_id)
            self.assertEqual(sighting.raw_participant_person_ids, (source.person_id,))
            source_intelligence = store.get_person_intelligence(source.person_id)
            self.assertEqual(source_intelligence.canonical_person_id, survivor.person_id)
            self.assertEqual(source_intelligence.lifecycle_status, "MERGED")
            self.assertEqual(source_intelligence.canonical_lifecycle_status, "ACTIVE")

    def test_identity_correction_moves_current_sighting_and_preserves_raw_participant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            original = store.create_person("Original")
            corrected = store.create_person("Corrected")
            observation_id = self._finalize(
                store, "correction", [original.person_id],
                "2026-08-02T11:00:00+00:00",
            )
            store.correct_observation_identity(
                observation_id, original.person_id, corrected.person_id, "correct-identity",
            )

            self.assertEqual(store.list_person_sightings(original.person_id), [])
            sighting = store.list_person_sightings(corrected.person_id)[0]
            self.assertEqual(sighting.raw_participant_person_ids, (original.person_id,))
            self.assertEqual(sighting.correction_operation_ids, ("correct-identity",))

    def test_graph_analytics_uses_only_normalized_evidence_and_counts_types_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("First")
            second = store.create_person("Second")
            unrelated = store.create_person("Unrelated")
            observation_id = self._finalize(
                store, "together", [first.person_id, second.person_id],
                "2026-08-03T12:00:00+00:00",
            )
            graph.record_observation_evidence(observation_id, "together-evidence")
            repeated_observation = self._finalize(
                store, "together-again", [first.person_id, second.person_id],
                "2026-08-03T13:00:00+00:00",
            )
            graph.record_observation_evidence(repeated_observation, "together-again-evidence")
            other_observation = self._finalize(
                store, "unrelated", [second.person_id, unrelated.person_id],
                "2026-08-04T12:00:00+00:00",
            )
            graph.record_observation_evidence(other_observation, "unrelated-evidence")
            store._legacy_create_person_association(
                first.person_id, unrelated.person_id, "Legacy operator", "legacy-association",
            )

            relationships = store.get_person_intelligence(first.person_id).relationships
            self.assertEqual(len(relationships), 1)
            relationship = relationships[0]
            self.assertEqual(relationship.person_id, second.person_id)
            self.assertEqual(relationship.evidence_count, 2)
            self.assertEqual(relationship.evidence_type_counts, {"CO_OBSERVED": 2})
            self.assertEqual(relationship.co_observation_count, 2)
            self.assertEqual(relationship.evidence[0].source_entity_id, observation_id)

    def test_no_face_identity_has_presence_activity_and_relationship_analytics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            no_face = store.create_person("No Face")
            other = store.create_person("Known")
            observation_id = self._finalize(
                store, "no-face", [no_face.person_id, other.person_id],
                "2026-08-05T12:00:00+00:00",
            )
            graph.record_observation_evidence(observation_id, "no-face-evidence")
            store.update_person_profile(
                no_face.person_id, no_face.name, None, None, None, "Operator",
                operation_id="no-face-profile",
            )

            intelligence = store.get_person_intelligence(no_face.person_id)
            self.assertEqual(intelligence.biometric_status, "NO_FACE")
            self.assertEqual(intelligence.embedding_count, 0)
            self.assertIsNone(intelligence.confidence_summary["score"])
            self.assertEqual(intelligence.presence.observation_count, 1)
            self.assertEqual(intelligence.relationships[0].person_id, other.person_id)
            self.assertTrue(any(item["operation_id"] == "no-face-profile" for item in intelligence.activity))


if __name__ == "__main__":
    unittest.main()
