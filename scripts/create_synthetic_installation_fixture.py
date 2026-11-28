"""Create a populated disposable synthetic SentriFace library for installer rehearsal.

This fixture uses generated identities and media only. It must never be pointed at
or merged into real operator data.
"""
from __future__ import annotations

import argparse
import base64
import uuid
from pathlib import Path

from sentriface.auth import AuthService
from sentriface.backup_service import BackupService
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.secure_files import write_protected_bytes
from sentriface.secure_storage import load_or_create_master_key
from sentriface.storage.sqlite_store import SQLiteIdentityStore

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
ACTOR = {"user_id": "fixture", "username": "synthetic-fixture"}


def _operation(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sentriface-fixture:{label}"))


def create_fixture(data_dir: Path) -> dict[str, object]:
    data_dir = data_dir.resolve()
    database = data_dir / "sentriface.db"
    if database.exists():
        raise RuntimeError(f"Refusing to overwrite existing SentriFace database: {database}")
    data_dir.mkdir(parents=True, exist_ok=True)
    key = load_or_create_master_key(data_dir)
    store = SQLiteIdentityStore(database, database_key=key)
    store.initialize()
    try:
        people = {
            name: store.create_person(name, metadata={"role": "synthetic-release-fixture"})
            for name in ("Avery Stone", "Blair Rivers", "Casey Morgan", "Devon Archived", "Emery Deleted")
        }
        fixture_media = []
        for index, person in enumerate(people.values(), start=1):
            media = data_dir / "faces" / "fixture" / f"{index}-{person.name.replace(' ', '-').lower()}.png"
            write_protected_bytes(media, PNG_1X1 + bytes([index]), key)
            fixture_media.append(media)
            vector = [float(index) / 100.0] * 512
            store.add_embedding(
                person.person_id,
                vector,
                quality_score=0.91,
                source_image=str(media),
                crop_path=str(media),
            )
        first, second, third = people["Avery Stone"], people["Blair Rivers"], people["Casey Morgan"]
        store.update_person_profile(
            first.person_id,
            first.name,
            "Analyst",
            "GB",
            "HIGH",
            "synthetic-fixture",
            tags=["fixture", "release"],
            operation_id=_operation("profile"),
            actor=ACTOR,
            source="installer-fixture",
        )
        store.create_note(
            first.person_id,
            "Synthetic release note referencing @[Blair Rivers].",
            _operation("note"),
            mentioned_person_ids=[second.person_id],
            actor=ACTOR,
            source="installer-fixture",
        )
        store.create_manual_association(
            first.person_id,
            second.person_id,
            _operation("manual-association"),
            actor=ACTOR,
            source="installer-fixture",
        )
        observation = store.create_observation(
            _operation("event"),
            observed_at="2026-01-15T10:30:00Z",
            location="Synthetic Site",
            context={"occasion": "Installer rehearsal"},
            source="installer-fixture",
            actor=ACTOR,
            participant_ids=[first.person_id, second.person_id, third.person_id],
            media=[{"media_id": "fixture-event-media", "media_path": str(fixture_media[0])}],
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id,
            _operation("event-finalize"),
        )
        GlobalIdentityGraphService(store).record_observation_evidence(
            observation.observation_id,
            _operation("event-evidence"),
        )
        store.archive_person(
            people["Devon Archived"].person_id,
            _operation("archive"),
            actor=ACTOR,
            source="installer-fixture",
        )
        store.soft_delete_person(
            people["Emery Deleted"].person_id,
            _operation("delete"),
            actor=ACTOR,
            source="installer-fixture",
        )
        auth = AuthService(database, key)
        owner, _token = auth.signup_initial(
            "fixture-owner",
            "Synthetic Fixture Owner",
            "fixture-owner-passphrase-1",
        )
        backup = BackupService(
            database,
            data_dir / "backups",
            data_dir=data_dir,
            database_key=key,
        ).create_backup(reason="installer-rehearsal-fixture", operation_id=_operation("backup"))
        return {
            "data_dir": str(data_dir),
            "people": len(people),
            "observation_id": observation.observation_id,
            "owner_user_id": owner.user_id,
            "backup_id": backup.backup_id,
        }
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    result = create_fixture(args.data_dir)
    print("Created disposable synthetic SentriFace fixture:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print("  username: fixture-owner")
    print("Never use this destructive rehearsal fixture with real operator data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
