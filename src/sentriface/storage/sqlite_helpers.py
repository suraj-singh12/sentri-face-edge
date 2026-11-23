"""Transaction-level helpers for reviews, notes, evidence, graph projection, Encounters, merges and people."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from dataclasses import replace
from datetime import (
    datetime,
    timezone,
)
from typing import Callable
from sentriface.errors import EncounterRelationConflict
from sentriface.models import (
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    FaceBox,
    GraphConnection,
    GraphReadEdge,
    GraphReadFilter,
    GraphReadNode,
    InitFace,
    IdentityCorrection,
    MatchDecision,
    MergeAffectedAction,
    MergeAffectedItem,
    MergeConflictResolution,
    MergeConflictStrategy,
    MergeOperation,
    Note,
    Observation,
    ObservationMedia,
    ObservationParticipant,
    PendingAddition,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PresenceAnalytics,
    QualityReport,
    QualityStatus,
    PhotoReview,
    ReviewFaceDecision,
    RecognitionDetail,
    RelationshipEvidence,
    RelationshipAnalytics,
    Sighting,
    TemporalCount,
    LocationCount,
    utc_now,
)
from sentriface.media_registry import (
    media_content_identity,
    require_existing_media,
)
from sentriface.storage.sqlite_constants import (
    EMBEDDING_RECOGNITION_STATES,
    PERSON_LIFECYCLE_STATUSES,
    OPERATION_STATUSES,
    OPERATION_STATUS_TRANSITIONS,
    MERGE_COLLECTION_ITEM_TYPES,
    _unpack_embedding,
)


def _encounter_draft_references(conn, review_id: str) -> list[dict]:
    review = conn.execute("SELECT status, review_phase FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
    if review is None or review["status"] != "IN_PROGRESS" or review["review_phase"] not in {"IDENTITIES", "RELATIONS"}:
        return []
    rows = conn.execute(
        "SELECT f.*, i.vector, i.quality_status, i.crop_path, i.source_image FROM photo_review_faces f "
        "JOIN init_faces i ON i.init_face_id = f.staged_face_id WHERE f.review_id = ? "
        "AND f.staged_face_type = 'INIT_FACE' AND f.decision IN ('ACCEPT_NEW_PERSON', 'ACCEPT_EXISTING_PERSON')",
        (review_id,),
    ).fetchall()
    result = []
    for row in rows:
        draft_created = row["decision"] == "ACCEPT_NEW_PERSON"
        person_id = None if draft_created else _resolve_canonical_person_id(conn, row["person_id"])
        person = None if draft_created else conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
        if not draft_created and (person is None or person["lifecycle_status"] != "ACTIVE" or person["deleted_at"]):
            continue
        result.append({
            "face_id": str(row["face_id"]), "key": str(row["new_person_key"] or row["face_id"]) if draft_created else person_id,
            "person_id": person_id, "draft_created": draft_created,
            "name": str(row["new_person_name"] or "New Person") if draft_created else str(person["name"]),
            "metadata": json.loads((row["new_person_metadata"] if draft_created else person["metadata"]) or "{}"),
            "vector": _unpack_embedding(row["vector"]),
            "recognition_state": _review_face_recognition_state(row, json.loads(row["recognition_detail"] or "{}")),
            "image": str(row["crop_path"] or row["source_image"]),
        })
    return result


def _proof_only_duplicate_matches(
    conn: sqlite3.Connection, incoming_vectors: list[Embedding], threshold: float,
    *, review_id: str | None = None, excluded_draft_key: str | None = None,
) -> list[dict]:
    """Exceptional duplicate hint, isolated from ordinary index/search eligibility."""
    if not incoming_vectors:
        return []
    references = _encounter_draft_references(conn, review_id) if review_id else []
    for record in _list_embeddings_in_transaction(conn):
        person = conn.execute("SELECT name, metadata FROM persons WHERE person_id = ?", (record.person_id,)).fetchone()
        references.append({"key": record.person_id, "person_id": record.person_id, "draft_created": False,
                           "name": person["name"], "metadata": json.loads(person["metadata"] or "{}"),
                           "vector": record.vector, "recognition_state": record.recognition_state,
                           "image": record.crop_path or record.source_image})
    by_person = {}
    for reference in references:
        by_person.setdefault((reference["draft_created"], reference["key"]), []).append(reference)
    candidates = []
    for (draft_created, key), samples in by_person.items():
        if draft_created and key == excluded_draft_key:
            continue
        if {sample["recognition_state"] for sample in samples} != {"PROOF_ONLY"}:
            continue
        best = max(samples, key=lambda sample: max(sum(a * b for a, b in zip(vector, sample["vector"])) for vector in incoming_vectors))
        score = max(sum(a * b for a, b in zip(vector, best["vector"])) for vector in incoming_vectors)
        if score >= threshold:
            candidates.append({"person_id": f"draft:{key}" if draft_created else key,
                               "draft_person_key": key if draft_created else None, "draft_created": draft_created,
                               "name": best["name"], "metadata": best["metadata"], "representative_image": best["image"],
                               "score": score, "basis": "PROOF_ONLY_DUPLICATE_CHECK"})
    return sorted(candidates, key=lambda item: (-item["score"], item["person_id"]))[:5]


def _insert_identified_person_record(
    conn: sqlite3.Connection,
    *,
    person_id: str,
    name: str,
    metadata: dict,
    enrollment_status: str,
) -> Person:
    normalized_name = str(name).strip()
    normalized_metadata = dict(metadata or {})
    if not _has_meaningful_identity_context(normalized_name, normalized_metadata, ""):
        raise ValueError("A person without a face requires meaningful identity or context")
    created_at = utc_now()
    person = Person(
        person_id=person_id,
        name=normalized_name,
        metadata=normalized_metadata,
        created_at=created_at,
        enrollment_status=enrollment_status,
        lifecycle_status="ACTIVE",
        identity_status="IDENTIFIED",
        biometric_status="NO_FACE",
    )
    conn.execute(
        """
        INSERT INTO persons(
            person_id, name, metadata, created_at, enrollment_status, notes,
            lifecycle_status, identity_status, biometric_status, lifecycle_changed_at
        ) VALUES (?, ?, ?, ?, ?, '', 'ACTIVE', 'IDENTIFIED', 'NO_FACE', ?)
        """,
        (
            person.person_id,
            person.name,
            json.dumps(person.metadata, separators=(",", ":")),
            person.created_at,
            person.enrollment_status,
            person.created_at,
        ),
    )
    return person


def _create_placeholder_record(
    conn: sqlite3.Connection,
    name: str,
    metadata: dict | None,
    editor_name: str,
    notes: str = "",
) -> Person:
    duplicate = conn.execute(
        """
        SELECT 1 FROM persons
        WHERE enrollment_status = 'placeholder'
          AND lifecycle_status <> 'DELETED'
          AND lower(trim(name)) = lower(trim(?))
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    if duplicate is not None:
        raise _placeholder_name_conflict(
            sqlite3.IntegrityError("duplicate placeholder name")
        )
    placeholder_metadata = dict(metadata or {})
    placeholder_metadata["tags"] = _normalize_tags(
        placeholder_metadata.get("tags", [])
    )
    person = Person(
        person_id=str(uuid.uuid4()),
        name=name,
        metadata=placeholder_metadata,
        enrollment_status="placeholder",
        notes=notes.strip(),
    )
    try:
        conn.execute(
            """
            INSERT INTO persons(
                person_id, name, metadata, created_at, enrollment_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                person.person_id,
                person.name,
                json.dumps(person.metadata, separators=(",", ":")),
                person.created_at,
                person.enrollment_status,
                person.notes,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "placeholder" in str(exc).lower() or "persons.name" in str(exc).lower():
            raise _placeholder_name_conflict(exc) from exc
        raise
    _insert_person_change(
        conn,
        PersonChange(
            change_id=str(uuid.uuid4()),
            person_id=person.person_id,
            previous_name="",
            new_name=person.name,
            previous_rank="",
            new_rank=str(person.metadata.get("rank") or ""),
            previous_country="",
            new_country=str(person.metadata.get("country") or ""),
            previous_importance="",
            new_importance=str(person.metadata.get("importance") or ""),
            previous_status=None,
            new_status="placeholder",
            previous_notes="",
            new_notes=person.notes,
            editor_name=editor_name,
            created_at=person.created_at,
        ),
    )
    _insert_unjournaled_profile_note(
        conn, person.person_id, person.notes, person.created_at,
    )
    return person


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_staged_review_face(
    conn: sqlite3.Connection, staged_type: str, staged_id: str,
) -> None:
    _staged_review_face_row(conn, staged_type, staged_id)


def _staged_review_face_row(
    conn: sqlite3.Connection, staged_type: str, staged_id: str,
) -> sqlite3.Row:
    normalized_type = str(staged_type).strip().upper()
    normalized_id = str(staged_id).strip()
    if normalized_type == "PENDING_ADDITION":
        row = conn.execute(
            """
            SELECT pending_id AS staged_face_id, vector, quality_score,
                   source_image, crop_path, quality_status
            FROM pending_additions WHERE pending_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    elif normalized_type == "INIT_FACE":
        row = conn.execute(
            """
            SELECT init_face_id AS staged_face_id, vector, quality_score,
                   source_image, crop_path, quality_status
            FROM init_faces WHERE init_face_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    else:
        raise ValueError(f"Unsupported staged face type: {staged_type}")
    if row is None:
        raise KeyError(f"Unknown staged review face: {normalized_id}")
    return row


def _review_face_recognition_state(staged: sqlite3.Row, detail: dict) -> str:
    if str(staged["quality_status"]).lower() != "bad":
        return "GOOD"
    state = str(detail.get("embedding_state") or "PROOF_ONLY").upper()
    if state not in EMBEDDING_RECOGNITION_STATES - {"GOOD"}:
        raise ValueError("Poor-quality review face requires accepted or proof-only state")
    return state


def _require_active_review_person(
    conn: sqlite3.Connection, person_id: object | None,
) -> str:
    normalized_id = str(person_id or "").strip()
    row = conn.execute(
        """
        SELECT 1 FROM persons
        WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
        """,
        (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown active person: {normalized_id}")
    return normalized_id


def _reference_records(conn: sqlite3.Connection, person_id: str | None = None) -> list[dict]:
    records = []
    canonical = _resolve_canonical_person_id(conn, person_id) if person_id else None
    for row in conn.execute("""SELECT h.*, COALESCE((SELECT active FROM recognition_reference_revisions v
        WHERE v.enrollment_id = h.enrollment_id ORDER BY v.created_at DESC, v.rowid DESC LIMIT 1), 1) AS active
        FROM biometric_enrollment_history h ORDER BY h.created_at, h.enrollment_id""").fetchall():
        owner = _resolve_canonical_person_id(conn, row["person_id"])
        if canonical is not None and owner != canonical:
            continue
        records.append({**dict(row), "reference_id": row["enrollment_id"], "canonical_person_id": owner,
                        "media_id": row["source_media_id"], "active": bool(row["active"]),
                        "origin": "STANDALONE_ENROLLMENT"})
    return records


def _active_reference_count(conn: sqlite3.Connection, person_id: str) -> int:
    return len({r["media_id"] or r["reference_id"] for r in _reference_records(conn, person_id) if r["active"]})


def _require_reference_mutation_person(conn: sqlite3.Connection, person_id: str) -> None:
    row = conn.execute("SELECT lifecycle_status FROM persons WHERE person_id = ?", (person_id,)).fetchone()
    if row is None or row[0] != "ACTIVE":
        raise ValueError("Restore the active canonical Person before managing References")


def _require_reference_media_role(conn: sqlite3.Connection, media_id: str, person_id: str, key: bytes | None = None) -> None:
    if conn.execute("SELECT 1 FROM observation_media WHERE media_id = ?", (media_id,)).fetchone():
        raise ValueError("Encounter media cannot become Reference Only; use its Encounter-derived sample")
    # Legacy single-photo review APIs used a name/opaque media ID. Exact role
    # protection also compares their authenticated source bytes after relocation.
    for row in conn.execute("SELECT media_id, media_path FROM observation_media WHERE media_path IS NOT NULL"):
        identity = str(row["media_id"])
        if len(identity) == 64 and all(c in "0123456789abcdef" for c in identity):
            continue
        if media_content_identity(row["media_path"], key) == media_id:
            raise ValueError("Encounter media cannot become Reference Only; use its Encounter-derived sample")
    for reference in _reference_records(conn):
        if reference["media_id"] == media_id and reference["canonical_person_id"] != person_id:
            raise ValueError("This Reference Only image already belongs to another Person")


def _require_encounter_media_role(conn: sqlite3.Connection, media_id: str) -> None:
    if conn.execute("SELECT 1 FROM biometric_enrollment_history WHERE source_media_id = ?", (media_id,)).fetchone():
        raise ValueError("This image is Reference Only biometric material; upload the original occurrence/scene photograph")


def _source_sample_authority(conn: sqlite3.Connection) -> dict[str, dict]:
    """Derive one sample's eligible source identities; never rewrite its sources."""
    sources: dict[str, list[tuple[str, str]]] = {}
    known: set[str] = set()
    for reference in _reference_records(conn):
        eid = reference["embedding_id"]
        known.add(eid)
        if reference["active"]:
            sources.setdefault(eid, []).append((reference["canonical_person_id"], reference["recognition_state"]))
    for observation in conn.execute("SELECT observation_id FROM observations WHERE status = 'FINALIZED'").fetchall():
        oid = observation[0]
        participants = set(_effective_observation_person_ids(conn, oid))
        for assignment in _effective_face_assignments(conn, oid):
            eid = assignment["embedding_id"]
            known.add(eid)
            owner = _resolve_canonical_person_id(conn, assignment["current_person_id"])
            if owner not in participants:
                continue
            row = conn.execute("""SELECT e.recognition_state, f.recognition_detail FROM embeddings e
                JOIN observation_face_assignments a ON a.embedding_id=e.embedding_id
                JOIN photo_review_faces f ON f.review_id=a.review_id AND f.face_id=a.face_id
                WHERE a.assignment_id=?""", (assignment["assignment_id"],)).fetchone()
            if row is None:
                row = conn.execute("SELECT recognition_state FROM embeddings WHERE embedding_id=?", (eid,)).fetchone()
                state = row[0]
            else:
                state = json.loads(row["recognition_detail"] or "{}").get("source_recognition_state", row["recognition_state"])
            sources.setdefault(eid, []).append((owner, state))
    result = {}
    for embedding in conn.execute("SELECT embedding_id, person_id, recognition_state FROM embeddings").fetchall():
        eid = embedding["embedding_id"]
        entries = sources.get(eid, [])
        if eid not in known:
            entries = [(_effective_embedding_owner_person_id(conn, embedding), embedding["recognition_state"])]
        owners = {owner for owner, _ in entries}
        state = next((s for s in ("GOOD", "POOR_ACCEPTED", "PROOF_ONLY") if any(v == s for _, v in entries)), "PROOF_ONLY")
        result[eid] = {"owners": owners, "conflict": len(owners) > 1,
                       "owner": next(iter(owners)) if len(owners) == 1 else None, "state": state}
    return result


def _eligible_source_samples(conn: sqlite3.Connection) -> list[EmbeddingRecord]:
    authority = _source_sample_authority(conn)
    result, seen = [], {}
    for row in conn.execute("SELECT * FROM embeddings WHERE deleted_at IS NULL ORDER BY created_at, embedding_id").fetchall():
        sample = authority[row["embedding_id"]]
        owner = sample["owner"]
        if owner is None:
            continue
        person = conn.execute("SELECT lifecycle_status FROM persons WHERE person_id = ?", (owner,)).fetchone()
        if person is None or person[0] != "ACTIVE":
            continue
        key = (owner, row["vector"])
        if key in seen:
            index = seen[key]
            rank = {"GOOD": 0, "POOR_ACCEPTED": 1, "PROOF_ONLY": 2}
            if rank[sample["state"]] < rank[result[index].recognition_state]:
                result[index] = replace(result[index], recognition_state=sample["state"])
            continue
        seen[key] = len(result)
        record = _embedding_from_row(row, raw_person_id=_raw_embedding_owner_person_id(conn, row), canonical_person_id=owner)
        result.append(replace(record, person_id=owner, recognition_state=sample["state"]))
    return result


def _refresh_source_biometric_status(conn: sqlite3.Connection) -> None:
    eligible = {r.person_id for r in _eligible_source_samples(conn) if r.recognition_state != "PROOF_ONLY"}
    for person in conn.execute("SELECT person_id, lifecycle_status FROM persons").fetchall():
        if person["lifecycle_status"] == "ACTIVE":
            enrolled = person["person_id"] in eligible
            conn.execute("UPDATE persons SET biometric_status = ?, enrollment_status = ? WHERE person_id = ?",
                         ("ENROLLED" if enrolled else "NO_FACE", "enrolled" if enrolled else "placeholder", person["person_id"]))


def _reference_integrity_errors(conn: sqlite3.Connection) -> list[str]:
    errors = [str(row[0]) for row in conn.execute("""SELECT h.enrollment_id FROM biometric_enrollment_history h
        JOIN embeddings e ON e.embedding_id=h.embedding_id JOIN photo_reviews r ON r.review_id=h.review_id
        WHERE h.recognition_state NOT IN ('GOOD','POOR_ACCEPTED','PROOF_ONLY')
        OR (h.no_context_declared=1 AND (h.source_image IS NULL OR h.source_media_id IS NULL
            OR length(h.source_media_id)<>64 OR h.source_media_id GLOB '*[^0-9a-f]*'
            OR r.source<>'reference-only' OR r.status<>'COMPLETED' OR r.observation_id IS NOT NULL))""").fetchall()]
    errors.extend(str(row[0]) for row in conn.execute("""SELECT v.enrollment_id
        FROM recognition_reference_revisions v JOIN operation_journal j ON j.operation_id=v.operation_id
        WHERE j.status<>'COMMITTED' OR j.operation_type<>'identity.reference.lifecycle'""").fetchall())
    return sorted(set(errors))


def _attachment_ownership_errors(conn: sqlite3.Connection) -> list[str]:
    """Shared live/migration/restore integrity contract for existing scan drafts."""
    return [str(row[0]) for row in conn.execute("""
        SELECT s.session_id FROM init_sessions s
        LEFT JOIN observations o ON o.observation_id = s.target_observation_id
        WHERE s.target_observation_id IS NOT NULL AND (
            o.status IS NOT 'FINALIZED' OR trim(coalesce(s.expected_encounter_revision, '')) = ''
            OR EXISTS (SELECT 1 FROM photo_reviews r WHERE r.session_id = s.session_id
                       AND r.target_observation_id IS NOT s.target_observation_id))
        ORDER BY s.session_id
    """)]


def _photo_review_from_conn(conn: sqlite3.Connection, review_id: str) -> PhotoReview:
    row = conn.execute(
        "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown photo review: {review_id}")
    face_rows = conn.execute(
        "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
        (review_id,),
    ).fetchall()
    faces = tuple(
        ReviewFaceDecision(
            review_id=str(item["review_id"]),
            face_id=str(item["face_id"]),
            staged_face_type=str(item["staged_face_type"]),
            staged_face_id=str(item["staged_face_id"]),
            decision=item["decision"],
            person_id=item["person_id"],
            new_person_key=item["new_person_key"],
            new_person_name=item["new_person_name"],
            new_person_metadata=json.loads(item["new_person_metadata"] or "{}"),
            notes=str(item["notes"] or ""),
            mentioned_person_ids=tuple(json.loads(item["mentioned_person_ids"] or "[]")),
            recognition_detail=json.loads(item["recognition_detail"] or "{}"),
        )
        for item in face_rows
    )
    return PhotoReview(
        review_id=str(row["review_id"]),
        media_id=str(row["media_id"]),
        media_path=row["media_path"],
        source=str(row["source"]),
        status=str(row["status"]),
        faces=faces,
        created_at=str(row["created_at"]),
        observation_id=row["observation_id"],
        completed_operation_id=row["completed_operation_id"],
        completed_at=row["completed_at"],
    )


def _review_identity_ref(conn: sqlite3.Connection, row: sqlite3.Row) -> str | None:
    if row["decision"] == "ACCEPT_EXISTING_PERSON":
        return f"person:{_resolve_canonical_person_id(conn, str(row['person_id']))}"
    if row["decision"] == "ACCEPT_NEW_PERSON":
        return f"draft:{str(row['new_person_key'] or row['face_id'])}"
    return None


def _remove_review_staging(conn: sqlite3.Connection, review_id: str) -> None:
    rows = conn.execute(
        "SELECT staged_face_type, staged_face_id FROM photo_review_faces WHERE review_id = ?",
        (review_id,),
    ).fetchall()
    conn.executemany(
        "DELETE FROM pending_additions WHERE pending_id = ?",
        [(row["staged_face_id"],) for row in rows if row["staged_face_type"] == "PENDING_ADDITION"],
    )
    conn.executemany(
        "DELETE FROM init_faces WHERE init_face_id = ?",
        [(row["staged_face_id"],) for row in rows if row["staged_face_type"] == "INIT_FACE"],
    )


def _create_review_person_note(
    conn: sqlite3.Connection,
    owner_person_id: str,
    content: str,
    mentioned_person_ids: list[str],
    operation_id: str,
    actor: dict | None,
    source: str,
    *,
    subject_type: str = "PERSON",
    subject_id: str | None = None,
) -> str:
    mentions = _normalize_note_mentions(conn, owner_person_id, mentioned_person_ids)
    note_id = str(uuid.uuid4())
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO notes(
            note_id, owner_person_id, subject_type, subject_id,
            is_profile_note, status, created_operation_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 0, 'ACTIVE', ?, ?, ?)
        """,
        (note_id, owner_person_id, subject_type, subject_id or owner_person_id, operation_id, created_at, created_at),
    )
    revision_id = _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=1,
        content=content,
        mentions=mentions,
        actor=actor,
        author_name="",
        operation_id=operation_id,
        created_at=created_at,
    )
    _sync_note_reference_evidence(
        conn,
        note_id=note_id,
        owner_person_id=owner_person_id,
        revision_id=revision_id,
        mentions=mentions,
        operation_id=operation_id,
        source=source,
        created_at=created_at,
    )
    return note_id


def _normalize_note_mentions(
    conn: sqlite3.Connection,
    owner_person_id: str,
    mentioned_person_ids: list[str] | None,
    historical_person_ids: set[str] | None = None,
) -> list[tuple[str, str]]:
    normalized_ids = sorted({
        str(person_id).strip()
        for person_id in (mentioned_person_ids or [])
        if str(person_id).strip()
    })
    mentions: list[tuple[str, str]] = []
    for person_id in normalized_ids:
        row = conn.execute(
            """
            SELECT name, lifecycle_status, deleted_at
            FROM persons WHERE person_id = ?
            """,
            (person_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown mentioned person: {person_id}")
        if person_id != owner_person_id and person_id not in (historical_person_ids or set()) and (
            row["lifecycle_status"] != "ACTIVE" or row["deleted_at"] is not None
        ):
            raise KeyError(f"Mentioned person is not active: {person_id}")
        mentions.append((person_id, str(row["name"])))
    return mentions


def _note_row(conn: sqlite3.Connection, note_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT n.*, r.revision_id, r.revision_number, r.content,
               r.actor, r.author_name, r.operation_id AS revision_operation_id,
               r.created_at AS revision_created_at
        FROM notes n
        JOIN note_revisions r ON r.note_id = n.note_id
        WHERE n.note_id = ?
          AND r.revision_number = (
              SELECT MAX(latest.revision_number)
              FROM note_revisions latest WHERE latest.note_id = n.note_id
          )
        """,
        (note_id,),
    ).fetchone()


def _note_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> Note:
    mention_rows = conn.execute(
        """
        SELECT referenced_person_id
        FROM note_revision_mentions
        WHERE revision_id = ?
        ORDER BY referenced_person_id
        """,
        (row["revision_id"],),
    ).fetchall()
    raw_mentioned_person_ids = tuple(str(item[0]) for item in mention_rows)
    effective_mentioned_person_ids = tuple(sorted({
        _resolve_canonical_person_id(conn, person_id)
        for person_id in raw_mentioned_person_ids
    }))
    return Note(
        note_id=str(row["note_id"]),
        owner_person_id=str(row["owner_person_id"]),
        status=str(row["status"]),
        content=str(row["content"]),
        revision_number=int(row["revision_number"]),
        mentioned_person_ids=raw_mentioned_person_ids,
        subject_type=str(row["subject_type"]),
        subject_id=str(row["subject_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        retired_at=row["retired_at"],
        canonical_owner_person_id=_resolve_canonical_person_id(conn, row["owner_person_id"]),
        effective_mentioned_person_ids=effective_mentioned_person_ids,
    )


def _insert_note_revision(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    revision_number: int,
    content: str,
    mentions: list[tuple[str, str]],
    actor: dict | None,
    author_name: str,
    operation_id: str | None,
    created_at: str,
) -> str:
    actor_snapshot, actor_payload, _ = _operation_actor_snapshot(actor)
    resolved_author = (
        author_name.strip()
        or str(actor_snapshot.get("display_name") or actor_snapshot.get("username") or "")
        or "SentriFace"
    )
    revision_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO note_revisions(
            revision_id, note_id, revision_number, content, actor,
            author_name, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            note_id,
            revision_number,
            content,
            actor_payload,
            resolved_author,
            operation_id,
            created_at,
        ),
    )
    conn.executemany(
        """
        INSERT INTO note_revision_mentions(
            revision_id, referenced_person_id, display_name, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (revision_id, person_id, display_name, created_at)
            for person_id, display_name in mentions
        ],
    )
    return revision_id


def _sync_note_reference_evidence(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    owner_person_id: str,
    revision_id: str,
    mentions: list[tuple[str, str]],
    operation_id: str,
    source: str | None,
    created_at: str,
) -> None:
    desired_ids = {
        person_id for person_id, _ in mentions if person_id != owner_person_id
    }
    active_rows = conn.execute(
        """
        SELECT mention_id, referenced_person_id
        FROM note_mentions
        WHERE note_id = ? AND active = 1
        ORDER BY referenced_person_id
        """,
        (note_id,),
    ).fetchall()
    active_by_person = {
        str(row["referenced_person_id"]): str(row["mention_id"])
        for row in active_rows
    }
    removed_ids = sorted(set(active_by_person) - desired_ids)
    for person_id in removed_ids:
        mention_id = active_by_person[person_id]
        conn.execute(
            """
            UPDATE note_mentions
            SET active = 0, retired_revision_id = ?, retired_operation_id = ?,
                retired_at = ?
            WHERE mention_id = ? AND active = 1
            """,
            (revision_id, operation_id, created_at, mention_id),
        )
        conn.execute(
            """
            UPDATE relationship_evidence
            SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
            WHERE evidence_type = 'NOTE_REFERENCE'
              AND source_entity_type = 'NOTE'
              AND source_entity_id = ? AND active = 1
            """,
            (operation_id, created_at, mention_id),
        )
    for person_id in sorted(desired_ids - set(active_by_person)):
        mention_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO note_mentions(
                mention_id, note_id, referenced_person_id, active,
                created_revision_id, created_operation_id, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                mention_id,
                note_id,
                person_id,
                revision_id,
                operation_id,
                created_at,
            ),
        )
        _insert_relationship_evidence(
            conn,
            evidence_type="NOTE_REFERENCE",
            source_entity_type="NOTE",
            source_entity_id=mention_id,
            source_person_id=owner_person_id,
            target_person_id=person_id,
            relationship_type="REFERENCES",
            directionality="DIRECTED",
            source=source,
            created_operation_id=operation_id,
            created_at=created_at,
        )


def _insert_unjournaled_profile_note(
    conn: sqlite3.Connection,
    person_id: str,
    content: str,
    created_at: str,
) -> None:
    if not content or conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notes'"
    ).fetchone() is None:
        return
    note_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO notes(
            note_id, owner_person_id, subject_type, subject_id, is_profile_note,
            status, created_at, updated_at
        ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?)
        """,
        (note_id, person_id, person_id, created_at, created_at),
    )
    _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=1,
        content=content,
        mentions=[],
        actor={"display_name": "SentriFace", "roles": []},
        author_name="SentriFace",
        operation_id=None,
        created_at=created_at,
    )


def _normalize_evidence_endpoints(
    source_person_id: str,
    target_person_id: str,
    directionality: str,
) -> tuple[str, str]:
    source = str(source_person_id).strip()
    target = str(target_person_id).strip()
    if not source or not target:
        raise ValueError("Relationship evidence requires two person IDs")
    if source == target:
        raise ValueError("Relationship evidence cannot reference the same raw person twice")
    if directionality == "UNDIRECTED":
        return tuple(sorted((source, target)))
    if directionality == "DIRECTED":
        return source, target
    raise ValueError(f"Unsupported evidence directionality: {directionality}")


def _insert_relationship_evidence(
    conn: sqlite3.Connection,
    *,
    evidence_type: str,
    source_entity_type: str,
    source_entity_id: str,
    source_person_id: str,
    target_person_id: str,
    relationship_type: str,
    directionality: str,
    source: str | None,
    created_operation_id: str,
    created_at: str,
    evidence_revision_id: str | None = None,
) -> str:
    normalized_source, normalized_target = _normalize_evidence_endpoints(
        source_person_id, target_person_id, directionality,
    )
    evidence_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join((
            "sentriface",
            evidence_type,
            source_entity_id,
            evidence_revision_id or source_entity_id,
            normalized_source,
            normalized_target,
            relationship_type,
            directionality,
        )),
    ))
    conn.execute(
        """
        INSERT OR IGNORE INTO relationship_evidence(
            evidence_id, evidence_type, source_entity_type, source_entity_id,
            evidence_revision_id, source_person_id, target_person_id, relationship_type,
            directionality, active, source, created_operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            evidence_id,
            evidence_type,
            source_entity_type,
            source_entity_id,
            evidence_revision_id or source_entity_id,
            normalized_source,
            normalized_target,
            relationship_type,
            directionality,
            source,
            created_operation_id,
            created_at,
        ),
    )
    return evidence_id


def _relationship_evidence_from_row(row: sqlite3.Row) -> RelationshipEvidence:
    return RelationshipEvidence(
        evidence_id=row["evidence_id"],
        evidence_type=row["evidence_type"],
        source_entity_type=row["source_entity_type"],
        source_entity_id=row["source_entity_id"],
        evidence_revision_id=row["evidence_revision_id"],
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        directionality=row["directionality"],
        active=bool(row["active"]),
        source=row["source"],
        created_operation_id=row["created_operation_id"],
        created_at=row["created_at"],
        deactivated_operation_id=row["deactivated_operation_id"],
        deactivated_at=row["deactivated_at"],
    )


def _graph_connection_from_row(row: sqlite3.Row) -> GraphConnection:
    return GraphConnection(
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        directionality=row["directionality"],
        evidence_count=int(row["evidence_count"]),
        evidence_types=tuple(json.loads(row["evidence_types"])),
        last_evidence_at=row["last_evidence_at"],
    )


def _list_relationship_evidence_for_source(
    conn: sqlite3.Connection,
    evidence_type: str,
    source_entity_id: str,
) -> list[RelationshipEvidence]:
    rows = conn.execute(
        """
        SELECT * FROM relationship_evidence
        WHERE evidence_type = ? AND source_entity_id = ?
        ORDER BY source_person_id, target_person_id, evidence_id
        """,
        (evidence_type, source_entity_id),
    ).fetchall()
    return [_relationship_evidence_from_row(row) for row in rows]


def _expected_graph_connections(
    conn: sqlite3.Connection,
) -> tuple[list[GraphConnection], list[str], int]:
    errors: list[str] = []
    aggregates: dict[tuple[str, str, str, str], dict] = {}
    resolve_canonical = _batch_canonical_resolver(conn)
    co_observation_ids = {
        str(row[0]) for row in conn.execute(
            """
            SELECT DISTINCT source_entity_id
            FROM relationship_evidence
            WHERE evidence_type = 'CO_OBSERVED'
            """
        )
    }
    observation_statuses = {
        str(row["observation_id"]): str(row["status"])
        for row in conn.execute(
            "SELECT observation_id, status FROM observations ORDER BY observation_id"
        )
        if str(row["observation_id"]) in co_observation_ids
    }
    raw_participants: dict[str, set[str]] = {
        observation_id: set() for observation_id in co_observation_ids
    }
    for row in conn.execute(
        """
        SELECT observation_id, person_id
        FROM observation_participants
        ORDER BY observation_id, person_id
        """
    ):
        observation_id = str(row["observation_id"])
        if observation_id in raw_participants:
            raw_participants[observation_id].add(str(row["person_id"]))
    effective_participants, participant_errors = (
        _batch_effective_observation_person_ids(
            conn, co_observation_ids, raw_participants, resolve_canonical,
        )
    )
    errors.extend(participant_errors)
    # A retired generation can name a corrected participant subsequently removed
    # from current presence. Immutable corrections prove that historical endpoint;
    # never rewrite it or require it to remain a current participant.
    historical_correction_targets: dict[str, set[str]] = {}
    for row in conn.execute(
        "SELECT observation_id, to_person_id FROM identity_corrections "
        "WHERE correction_type IN ('OBSERVATION_IDENTITY', 'FACE_ASSIGNMENT')"
    ):
        historical_correction_targets.setdefault(str(row[0]), set()).add(str(row[1]))
    note_mentions = {
        str(row["mention_id"]): row
        for row in conn.execute(
            """
            SELECT m.mention_id, m.referenced_person_id, m.active,
                   n.owner_person_id, n.status
            FROM note_mentions m
            JOIN notes n ON n.note_id = m.note_id
            ORDER BY m.mention_id
            """
        )
    }
    note_reference_state: dict[str, dict[str, int]] = {
        mention_id: {"active": 0, "matching_active": 0}
        for mention_id in note_mentions
    }
    active_evidence_count = 0
    for row in conn.execute(
        "SELECT * FROM relationship_evidence ORDER BY created_at, evidence_id"
    ):
        evidence_id = str(row["evidence_id"])
        active_shape = (
            bool(row["active"])
            and row["deactivated_operation_id"] is None
            and row["deactivated_at"] is None
        )
        retired_shape = (
            not bool(row["active"])
            and row["deactivated_operation_id"] is not None
            and row["deactivated_at"] is not None
        )
        if not (active_shape or retired_shape):
            errors.append(
                f"Evidence {evidence_id} has invalid active/deactivation provenance"
            )
        if row["evidence_type"] == "CO_OBSERVED":
            observation_id = str(row["source_entity_id"])
            observation_status = observation_statuses.get(observation_id)
            if observation_status is None:
                errors.append(f"Evidence {evidence_id} has a missing observation source")
            elif observation_status != "FINALIZED":
                errors.append(f"Evidence {evidence_id} references a non-finalized observation")
            raw_participant_ids = raw_participants.get(observation_id, set())
            effective_participant_ids = effective_participants.get(observation_id, set())
            endpoints_valid = True
            for endpoint in (row["source_person_id"], row["target_person_id"]):
                endpoint_id = str(endpoint)
                if endpoint_id in raw_participant_ids:
                    continue
                if retired_shape and endpoint_id in historical_correction_targets.get(observation_id, set()):
                    continue
                try:
                    effective_endpoint = resolve_canonical(endpoint_id)
                except (KeyError, RuntimeError, ValueError):
                    endpoints_valid = False
                    break
                if effective_endpoint not in effective_participant_ids:
                    endpoints_valid = False
                    break
            if not endpoints_valid:
                errors.append(f"Evidence {evidence_id} endpoints are not observation participants")
        elif row["evidence_type"] == "NOTE_REFERENCE":
            mention_id = str(row["source_entity_id"])
            mention = note_mentions.get(mention_id)
            if mention is None:
                errors.append(f"Evidence {evidence_id} has a missing note mention source")
            else:
                state = note_reference_state[mention_id]
                if bool(row["active"]):
                    state["active"] = int(state["active"]) + 1
                if (
                    row["source_person_id"] != mention["owner_person_id"]
                    or row["target_person_id"] != mention["referenced_person_id"]
                ):
                    errors.append(f"Evidence {evidence_id} endpoints do not match its note mention")
                matching_shape = (
                    row["source_person_id"] == mention["owner_person_id"]
                    and row["target_person_id"] == mention["referenced_person_id"]
                    and row["relationship_type"] == "REFERENCES"
                    and row["directionality"] == "DIRECTED"
                )
                if bool(row["active"]) and matching_shape:
                    state["matching_active"] = int(state["matching_active"]) + 1
                if row["relationship_type"] != "REFERENCES":
                    errors.append(
                        f"Evidence {evidence_id} has an invalid NOTE_REFERENCE relationship type"
                    )
                if row["directionality"] != "DIRECTED":
                    errors.append(
                        f"Evidence {evidence_id} has invalid NOTE_REFERENCE directionality"
                    )
                if bool(row["active"]) and not (
                    bool(mention["active"])
                    and mention["status"] == "ACTIVE"
                ):
                    errors.append(
                        f"Evidence {evidence_id} has no current active note mention source"
                    )
        if not bool(row["active"]):
            continue
        active_evidence_count += 1
        try:
            source_person_id = resolve_canonical(str(row["source_person_id"]))
            target_person_id = resolve_canonical(str(row["target_person_id"]))
        except (KeyError, RuntimeError, ValueError) as exc:
            errors.append(f"Evidence {evidence_id} has invalid canonical endpoints: {exc}")
            continue
        if source_person_id == target_person_id:
            continue
        if row["directionality"] == "UNDIRECTED":
            source_person_id, target_person_id = sorted((source_person_id, target_person_id))
        key = (
            source_person_id,
            target_person_id,
            str(row["relationship_type"]),
            str(row["directionality"]),
        )
        aggregate = aggregates.setdefault(key, {
            "count": 0,
            "types": set(),
            "last": str(row["created_at"]),
        })
        aggregate["count"] += 1
        aggregate["types"].add(str(row["evidence_type"]))
        aggregate["last"] = max(aggregate["last"], str(row["created_at"]))
    for mention_id, mention in sorted(note_mentions.items()):
        state = note_reference_state[mention_id]
        expected_active = 1 if (
            bool(mention["active"])
            and mention["status"] == "ACTIVE"
            and mention["owner_person_id"] != mention["referenced_person_id"]
        ) else 0
        actual_active = int(state["active"])
        matching_active = int(state["matching_active"])
        if actual_active != expected_active or matching_active != expected_active:
            errors.append(
                "NOTE_REFERENCE current active cardinality disagrees for mention "
                f"{mention_id}: expected {expected_active}, matching {matching_active}, "
                f"all active {actual_active}"
            )
    connections = [
        GraphConnection(
            source_person_id=key[0],
            target_person_id=key[1],
            relationship_type=key[2],
            directionality=key[3],
            evidence_count=int(value["count"]),
            evidence_types=tuple(sorted(value["types"])),
            last_evidence_at=str(value["last"]),
        )
        for key, value in sorted(aggregates.items())
    ]
    return connections, errors, active_evidence_count


def _batch_canonical_resolver(conn: sqlite3.Connection) -> Callable[[str], str]:
    people = {
        str(row["person_id"]): (
            str(row["lifecycle_status"]),
            str(row["canonical_person_id"]) if row["canonical_person_id"] else None,
        )
        for row in conn.execute(
            """
            SELECT person_id, lifecycle_status, canonical_person_id
            FROM persons ORDER BY person_id
            """
        )
    }
    cache: dict[str, str] = {}

    def resolve(person_id: str) -> str:
        normalized_id = str(person_id).strip()
        if not normalized_id:
            raise ValueError("Person ID is required")
        cached = cache.get(normalized_id)
        if cached is not None:
            return cached
        current_id = normalized_id
        path: list[str] = []
        visited: set[str] = set()
        while True:
            if current_id in visited:
                raise RuntimeError("Canonical identity cycle detected")
            visited.add(current_id)
            path.append(current_id)
            person = people.get(current_id)
            if person is None:
                if len(path) == 1:
                    raise KeyError(f"Unknown person: {current_id}")
                raise RuntimeError(
                    f"Canonical identity target does not exist: {current_id}"
                )
            lifecycle_status, target_id = person
            if lifecycle_status != "MERGED":
                if target_id is not None:
                    raise RuntimeError(
                        "Non-merged identity has an invalid canonical mapping"
                    )
                for path_id in path:
                    cache[path_id] = current_id
                return current_id
            if target_id is None:
                raise RuntimeError("Merged identity has no canonical target")
            current_id = target_id

    return resolve


def _batch_effective_observation_person_ids(
    conn: sqlite3.Connection,
    observation_ids: set[str],
    raw_participants: dict[str, set[str]],
    resolve_canonical: Callable[[str], str],
    *, selected_observations_only: bool = False,
) -> tuple[dict[str, set[str]], list[str]]:
    if not observation_ids:
        return {}, []
    selection = (
        "WHERE observation_id IN (SELECT value FROM json_each(?))"
        if selected_observations_only else ""
    )
    selection_params = (json.dumps(sorted(observation_ids)),) if selected_observations_only else ()
    assignment_current: dict[str, str] = {}
    assignment_originals: dict[str, set[str]] = {
        observation_id: set() for observation_id in observation_ids
    }
    assignment_observation: dict[str, str] = {}
    for row in conn.execute(
        f"""
        SELECT assignment_id, observation_id, original_person_id
        FROM observation_face_assignments {selection}
        ORDER BY observation_id, assignment_id
        """, selection_params,
    ):
        observation_id = str(row["observation_id"])
        if observation_id not in observation_ids:
            continue
        assignment_id = str(row["assignment_id"])
        original_person_id = str(row["original_person_id"])
        assignment_observation[assignment_id] = observation_id
        assignment_current[assignment_id] = original_person_id
        assignment_originals[observation_id].add(original_person_id)
    observation_corrections: dict[str, list[tuple[str, str]]] = {
        observation_id: [] for observation_id in observation_ids
    }
    for row in conn.execute(
        f"""
        SELECT correction_type, observation_id, face_assignment_id,
               from_person_id, to_person_id
        FROM identity_corrections {selection}
        ORDER BY created_at, rowid, correction_id
        """, selection_params,
    ):
        correction_type = str(row["correction_type"])
        if correction_type == "FACE_ASSIGNMENT" and row["face_assignment_id"]:
            assignment_id = str(row["face_assignment_id"])
            if assignment_id in assignment_current:
                assignment_current[assignment_id] = str(row["to_person_id"])
        elif correction_type == "OBSERVATION_IDENTITY" and row["observation_id"]:
            observation_id = str(row["observation_id"])
            if observation_id in observation_corrections:
                observation_corrections[observation_id].append((
                    str(row["from_person_id"]), str(row["to_person_id"]),
                ))
    assignment_effective: dict[str, set[str]] = {
        observation_id: set() for observation_id in observation_ids
    }
    for assignment_id, person_id in assignment_current.items():
        assignment_effective[assignment_observation[assignment_id]].add(person_id)
    result: dict[str, set[str]] = {}
    errors: list[str] = []
    for observation_id in sorted(observation_ids):
        current = (
            set(raw_participants.get(observation_id, set()))
            - assignment_originals[observation_id]
        )
        current.update(assignment_effective[observation_id])
        for from_person_id, to_person_id in observation_corrections[observation_id]:
            if from_person_id not in current:
                errors.append(
                    f"Observation {observation_id} correction source "
                    f"{from_person_id} is not a current participant"
                )
                continue
            current.remove(from_person_id)
            current.add(to_person_id)
        effective: set[str] = set()
        for person_id in sorted(current):
            try:
                resolve_canonical(person_id)
                effective.add(person_id)
            except (KeyError, RuntimeError, ValueError) as exc:
                errors.append(
                    f"Observation {observation_id} participant {person_id} "
                    f"cannot resolve: {exc}"
                )
        result[observation_id] = effective
    revision_rows = conn.execute(f"SELECT observation_id, person_id, disposition FROM encounter_participant_revisions {selection} ORDER BY created_at, rowid", selection_params) if _table_exists(conn, "encounter_participant_revisions") else []
    for revision in revision_rows:
        oid = str(revision["observation_id"])
        if oid in result:
            pid = str(revision["person_id"])
            if revision["disposition"] == "PRESENT":
                result[oid].add(pid)
            else:
                result[oid].discard(pid)
    result = {oid: {resolve_canonical(pid) for pid in ids} for oid, ids in result.items()}
    return result, errors


def _retire_canonical_manual_collisions(conn: sqlite3.Connection, operation_id: str, survivor_id: str) -> None:
    """One standing assertion per canonical unordered pair; preserve raw history."""
    seen: set[tuple[str, str]] = set()
    resolve = _batch_canonical_resolver(conn)
    for row in conn.execute(
        "SELECT evidence_id, source_person_id, target_person_id FROM relationship_evidence "
        "WHERE evidence_type = 'MANUAL_ASSOCIATION' AND active = 1 ORDER BY created_at, evidence_id"
    ).fetchall():
        pair = tuple(sorted(resolve(str(row[key])) for key in ("source_person_id", "target_person_id")))
        if survivor_id not in pair:
            continue
        if pair[0] == pair[1] or pair in seen:
            conn.execute(
                "UPDATE relationship_evidence SET active = 0, deactivated_operation_id = ?, deactivated_at = ? "
                "WHERE evidence_id = ?", (operation_id, utc_now(), row["evidence_id"]),
            )
        seen.add(pair)


def _graph_connection_signature(item: GraphConnection) -> tuple:
    return (
        item.source_person_id,
        item.target_person_id,
        item.relationship_type,
        item.directionality,
        item.evidence_count,
        tuple(sorted(item.evidence_types)),
        item.last_evidence_at,
    )


def _graph_connection_row_signature(row: sqlite3.Row) -> tuple:
    try:
        evidence_types_value = json.loads(row["evidence_types"])
        if not isinstance(evidence_types_value, list):
            raise ValueError("evidence_types must be a JSON list")
        evidence_types = tuple(sorted(str(item) for item in evidence_types_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        evidence_types = ("<invalid-json>", str(row["evidence_types"]))
    return (
        str(row["source_person_id"]),
        str(row["target_person_id"]),
        str(row["relationship_type"]),
        str(row["directionality"]),
        row["evidence_count"],
        evidence_types,
        str(row["last_evidence_at"]),
    )


def _insert_graph_projection_rows(
    conn: sqlite3.Connection, connections: list[GraphConnection],
) -> None:
    conn.executemany(
        """
        INSERT INTO graph_connections(
            source_person_id, target_person_id, relationship_type, directionality,
            evidence_count, evidence_types, last_evidence_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.source_person_id,
                item.target_person_id,
                item.relationship_type,
                item.directionality,
                item.evidence_count,
                json.dumps(item.evidence_types, separators=(",", ":")),
                item.last_evidence_at,
            )
            for item in connections
        ],
    )


