from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sentriface.components.linear_index import LinearFaceIndex
from sentriface.engine import FaceEngine
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class RecognitionLifecycleFilterTest(unittest.TestCase):
    def _engine_with_index(self, root: Path):
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        engine = object.__new__(FaceEngine)
        engine.store = store
        engine.index = LinearFaceIndex()
        engine.config = SimpleNamespace(top_k=3)
        return engine, store

    def test_stale_index_match_is_suppressed_after_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine, store = self._engine_with_index(Path(temp))
            person = store.create_person("Archived")
            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)
            engine.index.rebuild([embedding])

            store.archive_person(person.person_id, "archive-without-index-rebuild")

            self.assertEqual(engine._search_unique_people((1.0, 0.0)), [])

    def test_stale_index_embedding_is_remapped_to_current_active_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine, store = self._engine_with_index(Path(temp))
            previous = store.create_person("Previous")
            current = store.create_person("Current")
            embedding = store.add_embedding(previous.person_id, (1.0, 0.0), 0.9)
            engine.index.rebuild([embedding])
            with store._connect() as conn:
                conn.execute(
                    "UPDATE embeddings SET person_id = ? WHERE embedding_id = ?",
                    (current.person_id, embedding.embedding_id),
                )

            matches = engine._search_unique_people((1.0, 0.0))

            self.assertEqual([match.person_id for match in matches], [current.person_id])
            self.assertNotEqual(matches[0].person_id, previous.person_id)


if __name__ == "__main__":
    unittest.main()
