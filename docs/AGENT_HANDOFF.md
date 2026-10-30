# SentriFace Edge agent handoff

## Current handoff — 2026-10-29

**Hardening:** [World intelligence #3](https://github.com/suraj-singh12/sentri-face-edge/issues/3) is merged at `f907073edc3375dbfd15b8bb39cc6d32bc60f6b6` (schema v34). It adds backend discoveries/evidence reads without replacing the Current World UI. [Explore #13](https://github.com/suraj-singh12/sentri-face-edge/issues/13) awaits approved design/implementation; its related [draft PR #15](https://github.com/suraj-singh12/sentri-face-edge/pull/15) is unmerged, with pre-existing effective-participant discrepancy tracked by [P1 #22](https://github.com/suraj-singh12/sentri-face-edge/issues/22).

**QA:** [Foundation #17](https://github.com/suraj-singh12/sentri-face-edge/issues/17) has executed two real macOS browser/ONNX journeys through finalized Encounter, People/Events/World independent reads, restart and negative controls. [PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23) at `b81d451` passed [all five CI jobs](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40905213311) and was merged via #23 as `6a9ec82` after the final documentation head `6eda54a` passed all five jobs. Reuse `tests/qa_coverage.json` and the QA runbook in [DEVELOPMENT_MODE](DEVELOPMENT_MODE.md#qa-foundation-17); keep genuine photos/models, database and browser evidence outside Git/CI.

**Boundaries:** Python 3.12 only; production signing and current-artifact installer/model lifecycle acceptance remain pending under [#5](https://github.com/suraj-singh12/sentri-face-edge/issues/5). [Main CI #9](https://github.com/suraj-singh12/sentri-face-edge/issues/9) is explicitly deferred; do not touch `main` or merge draft work without authorization. For live priority and task status use [docs/README](README.md) and GitHub Issues.

## Historical Batch 3.7 / CI repair

Batch 3.7 was committed as `555433f082dc39112bd815dddf3a8f35791f2f4b` (schema v34), following previous schema-v33 Attach ownership. CI repair [#1](https://github.com/suraj-singh12/sentri-face-edge/issues/1) / [PR #8](https://github.com/suraj-singh12/sentri-face-edge/pull/8) passed five jobs at its original checkpoint `683f3641e3532f08e180fe6c4c4386ac0f798917`. Detailed historical results are below; do not confuse them with current PR #23 acceptance.

Normal different photos independently infer E1/E2; the earlier fixture manually reused `(1,0)`. Exact-vector dedup remains legitimate but cannot collapse source identity. Encounter reassignment never transfers Reference ownership. Conflicting shared-row current canonical owners derive recognition exclusion; source active state/count/history remain intact. Do not restore the old global-embedding interpretation or serialize a mutable conflict flag.

Canonical contributor reading order remains AGENTS → docs/README → IMPLEMENTATION_PLAN → PROJECT_OVERVIEW → ARCHITECTURE_STATE → DOMAIN_MODEL → FEATURES_BY_TAB → ARCHITECTURE_EXPLANATION → this handoff. Exact final verification/qualification and first failures are recorded in `/workspace/scratch/sentriface-batch37/REPORT.md`; prior partial evidence is preserved separately there. Future work must retain encryption, immutable source history, registry-owned authenticated closure and protected Linux source recovery custody.

**Final Batch 3.7 pre-commit qualification (code now pushed):** backend 736 passed / 47 skipped / 137 subtests; frontend 124 passed; production build, Python compile and diff checks passed. Real CPU ONNX/Chromium exercised both shared Reference entry points, admission rejection, cap/lifecycle, canonical merge, cross-role guards, permissions and retained Attach ownership. A supported encrypted backup restored into a completely fresh authority and normal restart preserved domain truth. Supported graph rebuild passed with unchanged Reference state and occurrence projection. Exact evidence, first failures and scope limits remain in the external Batch 3.7 report.

Encounter revision fingerprints exclude physical media locations, which legitimately relocate during restore; media IDs and semantic provenance remain versioned. Migration translates only still-valid pre-v34 Attach preconditions to the new fingerprint. Genuinely stale revisions remain stale. Source-scoped profile reads show the requested Person's own Reference/Encounter media instead of a shared embedding row's original image. Historical raw embedding ownership remains preserved. Cached legacy Add Face UI drafts can only be cancelled and reopened through the shared Reference route; there is no old admission bypass.

Following the historical Batch 3.7 checkpoint, World backend #3 was implemented and merged. Pending product work is [#22](https://github.com/suraj-singh12/sentri-face-edge/issues/22), [World Explore #13](https://github.com/suraj-singh12/sentri-face-edge/issues/13), [Encounter Split/Merge #4](https://github.com/suraj-singh12/sentri-face-edge/issues/4), [operator UI #6](https://github.com/suraj-singh12/sentri-face-edge/issues/6), and [release acceptance #5](https://github.com/suraj-singh12/sentri-face-edge/issues/5). QA #18–#21 remain gated. Review each issue before implementation; keep substantial UI Figma-first and never silently start another issue.

## Historical checkpoint — Batch 3.6 handoff

Baseline verified clean on `release-v2.0.0-hardening` at `1ea2a38d10be0da4c00fea4a3f53053b9eaef998`. At that checkpoint repairs were uncommitted; commit/tag/Batch 4 work was not authorized. Reuse media_registry source provenance for writer admission and P11; preserve its exclusion of self-proving observation membership and scoped accepted-face media bindings. Preserve registry-owned authenticated backup closure and staged-only relocation guards.

Merge retires affected canonical standing-manual collisions deterministically inside its transaction, retaining raw history and IDs. Recognition displays full server-staged operator decisions rather than stale proposals; candidate browsing fixes nested PersonSummary access. No schema, World algorithm, recognition model/threshold or packaged custody change.

Verification: 694 backend passed / 47 skipped / 135 subtests; 120 frontend passed; production build passed. Earlier focused setup failures and browser action/response-capture limitations are preserved in `/workspace/scratch/sentriface-batch36/`. Real complex rebuild succeeded; fresh supported recovery-kit import/Restore Safely, original administrator login and ordinary restored restart succeeded. Domain/assets/current reads match after declared physical-path, precondition-token and photo tie-order normalization; supported journals are the only durable authority additions. Secrets/kit/export remain in separate private directories.

At that checkpoint the next gate was a separately frozen clean-room reaudit; its uncommitted qualification was not Windows packaged release acceptance. Previous batch sections below are historical checkpoints.


## Historical Batch 3.5 handoff

Starting branch/baseline: `release-v2.0.0-hardening`, `cf8c847337735dc7d1acc4b185f9d0e1f01a732d`. At that checkpoint Batch 3.5 changes were uncommitted and auto-commit/tag was not authorized. Final gates are 676 backend passed / 47 skipped / 135 subtests, 118 frontend passed, production build and diff check passed. Targeted real ONNX/SQLCipher browser qualification and fresh recovery→restore→restart equivalence are complete; consult the tracker for evidence and bounded uncertainty. The next step after acceptance is a separately frozen three-phase clean-room reaudit, not Batch 4.

Preserve the canonical effective frame-support helper, durable face decision distinctions, explicit Person enrollment contract, common read reconciliation, archived historical profile capability, cancellation cleanup ordering and lifecycle preflight/revalidation. Do not replace active/effective evidence reads with historical generations or compact provenance. Linux source recovery uses the same source eligibility/storage boundary, a private encrypted recovery-code record, and validated recovery-kit key admission. Normal OS custody/packaged enforcement is unchanged. Select source recovery at construction before background workers, never as a late replacement. Preserve the staged-only completed-review media-relocation transaction and reinstated live guard. Standalone completion retries retain the original operation ID.

Qualification artifacts are outside tracked source at `/workspace/scratch/sentriface-batch3-5/`; credentials/recovery codes there are private qualification data and must not be printed, screenshotted or committed. The original clean-room evidence remains separate. World scoring/clustering, note scope distinctions, draft isolation, idempotency, permissions, recognition models and release packaging remain protected.

This is the shortest safe path for an engineer or coding agent taking over the
current 2.0.0 release work. It is an orientation guide, not a replacement for the
normative rules in the repository-root `AGENTS.md`.

## Batch 3 handoff (2026-10-02)

The committed Batch 3 baseline and current verification follow-up contain schema v32 finalized Encounter management and People integration. Use existing review completion for Attach Media; do not create a second observation or duplicate managed assets. Effective reads overlay append-only metadata/participant revisions and retain original face/correction/Relations history. Canonical merge conflicts require explicit Encounter Relations resolution. Manual create/retire uses normalized evidence and existing `add`; finalized corrections use `destroy`; reads use `view`. The deleted-Person historical summary fix permits tombstone access without widening active recognition eligibility. The follow-up deduplicates active canonical manual assertions, retains actual accepted-face media in existing immutable decision JSON, guards Move Face during amendments, and keeps legacy identity corrections consistent with participant revisions. A typed merge refusal supplies the existing Encounter ID for direct operator navigation.

Batch 3 gates: 577 backend passed, 47 skipped, 115 subtests passed; 112 frontend passed; production build and diff check passed. Authenticated synthetic-data UI exercised corrections, profile integration, manual add/retire and same-occurrence attachment. Follow-up gates: 583 backend passed, 47 skipped, 115 subtests; 112 frontend passed; build/diff check passed. A real Linux Secret Service vault enabled authenticated tests. Chromium exercised same-occurrence attachment, corrections, profile/manual controls, a small window and tombstone historical reads on isolated synthetic data. The canonical tracker owns exact coverage and manual limits. Older gate counts below are historical. Preserve World vNext, Encounter Split/Merge, signing/current-artifact Windows acceptance and P14 update delivery as deferred. No auto-commit or tag. Reading order/README ownership is unchanged.

## Historical checkpoints — post-P14 through partial Batch 3.7

The records below preserve earlier source and release milestones. Their schema versions, test counts, working-tree status, artifacts and pending walkthroughs describe those checkpoints, not the current v34/green-CI baseline above. The dated P14 acceptance record owns the older artifact's checksum; it does not identify or accept the latest CI installer.

- Application version: `2.0.0` (`src/sentriface/_version.py`).
- Database schema at the earlier partial Batch 3.7 checkpoint: v33 (`SQLiteIdentityStore`), extending v32 with targeted scan ownership; v30 is the Batch 2 staging foundation and v28 remains the frozen P11/P14 release baseline.
- Batch 2/3 correction: durable pre-grouping media exclusion/restore, automatic finalized-media exclusion, reconciled group IDs/selected faces, combined canonical committed+active-draft recognition and proof-only duplicate prevention, atomic selected-face draft decisions, current-value form validation, 4.5-second default notifications, 250×250 Peek In and left-aligned recognition preference. Drafted means draft-created Person only. This is the historical Batch 2 stabilization checkpoint. Batch 3 now implements Encounter Management/Attach/Correct, profile/manual association integration and the deleted-Person historical-read fix; World vNext and Encounter Split/Merge remain deferred.
- Final correctness gates: 561 backend tests passed, 47 skipped, 114 subtests; 112 frontend tests passed; production build/diff check passed. Authenticated synthetic-media development UI verified removal/reload, Event→Person flow, Peek In, filled forms, proof-only draft reuse, quality preference, final completion and Person Profile persistence. This is not production-model, full-role or release acceptance.
- P0 through P14 source implementation is complete.
- P10 through P13 are frozen.
- Windows source mode and the unsigned pre-tag Windows 11 AMD64 build gates pass.
  That checkpoint's engineering installer and evidence were under
  `dist/windows-x64/2.0.0/`; see `docs/p14/P14_RELEASE_ACCEPTANCE.md` for its
  checksum and exact acceptance boundary.
- A controlled non-exportable signing identity exists, but installing its public
  certificate into CurrentUser Root and TrustedPublisher was not authorized.
  Production release acceptance therefore still requires explicit trust-store
  approval, a verified signed candidate, the disposable-machine installer/model
  lifecycle, and a final clean build from exact tag `rc-v2.0.0` or
  `release-v2.0.0`.
- That checkpoint's artifact had not passed installed model onboarding, activation,
  restart persistence, rollback, or recognition with representative face images.
  Source-mode model lifecycle and packaged external ONNX sessions passed; the
  earlier installer lifecycle in the P14 record applies to a different artifact.
- The runtime is offline and loopback-only. Do not weaken the application socket
  guard, OS network-policy checks, or localhost request validation.
- Post-P14 source stabilization fixes the shared person-profile read contract,
  review selection state, form scroll, country search, operator terminology,
  Settings layout, and macOS development reset. A subsequent recognition UI
  correction lets the result panels keep their height above the action buttons,
  compacts the new-person form, and scrolls that form below the fixed header.
  The source backend suite (532 passed, 47 skipped, 106 subtests), frontend suite
  (99 passed), and frontend build pass. The recognition and Review Photos
  transitions still need live UI verification. Do not treat those manual flows
  as release acceptance.
- The 2026-09-27 Encounter batch places shared Event metadata and selected Event Note IDs on finalized observations, separates Event and Person forms, repairs Queue metadata/mentions, and uses the existing sighting note subject. Event Note IDs are Encounter→Person references, never Person relationship evidence. Pre-Batch-2 integration adds explicit NO_FACE Browse, durable face-origin reads, accepted-poor recognition fallback, a proof-only pre-creation duplicate check, and bounded read-only Global/Person Events. Schema v29 carries embedding eligibility and Queue search preference. Historical >~1 MB upload media is reduced before persistence; CPU detector preparation is transient. Current feature/role inventory is `docs/FEATURES_BY_TAB.md`; exact status and risks are in `docs/IMPLEMENTATION_PLAN.md`.
- At the Batch 2 checkpoint, the then-uncommitted working tree extended existing Queue staging and atomic review completion with serial Encounter drafts and durable Relations decisions. Schema v30 adds staging links and the minimal negative decision authority; positive evidence and graph projection remain separate. Exact retained media dedup, draft recognition overlay, lifecycle guards and relation-aware correction are implemented in source. Full backend/frontend/build gates pass; the canonical tracker records exact results and the outstanding live authenticated UI walkthrough. Do not treat this as a signed release or Windows acceptance.
- The 2026-09-29 post-Batch-2 stabilization refines this same working tree. Review Photos now identifies finalized-media conflicts per photo and can continue with valid siblings; grouping is Encounter-first, asks for a count, and can suggest existing uploaded-subfolder boundaries. Skip is temporary group deferral and never a final identity decision; all deferred groups return automatically. Long queue reviews use page scroll, the current face is boxed, Relations choices show pressed state, and Person Graph hover explains distinct canonical shared Encounters and directed note references. No new schema, authority, or World scoring was added. The tracker owns exact verification status and deferred manual walkthrough.

## Read in this order

1. `AGENTS.md` — non-negotiable product, authority, transaction, and test rules.
2. `docs/README.md` — documentation map.
3. `docs/IMPLEMENTATION_PLAN.md` — canonical current batch tracker and phase order.
4. `docs/PROJECT_OVERVIEW.md` — product mental model.
5. `docs/ARCHITECTURE_STATE.md` — current implementation checkpoint.
6. `docs/DOMAIN_MODEL.md` — normative authority and terminology.
7. `docs/FEATURES_BY_TAB.md` — current screens, roles and boundaries.
8. `docs/ARCHITECTURE_EXPLANATION.md` — detailed design reasoning.
9. This handoff — operational and release boundary.
10. The relevant frozen phase record under `docs/p10`, `docs/p11`, `docs/p12`, or
   `docs/p14` before changing that area.

Historical files and pre-optimization benchmark artifacts are evidence, not
current authority. `src/sentriface/ui_static/` is generated from `frontend/` and
must not be edited by hand.

## Architectural map

| Concern | Primary implementation |
| --- | --- |
| Domain records | `src/sentriface/models.py` |
| Storage contract | `src/sentriface/contracts.py::IdentityStore` |
| SQLCipher store and migrations | `src/sentriface/storage/sqlite_store.py::SQLiteIdentityStore` |
| Recognition/application boundary | `src/sentriface/engine.py::FaceEngine` |
| Loopback API, auth, and route policy | `src/sentriface/api_server.py` |
| Identity lifecycle and merge | `src/sentriface/{identity_service,merge_service,revert_service}.py` |
| Evidence graph and read models | `src/sentriface/{graph_service,graph_read_service,intelligence_service}.py` |
| Integrity and recovery | `src/sentriface/{integrity,structured_repair_service,integrity_recovery_service}.py` |
| Backup/restore and media closure | `src/sentriface/{backup_service,media_registry}.py` |
| Model authority and runtime activation | `src/sentriface/{model_bundle,model_activation,model_setup}.py` |
| Runtime/offline hardening | `src/sentriface/{runtime_hardening,offline_guard,os_network_policy}.py` |
| Licensing | `src/sentriface/licensing/` |
| React shell and controllers | `frontend/src/SentriFaceApp.jsx`, `frontend/src/hooks/` |
| React views | `frontend/src/views/` |
| Windows release build | `build_release.ps1`, `installer/SentriFaceEdge.iss`, `packaging/windows/` |

## Authority rules to keep in mind

- Recognition output is a proposal. Only explicit operator finalisation creates
  identity, participant, evidence, or graph truth.
- Multi-face review is all-or-nothing: every face needs a final decision before
  the operator completes the review.
- Graph edges are derived from independently retained evidence. Removing one
  evidence record must not remove an edge supported by other evidence.
- Corrections and merges preserve raw history. Archive and delete are lifecycle
  states; merge sources resolve to a surviving canonical identity.
- Important writes use an operation/idempotency ID. A graph-affecting authority
  change, its evidence/projection change, and its journal transition commit in
  one SQLite transaction.
- The React application renders backend truth; it does not maintain durable
  identity associations or reconstruct graph semantics.

## Local development

Use Python 3.12 only; Python 3.11 support is disabled. On macOS, use the source launcher for a fast,
product-isolated synthetic development run:

```bash
./run.sh
```

Open `http://127.0.0.1:8765`. The development runtime exercises application
workflows but produces synthetic face results. It uses
`~/Library/Application Support/SentriFace-Dev`, never the installed-product
authority. Real ONNX source setup and model licensing steps are documented in
the root `README.md` and `models/MODELS.md`.

On Windows, use the equivalent PowerShell launcher:

```powershell
.\run.ps1
```

It uses `%LOCALAPPDATA%\SentriFace-Dev` and a repository-local `.venv312`; it
refuses the installed-product authority. See `docs/DEVELOPMENT_MODE.md` for real
ONNX setup, the execution-policy fallback, and the confirmed development-only
reset.

The normal verification gate is:

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Run focused tests first while developing. Migration, graph, backup/restore,
runtime-hardening, licensing, and packaging work has additional mandatory gates
in `AGENTS.md`, the phase acceptance documents, and `packaging/README.md`.

## Release and support boundary

- `src/sentriface/_version.py::APP_VERSION` is the release version authority.
- Production release mode requires a clean tree at exact tag `rc-v<version>` or
  `release-v<version>`.
- Model weights and private signing/license keys must never enter release artifacts.
- Windows uninstall intentionally preserves per-user data, models, backups,
  recovery material, logs, license state, and the OS-vault key.
- `tools/wipe_clean_this_machine_installation_and_data.py` and credential cleanup
  scripts are destructive test/support utilities. Read `tools/dangerous_scripts.md`
  before using them; never run them on a machine containing required data.
- A packaged Windows startup failure now displays a native error dialog as well
  as the diagnostic console message, while retaining fail-closed startup.

## Before handing off again

1. Keep `docs/ARCHITECTURE_STATE.md` and `docs/IMPLEMENTATION_PLAN.md` consistent.
2. Update `docs/README.md` when adding, moving, or superseding a document.
3. Record operator-visible changes in `CHANGELOG.md`.
4. Preserve historical acceptance records rather than rewriting them as current.
5. Report the branch, changed files, tests run, and any remaining release gate.
