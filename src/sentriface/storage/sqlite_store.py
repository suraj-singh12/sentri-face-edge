from __future__ import annotations

import json
import sqlite3
import struct
import uuid
from pathlib import Path

from sentriface.models import (
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    FaceBox,
    Match,
    MatchDecision,
    PendingAddition,
    Person,
    utc_now,
)

SCHEMA_VERSION = 1


class SQLiteIdentityStore:
    def __init__(self, db_path: Path, embedding_dim: int = 512) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than this app supports "
                    f"({SCHEMA_VERSION}). Please update SentriFace."
                )
            if version == 0:
                _migrate_0_to_1(conn)
                version = 1
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported database schema version: {version}")

    def create_person(self, name: str, metadata: dict | None = None) -> Person:
        person = Person(
            person_id=str(uuid.uuid4()),
            name=name,
            metadata=metadata or {},
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persons(person_id, name, metadata, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    person.person_id,
                    person.name,
                    json.dumps(person.metadata, separators=(",", ":")),
                    person.created_at,
                ),
            )
        return person

    def get_person(self, person_id: str) -> Person | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT person_id, name, metadata, created_at
                FROM persons
                WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return Person(
            person_id=row["person_id"],
            name=row["name"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
        )

    def add_embedding(
        self,
        person_id: str,
        vector: Embedding,
        quality_score: float,
        source_image: str | None = None,
        crop_path: str | None = None,
    ) -> EmbeddingRecord:
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Expected {self.embedding_dim} dimensions, got {len(vector)}")
        record = EmbeddingRecord(
            embedding_id=str(uuid.uuid4()),
            person_id=person_id,
            vector=tuple(vector),
            quality_score=quality_score,
            source_image=source_image,
            crop_path=crop_path,
            created_at=utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings(
                    embedding_id, person_id, vector, quality_score,
                    source_image, crop_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.embedding_id,
                    record.person_id,
                    _pack_embedding(record.vector),
                    record.quality_score,
                    record.source_image,
                    record.crop_path,
                    record.created_at,
                ),
            )
        return record

    def list_embeddings(self) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT embedding_id, person_id, vector, quality_score,
                       source_image, crop_path, created_at
                FROM embeddings
                """
            ).fetchall()
        return [
            EmbeddingRecord(
                embedding_id=row["embedding_id"],
                person_id=row["person_id"],
                vector=_unpack_embedding(row["vector"]),
                quality_score=row["quality_score"],
                source_image=row["source_image"],
                crop_path=row["crop_path"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_pending_addition(self, pending: PendingAddition) -> None:
        if len(pending.vector) != self.embedding_dim:
            raise ValueError(f"Expected {self.embedding_dim} dimensions, got {len(pending.vector)}")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_additions(
                    pending_id, source_image, box_x, box_y, box_width, box_height,
                    box_confidence, quality_score, landmarks, crop_path, vector,
                    matches, decision, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending.pending_id,
                    pending.source_image,
                    pending.face.box.x,
                    pending.face.box.y,
                    pending.face.box.width,
                    pending.face.box.height,
                    pending.face.box.confidence,
                    pending.face.quality_score,
                    json.dumps(pending.face.landmarks),
                    pending.face.crop_path,
                    _pack_embedding(pending.vector),
                    json.dumps([match.__dict__ for match in pending.matches]),
                    pending.decision.value,
                    pending.created_at,
                ),
            )

    def get_pending_addition(self, pending_id: str) -> PendingAddition | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pending_id, source_image, box_x, box_y, box_width, box_height,
                       box_confidence, quality_score, landmarks, crop_path, vector,
                       matches, decision, created_at
                FROM pending_additions
                WHERE pending_id = ?
                """,
                (pending_id,),
            ).fetchone()
        return _pending_from_row(row) if row else None

    def list_pending_additions(self) -> list[PendingAddition]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT pending_id, source_image, box_x, box_y, box_width, box_height,
                       box_confidence, quality_score, landmarks, crop_path, vector,
                       matches, decision, created_at
                FROM pending_additions
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_pending_from_row(row) for row in rows]

    def delete_pending_addition(self, pending_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _pack_embedding(vector: Embedding) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_embedding(payload: bytes) -> Embedding:
    count = len(payload) // 4
    return struct.unpack(f"{count}f", payload)


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            vector BLOB NOT NULL,
            quality_score REAL NOT NULL,
            source_image TEXT,
            crop_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_embeddings_person
        ON embeddings(person_id);

        CREATE TABLE IF NOT EXISTS pending_additions (
            pending_id TEXT PRIMARY KEY,
            source_image TEXT NOT NULL,
            box_x INTEGER NOT NULL,
            box_y INTEGER NOT NULL,
            box_width INTEGER NOT NULL,
            box_height INTEGER NOT NULL,
            box_confidence REAL NOT NULL,
            quality_score REAL NOT NULL,
            landmarks TEXT,
            crop_path TEXT,
            vector BLOB NOT NULL,
            matches TEXT NOT NULL,
            decision TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        PRAGMA user_version = 1;
        """
    )


def _pending_from_row(row: sqlite3.Row) -> PendingAddition:
    raw_landmarks = json.loads(row["landmarks"]) if row["landmarks"] else None
    landmarks = tuple(tuple(point) for point in raw_landmarks) if raw_landmarks else None
    matches = [
        Match(
            person_id=item["person_id"],
            score=item["score"],
            embedding_id=item["embedding_id"],
        )
        for item in json.loads(row["matches"])
    ]
    return PendingAddition(
        pending_id=row["pending_id"],
        source_image=row["source_image"],
        face=DetectedFace(
            box=FaceBox(
                x=row["box_x"],
                y=row["box_y"],
                width=row["box_width"],
                height=row["box_height"],
                confidence=row["box_confidence"],
            ),
            quality_score=row["quality_score"],
            landmarks=landmarks,
            crop_path=row["crop_path"],
        ),
        vector=_unpack_embedding(row["vector"]),
        matches=matches,
        decision=MatchDecision(row["decision"]),
        created_at=row["created_at"],
    )
