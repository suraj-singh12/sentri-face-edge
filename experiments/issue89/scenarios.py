"""Issue #89 scenario fixtures.

Every scenario = shared base world + (Database B only) Event X and its
contributions + shared later operations. Shared steps carry identical step
labels/clock slots in A and B, so their identifiers and timestamps match.
Where the counterfactual later operation must differ in A (because X never
existed), the scenario says so explicitly in ``counterfactual``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .harness.env import DET
from .harness.photos import composite
from .harness.app import KIT
from .harness.workflows import EventSpec, Operator

PROBES = [f"{n}-8" for n in ("alder", "birch", "cedar", "dogwood", "elm", "fir", "ginkgo", "hazel", "iris", "juniper",
                              "kauri", "laurel", "maple", "nutmeg")]


def step(label, at):
    return DET.step(label, at)


def pair(*parts):
    name = "+".join(parts)
    composite(KIT, name, list(parts))
    return name


def base(op: Operator):
    """Shared base world (identical in every Database A and B)."""
    with step("base.1", "2026-03-02T09:00:00+00:00"):
        op.create_event(EventSpec("base.1", ["alder-0", "birch-0"], "2026-03-02", "Delhi", "Meeting-1",
                                  time="09:00", time_precision="exact", event_notes="Quarterly meeting"))
    with step("base.2", "2026-03-20T09:00:00+00:00"):
        op.create_event(EventSpec("base.2", [pair("alder-1", "cedar-1"), "scene"], "2026-03-20", "Pune", "Meeting-2"))
    with step("base.3", "2026-04-10T09:00:00+00:00"):
        op.create_event(EventSpec("base.3", [pair("birch-2", "cedar-2", "dogwood-2")], "2026-04-10", "Mumbai", "Meeting-3",
                                  relations={frozenset({"Birch", "Dogwood"}): "EXCLUDE"},
                                  sighting_notes={"Cedar": ("Spoke about @Alder", ["Alder"])}))
    with step("base.5", "2026-04-25T09:00:00+00:00"):
        op.create_event(EventSpec("base.5", ["iris-0", "juniper-0"], "2026-04-25", "Delhi", "Meeting-5"))
    with step("base.6", "2026-04-28T09:00:00+00:00"):
        op.create_event(EventSpec("base.6", ["hazel-1", "juniper-3"], "2026-04-28", "Pune", "Meeting-6",
                                  faces={"Juniper": "new"}))
        # The second Juniper photo was (deliberately) saved as a separate new Person
        # "Juniper" duplicate; rename via profile edit to "Juniper Two".
        dup = [p for p in op.app.get("/api/persons")["persons"] if p["name"] == "Juniper"]
        newest = sorted(dup, key=lambda p: p["created_at"])[-1]
        op.app.post("/api/person-update", {"person_id": newest["person_id"], "name": "Juniper Two", "rank": "-", "country": "-",
                                           "importance": "-", "tags": [], "operation_id": str(__import__("uuid").uuid4())})
    with step("base.7", "2026-04-29T09:00:00+00:00"):
        op.create_person("Elm")
        op.add_reference("Elm", "elm-blur", state="PROOF_ONLY")
        op.person_note("Dogwood", "Knows @Alder from work", ["Alder"])
        op.manual_association("Cedar", "Elm")
    with step("base.4", "2026-05-10T09:00:00+00:00"):
        op.create_event(EventSpec("base.4", ["alder-2", "birch-3"], "2026-05-10", "Goa", "Meeting-4"))


@dataclass
class Scenario:
    sid: str
    title: str
    x_occasion: str
    covers: list[str]
    x: Callable[[Operator], None]
    post: Callable[[Operator, str], None] = lambda op, variant: None
    counterfactual: str = "Database A = base world + identical later operations; X never executed."
    notes: list[str] = field(default_factory=list)
    before_delete: Callable | None = None


# --------------------------------------------------------------------- S1
def s1_x(op):
    with step("X", "2026-05-20T09:00:00+00:00"):
        op.create_event(EventSpec("X", [pair("fir-0", "ginkgo-0"), "kauri-0"], "2026-05-20", "Goa", "Event-X",
                                  event_notes="Unscheduled visit, @Alder named", event_mentions=["Alder"],
                                  sighting_notes={"Fir": ("Asked for @Birch", ["Birch"])}))


def s1_post(op, variant):
    with step("post.1", "2026-05-25T09:00:00+00:00"):
        op.create_event(EventSpec("post.1", ["birch-4", "dogwood-4"], "2026-05-25", "Mumbai", "Meeting-7"))


# --------------------------------------------------------------------- S2
def s2_x(op):
    with step("X", "2026-04-20T09:00:00+00:00"):
        op.create_event(EventSpec("X", ["alder-3", "alder-4", "cedar-3"], "2026-04-20", "Delhi", "Event-X",
                                  sighting_notes={"Alder": ("Discussed @Dogwood", ["Dogwood"])}))


# --------------------------------------------------------------------- S3
def s3_x(op):
    with step("X", "2026-02-01T09:00:00+00:00"):
        op.create_event(EventSpec("X", [pair("dogwood-5", "iris-5"), "kauri-1"], "2026-02-01", "Mumbai", "Event-X",
                                  relations={frozenset({"Iris", "Kauri"}): "EXCLUDE"}))


# --------------------------------------------------------------------- S4
def s4_x(op):
    with step("X", "2026-04-05T09:00:00+00:00"):
        op.create_event(EventSpec("X", ["laurel-0", "maple-0", "nutmeg-0", "alder-6"], "2026-04-05", "Pune", "Event-X"))


def s4_post(op, variant):
    with step("post.L", "2026-04-15T09:00:00+00:00"):
        op.create_event(EventSpec("post.L", ["laurel-1", "birch-5"], "2026-04-15", "Goa", "Meeting-L"))
    with step("post.M", "2026-04-16T09:00:00+00:00"):
        if variant == "A":
            op.create_person("Maple")          # counterfactual: Maple can only exist as a manual profile
        op.edit_profile("Maple", rank="Analyst", tags=("watch",))
        op.person_note("Maple", "Maple profile note about @Cedar", ["Cedar"])
    with step("post.N", "2026-04-17T09:00:00+00:00"):
        if variant == "A":
            op.create_person("Nutmeg")
        op.add_reference("Nutmeg", "nutmeg-1", state="GOOD")
        op.manual_association("Nutmeg", "Birch")
    s1_post(op, variant)


# --------------------------------------------------------------------- S5
def s5_x(op):
    with step("X", "2026-04-18T09:00:00+00:00"):
        op.create_event(EventSpec("X", [pair("birch-6", "dogwood-6"), "fir-1", "juniper-5", "cedar-6"], "2026-04-18", "Mumbai",
                                  "Event-X", assign={"Juniper": "Juniper Two"}))
    with step("X.amend", "2026-04-19T09:00:00+00:00"):
        op.amend_location("Event-X", "Goa")
    with step("X.reassign", "2026-04-19T10:00:00+00:00"):
        op.reassign("Event-X", "Fir", "Hazel")
    with step("X.attach", "2026-04-19T11:00:00+00:00"):
        op.create_event(EventSpec("X.attach", ["hazel-2", "scene-2"], "", "", ""), attach_to=op.event_id("Event-X"))


def s5_post(op, variant):
    with step("post.merge", "2026-05-12T09:00:00+00:00"):
        op.merge("Juniper Two", "Juniper")
    with step("post.archive", "2026-05-12T10:00:00+00:00"):
        op.archive("Dogwood")
    with step("post.delete", "2026-05-12T11:00:00+00:00"):
        op.delete_person("Cedar")
    s1_post_without_dogwood(op, variant)


def s1_post_without_dogwood(op, variant):
    with step("post.1", "2026-05-25T09:00:00+00:00"):
        op.create_event(EventSpec("post.1", ["birch-4", "elm-4"], "2026-05-25", "Mumbai", "Meeting-7"))


# --------------------------------------------------------------------- S6
def s6_x(op):
    with step("X", "2026-05-05T09:00:00+00:00"):
        op.create_event(EventSpec("X", ["alder-blur", "birch-7", "elm-0", "ginkgo-1"], "2026-05-05", "Delhi", "Event-X",
                                  quality={"Alder": "POOR_ACCEPTED", "Birch": "PROOF_ONLY", "Elm": "GOOD", "Ginkgo": "POOR_ACCEPTED"}))


# --------------------------------------------------------------------- S7
def s7_x(op):
    with step("X", "2026-05-12T09:00:00+00:00"):
        result = op.create_event(EventSpec("X", ["kauri-2", "maple-1", "scene", "scene-2"], "2026-05-12", "Pune", "Event-X"))
    op.probes = {"X.duplicates_excluded_at_creation": result["duplicates_excluded"]}
    with step("X.reuse", "2026-05-13T09:00:00+00:00"):
        scan = op.app.scan(["kauri-2"])
        media = op.app.get(f"/api/queue-encounters?session_id={scan['session_id']}")["media"]
        op.probes["X.photo_reuse_in_new_event"] = [{"finalized_encounter": bool(m["finalized_encounter"]), "excluded": m["excluded"]} for m in media]
        op.app.request("DELETE", f"/api/queue-session?session_id={scan['session_id']}")
    with step("X.reference", "2026-05-13T10:00:00+00:00"):
        status, payload = op.app.request("POST", "/api/reference-prepare", {"path": op.app.upload(["kauri-2"]), "person_id": op.person_id("Kauri")}, expect=None)
        op.probes["X.photo_as_reference"] = {"status": status, "error": payload.get("error") if isinstance(payload, dict) else payload}
        if status == 200:
            op.app.post("/api/reference-cancel", {"review_id": payload["review_id"]})


def s7_post(op, variant):
    with step("post.check", "2026-05-20T09:00:00+00:00"):
        status, payload = op.app.request("POST", "/api/recognize", {"path": op.app.upload(["kauri-2"]), "quality_only": True}, expect=None)
        op.probes = getattr(op, "probes", {})
        op.probes["post.check_a_photo"] = {"status": status, "matches": [[(m["name"], round(m["score"], 4)) for m in f["matches"]] for f in payload.get("faces", [])]}
    s1_post(op, variant)


# --------------------------------------------------------------------- S8
def s8_x(op):
    with step("X.manual", "2026-01-14T09:00:00+00:00"):
        op.create_person("Nutmeg")      # manual profile created "for" the legacy Event (no authoritative link)
    with step("X", "2026-01-15T09:00:00+00:00"):
        # Legacy Events can no longer be finalized through FaceEngine; use the same
        # storage-domain fixture path as tests/test_world_graph_v2.py::_observe and QA J02.
        import uuid as _uuid
        from sentriface.graph_service import GlobalIdentityGraphService
        store = op.app.store
        observation = store.create_observation(str(_uuid.uuid4()), observed_at="2026-01-15T10:00:00+00:00", location="Delhi",
                                               context={"occasion": "Event-X"},
                                               participant_ids=[op.person_id("Alder"), op.person_id("Hazel"), op.person_id("Nutmeg")])
        store._finalize_observation_without_graph_evidence(observation.observation_id, str(_uuid.uuid4()))
        GlobalIdentityGraphService(store).record_observation_evidence(observation.observation_id, str(_uuid.uuid4()))


SCENARIOS = {
    "S1": Scenario("S1", "Newest multi-photo Event creating three Persons exclusively; sole relationship evidence",
                   "Event-X", ["multi-person", "multiple photos", "shared-frame + same-event-only", "newest Event / last seen",
                               "Persons created exclusively by X", "X sole evidence", "Event Note mention", "Sighting Note NOTE_REFERENCE",
                               "exclusively owned photos and crops"], s1_x, s1_post),
    "S2": Scenario("S2", "Mid-history Event of pre-existing People; repeated appearance; supplies 1 of 2 observations crossing Explore threshold",
                   "Event-X", ["pre-existing participants", "repeated appearance of same Person", "Event between earlier and later Events",
                               "X contributes one of several observations", "X makes a relationship reach strength 2",
                               "Sighting Note mention towards an existing Person-Note relationship"], s2_x, s1_post),
    "S3": Scenario("S3", "Oldest Event bridging two World clusters; excluded pair; first-seen supplier; mixed new/existing",
                   "Event-X", ["oldest Event / first seen", "X connects independent clusters", "included and excluded pairs",
                               "shared-frame evidence", "Person created exclusively by X alongside pre-existing"], s3_x, s1_post),
    "S4": Scenario("S4", "Persons created by X that later acquire independent data (appearance, edits, notes, Reference, Manual Association)",
                   "Event-X", ["Person created by X but subsequently appearing elsewhere", "subsequent profile edits and Person Notes",
                               "additional Reference Only sample", "Manual Association", "pre-existing participant"], s4_x, s4_post,
                   counterfactual=("Database A cannot contain 'Person created by X'. A uses the closest valid control: Laurel is created "
                                   "by the later Event; Maple and Nutmeg are created manually (person-create) before the same later "
                                   "edits/Reference/association. Remaining differences are the product-policy question.")),
    "S5": Scenario("S5", "Amended + corrected + attached Event; reassigned face; participants later merged, archived and independently deleted",
                   "Event-X", ["corrected and amended Event (metadata revision)", "reassigned faces / corrected participant",
                               "Attach Media incl. supporting photo without faces", "merged Person", "archived Person",
                               "independently deleted Person", "Person created by X then reassigned away"], s5_x, s5_post),
    "S6": Scenario("S6", "Biometric quality states; X-only GOOD sample makes a NO_FACE Reference-only Person ENROLLED",
                   "Event-X", ["POOR_ACCEPTED and PROOF_ONLY samples", "recognition eligibility", "biometric availability NO_FACE/ENROLLED",
                               "independent Reference Only sample preserved", "representative photographs", "linear and HNSW indexes"], s6_x, s1_post),
    "S7": Scenario("S7", "Shared physical media, blocked reuse, Check a Photo staging of X's photo, reimport after deletion",
                   "Event-X", ["shared physical media (exact duplicate scene)", "photo reuse in new Event blocked", "photo reuse as Reference blocked",
                               "photo subsequently referenced by an independent staged review", "reimport after deletion", "media registry closure"],
                   s7_x, s7_post),
    "S8": Scenario("S8", "Legacy media-free Event created through the domain service; manual profile with ambiguous creation provenance",
                   "Event-X", ["legacy Event (no review / no media)", "ambiguous creation provenance", "oldest Event"], s8_x, s1_post,
                   counterfactual="A = base + later ops; the manual profile 'Nutmeg' exists only in B (created for X but not linked to it)."),
}