def _graph_revision_token(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT revision FROM graph_state WHERE singleton_id = 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("Graph revision state is unavailable")
    return f"g{int(row['revision'])}"


def _advance_graph_revision(conn: sqlite3.Connection) -> None:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'graph_state'"
    ).fetchone()
    if table_exists is None:
        return
    cursor = conn.execute(
        """
        UPDATE graph_state
        SET revision = revision + 1, updated_at = ?
        WHERE singleton_id = 1
        """,
        (utc_now(),),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Graph revision state is unavailable")


def _normalize_graph_filters(filters: GraphReadFilter | None) -> GraphReadFilter:
    value = filters or GraphReadFilter()

    def choices(items: tuple[str, ...], *, upper: bool = False) -> tuple[str, ...]:
        normalized = {
            (str(item).strip().upper() if upper else str(item).strip())
            for item in items
            if str(item).strip()
        }
        return tuple(sorted(normalized, key=str.casefold))

    date_from = _optional_text(value.date_from)
    date_to = _optional_text(value.date_to)
    start = _graph_filter_datetime(date_from, end_of_day=False) if date_from else None
    end = _graph_filter_datetime(date_to, end_of_day=True) if date_to else None
    if start and end and start > end:
        raise ValueError("Graph date_from must be earlier than or equal to date_to")
    lifecycle = choices(value.lifecycle, upper=True)
    unsupported = set(lifecycle) - PERSON_LIFECYCLE_STATUSES
    if unsupported:
        raise ValueError(f"Unsupported graph lifecycle filter: {sorted(unsupported)[0]}")
    min_frequency = value.min_frequency
    if min_frequency is not None and float(min_frequency) < 0:
        raise ValueError("Graph minimum frequency cannot be negative")
    min_strength = value.min_relationship_strength
    if min_strength is not None and int(min_strength) < 1:
        raise ValueError("Graph minimum relationship strength must be at least 1")
    return GraphReadFilter(
        date_from=date_from,
        date_to=date_to,
        location=_optional_text(value.location),
        lifecycle=lifecycle,
        country=choices(value.country),
        rank=choices(value.rank),
        priority=choices(value.priority),
        min_frequency=float(min_frequency) if min_frequency is not None else None,
        min_relationship_strength=int(min_strength) if min_strength is not None else None,
    )


def _graph_filter_datetime(value: str, *, end_of_day: bool) -> datetime:
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid graph date/time: {value}") from exc
    if len(text) == 10 and end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _graph_occurrence_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _graph_read_components(
    conn: sqlite3.Connection,
    filters: GraphReadFilter,
    *,
    always_include_person_id: str | None = None,
) -> tuple[dict[str, GraphReadNode], tuple[GraphReadEdge, ...]]:
    canonical_ids: set[str] = set()
    aliases: dict[str, list[str]] = {}
    for row in conn.execute("SELECT person_id FROM persons ORDER BY person_id").fetchall():
        raw_id = str(row["person_id"])
        canonical_id = _resolve_canonical_person_id(conn, raw_id)
        canonical_ids.add(canonical_id)
        if raw_id != canonical_id:
            aliases.setdefault(canonical_id, []).append(raw_id)

    all_nodes = {
        person_id: _graph_read_node(
            conn, person_id, historical_person_ids=tuple(sorted(aliases.get(person_id, []))),
        )
        for person_id in sorted(canonical_ids)
    }
    nodes = {
        person_id: node
        for person_id, node in all_nodes.items()
        if person_id == always_include_person_id or _graph_node_matches(node, filters)
    }

    start = (
        _graph_filter_datetime(filters.date_from, end_of_day=False)
        if filters.date_from else None
    )
    end = (
        _graph_filter_datetime(filters.date_to, end_of_day=True)
        if filters.date_to else None
    )
    observations = {
        str(row["observation_id"]): row
        for row in conn.execute(
            "SELECT observation_id, status, observed_at, created_at, location FROM effective_observations"
        ).fetchall()
    }
    scoped_people: set[str] = set()
    if start or end or filters.location:
        for observation_id, observation in observations.items():
            if observation["status"] != "FINALIZED":
                continue
            occurrence_at = str(observation["observed_at"] or observation["created_at"])
            if not _graph_time_matches(occurrence_at, start, end):
                continue
            if filters.location and str(observation["location"] or "").casefold() != filters.location.casefold():
                continue
            scoped_people.update(_effective_observation_person_ids(conn, observation_id))

    aggregates: dict[tuple[str, str], dict[str, object]] = {}
    evidence_rows = conn.execute(
        "SELECT * FROM relationship_evidence WHERE active = 1 ORDER BY created_at, evidence_id"
    ).fetchall()
    for row in evidence_rows:
        observation = (
            observations.get(str(row["source_entity_id"]))
            if row["evidence_type"] == "CO_OBSERVED"
            and row["source_entity_type"] == "OBSERVATION"
            else None
        )
        occurrence_at = str(
            (observation["observed_at"] or observation["created_at"])
            if observation is not None else row["created_at"]
        )
        if not _graph_time_matches(occurrence_at, start, end):
            continue
        if filters.location:
            if observation is None:
                continue
            if str(observation["location"] or "").casefold() != filters.location.casefold():
                continue
        source_id = _resolve_canonical_person_id(conn, str(row["source_person_id"]))
        target_id = _resolve_canonical_person_id(conn, str(row["target_person_id"]))
        if source_id == target_id:
            continue
        pair = tuple(sorted((source_id, target_id)))
        aggregate = aggregates.setdefault(pair, {
            "items": [], "types": {}, "relationships": {}, "sources": set(),
            "directions": {}, "note_directions": {}, "encounters": set(),
            "latest_encounter": None, "first": occurrence_at, "last": occurrence_at,
        })
        aggregate["items"].append(row)
        evidence_type = str(row["evidence_type"])
        aggregate["types"][evidence_type] = aggregate["types"].get(evidence_type, 0) + 1
        relationship_type = str(row["relationship_type"])
        aggregate["relationships"][relationship_type] = (
            aggregate["relationships"].get(relationship_type, 0) + 1
        )
        aggregate["sources"].add((str(row["source_entity_type"]), str(row["source_entity_id"])))
        direction_key = (
            "UNDIRECTED" if row["directionality"] == "UNDIRECTED"
            else f"{source_id}->{target_id}"
        )
        aggregate["directions"][direction_key] = aggregate["directions"].get(direction_key, 0) + 1
        if evidence_type == "NOTE_REFERENCE":
            aggregate["note_directions"][direction_key] = aggregate["note_directions"].get(direction_key, 0) + 1
        if evidence_type == "CO_OBSERVED" and observation is not None:
            aggregate["encounters"].add(str(row["source_entity_id"]))
            latest = aggregate["latest_encounter"]
            if latest is None or _graph_occurrence_datetime(occurrence_at) > _graph_occurrence_datetime(latest):
                aggregate["latest_encounter"] = occurrence_at
        if _graph_occurrence_datetime(occurrence_at) < _graph_occurrence_datetime(str(aggregate["first"])):
            aggregate["first"] = occurrence_at
        if _graph_occurrence_datetime(occurrence_at) > _graph_occurrence_datetime(str(aggregate["last"])):
            aggregate["last"] = occurrence_at
        scoped_people.update((source_id, target_id))

    if start or end or filters.location:
        nodes = {
            person_id: node for person_id, node in nodes.items()
            if person_id == always_include_person_id or person_id in scoped_people
        }

    edges: list[GraphReadEdge] = []
    for pair, aggregate in sorted(aggregates.items()):
        if pair[0] not in nodes or pair[1] not in nodes:
            continue
        evidence_count = len(aggregate["items"])
        if (
            filters.min_relationship_strength is not None
            and evidence_count < filters.min_relationship_strength
        ):
            continue
        directions = aggregate["directions"]
        if set(directions) == {"UNDIRECTED"}:
            source_id, target_id = pair
            directionality = "UNDIRECTED"
        elif len(directions) == 1 and "UNDIRECTED" not in directions:
            source_id, target_id = next(iter(directions)).split("->", 1)
            directionality = "DIRECTED"
        else:
            source_id, target_id = pair
            directionality = "MIXED"
        evidence_types = tuple(sorted(aggregate["types"]))
        relationship_types = tuple(sorted(aggregate["relationships"]))
        edges.append(GraphReadEdge(
            source_person_id=source_id,
            target_person_id=target_id,
            connected_person_id=None,
            canonical_source_person_id=source_id,
            canonical_target_person_id=target_id,
            relationship_strength=evidence_count,
            evidence_count=evidence_count,
            evidence_types=evidence_types,
            first_occurrence_at=str(aggregate["first"]),
            last_occurrence_at=str(aggregate["last"]),
            directionality=directionality,
            relationship_types=relationship_types,
            relationship_type_summary=(
                relationship_types[0] if len(relationship_types) == 1 else "MULTIPLE"
            ),
            strength_basis="active_authoritative_evidence_count",
            provenance_summary={
                "evidence_type_counts": dict(sorted(aggregate["types"].items())),
                "relationship_type_counts": dict(sorted(aggregate["relationships"].items())),
                "source_record_count": len(aggregate["sources"]),
                "direction_counts": dict(sorted(directions.items())),
                "distinct_encounter_count": len(aggregate["encounters"]),
                "latest_shared_encounter_at": aggregate["latest_encounter"],
                "note_reference_direction_counts": dict(sorted(aggregate["note_directions"].items())),
            },
        ))
    return nodes, tuple(edges)


def _graph_time_matches(
    value: str, start: datetime | None, end: datetime | None,
) -> bool:
    occurrence = _graph_occurrence_datetime(value)
    return not ((start and occurrence < start) or (end and occurrence > end))


def _graph_read_node(
    conn: sqlite3.Connection,
    person_id: str,
    *,
    historical_person_ids: tuple[str, ...] = (),
) -> GraphReadNode:
    row = conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"Canonical graph person is unavailable: {person_id}")
    metadata = json.loads(row["metadata"] or "{}")
    sightings = _list_person_sightings(conn, person_id)
    presence = _presence_analytics(sightings)
    embedding_rows = conn.execute(
        "SELECT embedding_id, person_id, crop_path, source_image FROM embeddings WHERE deleted_at IS NULL"
    ).fetchall()
    effective_embeddings = [
        item for item in embedding_rows
        if _effective_embedding_owner_person_id(conn, item) == person_id
    ]
    representative_id = metadata.get("representative_embedding_id")
    representative = next((
        str(item["crop_path"] or item["source_image"])
        for item in effective_embeddings
        if item["embedding_id"] == representative_id and (item["crop_path"] or item["source_image"])
    ), None)
    if representative is None:
        representative = next((
            str(item["crop_path"] or item["source_image"])
            for item in effective_embeddings if item["crop_path"] or item["source_image"]
        ), None)
    lifecycle = str(row["lifecycle_status"])
    return GraphReadNode(
        person_id=person_id,
        canonical_person_id=person_id,
        display_name=str(row["name"]),
        lifecycle_status=lifecycle,
        biometric_status=str(row["biometric_status"]),
        representative_media_reference=representative,
        allowed_actions=_graph_allowed_actions(lifecycle),
        state_indicator="CURRENT" if lifecycle == "ACTIVE" else "HISTORICAL",
        historical_person_ids=historical_person_ids,
        summary_intelligence={
            "observation_count": presence.observation_count,
            "first_seen_at": presence.first_seen_at,
            "last_seen_at": presence.last_seen_at,
            "frequency_per_30_days": presence.frequency_per_30_days,
            "frequency_label": presence.frequency_label,
            "locations": [
                {"location": item.location, "count": item.count, "last_observed_at": item.last_observed_at}
                for item in presence.locations
            ],
            "country": metadata.get("country"),
            "rank": metadata.get("rank"),
            "priority": metadata.get("importance"),
        },
    )


