from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
from typing import Iterator


@dataclass(frozen=True)
class MediaReferenceSpec:
    """One schema-owned durable media reference.

    Registry entries are code authority. Backup manifests may name only the
    stable ``registry_id`` and row identity emitted from these entries; they
    never provide a table, column, or SQL fragment used for mutation.
    """

    table: str
    identity_columns: tuple[str, ...]
    path_column: str
    media_class: str
    rewrite_behavior: str = "RELOCATE"
    protected_media: bool = True

    @property
    def registry_id(self) -> str:
        return f"{self.table}.{self.path_column}"


MEDIA_AUTHORITY_REGISTRY: tuple[MediaReferenceSpec, ...] = (
    MediaReferenceSpec("embeddings", ("embedding_id",), "source_image", "FACE_SOURCE"),
    MediaReferenceSpec("embeddings", ("embedding_id",), "crop_path", "FACE_CROP"),
    MediaReferenceSpec("pending_additions", ("pending_id",), "source_image", "ENROLLMENT_SOURCE"),
    MediaReferenceSpec("pending_additions", ("pending_id",), "crop_path", "ENROLLMENT_CROP"),
    MediaReferenceSpec("init_faces", ("init_face_id",), "source_image", "INITIALIZATION_SOURCE"),
    MediaReferenceSpec("init_faces", ("init_face_id",), "crop_path", "INITIALIZATION_CROP"),
    MediaReferenceSpec("recognition_details", ("detail_id",), "image_path", "HISTORICAL_RECOGNITION"),
    MediaReferenceSpec(
        "observation_media",
        ("observation_id", "media_id"),
        "media_path",
        "OBSERVATION_MEDIA",
    ),
    MediaReferenceSpec("photo_reviews", ("review_id",), "media_path", "PHOTO_REVIEW_MEDIA"),
    MediaReferenceSpec("init_session_media", ("session_id", "media_id"), "media_path", "INITIALIZATION_SOURCE"),
    MediaReferenceSpec("photo_review_media", ("review_id", "media_id"), "media_path", "PHOTO_REVIEW_MEDIA"),
)

MEDIA_REGISTRY_BY_ID = {item.registry_id: item for item in MEDIA_AUTHORITY_REGISTRY}


def media_content_identity(path: str | Path) -> str:
    """Identify the retained media bytes; managed object names encode plaintext digest."""
    media_path = Path(path)
    stem = media_path.stem.lower()
    if (
        media_path.parent.name == "objects"
        and media_path.parent.parent.name == "uploads"
        and len(stem) == 64
        and all(character in "0123456789abcdef" for character in stem)
    ):
        return stem
    if media_path.is_file():
        digest = hashlib.sha256()
        with media_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    # Historical fixture paths can lack a local file; retain stable path identity.
    return hashlib.sha256(str(media_path).encode("utf-8")).hexdigest()


def available_media_specs(conn: sqlite3.Connection) -> tuple[MediaReferenceSpec, ...]:
    """Return only registry entries present in this historical schema."""
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    available: list[MediaReferenceSpec] = []
    for spec in MEDIA_AUTHORITY_REGISTRY:
        if spec.table not in tables:
            continue
        columns = {
            str(row[1])
            for row in conn.execute(f'PRAGMA table_info("{spec.table}")').fetchall()
        }
        if spec.path_column in columns and set(spec.identity_columns) <= columns:
            available.append(spec)
    return tuple(available)


def iter_media_references(
    conn: sqlite3.Connection,
) -> Iterator[tuple[MediaReferenceSpec, tuple[str, ...], str]]:
    """Enumerate durable references from one completed database snapshot."""
    for spec in available_media_specs(conn):
        selected = ", ".join(
            [*(f'"{column}"' for column in spec.identity_columns), f'"{spec.path_column}"']
        )
        order = ", ".join(f'"{column}"' for column in spec.identity_columns)
        rows = conn.execute(
            f'SELECT {selected} FROM "{spec.table}" '
            f'WHERE "{spec.path_column}" IS NOT NULL '
            f'AND TRIM("{spec.path_column}") != \'\' ORDER BY {order}'
        ).fetchall()
        for row in rows:
            identity = tuple(str(row[index]) for index in range(len(spec.identity_columns)))
            yield spec, identity, str(row[len(spec.identity_columns)])


def stable_identity(spec: MediaReferenceSpec, values: tuple[str, ...]) -> dict[str, str]:
    if len(values) != len(spec.identity_columns):
        raise ValueError("Media reference identity has the wrong shape")
    return dict(zip(spec.identity_columns, values, strict=True))


def identity_values(spec: MediaReferenceSpec, identity: object) -> tuple[str, ...]:
    if not isinstance(identity, dict) or set(identity) != set(spec.identity_columns):
        raise ValueError("Media reference identity is malformed")
    values = tuple(str(identity[column]).strip() for column in spec.identity_columns)
    if any(not value or len(value) > 1024 for value in values):
        raise ValueError("Media reference identity is invalid")
    return values


def update_media_reference(
    conn: sqlite3.Connection,
    spec: MediaReferenceSpec,
    identity: tuple[str, ...],
    restored_path: str,
) -> None:
    """Apply one registry-approved path rewrite to one stable row."""
    if spec.rewrite_behavior != "RELOCATE":
        raise ValueError("Unsupported media rewrite behavior")
    where = " AND ".join(f'"{column}" = ?' for column in spec.identity_columns)
    cursor = conn.execute(
        f'UPDATE "{spec.table}" SET "{spec.path_column}" = ? WHERE {where}',
        (restored_path, *identity),
    )
    if cursor.rowcount != 1:
        raise KeyError(f"Media reference row is missing: {spec.registry_id}")
