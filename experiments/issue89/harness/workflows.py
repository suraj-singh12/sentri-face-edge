"""Operator workflows driven through the real HTTP API (no direct SQL writes)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from .app import KIT, ApiError, App


def kit_manifest() -> dict:
    return json.loads((KIT / "kit.json").read_text())["photos"]


@dataclass
class EventSpec:
    """One Queue Event, described by operator decisions (not by recognition).

    ``faces`` overrides per identity: ``"new"`` (Create Person), ``"existing"``
    (Use Existing), ``"exclude"`` (final negative decision). Default: existing
    when a Person with that name already exists, otherwise new.
    ``quality``: identity -> GOOD / POOR_ACCEPTED / PROOF_ONLY.
    ``relations``: frozenset({a, b}) -> INCLUDE/EXCLUDE (default INCLUDE).
    ``sighting_notes``: identity -> (text, [mentioned names]).
    """

    label: str
    photos: list[str]
    date: str
    location: str
    occasion: str
    time: str = ""
    time_precision: str = "unknown"
    event_notes: str = ""
    event_mentions: list[str] = field(default_factory=list)
    faces: dict[str, str] = field(default_factory=dict)
    quality: dict[str, str] = field(default_factory=dict)
    relations: dict = field(default_factory=dict)
    sighting_notes: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    context: str = "ordinary"
    assign: dict[str, str] = field(default_factory=dict)   # identity -> existing Person name


class Operator:
    def __init__(self, app: App):
        self.app = app
        self.recognition_log: list[dict] = []

    # ------------------------------------------------------------- lookups
    def person_id(self, name: str, *, required=True) -> str | None:
        with self.app.store._connect() as conn:
            rows = conn.execute("SELECT person_id FROM persons WHERE name = ? AND lifecycle_status <> 'MERGED' ORDER BY created_at", (name,)).fetchall()
        if not rows:
            if required:
                raise KeyError(name)
            return None
        return rows[0][0]

    def event_id(self, occasion: str) -> str:
        with self.app.store._connect() as conn:
            rows = conn.execute("SELECT observation_id, context FROM observations WHERE status='FINALIZED'").fetchall()
        for oid, context in rows:
            if json.loads(context or "{}").get("occasion") == occasion:
                return oid
        raise KeyError(occasion)

    def revision(self, observation_id: str) -> str:
        return self.app.get(f"/api/encounter?observation_id={observation_id}")["revision"]

    # -------------------------------------------------------------- Events
    def _face_identities(self, scan: dict) -> dict[str, str]:
        """Map init_face_id -> fixture identity from photo content + box order."""
        manifest = kit_manifest()
        by_sha = {entry["sha256"]: entry for entry in manifest.values()}
        faces_by_media: dict[str, list[dict]] = {}
        for group in scan["groups"]:
            for face in group["faces"]:
                faces_by_media.setdefault(face["source_image"], []).append(face)
        identities = {}
        for media_path, faces in faces_by_media.items():
            sha = media_path.rsplit("/", 1)[-1].split(".")[0]
            entry = by_sha[sha]
            ordered = sorted(faces, key=lambda f: f["box"]["x"])
            assert len(ordered) == len(entry["faces"]), (entry, len(ordered))
            for face, identity in zip(ordered, entry["faces"]):
                identities[face["init_face_id"]] = identity
        return identities

    def create_event(self, spec: EventSpec, *, finish=True, attach_to: str | None = None) -> dict:
        app = self.app
        revision = self.revision(attach_to) if attach_to else None
        scan = app.scan(spec.photos, target=attach_to, revision=revision)
        session = scan["session_id"]
        identities = self._face_identities(scan)
        media = app.get(f"/api/queue-encounters?session_id={session}")["media"]
        media_ids = [m["media_id"] for m in media if not m["excluded"] and not m["finalized_encounter"]]
        duplicates = [m["media_id"] for m in media if m["finalized_encounter"]]
        if attach_to:
            reviews = app.post("/api/encounter-attach-media", {"observation_id": attach_to, "session_id": session,
                                                               "expected_revision": revision, "media_ids": media_ids})["reviews"]
        else:
            reviews = app.post("/api/queue-encounters-plan", {"session_id": session, "media_groups": [media_ids]})["reviews"]
        review_id = reviews[0]["review_id"]
        if not attach_to:
            app.post("/api/queue-encounter-event", {"review_id": review_id, "event_details": {
                "date": spec.date, "time": spec.time, "end_time": "", "time_precision": spec.time_precision,
                "place_seen": spec.location, "event_occasion": spec.occasion, "event_context": spec.context,
                "event_notes": spec.event_notes,
                "event_mentioned_person_ids": [self.person_id(n) for n in spec.event_mentions]}})
        if not finish:
            return {"session_id": session, "review_id": review_id, "pending": True}
        groups = app.get(f"/api/queue-groups?session_id={session}")["groups"]
        noted = set()
        for group in groups:
            for face in group["faces"]:
                identity = identities[face["init_face_id"]]
                self.recognition_log.append({"event": spec.label, "identity": identity, "quality": face["quality"]["status"],
                                             "top_matches": [(m["name"], round(m["score"], 4), m["classification"]) for m in face["matches"][:3]],
                                             "group_matches": [(m["name"], round(m["score"], 4)) for m in group.get("matches", [])[:3]]})
                target = spec.assign.get(identity, identity)
                mode = spec.faces.get(identity) or ("existing" if self.person_id(target, required=False) else "new")
                payload = {"review_id": review_id, "face_ids": [face["init_face_id"]],
                           "recognition_detail": {"added_by": "Fixture Custodian", "individual_count": 0}}
                state = spec.quality.get(identity) or ("POOR_ACCEPTED" if face["quality"]["status"] == "bad" else "GOOD")
                if mode == "exclude":
                    payload["decision"] = "EXCLUDE"
                else:
                    payload["quality_choices"] = {face["init_face_id"]: state}
                    if mode == "new":
                        payload.update(decision="ACCEPT_NEW_PERSON", new_person_key=f"{spec.label}:{identity}", new_person_name=identity,
                                       new_person_metadata={"rank": "", "country": "", "importance": "", "added_by": "Fixture Custodian"})
                    else:
                        payload.update(decision="ACCEPT_EXISTING_PERSON", person_id=self.person_id(target))
                    if identity in spec.sighting_notes and identity not in noted:
                        text, mentions = spec.sighting_notes[identity]
                        payload.update(notes=text, mentioned_person_ids=[self.person_id(n) for n in mentions])
                        noted.add(identity)
                try:
                    app.post("/api/queue-encounter-decision", payload)
                except ApiError as exc:
                    if "duplicate" in json.dumps(exc.payload).lower() and mode == "new":
                        payload["recognition_detail"]["proof_only_duplicate_override"] = True
                        app.post("/api/queue-encounter-decision", payload)
                    else:
                        raise
        ready = app.post("/api/queue-encounter-identities-complete", {"review_id": review_id})["review"]
        names = {}
        for candidate in ready.get("relation_candidates", []):
            pair = frozenset({candidate["first_name"], candidate["second_name"]})
            disposition = spec.relations.get(pair, "INCLUDE")
            names["|".join(sorted(pair))] = (disposition, candidate["support"])
            app.post("/api/queue-encounter-relation", {"review_id": review_id, "first_ref": candidate["first_ref"],
                                                       "second_ref": candidate["second_ref"], "disposition": disposition})
        operation_id = str(uuid.uuid4())
        completed = app.post("/api/queue-encounter-complete", {"review_id": review_id, "operation_id": operation_id})
        return {"observation_id": completed["result"].get("observation_id"), "operation_id": operation_id,
                "review_id": review_id, "session_id": session, "relations": names, "duplicates_excluded": duplicates,
                "result": completed["result"]}

    # ------------------------------------------------------------- People
    def create_person(self, name: str, *, seen_date="2025-01-01", place="Unknown"):
        return self.app.post("/api/person-create", {"name": name, "rank": "-", "country": "-", "importance": "-", "tags": [],
                                                    "added_by": "Fixture Custodian", "seen_date": seen_date, "seen_time": "12:00",
                                                    "place_seen": place, "individual_count": 0, "event_occasion": "Manual profile",
                                                    "operation_id": str(uuid.uuid4())})

    def person_note(self, name: str, text: str, mentions: list[str] = ()):  # Person (profile) Note
        pid = self.person_id(name)
        previous = self.app.get(f"/api/person?person_id={pid}")["person"].get("notes", "")
        return self.app.post("/api/person-notes", {"person_id": pid, "notes": text, "expected_previous_notes": previous,
                                                   "mentioned_person_ids": [self.person_id(n) for n in mentions],
                                                   "operation_id": str(uuid.uuid4())})

    def edit_profile(self, name: str, *, rank="Edited rank", tags=("edited",)):
        pid = self.person_id(name)
        return self.app.post("/api/person-update", {"person_id": pid, "name": name, "rank": rank, "country": "-",
                                                    "importance": "-", "tags": list(tags), "operation_id": str(uuid.uuid4())})

    def manual_association(self, a: str, b: str):
        return self.app.post("/api/person-association", {"first_person_id": self.person_id(a), "second_person_id": self.person_id(b),
                                                         "operation_id": str(uuid.uuid4())})

    def add_reference(self, name: str, photo: str, state="GOOD"):
        path = self.app.upload([photo])
        pid = self.person_id(name)
        review = self.app.post("/api/reference-prepare", {"path": path, "person_id": pid})
        return self.app.post("/api/reference-confirm", {"review_id": review["review_id"], "person_id": pid,
                                                        "operation_id": str(uuid.uuid4()), "no_context_acknowledged": True,
                                                        "recognition_state": state})

    def merge(self, source: str, target: str):
        return self.app.post("/api/person-merge", {"source_person_id": self.person_id(source), "target_person_id": self.person_id(target),
                                                   "operation_id": str(uuid.uuid4()), "reason": "Fixture merge"})

    def archive(self, name: str):
        return self.app.post("/api/person-archive", {"person_id": self.person_id(name), "operation_id": str(uuid.uuid4())})

    def delete_person(self, name: str):
        return self.app.post("/api/person-purge", {"person_id": self.person_id(name), "operation_id": str(uuid.uuid4())})

    def correct_event(self, occasion: str, **values):
        oid = self.event_id(occasion)
        return self.app.post("/api/encounter-correct", {"observation_id": oid, "operation_id": str(uuid.uuid4()),
                                                        "expected_revision": self.revision(oid), **values})

    def reassign(self, occasion: str, source: str, target: str):
        return self.correct_event(occasion, participant_correction={"action": "REASSIGN", "person_id": self.person_id(source),
                                                                    "to_person_id": self.person_id(target)})

    def amend_location(self, occasion: str, location: str):
        return self.correct_event(occasion, event_details={"place_seen": location})
