from __future__ import annotations

from functools import lru_cache

import base64
import hashlib
import json
import sqlite3
import struct
import uuid
from contextlib import closing, contextmanager, nullcontext
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sentriface.backup_service import BackupError, BackupService
from sentriface.errors import (
    EncounterRelationConflict,
    InputValidationError,
    GraphProjectionPostcheckError,
    GraphProjectionRebuildRefused,
    StructuredRepairRefused,
    OperationRevertRefused,
)
from sentriface.models import (
    ArchivedCanonicalSurvivorRepairPrecondition,
    NoteReferenceReconciliationPrecondition,
    NoteReferenceRepairPlan,
    OperationRevertPrecondition,
    DetectedFace,
    Embedding,
    EmbeddingRecord,
    FaceBox,
    GlobalGraphProjection,
    GraphConnection,
    GraphNode,
    GraphReadEdge,
    GraphReadFilter,
    GraphReadNode,
    InitFace,
    InitGroup,
    InitSession,
    IdentityCorrection,
    MatchDecision,
    MergeAffectedAction,
    MergeAffectedItem,
    MergeConflictResolution,
    MergeConflictStrategy,
    MergeOperation,
    Note,
    NoteRevision,
    Observation,
    ObservationMedia,
    ObservationParticipant,
    PendingAddition,
    Person,
    PersonIntelligence,
    PersonGraphReadModel,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonSummary,
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
    WorldGraphReadModel,
    WorldCluster,
    WorldCollection,
    WorldDetailLevel,
    WorldDiscovery,
    WorldEvent,
    WorldEvidence,
    WorldExplanation,
    WorldGraphRequest,
    WorldGraphV2ReadModel,
    WorldMediaReference,
    WorldPageState,
    WorldPattern,
    WorldPerson,
    WorldReadFilter,
    WorldReadLimits,
    WorldRelationship,
    utc_now,
    person_recovery_status,
)
from sentriface.media_registry import media_content_identity, require_existing_media

from sentriface.secure_storage import INTEGRITY_ERRORS, connect_database, ensure_encrypted_database

# Module-level helpers live in the modules below. They are re-exported here so
# existing imports keep working; SQLiteIdentityStore resolves them from here.
from sentriface.storage.sqlite_constants import (
    SCHEMA_VERSION,
    EMBEDDING_RECOGNITION_STATES,
    DELETED_FACE_RETENTION_DAYS,
    DELETED_PERSON_RECOVERY_DAYS,
    PERSON_LIFECYCLE_STATUSES,
    RESTORABLE_PERSON_LIFECYCLE_STATUSES,
    PERSON_IDENTITY_STATUSES,
    PERSON_BIOMETRIC_STATUSES,
    RELATIONSHIP_EVIDENCE_TYPES,
    OPERATION_STATUSES,
    OPERATION_STATUS_TRANSITIONS,
    REVIEW_DECISIONS,
    MERGE_COLLECTION_ITEM_TYPES,
    SchemaMigrationError,
    SchemaMigration,
    _pack_embedding,
    _unpack_embedding,
)
from sentriface.storage.sqlite_helpers import (
    _encounter_draft_references,
    _proof_only_duplicate_matches,
    _insert_identified_person_record,
    _create_placeholder_record,
    _optional_text,
    _require_staged_review_face,
    _staged_review_face_row,
    _review_face_recognition_state,
    _require_active_review_person,
    _reference_records,
    _active_reference_count,
    _require_reference_mutation_person,
    _require_reference_media_role,
    _require_encounter_media_role,
    _source_sample_authority,
    _eligible_source_samples,
    _refresh_source_biometric_status,
    _reference_integrity_errors,
    _attachment_ownership_errors,
    _photo_review_from_conn,
    _review_identity_ref,
    _remove_review_staging,
    _create_review_person_note,
    _normalize_note_mentions,
    _note_row,
    _note_from_row,
    _insert_note_revision,
    _sync_note_reference_evidence,
    _insert_unjournaled_profile_note,
    _normalize_evidence_endpoints,
    _insert_relationship_evidence,
    _relationship_evidence_from_row,
    _graph_connection_from_row,
    _list_relationship_evidence_for_source,
    _expected_graph_connections,
    _batch_canonical_resolver,
    _batch_effective_observation_person_ids,
    _retire_canonical_manual_collisions,
    _graph_connection_signature,
    _graph_connection_row_signature,
    _insert_graph_projection_rows,
    _graph_revision_token,
    _advance_graph_revision,
    _normalize_graph_filters,
    _graph_filter_datetime,
    _graph_occurrence_datetime,
    _graph_read_components,
    _graph_time_matches,
    _graph_read_node,
    _graph_node_matches,
    _graph_allowed_actions,
    _validate_graph_projection,
    _require_observation,
    _require_draft_observation,
    _require_existing_media,
    _attach_observation_media,
    _add_observation_participant,
    _list_observation_media,
    _table_exists,
    _encounter_detail_person,
    _append_participant_revision,
    _encounter_event_details,
    _encounter_revision,
    _require_encounter_revision,
    _require_no_encounter_amendment,
    _encounter_person_media,
    _media_pair_support,
    _encounter_read_record,
    _insert_identity_correction,
    _identity_correction_from_row,
    _effective_face_assignments,
    _corrected_observation_person_ids,
    _effective_observation_person_ids,
    _list_person_sightings,
    _presence_analytics,
    _person_relationship_analytics,
    _list_observation_participants,
    _list_raw_observation_participants,
    _review_encounter_metadata,
    _observation_from_row,
    _observation_media_from_row,
    _observation_participant_from_row,
    _has_meaningful_identity_context,
    _profile_note_snapshot,
    _write_merge_profile_note_revision,
    _require_person_lifecycle_preconditions,
    _require_no_active_encounter_draft_reference,
    _preview_identity_merge,
    _proposed_merge_conflicts,
    _discover_merge_affected_items,
    _resolve_merge_conflicts,
    _combine_merge_value,
    _merge_inventory_with_profile_changes,
    _apply_merge_profile_resolutions,
    _synchronize_survivor_biometric_state,
    _list_embeddings_in_transaction,
    _set_canonical_person_id_in_transaction,
    _insert_merge_manifest_in_transaction,
    _get_merge_operation,
    _resolve_canonical_person_id,
    _person_historical_counts,
    _canonical_person_pair,
    _require_active_people,
    _new_person_association,
    _insert_person_association,
    _person_association_from_row,
    _legacy_create_note_associations,
    _person_from_row,
    _insert_person_change,
    _mark_person_enrolled,
    _placeholder_name_conflict,
    _journal_json_object,
    _journal_json_array,
    _json_value_payload,
    _operation_actor_snapshot,
    _begin_journal_operation,
    _transition_journal_operation,
    _get_journal_operation,
    _existing_committed_operation_result,
    _existing_person_operation,
    _begin_person_operation,
    _record_person_operation,
    _normalize_tags,
    _pending_from_row,
    _person_match_from_json,
    _embedding_from_row,
    _raw_embedding_owner_person_id,
    _current_embedding_owner_person_id,
    _effective_embedding_owner_person_id,
    _recognition_detail_from_row,
    _person_change_from_row,
    _init_face_from_row,
)
from sentriface.storage.sqlite_migrations import (
    _execute_migration_script,
    _migrate_0_to_1,
    _migrate_1_to_2,
    _migrate_2_to_3,
    _migrate_3_to_4,
    _migrate_4_to_5,
    _migrate_5_to_6,
    _migrate_6_to_7,
    _migrate_7_to_8,
    _migrate_8_to_9,
    _migrate_9_to_10,
    _migrate_10_to_11,
    _migrate_11_to_12,
    _migrate_12_to_13,
    _migrate_13_to_14,
    _migrate_14_to_15,
    _migrate_15_to_16,
    _migrate_16_to_17,
    _migrate_17_to_18,
    _migrate_18_to_19,
    _migrate_19_to_20,
    _migrate_20_to_21,
    _migrate_21_to_22,
    _migrate_22_to_23,
    _migrate_23_to_24,
    _migrate_24_to_25,
    _migrate_25_to_26,
    _migrate_27_to_28,
    _migrate_28_to_29,
    _migrate_29_to_30,
    _migrate_30_to_31,
    _migrate_31_to_32,
    _migrate_32_to_33,
    _require_supported_schema_version,
)
from sentriface.storage.sqlite_world import (
    _world_event_time,
    _WORLD_FILTERS_VERSION,
    _WORLD_CLUSTER_VERSION,
    _WORLD_RANKING_VERSION,
    _WORLD_CALCULATION_VERSION,
    _WORLD_RECENT_WINDOWS,
    _WORLD_MAX_LIMITS,
    _WorldReadContext,
    _normalize_world_collection,
    _world_page_state,
    _world_result,
    _world_location_text,
    _world_bounded_state,
    _world_recurrence_for_pairs,
    _world_location_suggestions_read,
    _world_has_event_scope,
    _world_degree,
    _world_explanation_scope,
    _normalize_world_limits,
    _world_datetime,
    _world_stored_datetime,
    _normalize_world_filters,
    _normalize_world_focus,
    _world_people_scope,
    _world_canonical_map,
    _world_scope_sql,
    _world_register_effective_evidence_function,
    _world_relationship_scope,
    _world_scoped_event_people,
    _world_activity_counts,
    _world_full_scope_event_statistics,
    _world_use_participant_first_overview,
    _WorldOverviewStatisticsAggregate,
    _world_activity_bucket,
    _world_rank_people,
    _world_person,
    _world_clusters,
    _world_relationship_models,
    _world_relationship,
    _world_participant_sources,
    _world_participant_source,
    _world_effective_participant_cte,
    _world_scoped_event_count,
    _world_person_event_count,
    _world_person_events,
    _world_person_event_membership_sql,
    _world_register_effective_person_function,
    _world_event_row,
    _world_event_participant_mapping,
    _world_participant_mapping,
    _world_event_batch_data,
    _world_context_summary,
    _world_event_evidence_summary,
    _world_event_evidence_count,
    _world_event_media_count,
    _world_event_media_page,
    _world_event_from_row,
    _world_evidence_page,
    _world_facets,
    _world_location_facets_effective,
    _world_token,
    _world_decode_cursor,
    _world_cursor_as_of,
    _world_scope_fingerprint,
    _world_filter_fingerprint,
)
from sentriface.storage.sqlite_repair import (
    _R01_REPAIR_ID,
    _R01_SPEC_VERSION,
    _R01_INVARIANT_ID,
    _R01_FINGERPRINT_VERSION,
    _R01_OPERATION_TYPE,
    _r01_hash,
    _r01_table_fingerprint,
    _r01_canonical_fingerprint,
    _r01_resolve_paths,
    _r01_merge_snapshot,
    _r01_relevant_operation_fingerprint,
    _r01_precondition_from_report,
    _validate_r01_request_shape,
    _r01_existing_result,
    _restore_archived_person_in_transaction,
    _R02_REPAIR_ID,
    _R02_SPEC_VERSION,
    _R02_FINGERPRINT_VERSION,
    _R02_OPERATION_TYPE,
    _R02_ALLOWED_INVARIANTS,
    _R02_STALE_EVIDENCE_MESSAGE,
    _r02_failure_checkpoint,
    _r02_rows_fingerprint,
    _r02_revision_snapshot,
    _r02_group_rows,
    _r02_validate_history,
    _r02_canonical_snapshot,
    _r02_plan_for_state,
    _r02_graph_key,
    _r02_classify_findings,
    _r02_precondition_from_report,
    _validate_r02_request_shape,
    _r02_existing_result,
    _r02_affected_entities,
    _r02_planned_append_ids,
    _r02_append_evidence,
    _r02_immutable_fingerprint,
    _r02_unrelated_fingerprint,
    _r02_retired_history_fingerprint,
    _P11D_REVERT_SPEC_VERSION,
    _P11D_FINGERPRINT_VERSION,
    _P11D_REVERT_OPERATION_TYPE,
    _p11d_checkpoint,
    _p11d_person_fingerprint,
    _p11d_person_stable_fingerprint,
    _p11d_merge_state_fingerprint,
    _p11d_immutable_fingerprint,
    _p11d_affected_entities,
    _p11d_later_dependencies,
    _p11d_precondition_from_report,
    _validate_p11d_request_shape,
    _p11d_existing_result,
)


class SQLiteIdentityStore:
    def __init__(
        self,
        db_path: Path,
        embedding_dim: int = 512,
        backup_dir: Path | None = None,
        backup_retention_limit: int = 10,
        database_key: bytes | None = None,
    ) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.backup_dir = backup_dir or db_path.parent / "backups"
        self.backup_retention_limit = backup_retention_limit
        self.database_key = database_key

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_key is not None:
            ensure_encrypted_database(self.db_path, self.database_key)
        initial_version = self._schema_version()
        _require_supported_schema_version(initial_version)
        if 0 < initial_version < SCHEMA_VERSION:
            self._create_pre_migration_backup(initial_version)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            _require_supported_schema_version(current_version)
            if current_version != initial_version:
                raise SchemaMigrationError(
                    "Database schema version changed while migration was being prepared "
                    f"(v{initial_version} to v{current_version}); startup was stopped safely."
                )
            _apply_schema_migrations(conn, current_version)
            if current_version == SCHEMA_VERSION:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _validate_current_domain_state(conn)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    def _schema_version(self) -> int:
        if not self.db_path.exists():
            return 0
        with closing(connect_database(self.db_path, self.database_key)) as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def _create_pre_migration_backup(self, version: int) -> None:
        reason = f"before-schema-migration-v{version}-to-v{SCHEMA_VERSION}"
        operation_id = f"schema-migration-v{version}-to-v{SCHEMA_VERSION}"
        service = BackupService(
            self.db_path,
            self.backup_dir,
            retention_limit=self.backup_retention_limit,
            database_key=self.database_key,
        )
        existing = service.find_by_operation(operation_id)
        if existing is not None:
            if not service.verify_backup(existing.backup_id):
                raise BackupError(
                    f"Existing pre-migration backup failed verification: {existing.backup_id}"
                )
            return
        backup = service.create_backup(reason=reason, operation_id=operation_id)
        if not backup.verified or not service.verify_backup(backup.backup_id):
            raise BackupError(f"Pre-migration backup failed verification: {backup.backup_id}")

    def create_person(
        self,
        name: str,
        metadata: dict | None = None,
        notes: str = "",
        identity_status: str = "IDENTIFIED",
    ) -> Person:
        """Internal fixture/compatibility primitive; production uses IdentityService."""
        normalized_name = name.strip()
        normalized_metadata = metadata or {}
        normalized_notes = notes.strip()
        normalized_identity_status = identity_status.strip().upper()
        if normalized_identity_status not in PERSON_IDENTITY_STATUSES:
            raise ValueError(f"Unsupported identity status: {identity_status}")
        if not _has_meaningful_identity_context(
            normalized_name, normalized_metadata, normalized_notes,
        ):
            raise ValueError("A person without a face requires meaningful identity or context")
        person = Person(
            person_id=str(uuid.uuid4()),
            name=normalized_name,
            metadata=normalized_metadata,
            notes=normalized_notes,
            identity_status=normalized_identity_status,
            biometric_status="NO_FACE",
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persons(
                    person_id, name, metadata, created_at, notes,
                    identity_status, biometric_status, lifecycle_changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'NO_FACE', ?)
                """,
                (
                    person.person_id,
                    person.name,
                    json.dumps(person.metadata, separators=(",", ":")),
                    person.created_at,
                    person.notes,
                    person.identity_status,
                    person.created_at,
                ),
            )
            _insert_unjournaled_profile_note(
                conn, person.person_id, person.notes, person.created_at,
            )
        return person

    def create_identified_person(
        self,
        name: str,
        metadata: dict,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str = "identity-service",
    ) -> Person:
        normalized_name = str(name).strip()
        normalized_metadata = dict(metadata or {})
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.create",
            )
            if existing is not None:
                row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ?",
                    (existing.get("person_id"),),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed identity creation is missing its person")
                return _person_from_row(row)
            person_id = str(uuid.uuid4())
            _begin_journal_operation(
                conn,
                "identity.create",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"identity_status": "IDENTIFIED", "biometric_status": "NO_FACE"},
            )
            try:
                person = _insert_identified_person_record(
                    conn,
                    person_id=person_id,
                    name=normalized_name,
                    metadata=normalized_metadata,
                    enrollment_status="placeholder",
                )
            except INTEGRITY_ERRORS as exc:
                raise _placeholder_name_conflict(exc, normalized_name) from exc
            result = {
                "person_id": person.person_id,
                "lifecycle_status": "ACTIVE",
                "identity_status": "IDENTIFIED",
                "biometric_status": "NO_FACE",
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return person

    def _legacy_create_placeholder_person(
        self,
        name: str,
        metadata: dict | None,
        editor_name: str,
        operation_id: str,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> Person:
        normalized_name = name.strip()
        if not normalized_name:
            raise KeyError("Person name is required")
        if not editor_name.strip():
            raise KeyError("Created by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "create-placeholder")
            if existing:
                row = conn.execute(
                    """
                    SELECT * FROM persons WHERE person_id = ?
                    """,
                    (existing["person_id"],),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Stored placeholder creation result is no longer available")
                return _person_from_row(row)
            person = _create_placeholder_record(
                conn,
                normalized_name,
                metadata,
                editor_name.strip(),
                notes,
            )
            automatic_associations = _legacy_create_note_associations(
                conn, person.person_id, person.notes, editor_name.strip(), mentioned_person_ids or [],
            )
            _record_person_operation(
                conn,
                operation_id,
                "create-placeholder",
                {
                    "person_id": person.person_id,
                    "person_ids": [person.person_id, *[item.target_person_id if item.source_person_id == person.person_id else item.source_person_id for item in automatic_associations]],
                    "enrollment_status": "placeholder",
                    "automatic_association_ids": [item.association_id for item in automatic_associations],
                },
            )
        return person

    def get_person(self, person_id: str, include_archived: bool = False) -> Person | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM persons
                WHERE person_id = ? {" " if include_archived else "AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return _person_from_row(row)

    def get_effective_person(self, person_id: str) -> Person | None:
        with self._connect() as conn:
            try:
                canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            except KeyError:
                return None
            row = conn.execute(
                """
                SELECT * FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (canonical_person_id,),
            ).fetchone()
        return _person_from_row(row) if row is not None else None

    def list_persons(self, archived: bool = False) -> list[PersonSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.*
                FROM persons p
                WHERE {"p.lifecycle_status <> 'ACTIVE' OR p.deleted_at IS NOT NULL" if archived else "p.lifecycle_status = 'ACTIVE' AND p.deleted_at IS NULL"}
                ORDER BY p.name COLLATE NOCASE
                """
            ).fetchall()
            effective_embedding_counts: dict[str, int] = {}
            for embedding_row in conn.execute(
                "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
            ).fetchall():
                canonical_id = _effective_embedding_owner_person_id(conn, embedding_row)
                effective_embedding_counts[canonical_id] = (
                    effective_embedding_counts.get(canonical_id, 0) + 1
                )
            analytics_by_canonical: dict[str, PresenceAnalytics] = {}
            row_canonical_ids: dict[str, str] = {}
            for row in rows:
                canonical_id = _resolve_canonical_person_id(conn, str(row["person_id"]))
                row_canonical_ids[str(row["person_id"])] = canonical_id
                if canonical_id not in analytics_by_canonical:
                    analytics_by_canonical[canonical_id] = _presence_analytics(
                        _list_person_sightings(conn, canonical_id)
                    )
        return [
            PersonSummary(
                person=Person(
                    person_id=row["person_id"],
                    name=row["name"],
                    metadata=json.loads(row["metadata"]),
                    created_at=row["created_at"],
                    deleted_at=row["deleted_at"],
                    enrollment_status=row["enrollment_status"],
                    notes=row["notes"],
                    lifecycle_status=row["lifecycle_status"],
                    canonical_person_id=row["canonical_person_id"],
                    identity_status=row["identity_status"],
                    biometric_status=row["biometric_status"],
                    restore_until=row["restore_until"],
                ),
                embedding_count=effective_embedding_counts.get(
                    row_canonical_ids[str(row["person_id"])], 0,
                ),
                sighting_count=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].observation_count,
                last_seen_at=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].last_seen_at,
                first_seen_at=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].first_seen_at,
                frequency_per_30_days=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].frequency_per_30_days,
                frequency_label=analytics_by_canonical[
                    row_canonical_ids[str(row["person_id"])]
                ].frequency_label,
            )
            for row in rows
        ]

    def list_embeddings_for_person(
        self,
        person_id: str,
        include_archived: bool = False,
    ) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            requested_canonical_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.vector, e.quality_score,
                       e.source_image, e.crop_path, e.created_at, e.recognition_state
                FROM embeddings e
                WHERE e.deleted_at IS NULL
                ORDER BY e.created_at ASC
                """
            ).fetchall()
            source_authority = _source_sample_authority(conn)
            result = []
            references = _reference_records(conn, requested_canonical_id)
            for row in rows:
                eid = row["embedding_id"]
                if requested_canonical_id not in source_authority[eid]["owners"]:
                    continue
                record = _embedding_from_row(row, raw_person_id=_raw_embedding_owner_person_id(conn, row),
                                             canonical_person_id=requested_canonical_id)
                own_reference = next((r for r in references if r["active"] and r["embedding_id"] == eid), None)
                if own_reference:
                    record = replace(record, source_image=own_reference["source_image"], crop_path=own_reference["crop_path"],
                                     recognition_state=own_reference["recognition_state"])
                else:
                    for observation in conn.execute("SELECT observation_id FROM observations WHERE status='FINALIZED'").fetchall():
                        assignment = next((a for a in _effective_face_assignments(conn, observation[0])
                            if a["embedding_id"] == eid and _resolve_canonical_person_id(conn, a["current_person_id"]) == requested_canonical_id), None)
                        if assignment is None:
                            continue
                        source = conn.execute("""SELECT m.media_path, f.recognition_detail FROM observation_face_assignments a
                            JOIN photo_review_faces f ON f.review_id=a.review_id AND f.face_id=a.face_id
                            JOIN observation_media m ON m.observation_id=a.observation_id
                              AND m.media_id=json_extract(f.recognition_detail,'$.encounter_media_id')
                            WHERE a.assignment_id=?""", (assignment["assignment_id"],)).fetchone()
                        if source and source[0] != record.source_image:
                            record = replace(record, source_image=source[0], crop_path=None)
                        if source:
                            record = replace(record, recognition_state=json.loads(source[1] or "{}").get("source_recognition_state", record.recognition_state))
                        break
                result.append(record)
            if not include_archived:
                canonical = conn.execute(
                    "SELECT lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (requested_canonical_id,),
                ).fetchone()
                if canonical is None or canonical["lifecycle_status"] != "ACTIVE" or canonical["deleted_at"]:
                    return []
            return result

    def face_origins_for_embeddings(self, embedding_ids: list[str], person_id: str | None = None) -> dict[str, list[dict]]:
        """Read immutable review provenance without guessing the origin of legacy faces."""
        ids = sorted(set(embedding_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            canonical = _resolve_canonical_person_id(conn, person_id) if person_id else None
            origins: dict[str, list[dict]] = {embedding_id: [] for embedding_id in ids}
            for row in conn.execute(
                f"SELECT assignment_id, embedding_id, observation_id, review_id, created_operation_id "
                f"FROM observation_face_assignments WHERE embedding_id IN ({placeholders}) "
                "ORDER BY created_at, assignment_id", ids,
            ):
                if canonical and not any(a["assignment_id"] == row["assignment_id"]
                    and _resolve_canonical_person_id(conn, a["current_person_id"]) == canonical
                    for a in _effective_face_assignments(conn, row["observation_id"])):
                    continue
                origins[str(row["embedding_id"])].append({
                    "face_origin": "ENCOUNTER",
                    "observation_id": str(row["observation_id"]),
                    "review_id": str(row["review_id"]),
                    "operation_id": str(row["created_operation_id"]),
                })
            for row in conn.execute(
                f"SELECT embedding_id, person_id, review_id, operation_id "
                f"FROM biometric_enrollment_history WHERE embedding_id IN ({placeholders}) "
                "ORDER BY created_at, enrollment_id", ids,
            ):
                if canonical and _resolve_canonical_person_id(conn, row["person_id"]) != canonical:
                    continue
                origins[str(row["embedding_id"])].append({
                    "face_origin": "STANDALONE_ENROLLMENT",
                    "observation_id": None,
                    "review_id": str(row["review_id"]),
                    "operation_id": str(row["operation_id"]),
                })
            return {
                embedding_id: records or [{"face_origin": "UNKNOWN_LEGACY"}]
                for embedding_id, records in origins.items()
            }

    def proof_only_duplicate_candidates(self, vectors: list[Embedding], threshold: float, *, review_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            return _proof_only_duplicate_matches(conn, vectors, threshold, review_id=review_id)

    def list_raw_embeddings_for_person(
        self, person_id: str, include_deleted: bool = False,
    ) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            rows = conn.execute(
                f"""
                SELECT embedding_id, person_id, vector, quality_score,
                       source_image, crop_path, created_at, recognition_state
                FROM embeddings
                {"" if include_deleted else "WHERE deleted_at IS NULL"}
                ORDER BY created_at ASC
                """
            ).fetchall()
            return [
                _embedding_from_row(
                    row,
                    raw_person_id=_raw_embedding_owner_person_id(conn, row),
                    canonical_person_id=_effective_embedding_owner_person_id(conn, row),
                )
                for row in rows
                if _raw_embedding_owner_person_id(conn, row) == person_id
            ]

    def _legacy_rename_person(self, person_id: str, name: str) -> None:
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "UPDATE persons SET name = ? WHERE person_id = ? AND deleted_at IS NULL",
                    (name, person_id),
                )
            except INTEGRITY_ERRORS as exc:
                raise _placeholder_name_conflict(exc, name) from exc
        if cursor.rowcount == 0:
            raise KeyError(f"Unknown person: {person_id}")

    def update_person_profile(
        self,
        person_id: str,
        name: str,
        rank: str | None,
        country: str | None,
        importance: str | None,
        editor_name: str,
        tags: list[str] | None = None,
        *,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> PersonChange:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.profile.update",
            )
            if existing is None:
                existing = _begin_person_operation(conn, operation_id, "update-profile")
            if existing:
                change_row = conn.execute(
                    """
                    SELECT change_id, person_id, previous_name, new_name,
                           previous_rank, new_rank, previous_country, new_country,
                           previous_importance, new_importance,
                           previous_status, new_status, previous_notes, new_notes,
                           editor_name, created_at
                    FROM person_change_history
                    WHERE change_id = ?
                    """,
                    (existing["change_id"],),
                ).fetchone()
                if change_row is None:
                    raise RuntimeError("Stored profile update result is no longer available")
                return _person_change_from_row(change_row)
            row = conn.execute(
                """
                SELECT person_id, name, metadata, enrollment_status, notes
                FROM persons
                WHERE person_id = ? AND deleted_at IS NULL
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            _begin_journal_operation(
                conn,
                "identity.profile.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
            )
            previous_metadata = json.loads(row["metadata"])
            previous_name = row["name"]
            next_metadata = {
                **previous_metadata,
                "rank": rank or "",
                "country": country or "",
                "importance": importance or "",
                "tags": _normalize_tags(tags if tags is not None else previous_metadata.get("tags", [])),
            }
            change = PersonChange(
                change_id=str(uuid.uuid4()),
                person_id=person_id,
                previous_name=previous_name,
                new_name=name,
                previous_rank=previous_metadata.get("rank") or "",
                new_rank=rank or "",
                previous_country=previous_metadata.get("country") or "",
                new_country=country or "",
                previous_importance=previous_metadata.get("importance") or "",
                new_importance=importance or "",
                previous_status=row["enrollment_status"],
                new_status=row["enrollment_status"],
                previous_notes=row["notes"],
                new_notes=row["notes"],
                editor_name=editor_name,
                created_at=utc_now(),
            )
            try:
                conn.execute(
                    """
                    UPDATE persons
                    SET name = ?, metadata = ?
                    WHERE person_id = ? AND deleted_at IS NULL
                    """,
                    (
                        name,
                        json.dumps(next_metadata, separators=(",", ":")),
                        person_id,
                    ),
                )
            except INTEGRITY_ERRORS as exc:
                raise _placeholder_name_conflict(exc, name) from exc
            _insert_person_change(conn, change)
            result = {"change_id": change.change_id, "person_id": person_id}
            _record_person_operation(
                conn, operation_id, "update-profile", result,
            )
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
        return change

    def create_note(
        self,
        owner_person_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        normalized_content = content.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.create",
            )
            if existing_result is not None:
                if existing_result.get("owner_person_id") != owner_person_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, str(existing_result["note_id"]))
                if row is None:
                    raise RuntimeError("Committed note creation is missing its note")
                return _note_from_row(conn, row)
            owner = conn.execute(
                """
                SELECT person_id FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (owner_person_id,),
            ).fetchone()
            if owner is None:
                raise KeyError(f"Unknown active person: {owner_person_id}")
            mentions = _normalize_note_mentions(
                conn, owner_person_id, mentioned_person_ids,
            )
            note_id = str(uuid.uuid4())
            created_at = utc_now()
            _begin_journal_operation(
                conn,
                "note.create",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": owner_person_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id, _ in mentions
                    ],
                ],
            )
            conn.execute(
                """
                INSERT INTO notes(
                    note_id, owner_person_id, subject_type, subject_id,
                    is_profile_note, status, created_operation_id, created_at, updated_at
                ) VALUES (?, ?, 'PERSON', ?, 0, 'ACTIVE', ?, ?, ?)
                """,
                (
                    note_id,
                    owner_person_id,
                    owner_person_id,
                    operation_id,
                    created_at,
                    created_at,
                ),
            )
            revision_id = _insert_note_revision(
                conn,
                note_id=note_id,
                revision_number=1,
                content=normalized_content,
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
                source=_optional_text(source),
                created_at=created_at,
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": owner_person_id,
                "revision_number": 1,
                "mentioned_person_ids": [person_id for person_id, _ in mentions],
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def update_note(
        self,
        note_id: str,
        content: str,
        operation_id: str,
        *,
        mentioned_person_ids: list[str] | None = None,
        expected_revision_number: int | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        normalized_content = content.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.update",
            )
            if existing_result is not None:
                if existing_result.get("note_id") != note_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, note_id)
                if row is None:
                    raise RuntimeError("Committed note update is missing its note")
                return _note_from_row(conn, row)
            row = _note_row(conn, note_id)
            if row is None or row["status"] != "ACTIVE":
                raise KeyError(f"Unknown active note: {note_id}")
            current = _note_from_row(conn, row)
            if (
                expected_revision_number is not None
                and current.revision_number != expected_revision_number
            ):
                raise KeyError("The note was changed elsewhere. Reload it and try again.")
            mentions = _normalize_note_mentions(
                conn,
                current.owner_person_id,
                mentioned_person_ids,
                historical_person_ids=set(current.mentioned_person_ids),
            )
            desired_mention_ids = tuple(person_id for person_id, _ in mentions)
            changed = (
                current.content != normalized_content
                or current.mentioned_person_ids != desired_mention_ids
            )
            _begin_journal_operation(
                conn,
                "note.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": current.owner_person_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id, _ in mentions
                    ],
                ],
                details={"previous_revision_number": current.revision_number},
            )
            revision_number = current.revision_number
            if changed:
                revision_number += 1
                created_at = utc_now()
                revision_id = _insert_note_revision(
                    conn,
                    note_id=note_id,
                    revision_number=revision_number,
                    content=normalized_content,
                    mentions=mentions,
                    actor=actor,
                    author_name="",
                    operation_id=operation_id,
                    created_at=created_at,
                )
                _sync_note_reference_evidence(
                    conn,
                    note_id=note_id,
                    owner_person_id=current.owner_person_id,
                    revision_id=revision_id,
                    mentions=mentions,
                    operation_id=operation_id,
                    source=_optional_text(source),
                    created_at=created_at,
                )
                conn.execute(
                    "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                    (created_at, note_id),
                )
                if row["is_profile_note"]:
                    conn.execute(
                        "UPDATE persons SET notes = ? WHERE person_id = ?",
                        (normalized_content, current.owner_person_id),
                    )
                _replace_graph_projection(conn)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"])
                    )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": current.owner_person_id,
                "revision_number": revision_number,
                "changed": changed,
                "mentioned_person_ids": list(desired_mention_ids),
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def get_note(self, note_id: str, include_retired: bool = False) -> Note | None:
        with self._connect() as conn:
            row = _note_row(conn, note_id)
            if row is None or (row["status"] == "RETIRED" and not include_retired):
                return None
            return _note_from_row(conn, row)

    def get_person_note(
        self, person_id: str, include_retired: bool = False,
    ) -> Note | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT note_id FROM notes
                WHERE owner_person_id = ? AND is_profile_note = 1
                {' ' if include_retired else "AND status = 'ACTIVE'"}
                ORDER BY CASE status WHEN 'ACTIVE' THEN 0 ELSE 1 END,
                         updated_at DESC, note_id
                LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            note_row = _note_row(conn, str(row["note_id"]))
            return _note_from_row(conn, note_row)

    def list_person_notes(
        self,
        person_id: str,
        *,
        raw: bool = False,
        include_retired: bool = False,
    ) -> list[Note]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                f"""
                SELECT note_id, owner_person_id FROM notes
                {' ' if include_retired else "WHERE status = 'ACTIVE'"}
                ORDER BY updated_at DESC, note_id
                """
            ).fetchall()
            notes: list[Note] = []
            for item in rows:
                owner_id = str(item["owner_person_id"])
                matches = (
                    owner_id == str(person_id)
                    if raw
                    else _resolve_canonical_person_id(conn, owner_id) == canonical_person_id
                )
                if matches:
                    notes.append(_note_from_row(
                        conn, _note_row(conn, str(item["note_id"])),
                    ))
            return notes

    def list_note_revisions(self, note_id: str) -> list[NoteRevision]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM notes WHERE note_id = ?", (note_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown note: {note_id}")
            rows = conn.execute(
                """
                SELECT * FROM note_revisions
                WHERE note_id = ? ORDER BY revision_number
                """,
                (note_id,),
            ).fetchall()
            revisions: list[NoteRevision] = []
            for row in rows:
                mention_rows = conn.execute(
                    """
                    SELECT referenced_person_id FROM note_revision_mentions
                    WHERE revision_id = ? ORDER BY referenced_person_id
                    """,
                    (row["revision_id"],),
                ).fetchall()
                revisions.append(NoteRevision(
                    revision_id=str(row["revision_id"]),
                    note_id=str(row["note_id"]),
                    revision_number=int(row["revision_number"]),
                    content=str(row["content"]),
                    mentioned_person_ids=tuple(str(item[0]) for item in mention_rows),
                    actor=json.loads(row["actor"]),
                    author_name=str(row["author_name"]),
                    operation_id=row["operation_id"],
                    created_at=str(row["created_at"]),
                    effective_mentioned_person_ids=tuple(sorted({
                        _resolve_canonical_person_id(conn, str(item[0]))
                        for item in mention_rows
                    })),
                ))
            return revisions

    def retire_note(
        self,
        note_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> Note:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.retire",
            )
            if existing_result is not None:
                if existing_result.get("note_id") != note_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _note_row(conn, note_id)
                if row is None:
                    raise RuntimeError("Committed note retirement is missing its note")
                return _note_from_row(conn, row)
            row = _note_row(conn, note_id)
            if row is None or row["status"] != "ACTIVE":
                raise KeyError(f"Unknown active note: {note_id}")
            _begin_journal_operation(
                conn,
                "note.retire",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "notes-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": row["owner_person_id"]},
                ],
            )
            retired_at = utc_now()
            active_mentions = conn.execute(
                """
                SELECT mention_id FROM note_mentions
                WHERE note_id = ? AND active = 1 ORDER BY mention_id
                """,
                (note_id,),
            ).fetchall()
            for mention in active_mentions:
                mention_id = str(mention["mention_id"])
                conn.execute(
                    """
                    UPDATE note_mentions
                    SET active = 0, retired_revision_id = ?, retired_operation_id = ?,
                        retired_at = ?
                    WHERE mention_id = ? AND active = 1
                    """,
                    (row["revision_id"], operation_id, retired_at, mention_id),
                )
                conn.execute(
                    """
                    UPDATE relationship_evidence
                    SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                    WHERE evidence_type = 'NOTE_REFERENCE'
                      AND source_entity_type = 'NOTE'
                      AND source_entity_id = ? AND active = 1
                    """,
                    (operation_id, retired_at, mention_id),
                )
            conn.execute(
                """
                UPDATE notes
                SET status = 'RETIRED', retired_operation_id = ?, retired_at = ?,
                    updated_at = ?
                WHERE note_id = ? AND status = 'ACTIVE'
                """,
                (operation_id, retired_at, retired_at, note_id),
            )
            if row["is_profile_note"]:
                conn.execute(
                    "UPDATE persons SET notes = '' WHERE person_id = ?",
                    (row["owner_person_id"],),
                )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            _transition_journal_operation(conn, operation_id, "COMMITTED", {
                "note_id": note_id,
                "owner_person_id": row["owner_person_id"],
                "retired": True,
                "deactivated_mentions": len(active_mentions),
            })
            return _note_from_row(conn, _note_row(conn, note_id))

    def update_person_notes(
        self,
        person_id: str,
        notes: str,
        expected_previous_notes: str,
        editor_name: str,
        operation_id: str,
        mentioned_person_ids: list[str] | None = None,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> tuple[bool, Person, PersonChange | None]:
        next_notes = notes.strip()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "note.profile-save",
            )
            if existing_result is not None:
                if existing_result.get("person_id") != person_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                person_row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError("This person no longer exists")
                change = None
                if existing_result.get("change_id"):
                    change_row = conn.execute(
                        "SELECT * FROM person_change_history WHERE change_id = ?",
                        (existing_result["change_id"],),
                    ).fetchone()
                    change = _person_change_from_row(change_row) if change_row else None
                return (
                    bool(existing_result.get("changed")),
                    _person_from_row(person_row),
                    change,
                )
            legacy_result = _existing_person_operation(
                conn, operation_id, "update-person-notes",
            )
            if legacy_result is not None:
                person_row = conn.execute(
                    "SELECT * FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError("This person no longer exists")
                change_row = None
                if legacy_result.get("change_id"):
                    change_row = conn.execute(
                        "SELECT * FROM person_change_history WHERE change_id = ?",
                        (legacy_result["change_id"],),
                    ).fetchone()
                return (
                    bool(legacy_result.get("changed")),
                    _person_from_row(person_row),
                    _person_change_from_row(change_row) if change_row else None,
                )
            row = conn.execute(
                """
                SELECT * FROM persons
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE' AND deleted_at IS NULL
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError("This person no longer exists")
            active_note_row = conn.execute(
                """
                SELECT note_id FROM notes
                WHERE owner_person_id = ? AND is_profile_note = 1 AND status = 'ACTIVE'
                ORDER BY updated_at DESC, note_id LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            note_row = (
                _note_row(conn, str(active_note_row["note_id"]))
                if active_note_row is not None else None
            )
            current_note = _note_from_row(conn, note_row) if note_row is not None else None
            current_notes = current_note.content if current_note is not None else ""
            if current_notes != expected_previous_notes:
                raise KeyError("Notes were changed elsewhere. Reopen this profile and try again.")
            mentions = _normalize_note_mentions(
                conn,
                person_id,
                mentioned_person_ids,
                historical_person_ids=(
                    set(current_note.mentioned_person_ids) if current_note is not None else set()
                ),
            )
            desired_ids = tuple(person_id for person_id, _ in mentions)
            mentions_changed = (
                current_note is None or current_note.mentioned_person_ids != desired_ids
            )
            content_changed = current_notes != next_notes
            changed = content_changed or mentions_changed
            note_id = current_note.note_id if current_note is not None else str(uuid.uuid4())
            operation_actor = actor or {
                "display_name": editor_name.strip(),
                "roles": [],
            }
            _begin_journal_operation(
                conn,
                "note.profile-save",
                operation_id=operation_id,
                actor=operation_actor,
                source=_optional_text(source) or "person-notes",
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "person", "entity_id": person_id},
                    *[
                        {"entity_type": "person", "entity_id": mentioned_id}
                        for mentioned_id, _ in mentions
                    ],
                ],
            )
            change = None
            revision_number = current_note.revision_number if current_note else 0
            if changed:
                created_at = utc_now()
                if current_note is None:
                    conn.execute(
                        """
                        INSERT INTO notes(
                            note_id, owner_person_id, subject_type, subject_id,
                            is_profile_note, status, created_operation_id, created_at, updated_at
                        ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?, ?)
                        """,
                        (
                            note_id,
                            person_id,
                            person_id,
                            operation_id,
                            created_at,
                            created_at,
                        ),
                    )
                revision_number += 1
                revision_id = _insert_note_revision(
                    conn,
                    note_id=note_id,
                    revision_number=revision_number,
                    content=next_notes,
                    mentions=mentions,
                    actor=operation_actor,
                    author_name=editor_name,
                    operation_id=operation_id,
                    created_at=created_at,
                )
                _sync_note_reference_evidence(
                    conn,
                    note_id=note_id,
                    owner_person_id=person_id,
                    revision_id=revision_id,
                    mentions=mentions,
                    operation_id=operation_id,
                    source=_optional_text(source),
                    created_at=created_at,
                )
                conn.execute(
                    "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                    (created_at, note_id),
                )
                conn.execute(
                    "UPDATE persons SET notes = ? WHERE person_id = ?",
                    (next_notes, person_id),
                )
                if content_changed:
                    metadata = json.loads(row["metadata"])
                    change = PersonChange(
                        change_id=str(uuid.uuid4()),
                        person_id=person_id,
                        previous_name=row["name"],
                        new_name=row["name"],
                        previous_rank=(metadata.get("rank") or ""),
                        new_rank=(metadata.get("rank") or ""),
                        previous_country=(metadata.get("country") or ""),
                        new_country=(metadata.get("country") or ""),
                        previous_importance=(metadata.get("importance") or ""),
                        new_importance=(metadata.get("importance") or ""),
                        previous_status=row["enrollment_status"],
                        new_status=row["enrollment_status"],
                        previous_notes=current_notes,
                        new_notes=next_notes,
                        editor_name=editor_name.strip(),
                        created_at=created_at,
                    )
                    _insert_person_change(conn, change)
                _replace_graph_projection(conn)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"])
                    )
            result = {
                "person_id": person_id,
                "person_ids": [person_id, *list(desired_ids)],
                "note_id": note_id,
                "change_id": change.change_id if change else None,
                "changed": changed,
                "revision_number": revision_number,
                "mentioned_person_ids": list(desired_ids),
            }
            _record_person_operation(
                conn, operation_id, "update-person-notes", result,
            )
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
        return changed, _person_from_row(updated), change

    def list_person_changes(self, person_id: str) -> list[PersonChange]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT change_id, person_id, previous_name, new_name,
                       previous_rank, new_rank, previous_country, new_country,
                       previous_importance, new_importance,
                       previous_status, new_status, previous_notes, new_notes,
                       editor_name, created_at
                FROM person_change_history
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [
                _person_change_from_row(row) for row in rows
                if _resolve_canonical_person_id(conn, str(row["person_id"]))
                == canonical_person_id
            ]

    def list_raw_person_changes(self, person_id: str) -> list[PersonChange]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT change_id, person_id, previous_name, new_name,
                       previous_rank, new_rank, previous_country, new_country,
                       previous_importance, new_importance,
                       previous_status, new_status, previous_notes, new_notes,
                       editor_name, created_at
                FROM person_change_history
                WHERE person_id = ?
                ORDER BY created_at DESC
                """,
                (person_id,),
            ).fetchall()
        return [_person_change_from_row(row) for row in rows]

    def list_person_operations(self, person_id: str) -> list[dict]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            return self._list_person_operations(
                conn, person_id, canonical_person_id=canonical_person_id,
            )

    def list_raw_person_operations(self, person_id: str) -> list[dict]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            return self._list_person_operations(conn, person_id, canonical_person_id=None)

    def _list_person_operations(
        self,
        conn: sqlite3.Connection,
        person_id: str,
        *,
        canonical_person_id: str | None,
    ) -> list[dict]:
        rows = conn.execute(
            """
            SELECT operation_id FROM operation_journal
            WHERE status IN ('COMMITTED', 'REVERTED')
            ORDER BY created_at DESC, operation_id DESC
            """
        ).fetchall()
        operations: list[dict] = []
        for row in rows:
            operation = _get_journal_operation(conn, str(row["operation_id"]))
            if operation is None:
                continue
            involved_ids = {
                str(item.get("entity_id"))
                for item in operation["affected_entities"]
                if isinstance(item, dict)
                and item.get("entity_type") == "person"
                and item.get("entity_id")
            }
            if canonical_person_id is None:
                matches = person_id in involved_ids
            else:
                matches = any(
                    _resolve_canonical_person_id(conn, str(involved_id))
                    == canonical_person_id
                    for involved_id in involved_ids
                    if conn.execute(
                        "SELECT 1 FROM persons WHERE person_id = ?", (involved_id,),
                    ).fetchone() is not None
                )
            if not matches:
                continue
            history = operation.get("status_history") or []
            result = dict(history[-1].get("details") or {}) if history else {}
            operations.append(
                {
                    "operation_id": operation["operation_id"],
                    "operation_type": operation["operation_type"],
                    "status": operation["status"],
                    "actor": operation["actor"],
                    "source": operation["source"],
                    "created_at": operation["created_at"],
                    "completed_at": operation["completed_at"],
                    "result": result,
                }
            )
        return operations

    def _legacy_create_person_association(
        self,
        source_person_id: str,
        target_person_id: str,
        actor_name: str,
        operation_id: str,
    ) -> PersonAssociation:
        actor = actor_name.strip()
        if not actor:
            raise KeyError("Created by is required")
        person_a_id, person_b_id = _canonical_person_pair(
            source_person_id,
            target_person_id,
        )
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "create-person-association",
            )
            if existing:
                row = conn.execute(
                    "SELECT * FROM person_associations WHERE association_id = ?",
                    (existing["association_id"],),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Stored association result is no longer available")
                return _person_association_from_row(row)
            _require_active_people(conn, person_a_id, person_b_id)
            current = conn.execute(
                "SELECT * FROM person_associations WHERE source_person_id = ? AND target_person_id = ? AND relationship_type = 'ASSOCIATED_WITH'",
                (person_a_id, person_b_id),
            ).fetchone()
            if current is not None:
                if current["association_origin"] == "automatic_mention":
                    conn.execute(
                        "UPDATE person_associations SET association_origin = 'manual', updated_at = ?, created_by = ? WHERE association_id = ?",
                        (utc_now(), actor, current["association_id"]),
                    )
                    association = _person_association_from_row(conn.execute(
                        "SELECT * FROM person_associations WHERE association_id = ?", (current["association_id"],),
                    ).fetchone())
                    _record_person_operation(conn, operation_id, "create-person-association", {
                        "association_id": association.association_id,
                        "source_person_id": source_person_id,
                        "target_person_id": target_person_id,
                        "relationship_type": association.relationship_type,
                        "actor_name": actor,
                        "upgraded_from_automatic": True,
                    })
                    return association
                raise KeyError("These people are already associated")
            association = _new_person_association(person_a_id, person_b_id, actor)
            try:
                _insert_person_association(conn, association)
            except INTEGRITY_ERRORS as exc:
                if "person_associations" in str(exc):
                    raise KeyError("These people are already associated") from exc
                raise
            _record_person_operation(
                conn,
                operation_id,
                "create-person-association",
                {
                    "association_id": association.association_id,
                    "source_person_id": source_person_id,
                    "target_person_id": target_person_id,
                    "relationship_type": association.relationship_type,
                    "actor_name": actor,
                },
            )
            return association

    def _legacy_create_placeholder_association(
        self,
        source_person_id: str,
        name: str,
        metadata: dict | None,
        actor_name: str,
        operation_id: str,
    ) -> tuple[Person, PersonAssociation]:
        actor = actor_name.strip()
        normalized_name = name.strip().lstrip("@").strip()
        if not normalized_name:
            raise KeyError("Person name is required")
        if not actor:
            raise KeyError("Created by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "create-placeholder-association",
            )
            if existing:
                person_row = conn.execute(
                    """
                    SELECT * FROM persons WHERE person_id = ?
                    """,
                    (existing["target_person_id"],),
                ).fetchone()
                association_row = conn.execute(
                    "SELECT * FROM person_associations WHERE association_id = ?",
                    (existing["association_id"],),
                ).fetchone()
                if person_row is None or association_row is None:
                    raise RuntimeError("Stored placeholder association is no longer available")
                return (
                    _person_from_row(person_row),
                    _person_association_from_row(association_row),
                )
            _require_active_people(conn, source_person_id)
            person = _create_placeholder_record(
                conn,
                normalized_name,
                metadata,
                actor,
            )
            person_a_id, person_b_id = _canonical_person_pair(
                source_person_id,
                person.person_id,
            )
            association = _new_person_association(person_a_id, person_b_id, actor)
            _insert_person_association(conn, association)
            _record_person_operation(
                conn,
                operation_id,
                "create-placeholder-association",
                {
                    "association_id": association.association_id,
                    "source_person_id": source_person_id,
                    "target_person_id": person.person_id,
                    "relationship_type": association.relationship_type,
                    "actor_name": actor,
                },
            )
            return person, association

    def list_person_associations(
        self,
        person_id: str,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[PersonAssociation]:
        with self._connect() as conn:
            person = conn.execute(
                f"""
                SELECT 1 FROM persons
                WHERE person_id = ? {" " if include_archived else "AND deleted_at IS NULL"}
                """,
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            limit_clause = " LIMIT ?" if limit is not None else ""
            params: tuple = (person_id, person_id, max(1, int(limit))) if limit is not None else (person_id, person_id)
            rows = conn.execute(
                f"""
                SELECT association_id, source_person_id, target_person_id,
                       relationship_type, created_at, updated_at, created_by, association_origin
                FROM person_associations
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY updated_at DESC, association_id
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [_person_association_from_row(row) for row in rows]

    def _legacy_remove_person_association(
        self,
        association_id: str,
        actor_name: str,
        operation_id: str,
    ) -> dict:
        actor = actor_name.strip()
        if not actor:
            raise KeyError("Removed by is required")
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "remove-person-association",
            )
            if existing:
                return existing
            row = conn.execute(
                "SELECT * FROM person_associations WHERE association_id = ?",
                (association_id,),
            ).fetchone()
            if row is None:
                raise KeyError("This association no longer exists")
            association = _person_association_from_row(row)
            conn.execute(
                "DELETE FROM person_associations WHERE association_id = ?",
                (association_id,),
            )
            result = {
                "association_id": association_id,
                "source_person_id": association.source_person_id,
                "target_person_id": association.target_person_id,
                "relationship_type": association.relationship_type,
                "removed": True,
                "actor_name": actor,
            }
            _record_person_operation(
                conn,
                operation_id,
                "remove-person-association",
                result,
            )
            return result

    def get_person_operation(self, operation_id: str, operation_type: str) -> dict | None:
        with self._connect() as conn:
            return _existing_person_operation(conn, operation_id, operation_type)

    def begin_operation(
        self,
        operation_type: str,
        *,
        operation_id: str | None = None,
        actor: dict | None = None,
        source: str | None = None,
        context: dict | None = None,
        affected_entities: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        with self._connect() as conn:
            return _begin_journal_operation(
                conn,
                operation_type,
                operation_id=operation_id,
                actor=actor,
                source=source,
                context=context,
                affected_entities=affected_entities,
                details=details,
            )

    def mark_operation_committed(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "COMMITTED", details)

    def mark_operation_failed(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "FAILED", details)

    def mark_operation_rolled_back(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "ROLLED_BACK", details)

    def mark_operation_reverted(self, operation_id: str, details: dict | None = None) -> dict:
        return self._mark_operation_status(operation_id, "REVERTED", details)

    def record_merge_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
        context: dict | None = None,
        affected_entities: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        """Record failure only after the merge transaction has rolled back."""
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM merge_operations WHERE operation_journal_id = ?",
                (operation_id,),
            ).fetchone() is not None:
                raise RuntimeError("Cannot mark a merge failed while partial manifest state exists")
            existing = _get_journal_operation(conn, operation_id)
            if existing is not None:
                if existing["operation_type"] != "identity.merge":
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                if existing["status"] in {"FAILED", "ROLLED_BACK"}:
                    return existing
                if existing["status"] != "STARTED":
                    raise ValueError("Only a started merge attempt can fail")
            else:
                _begin_journal_operation(
                    conn,
                    "identity.merge",
                    operation_id=operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge",
                    context=context,
                    affected_entities=affected_entities,
                    details={"transaction_rolled_back": True},
                )
            return _transition_journal_operation(
                conn,
                operation_id,
                "FAILED",
                {"transaction_rolled_back": True, **(details or {})},
            )

    def _mark_operation_status(
        self,
        operation_id: str,
        status: str,
        details: dict | None,
    ) -> dict:
        with self._connect() as conn:
            return _transition_journal_operation(conn, operation_id, status, details)

    def get_operation(self, operation_id: str) -> dict | None:
        with self._connect() as conn:
            return _get_journal_operation(conn, operation_id)

    def latest_committed_operation_at(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) AS latest FROM operation_journal WHERE status = 'COMMITTED'",
            ).fetchone()
            return str(row["latest"] or "") if row else ""

    def list_recent_operations(self, limit: int = 50) -> list[dict]:
        if limit < 1 or limit > 500:
            raise ValueError("Operation list limit must be between 1 and 500")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT operation_id FROM operation_journal ORDER BY created_at DESC, operation_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_get_journal_operation(conn, row["operation_id"]) for row in rows]

    def create_observation(
        self,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
        participant_ids: list[str] | None = None,
        media: list[dict] | None = None,
    ) -> Observation:
        observation_id = str(uuid.uuid4())
        _, context_payload = _journal_json_object(context, "observation context")
        normalized_source = _optional_text(source)
        participants = [str(item).strip() for item in (participant_ids or [])]
        if any(not item for item in participants):
            raise ValueError("Observation participant IDs cannot be empty")
        media_items = media or []
        if not isinstance(media_items, list) or any(
            not isinstance(item, dict) for item in media_items
        ):
            raise ValueError("Observation media must be a list of objects")
        created_at = utc_now()
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.create",
            )
            if existing_result is not None:
                row = conn.execute(
                    "SELECT * FROM effective_observations WHERE observation_id = ?",
                    (existing_result.get("observation_id"),),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed observation creation is missing its observation")
                return _observation_from_row(row)
            _begin_journal_operation(
                conn,
                "observation.create",
                operation_id=operation_id,
                actor=actor,
                source=normalized_source or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id in participants
                    ],
                    *[
                        {"entity_type": "media", "entity_id": str(item.get("media_id") or "")}
                        for item in media_items
                    ],
                ],
                details={"initial_status": "DRAFT"},
            )
            conn.execute(
                """
                INSERT INTO observations(
                    observation_id, status, observed_at, location, context, source,
                    created_operation_id, created_at, updated_at
                ) VALUES (?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    _optional_text(observed_at),
                    _optional_text(location),
                    context_payload,
                    normalized_source,
                    operation_id,
                    created_at,
                    created_at,
                ),
            )
            for item in media_items:
                _attach_observation_media(
                    conn,
                    observation_id,
                    str(item.get("media_id") or ""),
                    item.get("media_path"),
                    _optional_text(item.get("source")) or normalized_source,
                    operation_id,
                )
            for person_id in participants:
                _add_observation_participant(
                    conn, observation_id, person_id, normalized_source, operation_id,
                )
            result = {
                "observation_id": observation_id,
                "status": "DRAFT",
                "participant_count": len(_list_observation_participants(conn, observation_id)),
                "media_count": len(_list_observation_media(conn, observation_id)),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            row = conn.execute(
                "SELECT * FROM effective_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(row)

    def create_photo_review(
        self,
        review_id: str,
        media_id: str,
        faces: list[dict],
        *,
        media_path: str | None = None,
        source: str = "check-photo",
    ) -> PhotoReview:
        normalized_review_id = str(review_id).strip()
        normalized_media_id = str(media_id).strip()
        if not normalized_review_id or not normalized_media_id:
            raise ValueError("Review ID and media ID are required")
        if not faces:
            raise ValueError("A review requires at least one detected face")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM photo_reviews WHERE review_id = ?", (normalized_review_id,),
            ).fetchone()
            if existing is not None:
                return _photo_review_from_conn(conn, normalized_review_id)
            _require_existing_media(conn, normalized_media_id, media_path)
            created_at = utc_now()
            conn.execute(
                """
                INSERT INTO photo_reviews(
                    review_id, media_id, media_path, source, status, created_at
                ) VALUES (?, ?, ?, ?, 'IN_PROGRESS', ?)
                """,
                (
                    normalized_review_id, normalized_media_id, _optional_text(media_path),
                    str(source).strip() or "check-photo", created_at,
                ),
            )
            seen_face_ids: set[str] = set()
            for face in faces:
                face_id = str(face.get("face_id") or "").strip()
                staged_type = str(face.get("staged_face_type") or "").strip().upper()
                staged_id = str(face.get("staged_face_id") or "").strip()
                if not face_id or face_id in seen_face_ids:
                    raise ValueError("Review face IDs must be non-empty and unique")
                _require_staged_review_face(conn, staged_type, staged_id)
                seen_face_ids.add(face_id)
                conn.execute(
                    """
                    INSERT INTO photo_review_faces(
                        review_id, face_id, staged_face_type, staged_face_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (normalized_review_id, face_id, staged_type, staged_id, created_at, created_at),
                )
            if media_path:
                conn.execute(
                    "INSERT OR IGNORE INTO photo_review_media(review_id, media_id, media_path, ordinal) "
                    "VALUES (?, ?, ?, 0)",
                    (normalized_review_id, normalized_media_id, str(media_path)),
                )
            return _photo_review_from_conn(conn, normalized_review_id)

    def plan_init_session_encounters(self, session_id: str, media_groups: list[list[str]], *, target_observation_id: str | None = None, expected_revision: str | None = None) -> list[dict]:
        """Partition a scanned Queue session into serial, non-authoritative reviews."""
        # Ownership is admission intent, not the result of successful planning.
        # Commit it independently so a rejected precondition cannot return these
        # photos to ordinary new-Encounter work (including compatibility callers).
        if target_observation_id:
            self.bind_init_session_attachment(session_id, target_observation_id, expected_revision)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute("SELECT * FROM init_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if session is None:
                raise KeyError(f"Unknown init session: {session_id}")
            if session["status"] == "closed":
                raise ValueError("This draft is closed")
            if session["target_observation_id"] and target_observation_id != session["target_observation_id"]:
                raise ValueError("These photos belong to a targeted Attach Media draft; Retry or Cancel it")
            if target_observation_id:
                if len(media_groups) != 1:
                    raise ValueError("Attach Media requires one existing Event")
                _require_encounter_revision(conn, target_observation_id, expected_revision)
                _require_no_encounter_amendment(conn, target_observation_id, session_id=session_id)
            existing_reviews = conn.execute(
                "SELECT review_id FROM photo_reviews WHERE session_id = ? ORDER BY sequence_number", (session_id,),
            ).fetchall()
            if existing_reviews:
                existing_groups = [[str(item["media_id"]) for item in conn.execute(
                    "SELECT media_id FROM photo_review_media WHERE review_id = ? ORDER BY ordinal",
                    (review["review_id"],),
                )] for review in existing_reviews]
                if existing_groups == media_groups and all(
                    conn.execute("SELECT target_observation_id FROM photo_reviews WHERE review_id = ?", (r["review_id"],)).fetchone()[0] == target_observation_id
                    for r in existing_reviews
                ):
                    return _list_init_session_encounter_reviews(conn, session_id)
                raise ValueError("Event grouping has already been confirmed for this session")
            media_rows = conn.execute(
                "SELECT media_id, media_path FROM init_session_media WHERE session_id = ? AND excluded = 0 ORDER BY media_id",
                (session_id,),
            ).fetchall()
            known_media = {str(row["media_id"]): str(row["media_path"]) for row in media_rows}
            supplied = [media_id for group in media_groups for media_id in group]
            if not media_groups or any(not group for group in media_groups) or len(supplied) != len(set(supplied)) or not set(supplied).issubset(known_media):
                raise ValueError("Every selected media item must belong to exactly one Event")
            for media_id in supplied:
                media_path = known_media[media_id]
                previous = conn.execute(
                    "SELECT om.observation_id FROM observation_media om "
                    "JOIN effective_observations o ON o.observation_id = om.observation_id "
                    "WHERE (om.media_id = ? OR om.media_path = ?) AND o.status = 'FINALIZED' LIMIT 1",
                    (media_content_identity(media_path), media_path),
                ).fetchone()
                if previous is not None:
                    raise ValueError(
                        f"This media already belongs to finalized Event {previous['observation_id']}"
                    )
            created_at = utc_now()
            staged_group_encounters: dict[str, set[int]] = {}
            staged_face_encounter: dict[str, tuple[str, int]] = {}
            for sequence_number, group in enumerate(media_groups):
                first_id = group[0]
                review_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:queue-encounter:{session_id}:{sequence_number}"))
                phase = "EVENT" if sequence_number == 0 else "WAITING"
                conn.execute(
                    "INSERT INTO photo_reviews(review_id, media_id, media_path, source, status, created_at, "
                    "session_id, sequence_number, review_phase) VALUES (?, ?, ?, 'queue', 'IN_PROGRESS', ?, ?, ?, ?)",
                    (review_id, first_id, known_media[first_id], created_at, session_id, sequence_number, phase),
                )
                if target_observation_id:
                    observation = _require_observation(conn, target_observation_id)
                    conn.execute(
                        "UPDATE photo_reviews SET target_observation_id = ?, expected_encounter_revision = ?, "
                        "event_details = ?, event_details_complete = 1, review_phase = 'IDENTITIES' WHERE review_id = ?",
                        (target_observation_id, expected_revision, json.dumps(_encounter_event_details(observation)), review_id),
                    )
                for ordinal, media_id in enumerate(group):
                    conn.execute(
                        "INSERT INTO photo_review_media(review_id, media_id, media_path, ordinal) VALUES (?, ?, ?, ?)",
                        (review_id, media_id, known_media[media_id], ordinal),
                    )
                placeholders = ",".join("?" for _ in group)
                media_paths = [known_media[media_id] for media_id in group]
                group_faces = conn.execute(
                    f"SELECT init_face_id, group_id FROM init_faces WHERE session_id = ? AND source_image IN ({placeholders}) "
                    "ORDER BY created_at, init_face_id",
                    (session_id, *media_paths),
                ).fetchall()
                if not group_faces and not target_observation_id:
                    raise ValueError("Each Event needs at least one detected face")
                for face in group_faces:
                    staged_group_encounters.setdefault(str(face["group_id"]), set()).add(sequence_number)
                    staged_face_encounter[str(face["init_face_id"])] = (str(face["group_id"]), sequence_number)
                    conn.execute(
                        "INSERT INTO photo_review_faces(review_id, face_id, staged_face_type, staged_face_id, "
                        "created_at, updated_at) VALUES (?, ?, 'INIT_FACE', ?, ?, ?)",
                        (review_id, face["init_face_id"], face["init_face_id"], created_at, created_at),
                    )
            # Split only scan groups that actually cross confirmed Encounter boundaries.
            for face_id, (group_id, sequence_number) in staged_face_encounter.items():
                if len(staged_group_encounters[group_id]) > 1:
                    conn.execute(
                        "UPDATE init_faces SET group_id = ? WHERE init_face_id = ?",
                        (f"encounter_{sequence_number}_{face_id}", face_id),
                    )
            return _list_init_session_encounter_reviews(conn, session_id)

    def list_init_session_encounter_reviews(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            return _list_init_session_encounter_reviews(conn, session_id)

    def get_encounter_review(self, review_id: str) -> dict:
        with self._connect() as conn:
            return _encounter_review_read(conn, review_id)

    def list_encounter_draft_references(self, review_id: str) -> list[dict]:
        """Read accepted draft faces for transient in-session matching only."""
        with self._connect() as conn:
            return _encounter_draft_references(conn, review_id)

    def save_encounter_review_event(self, review_id: str, event_details: dict) -> dict:
        """Store Event details once on the active draft; no Observation is created."""
        if not isinstance(event_details, dict):
            raise ValueError("Event details must be an object")
        _review_encounter_metadata([event_details])
        with self._connect() as conn:
            review = conn.execute("SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
            if review is None or review["status"] != "IN_PROGRESS" or review["review_phase"] not in {"EVENT", "IDENTITIES"}:
                raise ValueError("Event details can only be saved for the active Event review")
            if review["target_observation_id"]:
                raise ValueError("Use Correct Event to change finalized Event details")
            for person_id in event_details.get("event_mentioned_person_ids", []):
                if conn.execute("SELECT 1 FROM persons WHERE person_id = ?", (person_id,)).fetchone() is None:
                    raise ValueError(f"Unknown Event Note mentioned person: {person_id}")
            conn.execute(
                "UPDATE photo_reviews SET event_details = ?, event_details_complete = 1, review_phase = 'IDENTITIES' "
                "WHERE review_id = ?",
                (json.dumps(event_details, separators=(",", ":")), review_id),
            )
            return _encounter_review_read(conn, review_id)

    def complete_encounter_identity_review(self, review_id: str) -> dict:
        with self._connect() as conn:
            review = conn.execute("SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
            if review is None or review["status"] != "IN_PROGRESS" or review["review_phase"] != "IDENTITIES" or not review["event_details_complete"]:
                raise ValueError("Complete Event details and identity review first")
            rows = conn.execute("SELECT * FROM photo_review_faces WHERE review_id = ?", (review_id,)).fetchall()
            if (not rows and not review["target_observation_id"]) or any(row["decision"] in (None, "SKIP") for row in rows):
                raise ValueError("Every detected face needs a final identity decision")
            candidates = _review_relation_candidates(conn, review_id)
            conn.execute("UPDATE photo_reviews SET review_phase = 'RELATIONS' WHERE review_id = ?", (review_id,))
            result = _encounter_review_read(conn, review_id)
            result["relation_candidates"] = candidates
            return result

    def set_encounter_relation_decision(
        self, review_id: str, first_ref: str, second_ref: str, disposition: str,
    ) -> dict:
        normalized_disposition = str(disposition).upper()
        if normalized_disposition not in {"INCLUDE", "EXCLUDE"}:
            raise ValueError("Relation decision must be INCLUDE or EXCLUDE")
        pair = tuple(sorted((first_ref, second_ref)))
        if pair[0] == pair[1]:
            raise ValueError("A Person cannot have a Relation to themselves")
        with self._connect() as conn:
            review = conn.execute("SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
            if review is None or review["status"] != "IN_PROGRESS" or review["review_phase"] != "RELATIONS":
                raise ValueError("Relations can only be decided after identity review")
            candidates = {(item["first_ref"], item["second_ref"]): item for item in _review_relation_candidates(conn, review_id)}
            candidate = candidates.get(pair)
            if candidate is None:
                raise ValueError("Relation pair is not a final participant candidate")
            previous = conn.execute(
                "SELECT decision_id, disposition FROM encounter_relation_decisions "
                "WHERE review_id = ? AND first_ref = ? AND second_ref = ? AND active = 1",
                (review_id, *pair),
            ).fetchone()
            if previous is not None and previous["disposition"] == normalized_disposition:
                return _encounter_review_read(conn, review_id)
            if previous is not None:
                conn.execute("UPDATE encounter_relation_decisions SET active = 0 WHERE decision_id = ?", (previous["decision_id"],))
            conn.execute(
                "INSERT INTO encounter_relation_decisions(decision_id, review_id, first_ref, second_ref, "
                "disposition, support, supersedes_decision_id, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), review_id, *pair, normalized_disposition,
                 candidate["support"], previous["decision_id"] if previous else None, utc_now()),
            )
            return _encounter_review_read(conn, review_id)

    def set_photo_review_face_decision(
        self,
        review_id: str,
        face_id: str,
        decision: str,
        *,
        person_id: str | None = None,
        new_person_key: str | None = None,
        new_person_name: str | None = None,
        new_person_metadata: dict | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        recognition_detail: dict | None = None,
        proof_only_duplicate_threshold: float = 0.5,
        _conn=None,
    ) -> PhotoReview:
        normalized_decision = str(decision).strip().upper()
        if normalized_decision not in REVIEW_DECISIONS:
            raise ValueError(f"Unsupported review decision: {decision}")
        metadata, metadata_payload = _journal_json_object(
            new_person_metadata, "new person metadata",
        )
        del metadata
        _, recognition_detail_payload = _journal_json_object(
            recognition_detail, "recognition detail",
        )
        mention_ids = sorted({str(item).strip() for item in (mentioned_person_ids or []) if str(item).strip()})
        with self._connect() if _conn is None else nullcontext(_conn) as conn:
            review = conn.execute(
                "SELECT status, review_phase FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can be changed")
            if review["review_phase"] != "LEGACY" and review["review_phase"] != "IDENTITIES":
                raise ValueError("Complete Event details before deciding identities")
            if review["review_phase"] == "IDENTITIES" and normalized_decision == "SKIP":
                raise ValueError("Skip for now postpones an identity group; it is not a final decision")
            if normalized_decision == "ACCEPT_EXISTING_PERSON":
                _require_active_review_person(conn, person_id)
                new_person_key = new_person_name = None
            elif normalized_decision == "ACCEPT_NEW_PERSON":
                if not str(new_person_name or "").strip():
                    raise ValueError("A name is required for a new person decision")
                person_id = None
                new_person_key = str(new_person_key or face_id).strip()
                if review["review_phase"] == "IDENTITIES" and (recognition_detail or {}).get("proof_only_duplicate_override") is not True:
                    staged = conn.execute(
                        "SELECT i.vector FROM init_faces i JOIN photo_review_faces f ON f.staged_face_id = i.init_face_id "
                        "WHERE f.review_id = ? AND f.face_id = ? AND f.staged_face_type = 'INIT_FACE'", (review_id, face_id),
                    ).fetchone()
                    if staged and _proof_only_duplicate_matches(
                        conn, [_unpack_embedding(staged["vector"])], proof_only_duplicate_threshold,
                        review_id=review_id, excluded_draft_key=new_person_key,
                    ):
                        raise ValueError("A proof-only Person may already match this face; choose existing or explicitly create anyway")
            else:
                person_id = new_person_key = new_person_name = None
                metadata_payload = "{}"
                notes = ""
                mention_ids = []
                recognition_detail_payload = "{}"
            cursor = conn.execute(
                """
                UPDATE photo_review_faces
                SET decision = ?, person_id = ?, new_person_key = ?, new_person_name = ?,
                    new_person_metadata = ?, notes = ?, mentioned_person_ids = ?,
                    recognition_detail = ?, updated_at = ?
                WHERE review_id = ? AND face_id = ?
                """,
                (
                    normalized_decision, person_id, new_person_key,
                    _optional_text(new_person_name), metadata_payload, str(notes or "").strip(),
                    json.dumps(mention_ids, separators=(",", ":")),
                    recognition_detail_payload, utc_now(), review_id, face_id,
                ),
            )
            if not cursor.rowcount:
                raise KeyError(f"Unknown review face: {face_id}")
            return _photo_review_from_conn(conn, review_id)

    def set_photo_review_face_decisions(self, review_id: str, decisions: list[dict], **values) -> PhotoReview:
        """Commit a selected-face draft action and its duplicate guards together."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for item in decisions:
                self.set_photo_review_face_decision(review_id, **values, **item, _conn=conn)
            return _photo_review_from_conn(conn, review_id)

    def get_photo_review(self, review_id: str) -> PhotoReview | None:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone() is None:
                return None
            return _photo_review_from_conn(conn, review_id)

    def cancel_photo_review(self, review_id: str) -> PhotoReview:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, session_id, review_phase FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if row["status"] == "COMPLETED":
                raise ValueError("A completed review cannot be cancelled")
            conn.execute(
                "UPDATE photo_reviews SET status = 'CANCELLED' WHERE review_id = ?",
                (review_id,),
            )
            conn.execute(
                "DELETE FROM encounter_relation_decisions WHERE review_id = ? AND observation_id IS NULL",
                (review_id,),
            )
            _remove_review_staging(conn, review_id)
            if row["session_id"] is not None and row["review_phase"] != "WAITING":
                next_review = conn.execute(
                    "SELECT review_id FROM photo_reviews WHERE session_id = ? AND status = 'IN_PROGRESS' "
                    "AND review_phase = 'WAITING' ORDER BY sequence_number LIMIT 1",
                    (row["session_id"],),
                ).fetchone()
                if next_review is not None:
                    conn.execute("UPDATE photo_reviews SET review_phase = 'EVENT' WHERE review_id = ?", (next_review["review_id"],))
            if row["session_id"] is not None and conn.execute(
                "SELECT 1 FROM photo_reviews WHERE session_id = ? AND status = 'IN_PROGRESS' LIMIT 1",
                (row["session_id"],),
            ).fetchone() is None:
                conn.execute("UPDATE init_sessions SET status = 'closed' WHERE session_id = ?", (row["session_id"],))
            return _photo_review_from_conn(conn, review_id)

    def complete_photo_review(
        self,
        review_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
        proof_only_duplicate_threshold: float = 0.5,
    ) -> dict:
        """Commit a complete review and all authoritative consequences atomically."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(
                conn, operation_id, "review.complete",
            )
            if existing is not None:
                if existing.get("review_id") != review_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            review = conn.execute(
                "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can be completed")
            if review["source"] == "reference-only":
                raise ValueError("Confirm Reference Only without creating an Event")
            target_observation_id = review["target_observation_id"]
            original_participant_ids = []
            if target_observation_id:
                _require_encounter_revision(conn, target_observation_id, review["expected_encounter_revision"])
                original_participant_ids = _effective_observation_person_ids(conn, target_observation_id)
            face_rows = conn.execute(
                "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
                (review_id,),
            ).fetchall()
            if (not face_rows and not target_observation_id) or any(row["decision"] is None or row["decision"] == "SKIP" for row in face_rows):
                raise ValueError("Every detected face requires a final decision before completion")
            encounter_review = review["review_phase"] == "RELATIONS"
            if review["review_phase"] not in {"LEGACY", "RELATIONS"}:
                raise ValueError("Complete Event details, identity review, and Relations first")
            for media in conn.execute("SELECT media_id, media_path FROM photo_review_media WHERE review_id=?", (review_id,)).fetchall():
                _require_encounter_media_role(conn, media_content_identity(media["media_path"]))
            if review["media_path"]:
                _require_encounter_media_role(conn, media_content_identity(review["media_path"]))
            if encounter_review:
                for media_row in conn.execute(
                    "SELECT media_id, media_path FROM photo_review_media WHERE review_id = ?", (review_id,),
                ).fetchall():
                    previous = conn.execute(
                        "SELECT om.observation_id FROM observation_media om "
                        "JOIN effective_observations o ON o.observation_id = om.observation_id "
                        "WHERE (om.media_id = ? OR om.media_path = ?) AND o.status = 'FINALIZED' LIMIT 1",
                        (media_row["media_id"], media_row["media_path"]),
                    ).fetchone()
                    if previous is not None:
                        raise ValueError(
                            f"This media already belongs to finalized Event {previous['observation_id']}"
                        )
            relation_rows: list[sqlite3.Row] = []
            if encounter_review:
                candidates = {
                    (item["first_ref"], item["second_ref"]): item
                    for item in _review_relation_candidates(conn, review_id)
                }
                relation_rows = conn.execute(
                    "SELECT * FROM encounter_relation_decisions WHERE review_id = ? AND active = 1 "
                    "ORDER BY first_ref, second_ref", (review_id,),
                ).fetchall()
                if {(item["first_ref"], item["second_ref"]) for item in relation_rows} != set(candidates):
                    raise ValueError("Every candidate Relation requires INCLUDE or EXCLUDE")
                if any(item["support"] != candidates[(item["first_ref"], item["second_ref"])]["support"] for item in relation_rows):
                    raise ValueError("Relation support changed; review the draft again")
            _begin_journal_operation(
                conn,
                "review.complete",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or str(review["source"]),
                affected_entities=[
                    {"entity_type": "review", "entity_id": review_id},
                    {"entity_type": "media", "entity_id": review["media_id"]},
                ],
                details={"face_count": len(face_rows)},
            )
            assigned_by_face: dict[str, str] = {}
            created_by_key: dict[str, str] = {}
            created_person_ids: list[str] = []
            embedding_ids: list[str] = []
            embedding_by_face: dict[str, str] = {}
            note_ids: list[str] = []
            created_note_keys: set[tuple[str, str, tuple[str, ...]]] = set()
            staged_media_paths: set[str] = set()
            media_by_face: dict[str, str] = {}
            detail_inputs: list[tuple[str, str, str, dict, str, list[str], str]] = []
            for row in face_rows:
                decision = str(row["decision"])
                if decision in {"EXCLUDE", "SKIP"}:
                    continue
                staged = _staged_review_face_row(conn, row["staged_face_type"], row["staged_face_id"])
                staged_media_paths.add(str(staged["source_image"]))
                media_by_face[str(row["face_id"])] = str(staged["source_image"])
                if decision == "ACCEPT_EXISTING_PERSON":
                    person_id = _require_active_review_person(conn, row["person_id"])
                else:
                    key = str(row["new_person_key"] or row["face_id"])
                    person_id = created_by_key.get(key)
                    if person_id is None:
                        duplicate_detail = json.loads(row["recognition_detail"] or "{}")
                        if duplicate_detail.get("proof_only_duplicate_override") is not True and _proof_only_duplicate_matches(
                            conn, [_unpack_embedding(staged["vector"])],
                            proof_only_duplicate_threshold,
                        ):
                            raise ValueError(
                                "Proof-only duplicate check requires an explicit existing-person "
                                "choice or create-new override"
                            )
                        name = str(row["new_person_name"] or "").strip()
                        metadata = json.loads(row["new_person_metadata"] or "{}")
                        if not _has_meaningful_identity_context(name, metadata, str(row["notes"] or "")):
                            raise ValueError("A new person requires meaningful identity or context")
                        person_id = str(uuid.uuid4())
                        _insert_identified_person_record(
                            conn,
                            person_id=person_id,
                            name=name,
                            metadata=metadata,
                            enrollment_status="enrolled",
                        )
                        created_by_key[key] = person_id
                        created_person_ids.append(person_id)
                assigned_by_face[str(row["face_id"])] = person_id
                detail_payload = json.loads(row["recognition_detail"] or "{}")
                recognition_state = _review_face_recognition_state(staged, detail_payload)
                duplicate = conn.execute(
                    "SELECT embedding_id, recognition_state FROM embeddings WHERE person_id = ? AND vector = ? AND deleted_at IS NULL",
                    (person_id, staged["vector"]),
                ).fetchone()
                if duplicate is None:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at, recognition_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id, person_id, staged["vector"], staged["quality_score"],
                            staged["source_image"], staged["crop_path"], utc_now(),
                            recognition_state,
                        ),
                    )
                    embedding_ids.append(embedding_id)
                else:
                    embedding_id = str(duplicate["embedding_id"])
                    if recognition_state == "POOR_ACCEPTED" and duplicate["recognition_state"] == "PROOF_ONLY":
                        conn.execute(
                            "UPDATE embeddings SET recognition_state = 'POOR_ACCEPTED' WHERE embedding_id = ?",
                            (embedding_id,),
                        )
                _mark_person_enrolled(conn, person_id)
                embedding_by_face[str(row["face_id"])] = embedding_id
                content = str(row["notes"] or "").strip()
                mention_ids = json.loads(row["mentioned_person_ids"] or "[]")
                note_key = (person_id, content, tuple(sorted(mention_ids)))
                if detail_payload:
                    detail_inputs.append((
                        str(row["face_id"]), person_id, embedding_id,
                        detail_payload, content, mention_ids, decision,
                    ))
                elif (content or mention_ids) and note_key not in created_note_keys:
                    note_ids.append(_create_review_person_note(
                        conn, person_id, content, mention_ids, operation_id, actor,
                        _optional_text(source) or str(review["source"]),
                    ))
                    created_note_keys.add(note_key)
            if not assigned_by_face and not target_observation_id:
                raise ValueError("A completed review requires at least one accepted person")
            canonical_participants: dict[str, str] = {}
            for face_id in sorted(assigned_by_face):
                raw_id = assigned_by_face[face_id]
                canonical_participants.setdefault(_resolve_canonical_person_id(conn, raw_id), raw_id)
            observed_at, location, encounter_context = _review_encounter_metadata(
                [json.loads(review["event_details"] or "{}")] if encounter_review
                else [detail for _, _, _, detail, _, _, _ in detail_inputs]
            )
            event_mentions = encounter_context.get("event_mentioned_person_ids") or []
            for mentioned_id in event_mentions:
                if conn.execute(
                    "SELECT 1 FROM persons WHERE person_id = ?", (mentioned_id,),
                ).fetchone() is None:
                    raise ValueError(f"Unknown Event Note mentioned person: {mentioned_id}")
            encounter_context["added_by"] = (
                (actor or {}).get("display_name")
                or (actor or {}).get("username")
                or encounter_context["added_by"]
            )
            observation_id = target_observation_id or str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:review:{review_id}"))
            now = utc_now()
            if not target_observation_id:
                conn.execute(
                    """
                    INSERT INTO observations(
                        observation_id, status, observed_at, location, context,
                        source, created_operation_id, created_at, updated_at
                    ) VALUES (?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id, observed_at, location,
                        json.dumps(encounter_context, separators=(",", ":")),
                        str(review["source"]), operation_id, now, now,
                    ),
                )
            staged_review_media = conn.execute(
                "SELECT media_id, media_path FROM photo_review_media WHERE review_id = ? ORDER BY ordinal, media_id",
                (review_id,),
            ).fetchall()
            for media_row in staged_review_media:
                _attach_observation_media(
                    conn, observation_id, media_row["media_id"], media_row["media_path"],
                    str(review["source"]), operation_id,
                )
            if not staged_review_media:
                _attach_observation_media(
                    conn, observation_id, review["media_id"], review["media_path"],
                    str(review["source"]), operation_id,
                )
            for face_id in sorted(assigned_by_face):
                assignment_id = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"sentriface:observation-face:{observation_id}:{face_id}",
                ))
                conn.execute(
                    """
                    INSERT INTO observation_face_assignments(
                        assignment_id, observation_id, review_id, face_id,
                        embedding_id, original_person_id, created_operation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assignment_id, observation_id, review_id, face_id,
                        embedding_by_face[face_id], assigned_by_face[face_id],
                        operation_id, now,
                    ),
                )
            primary_path = str(review["media_path"] or "")
            for media_path in sorted(staged_media_paths):
                if media_path == primary_path or (encounter_review and any(item["media_path"] == media_path for item in staged_review_media)):
                    continue
                _attach_observation_media(
                    conn, observation_id, media_path, media_path,
                    str(review["source"]), operation_id,
                )
            for canonical_id in sorted(canonical_participants):
                _add_observation_participant(
                    conn, observation_id, canonical_id, str(review["source"]), operation_id,
                )
            # A reused embedding retains its original enrollment image. Preserve
            # this face's actual Encounter media on its immutable review decision.
            for face_id, media_path in media_by_face.items():
                media = conn.execute(
                    "SELECT media_id FROM observation_media WHERE observation_id = ? AND media_path = ? ORDER BY media_id LIMIT 1",
                    (observation_id, media_path),
                ).fetchone()
                if media is None:
                    raise ValueError("Accepted face has no attached Event media")
                decision = conn.execute(
                    "SELECT recognition_detail FROM photo_review_faces WHERE review_id = ? AND face_id = ?",
                    (review_id, face_id),
                ).fetchone()
                detail = json.loads(decision[0] or "{}")
                detail["encounter_media_id"] = str(media[0])
                staged_face = next(r for r in face_rows if str(r["face_id"]) == face_id)
                detail["source_recognition_state"] = _review_face_recognition_state(
                    _staged_review_face_row(conn, staged_face["staged_face_type"], staged_face["staged_face_id"]), detail)
                conn.execute(
                    "UPDATE photo_review_faces SET recognition_detail = ? WHERE review_id = ? AND face_id = ?",
                    (json.dumps(detail), review_id, face_id),
                )
            finalized_at = utc_now()
            if not target_observation_id:
                conn.execute("UPDATE observations SET status = 'FINALIZED', finalized_at = ?, updated_at = ? WHERE observation_id = ?",
                             (finalized_at, finalized_at, observation_id))
            else:
                for person_id in canonical_participants:
                    if person_id not in _effective_observation_person_ids(conn, observation_id):
                        _append_participant_revision(conn, observation_id, person_id, "PRESENT", operation_id)
                canonical_participants.update({pid: pid for pid in _effective_observation_person_ids(conn, observation_id)})
                conn.execute("UPDATE observations SET updated_at = ? WHERE observation_id = ?", (finalized_at, observation_id))
            participant_ids = sorted(canonical_participants)
            detail_ids: list[str] = []
            for face_id, person_id, embedding_id, detail, detail_notes, mention_ids, decision in detail_inputs:
                detail_id = str(uuid.uuid4())
                person_name = str(conn.execute(
                    "SELECT name FROM persons WHERE person_id = ?", (person_id,),
                ).fetchone()[0])
                conn.execute(
                    """
                    INSERT INTO recognition_details(
                        detail_id, embedding_id, person_id, image_id, image_path,
                        name, decision, seen_date, seen_time, place_seen,
                        individual_count, event_occasion, rank, country,
                        importance, added_by, notes, created_at, observation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail_id, embedding_id, person_id,
                        str(detail.get("image_id") or f"{review['media_id']}#{face_id}"),
                        str(detail.get("image_path") or review["media_path"] or ""),
                        str(detail.get("name") or person_name),
                        str(detail.get("decision") or "accepted"),
                        str(observed_at or "").split("T", 1)[0],
                        str(encounter_context.get("start_time") or ""),
                        str(location or ""),
                        int(detail["individual_count"] if detail.get("individual_count") is not None else len(participant_ids)),
                        str(encounter_context.get("occasion") or ""),
                        _optional_text(detail.get("rank")),
                        _optional_text(detail.get("country")),
                        _optional_text(detail.get("importance")),
                        _optional_text(detail.get("added_by")),
                        detail_notes, utc_now(), observation_id,
                    ),
                )
                detail_ids.append(detail_id)
                note_key = (person_id, detail_notes, tuple(sorted(mention_ids)))
                if (detail_notes or mention_ids) and note_key not in created_note_keys:
                    note_ids.append(_create_review_person_note(
                        conn, person_id, detail_notes, mention_ids, operation_id, actor,
                        _optional_text(source) or str(review["source"]),
                        subject_type="RECOGNITION_DETAIL", subject_id=detail_id,
                    ))
                    created_note_keys.add(note_key)
            evidence_ids: list[str] = []
            included_pairs: list[tuple[str, str]] = []
            if encounter_review:
                ref_to_person = {
                    **{f"person:{person_id}": person_id for person_id in participant_ids},
                    **{f"draft:{key}": person_id for key, person_id in created_by_key.items()},
                }
                resolved_pairs: set[tuple[str, str]] = set()
                for relation in relation_rows:
                    first_id = ref_to_person.get(str(relation["first_ref"]))
                    second_id = ref_to_person.get(str(relation["second_ref"]))
                    if first_id is None or second_id is None:
                        raise ValueError("A Relation identity changed before finalization")
                    effective_pair = tuple(sorted((
                        _resolve_canonical_person_id(conn, first_id),
                        _resolve_canonical_person_id(conn, second_id),
                    )))
                    if effective_pair[0] == effective_pair[1] or effective_pair in resolved_pairs:
                        raise ValueError("Relations collapsed to an ambiguous canonical pair")
                    resolved_pairs.add(effective_pair)
                    conn.execute(
                        "UPDATE encounter_relation_decisions SET observation_id = ?, first_person_id = ?, "
                        "second_person_id = ?, operation_id = ?, support = ? WHERE decision_id = ?",
                        (observation_id, effective_pair[0], effective_pair[1], operation_id,
                         _encounter_pair_support(conn, observation_id, *effective_pair), relation["decision_id"]),
                    )
                    if relation["disposition"] == "INCLUDE":
                        included_pairs.append(effective_pair)
            else:
                included_pairs = [
                    (first_id, second_id)
                    for index, first_id in enumerate(participant_ids)
                    for second_id in participant_ids[index + 1:]
                ]
            if target_observation_id:
                if not conn.execute("SELECT 1 FROM encounter_relation_decisions WHERE observation_id = ? AND review_id <> ?", (observation_id, review_id)).fetchone():
                    original_participants = _effective_observation_person_ids(conn, observation_id)
                    # Newly accepted participants are already present: only pre-amendment pairs were settled.
                    original_participants = [pid for pid in original_participants if pid in original_participant_ids]
                    desired = _effective_encounter_relations(conn, observation_id)
                    for index, first in enumerate(original_participants):
                        for second in original_participants[index+1:]:
                            desired.setdefault((first, second), {"disposition": "INCLUDE", "support": _encounter_pair_support(conn, observation_id, first, second)})
                    _write_encounter_relation_revisions(conn, observation_id, desired, operation_id)
                _refresh_encounter_relation_support(conn, observation_id, operation_id)
                _, evidence_ids = _recalculate_observation_evidence(conn, observation_id, operation_id, source or "encounter-attachment")
                included_pairs = []
            for first_id, second_id in included_pairs:
                    evidence_ids.append(_insert_relationship_evidence(
                        conn,
                        evidence_type="CO_OBSERVED",
                        source_entity_type="OBSERVATION",
                        source_entity_id=observation_id,
                        source_person_id=first_id,
                        target_person_id=second_id,
                        relationship_type="ASSOCIATED_WITH",
                        directionality="UNDIRECTED",
                        source=_optional_text(source) or str(review["source"]),
                        created_operation_id=operation_id,
                        created_at=finalized_at,
                    ))
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            conn.execute(
                """
                UPDATE photo_reviews
                SET status = 'COMPLETED', observation_id = ?,
                    completed_operation_id = ?, completed_at = ?
                WHERE review_id = ? AND status = 'IN_PROGRESS'
                """,
                (observation_id, operation_id, finalized_at, review_id),
            )
            _remove_review_staging(conn, review_id)
            if encounter_review and review["session_id"] is not None:
                next_review = conn.execute(
                    "SELECT review_id FROM photo_reviews WHERE session_id = ? AND status = 'IN_PROGRESS' "
                    "AND review_phase = 'WAITING' ORDER BY sequence_number LIMIT 1",
                    (review["session_id"],),
                ).fetchone()
                if next_review is not None:
                    conn.execute("UPDATE photo_reviews SET review_phase = 'EVENT' WHERE review_id = ?", (next_review["review_id"],))
                else:
                    conn.execute("UPDATE init_sessions SET status = 'closed' WHERE session_id = ?", (review["session_id"],))
            result = {
                "review_id": review_id,
                "media_id": str(review["media_id"]),
                "media_ids": [
                    item.media_id for item in _list_observation_media(conn, observation_id)
                ],
                "observation_id": observation_id,
                "accepted_existing_person_ids": sorted({
                    str(row["person_id"]) for row in face_rows
                    if row["decision"] == "ACCEPT_EXISTING_PERSON"
                }),
                "created_person_ids": created_person_ids,
                "created_people": [
                    {
                        "person_id": person_id,
                        "name": str(conn.execute(
                            "SELECT name FROM persons WHERE person_id = ?", (person_id,),
                        ).fetchone()[0]),
                    }
                    for person_id in created_person_ids
                ],
                "excluded_count": sum(
                    row["decision"] in {"EXCLUDE", "SKIP"} for row in face_rows
                ),
                "participant_ids": participant_ids,
                "embedding_ids": embedding_ids,
                "embedding_assignments": embedding_by_face,
                "face_media": media_by_face,
                "note_ids": note_ids,
                "recognition_detail_ids": detail_ids,
                "graph_evidence_ids": evidence_ids,
                "graph_evidence_count": len(evidence_ids),
                "face_assignments": assigned_by_face,
            }
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def correct_observation_identity(
        self,
        observation_id: str,
        from_person_id: str,
        to_person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.observation.correct",
            )
            if existing is not None:
                if existing.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            observation = _require_observation(conn, observation_id)
            if observation["status"] != "FINALIZED":
                raise ValueError("Only a finalized observation can be corrected")
            _require_no_encounter_amendment(conn, observation_id)
            canonical_from_person_id = _resolve_canonical_person_id(conn, from_person_id)
            canonical_to_person_id = _resolve_canonical_person_id(conn, to_person_id)
            _require_active_review_person(conn, canonical_to_person_id)
            if canonical_from_person_id == canonical_to_person_id:
                raise ValueError("Correction source and target must be different")
            effective_before = _effective_observation_person_ids(conn, observation_id)
            if canonical_from_person_id not in effective_before:
                raise KeyError(
                    f"Person {canonical_from_person_id} is not an effective participant"
                )
            corrected_raw_before = _corrected_observation_person_ids(conn, observation_id)
            matching_raw_ids = {
                raw_person_id for raw_person_id in corrected_raw_before
                if _resolve_canonical_person_id(conn, raw_person_id)
                == canonical_from_person_id
            }
            assignments = _effective_face_assignments(conn, observation_id)
            matching = [
                item for item in assignments
                if _resolve_canonical_person_id(conn, item["current_person_id"])
                == canonical_from_person_id
            ]
            affected_entities = [
                {"entity_type": "observation", "entity_id": observation_id},
                {"entity_type": "person", "entity_id": canonical_from_person_id},
                {"entity_type": "person", "entity_id": canonical_to_person_id},
                *[
                    {"entity_type": "embedding", "entity_id": item["embedding_id"]}
                    for item in matching
                ],
            ]
            _begin_journal_operation(
                conn,
                "identity.observation.correct",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=affected_entities,
                details={
                    "observation_id": observation_id,
                    "from_person_id": canonical_from_person_id,
                    "to_person_id": canonical_to_person_id,
                    "raw_from_person_ids": sorted(matching_raw_ids),
                },
            )
            correction_ids: list[str] = []
            for assignment in matching:
                correction_ids.append(_insert_identity_correction(
                    conn,
                    correction_type="FACE_ASSIGNMENT",
                    observation_id=observation_id,
                    face_assignment_id=assignment["assignment_id"],
                    embedding_id=assignment["embedding_id"],
                    from_person_id=str(assignment["current_person_id"]),
                    to_person_id=canonical_to_person_id,
                    operation_id=operation_id,
                ))
            assignment_current_ids = {
                str(item["current_person_id"]) for item in matching
            }
            for raw_from_person_id in sorted(matching_raw_ids - assignment_current_ids):
                correction_ids.append(_insert_identity_correction(
                    conn,
                    correction_type="OBSERVATION_IDENTITY",
                    observation_id=observation_id,
                    face_assignment_id=None,
                    embedding_id=None,
                    from_person_id=raw_from_person_id,
                    to_person_id=canonical_to_person_id,
                    operation_id=operation_id,
                ))
            _revise_encounter_relations_for_identity_correction(
                conn, observation_id, canonical_from_person_id,
                canonical_to_person_id, operation_id,
            )
            _append_participant_revision(conn, observation_id, canonical_from_person_id, "REMOVED", operation_id)
            _append_participant_revision(conn, observation_id, canonical_to_person_id, "PRESENT", operation_id)
            effective_after, evidence_ids = _recalculate_observation_evidence(
                conn, observation_id, operation_id,
                _optional_text(source) or "identity-correction-service",
            )
            result = {
                "observation_id": observation_id,
                "from_person_id": canonical_from_person_id,
                "to_person_id": canonical_to_person_id,
                "raw_from_person_ids": sorted(matching_raw_ids),
                "previous_participant_ids": effective_before,
                "participant_ids": effective_after,
                "correction_ids": correction_ids,
                "graph_evidence_ids": evidence_ids,
                "graph_evidence_count": len(evidence_ids),
            }
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def move_face(
        self,
        embedding_id: str,
        to_person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.face.move",
            )
            if existing is not None:
                if existing.get("embedding_id") != embedding_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            target_person_id = _require_active_review_person(
                conn, _resolve_canonical_person_id(conn, to_person_id),
            )
            embedding = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at
                FROM embeddings e
                WHERE e.embedding_id = ?
                  AND e.deleted_at IS NULL
                """,
                (embedding_id,),
            ).fetchone()
            if embedding is None:
                raise KeyError(f"Unknown active embedding: {embedding_id}")
            if conn.execute("SELECT 1 FROM biometric_enrollment_history WHERE embedding_id=?", (embedding_id,)).fetchone():
                raise ValueError("Reference Only ownership cannot be moved; correct the Event or retire and deliberately add a Reference")
            raw_from_person_id = _raw_embedding_owner_person_id(conn, embedding)
            from_person_id = _effective_embedding_owner_person_id(conn, embedding)
            if from_person_id == target_person_id:
                raise ValueError("Face already belongs to the selected person")
            source = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ?",
                (from_person_id,),
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown current embedding owner: {from_person_id}")
            assignments = conn.execute(
                """
                SELECT observation_id FROM observation_face_assignments
                WHERE embedding_id = ? ORDER BY observation_id
                """,
                (embedding_id,),
            ).fetchall()
            affected_observation_ids = sorted({str(row["observation_id"]) for row in assignments})
            for observation_id in affected_observation_ids:
                _require_no_encounter_amendment(conn, observation_id)
            _begin_journal_operation(
                conn,
                "identity.face.move",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": from_person_id},
                    {"entity_type": "person", "entity_id": target_person_id},
                    *[
                        {"entity_type": "observation", "entity_id": item}
                        for item in affected_observation_ids
                    ],
                ],
                details={
                    "raw_owner_person_id": raw_from_person_id,
                    "from_person_id": from_person_id,
                    "to_person_id": target_person_id,
                },
            )
            correction_ids = [_insert_identity_correction(
                conn,
                correction_type="FACE_OWNERSHIP",
                observation_id=None,
                face_assignment_id=None,
                embedding_id=embedding_id,
                from_person_id=from_person_id,
                to_person_id=target_person_id,
                operation_id=operation_id,
            )]
            for observation_id in affected_observation_ids:
                for assignment in _effective_face_assignments(conn, observation_id):
                    if (
                        assignment["embedding_id"] == embedding_id
                        and _resolve_canonical_person_id(
                            conn, assignment["current_person_id"],
                        ) == from_person_id
                    ):
                        correction_ids.append(_insert_identity_correction(
                            conn,
                            correction_type="FACE_ASSIGNMENT",
                            observation_id=observation_id,
                            face_assignment_id=assignment["assignment_id"],
                            embedding_id=embedding_id,
                            from_person_id=assignment["current_person_id"],
                            to_person_id=target_person_id,
                            operation_id=operation_id,
                        ))
            source_metadata = json.loads(source["metadata"] or "{}")
            if source_metadata.get("representative_embedding_id") == embedding_id:
                source_metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(source_metadata, separators=(",", ":")), from_person_id),
                )
            remaining = any(
                _effective_embedding_owner_person_id(conn, item) == from_person_id
                for item in conn.execute(
                    "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
                ).fetchall()
            )
            if not remaining:
                conn.execute(
                    """
                    UPDATE persons
                    SET biometric_status = 'NO_FACE', enrollment_status = 'placeholder'
                    WHERE person_id = ?
                    """,
                    (from_person_id,),
                )
            _mark_person_enrolled(conn, target_person_id)
            graph_evidence_ids: list[str] = []
            participants_by_observation: dict[str, list[str]] = {}
            for observation_id in affected_observation_ids:
                participants, evidence_ids = _recalculate_observation_evidence(
                    conn, observation_id, operation_id,
                    _optional_text(source) or "identity-correction-service",
                )
                participants_by_observation[observation_id] = participants
                graph_evidence_ids.extend(evidence_ids)
            if not affected_observation_ids:
                _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "embedding_id": embedding_id,
                "raw_owner_person_id": raw_from_person_id,
                "source_person_id": from_person_id,
                "target_person_id": target_person_id,
                "moved": True,
                "changed": True,
                "affected_observation_ids": affected_observation_ids,
                "participants_by_observation": participants_by_observation,
                "correction_ids": correction_ids,
                "graph_evidence_ids": graph_evidence_ids,
                "graph_evidence_count": len(graph_evidence_ids),
            }
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def add_face_to_person(
        self,
        review_id: str,
        person_id: str,
        operation_id: str,
        *,
        actor: dict | None = None,
        source: str | None = None,
        no_context_acknowledged: bool = False,
    ) -> dict:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(
                conn, operation_id, "identity.face.add",
            )
            if existing is not None:
                if existing.get("review_id") != review_id or existing.get("person_id") != person_id or no_context_acknowledged is not True:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing
            _require_reference_mutation_person(conn, person_id)
            person_id = _require_active_review_person(
                conn, _resolve_canonical_person_id(conn, person_id),
            )
            _require_reference_mutation_person(conn, person_id)
            if no_context_acknowledged is not True:
                raise ValueError("Confirm that no reliable Event context is available")
            review = conn.execute(
                "SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,),
            ).fetchone()
            if review is None:
                raise KeyError(f"Unknown photo review: {review_id}")
            if review["status"] != "IN_PROGRESS":
                raise ValueError("Only an in-progress review can add a face")
            if review["source"] != "reference-only":
                raise ValueError("Use the cropped single-face Reference Only admission flow")
            faces = conn.execute(
                "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id",
                (review_id,),
            ).fetchall()
            if len(faces) != 1:
                raise ValueError("Reference Only requires exactly one detected face; crop the image and upload again")
            if not faces or any(row["decision"] in {None, "SKIP"} for row in faces):
                raise ValueError("Every detected face requires a final decision before completion")
            accepted = [row for row in faces if row["decision"] == "ACCEPT_EXISTING_PERSON"]
            if not accepted:
                raise ValueError("Add Face requires at least one accepted face")
            if any(
                _resolve_canonical_person_id(conn, str(row["person_id"] or "")) != person_id
                for row in accepted
            ):
                raise ValueError("Every accepted face must target the selected existing person")
            if any(row["decision"] == "ACCEPT_NEW_PERSON" for row in faces):
                raise ValueError("Add Face cannot create another identity")
            _begin_journal_operation(
                conn,
                "identity.face.add",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-correction-service",
                affected_entities=[
                    {"entity_type": "review", "entity_id": review_id},
                    {"entity_type": "person", "entity_id": person_id},
                    *[
                        {"entity_type": "review_face", "entity_id": str(row["face_id"])}
                        for row in accepted
                    ],
                ],
                details={"person_id": person_id, "accepted_face_count": len(accepted)},
            )
            embedding_ids: list[str] = []
            created_embedding_ids: list[str] = []
            created_reference_ids: list[str] = []
            for row in accepted:
                staged = _staged_review_face_row(
                    conn, row["staged_face_type"], row["staged_face_id"],
                )
                recognition_state = _review_face_recognition_state(
                    staged, json.loads(row["recognition_detail"] or "{}"),
                )
                media_id = media_content_identity(staged["source_image"])
                _require_reference_media_role(conn, media_id, person_id, self.database_key)
                references = _reference_records(conn, person_id)
                duplicate_reference = next((r for r in references if r["media_id"] == media_id), None)
                if duplicate_reference is None:
                    duplicate_reference = next((r for r in references if r["active"] and conn.execute(
                        "SELECT vector FROM embeddings WHERE embedding_id = ?", (r["embedding_id"],)
                    ).fetchone()[0] == staged["vector"]), None)
                if duplicate_reference is not None:
                    if not duplicate_reference["active"]:
                        raise ValueError("This Reference is retired; restore the existing Reference instead")
                    embedding_ids.append(duplicate_reference["embedding_id"])
                    continue
                if _active_reference_count(conn, person_id) >= 4:
                    raise ValueError("Four active Recognition References are already present; retire one before adding another")
                for reference in _reference_records(conn):
                    if reference["active"] and reference["canonical_person_id"] != person_id and conn.execute(
                        "SELECT vector FROM embeddings WHERE embedding_id = ?", (reference["embedding_id"],)
                    ).fetchone()[0] == staged["vector"]:
                        raise ValueError("This exact biometric sample is already an active Reference for another Person")
                duplicate = conn.execute(
                    """
                    SELECT embedding_id, recognition_state FROM embeddings
                    WHERE person_id = ? AND vector = ? AND deleted_at IS NULL
                    """,
                    (person_id, staged["vector"]),
                ).fetchone()
                if duplicate is None:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at, recognition_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id, person_id, staged["vector"], staged["quality_score"],
                            staged["source_image"], staged["crop_path"], utc_now(),
                            recognition_state,
                        ),
                    )
                    created_embedding_ids.append(embedding_id)
                else:
                    embedding_id = str(duplicate["embedding_id"])
                    if recognition_state == "POOR_ACCEPTED" and duplicate["recognition_state"] == "PROOF_ONLY":
                        conn.execute(
                            "UPDATE embeddings SET recognition_state = 'POOR_ACCEPTED' WHERE embedding_id = ?",
                            (embedding_id,),
                        )
                embedding_ids.append(embedding_id)
                reference_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:enrollment:{operation_id}:{embedding_id}"))
                conn.execute(
                    """
                    INSERT OR IGNORE INTO biometric_enrollment_history(
                        enrollment_id, embedding_id, person_id, review_id, operation_id, created_at,
                        source_media_id, source_image, crop_path, recognition_state, no_context_declared
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reference_id,
                        embedding_id, person_id, review_id, operation_id, utc_now(),
                        media_id, staged["source_image"], staged["crop_path"], recognition_state, 1,
                    ),
                )
                created_reference_ids.append(reference_id)
            _mark_person_enrolled(conn, person_id)
            if not created_reference_ids:
                conn.execute("DELETE FROM photo_review_media WHERE review_id=?", (review_id,))
                conn.execute("UPDATE photo_reviews SET media_path=NULL WHERE review_id=?", (review_id,))
            completed_at = utc_now()
            conn.execute(
                """
                UPDATE photo_reviews
                SET status = 'COMPLETED', completed_operation_id = ?, completed_at = ?
                WHERE review_id = ? AND status = 'IN_PROGRESS'
                """,
                (operation_id, completed_at, review_id),
            )
            _remove_review_staging(conn, review_id)
            result = {
                "review_id": review_id,
                "person_id": person_id,
                "embedding_ids": embedding_ids,
                "created_embedding_ids": created_embedding_ids,
                "created_reference_ids": created_reference_ids,
                "created_person_ids": [],
                "observation_id": None,
                "graph_evidence_ids": [],
                "graph_evidence_count": 0,
            }
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_recognition_references(self, person_id: str) -> dict:
        with self._connect() as conn:
            records = _reference_records(conn, person_id)
            authority = _source_sample_authority(conn)
            for record in records:
                sample = authority[record["embedding_id"]]
                record["recognition_conflict"] = sample["conflict"]
                person = conn.execute("SELECT lifecycle_status FROM persons WHERE person_id = ?", (record["canonical_person_id"],)).fetchone()
                available = conn.execute("SELECT deleted_at FROM embeddings WHERE embedding_id=?", (record["embedding_id"],)).fetchone()[0] is None
                record["recognition_eligible"] = bool(available and record["active"] and person[0] == "ACTIVE"
                    and not sample["conflict"] and record["recognition_state"] != "PROOF_ONLY")
            drafts = [dict(row) for row in conn.execute("""SELECT r.review_id, p.quality_status AS quality, r.media_path AS image_path
                FROM photo_reviews r JOIN photo_review_faces f ON f.review_id=r.review_id
                JOIN pending_additions p ON p.pending_id=f.staged_face_id
                WHERE r.source='reference-only' AND r.status='IN_PROGRESS' AND f.person_id=? ORDER BY r.created_at""", (person_id,))]
            canonical = _resolve_canonical_person_id(conn, person_id)
            encounter_coverage = any(
                authority[a["embedding_id"]]["owner"] == canonical
                and authority[a["embedding_id"]]["state"] != "PROOF_ONLY"
                for row in conn.execute("SELECT observation_id FROM observations WHERE status='FINALIZED'").fetchall()
                for a in _effective_face_assignments(conn, row[0])
                if _resolve_canonical_person_id(conn, a["current_person_id"]) == canonical)
            return {"references": records, "drafts": drafts, "active_count": _active_reference_count(conn, person_id), "limit": 4,
                    "has_encounter_coverage": encounter_coverage}

    def set_reference_active(self, reference_id: str, person_id: str, active: bool, operation_id: str,
                             *, actor: dict | None = None, failure_injector=None) -> dict:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(conn, operation_id, "identity.reference.lifecycle")
            if existing is not None:
                if existing.get("reference_id") != reference_id or existing.get("active") != active or existing.get("person_id") != person_id:
                    raise ValueError("Operation ID already used with another Reference command")
                return existing
            _require_reference_mutation_person(conn, person_id)
            reference = next((r for r in _reference_records(conn, person_id) if r["reference_id"] == reference_id), None)
            if reference is None:
                raise ValueError("Reference does not belong to this canonical Person")
            if active and not reference["active"]:
                already_counted = any(r["active"] and r["media_id"] == reference["media_id"]
                                      for r in _reference_records(conn, person_id))
                if not already_counted and _active_reference_count(conn, person_id) >= 4:
                    raise ValueError("Retire a Reference before restoring: maximum four active sources")
                if conn.execute("SELECT 1 FROM embeddings WHERE embedding_id=? AND deleted_at IS NULL", (reference["embedding_id"],)).fetchone() is None:
                    raise ValueError("This Reference sample is unavailable")
            _begin_journal_operation(conn, "identity.reference.lifecycle", operation_id=operation_id, actor=actor,
                source="recognition-reference-management", affected_entities=[{"entity_type":"person","entity_id":person_id}],
                details={"reference_id": reference_id, "active": active})
            if reference["active"] != active:
                conn.execute("INSERT INTO recognition_reference_revisions VALUES (?, ?, ?, ?, ?)",
                             (str(uuid.uuid4()), reference_id, int(active), operation_id, utc_now()))
            if failure_injector:
                failure_injector("reference_lifecycle")
            result = {"reference_id": reference_id, "active": active, "person_id": person_id}
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def validate_reference_media(self, media_path: str, person_id: str) -> None:
        with self._connect() as conn:
            _require_reference_mutation_person(conn, person_id)
            _require_reference_media_role(conn, media_content_identity(media_path, self.database_key), person_id, self.database_key)

    def validate_encounter_media(self, media_path: str) -> None:
        with self._connect() as conn:
            _require_encounter_media_role(conn, media_content_identity(media_path, self.database_key))

    def cancel_reference_review(self, review_id: str) -> None:
        with self._connect() as conn:
            review = conn.execute("SELECT source, status FROM photo_reviews WHERE review_id=?", (review_id,)).fetchone()
            if review is None or review["source"] != "reference-only" or review["status"] == "COMPLETED":
                raise ValueError("Only an uncommitted Reference draft can be cancelled")
            _remove_review_staging(conn, review_id)
            conn.execute("DELETE FROM photo_review_media WHERE review_id=?", (review_id,))
            conn.execute("UPDATE photo_reviews SET status='CANCELLED', media_path=NULL WHERE review_id=?", (review_id,))

    def list_corrections_for_observation(
        self, observation_id: str,
    ) -> list[IdentityCorrection]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM identity_corrections
                WHERE observation_id = ? ORDER BY created_at, correction_id
                """,
                (observation_id,),
            ).fetchall()
        return [_identity_correction_from_row(row) for row in rows]

    def list_corrections_for_embedding(
        self, embedding_id: str,
    ) -> list[IdentityCorrection]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM identity_corrections
                WHERE embedding_id = ? ORDER BY created_at, correction_id
                """,
                (embedding_id,),
            ).fetchall()
        return [_identity_correction_from_row(row) for row in rows]

    def get_observation(self, observation_id: str) -> Observation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM effective_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        return _observation_from_row(row) if row else None

    def update_observation(
        self,
        observation_id: str,
        operation_id: str,
        *,
        observed_at: str | None = None,
        location: str | None = None,
        context: dict | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> Observation:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.update",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _require_observation(conn, observation_id)
                return _observation_from_row(row)
            current = _require_draft_observation(conn, observation_id)
            if context is None:
                context_payload = current["context"]
            else:
                _, context_payload = _journal_json_object(context, "observation context")
            _begin_journal_operation(
                conn,
                "observation.update",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                ],
            )
            updated_at = utc_now()
            conn.execute(
                """
                UPDATE observations
                SET observed_at = ?, location = ?, context = ?, source = ?, updated_at = ?
                WHERE observation_id = ? AND status = 'DRAFT'
                """,
                (
                    current["observed_at"] if observed_at is None else _optional_text(observed_at),
                    current["location"] if location is None else _optional_text(location),
                    context_payload,
                    current["source"] if source is None else _optional_text(source),
                    updated_at,
                    observation_id,
                ),
            )
            result = {"observation_id": observation_id, "updated": True}
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute(
                "SELECT * FROM effective_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(updated)

    def attach_observation_media(
        self,
        observation_id: str,
        media_id: str,
        operation_id: str,
        *,
        media_path: str | None = None,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationMedia:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.media.attach",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = conn.execute(
                    """
                    SELECT observation_id, media_id, media_path, source, operation_id, created_at
                    FROM observation_media WHERE observation_id = ? AND media_id = ?
                    """,
                    (observation_id, existing_result.get("media_id")),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed media attachment is missing its membership")
                return _observation_media_from_row(row)
            _require_draft_observation(conn, observation_id)
            _begin_journal_operation(
                conn,
                "observation.media.attach",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "media", "entity_id": str(media_id).strip()},
                ],
            )
            item, changed = _attach_observation_media(
                conn, observation_id, media_id, media_path, source, operation_id,
            )
            _transition_journal_operation(
                conn,
                operation_id,
                "COMMITTED",
                {"observation_id": observation_id, "media_id": item.media_id, "changed": changed},
            )
            return item

    def add_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> ObservationParticipant:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.participant.add",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                participants = _list_raw_observation_participants(conn, observation_id)
                for participant in participants:
                    if participant.person_id == existing_result.get("person_id"):
                        return participant
                raise RuntimeError("Committed participant addition is missing its participant")
            _require_draft_observation(conn, observation_id)
            raw_person_id = str(person_id).strip()
            if not raw_person_id:
                raise ValueError("Person ID is required")
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (raw_person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {raw_person_id}")
            _begin_journal_operation(
                conn,
                "observation.participant.add",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "person", "entity_id": raw_person_id},
                ],
            )
            participant, changed = _add_observation_participant(
                conn, observation_id, raw_person_id, source, operation_id,
            )
            _transition_journal_operation(
                conn,
                operation_id,
                "COMMITTED",
                {
                    "observation_id": observation_id,
                    "person_id": participant.person_id,
                    "canonical_person_id": participant.canonical_person_id,
                    "changed": changed,
                },
            )
            return participant

    def remove_observation_participant(
        self,
        observation_id: str,
        person_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.participant.remove",
            )
            if existing_result is not None:
                if (
                    existing_result.get("observation_id") != observation_id
                    or existing_result.get("person_id") != str(person_id).strip()
                ):
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return existing_result
            _require_draft_observation(conn, observation_id)
            raw_person_id = str(person_id).strip()
            if not raw_person_id:
                raise ValueError("Person ID is required")
            _begin_journal_operation(
                conn,
                "observation.participant.remove",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                    {"entity_type": "person", "entity_id": raw_person_id},
                ],
            )
            cursor = conn.execute(
                "DELETE FROM observation_participants WHERE observation_id = ? AND person_id = ?",
                (observation_id, raw_person_id),
            )
            result = {
                "observation_id": observation_id,
                "person_id": raw_person_id,
                "removed": bool(cursor.rowcount),
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        return self.list_effective_observation_participants(observation_id)

    def list_raw_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_raw_observation_participants(conn, observation_id)

    def list_effective_observation_participants(
        self, observation_id: str,
    ) -> list[ObservationParticipant]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_observation_participants(conn, observation_id)

    def list_observation_media(self, observation_id: str) -> list[ObservationMedia]:
        with self._connect() as conn:
            _require_observation(conn, observation_id)
            return _list_observation_media(conn, observation_id)

    def correct_encounter(self, observation_id: str, operation_id: str, *, expected_revision: str,
                          event_details: dict | None = None, participant_correction: dict | None = None,
                          relations: list[dict] | None = None, actor: dict | None = None, source: str | None = None) -> dict:
        """Apply reviewed forward corrections, evidence and journal in one transaction."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(conn, operation_id, "encounter.correct")
            if existing is not None:
                if existing["observation_id"] != observation_id:
                    raise KeyError("Operation ID belongs to another Event")
                return existing
            _require_encounter_revision(conn, observation_id, expected_revision)
            _require_no_encounter_amendment(conn, observation_id)
            observation = _require_observation(conn, observation_id)
            before = _encounter_read_record(conn, observation)
            historical_relations = [{"first_person_id": pair[0], "second_person_id": pair[1],
                "disposition": value["disposition"], "support": value["support"]}
                for pair, value in _effective_encounter_relations(conn, observation_id).items()]
            _begin_journal_operation(conn, "encounter.correct", operation_id=operation_id, actor=actor,
                                     source=source or "encounter-management", affected_entities=[
                                         {"entity_type": "observation", "entity_id": observation_id},
                                         *[{"entity_type": "person", "entity_id": person_id} for person_id in sorted(set(before["participant_ids"] + before["mentioned_person_ids"] +
                                             [value for key, value in (participant_correction or {}).items() if key in {"person_id", "to_person_id"}]) )]],
                                     details={"historical_value": before})
            if event_details is not None:
                allowed = {"date", "time", "end_time", "time_precision", "place_seen", "event_occasion", "event_context", "event_notes", "event_mentioned_person_ids"}
                if not isinstance(event_details, dict) or set(event_details) - allowed:
                    raise ValueError("Unknown Event detail field")
                merged_details = {**_encounter_event_details(observation), **event_details}
                observed_at, location, context = _review_encounter_metadata([merged_details])
                for pid in context["event_mentioned_person_ids"]:
                    _resolve_canonical_person_id(conn, pid)
                context["added_by"] = json.loads(observation["context"]).get("added_by")
                conn.execute("INSERT INTO encounter_metadata_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (str(uuid.uuid4()), observation_id, observed_at, location, json.dumps(context), operation_id, utc_now()))
            if participant_correction:
                if set(participant_correction) - {"action", "person_id", "to_person_id"}:
                    raise ValueError("Unknown participant correction field")
                action = str(participant_correction.get("action", "")).upper()
                pid = _resolve_canonical_person_id(conn, str(participant_correction.get("person_id", "")))
                participants = _effective_observation_person_ids(conn, observation_id)
                if action == "REASSIGN":
                    target = _require_active_review_person(conn, str(participant_correction.get("to_person_id", "")))
                    target = _resolve_canonical_person_id(conn, target)
                    if pid not in participants or target == pid:
                        raise ValueError("Select a current participant and a different active Person")
                    assignments = [a for a in _effective_face_assignments(conn, observation_id)
                                   if _resolve_canonical_person_id(conn, a["current_person_id"]) == pid]
                    for assignment in assignments:
                        _insert_identity_correction(conn, correction_type="FACE_ASSIGNMENT", observation_id=observation_id,
                            face_assignment_id=assignment["assignment_id"], embedding_id=assignment["embedding_id"],
                            from_person_id=assignment["current_person_id"], to_person_id=target, operation_id=operation_id)
                    for raw in _corrected_observation_person_ids(conn, observation_id):
                        if _resolve_canonical_person_id(conn, raw) == pid:
                            _insert_identity_correction(conn, correction_type="OBSERVATION_IDENTITY", observation_id=observation_id,
                                face_assignment_id=None, embedding_id=None, from_person_id=raw, to_person_id=target, operation_id=operation_id)
                    # A prior explicit presence revision needs a forward removal/presence revision too.
                    _add_observation_participant(conn, observation_id, target, "identity-correction", operation_id)
                    for person, disposition in ((pid, "REMOVED"), (target, "PRESENT")):
                        _append_participant_revision(conn, observation_id, person, disposition, operation_id)
                    _revise_encounter_relations_for_identity_correction(conn, observation_id, pid, target, operation_id)
                elif action in {"ADD", "REMOVE"}:
                    if action == "ADD":
                        _require_active_review_person(conn, pid)
                        if pid in participants:
                            raise ValueError("Person is already a participant")
                        _add_observation_participant(conn, observation_id, pid, "encounter-correction", operation_id)
                    elif pid not in participants or len(participants) <= 1:
                        raise ValueError("Cannot remove the last or an absent participant")
                    _append_participant_revision(conn, observation_id, pid, "PRESENT" if action == "ADD" else "REMOVED", operation_id)
                else:
                    raise ValueError("Participant correction must be ADD, REMOVE or REASSIGN")
            if participant_correction and participant_correction.get("action", "").upper() == "REASSIGN":
                for affected in (pid, target):
                    owns_faces = any(_effective_embedding_owner_person_id(conn, e) == affected for e in conn.execute("SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"))
                    if owns_faces:
                        _mark_person_enrolled(conn, affected)
                    else:
                        conn.execute("UPDATE persons SET biometric_status = 'NO_FACE', enrollment_status = 'placeholder' WHERE person_id = ?", (affected,))
            participants = _effective_observation_person_ids(conn, observation_id)
            if not participants:
                raise ValueError("An Event needs at least one participant")
            desired = _effective_encounter_relations(conn, observation_id)
            # Legacy finalized reviews have implicit positive pair authority; materialize it on first correction.
            if not conn.execute("SELECT 1 FROM encounter_relation_decisions WHERE observation_id = ?", (observation_id,)).fetchone():
                desired = {tuple(sorted((a, b))): {"disposition": "INCLUDE", "support": _encounter_pair_support(conn, observation_id, a, b)}
                           for index, a in enumerate(before["participant_ids"]) for b in before["participant_ids"][index+1:]}
                if participant_correction and participant_correction.get("action", "").upper() == "REASSIGN":
                    desired = {tuple(sorted(target if member == pid else member for member in pair)): value
                               for pair, value in desired.items() if len({target if member == pid else member for member in pair}) == 2}
            desired = {pair: value for pair, value in desired.items() if set(pair).issubset(participants)}
            supplied_pairs = set()
            for relation in relations or []:
                if set(relation) != {"first_person_id", "second_person_id", "disposition"}:
                    raise ValueError("Invalid Relation correction")
                pair = tuple(sorted(_resolve_canonical_person_id(conn, relation[key]) for key in ("first_person_id", "second_person_id")))
                disposition = str(relation["disposition"]).upper()
                if pair[0] == pair[1] or not set(pair).issubset(participants) or disposition not in {"INCLUDE", "EXCLUDE"} or pair in supplied_pairs:
                    raise ValueError("Invalid or duplicate effective Relation pair")
                supplied_pairs.add(pair)
                desired[pair] = {"disposition": disposition, "support": _encounter_pair_support(conn, observation_id, *pair)}
            candidates = {(a, b) for index, a in enumerate(participants) for b in participants[index+1:]}
            if set(desired) != candidates:
                raise ValueError("Every new participant pair requires an explicit INCLUDE or EXCLUDE decision")
            _write_encounter_relation_revisions(conn, observation_id, desired, operation_id)
            _refresh_encounter_relation_support(conn, observation_id, operation_id)
            _, evidence_ids = _recalculate_observation_evidence(conn, observation_id, operation_id, source or "encounter-management")
            conn.execute("UPDATE observations SET updated_at = ? WHERE observation_id = ?", (utc_now(), observation_id))
            after = _encounter_read_record(conn, _require_observation(conn, observation_id))
            result = {"observation_id": observation_id, "historical_value": before, "effective_value": after,
                      "participant_correction": participant_correction, "graph_evidence_ids": evidence_ids,
                      "historical_relations": historical_relations,
                      "effective_relations": [{"first_person_id": pair[0], "second_person_id": pair[1], "disposition": row["disposition"], "support": row["support"]}
                          for pair, row in _effective_encounter_relations(conn, observation_id).items()]}
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def create_manual_association(self, first_person_id: str, second_person_id: str, operation_id: str,
                                  *, actor: dict | None = None, source: str | None = None) -> dict:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(conn, operation_id, "manual_association.create")
            pair = tuple(sorted(_resolve_canonical_person_id(conn, pid) for pid in (first_person_id, second_person_id)))
            if existing is not None:
                committed_pair = tuple(sorted(_resolve_canonical_person_id(conn, pid) for pid in existing["person_ids"]))
                if committed_pair != pair:
                    raise KeyError("Operation ID belongs to another association")
                return existing
            if pair[0] == pair[1]:
                raise ValueError("A Person cannot be associated with themselves")
            for pid in pair:
                _require_active_review_person(conn, pid)
            _begin_journal_operation(conn, "manual_association.create", operation_id=operation_id, actor=actor,
                source=source or "manual-association", affected_entities=[{"entity_type": "person", "entity_id": pid} for pid in pair], details={})
            # Different requests for the same canonical pair are one standing
            # assertion. Keep historical rows and journal the reconciled result.
            for assertion in conn.execute(
                "SELECT evidence_id, source_person_id, target_person_id FROM relationship_evidence "
                "WHERE evidence_type = 'MANUAL_ASSOCIATION' AND source_entity_type = 'MANUAL_ASSERTION' "
                "AND directionality = 'UNDIRECTED' AND active = 1 ORDER BY created_at, evidence_id"
            ):
                existing_pair = tuple(sorted(_resolve_canonical_person_id(conn, str(assertion[key]))
                    for key in ("source_person_id", "target_person_id")))
                if existing_pair == pair:
                    result = {"evidence_id": str(assertion["evidence_id"]), "person_ids": list(pair)}
                    _transition_journal_operation(conn, operation_id, "COMMITTED", result)
                    return result
            evidence_id = _insert_relationship_evidence(conn, evidence_type="MANUAL_ASSOCIATION", source_entity_type="MANUAL_ASSERTION",
                source_entity_id=operation_id, source_person_id=pair[0], target_person_id=pair[1], relationship_type="ASSOCIATED_WITH",
                directionality="UNDIRECTED", source=source or "manual-association", created_operation_id=operation_id, created_at=utc_now())
            _replace_graph_projection(conn)
            result = {"evidence_id": evidence_id, "person_ids": list(pair)}
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def retire_manual_association(self, evidence_id: str, operation_id: str, *, actor: dict | None = None, source: str | None = None) -> dict:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = _existing_committed_operation_result(conn, operation_id, "manual_association.retire")
            if existing is not None:
                if existing["evidence_id"] != evidence_id:
                    raise KeyError("Operation ID belongs to another association")
                return existing
            row = conn.execute("SELECT * FROM relationship_evidence WHERE evidence_id = ? AND evidence_type = 'MANUAL_ASSOCIATION'", (evidence_id,)).fetchone()
            if row is None or not row["active"]:
                raise ValueError("Select an active Manual Association")
            _begin_journal_operation(conn, "manual_association.retire", operation_id=operation_id, actor=actor,
                source=source or "manual-association", affected_entities=[
                    {"entity_type": "evidence", "entity_id": evidence_id},
                    *[{"entity_type": "person", "entity_id": pid} for pid in sorted({
                        str(row["source_person_id"]), str(row["target_person_id"]),
                        _resolve_canonical_person_id(conn, str(row["source_person_id"])),
                        _resolve_canonical_person_id(conn, str(row["target_person_id"])),
                    })]], details={})
            conn.execute("UPDATE relationship_evidence SET active = 0, deactivated_operation_id = ?, deactivated_at = ? WHERE evidence_id = ?",
                         (operation_id, utc_now(), evidence_id))
            _replace_graph_projection(conn)
            result = {"evidence_id": evidence_id, "retired": True}
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_person_encounter_media(self, person_id: str) -> list[dict]:
        with self._connect() as conn:
            conn.execute("BEGIN")
            canonical = _resolve_canonical_person_id(conn, person_id)
            items = {}
            for observation in conn.execute("SELECT observation_id FROM effective_observations WHERE status = 'FINALIZED'"):
                oid = str(observation[0])
                for path in _encounter_person_media(conn, oid, canonical):
                    item = items.setdefault(path, {"media_path": path, "observation_ids": []})
                    item["observation_ids"].append(oid)
            return list(items.values())

    def query_encounters(
        self, *, limit: int = 25, cursor: str = "", search: str = "",
        date_from: str = "", date_to: str = "", location: str = "",
        context: str = "", participant_id: str = "", mentioned_person_id: str = "",
        person_id: str = "", person_status: str = "",
    ) -> dict:
        """Bounded read of finalized observations; mentions never become participants."""
        page_size = max(1, min(int(limit), 50))
        if context and context not in {"ordinary", "public", "unknown"}:
            raise ValueError("Unknown Event context")
        if person_status and person_status not in {"PRESENT", "MENTIONED", "BOTH"}:
            raise ValueError("Unknown Person Event status")
        with self._connect() as conn:
            conn.execute("BEGIN")
            requested = {
                name: _resolve_canonical_person_id(conn, value) if value else ""
                for name, value in (
                    ("participant", participant_id),
                    ("mentioned", mentioned_person_id),
                    ("person", person_id),
                )
            }
            conditions = ["status = 'FINALIZED'"]
            arguments: list[str] = []
            if search.strip():
                conditions.append("(LOWER(COALESCE(location, '')) LIKE ? OR LOWER(COALESCE(json_extract(context, '$.occasion'), '')) LIKE ?)")
                needle = f"%{search.strip().lower()}%"
                arguments.extend((needle, needle))
            if location.strip():
                conditions.append("LOWER(COALESCE(location, '')) LIKE ?")
                arguments.append(f"%{location.strip().lower()}%")
            if date_from:
                conditions.append("SUBSTR(COALESCE(observed_at, created_at), 1, 10) >= ?")
                arguments.append(date_from)
            if date_to:
                conditions.append("SUBSTR(COALESCE(observed_at, created_at), 1, 10) <= ?")
                arguments.append(date_to)
            if context:
                conditions.append("COALESCE(json_extract(context, '$.category'), 'unknown') = ?")
                arguments.append(context)
            if cursor:
                try:
                    cursor_time, cursor_id = cursor.rsplit("|", 1)
                except ValueError as exc:
                    raise ValueError("Invalid Events page; reload the Events list") from exc
                conditions.append("(COALESCE(observed_at, created_at), observation_id) < (?, ?)")
                arguments.extend((cursor_time, cursor_id))
            items: list[dict] = []
            last_scanned: tuple[str, str] | None = None
            while len(items) <= page_size:
                where = " AND ".join(conditions)
                rows = conn.execute(
                    f"SELECT * FROM effective_observations WHERE {where} "
                    "ORDER BY COALESCE(observed_at, created_at) DESC, observation_id DESC LIMIT 100",
                    arguments,
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    last_scanned = (str(row["observed_at"] or row["created_at"]), str(row["observation_id"]))
                    record = _encounter_read_record(conn, row)
                    participant_ids = set(record["participant_ids"])
                    mention_ids = set(record["mentioned_person_ids"])
                    if requested["participant"] and requested["participant"] not in participant_ids:
                        continue
                    if requested["mentioned"] and requested["mentioned"] not in mention_ids:
                        continue
                    if requested["person"]:
                        selected = requested["person"]
                        record["person_status"] = (
                            "BOTH" if selected in participant_ids and selected in mention_ids else
                            "PRESENT" if selected in participant_ids else
                            "MENTIONED" if selected in mention_ids else ""
                        )
                        if not record["person_status"] or (person_status and record["person_status"] != person_status):
                            continue
                        record["person_media"] = []
                        record["sighting_notes"] = []
                        if selected in participant_ids:
                            record["person_media"] = _encounter_person_media(conn, record["observation_id"], selected)
                            record["sighting_notes"] = [str(note["content"]) for note in conn.execute(
                                "SELECT d.person_id, d.embedding_id, r.content FROM recognition_details d JOIN notes n ON n.subject_id = d.detail_id "
                                "JOIN note_revisions r ON r.note_id = n.note_id WHERE d.observation_id = ? AND n.status = 'ACTIVE' "
                                "AND r.revision_number = (SELECT MAX(r2.revision_number) FROM note_revisions r2 WHERE r2.note_id = n.note_id)",
                                (record["observation_id"],)) if _encounter_detail_person(conn, record["observation_id"], note) == selected]
                    items.append(record)
                    if len(items) > page_size:
                        break
                if len(items) > page_size or len(rows) < 100 or last_scanned is None:
                    break
                conditions = [item for item in conditions if "COALESCE(observed_at, created_at), observation_id" not in item]
                if cursor:
                    arguments = arguments[:-2]
                conditions.append("(COALESCE(observed_at, created_at), observation_id) < (?, ?)")
                arguments.extend(last_scanned)
                cursor = "continued"
            has_more = len(items) > page_size
            items = items[:page_size]
            next_cursor = (
                f"{items[-1]['sort_at']}|{items[-1]['observation_id']}" if has_more and items else None
            )
            return {"events": items, "next_cursor": next_cursor}

    def get_encounter_read(self, observation_id: str) -> dict:
        with self._connect() as conn:
            conn.execute("BEGIN")
            row = _require_observation(conn, observation_id)
            if row["status"] != "FINALIZED":
                raise KeyError(f"Unknown finalized Event: {observation_id}")
            record = _encounter_read_record(conn, row)
            record["revision"] = _encounter_revision(conn, observation_id)
            record["event_details"] = _encounter_event_details(row)
            record["historical_people"] = [{"person_id": str(person[0]), "name": str(person[1]), "lifecycle_status": str(person[2])}
                for person in conn.execute("SELECT person_id, name, lifecycle_status FROM persons WHERE person_id IN ("
                    "SELECT person_id FROM observation_participants WHERE observation_id = ? UNION SELECT from_person_id FROM identity_corrections WHERE observation_id = ? "
                    "UNION SELECT to_person_id FROM identity_corrections WHERE observation_id = ?)", (observation_id, observation_id, observation_id))]
            for collection in (record["participants"], record["mentioned_people"]):
                for person in collection:
                    person["lifecycle_status"] = str(conn.execute("SELECT lifecycle_status FROM persons WHERE person_id = ?", (person["person_id"],)).fetchone()[0])
            record["relations"] = [{"first_person_id": pair[0], "second_person_id": pair[1],
                "disposition": relation["disposition"], "support": relation["support"]}
                for pair, relation in sorted(_effective_encounter_relations(conn, observation_id).items())]
            record["history"] = []
            operations = conn.execute(
                "SELECT j.operation_id FROM operation_journal j WHERE j.status = 'COMMITTED' AND "
                "(EXISTS(SELECT 1 FROM json_each(j.affected_entities) e WHERE json_extract(e.value, '$.entity_type') = 'observation' "
                "AND json_extract(e.value, '$.entity_id') = ?) OR EXISTS(SELECT 1 FROM operation_journal_status_history h "
                "WHERE h.operation_id = j.operation_id AND h.to_status = 'COMMITTED' AND json_extract(h.details, '$.observation_id') = ?)) "
                "ORDER BY j.created_at DESC, j.rowid DESC LIMIT 101", (observation_id, observation_id)).fetchall()
            record["history_has_more"] = len(operations) > 100
            for operation in operations[:100]:
                entry = _get_journal_operation(conn, str(operation[0]))
                record["history"].append({**{key: entry.get(key) for key in ("operation_id", "operation_type", "actor", "created_at", "details")},
                    "result": entry["status_history"][-1]["details"] if entry["status_history"] else {}})
            record["media"] = [
                {"media_id": item.media_id, "media_path": item.media_path}
                for item in _list_observation_media(conn, observation_id)
            ]
            record["sighting_notes"] = [
                {
                    "person_id": _encounter_detail_person(conn, observation_id, item),
                    "raw_person_id": str(item["person_id"]),
                    "content": str(item["content"]),
                }
                for item in conn.execute(
                    "SELECT d.person_id, d.embedding_id, n.content FROM recognition_details d "
                    "JOIN (SELECT notes.subject_id, revisions.content FROM notes "
                    "JOIN note_revisions revisions ON revisions.note_id = notes.note_id "
                    "WHERE notes.subject_type = 'RECOGNITION_DETAIL' AND notes.status = 'ACTIVE' "
                    "AND revisions.revision_number = (SELECT MAX(r2.revision_number) FROM note_revisions r2 WHERE r2.note_id = notes.note_id)) n "
                    "ON n.subject_id = d.detail_id WHERE d.observation_id = ? ORDER BY d.created_at, d.detail_id",
                    (observation_id,),
                )
            ]
            return record

    def _finalize_observation_without_graph_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> Observation:
        """Low-level P3 primitive reserved for fixtures and future atomic P6 work."""
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "observation.finalize",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = _require_observation(conn, observation_id)
                return _observation_from_row(row)
            _require_draft_observation(conn, observation_id)
            participant_count = int(conn.execute(
                "SELECT COUNT(*) FROM observation_participants WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()[0])
            if participant_count < 1:
                raise ValueError("A finalized observation requires at least one participant")
            _begin_journal_operation(
                conn,
                "observation.finalize",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "observation-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": observation_id},
                ],
                details={"participant_count": participant_count},
            )
            finalized_at = utc_now()
            conn.execute(
                """
                UPDATE observations
                SET status = 'FINALIZED', finalized_at = ?, updated_at = ?
                WHERE observation_id = ? AND status = 'DRAFT'
                """,
                (finalized_at, finalized_at, observation_id),
            )
            # A finalized event is World-visible even when it has one participant and
            # therefore creates no relationship evidence/projection replacement.
            _advance_graph_revision(conn)
            result = {
                "observation_id": observation_id,
                "status": "FINALIZED",
                "participant_count": participant_count,
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            row = conn.execute(
                "SELECT * FROM effective_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            return _observation_from_row(row)

    def list_observations_for_person(self, person_id: str) -> list[Observation]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = [
                row for row in conn.execute(
                    """
                    SELECT o.* FROM effective_observations o
                    ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                    """
                ).fetchall()
                if canonical_person_id
                in _effective_observation_person_ids(conn, str(row["observation_id"]))
            ]
        return [_observation_from_row(row) for row in rows]

    def list_raw_observations_for_person(self, person_id: str) -> list[Observation]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone() is None:
                raise KeyError(f"Unknown person: {person_id}")
            rows = conn.execute(
                """
                SELECT o.* FROM effective_observations o
                JOIN observation_participants p ON p.observation_id = o.observation_id
                WHERE p.person_id = ?
                ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                """,
                (person_id,),
            ).fetchall()
        return [_observation_from_row(row) for row in rows]

    def list_person_sightings(self, person_id: str) -> list[Sighting]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            return _list_person_sightings(conn, canonical_person_id)

    def get_person_intelligence(self, person_id: str) -> PersonIntelligence:
        with self._connect() as conn:
            requested = conn.execute(
                "SELECT * FROM persons WHERE person_id = ?", (person_id,),
            ).fetchone()
            if requested is None:
                raise KeyError(f"Unknown person: {person_id}")
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            canonical = conn.execute(
                "SELECT * FROM persons WHERE person_id = ?", (canonical_person_id,),
            ).fetchone()
            if canonical is None:
                raise RuntimeError("Canonical person record is unavailable")
            sightings = _list_person_sightings(conn, canonical_person_id)
            presence = _presence_analytics(sightings)
            relationships = _person_relationship_analytics(conn, canonical_person_id)
            embedding_count = sum(
                _effective_embedding_owner_person_id(conn, row) == canonical_person_id
                for row in conn.execute(
                    "SELECT embedding_id, person_id FROM embeddings WHERE deleted_at IS NULL"
                ).fetchall()
            )
            activity = tuple(self._list_person_operations(
                conn, canonical_person_id, canonical_person_id=canonical_person_id,
            ))
            return PersonIntelligence(
                requested_person_id=person_id,
                canonical_person_id=canonical_person_id,
                lifecycle_status=str(requested["lifecycle_status"]),
                canonical_lifecycle_status=str(canonical["lifecycle_status"]),
                biometric_status=str(canonical["biometric_status"]),
                embedding_count=embedding_count,
                confidence_summary={
                    "score": None,
                    "basis": "operator-finalized observations and current biometric enrollment",
                    "accepted_observation_count": presence.observation_count,
                    "active_embedding_count": embedding_count,
                    "probabilistic_confidence_available": False,
                },
                presence=presence,
                relationships=relationships,
                activity=activity,
                provenance=(
                    "persons.lifecycle_status",
                    "persons.canonical_person_id",
                    "finalized observations and effective participants",
                    "active relationship_evidence",
                    "operation_journal",
                ),
            )

    def list_observations_for_media(self, media_id: str) -> list[Observation]:
        normalized_media_id = str(media_id).strip()
        if not normalized_media_id:
            raise ValueError("Media ID is required")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT o.*
                FROM effective_observations o
                JOIN observation_media m ON m.observation_id = o.observation_id
                WHERE m.media_id = ?
                ORDER BY COALESCE(o.observed_at, o.created_at) DESC, o.observation_id
                """,
                (normalized_media_id,),
            ).fetchall()
        return [_observation_from_row(row) for row in rows]

    def record_observation_evidence(
        self,
        observation_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        normalized_observation_id = str(observation_id).strip()
        if not normalized_observation_id:
            raise ValueError("Observation ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.observation-evidence.record",
            )
            if existing_result is not None:
                if existing_result.get("observation_id") != normalized_observation_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return _list_relationship_evidence_for_source(
                    conn, "CO_OBSERVED", normalized_observation_id,
                )
            observation = _require_observation(conn, normalized_observation_id)
            if observation["status"] != "FINALIZED":
                raise ValueError("Co-observation evidence requires a finalized observation")
            participants = conn.execute(
                """
                SELECT person_id
                FROM observation_participants
                WHERE observation_id = ?
                ORDER BY person_id
                """,
                (normalized_observation_id,),
            ).fetchall()
            raw_person_ids = [str(participant["person_id"]) for participant in participants]
            _begin_journal_operation(
                conn,
                "graph.observation-evidence.record",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {"entity_type": "observation", "entity_id": normalized_observation_id},
                    *[
                        {"entity_type": "person", "entity_id": person_id}
                        for person_id in raw_person_ids
                    ],
                ],
                details={"evidence_type": "CO_OBSERVED"},
            )
            created_at = utc_now()
            for index, first_person_id in enumerate(raw_person_ids):
                for second_person_id in raw_person_ids[index + 1:]:
                    _insert_relationship_evidence(
                        conn,
                        evidence_type="CO_OBSERVED",
                        source_entity_type="OBSERVATION",
                        source_entity_id=normalized_observation_id,
                        source_person_id=first_person_id,
                        target_person_id=second_person_id,
                        relationship_type="ASSOCIATED_WITH",
                        directionality="UNDIRECTED",
                        source=_optional_text(source),
                        created_operation_id=operation_id,
                        created_at=created_at,
                    )
            evidence = _list_relationship_evidence_for_source(
                conn, "CO_OBSERVED", normalized_observation_id,
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "observation_id": normalized_observation_id,
                "evidence_ids": [item.evidence_id for item in evidence],
                "evidence_count": len(evidence),
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return evidence

    def deactivate_relationship_evidence(
        self,
        evidence_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> RelationshipEvidence:
        normalized_evidence_id = str(evidence_id).strip()
        if not normalized_evidence_id:
            raise ValueError("Evidence ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.evidence.deactivate",
            )
            if existing_result is not None:
                if existing_result.get("evidence_id") != normalized_evidence_id:
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                row = conn.execute(
                    "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                    (normalized_evidence_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Committed evidence deactivation is missing its evidence")
                return _relationship_evidence_from_row(row)
            row = conn.execute(
                "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                (normalized_evidence_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown relationship evidence: {normalized_evidence_id}")
            _begin_journal_operation(
                conn,
                "graph.evidence.deactivate",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {"entity_type": "relationship_evidence", "entity_id": normalized_evidence_id},
                    {"entity_type": "person", "entity_id": row["source_person_id"]},
                    {"entity_type": "person", "entity_id": row["target_person_id"]},
                ],
            )
            changed = False
            if bool(row["active"]):
                deactivated_at = utc_now()
                conn.execute(
                    """
                    UPDATE relationship_evidence
                    SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                    WHERE evidence_id = ? AND active = 1
                    """,
                    (operation_id, deactivated_at, normalized_evidence_id),
                )
                changed = True
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "evidence_id": normalized_evidence_id,
                "deactivated": True,
                "changed": changed,
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            updated = conn.execute(
                "SELECT * FROM relationship_evidence WHERE evidence_id = ?",
                (normalized_evidence_id,),
            ).fetchone()
            return _relationship_evidence_from_row(updated)

    def deactivate_relationship_evidence_for_source(
        self,
        evidence_type: str,
        source_entity_id: str,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
    ) -> list[RelationshipEvidence]:
        normalized_type = str(evidence_type).strip().upper()
        if normalized_type not in RELATIONSHIP_EVIDENCE_TYPES:
            raise ValueError(f"Unsupported relationship evidence type: {evidence_type}")
        normalized_source_entity_id = str(source_entity_id).strip()
        if not normalized_source_entity_id:
            raise ValueError("Evidence source entity ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, operation_id, "graph.source-evidence.deactivate",
            )
            if existing_result is not None:
                if (
                    existing_result.get("evidence_type") != normalized_type
                    or existing_result.get("source_entity_id") != normalized_source_entity_id
                ):
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                return _list_relationship_evidence_for_source(
                    conn, normalized_type, normalized_source_entity_id,
                )
            rows = conn.execute(
                """
                SELECT * FROM relationship_evidence
                WHERE evidence_type = ? AND source_entity_id = ?
                ORDER BY evidence_id
                """,
                (normalized_type, normalized_source_entity_id),
            ).fetchall()
            if not rows:
                raise KeyError(
                    f"No {normalized_type} evidence exists for source {normalized_source_entity_id}"
                )
            _begin_journal_operation(
                conn,
                "graph.source-evidence.deactivate",
                operation_id=operation_id,
                actor=actor,
                source=_optional_text(source) or "global-graph-service",
                affected_entities=[
                    {
                        "entity_type": "relationship_evidence",
                        "entity_id": row["evidence_id"],
                    }
                    for row in rows
                ],
                details={
                    "evidence_type": normalized_type,
                    "source_entity_id": normalized_source_entity_id,
                },
            )
            deactivated_at = utc_now()
            cursor = conn.execute(
                """
                UPDATE relationship_evidence
                SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
                WHERE evidence_type = ? AND source_entity_id = ? AND active = 1
                """,
                (
                    operation_id,
                    deactivated_at,
                    normalized_type,
                    normalized_source_entity_id,
                ),
            )
            _replace_graph_projection(conn)
            validation = _validate_graph_projection(conn)
            if not validation["valid"]:
                raise RuntimeError(
                    "Graph projection validation failed: " + "; ".join(validation["errors"])
                )
            result = {
                "evidence_type": normalized_type,
                "source_entity_id": normalized_source_entity_id,
                "deactivated_count": int(cursor.rowcount),
                "connection_count": validation["actual_connection_count"],
            }
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return _list_relationship_evidence_for_source(
                conn, normalized_type, normalized_source_entity_id,
            )

    def get_person_neighbors(self, person_id: str) -> list[GraphConnection]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT * FROM graph_connections
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY last_evidence_at DESC, source_person_id, target_person_id,
                         relationship_type, directionality
                """,
                (canonical_person_id, canonical_person_id),
            ).fetchall()
        return [_graph_connection_from_row(row) for row in rows]

    def get_connection_evidence(
        self,
        source_person_id: str,
        target_person_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[RelationshipEvidence]:
        with self._connect() as conn:
            canonical_source = _resolve_canonical_person_id(conn, source_person_id)
            canonical_target = _resolve_canonical_person_id(conn, target_person_id)
            if canonical_source == canonical_target:
                return []
            rows = conn.execute(
                f"SELECT * FROM relationship_evidence "
                f"{' ' if include_inactive else 'WHERE active = 1 '}"
                "ORDER BY created_at, evidence_id"
            ).fetchall()
            evidence: list[RelationshipEvidence] = []
            for row in rows:
                resolved_source = _resolve_canonical_person_id(
                    conn, row["source_person_id"],
                )
                resolved_target = _resolve_canonical_person_id(
                    conn, row["target_person_id"],
                )
                if row["directionality"] == "UNDIRECTED":
                    matches = tuple(sorted((resolved_source, resolved_target))) == tuple(
                        sorted((canonical_source, canonical_target))
                    )
                else:
                    matches = (
                        resolved_source == canonical_source
                        and resolved_target == canonical_target
                    )
                if matches:
                    evidence.append(_relationship_evidence_from_row(row))
            return evidence

    def get_global_graph_projection(self) -> GlobalGraphProjection:
        with self._connect() as conn:
            person_rows = conn.execute(
                "SELECT person_id, name, lifecycle_status FROM persons ORDER BY person_id"
            ).fetchall()
            nodes = tuple(
                GraphNode(
                    person_id=row["person_id"],
                    canonical_person_id=_resolve_canonical_person_id(conn, row["person_id"]),
                    name=row["name"],
                    lifecycle_status=row["lifecycle_status"],
                )
                for row in person_rows
            )
            connection_rows = conn.execute(
                """
                SELECT * FROM graph_connections
                ORDER BY source_person_id, target_person_id, relationship_type, directionality
                """
            ).fetchall()
            connections = tuple(_graph_connection_from_row(row) for row in connection_rows)
            return GlobalGraphProjection(nodes=nodes, connections=connections)

    def get_graph_revision(self) -> str:
        with self._connect() as conn:
            return _graph_revision_token(conn)

    def get_person_graph_read(
        self, person_id: str, filters: GraphReadFilter | None = None,
    ) -> PersonGraphReadModel:
        normalized_person_id = str(person_id).strip()
        if not normalized_person_id:
            raise ValueError("Person ID is required")
        normalized_filters = _normalize_graph_filters(filters)
        with self._connect() as conn:
            requested = conn.execute(
                "SELECT lifecycle_status FROM persons WHERE person_id = ?",
                (normalized_person_id,),
            ).fetchone()
            if requested is None:
                raise KeyError(f"Unknown person: {normalized_person_id}")
            root_person_id = _resolve_canonical_person_id(conn, normalized_person_id)
            nodes_by_id, edges = _graph_read_components(
                conn, normalized_filters, always_include_person_id=root_person_id,
            )
            root = nodes_by_id.get(root_person_id)
            if root is None:
                root = _graph_read_node(conn, root_person_id)
            person_edges = tuple(
                GraphReadEdge(
                    **{
                        **item.__dict__,
                        "connected_person_id": (
                            item.target_person_id
                            if item.source_person_id == root_person_id
                            else item.source_person_id
                        ),
                    }
                )
                for item in edges
                if root_person_id in {item.source_person_id, item.target_person_id}
            )
            included_ids = {root_person_id}
            included_ids.update(
                item.connected_person_id for item in person_edges if item.connected_person_id
            )
            nodes = tuple(
                root if item_id == root_person_id else nodes_by_id[item_id]
                for item_id in sorted(included_ids, key=lambda value: (
                    value != root_person_id,
                    (root if value == root_person_id else nodes_by_id[value]).display_name.casefold(),
                    value,
                ))
            )
            return PersonGraphReadModel(
                graph_revision=_graph_revision_token(conn),
                generated_at=utc_now(),
                requested_person_id=normalized_person_id,
                root_person_id=root_person_id,
                root_requested_state=str(requested["lifecycle_status"]),
                filters=normalized_filters,
                nodes=nodes,
                edges=person_edges,
            )

    def get_world_graph_read(
        self, filters: GraphReadFilter | None = None,
    ) -> WorldGraphReadModel:
        normalized_filters = _normalize_graph_filters(filters)
        with self._connect() as conn:
            nodes_by_id, edges = _graph_read_components(conn, normalized_filters)
            return WorldGraphReadModel(
                graph_revision=_graph_revision_token(conn),
                generated_at=utc_now(),
                filters=normalized_filters,
                nodes=tuple(sorted(
                    nodes_by_id.values(),
                    key=lambda item: (item.display_name.casefold(), item.person_id),
                )),
                edges=edges,
            )

    def get_world_graph_v2_read(
        self, request: WorldGraphRequest | None = None,
    ) -> WorldGraphV2ReadModel:
        with self._connect() as conn:
            return _world_graph_v2_read(conn, request or WorldGraphRequest())

    def rebuild_graph_projection(
        self,
        operation_id: str,
        *,
        source: str | None = None,
        actor: dict | None = None,
        reason: str | None = None,
        context: dict | None = None,
    ) -> dict:
        """Explicit P11-B recovery command for the derived graph projection only."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        with self._connect() as conn:
            existing_result = _existing_committed_operation_result(
                conn, normalized_operation_id, "graph.projection.rebuild",
            )
            if existing_result is not None:
                return existing_result

        # Import locally to keep the read-only P11-A module independent from store startup.
        from sentriface.integrity import ReadOnlyIntegrityChecker

        preflight = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        projection_findings = tuple(
            item for item in preflight.findings
            if item.invariant_id == "P11-GRAPH-001"
        )
        blocking_findings = tuple(
            item for item in preflight.findings
            if item.invariant_id != "P11-GRAPH-001"
            and item.severity.value in {"CRITICAL", "ERROR"}
        )
        preflight_status = (
            "BLOCKED"
            if blocking_findings or preflight.findings_truncated
            else "PROJECTION_DRIFT"
            if projection_findings
            else "PASS"
        )
        preflight_summary = {
            "status": preflight_status,
            "finding_count": len(preflight.findings),
            "projection_finding_count": len(projection_findings),
            "blocking_finding_count": len(blocking_findings),
            "blocking_invariant_ids": sorted({
                item.invariant_id for item in blocking_findings
            }),
            "findings_truncated": preflight.findings_truncated,
        }
        if preflight_status == "BLOCKED":
            self._record_graph_rebuild_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                context=context,
                details={
                    "reason": _optional_text(reason),
                    "preflight": preflight_summary,
                    "refused": True,
                    "transaction_rolled_back": True,
                },
            )
            raise GraphProjectionRebuildRefused(
                normalized_operation_id,
                preflight,
                "Graph projection rebuild refused because authoritative integrity "
                "findings prevent deterministic interpretation",
            )

        failure_details: dict = {
            "reason": _optional_text(reason),
            "preflight": preflight_summary,
            "transaction_rolled_back": True,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing_result = _existing_committed_operation_result(
                    conn, normalized_operation_id, "graph.projection.rebuild",
                )
                if existing_result is not None:
                    return existing_result
                revision_before = _graph_revision_token(conn)
                failure_details["revision_before"] = revision_before
                expected, authority_errors, active_evidence_count = (
                    _expected_graph_connections(conn)
                )
                if authority_errors:
                    failure_details.update({
                        "revision_before": revision_before,
                        "authority_error_count": len(authority_errors),
                        "authority_errors": authority_errors[:20],
                    })
                    raise RuntimeError(
                        "Authoritative relationship evidence became invalid after "
                        "preflight: " + "; ".join(authority_errors[:20])
                    )
                actual_rows = conn.execute(
                    """
                    SELECT * FROM graph_connections
                    ORDER BY source_person_id, target_person_id,
                             relationship_type, directionality
                    """
                ).fetchall()
                expected_signatures = {
                    _graph_connection_signature(item) for item in expected
                }
                actual_signatures = {
                    _graph_connection_row_signature(item) for item in actual_rows
                }
                changed = expected_signatures != actual_signatures
                added_count = len(expected_signatures - actual_signatures)
                removed_count = len(actual_signatures - expected_signatures)
                failure_details.update({
                    "active_evidence_count": active_evidence_count,
                    "expected_edge_count": len(expected),
                    "stored_edge_count_before": len(actual_rows),
                    "added_count": added_count,
                    "removed_count": removed_count,
                })
                operation = _begin_journal_operation(
                    conn,
                    "graph.projection.rebuild",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "global-graph-service",
                    context=context,
                    affected_entities=[{
                        "entity_type": "graph_projection",
                        "entity_id": "graph_connections",
                    }],
                    details={
                        "reason": _optional_text(reason),
                        "preflight": preflight_summary,
                        "revision_before": revision_before,
                    },
                )
                if changed:
                    _write_graph_projection(conn, expected)
                validation = _validate_graph_projection(conn)
                if not validation["valid"]:
                    raise RuntimeError(
                        "Graph projection validation failed: "
                        + "; ".join(validation["errors"][:20])
                    )
                if changed:
                    _advance_graph_revision(conn)
                revision_after = _graph_revision_token(conn)
                result = {
                    "operation_id": normalized_operation_id,
                    "started_at": operation["created_at"],
                    "changed": changed,
                    "revision_before": revision_before,
                    "revision_after": revision_after,
                    "active_evidence_count": active_evidence_count,
                    "expected_edge_count": len(expected),
                    "stored_edge_count_before": len(actual_rows),
                    "stored_edge_count_after": validation["actual_connection_count"],
                    "added_count": added_count,
                    "removed_count": removed_count,
                    "preflight_status": preflight_status,
                    "postcheck_status": "PASS",
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
        except Exception as exc:
            failure_details.update({
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            self._record_graph_rebuild_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                context=context,
                details=failure_details,
            )
            raise

        postcheck = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        if postcheck.status != "PASS":
            failed_result = {**result, "postcheck_status": postcheck.status}
            raise GraphProjectionPostcheckError(failed_result, postcheck)
        return result

    def _record_graph_rebuild_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict | None,
        source: str | None,
        context: dict | None,
        details: dict,
    ) -> dict:
        """Record failure only after a rebuild transaction has rolled back."""
        with self._connect() as conn:
            existing = _get_journal_operation(conn, operation_id)
            if existing is not None:
                if existing["operation_type"] != "graph.projection.rebuild":
                    raise KeyError(f"Operation ID already exists: {operation_id}")
                if existing["status"] == "FAILED":
                    return existing
                if existing["status"] != "STARTED":
                    raise ValueError("Only a started graph rebuild can fail")
            else:
                _begin_journal_operation(
                    conn,
                    "graph.projection.rebuild",
                    operation_id=operation_id,
                    actor=actor,
                    source=_optional_text(source) or "global-graph-service",
                    context=context,
                    affected_entities=[{
                        "entity_type": "graph_projection",
                        "entity_id": "graph_connections",
                    }],
                    details={"transaction_rolled_back": True},
                )
            return _transition_journal_operation(
                conn, operation_id, "FAILED", details,
            )

    def validate_graph_projection(self) -> dict:
        with self._connect() as conn:
            return _validate_graph_projection(conn)

    def get_embedding_lifecycle(self, embedding_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at, e.purge_after, e.erased_at,
                       e.source_image, e.crop_path,
                       p.name AS person_name, p.deleted_at AS person_deleted_at
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["raw_person_id"] = _raw_embedding_owner_person_id(conn, row)
            result["canonical_person_id"] = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT name, deleted_at FROM persons WHERE person_id = ?",
                (result["canonical_person_id"],),
            ).fetchone()
            if effective_person is not None:
                result["person_name"] = effective_person["name"]
                result["person_deleted_at"] = effective_person["deleted_at"]
            return result

    def get_person_lifecycle(self, person_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT person_id, lifecycle_status, canonical_person_id,
                       identity_status, biometric_status, deleted_at, lifecycle_changed_at
                FROM persons WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["resolved_canonical_person_id"] = _resolve_canonical_person_id(conn, person_id)
            return result

    def resolve_canonical_person_id(self, person_id: str) -> str:
        with self._connect() as conn:
            return _resolve_canonical_person_id(conn, person_id)

    def get_merge_operation(self, merge_operation_id: str) -> MergeOperation | None:
        with self._connect() as conn:
            return _get_merge_operation(conn, merge_operation_id)

    def preview_identity_merge(
        self, source_person_id: str, target_person_id: str,
    ) -> dict:
        with self._connect() as conn:
            return _preview_identity_merge(conn, source_person_id, target_person_id)

    def execute_identity_merge(
        self,
        source_person_id: str,
        target_person_id: str,
        operation_id: str,
        *,
        conflict_resolutions: list[dict] | dict[str, dict | str] | None = None,
        actor: dict | None = None,
        source: str | None = None,
        reason: str | None = None,
        context: dict | None = None,
        publish_index: Callable[[list[EmbeddingRecord]], None] | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Merge operation ID is required")
        normalized_source_id = str(source_person_id).strip()
        normalized_requested_target_id = str(target_person_id).strip()
        with self._connect() as conn:
            existing = _get_journal_operation(conn, normalized_operation_id)
            if existing is not None:
                if existing["operation_type"] != "identity.merge":
                    raise KeyError(f"Operation ID already exists: {normalized_operation_id}")
                prior = existing.get("details", {})
                if (
                    prior.get("source_person_id") != normalized_source_id
                    or prior.get("requested_target_person_id") != normalized_requested_target_id
                ):
                    raise ValueError("Merge operation ID belongs to a different request")
                if existing["status"] == "COMMITTED":
                    history = existing.get("status_history") or []
                    return dict(history[-1]["details"]) if history else {}
                if existing["status"] in {"FAILED", "ROLLED_BACK"}:
                    raise ValueError(
                        "A failed merge operation ID cannot be reused; retry with a new operation ID"
                    )
        preview = self.preview_identity_merge(source_person_id, target_person_id)
        requested = {
            "source_person_id": preview["source_person_id"],
            "requested_target_person_id": preview["requested_target_person_id"],
            "target_person_id": preview["target_person_id"],
        }
        with self._connect() as conn:
            existing = _get_journal_operation(conn, normalized_operation_id)
            if existing is not None:
                prior = existing.get("details", {})
                for key, value in requested.items():
                    if prior.get(key) != value:
                        raise ValueError("Merge operation ID belongs to a different request")
            else:
                _begin_journal_operation(
                    conn,
                    "identity.merge",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge-service",
                    context=context,
                    affected_entities=[
                        {"entity_type": "person", "entity_id": preview["source_person_id"]},
                        {"entity_type": "person", "entity_id": preview["target_person_id"]},
                    ],
                    details=requested,
                )
        try:
            with self._connect() as conn:
                current = _get_journal_operation(conn, normalized_operation_id)
                if current is None or current["status"] != "STARTED":
                    raise RuntimeError("Merge journal is not in STARTED state")
                combined = {r["media_id"] or r["reference_id"] for r in _reference_records(conn)
                            if r["active"] and r["canonical_person_id"] in {
                                _resolve_canonical_person_id(conn, source_person_id),
                                _resolve_canonical_person_id(conn, target_person_id)}}
                if len(combined) > 4:
                    raise ValueError("This merge would produce more than four active Recognition References; reduce the combined sources to four or fewer and retry")
                preview = _preview_identity_merge(
                    conn, source_person_id, target_person_id,
                    exclude_operation_id=normalized_operation_id,
                )
                conflicts = _resolve_merge_conflicts(
                    preview["conflicts"], conflict_resolutions,
                )
                affected_items = _merge_inventory_with_profile_changes(
                    preview["affected_items"], conflicts,
                    preview["source_person_id"], preview["target_person_id"],
                )
                _insert_merge_manifest_in_transaction(
                    conn,
                    merge_operation_id=normalized_operation_id,
                    source_person_id=preview["source_person_id"],
                    target_person_id=preview["target_person_id"],
                    operation_journal_id=normalized_operation_id,
                    actor=actor,
                    reason=reason,
                    context={
                        **(context or {}),
                        "requested_target_person_id": preview["requested_target_person_id"],
                        "source_component_person_ids": preview["source_component_person_ids"],
                    },
                    affected_items=affected_items,
                    conflicts=conflicts,
                )
                _apply_merge_profile_resolutions(
                    conn,
                    preview["source_person_id"],
                    preview["target_person_id"],
                    conflicts,
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=_optional_text(source) or "identity-merge-service",
                )
                _set_canonical_person_id_in_transaction(
                    conn, preview["source_person_id"], preview["target_person_id"],
                )
                if failure_injector is not None:
                    failure_injector("after_canonical_update")
                _synchronize_survivor_biometric_state(conn, preview["target_person_id"])
                _retire_canonical_manual_collisions(conn, normalized_operation_id, preview["target_person_id"])
                for encounter in conn.execute("SELECT DISTINCT observation_id FROM encounter_relation_decisions WHERE active = 1 AND observation_id IS NOT NULL").fetchall():
                    oid = str(encounter[0])
                    rows = conn.execute("SELECT first_person_id, second_person_id FROM encounter_relation_decisions WHERE observation_id = ? AND active = 1", (oid,)).fetchall()
                    canonical_pairs = [tuple(sorted(_resolve_canonical_person_id(conn, str(member)) for member in pair)) for pair in rows]
                    if len(set(canonical_pairs)) < len(rows) or any(pair[0] == pair[1] for pair in canonical_pairs):
                        desired = _effective_encounter_relations(conn, oid)
                        _write_encounter_relation_revisions(conn, oid, desired, normalized_operation_id)
                        _recalculate_observation_evidence(conn, oid, normalized_operation_id, source or "identity-merge-service")
                _replace_graph_projection(conn)
                if failure_injector is not None:
                    failure_injector("after_graph_rebuild")
                validation = _validate_merge_state(
                    conn, preview["source_person_id"], preview["target_person_id"],
                )
                if not validation["valid"]:
                    raise RuntimeError(
                        "Merge validation failed: " + "; ".join(validation["errors"])
                    )
                _refresh_source_biometric_status(conn)
                embeddings = _list_embeddings_in_transaction(conn)
                if publish_index is not None:
                    publish_index(embeddings)
                if failure_injector is not None:
                    failure_injector("after_index_publication")
                result = {
                    "merge_operation_id": normalized_operation_id,
                    "source_person_id": preview["source_person_id"],
                    "requested_target_person_id": preview["requested_target_person_id"],
                    "target_person_id": preview["target_person_id"],
                    "canonical_person_id": preview["target_person_id"],
                    "merged": True,
                    "affected_item_count": len(affected_items),
                    "conflict_count": len(conflicts),
                    "graph_validation": validation["graph"],
                    "undo_supported": False,
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except Exception as exc:
            self.record_merge_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=_optional_text(source) or "identity-merge-service",
                context=context,
                affected_entities=[
                    {"entity_type": "person", "entity_id": preview["source_person_id"]},
                    {"entity_type": "person", "entity_id": preview["target_person_id"]},
                ],
                details={
                    **requested,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

    def list_historical_persons(self) -> list[PersonSummary]:
        return self.list_persons(archived=True)

    def validate_person_lifecycle_operation(self, person_id: str, operation_id: str, operation_type: str) -> None:
        """Read-only early admission; mutations revalidate under their transaction."""
        with self._connect() as conn:
            if _existing_person_operation(conn, operation_id, operation_type) is not None:
                return
            _require_person_lifecycle_preconditions(conn, person_id, operation_type)

    def archive_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "archive-person")
            if existing:
                return existing
            row = _require_person_lifecycle_preconditions(conn, person_id, "archive-person")
            _begin_journal_operation(
                conn,
                "identity.archive",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": row["lifecycle_status"]},
            )
            archived_at = row["deleted_at"] or utc_now()
            cursor = conn.execute(
                """
                UPDATE persons
                SET lifecycle_status = 'ARCHIVED', deleted_at = ?, lifecycle_changed_at = ?
                WHERE person_id = ? AND lifecycle_status = 'ACTIVE'
                """,
                (archived_at, archived_at, person_id),
            )
            result = {
                "person_id": person_id,
                "archived": True,
                "archived_at": archived_at,
                "lifecycle_status": "ARCHIVED",
                "changed": bool(cursor.rowcount),
            }
            _record_person_operation(conn, operation_id, "archive-person", result)
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def restore_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-person")
            if existing and existing["person_id"] != person_id:
                raise ValueError("Restore operation ID belongs to a different person")
            row = conn.execute(
                "SELECT lifecycle_status, restore_until FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown person: {person_id}")
            previous_status = row["lifecycle_status"]
            if previous_status == "DELETED" and person_recovery_status(row["restore_until"], utc_now()) == "EXPIRED":
                raise InputValidationError(
                    "Non-recoverable — this profile cannot be restored.", reason="person_recovery_expired",
                )
            if existing:
                if previous_status != "ACTIVE":
                    raise InputValidationError(
                        "This profile changed since the original Restore. Refresh and try again.",
                        reason="person_restore_stale",
                    )
                return existing
            if previous_status not in RESTORABLE_PERSON_LIFECYCLE_STATUSES:
                raise KeyError(f"Only archived or deleted people can be restored: {person_id}")
            _begin_journal_operation(
                conn,
                "identity.restore",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": previous_status},
            )
            cursor = _restore_archived_person_in_transaction(
                conn, person_id, RESTORABLE_PERSON_LIFECYCLE_STATUSES,
            )
            result = {
                "person_id": person_id,
                "restored": True,
                "previous_lifecycle_status": previous_status,
                "lifecycle_status": "ACTIVE",
                "changed": bool(cursor.rowcount),
            }
            _record_person_operation(conn, operation_id, "restore-person", result)
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def prepare_restore_archived_canonical_survivor(
        self, survivor_person_id: str,
    ) -> ArchivedCanonicalSurvivorRepairPrecondition:
        """Diagnose and bind the one authorized P11-C R01 mutation."""
        normalized_id = str(survivor_person_id).strip()
        if not normalized_id:
            raise ValueError("Survivor person ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _r01_precondition_from_report(conn, report, normalized_id)

    def execute_restore_archived_canonical_survivor(
        self,
        precondition: ArchivedCanonicalSurvivorRepairPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        """Execute P11C-R01 only; the caller performs the full P11-A post-check."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Repair reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Repair reason must not exceed 500 characters")
        _validate_r01_request_shape(precondition)

        with self._connect() as conn:
            existing = _r01_existing_result(
                conn, normalized_operation_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "repair_id": precondition.repair_id,
            "repair_spec_version": precondition.repair_spec_version,
            "invariant_ids": list(precondition.invariant_ids),
            "finding_fingerprint_version": precondition.finding_fingerprint_version,
            "finding_fingerprint": precondition.finding_fingerprint,
            "survivor_person_id": precondition.survivor_person_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _r01_existing_result(
                    conn, normalized_operation_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _r01_precondition_from_report(
                    conn, report, precondition.survivor_person_id,
                )
                if current != precondition:
                    raise StructuredRepairRefused(
                        "R01 refused because the diagnosed authoritative state is stale",
                        report=report,
                    )
                connections_before = _r01_table_fingerprint(conn, "graph_connections")
                canonical_before = _r01_canonical_fingerprint(conn)
                merge_before = precondition.merge_state_fingerprint
                revision_before = _graph_revision_token(conn)
                _begin_journal_operation(
                    conn,
                    "integrity.repair.canonical-survivor.restore",
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=source or "structured-repair-service",
                    affected_entities=[
                        {"entity_type": "person", "entity_id": item}
                        for item in precondition.affected_entity_ids[:50]
                    ],
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entity_ids),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entity_ids
                        ),
                        "before_state_fingerprint": _r01_hash({
                            "lifecycle": precondition.expected_lifecycle_status,
                            "deleted_at": precondition.expected_deleted_at,
                            "lifecycle_changed_at": precondition.expected_lifecycle_changed_at,
                            "canonical_person_id": precondition.expected_canonical_person_id,
                            "merge_state_fingerprint": merge_before,
                        }),
                    },
                )
                _restore_archived_person_in_transaction(
                    conn, precondition.survivor_person_id,
                )
                post = _validate_r01_postconditions(
                    conn,
                    precondition,
                    canonical_before=canonical_before,
                    connections_before=connections_before,
                    merge_before=merge_before,
                    revision_before=revision_before,
                )
                result = {
                    "repair_id": precondition.repair_id,
                    "repair_spec_version": precondition.repair_spec_version,
                    "invariant_ids": list(precondition.invariant_ids),
                    "finding_fingerprint_version": precondition.finding_fingerprint_version,
                    "finding_fingerprint": precondition.finding_fingerprint,
                    "survivor_person_id": precondition.survivor_person_id,
                    "merge_path_count": len(precondition.merge_paths),
                    "merge_path_fingerprint": _r01_hash(precondition.merge_paths),
                    "lifecycle_before": "ARCHIVED",
                    "lifecycle_after": "ACTIVE",
                    "graph_revision_before": revision_before,
                    "graph_revision_after": post["graph_revision_after"],
                    "changed": True,
                    "immediate_postcondition_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except StructuredRepairRefused:
            raise
        except Exception as exc:
            self._record_r01_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_r01_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                "integrity.repair.canonical-survivor.restore",
                operation_id=operation_id,
                actor=actor,
                source=source or "structured-repair-service",
                affected_entities=[{
                    "entity_type": "person",
                    "entity_id": details["survivor_person_id"],
                }],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def prepare_note_reference_reconciliation(
        self, note_id: str, referenced_person_id: str,
    ) -> NoteReferenceReconciliationPrecondition:
        """Diagnose and bind one authorized P11-C R02 note/person scope."""
        normalized_note_id = str(note_id).strip()
        normalized_person_id = str(referenced_person_id).strip()
        if not normalized_note_id:
            raise ValueError("Note ID is required")
        if not normalized_person_id:
            raise ValueError("Referenced person ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _r02_precondition_from_report(
                conn, report, normalized_note_id, normalized_person_id,
            )

    def execute_note_reference_reconciliation(
        self,
        precondition: NoteReferenceReconciliationPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
    ) -> dict:
        """Execute only P11C-R02; the caller performs the full P11-A post-check."""
        normalized_operation_id = str(operation_id).strip()
        if not normalized_operation_id:
            raise ValueError("Operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Repair reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Repair reason must not exceed 500 characters")
        _validate_r02_request_shape(precondition)

        with self._connect() as conn:
            existing = _r02_existing_result(
                conn, normalized_operation_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "repair_id": precondition.repair_id,
            "repair_spec_version": precondition.repair_spec_version,
            "invariant_ids": list(precondition.invariant_ids),
            "finding_fingerprint_version": precondition.finding_fingerprint_version,
            "finding_fingerprint": precondition.finding_fingerprint,
            "plan_type": precondition.plan.value,
            "note_id": precondition.note_id,
            "referenced_person_id": precondition.referenced_person_id,
            "authoritative_revision_id": precondition.latest_revision_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _r02_existing_result(
                    conn, normalized_operation_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _r02_precondition_from_report(
                    conn,
                    report,
                    precondition.note_id,
                    precondition.referenced_person_id,
                )
                if current != precondition:
                    raise StructuredRepairRefused(
                        "R02 refused because the diagnosed authoritative state is stale",
                        report=report,
                    )

                immutable_before = _r02_immutable_fingerprint(conn)
                unrelated_before = _r02_unrelated_fingerprint(
                    conn, precondition, normalized_operation_id,
                )
                historical_before = _r02_retired_history_fingerprint(conn, precondition)
                revision_before = _graph_revision_token(conn)
                connection_count_before = int(conn.execute(
                    "SELECT COUNT(*) FROM graph_connections"
                ).fetchone()[0])
                planned_occurrence_id, planned_evidence_id = _r02_planned_append_ids(
                    precondition, normalized_operation_id,
                )
                _begin_journal_operation(
                    conn,
                    _R02_OPERATION_TYPE,
                    operation_id=normalized_operation_id,
                    actor=actor,
                    source=source or "structured-repair-service",
                    affected_entities=_r02_affected_entities(
                        precondition,
                        planned_occurrence_id=planned_occurrence_id,
                        planned_evidence_id=planned_evidence_id,
                    ),
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entity_ids),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entity_ids
                        ),
                        "before_state_fingerprint": _r01_hash({
                            "revision_history": precondition.revision_history_fingerprint,
                            "occurrence_group": precondition.occurrence_group_fingerprint,
                            "evidence_history": precondition.evidence_history_fingerprint,
                            "canonical_state": precondition.canonical_state_fingerprint,
                            "graph_projection": precondition.graph_projection_fingerprint,
                            "relevant_operations": precondition.relevant_operation_fingerprint,
                        }),
                    },
                )
                _r02_failure_checkpoint("after_journal_started")
                mutation = _apply_r02_plan(
                    conn,
                    precondition,
                    normalized_operation_id,
                    source=_optional_text(source),
                    planned_occurrence_id=planned_occurrence_id,
                )
                if mutation["active_evidence_changed"]:
                    _r02_maintain_affected_projection(conn, precondition)
                    _r02_failure_checkpoint("after_graph_projection")
                    _advance_graph_revision(conn)
                    _r02_failure_checkpoint("after_graph_revision_advance")
                post = _validate_r02_postconditions(
                    conn,
                    precondition,
                    operation_id=normalized_operation_id,
                    mutation=mutation,
                    immutable_before=immutable_before,
                    unrelated_before=unrelated_before,
                    historical_before=historical_before,
                    revision_before=revision_before,
                )
                _r02_failure_checkpoint("after_immediate_validation")
                result = {
                    **failure_details,
                    "occurrences_appended": mutation["occurrences_appended"],
                    "occurrences_retired": mutation["occurrences_retired"],
                    "evidence_appended": mutation["evidence_appended"],
                    "evidence_retired": mutation["evidence_retired"],
                    "graph_revision_before": revision_before,
                    "graph_revision_after": post["graph_revision_after"],
                    "connection_count_before": connection_count_before,
                    "connection_count_after": post["connection_count_after"],
                    "changed": True,
                    "immediate_validation_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _r02_failure_checkpoint("before_commit")
                _transition_journal_operation(
                    conn, normalized_operation_id, "COMMITTED", result,
                )
                return result
        except StructuredRepairRefused:
            raise
        except Exception as exc:
            self._record_r02_attempt_failed(
                normalized_operation_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_r02_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                _R02_OPERATION_TYPE,
                operation_id=operation_id,
                actor=actor,
                source=source or "structured-repair-service",
                affected_entities=[
                    {"entity_type": "note", "entity_id": details["note_id"]},
                    {
                        "entity_type": "person",
                        "entity_id": details["referenced_person_id"],
                    },
                ],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def prepare_operation_revert(
        self, operation_id: str,
    ) -> OperationRevertPrecondition:
        """Prepare the one P11-D whitelist entry without mutating history."""
        normalized_id = str(operation_id).strip()
        if not normalized_id:
            raise ValueError("Operation ID is required")
        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        with self._connect() as conn:
            conn.execute("BEGIN")
            return _p11d_precondition_from_report(conn, report, normalized_id)

    def execute_operation_revert(
        self,
        precondition: OperationRevertPrecondition,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> dict:
        """Execute a guarded safe-merge revert; no dynamic inversion is accepted."""
        normalized_revert_id = str(operation_id).strip()
        if not normalized_revert_id:
            raise ValueError("Revert operation ID is required")
        if not isinstance(actor, dict) or not actor:
            raise ValueError("Authenticated actor is required")
        normalized_reason = str(reason).strip()
        if not normalized_reason:
            raise ValueError("Revert reason is required")
        if len(normalized_reason) > 500:
            raise ValueError("Revert reason must not exceed 500 characters")
        _validate_p11d_request_shape(precondition)

        with self._connect() as conn:
            existing = _p11d_existing_result(
                conn, normalized_revert_id, precondition,
            )
            if existing is not None:
                return existing

        from sentriface.integrity import ReadOnlyIntegrityChecker

        report = ReadOnlyIntegrityChecker(
            self.db_path, database_key=self.database_key,
        ).run()
        failure_details = {
            "revert_spec_version": precondition.revert_spec_version,
            "fingerprint_version": precondition.fingerprint_version,
            "fingerprint": precondition.fingerprint,
            "reverted_operation_id": precondition.operation_id,
            "reverted_operation_type": precondition.operation_type,
            "source_person_id": precondition.source_person_id,
            "target_person_id": precondition.target_person_id,
        }
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = _p11d_existing_result(
                    conn, normalized_revert_id, precondition,
                )
                if existing is not None:
                    return existing
                current = _p11d_precondition_from_report(
                    conn, report, precondition.operation_id,
                )
                if current != precondition:
                    raise OperationRevertRefused(
                        "Revert refused because the prepared authoritative state is stale",
                        report=report,
                    )

                immutable_before = _p11d_immutable_fingerprint(
                    conn, precondition.operation_id,
                )
                target_before = _p11d_person_fingerprint(
                    conn, precondition.target_person_id,
                )
                source_stable_before = _p11d_person_stable_fingerprint(
                    conn, precondition.source_person_id,
                )
                revision_before = _graph_revision_token(conn)
                _begin_journal_operation(
                    conn,
                    _P11D_REVERT_OPERATION_TYPE,
                    operation_id=normalized_revert_id,
                    actor=actor,
                    source=source or "guarded-operation-revert-service",
                    affected_entities=[
                        {"entity_type": "operation", "entity_id": precondition.operation_id},
                        {"entity_type": "person", "entity_id": precondition.source_person_id},
                        {"entity_type": "person", "entity_id": precondition.target_person_id},
                    ],
                    details={
                        **failure_details,
                        "reason": normalized_reason,
                        "affected_entity_count": len(precondition.affected_entities),
                        "affected_entity_fingerprint": _r01_hash(
                            precondition.affected_entities
                        ),
                        "dependency_state_fingerprint": (
                            precondition.dependency_state_fingerprint
                        ),
                    },
                )
                _p11d_checkpoint(failure_injector, "after_journal_started")
                changed_at = utc_now()
                cursor = conn.execute(
                    """
                    UPDATE persons
                    SET lifecycle_status = 'ACTIVE', canonical_person_id = NULL,
                        deleted_at = NULL, lifecycle_changed_at = ?
                    WHERE person_id = ? AND lifecycle_status = 'MERGED'
                      AND canonical_person_id = ?
                      AND lifecycle_changed_at = ?
                    """,
                    (
                        changed_at,
                        precondition.source_person_id,
                        precondition.target_person_id,
                        precondition.expected_source_lifecycle_changed_at,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OperationRevertRefused(
                        "Revert refused because the merge source changed"
                    )
                _p11d_checkpoint(failure_injector, "during_mutation")
                _replace_graph_projection(conn)
                _p11d_checkpoint(failure_injector, "during_graph_update")
                validation = _validate_p11d_postconditions(
                    conn,
                    precondition,
                    immutable_before=immutable_before,
                    target_before=target_before,
                    source_stable_before=source_stable_before,
                    revision_before=revision_before,
                )
                _p11d_checkpoint(failure_injector, "during_validation")
                _transition_journal_operation(
                    conn,
                    precondition.operation_id,
                    "REVERTED",
                    {
                        "reverted_by_operation_id": normalized_revert_id,
                        "revert_fingerprint": precondition.fingerprint,
                    },
                )
                result = {
                    **failure_details,
                    "revert_operation_id": normalized_revert_id,
                    "source_lifecycle_before": "MERGED",
                    "source_lifecycle_after": "ACTIVE",
                    "graph_revision_before": revision_before,
                    "graph_revision_after": validation["graph_revision_after"],
                    "changed": True,
                    "immediate_validation_status": "PASS",
                    "postcheck_status": "PENDING",
                }
                _transition_journal_operation(
                    conn, normalized_revert_id, "COMMITTED", result,
                )
                _p11d_checkpoint(failure_injector, "before_commit")
                return result
        except OperationRevertRefused:
            raise
        except Exception as exc:
            self._record_p11d_revert_attempt_failed(
                normalized_revert_id,
                actor=actor,
                source=source,
                details={
                    **failure_details,
                    "transaction_rolled_back": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
            )
            raise

    def _record_p11d_revert_attempt_failed(
        self,
        operation_id: str,
        *,
        actor: dict,
        source: str | None,
        details: dict,
    ) -> None:
        with self._connect() as conn:
            if _get_journal_operation(conn, operation_id) is not None:
                return
            _begin_journal_operation(
                conn,
                _P11D_REVERT_OPERATION_TYPE,
                operation_id=operation_id,
                actor=actor,
                source=source or "guarded-operation-revert-service",
                affected_entities=[
                    {"entity_type": "operation", "entity_id": details["reverted_operation_id"]},
                    {"entity_type": "person", "entity_id": details["source_person_id"]},
                    {"entity_type": "person", "entity_id": details["target_person_id"]},
                ],
                details=details,
            )
            _transition_journal_operation(conn, operation_id, "FAILED", details)

    def soft_delete_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        return self._soft_delete_person(
            person_id, operation_id, "soft-delete-person", actor, source,
        )

    def permanently_delete_person(
        self,
        person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Compatibility entry point for the former destructive UI action."""
        return self._soft_delete_person(person_id, operation_id, "purge-person", actor, source)

    def _soft_delete_person(
        self,
        person_id: str,
        operation_id: str,
        legacy_operation_type: str,
        actor: dict | None,
        source: str | None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, legacy_operation_type)
            if existing:
                return existing
            person = _require_person_lifecycle_preconditions(conn, person_id, legacy_operation_type)
            _begin_journal_operation(
                conn,
                "identity.delete",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
                details={"previous_status": person["lifecycle_status"]},
            )
            now = utc_now()
            deleted_at = person["deleted_at"] or now
            restore_until = (datetime.fromisoformat(now) + timedelta(days=DELETED_PERSON_RECOVERY_DAYS)).isoformat()
            cursor = conn.execute(
                """
                UPDATE persons
                SET lifecycle_status = 'DELETED', deleted_at = ?, lifecycle_changed_at = ?, restore_until = ?
                WHERE person_id = ? AND lifecycle_status <> 'DELETED'
                """,
                (deleted_at, deleted_at, restore_until, person_id),
            )
            counts = _person_historical_counts(conn, person_id)
            result = {
                "person_id": person_id,
                "person_name": person["name"],
                "deleted": True,
                "permanent": False,
                "tombstoned": True,
                "lifecycle_status": "DELETED",
                "deleted_at": deleted_at,
                "changed": bool(cursor.rowcount),
                **counts,
                "deleted_embeddings": 0,
                "deleted_sightings": 0,
                "deleted_profile_changes": 0,
                "deleted_queue_exclusions": 0,
                "deleted_associations": 0,
                "deleted_association_ids": [],
            }
            _record_person_operation(conn, operation_id, legacy_operation_type, result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def _set_canonical_person_id_for_merge(
        self,
        person_id: str,
        canonical_person_id: str,
        operation_id: str,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        """Compatibility harness; the connection-scoped helper is the P8 primitive."""
        with self._connect() as conn:
            _begin_journal_operation(
                conn,
                "identity.canonical-map",
                operation_id=operation_id,
                actor=actor,
                source=source or "identity-lifecycle",
                affected_entities=[
                    {"entity_type": "person", "entity_id": person_id},
                    {"entity_type": "person", "entity_id": canonical_person_id},
                ],
                details={"requested_canonical_person_id": canonical_person_id},
            )
            result = _set_canonical_person_id_in_transaction(
                conn, person_id, canonical_person_id,
            )
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'graph_connections'"
            ).fetchone() is not None:
                _replace_graph_projection(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_file_references_for_person(self, person_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_image AS path FROM embeddings
                WHERE person_id = ? AND source_image IS NOT NULL
                UNION
                SELECT crop_path AS path FROM embeddings
                WHERE person_id = ? AND crop_path IS NOT NULL
                UNION
                SELECT image_path AS path FROM recognition_details
                WHERE person_id = ? AND image_path IS NOT NULL
                """,
                (person_id, person_id, person_id),
            ).fetchall()
        return [str(row["path"]) for row in rows if row["path"]]

    def physically_purge_person(self, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "physical-purge-person")
            if existing:
                return existing
            person = conn.execute(
                "SELECT name, deleted_at FROM persons WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            embedding_count = int(conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            sighting_count = int(conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            change_count = int(conn.execute(
                "SELECT COUNT(*) FROM person_change_history WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            exclusion_count = int(conn.execute(
                "SELECT COUNT(*) FROM init_face_person_exclusions WHERE person_id = ?",
                (person_id,),
            ).fetchone()[0])
            association_rows = conn.execute(
                """
                SELECT association_id FROM person_associations
                WHERE source_person_id = ? OR target_person_id = ?
                ORDER BY association_id
                """,
                (person_id, person_id),
            ).fetchall()
            conn.execute("DELETE FROM recognition_details WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM init_face_person_exclusions WHERE person_id = ?", (person_id,))
            conn.execute(
                "DELETE FROM person_associations WHERE source_person_id = ? OR target_person_id = ?",
                (person_id, person_id),
            )
            conn.execute("DELETE FROM person_change_history WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM embeddings WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM persons WHERE person_id = ?", (person_id,))
            result = {
                "person_id": person_id,
                "person_name": person["name"],
                "was_archived": person["deleted_at"] is not None,
                "deleted": True,
                "permanent": True,
                "deleted_embeddings": embedding_count,
                "deleted_sightings": sighting_count,
                "deleted_profile_changes": change_count,
                "deleted_queue_exclusions": exclusion_count,
                "deleted_associations": len(association_rows),
                "deleted_association_ids": [row["association_id"] for row in association_rows],
            }
            _record_person_operation(conn, operation_id, "physical-purge-person", result)
            return result

    def delete_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        """Soft-delete a face for 30 days while retaining its linked sightings."""
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM biometric_enrollment_history WHERE embedding_id=?", (embedding_id,)).fetchone():
                raise ValueError("Reference Only history cannot enter timed Deleted Faces; retire the Reference instead")
            existing = _begin_person_operation(conn, operation_id, "soft-delete-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.source_image, e.crop_path, e.deleted_at,
                       e.purge_after, p.metadata
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown embedding: {embedding_id}")
            if row["deleted_at"]:
                raise KeyError("Face is already in Deleted Faces")
            raw_person_id = _raw_embedding_owner_person_id(conn, row)
            effective_person_id = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ?",
                (effective_person_id,),
            ).fetchone()
            if effective_person is None:
                raise KeyError(f"Unknown effective person: {effective_person_id}")
            _begin_journal_operation(
                conn, "biometric.face.delete", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": effective_person_id},
                ],
            )
            detail_count = conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()[0]
            deleted_at = utc_now()
            purge_after = (
                datetime.fromisoformat(deleted_at)
                + timedelta(days=DELETED_FACE_RETENTION_DAYS)
            ).isoformat()
            conn.execute(
                """
                UPDATE embeddings
                SET deleted_at = ?, purge_after = ?
                WHERE embedding_id = ? AND deleted_at IS NULL
                """,
                (deleted_at, purge_after, embedding_id),
            )
            metadata = json.loads(effective_person["metadata"])
            if metadata.get("representative_embedding_id") == embedding_id:
                metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), effective_person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": effective_person_id,
                "raw_person_id": raw_person_id,
                "deleted": True,
                "permanent": False,
                "retained_sightings": detail_count,
                "deleted_at": deleted_at,
                "purge_after": purge_after,
                "source_image": row["source_image"],
                "crop_path": row["crop_path"],
            }
            _record_person_operation(conn, operation_id, "soft-delete-embedding", result)
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_deleted_embeddings(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.quality_score,
                       e.source_image, e.crop_path, e.created_at,
                       e.deleted_at, e.purge_after,
                       p.name, p.deleted_at AS person_deleted_at,
                       p.lifecycle_status AS person_lifecycle_status,
                       p.canonical_person_id AS canonical_person_id,
                       COUNT(d.detail_id) AS sighting_count
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                LEFT JOIN recognition_details d ON d.embedding_id = e.embedding_id
                WHERE e.deleted_at IS NOT NULL AND e.erased_at IS NULL
                GROUP BY e.embedding_id
                ORDER BY e.deleted_at DESC
                """
            ).fetchall()
            result: list[dict] = []
            for row in rows:
                item = dict(row)
                raw_person_id = _raw_embedding_owner_person_id(conn, row)
                effective_person_id = _effective_embedding_owner_person_id(conn, row)
                effective_person = conn.execute(
                    "SELECT name, lifecycle_status, deleted_at FROM persons WHERE person_id = ?",
                    (effective_person_id,),
                ).fetchone()
                item["raw_person_id"] = raw_person_id
                item["person_id"] = effective_person_id
                item["canonical_person_id"] = effective_person_id
                if effective_person is not None:
                    item["name"] = effective_person["name"]
                    item["person_lifecycle_status"] = effective_person["lifecycle_status"]
                    item["person_deleted_at"] = effective_person["deleted_at"]
                result.append(item)
            return result

    def restore_deleted_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "restore-deleted-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT e.embedding_id, e.person_id, e.deleted_at, e.purge_after, e.erased_at
                FROM embeddings e
                WHERE e.embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown deleted face: {embedding_id}")
            if row["deleted_at"] is None:
                raise KeyError("Face is not deleted")
            if row["erased_at"] is not None:
                raise KeyError("This face was erased and can't be restored")
            raw_person_id = _raw_embedding_owner_person_id(conn, row)
            effective_person_id = _effective_embedding_owner_person_id(conn, row)
            effective_person = conn.execute(
                "SELECT lifecycle_status, deleted_at, metadata FROM persons WHERE person_id = ?",
                (effective_person_id,),
            ).fetchone()
            if (
                effective_person is None
                or effective_person["lifecycle_status"] != "ACTIVE"
                or effective_person["deleted_at"] is not None
            ):
                raise KeyError("Only an active identity can receive a restored face")
            _begin_journal_operation(
                conn, "biometric.face.restore", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": effective_person_id},
                ],
            )
            conn.execute(
                """
                UPDATE embeddings
                SET deleted_at = NULL, purge_after = NULL
                WHERE embedding_id = ? AND deleted_at IS NOT NULL
                """,
                (embedding_id,),
            )
            metadata = json.loads(effective_person["metadata"])
            if not metadata.get("representative_embedding_id"):
                metadata["representative_embedding_id"] = embedding_id
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(metadata, separators=(",", ":")), effective_person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "person_id": effective_person_id,
                "raw_person_id": raw_person_id,
                "restored": True,
                "previously_deleted_at": row["deleted_at"],
            }
            _record_person_operation(conn, operation_id, "restore-deleted-embedding", result)
            _refresh_source_biometric_status(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def permanently_delete_embedding(
        self, embedding_id: str, operation_id: str,
        actor: dict | None = None, source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "purge-deleted-embedding")
            if existing:
                return existing
            row = conn.execute(
                """
                SELECT embedding_id, person_id, source_image, crop_path, deleted_at, purge_after, erased_at
                FROM embeddings
                WHERE embedding_id = ?
                """,
                (embedding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown deleted face: {embedding_id}")
            if row["deleted_at"] is None:
                raise KeyError("Move the face to Deleted Faces before deleting it permanently")
            if row["erased_at"] is not None:
                raise KeyError("This face has already been erased")
            if conn.execute("SELECT 1 FROM biometric_enrollment_history WHERE embedding_id=?", (embedding_id,)).fetchone():
                raise ValueError("Reference history is retained; retire the source instead of purging it")
            _begin_journal_operation(
                conn, "biometric.face.purge", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id},
                    {"entity_type": "person", "entity_id": row["person_id"]},
                ],
            )
            detail_count = conn.execute(
                "SELECT COUNT(*) FROM recognition_details WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()[0]
            stub_retained = _erase_deleted_face_in_transaction(conn, row, utc_now())
            result = {
                "embedding_id": embedding_id,
                "person_id": row["person_id"],
                "deleted": True,
                "permanent": True,
                "stub_retained": stub_retained,
                "deleted_sightings": detail_count,
                "source_image": row["source_image"],
                "crop_path": row["crop_path"],
                "previously_deleted_at": row["deleted_at"],
                "previous_purge_after": row["purge_after"],
            }
            _record_person_operation(conn, operation_id, "purge-deleted-embedding", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def list_expired_deleted_embedding_ids(self, now: str | None = None) -> list[str]:
        cutoff = now or utc_now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT embedding_id
                FROM embeddings
                WHERE deleted_at IS NOT NULL
                  AND erased_at IS NULL
                  AND purge_after IS NOT NULL
                  AND purge_after <= ?
                  AND NOT EXISTS (SELECT 1 FROM biometric_enrollment_history h WHERE h.embedding_id=embeddings.embedding_id)
                ORDER BY purge_after ASC
                """,
                (cutoff,),
            ).fetchall()
        return [row["embedding_id"] for row in rows]

    def purge_expired_deleted_embeddings(
        self,
        embedding_ids: list[str],
        operation_id: str,
        now: str | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        unique_ids = list(dict.fromkeys(embedding_ids))
        with self._connect() as conn:
            existing = _begin_person_operation(
                conn,
                operation_id,
                "purge-expired-embeddings",
            )
            if existing:
                return existing
            _begin_journal_operation(
                conn, "biometric.face.purge-expired", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "retention-service",
                affected_entities=[
                    {"entity_type": "embedding", "entity_id": embedding_id}
                    for embedding_id in unique_ids
                ],
            )
            if not unique_ids:
                result = {
                    "embedding_ids": [],
                    "person_ids": [],
                    "purged": 0,
                    "deleted_sightings": 0,
                }
                _record_person_operation(
                    conn,
                    operation_id,
                    "purge-expired-embeddings",
                    result,
                )
                _transition_journal_operation(conn, operation_id, "COMMITTED", result)
                return result
            placeholders = ", ".join("?" for _ in unique_ids)
            rows = conn.execute(
                f"""
                SELECT embedding_id, person_id, source_image, crop_path
                FROM embeddings
                WHERE embedding_id IN ({placeholders})
                  AND deleted_at IS NOT NULL
                  AND erased_at IS NULL
                  AND purge_after IS NOT NULL
                  AND purge_after <= ?
                  AND NOT EXISTS (SELECT 1 FROM biometric_enrollment_history h WHERE h.embedding_id=embeddings.embedding_id)
                ORDER BY embedding_id
                """,
                (*unique_ids, now or utc_now()),
            ).fetchall()
            eligible_ids = [row["embedding_id"] for row in rows]
            detail_count = 0
            if eligible_ids:
                eligible_placeholders = ", ".join("?" for _ in eligible_ids)
                detail_count = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM recognition_details
                    WHERE embedding_id IN ({eligible_placeholders})
                    """,
                    eligible_ids,
                ).fetchone()[0]
            erased_at = utc_now()
            stub_ids = [
                row["embedding_id"]
                for row in rows
                if _erase_deleted_face_in_transaction(conn, row, erased_at)
            ]
            result = {
                "embedding_ids": eligible_ids,
                "person_ids": sorted({row["person_id"] for row in rows}),
                "purged": len(eligible_ids),
                "stub_embedding_ids": stub_ids,
                "deleted_sightings": detail_count,
                "paths": [
                    {
                        "source_image": row["source_image"],
                        "crop_path": row["crop_path"],
                    }
                    for row in rows
                ],
            }
            _record_person_operation(
                conn,
                operation_id,
                "purge-expired-embeddings",
                result,
            )
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def _legacy_move_embedding(self, embedding_id: str, person_id: str, operation_id: str) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "move-embedding")
            if existing:
                return existing
            target = conn.execute(
                "SELECT name, metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if target is None:
                raise KeyError(f"Unknown person: {person_id}")
            embedding = conn.execute(
                """
                SELECT e.person_id, p.metadata
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ?
                  AND e.deleted_at IS NULL
                  AND p.deleted_at IS NULL
                """,
                (embedding_id,),
            ).fetchone()
            if embedding is None:
                raise KeyError(f"Unknown embedding: {embedding_id}")
            source_person_id = embedding["person_id"]
            if source_person_id == person_id:
                result = {
                    "embedding_id": embedding_id,
                    "source_person_id": source_person_id,
                    "target_person_id": person_id,
                    "moved": True,
                    "changed": False,
                    "moved_sightings": 0,
                }
                _record_person_operation(conn, operation_id, "move-embedding", result)
                return result
            conn.execute(
                "UPDATE embeddings SET person_id = ? WHERE embedding_id = ?",
                (person_id, embedding_id),
            )
            _mark_person_enrolled(conn, person_id)
            detail_cursor = conn.execute(
                """
                UPDATE recognition_details
                SET person_id = ?, name = ?
                WHERE embedding_id = ?
                """,
                (person_id, target["name"], embedding_id),
            )
            source_metadata = json.loads(embedding["metadata"])
            if source_metadata.get("representative_embedding_id") == embedding_id:
                source_metadata.pop("representative_embedding_id", None)
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(source_metadata, separators=(",", ":")), source_person_id),
                )
            target_metadata = json.loads(target["metadata"])
            if not target_metadata.get("representative_embedding_id"):
                target_metadata["representative_embedding_id"] = embedding_id
                conn.execute(
                    "UPDATE persons SET metadata = ? WHERE person_id = ?",
                    (json.dumps(target_metadata, separators=(",", ":")), person_id),
                )
            result = {
                "embedding_id": embedding_id,
                "source_person_id": source_person_id,
                "target_person_id": person_id,
                "moved": True,
                "changed": True,
                "moved_sightings": detail_cursor.rowcount,
            }
            _record_person_operation(conn, operation_id, "move-embedding", result)
            return result

    def _legacy_merge_persons(
        self, source_person_id: str, target_person_id: str, operation_id: str,
    ) -> dict:
        """Retained only to read/test legacy merge history until normalized P8 merge."""
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "merge-persons")
            if existing:
                return existing
            if source_person_id == target_person_id:
                raise KeyError("Source and target person must be different")
            source = conn.execute(
                "SELECT name, metadata, deleted_at, enrollment_status FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (source_person_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT name, metadata, deleted_at, enrollment_status FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (target_person_id,),
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown source person: {source_person_id}")
            if target is None:
                raise KeyError(f"Unknown target person: {target_person_id}")
            embedding_rows = conn.execute(
                "SELECT embedding_id, deleted_at FROM embeddings WHERE person_id = ? ORDER BY embedding_id",
                (source_person_id,),
            ).fetchall()
            detail_rows = conn.execute(
                "SELECT detail_id, name FROM recognition_details WHERE person_id = ? ORDER BY detail_id",
                (source_person_id,),
            ).fetchall()
            source_exclusions = conn.execute(
                "SELECT session_id, init_face_id FROM init_face_person_exclusions WHERE person_id = ? ORDER BY session_id, init_face_id",
                (source_person_id,),
            ).fetchall()
            target_exclusions = conn.execute(
                "SELECT session_id, init_face_id FROM init_face_person_exclusions WHERE person_id = ? ORDER BY session_id, init_face_id",
                (target_person_id,),
            ).fetchall()
            moved_embeddings = sum(1 for row in embedding_rows if row["deleted_at"] is None)
            moved_deleted_faces = sum(1 for row in embedding_rows if row["deleted_at"] is not None)
            moved_sightings = len(detail_rows)
            original_source_metadata = json.loads(source["metadata"])
            original_target_metadata = json.loads(target["metadata"])
            conn.execute(
                "UPDATE embeddings SET person_id = ? WHERE person_id = ?",
                (target_person_id, source_person_id),
            )
            if embedding_rows:
                _mark_person_enrolled(conn, target_person_id)
            conn.execute(
                """
                UPDATE recognition_details
                SET person_id = ?, name = ?
                WHERE person_id = ?
                """,
                (target_person_id, target["name"], source_person_id),
            )
            source_metadata = dict(original_source_metadata)
            target_metadata = dict(original_target_metadata)
            merged_tags = _normalize_tags([
                *target_metadata.get("tags", []),
                *source_metadata.get("tags", []),
            ])
            if merged_tags:
                target_metadata["tags"] = merged_tags
            target_metadata["favorite"] = bool(
                target_metadata.get("favorite") or source_metadata.get("favorite")
            )
            if not target_metadata.get("representative_embedding_id"):
                source_representative = source_metadata.get("representative_embedding_id")
                if source_representative:
                    target_metadata["representative_embedding_id"] = source_representative
            conn.execute(
                "UPDATE persons SET metadata = ? WHERE person_id = ?",
                (json.dumps(target_metadata, separators=(",", ":")), target_person_id),
            )
            source_metadata["merged_into"] = target_person_id
            source_metadata["merged_at"] = utc_now()
            conn.execute(
                """
                UPDATE persons
                SET metadata = ?, deleted_at = ?
                WHERE person_id = ?
                """,
                (
                    json.dumps(source_metadata, separators=(",", ":")),
                    source_metadata["merged_at"],
                    source_person_id,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO init_face_person_exclusions(
                    session_id, init_face_id, person_id, created_at
                )
                SELECT session_id, init_face_id, ?, created_at
                FROM init_face_person_exclusions
                WHERE person_id = ?
                """,
                (target_person_id, source_person_id),
            )
            conn.execute(
                "DELETE FROM init_face_person_exclusions WHERE person_id = ?",
                (source_person_id,),
            )
            result = {
                "source_person_id": source_person_id,
                "target_person_id": target_person_id,
                "merged": True,
                "moved_embeddings": moved_embeddings,
                "moved_deleted_faces": moved_deleted_faces,
                "moved_sightings": moved_sightings,
                "undo_supported": True,
                "undo_snapshot": {
                    "source_name": source["name"],
                    "target_name": target["name"],
                    "source_metadata": original_source_metadata,
                    "target_metadata": original_target_metadata,
                    "source_status": source["enrollment_status"],
                    "target_status": target["enrollment_status"],
                    "merged_source_metadata": source_metadata,
                    "merged_target_metadata": target_metadata,
                    "embedding_ids": [row["embedding_id"] for row in embedding_rows],
                    "embedding_states": [
                        {
                            "embedding_id": row["embedding_id"],
                            "deleted_at": row["deleted_at"],
                        }
                        for row in embedding_rows
                    ],
                    "details": [
                        {"detail_id": row["detail_id"], "name": row["name"]}
                        for row in detail_rows
                    ],
                    "source_exclusions": [dict(row) for row in source_exclusions],
                    "target_exclusions": [dict(row) for row in target_exclusions],
                },
            }
            _record_person_operation(conn, operation_id, "merge-persons", result)
            return result

    def _legacy_undo_merge_persons(
        self, merge_operation_id: str, operation_id: str,
    ) -> dict:
        """Retained only to read/test legacy merge history until normalized P8 merge."""
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "undo-merge-persons")
            if existing:
                return existing
            merge = _existing_person_operation(conn, merge_operation_id, "merge-persons")
            if merge is None:
                raise KeyError("Unknown merge operation")
            snapshot = merge.get("undo_snapshot")
            if not snapshot:
                raise KeyError("This older merge cannot be undone safely from profile history")
            source_person_id = str(merge["source_person_id"])
            target_person_id = str(merge["target_person_id"])
            prior_undo = conn.execute(
                "SELECT 1 FROM person_operations WHERE operation_type = 'undo-merge-persons' AND json_extract(result, '$.merge_operation_id') = ?",
                (merge_operation_id,),
            ).fetchone()
            if prior_undo:
                raise KeyError("This merge has already been undone")
            source = conn.execute(
                "SELECT metadata, deleted_at FROM persons WHERE person_id = ?",
                (source_person_id,),
            ).fetchone()
            target = conn.execute(
                "SELECT metadata, deleted_at FROM persons WHERE person_id = ?",
                (target_person_id,),
            ).fetchone()
            if source is None or target is None:
                raise KeyError("One of the merged profiles no longer exists")
            if target["deleted_at"] is not None:
                raise KeyError("Restore the kept profile before undoing this merge")
            if json.loads(source["metadata"]) != snapshot["merged_source_metadata"]:
                raise KeyError("The merged record changed after the merge; undo was not applied")
            if json.loads(target["metadata"]) != snapshot["merged_target_metadata"]:
                raise KeyError("The kept profile changed after the merge; undo was not applied")
            embedding_ids = list(snapshot.get("embedding_ids") or [])
            if embedding_ids:
                placeholders = ", ".join("?" for _ in embedding_ids)
                rows = conn.execute(
                    f"SELECT embedding_id, person_id, deleted_at FROM embeddings WHERE embedding_id IN ({placeholders})",
                    embedding_ids,
                ).fetchall()
                expected_embedding_states = {
                    str(item["embedding_id"]): item.get("deleted_at")
                    for item in snapshot.get("embedding_states") or []
                }
                if len(rows) != len(embedding_ids) or any(
                    row["person_id"] != target_person_id
                    or (
                        expected_embedding_states
                        and row["deleted_at"] != expected_embedding_states.get(str(row["embedding_id"]))
                    )
                    for row in rows
                ):
                    raise KeyError("Merged photos changed after the merge; undo was not applied")
                detail_ids = {str(item["detail_id"]) for item in snapshot.get("details") or []}
                linked_details = conn.execute(
                    f"SELECT detail_id, person_id, name FROM recognition_details WHERE embedding_id IN ({placeholders})",
                    embedding_ids,
                ).fetchall()
                if any(
                    row["person_id"] != target_person_id
                    or row["detail_id"] not in detail_ids
                    or row["name"] != snapshot["target_name"]
                    for row in linked_details
                ):
                    raise KeyError("Merged sightings changed after the merge; undo was not applied")
                conn.execute(
                    f"UPDATE embeddings SET person_id = ? WHERE embedding_id IN ({placeholders})",
                    (source_person_id, *embedding_ids),
                )
            for detail in snapshot.get("details") or []:
                cursor = conn.execute(
                    "UPDATE recognition_details SET person_id = ?, name = ? WHERE detail_id = ? AND person_id = ?",
                    (source_person_id, detail["name"], detail["detail_id"], target_person_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError("A merged sighting changed after the merge; undo was not applied")
            conn.execute(
                "UPDATE persons SET metadata = ?, deleted_at = NULL, enrollment_status = ? WHERE person_id = ?",
                (
                    json.dumps(snapshot["source_metadata"], separators=(",", ":")),
                    snapshot.get("source_status", "enrolled"),
                    source_person_id,
                ),
            )
            conn.execute(
                "UPDATE persons SET metadata = ?, enrollment_status = ? WHERE person_id = ?",
                (
                    json.dumps(snapshot["target_metadata"], separators=(",", ":")),
                    snapshot.get("target_status", "enrolled"),
                    target_person_id,
                ),
            )
            source_exclusions = snapshot.get("source_exclusions") or []
            target_exclusions = snapshot.get("target_exclusions") or []
            affected = {
                (item["session_id"], item["init_face_id"])
                for item in [*source_exclusions, *target_exclusions]
            }
            expected_target_exclusions = affected
            if affected:
                current_exclusions = conn.execute(
                    "SELECT session_id, init_face_id, person_id FROM init_face_person_exclusions WHERE person_id IN (?, ?)",
                    (source_person_id, target_person_id),
                ).fetchall()
                current_source = {
                    (row["session_id"], row["init_face_id"])
                    for row in current_exclusions
                    if row["person_id"] == source_person_id
                }
                current_target = {
                    (row["session_id"], row["init_face_id"])
                    for row in current_exclusions
                    if row["person_id"] == target_person_id
                    and (row["session_id"], row["init_face_id"]) in affected
                }
                if current_source.intersection(affected) or current_target != expected_target_exclusions:
                    raise KeyError("Merge exclusions changed after the merge; undo was not applied")
            for session_id, init_face_id in affected:
                conn.execute(
                    "DELETE FROM init_face_person_exclusions WHERE session_id = ? AND init_face_id = ? AND person_id IN (?, ?)",
                    (session_id, init_face_id, source_person_id, target_person_id),
                )
            now = utc_now()
            conn.executemany(
                "INSERT OR IGNORE INTO init_face_person_exclusions(session_id, init_face_id, person_id, created_at) VALUES (?, ?, ?, ?)",
                [(item["session_id"], item["init_face_id"], source_person_id, now) for item in source_exclusions]
                + [(item["session_id"], item["init_face_id"], target_person_id, now) for item in target_exclusions],
            )
            result = {
                "source_person_id": source_person_id,
                "target_person_id": target_person_id,
                "merge_operation_id": merge_operation_id,
                "restored_embeddings": len(embedding_ids),
                "restored_sightings": len(snapshot.get("details") or []),
                "undone": True,
            }
            _record_person_operation(conn, operation_id, "undo-merge-persons", result)
            return result

    def update_person_preferences(
        self,
        person_id: str,
        operation_id: str,
        favorite: bool | None = None,
        representative_embedding_id: str | None = None,
        actor: dict | None = None,
        source: str | None = None,
    ) -> dict:
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, "person-preferences")
            if existing:
                return existing
            person = conn.execute(
                "SELECT metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if person is None:
                raise KeyError(f"Unknown person: {person_id}")
            _begin_journal_operation(
                conn, "identity.preferences.update", operation_id=operation_id,
                actor=actor, source=_optional_text(source) or "identity-service",
                affected_entities=[{"entity_type": "person", "entity_id": person_id}],
            )
            metadata = json.loads(person["metadata"])
            changed_preferences = []
            if favorite is not None:
                metadata["favorite"] = bool(favorite)
                changed_preferences.append("favorite")
            if representative_embedding_id is not None:
                owned = conn.execute(
                    """
                    SELECT embedding_id, person_id FROM embeddings
                    WHERE embedding_id = ? AND deleted_at IS NULL
                    """,
                    (representative_embedding_id,),
                ).fetchone()
                if (
                    owned is None
                    or _effective_embedding_owner_person_id(conn, owned)
                    != _resolve_canonical_person_id(conn, person_id)
                ):
                    raise KeyError(
                        f"Embedding {representative_embedding_id} does not belong to person {person_id}"
                    )
                metadata["representative_embedding_id"] = representative_embedding_id
                changed_preferences.append("representative_photo")
            conn.execute(
                "UPDATE persons SET metadata = ? WHERE person_id = ?",
                (json.dumps(metadata, separators=(",", ":")), person_id),
            )
            result = {
                "person_id": person_id,
                "favorite": bool(metadata.get("favorite")),
                "representative_embedding_id": metadata.get("representative_embedding_id"),
                "changed_preferences": changed_preferences,
                "updated": True,
            }
            _record_person_operation(conn, operation_id, "person-preferences", result)
            _transition_journal_operation(conn, operation_id, "COMMITTED", result)
            return result

    def add_recognition_detail(
        self,
        embedding_id: str,
        person_id: str,
        image_id: str,
        name: str,
        decision: str,
        seen_date: str,
        seen_time: str,
        place_seen: str,
        individual_count: int,
        event_occasion: str,
        image_path: str | None = None,
        rank: str | None = None,
        country: str | None = None,
        importance: str | None = None,
        added_by: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        operation_id: str | None = None,
    ) -> RecognitionDetail:
        """Internal legacy/import primitive; production review details use P6."""
        detail = RecognitionDetail(
            detail_id=str(uuid.uuid4()),
            embedding_id=embedding_id,
            person_id=person_id,
            image_id=image_id,
            image_path=image_path,
            name=name,
            decision=decision,
            seen_date=seen_date,
            seen_time=seen_time,
            place_seen=place_seen,
            individual_count=individual_count,
            event_occasion=event_occasion,
            rank=rank,
            country=country,
            importance=importance,
            added_by=added_by,
            notes=notes.strip(),
            created_at=utc_now(),
        )
        with self._connect() as conn:
            if operation_id:
                existing = _begin_person_operation(conn, operation_id, "recognition-followup")
                if existing:
                    row = conn.execute(
                        "SELECT * FROM recognition_details WHERE detail_id = ?",
                        (str(existing["detail_id"]),),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("Recognition follow-up operation is missing its detail")
                    return _recognition_detail_from_row(row)
            owned = conn.execute(
                """
                SELECT 1
                FROM embeddings e
                JOIN persons p ON p.person_id = e.person_id
                WHERE e.embedding_id = ? AND e.person_id = ?
                  AND e.deleted_at IS NULL AND p.deleted_at IS NULL
                """,
                (embedding_id, person_id),
            ).fetchone()
            if owned is None:
                raise KeyError("Recognition detail must reference an active face owned by the person")
            conn.execute(
                """
                INSERT INTO recognition_details(
                    detail_id, embedding_id, person_id, image_id, image_path,
                    name, decision, seen_date, seen_time, place_seen,
                    individual_count, event_occasion, rank, country,
                    importance, added_by, notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detail.detail_id,
                    detail.embedding_id,
                    detail.person_id,
                    detail.image_id,
                    detail.image_path,
                    detail.name,
                    detail.decision,
                    detail.seen_date,
                    detail.seen_time,
                    detail.place_seen,
                    detail.individual_count,
                    detail.event_occasion,
                    detail.rank,
                    detail.country,
                    detail.importance,
                    detail.added_by,
                    detail.notes,
                    detail.created_at,
                ),
            )
            profile_updates = {
                key: value
                for key, value in {
                    "rank": rank,
                    "country": country,
                    "importance": importance,
                }.items()
                if value
            }
            creator_name = added_by.strip() if decision == "new" and added_by and added_by.strip() else ""
            if profile_updates or creator_name:
                row = conn.execute(
                    "SELECT metadata FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if row is not None:
                    metadata = json.loads(row["metadata"])
                    metadata.update(profile_updates)
                    if creator_name:
                        metadata.setdefault("added_by", creator_name)
                    conn.execute(
                        "UPDATE persons SET metadata = ? WHERE person_id = ? AND deleted_at IS NULL",
                        (json.dumps(metadata, separators=(",", ":")), person_id),
                    )
            automatic_associations = _legacy_create_note_associations(
                conn, person_id, detail.notes, (added_by or "").strip(), mentioned_person_ids or [],
            )
            if operation_id:
                _record_person_operation(
                    conn,
                    operation_id,
                    "recognition-followup",
                    {
                        "detail_id": detail.detail_id,
                        "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                        "automatic_association_ids": [item.association_id for item in automatic_associations],
                    },
                )
        return detail

    def list_recognition_details_for_embedding(self, embedding_id: str) -> list[RecognitionDetail]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT detail_id, embedding_id, person_id, image_id, image_path,
                       name, decision, seen_date, seen_time, place_seen,
                       individual_count, event_occasion, rank, country,
                       importance, added_by, notes, created_at
                FROM recognition_details
                WHERE embedding_id = ?
                ORDER BY created_at ASC
                """,
                (embedding_id,),
            ).fetchall()
        return [_recognition_detail_from_row(row) for row in rows]

    def list_recognition_details_for_person(self, person_id: str) -> list[RecognitionDetail]:
        with self._connect() as conn:
            canonical_person_id = _resolve_canonical_person_id(conn, person_id)
            rows = conn.execute(
                """
                SELECT d.detail_id, d.embedding_id, d.person_id, d.image_id, d.image_path,
                       d.name, d.decision, d.seen_date, d.seen_time, d.place_seen,
                       d.individual_count, d.event_occasion, d.rank, d.country,
                       d.importance, d.added_by, d.notes, d.created_at
                FROM recognition_details d
                JOIN embeddings e ON e.embedding_id = d.embedding_id
                WHERE e.deleted_at IS NULL
                ORDER BY d.seen_date DESC, d.seen_time DESC, d.created_at DESC
                """
            ).fetchall()
            return [
                _recognition_detail_from_row(row) for row in rows
                if (
                    (embedding := conn.execute(
                        "SELECT embedding_id, person_id FROM embeddings WHERE embedding_id = ?",
                        (row["embedding_id"],),
                    ).fetchone()) is not None
                    and _effective_embedding_owner_person_id(conn, embedding)
                    == canonical_person_id
                )
            ]

    def list_raw_recognition_details_for_person(
        self, person_id: str,
    ) -> list[RecognitionDetail]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.detail_id, d.embedding_id, d.person_id, d.image_id, d.image_path,
                       d.name, d.decision, d.seen_date, d.seen_time, d.place_seen,
                       d.individual_count, d.event_occasion, d.rank, d.country,
                       d.importance, d.added_by, d.notes, d.created_at
                FROM recognition_details d
                JOIN embeddings e ON e.embedding_id = d.embedding_id
                WHERE d.person_id = ? AND e.deleted_at IS NULL
                ORDER BY d.seen_date DESC, d.seen_time DESC, d.created_at DESC
                """,
                (person_id,),
            ).fetchall()
        return [_recognition_detail_from_row(row) for row in rows]

    def backup_to(self, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            with closing(connect_database(target_path, self.database_key)) as target:
                source.backup(target)

    def add_embedding(
        self,
        person_id: str,
        vector: Embedding,
        quality_score: float,
        source_image: str | None = None,
        crop_path: str | None = None,
    ) -> EmbeddingRecord:
        """Internal fixture/import primitive; production enrollment uses P6."""
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
            person_exists = conn.execute(
                "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                (person_id,),
            ).fetchone()
            if person_exists is None:
                raise KeyError(f"Unknown person: {person_id}")
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
            _mark_person_enrolled(conn, person_id)
        return record

    def list_embeddings(self) -> list[EmbeddingRecord]:
        with self._connect() as conn:
            return _eligible_source_samples(conn)

    def current_embedding_person_ids(self, embedding_ids: list[str], *, quality_only: bool = True) -> dict[str, str]:
        selected = set(embedding_ids)
        with self._connect() as conn:
            samples = _eligible_source_samples(conn)
            good_people = {r.person_id for r in samples if r.recognition_state == "GOOD"}
            return {r.embedding_id: r.person_id for r in samples if r.embedding_id in selected
                    and r.recognition_state != "PROOF_ONLY"
                    and (not quality_only or r.recognition_state == "GOOD" or r.person_id not in good_people)}

    def save_pending_addition(self, pending: PendingAddition) -> None:
        if len(pending.vector) != self.embedding_dim:
            raise ValueError(f"Expected {self.embedding_dim} dimensions, got {len(pending.vector)}")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_additions(
                    pending_id, source_image, box_x, box_y, box_width, box_height,
                    box_confidence, quality_score, landmarks, crop_path, vector,
                    matches, decision, quality_status, pending_quality_score,
                    quality_reasons, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(
                        [
                            {
                                "person_id": match.person_id,
                                "score": match.score,
                                "embedding_ids": list(match.embedding_ids),
                                "embeddings_matched": match.embeddings_matched,
                            }
                            for match in pending.matches
                        ]
                    ),
                    pending.decision.value,
                    pending.quality.status.value,
                    pending.quality.score,
                    json.dumps(pending.quality.reasons),
                    pending.created_at,
                ),
            )

    def get_pending_addition(self, pending_id: str) -> PendingAddition | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pending_id, source_image, box_x, box_y, box_width, box_height,
                       box_confidence, quality_score, landmarks, crop_path, vector,
                       matches, decision, quality_status, pending_quality_score,
                       quality_reasons, created_at
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
                       matches, decision, quality_status, pending_quality_score,
                       quality_reasons, created_at
                FROM pending_additions
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_pending_from_row(row) for row in rows]

    def list_all_file_references(self) -> list[str]:
        """Return paths from active, archived, deleted, pending, and queue state."""
        queries = (
            "SELECT source_image AS path FROM embeddings WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM embeddings WHERE crop_path IS NOT NULL",
            "SELECT source_image AS path FROM biometric_enrollment_history WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM biometric_enrollment_history WHERE crop_path IS NOT NULL",
            "SELECT image_path AS path FROM recognition_details WHERE image_path IS NOT NULL",
            "SELECT media_path AS path FROM observation_media WHERE media_path IS NOT NULL",
            "SELECT source_image AS path FROM pending_additions WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM pending_additions WHERE crop_path IS NOT NULL",
            "SELECT source_path AS path FROM init_sessions WHERE source_path IS NOT NULL",
            "SELECT source_image AS path FROM init_faces WHERE source_image IS NOT NULL",
            "SELECT crop_path AS path FROM init_faces WHERE crop_path IS NOT NULL",
        )
        with self._connect() as conn:
            return [
                str(row["path"])
                for query in queries
                for row in conn.execute(query).fetchall()
                if row["path"]
            ]

    def _legacy_confirm_pending_addition(
        self,
        pending_id: str,
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
        recognition_detail: dict | None = None,
    ) -> tuple[Person, EmbeddingRecord]:
        operation_type = "confirm-pending-existing" if person_id else "confirm-pending-new"
        creating_new_person = person_id is None
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, operation_type)
            if existing:
                # A lost-response retry may have re-prepared the same face.
                # The committed operation wins; discard the retry-only row.
                conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))
                return self._confirmed_records(
                    conn, str(existing["person_id"]), str(existing["embedding_id"])
                )
            pending_row = conn.execute(
                "SELECT * FROM pending_additions WHERE pending_id = ?", (pending_id,)
            ).fetchone()
            if pending_row is None:
                raise KeyError(f"Unknown pending addition: {pending_id}")
            if person_id:
                person_row = conn.execute(
                    "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError(f"Unknown person: {person_id}")
            else:
                if not name or not name.strip():
                    raise KeyError("Person name is required")
                person_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO persons(person_id, name, metadata, created_at, notes) VALUES (?, ?, ?, ?, ?)",
                    (
                        person_id,
                        name.strip(),
                        json.dumps(metadata or {}, separators=(",", ":")),
                        utc_now(),
                        notes.strip(),
                    ),
                )
                automatic_associations = _legacy_create_note_associations(
                    conn, person_id, notes.strip(), "SentriFace", mentioned_person_ids or [],
                )
            if not creating_new_person:
                automatic_associations = []
            embedding_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO embeddings(
                    embedding_id, person_id, vector, quality_score,
                    source_image, crop_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    embedding_id,
                    person_id,
                    pending_row["vector"],
                    pending_row["quality_score"],
                    pending_row["source_image"],
                    pending_row["crop_path"],
                    utc_now(),
                ),
            )
            _mark_person_enrolled(conn, person_id)
            detail_id = None
            if recognition_detail is not None:
                detail_id = str(uuid.uuid4())
                detail_notes = str(recognition_detail.get("notes") or "").strip()
                conn.execute(
                    """
                    INSERT INTO recognition_details(
                        detail_id, embedding_id, person_id, image_id, image_path,
                        name, decision, seen_date, seen_time, place_seen,
                        individual_count, event_occasion, rank, country,
                        importance, added_by, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail_id, embedding_id, person_id,
                        recognition_detail["image_id"], recognition_detail.get("image_path"),
                        recognition_detail["name"], recognition_detail.get("decision", "existing"),
                        recognition_detail["seen_date"], recognition_detail["seen_time"],
                        recognition_detail["place_seen"], int(recognition_detail["individual_count"]),
                        recognition_detail["event_occasion"], recognition_detail.get("rank"),
                        recognition_detail.get("country"), recognition_detail.get("importance"),
                        recognition_detail.get("added_by"), detail_notes, utc_now(),
                    ),
                )
                automatic_associations.extend(_legacy_create_note_associations(
                    conn, person_id, detail_notes,
                    str(recognition_detail.get("added_by") or "").strip(),
                    list(recognition_detail.get("mentioned_person_ids") or []),
                ))
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))
            _record_person_operation(
                conn,
                operation_id,
                operation_type,
                {
                    "person_id": person_id,
                    "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                    "embedding_id": embedding_id,
                    "detail_id": detail_id,
                    "automatic_association_ids": [item.association_id for item in automatic_associations],
                },
            )
            return self._confirmed_records(conn, person_id, embedding_id)

    @staticmethod
    def _confirmed_records(
        conn: sqlite3.Connection,
        person_id: str,
        embedding_id: str,
    ) -> tuple[Person, EmbeddingRecord]:
        person_row = conn.execute(
            "SELECT * FROM persons WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        embedding_row = conn.execute(
            """
            SELECT embedding_id, person_id, vector, quality_score,
                   source_image, crop_path, created_at, recognition_state
            FROM embeddings WHERE embedding_id = ?
            """,
            (embedding_id,),
        ).fetchone()
        if person_row is None or embedding_row is None:
            raise RuntimeError("Confirmed identity operation is missing durable records")
        person = _person_from_row(person_row)
        return person, _embedding_from_row(embedding_row)
    def delete_pending_addition(self, pending_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_additions WHERE pending_id = ?", (pending_id,))

    def bind_init_session_attachment(self, session_id: str, observation_id: str,
                                     expected_revision: str | None) -> None:
        """Retain workflow ownership even when subsequent planning is rejected."""
        if not isinstance(expected_revision, str) or not expected_revision.strip():
            raise ValueError("Attach Media requires an Event revision")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute("SELECT * FROM init_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if session is None:
                raise KeyError(f"Unknown init session: {session_id}")
            if session["status"] == "closed":
                raise ValueError("This draft is closed")
            observation = _require_observation(conn, observation_id)
            if observation["status"] != "FINALIZED":
                raise ValueError("Attach Media requires a finalized Event")
            if session["target_observation_id"] not in (None, observation_id):
                raise ValueError("An Attach Media draft cannot change its target Event")
            reviews = conn.execute("SELECT target_observation_id FROM photo_reviews WHERE session_id = ?", (session_id,)).fetchall()
            if any(row["target_observation_id"] != observation_id for row in reviews):
                raise ValueError("Event grouping has already been confirmed for this session")
            # A materialized review owns its original revision precondition. A
            # pre-plan Retry may explicitly admit a fresh revision of this target.
            if not reviews:
                conn.execute("UPDATE init_sessions SET target_observation_id = ?, expected_encounter_revision = ? WHERE session_id = ?",
                             (observation_id, expected_revision, session_id))

    def create_init_session(self, source_path: str, *, quality_only: bool = True,
                            target_observation_id: str | None = None,
                            expected_revision: str | None = None) -> InitSession:
        if target_observation_id and (not isinstance(expected_revision, str) or not expected_revision.strip()):
            raise ValueError("Attach Media requires an Event revision")
        session = InitSession(
            session_id=str(uuid.uuid4()),
            source_path=source_path,
            status="pending",
            quality_only=quality_only,
            target_observation_id=target_observation_id,
            expected_encounter_revision=expected_revision,
        )
        with self._connect() as conn:
            if target_observation_id:
                observation = _require_observation(conn, target_observation_id)
                if observation["status"] != "FINALIZED":
                    raise ValueError("Attach Media requires a finalized Event")
            conn.execute(
                """
                INSERT INTO init_sessions(session_id, source_path, status, created_at, quality_only,
                                         target_observation_id, expected_encounter_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session.session_id, session.source_path, session.status, session.created_at, int(quality_only),
                 target_observation_id, expected_revision),
            )
        return session

    def retry_targeted_scan(self, session_id: str) -> InitSession:
        """Retry processing in the same unplanned, targeted staging authority."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute("SELECT * FROM init_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if session is None or not session["target_observation_id"] or session["status"] != "processing_failed":
                raise ValueError("Only a failed targeted scan can be retried")
            if conn.execute("SELECT 1 FROM photo_reviews WHERE session_id = ?", (session_id,)).fetchone():
                raise ValueError("A planned review cannot be rescanned")
            conn.execute("DELETE FROM init_face_person_exclusions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_groups WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_faces WHERE session_id = ?", (session_id,))
            conn.execute("UPDATE init_sessions SET status = 'pending' WHERE session_id = ?", (session_id,))
        return self.get_init_session(session_id)

    def finish_targeted_scan(self, session_id: str, media_paths: list[str]) -> None:
        with self._connect() as conn:
            retained = set(media_paths)
            for row in conn.execute("SELECT media_id, media_path FROM init_session_media WHERE session_id = ?", (session_id,)):
                if row["media_path"] not in retained:
                    conn.execute("DELETE FROM init_session_media WHERE session_id = ? AND media_id = ?", (session_id, row["media_id"]))

    def mark_targeted_scan_failed(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE init_sessions SET status = 'processing_failed' WHERE session_id = ? AND target_observation_id IS NOT NULL", (session_id,))

    def save_init_faces(self, faces: list[InitFace]) -> None:
        if not faces:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO init_faces(
                    init_face_id, session_id, group_id, source_image,
                    box_x, box_y, box_width, box_height, box_confidence,
                    face_quality_score, landmarks, crop_path, vector,
                    quality_status, quality_score, quality_reasons, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        face.init_face_id,
                        face.session_id,
                        face.group_id,
                        face.source_image,
                        face.face.box.x,
                        face.face.box.y,
                        face.face.box.width,
                        face.face.box.height,
                        face.face.box.confidence,
                        face.face.quality_score,
                        json.dumps(face.face.landmarks),
                        face.face.crop_path,
                        _pack_embedding(face.vector),
                        face.quality.status.value,
                        face.quality.score,
                        json.dumps(face.quality.reasons),
                        face.created_at,
                    )
                    for face in faces
                ],
            )

    def save_init_session_media(self, session_id: str, media_paths: list[str]) -> None:
        """Persist every distinct scanned image, including images without a detected face."""
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM init_sessions WHERE session_id = ?", (session_id,)).fetchone() is None:
                raise KeyError(f"Unknown init session: {session_id}")
            for media_path in dict.fromkeys(media_paths):
                normalized_path = str(media_path).strip()
                if not normalized_path:
                    raise ValueError("Queue media path is required")
                media_id = media_content_identity(normalized_path)
                _require_encounter_media_role(conn, media_id)
                conn.execute(
                    "INSERT OR IGNORE INTO init_session_media(session_id, media_id, media_path, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, media_id, normalized_path, utc_now()),
                )

    def list_init_session_media(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM init_sessions WHERE session_id = ?", (session_id,)).fetchone() is None:
                raise KeyError(f"Unknown init session: {session_id}")
            media = []
            for row in conn.execute(
                    "SELECT media_id, media_path, excluded FROM init_session_media "
                    "WHERE session_id = ? ORDER BY created_at, media_id",
                    (session_id,),
                ):
                previous = conn.execute(
                    "SELECT o.observation_id, o.observed_at, o.context FROM observation_media om "
                    "JOIN effective_observations o ON o.observation_id = om.observation_id "
                    "WHERE (om.media_id = ? OR om.media_path = ?) AND o.status = 'FINALIZED' "
                    "ORDER BY o.finalized_at LIMIT 1",
                    (row["media_id"], row["media_path"]),
                ).fetchone()
                context = json.loads(previous["context"] or "{}") if previous else {}
                media.append({
                    "media_id": str(row["media_id"]), "media_path": str(row["media_path"]),
                    "excluded": bool(row["excluded"]),
                    "face_count": conn.execute(
                        "SELECT COUNT(*) FROM init_faces WHERE session_id = ? AND source_image = ?",
                        (session_id, row["media_path"]),
                    ).fetchone()[0],
                    "finalized_encounter": {
                        "observation_id": str(previous["observation_id"]),
                        "observed_at": previous["observed_at"],
                        "occasion": context.get("occasion"),
                        "event_time": _world_event_time(previous["observed_at"], context),
                    } if previous else None,
                })
            return media

    def set_init_media_excluded(self, session_id: str, media_id: str, excluded: bool) -> None:
        """Selection only: never remove managed media or historical authority."""
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM photo_reviews WHERE session_id = ?", (session_id,)).fetchone():
                raise ValueError("Media selection is locked after Event grouping")
            cursor = conn.execute(
                "UPDATE init_session_media SET excluded = ? WHERE session_id = ? AND media_id = ?",
                (int(excluded), session_id, media_id),
            )
            if not cursor.rowcount:
                raise KeyError(f"Unknown queued media: {media_id}")

    def set_init_session_quality_policy(self, session_id: str, quality_only: bool) -> None:
        with self._connect() as conn:
            cursor = conn.execute("UPDATE init_sessions SET quality_only = ? WHERE session_id = ?", (int(quality_only), session_id))
            if not cursor.rowcount:
                raise KeyError(f"Unknown init session: {session_id}")

    def get_init_session(self, session_id: str) -> InitSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, source_path, status, created_at, quality_only,
                       target_observation_id, expected_encounter_revision
                FROM init_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return InitSession(
            session_id=row["session_id"],
            source_path=row["source_path"],
            status=row["status"],
            created_at=row["created_at"],
            quality_only=bool(row["quality_only"]),
            target_observation_id=row["target_observation_id"],
            expected_encounter_revision=row["expected_encounter_revision"],
        )

    def list_init_sessions(self) -> list[InitSession]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, source_path, status, created_at, quality_only,
                       target_observation_id, expected_encounter_revision
                FROM init_sessions
                WHERE status <> 'closed'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            InitSession(
                session_id=row["session_id"],
                source_path=row["source_path"],
                status=row["status"],
                created_at=row["created_at"],
                quality_only=bool(row["quality_only"]),
                target_observation_id=row["target_observation_id"],
                expected_encounter_revision=row["expected_encounter_revision"],
            )
            for row in rows
        ]

    def delete_init_session(self, session_id: str) -> None:
        with self._connect() as conn:
            reviews = conn.execute(
                "SELECT review_id, status FROM photo_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            for review in reviews:
                if review["status"] == "IN_PROGRESS":
                    conn.execute("UPDATE photo_reviews SET status = 'CANCELLED' WHERE review_id = ?", (review["review_id"],))
                    conn.execute(
                        "DELETE FROM encounter_relation_decisions WHERE review_id = ? AND observation_id IS NULL",
                        (review["review_id"],),
                    )
                    _remove_review_staging(conn, str(review["review_id"]))
            conn.execute("DELETE FROM init_face_person_exclusions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_groups WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_faces WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM init_session_media WHERE session_id = ?", (session_id,))
            if reviews:
                conn.execute("UPDATE init_sessions SET status = 'closed' WHERE session_id = ?", (session_id,))
            else:
                conn.execute("DELETE FROM init_sessions WHERE session_id = ?", (session_id,))

    def list_init_groups(self, session_id: str) -> list[InitGroup]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, COALESCE(g.status, 'pending') AS group_status
                FROM init_faces f
                LEFT JOIN init_groups g
                  ON g.session_id = f.session_id AND g.group_id = f.group_id
                WHERE f.session_id = ?
                ORDER BY f.group_id, f.created_at
                """,
                (session_id,),
            ).fetchall()
        groups: dict[str, InitGroup] = {}
        for row in rows:
            group_id = row["group_id"]
            if group_id not in groups:
                groups[group_id] = InitGroup(
                    group_id=group_id,
                    session_id=session_id,
                    status=row["group_status"],
                    faces=[],
                )
            groups[group_id].faces.append(_init_face_from_row(row))
        return list(groups.values())

    def mark_init_group_status(self, session_id: str, group_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO init_groups(session_id, group_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, group_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (session_id, group_id, status, utc_now()),
            )

    def _legacy_confirm_init_faces_atomic(
        self,
        session_id: str,
        group_id: str,
        init_face_ids: list[str],
        operation_id: str,
        *,
        person_id: str | None = None,
        name: str | None = None,
        notes: str = "",
        mentioned_person_ids: list[str] | None = None,
    ) -> dict:
        operation_type = "confirm-init-existing" if person_id else "confirm-init-new"
        creating_new_person = person_id is None
        selected_ids = list(dict.fromkeys(item for item in init_face_ids if item))
        if not selected_ids:
            raise KeyError("Select at least one image")
        with self._connect() as conn:
            existing = _begin_person_operation(conn, operation_id, operation_type)
            if existing:
                return existing
            placeholders = ", ".join("?" for _ in selected_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM init_faces
                WHERE session_id = ? AND group_id = ?
                  AND init_face_id IN ({placeholders})
                ORDER BY created_at
                """,
                (session_id, group_id, *selected_ids),
            ).fetchall()
            if len(rows) != len(selected_ids):
                raise KeyError("One or more selected images are no longer in this group")
            status_row = conn.execute(
                "SELECT status FROM init_groups WHERE session_id = ? AND group_id = ?",
                (session_id, group_id),
            ).fetchone()
            if status_row is not None and status_row["status"] != "pending":
                raise KeyError(f"Queue group is not pending: {group_id}")
            if person_id:
                person_row = conn.execute(
                    "SELECT 1 FROM persons WHERE person_id = ? AND deleted_at IS NULL",
                    (person_id,),
                ).fetchone()
                if person_row is None:
                    raise KeyError(f"Unknown person: {person_id}")
            else:
                if not name or not name.strip():
                    raise KeyError("Person name is required")
                person_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO persons(person_id, name, metadata, created_at, notes) VALUES (?, ?, '{}', ?, ?)",
                    (person_id, name.strip(), utc_now(), notes.strip()),
                )
                automatic_associations = _legacy_create_note_associations(
                    conn, person_id, notes.strip(), "SentriFace", mentioned_person_ids or [],
                )
            if not creating_new_person:
                automatic_associations = []
            existing_embeddings = conn.execute(
                """
                SELECT embedding_id, vector FROM embeddings
                WHERE person_id = ? AND deleted_at IS NULL
                ORDER BY created_at
                """,
                (person_id,),
            ).fetchall()
            known = [
                (row["embedding_id"], _unpack_embedding(row["vector"]))
                for row in existing_embeddings
            ]
            accepted: list[dict] = []
            for row in rows:
                vector = _unpack_embedding(row["vector"])
                duplicate_id = next(
                    (
                        embedding_id
                        for embedding_id, known_vector in known
                        if sum(a * b for a, b in zip(vector, known_vector)) >= 0.9999
                    ),
                    None,
                )
                if duplicate_id:
                    embedding_id = duplicate_id
                    duplicate = True
                else:
                    embedding_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO embeddings(
                            embedding_id, person_id, vector, quality_score,
                            source_image, crop_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            embedding_id,
                            person_id,
                            row["vector"],
                            row["quality_score"],
                            row["source_image"],
                            row["crop_path"],
                            utc_now(),
                        ),
                    )
                    known.append((embedding_id, vector))
                    duplicate = False
                accepted.append(
                    {
                        "face_id": row["init_face_id"],
                        "embedding_id": embedding_id,
                        "image_id": Path(row["source_image"]).name,
                        "image_path": row["source_image"],
                        "duplicate": duplicate,
                    }
                )
            _mark_person_enrolled(conn, person_id)
            conn.execute(
                f"DELETE FROM init_faces WHERE init_face_id IN ({placeholders})",
                selected_ids,
            )
            remaining = conn.execute(
                "SELECT init_face_id FROM init_faces WHERE session_id = ? AND group_id = ?",
                (session_id, group_id),
            ).fetchall()
            if remaining:
                now = utc_now()
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO init_face_person_exclusions(
                        session_id, init_face_id, person_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [(session_id, row["init_face_id"], person_id, now) for row in remaining],
                )
            status = "pending" if remaining else "confirmed"
            conn.execute(
                """
                INSERT INTO init_groups(session_id, group_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, group_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (session_id, group_id, status, utc_now()),
            )
            result = {
                "person_id": person_id,
                "person_ids": [person_id, *[item.target_person_id if item.source_person_id == person_id else item.source_person_id for item in automatic_associations]],
                "accepted": accepted,
                "automatic_association_ids": [item.association_id for item in automatic_associations],
            }
            _record_person_operation(conn, operation_id, operation_type, result)
            return result
    def delete_init_faces(self, init_face_ids: list[str]) -> None:
        if not init_face_ids:
            return
        with self._connect() as conn:
            conn.executemany("DELETE FROM init_faces WHERE init_face_id = ?", [(face_id,) for face_id in init_face_ids])

    def update_init_face_groups(self, assignments: dict[str, str]) -> None:
        if not assignments:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE init_faces SET group_id = ? WHERE init_face_id = ?",
                [(group_id, face_id) for face_id, group_id in assignments.items()],
            )

    def add_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
        person_id: str,
    ) -> None:
        if not init_face_ids:
            return
        now = utc_now()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO init_face_person_exclusions(session_id, init_face_id, person_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(session_id, face_id, person_id, now) for face_id in init_face_ids],
            )

    def list_init_face_person_exclusions(
        self,
        session_id: str,
        init_face_ids: list[str],
    ) -> dict[str, set[str]]:
        if not init_face_ids:
            return {}
        placeholders = ", ".join("?" for _ in init_face_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT init_face_id, person_id
                FROM init_face_person_exclusions
                WHERE session_id = ? AND init_face_id IN ({placeholders})
                """,
                (session_id, *init_face_ids),
            ).fetchall()
            exclusions: dict[str, set[str]] = {}
            for row in rows:
                exclusions.setdefault(row["init_face_id"], set()).add(
                    _resolve_canonical_person_id(conn, row["person_id"]),
                )
            return exclusions

    @contextmanager
    def _connect(self):
        conn = connect_database(self.db_path, self.database_key, timeout=30, row_factory=True)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _migrate_26_to_27(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE graph_state (
            singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
            revision INTEGER NOT NULL CHECK(revision >= 1),
            updated_at TEXT NOT NULL
        );
        INSERT INTO graph_state(singleton_id, revision, updated_at)
        VALUES (1, 1, CURRENT_TIMESTAMP);

        CREATE INDEX idx_relationship_evidence_active_endpoints_time
        ON relationship_evidence(active, source_person_id, target_person_id, created_at);
        CREATE INDEX idx_observations_finalized_time_location
        ON observations(status, observed_at, location);

        CREATE TRIGGER graph_revision_person_insert
        AFTER INSERT ON persons
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;
        CREATE TRIGGER graph_revision_person_read_fields
        AFTER UPDATE OF name, metadata, lifecycle_status, canonical_person_id,
                        identity_status, biometric_status ON persons
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;

        PRAGMA user_version = 27;
        """,
    )
    # v27 introduced graph_state. Normalize a drifting pre-P11 projection once
    # inside the schema-upgrade transaction; do not churn an already-equal graph.
    expected, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError(
            "Relationship evidence validation failed: " + "; ".join(errors)
        )
    actual_rows = conn.execute("SELECT * FROM graph_connections").fetchall()
    if (
        {_graph_connection_signature(item) for item in expected}
        != {_graph_connection_row_signature(item) for item in actual_rows}
    ):
        _write_graph_projection(conn, expected)
        _advance_graph_revision(conn)


def _migrate_33_to_34(conn: sqlite3.Connection) -> None:
    """Reference source authority extends immutable enrollment provenance."""
    _execute_migration_script(conn, """
        ALTER TABLE biometric_enrollment_history ADD COLUMN source_media_id TEXT;
        ALTER TABLE biometric_enrollment_history ADD COLUMN source_image TEXT;
        ALTER TABLE biometric_enrollment_history ADD COLUMN crop_path TEXT;
        ALTER TABLE biometric_enrollment_history ADD COLUMN recognition_state TEXT
            CHECK(recognition_state IN ('GOOD','POOR_ACCEPTED','PROOF_ONLY'));
        ALTER TABLE biometric_enrollment_history ADD COLUMN no_context_declared INTEGER NOT NULL DEFAULT 0
            CHECK(no_context_declared IN (0,1));
        DROP TRIGGER biometric_enrollment_history_no_update;
        UPDATE biometric_enrollment_history SET
            source_image = COALESCE((SELECT media_path FROM photo_reviews r WHERE r.review_id = biometric_enrollment_history.review_id),
                (SELECT source_image FROM embeddings e WHERE e.embedding_id = biometric_enrollment_history.embedding_id)),
            crop_path = (SELECT crop_path FROM embeddings e WHERE e.embedding_id = biometric_enrollment_history.embedding_id),
            recognition_state = (SELECT recognition_state FROM embeddings e WHERE e.embedding_id = biometric_enrollment_history.embedding_id);
        CREATE TABLE recognition_reference_revisions (
            revision_id TEXT PRIMARY KEY,
            enrollment_id TEXT NOT NULL REFERENCES biometric_enrollment_history(enrollment_id) ON DELETE RESTRICT,
            active INTEGER NOT NULL CHECK(active IN (0,1)),
            operation_id TEXT NOT NULL REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            UNIQUE(enrollment_id, operation_id)
        );
        CREATE INDEX reference_revision_source ON recognition_reference_revisions(enrollment_id, created_at);
        CREATE TRIGGER reference_revision_no_update BEFORE UPDATE ON recognition_reference_revisions
            BEGIN SELECT RAISE(ABORT, 'Reference lifecycle revisions are immutable'); END;
        CREATE TRIGGER reference_revision_no_delete BEFORE DELETE ON recognition_reference_revisions
            BEGIN SELECT RAISE(ABORT, 'Reference lifecycle history cannot be deleted'); END;
    """)
    for row in conn.execute("SELECT enrollment_id, source_image FROM biometric_enrollment_history").fetchall():
        if row["source_image"]:
            conn.execute("UPDATE biometric_enrollment_history SET source_media_id = ? WHERE enrollment_id = ?",
                         (media_content_identity(row["source_image"]), row["enrollment_id"]))
    _execute_migration_script(conn, """
        CREATE TRIGGER biometric_enrollment_history_no_update BEFORE UPDATE ON biometric_enrollment_history
            BEGIN SELECT RAISE(ABORT, 'Enrollment history is immutable'); END;
        PRAGMA user_version = 34;
    """)


def _migrate_35_to_36(conn: sqlite3.Connection) -> None:
    """Accounts whose password an administrator set must choose their own at sign-in."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(app_users)").fetchall()}
    _execute_migration_script(conn, ("" if not columns or "must_change_password" in columns else
        "ALTER TABLE app_users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0\n"
        "    CHECK(must_change_password IN (0,1));\n") + "PRAGMA user_version = 36;")


def _migrate_36_to_37(conn: sqlite3.Connection) -> None:
    """Give existing Person tombstones a fresh recovery window."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    if "restore_until" not in columns:
        conn.execute("ALTER TABLE persons ADD COLUMN restore_until TEXT")
    restore_until = (datetime.fromisoformat(utc_now()) + timedelta(days=DELETED_PERSON_RECOVERY_DAYS)).isoformat()
    conn.execute(
        "UPDATE persons SET restore_until = ? WHERE lifecycle_status = 'DELETED' AND restore_until IS NULL",
        (restore_until,),
    )
    conn.execute("PRAGMA user_version = 37")


def _migrate_34_to_35(conn: sqlite3.Connection) -> None:
    """Erased faces become retained stubs so Event and correction history stay valid."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
    _execute_migration_script(conn, ("" if "erased_at" in columns else
        "ALTER TABLE embeddings ADD COLUMN erased_at TEXT;\n") + "PRAGMA user_version = 35;")
    _refresh_source_biometric_status(conn)
    # Physical relocation is not an Encounter change. Translate only still-valid
    # legacy draft fingerprints; genuinely stale preconditions remain stale.
    for row in conn.execute("SELECT observation_id FROM observations WHERE status='FINALIZED'").fetchall():
        oid = row[0]
        previous = _encounter_revision(conn, oid, include_media_locations=True)
        current = _encounter_revision(conn, oid)
        conn.execute("UPDATE init_sessions SET expected_encounter_revision=? WHERE target_observation_id=? AND expected_encounter_revision=?",
                     (current, oid, previous))
        conn.execute("UPDATE photo_reviews SET expected_encounter_revision=? WHERE target_observation_id=? AND status='IN_PROGRESS' AND expected_encounter_revision=?",
                     (current, oid, previous))


def _erase_deleted_face_in_transaction(conn: sqlite3.Connection, row: sqlite3.Row, erased_at: str) -> bool:
    """Erase one deleted face; return True when a "face removed" stub is kept.

    Event face lists and correction history reference faces with ON DELETE
    RESTRICT. Such faces keep only their ID and owner; the biometric vector,
    face crop and legacy sightings are removed. An Event photo stays because
    the Event still uses it.
    """
    embedding_id = row["embedding_id"]
    conn.execute("DELETE FROM recognition_details WHERE embedding_id = ?", (embedding_id,))
    referenced = conn.execute(
        """
        SELECT 1 FROM observation_face_assignments WHERE embedding_id = ?
        UNION ALL SELECT 1 FROM identity_corrections WHERE embedding_id = ?
        LIMIT 1
        """,
        (embedding_id, embedding_id),
    ).fetchone() is not None
    if not referenced:
        conn.execute("DELETE FROM embeddings WHERE embedding_id = ?", (embedding_id,))
        return False
    source_image = row["source_image"]
    if source_image and conn.execute(
        """
        SELECT 1 FROM observation_media WHERE media_path = ?
        UNION ALL SELECT 1 FROM photo_reviews WHERE media_path = ?
        UNION ALL SELECT 1 FROM photo_review_media WHERE media_path = ?
        LIMIT 1
        """,
        (source_image, source_image, source_image),
    ).fetchone() is None:
        source_image = None
    conn.execute(
        """
        UPDATE embeddings
        SET vector = X'', quality_score = 0, crop_path = NULL, source_image = ?,
            purge_after = NULL, erased_at = ?
        WHERE embedding_id = ? AND erased_at IS NULL
        """,
        (source_image, erased_at, embedding_id),
    )
    return True


def _schema_migrations() -> tuple[SchemaMigration, ...]:
    """Return the ordered migration registry.

    Future schema work adds one `_migrate_N_to_N_plus_1` function and one entry
    here, then increments `SCHEMA_VERSION`. Resolving the functions on each call
    keeps migration failure tests and recovery tooling able to patch a step.
    """
    return (
        SchemaMigration(0, 1, _migrate_0_to_1),
        SchemaMigration(1, 2, _migrate_1_to_2),
        SchemaMigration(2, 3, _migrate_2_to_3),
        SchemaMigration(3, 4, _migrate_3_to_4),
        SchemaMigration(4, 5, _migrate_4_to_5),
        SchemaMigration(5, 6, _migrate_5_to_6),
        SchemaMigration(6, 7, _migrate_6_to_7),
        SchemaMigration(7, 8, _migrate_7_to_8),
        SchemaMigration(8, 9, _migrate_8_to_9),
        SchemaMigration(9, 10, _migrate_9_to_10),
        SchemaMigration(10, 11, _migrate_10_to_11),
        SchemaMigration(11, 12, _migrate_11_to_12),
        SchemaMigration(12, 13, _migrate_12_to_13),
        SchemaMigration(13, 14, _migrate_13_to_14),
        SchemaMigration(14, 15, _migrate_14_to_15),
        SchemaMigration(15, 16, _migrate_15_to_16),
        SchemaMigration(16, 17, _migrate_16_to_17),
        SchemaMigration(17, 18, _migrate_17_to_18),
        SchemaMigration(18, 19, _migrate_18_to_19),
        SchemaMigration(19, 20, _migrate_19_to_20),
        SchemaMigration(20, 21, _migrate_20_to_21),
        SchemaMigration(21, 22, _migrate_21_to_22),
        SchemaMigration(22, 23, _migrate_22_to_23),
        SchemaMigration(23, 24, _migrate_23_to_24),
        SchemaMigration(24, 25, _migrate_24_to_25),
        SchemaMigration(25, 26, _migrate_25_to_26),
        SchemaMigration(26, 27, _migrate_26_to_27),
        SchemaMigration(27, 28, _migrate_27_to_28),
        SchemaMigration(28, 29, _migrate_28_to_29),
        SchemaMigration(29, 30, _migrate_29_to_30),
        SchemaMigration(30, 31, _migrate_30_to_31),
        SchemaMigration(31, 32, _migrate_31_to_32),
        SchemaMigration(32, 33, _migrate_32_to_33),
        SchemaMigration(33, 34, _migrate_33_to_34),
        SchemaMigration(34, 35, _migrate_34_to_35),
        SchemaMigration(35, 36, _migrate_35_to_36),
        SchemaMigration(36, 37, _migrate_36_to_37),
    )


def _validated_migration_registry() -> tuple[SchemaMigration, ...]:
    migrations = _schema_migrations()
    expected_version = 0
    for migration in migrations:
        if migration.from_version != expected_version or migration.to_version != expected_version + 1:
            raise SchemaMigrationError(
                "Invalid schema migration registry: expected "
                f"v{expected_version} to v{expected_version + 1}, found "
                f"v{migration.from_version} to v{migration.to_version}."
            )
        expected_version = migration.to_version
    if expected_version != SCHEMA_VERSION:
        raise SchemaMigrationError(
            "Invalid schema migration registry: "
            f"ends at v{expected_version}, expected v{SCHEMA_VERSION}."
        )
    return migrations


def migrate_staged_database(
    database_path: Path,
    *,
    database_key: bytes | None = None,
) -> tuple[int, int]:
    """Migrate and validate a disposable restore candidate in place.

    The caller owns the staged copy and its safety boundary. Unlike normal
    startup this deliberately creates no pre-migration backup and never opens
    or mutates the live configured database.
    """
    with closing(connect_database(database_path, database_key, row_factory=True)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        source_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        _require_supported_schema_version(source_version)
        _apply_schema_migrations(
            conn, source_version, allow_graph_projection_drift=True,
        )
        final_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if final_version == SCHEMA_VERSION and source_version == final_version:
            conn.execute("BEGIN IMMEDIATE")
            try:
                _validate_current_domain_state(
                    conn, allow_graph_projection_drift=True,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return source_version, final_version


def _apply_schema_migrations(
    conn: sqlite3.Connection,
    current_version: int,
    *,
    allow_graph_projection_drift: bool = False,
) -> None:
    migrations = _validated_migration_registry()
    if current_version == SCHEMA_VERSION:
        return
    migrations_by_version = {migration.from_version: migration for migration in migrations}
    if current_version not in migrations_by_version:
        raise SchemaMigrationError(f"Unsupported database schema version: {current_version}")

    conn.execute("BEGIN IMMEDIATE")
    version = current_version
    try:
        while version < SCHEMA_VERSION:
            migration = migrations_by_version.get(version)
            if migration is None:
                raise SchemaMigrationError(
                    f"No migration is registered from database schema v{version}."
                )
            try:
                migration.apply(conn)
            except Exception as exc:
                raise SchemaMigrationError(
                    f"Database migration v{migration.from_version} to "
                    f"v{migration.to_version} failed: {exc}"
                ) from exc
            migrated_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if migrated_version != migration.to_version:
                raise SchemaMigrationError(
                    f"Database migration v{migration.from_version} to "
                    f"v{migration.to_version} reported schema v{migrated_version}."
                )
            version = migrated_version
        _validate_current_domain_state(
            conn,
            allow_graph_projection_drift=allow_graph_projection_drift,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _validate_current_domain_state(
    conn: sqlite3.Connection,
    *,
    allow_graph_projection_drift: bool = False,
) -> None:
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    authoritative_foreign_key_errors = [
        row for row in foreign_key_errors if str(row[0]) != "graph_connections"
    ]
    if authoritative_foreign_key_errors:
        raise SchemaMigrationError(
            "Database domain validation failed: dangling foreign-key references"
        )
    attachment_errors = _attachment_ownership_errors(conn)
    if attachment_errors:
        raise SchemaMigrationError("Invalid Attach Media ownership: " + "; ".join(attachment_errors))
    reference_errors = _reference_integrity_errors(conn)
    if reference_errors:
        raise SchemaMigrationError("Invalid Reference source authority: " + "; ".join(reference_errors))

    lifecycle_errors: list[str] = []
    people = conn.execute(
        """
        SELECT person_id, lifecycle_status, canonical_person_id, deleted_at,
               identity_status, biometric_status, name, notes, metadata
        FROM persons ORDER BY person_id
        """
    ).fetchall()
    for person in people:
        person_id = str(person["person_id"])
        lifecycle_status = str(person["lifecycle_status"])
        canonical_person_id = person["canonical_person_id"]
        if lifecycle_status not in PERSON_LIFECYCLE_STATUSES:
            lifecycle_errors.append(f"Person {person_id} has invalid lifecycle {lifecycle_status}")
            continue
        if lifecycle_status == "ACTIVE" and person["deleted_at"] is not None:
            lifecycle_errors.append(f"Active person {person_id} has a deletion timestamp")
        if lifecycle_status != "ACTIVE" and person["deleted_at"] is None:
            lifecycle_errors.append(f"Historical person {person_id} lacks a lifecycle timestamp")
        if lifecycle_status == "MERGED" and canonical_person_id is None:
            lifecycle_errors.append(f"Merged person {person_id} has no canonical identity")
        if lifecycle_status != "MERGED" and canonical_person_id is not None:
            lifecycle_errors.append(f"Non-merged person {person_id} has a canonical mapping")
        if canonical_person_id is not None:
            try:
                _resolve_canonical_person_id(conn, person_id)
            except (KeyError, RuntimeError, ValueError) as exc:
                lifecycle_errors.append(f"Person {person_id} has invalid canonical mapping: {exc}")
        try:
            metadata = json.loads(person["metadata"] or "{}")
        except (TypeError, json.JSONDecodeError):
            lifecycle_errors.append(f"Person {person_id} has invalid metadata")
            metadata = {"invalid": True}
        if (
            person["identity_status"] == "UNIDENTIFIED"
            and person["biometric_status"] == "NO_FACE"
            and not str(person["name"] or "").strip()
            and not str(person["notes"] or "").strip()
            and not metadata
        ):
            lifecycle_errors.append(f"Person {person_id} is unidentified with no face or context")
    if lifecycle_errors:
        raise SchemaMigrationError(
            "Database domain validation failed: " + "; ".join(lifecycle_errors)
        )

    _, evidence_errors, _ = _expected_graph_connections(conn)
    if evidence_errors:
        raise SchemaMigrationError(
            "Database relationship evidence validation failed: "
            + "; ".join(evidence_errors)
        )
    validation = _validate_graph_projection(conn)
    if not validation["valid"] and not allow_graph_projection_drift:
        raise SchemaMigrationError(
            "Database graph projection validation failed; run the explicit P11-B "
            "graph projection rebuild after reviewing integrity findings: "
            + "; ".join(validation["errors"])
        )


def _review_relation_candidates(conn: sqlite3.Connection, review_id: str) -> list[dict]:
    faces = conn.execute(
        "SELECT * FROM photo_review_faces WHERE review_id = ? ORDER BY face_id", (review_id,),
    ).fetchall()
    media_by_ref: dict[str, set[str]] = {}
    name_by_ref: dict[str, str] = {}
    for face in faces:
        identity_ref = _review_identity_ref(conn, face)
        if identity_ref is None:
            continue
        staged = _staged_review_face_row(conn, face["staged_face_type"], face["staged_face_id"])
        media_by_ref.setdefault(identity_ref, set()).add(str(staged["source_image"]))
        if identity_ref.startswith("draft:"):
            name_by_ref[identity_ref] = str(face["new_person_name"] or "New Person")
        else:
            person = conn.execute("SELECT name FROM persons WHERE person_id = ?", (identity_ref[7:],)).fetchone()
            name_by_ref[identity_ref] = str(person["name"]) if person else "Historical Person"
    review = conn.execute("SELECT target_observation_id FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
    settled_pairs = set()
    if review and review["target_observation_id"]:
        target = str(review["target_observation_id"])
        for pid in _effective_observation_person_ids(conn, target):
            ref = f"person:{pid}"
            media_by_ref.setdefault(ref, set()).update(_encounter_person_media(conn, target, pid))
            name_by_ref[ref] = str(conn.execute("SELECT name FROM persons WHERE person_id = ?", (pid,)).fetchone()[0])
        settled_pairs = {tuple(f"person:{pid}" for pid in pair) for pair in _effective_encounter_relations(conn, target)}
        if not conn.execute("SELECT 1 FROM encounter_relation_decisions WHERE observation_id = ?", (target,)).fetchone():
            original = _effective_observation_person_ids(conn, target)
            settled_pairs = {(f"person:{a}", f"person:{b}") for index, a in enumerate(original) for b in original[index+1:]}
    refs = sorted(media_by_ref)
    return [
        {
            "first_ref": first_ref, "second_ref": second_ref,
            "first_name": name_by_ref[first_ref], "second_name": name_by_ref[second_ref],
            "support": _media_pair_support(media_by_ref[first_ref], media_by_ref[second_ref]),
        }
        for index, first_ref in enumerate(refs)
        for second_ref in refs[index + 1:]
        if (first_ref, second_ref) not in settled_pairs
    ]


def _encounter_review_read(conn: sqlite3.Connection, review_id: str) -> dict:
    row = conn.execute("SELECT * FROM photo_reviews WHERE review_id = ?", (review_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown Event review: {review_id}")
    media = [
        {"media_id": str(item["media_id"]), "media_path": str(item["media_path"])}
        for item in conn.execute(
            "SELECT media_id, media_path FROM photo_review_media WHERE review_id = ? ORDER BY ordinal, media_id",
            (review_id,),
        )
    ]
    faces = [
        {
            "face_id": str(item["face_id"]), "group_id": str(item["group_id"] or item["face_id"]),
            "source_image": str(item["source_image"]) if item["source_image"] else None,
            "decision": None if row["review_phase"] != "LEGACY" and item["decision"] == "SKIP" else item["decision"],
            "person_id": item["person_id"], "new_person_key": item["new_person_key"],
            "new_person_name": item["new_person_name"],
            "new_person_metadata": json.loads(item["new_person_metadata"] or "{}"),
            "notes": str(item["notes"] or ""),
            "mentioned_person_ids": json.loads(item["mentioned_person_ids"] or "[]"),
            "recognition_detail": json.loads(item["recognition_detail"] or "{}"),
            "quality_status": item["quality_status"],
            "face_erased": item["face_erased_at"] is not None,
        }
        for item in conn.execute(
            "SELECT f.*, i.group_id, COALESCE(i.source_image, e.source_image) AS source_image, "
            "i.quality_status, e.erased_at AS face_erased_at "
            "FROM photo_review_faces f LEFT JOIN init_faces i "
            "ON f.staged_face_type = 'INIT_FACE' AND i.init_face_id = f.staged_face_id "
            "LEFT JOIN observation_face_assignments a ON a.review_id = f.review_id AND a.face_id = f.face_id "
            "LEFT JOIN embeddings e ON e.embedding_id = a.embedding_id "
            "WHERE f.review_id = ? ORDER BY f.face_id",
            (review_id,),
        )
    ]
    relations = [dict(item) for item in conn.execute(
        "SELECT first_ref, second_ref, disposition, support FROM encounter_relation_decisions "
        "WHERE review_id = ? AND active = 1 ORDER BY first_ref, second_ref",
        (review_id,),
    )]
    return {
        "review_id": review_id, "session_id": row["session_id"], "sequence_number": row["sequence_number"],
        "status": str(row["status"]), "phase": str(row["review_phase"]),
        "observation_id": row["observation_id"],
        "target_observation_id": row["target_observation_id"],
        "event_details_complete": bool(row["event_details_complete"]),
        "event_details": json.loads(row["event_details"] or "{}"),
        "media": media, "faces": faces,
        "identity_resolved": sum(face["decision"] is not None for face in faces),
        "identity_total": len(faces),
        "relation_candidates": _review_relation_candidates(conn, review_id)
            if row["status"] == "IN_PROGRESS" and row["review_phase"] == "RELATIONS" else [],
        "relations": relations,
    }


def _list_init_session_encounter_reviews(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    reviews = conn.execute(
        "SELECT review_id FROM photo_reviews WHERE session_id = ? ORDER BY sequence_number",
        (session_id,),
    ).fetchall()
    return [_encounter_review_read(conn, str(item["review_id"])) for item in reviews]


def _replace_graph_projection(conn: sqlite3.Connection) -> None:
    connections, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError("Relationship evidence validation failed: " + "; ".join(errors))
    _write_graph_projection(conn, connections)
    _advance_graph_revision(conn)


def _write_graph_projection(
    conn: sqlite3.Connection, connections: list[GraphConnection],
) -> None:
    conn.execute("DELETE FROM graph_connections")
    _insert_graph_projection_rows(conn, connections)


def _world_graph_v2_read(
    conn: sqlite3.Connection, request: WorldGraphRequest,
) -> WorldGraphV2ReadModel:
    owns_snapshot = not conn.in_transaction
    if owns_snapshot:
        # The revision read is the first read in this deferred transaction. WAL
        # then keeps every later SELECT on the same snapshot while writers remain
        # free to commit on their own connections.
        conn.execute("BEGIN")
    try:
        result = _world_graph_v2_read_snapshot(conn, request)
    except Exception:
        if owns_snapshot:
            conn.rollback()
        raise
    if owns_snapshot:
        conn.commit()
    return result


def _world_graph_v2_read_snapshot(
    conn: sqlite3.Connection, request: WorldGraphRequest,
) -> WorldGraphV2ReadModel:
    # Request-local, bounded memoization: repeated evidence/participant joins and
    # subsequent collection queries reuse parsed instants without retaining a DB cache.
    instant = lru_cache(maxsize=4096)(_world_stored_datetime)
    @lru_cache(maxsize=4096)
    def time_key(value):
        dt = instant(value)
        if dt is None:
            return None
        return ((dt.toordinal() * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second)
                * 1000000 + dt.microsecond)
    conn.create_function("world_time", 1, time_key, deterministic=True)
    # NULL instants fail date predicates and sort after known instants in DESC
    # pages. Extrema ignore unknowns while retaining raw source strings.
    conn.create_function("world_occurrence", 1, lambda value: value if instant(value) is not None else None, deterministic=True)
    def compare_instants(first, second):
        first_key, second_key = time_key(first), time_key(second)
        # Exact keys are positive ordinal microseconds. Unknowns compare equal
        # here; paginated collections use their stable source ID as the tie-break.
        first_key = first_key if first_key is not None else -1
        second_key = second_key if second_key is not None else -1
        return (first_key > second_key) - (first_key < second_key)
    conn.create_collation("world_instant", compare_instants)
    revision = _graph_revision_token(conn)
    if request.revision is not None and request.revision != revision:
        raise ValueError("World revision is stale; request a new snapshot")
    cursor_as_of = _world_cursor_as_of(request.cursor)
    if request.as_of and cursor_as_of and _world_datetime(request.as_of, "as_of") != _world_datetime(cursor_as_of, "cursor as_of"):
        raise ValueError("World cursor does not match the requested as_of")
    as_of_dt = _world_datetime(request.as_of or cursor_as_of or utc_now(), "as_of")
    as_of = as_of_dt.isoformat()
    view = str(request.view).strip().upper()
    if view not in {"CURRENT", "EXPLORE"}:
        raise ValueError("Unsupported World view")
    filter_intent = request.filters
    if view == "EXPLORE":
        if not filter_intent.evidence_type:
            raise ValueError("Explore requires at least one evidence type")
        if filter_intent.min_relationship_strength is None:
            filter_intent = replace(filter_intent, min_relationship_strength=2)
    filters = _normalize_world_filters(filter_intent, as_of_dt)
    if view == "EXPLORE" and not filters.evidence_type:
        raise ValueError("Explore requires at least one evidence type")
    if type(request.include_below_threshold) is not bool:
        raise ValueError("World include_below_threshold must be a boolean")
    if type(request.discovery_period_days) is not int or request.discovery_period_days not in {7, 30, 90}:
        raise ValueError("World discovery period must be 7, 30 or 90 days")
    limits = _normalize_world_limits(request.limits)
    level = WorldDetailLevel(request.detail_level)
    focus_type, focus_id = _normalize_world_focus(level, request.focus_type, request.focus_id)
    ranking = str(request.ranking or "SALIENCE").strip().upper()
    if ranking not in {"SALIENCE", "RECENT_ACTIVITY", "EVIDENCE_COUNT", "DISPLAY_NAME"}:
        raise ValueError(f"Unsupported World ranking intent: {ranking}")
    if ranking == "RECENT_ACTIVITY" and not (filters.recent_activity or filters.date_from or filters.date_to):
        raise ValueError("RECENT_ACTIVITY ranking requires an explicit recent or date scope")
    collection = _normalize_world_collection(level, request.collection)
    scope_fingerprint = _world_scope_fingerprint(filters, ranking, limits)
    scope_fingerprint = hashlib.sha256(json.dumps([
        scope_fingerprint, view, request.include_below_threshold,
        request.discovery_period_days, _world_location_text(request.location_query),
    ]).encode()).hexdigest()[:24]
    offset = _world_decode_cursor(
        request.cursor, revision, level, focus_type, focus_id, collection,
        as_of, scope_fingerprint,
    )
    context = _WorldReadContext(
        request=request, revision=revision, as_of=as_of, filters=filters,
        limits=limits, level=level, focus_type=focus_type, focus_id=focus_id,
        collection=collection, ranking=ranking, scope_fingerprint=scope_fingerprint,
        offset=offset,
    )
    return {
        WorldDetailLevel.WORLD_SCOPE: _world_scope_read,
        WorldDetailLevel.CLUSTER: _world_cluster_read,
        WorldDetailLevel.PERSON: _world_person_read,
        WorldDetailLevel.EVENT: _world_event_read,
        WorldDetailLevel.EVIDENCE: _world_evidence_read,
    }[level](conn, context)


def _world_scope_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    if context.collection == WorldCollection.LOCATION_FACETS:
        return _world_location_facets_read(conn, context)
    if context.collection == WorldCollection.LOCATION_SUGGESTIONS:
        return _world_location_suggestions_read(conn, context)
    if context.collection in {
        WorldCollection.MOST_FREQUENTLY_SEEN, WorldCollection.MOST_RECENTLY_SEEN,
        WorldCollection.MULTIPLE_LOCATIONS,
    }:
        return _world_discoveries_read(conn, context)
    facet_offset = context.offset if context.collection == WorldCollection.LOCATION_FACETS else 0
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        include_below_threshold=context.request.include_below_threshold,
    )
    statistics = _world_event_statistics(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        location_offset=facet_offset, location_limit=context.limits.facets,
    )
    activity = statistics["activity"]
    if _world_has_event_scope(context.filters):
        related = {
            value for item in relationships
            for value in (item["source_person_id"], item["target_person_id"])
        }
        people_rows = {
            person_id: row for person_id, row in people_rows.items()
            if activity.get(person_id, 0) > 0 or person_id in related
        }
        relationships = [
            item for item in relationships
            if item["source_person_id"] in people_rows and item["target_person_id"] in people_rows
        ]
    if context.filters.activity:
        allowed = set(context.filters.activity)
        people_rows = {
            person_id: row for person_id, row in people_rows.items()
            if _world_activity_bucket(activity.get(person_id, 0)) in allowed
        }
        relationships = [
            item for item in relationships
            if item["source_person_id"] in people_rows and item["target_person_id"] in people_rows
        ]
        statistics = _world_event_statistics(
            conn, context.filters, set(people_rows), canonical_map=canonical_map,
            location_offset=facet_offset, location_limit=context.limits.facets,
        )
        activity = statistics["activity"]
    degree = _world_degree(people_rows, relationships)
    ordered_ids = _world_rank_people(people_rows, activity, degree, context.ranking)
    clusters_all = _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters), relationships,
        people_rows, activity, min(context.limits.people, 10), context,
    )
    people: tuple[WorldPerson, ...] = ()
    clusters: tuple[WorldCluster, ...] = ()
    relationship_models: tuple[WorldRelationship, ...] = ()
    people_offset = context.offset if context.collection == WorldCollection.PEOPLE else 0
    cluster_offset = context.offset if context.collection == WorldCollection.CLUSTERS else 0
    if context.collection == WorldCollection.PEOPLE:
        page_ids = ordered_ids[people_offset:people_offset + context.limits.people]
        rank_positions = {person_id: index + 1 for index, person_id in enumerate(ordered_ids)}
        people = tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()),
                activity.get(person_id, 0), degree.get(person_id, {}),
                context, rank_position=rank_positions[person_id],
            ) for person_id in page_ids
        )
    if context.collection == WorldCollection.CLUSTERS or (
        context.collection == WorldCollection.PEOPLE and context.offset == 0
    ):
        clusters = tuple(replace(item, member_ids=()) for item in clusters_all[
            cluster_offset:cluster_offset + context.limits.clusters
        ])
    relationship_offset = context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0
    if context.collection == WorldCollection.RELATIONSHIPS:
        relationship_models = _world_relationship_models(
            conn, relationships[relationship_offset:relationship_offset + context.limits.relationships],
            context, canonical_map,
        )
    pagination = {
        WorldCollection.PEOPLE.value: _world_page_state(
            context, WorldCollection.PEOPLE, len(ordered_ids), len(people),
            context.limits.people, offset=people_offset,
        ),
        WorldCollection.CLUSTERS.value: _world_page_state(
            context, WorldCollection.CLUSTERS, len(clusters_all), len(clusters),
            context.limits.clusters, offset=cluster_offset,
        ),
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(relationships),
            len(relationship_models), context.limits.relationships,
            offset=relationship_offset,
        ),
        WorldCollection.LOCATION_FACETS.value: _world_page_state(
            context, WorldCollection.LOCATION_FACETS,
            int(statistics["location_total_count"]),
            len(statistics["locations"]), context.limits.facets,
            offset=facet_offset,
        ),
    }
    eligible_ids = set(people_rows)
    event_count = int(statistics["total"])
    all_patterns = tuple(_world_patterns(
        conn, context.filters, len(people_rows), context.limits.patterns,
        eligible_person_ids=eligible_ids, context=context,
        measured_total=int(statistics["total"]),
        measured_missing=int(statistics["missing"]),
    ))
    patterns = all_patterns if context.offset == 0 else ()
    pattern_total = len(all_patterns)
    facets = _world_facets(
        conn, context.filters, people_rows, relationships, activity, eligible_ids,
        location_facets=statistics["locations"], pattern_count=pattern_total,
    )
    pagination[WorldCollection.PATTERNS.value] = _world_page_state(
        context, WorldCollection.PATTERNS, pattern_total, len(patterns),
        context.limits.patterns,
        offset=(context.offset if context.collection == WorldCollection.PATTERNS else 0),
    )
    return _world_result(
        context,
        scope_totals={
            "people": len(people_rows), "relationships": len(relationships),
            "clusters": len(clusters_all), "finalized_events": event_count,
        },
        pagination=pagination,
        available_facets=facets,
        people=people, clusters=clusters, patterns=patterns,
        relationships=relationship_models,
    )


def _world_discoveries_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    """Bounded discoveries over the same corrected/canonical Encounter presence."""
    sources = _world_participant_sources(conn)
    people, _, canonical_map = _world_people_scope(conn, context.filters)
    if context.filters.activity:
        activity = _world_event_statistics(
            conn, context.filters, set(people), canonical_map=canonical_map,
            location_limit=1,
        )["activity"]
        people = {pid: row for pid, row in people.items()
                  if _world_activity_bucket(activity.get(pid, 0)) in context.filters.activity}
    _world_register_effective_person_function(conn, canonical_map)
    conn.create_function("world_discovery_eligible", 1, lambda pid: int(pid in people), deterministic=True)
    conn.create_function("world_location_text", 1, _world_location_text, deterministic=True)
    conn.create_function("world_location_key", 1, lambda value: _world_location_text(value).casefold(), deterministic=True)
    filters = context.filters
    end = _world_datetime(context.as_of, "as_of")
    period = None if context.collection == WorldCollection.MOST_RECENTLY_SEEN else (
        context.request.discovery_period_days
    )
    start = (end - timedelta(days=period)).isoformat() if period else None
    scoped = replace(
        filters, date_from=max(filter(None, (filters.date_from, start)), default=None),
        date_to=min(filter(None, (filters.date_to, context.as_of))),
    )
    # Normalize once per Encounter before participant joins. Keep location/status
    # predicates ahead of normalization; SQL integer division gives the exact UTC
    # ordinal day, including the final microsecond before midnight.
    event_scope, event_params = _world_scope_sql(
        replace(scoped, date_from=None, date_to=None), evidence=False,
    )
    scope_sql, time_params = _world_scope_sql(
        replace(scoped, locations=(), missing_location="INCLUDE"), evidence=False,
    )
    scope_sql = scope_sql.replace("world_time(COALESCE(o.observed_at, o.created_at))", "o.instant_key")
    params = [*event_params, *(time_params * len(sources))]
    appearances = " UNION ALL ".join(f"""
        SELECT DISTINCT o.observation_id AS event_id,
               world_effective_person(p.observation_id, p.person_id) AS person_id,
               COALESCE(o.observed_at, o.created_at) AS occurred_at,
               o.observed_at AS recorded_at, o.context AS event_context,
               o.instant_key AS time_key,
               o.instant_key / 86400000000 AS day,
               world_location_text(o.location) AS location,
               world_location_key(o.location) AS location_key
        FROM normalized_events o JOIN {source} p USING(observation_id)
        WHERE {scope_sql} AND o.instant_key IS NOT NULL
          AND world_discovery_eligible(world_effective_person(p.observation_id, p.person_id)) = 1
""" for source in sources)
    cte = f"""WITH normalized_events AS MATERIALIZED (
        SELECT o.observation_id, o.observed_at, o.created_at, o.location, o.status, o.context,
               world_time(COALESCE(o.observed_at, o.created_at)) AS instant_key
        FROM effective_observations o WHERE {event_scope}
    ), appearances AS MATERIALIZED ({appearances}
    )"""
    latest_day = None
    if context.collection == WorldCollection.MOST_RECENTLY_SEEN:
        latest_day = conn.execute(f"{cte} SELECT MAX(day) FROM appearances", params).fetchone()[0]
    selection = "day = ?" if context.collection == WorldCollection.MOST_RECENTLY_SEEN else "1 = 1"
    selected_params = [*params, latest_day] if context.collection == WorldCollection.MOST_RECENTLY_SEEN else params
    cte += f", selected AS MATERIALIZED (SELECT * FROM appearances WHERE {selection})"
    multiple = context.collection == WorldCollection.MULTIPLE_LOCATIONS
    measure = "COUNT(DISTINCT NULLIF(location_key, ''))" if multiple else "COUNT(*)"
    having = f"HAVING {measure} >= 2" if multiple else ""
    aggregate = f""", results AS (
        SELECT person_id, {measure} AS value, COUNT(*) AS event_count,
               SUM(CASE WHEN location_key = '' THEN 1 ELSE 0 END) AS missing
        FROM selected GROUP BY person_id {having}
    )"""
    total = int(conn.execute(f"{cte}{aggregate} SELECT COUNT(*) FROM results", selected_params).fetchone()[0])
    rows = conn.execute(
        f"{cte}{aggregate} SELECT * FROM results ORDER BY value DESC, person_id LIMIT ? OFFSET ?",
        [*selected_params, context.limits.people, context.offset],
    ).fetchall()
    ids = [str(row["person_id"]) for row in rows]
    supports: dict[str, list[dict]] = {pid: [] for pid in ids}
    locations: dict[str, list[str]] = {pid: [] for pid in ids}
    location_totals: dict[str, int] = {}
    if ids:
        placeholders = ",".join("?" for _ in ids)
        support_rows = conn.execute(
            f"""{cte}, numbered AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY time_key DESC, event_id) AS position
                FROM selected WHERE person_id IN ({placeholders})
            ) SELECT * FROM numbered WHERE position <= ? ORDER BY person_id, position""",
            [*selected_params, *ids, context.limits.events],
        ).fetchall()
        for row in support_rows:
            supports[str(row["person_id"])].append({
                "event_id": str(row["event_id"]), "occurred_at": str(row["occurred_at"]),
                "location": row["location"] or None,
                "event_time": _world_event_time(row["recorded_at"], row["event_context"]),
            })
        if multiple:
            location_rows = conn.execute(
                f"""{cte}, places AS (
                    SELECT person_id, location_key, MIN(location) AS location FROM selected
                    WHERE person_id IN ({placeholders}) AND location_key <> '' GROUP BY person_id, location_key
                ), numbered AS (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY location_key) AS position,
                           COUNT(*) OVER (PARTITION BY person_id) AS total FROM places
                ) SELECT * FROM numbered WHERE position <= ? ORDER BY person_id, position""",
                [*selected_params, *ids, context.limits.facets],
            ).fetchall()
            for row in location_rows:
                pid = str(row["person_id"])
                locations[pid].append(str(row["location"]))
                location_totals[pid] = int(row["total"])
    discoveries = tuple(WorldDiscovery(
        canonical_person_id=str(row["person_id"]), display_name=str(people[str(row["person_id"])]["name"]),
        discovery_type=context.collection.value, count=int(row["value"]),
        supporting_encounters=tuple(supports[str(row["person_id"])]),
        supporting_encounters_state=_world_bounded_state(
            int(row["event_count"]), len(supports[str(row["person_id"])]), "PERSON_EVENTS_COLLECTION",
        ),
        locations=tuple(locations[str(row["person_id"])]),
        locations_state=_world_bounded_state(
            location_totals.get(str(row["person_id"]), 0), len(locations[str(row["person_id"])]),
            "PERSON_EVENTS_COLLECTION",
        ),
        missing_location_count=int(row["missing"]),
    ) for row in rows)
    return _world_result(
        context, scope_totals={"discoveries": total}, discoveries=discoveries,
        discovery_context={
            "type": context.collection.value, "period_days": period,
            "date_from": scoped.date_from, "date_to": scoped.date_to,
            "latest_observed_day": datetime.fromordinal(int(latest_day)).date().isoformat() if latest_day is not None else None, "calendar_timezone": "UTC",
            "measurement": ("distinct_normalized_known_locations" if multiple
                            else "distinct_finalized_person_encounter_appearances"),
            "cluster_navigation": "PERSON.cluster_memberships_with_same_filters_and_revision",
            "missing_locations": "Excluded from distinct known location counts; reported separately.",
        },
        pagination={context.collection.value: _world_page_state(
            context, context.collection, total, len(discoveries), context.limits.people,
        )},
    )


def _world_location_facets_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    """Read the authoritative location collection without unrelated World models."""
    people_rows, _, canonical_map = _world_people_scope(conn, context.filters)
    eligible_ids = set(people_rows)
    if context.filters.activity:
        statistics = _world_event_statistics(
            conn, context.filters, eligible_ids, canonical_map=canonical_map,
            location_offset=context.offset, location_limit=context.limits.facets,
        )
        allowed = set(context.filters.activity)
        activity = statistics["activity"]
        eligible_ids = {
            person_id for person_id in eligible_ids
            if _world_activity_bucket(activity.get(person_id, 0)) in allowed
        }
        statistics = _world_event_statistics(
            conn, context.filters, eligible_ids, canonical_map=canonical_map,
            location_offset=context.offset, location_limit=context.limits.facets,
        )
    else:
        statistics = _world_location_facet_statistics(
            conn, context.filters, eligible_ids, canonical_map,
            context.offset, context.limits.facets,
        )
    pagination = {
        WorldCollection.LOCATION_FACETS.value: _world_page_state(
            context, WorldCollection.LOCATION_FACETS,
            int(statistics["location_total_count"]), len(statistics["locations"]),
            context.limits.facets, offset=context.offset,
        ),
    }
    return _world_result(
        context,
        scope_totals={"finalized_events": int(statistics["total"])},
        pagination=pagination,
        available_facets={"locations": statistics["locations"]},
    )


def _world_location_facet_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    canonical_map: dict[str, str],
    offset: int,
    limit: int,
) -> dict[str, object]:
    """Page event-based locations without calculating unrelated activity models."""
    if not eligible_ids:
        return {"locations": [], "location_total_count": 0, "total": 0}
    if eligible_ids != set(canonical_map.values()):
        return _world_event_statistics(
            conn, filters, eligible_ids, canonical_map=canonical_map,
            location_offset=offset, location_limit=limit,
        )
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    rows = conn.execute(
        f"""WITH scoped_events AS (
                SELECT LOWER(TRIM(COALESCE(o.location, ''))) AS location_key,
                       TRIM(COALESCE(o.location, '')) AS display_location
                FROM effective_observations o
                WHERE {scope_sql}
                  AND EXISTS (
                      SELECT 1 FROM observation_participants p
                      WHERE p.observation_id = o.observation_id
                  )
            ), grouped AS (
                SELECT location_key,
                       CASE WHEN location_key = '' THEN 'MISSING'
                            ELSE MIN(display_location) END AS value,
                       COUNT(*) AS event_count
                FROM scoped_events
                GROUP BY location_key
            )
            SELECT value, event_count,
                   COUNT(*) OVER () AS facet_total_count,
                   SUM(event_count) OVER () AS event_total_count
            FROM grouped
            ORDER BY event_count DESC, LOWER(value)
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    if not rows:
        return {"locations": [], "location_total_count": 0, "total": 0}
    return {
        "locations": [
            {"value": str(row["value"]), "count": int(row["event_count"])}
            for row in rows
        ],
        "location_total_count": int(rows[0]["facet_total_count"]),
        "total": int(rows[0]["event_total_count"]),
    }


def _world_cluster_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        include_below_threshold=context.request.include_below_threshold,
    )
    activity = _world_event_statistics(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        location_limit=1,
    )["activity"]
    if context.filters.activity:
        people_rows = {pid: row for pid, row in people_rows.items()
                       if _world_activity_bucket(activity.get(pid, 0)) in context.filters.activity}
        relationships = [item for item in relationships
                         if item["source_person_id"] in people_rows and item["target_person_id"] in people_rows]
    clusters = _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters), relationships,
        people_rows, activity, min(context.limits.people, 10), context,
    )
    cluster = next((item for item in clusters if item.cluster_id == context.focus_id), None)
    if cluster is None:
        raise KeyError("World cluster is unavailable in this revision and scope")
    members = tuple(cluster.member_ids)
    member_set = set(members)
    member_relationships = [
        item for item in relationships
        if item["source_person_id"] in member_set and item["target_person_id"] in member_set
    ]
    people: tuple[WorldPerson, ...] = ()
    relationship_models: tuple[WorldRelationship, ...] = ()
    if context.collection == WorldCollection.MEMBERS:
        ids = members[context.offset:context.offset + context.limits.people]
        degree = _world_degree(people_rows, member_relationships)
        people = tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()),
                activity.get(person_id, 0), degree.get(person_id, {}), context,
                selected_by_focus=True,
            ) for person_id in ids
        )
        cluster_out = replace(
            cluster, member_ids=ids,
            member_preview=tuple({
                "canonical_person_id": person_id,
                "display_name": str(people_rows[person_id]["name"]),
            } for person_id in ids),
        )
    else:
        rows = member_relationships[
            context.offset:context.offset + context.limits.relationships
        ]
        relationship_models = _world_relationship_models(conn, rows, context, canonical_map)
        cluster_out = replace(cluster, member_ids=())
    pagination = {
        WorldCollection.MEMBERS.value: _world_page_state(
            context, WorldCollection.MEMBERS, len(members), len(people),
            context.limits.people,
            offset=(context.offset if context.collection == WorldCollection.MEMBERS else 0),
        ),
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(member_relationships),
            len(relationship_models), context.limits.relationships,
            offset=(context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": cluster.member_count,
            "relationships": len(member_relationships), "clusters": 1,
            "finalized_events": _world_scoped_event_count(
                conn, context.filters, member_set, canonical_map=canonical_map,
            ),
        },
        pagination=pagination,
        people=people, clusters=(cluster_out,), relationships=relationship_models,
    )


def _world_person_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    people_rows, aliases, canonical_map = _world_people_scope(conn, context.filters)
    if context.filters.activity:
        activity = _world_event_statistics(
            conn, context.filters, set(people_rows), canonical_map=canonical_map,
            location_limit=1,
        )["activity"]
        people_rows = {pid: row for pid, row in people_rows.items()
                       if _world_activity_bucket(activity.get(pid, 0)) in context.filters.activity}
    canonical_id = canonical_map.get(str(context.focus_id))
    if canonical_id not in people_rows:
        raise KeyError("World person is unavailable in the effective scope")
    relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        focus_person_id=canonical_id,
        include_below_threshold=context.request.include_below_threshold,
    )
    all_relationships = _world_relationship_scope(
        conn, context.filters, set(people_rows), canonical_map=canonical_map,
        include_below_threshold=context.request.include_below_threshold,
    )
    memberships = tuple({
        "cluster_id": cluster.cluster_id,
        "graph_revision": cluster.graph_revision,
        "member_count": cluster.member_count,
        "grouping_algorithm": cluster.grouping_algorithm,
        "algorithm_version": cluster.algorithm_version,
    } for cluster in _world_clusters(
        context.revision, _world_filter_fingerprint(context.filters),
        all_relationships, people_rows, {},
        min(context.limits.people, 10), context,
    ) if canonical_id in cluster.member_ids)
    event_total = _world_person_event_count(
        conn, canonical_id, context.filters, canonical_map=canonical_map,
    )
    activity = {canonical_id: event_total}
    degree = _world_degree({canonical_id: people_rows[canonical_id]}, relationships)
    root = replace(_world_person(
        canonical_id, people_rows[canonical_id], aliases.get(canonical_id, ()),
        activity.get(canonical_id, 0), degree.get(canonical_id, {}), context,
        selected_by_focus=True,
    ), cluster_memberships=memberships)
    if str(context.request.view).strip().upper() == "EXPLORE":
        selected_scope_relationships = relationships
        if not context.request.include_below_threshold:
            selected_scope_relationships = _world_relationship_scope(
                conn, context.filters, set(people_rows), canonical_map=canonical_map,
                focus_person_id=canonical_id, include_below_threshold=True,
            )
        all_focus_relationships = selected_scope_relationships
        selected_types = set(context.filters.evidence_type)
        if selected_types != set(RELATIONSHIP_EVIDENCE_TYPES):
            all_focus_relationships = _world_relationship_scope(
                conn, replace(context.filters, evidence_type=()), set(people_rows),
                canonical_map=canonical_map, focus_person_id=canonical_id,
                include_below_threshold=True,
            )
        selected_ids = {item["relationship_id"] for item in selected_scope_relationships}
        all_ids = {item["relationship_id"] for item in all_focus_relationships}
        qualifying_count = sum(1 for item in selected_scope_relationships if item["qualifies_for_cluster"])
        visibility = {
            "selected_relationship_count": len(selected_scope_relationships),
            "qualifying_relationship_count": qualifying_count,
            "below_minimum_count": len(selected_scope_relationships) - qualifying_count,
            "evidence_type_excluded_count": len(all_ids - selected_ids),
            "all_evidence_relationship_count": len(all_focus_relationships),
            "semantics": "ACTIVE_AUTHORITATIVE_RELATIONSHIPS_IN_EFFECTIVE_SCOPE",
        }
        root = replace(root, intelligence_summary={
            **root.intelligence_summary,
            "relationship_visibility": visibility,
        })
    relationship_models: tuple[WorldRelationship, ...] = ()
    events: tuple[WorldEvent, ...] = ()
    people = (root,)
    if context.collection == WorldCollection.RELATIONSHIPS:
        page_rows = relationships[
            context.offset:context.offset + context.limits.relationships
        ]
        relationship_models = _world_relationship_models(conn, page_rows, context, canonical_map)
        neighbor_ids = {
            item["target_person_id"] if item["source_person_id"] == canonical_id
            else item["source_person_id"] for item in page_rows
        }
        people += tuple(
            _world_person(
                person_id, people_rows[person_id], aliases.get(person_id, ()), None,
                None, context, selected_by_focus=True,
            ) for person_id in sorted(neighbor_ids) if person_id in people_rows
        )
    else:
        _, event_rows = _world_person_events(
            conn, canonical_id, context.filters, context.offset, context.limits.events,
            canonical_map=canonical_map, known_total=event_total,
        )
        batch = _world_event_batch_data(conn, event_rows, canonical_map)
        events = tuple(_world_event_from_row(
            conn, row, participant_offset=0,
            participant_limit=0, provenance_offset=0, provenance_limit=0,
            context=context,
            prepared=batch[str(row["observation_id"])],
        ) for row in event_rows)
    pagination = {
        WorldCollection.RELATIONSHIPS.value: _world_page_state(
            context, WorldCollection.RELATIONSHIPS, len(relationships),
            len(relationship_models), context.limits.relationships,
            offset=(context.offset if context.collection == WorldCollection.RELATIONSHIPS else 0),
        ),
        WorldCollection.EVENTS.value: _world_page_state(
            context, WorldCollection.EVENTS, event_total, len(events),
            context.limits.events,
            offset=(context.offset if context.collection == WorldCollection.EVENTS else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": 1, "relationships": len(relationships),
            "clusters": 0, "finalized_events": event_total,
        },
        pagination=pagination, people=people, events=events,
        relationships=relationship_models,
    )


def _world_event_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    row = _world_event_row(conn, str(context.focus_id), context.filters)
    participant_mapping = _world_event_participant_mapping(conn, str(context.focus_id))
    participant_total = len(participant_mapping[0])
    provenance_total = len(participant_mapping[1])
    evidence_summary = _world_event_evidence_summary(conn, str(context.focus_id))
    evidence_total = _world_event_evidence_count(conn, str(context.focus_id), context.filters)
    media_total = _world_event_media_count(conn, str(context.focus_id))
    participant_offset = context.offset if context.collection == WorldCollection.PARTICIPANTS else 0
    provenance_offset = context.offset if context.collection == WorldCollection.PROVENANCE else 0
    event = _world_event_from_row(
        conn, row, participant_offset=participant_offset,
        participant_limit=(context.limits.people if context.collection == WorldCollection.PARTICIPANTS else 0),
        provenance_offset=provenance_offset,
        provenance_limit=(context.limits.provenance if context.collection == WorldCollection.PROVENANCE else 0),
        context=context,
        prepared=(participant_mapping, evidence_summary, media_total),
    )
    evidence: tuple[WorldEvidence, ...] = ()
    media: tuple[WorldMediaReference, ...] = ()
    if context.collection == WorldCollection.EVIDENCE:
        _, items = _world_evidence_page(
            conn, context.filters, "EVENT", context.focus_id,
            context.offset, context.limits.evidence,
        )
        if context.request.view.strip().upper() == "EXPLORE":
            items = _world_evidence_encounter_support(conn, items)
        evidence = tuple(items)
    elif context.collection == WorldCollection.MEDIA:
        _, media = _world_event_media_page(
            conn, str(context.focus_id), context.offset, context.limits.media,
        )
    pagination = {
        WorldCollection.PARTICIPANTS.value: _world_page_state(
            context, WorldCollection.PARTICIPANTS, participant_total,
            len(event.participants), context.limits.people,
            offset=participant_offset,
        ),
        WorldCollection.PROVENANCE.value: _world_page_state(
            context, WorldCollection.PROVENANCE, provenance_total,
            len(event.participant_provenance), context.limits.provenance,
            offset=provenance_offset,
        ),
        WorldCollection.EVIDENCE.value: _world_page_state(
            context, WorldCollection.EVIDENCE, evidence_total, len(evidence),
            context.limits.evidence,
            offset=(context.offset if context.collection == WorldCollection.EVIDENCE else 0),
        ),
        WorldCollection.MEDIA.value: _world_page_state(
            context, WorldCollection.MEDIA, media_total, len(media),
            context.limits.media,
            offset=(context.offset if context.collection == WorldCollection.MEDIA else 0),
        ),
    }
    return _world_result(
        context,
        scope_totals={
            "people": participant_total, "relationships": 0, "clusters": 0,
            "finalized_events": 1, "evidence": evidence_total, "media": media_total,
        },
        pagination=pagination, events=(event,), evidence=evidence, media=media,
    )


def _world_evidence_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    evidence: tuple[WorldEvidence, ...] = ()
    media: tuple[WorldMediaReference, ...] = ()
    if context.collection == WorldCollection.MEDIA:
        if context.focus_type != "EVIDENCE":
            raise ValueError("EVIDENCE media requires an EVIDENCE focus")
        evidence_total, detail = _world_evidence_page(
            conn, context.filters, "EVIDENCE", context.focus_id, 0, 1,
        )
        if evidence_total != 1 or not detail:
            raise KeyError("World evidence is unavailable in the effective scope")
        evidence = tuple(detail)
        item = detail[0]
        reference = item.supporting_references[0]
        if item.evidence_type == "CO_OBSERVED" and reference["source_entity_type"] == "OBSERVATION":
            media_total, media = _world_event_media_page(
                conn, str(reference["source_entity_id"]), context.offset,
                context.limits.media, supporting_evidence_id=item.evidence_id,
            )
        else:
            media_total = 0
        total = 1
    else:
        total, items = _world_evidence_page(
            conn, context.filters, context.focus_type, context.focus_id,
            context.offset, context.limits.evidence,
        )
        if context.request.view.strip().upper() == "EXPLORE":
            items = _world_evidence_encounter_support(conn, items)
        evidence = tuple(items)
        media_total = 0
    pagination = {
        WorldCollection.EVIDENCE.value: _world_page_state(
            context, WorldCollection.EVIDENCE, total, len(evidence),
            context.limits.evidence,
            offset=(context.offset if context.collection == WorldCollection.EVIDENCE else 0),
        ),
        WorldCollection.MEDIA.value: _world_page_state(
            context, WorldCollection.MEDIA, media_total, len(media),
            context.limits.media,
            offset=(context.offset if context.collection == WorldCollection.MEDIA else 0),
        ),
    }
    return _world_result(
        context, scope_totals={"evidence": total, "media": media_total},
        pagination=pagination, evidence=evidence, media=media,
    )


def _world_event_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
    location_offset: int = 0,
    location_limit: int = 100,
) -> dict[str, object]:
    """Calculate overview event metrics from one effective-participant projection."""
    if not eligible_ids:
        return {"activity": {}, "locations": [], "location_total_count": 0, "total": 0, "missing": 0}
    if canonical_map is not None and eligible_ids == set(canonical_map.values()):
        return _world_full_scope_event_statistics(
            conn, filters, canonical_map,
            location_offset=location_offset, location_limit=location_limit,
        )
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    cte = _world_effective_participant_cte(conn, scope_sql)
    placeholders = ",".join("?" for _ in eligible_ids)
    rows = conn.execute(
        f"""{cte}, eligible AS (
                SELECT e.observation_id, e.person_id,
                       CASE WHEN TRIM(COALESCE(o.location, '')) = '' THEN 'MISSING'
                            ELSE TRIM(o.location) END AS location
                FROM effective e JOIN effective_observations o USING(observation_id)
                WHERE e.person_id IN ({placeholders})
            ), event_set AS (
                SELECT DISTINCT observation_id, location FROM eligible
            )
            SELECT 'ACTIVITY' AS kind, person_id AS label,
                   COUNT(DISTINCT observation_id) AS value
            FROM eligible GROUP BY person_id
            UNION ALL
            SELECT 'LOCATION', location, COUNT(*) FROM event_set GROUP BY LOWER(location)
            UNION ALL
            SELECT 'TOTAL', '', COUNT(*) FROM event_set
            UNION ALL
            SELECT 'MISSING', '', COUNT(*) FROM event_set WHERE location = 'MISSING'""",
        [*params, *sorted(eligible_ids)],
    ).fetchall()
    activity: dict[str, int] = {}
    locations: list[dict[str, object]] = []
    total = missing = 0
    for row in rows:
        kind, label, value = str(row["kind"]), str(row["label"]), int(row["value"])
        if kind == "ACTIVITY":
            activity[label] = value
        elif kind == "LOCATION":
            locations.append({"value": label, "count": value})
        elif kind == "TOTAL":
            total = value
        elif kind == "MISSING":
            missing = value
    locations.sort(key=lambda item: (-int(item["count"]), str(item["value"]).casefold()))
    return {
        "activity": activity,
        "locations": locations[location_offset:location_offset + location_limit],
        "location_total_count": len(locations),
        "total": total, "missing": missing,
    }


def _world_evidence_encounter_support(
    conn: sqlite3.Connection, items: list[WorldEvidence],
) -> list[WorldEvidence]:
    """Exact current frame support only on bounded Explore proof expansions."""
    cache: dict[tuple[str, str], list[str]] = {}
    result = []
    for item in items:
        if item.evidence_type != "CO_OBSERVED":
            result.append(item)
            continue
        event_id = str(item.supporting_references[0]["source_entity_id"])
        source, target = item.effective_endpoints
        for person_id in (source, target):
            key = (event_id, person_id)
            if key not in cache:
                cache[key] = _encounter_person_media(conn, event_id, person_id)
        support = "SHARED_FRAME" if set(cache[event_id, source]) & set(cache[event_id, target]) else "SAME_ENCOUNTER_ONLY"
        result.append(replace(item, provenance={**item.provenance, "encounter_support": support}))
    return result


def _world_patterns(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    people_count: int,
    limit: int,
    *,
    eligible_person_ids: set[str],
    context: _WorldReadContext,
    measured_total: int | None = None,
    measured_missing: int | None = None,
) -> list[WorldPattern]:
    if not eligible_person_ids:
        return []
    if measured_total is None or measured_missing is None:
        statistics = _world_event_statistics(conn, filters, eligible_person_ids)
        total, missing = int(statistics["total"]), int(statistics["missing"])
    else:
        total, missing = measured_total, measured_missing
    if not total or not missing or limit < 1:
        return []
    explanation = WorldExplanation(
        summary=f"{missing} of {total} finalized events in scope have no location metadata.",
        basis_type="DATA_QUALITY_MEASUREMENT",
        factual_factors=(
            {"factor": "finalized_event_count", "value": total},
            {"factor": "missing_location_count", "value": missing},
            {"factor": "scoped_people_count", "value": people_count},
        ),
        calculation_version=_WORLD_CALCULATION_VERSION,
        calculation_scope=_world_explanation_scope(context),
        strongest_factors=(
            {"factor": "missing_location_count", "value": missing},
            {"factor": "finalized_event_count", "value": total},
        ),
        method="count_finalized_events_with_missing_location",
        threshold={"emit_when_missing_location_count_at_least": 1},
        sample={"finalized_event_count": total, "scoped_people_count": people_count},
        limitations=(
            "This is a data-quality measurement, not an anomaly, risk, or prediction.",
            "Free-text locations are not normalized place identities.",
        ),
    )
    return [WorldPattern(
        pattern_id=f"pattern:data-quality:missing-location:{hashlib.sha256(str([total, missing]).encode()).hexdigest()[:12]}",
        pattern_type="DATA_QUALITY", status="MEASURED", subject_ids=("WORLD_SCOPE",),
        metrics={"missing_location_count": missing, "finalized_event_count": total, "unit": "events"},
        calculation_version=_WORLD_CALCULATION_VERSION, explanation=explanation,
    )]


def _encounter_pair_support(conn, observation_id, first_id, second_id, *, media_by_person=None):
    # Reuse frame sets only within the caller's one-Encounter read snapshot.
    # This is not a durable cache or another source of pair support.
    if media_by_person is None:
        media_by_person = {}
    for person_id in (first_id, second_id):
        if person_id not in media_by_person:
            media_by_person[person_id] = _encounter_person_media(conn, observation_id, person_id)
    return _media_pair_support(media_by_person[first_id], media_by_person[second_id])


def _effective_encounter_relations(conn, observation_id):
    result = {}
    media_by_person = {}
    for row in conn.execute("SELECT * FROM encounter_relation_decisions WHERE observation_id = ? AND active = 1 ORDER BY decided_at, rowid", (observation_id,)):
        pair = tuple(sorted(_resolve_canonical_person_id(conn, str(row[key])) for key in ("first_person_id", "second_person_id")))
        if pair[0] == pair[1]:
            continue
        if pair in result and result[pair]["disposition"] != row["disposition"]:
            raise ValueError(f"Event {observation_id} has conflicting Relations")
        # Row ordering chooses a provenance predecessor, never current support.
        result[pair] = {**dict(row), "support": _encounter_pair_support(conn, observation_id, *pair, media_by_person=media_by_person)}
    return result


def _write_encounter_relation_revisions(conn, observation_id, desired, operation_id):
    existing = _effective_encounter_relations(conn, observation_id)
    review = conn.execute("SELECT review_id FROM photo_reviews WHERE observation_id = ? AND status = 'COMPLETED' ORDER BY completed_at LIMIT 1", (observation_id,)).fetchone()
    if not review:
        raise ValueError("Event has no completed review")
    for row in conn.execute("SELECT * FROM encounter_relation_decisions WHERE observation_id = ? AND active = 1", (observation_id,)).fetchall():
        pair = tuple(sorted(_resolve_canonical_person_id(conn, str(row[key])) for key in ("first_person_id", "second_person_id")))
        if pair not in desired or (existing.get(pair, {}).get("decision_id") != row["decision_id"]) or any(row[key] != desired[pair][key] for key in ("disposition", "support")):
            conn.execute("UPDATE encounter_relation_decisions SET active = 0 WHERE decision_id = ?", (row["decision_id"],))
    for pair, value in desired.items():
        previous = existing.get(pair)
        # Compare persisted history, not its derived effective support. A row
        # retired above must never be mistaken for an unchanged current row.
        stored = conn.execute("SELECT * FROM encounter_relation_decisions WHERE decision_id = ? AND active = 1", (previous["decision_id"],)).fetchone() if previous else None
        if stored and all(stored[key] == value[key] for key in ("disposition", "support")):
            continue
        conn.execute("INSERT INTO encounter_relation_decisions(decision_id, review_id, observation_id, first_ref, second_ref, first_person_id, second_person_id, disposition, support, supersedes_decision_id, operation_id, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), review[0], observation_id, f"person:{pair[0]}", f"person:{pair[1]}", *pair, value["disposition"], value["support"], previous["decision_id"] if previous else None, operation_id, utc_now()))


def _refresh_encounter_relation_support(conn, observation_id, operation_id):
    desired = {pair: {**row, "support": _encounter_pair_support(conn, observation_id, *pair)}
               for pair, row in _effective_encounter_relations(conn, observation_id).items()}
    _write_encounter_relation_revisions(conn, observation_id, desired, operation_id)


def _recalculate_observation_evidence(
    conn: sqlite3.Connection,
    observation_id: str,
    operation_id: str,
    source: str,
) -> tuple[list[str], list[str]]:
    deactivated_at = utc_now()
    conn.execute(
        """
        UPDATE relationship_evidence
        SET active = 0, deactivated_operation_id = ?, deactivated_at = ?
        WHERE evidence_type = 'CO_OBSERVED'
          AND source_entity_type = 'OBSERVATION'
          AND source_entity_id = ? AND active = 1
        """,
        (operation_id, deactivated_at, observation_id),
    )
    participant_ids = _effective_observation_person_ids(conn, observation_id)
    evidence_ids: list[str] = []
    created_at = utc_now()
    has_relation_authority = conn.execute(
        "SELECT 1 FROM encounter_relation_decisions WHERE observation_id = ? LIMIT 1",
        (observation_id,),
    ).fetchone() is not None
    if has_relation_authority:
        included_pairs = sorted(pair for pair, row in _effective_encounter_relations(conn, observation_id).items()
                                if row["disposition"] == "INCLUDE")
    else:
        included_pairs = [
            (first_person_id, second_person_id)
            for index, first_person_id in enumerate(participant_ids)
            for second_person_id in participant_ids[index + 1:]
        ]
    for first_person_id, second_person_id in included_pairs:
        if first_person_id == second_person_id:
            continue
        if first_person_id not in participant_ids or second_person_id not in participant_ids:
            raise ValueError("Event Relation no longer matches its participants")
        evidence_ids.append(_insert_relationship_evidence(
                conn,
                evidence_type="CO_OBSERVED",
                source_entity_type="OBSERVATION",
                source_entity_id=observation_id,
                evidence_revision_id=operation_id,
                source_person_id=first_person_id,
                target_person_id=second_person_id,
                relationship_type="ASSOCIATED_WITH",
                directionality="UNDIRECTED",
                source=source,
                created_operation_id=operation_id,
                created_at=created_at,
        ))
    _replace_graph_projection(conn)
    validation = _validate_graph_projection(conn)
    if not validation["valid"]:
        raise RuntimeError(
            "Graph projection validation failed: " + "; ".join(validation["errors"])
        )
    return participant_ids, evidence_ids


def _revise_encounter_relations_for_identity_correction(
    conn: sqlite3.Connection, observation_id: str, from_person_id: str,
    to_person_id: str, operation_id: str,
) -> None:
    """Append effective pair revisions; preserve retired decisions as history."""
    rows = conn.execute(
        "SELECT * FROM encounter_relation_decisions WHERE observation_id = ? AND active = 1 "
        "ORDER BY decided_at, decision_id", (observation_id,),
    ).fetchall()
    if not rows:
        return
    mapped: dict[tuple[str, str], list[sqlite3.Row]] = {}
    changed: set[str] = set()
    self_rows: list[sqlite3.Row] = []
    for row in rows:
        before = tuple(sorted((
            _resolve_canonical_person_id(conn, str(row["first_person_id"])),
            _resolve_canonical_person_id(conn, str(row["second_person_id"])),
        )))
        after = tuple(sorted(to_person_id if person_id == from_person_id else person_id for person_id in before))
        if after[0] == after[1]:
            self_rows.append(row)
            continue
        mapped.setdefault(after, []).append(row)
        if after != before:
            changed.add(str(row["decision_id"]))
    for pair, pair_rows in mapped.items():
        if len({str(row["disposition"]) for row in pair_rows}) > 1:
            raise ValueError(f"Event Relation conflict after identity correction for {pair[0]} and {pair[1]}")
    for row in self_rows:
        conn.execute("UPDATE encounter_relation_decisions SET active = 0 WHERE decision_id = ?", (row["decision_id"],))
    for pair, pair_rows in mapped.items():
        if not any(str(row["decision_id"]) in changed for row in pair_rows) and len(pair_rows) == 1:
            continue
        conn.executemany(
            "UPDATE encounter_relation_decisions SET active = 0 WHERE decision_id = ?",
            [(row["decision_id"],) for row in pair_rows],
        )
        predecessor = pair_rows[-1]
        conn.execute(
            "INSERT INTO encounter_relation_decisions(decision_id, review_id, observation_id, "
            "first_ref, second_ref, first_person_id, second_person_id, disposition, "
            "support, supersedes_decision_id, operation_id, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), predecessor["review_id"], observation_id,
                f"person:{pair[0]}", f"person:{pair[1]}", *pair,
                predecessor["disposition"],
                _encounter_pair_support(conn, observation_id, *pair),
                predecessor["decision_id"], operation_id, utc_now(),
            ),
        )


def _validate_merge_state(
    conn: sqlite3.Connection, source_person_id: str, target_person_id: str,
) -> dict:
    errors: list[str] = []
    source = conn.execute(
        "SELECT lifecycle_status, canonical_person_id FROM persons WHERE person_id = ?",
        (source_person_id,),
    ).fetchone()
    target = conn.execute(
        "SELECT lifecycle_status, canonical_person_id, deleted_at FROM persons WHERE person_id = ?",
        (target_person_id,),
    ).fetchone()
    if source is None or source["lifecycle_status"] != "MERGED" or source["canonical_person_id"] != target_person_id:
        errors.append("Source is not mapped to the requested survivor")
    if target is None or target["lifecycle_status"] != "ACTIVE" or target["canonical_person_id"] is not None or target["deleted_at"] is not None:
        errors.append("Survivor is not terminal and active")
    try:
        if _resolve_canonical_person_id(conn, source_person_id) != target_person_id:
            errors.append("Canonical resolution does not reach the survivor")
    except (KeyError, RuntimeError, ValueError) as exc:
        errors.append(str(exc))
    graph = _validate_graph_projection(conn)
    errors.extend(graph["errors"])
    foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        errors.append("Foreign key validation failed")
    return {"valid": not errors, "errors": errors, "graph": graph}


def _validate_r01_postconditions(
    conn: sqlite3.Connection,
    precondition: ArchivedCanonicalSurvivorRepairPrecondition,
    *,
    canonical_before: str,
    connections_before: str,
    merge_before: str,
    revision_before: str,
) -> dict:
    row = conn.execute(
        "SELECT lifecycle_status, deleted_at, canonical_person_id FROM persons WHERE person_id = ?",
        (precondition.survivor_person_id,),
    ).fetchone()
    if row is None or tuple(row) != ("ACTIVE", None, None):
        raise RuntimeError("R01 immediate lifecycle postcondition failed")
    sources, paths = _r01_resolve_paths(conn, precondition.survivor_person_id)
    merge_ids, merge_after = _r01_merge_snapshot(conn, sources)
    if (
        sources != precondition.merge_source_person_ids
        or paths != precondition.merge_paths
        or merge_ids != precondition.merge_operation_ids
        or merge_after != merge_before
        or _r01_canonical_fingerprint(conn) != canonical_before
    ):
        raise RuntimeError("R01 changed canonical or merge history")
    if _r01_table_fingerprint(conn, "graph_connections") != connections_before:
        raise RuntimeError("R01 unexpectedly changed the graph projection")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError("R01 graph validation failed: " + "; ".join(projection["errors"][:10]))
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("R01 foreign-key postcondition failed")
    before_number = int(revision_before[1:])
    revision_after = _graph_revision_token(conn)
    if revision_after != f"g{before_number + 1}":
        raise RuntimeError("R01 must advance graph revision exactly once")
    return {"graph_revision_after": revision_after, "projection": projection}


def _apply_r02_plan(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    operation_id: str,
    *,
    source: str | None,
    planned_occurrence_id: str | None,
) -> dict:
    created_at = utc_now()
    mutation = {
        "occurrences_appended": 0,
        "occurrences_retired": 0,
        "evidence_appended": 0,
        "evidence_retired": 0,
        "active_evidence_changed": False,
        "appended_occurrence_ids": [],
        "appended_evidence_ids": [],
        "retired_occurrence_ids": [],
        "retired_evidence_ids": [],
    }
    active_occurrence_id = (
        precondition.active_occurrence_ids[0]
        if precondition.active_occurrence_ids else None
    )
    if precondition.plan is NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE:
        if planned_occurrence_id is None:
            raise RuntimeError("R02 occurrence append is missing its planned identity")
        mention_id = planned_occurrence_id
        conn.execute(
            """
            INSERT INTO note_mentions(
                mention_id, note_id, referenced_person_id, active,
                created_revision_id, created_operation_id, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                mention_id,
                precondition.note_id,
                precondition.referenced_person_id,
                precondition.latest_revision_id,
                operation_id,
                created_at,
            ),
        )
        mutation["occurrences_appended"] = 1
        mutation["appended_occurrence_ids"].append(mention_id)
        _r02_failure_checkpoint("after_occurrence_append")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=mention_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 retirement plan lost its active occurrence")
        cursor = conn.execute(
            """
            UPDATE note_mentions
            SET active=0, retired_revision_id=?, retired_operation_id=?, retired_at=?
            WHERE mention_id=? AND active=1
            """,
            (
                precondition.latest_revision_id,
                operation_id,
                created_at,
                active_occurrence_id,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("R02 failed to retire the selected occurrence")
        mutation["occurrences_retired"] = 1
        mutation["retired_occurrence_ids"].append(active_occurrence_id)
        _r02_failure_checkpoint("after_occurrence_retirement")
        rows = conn.execute(
            """
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            ORDER BY evidence_id
            """,
            (active_occurrence_id,),
        ).fetchall()
        if rows:
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id=?, deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (operation_id, created_at, active_occurrence_id),
            )
            mutation["evidence_retired"] = len(rows)
            mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
            mutation["active_evidence_changed"] = True
            _r02_failure_checkpoint("after_evidence_retirement")
    elif precondition.plan is NoteReferenceRepairPlan.APPEND_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 evidence append plan lost its active occurrence")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=active_occurrence_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE:
        if active_occurrence_id is None:
            raise RuntimeError("R02 duplicate replacement lost its active occurrence")
        rows = conn.execute(
            """
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            ORDER BY evidence_id
            """,
            (active_occurrence_id,),
        ).fetchall()
        if len(rows) < 2:
            raise RuntimeError("R02 duplicate evidence plan no longer has duplicates")
        conn.execute(
            """
            UPDATE relationship_evidence
            SET active=0, deactivated_operation_id=?, deactivated_at=?
            WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
            """,
            (operation_id, created_at, active_occurrence_id),
        )
        mutation["evidence_retired"] = len(rows)
        mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_duplicate_evidence_retire_phase")
        evidence_id = _r02_append_evidence(
            conn,
            mention_id=active_occurrence_id,
            owner_person_id=precondition.owner_person_id,
            referenced_person_id=precondition.referenced_person_id,
            operation_id=operation_id,
            source=source,
            created_at=created_at,
        )
        mutation["evidence_appended"] = 1
        mutation["appended_evidence_ids"].append(evidence_id)
        _r02_failure_checkpoint("after_replacement_evidence_append")
    elif precondition.plan is NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE:
        placeholders = ",".join("?" for _ in precondition.occurrence_ids)
        rows = conn.execute(
            f"""
            SELECT evidence_id FROM relationship_evidence
            WHERE evidence_type='NOTE_REFERENCE' AND active=1
              AND source_entity_id IN ({placeholders})
            ORDER BY evidence_id
            """,
            precondition.occurrence_ids,
        ).fetchall()
        if not rows:
            raise RuntimeError("R02 stale evidence plan no longer has active evidence")
        conn.execute(
            f"""
            UPDATE relationship_evidence
            SET active=0, deactivated_operation_id=?, deactivated_at=?
            WHERE evidence_type='NOTE_REFERENCE' AND active=1
              AND source_entity_id IN ({placeholders})
            """,
            (operation_id, created_at, *precondition.occurrence_ids),
        )
        mutation["evidence_retired"] = len(rows)
        mutation["retired_evidence_ids"].extend(str(row[0]) for row in rows)
        mutation["active_evidence_changed"] = True
        _r02_failure_checkpoint("after_evidence_retirement")
    else:  # pragma: no cover - the typed enum and request guard make this unreachable.
        raise RuntimeError("Unsupported R02 plan")
    return mutation


def _r02_maintain_affected_projection(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
) -> None:
    """Replace only the one effective directed relationship aggregate R02 can affect."""
    connections, errors, _ = _expected_graph_connections(conn)
    if errors:
        raise RuntimeError(
            "R02 relationship evidence validation failed: " + "; ".join(errors[:10])
        )
    resolve = _batch_canonical_resolver(conn)
    source_person_id = resolve(precondition.owner_person_id)
    target_person_id = resolve(precondition.referenced_person_id)
    if source_person_id == target_person_id:
        return
    key = (
        source_person_id, target_person_id, "REFERENCES", "DIRECTED",
    )
    expected = [
        item for item in connections
        if _graph_connection_signature(item)[:4] == key
    ]
    if len(expected) > 1:
        raise RuntimeError("R02 shared graph authority returned duplicate affected keys")
    conn.execute(
        """
        DELETE FROM graph_connections
        WHERE source_person_id=? AND target_person_id=?
          AND relationship_type='REFERENCES' AND directionality='DIRECTED'
        """,
        (source_person_id, target_person_id),
    )
    _insert_graph_projection_rows(conn, expected)


def _validate_r02_postconditions(
    conn: sqlite3.Connection,
    precondition: NoteReferenceReconciliationPrecondition,
    *,
    operation_id: str,
    mutation: dict,
    immutable_before: str,
    unrelated_before: str,
    historical_before: str,
    revision_before: str,
) -> dict:
    if _r02_immutable_fingerprint(conn) != immutable_before:
        raise RuntimeError("R02 changed immutable note revision authority")
    if _r02_unrelated_fingerprint(conn, precondition, operation_id) != unrelated_before:
        raise RuntimeError("R02 changed unrelated authoritative state")
    if _r02_retired_history_fingerprint(conn, precondition) != historical_before:
        raise RuntimeError("R02 rewrote pre-existing retired history")
    latest, latest_mentions, revision_fingerprint = _r02_revision_snapshot(
        conn, precondition.note_id,
    )
    if (
        str(latest["revision_id"]) != precondition.latest_revision_id
        or int(latest["revision_number"]) != precondition.latest_revision_number
        or latest_mentions != precondition.latest_revision_mentions
        or revision_fingerprint != precondition.revision_history_fingerprint
    ):
        raise RuntimeError("R02 latest revision authority changed")
    occurrences, evidence = _r02_group_rows(
        conn, precondition.note_id, precondition.referenced_person_id,
    )
    _r02_validate_history(
        conn,
        conn.execute("SELECT * FROM notes WHERE note_id=?", (precondition.note_id,)).fetchone(),
        occurrences,
        evidence,
        allowed_started_operation_id=operation_id,
    )
    expected_occurrence = (
        precondition.note_status == "ACTIVE"
        and precondition.referenced_person_id in precondition.latest_revision_mentions
        and precondition.referenced_person_id != precondition.owner_person_id
    )
    active_occurrences = [row for row in occurrences if bool(row["active"])]
    if len(active_occurrences) != (1 if expected_occurrence else 0):
        raise RuntimeError("R02 immediate NOTE-002 cardinality postcondition failed")
    active_occurrence_ids = {
        str(row["mention_id"]) for row in active_occurrences
    }
    active_evidence = [row for row in evidence if bool(row["active"])]
    expected_evidence = 1 if expected_occurrence else 0
    matching_active = [
        row for row in active_evidence
        if str(row["source_entity_id"]) in active_occurrence_ids
        and row["source_person_id"] == precondition.owner_person_id
        and row["target_person_id"] == precondition.referenced_person_id
        and row["relationship_type"] == "REFERENCES"
        and row["directionality"] == "DIRECTED"
    ]
    if len(active_evidence) != expected_evidence or len(matching_active) != expected_evidence:
        raise RuntimeError("R02 immediate NOTE-003 cardinality postcondition failed")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError(
            "R02 graph/evidence postcondition failed: "
            + "; ".join(projection["errors"][:10])
        )
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("R02 foreign-key postcondition failed")
    journal = _get_journal_operation(conn, operation_id)
    if (
        journal is None
        or journal["operation_type"] != _R02_OPERATION_TYPE
        or journal["status"] != "STARTED"
        or tuple(item["to_status"] for item in journal["status_history"]) != ("STARTED",)
    ):
        raise RuntimeError("R02 transaction-local journal postcondition failed")
    before_number = int(revision_before[1:])
    revision_after = _graph_revision_token(conn)
    expected_revision = (
        f"g{before_number + 1}"
        if mutation["active_evidence_changed"] else revision_before
    )
    if revision_after != expected_revision:
        raise RuntimeError("R02 graph revision did not follow the frozen rule")
    return {
        "graph_revision_after": revision_after,
        "connection_count_after": projection["actual_connection_count"],
    }


def _validate_p11d_postconditions(
    conn: sqlite3.Connection,
    precondition: OperationRevertPrecondition,
    *,
    immutable_before: str,
    target_before: str,
    source_stable_before: str,
    revision_before: str,
) -> dict:
    source = conn.execute(
        """
        SELECT lifecycle_status, canonical_person_id, deleted_at
        FROM persons WHERE person_id=?
        """,
        (precondition.source_person_id,),
    ).fetchone()
    if (
        source is None
        or source["lifecycle_status"] != "ACTIVE"
        or source["canonical_person_id"] is not None
        or source["deleted_at"] is not None
    ):
        raise RuntimeError("P11-D source lifecycle/canonical postcondition failed")
    if _p11d_person_fingerprint(conn, precondition.target_person_id) != target_before:
        raise RuntimeError("P11-D changed the merge survivor")
    if (
        _p11d_person_stable_fingerprint(conn, precondition.source_person_id)
        != source_stable_before
    ):
        raise RuntimeError("P11-D changed non-lifecycle source state")
    if _p11d_immutable_fingerprint(conn, precondition.operation_id) != immutable_before:
        raise RuntimeError("P11-D changed immutable merge history")
    projection = _validate_graph_projection(conn)
    if not projection["valid"]:
        raise RuntimeError(
            "P11-D graph postcondition failed: " + "; ".join(projection["errors"][:10])
        )
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("P11-D foreign-key postcondition failed")
    journal = _get_journal_operation(conn, precondition.operation_id)
    if journal is None or journal["status"] != "COMMITTED":
        raise RuntimeError("P11-D changed the original journal before validation")
    revision_after = _graph_revision_token(conn)
    expected_revision = f"g{int(revision_before[1:]) + 2}"
    if revision_after != expected_revision:
        raise RuntimeError("P11-D graph revision did not follow existing merge rules")
    return {
        "graph_revision_after": revision_after,
        "connection_count_after": projection["actual_connection_count"],
    }