def _graph_node_matches(node: GraphReadNode, filters: GraphReadFilter) -> bool:
    summary = node.summary_intelligence

    def matches(value: object, choices: tuple[str, ...]) -> bool:
        return not choices or str(value or "").casefold() in {item.casefold() for item in choices}

    return (
        (not filters.lifecycle or node.lifecycle_status in filters.lifecycle)
        and matches(summary.get("country"), filters.country)
        and matches(summary.get("rank"), filters.rank)
        and matches(summary.get("priority"), filters.priority)
        and (
            filters.min_frequency is None
            or float(summary.get("frequency_per_30_days") or 0) >= filters.min_frequency
        )
    )


def _graph_allowed_actions(lifecycle_status: str) -> tuple[str, ...]:
    return {
        "ACTIVE": (
            "OPEN", "EDIT", "EDIT_NOTES", "FAVORITE", "MANAGE_FACES",
            "ARCHIVE", "DELETE", "MERGE",
        ),
        "ARCHIVED": ("VIEW_HISTORY", "RESTORE", "DELETE"),
        "DELETED": ("VIEW_HISTORY", "RESTORE"),
        "MERGED": ("VIEW_HISTORY", "OPEN_CANONICAL"),
    }.get(lifecycle_status, ("VIEW_HISTORY",))


