from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.models import DetectedFace, FaceBox, InitFace, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore, SCHEMA_VERSION, SchemaMigrationError, _schema_migrations
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import WorldGraphRequest, WorldDetailLevel
from sentriface.errors import OperationRevertRefused
from tests import test_identity_corrections as correction_helpers


class EncounterManagementTest(unittest.TestCase):
    _pending = correction_helpers.IdentityCorrectionTest._pending
    _finalize = correction_helpers.IdentityCorrectionTest._finalize

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteIdentityStore(Path(self.temp.name) / 'identity.db', embedding_dim=2)
        self.store.initialize()
        self.a, self.b, self.c, self.d = [self.store.create_person(name) for name in ('A', 'B', 'C', 'D')]
        self.oid = self._finalize(self.store, 'original', [self.a, self.b])['observation_id']

    def correct(self, op, **values):
        return self.store.correct_encounter(self.oid, op, expected_revision=self.store.get_encounter_read(self.oid)['revision'], **values)

    def pair(self, a, b, decision='INCLUDE'):
        return {'first_person_id': a.person_id, 'second_person_id': b.person_id, 'disposition': decision}

    def evidence(self):
        with self.store._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM relationship_evidence WHERE active = 1 AND evidence_type = 'CO_OBSERVED'")]

    def test_metadata_mentions_history_stale_and_retry(self):
        previous = self.store.get_encounter_read(self.oid)
        result = self.correct('metadata', event_details={'date': '2026-09-29', 'place_seen': 'Delhi', 'event_occasion': 'Meeting', 'event_notes': '@C and literal @D', 'event_mentioned_person_ids': [self.c.person_id]})
        current = self.store.get_encounter_read(self.oid)
        self.assertEqual(current['location'], 'Delhi')
        self.assertNotEqual(result['historical_value']['location'], 'Delhi')
        self.assertEqual(current['mentioned_person_ids'], [self.c.person_id])
        self.assertEqual(self.store.query_encounters(person_id=self.c.person_id)['events'][0]['person_status'], 'MENTIONED')
        self.assertEqual(self.store.list_person_encounter_media(self.c.person_id), [])
        retry = self.store.correct_encounter(self.oid, 'metadata', expected_revision=previous['revision'])
        self.assertEqual(result, retry)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.store.correct_encounter(self.oid, 'stale', expected_revision=previous['revision'])
        self.correct('mention-remove', event_details={'event_mentioned_person_ids': []})
        self.assertEqual(self.store.get_encounter_read(self.oid)['mentioned_person_ids'], [])
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM relationship_evidence WHERE evidence_type = 'NOTE_REFERENCE'").fetchone()[0], 0)
        self.assertTrue(any(item['operation_id'] == 'metadata' for item in current['history']))

    def test_remove_add_relations_rebuild_and_mention_independence(self):
        self.correct('mention-b', event_details={'event_mentioned_person_ids': [self.b.person_id]})
        self.correct('remove-b', participant_correction={'action': 'REMOVE', 'person_id': self.b.person_id})
        self.assertEqual(self.store.get_encounter_read(self.oid)['participant_ids'], [self.a.person_id])
        self.assertEqual(self.store.query_encounters(person_id=self.b.person_id)['events'][0]['person_status'], 'MENTIONED')
        self.assertEqual(self.evidence(), [])
        with self.assertRaisesRegex(ValueError, 'explicit'):
            self.correct('add-no-pairs', participant_correction={'action': 'ADD', 'person_id': self.c.person_id})
        self.assertIsNone(self.store.get_operation('add-no-pairs'))
        self.correct('add-c', participant_correction={'action': 'ADD', 'person_id': self.c.person_id}, relations=[self.pair(self.a, self.c, 'EXCLUDE')])
        self.correct('include-c', relations=[self.pair(self.a, self.c)])
        self.assertEqual(len(self.evidence()), 1)
        result = self.correct('exclude-c', relations=[self.pair(self.a, self.c, 'EXCLUDE')])
        self.assertEqual(self.evidence(), [])
        self.assertEqual(result, self.store.correct_encounter(self.oid, 'exclude-c', expected_revision='old'))
        self.store.rebuild_graph_projection('rebuild')
        self.assertEqual(self.evidence(), [])
        self.assertTrue(self.store.validate_graph_projection()['valid'])
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM observation_participants WHERE observation_id = ? AND person_id = ?", (self.oid, self.b.person_id)).fetchone()[0], 1)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM encounter_relation_decisions WHERE active = 0").fetchone()[0], 0)

    def test_reassignment_preserves_face_and_effective_photos(self):
        self.correct('reassign-b', participant_correction={'action': 'REASSIGN', 'person_id': self.b.person_id, 'to_person_id': self.d.person_id})
        current = self.store.get_encounter_read(self.oid)
        self.assertEqual(set(current['participant_ids']), {self.a.person_id, self.d.person_id})
        self.assertEqual(self.store.list_person_encounter_media(self.b.person_id), [])
        self.assertTrue(self.store.list_person_encounter_media(self.d.person_id))
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM observation_face_assignments WHERE original_person_id = ?", (self.b.person_id,)).fetchone()[0], 1)
        self.assertTrue(self.store.validate_graph_projection()['valid'])

    def amendment(self, faces, path='/managed/attached.jpg'):
        session = self.store.create_init_session('/managed/attach')
        self.store.save_init_session_media(session.session_id, [path])
        self.store.save_init_faces([InitFace(init_face_id=f'{session.session_id}-face-{index}', session_id=session.session_id,
            group_id=f'group-{index}', source_image=path, face=DetectedFace(FaceBox(1, 1, 10, 10, .9), .9),
            vector=(.3+index*.1, .7-index*.1), quality=QualityReport(QualityStatus.GOOD, .9)) for index in range(len(faces))])
        ids = [item['media_id'] for item in self.store.list_init_session_media(session.session_id)]
        reviews = self.store.plan_init_session_encounters(session.session_id, [ids], target_observation_id=self.oid,
            expected_revision=self.store.get_encounter_read(self.oid)['revision'])
        rid = reviews[0]['review_id']
        for face, person in zip(reviews[0]['faces'], faces):
            self.store.set_photo_review_face_decision(rid, face['face_id'], 'ACCEPT_EXISTING_PERSON', person_id=person.person_id)
        return rid

    def test_attach_same_occurrence_existing_pair_preserved_new_pairs_explicit(self):
        rid = self.amendment([self.a, self.b, self.c])
        review = self.store.complete_encounter_identity_review(rid)
        self.assertEqual(len(review['relation_candidates']), 2)
        for pair in review['relation_candidates']:
            self.store.set_encounter_relation_decision(rid, pair['first_ref'], pair['second_ref'], 'EXCLUDE')
        before_media = len(self.store.list_observation_media(self.oid))
        result = self.store.complete_photo_review(rid, 'attach')
        self.assertEqual(result['observation_id'], self.oid)
        self.assertEqual(len(self.store.query_encounters()['events']), 1)
        self.assertEqual(len(self.store.list_observation_media(self.oid)), before_media+1)
        self.assertEqual(len(self.evidence()), 1)
        relations = self.store.get_encounter_read(self.oid)['relations']
        ab = next(row for row in relations if {row['first_person_id'], row['second_person_id']} == {self.a.person_id, self.b.person_id})
        self.assertEqual(ab['support'], 'SHARED_FRAME')
        self.assertEqual(ab['disposition'], 'INCLUDE')
        self.assertEqual(result, self.store.complete_photo_review(rid, 'attach'))
        self.store.rebuild_graph_projection('after-attach-rebuild')
        self.assertEqual(len(self.evidence()), 1)

    def test_attachment_guards_and_rollback(self):
        rid = self.amendment([self.a])
        with self.assertRaisesRegex(ValueError, 'active Attach'):
            self.correct('blocked', event_details={'place_seen': 'Elsewhere'})
        with self.assertRaisesRegex(ValueError, 'active Encounter'):
            self.store.archive_person(self.b.person_id, 'archive-blocked')
        self.store.complete_encounter_identity_review(rid)
        with patch('sentriface.storage.sqlite_store._replace_graph_projection', side_effect=RuntimeError('injected')):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.store.complete_photo_review(rid, 'failed-attach')
        self.assertIsNone(self.store.get_operation('failed-attach'))
        self.assertEqual(self.store.get_encounter_review(rid)['status'], 'IN_PROGRESS')
        self.assertEqual(len(self.store.query_encounters()['events']), 1)

    def test_dedup_refuses_existing_encounter_media(self):
        with self.assertRaisesRegex(ValueError, 'already belongs'):
            self.amendment([self.a], '/managed/original-pending-0.jpg')
        other = self._finalize(self.store, 'other', [self.c])['observation_id']
        with self.assertRaisesRegex(ValueError, other):
            self.amendment([self.c], '/managed/other-pending-0.jpg')

    def test_manual_evidence_independent_retirement_retry_and_rollback(self):
        manual = self.store.create_manual_association(self.a.person_id, self.b.person_id, 'manual')
        self.assertEqual(manual, self.store.create_manual_association(self.a.person_id, self.b.person_id, 'manual'))
        self.assertEqual(set(self.store.get_person_neighbors(self.a.person_id)[0].evidence_types), {'MANUAL_ASSOCIATION', 'CO_OBSERVED'})
        with patch('sentriface.storage.sqlite_store._replace_graph_projection', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.store.retire_manual_association(manual['evidence_id'], 'failed-retire')
        self.assertIsNone(self.store.get_operation('failed-retire'))
        retired = self.store.retire_manual_association(manual['evidence_id'], 'retire')
        self.assertEqual(retired, self.store.retire_manual_association(manual['evidence_id'], 'retire'))
        self.assertEqual(self.store.get_person_neighbors(self.a.person_id)[0].evidence_types, ('CO_OBSERVED',))
        with patch('sentriface.storage.sqlite_store._replace_graph_projection', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.store.create_manual_association(self.a.person_id, self.c.person_id, 'failed-create')
        self.assertIsNone(self.store.get_operation('failed-create'))

    def test_each_correction_rolls_back_before_and_after_authority(self):
        for op, values in [('metadata', {'event_details': {'place_seen': 'Agra'}}),
                           ('remove', {'participant_correction': {'action': 'REMOVE', 'person_id': self.b.person_id}}),
                           ('relation', {'relations': [self.pair(self.a, self.b, 'EXCLUDE')]})]:
            before = self.store.get_encounter_read(self.oid)
            with patch('sentriface.storage.sqlite_store._replace_graph_projection', side_effect=RuntimeError('injected')):
                with self.assertRaises(RuntimeError):
                    self.correct(f'failed-{op}', **values)
            self.assertEqual(before, self.store.get_encounter_read(self.oid))
            self.assertIsNone(self.store.get_operation(f'failed-{op}'))

    def test_schema_upgrade_backup_foreign_keys_repeat_and_rollback(self):
        path = Path(self.temp.name) / 'old.db'
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            for migration in _schema_migrations():
                if migration.to_version <= 31:
                    migration.apply(conn)
        old = SQLiteIdentityStore(path, embedding_dim=2)
        from sentriface.storage.sqlite_store import _migrate_31_to_32
        def fail_after_extension(conn):
            _migrate_31_to_32(conn)
            raise RuntimeError('forced amendment migration failure')
        with patch('sentriface.storage.sqlite_store._migrate_31_to_32', fail_after_extension):
            with self.assertRaisesRegex(SchemaMigrationError, 'forced amendment migration failure'):
                old.initialize()
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 31)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name = 'encounter_participant_revisions'").fetchone())
            self.assertNotIn('target_observation_id', [row[1] for row in conn.execute('PRAGMA table_info(photo_reviews)')])
        old.initialize()
        old.initialize()
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertTrue(list(old.backup_dir.iterdir()))

    def test_removed_identity_later_merge_preserves_survivor_participation(self):
        self.correct('remove-before-merge', participant_correction={'action': 'REMOVE', 'person_id': self.b.person_id})
        self.store.execute_identity_merge(self.b.person_id, self.a.person_id, 'removed-merge')
        self.assertEqual(self.store.get_encounter_read(self.oid)['participant_ids'], [self.a.person_id])
        self.assertEqual(len(self.store.list_person_sightings(self.a.person_id)), 1)
        self.assertTrue(self.store.validate_graph_projection()['valid'])
        self.assertEqual(ReadOnlyIntegrityChecker(self.store.db_path).run().findings, ())

    def test_merge_relation_conflict_can_be_corrected_then_deduplicated(self):
        self.correct('add-for-merge', participant_correction={'action': 'ADD', 'person_id': self.c.person_id},
                     relations=[self.pair(self.a, self.c), self.pair(self.b, self.c, 'EXCLUDE')])
        with self.assertRaisesRegex(ValueError, self.oid):
            self.store.preview_identity_merge(self.b.person_id, self.a.person_id)
        self.correct('resolve-merge', relations=[self.pair(self.b, self.c)])
        self.store.execute_identity_merge(self.b.person_id, self.a.person_id, 'resolved-merge')
        self.assertEqual(set(self.store.get_encounter_read(self.oid)['participant_ids']), {self.a.person_id, self.c.person_id})
        self.assertEqual(len(self.evidence()), 1)
        with self.assertRaisesRegex(OperationRevertRefused, 'safely reversible|Relations'):
            self.store.prepare_operation_revert('resolved-merge')
        self.store.rebuild_graph_projection('merged-rebuild')
        self.assertEqual(len(self.evidence()), 1)
        self.assertEqual(ReadOnlyIntegrityChecker(self.store.db_path).run().findings, ())

    def test_attachment_without_faces_keeps_occurrence_and_participants(self):
        rid = self.amendment([])
        self.store.complete_encounter_identity_review(rid)
        result = self.store.complete_photo_review(rid, 'no-face-attachment')
        self.assertEqual(result['observation_id'], self.oid)
        self.assertEqual(set(self.store.get_encounter_read(self.oid)['participant_ids']), {self.a.person_id, self.b.person_id})
        self.assertEqual(len(self.evidence()), 1)
        self.assertEqual(ReadOnlyIntegrityChecker(self.store.db_path).run().findings, ())

    def test_all_excluded_attachment_reuses_standalone_media_reference(self):
        path = '/managed/standalone.jpg'
        embedding = self.store.add_embedding(self.d.person_id, (.5, .5), .9, source_image=path)
        rid = self.amendment([self.a], path)
        face = self.store.get_encounter_review(rid)['faces'][0]
        self.store.set_photo_review_face_decision(rid, face['face_id'], 'EXCLUDE')
        self.store.complete_encounter_identity_review(rid)
        self.store.complete_photo_review(rid, 'excluded-attachment')
        self.assertEqual(set(self.store.get_encounter_read(self.oid)['participant_ids']), {self.a.person_id, self.b.person_id})
        self.assertEqual(self.store.list_raw_embeddings_for_person(self.d.person_id)[0].embedding_id, embedding.embedding_id)
        self.assertEqual(self.store.list_person_encounter_media(self.d.person_id), [])
        self.assertEqual(len(self.store.query_encounters()['events']), 1)
        self.assertTrue(self.store.validate_graph_projection()['valid'])

    def test_new_person_attachment_is_nonauthoritative_until_completion(self):
        rid = self.amendment([self.a])
        face = self.store.get_encounter_review(rid)['faces'][0]
        self.store.set_photo_review_face_decision(rid, face['face_id'], 'ACCEPT_NEW_PERSON', new_person_key='new-key', new_person_name='New Person')
        review = self.store.complete_encounter_identity_review(rid)
        self.assertEqual(len(self.store.list_persons()), 4)
        for pair in review['relation_candidates']:
            self.store.set_encounter_relation_decision(rid, pair['first_ref'], pair['second_ref'], 'INCLUDE')
        result = self.store.complete_photo_review(rid, 'new-person-attachment')
        self.assertEqual(result['observation_id'], self.oid)
        self.assertEqual(len(self.store.list_persons()), 5)
        self.assertEqual(len(self.store.get_encounter_read(self.oid)['participant_ids']), 3)
        self.assertEqual(len(self.evidence()), 3)
        self.assertEqual(ReadOnlyIntegrityChecker(self.store.db_path).run().findings, ())

    def test_world_reads_current_metadata_and_participation(self):
        self.correct('world-metadata', event_details={'place_seen': 'Agra'})
        self.correct('world-removal', participant_correction={'action': 'REMOVE', 'person_id': self.b.person_id})
        world = self.store.get_world_graph_v2_read(WorldGraphRequest(detail_level=WorldDetailLevel.EVENT, focus_type='EVENT', focus_id=self.oid))
        self.assertEqual(world.events[0].location, 'Agra')
        self.assertEqual({p['person_id'] for p in world.events[0].participants}, {self.a.person_id})
