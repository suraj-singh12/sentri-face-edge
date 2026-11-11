# Existing architecture and reuse map

Source reviewed: `b457f0a723e845dd1a92a07a577072c85146c89a` (hardening). This is a **source review**, not a runtime acceptance report or an approved redesign. Runtime evidence and findings belong to the audit INDEX/journeys/findings. [The canonical charter](../../docs/UI_UX_DESIGN.md), [feature map](../../docs/FEATURES_BY_TAB.md), and [domain model](../../docs/DOMAIN_MODEL.md) remain the authorities.

## Existing boundaries to retain

The current composition is `AuthGate → ModelGate → RecoveryGate → SentriFaceShell`. [SentriFaceApp.jsx](../../frontend/src/SentriFaceApp.jsx) owns navigation, capabilities, theme, notices and shared backup/password dialogs. [useSentriFaceController](../../frontend/src/hooks/useSentriFaceController.js) composes existing hooks; it is not a second domain store. Controllers send intent through [useApiClient](../../frontend/src/hooks/useApiClient.js) to the authenticated loopback API. [api_server.py](../../src/sentriface/api_server.py) independently checks capabilities and license policy. [FaceEngine](../../src/sentriface/engine.py), the [IdentityStore protocol](../../src/sentriface/contracts.py), and [SQLiteIdentityStore](../../src/sentriface/storage/sqlite_store.py) retain domain, persistence and transaction authority.

A later design pass can reorganize presentation within these owners. Moving domain state into React, duplicating navigation authority, adding a second Encounter editor or creating a new graph store would increase risk without resolving a demonstrated task problem.

## UX-00–UX-15 reuse ownership

| UX ID | Current task/surface | Existing reusable owner | Preserve while refining |
| --- | --- | --- | --- |
| UX-00 | Initial owner, sign in, model admission, safety-copy and license gates | `components/AuthGate.jsx`, `ModelGate.jsx`, `RecoveryGate.jsx`; `hooks/useLicenseController.js` | Existing gate order; non-admin explanation/exit; disabled/working/error/retry; explicit model admission and recovery-risk acknowledgment. A model result is not an identity decision. |
| UX-01 | Shell, navigation, account, refresh, theme and quick backup | `SentriFaceApp.jsx`; `constants.js::VIEWS`; `useAppData.js`; `useApiClient.js` | Capability-filtered tabs, backup confirmation, password/sign-out behavior, retained context and live server refresh. License restriction routes to recovery Settings rather than silently removing recovery. |
| UX-02 | Check a photo, comparison, Browse People, follow-up and completion | `views/RecognizeView.jsx`; `hooks/useRecognizeController.js`; `components/Shared.jsx`; `RecognitionFollowupForm.jsx`; `reviewState.js` | Single-photo review authority, exact face selection, accepted/deferred/excluded decisions, existing completion operation IDs, proof-only duplicate hints and target-specific enrollment. No committed Person/profile exists merely because a new identity is staged. |
| UX-03 | Import, progress, sessions, media exclusions, Encounter grouping | `views/QueueView.jsx`; `hooks/useFileUploads.js`; `hooks/useQueueController.js` | Existing upload admission/cancellation and cleanup; persisted per-photo exclusions before grouping; finalized-media conflicts; operator-confirmed partition. Folder hints remain suggestions. |
| UX-04 | Event details, identity groups, Relations, completion, Attach retry | `QueueView.jsx`; `useQueueController.js`; `EncounterDetailsModal.jsx`; `RecognitionFollowupForm.jsx` | One active durable draft, explicit final decision for every face and every new participant pair, serial advance; final atomic completion. Targeted Attach cannot fall back into general new-Encounter grouping. |
| UX-05 | People collections/search/group/sort/grid/list/pagination | `views/PeopleView.jsx`; `utils/profileBrowse.js`; People read model from `useAppData.js` | Backend statistics and sort semantics; distinguish active, historical, no eligible reference and deleted-face states. Do not replace People collection semantics with graph filters. |
| UX-06 | Profile Overview/Photos/Sightings/Events/Associations/Activity and Person Graph | `PeopleView.jsx`; `PersonGraphView.jsx`; `hooks/usePeopleController.js`; `utils/personGraph.js`, `personGraphLayout.js` | Distinct meanings of sightings, Event mentions, operational activity and graph evidence; authoritative refresh/generation guards; historical inactive nodes; return path. |
| UX-07 | Create/edit/notes/favorite/recognition references/photo actions | Existing forms and drawers in `PeopleView.jsx`; `views/RecognitionReferences.jsx`; `usePeopleController.js` | Shared Add Face/Manage Recognition References operation, explicit no-context consent, /4 active source limit, quality and source lifecycle; note selected IDs. Retiring a Reference does not delete its media or create an occurrence. |
| UX-08 | Archive/restore/tombstone/merge and manual associations | Existing People management dialogs and association panel; `usePeopleController.js`; backend identity/lifecycle/evidence commands | Immutable raw history, canonical survivor, lifecycle eligibility, duplicate manual-pair handling, merge conflicts and Open conflicting Encounter path. Tombstone is not historical erasure. |
| UX-09 | Global Events, filters, details, participants/media/notes/history, Attach | `views/EventsView.jsx`; `useAppData.js::queryEncounters/loadEncounterDetail`; shared detail components | Same finalized Encounter ID across entry points; bounded newest-first pages; explicit attendance vs mention; `add` Attach permission independent of correction permission. |
| UX-10 | Metadata, participant and Relations corrections | `components/EncounterDetailsModal.jsx` with `correction`; `EncounterManagementModal.jsx`; `EventsView.jsx`; `useSentriFaceController.js::correctEncounter` | Current `expected_revision`, explicit pair choices, append-only history, reload after stale/conflict, atomic correction and journal. Corrections retain original finalization/provenance. |
| UX-11 | World Explore discovery, canvas, inspector and proof | `WorldWorkspace.jsx`; `WorldExploreView.jsx`, `WorldExploreCanvas.jsx`; `hooks/useWorldExplore.js`; separate `useWorldController` instance; World read utilities | Explore UI default, draft/Apply criteria, selected evidence, visual-only weaker toggle, local Period scope, bounded membership and source proof. Canvas layout does not determine membership. |
| UX-12 | World Connections, nested clusters/people/events/evidence/media | `WorldView.jsx`; `ClusterDrilldownView.jsx`, `WorldPersonDrilldownView.jsx`, `WorldEventDrilldownView.jsx`, `WorldEvidenceDrilldownView.jsx`, `WorldRelationshipProof.jsx`, `WorldMediaPreview.jsx`; World controllers | **Connections** name and existing `CURRENT` API semantics; separate scopes and retained selections; revision-bound bounded reads, back paths and stale invalidation. Event is a proof/history view, not a graph node. |
| UX-13 | License, backup/restore, accounts, integrity, details/log/support | `DebugView.jsx`; `LicensePanel.jsx`, `AccountsPanel.jsx`, `RecoveryPanel.jsx`, `MachineProfilePanel.jsx`, `AboutSupportPanel.jsx`; `useAppData.js`, recovery/license hooks | Per-section capabilities; no generic all-settings permission; verified portable backup closure and safe restore; guarded frozen P11 preparation/execute commands; source ONNX vs packaged boundary distinction. |
| UX-14 | Shared dialogs, popovers, menus, galleries, toasts and focus | Mantine primitives already used across views; `components/Shared.jsx`; shell dialogs; `useApiClient.js`; `sentriface-interface.css` | Consistent anatomy, labels and focus/escape/return expectations while retaining domain-specific confirmation strength. Native prompts and file selectors require separate capture/input treatment. |
| UX-15 | Cross-feature transitions and recovery | `useSentriFaceController.js` composition; `useAppData.js::reconcileDomainReads`; `usePeopleController.js::invalidatePersonGraph`; World revision/generation controllers; current navigation callbacks | Replace current reads from backend after mutations; do not patch graph counts/IDs optimistically; preserve Attach target/revision and caller return context. Recognition proposals never update graph evidence. |