def _validate_graph_projection(conn: sqlite3.Connection) -> dict:
    expected, errors, active_evidence_count = _expected_graph_connections(conn)
    actual_rows = conn.execute(
        """
        SELECT * FROM graph_connections
        ORDER BY source_person_id, target_person_id, relationship_type, directionality
        """
    ).fetchall()
    actual: list[GraphConnection] = []
    for row in actual_rows:
        try:
            actual.append(_graph_connection_from_row(row))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(
                "Invalid projected connection payload for "
                f"{row['source_person_id']} -> {row['target_person_id']}: {exc}"
            )
    expected_map = {
        (
            item.source_person_id,
            item.target_person_id,
            item.relationship_type,
            item.directionality,
        ): item
        for item in expected
    }
    actual_map = {
        (
            item.source_person_id,
            item.target_person_id,
            item.relationship_type,
            item.directionality,
        ): item
        for item in actual
    }
    for key in sorted(expected_map.keys() - actual_map.keys()):
        errors.append(f"Missing projected connection: {key}")
    for key in sorted(actual_map.keys() - expected_map.keys()):
        errors.append(f"Unexpected projected connection: {key}")
    for key in sorted(expected_map.keys() & actual_map.keys()):
        if expected_map[key] != actual_map[key]:
            errors.append(f"Projected connection does not match evidence: {key}")
    dangling = conn.execute(
        """
        SELECT g.source_person_id, g.target_person_id
        FROM graph_connections g
        LEFT JOIN persons source ON source.person_id = g.source_person_id
        LEFT JOIN persons target ON target.person_id = g.target_person_id
        WHERE source.person_id IS NULL OR target.person_id IS NULL
        """
    ).fetchall()
    for row in dangling:
        errors.append(
            f"Dangling projected connection: {row['source_person_id']} -> {row['target_person_id']}"
        )
    self_edges = conn.execute(
        "SELECT source_person_id FROM graph_connections WHERE source_person_id = target_person_id"
    ).fetchall()
    for row in self_edges:
        errors.append(f"Illegal projected self-edge: {row['source_person_id']}")
    return {
        "valid": not errors,
        "errors": errors,
        "active_evidence_count": active_evidence_count,
        "expected_connection_count": len(expected),
        "actual_connection_count": len(actual),
    }


def _require_observation(conn: sqlite3.Connection, observation_id: str) -> sqlite3.Row:
    normalized_id = str(observation_id).strip()
    if not normalized_id:
        raise ValueError("Observation ID is required")
    row = conn.execute(
        "SELECT * FROM effective_observations WHERE observation_id = ?", (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown observation: {normalized_id}")
    return row


def _require_draft_observation(conn: sqlite3.Connection, observation_id: str) -> sqlite3.Row:
    row = _require_observation(conn, observation_id)
    if row["status"] != "DRAFT":
        raise ValueError("Finalized observations cannot be changed")
    return row


def _require_existing_media(
    conn: sqlite3.Connection,
    media_id: str,
    media_path: str | None,
) -> None:
    require_existing_media(conn, media_id, media_path)


def _attach_observation_media(
    conn: sqlite3.Connection,
    observation_id: str,
    media_id: str,
    media_path: str | None,
    source: str | None,
    operation_id: str,
) -> tuple[ObservationMedia, bool]:
    normalized_media_id = str(media_id).strip()
    if not normalized_media_id:
        raise ValueError("Media ID is required")
    normalized_media_path = _optional_text(media_path)
    existing = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media WHERE observation_id = ? AND media_id = ?
        """,
        (observation_id, normalized_media_id),
    ).fetchone()
    if existing is not None:
        return _observation_media_from_row(existing), False
    _require_existing_media(conn, normalized_media_id, normalized_media_path)
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO observation_media(
            observation_id, media_id, media_path, source, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            normalized_media_id,
            normalized_media_path,
            _optional_text(source),
            operation_id,
            created_at,
        ),
    )
    row = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media WHERE observation_id = ? AND media_id = ?
        """,
        (observation_id, normalized_media_id),
    ).fetchone()
    return _observation_media_from_row(row), True


def _add_observation_participant(
    conn: sqlite3.Connection,
    observation_id: str,
    person_id: str,
    source: str | None,
    operation_id: str,
) -> tuple[ObservationParticipant, bool]:
    normalized_person_id = str(person_id).strip()
    if not normalized_person_id:
        raise ValueError("Person ID is required")
    if conn.execute(
        "SELECT 1 FROM persons WHERE person_id = ?", (normalized_person_id,),
    ).fetchone() is None:
        raise KeyError(f"Unknown person: {normalized_person_id}")
    canonical_person_id = _resolve_canonical_person_id(conn, normalized_person_id)
    existing_rows = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ?
        ORDER BY p.created_at, p.person_id
        """,
        (observation_id,),
    ).fetchall()
    for row in existing_rows:
        existing = _observation_participant_from_row(conn, row)
        if existing.person_id == normalized_person_id:
            return existing, False
        if existing.canonical_person_id == canonical_person_id:
            return existing, False
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO observation_participants(
            observation_id, person_id, source, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            normalized_person_id,
            _optional_text(source),
            operation_id,
            created_at,
        ),
    )
    row = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ? AND p.person_id = ?
        """,
        (observation_id, normalized_person_id),
    ).fetchone()
    return _observation_participant_from_row(conn, row), True


def _list_observation_media(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationMedia]:
    rows = conn.execute(
        """
        SELECT observation_id, media_id, media_path, source, operation_id, created_at
        FROM observation_media
        WHERE observation_id = ?
        ORDER BY created_at, media_id
        """,
        (observation_id,),
    ).fetchall()
    return [_observation_media_from_row(row) for row in rows]


def _table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (name,)).fetchone() is not None


def _encounter_detail_person(conn, observation_id, detail):
    for assignment in _effective_face_assignments(conn, observation_id):
        if assignment["embedding_id"] == detail["embedding_id"]:
            return _resolve_canonical_person_id(conn, assignment["current_person_id"])
    return _resolve_canonical_person_id(conn, str(detail["person_id"]))


