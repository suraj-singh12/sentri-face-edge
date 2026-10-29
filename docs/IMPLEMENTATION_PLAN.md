# Global identity graph implementation plan

## Issue #22 — corrected World participation (review pending)

Foundation #23 merged as `6a9ec8250561154157fbc5d45fb03857d4d1687c`
following five successful jobs at head `6eda54a59bb795458ed116350289e985a7d49675`;
#17 is closed. Identity and Period changes still require separate operator merges.

Reproduced eight failing assertions against untouched hardening `f907073` with
fixed `as_of=2026-10-29T12:00:00Z`: E1 B/Delhi/Oct 27 12:00 and E2 A/Agra/Oct 28
12:00; Move Face appends FACE_ASSIGNMENT A→B. Inspector/People correctly retain
E1+E2 for B. Frequent retains A, Recent reports A, Multiple Locations omits B.
World scoped presence/activity, overview activity, focused event membership and
World event inspector also retain A in independent single-E2 probes. The existing
stored-revision Encounter REASSIGN command already passes this minimal discovery
case because it additionally records raw target participation and explicit revisions.
Do not conflate the two supported historical paths.

The read fix reuses `_batch_effective_observation_person_ids` for amended events,
exposing their effective raw membership to existing SQL consumers. Unamended events
retain indexed raw membership; canonical resolution/deduplication follows correction
interpretation. Discoveries join disjoint unamended/amended sources separately;
overview retains its fast aggregate and selectively replaces affected counts.
There is no schema, write, cache, journal, evidence-authority or permission change.
World event inspection now recognizes face corrections without requiring an explicit
participant revision. Existing evidence endpoint interpretation is preserved:
correction commands regenerate active evidence, and bounded probes verify actual
endpoints/source Encounters instead of remapping raw evidence speculatively.

Permanent regressions in `tests/test_world_intelligence.py` cover independent
before/after E1/E2 truth, correction chains and reversals, multiple independent faces,
explicit add/remove precedence, canonical occurrence deduplication, archive/delete
history, repeated reads, reopen/rebuild, encrypted backup/import/restore and immutable
correction/evidence IDs. Legacy and current finalized review helpers are reused;
no manufactured final projection is used for correctness. Modern explicit Relations
continue to reject an unsupported Move Face when its pairs would become invalid;
use the revision-bound Encounter REASSIGN command for that scenario. No relation
semantics are expanded by this read correction.

Exact-SHA checks, measured performance and combined Period acceptance belong to the
linked PR and #22 evidence. PR #15 stays independent; #13 remains open for Explore UI.

## Issue #13 — bounded backend Period correction (review pending)

Based on refreshed hardening `f907073edc3375dbfd15b8bb39cc6d32bc60f6b6`.
Multiple Locations now shares Frequent’s validated `discovery_period_days`
(7/30/90, default 30), replacing its fixed 30-day override. This supersedes the
original Issue #3 fixed-window behavior; historical acceptance records remain intact.
Recent and all graph/cluster/evidence/proof/inspector semantics remain independent.
No UI, schema, storage authority, worker or API changes. Independent frozen-SHA
adversarial QA and explicit merge authorization remain pending.

Regression coverage extends existing World intelligence fixtures for distinct windows,
default equivalence, UTC microsecond boundaries/offsets, normalization/support caps,
corrections/merges, cursor/filter/revision binding, snapshot consistency, isolation,
and rebuild/restart/encrypted restore across all three periods.

Local verification (Python 3.12, Linux): focused World suite 88 passed / 15 subtests;
full backend 793 passed / 54 skipped / 137 subtests; final timestamp/Period subset
10 passed. Frontend clean-install tests 124 passed; production build reproduced
committed assets. Dependency check, Python compilation and diff whitespace checks
passed. No separate lint/type checker is configured. Skips cover obsolete APIs and
platform-specific checks (Windows PowerShell/Inno and macOS); no World tests skipped.
Exact-SHA CI and independent QA status belong to the draft PR.

## Current delivery gate — World #3 merged; QA #17 accepted on draft PR

