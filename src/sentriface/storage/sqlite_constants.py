"""Schema version, domain constants and embedding packing shared by the SQLite store modules."""
from __future__ import annotations

import sqlite3
import struct

from dataclasses import dataclass
from typing import Callable
from sentriface.models import Embedding


SCHEMA_VERSION = 37
DELETED_PERSON_RECOVERY_DAYS = 30
EMBEDDING_RECOGNITION_STATES = frozenset({"GOOD", "POOR_ACCEPTED", "PROOF_ONLY"})
DELETED_FACE_RETENTION_DAYS = 30
PERSON_LIFECYCLE_STATUSES = frozenset({"ACTIVE", "ARCHIVED", "DELETED", "MERGED"})
RESTORABLE_PERSON_LIFECYCLE_STATUSES = ("ARCHIVED", "DELETED")
PERSON_IDENTITY_STATUSES = frozenset({"IDENTIFIED", "UNIDENTIFIED"})
PERSON_BIOMETRIC_STATUSES = frozenset({"NO_FACE", "ENROLLED"})
RELATIONSHIP_EVIDENCE_TYPES = frozenset({
    "CO_OBSERVED", "NOTE_REFERENCE", "MANUAL_ASSOCIATION",
})
OPERATION_STATUSES = frozenset({"STARTED", "COMMITTED", "FAILED", "ROLLED_BACK", "REVERTED"})
OPERATION_STATUS_TRANSITIONS = {
    "STARTED": frozenset({"COMMITTED", "FAILED", "ROLLED_BACK"}),
    "FAILED": frozenset({"ROLLED_BACK"}),
    "COMMITTED": frozenset({"REVERTED"}),
    "ROLLED_BACK": frozenset(),
    "REVERTED": frozenset(),
}
REVIEW_DECISIONS = frozenset({
    "ACCEPT_EXISTING_PERSON", "ACCEPT_NEW_PERSON", "EXCLUDE", "SKIP",
})
MERGE_COLLECTION_ITEM_TYPES = frozenset({
    "EMBEDDING", "PHOTO", "OBSERVATION", "OBSERVATION_PARTICIPANT",
    "NOTE", "NOTE_MENTION", "HISTORY", "GRAPH_EVIDENCE",
})


class SchemaMigrationError(RuntimeError):
    """Raised when the database cannot be migrated safely to the current schema."""


@dataclass(frozen=True)
class SchemaMigration:
    from_version: int
    to_version: int
    apply: Callable[[sqlite3.Connection], None]
def _pack_embedding(vector: Embedding) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_embedding(payload: bytes) -> Embedding:
    count = len(payload) // 4
    return struct.unpack(f"{count}f", payload)
