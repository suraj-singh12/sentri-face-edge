from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.engine import FaceEngine
from sentriface.contracts import IdentityStore
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class DomainWorkflowGateTest(unittest.TestCase):
    def test_public_canonical_mapping_is_gated_until_p8(self) -> None:
        engine = object.__new__(FaceEngine)

        with self.assertRaisesRegex(RuntimeError, "temporarily unavailable.*P8"):
            engine.set_canonical_person_id("source", "target", "canonical-map")

        self.assertFalse(hasattr(IdentityStore, "set_canonical_person_id"))
        self.assertFalse(hasattr(SQLiteIdentityStore, "set_canonical_person_id"))

    def test_public_merge_and_undo_are_gated_without_mutating_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteIdentityStore(Path(temp) / "sentriface.db", embedding_dim=2)
            store.initialize()
            engine = object.__new__(FaceEngine)
            engine.store = store
            source = store.create_person("Source")
            target = store.create_person("Target")

            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable.*P8"):
                engine.merge_persons(source.person_id, target.person_id, "gated-merge")
            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable.*P8"):
                engine.undo_merge_persons("legacy-merge", "gated-undo")

            self.assertEqual(store.get_person(source.person_id).lifecycle_status, "ACTIVE")
            self.assertEqual(store.get_person(target.person_id).lifecycle_status, "ACTIVE")
            self.assertIsNone(store.get_person_operation("gated-merge", "merge-persons"))


if __name__ == "__main__":
    unittest.main()