World intelligence [#3](https://github.com/suraj-singh12/sentri-face-edge/issues/3) is merged into hardening at `f907073`. Optional Explore UI is [#13](https://github.com/suraj-singh12/sentri-face-edge/issues/13); period-scope [draft PR #15](https://github.com/suraj-singh12/sentri-face-edge/pull/15) is held while the independently reproduced correction inconsistency [#22](https://github.com/suraj-singh12/sentri-face-edge/issues/22) is investigated. QA Foundation [#17](https://github.com/suraj-singh12/sentri-face-edge/issues/17) passed two genuine macOS QA-J01 runs and five CI jobs on [draft PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23) (`b81d451`); it was merged as `6a9ec82` after all five checks passed at final head `6eda54a`. Future QA phases #18–#21 require operator gates; release #5 remains pending. GitHub Issues own live task status.

## Historical Issue #3 implementation and test plan

Issue branch starts at refreshed `release-v2.0.0-hardening` commit
`9b02eba72b155421f06cb7a4b590047380dd59eb`. Implementation extends World v2 and
connected components, evidence and Encounter reads; there is no graphical UI,
migration, extra graph/location authority or background-job system. Current World
keeps its existing defaults and generated assets. See DOMAIN_MODEL for the additive
request/response contract and Issue #13's honest-loading constraint.

Impact/verification checklist: Current/Explore defaults; all seven nonempty evidence
combinations and thresholds 1/2/4/large; star/chain/components/bridge and weaker-edge
exclusion; separate recurrence/direction/provenance; correction/removal/merge/history;
latest day and 7/30/90 boundaries; location comparison, successful-save-only suggestions;
revision/cursor/snapshot/auth boundaries; rebuild/restart/encrypted restore equivalence;
100/10k-person bounds; full backend/frontend tests and production asset equality.

An adversarial reassignment-then-removal test found that graph validation demanded
current participation from a valid retired corrected endpoint. Validation now admits
that endpoint only with immutable correction-target proof; evidence/history writes
remain unchanged and active-participant validation remains in place. Activity-scoped
Person/Cluster expansion now applies the same eligibility as the overview, so
discovery navigation does not lose its scoped cluster identity.

Reproduce using Python 3.12 and a disposable checkout/data directory:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pip check
python -m pytest -q tests/test_world_intelligence.py tests/test_world_graph_v2.py tests/test_world_graph_v2_freeze.py
python -m pytest -q
python -m pytest -q -s tests/test_world_intelligence.py::test_discovery_scale_bounds_and_determinism
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
git diff --exit-code -- src/sentriface/ui_static
```

All new fixtures use temporary databases; the scale fixture reuses
`scripts/benchmark_world_v2.py::_seed`, whose authority shortcuts are restricted to
disposable benchmark databases. Do not run fixture seeding on operator data.
The new scale gate covers 100 people/1,000 Encounters and 10,000 people/100,000
Encounters (two participants each), bounded repeatable discovery/relationship/cluster
reads and constant statement-count caps. Recorded single-read development timings
were 0.002–0.025s and 0.134–3.439s respectively, 4–11 traced statements; payloads stayed
under 31 KB with 10-person/relationship, 3-support and 2-location preview limits.
These are local smoke measurements, not replacements for the frozen P10 million-
Encounter p50/p95 record, nor independent acceptance results.

Highest-risk independent challenges: identical canonical pairs from many photos and
merged raw identities; mixed selected strength versus recurrence; retired corrected
endpoints after removal; qualifying/weak bridges and no indirect edges; last-day
scope with repeated people across several Encounters; period boundaries and UTC day
handling; normalized locations without geocoding; cancelled/failed/corrected location
writes; stale cursor/filter/revision rejection; concurrent writes; encrypted restore
and restart. Local final verification: **768 backend passed, 54 skipped, 137 subtests passed**;
**124 frontend passed**, zero frontend skips/failures; production build and generated
asset equality passed; dependency, compile and whitespace checks passed. The 54
backend skips are 42 obsolete compatibility tests and 12 requiring Windows
PowerShell, not passes. Focused World regression: 63 passed / 15 subtests. All 32
Issue #3 tests pass within the full suite. CI platform/packaging results accompany
the draft PR; independent testing and operator acceptance remain outstanding.

## Completed baseline — Batch 3.7 (committed; schema v34)

Committed and pushed on `release-v2.0.0-hardening` as `555433f082dc39112bd815dddf3a8f35791f2f4b` (parent/original starting baseline `30b89cb7af2ef35316db321457264f7aabb8b2c8`). Attach ownership/Retry/Cancel, cleanup and backup-button work is included. Batch 4 has not started. This is source implementation qualification, not signed 2.0.0 release acceptance.

The source-ownership decision is resolved: Reference identity remains independent of Encounter correction. The earlier blocker fixture supplied identical synthetic vectors; real distinct photos independently produced E1/E2 (cosine about 0.709). Production exact-vector dedup remains allowed for equal model outputs. The bounded shared-row issue is handled by source-specific authority and derived recognition exclusion when current canonical source identities disagree.

Migration 33→34 extends `biometric_enrollment_history` with source media/path/crop, source quality and explicit no-context declaration; existing enrollment owner/ID/history are preserved and legacy declaration remains false. The small append-only `recognition_reference_revisions` table represents retire/restore because immutable creation history cannot itself change lifecycle and timed Deleted Faces may purge provenance. This reuses the existing SQL transaction, operation journal, media registry and encrypted snapshot format. Migration rollback, repeat startup and old-backup asset relocation are tested.

Shared single-face admission, four-source cap, source retirement/restore, quality/status/canonical recognition, exact cross-role media guards, cap-safe merge and management UI are integrated. Neither Reference entry point creates occurrence/evidence/World semantics. Encounter REASSIGN writes assignment correction only; global Move Face and Deleted Faces reject independently owned Reference samples and direct operators to Encounter correction or Reference retirement. No Transfer Reference shortcut or new recognition index is introduced.

Existing scan-session target/revision ownership remains schema-v33's smallest extension. Rejected Attach is durable until Retry or explicit Cancel; retry processes only owned media and revalidates the same target. Restored shared-directory cleanup never recursively owns unrelated uploads. The backup-card-specific sizing fix retains pointer and keyboard access without a Settings redesign.

Exact test/live results and preserved earlier evidence are in `/workspace/scratch/sentriface-batch37/REPORT.md`; implementation readiness requires full regression, real ONNX/Chromium, fresh encrypted restore/restart and supported rebuild, rather than unit tests alone.

**Final Batch 3.7 qualification (completed before commit `555433f`):** backend 736 passed / 47 skipped / 137 subtests; frontend 124 passed; production build, Python compile and diff checks passed. Real CPU ONNX/Chromium exercised both shared Reference entry points, admission rejection, cap/lifecycle, canonical merge, cross-role guards, permissions and retained Attach ownership. A supported encrypted backup restored into a completely fresh authority and normal restart preserved domain truth. Supported graph rebuild passed with unchanged Reference state and occurrence projection. Exact evidence, first failures and scope limits remain in the external Batch 3.7 report.

Encounter revision fingerprints exclude physical media locations, which legitimately relocate during restore; media IDs and semantic provenance remain versioned. Migration translates only still-valid pre-v34 Attach preconditions to the new fingerprint. Genuinely stale revisions remain stale. Source-scoped profile reads show the requested Person's own Reference/Encounter media instead of a shared embedding row's original image. Historical raw embedding ownership remains preserved. Cached legacy Add Face UI drafts can only be cancelled and reopened through the shared Reference route; there is no old admission bypass.

## CI baseline and remaining priorities — GitHub Issues

**P0 complete — Issue #1:** [PR #8](https://github.com/suraj-singh12/sentri-face-edge/pull/8) merged into `release-v2.0.0-hardening` as `683f3641e3532f08e180fe6c4c4386ac0f798917`. [Hardening workflow #40071662474](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40071662474) passed all five jobs on that commit:

| CI check | Result |
| --- | --- |
| `backend (ubuntu-latest)` | PASS |
| `backend (macos-latest)` | PASS |
| `backend (windows-latest)` | PASS |
| `frontend` | PASS |
| `windows-package` | PASS |

Python 3.12 is the only active source/CI target; Python 3.11 is disabled. The Windows job built and uploaded `SentriFaceEdge-2.0.0-x64-unsigned-pretag-rc.exe` with packaged-runtime, native-AMD64 inspection and provenance checks. This is an unsigned engineering candidate: production signatures, exact-tag rebuild and current-artifact disposable-Windows installer/model lifecycle acceptance remain pending under [#5](https://github.com/suraj-singh12/sentri-face-edge/issues/5). Historical P14 lifecycle and external-model results do not verify this CI artifact.

**Historical CI failure (resolved by #1):** the original `555433f` workflow ran Python 3.11/3.12. Linux passed, while platform-specific test selection, Windows launcher/reset behavior and frontend generated-asset drift left the workflow red; Windows packaging stopped at its backend gate. Issue #1 repaired those failures and the later detached-HEAD, Inno compiler-version/stderr and noninteractive Nuitka packaging defects. The green Python-3.12 run above supersedes that failed CI state; the earlier local/live qualification remains separate evidence.

P1 documentation reconciliation is [#2](https://github.com/suraj-singh12/sentri-face-edge/issues/2). Feature roadmap, all requiring **bounded operator issue review before implementation**: [#3 Batch 4 World vNext](https://github.com/suraj-singh12/sentri-face-edge/issues/3) (Person-only recurrence, relationship explanation, visible/group-forming edges, deterministic grouping and correctness under correction/merge/rebuild/backup), [#4 Encounter Split/Merge](https://github.com/suraj-singh12/sentri-face-edge/issues/4) (semantics not yet approved), [#6 Figma-first operator UI/acceptance](https://github.com/suraj-singh12/sentri-face-edge/issues/6), and [#5 signed 2.0.0 release acceptance](https://github.com/suraj-singh12/sentri-face-edge/issues/5). No feature issue authorizes implementation until reviewed. Resolve consequential product decisions in one concise review round where possible; preserve the reuse-first architecture and canonical docs; use feature branches/PRs and green CI before merging.

Earlier P0–P14 in this document are historical engineering phase names, distinct from the new P0–P4 **priority** labels in GitHub issue titles. Old batch sections below are historical checkpoints, not the present repository state.

## Historical checkpoint — Batch 3.6 Provenance & Canonical Integrity Repair

Starting branch/commit: `release-v2.0.0-hardening` / `1ea2a38d10be0da4c00fea4a3f53053b9eaef998`, clean. At that checkpoint changes were uncommitted; no tag or Batch 4 work was authorized.

The subsequent independent reaudit superseded Batch 3.5's bounded qualification: legitimate multi-photo history was rejected by P11 because its provenance query omitted registered review/session media and relied on enrollment-image paths. Write admission and P11 now reuse the existing server-owned media registry source-reference contract, excluding observation membership as its own proof. Saved accepted-face occurrence media must belong to that face's observation. Historical enrollment, review and correction references remain valid regardless of current lifecycle; physical closure, protected-file authentication, registry identities and archive/path checks remain independently mandatory in the existing backup pipeline. Rebuild and restore consume the same P11 checker, without bypasses or schema changes.

Merge retires redundant standing Manual Associations for affected canonical unordered pairs within its existing transaction/journal. Stable oldest assertion survives; raw IDs, metadata, distinct origin records and retirement provenance remain. Create/reverse-create reuse that assertion, retirement leaves independent Encounter/note evidence intact, and rebuild/restore preserve the normalized current state. Recognition caches full server-staged face decisions and displays the resolved identity from that same snapshot; model candidates remain proposals. Active-draft Browse People also fixes a nested PersonSummary DTO access exposed during live override qualification.

**Verification:** focused existing store/integrity/merge/backup tests 80 passed; new provenance/manual invariants initially 16 passed; final self-review invariants 18 passed; focused broader regressions 161 passed plus API regressions 15 passed; active-draft browse API 2 passed; recognition rendered tests 5 passed. Full backend 694 passed / 47 skipped / 135 subtests; full frontend 120 passed. Production build passed with the existing chunk advisory. The first full backend run passed 692 tests; after adding safe-revert refusal and retirement rollback coverage, the final run passed 694. The frontend first full run passed. Merge-linked manual retirement is excluded from the existing restricted safe-revert whitelist; that canonical-only inverse cannot restore retired standing state. Earlier focused harness/test failures (UUID restore IDs, directed-edge aggregation, incorrect test cwd, badge/button count, nonexistent selected test path and nonexistent test helper) are preserved in external logs; these were corrected, not hidden or attributed to nondeterminism.

**Actual fresh real qualification:** supported Linux source ONNX CPU + encrypted authority and rendered Chromium: UI creation/NO_FACE enrollment, three-photo review, recurring and multi-photo history, known enrollment-media attachment, Relations correction, Manual create/retire around alias merge, archive/history/Restore and tombstone, proposal acceptance, different existing/new identity resolutions, poor/unknown proposals, mixed accepted/deferred faces, refresh and restart/resume. Some repetitive history/notes/participant revisions use supplementary authenticated product APIs. Public fixtures and intentional authority overrides are identified in external evidence; this is not a statistical recognition test.

Source authority: 13 Persons (10 ACTIVE, 1 ARCHIVED, 1 DELETED, 1 MERGED), 23 samples (18 GOOD, 3 POOR_ACCEPTED, 2 PROOF_ONLY), 13 Encounters, 19 media rows, 20 raw participant rows, 9 Relation generations, 20 evidence records (10 active), 1 metadata and 2 participant revisions. Person reads include Encounter and STANDALONE_ENROLLMENT origins. Closure: 44 assets / 125 bindings / zero missing. Supported rebuild committed with PASS pre/post checks, unchanged domain/evidence/projection rows and revision g59; only rebuild journal records were added.

Recovery configured through UI; verified complete/restorable encrypted export imported into a completely fresh models-only root admitted through the supported recovery kit/code. UI Restore Safely committed and restored 44 files. Original source administrator authenticated. Source/restored domain tables and asset hashes match after physical-path normalization; existing journals survive, with only restore/rebuild journal additions. Normal fresh-root restart without kit arguments/authentication preserves the entire compared durable snapshot. Current People/Events/Encounter/World and raw historical profiles match semantically. Physical relocation legitimately changes Encounter precondition hashes and tie ordering of photo arrays; comparison records state these differences explicitly. Existing staged-only media relocation/immutability protection is unchanged.

Evidence: `/workspace/scratch/sentriface-batch36/`; credentials, recovery code/kit and encrypted export are outside that evidence directory. Mouse click attempts on compact backup action icons encountered pointer interception; keyboard activation completed the supported UI workflow. The restore response body was lost to the intentional UI reload; the committed restore receipt, journal, authenticated reads and snapshot comparisons establish success. These qualification harness limitations remain recorded.

This completes Batch 3.6's targeted qualification, not a new frozen three-phase reaudit or packaged Windows release acceptance. World vNext remains unimplemented.


## Historical checkpoint — Batch 3.5 Canonical Coherence & Audit Completion

Baseline: `release-v2.0.0-hardening` at `cf8c847337735dc7d1acc4b185f9d0e1f01a732d`. No commit/tag, Batch 4, World redesign or release-artifact work is authorized in this batch.

Implemented: one effective-media pair-support interpretation; explicit target enrollment and durable face-decision projections; common mutation read reconciliation; reachable archived profile/restore; actionable queue counts and distinct counterpart counts; stale queue snapshot guards; terminal cancellation cleanup ordering; lifecycle preflight before backup with transaction revalidation; Linux source-only encrypted recovery custody and verified-kit key admission; truthful source-runtime/network-boundary status.

Schema remains v32. No historical evidence is deleted to simplify current reads. Existing model/quality/recognition policy, note scopes, transaction/journal/idempotency, media dedup, lifecycle provenance, encryption, activation and production platform boundaries remain unchanged.

**Final Batch 3.5 gates:** 676 backend tests passed, 47 skipped, 135 subtests passed; 118 frontend tests passed; production frontend build and `git diff --check` passed. Full backend checkpoints were green (649 before additional regression coverage, then 671, 675, 675 after atomic cancellation, and 676 after dense-history coverage). No intermittent full-suite failure occurred. Earlier focused/build/test-harness failures were recorded and corrected rather than hidden.

**Targeted real-runtime qualification:** exact `./run.sh models` / `./run.sh onnx`, isolated SQLCipher authority, real SCRFD/ArcFace CPU and rendered Chromium. Verified three NO_FACE standalone quality states; durable Skip→restart and Discard→refresh; mixed-support merge with immediate retained Encounter refresh; Archived historical profile→Restore; distinct counterpart counts; finalized-only/mixed queue counts; five delayed Event transitions; three real processing cancellations and 20 publication-time cancellation subtests. A deliberately lost enrollment response retried the same operation ID with the identical result, one enrollment and one journal record.

**Recovery completion:** supported source recovery setup, encrypted UI export, fresh models-only root, `./run.sh onnx --recover-kit …`, normal fresh administrator, encrypted UI import and safe restore, normal source administrator login and restart. Compared 8 Persons (5 ACTIVE, 1 ARCHIVED, 1 MERGED, 1 DELETED), 12 faces (10 GOOD, 1 POOR_ACCEPTED, 1 PROOF_ONLY), 7 Encounters, corrected metadata/participants/Event mentions, raw and active evidence, Manual Associations, canonical history, graph and current World. No compared effective domain changed through restore/restart; 34 assets/99 registry bindings had zero missing references. Custody records are not backup assets.

Fresh restore exposed an existing broad completed-review UPDATE guard rejecting media relocation. The existing disposable-candidate restore transaction now suspends that exact guard only while registry-owned paths relocate, proves all other review fields unchanged, and reinstalls it before commit. Rollback covers paths and guard together; live review immutability remains enforced. No schema change or general mutation exception was added.

The exact audited Event-form detachment was not reproduced. Baseline delayed-response controls did reproduce loss of active face selection; live selection/generation guards address that concrete race. Windows/macOS native runtime acceptance and the future complete three-phase clean-room reaudit remain separate. Artifacts: `/workspace/scratch/sentriface-batch3-5/`. No commit or tag was made.

## Batch 3 — Encounter Management + People Integration (2026-10-02)

Implemented in source on the existing Batch 2 authority: compact Global Events, finalized Encounter detail, Attach Media, metadata/selected-mention correction, participant reassign/remove/add, Relations INCLUDE/EXCLUDE revision, profile integration, and normalized Manual Association create/retire. The deleted-Person historical summary regression is fixed. Schema v32 follows the required migration/journal foundations; no second Encounter, Person, media, graph or recognition subsystem was introduced.

Attach Media binds the existing durable review to one finalized observation and its expected revision. Completion appends media/accepted face history to that observation, retains settled pairs, requires explicit decisions for new canonical pairs, and refreshes support without creating another occurrence. Metadata and participant revisions preserve original finalized authority. Important mutations require operation IDs, commit their journal/evidence/projection together, and reject stale or competing amendment state. Recognition proposals and unsaved forms remain nonauthoritative.

The seven canonical documents below now distinguish this implementation from historical Batch 1/2 checkpoints. README ownership and reading order remain unchanged. **Verification:** focused Encounter management tests: 15 passed; authenticated role/tombstone API test: 1 passed. Full backend: 577 passed, 47 skipped, 115 subtests passed. Frontend: 112 passed. Production build and `git diff --check` passed; the existing large-chunk build warning remains. The migration suite covers supported upgrades; new v31→v32 coverage injects failure after the extension and verifies rollback, backup, repeat startup and foreign keys. Focused coverage includes independent evidence, canonical merge/removal, explicit new pairs, zero-face/all-excluded/new-Person attachment, stale/idempotent writes, graph-failure rollback, rebuild and effective World reads.

**Actual manual UI:** authenticated isolated synthetic-data development app: compact Events list/detail, location save, INCLUDE→EXCLUDE, Bob→Diana reassignment, human-readable correction history, profile Photos origin, profile Events PRESENT/navigation, Manual Association add/retire, and Attach Media upload → explicit face exclusion → Relations → Complete Review. Detail shows two media items within the same Encounter with unchanged participants/pair decision. Page scrolling was exercised. Production recognition, long-list stress, every role's visual walkthrough, and Windows artifact acceptance were not exercised. Role enforcement and named deleted historical reads were tested through the authenticated API, not a tombstone UI walkthrough. World vNext scoring/recurrence tiers/clustering, Encounter Split/Merge, and signed/current-artifact Windows acceptance remain deferred. No commit or tag is authorized.

The older dated stabilization sections below are historical checkpoints. Their references to Encounter Management, Manual Association UI, or the deleted-Person bug as deferred are superseded by this Batch 3 section.


### Batch 3 follow-up verification on release-v2.0.0-hardening

The committed implementation was reviewed against the full Batch 3 specification. Corrected gaps: separate operation IDs no longer duplicate an active canonical Manual Association; retries after endpoint merge preserve the original result; reused embeddings retain actual accepted-face media through server-derived IDs in existing immutable decision JSON; explicit attachment can restore removed participation through a forward PRESENT revision; older identity correction respects participant revisions; Move Face cannot mutate an Encounter with an active amendment; Events reads use one snapshot. Merge conflict responses expose the affected Encounter for direct UI navigation. Manual removal explains evidence independence and association controls wrap on small windows. Schema remains v32 and World algorithms remain frozen.

**Current verification:** focused Encounter management/API/identity-correction suites: 33 passed. Full backend with a real isolated Linux Secret Service vault: 583 passed, 47 skipped, 115 subtests passed. Frontend: 112 passed, 0 failed. Production frontend build and `git diff --check` passed; the existing large-chunk warning remains. No additional schema migration was introduced.

**Actual current browser verification:** authenticated headless Chromium, isolated synthetic-data dev runtime: compact Events/detail; Delhi→Agra metadata save; INCLUDE→EXCLUDE; Bob→Diana reassignment; readable history; correction controls at 390×700; Person Photos origin, Events and Sightings; Manual Association create/retire; Attach Media upload, explicit detected-face exclusion, Relations and completion with the same Encounter ID, three media items, unchanged participant count and prior pair decision. After tombstoning Diana, authenticated reads exercised People, Global Events, detail, active and raw deleted profiles, Person Graph, association graph, World, notes, Relations and every attached media image. Browser detail displayed Diana as deleted; People, Associations and World remained usable with no page errors. These are browser-driven synthetic workflow checks, not production recognition, exhaustive long-list stress, every role visual walkthrough, or Windows artifact acceptance. Role refusals remain covered by authenticated API tests. Previous Batch 3 counts and manual results above describe the committed baseline and are not substituted for the current run. No commit or tag is made.

## Current correctness stabilization (2026-10-01)

Completed: the eight manually reported Review Photos defects are corrected without starting Encounter Management, Manual Association UI or World vNext. Existing Queue/review staging remains the owner. Schema v31 minimally extends `init_session_media` with durable `excluded` selection; v30 membership alone cannot remember an operator removal on restart. Selection locks after grouping; no physical or historical media is deleted. There is no new table, subsystem, media path, note authority or recognition index.

Locked recognition rule: committed and accepted active-Encounter draft samples form one transient candidate view, grouped by canonical Person (or draft-created key). With GOOD available, preference ON uses GOOD only; OFF uses GOOD plus POOR_ACCEPTED. Without GOOD, POOR_ACCEPTED is fallback under either setting. PROOF_ONLY never participates in ordinary matching. The shared pre-creation duplicate guard considers otherwise unsearchable proof-only-only identities in the same combined view. `Drafted` means the Person itself was created in the active draft, never merely that an existing Person received a draft face. Global Person/embedding/graph/Events authority stays committed-only.

Root causes corrected: planning/regrouping changed IDs while the UI retained scan groups; refresh did not reconcile selected face membership; an asynchronous delayed reset could erase a newly opened form; removal lived only in React; draft matching excluded accepted existing-Person faces and ranked independently of committed references; duplicate prevention missed draft-only proof identities; the opening instruction toast was easily mistaken for validation. Submission now uses current, trimmed form values with explicit missing-field messages. Finalized-media cards are disabled/excluded automatically. Peek In uses an existing crop or stored box, clipped to a 250×250 aspect-preserving preview, without detection or persistence. Normal notifications default to 4.5 seconds; operator decisions remain modal. The quality preference is left-aligned in the review header and persists through the session API. `Drafted` is displayed only for draft-created Persons. Existing committed-person rejection remains available; draft-created suggestions use explicit selection/skip instead of sending a synthetic draft ID to the committed-person exclusion command.

Automated verification: full backend **561 passed, 47 skipped, 114 subtests passed**; full frontend **112/112 passed**; production frontend build and `git diff --check` passed. Focused migration/store/review/authenticated Queue API tests cover v30→v31 default compatibility, rollback after partial schema change, repeat startup, lifecycle/canonical preservation and foreign keys; durable removal/restart/restore and grouping lock; mixed committed/draft quality matrix; committed and draft proof-only duplicates; reuse/override; no global enrollment leak; and selected-face draft rollback. Existing full-suite coverage preserves notes, NO_FACE/Add Face, media, merge/correction, Skip/Discard, Relations and atomic finalization. Generated UI assets were rebuilt only from frontend sources. The existing bundle-size warning remains.

Live manual verification used an authenticated isolated **development** instance with synthetic media, not production recognition models. Verified: automatic finalized-media exclusion with no X; removal surviving reload and restore; grouping→Event popup→normal Person resolution; face Peek In and close; filled Name/Rank/Country/Tag/Added by/count submission; proof-only draft Tony warning with `Drafted`; Use Existing reuse; later ordinary GOOD draft suggestion; preference ON/OFF and warning; one effective participant/no self-pair; final completion and Person Profile fields/media with one sighting. Notifications appeared and cleared during the walkthrough. Production-model visual validation, larger review sets and full role walkthrough remain separate verification limits.

Next work remains the planned later phases: Encounter Management/Attach/Correct/Split/Merge, Manual Association UI, World vNext and visual refinements. The high-priority deleted-Person `Unknown person: <UUID>` lifecycle regression remains deferred; this pass did not reproduce or redesign it. Preserve the current identity, note-scope/evidence, transaction/journal and committed-only index boundaries as prerequisites. No commit or release tag was made. Canonical reading order remains `AGENTS.md` → `docs/README.md` → this tracker → overview → architecture state → domain → features → architecture explanation → handoff.

## Historical first Review Photos stabilization (2026-09-29)

This first pass retained Batch 2 authority and schema v30. Its local-only media removal, stale grouping snapshots and separate draft candidate ranking were subsequently found insufficient in manual testing; the current 2026-10-01 correction above supersedes those details. It established finalized-media conflict reads, Encounter-first grouping, bounded multiple-Encounter allocations and optional uploaded-subfolder hints. A second finalized Encounter cannot be manufactured from the same retained bytes. The operator confirms every boundary.

**Locked Skip rule:** Skip defers an unresolved identity group. It is never a final identity decision and cannot unlock Relations or Complete Review. The group leaves the actionable list while other pending groups remain, then returns automatically when none remain; an all-skipped pass requeues the deferred groups. A refresh/restart also repairs an all-deferred draft. Discard/`EXCLUDE` is the final negative face decision and does not return. Resolved groups leave the actionable list. The same active Encounter's media and Event details remain staged throughout.

The first pass established page scrolling, current-face boxes, visible Relations choices and canonical graph association summaries. The current correction moves the quality preference into the left-aligned review header and expands the shared duplicate guard to accepted active-draft references. These controls do not govern face storage. Graph summaries do not change World authority or recurrence scoring. Event selected IDs remain structured Encounter→Person references only, with no relationship evidence.

No new table, service, durable authority, or recognition index was introduced. The current pass extends existing Queue group status, media membership read, Encounter plan validation, graph provenance summary, and React views. **Verification:** focused store/graph/Queue tests passed (55 passed, 2 skipped); authenticated loopback Queue API passed; full backend passed (556 passed, 47 skipped, 108 subtests); full frontend passed (109/109); production frontend build and `git diff --check` passed. The current build was generated from `frontend/`, not edited by hand. Computer-use inventory found no open SentriFace UI/browser tab, so actual authenticated operator visual verification of scrolling, grouping, face box, Relation state, duplicate card, and preference placement is still pending. Remaining deferred work: deleted-Person `Unknown person: <UUID>` lifecycle regression, this visual walkthrough, Encounter management, Manual Association UI, and World vNext. Do not start those as part of this stabilization pass.

## Batch 2 source implementation complete (2026-09-28)

**Locked note-scope rule (supersedes the earlier Batch 1 request):** a mention in any scope is semantic only when the operator selects a Person and the person ID is saved; literal unselected `@Name` is inert. A selected `PERSON_NOTE` mention creates Person→Person `NOTE_REFERENCE`; a selected `SIGHTING_NOTE` mention creates sighted Person→mentioned Person `NOTE_REFERENCE`; a selected `EVENT_NOTE` mention stores only an Encounter→Person reference on the observation. Event Note mentions create no `relationship_evidence`, `NOTE_REFERENCE`, `CO_OBSERVED`, or World/cluster/recurrence effect. `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` remain distinct evidence types. This is the current rule for implementation and future work; any earlier Batch 1 wording requiring Event Note `NOTE_REFERENCE` is obsolete.

Batch 2 now extends the existing Queue `init_sessions`/`init_faces` and P6 `photo_reviews` staging. Schema v30 adds serial review phase, saved Event details, staged multi-media membership, and one small `encounter_relation_decisions` authority table. The latter is necessary because absence of positive `relationship_evidence` cannot distinguish an intentional `EXCLUDE` from an undecided pair. There is no parallel Encounter, Person, media, note, graph, or recognition index system. One active draft per session proceeds through grouping → Event once → identity decisions → Relations → journaled `review.complete`; later Encounter drafts wait and are activated in sequence. Event/identity/Relations drafts are durable but nonauthoritative until the existing finalization transaction commits Person, observation, participants, face assignments, media references, notes, evidence, graph and journal together. Every canonical pair needs `INCLUDE` or `EXCLUDE`; included pairs get at most one `CO_OBSERVED` occurrence per Encounter, and excluded pairs remain historical participants without that evidence. `SHARED_FRAME` and `SAME_ENCOUNTER_ONLY` are stored support explanations, not World weights.

Current Queue UI exposes explicit One Encounter / Multiple Encounters grouping, confirms Event once, keeps Person and Sighting fields on the page, shows Relations decisions and serial progress, and resumes backend draft state after restart. The post-Batch-2 pass above enables folder-based suggestions when distinct uploaded subfolders are available; the operator remains the Encounter authority. Newly accepted draft faces are compared in a transient active-Encounter candidate overlay, never the global index. Existing accepted-poor fallback applies to draft and committed references; `PROOF_ONLY` never enters ordinary matching. Exact managed uploads already use content-addressed encrypted objects; Queue additionally deduplicates identical retained bytes across filenames and refuses a second finalized Encounter for known exact media. Standalone Add Face remains independent and shared media objects are reused. Lifecycle mutations refuse active-draft references. Correction appends/retire Relations revisions and rebuilds included evidence without resurrecting exclusions; merge preview refuses pair collapse that would make Relation decisions ambiguous. Global/Person Events and World remain read projections, with no new Encounter management or World scoring.

**Verification and status:** Batch 2 source work and final self-review are complete in the uncommitted working tree. Focused store tests cover serial review, restart, relation support/exclusion, correction, lifecycle/merge refusal, draft eligibility, exact media, idempotent finalization, and forced graph-failure rollback of the new Encounter path. The authenticated loopback draft API test passes. Final gates: `.venv312` backend 554 passed, 47 skipped, 108 subtests passed; frontend 106 passed; production frontend build passed; `git diff --check` passed. No authenticated SentriFace window was open, so live operator walkthrough and role-by-role UI verification remain unverified and are required before release acceptance. The reported deleted-Person `Unknown person: <UUID>` regression, compact Events/Person Profile presentation, and missing Manual Association Add action remain tracked. Future recurrence must count distinct `(Encounter ID, effective canonical pair)`; do not interpret media count or raw evidence rows as independent occurrences. Batch 2 adds no Encounter browser, Attach Media, full Encounter correction UI, split/merge Encounter, Manual Association UI, World vNext, or arbitrary recurrence tiers.

The canonical reading order remains `AGENTS.md` → `docs/README.md` → this tracker → `docs/PROJECT_OVERVIEW.md` → `docs/ARCHITECTURE_STATE.md` → `docs/DOMAIN_MODEL.md` → `docs/FEATURES_BY_TAB.md` → `docs/ARCHITECTURE_EXPLANATION.md` → `docs/AGENT_HANDOFF.md`. The section below records the completed pre-Batch-2 baseline; its references to Batch 2 as future work are historical to that checkpoint.

## Historical stabilization baseline (2026-09-27) — pre-Batch-2 integration after Batch 1

Locked 2026-09-27 continuation: Encounter authority is the existing finalized observation; Person authority is the existing Person/lifecycle record; a sighting is accepted Person + Encounter participation. Keep `EVENT_NOTE` (Encounter), `SIGHTING_NOTE` (Person + Encounter), and editable `PERSON_NOTE` (general profile) distinct. Selected Event Note IDs are structured Encounter→Person provenance, never Person relationship evidence; selected Sighting/Person Note IDs produce Person→Person `NOTE_REFERENCE`. Literal `@Name` is inert. `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` remain separate. ACTIVE `NO_FACE` Persons are real identities; Add Face enrolls without an Encounter. `GOOD`, `POOR_ACCEPTED`, and `PROOF_ONLY` describe stored embeddings, independently of Person biometric status and face origin. **Prefer quality photos for recognition** defaults ON: for a Person with GOOD, ON uses GOOD and OFF adds POOR_ACCEPTED; a Person with no GOOD but accepted poor samples uses POOR_ACCEPTED as fallback under either setting. PROOF_ONLY never enters ordinary matching; only the separate pre-new-Person duplicate check may compare it. The switch governs stored candidates, not incoming quality or storage. Existing encrypted upload reduces >~1 MB images to a ~≤1 MB historical source; detector processing is transient. Do not retain the giant original.

At this pre-Batch-2 checkpoint, the high-priority deferred lifecycle bug was manual deletion of a Person producing `Unknown person: <UUID>` and disrupting People/other tabs. Full lifecycle/Encounter integration still belongs to later People work. The historical scope excluded multi-Encounter orchestration and durable pair INCLUDE/EXCLUDE, which the current Batch 2 section above now implements. Mutable Encounter attach/correct/browse workflows, Manual Association UI, and World vNext remain deferred.

This document is the canonical tracker. The existing P0–P14 implementation is the baseline; P14 production release acceptance remains pending. Locked decisions: one offline identity graph; finalized observations/events are the Encounter authority; participant decisions and graph evidence commit with the existing journal and operation ID; recognition proposals never become authority; source media and accepted quality-gated embeddings retain their existing ownership; archived, deleted, and merged identities remain historically represented. Prefer additive extensions of the existing observation and person records to new tables or services.

Historical implementation order: Batch 1 first traced code/media, repaired Person/navigation/review/mention defects, extended observation authority and form separation, then persisted embedding eligibility. The pre-Batch-2 integration added NO_FACE Browse, face-origin reads, accepted-poor fallback, proof-only duplicate prevention, and read-only Events. The current Batch 2 section above supersedes this checkpoint for Review Photos orchestration and Relations INCLUDE/EXCLUDE; World recurrence, mutable Encounter attachment/correction/split/merge, and new clustering rules remain deferred.

Completed work: traced upload, recognition, staging, Queue, Person, notes, observation, World and graph paths. Queue new-person metadata, shared profile navigation, new-to-existing state clearing and selected-ID suggestions are repaired. Recognize and Queue ask Event details once in a modal; Person forms retain Name, Rank, Country, Tag, Added by where applicable, individual count and Sighting Notes, with Event context read-only. Event Notes and selected IDs reside in observation context and do not create relationship evidence. Finalized review writes shared Event metadata once and mirrors compatibility detail fields; conflicts roll back. Schema v29 adds embedding recognition state and Queue search policy. Normal search/index enforces GOOD/POOR_ACCEPTED fallback policy and excludes PROOF_ONLY. Browse now offers ranked biometric profiles by default or explicitly selected ACTIVE NO_FACE profiles, with no fake scores. A separate proof-only duplicate check runs before new Person creation, with use-existing and create-anyway decisions. Existing face-assignment/enrollment history yields ENCOUNTER/STANDALONE_ENROLLMENT origin, otherwise UNKNOWN_LEGACY. A bounded read-only Events API/tab and Person Profile Events view read finalized observations with PRESENT/MENTIONED/BOTH. Add Face remains independent of Encounter. Historical IDs, media, evidence and corrections remain intact.

Verified media path: an 18,136,302-byte 6000×4000 JPEG becomes an 889,549-byte 1600×1066 managed JPEG; detector preprocessing produces a transient 640×640 tensor (640×426 content, 107-pixel vertical padding). The giant original is not retained. `max_image_edge` is configured but currently unused by ONNX detection; model input letterboxing already bounds the tensor, so changing preprocessing needs separate quality/coordinate validation. Remaining risks: the reported deleted-Person `Unknown person: <UUID>` lifecycle regression is deferred; no authenticated runtime UI was available for live manual verification of profile navigation or modal transitions. The serial multi-Encounter workflow named as future work at this historical checkpoint was implemented in Batch 2 above.

Pre-Batch-2 integration status: source implementation complete; live authenticated UI walkthrough remains pending on a configured runtime. Focused coverage includes no-face/Add Face, migration, Queue policy restart, embedding/index/stale-index protection, duplicate-prevention accept/reject, Event/Sighting selected IDs, bounded Event filters/pages and role enforcement, face-origin restart reads, media processing, transaction rollback, and Person persistence/navigation. Final gate: 546 backend tests passed (47 skipped, 107 subtests passed), 106 frontend tests passed, production frontend build passed, and `git diff --check` passed. No commit or release tag was made. The only intentionally new mechanisms are a bounded read-only Events API/UI projection and the exceptional pre-creation proof-only comparison; both reuse existing observation, embedding, storage, transaction and role authority and add no table or domain event system. Batch 2 prerequisites: transaction/journal discipline, canonical resolution, archive/tombstone history, media closure, three note scopes, distinct evidence types, and recognition eligibility.

Compatibility decision: v29 maps existing embedding rows to `GOOD` for prior search eligibility. This preserves historic matching behavior without claiming that the old quality assessment was re-run; post-v29 `GOOD` rows are quality-gated. Existing Queue sessions default to quality-only ON. No historical observation/person/media/evidence IDs are rewritten. The reported deleted-Person loading regression remains high priority in People lifecycle work. The configured ONNX `max_image_edge` is inert; its 640×640 model-input letterbox is the actual processing bound. Clean up that obsolete setting only with detector-quality and coordinate checks.

Final Event Note decision for this integration: Event Notes have no inherent source Person. Selected IDs remain structured Encounter→Person mention provenance in finalized observation context, searchable in Events and Person Profile Events; they never create `relationship_evidence`, `NOTE_REFERENCE`, `CO_OBSERVED`, a participant, or a World edge. Person and Sighting Notes retain normalized revisions/occurrences and Person→Person `NOTE_REFERENCE`. Do not fabricate an Event Note owner from participants. Future Event Note editing/correction, if added, must preserve revision history and transactional selected-ID authority; this read-only Events pass adds no edit command.

Locked later World direction, not implemented here: one distinct (Encounter ID, effective canonical Person pair) contributes at most one independent co-observation recurrence, even across many media or after a merge. Shared-frame and same-Encounter/no-shared-frame are distinct supporting explanations whose counts sum to independent Encounters. Public/group context does not silently discount independent occurrences. Recurrence, recent activity, evidence type and group-forming eligibility remain separate. Current World still uses evidence-count strength and deterministic connected components; no new recurrence tiers or bridge thresholds are implemented.

Canonical coding-agent reading order: `AGENTS.md` → `docs/README.md` → this plan → `docs/PROJECT_OVERVIEW.md` → `docs/ARCHITECTURE_STATE.md` → `docs/DOMAIN_MODEL.md` → `docs/FEATURES_BY_TAB.md` → `docs/ARCHITECTURE_EXPLANATION.md` → `docs/AGENT_HANDOFF.md`. Human entry path: `docs/README.md` → `docs/PROJECT_OVERVIEW.md` → `docs/FEATURES_BY_TAB.md` → `docs/DOMAIN_MODEL.md` → `docs/ARCHITECTURE_EXPLANATION.md`. Consult `docs/p14/P14_RELEASE_ACCEPTANCE.md` before release claims or tooling changes. Every batch updates every affected canonical document before completion.

Implement in order. Each phase must preserve offline operation, use additive migrations where possible, keep important writes transactional and journaled, and add upgrade/failure tests before moving on.

Status after P14 Windows acceptance: P0 through P14 source implementation are complete; P10 through P13 remain frozen. P11-A establishes the integrity authority/invariant model and explicit read-only checker; P11-A1 and P11-C2A retain the two R02 safety-stop corrections for occurrence and evidence history. P11-B provides deterministic graph rebuild. P11-C remains exactly two explicit typed commands: R01 archived-terminal restoration and R02 append/retire-only note-reference reconciliation. P11-D remains one explicit guarded normalized-merge revert subset. P11-E adds only the administrator-gated, token-bound Integrity & Recovery API/UI over those services. P12 hardens format-v3 portable backup closure and guarded staged restore without changing the P11 whitelist, schema, or dependencies. P13 hardens unpackaged operational model authority, activation, runtime lifecycle, logging, and managed storage without changing schema or domain authority. Historical real-host unsigned Windows x64 build/install/runtime/lifecycle acceptance passes. The 2026-09-20 version-2.0.0 hardening candidate additionally passes locked source gates, current-source packaged runtime tests, external ONNX session checks, and strict native-AMD64 inspection of the Inno Setup 7 installer plus every runtime binary. Clean-tag Authenticode-signed production acceptance and a disposable-VM lifecycle run of the final artifact remain pending.

## P0 Database migration/version foundation — Complete

Refactor the inline version chain in `src/sentriface/storage/sqlite_store.py` into an explicit, testable migration registry without changing runtime domain behavior. Define supported-version policy, schema introspection, transaction boundaries, backup-before-migration, failure recovery, and fixtures for representative old schemas. Exit: fresh install and every supported upgrade reach the same schema; failed/repeated migrations are safe and verified.

## P1 Operation Journal — Complete

Extend the legacy `person_operations` model with a general immutable operation journal while retaining idempotency compatibility. Record actor, operation type, affected entities, before/after or inverse payload, status, and timestamps in the same transaction as each important normalized write. Exit: the journal foundation and status model are available, phase-owned important writes are journaled and retry-safe, and remaining legacy gaps are enumerated rather than speculatively backfilled.

## P2 Identity lifecycle + canonical identity — Complete

Introduce explicit `ACTIVE`, `ARCHIVED`, `DELETED`, and `MERGED` lifecycle states and normalized canonical-resolution/merge-history primitives. Remove physical person erasure from normal lifecycle semantics; provide compatibility mapping from `deleted_at` and `metadata.merged_into`. Exit: archived/deleted/merged source identities resolve correctly while remaining historically queryable.

## P3 Observation/Event model — Complete

Add events/observations, event photos, detected-face review decisions, and accepted participants. Migrate or bridge `recognition_details`; enforce one participant per canonical person per event and allow multiple photos. Exit: event completion is explicit, participant deduplication/self-link rules hold, and existing sightings remain accessible.

## P4 Global graph + relationship evidence engine — Complete

Add normalized evidence records and a rebuildable relationship projection. Keep `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` evidence distinct, explainable, independently removable, and canonicalized while retaining their observation, note-mention, or manual-assertion provenance. Provide storage/service APIs; do not add final Person Graph/World UI yet. Exit: rebuild is deterministic and produces the same projection as incremental transactional updates.

## P5 Notes/revisions/@Person mentions — Complete

Normalize person and legacy recognition-detail notes, revisions, and exact mention occurrences. Resolve explicit person-ID mentions only on save; diff revisions so removed mentions retire only their evidence. Migrate existing profile/sighting notes and `automatic_mention` associations without inventing provenance that cannot be established. Exit: save/edit/remove/duplicate-name/canonical-resolution cases preserve independent evidence correctly.

## P6 Check Photo/Queue atomic finalisation — Complete

Create one backend finalisation command per photo/event review. Require a final decision for every detected face plus explicit completion; atomically persist identities/participants/details/evidence/journal or nothing. Replace frontend request loops in `useRecognizeController.js` and `useQueueController.js` with the command. Exit: injected failures cannot leave partial identity, event, mention, or graph state.

## Hardening/consolidation pass — Complete

After P6, consolidate production mutation paths behind the storage/service boundary, gate legacy domain writes, strengthen startup domain validation and canonical-aware recognition/index behavior, and retain the existing relationship UI as a compatibility read model. This pass does not add a new domain phase.

## P7 Recognition corrections/Move Face/Add Face — Complete

Model corrections as authoritative, journaled history rather than silent ownership rewrites. Support corrected participant identity, Move Face, and Add Face while retaining original proposal/decision provenance and rebuilding affected projections. Exit: correction paths are atomic and historically explainable; general operation revert remains P11 work.

## P8-A Identity Merge infrastructure foundation — Complete

Add the caller-owned, connection-scoped canonical update primitive; immutable normalized merge manifests, affected-item records, and typed conflict strategies; terminal-survivor validation; and canonical-aware current read models. Do not expose or execute the normalized Merge workflow in this subphase. Exit: the storage/domain primitives can participate in a future single merge transaction without treating legacy merge snapshots as normalized truth.

## P8-B Identity Merge orchestration — Complete

Orchestrate Merge on the P8-A foundation. Preserve source records and evidence, resolve reads to the canonical survivor, apply explicit conflict strategies, canonicalize projected pairs, prevent self-links, and define safe revert preconditions. The authoritative change, merge manifest, affected items, graph projection update, and operation journal must share one transaction. Exit: the normalized Merge workflow is exposed through the backend boundary; merge chains, archived/deleted identities, notes, events, corrections, and evidence survive intact; and the manifest retains the inverse data needed for guarded P11 revert work.

## P8-C Architecture hardening — Complete

Remove compatibility stores from current-truth decisions without deleting their historical data. Embedding enrollment ownership remains raw provenance while correction history and terminal canonical resolution determine effective ownership. Merge note conflicts append normalized note revisions before refreshing the `persons.notes` mirror. Profile activity reads the global operation journal, current relationship reads use the evidence-derived graph projection, and review/identity request boundaries require an operation ID plus authenticated actor. Exit: `person_associations`, `persons.notes`, `person_operations`, and `recognition_details` are restricted to compatibility, migration, or historical display; none determines current graph, activity, notes, identity, or P9 analytics.

## P9 Intelligence, Sightings, Analytics, and Derived Read Models — Complete

Added a read-only intelligence service and normalized backend models for effective sightings, presence, monthly/location trends, evidence-derived relationship analytics, and profile intelligence. Sightings now come only from finalized observations and corrected/canonical effective participants, collapse duplicate faces within an observation, retain raw provenance, and aggregate merge history under the survivor. People summaries and sort/group fields use backend-provided observation counts, first/last seen, frequency values, and labels; the profile renders normalized sighting rows. Relationship strength and history come only from active `relationship_evidence`, and activity comes only from `operation_journal`. `recognition_details`, `person_associations`, `persons.notes`, and `person_operations` remain compatibility data rather than analytics truth. No-face identities are supported without biometric enrollment. No authoritative table, graph mutation, dependency, or schema migration was added. Exit: photo/embedding deletion cannot erase event participation, corrections move the effective current sighting while preserving raw history, merges union canonical history, and focused plus full regression suites verify the behavior.

## P9.5 Frontend normalization — Complete

Converted React into a rendering and interaction layer over explicit backend read contracts. People collection statistics, intelligence ordering, lifecycle/canonical identity, allowed actions, normalized notes and mention occurrences, relationship rows, and journal activity now arrive from backend services. The existing relationship modal consumes a versioned backend subgraph with canonical endpoints, depth, counts, evidence, lifecycle, and revision metadata; the client computes coordinates only. Identity mutations invalidate and refetch authoritative collections/profiles instead of synthesizing final state. Legacy recognition detail remains available only inside historical face/photo presentation. No P10 Person Graph or World projection was implemented.

## P10-A Graph and World intelligence backend contracts — Complete

Added typed Person Graph and World Graph read models behind `GraphReadService`, versioned loopback APIs, backend-owned temporal/location/lifecycle/profile/frequency/strength filtering, canonical node collapse, evidence-derived provenance summaries, and an opaque durable graph revision token. Schema v27 adds only the singleton revision state and two required read indexes; responses remain uncached and expose no raw evidence or compatibility tables. Exit: frontend consumers can render consistent Person and World projections and detect stale data without reconstructing graph truth.

## P10-B Person Graph UI — Complete

Added a dedicated Person Graph workspace inside People. It consumes only the versioned P10-A Person Graph and revision contracts, renders backend-provided nodes/edges/lifecycle/actions/evidence, and owns only deterministic node coordinates plus pan, zoom, hover, and selection state. Graph revision is an opaque consistency token. In the current offline single-user model, the UI validates it at lifecycle boundaries and after known graph mutations. Continuous polling is intentionally avoided. Opening stores the revision; returning validates once and reuses unchanged state; successful graph mutations invalidate the snapshot; changed, invalidated, and manually refreshed graphs are replaced in full. Node navigation follows backend `allowed_actions`. Empty and large graphs are covered without adding client topology reconstruction. No World UI or backend change was introduced.

## P10-C World Graph architecture and product design review — Complete

Defined World as a scope-first, progressive spatial/temporal projection of the one global identity graph rather than a zoomed-out Person Graph. Canonical people and evidence-derived relationships are primary; backend-computed clusters are ephemeral read-model summaries; finalized events are explicit evidence drill-down; and locations remain filters/facets until a normalized place identity exists. Defined the initial progressive-level concept, unknown-person boundaries, backend filter ownership, contract gaps, scaling limits, and the Person Graph decisions that may or may not be reused. No UI, rendering, backend behavior, schema, dependency, or generated asset changed. Exit: the product model and backend/frontend responsibility boundary are documented before implementation.

## P10-D World Intelligence read-model architecture review — Complete

Defined World as a backend-owned intelligence system over canonical people, finalized events, normalized evidence, and journaled history. Classified clusters, patterns, salience, ranking, explanations, and aggregate edges as deterministic revision-bound read objects; excluded unsupported topology and speculative inference; separated five semantic detail levels from frontend zoom; defined normative filter ordering and structured explanation contracts; selected a single bounded `/api/world-graph` version 2 route; and set scaling/cursor/cache boundaries. No UI, backend behavior, schema, dependency, or generated asset changed. Exit: the entity, intelligence, explanation, filter, read-contract, scale, and frontend/backend ownership decisions are explicit enough to implement and test without inventing semantics.

## P10-E Bounded World read and expansion contract — Complete and frozen

Implemented `/api/world-graph?version=2` as a typed, bounded, revision-consistent backend projection while preserving version 1. Added the five semantic detail levels, typed focus, effective filters/facets, deterministic ranking factors, revision-bound cursors and cluster identities, canonical people/historical IDs, finalized event detail, bounded evidence provenance, evidence-derived relationships, deterministic explained clusters, measured data-quality patterns, scope/returned totals, and hard response caps. Existing normalized truth is queried directly; no World table, cache, dependency, frontend code, or generated asset was added. Schema v28 only refines shared revision invalidation so World-visible person fields advance it while unrelated metadata does not; finalized single-participant events now advance revision transactionally. Exit: focused tests cover contract validation, normalization, caps/pagination/stale revisions, merge collapse/no self-links, lifecycle/biometric state, evidence provenance/type filters, deterministic cluster explanations, finalized-event gating, missing location, non-speculative patterns, and relevant/irrelevant revision inputs.

Final stabilization completed: every response is held to one revision-bound SQLite snapshot; relationship projection and evidence expansion share correction-before-canonical endpoint semantics; self-edge/cross-edge leakage is suppressed; and evidence counts equal supporting scoped rows. The full documented navigation is backend-owned, including overview relationships, cluster ranking/activity, person cluster membership, independent event participants/provenance/evidence/media, exact evidence media, and reference-only media. All bounded collections and dynamic location facets report truthful page state. Partial neighbour analytics are explicitly `NOT_LOADED`. Evidence and empty-person read paths are constant-query for bounded pages, reducing the recorded diagnostics from 78 to 17 and 1,004 to at most 6 statements respectively. The Python invariant/full suites and frontend test/build checks pass.

The final consolidated artifact, `docs/p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json`, records Dataset A/B sparse/dense cold/warm p50/p95, SQL counts, payloads, returned counts, and cursor walks. Dense-B allocation tracing remains explicitly unavailable because instrumentation distorts runtime; product latency is measured without it. The former dense observation×alias adjustments, focused-person event scans, repeated complete-World facet pages, and recursive cluster scoped counts were replaced with bounded participant-first or collection-specific reads without changing semantics. P10-PERF-01 through P10-PERF-05 pass. No cache, materialized view, background work, dependency, index, schema, or frontend feature was added.

## P10-F World UI — Complete and frozen

P10-F1 adds World as a persistent first-class top-level view and renders only frozen `WORLD_SCOPE` authority: normalized effective scope controls, backend totals/facets, ranked canonical people, revision-bound cluster summaries, measured patterns, typed relationship pages, truthful analytics availability, page/truncation state, and structured factual explanations. P10-F2 adds a backend-requested `CLUSTER` workspace with factual cluster explanation, independently bounded member and relationship collections, page replacement, selected-member navigation intent, relationship inspection, and stale revision/cluster recovery to an authoritative `WORLD_SCOPE` reload. P10-F3 adds fresh `PERSON` entry from WORLD_SCOPE and CLUSTER, a compact scoped identity/intelligence header, backend-provided cluster memberships, independently bounded relationship and finalized-event summary pages, factual relationship inspection, event navigation intent, origin-aware return navigation, and stale person/canonical recovery. P10-F4 adds a fresh `EVENT` read from PERSON, finalized observation context, independently bounded effective participant, raw provenance, evidence-summary, and media-reference pages, backend raw-to-effective interpretation, retained PERSON return state, and stale event recovery. P10-F5 adds a fresh `EVIDENCE` read from EVENT, explicit raw versus current-effective endpoints, typed/directed factual provenance and explanation, independent bounded Evidence → Media reads, truthful unavailable/requested-empty/not-requested/truncated states, and shared inspection-only media preview with explicit EVENT or EVIDENCE origin. The controller replaces immutable bounded responses, validates retained state at navigation boundaries, invalidates after known graph mutations, and performs no polling or page concatenation. Layout, selection, interaction state, and visual presentation remain client concerns; identity, participation, provenance, evidence/media membership, filters, ranking, intelligence, explanations, pagination, and revision ownership remain backend concerns. P10-FR-01 through P10-FR-04 are fixed, including the follow-up acceptance of the frozen empty `collection_not_requested` page state. The final post-fix integration/runtime gate passes, so P10-F1 through P10-F5 and P10 as a whole are frozen.

## P11 Integrity / rebuild / repair / revert / recovery UI — Complete and frozen

P11-A is complete. `docs/p11/P11_INTEGRITY_MODEL.md` records the verified authority map, fixed invariant registry, restrained severity/future-handling model, and explicit `ReadOnlyIntegrityChecker`. It checks schema/SQLite/FKs, identity and canonical chains, corrections, observations/media/reviews, evidence and graph projection equivalence, notes/mentions, merge manifests/inverse structure, and journal transitions/results from one query-only snapshot. It creates no journal row and performs no mutation.

P11-B is complete. The existing graph service command now performs explicit recovery only: full P11-A preflight; refusal on authoritative ambiguity; one `BEGIN IMMEDIATE` snapshot; shared deterministic projection calculation; no-op comparison; complete derived replacement and in-transaction validation; one revision advance only on change; bounded immutable journal result; and post-commit P11-A verification. Current-schema startup no longer silently repairs projection drift. There is no schema, dependency, HTTP/API, frontend, worker, polling, vector-index, structured-repair, or revert change.

P11-C1 authority audit/catalog/execution design, P11-C2A's consolidated note/evidence/graph refreeze, and both catalog commands are complete. R01 restores only an otherwise-valid archived terminal survivor from a finding-bound token. R02 binds one existing note/person group and selects exactly one of five frozen append/retire plans; preserves immutable revisions, mention snapshots, retired occurrence/evidence history, other evidence types, correction/canonical authority, and unrelated state; maintains only the affected graph aggregate; follows the exact revision rule; journals atomically; and requires full P11-A afterward. Only the exact stale-active `NOTE_REFERENCE` on a proven inactive source is admitted from `P11-EVIDENCE-001`; every other evidence finding refuses. Generic repair, canonical retargeting, lifecycle/identity guessing, missing-history reconstruction, automatic invocation, and revert remain rejected.

P11-A1 records the first safety-stop correction: the former row-by-row `P11-NOTE-002` rule incorrectly expected a retired occurrence to reactivate when its person appeared in a later revision. P11-C2A records the second safety-stop correction: `P11-EVIDENCE-001` and the shared graph builder incorrectly expected each retired evidence revision to mirror current occurrence state. The consolidated rule validates occurrence/evidence history per row, enforces current active cardinalities separately, aggregates active evidence only, preserves the wholly-missing-group coverage boundary, and changes no normal domain mutation code.

P11-D is complete. The audit classifies only the no-survivor-mutation/no-later-dependency subset of normalized `identity.merge` as `SAFE_GUARDED_REVERT`. `prepare_revert()` returns an immutable schema-v28 token binding operation identity/type/fingerprint, exact journal and merge history, affected entities, source/target state, relevant lifecycle/graph revisions, projection fingerprint, and dependency state. `execute_revert()` revalidates under `BEGIN IMMEDIATE`, restores the formerly active source without deleting the merge manifest, rebuilds/validates the graph, appends a new `identity.merge.revert`, transitions the original merge to `REVERTED`, and runs P11-A after commit. Profile/note/biometric-changing merges, archived-source merges, later-dependent merges, corrections, repairs, evidence retirements, note retirement, finalisation, and projection rebuild refuse; lifecycle/profile/note/face operations remain forward compensating operations where normal domain commands permit them; physically purged data remains backup/restore-only. P11-E exposes only this frozen prepare/execute command; there is no generic undo/revert-all, schema, dependency, worker, polling, or automatic discovery.

P11-E is complete. `IntegrityRecoveryApplication` runs P11-A, emits a bounded redacted version-1 DTO, maps only exact finding groups to preparation references, signs report/action and typed P11-C/D preconditions with a process-local server secret, and delegates execution only to P11-B, R01, R02, and P11-D. All ten `/api/integrity/*` routes explicitly require `recovery`, reject unknown request fields, derive actor identity from the authenticated administrator session, work independently of recognition model readiness, return typed conflicts for stale/refused actions, and preserve `committed: true` for post-check failures. The Debug/System panel implements manual check → select → prepare → exact plan → reason/confirmation → execute → returned P11-A report. It does not infer repair plans or reversibility, patch domain state optimistically, poll, auto-run, add a worker/scheduler, or expose P12 behavior.

P11 exit is satisfied: corruption/drift is reported without inference, rebuild is idempotent, supported repair/revert is guarded and audited, the UI cannot bypass preparation, and authority is never reconstructed by guessing. P12 consumes those gates without broadening them.

## P12 Backup/Restore — Complete

Portable format v3 binds the encrypted SQLite snapshot, schema and non-secret key identity, journal/integrity fingerprints, and complete durable-media closure through a server-owned stable-row registry. Backup creation snapshots first, enumerates from that snapshot, authenticates copied protected content, detects concurrent replacement/truncation, and marks incomplete captures non-restorable. Restore explicitly requires administrator `database_restore`, a backup ID and operation UUID, a complete verified safety backup, disposable staged migration, registry-only path rewrite, protected-media authentication, deterministic P11-B rebuild, and clean P11-A before install and after reload. Source history is preserved and restore becomes new immutable history; a sidecar/receipt coordinates interruption without becoming domain authority. All registered older schemas migrate only on the staged copy; future/unknown/incomplete/ambiguous/wrong-key inputs refuse. Failure injection across every installation boundary proves old authority or safety-backup rollback, with no half-installed database/media pair. Exit satisfied with no schema/dependency/worker/polling change and only the existing UI's required response-contract adjustment.

## P13 Runtime hardening — Complete

P13-A adds immutable server-owned model bundles, opaque expiring single-use uploads, strict fixed-shape manifests, duplicate/traversal/symlink/size/malformed-content refusal, bounded stale cleanup, and one active-bundle authority shared by UI-server and ONNX CLI startup; loose startup-path flags no longer bypass it. P13-B adds signed expiring preparation tokens bound to candidate/current fingerprints, calibration and usage declarations, manifest versions, CPU ONNX loading, detector/recognizer contracts, embedding dimension, thresholds, and runtime availability. P13-C adds administrator-only exact-token activation and explicit rollback, stable-engine recognition-component swapping, previous-known-good retention, operational filesystem receipts, stale refusal, failure rollback, and idempotent UUID retry. Model state remains outside SQLite and domain journals.

P13-D adds a cross-process instance lock, startup readiness, SIGINT/SIGTERM admission stop, queue cancellation, bounded drain, maintenance/network monitor stop, HTTP/store close, and lock release; browser heartbeat does not control shutdown. P13-E adds production INFO defaults, structured centralized redaction, and bounded authenticated encrypted log rotation/retention. P13-F validates managed directories, writability, disk headroom, symlink containment, safe temporary cleanup, keyring/key compatibility before recovered-key replacement, and SQLite durability pragmas. P13-G adds adversarial model, activation/rollback, lifecycle/signal, redaction/rotation, permissions/symlink, disk-pressure, authorization, path-leakage, and regression gates.

Exit: schema remains v28; recognition remains proposal-only; P10/P11/P12 semantics, backup authority, media registry, graph, repairs, and domain history are unchanged. No telemetry, cloud/model download, licensing, activation-key gating, installer, signing, updater, packaging, release automation, worker, scheduler, or polling behavior was added.

## P14 Windows packaging/licensing — Implementation and unsigned Windows acceptance complete; production acceptance pending

P14-A adds strict canonical SFE2/Ed25519 offline license authority, public-key selection, MachineGuid fingerprint v2, and bounded per-user HKCU persistence outside domain authority. P14-B adds administrator-only authenticated activation and a backend-enforced unlicensed recovery shell that preserves model prerequisites, backup/restore, P11 recovery, and support. P14-C/D add one release-version authority, Nuitka standalone Windows x64 construction, immutable Program Files installation, the existing LocalAppData authority, exact verified outbound firewall policy, graceful upgrade shutdown, downgrade refusal, and data-preserving uninstall. P14-E adds external Authenticode hooks, signature verification, checksums, dependency/license inventory, provenance, artifact inspection, and active CI packaging gates. No model weights or private license key are included.

Exit status: the historical Windows 11 x64 development acceptance matrix in `docs/p14/P14_RELEASE_ACCEPTANCE.md` passed source regression, installed runtime, clean install, unlicensed recovery, licensing tests with ephemeral keys, model onboarding/rollback, firewall enforcement, repair, an earlier-version upgrade, downgrade refusal, uninstall/reinstall preservation, failed-install rollback, and artifact inspection for an earlier installer. The current 2.0.0 pre-tag candidate passed source, build, inspection, and packaged runtime checks; its installed lifecycle and packaged model onboarding/activation/rollback remain pending on a disposable Windows host. The intended controlled-production release version is `2.0.0`. Production acceptance also requires verified executable and installer signatures and final artifacts built from clean exact `rc-v2.0.0` or `release-v2.0.0` tagged source. The production trust-root match is independently verified; a production token was not provided.

## Cross-phase gates

- Preserve `FaceEngine`, `IdentityStore`, SQLite, loopback API, React controllers/views, derived vector indexes, and backup services where reasonable.
- Do not use recognition proposals, temporary queue groups, or frontend graph objects as authoritative inputs.
- Every graph-affecting change and its journal entry share one transaction.
- Add tests for failure rollback, idempotent retries, canonical merge chains, evidence independence, participant deduplication, no self-links, archived/tombstoned rendering data, rebuild equivalence, and zero non-loopback network access.

## Issue #3 independent QA timestamp repair

Original f3faa7582692cd4f8e20d8804da884c5d39a14c3 reproduced the A/B/C
offset failure. Shared World predicates, proof/event ordering, recurrence and cluster
occurrence extrema now use exact UTC instants while returning original source text.
Naive values retain UTC semantics. Calendar days use the same parser to avoid
SQLite fractional rounding at midnight. Cursor fingerprints include chronology.
No schema, journal, source timestamp, UI, bounds or index definition changes.

Native SQLite floating date conversions were rejected because microsecond boundaries
can round; rewriting timestamps would destroy original offset/precision provenance.
Instead SQL invokes the existing Python UTC parser through bounded request-local
4,096-entry parsing and integer-key memoization. Discovery SQL materializes one
key per effective Encounter after status/location filtering and before participant
joins, then reuses it for range predicates, exact integer UTC ordinal days and
support ordering. This avoids repeated normalization when timestamp cardinality
exceeds the memoization bound. Integer microseconds fit SQLite
64-bit integers over Python's full datetime range. SQL still owns joins, grouping,
ordering and pagination; no complete dataset is returned to Python for sorting.

Verification: 773 backend passed / 54 skipped / 137 subtests; 124 frontend passed;
production build, committed asset equality, dependency and compile checks passed.
Additional offset/proof/midnight/restart assertions passed. Skips remain existing
obsolete compatibility and platform requirements. Final CI evidence accompanies PR #14.

Matched sequential single-read smoke measurements (same fixture/parameters, separate
detached original checkout and corrected checkout, no competing full-suite run):

| Dataset / discovery | Original seconds | Corrected seconds | SQL statements | Payload bytes |
| --- | ---: | ---: | ---: | ---: |
| 100 people / 1,000 Encounters: frequent | .014 | .014 | 9 | 10,985 |
| same: recent | .028 | .028 | 10 | 10,940 |
| same: locations | .017 | .017 | 10 | 11,063 |
| 10,000 people / 100,000 Encounters: frequent | 1.305 | 1.373 | 9 | 10,989 |
| same: recent | 3.436 | 3.228 | 10 | 10,944 |
| same: locations | 1.933 | 1.907 | 10 | 11,067 |

Statement counts/payloads were identical; existing participant-first index protections
and bounded page regressions pass. On this existing fixture the corrected reads remain close to the original; these
single samples vary by -.208 to +.068 seconds. These
are development smoke samples, not universal latency estimates or p50/p95 claims.
Reproduce with the existing test_discovery_scale_bounds_and_determinism test in
tests/test_world_intelligence.py on the original and corrected source separately.
Independent QA must retest offset boundaries, same UTC day across offsets, fractional
midnight, proof extrema/order, stable cursor walks, and representative timestamp
cardinality beyond the 4,096-entry memoization bound. Acceptance remains pending.

A matched stress workload additionally assigns 100,000 distinct microsecond
instants across UTC/+02:00/-02:00 representations to the same 10,000-person /
100,000-Encounter fixture (all within one valid UTC day). Original→corrected
seconds: frequent 2.356→2.841; recent 2.891→3.563; locations 3.349→3.743.
Returned subject IDs/counts and the 10-person/3-support/2-location caps agree.
The remaining .394–.672s overhead (12–23%) is exact instant parsing/key creation
for unique source values; it is not hidden by an unbounded cache. The first
memoization-only candidate was rejected after this workload showed ~50% overhead.
Query-local Encounter normalization reduced that overhead without a migration or
source rewrite. Fixture generation and scope are identical between revisions, and
latencies exclude seeding; these remain single-read development smoke samples.

### Issue #3 historical timestamp compatibility repair (2026-10-28)

Independent QA found a compatibility regression on `136332610eb27e89dae69c8e65e21a604638b353`:
the storage interface accepts non-date observed-time text, but strict UTC parsing
made unscoped World relationships, scoped reads and discoveries throw instead of
returning valid coexisting records. Reproduced independently through
`GraphReadService` with `bad-date` plus a valid finalized Encounter for one pair.
The submitted source raises `ValueError: Invalid World occurrence: bad-date`.

The correction keeps strict request parsing and adds a historical-source parser
returning unknown for malformed or UTC-out-of-range dates. Request-local bounded
memoization includes unknown results. SQL time keys are NULL for unknowns; date
predicates exclude them, while unscoped evidence/recurrence counts retain them.
A source-preserving SQL function supplies NULL to extrema without losing the raw
record; SQL collation, Python edge/cluster extrema, event/evidence explanations
and recurrence bounds consistently handle unknowns. Raw `occurred_at` remains
unchanged. Chronological SQL pages place valid instants first, then unknowns, with
stable source-ID ties. The chronology fingerprint changes to reject older cursors.
Discovery normalization/CTE reuse, exact integer microseconds and UTC calendar-day
grouping remain intact; no schema, migration, historical rewrite or durable cache.

Regression coverage exercises Current and Explore through the service boundary:
one invalid plus valid, several/all invalid, invalid-only corrected relationships,
valid extrema, recurrence counts, proof and Encounter cursor walks, unknown ties,
7/30/90-day frequency, latest UTC day, locations, offsets and midnight microseconds,
strict malformed/out-of-range request rejection, revision consistency, corrections,
rebuild/restart and encrypted backup/restore with invalid history. Original A/B/C
and all previous UTC precision tests remain unchanged.

Matched sequential performance smoke samples against failed SHA `1363326`, same
fixtures/parameters/limits as above, seeding excluded, no concurrent test workloads:

| Dataset/read | Failed SHA seconds | Compatibility fix seconds | Statements | Payload bytes |
| --- | ---: | ---: | ---: | ---: |
| 100 people / 1k Encounters: frequent | .016 | .014 | 9 | 10,985 |
| same: latest day | .028 | .028 | 10 | 10,940 |
| same: locations | .018 | .018 | 10 | 11,063 |
| 10k people / 100k Encounters: frequent | 1.481 | 1.350 | 9 | 10,989 |
| same: latest day | 3.924 | 3.072 | 10 | 10,944 |
| same: locations | 1.936 | 1.777 | 10 | 11,067 |
| same: relationships | .716 | .676 | 11 | 29,770 |
| same: clusters | .655 | .646 | 9 | 10,077 |

The existing scale test passes bounded response, deterministic results, statement
count and latency assertions on both sources. A separate matched stress fixture
with 100k distinct microsecond instants across UTC/+02/-02 gives failed→corrected
seconds: frequent 2.885→2.726, latest day 3.743→3.737, locations 3.731→3.588.
Returned Person IDs/counts and caps match. No material regression appears; timing
variation is not evidence of an intrinsic speed improvement. These are single-read
development samples, not universal estimates or p50/p95. The standard test is
`test_discovery_scale_bounds_and_determinism`; the stress fixture uses the same
`_seed(10000,100000,participants_per_event=2)` then assigns event i the instant
2026-08-01T12:00:00Z + i microseconds, cycling +02/-02/UTC representations, with
as_of 2026-08-02T00:00:00Z and limits people=10/events=3/facets=2. Failed-source
malformed-data workloads cannot produce a successful comparison: their exception
is the independently reproduced defect.

Final local verification: Python 3.12 full suite **784 passed, 54 skipped,
137 subtests passed** (121.67s). The 54 skips retain 42 obsolete compatibility tests
and 12 Windows PowerShell requirements on Linux. Focused new compatibility,
strict-date, UTC and restore tests: **17 passed**. World suites before the three
additional strict UTC-overflow parameter cases: **76 passed, 15 subtests passed**;
the final full suite includes all cases. Frontend **124 passed**; production build,
committed-asset equality, dependency, compile and whitespace checks passed. Final
self-review found no unrelated UI, identity, authority or historical-data writes.
Exact-source five-job CI evidence is recorded on draft PR #14. Independent QA and
operator approval remain required; no merge, release or Issue #3 closure.
