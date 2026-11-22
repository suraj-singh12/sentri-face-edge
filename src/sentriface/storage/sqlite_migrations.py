"""Inline schema migrations and the migration registry for the SQLite identity store."""
from __future__ import annotations

import json
import sqlite3
import uuid

from sentriface.models import utc_now
from sentriface.storage.sqlite_constants import (
    SCHEMA_VERSION,
    SchemaMigrationError,
)
from sentriface.storage.sqlite_helpers import _legacy_create_note_associations


def _execute_migration_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without sqlite3.executescript's implicit commit."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if not sqlite3.complete_statement(statement):
            continue
        sql = statement.strip()
        if sql:
            conn.execute(sql)
        statement = ""
    if statement.strip():
        raise SchemaMigrationError("Migration contains an incomplete SQL statement")


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            deleted_at TEXT
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
            quality_status TEXT NOT NULL DEFAULT 'warn',
            pending_quality_score REAL NOT NULL DEFAULT 0,
            quality_reasons TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        PRAGMA user_version = 1;
        """
    )


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(pending_additions)").fetchall()
    }
    if "quality_status" not in columns:
        conn.execute("ALTER TABLE pending_additions ADD COLUMN quality_status TEXT NOT NULL DEFAULT 'warn'")
    if "pending_quality_score" not in columns:
        conn.execute(
            "ALTER TABLE pending_additions ADD COLUMN pending_quality_score REAL NOT NULL DEFAULT 0"
        )
    if "quality_reasons" not in columns:
        conn.execute("ALTER TABLE pending_additions ADD COLUMN quality_reasons TEXT NOT NULL DEFAULT '[]'")
    conn.execute("PRAGMA user_version = 2")


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS init_sessions (
            session_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS init_faces (
            init_face_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            source_image TEXT NOT NULL,
            box_x INTEGER NOT NULL,
            box_y INTEGER NOT NULL,
            box_width INTEGER NOT NULL,
            box_height INTEGER NOT NULL,
            box_confidence REAL NOT NULL,
            face_quality_score REAL NOT NULL,
            landmarks TEXT,
            crop_path TEXT,
            vector BLOB NOT NULL,
            quality_status TEXT NOT NULL,
            quality_score REAL NOT NULL,
            quality_reasons TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_init_faces_session_group
        ON init_faces(session_id, group_id);

        CREATE TABLE IF NOT EXISTS init_groups (
            session_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(session_id, group_id),
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id)
        );

        PRAGMA user_version = 3;
        """
    )


def _migrate_3_to_4(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(persons)").fetchall()
    }
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE persons ADD COLUMN deleted_at TEXT")
    conn.execute("PRAGMA user_version = 4")


def _migrate_4_to_5(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS recognition_details (
            detail_id TEXT PRIMARY KEY,
            embedding_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            image_id TEXT NOT NULL,
            image_path TEXT,
            name TEXT NOT NULL,
            decision TEXT NOT NULL,
            seen_date TEXT NOT NULL,
            seen_time TEXT NOT NULL,
            place_seen TEXT NOT NULL,
            individual_count INTEGER NOT NULL,
            event_occasion TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id),
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_recognition_details_embedding
        ON recognition_details(embedding_id);

        CREATE INDEX IF NOT EXISTS idx_recognition_details_person
        ON recognition_details(person_id);

        CREATE INDEX IF NOT EXISTS idx_recognition_details_image
        ON recognition_details(image_id);

        PRAGMA user_version = 5;
        """
    )


def _migrate_5_to_6(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)").fetchall()}
    additions = {
        "rank": "ALTER TABLE recognition_details ADD COLUMN rank TEXT",
        "country": "ALTER TABLE recognition_details ADD COLUMN country TEXT",
        "importance": "ALTER TABLE recognition_details ADD COLUMN importance TEXT",
        "added_by": "ALTER TABLE recognition_details ADD COLUMN added_by TEXT",
    }
    for column, statement in additions.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 6")


def _migrate_6_to_7(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_change_history (
            change_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            previous_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            previous_rank TEXT,
            new_rank TEXT,
            previous_country TEXT,
            new_country TEXT,
            previous_importance TEXT,
            new_importance TEXT,
            editor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_person_change_history_person
        ON person_change_history(person_id);

        PRAGMA user_version = 7;
        """
    )


def _migrate_7_to_8(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS init_face_person_exclusions (
            session_id TEXT NOT NULL,
            init_face_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(session_id, init_face_id, person_id),
            FOREIGN KEY(session_id) REFERENCES init_sessions(session_id),
            FOREIGN KEY(init_face_id) REFERENCES init_faces(init_face_id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_init_face_person_exclusions_face
        ON init_face_person_exclusions(init_face_id);

        PRAGMA user_version = 8;
        """
    )


def _migrate_8_to_9(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_operations (
            operation_id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_person_operations_created
        ON person_operations(created_at);

        PRAGMA user_version = 9;
        """
    )


def _migrate_9_to_10(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            vector BLOB NOT NULL,
            quality_score REAL NOT NULL,
            source_image TEXT,
            crop_path TEXT,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            purge_after TEXT,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE embeddings ADD COLUMN deleted_at TEXT")
    if "purge_after" not in columns:
        conn.execute("ALTER TABLE embeddings ADD COLUMN purge_after TEXT")
    _execute_migration_script(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_embeddings_deleted
        ON embeddings(deleted_at, purge_after);

        PRAGMA user_version = 10;
        """
    )


def _migrate_10_to_11(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS app_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            username_norm TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            roles TEXT NOT NULL,
            disabled INTEGER NOT NULL DEFAULT 0,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_app_users_enabled
        ON app_users(disabled, username_norm);

        CREATE TABLE IF NOT EXISTS auth_audit (
            audit_id TEXT PRIMARY KEY,
            actor_user_id TEXT,
            target_user_id TEXT,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_auth_audit_created
        ON auth_audit(created_at);

        PRAGMA user_version = 11;
        """
    )


def _migrate_11_to_12(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by_user_id TEXT,
            FOREIGN KEY(updated_by_user_id) REFERENCES app_users(user_id)
        );

        PRAGMA user_version = 12;
        """
    )


def _migrate_12_to_13(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS persons (
            person_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            enrollment_status TEXT NOT NULL DEFAULT 'enrolled'
        );

        CREATE TABLE IF NOT EXISTS person_change_history (
            change_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            previous_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            previous_rank TEXT,
            new_rank TEXT,
            previous_country TEXT,
            new_country TEXT,
            previous_importance TEXT,
            new_importance TEXT,
            previous_status TEXT,
            new_status TEXT,
            editor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );
        """
    )
    person_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(persons)").fetchall()
    }
    if "enrollment_status" not in person_columns:
        conn.execute(
            "ALTER TABLE persons ADD COLUMN enrollment_status TEXT NOT NULL DEFAULT 'enrolled'"
        )
    history_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(person_change_history)").fetchall()
    }
    if "previous_status" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN previous_status TEXT")
    if "new_status" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN new_status TEXT")
    _execute_migration_script(
        conn,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_placeholder_name
        ON persons(lower(trim(name)))
        WHERE enrollment_status = 'placeholder' AND deleted_at IS NULL;

        PRAGMA user_version = 13;
        """
    )


def _migrate_13_to_14(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS person_associations (
            association_id TEXT PRIMARY KEY,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            CHECK(source_person_id < target_person_id),
            CHECK(relationship_type = 'ASSOCIATED_WITH'),
            UNIQUE(source_person_id, target_person_id, relationship_type),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_person_associations_source
        ON person_associations(source_person_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_person_associations_target
        ON person_associations(target_person_id, updated_at DESC);

        PRAGMA user_version = 14;
        """
    )