Paths in this table are under `frontend/src/` unless otherwise stated. This maps reuse owners, not counts of independent controls or verified runtime cases.

## Shared presentation assets already available

- **Provider:** Mantine 9.3.0, primary teal, Inter/system font stack, 8px `md`/`lg` radius, global Notifications in the shell. Refine through the existing provider and CSS rather than layering a new theme authority.
- **Theme surfaces:** `sentriface-interface.css` declares light/dark `--sentriface-app-bg`, `header-bg`, `card-bg`, `solid-card-bg`, `card-border`, `card-shadow`, `tab-color`, `muted-surface`, `border`, `accent-border/text`, `drop-border/bg`, `summary-bg`, `new-action-color/bg` and `metrics-bg/text`. Existing class families cover shell, recognition, Queue, People, Settings, World and Explore. Token reuse is viable, but contrast must be measured in rendered states, including gradients/translucency.
- **Responsive layout:** existing CSS breakpoints include 62em, 48em and Explore's 1100px compact panel selector. Existing workspace measurement uses actual inner height and element top; preserve viewport containment when reducing notice/header density.
- **Shared recognition components:** `Surface`, `ImageFrame`, `SafeImage`, `LoadImagePanel`, `BestMatchPanel`, `GalleryPanel`, `InputImageQuality`, `Metrics`, `Thumb`, `EmptyCard`. `SafeImage` already supplies an image-failure fallback; a later pass can make fallback feedback coherent instead of adding new gallery implementations.
- **Forms:** `RecognitionFollowupForm`, `CountrySelect`, `SavedLocationInput`, Event details/correction modal and existing Person editable fields. Saved-location autocomplete is a bounded backend read after three normalized characters; typing/cancellation must never register locations.
- **Icons:** current Tabler set supplies the established vocabulary. Preserve text labels and accessible names; matching icon appearance alone does not prove usable keyboard/screen-reader behavior.
- **Feedback:** `useApiClient` exposes common timeout/error/auth-required/models-required handling, in-flight GET deduplication and notifications (ordinary default 4.5s). Backup/import/restore supply longer specialized feedback. Standardizing presentation should keep committed-vs-rejected and retry semantics intact.

