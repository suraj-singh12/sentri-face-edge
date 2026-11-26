"""Process-local *candidate corrections* discovered by the differential runs.

They are installed only in experiment processes to test whether the smallest
safe production change would close a measured discrepancy. Nothing here edits
``src/``.

R1  Person activity / management events (``_list_person_operations``) list
    every COMMITTED or REVERTED journal entry naming the Person. After an
    erasure, X's ``encounter.correct`` / legacy observation operations stay in
    the journal (immutable) and keep appearing in Alder's/Hazel's profile.
    Candidate fix: hide operations whose REVERTED transition was written by an
    ``event.erase`` operation.

R2  Recognition proposals already staged before the deletion (Check a Photo /
    pending additions) still rank erased Persons/samples. Candidate fix:
    recompute those staged proposals against the rebuilt index.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from sentriface.storage import sqlite_store

_STATE = {"installed": False}


def install() -> None:
    if _STATE["installed"]:
        return
    original = sqlite_store.SQLiteIdentityStore._list_person_operations

    def list_person_operations(self, conn, person_id, *, canonical_person_id):
        operations = original(self, conn, person_id, canonical_person_id=canonical_person_id)
        erased = {row[0] for row in conn.execute(
            "SELECT operation_id FROM operation_journal_status_history WHERE to_status = 'REVERTED' "
            "AND json_extract(details, '$.reason') = 'event.erase'")}
        return [op for op in operations if op.get("operation_id") not in erased]

    sqlite_store.SQLiteIdentityStore._list_person_operations = list_person_operations
    _STATE["installed"] = True


def refresh_stale_proposals(engine, erased_person_ids, erased_embedding_ids) -> list[str]:
    """R2: recompute staged pending-addition proposals that rank erased identities."""
    erased_people, erased_samples = set(erased_person_ids), set(erased_embedding_ids)
    refreshed = []
    with engine.store._connect() as conn:
        rows = conn.execute("SELECT pending_id, matches FROM pending_additions").fetchall()
    for pending_id, matches in rows:
        stale = [m for m in json.loads(matches or "[]")
                 if m.get("person_id") in erased_people or erased_samples & set(m.get("embedding_ids") or [])]
        if not stale:
            continue
        pending = next(p for p in engine.store.list_pending_additions() if p.pending_id == pending_id)
        fresh = engine._search_unique_people(pending.vector, quality_only=True)
        # Same serialization as SQLiteIdentityStore.save_pending_addition.
        encoded = json.dumps([{"person_id": m.person_id, "score": m.score, "embedding_ids": list(m.embedding_ids),
                               "embeddings_matched": m.embeddings_matched} for m in fresh])
        decision = engine._decide(fresh)
        with engine.store._connect() as conn:
            conn.execute("UPDATE pending_additions SET matches = ?, decision = ? WHERE pending_id = ?",
                         (encoded, getattr(decision, "value", decision), pending_id))
        refreshed.append(pending_id)
    return refreshed
