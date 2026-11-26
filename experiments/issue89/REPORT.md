# Issue #89 — Experimental permanent Event deletion: differential test report

Branch `experiment/issue-89-event-hard-deletion`, based on `v2-hardening-followups` @ `d5c710b7a2d12e142fcae7d8c1a75cc9604cbcb3` (schema v37, merge of PR #91 / Issue #90). Nothing under `src/` or `frontend/` was changed. All experimental code is in `experiments/issue89/`. This is not a production implementation and is not proposed for merge.

## 1. Outcome

- **Hard deletion can reach Database A behaviour for Events whose contributions are self-contained (S1, S2, S3).** That requires four changes to the current system, each found by experiment:
  1. guarded delete triggers (schema);
  2. a journal transition for orphaned operations;
  3. a person-activity read filter;
  4. a refresh of recognition proposals staged before the deletion.
- **In those scenarios the measured A-versus-B′ difference** is limited to security-audit rows, the graph revision counter, and the retained operation journal. Covered: 254 backend reads, every table row, decrypted media, eligibility, and genuine recognition on linear and HNSW indexes.
- **It holds over time.** The difference survived restart, graph rebuild, later normal operations, and encrypted backup and restore.
- **Hard deletion cannot reach A where later independent records were built on X's existence (S4, S5, S6, S8).** The blocking records are:
  - immutable merge manifests and operation results that counted X's items;
  - `person_change_history` rows written by X, which have no operation provenance;
  - Persons created by X who later gained independent data;
  - manual profiles whose link to X is not recorded.

  These are architectural constraints and policy questions. More coding cannot remove them.
- **The unmodified v37 schema refuses deletion (H0).** Twelve append-only triggers abort it. Deleting the rows they protect is only possible by relaxing those triggers for a journaled erasure operation.
- **Logical deletion using existing primitives fixes relationships, graph and World edges, and integrity.** It does not fix the following, all measured:
  - Events lists, search and filters;
  - sightings, presence analytics and discoveries;
  - recognition eligibility of samples owned by retained Persons;
  - physical media.

  A complete logical design therefore needs filters on about 100 read sites (source count) and on write-time derivations.

**Recommendation:** do not ship Event hard deletion in the current release window. If #89 proceeds, implement logical deletion first (Deleted Events with 30-day recovery). Then implement permanent erasure as a separate, guarded, journaled purge with the H2 mechanism, under the constraints and decisions in §9–§10.

## 2. Method and environment (executed)

- **Applications.** Every Database A and B was built through the real loopback HTTP API of `create_server(runtime="onnx")`, using the request sequence of the React Queue, People and Events UI:
  - upload-chunk, queue-scan, plan, Event details, per-face decisions, Relations, complete;
  - Attach Media, encounter-correct, merge, archive, delete;
  - Person Notes, Manual Associations, Reference Only.
  Each authority is a disposable directory with its own encrypted SQLCipher database, its own key (in a file-backed test keyring) and its own media.
- **Recognition.** Genuine InsightFace buffalo_s, admitted through the real `sentriface.model_setup` CLI as `noncommercial-research`:
  - detector `det_500m.onnx` sha256 `5e4447f5…a3a`, the same hash as the repository's `models/model-usage.json`;
  - recognizer `w600k_mbf.onnx` sha256 `9cc6e4a7…b4f`.
  No simulated recognition was used for any biometric claim.
- **Photographs.** Labeled Faces in the Wild (funneled) photographs, mapped to 14 pseudonyms (`harness/photos.py`). The kit has 162 photos:
  - 140 single-person photos;
  - 14 blurred poor-quality variants;
  - 6 composite multi-person photos (disclosed tiling);
  - 2 face-free scene photos.

  Every photo was validated with the real detector. Same-identity similarity is ≥ 0.6. The maximum cross-identity similarity is 0.19. Photos are not committed. Screenshots blur every photograph because the repository is public.
- **Determinism.** `harness/env.py` gives every fixture step a scripted clock and UUIDs keyed by (step, call site, counter). Shared steps therefore produce byte-identical IDs and timestamps in A and B. B′ is compared with A row by row, with no ID normalization. The only aliasing is Person ID→name and Event ID→occasion, used where a counterfactual step must differ. Revision-bound tokens are counted and reported.
- **Noise control** (`run_noise_control.py`). Two independent builds of the same Database A were identical except for `app_users` and `auth_audit`: wall-clock sign-in times and the argon2 salt.
- **Measurements per database** (`harness/measure.py`):
  - every row of every table;
  - decrypted SHA-256 of every managed file;
  - the eligible recognition sample set;
  - about 250–320 backend reads: People, profiles, sightings, intelligence, Person Graph, neighbours, Events with search, filter and pagination, Event detail, Deleted Faces, pending proposals, queue sessions, and World Connections, Explore and Explore-all at scope, cluster, Person, Event and relationship-evidence levels, plus Discoveries for 7, 30 and 90 days;
  - genuine recognition of 14 held-out probe photos under linear and HNSW indexes, with quality preference on and off;
  - the P11 integrity report.
- **Post-deletion checks.** Applied identically to A* and B′ (`run_scenario.post_deletion_checks`):
  - restart;
  - P11-B graph rebuild command;
  - a later Event and a Person Note;
  - encrypted backup, restore and restart.
- **Baseline suite on this branch:** `pytest` gave 1010 passed and 57 skipped (browser suites excluded), with no `src/` change.

## 3. Mechanism iterations (executed)

| Iteration | Mechanism | Measured result (S1) |
|---|---|---|
| H0 | Dependency-ordered `DELETE` plan on the unmodified v37 schema, one savepoint per statement, rolled back | Blocked. Trigger aborts: `relationship_evidence_no_delete`, `note_revision_mentions_no_delete`, `note_mentions_no_delete`, `note_revisions_no_delete`, `notes_no_delete`, `observation_face_assignments_no_delete`, `observation_participants_draft_delete`, `observation_media_draft_delete`, `observations_no_delete`. FK RESTRICT aborts follow from those: `photo_reviews` ← `observation_face_assignments.review_id`; `embeddings` ← `observation_face_assignments.embedding_id`; `persons` ← 6 child columns. Only `encounter_relation_decisions`, `recognition_details`, `photo_review_*` and `graph_connections` deleted. Completed reviews are update-immutable but not delete-protected. |
| H1 | Additive table `experimental_event_erasure_rows`, insertable only while an `event.erase` journal is STARTED. The 12 no-delete triggers are re-created with one extra condition: the row was enumerated for that STARTED operation. FKs stay ON and `foreign_key_check` runs before COMMIT. | All B′ data equal to A. **P11-JOURNAL-003 CRITICAL**: the committed `review.complete` has no `photo_reviews` result. **Encrypted backup restore of B′ refused** (HTTP 409 `backup_not_restorable`). Blocker. |
| H1b | H1, plus every operation whose linked result rows were all erased moves COMMITTED→REVERTED (an existing allowed transition) with `{"reason":"event.erase","erased_by_operation_id":…}` | S1–S3: integrity PASS and restore 200. S5 and S8: profile **activity** of surviving Persons still lists X's `encounter.correct` and legacy observation operations. S7: a staged Check-a-photo proposal ranks the erased Person (`name: "unknown"`, score 1.0). |
| H2 | H1b, plus R1 (hide erasure-reverted operations from `_list_person_operations`) and R2 (recompute staged pending-addition proposals against the rebuilt index), process-local candidate fixes in `harness/read_fixes.py` | Results in §4. |

The H2 transaction (`harness/hard_delete.py`) runs these steps:

1. `BEGIN IMMEDIATE`.
2. Check: replay, existence, `FINALIZED`, expected revision, and no pending Attach Media.
3. Plan from X's authoritative records.
4. Journal `event.erase` (STARTED).
5. Enumerate the guarded rows.
6. Ordered deletes, with each count checked against the plan.
7. Journal REVERTED transitions.
8. `_refresh_source_biometric_status`, `_replace_graph_projection`, `_validate_graph_projection`.
9. Remove the plan rows and run `PRAGMA foreign_key_check`.
10. COMMIT.

Before the transaction the existing durable `CleanupService` schedules the physical candidates. After COMMIT it runs with a live-reference re-check, and startup retries it. The route `POST /api/experimental/event-delete` is installed process-locally. It requires capability `destroy`, takes a pre-delete safety backup, and rebuilds the recognition index.

Persons created by X are identified from immutable `ACCEPT_NEW_PERSON` decisions joined to X's own face assignments. A created Person is erased only when none of 15 independent-dependency checks match, for example another Event, a Reference, a note owned or mentioned, a Manual Association, merge history, profile edits or an Event Note mention elsewhere.

## 4. Scenario results (H2 unless stated)

Every table below is generated from measurements. The full 39-measure tables, including first/last seen, recognition top-1 per probe, notes and mentions, are in `evidence/TABLES.md`. Raw diffs are in `evidence/<run>/report.json`. Rows not listed were equal.

### S1 — Newest multi-photo Event creating three Persons exclusively; sole evidence; Event and Sighting Note mentions

| Measure | Database A | Database B | Database B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Persons (lifecycle) | 9 ACTIVE | 12 ACTIVE | 9 ACTIVE | yes | Fir, Ginkgo and Kauri had no independent data and were erased |
| ENROLLED / NO_FACE | 8 / 1 | 11 / 1 | 8 / 1 | yes | |
| Events listed / sightings | 7 / 15 | 8 / 18 | 7 / 15 | yes | |
| Media refs; files (objects, crops, other) | 13; (14, 16, 2) | 15; (16, 19, 2) | 13; (14, 16, 2) | yes | Plaintext hashes identical; 2 photos and 3 crops removed |
| Eligible samples; recognition (linear and HNSW, both quality modes) | 16; probes fir/ginkgo/kauri → Alder 0.110 / Juniper 0.129 / Birch 0.215 | 19; fir→Fir 0.603, ginkgo→Ginkgo 0.605, kauri→Kauri 0.607 | 16; identical to A | yes | Genuine ONNX scores equal to 6 d.p. |
| Active evidence | CO 8, NOTE 2, MANUAL 1 | CO 11, NOTE 3, MANUAL 1 | CO 8, NOTE 2, MANUAL 1 | yes | |
| Graph rows; Person Graph edges | 10; 8 | 14; 12 | 10; 8 | yes | |
| World Connections clusters | {Alder…Elm} {Hazel, Juniper Two} {Iris, Juniper} | first cluster + Fir, Ginkgo, Kauri | = A | yes | |
| Discoveries, frequent 30 days | Birch 2, Alder 1, Dogwood 1 | + Fir, Ginkgo, Kauri 1 | = A | yes | |
| Events search "Goa" | 1 | 2 | 1 | yes | |
| API reads differing | — | 120/313 | **0/254** | yes | 12 ordering-only, see D7 |
| Integrity / restore | PASS / 200 | PASS | PASS / 200 | yes | H1 gave CRITICAL and 409 |
| Journal rows; graph revision | 12; 30 | 13; 37 | 14; 38 | no (justified) | Retained REVERTED `review.complete` plus the `event.erase` audit entry; monotonic counter |

Post-deletion checks: restart, graph rebuild (`changed: false` in both), later operations, and backup/restore gave 0 API differences, equal files and PASS each time.

### S2 — Mid-history Event of pre-existing People; repeated appearance; second observation crossing Explore threshold 2

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Persons; ENROLLED | 9; 8 | 9; 8 | 9; 8 | yes | No Person was created by X |
| Sightings; media; eligible samples | 15; 13; 16 | 17; 16; 19 | 15; 13; 16 | yes | Alder's two X samples and Cedar's one X sample were erased |
| Explore clusters (CO_OBSERVED ≥ 2) | {Alder, Birch} | {Alder, Birch, Cedar} | {Alder, Birch} | yes | X supplied the second Alder–Cedar observation |
| NOTE_REFERENCE | 2 | 3 | 2 | yes | X's Sighting Note Alder→Dogwood erased; the independent Person Note Dogwood→Alder kept |
| API differing; recognition; integrity | — | 93/259 | 0/252; equal; PASS | yes | |

### S3 — Oldest Event bridging two World clusters; excluded pair; first-seen supplier

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| World Connections clusters | {Alder…Elm} {Hazel, Juniper Two} {Iris, Juniper} | {Alder…Elm, Iris, Juniper, Kauri} {Hazel, Juniper Two} | = A | yes | The bridge Dogwood–Iris was supplied only by X |
| CO_OBSERVED | 8 | 10 | 8 | yes | Iris–Kauri was EXCLUDE, so X wrote 2 pair records, not 3 |
| First seen Dogwood / Iris | 2026-04-10 / 2026-04-25 | 2026-02-01 / 2026-02-01 | = A | yes | First seen is computed at read time |
| Persons | 9 | 10 | 9 | yes | Kauri erased |
| API differing; integrity | — | 123/279 | 0/252; PASS | yes | |

### S4 — Persons created by X that later gain independent data (counterfactual ambiguity)

The counterfactual A is the closest valid control:
- Laurel is created by the later Event Meeting-L.
- Maple and Nutmeg are created manually, then receive the same later edits, Person Note, Reference and Manual Association.

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Persons | 12 | 12 | 12 | yes (count) | X's 3 created Persons were **retained** with reasons: Laurel (another Event), Maple (profile edits and operation history), Nutmeg (Reference and Manual Association) |
| ENROLLED / NO_FACE | 10 / 2 | 11 / 1 | 10 / 2 | yes | Maple fell back to NO_FACE when X's sample was erased |
| Sightings; media; eligible | 17; 15; 19 | 21; 19; 23 | 17; 15; 19 | yes | |
| Rows differing | — | — | persons 3, embeddings 2, observation rows 1–2, `person_change_history` 6 vs 5, `person_operations` 2, journal 7 | **no** | Laurel, Maple and Nutmeg have creation time, metadata (`initial_observation` from manual create in A versus review metadata in B) and IDs from X. In B, Meeting-L recorded Laurel as `ACCEPT_EXISTING_PERSON`; in A as `ACCEPT_NEW_PERSON`. |
| API differing | — | 141/322 | 93/311 | **no** | All 93 are the retained-Person identities above and the immutable Meeting-L review history |

This is a **policy decision (P1)**, not a defect. B′ cannot equal A because A's history cannot contain "a Person created by X".

### S5 — Amended + corrected + attached X; reassigned face; participants later merged, archived and independently deleted

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Persons (lifecycle) | 6 ACTIVE, 1 ARCHIVED, 1 DELETED, 1 MERGED | 7 ACTIVE, … | = A | yes | Fir (created by X, then reassigned to Hazel) erased; Hazel kept |
| Sightings; media; eligible | 17; 13; 13 | 23; 19; 17 | 17; 13; 13 | yes | Erased: metadata revision, 2 participant revisions, 1 correction, 14 relation decisions, 40 evidence generations, attach review and session |
| World Connections / Explore | {…Elm} {Hazel, Iris, Juniper} / {Alder, Birch} | single 8-person cluster / 2 clusters | = A | yes | |
| `merge_affected_items` | 20 | 52 | **52** | **no** | The immutable merge manifest (Juniper Two→Juniper, after X) lists 32 items of X: assignment, decision, evidence and media IDs |
| Merge / delete result shown in profile activity | affected 20, evidence 10; Cedar retained_sightings 2 | 52, 20; 3 | **52, 20; 3** | **no** | Immutable operation results written while X existed |
| API differing | — | 185/284 | **8/248** (16 under H1b) | **no** | Remaining: activity of Juniper, Juniper Two and Cedar (counts above). R1 removed the Birch, Dogwood and Hazel leaks. |

This is an **architectural constraint (C2)**. Classification of the residual: historical provenance at the time of the merge or deletion. It is content-free (IDs and counts) but visible to the operator.

### S6 — Quality states; X-only GOOD sample made a Reference-only Person ENROLLED

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| ENROLLED / NO_FACE | 8 / 1 | 10 / 0 | 8 / 1 | yes | Elm returned to NO_FACE; its PROOF_ONLY Reference was preserved |
| Samples by state; eligible | GOOD 15, PROOF 1; 16 | +POOR_ACCEPTED 2, +PROOF_ONLY 1, +GOOD 1; 20 | = A | yes | |
| Recognition elm-8 / ginkgo-8 | Cedar 0.130 / Juniper 0.129 | Elm and Ginkgo strong | = A | yes | |
| `person_change_history` | 3 | 4 | **4** | **no** | X wrote Elm "placeholder→enrolled" (editor `SentriFace`). The table has no operation column, so the row cannot be attributed to X. The biometric refresh wrote no reverse row. Shown in Elm's API `changes` (2 reads). |

This is **constraint C3**.

### S7 — Shared physical media; blocked reuse; staged Check-a-photo of X's photo; reimport

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Duplicate admission in X | — | `scene` (already in Meeting-2) auto-excluded | — | n/a | The shared object stayed after deletion and Meeting-2 is intact |
| Reuse of X photo in a new Event (B only, before delete) | — | `finalized_encounter: true` | — | n/a | The product blocks "samples reused elsewhere", so that case is unreachable |
| X photo as Reference (B only) | — | HTTP 400 "Event media cannot become Reference Only" | — | n/a | Also unreachable |
| Check a photo of kauri-2 (shared step) | top Cedar 0.232 | top Kauri 1.000 | refreshed: Cedar 0.232, `unknown` decision | yes semantically | H1b left the erased Kauri ranked (D3). R2 recompute leaves residual drift: Birch 4 samples instead of 3 (a sample added later) and scores differing at 1e-8 |
| Files (objects, crops, other) | (15, 17, 3) | (17, 19, 4) | (15, 17, **4**) | **no** | The extra file is an unreferenced `uploads/batches/…` copy left by the B-only discard of the reuse attempt. This is a pre-existing cleanup gap, unrelated to deletion. The X photo object is retained because the staged review references it. |
| API differing; integrity | — | 65 | 1 (`pending`, drift above); PASS | partial | |

### S8 — Legacy media-free Event; manual profile with ambiguous provenance

The legacy Event was created through the storage domain fixture path used by `tests/test_world_graph_v2.py` and QA J02, because `FaceEngine` no longer finalizes legacy Events.

| Measure | A | B | B′ | Equivalent? | Explanation |
|---|---|---|---|---|---|
| Events; sightings; CO_OBSERVED | 7; 15; 8 | 8; 18; 11 | 7; 15; 8 | yes | 1 observation, 3 participants and 3 evidence rows erased; 2 operations reverted |
| Persons | 9 | 10 | **10** | **no** | Nutmeg was created manually the day before X. No record links it to X, so it is retained (the planner never guesses). Visible in People (10 vs 9, screenshot `S8-H2`). |
| Activity (H1b → H2) | — | — | Alder and Hazel listed X's legacy operations → removed by R1 | yes after R1 | |

This is **policy P2**: provenance of manual profiles.

### S9 — Operational edge cases (S1 world, H2, `run_operational.py`)

| Probe | Measured result | Equivalent / correct? |
|---|---|---|
| Pending Attach Media targeting X | 409 `pending_attach_media`; after `DELETE /api/queue-session` the cancelled attach review and session rows remain and are erased with X | yes |
| Viewer / operator / technician | 403 `permission_denied` each; unauthenticated 401 | yes |
| Stale request (X amended after the revision was read) | 409 `stale_revision` | yes |
| Injected failure before deleting `observation_media`, `observations` or `persons` | Rolled back; DB, files, API, recognition and integrity identical to before (3/3) | yes |
| Crash after COMMIT, before file cleanup and index rebuild | Immediately: 6 orphan files, cleanup journal pending; recognition showed no erased Person, because searches resolve owners from the DB. After restart: `CleanupService.retry_all` removed them, files 32 = 32, journal gone, A-vs-B′ API 0 differences | yes |
| Replay of the same operation ID | 200 `replayed: true`, no new backup | yes |
| New delete request for the erased Event | 409 `event_not_found` | yes |
| Restore of the pre-delete safety backup | 200; Event X and all its contributions **reappear** | expected; see P4 |

### Logical deletion (L) on the same controls

L is authority-only: a `experimental_deleted_events` row, deactivated evidence, retired Sighting Notes with a retirement revision, linked Persons moved to DELETED with 30-day `restore_until`, and biometric/graph refresh. Production reads are unmodified (`harness/logical_delete.py`). An earlier attempt to simulate full read filtering with TEMP shadow views was abandoned. Production queries depend on `rowid` and `SELECT *` row shapes, and validators share helpers with current-state reads: the graph validator rejected filtered evidence sources.

| Measure (A vs B′-L) | S1 | S2 | S4 | S5 | S6 |
|---|---|---|---|---|---|
| Relationships, graph rows, World clusters, Explore | equal | equal | equal | equal | equal |
| Integrity / restore | PASS / 200 | PASS / 200 | PASS / 200 | PASS / 200 | PASS / 200 |
| Events list / search / filters | X listed (8 vs 7) | X listed | X listed | X listed | X listed |
| Sightings (sum) | 18 vs 15 | 17 vs 15 | 21 vs 17 | 23 vs 17 | 19 vs 15 |
| Discoveries frequent (30 days) | + Fir, Ginkgo, Kauri | equal | equal | equal | Birch 3, Alder 2, + Elm, Ginkgo |
| Eligible samples / recognition | equal (Persons DELETED) | 19 vs 16 / differs | 23 vs 19 / differs | 17 vs 13 / differs | 19 vs 16, Elm stays ENROLLED / differs |
| Physical files retained | +5 | +6 | +8 | +12 | +8 |
| API reads differing | 78 | 82 | 135 | 153 | 116 |
| UI (screenshots `S1-L`) | Events shows "Event-X … Participants: Fir, Ginkgo, Kauri · Mentioned: Alder"; World Connections "Effective people 12" vs 8 | | | | |

Logical deletion preserves all history and recovers cleanly, which Issue #89 requires for Deleted Events. It is not current-state equivalent until these surfaces exclude deleted Events:
- Events reads;
- presence and frequency;
- discoveries;
- recognition eligibility;
- `_refresh_source_biometric_status`.

Source analysis: 103 query sites in `sqlite_world.py`, `sqlite_store.py`, `sqlite_helpers.py`, `graph_read_service.py` and `intelligence_service.py` reference `observations`, `observation_participants`, `effective_observations` or `FINALIZED`.

## 5. Discrepancy register

| # | Discrepancy (reproduced in) | Root cause (source) | Class | Smallest correction tested | Retest |
|---|---|---|---|---|---|
| D1 | Deletion aborted (H0, all) | 12 unconditional no-delete or draft-only triggers (`sqlite_migrations.py`) plus FK RESTRICT chain | Architectural constraint C1 | Guarded triggers bound to a STARTED `event.erase` journal (H1) | Passes, FK check clean |
| D2 | P11-JOURNAL-003 CRITICAL; backup restore refused 409 (S1-H1) | `integrity.py::_check_journal_results` expects a `photo_reviews` row for every COMMITTED `review.complete`; restore requires a clean P11 report | Defect of naive deletion | COMMITTED→REVERTED with erasure provenance (H1b) | PASS, restore 200 in all scenarios |
| D3 | Staged Check-a-photo / pending proposal ranks the erased Person (`unknown`, 1.0) (S7-H1b) | `pending_additions.matches` stores proposals computed before deletion | Defect | R2 recompute against the rebuilt index | Erased identity gone; residual drift is non-authoritative |
| D4 | Profile activity shows erased Event's operations (S5 and S8, H1b) | `SQLiteIdentityStore._list_person_operations` lists COMMITTED and REVERTED journal entries naming the Person | Defect | R1 filter erasure-reverted operations | Removed (S5 16→8, S8 leak gone) |
| D5 | Merge manifest and operation results keep X's counts (S5) | `merge_affected_items`, operation results and `person_operations.result` are immutable snapshots | Constraint C2 / policy P3 | none (rewrite forbidden) | Remains: 8 reads |
| D6 | `person_change_history` "placeholder→enrolled" from X remains (S6) | `_mark_person_enrolled` writes history without operation provenance | Constraint C3 | none without a schema change (operation_id column for future rows) | Remains: 2 reads |
| D7 | World cluster order swaps among ties (all, including order-only) | `sqlite_world.py:1062` cluster ID = hash(graph revision, …), used as the final tie-break | Existing behaviour; any write advancing the revision does the same | none needed | Classified ordering-only (6–12 reads) |
| D8 | Retained Persons created by X differ from the A control (S4) | A cannot contain "created by X"; creation provenance lives only in immutable review decisions | Policy P1 | n/a | Demonstrated |
| D9 | Manual profile created for X retained (S8) | No authoritative link | Policy P2 | n/a | Demonstrated |
| D10 | Orphan upload copy after session discard (S7, B-only probe) | Pre-existing discard/upload cleanup, unrelated to deletion | Out of scope | — | Reported |
| D11 | Immutable journal keeps X's IDs: review, media SHA-256, embedding IDs, observation ID (all); `encounter.correct.details.historical_value` keeps X's location and context (S5) | `operation_journal_identity_immutable`, `operation_journal_*_no_delete` | Constraint C4 | none | Residual scan counts in each `report.json` |

## 6. What remains in B′ (residual scan, H2)

- **S1–S4, S6, S7:** only `operation_journal.affected_entities` and status-history details still contain X tokens (review ID, media SHA-256, observation ID, embedding IDs). No names, notes text or locations remain.
- **S5:** additionally, `operation_journal.details` of X's `encounter.correct` operations contain the observation ID and the historical Event value, and 32 `merge_affected_items` rows are retained.
- **S7:** additionally, the independent staged review keeps X's photo, as intended.
- **The pre-delete safety backup and every older backup still contain X in full.** Restoring one brings X back (S9).

## 7. Paired application screenshots (photographs blurred)

`evidence/<run>/screens/{A,Bprime}/1-people … 6-check-a-photo.jpg`, rendered-text diffs in `screens/text-diff.json`. Runs: S1-H2, S3-H2, S5-H2, S6-H2, S7-H2, S8-H2, S1-L. The page captures 0 page errors in every run.

- **S1, S3, S5, S6, S7 (H2):** every screen's text is identical apart from the "last refreshed" clock. This includes Check a photo with genuine probes: fir-8 shows "No match found" in both A and B′.
- **S8 (H2):** People shows 10 vs 9 because of the retained manual Nutmeg profile.
- **S1-L:** Events lists Event-X with its participants and mention. World Connections shows "Effective people 12" vs 8.
- **API-only residuals:** the S5 and S6 differences are not visible on the captured profile screens.

## 8. Executed, source-based and untested

- **Executed:** everything in §3–§7.
- **Source-based only:**
  - the 103-site count for logical filters;
  - the stale-index explanation (DB owner resolution);
  - the fact that `completed_photo_reviews_immutable` guards UPDATE only.
- **Untested:**
  - packaged Windows build;
  - migration v37→v38 of real libraries;
  - 30-day expiry worker;
  - Event restore with conflicting reimported photos;
  - concurrency under the exclusive operation gate. The experimental route runs under the shared gate; production must join the exclusive backup gate like Delete Person.
  - very large libraries and performance. Deletion duration was not measured.

## 9. Architectural blockers to resolve before any production erasure

- **C1.** The append-only triggers need a guarded erasure exception. This is migration v38, and the P11 schema expectations must be updated.
- **C2 / C3 / C4.** Immutable merge manifests, operation results, `person_change_history` without provenance, and journal details holding Event content. Either accept them as audit provenance (content-free) or redesign: add an operation column to the change history, and introduce content-free journal redaction stubs.
- **Integrity.** JOURNAL-003 must formally accept erasure-reverted operations. Activity and proposal reads need R1 and R2.

## 10. Unresolved product decisions

- **P1.** Persons created by X who later gained independent data: keep them as they are, which is what this experiment did? Or keep them while stripping X-derived creation metadata?
- **P2.** Manual profiles without an authoritative Event link are never Event-owned. Confirm this.
- **P3.** Is retaining merge and deletion result counts that include erased items acceptable audit history, given they show in profile activity?
- **P4.** Backups taken before erasure still contain X. Decide what disclosure is required, and whether a retention policy applies.
- **P5.** Staged proposals: should they be recomputed against the current gallery (R2) or discarded?

## 11. Recommended architecture (grounded in the runs)

1. **Deleted Events first (logical).** Add an Event lifecycle with `restore_until`. Reuse the L writes: evidence deactivation, Sighting Note retirement, linked-Person DELETED, and biometric and graph refresh. Add filters to every Events, presence, discovery and eligibility read, plus `_refresh_source_biometric_status`, guided by the L leak list. The S1–S6 controls give a ready regression oracle.
2. **Permanent erasure as a separate guarded purge (the H2 shape).** It needs:
   - the v38 guarded triggers and the erasure-row table;
   - planning from authoritative records only, using the 15 dependency checks;
   - one IMMEDIATE transaction with journal, ordered deletes and a count check;
   - REVERTED transitions with provenance;
   - biometric, graph and FK validation;
   - a CleanupService journal scheduled before the transaction and retried at startup;
   - an index rebuild;
   - R1 and R2;
   - a refusal while Attach Media is pending.
3. **Keep the differential harness as an acceptance gate.** The required result is A vs B′ = only security, revision and journal rows, for S1–S3 and any new scenario.

## 12. Reproduction

```bash
cd sentri-face-edge
experiments/issue89/fetch_assets.sh                       # buffalo_s + LFW (research use; not committed)
python -m experiments.issue89.harness.photos /projects/sandbox/kit
python -m experiments.issue89.run_noise_control
for s in S1 S2 S3 S4 S5 S6 S7 S8; do python -m experiments.issue89.run_scenario $s --variant H2; done
python -m experiments.issue89.run_scenario S1 --variant H1   # iteration evidence (likewise H1b, L)
python -m experiments.issue89.run_operational
python -m experiments.issue89.summarize > experiments/issue89/evidence/TABLES.md
PLAYWRIGHT_BROWSERS_PATH=... python -m experiments.issue89.browser_verify S1:H2 S5:H2 S6:H2   # after the matching run
```

The recorded environment was Linux, Python 3.12.15, onnxruntime 1.32.0, numpy 1.26.4, OpenCV 4.11.0 and Playwright Chromium 1255. Each scenario takes about 4 minutes, including post-checks. Environment variables: `ISSUE89_RUNS` (authorities), `ISSUE89_KIT` and `ISSUE89_KEYRING`. Evidence files are under `experiments/issue89/evidence/`.