## Capability and security boundaries

[The API's `_required_capability`](../../src/sentriface/api_server.py) is the enforcement oracle; hidden/disabled controls are presentation only.

| Capability | Current operational meaning |
| --- | --- |
| `view` | Common authenticated reads, People/Events/World and status; all five roles. |
| `recognize` | Upload and recognition proposal processing; all five roles. Does not authorize review finalization. |
| `add` | Person create/edit/preferences/notes, manual association create/retire, Reference operations, review/Queue mutations and Attach. Operator, Custodian, Administrator. |
| `destroy` | Archive/restore/merge/tombstone, face move/delete/restore/purge and finalized Encounter corrections. Custodian, Administrator. |
| `backups` / `backup_delete` | Create/list/export versus deletion. Custodian has both; Technician has creation/export; Administrator has both. |
| `database_restore` | Encrypted import and restore; Administrator only. A visible Backups section does not imply restore authority. |
| `technical` | Activity logs, machine diagnostics and support package; Technician, Administrator. |
| `administer` | Account management and model writes; Administrator. |
| `recovery` | Recovery configuration/acknowledgment and integrity preparation/execution; Administrator. |
| `license_administer` | License activation; Administrator. Status/read recovery availability is separate. |

Preserve loopback-only access, session/header checks, offline socket guard and platform policy, encrypted database/media, local admitted-model responsibility, and OS credential custody. A macOS source run cannot qualify Windows enforced licensing/firewall or packaged signing. Public screenshots must not reveal real identities/photos, secrets, vault locations, raw database/log content or private model declarations.

## Authority consequences to keep visible

| Operator decision | Durable consequence / what must remain distinct |
| --- | --- |
| Accept existing/create new during review | Draft choice first; explicit Complete Review atomically saves finalized Encounter, participant assignments, media, notes, permitted evidence, graph projection and operation journal. |
| Defer vs discard | Defer remains unresolved and returns; final negative decision excludes participation. Both differ from cancelling the entire draft. |
| Reference Only confirm/retire/restore | Source assignment/quality/lifecycle changes within the existing cap; no Encounter, sighting, recurrence, relationship or Event history. Sample conflict eligibility is derived. |
| Selected Person/Sighting note mention | Saved selected ID creates directed note evidence; literal `@Name` alone is inert. Event selected mention is Encounter→Person provenance and does not create attendance or Person relationship evidence. |
| Relations INCLUDE/EXCLUDE | Attendance stays separate; only included effective canonical pair supports CO_OBSERVED. Independent manual/note evidence survives exclusion. |
| Attach Media | Same Encounter ID and occurrence; new media/provenance and explicit new-pair decisions as needed. Does not increase recurrence just because another photo was uploaded. |
| Archive/delete/merge | Lifecycle or canonical resolution changes; raw IDs/history/evidence are retained. Active selection/recognition and historical profile access have different eligibility. |
| Correction | Append new interpretation/history with expected revision; preserve original face/media/source ownership. Correction is not destructive rewriting of original truth. |
| Restore/rebuild | Restore replaces current authority only through verified closure/safety backup/rollback; graph rebuild changes derived projection only. Neither is a general permission to infer missing authority. |

## Candidate #4 entry points, not Split/Merge policy

Current #4 Encounter Split/Merge is **not implemented**. The following are existing surfaces to evaluate during the separately approved domain-policy/Figcraft phase:

1. **Global Event detail:** alongside existing Attach and metadata/participant/Relations correction, where operator intent and the current revision are already available. Reuse Event identity/metadata/participant/media/history presentation and stale handling. This is a placement candidate, not authorization to expose a new command.
2. **People → Events → shared Event detail:** converge on the same approved command surface rather than creating a Person-specific editor with different rules.
3. **World proof/source Event drilldown:** retain read-only proof; a future approved transition may lead to the same global detail, preserving originating proof context and current permissions. Do not mutate graph geometry to split/merge occurrences.
4. **Review Photos grouping:** reuse partition-preview vocabulary and media selection patterns as interaction research. Current grouping concerns **unfinalized imported media**; it is not evidence that finalized Encounter Split/Merge can reuse the same mutation semantics.
5. **Conflict recovery:** existing Open conflicting Encounter after a Person merge is a model for a specific, explained correction route and retry. It does not authorize automatic relation changes or Encounter merging.

Before any future commands, #4 must separately decide metadata, media, participants/Relations, selected mentions, recurrence, original lineage, canonical/lifecycle state, permissions, concurrency, operation ID/restart/rebuild and backup/restore consequences. This audit defines none of those policies.

## Engineering tradeoffs for the next phase

Keep large view files as current owners during design review; file size alone is not a runtime defect or reason for a rewrite. Common dialog labels/focus/error anatomy and shared task language can be refined in existing components with relatively low domain impact. Splitting components later may help maintenance, but only after the approved interaction remains traceable to the source inventory and tests. A clean-looking canvas or profile that hides history, exclusions, pending work, capability limits or recovery would be a regression even if it uses fewer controls.