def _migrate_14_to_15(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    person_columns = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    detail_columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")}
    history_columns = {row[1] for row in conn.execute("PRAGMA table_info(person_change_history)")}
    if "persons" in tables and "notes" not in person_columns:
        conn.execute("ALTER TABLE persons ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if "recognition_details" in tables and "notes" not in detail_columns:
        conn.execute("ALTER TABLE recognition_details ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    if "person_change_history" in tables and "previous_notes" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN previous_notes TEXT")
    if "person_change_history" in tables and "new_notes" not in history_columns:
        conn.execute("ALTER TABLE person_change_history ADD COLUMN new_notes TEXT")
    conn.execute("PRAGMA user_version = 15")


def _migrate_15_to_16(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(person_associations)")}
    person_columns = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    detail_columns = {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")}
    if "person_associations" in tables and "association_origin" not in columns:
        conn.execute(
            "ALTER TABLE person_associations ADD COLUMN association_origin TEXT NOT NULL DEFAULT 'manual'"
        )
    if "notes" in person_columns and "person_associations" in tables:
        for row in conn.execute(
            "SELECT person_id, notes FROM persons WHERE deleted_at IS NULL AND notes LIKE '%@%'"
        ).fetchall():
            _legacy_create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
    if "notes" in detail_columns and "person_associations" in tables:
        for row in conn.execute(
            "SELECT person_id, notes FROM recognition_details WHERE notes LIKE '%@%'"
        ).fetchall():
            _legacy_create_note_associations(conn, row["person_id"], row["notes"] or "", "SentriFace migration", [])
    conn.execute("PRAGMA user_version = 16")


def _migrate_16_to_17(conn: sqlite3.Connection) -> None:
    # `person_operations` remains the legacy idempotency/result store. Its rows
    # lack reliable actor and lifecycle data, so backfilling would invent audit
    # history. New journal-aware work uses these dedicated tables instead.
    _execute_migration_script(
        conn,
        """
        CREATE TABLE operation_journal (
            operation_id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('STARTED', 'COMMITTED', 'FAILED', 'ROLLED_BACK', 'REVERTED')),
            actor_user_id TEXT,
            actor TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            affected_entities TEXT NOT NULL DEFAULT '[]',
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE INDEX idx_operation_journal_created
        ON operation_journal(created_at DESC);

        CREATE INDEX idx_operation_journal_status
        ON operation_journal(status, created_at DESC);

        CREATE INDEX idx_operation_journal_actor
        ON operation_journal(actor_user_id, created_at DESC);

        CREATE TABLE operation_journal_status_history (
            transition_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL CHECK(to_status IN ('STARTED', 'COMMITTED', 'FAILED', 'ROLLED_BACK', 'REVERTED')),
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_operation_journal_history_operation
        ON operation_journal_status_history(operation_id, created_at, transition_id);

        CREATE TRIGGER operation_journal_no_delete
        BEFORE DELETE ON operation_journal
        BEGIN
            SELECT RAISE(ABORT, 'operation journal records cannot be deleted');
        END;

        CREATE TRIGGER operation_journal_identity_immutable
        BEFORE UPDATE OF operation_id, operation_type, actor_user_id, actor, source,
                         context, affected_entities, details, created_at
        ON operation_journal
        BEGIN
            SELECT RAISE(ABORT, 'operation journal identity and details are immutable');
        END;

        CREATE TRIGGER operation_journal_history_no_update
        BEFORE UPDATE ON operation_journal_status_history
        BEGIN
            SELECT RAISE(ABORT, 'operation journal history is append-only');
        END;

        CREATE TRIGGER operation_journal_history_no_delete
        BEFORE DELETE ON operation_journal_status_history
        BEGIN
            SELECT RAISE(ABORT, 'operation journal history cannot be deleted');
        END;

        PRAGMA user_version = 17;
        """,
    )


def _migrate_17_to_18(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE persons ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE' "
        "CHECK(lifecycle_status IN ('ACTIVE', 'ARCHIVED', 'DELETED', 'MERGED'))"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN canonical_person_id TEXT REFERENCES persons(person_id) "
        "ON DELETE RESTRICT CHECK(canonical_person_id IS NULL OR canonical_person_id <> person_id)"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN identity_status TEXT NOT NULL DEFAULT 'IDENTIFIED' "
        "CHECK(identity_status IN ('IDENTIFIED', 'UNIDENTIFIED'))"
    )
    conn.execute(
        "ALTER TABLE persons ADD COLUMN biometric_status TEXT NOT NULL DEFAULT 'NO_FACE' "
        "CHECK(biometric_status IN ('NO_FACE', 'ENROLLED'))"
    )
    conn.execute("ALTER TABLE persons ADD COLUMN lifecycle_changed_at TEXT")

    rows = conn.execute(
        "SELECT person_id, metadata, deleted_at, enrollment_status "
        "FROM persons ORDER BY person_id"
    ).fetchall()
    has_embeddings_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'embeddings'"
    ).fetchone() is not None
    person_ids = {str(row["person_id"]) for row in rows}
    legacy_canonical_mappings: dict[str, str] = {}
    for row in rows:
        if not row["deleted_at"]:
            continue
        person_id = str(row["person_id"])
        metadata = json.loads(row["metadata"] or "{}")
        legacy_target = str(metadata.get("merged_into") or "").strip()
        if not legacy_target:
            continue
        if legacy_target == person_id:
            raise SchemaMigrationError(
                f"Invalid legacy canonical mapping for {person_id}: self-reference"
            )
        if legacy_target not in person_ids:
            raise SchemaMigrationError(
                f"Invalid legacy canonical mapping for {person_id}: "
                f"target {legacy_target} does not exist"
            )
        legacy_canonical_mappings[person_id] = legacy_target
    for source_person_id in sorted(legacy_canonical_mappings):
        visited: set[str] = set()
        current_person_id = source_person_id
        while current_person_id in legacy_canonical_mappings:
            if current_person_id in visited:
                raise SchemaMigrationError(
                    f"Invalid legacy canonical mapping for {source_person_id}: cycle detected"
                )
            visited.add(current_person_id)
            current_person_id = legacy_canonical_mappings[current_person_id]
    for row in rows:
        person_id = str(row["person_id"])
        legacy_target = legacy_canonical_mappings.get(person_id)
        if legacy_target is not None:
            lifecycle_status = "MERGED"
            canonical_person_id = legacy_target
        elif row["deleted_at"]:
            lifecycle_status = "ARCHIVED"
            canonical_person_id = None
        else:
            lifecycle_status = "ACTIVE"
            canonical_person_id = None
        if has_embeddings_table:
            has_embedding = conn.execute(
                "SELECT 1 FROM embeddings WHERE person_id = ? LIMIT 1",
                (person_id,),
            ).fetchone() is not None
        else:
            has_embedding = row["enrollment_status"] == "enrolled"
        biometric_status = "ENROLLED" if has_embedding else "NO_FACE"
        conn.execute(
            """
            UPDATE persons
            SET lifecycle_status = ?, canonical_person_id = ?, identity_status = 'IDENTIFIED',
                biometric_status = ?, lifecycle_changed_at = COALESCE(deleted_at, created_at)
            WHERE person_id = ?
            """,
            (lifecycle_status, canonical_person_id, biometric_status, person_id),
        )

    _execute_migration_script(
        conn,
        """
        CREATE INDEX idx_persons_lifecycle
        ON persons(lifecycle_status, name COLLATE NOCASE);

        CREATE INDEX idx_persons_canonical
        ON persons(canonical_person_id);

        CREATE TRIGGER persons_identity_biometric_insert
        BEFORE INSERT ON persons
        WHEN NEW.identity_status = 'UNIDENTIFIED'
         AND NEW.biometric_status = 'NO_FACE'
         AND trim(NEW.name) = ''
         AND trim(NEW.notes) = ''
         AND trim(NEW.metadata) IN ('', '{}')
        BEGIN
            SELECT RAISE(ABORT, 'an unidentified person without a face or context is invalid');
        END;

        CREATE TRIGGER persons_identity_biometric_update
        BEFORE UPDATE OF identity_status, biometric_status ON persons
        WHEN NEW.identity_status = 'UNIDENTIFIED'
         AND NEW.biometric_status = 'NO_FACE'
         AND trim(NEW.name) = ''
         AND trim(NEW.notes) = ''
         AND trim(NEW.metadata) IN ('', '{}')
        BEGIN
            SELECT RAISE(ABORT, 'an unidentified person without a face or context is invalid');
        END;

        CREATE TRIGGER persons_canonical_insert
        BEFORE INSERT ON persons
        WHEN NEW.canonical_person_id IS NOT NULL OR NEW.lifecycle_status = 'MERGED'
        BEGIN
            SELECT CASE
                WHEN NEW.lifecycle_status <> 'MERGED' OR NEW.canonical_person_id IS NULL
                THEN RAISE(ABORT, 'canonical mapping requires MERGED lifecycle status')
            END;
            SELECT CASE
                WHEN NEW.canonical_person_id = NEW.person_id
                THEN RAISE(ABORT, 'canonical identity cannot reference itself')
            END;
            SELECT CASE
                WHEN NOT EXISTS(SELECT 1 FROM persons WHERE person_id = NEW.canonical_person_id)
                THEN RAISE(ABORT, 'canonical identity target does not exist')
            END;
        END;

        CREATE TRIGGER persons_canonical_update
        BEFORE UPDATE OF canonical_person_id, lifecycle_status ON persons
        WHEN NEW.canonical_person_id IS NOT NULL OR NEW.lifecycle_status = 'MERGED'
        BEGIN
            SELECT CASE
                WHEN NEW.lifecycle_status <> 'MERGED' OR NEW.canonical_person_id IS NULL
                THEN RAISE(ABORT, 'canonical mapping requires MERGED lifecycle status')
            END;
            SELECT CASE
                WHEN NEW.canonical_person_id = NEW.person_id
                THEN RAISE(ABORT, 'canonical identity cannot reference itself')
            END;
            SELECT CASE
                WHEN NOT EXISTS(SELECT 1 FROM persons WHERE person_id = NEW.canonical_person_id)
                THEN RAISE(ABORT, 'canonical identity target does not exist')
            END;
            WITH RECURSIVE canonical_chain(person_id, canonical_person_id) AS (
                SELECT person_id, canonical_person_id
                FROM persons WHERE person_id = NEW.canonical_person_id
                UNION
                SELECT p.person_id, p.canonical_person_id
                FROM persons p
                JOIN canonical_chain c ON p.person_id = c.canonical_person_id
                WHERE c.canonical_person_id IS NOT NULL
            )
            SELECT CASE
                WHEN EXISTS(SELECT 1 FROM canonical_chain WHERE person_id = NEW.person_id)
                THEN RAISE(ABORT, 'canonical identity cycle detected')
            END;
        END;

        PRAGMA user_version = 18;
        """,
    )


def _migrate_18_to_19(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE observations (
            observation_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'DRAFT'
                CHECK(status IN ('DRAFT', 'FINALIZED')),
            observed_at TEXT,
            location TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finalized_at TEXT,
            FOREIGN KEY(created_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (status = 'DRAFT' AND finalized_at IS NULL)
                OR (status = 'FINALIZED' AND finalized_at IS NOT NULL)
            )
        );

        CREATE INDEX idx_observations_status_time
        ON observations(status, observed_at, created_at);

        CREATE TABLE observation_media (
            observation_id TEXT NOT NULL,
            media_id TEXT NOT NULL,
            media_path TEXT,
            source TEXT,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(observation_id, media_id),
            FOREIGN KEY(observation_id)
                REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_media_media
        ON observation_media(media_id, observation_id);

        CREATE TABLE observation_participants (
            observation_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            source TEXT,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(observation_id, person_id),
            FOREIGN KEY(observation_id)
                REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(person_id)
                REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_participants_person
        ON observation_participants(person_id, observation_id);

        CREATE TRIGGER observations_no_delete
        BEFORE DELETE ON observations
        BEGIN
            SELECT RAISE(ABORT, 'observations cannot be deleted');
        END;

        CREATE TRIGGER observations_id_immutable
        BEFORE UPDATE OF observation_id ON observations
        BEGIN
            SELECT RAISE(ABORT, 'observation IDs are immutable');
        END;

        CREATE TRIGGER observations_finalized_immutable
        BEFORE UPDATE OF observed_at, location, context, source ON observations
        WHEN OLD.status = 'FINALIZED'
        BEGIN
            SELECT RAISE(ABORT, 'finalized observations are immutable');
        END;

        CREATE TRIGGER observations_status_transition
        BEFORE UPDATE OF status ON observations
        BEGIN
            SELECT CASE
                WHEN OLD.status <> 'DRAFT' OR NEW.status <> 'FINALIZED'
                THEN RAISE(ABORT, 'invalid observation status transition')
            END;
            SELECT CASE
                WHEN NOT EXISTS(
                    SELECT 1 FROM observation_participants p
                    WHERE p.observation_id = OLD.observation_id
                )
                THEN RAISE(ABORT, 'a finalized observation requires a participant')
            END;
        END;

        CREATE TRIGGER observation_media_draft_insert
        BEFORE INSERT ON observation_media
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = NEW.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation media can change only while draft');
        END;

        CREATE TRIGGER observation_media_draft_delete
        BEFORE DELETE ON observation_media
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = OLD.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation media can change only while draft');
        END;

        CREATE TRIGGER observation_participants_draft_insert
        BEFORE INSERT ON observation_participants
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = NEW.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation participants can change only while draft');
        END;

        CREATE TRIGGER observation_participants_draft_delete
        BEFORE DELETE ON observation_participants
        WHEN NOT EXISTS(
            SELECT 1 FROM observations o
            WHERE o.observation_id = OLD.observation_id AND o.status = 'DRAFT'
        )
        BEGIN
            SELECT RAISE(ABORT, 'observation participants can change only while draft');
        END;

        PRAGMA user_version = 19;
        """,
    )
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "recognition_details" in tables:
        detail_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(recognition_details)")
        }
        if "observation_id" not in detail_columns:
            conn.execute(
                "ALTER TABLE recognition_details ADD COLUMN observation_id TEXT "
                "REFERENCES observations(observation_id) ON DELETE RESTRICT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recognition_details_observation "
            "ON recognition_details(observation_id)"
        )


def _migrate_19_to_20(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE relationship_evidence (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL
                CHECK(evidence_type IN ('CO_OBSERVED', 'NOTE_REFERENCE', 'MANUAL_ASSOCIATION')),
            source_entity_type TEXT NOT NULL
                CHECK(source_entity_type IN ('OBSERVATION', 'NOTE', 'MANUAL_ASSERTION')),
            source_entity_id TEXT NOT NULL,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            directionality TEXT NOT NULL DEFAULT 'UNDIRECTED'
                CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deactivated_operation_id TEXT,
            deactivated_at TEXT,
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(deactivated_operation_id)
                REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(
                evidence_type, source_entity_type, source_entity_id,
                source_person_id, target_person_id, relationship_type, directionality
            ),
            CHECK(source_person_id <> target_person_id),
            CHECK(
                (active = 1 AND deactivated_operation_id IS NULL AND deactivated_at IS NULL)
                OR
                (active = 0 AND deactivated_operation_id IS NOT NULL AND deactivated_at IS NOT NULL)
            ),
            CHECK(
                (evidence_type = 'CO_OBSERVED' AND source_entity_type = 'OBSERVATION')
                OR (evidence_type = 'NOTE_REFERENCE' AND source_entity_type = 'NOTE')
                OR (evidence_type = 'MANUAL_ASSOCIATION' AND source_entity_type = 'MANUAL_ASSERTION')
            )
        );

        CREATE INDEX idx_relationship_evidence_source
        ON relationship_evidence(evidence_type, source_entity_id, active);

        CREATE INDEX idx_relationship_evidence_people
        ON relationship_evidence(source_person_id, target_person_id, active);

        CREATE TABLE graph_connections (
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            directionality TEXT NOT NULL
                CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            evidence_count INTEGER NOT NULL CHECK(evidence_count > 0),
            evidence_types TEXT NOT NULL,
            last_evidence_at TEXT NOT NULL,
            PRIMARY KEY(
                source_person_id, target_person_id, relationship_type, directionality
            ),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            CHECK(source_person_id <> target_person_id),
            CHECK(directionality = 'DIRECTED' OR source_person_id < target_person_id)
        );

        CREATE INDEX idx_graph_connections_target
        ON graph_connections(target_person_id, source_person_id);

        CREATE TRIGGER relationship_evidence_no_delete
        BEFORE DELETE ON relationship_evidence
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence cannot be deleted');
        END;

        CREATE TRIGGER relationship_evidence_identity_immutable
        BEFORE UPDATE OF evidence_id, evidence_type, source_entity_type, source_entity_id,
                         source_person_id, target_person_id, relationship_type, directionality,
                         source, created_operation_id, created_at
        ON relationship_evidence
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence provenance is immutable');
        END;

        CREATE TRIGGER relationship_evidence_deactivation_only
        BEFORE UPDATE OF active, deactivated_operation_id, deactivated_at
        ON relationship_evidence
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN
            SELECT RAISE(ABORT, 'relationship evidence can only transition from active to inactive');
        END;

        PRAGMA user_version = 20;
        """,
    )


def _migrate_20_to_21(conn: sqlite3.Connection) -> None:
    invalid = conn.execute(
        """
        SELECT evidence_id
        FROM relationship_evidence
        WHERE directionality = 'UNDIRECTED'
          AND source_person_id >= target_person_id
        LIMIT 1
        """
    ).fetchone()
    if invalid is not None:
        raise SchemaMigrationError(
            "Cannot enforce undirected evidence ordering: "
            f"evidence {invalid['evidence_id']} has non-canonical raw endpoint order"
        )
    _execute_migration_script(
        conn,
        """
        CREATE TRIGGER relationship_evidence_undirected_order_insert
        BEFORE INSERT ON relationship_evidence
        WHEN NEW.directionality = 'UNDIRECTED'
         AND NEW.source_person_id >= NEW.target_person_id
        BEGIN
            SELECT RAISE(ABORT, 'undirected evidence endpoints must be ordered');
        END;

        PRAGMA user_version = 21;
        """,
    )


def _migrate_21_to_22(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE notes (
            note_id TEXT PRIMARY KEY,
            owner_person_id TEXT NOT NULL,
            subject_type TEXT NOT NULL CHECK(subject_type IN ('PERSON', 'RECOGNITION_DETAIL')),
            subject_id TEXT NOT NULL,
            is_profile_note INTEGER NOT NULL DEFAULT 0 CHECK(is_profile_note IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'RETIRED')),
            created_operation_id TEXT,
            retired_operation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            retired_at TEXT,
            FOREIGN KEY(owner_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (status = 'ACTIVE' AND retired_operation_id IS NULL AND retired_at IS NULL)
                OR
                (status = 'RETIRED' AND retired_operation_id IS NOT NULL AND retired_at IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX idx_notes_active_profile
        ON notes(owner_person_id)
        WHERE is_profile_note = 1 AND status = 'ACTIVE';

        CREATE INDEX idx_notes_subject
        ON notes(subject_type, subject_id, status);

        CREATE TABLE note_revisions (
            revision_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            revision_number INTEGER NOT NULL CHECK(revision_number > 0),
            content TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '{}',
            author_name TEXT NOT NULL DEFAULT '',
            operation_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(note_id) REFERENCES notes(note_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(note_id, revision_number)
        );

        CREATE INDEX idx_note_revisions_note
        ON note_revisions(note_id, revision_number);

        CREATE TABLE note_revision_mentions (
            revision_id TEXT NOT NULL,
            referenced_person_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(revision_id, referenced_person_id),
            FOREIGN KEY(revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(referenced_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE TABLE note_mentions (
            mention_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            referenced_person_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            created_revision_id TEXT NOT NULL,
            retired_revision_id TEXT,
            created_operation_id TEXT NOT NULL,
            retired_operation_id TEXT,
            created_at TEXT NOT NULL,
            retired_at TEXT,
            FOREIGN KEY(note_id) REFERENCES notes(note_id) ON DELETE RESTRICT,
            FOREIGN KEY(referenced_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_revision_id) REFERENCES note_revisions(revision_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(retired_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            CHECK(
                (active = 1 AND retired_revision_id IS NULL
                 AND retired_operation_id IS NULL AND retired_at IS NULL)
                OR
                (active = 0 AND retired_operation_id IS NOT NULL AND retired_at IS NOT NULL)
            )
        );

        CREATE UNIQUE INDEX idx_note_mentions_active_target
        ON note_mentions(note_id, referenced_person_id)
        WHERE active = 1;

        CREATE TRIGGER notes_no_delete
        BEFORE DELETE ON notes
        BEGIN
            SELECT RAISE(ABORT, 'notes cannot be deleted');
        END;

        CREATE TRIGGER notes_identity_immutable
        BEFORE UPDATE OF note_id, owner_person_id, subject_type, subject_id,
                         is_profile_note, created_operation_id, created_at
        ON notes
        BEGIN
            SELECT RAISE(ABORT, 'note identity and provenance are immutable');
        END;

        CREATE TRIGGER notes_retirement_only
        BEFORE UPDATE OF status, retired_operation_id, retired_at ON notes
        WHEN OLD.status = 'RETIRED' OR NEW.status <> 'RETIRED'
        BEGIN
            SELECT RAISE(ABORT, 'notes can only transition from active to retired');
        END;

        CREATE TRIGGER note_revisions_no_update
        BEFORE UPDATE ON note_revisions
        BEGIN
            SELECT RAISE(ABORT, 'note revisions are immutable');
        END;

        CREATE TRIGGER note_revisions_no_delete
        BEFORE DELETE ON note_revisions
        BEGIN
            SELECT RAISE(ABORT, 'note revisions cannot be deleted');
        END;

        CREATE TRIGGER note_revision_mentions_no_update
        BEFORE UPDATE ON note_revision_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note revision mentions are immutable');
        END;

        CREATE TRIGGER note_revision_mentions_no_delete
        BEFORE DELETE ON note_revision_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note revision mentions cannot be deleted');
        END;

        CREATE TRIGGER note_mentions_no_delete
        BEFORE DELETE ON note_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note mentions cannot be deleted');
        END;

        CREATE TRIGGER note_mentions_identity_immutable
        BEFORE UPDATE OF mention_id, note_id, referenced_person_id,
                         created_revision_id, created_operation_id, created_at
        ON note_mentions
        BEGIN
            SELECT RAISE(ABORT, 'note mention provenance is immutable');
        END;

        CREATE TRIGGER note_mentions_deactivation_only
        BEFORE UPDATE OF active, retired_revision_id, retired_operation_id, retired_at
        ON note_mentions
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN
            SELECT RAISE(ABORT, 'note mentions can only transition from active to inactive');
        END;
        """,
    )
    actor_payload = json.dumps(
        {"display_name": "Legacy migration", "roles": []}, separators=(",", ":"),
    )
    person_rows = conn.execute(
        """
        SELECT person_id, notes, created_at
        FROM persons
        WHERE trim(notes) <> ''
        ORDER BY person_id
        """
    ).fetchall()
    for row in person_rows:
        note_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface:person-note:{row['person_id']}"))
        revision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note_id}:revision:1"))
        created_at = str(row["created_at"] or utc_now())
        conn.execute(
            """
            INSERT INTO notes(
                note_id, owner_person_id, subject_type, subject_id, is_profile_note,
                status, created_at, updated_at
            ) VALUES (?, ?, 'PERSON', ?, 1, 'ACTIVE', ?, ?)
            """,
            (note_id, row["person_id"], row["person_id"], created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO note_revisions(
                revision_id, note_id, revision_number, content, actor,
                author_name, operation_id, created_at
            ) VALUES (?, ?, 1, ?, ?, 'Legacy migration', NULL, ?)
            """,
            (revision_id, note_id, row["notes"], actor_payload, created_at),
        )
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "recognition_details" in tables:
        detail_rows = conn.execute(
            """
            SELECT detail_id, person_id, notes, created_at
            FROM recognition_details
            WHERE trim(notes) <> ''
            ORDER BY detail_id
            """
        ).fetchall()
        for row in detail_rows:
            note_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"sentriface:recognition-note:{row['detail_id']}",
            ))
            revision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{note_id}:revision:1"))
            created_at = str(row["created_at"] or utc_now())
            conn.execute(
                """
                INSERT INTO notes(
                    note_id, owner_person_id, subject_type, subject_id,
                    is_profile_note, status, created_at, updated_at
                ) VALUES (?, ?, 'RECOGNITION_DETAIL', ?, 0, 'ACTIVE', ?, ?)
                """,
                (note_id, row["person_id"], row["detail_id"], created_at, created_at),
            )
            conn.execute(
                """
                INSERT INTO note_revisions(
                    revision_id, note_id, revision_number, content, actor,
                    author_name, operation_id, created_at
                ) VALUES (?, ?, 1, ?, ?, 'Legacy migration', NULL, ?)
                """,
                (revision_id, note_id, row["notes"], actor_payload, created_at),
            )
    conn.execute("PRAGMA user_version = 22")


def _migrate_22_to_23(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE photo_reviews (
            review_id TEXT PRIMARY KEY,
            media_id TEXT NOT NULL,
            media_path TEXT,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
                CHECK(status IN ('IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
            observation_id TEXT,
            completed_operation_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
            FOREIGN KEY(completed_operation_id) REFERENCES operation_journal(operation_id)
        );

        CREATE TABLE photo_review_faces (
            review_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            staged_face_type TEXT NOT NULL
                CHECK(staged_face_type IN ('PENDING_ADDITION', 'INIT_FACE')),
            staged_face_id TEXT NOT NULL,
            decision TEXT
                CHECK(decision IS NULL OR decision IN (
                    'ACCEPT_EXISTING_PERSON', 'ACCEPT_NEW_PERSON', 'EXCLUDE', 'SKIP'
                )),
            person_id TEXT,
            new_person_key TEXT,
            new_person_name TEXT,
            new_person_metadata TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            mentioned_person_ids TEXT NOT NULL DEFAULT '[]',
            recognition_detail TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(review_id, face_id),
            UNIQUE(staged_face_type, staged_face_id),
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id),
            FOREIGN KEY(person_id) REFERENCES persons(person_id)
        );

        CREATE INDEX idx_photo_reviews_status_created
        ON photo_reviews(status, created_at);

        CREATE TRIGGER completed_photo_reviews_immutable
        BEFORE UPDATE ON photo_reviews
        WHEN OLD.status = 'COMPLETED'
        BEGIN
            SELECT RAISE(ABORT, 'completed reviews are immutable');
        END;

        CREATE TRIGGER completed_photo_review_faces_immutable
        BEFORE UPDATE ON photo_review_faces
        WHEN EXISTS (
            SELECT 1 FROM photo_reviews r
            WHERE r.review_id = OLD.review_id AND r.status = 'COMPLETED'
        )
        BEGIN
            SELECT RAISE(ABORT, 'completed review decisions are immutable');
        END;

        PRAGMA user_version = 23;
        """,
    )


def _migrate_23_to_24(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE observation_face_assignments (
            assignment_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            embedding_id TEXT NOT NULL,
            original_person_id TEXT NOT NULL,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(observation_id, face_id),
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(original_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_observation_face_assignments_embedding
        ON observation_face_assignments(embedding_id, observation_id);

        CREATE TABLE identity_corrections (
            correction_id TEXT PRIMARY KEY,
            correction_type TEXT NOT NULL CHECK(correction_type IN (
                'OBSERVATION_IDENTITY', 'FACE_ASSIGNMENT', 'FACE_OWNERSHIP'
            )),
            observation_id TEXT,
            face_assignment_id TEXT,
            embedding_id TEXT,
            from_person_id TEXT NOT NULL,
            to_person_id TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(from_person_id <> to_person_id),
            FOREIGN KEY(observation_id) REFERENCES observations(observation_id) ON DELETE RESTRICT,
            FOREIGN KEY(face_assignment_id) REFERENCES observation_face_assignments(assignment_id) ON DELETE RESTRICT,
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(from_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(to_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_identity_corrections_observation
        ON identity_corrections(observation_id, created_at, correction_id);

        CREATE INDEX idx_identity_corrections_embedding
        ON identity_corrections(embedding_id, created_at, correction_id);

        CREATE TABLE biometric_enrollment_history (
            enrollment_id TEXT PRIMARY KEY,
            embedding_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(operation_id, embedding_id),
            FOREIGN KEY(embedding_id) REFERENCES embeddings(embedding_id) ON DELETE RESTRICT,
            FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(review_id) REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE TRIGGER observation_face_assignments_no_update
        BEFORE UPDATE ON observation_face_assignments
        BEGIN
            SELECT RAISE(ABORT, 'observation face assignments are immutable');
        END;

        CREATE TRIGGER observation_face_assignments_no_delete
        BEFORE DELETE ON observation_face_assignments
        BEGIN
            SELECT RAISE(ABORT, 'observation face assignments cannot be deleted');
        END;

        CREATE TRIGGER identity_corrections_no_update
        BEFORE UPDATE ON identity_corrections
        BEGIN
            SELECT RAISE(ABORT, 'identity corrections are immutable');
        END;

        CREATE TRIGGER identity_corrections_no_delete
        BEFORE DELETE ON identity_corrections
        BEGIN
            SELECT RAISE(ABORT, 'identity corrections cannot be deleted');
        END;

        CREATE TRIGGER biometric_enrollment_history_no_update
        BEFORE UPDATE ON biometric_enrollment_history
        BEGIN
            SELECT RAISE(ABORT, 'biometric enrollment history is immutable');
        END;

        CREATE TRIGGER biometric_enrollment_history_no_delete
        BEFORE DELETE ON biometric_enrollment_history
        BEGIN
            SELECT RAISE(ABORT, 'biometric enrollment history cannot be deleted');
        END;
        """,
    )


    completed_reviews = conn.execute(
        """
        SELECT r.review_id, r.observation_id, r.completed_operation_id, h.details, r.completed_at
        FROM photo_reviews r
        JOIN operation_journal_status_history h
          ON h.operation_id = r.completed_operation_id AND h.to_status = 'COMMITTED'
        WHERE r.status = 'COMPLETED' AND r.observation_id IS NOT NULL
        ORDER BY r.review_id
        """
    ).fetchall()
    for review in completed_reviews:
        result = json.loads(review["details"] or "{}")
        face_assignments = result.get("face_assignments") or {}
        embedding_assignments = result.get("embedding_assignments") or {}
        for face_id in sorted(set(face_assignments) & set(embedding_assignments)):
            assignment_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sentriface:observation-face:{review['observation_id']}:{face_id}",
            ))
            conn.execute(
                """
                INSERT OR IGNORE INTO observation_face_assignments(
                    assignment_id, observation_id, review_id, face_id, embedding_id,
                    original_person_id, created_operation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id, review["observation_id"], review["review_id"], face_id,
                    embedding_assignments[face_id], face_assignments[face_id],
                    review["completed_operation_id"], review["completed_at"] or utc_now(),
                ),
            )

    _execute_migration_script(
        conn,
        """
        DROP TRIGGER relationship_evidence_no_delete;
        DROP TRIGGER relationship_evidence_identity_immutable;
        DROP TRIGGER relationship_evidence_deactivation_only;
        DROP TRIGGER relationship_evidence_undirected_order_insert;
        DROP INDEX idx_relationship_evidence_source;
        DROP INDEX idx_relationship_evidence_people;
        ALTER TABLE relationship_evidence RENAME TO relationship_evidence_v23;

        CREATE TABLE relationship_evidence (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL CHECK(evidence_type IN ('CO_OBSERVED', 'NOTE_REFERENCE', 'MANUAL_ASSOCIATION')),
            source_entity_type TEXT NOT NULL CHECK(source_entity_type IN ('OBSERVATION', 'NOTE', 'MANUAL_ASSERTION')),
            source_entity_id TEXT NOT NULL,
            evidence_revision_id TEXT NOT NULL,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT 'ASSOCIATED_WITH',
            directionality TEXT NOT NULL DEFAULT 'UNDIRECTED' CHECK(directionality IN ('UNDIRECTED', 'DIRECTED')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            source TEXT,
            created_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deactivated_operation_id TEXT,
            deactivated_at TEXT,
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(created_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(deactivated_operation_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT,
            UNIQUE(evidence_type, source_entity_type, source_entity_id, evidence_revision_id,
                   source_person_id, target_person_id, relationship_type, directionality),
            CHECK(source_person_id <> target_person_id),
            CHECK((active = 1 AND deactivated_operation_id IS NULL AND deactivated_at IS NULL)
               OR (active = 0 AND deactivated_operation_id IS NOT NULL AND deactivated_at IS NOT NULL)),
            CHECK((evidence_type = 'CO_OBSERVED' AND source_entity_type = 'OBSERVATION')
               OR (evidence_type = 'NOTE_REFERENCE' AND source_entity_type = 'NOTE')
               OR (evidence_type = 'MANUAL_ASSOCIATION' AND source_entity_type = 'MANUAL_ASSERTION'))
        );

        INSERT INTO relationship_evidence(
            evidence_id, evidence_type, source_entity_type, source_entity_id,
            evidence_revision_id, source_person_id, target_person_id, relationship_type,
            directionality, active, source, created_operation_id, created_at,
            deactivated_operation_id, deactivated_at
        )
        SELECT evidence_id, evidence_type, source_entity_type, source_entity_id,
               source_entity_id, source_person_id, target_person_id, relationship_type,
               directionality, active, source, created_operation_id, created_at,
               deactivated_operation_id, deactivated_at
        FROM relationship_evidence_v23;
        DROP TABLE relationship_evidence_v23;

        CREATE INDEX idx_relationship_evidence_source
        ON relationship_evidence(evidence_type, source_entity_id, active);
        CREATE INDEX idx_relationship_evidence_people
        ON relationship_evidence(source_person_id, target_person_id, active);

        CREATE TRIGGER relationship_evidence_no_delete
        BEFORE DELETE ON relationship_evidence
        BEGIN SELECT RAISE(ABORT, 'relationship evidence cannot be deleted'); END;
        CREATE TRIGGER relationship_evidence_identity_immutable
        BEFORE UPDATE OF evidence_id, evidence_type, source_entity_type, source_entity_id,
                         evidence_revision_id, source_person_id, target_person_id,
                         relationship_type, directionality, source, created_operation_id, created_at
        ON relationship_evidence
        BEGIN SELECT RAISE(ABORT, 'relationship evidence provenance is immutable'); END;
        CREATE TRIGGER relationship_evidence_deactivation_only
        BEFORE UPDATE OF active, deactivated_operation_id, deactivated_at ON relationship_evidence
        WHEN OLD.active = 0 OR NEW.active <> 0
        BEGIN SELECT RAISE(ABORT, 'relationship evidence can only transition from active to inactive'); END;
        CREATE TRIGGER relationship_evidence_undirected_order_insert
        BEFORE INSERT ON relationship_evidence
        WHEN NEW.directionality = 'UNDIRECTED' AND NEW.source_person_id >= NEW.target_person_id
        BEGIN SELECT RAISE(ABORT, 'undirected evidence endpoints must be ordered'); END;

        PRAGMA user_version = 24;
        """,
    )


def _migrate_24_to_25(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        CREATE TABLE merge_operations (
            merge_operation_id TEXT PRIMARY KEY,
            source_person_id TEXT NOT NULL,
            target_person_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            previous_source_lifecycle_status TEXT NOT NULL,
            previous_target_lifecycle_status TEXT NOT NULL,
            previous_source_canonical_person_id TEXT,
            previous_target_canonical_person_id TEXT,
            reason TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            operation_journal_id TEXT NOT NULL UNIQUE,
            CHECK(source_person_id <> target_person_id),
            FOREIGN KEY(source_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(target_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_source_canonical_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_target_canonical_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(operation_journal_id) REFERENCES operation_journal(operation_id) ON DELETE RESTRICT
        );

        CREATE TABLE merge_affected_items (
            merge_operation_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            previous_person_id TEXT,
            effective_person_id TEXT,
            context TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(merge_operation_id, item_type, item_id),
            FOREIGN KEY(merge_operation_id) REFERENCES merge_operations(merge_operation_id) ON DELETE RESTRICT,
            FOREIGN KEY(previous_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT,
            FOREIGN KEY(effective_person_id) REFERENCES persons(person_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_merge_operations_people
        ON merge_operations(source_person_id, target_person_id, created_at);
        CREATE INDEX idx_merge_affected_items_lookup
        ON merge_affected_items(item_type, item_id);

        CREATE TRIGGER merge_operations_no_update
        BEFORE UPDATE ON merge_operations
        BEGIN SELECT RAISE(ABORT, 'merge operations are immutable'); END;
        CREATE TRIGGER merge_operations_no_delete
        BEFORE DELETE ON merge_operations
        BEGIN SELECT RAISE(ABORT, 'merge operations cannot be deleted'); END;
        CREATE TRIGGER merge_affected_items_no_update
        BEFORE UPDATE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items are immutable'); END;
        CREATE TRIGGER merge_affected_items_no_delete
        BEFORE DELETE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items cannot be deleted'); END;

        PRAGMA user_version = 25;
        """,
    )


def _migrate_25_to_26(conn: sqlite3.Connection) -> None:
    _execute_migration_script(
        conn,
        """
        DROP TRIGGER merge_affected_items_no_update;
        ALTER TABLE merge_affected_items ADD COLUMN raw_owner_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT;
        ALTER TABLE merge_affected_items ADD COLUMN effective_owner_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT;
        ALTER TABLE merge_affected_items ADD COLUMN action TEXT NOT NULL DEFAULT 'PRESERVE'
            CHECK(action IN ('PRESERVE', 'REINTERPRET_CANONICAL_OWNER', 'UNION_IN_CURRENT_VIEW', 'SELECT_VALUE'));
        ALTER TABLE merge_affected_items ADD COLUMN before_state TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE merge_affected_items ADD COLUMN after_state TEXT NOT NULL DEFAULT '{}';
        UPDATE merge_affected_items
        SET raw_owner_person_id = previous_person_id,
            effective_owner_person_id = effective_person_id;

        CREATE TRIGGER merge_affected_items_no_update
        BEFORE UPDATE ON merge_affected_items
        BEGIN SELECT RAISE(ABORT, 'merge affected items are immutable'); END;

        CREATE TABLE merge_conflict_resolutions (
            conflict_id TEXT PRIMARY KEY,
            merge_operation_id TEXT NOT NULL,
            category TEXT NOT NULL,
            field_name TEXT NOT NULL,
            source_value TEXT NOT NULL,
            target_value TEXT NOT NULL,
            strategy TEXT NOT NULL CHECK(strategy IN (
                'KEEP_SOURCE', 'KEEP_TARGET', 'COMBINE', 'USER_SELECTED'
            )),
            selected_value TEXT NOT NULL,
            inverse_data TEXT NOT NULL,
            UNIQUE(merge_operation_id, category, field_name),
            FOREIGN KEY(merge_operation_id) REFERENCES merge_operations(merge_operation_id) ON DELETE RESTRICT
        );

        CREATE INDEX idx_merge_conflicts_operation
        ON merge_conflict_resolutions(merge_operation_id, category, field_name);

        CREATE TRIGGER merge_conflicts_no_update
        BEFORE UPDATE ON merge_conflict_resolutions
        BEGIN SELECT RAISE(ABORT, 'merge conflict resolutions are immutable'); END;
        CREATE TRIGGER merge_conflicts_no_delete
        BEFORE DELETE ON merge_conflict_resolutions
        BEGIN SELECT RAISE(ABORT, 'merge conflict resolutions cannot be deleted'); END;

        CREATE TRIGGER merge_operations_require_terminal_survivor
        BEFORE INSERT ON merge_operations
        WHEN NOT EXISTS (
            SELECT 1 FROM persons p
            WHERE p.person_id = NEW.target_person_id
              AND p.lifecycle_status = 'ACTIVE'
              AND p.deleted_at IS NULL
              AND p.canonical_person_id IS NULL
        )
        BEGIN SELECT RAISE(ABORT, 'merge survivor must be the terminal active canonical identity'); END;

        CREATE TRIGGER merge_operations_require_journal_identity
        BEFORE INSERT ON merge_operations
        WHEN NEW.merge_operation_id <> NEW.operation_journal_id
          OR NOT EXISTS (
              SELECT 1 FROM operation_journal j
              WHERE j.operation_id = NEW.operation_journal_id
                AND j.operation_type = 'identity.merge'
                AND j.status = 'STARTED'
                AND j.actor = NEW.actor
          )
        BEGIN SELECT RAISE(ABORT, 'merge manifest must match its started journal identity and actor'); END;

        CREATE TRIGGER merge_affected_items_require_started_journal
        BEFORE INSERT ON merge_affected_items
        WHEN NOT EXISTS (
            SELECT 1 FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.merge_operation_id = NEW.merge_operation_id AND j.status = 'STARTED'
        )
        BEGIN SELECT RAISE(ABORT, 'merge manifest is closed'); END;

        CREATE TRIGGER merge_conflicts_require_started_journal
        BEFORE INSERT ON merge_conflict_resolutions
        WHEN NOT EXISTS (
            SELECT 1 FROM merge_operations m
            JOIN operation_journal j ON j.operation_id = m.operation_journal_id
            WHERE m.merge_operation_id = NEW.merge_operation_id AND j.status = 'STARTED'
        )
        BEGIN SELECT RAISE(ABORT, 'merge manifest is closed'); END;

        PRAGMA user_version = 26;
        """,
    )


def _migrate_27_to_28(conn: sqlite3.Connection) -> None:
    """Restrict the shared read revision to fields visible in graph/World contracts."""
    _execute_migration_script(
        conn,
        """
        DROP TRIGGER graph_revision_person_read_fields;
        CREATE TRIGGER graph_revision_person_read_fields
        AFTER UPDATE OF name, metadata, lifecycle_status, canonical_person_id,
                        identity_status, biometric_status ON persons
        WHEN OLD.name IS NOT NEW.name
          OR OLD.lifecycle_status IS NOT NEW.lifecycle_status
          OR OLD.canonical_person_id IS NOT NEW.canonical_person_id
          OR OLD.identity_status IS NOT NEW.identity_status
          OR OLD.biometric_status IS NOT NEW.biometric_status
          OR COALESCE(json_extract(OLD.metadata, '$.country'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.country'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.rank'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.rank'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.importance'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.importance'), '')
          OR COALESCE(json_extract(OLD.metadata, '$.representative_embedding_id'), '')
             IS NOT COALESCE(json_extract(NEW.metadata, '$.representative_embedding_id'), '')
        BEGIN
            UPDATE graph_state
            SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1;
        END;

        PRAGMA user_version = 28;
        """,
    )


def _migrate_28_to_29(conn: sqlite3.Connection) -> None:
    """Keep biometric provenance and search eligibility on the existing embedding."""
    conn.execute(
        "ALTER TABLE embeddings ADD COLUMN recognition_state TEXT NOT NULL "
        "DEFAULT 'GOOD' CHECK (recognition_state IN ('GOOD', 'POOR_ACCEPTED', 'PROOF_ONLY'))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS init_sessions ("
        "session_id TEXT PRIMARY KEY, source_path TEXT NOT NULL, "
        "status TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "ALTER TABLE init_sessions ADD COLUMN quality_only INTEGER NOT NULL "
        "DEFAULT 1 CHECK (quality_only IN (0, 1))"
    )
    conn.execute("PRAGMA user_version = 29")


def _migrate_29_to_30(conn: sqlite3.Connection) -> None:
    """Extend durable review staging and retain explicit Encounter pair decisions."""
    _execute_migration_script(conn, """
        ALTER TABLE photo_reviews ADD COLUMN session_id TEXT REFERENCES init_sessions(session_id);
        ALTER TABLE photo_reviews ADD COLUMN sequence_number INTEGER;
        ALTER TABLE photo_reviews ADD COLUMN review_phase TEXT NOT NULL DEFAULT 'LEGACY'
            CHECK(review_phase IN ('LEGACY', 'WAITING', 'EVENT', 'IDENTITIES', 'RELATIONS'));
        ALTER TABLE photo_reviews ADD COLUMN event_details TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE photo_reviews ADD COLUMN event_details_complete INTEGER NOT NULL DEFAULT 0
            CHECK(event_details_complete IN (0, 1));

        CREATE TABLE init_session_media (
            session_id TEXT NOT NULL REFERENCES init_sessions(session_id) ON DELETE CASCADE,
            media_id TEXT NOT NULL,
            media_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(session_id, media_id),
            UNIQUE(session_id, media_path)
        );

        CREATE TABLE photo_review_media (
            review_id TEXT NOT NULL REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            media_id TEXT NOT NULL,
            media_path TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            PRIMARY KEY(review_id, media_id),
            UNIQUE(review_id, media_path)
        );
        INSERT INTO photo_review_media(review_id, media_id, media_path, ordinal)
        SELECT review_id, media_id, media_path, 0 FROM photo_reviews
        WHERE media_path IS NOT NULL AND TRIM(media_path) <> '';

        CREATE TABLE encounter_relation_decisions (
            decision_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL REFERENCES photo_reviews(review_id) ON DELETE RESTRICT,
            observation_id TEXT REFERENCES observations(observation_id) ON DELETE RESTRICT,
            first_ref TEXT NOT NULL,
            second_ref TEXT NOT NULL,
            first_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT,
            second_person_id TEXT REFERENCES persons(person_id) ON DELETE RESTRICT,
            disposition TEXT NOT NULL CHECK(disposition IN ('INCLUDE', 'EXCLUDE')),
            support TEXT NOT NULL CHECK(support IN ('SHARED_FRAME', 'SAME_ENCOUNTER_ONLY')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            supersedes_decision_id TEXT REFERENCES encounter_relation_decisions(decision_id),
            operation_id TEXT REFERENCES operation_journal(operation_id),
            decided_at TEXT NOT NULL,
            CHECK(first_ref < second_ref),
            CHECK(first_person_id IS NULL OR second_person_id IS NULL OR first_person_id <> second_person_id)
        );
        CREATE UNIQUE INDEX idx_encounter_relation_active_pair
        ON encounter_relation_decisions(review_id, first_ref, second_ref) WHERE active = 1;
        CREATE INDEX idx_encounter_relation_observation
        ON encounter_relation_decisions(observation_id, active, disposition);
        CREATE UNIQUE INDEX idx_photo_review_session_sequence
        ON photo_reviews(session_id, sequence_number)
        WHERE session_id IS NOT NULL;
        PRAGMA user_version = 30;
    """)


def _migrate_30_to_31(conn: sqlite3.Connection) -> None:
    _execute_migration_script(conn, """
        ALTER TABLE init_session_media ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0, 1));
        PRAGMA user_version = 31;
    """)


def _migrate_31_to_32(conn: sqlite3.Connection) -> None:
    _execute_migration_script(conn, """
        ALTER TABLE photo_reviews ADD COLUMN target_observation_id TEXT REFERENCES observations(observation_id);
        ALTER TABLE photo_reviews ADD COLUMN expected_encounter_revision TEXT;
        CREATE UNIQUE INDEX idx_active_encounter_amendment ON photo_reviews(target_observation_id)
            WHERE status = 'IN_PROGRESS' AND target_observation_id IS NOT NULL;
        CREATE TABLE encounter_participant_revisions (
            revision_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL REFERENCES observations(observation_id),
            person_id TEXT NOT NULL REFERENCES persons(person_id),
            disposition TEXT NOT NULL CHECK(disposition IN ('PRESENT', 'REMOVED')),
            operation_id TEXT NOT NULL REFERENCES operation_journal(operation_id),
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_encounter_participant_revision ON encounter_participant_revisions(observation_id, created_at);
        CREATE TABLE encounter_metadata_revisions (
            revision_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL REFERENCES observations(observation_id),
            observed_at TEXT, location TEXT, context TEXT NOT NULL,
            operation_id TEXT NOT NULL REFERENCES operation_journal(operation_id),
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_encounter_metadata_revision ON encounter_metadata_revisions(observation_id, created_at);
        CREATE VIEW effective_observations AS
            SELECT o.observation_id, o.status,
                CASE WHEN r.revision_id IS NULL THEN o.observed_at ELSE r.observed_at END AS observed_at,
                CASE WHEN r.revision_id IS NULL THEN o.location ELSE r.location END AS location,
                CASE WHEN r.revision_id IS NULL THEN o.context ELSE r.context END AS context,
                o.source, o.created_operation_id, o.created_at, o.updated_at, o.finalized_at
            FROM observations o LEFT JOIN encounter_metadata_revisions r
                ON r.rowid = (SELECT r2.rowid FROM encounter_metadata_revisions r2
                    WHERE r2.observation_id = o.observation_id ORDER BY r2.created_at DESC, r2.rowid DESC LIMIT 1);
        CREATE TRIGGER encounter_metadata_no_update BEFORE UPDATE ON encounter_metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Encounter metadata revisions are immutable'); END;
        CREATE TRIGGER encounter_metadata_no_delete BEFORE DELETE ON encounter_metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Encounter metadata revisions cannot be deleted'); END;
        CREATE TRIGGER encounter_participant_revision_no_update BEFORE UPDATE ON encounter_participant_revisions
            BEGIN SELECT RAISE(ABORT, 'Participant revisions are immutable'); END;
        CREATE TRIGGER encounter_participant_revision_no_delete BEFORE DELETE ON encounter_participant_revisions
            BEGIN SELECT RAISE(ABORT, 'Participant revisions cannot be deleted'); END;
        DROP TRIGGER observation_media_draft_insert;
        CREATE TRIGGER observation_media_draft_insert BEFORE INSERT ON observation_media
            WHEN NOT EXISTS(SELECT 1 FROM observations o WHERE o.observation_id = NEW.observation_id AND
                (o.status = 'DRAFT' OR EXISTS(SELECT 1 FROM operation_journal j JOIN photo_reviews r
                    ON r.target_observation_id = o.observation_id WHERE j.operation_id = NEW.operation_id
                    AND j.operation_type = 'review.complete' AND j.status = 'STARTED' AND r.status = 'IN_PROGRESS')))
            BEGIN SELECT RAISE(ABORT, 'observation media requires draft or journaled amendment'); END;
        DROP TRIGGER observation_participants_draft_insert;
        CREATE TRIGGER observation_participants_draft_insert BEFORE INSERT ON observation_participants
            WHEN NOT EXISTS(SELECT 1 FROM observations o WHERE o.observation_id = NEW.observation_id AND
                (o.status = 'DRAFT' OR EXISTS(SELECT 1 FROM operation_journal j WHERE j.operation_id = NEW.operation_id
                    AND j.status = 'STARTED' AND (j.operation_type = 'encounter.correct' OR
                    (j.operation_type = 'review.complete' AND EXISTS(SELECT 1 FROM photo_reviews r
                        WHERE r.target_observation_id = o.observation_id AND r.status = 'IN_PROGRESS'))))))
            BEGIN SELECT RAISE(ABORT, 'observation participants requires draft or journaled correction'); END;
        PRAGMA user_version = 32;
    """)


def _migrate_32_to_33(conn: sqlite3.Connection) -> None:
    """Extend existing scan drafts with ownership retained before planning."""
    _execute_migration_script(conn, """
        ALTER TABLE init_sessions ADD COLUMN target_observation_id TEXT REFERENCES observations(observation_id);
        ALTER TABLE init_sessions ADD COLUMN expected_encounter_revision TEXT;
        UPDATE init_sessions SET
            target_observation_id = (SELECT target_observation_id FROM photo_reviews r
                WHERE r.session_id = init_sessions.session_id AND r.target_observation_id IS NOT NULL LIMIT 1),
            expected_encounter_revision = (SELECT expected_encounter_revision FROM photo_reviews r
                WHERE r.session_id = init_sessions.session_id AND r.target_observation_id IS NOT NULL LIMIT 1);
        CREATE TRIGGER init_session_attachment_target_immutable
        BEFORE UPDATE OF target_observation_id ON init_sessions
        WHEN OLD.target_observation_id IS NOT NULL
             AND NEW.target_observation_id IS NOT OLD.target_observation_id
        BEGIN
            SELECT RAISE(ABORT, 'Attach Media target is immutable');
        END;
        PRAGMA user_version = 33;
    """)


def _require_supported_schema_version(version: int) -> None:
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than this app supports "
            f"({SCHEMA_VERSION}). Please update SentriFace."
        )
    if version < 0:
        raise RuntimeError(f"Unsupported database schema version: {version}")