def _append_participant_revision(conn, observation_id, person_id, disposition, operation_id):
    # Freeze the raw component being removed today. A later merge must not
    # remove participation contributed by its future survivor.
    ids = [person_id]
    if disposition == "REMOVED":
        ids = [str(row[0]) for row in conn.execute("SELECT person_id FROM persons")
               if _resolve_canonical_person_id(conn, str(row[0])) == person_id]
    for raw_id in ids:
        conn.execute("INSERT INTO encounter_participant_revisions VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), observation_id, raw_id, disposition, operation_id, utc_now()))


def _encounter_event_details(row):
    context = json.loads(row["context"] or "{}")
    return {"date": str(row["observed_at"] or "")[:10], "time": context.get("start_time") or "",
            "end_time": context.get("end_time") or "", "time_precision": context.get("time_precision", "unknown"),
            "place_seen": row["location"] or "", "event_occasion": context.get("occasion") or "",
            "event_context": context.get("category", "unknown"), "event_notes": context.get("event_notes") or "",
            "event_mentioned_person_ids": context.get("event_mentioned_person_ids", [])}


def _encounter_revision(conn, observation_id, *, include_media_locations=False):
    # Bind the complete reviewed authority, including lifecycle/canonical interpretation.
    snapshot = {"observation": dict(_require_observation(conn, observation_id)),
                "participants": _effective_observation_person_ids(conn, observation_id),
                "media": [dict(row) for row in conn.execute("SELECT * FROM observation_media WHERE observation_id = ? ORDER BY media_id", (observation_id,))],
                "relations": [dict(row) for row in conn.execute("SELECT * FROM encounter_relation_decisions WHERE observation_id = ? ORDER BY decision_id", (observation_id,))],
                "corrections": [dict(row) for row in conn.execute("SELECT * FROM identity_corrections WHERE observation_id = ? ORDER BY correction_id", (observation_id,))],
                "participant_revisions": [dict(row) for row in conn.execute("SELECT * FROM encounter_participant_revisions WHERE observation_id = ? ORDER BY revision_id", (observation_id,))]}
    if not include_media_locations:
        for media in snapshot["media"]:
            media.pop("media_path", None)
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _require_encounter_revision(conn, observation_id, expected_revision):
    if _require_observation(conn, observation_id)["status"] != "FINALIZED":
        raise ValueError("Only a finalized Encounter can be managed")
    if not expected_revision or expected_revision != _encounter_revision(conn, observation_id):
        raise ValueError("Encounter changed; reload it before correcting or attaching media")


def _require_no_encounter_amendment(conn, observation_id, *, session_id=None):
    row = conn.execute("SELECT session_id FROM photo_reviews WHERE target_observation_id = ? AND status = 'IN_PROGRESS'", (observation_id,)).fetchone()
    if row and (not session_id or row["session_id"] != session_id):
        raise ValueError("Finish or discard the active Attach Media review before correcting this Encounter")


def _encounter_person_media(conn, observation_id, person_id):
    if person_id not in _effective_observation_person_ids(conn, observation_id):
        return []
    result = set()
    for assignment in _effective_face_assignments(conn, observation_id):
        if _resolve_canonical_person_id(conn, assignment["current_person_id"]) == person_id:
            media = conn.execute(
                "SELECT m.media_path FROM observation_face_assignments a "
                "JOIN photo_review_faces f ON f.review_id = a.review_id AND f.face_id = a.face_id "
                "JOIN observation_media m ON m.observation_id = a.observation_id "
                "AND m.media_id = json_extract(f.recognition_detail, '$.encounter_media_id') "
                "WHERE a.assignment_id = ?", (assignment["assignment_id"],),
            ).fetchone()
            if media and media[0]:
                result.add(str(media[0]))
                continue
            # Legacy single-photo review assignments belong to the review frame,
            # including reused embeddings whose enrollment photo is different.
            legacy = conn.execute("SELECT r.media_path FROM observation_face_assignments a JOIN photo_reviews r ON r.review_id = a.review_id WHERE a.assignment_id = ? AND r.review_phase = 'LEGACY'", (assignment["assignment_id"],)).fetchone()
            path = legacy[0] if legacy else None
            if not path:
                row = conn.execute("SELECT source_image FROM embeddings WHERE embedding_id = ?", (assignment["embedding_id"],)).fetchone()
                path = row[0] if row else None
            if path and conn.execute("SELECT 1 FROM observation_media WHERE observation_id = ? AND media_path = ?", (observation_id, path)).fetchone():
                result.add(str(path))
    return sorted(result)


def _media_pair_support(first_media, second_media):
    """One support meaning for draft and finalized effective frame sets."""
    return "SHARED_FRAME" if set(first_media) & set(second_media) else "SAME_ENCOUNTER_ONLY"


def _encounter_read_record(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    observation_id = str(row["observation_id"])
    context = json.loads(row["context"] or "{}")
    participant_ids = _effective_observation_person_ids(conn, observation_id)
    mentioned_ids = sorted({
        _resolve_canonical_person_id(conn, person_id)
        for person_id in context.get("event_mentioned_person_ids", [])
        if conn.execute("SELECT 1 FROM persons WHERE person_id = ?", (person_id,)).fetchone()
    })
    all_ids = sorted(set(participant_ids) | set(mentioned_ids))
    names = {}
    if all_ids:
        placeholders = ",".join("?" for _ in all_ids)
        names = {
            str(person["person_id"]): str(person["name"])
            for person in conn.execute(
                f"SELECT person_id, name FROM persons WHERE person_id IN ({placeholders})", all_ids,
            )
        }
    media_count = int(conn.execute(
        "SELECT COUNT(*) FROM observation_media WHERE observation_id = ?", (observation_id,),
    ).fetchone()[0])
    return {
        "observation_id": observation_id,
        "sort_at": str(row["observed_at"] or row["created_at"]),
        "observed_at": row["observed_at"],
        "occasion": context.get("occasion"),
        "start_time": context.get("start_time"),
        "end_time": context.get("end_time"),
        "time_precision": context.get("time_precision", "unknown"),
        "location": row["location"],
        "context": context.get("category", "unknown"),
        "event_notes": context.get("event_notes") or "",
        "participant_ids": participant_ids,
        "participants": [{"person_id": person_id, "name": names.get(person_id, "Historical person")}
                         for person_id in participant_ids],
        "mentioned_person_ids": mentioned_ids,
        "mentioned_people": [{"person_id": person_id, "name": names.get(person_id, "Historical person")}
                             for person_id in mentioned_ids],
        "media_count": media_count,
        "created_operation_id": row["created_operation_id"],
        "finalized_at": row["finalized_at"],
    }


def _insert_identity_correction(
    conn: sqlite3.Connection,
    *,
    correction_type: str,
    observation_id: str | None,
    face_assignment_id: str | None,
    embedding_id: str | None,
    from_person_id: str,
    to_person_id: str,
    operation_id: str,
) -> str:
    correction_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join((
            "sentriface-correction", operation_id, correction_type,
            observation_id or "", face_assignment_id or "", embedding_id or "",
            from_person_id, to_person_id,
        )),
    ))
    conn.execute(
        """
        INSERT INTO identity_corrections(
            correction_id, correction_type, observation_id, face_assignment_id,
            embedding_id, from_person_id, to_person_id, operation_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            correction_id, correction_type, observation_id, face_assignment_id,
            embedding_id, from_person_id, to_person_id, operation_id, utc_now(),
        ),
    )
    return correction_id


def _identity_correction_from_row(row: sqlite3.Row) -> IdentityCorrection:
    return IdentityCorrection(
        correction_id=str(row["correction_id"]),
        correction_type=str(row["correction_type"]),
        observation_id=row["observation_id"],
        face_assignment_id=row["face_assignment_id"],
        embedding_id=row["embedding_id"],
        from_person_id=str(row["from_person_id"]),
        to_person_id=str(row["to_person_id"]),
        operation_id=str(row["operation_id"]),
        created_at=str(row["created_at"]),
    )


def _effective_face_assignments(
    conn: sqlite3.Connection, observation_id: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT assignment_id, observation_id, face_id, embedding_id, original_person_id
        FROM observation_face_assignments
        WHERE observation_id = ? ORDER BY face_id, assignment_id
        """,
        (observation_id,),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        correction = conn.execute(
            """
            SELECT to_person_id FROM identity_corrections
            WHERE face_assignment_id = ? AND correction_type = 'FACE_ASSIGNMENT'
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (row["assignment_id"],),
        ).fetchone()
        result.append({
            "assignment_id": str(row["assignment_id"]),
            "observation_id": str(row["observation_id"]),
            "face_id": str(row["face_id"]),
            "embedding_id": str(row["embedding_id"]),
            "original_person_id": str(row["original_person_id"]),
            "current_person_id": str(
                correction["to_person_id"] if correction else row["original_person_id"]
            ),
        })
    return result


def _corrected_observation_person_ids(
    conn: sqlite3.Connection, observation_id: str,
) -> list[str]:
    base_ids = {
        str(row["person_id"])
        for row in conn.execute(
            "SELECT person_id FROM observation_participants WHERE observation_id = ?",
            (observation_id,),
        ).fetchall()
    }
    assignments = _effective_face_assignments(conn, observation_id)
    represented_original_ids = {item["original_person_id"] for item in assignments}
    effective_ids = base_ids - represented_original_ids
    effective_ids.update(item["current_person_id"] for item in assignments)
    participant_corrections = conn.execute(
        """
        SELECT from_person_id, to_person_id
        FROM identity_corrections
        WHERE observation_id = ? AND correction_type = 'OBSERVATION_IDENTITY'
        ORDER BY created_at, rowid
        """,
        (observation_id,),
    ).fetchall()
    for correction in participant_corrections:
        from_person_id = str(correction["from_person_id"])
        if from_person_id in effective_ids:
            effective_ids.remove(from_person_id)
            effective_ids.add(str(correction["to_person_id"]))
    for revision in conn.execute(
        "SELECT person_id, disposition FROM encounter_participant_revisions WHERE observation_id = ? ORDER BY created_at, rowid",
        (observation_id,),
    ):
        pid = str(revision["person_id"])
        if revision["disposition"] == "PRESENT":
            effective_ids.add(pid)
        else:
            effective_ids.discard(pid)
    return sorted(effective_ids)


def _effective_observation_person_ids(
    conn: sqlite3.Connection, observation_id: str,
) -> list[str]:
    corrected_ids = _corrected_observation_person_ids(conn, observation_id)
    return sorted({
        _resolve_canonical_person_id(conn, raw_person_id)
        for raw_person_id in corrected_ids
    })


def _list_person_sightings(
    conn: sqlite3.Connection, canonical_person_id: str,
) -> list[Sighting]:
    sightings: list[Sighting] = []
    rows = conn.execute(
        """
        SELECT * FROM effective_observations
        WHERE status = 'FINALIZED'
        ORDER BY COALESCE(observed_at, created_at) DESC, observation_id
        """
    ).fetchall()
    for row in rows:
        observation_id = str(row["observation_id"])
        effective_ids = tuple(_effective_observation_person_ids(conn, observation_id))
        if canonical_person_id not in effective_ids:
            continue
        raw_ids = tuple(sorted({
            str(item["person_id"])
            for item in conn.execute(
                "SELECT person_id FROM observation_participants WHERE observation_id = ?",
                (observation_id,),
            ).fetchall()
        }))
        correction_ids = tuple(
            str(item["operation_id"])
            for item in conn.execute(
                """
                SELECT DISTINCT operation_id FROM identity_corrections
                WHERE observation_id = ?
                ORDER BY created_at, operation_id
                """,
                (observation_id,),
            ).fetchall()
        )
        sightings.append(Sighting(
            sighting_id=f"{observation_id}:{canonical_person_id}",
            observation_id=observation_id,
            canonical_person_id=canonical_person_id,
            observed_at=str(row["observed_at"] or row["created_at"]),
            location=_optional_text(row["location"]),
            context=json.loads(row["context"] or "{}"),
            source=_optional_text(row["source"]),
            finalized_at=_optional_text(row["finalized_at"]),
            media=tuple(_list_observation_media(conn, observation_id)),
            raw_participant_person_ids=raw_ids,
            effective_participant_person_ids=effective_ids,
            correction_operation_ids=correction_ids,
        ))
    return sightings


def _presence_analytics(sightings: list[Sighting]) -> PresenceAnalytics:
    if not sightings:
        return PresenceAnalytics(
            observation_count=0,
            first_seen_at=None,
            last_seen_at=None,
            frequency_per_30_days=0.0,
            frequency_label="Never Seen",
            provenance=(
                "observations.status=FINALIZED",
                "effective corrected/canonical observation participants",
            ),
        )
    ordered = sorted(sightings, key=lambda item: (item.observed_at, item.observation_id))
    first_seen_at = ordered[0].observed_at
    last_seen_at = ordered[-1].observed_at
    try:
        first = datetime.fromisoformat(first_seen_at.replace("Z", "+00:00"))
        last = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        active_days = max(1.0, (last - first).total_seconds() / 86_400 + 1)
    except (TypeError, ValueError):
        active_days = 30.0
    frequency = round(len(ordered) / max(1.0, active_days / 30.0), 3)
    if frequency >= 8:
        frequency_label = "Very Frequent"
    elif frequency >= 3:
        frequency_label = "Frequent"
    elif frequency >= 1:
        frequency_label = "Occasional"
    else:
        frequency_label = "Rare"
    periods: dict[str, int] = {}
    locations: dict[str, dict[str, object]] = {}
    for sighting in ordered:
        period = sighting.observed_at[:7]
        periods[period] = periods.get(period, 0) + 1
        if sighting.location:
            item = locations.setdefault(sighting.location, {
                "count": 0, "last_observed_at": sighting.observed_at,
            })
            item["count"] = int(item["count"]) + 1
            item["last_observed_at"] = max(
                str(item["last_observed_at"]), sighting.observed_at,
            )
    return PresenceAnalytics(
        observation_count=len(ordered),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        frequency_per_30_days=frequency,
        frequency_label=frequency_label,
        timeline=tuple(TemporalCount(period=period, count=count)
                       for period, count in sorted(periods.items())),
        locations=tuple(sorted((
            LocationCount(
                location=location,
                count=int(values["count"]),
                last_observed_at=str(values["last_observed_at"]),
            )
            for location, values in locations.items()
        ), key=lambda item: (-item.count, item.location.casefold()))),
        provenance=(
            "observations.status=FINALIZED",
            "observations.observed_at (created_at fallback)",
            "effective corrected/canonical observation participants",
        ),
    )


def _person_relationship_analytics(
    conn: sqlite3.Connection, canonical_person_id: str,
) -> tuple[RelationshipAnalytics, ...]:
    aggregates: dict[tuple[str, str, str, str], list[RelationshipEvidence]] = {}
    rows = conn.execute(
        "SELECT * FROM relationship_evidence WHERE active = 1 ORDER BY created_at, evidence_id"
    ).fetchall()
    for row in rows:
        source_id = _resolve_canonical_person_id(conn, str(row["source_person_id"]))
        target_id = _resolve_canonical_person_id(conn, str(row["target_person_id"]))
        if source_id == target_id:
            continue
        if row["directionality"] == "UNDIRECTED":
            source_id, target_id = sorted((source_id, target_id))
        if canonical_person_id not in {source_id, target_id}:
            continue
        other_id = target_id if source_id == canonical_person_id else source_id
        key = (
            other_id,
            source_id,
            target_id,
            f"{row['relationship_type']}|{row['directionality']}",
        )
        aggregates.setdefault(key, []).append(_relationship_evidence_from_row(row))
    results: list[RelationshipAnalytics] = []
    for (other_id, source_id, target_id, relationship_key), evidence in aggregates.items():
        relationship_type, directionality = relationship_key.split("|", 1)
        type_counts: dict[str, int] = {}
        for item in evidence:
            type_counts[item.evidence_type] = type_counts.get(item.evidence_type, 0) + 1
        results.append(RelationshipAnalytics(
            person_id=other_id,
            source_person_id=source_id,
            target_person_id=target_id,
            relationship_type=relationship_type,
            directionality=directionality,
            evidence_count=len(evidence),
            evidence_type_counts=dict(sorted(type_counts.items())),
            first_evidence_at=min(item.created_at for item in evidence),
            last_evidence_at=max(item.created_at for item in evidence),
            co_observation_count=type_counts.get("CO_OBSERVED", 0),
            evidence=tuple(evidence),
        ))
    results.sort(key=lambda item: (item.last_evidence_at, item.person_id), reverse=True)
    results.sort(key=lambda item: item.evidence_count, reverse=True)
    return tuple(results)


def _list_observation_participants(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationParticipant]:
    correction = conn.execute(
        """
        SELECT operation_id, created_at FROM identity_corrections
        WHERE observation_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
        """,
        (observation_id,),
    ).fetchone()
    participants: list[ObservationParticipant] = []
    for person_id in _effective_observation_person_ids(conn, observation_id):
        person = conn.execute(
            "SELECT lifecycle_status FROM persons WHERE person_id = ?", (person_id,),
        ).fetchone()
        participants.append(ObservationParticipant(
            observation_id=observation_id,
            person_id=person_id,
            canonical_person_id=person_id,
            person_lifecycle_status=str(person["lifecycle_status"]),
            source="identity-correction" if correction is not None else "canonical-resolution",
            operation_id=str(correction["operation_id"]) if correction is not None else "",
            created_at=str(correction["created_at"]) if correction is not None else "",
        ))
    return participants


def _list_raw_observation_participants(
    conn: sqlite3.Connection, observation_id: str,
) -> list[ObservationParticipant]:
    rows = conn.execute(
        """
        SELECT p.observation_id, p.person_id, p.source, p.operation_id, p.created_at,
               person.lifecycle_status
        FROM observation_participants p
        JOIN persons person ON person.person_id = p.person_id
        WHERE p.observation_id = ?
        ORDER BY p.created_at, p.person_id
        """,
        (observation_id,),
    ).fetchall()
    return [_observation_participant_from_row(conn, row) for row in rows]


def _review_encounter_metadata(details: list[dict]) -> tuple[str | None, str | None, dict]:
    """Resolve one event's metadata from finalized face decisions, rejecting conflicts."""
    fields = ("date", "time", "end_time", "time_precision", "place_seen", "event_occasion", "event_context", "event_notes")
    values: dict[str, str] = {}
    for detail in details:
        for field in fields:
            value = str(detail.get(field) or "").strip()
            if not value:
                continue
            if field in values and values[field] != value:
                raise ValueError(f"Conflicting Encounter {field} across reviewed faces")
            values[field] = value
    date = values.get("date")
    start = values.get("time")
    end = values.get("end_time")
    if date:
        try:
            if len(date) != 10:
                raise ValueError("invalid date width")
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Encounter date must use ISO format") from exc
    for field, value in (("time", start), ("end_time", end)):
        if value:
            try:
                if len(value) != 5 or value[2] != ":":
                    raise ValueError("invalid time width")
                datetime.strptime(value, "%H:%M")
            except ValueError as exc:
                raise ValueError(f"Encounter {field} must use HH:MM format") from exc
    if start and not date:
        raise ValueError("Encounter time requires a date")
    if end and not start:
        raise ValueError("Encounter end time requires a start time")
    if start and end and end < start:
        raise ValueError("Encounter end time precedes start time")
    precision = values.get("time_precision", "exact" if start else "unknown").lower()
    if precision not in {"exact", "approximate", "unknown"}:
        raise ValueError("Encounter time precision must be exact, approximate, or unknown")
    if (precision == "unknown") == bool(start):
        raise ValueError("Encounter time and precision disagree")
    category = values.get("event_context", "unknown").lower()
    if category not in {"ordinary", "public", "unknown"}:
        raise ValueError("Encounter context must be ordinary, public, or unknown")
    mention_sets: set[tuple[str, ...]] = set()
    for detail in details:
        mentions = detail.get("event_mentioned_person_ids") or []
        if not isinstance(mentions, list) or any(
            not isinstance(item, str) or not item.strip() for item in mentions
        ):
            raise ValueError("Event Note mentions must be selected person IDs")
        mention_sets.add(tuple(sorted(set(mentions))))
    if len(mention_sets) > 1:
        raise ValueError("Conflicting Encounter Event Note mentions across reviewed faces")
    event_mentions = list(next(iter(mention_sets), ()))
    context = {
        "occasion": values.get("event_occasion") or None,
        "start_time": start or None,
        "end_time": end or None,
        "time_precision": precision,
        "category": category,
        "event_notes": values.get("event_notes") or None,
        "event_mentioned_person_ids": event_mentions,
        "added_by": next((str(item.get("added_by") or "").strip() for item in details if item.get("added_by")), None),
    }
    return (f"{date}T{start}:00" if date and start else date), values.get("place_seen") or None, context


def _observation_from_row(row: sqlite3.Row) -> Observation:
    return Observation(
        observation_id=row["observation_id"],
        status=row["status"],
        observed_at=row["observed_at"],
        location=row["location"],
        context=json.loads(row["context"]),
        source=row["source"],
        created_operation_id=row["created_operation_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finalized_at=row["finalized_at"],
    )


def _observation_media_from_row(row: sqlite3.Row) -> ObservationMedia:
    return ObservationMedia(
        observation_id=row["observation_id"],
        media_id=row["media_id"],
        media_path=row["media_path"],
        source=row["source"],
        operation_id=row["operation_id"],
        created_at=row["created_at"],
    )


def _observation_participant_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> ObservationParticipant:
    return ObservationParticipant(
        observation_id=row["observation_id"],
        person_id=row["person_id"],
        canonical_person_id=_resolve_canonical_person_id(conn, row["person_id"]),
        person_lifecycle_status=row["lifecycle_status"],
        source=row["source"],
        operation_id=row["operation_id"],
        created_at=row["created_at"],
    )


def _has_meaningful_identity_context(name: str, metadata: dict, notes: str) -> bool:
    if name.strip() or notes.strip():
        return True
    return any(value not in (None, "", [], {}, ()) for value in metadata.values())


def _profile_note_snapshot(conn: sqlite3.Connection, person_id: str) -> dict:
    row = conn.execute(
        """
        SELECT note_id FROM notes
        WHERE owner_person_id = ? AND is_profile_note = 1 AND status = 'ACTIVE'
        ORDER BY updated_at DESC, note_id LIMIT 1
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        return {"note_id": None, "content": "", "revision_number": 0, "mentions": ()}
    note = _note_from_row(conn, _note_row(conn, str(row["note_id"])))
    return {
        "note_id": note.note_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "mentions": note.mentioned_person_ids,
    }


def _write_merge_profile_note_revision(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    content: str,
    strategy: str,
    *,
    operation_id: str,
    actor: dict | None,
    source: str | None,
) -> None:
    source_note = _profile_note_snapshot(conn, source_person_id)
    target_note = _profile_note_snapshot(conn, target_person_id)
    if strategy == MergeConflictStrategy.KEEP_SOURCE.value:
        mention_ids = source_note["mentions"]
    elif strategy == MergeConflictStrategy.COMBINE.value:
        mention_ids = tuple(dict.fromkeys([
            *target_note["mentions"], *source_note["mentions"],
        ]))
    else:
        # USER_SELECTED content has no reliable parsed mention provenance.
        mention_ids = target_note["mentions"]
    mentions = _normalize_note_mentions(
        conn,
        target_person_id,
        list(mention_ids),
        historical_person_ids=set(mention_ids),
    )
    created_at = utc_now()
    note_id = target_note["note_id"] or str(uuid.uuid4())
    if target_note["note_id"] is None:
        conn.execute(
            """
            INSERT INTO notes(
                note_id, owner_person_id, subject_type, subject_id,
                is_profile_note, status, created_operation_id, created_at, updated_at
            ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?, ?)
            """,
            (note_id, target_person_id, target_person_id, operation_id, created_at, created_at),
        )
    revision_number = int(target_note["revision_number"]) + 1
    revision_id = _insert_note_revision(
        conn,
        note_id=note_id,
        revision_number=revision_number,
        content=content,
        mentions=mentions,
        actor=actor,
        author_name=str((actor or {}).get("display_name") or ""),
        operation_id=operation_id,
        created_at=created_at,
    )
    _sync_note_reference_evidence(
        conn,
        note_id=note_id,
        owner_person_id=target_person_id,
        revision_id=revision_id,
        mentions=mentions,
        operation_id=operation_id,
        source=source,
        created_at=created_at,
    )
    conn.execute("UPDATE notes SET updated_at = ? WHERE note_id = ?", (created_at, note_id))
    # Compatibility mirror is deliberately last: normalized revision is current truth.
    conn.execute("UPDATE persons SET notes = ? WHERE person_id = ?", (content, target_person_id))


def _require_person_lifecycle_preconditions(conn, person_id, operation_type):
    row = conn.execute("SELECT name, lifecycle_status, deleted_at FROM persons WHERE person_id = ?", (person_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    if operation_type == "archive-person" and row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
        raise KeyError(f"Only active or archived people can be archived: {person_id}")
    if operation_type in {"purge-person", "soft-delete-person"} and row["lifecycle_status"] == "MERGED":
        raise KeyError("Merged source identities cannot be deleted independently")
    _require_no_active_encounter_draft_reference(conn, person_id)
    return row


def _require_no_active_encounter_draft_reference(conn: sqlite3.Connection, person_id: str) -> None:
    for amendment in conn.execute("SELECT target_observation_id FROM photo_reviews WHERE target_observation_id IS NOT NULL AND status = 'IN_PROGRESS'"):
        if _resolve_canonical_person_id(conn, person_id) in _effective_observation_person_ids(conn, str(amendment[0])):
            raise ValueError("Person is referenced by an active Encounter amendment; finish or discard it first")
    selected = conn.execute(
        "SELECT r.review_id FROM photo_review_faces f "
        "JOIN photo_reviews r ON r.review_id = f.review_id "
        "WHERE r.status = 'IN_PROGRESS' AND r.review_phase <> 'LEGACY' "
        "AND (f.person_id = ? OR EXISTS ("
        "SELECT 1 FROM json_each(f.mentioned_person_ids) WHERE value = ?)) LIMIT 1",
        (person_id, person_id),
    ).fetchone()
    if selected is None:
        selected = conn.execute(
            "SELECT review_id FROM photo_reviews WHERE status = 'IN_PROGRESS' "
            "AND review_phase <> 'LEGACY' AND EXISTS ("
            "SELECT 1 FROM json_each(json_extract(event_details, '$.event_mentioned_person_ids')) "
            "WHERE value = ?) LIMIT 1",
            (person_id,),
        ).fetchone()
    if selected is not None:
        raise ValueError(
            f"Person is selected in active Encounter draft {selected['review_id']}; complete or discard that draft first"
        )


def _preview_identity_merge(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    *,
    exclude_operation_id: str | None = None,
) -> dict:
    source_id = str(source_person_id).strip()
    requested_target_id = str(target_person_id).strip()
    if not source_id or not requested_target_id:
        raise ValueError("Merge source and target IDs are required")
    source_row = conn.execute(
        "SELECT * FROM persons WHERE person_id = ?", (source_id,),
    ).fetchone()
    if source_row is None:
        raise KeyError(f"Unknown source person: {source_id}")
    if source_row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
        raise KeyError("Merge source must be an active or archived identity")
    if source_row["deleted_at"] is not None and source_row["lifecycle_status"] != "ARCHIVED":
        raise KeyError("Deleted identities cannot be merged")
    try:
        terminal_target_id = _resolve_canonical_person_id(conn, requested_target_id)
    except KeyError as exc:
        raise KeyError(f"Unknown target person: {requested_target_id}") from exc
    if terminal_target_id == source_id:
        raise ValueError("Merge source and survivor must be different; cycle/self merge rejected")
    target_row = conn.execute(
        "SELECT * FROM persons WHERE person_id = ?", (terminal_target_id,),
    ).fetchone()
    if (
        target_row is None
        or target_row["lifecycle_status"] != "ACTIVE"
        or target_row["deleted_at"] is not None
        or target_row["canonical_person_id"] is not None
    ):
        raise KeyError("Merge target must resolve to a terminal active canonical survivor")
    component_ids = sorted(
        str(row["person_id"])
        for row in conn.execute("SELECT person_id FROM persons ORDER BY person_id").fetchall()
        if _resolve_canonical_person_id(conn, str(row["person_id"])) == source_id
    )
    if source_id not in component_ids:
        component_ids.append(source_id)
        component_ids.sort()
    for person_id in [*component_ids, terminal_target_id]:
        _require_no_active_encounter_draft_reference(conn, person_id)
    relation_pairs: dict[tuple[str, str, str], str] = {}
    for relation in conn.execute(
        "SELECT observation_id, first_person_id, second_person_id, disposition "
        "FROM encounter_relation_decisions WHERE active = 1 AND observation_id IS NOT NULL",
    ).fetchall():
        identities = [
            terminal_target_id if _resolve_canonical_person_id(conn, str(relation[column])) in component_ids
            else _resolve_canonical_person_id(conn, str(relation[column]))
            for column in ("first_person_id", "second_person_id")
        ]
        pair = tuple(sorted(identities))
        if pair[0] == pair[1]:
            continue
        key = (str(relation["observation_id"]), *pair)
        prior = relation_pairs.get(key)
        if prior is not None and prior != str(relation["disposition"]):
            event = _require_observation(conn, str(relation["observation_id"]))
            occasion = json.loads(event["context"] or "{}").get("occasion") or "Unnamed Event"
            caption = f"{occasion}, {str(event['observed_at'] or 'Date unknown')[:10]}, {event['location'] or 'Location unknown'}"
            raise EncounterRelationConflict(
                f"Merge would collapse distinct Encounter Relation decisions in Encounter {relation['observation_id']} ({caption}); find it in Global Events and correct Relations before merging",
                str(relation["observation_id"]),
            )
        relation_pairs[key] = str(relation["disposition"])
    conflicts = _proposed_merge_conflicts(conn, source_row, target_row)
    affected_items = _discover_merge_affected_items(
        conn, component_ids, source_id, terminal_target_id,
        exclude_operation_id=exclude_operation_id,
    )
    return {
        "source_person_id": source_id,
        "requested_target_person_id": requested_target_id,
        "target_person_id": terminal_target_id,
        "canonical_person_id": terminal_target_id,
        "source_lifecycle_status": str(source_row["lifecycle_status"]),
        "target_lifecycle_status": str(target_row["lifecycle_status"]),
        "source_component_person_ids": component_ids,
        "conflicts": conflicts,
        "proposed_conflict_resolutions": conflicts,
        "affected_items": affected_items,
        "affected_item_count": len(affected_items),
        "will_mutate": False,
    }


def _proposed_merge_conflicts(
    conn: sqlite3.Connection, source_row: sqlite3.Row, target_row: sqlite3.Row,
) -> list[dict]:
    source_metadata = json.loads(source_row["metadata"] or "{}")
    target_metadata = json.loads(target_row["metadata"] or "{}")
    ignored_metadata = {"merged_into", "merged_at"}
    source_note = _profile_note_snapshot(conn, str(source_row["person_id"]))
    target_note = _profile_note_snapshot(conn, str(target_row["person_id"]))
    fields: dict[str, tuple[object, object]] = {
        "name": (str(source_row["name"]), str(target_row["name"])),
        "notes": (source_note["content"], target_note["content"]),
    }
    for key in sorted((set(source_metadata) | set(target_metadata)) - ignored_metadata):
        fields[key] = (source_metadata.get(key), target_metadata.get(key))
    conflicts: list[dict] = []
    for field_name, (source_value, target_value) in fields.items():
        if source_value == target_value:
            continue
        combine_valid = field_name in {"tags", "favorite", "notes"}
        if field_name == "tags":
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = _normalize_tags([
                *(target_value or []), *(source_value or []),
            ])
        elif field_name == "favorite":
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = bool(source_value or target_value)
        elif field_name == "notes" and source_value and target_value:
            strategy = MergeConflictStrategy.COMBINE.value
            selected_value = (
                target_value if source_value == target_value
                else f"{target_value}\n\n{source_value}"
            )
        elif target_value in (None, "", [], {}):
            strategy = MergeConflictStrategy.KEEP_SOURCE.value
            selected_value = source_value
        else:
            strategy = MergeConflictStrategy.KEEP_TARGET.value
            selected_value = target_value
        conflicts.append({
            "conflict_id": str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sentriface:merge-preview:{source_row['person_id']}:{target_row['person_id']}:{field_name}",
            )),
            "category": "PROFILE",
            "field_name": field_name,
            "source_value": source_value,
            "target_value": target_value,
            "strategy": strategy,
            "selected_value": selected_value,
            "combine_valid": combine_valid,
            "inverse_data": {
                "source_value": source_value,
                "target_value": target_value,
                "target_field_existed": (
                    field_name in {"name", "notes"} or field_name in target_metadata
                ),
            },
        })
    return conflicts


def _discover_merge_affected_items(
    conn: sqlite3.Connection,
    source_component_ids: list[str],
    source_person_id: str,
    target_person_id: str,
    *,
    exclude_operation_id: str | None = None,
) -> list[dict]:
    component = set(source_component_ids)
    items: dict[tuple[str, str], dict] = {}

    def add(
        item_type: str,
        item_id: object,
        raw_owner: str | None = None,
        *,
        action: str = MergeAffectedAction.UNION_IN_CURRENT_VIEW.value,
        before: dict | None = None,
        after: dict | None = None,
        context: dict | None = None,
    ) -> None:
        normalized_id = str(item_id)
        key = (item_type, normalized_id)
        items[key] = {
            "item_type": item_type,
            "item_id": normalized_id,
            "raw_owner_person_id": raw_owner,
            "effective_owner_person_id": target_person_id,
            "action": action,
            "before_state": before or ({"raw_owner_person_id": raw_owner} if raw_owner else {}),
            "after_state": after or {"canonical_person_id": target_person_id},
            "context": {"raw_provenance_retained": True, **(context or {})},
        }

    source = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (source_person_id,),
    ).fetchone()
    add(
        "PERSON", source_person_id, source_person_id,
        action=MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value,
        before={
            "lifecycle_status": source["lifecycle_status"],
            "canonical_person_id": source["canonical_person_id"],
        },
        after={"lifecycle_status": "MERGED", "canonical_person_id": target_person_id},
    )
    placeholders = ",".join("?" for _ in source_component_ids)
    args = tuple(source_component_ids)

    for row in conn.execute(
        f"SELECT * FROM embeddings WHERE person_id IN ({placeholders}) ORDER BY embedding_id", args,
    ).fetchall():
        owner = _raw_embedding_owner_person_id(conn, row)
        add("EMBEDDING", row["embedding_id"], owner, context={"deleted_at": row["deleted_at"]})
        for path_kind in ("source_image", "crop_path"):
            if row[path_kind]:
                add(
                    "PHOTO", f"{row['embedding_id']}:{path_kind}", owner,
                    context={"path_kind": path_kind, "path": row[path_kind]},
                )
    target_state = conn.execute(
        "SELECT biometric_status, enrollment_status FROM persons WHERE person_id = ?",
        (target_person_id,),
    ).fetchone()
    component_has_active_embedding = conn.execute(
        f"SELECT 1 FROM embeddings WHERE person_id IN ({placeholders}) AND deleted_at IS NULL LIMIT 1",
        args,
    ).fetchone() is not None
    if component_has_active_embedding and target_state["biometric_status"] != "ENROLLED":
        add(
            "CURRENT_STATE", "survivor-biometric-status", target_person_id,
            action=MergeAffectedAction.SELECT_VALUE.value,
            before={
                "biometric_status": target_state["biometric_status"],
                "enrollment_status": target_state["enrollment_status"],
            },
            after={"biometric_status": "ENROLLED", "enrollment_status": "enrolled"},
            context={"derived_from_preserved_embeddings": True},
        )
    for row in conn.execute(
        f"SELECT * FROM init_face_person_exclusions WHERE person_id IN ({placeholders}) ORDER BY session_id, init_face_id, person_id",
        args,
    ).fetchall():
        add(
            "RECOGNITION_EXCLUSION",
            f"{row['session_id']}:{row['init_face_id']}:{row['person_id']}",
            str(row["person_id"]), action=MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value,
        )
    for row in conn.execute(
        f"SELECT * FROM recognition_details WHERE person_id IN ({placeholders}) ORDER BY detail_id", args,
    ).fetchall():
        add("RECOGNITION_HISTORY", row["detail_id"], str(row["person_id"]))
    for row in conn.execute(
        f"SELECT * FROM person_change_history WHERE person_id IN ({placeholders}) ORDER BY change_id", args,
    ).fetchall():
        add("PROFILE_HISTORY", row["change_id"], str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute(
        f"SELECT * FROM biometric_enrollment_history WHERE person_id IN ({placeholders}) ORDER BY enrollment_id", args,
    ).fetchall():
        add("ENROLLMENT_HISTORY", row["enrollment_id"], str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value)
    affected_observation_ids: set[str] = set()
    for row in conn.execute("SELECT * FROM effective_observations ORDER BY observation_id").fetchall():
        corrected = _corrected_observation_person_ids(conn, str(row["observation_id"]))
        if any(person_id in component for person_id in corrected):
            affected_observation_ids.add(str(row["observation_id"]))
            add("OBSERVATION", row["observation_id"], context={"corrected_person_ids": corrected})
    for row in conn.execute("SELECT * FROM observation_media ORDER BY observation_id, media_id").fetchall():
        if str(row["observation_id"]) in affected_observation_ids:
            add(
                "OBSERVATION_MEDIA", f"{row['observation_id']}:{row['media_id']}",
                action=MergeAffectedAction.PRESERVE.value,
            )
    for row in conn.execute(
        f"SELECT * FROM observation_participants WHERE person_id IN ({placeholders}) ORDER BY observation_id, person_id",
        args,
    ).fetchall():
        add(
            "OBSERVATION_PARTICIPANT",
            f"{row['observation_id']}:{row['person_id']}",
            str(row["person_id"]),
            context={"observation_id": row["observation_id"]},
        )
    for row in conn.execute("SELECT * FROM identity_corrections ORDER BY correction_id").fetchall():
        if str(row["from_person_id"]) in component or str(row["to_person_id"]) in component:
            add("CORRECTION", row["correction_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM observation_face_assignments ORDER BY assignment_id").fetchall():
        if str(row["original_person_id"]) in component:
            add(
                "OBSERVATION_FACE_ASSIGNMENT", row["assignment_id"],
                str(row["original_person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    for row in conn.execute("SELECT * FROM photo_review_faces ORDER BY review_id, face_id").fetchall():
        if row["person_id"] is not None and str(row["person_id"]) in component:
            add(
                "PHOTO_REVIEW_DECISION", f"{row['review_id']}:{row['face_id']}",
                str(row["person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    note_ids: set[str] = set()
    for row in conn.execute("SELECT * FROM notes ORDER BY note_id").fetchall():
        owner = str(row["owner_person_id"])
        if owner in component or (row["subject_type"] == "PERSON" and str(row["subject_id"]) in component):
            note_ids.add(str(row["note_id"]))
            add("NOTE", row["note_id"], owner)
    for row in conn.execute("SELECT * FROM note_mentions ORDER BY mention_id").fetchall():
        if str(row["referenced_person_id"]) in component or str(row["note_id"]) in note_ids:
            note_id = str(row["note_id"])
            if note_id not in note_ids:
                note = conn.execute(
                    "SELECT owner_person_id FROM notes WHERE note_id = ?", (note_id,),
                ).fetchone()
                if note is not None:
                    note_ids.add(note_id)
                    add("NOTE", note_id, str(note["owner_person_id"]))
            add("NOTE_MENTION", row["mention_id"], str(row["referenced_person_id"]))
    if note_ids:
        note_placeholders = ",".join("?" for _ in note_ids)
        for row in conn.execute(
            f"SELECT * FROM note_revisions WHERE note_id IN ({note_placeholders}) ORDER BY revision_id",
            tuple(sorted(note_ids)),
        ).fetchall():
            add("NOTE_REVISION", row["revision_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM note_revision_mentions ORDER BY revision_id, referenced_person_id").fetchall():
        if str(row["referenced_person_id"]) in component:
            add(
                "NOTE_REVISION_MENTION",
                f"{row['revision_id']}:{row['referenced_person_id']}",
                str(row["referenced_person_id"]), action=MergeAffectedAction.PRESERVE.value,
            )
    affected_graph_people = component | {target_person_id}
    for row in conn.execute("SELECT * FROM relationship_evidence ORDER BY evidence_id").fetchall():
        if str(row["source_person_id"]) in affected_graph_people or str(row["target_person_id"]) in affected_graph_people:
            add("GRAPH_EVIDENCE", row["evidence_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM person_associations ORDER BY association_id").fetchall():
        if str(row["source_person_id"]) in component or str(row["target_person_id"]) in component:
            add("MANUAL_ASSOCIATION", row["association_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT * FROM merge_operations ORDER BY merge_operation_id").fetchall():
        if str(row["source_person_id"]) in component or str(row["target_person_id"]) in component:
            add("MERGE_HISTORY", row["merge_operation_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT operation_id, affected_entities FROM operation_journal ORDER BY operation_id").fetchall():
        if str(row["operation_id"]) == exclude_operation_id:
            continue
        entities = json.loads(row["affected_entities"] or "[]")
        if any(str(item.get("entity_id")) in component for item in entities if isinstance(item, dict)):
            add("OPERATION_HISTORY", row["operation_id"], action=MergeAffectedAction.PRESERVE.value)
    for row in conn.execute("SELECT operation_id, result FROM person_operations ORDER BY operation_id").fetchall():
        payload = json.loads(row["result"] or "{}")
        if any(
            value in component
            for key, value in payload.items()
            if key.endswith("person_id") and isinstance(value, str)
        ):
            add("LEGACY_OPERATION_HISTORY", row["operation_id"], action=MergeAffectedAction.PRESERVE.value)
    return [items[key] for key in sorted(items)]


def _resolve_merge_conflicts(
    proposed: list[dict],
    requested: list[dict] | dict[str, dict | str] | None,
) -> list[dict]:
    overrides: dict[str, dict] = {}
    if isinstance(requested, dict):
        for field_name, value in requested.items():
            overrides[str(field_name)] = (
                dict(value) if isinstance(value, dict) else {"strategy": str(value)}
            )
    elif requested is not None:
        if not isinstance(requested, list):
            raise ValueError("Conflict resolutions must be a list or field mapping")
        for item in requested:
            if not isinstance(item, dict) or not str(item.get("field_name") or "").strip():
                raise ValueError("Each conflict resolution requires field_name")
            overrides[str(item["field_name"])] = dict(item)
    result: list[dict] = []
    known_fields = {str(item["field_name"]) for item in proposed}
    unknown_fields = set(overrides) - known_fields
    if unknown_fields:
        raise ValueError("Unknown merge conflict fields: " + ", ".join(sorted(unknown_fields)))
    for conflict in proposed:
        resolved = dict(conflict)
        override = overrides.get(str(conflict["field_name"]), {})
        strategy = str(override.get("strategy") or resolved["strategy"]).strip().upper()
        try:
            typed_strategy = MergeConflictStrategy(strategy)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge conflict strategy: {strategy}") from exc
        if typed_strategy is MergeConflictStrategy.KEEP_SOURCE:
            selected = conflict["source_value"]
        elif typed_strategy is MergeConflictStrategy.KEEP_TARGET:
            selected = conflict["target_value"]
        elif typed_strategy is MergeConflictStrategy.COMBINE:
            if not conflict.get("combine_valid"):
                raise ValueError(f"COMBINE is not valid for profile field {conflict['field_name']}")
            selected = _combine_merge_value(
                str(conflict["field_name"]), conflict["source_value"], conflict["target_value"],
            )
        else:
            if "selected_value" not in override:
                raise ValueError(
                    f"USER_SELECTED requires selected_value for {conflict['field_name']}"
                )
            selected = override["selected_value"]
        resolved["strategy"] = typed_strategy.value
        resolved["selected_value"] = selected
        resolved.pop("combine_valid", None)
        result.append(resolved)
    return result


def _combine_merge_value(field_name: str, source_value, target_value):
    if field_name == "tags":
        return _normalize_tags([*(target_value or []), *(source_value or [])])
    if field_name == "favorite":
        return bool(source_value or target_value)
    if field_name == "notes":
        parts = [str(value).strip() for value in (target_value, source_value) if str(value or "").strip()]
        return "\n\n".join(dict.fromkeys(parts))
    raise ValueError(f"COMBINE is not valid for profile field {field_name}")


def _merge_inventory_with_profile_changes(
    inventory: list[dict], conflicts: list[dict], source_person_id: str, target_person_id: str,
) -> list[dict]:
    result = [dict(item) for item in inventory]
    for conflict in conflicts:
        result.append({
            "item_type": "PROFILE_FIELD",
            "item_id": str(conflict["field_name"]),
            "raw_owner_person_id": source_person_id,
            "effective_owner_person_id": target_person_id,
            "action": MergeAffectedAction.SELECT_VALUE.value,
            "before_state": {
                "source_value": conflict["source_value"],
                "target_value": conflict["target_value"],
            },
            "after_state": {"resulting_value": conflict["selected_value"]},
            "context": {"strategy": conflict["strategy"], "raw_provenance_retained": True},
        })
    return sorted(result, key=lambda item: (item["item_type"], item["item_id"]))


def _apply_merge_profile_resolutions(
    conn: sqlite3.Connection,
    source_person_id: str,
    target_person_id: str,
    conflicts: list[dict],
    *,
    operation_id: str,
    actor: dict | None,
    source: str | None,
) -> None:
    row = conn.execute(
        "SELECT name, notes, metadata FROM persons WHERE person_id = ?", (target_person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown merge survivor: {target_person_id}")
    name = str(row["name"])
    metadata = json.loads(row["metadata"] or "{}")
    selected_notes: str | None = None
    note_strategy: str | None = None
    for conflict in conflicts:
        field_name = str(conflict["field_name"])
        selected = conflict["selected_value"]
        if field_name == "name":
            name = str(selected or "").strip()
            if not name:
                raise ValueError("Merge survivor name cannot be empty")
        elif field_name == "notes":
            selected_notes = str(selected or "").strip()
            note_strategy = str(conflict["strategy"])
        else:
            if selected is None and not conflict["inverse_data"].get("target_field_existed"):
                metadata.pop(field_name, None)
            else:
                metadata[field_name] = selected
    conn.execute(
        "UPDATE persons SET name = ?, metadata = ? WHERE person_id = ?",
        (name, json.dumps(metadata, separators=(",", ":"), sort_keys=True), target_person_id),
    )
    if selected_notes is not None and note_strategy is not None:
        _write_merge_profile_note_revision(
            conn,
            source_person_id,
            target_person_id,
            selected_notes,
            note_strategy,
            operation_id=operation_id,
            actor=actor,
            source=source,
        )


def _synchronize_survivor_biometric_state(
    conn: sqlite3.Connection, target_person_id: str,
) -> None:
    has_embedding = any(
        _effective_embedding_owner_person_id(conn, row) == target_person_id
        for row in conn.execute(
            "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
        ).fetchall()
    )
    if has_embedding:
        conn.execute(
            "UPDATE persons SET biometric_status = 'ENROLLED', enrollment_status = 'enrolled' WHERE person_id = ?",
            (target_person_id,),
        )


def _list_embeddings_in_transaction(conn: sqlite3.Connection) -> list[EmbeddingRecord]:
    return _eligible_source_samples(conn)


def _set_canonical_person_id_in_transaction(
    conn: sqlite3.Connection,
    person_id: str,
    canonical_person_id: str,
) -> dict:
    """Update canonical state on the caller's connection without journaling or committing."""
    normalized_person_id = str(person_id).strip()
    normalized_target_id = str(canonical_person_id).strip()
    if not normalized_person_id or not normalized_target_id:
        raise ValueError("Source and canonical person IDs are required")
    source_row = conn.execute(
        "SELECT lifecycle_status FROM persons WHERE person_id = ?",
        (normalized_person_id,),
    ).fetchone()
    if source_row is None:
        raise KeyError(f"Unknown person: {normalized_person_id}")
    if source_row["lifecycle_status"] not in {"ACTIVE", "ARCHIVED"}:
        raise KeyError("Only active or archived identities can receive a canonical mapping")
    resolved_target = _resolve_canonical_person_id(conn, normalized_target_id)
    if resolved_target == normalized_person_id:
        raise ValueError("Canonical identity cannot reference itself or create a cycle")
    target_row = conn.execute(
        "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
        (resolved_target,),
    ).fetchone()
    if target_row is None:
        raise KeyError(f"Unknown canonical person: {normalized_target_id}")
    if target_row["lifecycle_status"] != "ACTIVE" or target_row["deleted_at"] is not None:
        raise KeyError("Canonical identity must resolve to an active person")
    changed_at = utc_now()
    try:
        conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = 'MERGED', canonical_person_id = ?,
                deleted_at = COALESCE(deleted_at, ?), lifecycle_changed_at = ?
            WHERE person_id = ?
            """,
            (resolved_target, changed_at, changed_at, normalized_person_id),
        )
    except sqlite3.IntegrityError as exc:
        if "cycle" in str(exc).lower() or "check constraint" in str(exc).lower():
            raise ValueError(
                "Canonical identity cannot reference itself or create a cycle"
            ) from exc
        raise
    return {
        "person_id": normalized_person_id,
        "canonical_person_id": resolved_target,
        "lifecycle_status": "MERGED",
        "mapped": True,
    }


def _insert_merge_manifest_in_transaction(
    conn: sqlite3.Connection,
    *,
    merge_operation_id: str,
    source_person_id: str,
    target_person_id: str,
    operation_journal_id: str,
    actor: dict | None = None,
    reason: str | None = None,
    context: dict | None = None,
    affected_items: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    created_at: str | None = None,
) -> MergeOperation:
    """Persist immutable merge provenance on the caller-owned transaction."""
    normalized_merge_id = str(merge_operation_id).strip()
    normalized_source_id = str(source_person_id).strip()
    normalized_target_id = str(target_person_id).strip()
    normalized_journal_id = str(operation_journal_id).strip()
    if not all((normalized_merge_id, normalized_source_id, normalized_target_id,
                normalized_journal_id)):
        raise ValueError("Merge, source, target, and journal IDs are required")
    if normalized_merge_id != normalized_journal_id:
        raise ValueError("Merge operation ID must match its journal operation ID")
    terminal_target_id = _resolve_canonical_person_id(conn, normalized_target_id)
    if normalized_source_id == terminal_target_id:
        raise ValueError("Merge source and survivor must be different")
    source_row = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (normalized_source_id,),
    ).fetchone()
    target_row = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (terminal_target_id,),
    ).fetchone()
    if source_row is None or target_row is None:
        raise KeyError("Merge source and target must both exist")
    journal = conn.execute(
        "SELECT operation_type, status, actor FROM operation_journal WHERE operation_id = ?",
        (normalized_journal_id,),
    ).fetchone()
    if journal is None:
        raise KeyError(f"Unknown operation journal entry: {normalized_journal_id}")
    if journal["status"] != "STARTED":
        raise ValueError("Merge manifest must be recorded while its journal is STARTED")
    if journal["operation_type"] != "identity.merge":
        raise ValueError("Merge manifest requires an identity.merge journal operation")
    _, actor_payload, _ = _operation_actor_snapshot(actor)
    if actor_payload != journal["actor"]:
        raise ValueError("Merge manifest actor must match its operation journal actor")
    if target_row["lifecycle_status"] != "ACTIVE" or target_row["canonical_person_id"] is not None:
        raise ValueError("Merge survivor must be the terminal active canonical identity")
    target_deleted = conn.execute(
        "SELECT deleted_at FROM persons WHERE person_id = ?", (terminal_target_id,),
    ).fetchone()[0]
    if target_deleted is not None:
        raise ValueError("Merge survivor must be the terminal active canonical identity")
    _, context_payload = _journal_json_object(context, "merge context")
    timestamp = created_at or utc_now()
    conn.execute(
        """
        INSERT INTO merge_operations(
            merge_operation_id, source_person_id, target_person_id, actor, created_at,
            previous_source_lifecycle_status, previous_target_lifecycle_status,
            previous_source_canonical_person_id, previous_target_canonical_person_id,
            reason, context, operation_journal_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_merge_id, normalized_source_id, terminal_target_id,
            actor_payload, timestamp, source_row["lifecycle_status"],
            target_row["lifecycle_status"], source_row["canonical_person_id"],
            target_row["canonical_person_id"], _optional_text(reason),
            context_payload, normalized_journal_id,
        ),
    )
    for item in affected_items or []:
        item_type = str(item.get("item_type") or "").strip().upper()
        item_id = str(item.get("item_id") or "").strip()
        if not item_type or not item_id:
            raise ValueError("Affected merge items require item_type and item_id")
        raw_owner_person_id = _optional_text(
            item.get("raw_owner_person_id", item.get("previous_person_id")),
        )
        effective_owner_person_id = _optional_text(
            item.get("effective_owner_person_id", item.get("effective_person_id")),
        )
        default_action = (
            MergeAffectedAction.UNION_IN_CURRENT_VIEW.value
            if item_type in MERGE_COLLECTION_ITEM_TYPES
            else MergeAffectedAction.REINTERPRET_CANONICAL_OWNER.value
        )
        action = str(item.get("action") or default_action).strip().upper()
        try:
            MergeAffectedAction(action)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge affected-item action: {action}") from exc
        _, item_context = _journal_json_object(item.get("context"), "affected item context")
        _, before_state = _journal_json_object(item.get("before_state"), "affected item before state")
        _, after_state = _journal_json_object(item.get("after_state"), "affected item after state")
        conn.execute(
            """
            INSERT INTO merge_affected_items(
                merge_operation_id, item_type, item_id, previous_person_id,
                effective_person_id, context, raw_owner_person_id,
                effective_owner_person_id, action, before_state, after_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_merge_id, item_type, item_id,
                raw_owner_person_id, effective_owner_person_id, item_context,
                raw_owner_person_id, effective_owner_person_id, action,
                before_state, after_state,
            ),
        )
    for conflict in conflicts or []:
        category = str(conflict.get("category") or "").strip().upper()
        field_name = str(conflict.get("field_name") or conflict.get("field") or "").strip()
        if not category or not field_name:
            raise ValueError("Merge conflicts require category and field_name")
        strategy_value = str(conflict.get("strategy") or "").strip().upper()
        try:
            strategy = MergeConflictStrategy(strategy_value)
        except ValueError as exc:
            raise ValueError(f"Unsupported merge conflict strategy: {strategy_value}") from exc
        source_value = conflict.get("source_value")
        target_value = conflict.get("target_value")
        selected_value = conflict.get("selected_value")
        if strategy is MergeConflictStrategy.KEEP_SOURCE and selected_value != source_value:
            raise ValueError("KEEP_SOURCE must select the source value")
        if strategy is MergeConflictStrategy.KEEP_TARGET and selected_value != target_value:
            raise ValueError("KEEP_TARGET must select the target value")
        inverse_data = conflict.get("inverse_data")
        if inverse_data is None:
            inverse_data = {
                "source_value": source_value,
                "target_value": target_value,
            }
        _, inverse_payload = _journal_json_object(inverse_data, "merge conflict inverse data")
        conn.execute(
            """
            INSERT INTO merge_conflict_resolutions(
                conflict_id, merge_operation_id, category, field_name,
                source_value, target_value, strategy, selected_value, inverse_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(conflict.get("conflict_id") or uuid.uuid4()), normalized_merge_id,
                category, field_name, _json_value_payload(source_value, "source value"),
                _json_value_payload(target_value, "target value"), strategy.value,
                _json_value_payload(selected_value, "selected value"), inverse_payload,
            ),
        )
    operation = _get_merge_operation(conn, normalized_merge_id)
    if operation is None:
        raise RuntimeError("Stored merge manifest could not be read")
    return operation


def _get_merge_operation(
    conn: sqlite3.Connection, merge_operation_id: str,
) -> MergeOperation | None:
    row = conn.execute(
        "SELECT * FROM merge_operations WHERE merge_operation_id = ?",
        (str(merge_operation_id).strip(),),
    ).fetchone()
    if row is None:
        return None
    item_rows = conn.execute(
        """
        SELECT * FROM merge_affected_items
        WHERE merge_operation_id = ? ORDER BY item_type, item_id
        """,
        (row["merge_operation_id"],),
    ).fetchall()
    conflict_rows = conn.execute(
        """
        SELECT * FROM merge_conflict_resolutions
        WHERE merge_operation_id = ? ORDER BY category, field_name, conflict_id
        """,
        (row["merge_operation_id"],),
    ).fetchall()
    return MergeOperation(
        merge_operation_id=str(row["merge_operation_id"]),
        source_person_id=str(row["source_person_id"]),
        target_person_id=str(row["target_person_id"]),
        actor=json.loads(row["actor"]),
        created_at=str(row["created_at"]),
        previous_source_lifecycle_status=str(row["previous_source_lifecycle_status"]),
        previous_target_lifecycle_status=str(row["previous_target_lifecycle_status"]),
        previous_source_canonical_person_id=row["previous_source_canonical_person_id"],
        previous_target_canonical_person_id=row["previous_target_canonical_person_id"],
        reason=row["reason"],
        context=json.loads(row["context"]),
        operation_journal_id=str(row["operation_journal_id"]),
        affected_items=tuple(MergeAffectedItem(
            item_type=str(item["item_type"]),
            item_id=str(item["item_id"]),
            raw_owner_person_id=item["raw_owner_person_id"],
            effective_owner_person_id=item["effective_owner_person_id"],
            action=MergeAffectedAction(str(item["action"])),
            before_state=json.loads(item["before_state"]),
            after_state=json.loads(item["after_state"]),
            context=json.loads(item["context"]),
        ) for item in item_rows),
        conflicts=tuple(MergeConflictResolution(
            conflict_id=str(item["conflict_id"]),
            category=str(item["category"]),
            field_name=str(item["field_name"]),
            source_value=json.loads(item["source_value"]),
            target_value=json.loads(item["target_value"]),
            strategy=MergeConflictStrategy(str(item["strategy"])),
            selected_value=json.loads(item["selected_value"]),
            inverse_data=json.loads(item["inverse_data"]),
        ) for item in conflict_rows),
    )


def _resolve_canonical_person_id(conn: sqlite3.Connection, person_id: str) -> str:
    current_id = str(person_id).strip()
    if not current_id:
        raise ValueError("Person ID is required")
    visited: set[str] = set()
    while True:
        if current_id in visited:
            raise RuntimeError("Canonical identity cycle detected")
        visited.add(current_id)
        row = conn.execute(
            "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
            (current_id,),
        ).fetchone()
        if row is None:
            if len(visited) == 1:
                raise KeyError(f"Unknown person: {current_id}")
            raise RuntimeError(f"Canonical identity target does not exist: {current_id}")
        canonical_person_id = row["canonical_person_id"]
        if row["lifecycle_status"] != "MERGED":
            if canonical_person_id is not None:
                raise RuntimeError("Non-merged identity has an invalid canonical mapping")
            return current_id
        if not canonical_person_id:
            raise RuntimeError("Merged identity has no canonical target")
        current_id = str(canonical_person_id)


def _person_historical_counts(conn: sqlite3.Connection, person_id: str) -> dict:
    return {
        "retained_embeddings": int(conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_sightings": int(conn.execute(
            "SELECT COUNT(*) FROM recognition_details WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_profile_changes": int(conn.execute(
            "SELECT COUNT(*) FROM person_change_history WHERE person_id = ?", (person_id,),
        ).fetchone()[0]),
        "retained_associations": int(conn.execute(
            """
            SELECT COUNT(*) FROM person_associations
            WHERE source_person_id = ? OR target_person_id = ?
            """,
            (person_id, person_id),
        ).fetchone()[0]),
    }


def _canonical_person_pair(source_person_id: str, target_person_id: str) -> tuple[str, str]:
    source = source_person_id.strip()
    target = target_person_id.strip()
    if not source or not target:
        raise KeyError("Choose two people to associate")
    if source == target:
        raise KeyError("A person cannot be associated with themselves")
    return tuple(sorted((source, target)))


def _require_active_people(conn: sqlite3.Connection, *person_ids: str) -> None:
    for person_id in person_ids:
        row = conn.execute(
            """
            SELECT 1 FROM persons
            WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
            """,
            (person_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown active person: {person_id}")


def _new_person_association(
    person_a_id: str,
    person_b_id: str,
    actor_name: str,
    association_origin: str = "manual",
) -> PersonAssociation:
    created_at = utc_now()
    return PersonAssociation(
        association_id=str(uuid.uuid4()),
        source_person_id=person_a_id,
        target_person_id=person_b_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=actor_name,
        association_origin=association_origin,
    )


def _insert_person_association(
    conn: sqlite3.Connection,
    association: PersonAssociation,
) -> None:
    conn.execute(
        """
        INSERT INTO person_associations(
            association_id, source_person_id, target_person_id,
            relationship_type, created_at, updated_at, created_by, association_origin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            association.association_id,
            association.source_person_id,
            association.target_person_id,
            association.relationship_type,
            association.created_at,
            association.updated_at,
            association.created_by,
            association.association_origin,
        ),
    )


def _person_association_from_row(row: sqlite3.Row) -> PersonAssociation:
    return PersonAssociation(
        association_id=row["association_id"],
        source_person_id=row["source_person_id"],
        target_person_id=row["target_person_id"],
        relationship_type=row["relationship_type"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row["created_by"],
        association_origin=row["association_origin"] if "association_origin" in row.keys() else "manual",
    )


def _legacy_create_note_associations(
    conn: sqlite3.Connection,
    owner_person_id: str,
    notes: str,
    actor_name: str,
    explicit_person_ids: list[str],
) -> list[PersonAssociation]:
    if not explicit_person_ids:
        return []
    active_rows = conn.execute(
        """
        SELECT person_id, name FROM persons
        WHERE lifecycle_status = 'ACTIVE' AND deleted_at IS NULL AND person_id <> ?
        """,
        (owner_person_id,),
    ).fetchall()
    rows_by_id = {row["person_id"]: row for row in active_rows}
    mentioned_ids = {
        str(person_id)
        for person_id in explicit_person_ids
        if str(person_id) in rows_by_id
    }
    created: list[PersonAssociation] = []
    for mentioned_id in sorted(mentioned_ids):
        person_a_id, person_b_id = _canonical_person_pair(owner_person_id, mentioned_id)
        existing = conn.execute(
            "SELECT 1 FROM person_associations WHERE source_person_id = ? AND target_person_id = ? AND relationship_type = 'ASSOCIATED_WITH'",
            (person_a_id, person_b_id),
        ).fetchone()
        if existing is not None:
            continue
        association = _new_person_association(
            person_a_id, person_b_id, actor_name or "SentriFace", "automatic_mention",
        )
        _insert_person_association(conn, association)
        created.append(association)
    return created


def _person_from_row(row: sqlite3.Row) -> Person:
    return Person(
        person_id=row["person_id"],
        name=row["name"],
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        deleted_at=row["deleted_at"],
        enrollment_status=row["enrollment_status"],
        notes=row["notes"] if "notes" in row.keys() else "",
        lifecycle_status=row["lifecycle_status"] if "lifecycle_status" in row.keys() else (
            "ARCHIVED" if row["deleted_at"] else "ACTIVE"
        ),
        canonical_person_id=(
            row["canonical_person_id"] if "canonical_person_id" in row.keys() else None
        ),
        identity_status=(row["identity_status"] if "identity_status" in row.keys() else "IDENTIFIED"),
        biometric_status=(row["biometric_status"] if "biometric_status" in row.keys() else "NO_FACE"),
    )


def _insert_person_change(conn: sqlite3.Connection, change: PersonChange) -> None:
    conn.execute(
        """
        INSERT INTO person_change_history(
            change_id, person_id, previous_name, new_name,
            previous_rank, new_rank, previous_country, new_country,
            previous_importance, new_importance, previous_status, new_status,
            previous_notes, new_notes, editor_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            change.change_id,
            change.person_id,
            change.previous_name,
            change.new_name,
            change.previous_rank,
            change.new_rank,
            change.previous_country,
            change.new_country,
            change.previous_importance,
            change.new_importance,
            change.previous_status,
            change.new_status,
            change.previous_notes,
            change.new_notes,
            change.editor_name,
            change.created_at,
        ),
    )


def _mark_person_enrolled(conn: sqlite3.Connection, person_id: str) -> None:
    row = conn.execute(
        """
        SELECT name, metadata, enrollment_status, notes
        FROM persons
        WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown person: {person_id}")
    conn.execute(
        "UPDATE persons SET biometric_status = 'ENROLLED' WHERE person_id = ?",
        (person_id,),
    )
    if row["enrollment_status"] != "placeholder":
        return
    conn.execute(
        "UPDATE persons SET enrollment_status = 'enrolled' WHERE person_id = ?",
        (person_id,),
    )
    metadata = json.loads(row["metadata"])
    _insert_person_change(
        conn,
        PersonChange(
            change_id=str(uuid.uuid4()),
            person_id=person_id,
            previous_name=row["name"],
            new_name=row["name"],
            previous_rank=metadata.get("rank") or "",
            new_rank=metadata.get("rank") or "",
            previous_country=metadata.get("country") or "",
            new_country=metadata.get("country") or "",
            previous_importance=metadata.get("importance") or "",
            new_importance=metadata.get("importance") or "",
            previous_status="placeholder",
            new_status="enrolled",
            previous_notes=row["notes"],
            new_notes=row["notes"],
            editor_name="SentriFace",
        ),
    )


def _placeholder_name_conflict(exc: sqlite3.IntegrityError) -> KeyError:
    return KeyError(
        "A placeholder with this name already exists. Add a photograph to that profile or choose a different name."
    )


def _journal_json_object(value: dict | None, label: str) -> tuple[dict, str]:
    normalized = value or {}
    if not isinstance(normalized, dict):
        raise ValueError(f"Operation {label} must be an object")
    try:
        payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Operation {label} must contain JSON-compatible values") from exc
    return normalized, payload


def _journal_json_array(value: list[dict] | None, label: str) -> tuple[list[dict], str]:
    normalized = value or []
    if not isinstance(normalized, list) or any(not isinstance(item, dict) for item in normalized):
        raise ValueError(f"Operation {label} must be a list of objects")
    try:
        payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Operation {label} must contain JSON-compatible values") from exc
    return normalized, payload


def _json_value_payload(value, label: str) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Merge {label} must be JSON-compatible") from exc


def _operation_actor_snapshot(actor: dict | None) -> tuple[dict, str, str | None]:
    if actor is not None and not isinstance(actor, dict):
        raise ValueError("Operation actor must be an AuthUser-compatible object")
    source = actor or {}
    roles = source.get("roles") or []
    if not isinstance(roles, (list, tuple)):
        raise ValueError("Operation actor roles must be a list")
    snapshot = {
        key: str(source[key])
        for key in ("user_id", "username", "display_name")
        if source.get(key) is not None
    }
    snapshot["roles"] = [str(role) for role in roles]
    _, payload = _journal_json_object(snapshot, "actor")
    return snapshot, payload, snapshot.get("user_id")


def _begin_journal_operation(
    conn: sqlite3.Connection,
    operation_type: str,
    *,
    operation_id: str | None = None,
    actor: dict | None = None,
    source: str | None = None,
    context: dict | None = None,
    affected_entities: list[dict] | None = None,
    details: dict | None = None,
) -> dict:
    normalized_type = str(operation_type).strip()
    if not normalized_type:
        raise ValueError("Operation type is required")
    normalized_id = str(operation_id or uuid.uuid4()).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    _, actor_payload, actor_user_id = _operation_actor_snapshot(actor)
    _, context_payload = _journal_json_object(context, "context")
    _, entities_payload = _journal_json_array(affected_entities, "affected entities")
    _, details_payload = _journal_json_object(details, "details")
    normalized_source = str(source).strip() if source is not None else None
    normalized_source = normalized_source or None
    created_at = utc_now()
    try:
        conn.execute(
            """
            INSERT INTO operation_journal(
                operation_id, operation_type, status, actor_user_id, actor,
                source, context, affected_entities, details, created_at
            ) VALUES (?, ?, 'STARTED', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_id,
                normalized_type,
                actor_user_id,
                actor_payload,
                normalized_source,
                context_payload,
                entities_payload,
                details_payload,
                created_at,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if conn.execute(
            "SELECT 1 FROM operation_journal WHERE operation_id = ?",
            (normalized_id,),
        ).fetchone():
            raise KeyError(f"Operation ID already exists: {normalized_id}") from exc
        raise
    conn.execute(
        """
        INSERT INTO operation_journal_status_history(
            transition_id, operation_id, from_status, to_status, details, created_at
        ) VALUES (?, ?, NULL, 'STARTED', '{}', ?)
        """,
        (str(uuid.uuid4()), normalized_id, created_at),
    )
    return _get_journal_operation(conn, normalized_id)


def _transition_journal_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    target_status: str,
    details: dict | None = None,
) -> dict:
    normalized_id = str(operation_id).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    if target_status not in OPERATION_STATUSES or target_status == "STARTED":
        raise ValueError(f"Unsupported operation status: {target_status}")
    row = conn.execute(
        "SELECT status FROM operation_journal WHERE operation_id = ?",
        (normalized_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown operation: {normalized_id}")
    current_status = str(row["status"])
    if target_status not in OPERATION_STATUS_TRANSITIONS[current_status]:
        raise ValueError(
            f"Invalid operation status transition: {current_status} -> {target_status}"
        )
    _, details_payload = _journal_json_object(details, "transition details")
    transitioned_at = utc_now()
    cursor = conn.execute(
        """
        UPDATE operation_journal
        SET status = ?, completed_at = ?
        WHERE operation_id = ? AND status = ?
        """,
        (target_status, transitioned_at, normalized_id, current_status),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Operation status changed concurrently; transition was not applied")
    conn.execute(
        """
        INSERT INTO operation_journal_status_history(
            transition_id, operation_id, from_status, to_status, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            normalized_id,
            current_status,
            target_status,
            details_payload,
            transitioned_at,
        ),
    )
    return _get_journal_operation(conn, normalized_id)


def _get_journal_operation(conn: sqlite3.Connection, operation_id: str) -> dict | None:
    normalized_id = str(operation_id).strip()
    if not normalized_id:
        raise ValueError("Operation ID is required")
    row = conn.execute(
        "SELECT * FROM operation_journal WHERE operation_id = ?",
        (normalized_id,),
    ).fetchone()
    if row is None:
        return None
    history = conn.execute(
        """
        SELECT transition_id, from_status, to_status, details, created_at
        FROM operation_journal_status_history
        WHERE operation_id = ?
        ORDER BY created_at, rowid
        """,
        (normalized_id,),
    ).fetchall()
    return {
        "operation_id": row["operation_id"],
        "operation_type": row["operation_type"],
        "status": row["status"],
        "actor": json.loads(row["actor"]),
        "source": row["source"],
        "context": json.loads(row["context"]),
        "affected_entities": json.loads(row["affected_entities"]),
        "details": json.loads(row["details"]),
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "status_history": [
            {
                "transition_id": item["transition_id"],
                "from_status": item["from_status"],
                "to_status": item["to_status"],
                "details": json.loads(item["details"]),
                "created_at": item["created_at"],
            }
            for item in history
        ],
    }


def _existing_committed_operation_result(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    operation = _get_journal_operation(conn, operation_id)
    if operation is None:
        return None
    if operation["operation_type"] != operation_type:
        raise KeyError(f"Operation ID already exists: {operation_id}")
    if operation["status"] != "COMMITTED":
        raise RuntimeError(
            f"Operation {operation_id} is {operation['status']} and cannot be retried"
        )
    history = operation["status_history"]
    return dict(history[-1]["details"]) if history else {}


def _existing_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    if not operation_id.strip():
        raise KeyError("operation_id is required")
    row = conn.execute(
        """
        SELECT operation_type, result
        FROM person_operations
        WHERE operation_id = ?
        """,
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    if row["operation_type"] != operation_type:
        raise KeyError("operation_id was already used for a different operation")
    return json.loads(row["result"])


def _begin_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
) -> dict | None:
    conn.execute("BEGIN IMMEDIATE")
    return _existing_person_operation(conn, operation_id, operation_type)


def _record_person_operation(
    conn: sqlite3.Connection,
    operation_id: str,
    operation_type: str,
    result: dict,
) -> None:
    conn.execute(
        """
        INSERT INTO person_operations(operation_id, operation_type, result, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            operation_id,
            operation_type,
            json.dumps(result, separators=(",", ":")),
            utc_now(),
        ),
    )


def _normalize_tags(values: list | tuple | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        tag = str(value).strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        normalized.append(tag[:48])
        seen.add(key)
        if len(normalized) == 20:
            break
    return normalized


def _pending_from_row(row: sqlite3.Row) -> PendingAddition:
    raw_landmarks = json.loads(row["landmarks"]) if row["landmarks"] else None
    landmarks = tuple(tuple(point) for point in raw_landmarks) if raw_landmarks else None
    matches = [_person_match_from_json(item) for item in json.loads(row["matches"])]
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
        quality=QualityReport(
            status=QualityStatus(row["quality_status"]),
            score=row["pending_quality_score"],
            reasons=tuple(json.loads(row["quality_reasons"])),
        ),
        created_at=row["created_at"],
    )


def _person_match_from_json(item: dict) -> PersonMatch:
    if "embedding_ids" in item:
        embedding_ids = tuple(item["embedding_ids"])
    else:
        embedding_ids = (item["embedding_id"],)
    return PersonMatch(
        person_id=item["person_id"],
        score=item["score"],
        embedding_ids=embedding_ids,
        embeddings_matched=item.get("embeddings_matched", len(embedding_ids)),
    )


def _embedding_from_row(
    row: sqlite3.Row, *, raw_person_id: str | None = None,
    canonical_person_id: str | None = None,
) -> EmbeddingRecord:
    return EmbeddingRecord(
        embedding_id=row["embedding_id"],
        person_id=raw_person_id or row["person_id"],
        vector=_unpack_embedding(row["vector"]),
        quality_score=row["quality_score"],
        source_image=row["source_image"],
        crop_path=row["crop_path"],
        created_at=row["created_at"],
        canonical_person_id=canonical_person_id,
        recognition_state=row["recognition_state"] if "recognition_state" in row.keys() else "GOOD",
    )


def _raw_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    """Return immutable enrollment ownership, including pre-P8-C moved faces."""
    embedding_id = str(row["embedding_id"])
    latest = conn.execute(
        """
        SELECT to_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at DESC, correction_id DESC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    stored_owner = str(row["person_id"])
    if latest is None or stored_owner != str(latest["to_person_id"]):
        return stored_owner
    correction = conn.execute(
        """
        SELECT from_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at ASC, correction_id ASC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    return str(correction["from_person_id"] if correction is not None else stored_owner)


def _current_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    """Return the latest corrected owner without rewriting raw ownership."""
    embedding_id = str(row["embedding_id"])
    correction = conn.execute(
        """
        SELECT to_person_id FROM identity_corrections
        WHERE embedding_id = ? AND correction_type = 'FACE_OWNERSHIP'
        ORDER BY created_at DESC, correction_id DESC LIMIT 1
        """,
        (embedding_id,),
    ).fetchone()
    return str(correction["to_person_id"] if correction is not None else row["person_id"])


def _effective_embedding_owner_person_id(
    conn: sqlite3.Connection, row: sqlite3.Row,
) -> str:
    return _resolve_canonical_person_id(
        conn, _current_embedding_owner_person_id(conn, row),
    )


def _recognition_detail_from_row(row: sqlite3.Row) -> RecognitionDetail:
    return RecognitionDetail(
        detail_id=row["detail_id"],
        embedding_id=row["embedding_id"],
        person_id=row["person_id"],
        image_id=row["image_id"],
        image_path=row["image_path"],
        name=row["name"],
        decision=row["decision"],
        seen_date=row["seen_date"],
        seen_time=row["seen_time"],
        place_seen=row["place_seen"],
        individual_count=row["individual_count"],
        event_occasion=row["event_occasion"],
        rank=row["rank"],
        country=row["country"],
        importance=row["importance"],
        added_by=row["added_by"],
        notes=row["notes"] if "notes" in row.keys() else "",
        created_at=row["created_at"],
    )


def _person_change_from_row(row: sqlite3.Row) -> PersonChange:
    return PersonChange(
        change_id=row["change_id"],
        person_id=row["person_id"],
        previous_name=row["previous_name"],
        new_name=row["new_name"],
        previous_rank=row["previous_rank"],
        new_rank=row["new_rank"],
        previous_country=row["previous_country"],
        new_country=row["new_country"],
        previous_importance=row["previous_importance"],
        new_importance=row["new_importance"],
        previous_status=row["previous_status"],
        new_status=row["new_status"],
        previous_notes=row["previous_notes"] if "previous_notes" in row.keys() else None,
        new_notes=row["new_notes"] if "new_notes" in row.keys() else None,
        editor_name=row["editor_name"],
        created_at=row["created_at"],
    )


def _init_face_from_row(row: sqlite3.Row) -> InitFace:
    raw_landmarks = json.loads(row["landmarks"]) if row["landmarks"] else None
    landmarks = tuple(tuple(point) for point in raw_landmarks) if raw_landmarks else None
    return InitFace(
        init_face_id=row["init_face_id"],
        session_id=row["session_id"],
        group_id=row["group_id"],
        source_image=row["source_image"],
        face=DetectedFace(
            box=FaceBox(
                x=row["box_x"],
                y=row["box_y"],
                width=row["box_width"],
                height=row["box_height"],
                confidence=row["box_confidence"],
            ),
            quality_score=row["face_quality_score"],
            landmarks=landmarks,
            crop_path=row["crop_path"],
        ),
        vector=_unpack_embedding(row["vector"]),
        quality=QualityReport(
            status=QualityStatus(row["quality_status"]),
            score=row["quality_score"],
            reasons=tuple(json.loads(row["quality_reasons"])),
        ),
        created_at=row["created_at"],
    )
