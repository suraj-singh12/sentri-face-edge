# Source oracle and journey contracts — Issue #6

Source: `b457f0a723e845dd1a92a07a577072c85146c89a` on `release-v2.0.0-hardening`. Source review resumed 2026-11-10. This extends the existing [UX-00–UX-15 register](../../docs/UI_UX_DESIGN.md), not its governance or domain authority. **This is an independent source oracle, not runtime evidence or completion certification.**

- [Per-definition inventory](source-inventory.csv): exact source path/line, owner function, element, label/expression, handler, explicit state props, capability context and authority consequence.
- [60 curated task contracts](source-journeys.csv): user goals and supported branches grouped by the current implementation.
- [509 branch/state contracts](source-branches.csv): one semicolon-delimited branch label from those tasks per row, with slots for runtime reconciliation.
- Runtime screenshots and actual journey records must independently confirm these contracts. An unexercised source branch stays **NOT RUN**, or is explicitly marked **BLOCKED** in the reconciled runtime ledger with a reason. Source existence never earns PASS.

## Counting rules and limits

The source-site inventory has **832 rows**, comprising **528 control-definition sites, 58 overlay-definition sites, 133 feedback/media sites, 101 container/composite sites and 12 cross-feature transitions** across 36 source files. Counts are definition sites, not distinct runtime controls or captured states. A shared component can render in several workflows; a mapped Button can render repeatedly; FileButton wraps a Button; a tooltip and its trigger are separate rows; a Modal title can vary. These are useful reconciliation targets but cannot be added to report a number of unique screens.

The **60 tasks** group implemented operator goals. The **509 branch/state contracts** are a bounded source-derived checklist, not all path permutations. One entry may represent an equivalence class (e.g. sort values), or a state (e.g. missing-media fallback); it is not automatically a separate journey. The denominator is fixed for this baseline and can be split when runtime reveals distinct behavior. Report task coverage and branch coverage separately; do not divide screenshots by either count.

The JSX scan retained interactive Mantine/native elements, explicit feedback/media, selected shared composites and clickable wrappers. It omitted layout-only wrappers, most static typography, CSS pseudo-elements, generated icon internals and inactive commented markup. Nearest named function attribution is lexical, not a compiler proof of runtime reachability. A child’s full visibility condition may be in its caller/controller and is **not inferred from a short source context**. Dynamic labels remain expressions. Some same-line definitions have `-instanceN` suffixes to keep IDs unique. Classifications are review aids; the exact handler/source is authoritative. No screenshot/runtime result is inferred from this lexical extraction.

Reproduce reconciliation by checking out the exact SHA, opening each `source` file/line from the CSV, inspecting the named function plus callers and state owner, then executing the corresponding task in the real UI under its capability. Compare menus' dynamic options, conditional markup and controller notifications with the runtime journey; record every uncovered definition/branch explicitly. The curated task list is independently readable without running a scanner or relying on historical screenshots.

## Capability oracle

The backend's [`ROLE_CAPABILITIES`](../../src/sentriface/auth.py#L32) and [`_required_capability`](../../src/sentriface/api_server.py#L252) are the authority. Roles can combine capabilities; single-role sampling does not qualify every arbitrary union.

| Role | Capability set |
| --- | --- |
| Viewer | `view`, `recognize` |
| Operator | Viewer + `add` |
| Custodian | Operator + `destroy`, `backups`, `backup_delete` |
| Technician | Viewer + `backups`, `technical` |
| Administrator | `view`, `recognize`, `add`, `destroy`, `backups`, `backup_delete`, `technical`, `administer`, `database_restore`, `recovery`, `license_administer` |

Important distinctions for role testing:

- All roles can recognize; only `add` can finalize review. Viewer/Technician recognition must not gain mutation authority.
- Reference prepare/confirm/cancel/**retire/restore** require `add`, not `destroy`; People additionally supplies `canEdit && ACTIVE` to the management modal. Read-only management can remain inspectable.
- Person lifecycle/merge, ordinary face move/delete/restore/purge and Encounter corrections use `destroy`. Deleted Faces reads also use `destroy`.
- Manual Association create/retire requires `add`. Independent evidence remains after one assertion retires.
- Technical Activity log `/api/events` is not domain Events; it requires `technical`. `/api/encounters` GET falls under `view`.
- Backup creation/export/list uses `backups`; deletion uses `backup_delete`; **import and restore** use `database_restore`. Custodian/Technician backup access does not imply restore access.
- Model POST activation/configuration uses `administer`. Integrity/recovery uses `recovery`. License activation uses `license_administer`; the section can render its status for other roles in the restricted recovery shell.
- A visible disabled/hidden action is only presentation. Denied API mutation and unchanged disposable authority must be checked independently when evaluating security.

## Source owners and implementation boundaries

| UX | Owner and current task contract | Distinct branches to reconcile | Authority to preserve |
| --- | --- | --- | --- |
| UX-00 | [AuthGate](../../frontend/src/components/AuthGate.jsx), [ModelGate](../../frontend/src/components/ModelGate.jsx), [RecoveryGate](../../frontend/src/components/RecoveryGate.jsx) | First owner setup, sign-in/error/sign-out, owner-only model admission, personal/research/business licence choices, staged candidate/token activation and cancellation, safety-copy setup/manual destination/risk acknowledgment/non-owner wait | Operational accounts/models/custody; no silent recognition decisions or domain repair |
| UX-01 | [Shell](../../frontend/src/SentriFaceApp.jsx), [controller](../../frontend/src/hooks/useSentriFaceController.js) | Six view identifiers, role-gated tabs, restricted license Settings shell, Day/Night, refresh, backup shortcut, account menu/password/sign-out, connection/research/demo/compatibility/safety notices | Persistent navigation/presentation; existing explicit commands |
| UX-02 | [RecognizeView](../../frontend/src/views/RecognizeView.jsx), [follow-up form](../../frontend/src/components/RecognitionFollowupForm.jsx), [controller](../../frontend/src/hooks/useRecognizeController.js) | Input/no-face/multi-face/quality selection, comparison, accept/new/Browse biometric or no-biometric, proof duplicate hint, deferred/discarded, one Event form, selected Sighting mentions, final completion, saved decision/retry/gallery | Suggestions are proposals; explicit saved decision and complete operation own identity/occurrence |
| UX-03 | [QueueView](../../frontend/src/views/QueueView.jsx), [queue controller](../../frontend/src/hooks/useQueueController.js) | File/folder/drop admission, invalid input feedback, progress/cancel, sessions, media remove/restore/finalized exclusion, one/multiple Encounter plan and subfolder suggestion, whole-session/group discard confirmations | Durable nonauthoritative staging; exact finalized media excluded; one occurrence cannot be manufactured again |
| UX-04 | Same Queue owner, [Event details](../../frontend/src/components/EncounterDetailsModal.jsx) | Event exact/approximate/unknown time, location suggestions, identity groups, Peek In crop, focused compare/zoom/sync, per-face quality, draft identity, defer/resume, every Relations pair, complete/summary, interrupted draft and targeted Attach retry/cancel | One active draft; finalization atomic; Attach retains bound Encounter before planning |
| UX-05 | [PeopleView](../../frontend/src/views/PeopleView.jsx), [people controller](../../frontend/src/hooks/usePeopleController.js) | All/Favorites/With Photos/No Photos/Archived/Deleted Faces; search; grouping; sorting; grid/list; page size/page controls; no-photo creation | Canonical/lifecycle reads; no-photo Person does not imply biometric or new occurrence |
| UX-06 | [PeopleGalleryView and profile tabs](../../frontend/src/views/PeopleView.jsx), [PersonGraphView](../../frontend/src/views/PersonGraphView.jsx) | Overview, Photos, Sightings, Events, Associations, Activity; profile photo; source labels; PRESENT/MENTIONED/BOTH; nested Event return; graph pan/zoom/fit/node/edge/restricted history | Existing intelligence/graph reads, effective presence distinct from selected mentions |
| UX-07 | Same People owner, [RecognitionReferences](../../frontend/src/views/RecognitionReferences.jsx) | Edit Person/Notes drawers, mention suggestions and no-photo mentioned identity creation, favorites; NO_FACE Add Face and ENROLLED management; acknowledgment, single-face admission, poor/proof quality, cap, duplicate no-op, draft resume, retire/restore/conflict | Reference source identity/lifecycle separate from sample; no Encounter/relationship/recurrence from Reference Only |
| UX-08 | Same People/controller owner | Archive/Restore/Delete, DELETE phrase, verified backup prerequisite, merge/survivor/conflicting Encounter, move/delete face, Deleted Faces restore/purge, manual association add/retire | Tombstone/history preserved; independent evidence; canonical merge not physical erasure |
| UX-09 | [EventsView](../../frontend/src/views/EventsView.jsx), app-data/controller | Search/date/location/context/participant/mentioned Person, bounded pages, detail/participants/Notes/Relations/media, expandable history, Attach | Finalized occurrence reads; same Encounter for Attach; mentions do not imply attendance |
| UX-10 | [EncounterManagementModal](../../frontend/src/components/EncounterManagementModal.jsx), shared Event form, Events owner | Correct metadata/selected mentions, participant REASSIGN/REMOVE/ADD, active target, new pair decisions, last-participant/incomplete/stale refusal, cancellation | Expected-revision append-only correction; original authority retained; graph/journal transaction |
| UX-11 | [WorldWorkspace](../../frontend/src/views/WorldWorkspace.jsx), [Explore](../../frontend/src/views/WorldExploreView.jsx), [canvas](../../frontend/src/views/WorldExploreCanvas.jsx), [explore hook](../../frontend/src/hooks/useWorldExplore.js), [relationship proof](../../frontend/src/views/WorldRelationshipProof.jsx) | Explore default; independent evidence popover and strength Apply/Reset; weaker-link toggle; Frequent/Multiple locations/Recently seen/Clusters; local 7/30/90 days; bounded Next pages; canvas inspector; compact panel selection; source/proof overlay/media | Backend authoritative clusters, evidence counts distinct from recurrence; no frontend graph truth |
| UX-12 | [WorldView](../../frontend/src/views/WorldView.jsx), [world controller](../../frontend/src/hooks/useWorldController.js), Cluster/Person/Event/Evidence drilldowns | Connections original CURRENT semantics, Overview/Clusters/Relationships/Patterns; time/location/missing-location/order/advanced facets; ranked selections; bounded nested collections; fresh revision reads; proof provenance/media; stale refresh/Back | Same graph; Event history is not a World node type; CURRENT API omitted-view default unchanged |
| UX-13 | [DebugView](../../frontend/src/views/DebugView.jsx), License/Accounts/Recovery/MachineProfile/About panels | Seven capability-gated destinations; backup create/export/import/restore/delete; accounts/roles/disable/password reset; integrity reports/supported plans/results; guarded merge-revert; log pause/clear/filter/export; support package | Existing operational commands and guarded P11/P12 authority only |
| UX-14 | [Shared](../../frontend/src/components/Shared.jsx), [media preview](../../frontend/src/components/WorldMediaPreview.jsx), [location](../../frontend/src/components/SavedLocationInput.jsx), [country](../../frontend/src/components/CountrySelect.jsx), [error boundary](../../frontend/src/components/AppErrorBoundary.jsx) | Gallery filters/sort/grid/list, missing-image fallback, modal/drawer/tooltip/popover state and keyboard focus, location threshold/cursors, country search, notification timing, render failure | Presentation delegates domain commands; originals/full-window screenshots remain baseline |
| UX-15 | Shell, People/World/Queue/Recognize/AppData controllers | Profile↔Graph, profile Event→global detail, conflict→Event correction, Attach→Review, completion→People, galleries→review, World semantic Back stack, safety notice→Settings, mutation invalidation, refresh/restart | Existing owner/controller navigation; no parallel identity/evidence state |

## Independent red-team source questions

These are **source-grounded test targets, not confirmed runtime defects**:

1. The Person profile says “Delete entire profile permanently?” while explaining tombstone/history retention. Verify actual operator understanding and resulting historical access; do not rewrite authority to match that label.
2. Note editing, no-photo creation, face-based recognition and Reference Only use different context and quality rules. Verify reusable forms do not imply an occurrence for contextless material.
3. Profile Events opens the global Events owner. Verify the Back action and filters preserve the context an operator expects; source wiring alone does not prove a return path to the originating profile.
4. Explore has bounded forward pages and compact panels. Verify selections and proof stay reachable at narrow sizes; do not invent a Previous control absent from source.
5. Exact transient toast text lives in controllers. Verify ordinary default 4.5-second timing using current runtime and record trigger/timing; source text is not a captured toast.
6. Archived/deleted/merged Person nodes must not become active via alternate graph or World navigation. Test `allowed_actions` and historical reads separately from mutation capabilities.
7. Shared model/reference samples, wrong identity assignment, four-source cap and contradictory Relations can refuse a merge. A successful simple merge does not qualify those exception paths.
8. A failed Attach plan retains its target. A screenshot of generic grouping cannot qualify targeted retry/cancel or restart ownership.
9. Recovery action tokens are exact, expiring and revalidated. A clean PASS report cannot qualify findings, refused recovery or committed-postcheck-failure presentation. Do not corrupt operator data to manufacture a screenshot.
10. Native macOS browser source runs cannot qualify Windows packaged license/firewall/installer, screen-reader behavior, VM scaling or genuine recognition merely by inspecting JSX.

## #4 boundary

Encounter Split/Merge is not implemented. Current reusable entry owners are global Event detail correction actions; Person Events and merge-conflict links into that same detail; Review Photos' pre-finalization grouping; Attach's existing target binding and recovery. Existing metadata/participant/Relations revisions, expected revision and operation ID, original media/provenance, journal, graph rebuild and safe restore form the reuse base. **None of these approves repartitioning finalized media/participants/notes/recurrence or defines new mutation semantics.**

## Reconciliation acceptance

A report may claim a covered task only after its required runtime steps and meaningful branches have ordered screenshots and evidence. A source-site row can be mapped to several runtime steps; a shared screenshot can cover equivalent sites only with an explanation. Report sampled equivalences (role/theme/viewport) and unsampled differences explicitly. No screenshot count proves 100% source, workflow, branch or accessibility coverage.

## Candidate reconciliation tool

Run `python3 audit-results/issue-6/tooling/reconcile.py` after capturing. The tool reads the ignored private capture metadata and accessibility snapshots. It writes [coverage.csv](coverage.csv), [evidence-candidates.csv](evidence-candidates.csv) and [coverage-summary.json](coverage-summary.json). It never publishes snapshots or their text. Public links use `screenshots/<UX-ID>/<filename>`; when a record declares a sanitized derivative, that derivative and its declared checksum are used explicitly.

Its denominator is **598 control/overlay/transition definition sites** (528 + 58 + 12). The other 234 source sites remain in the full source oracle and are excluded from this control-definition percentage. This is a source-definition reconciliation denominator, not unique rendered controls. Matching requires an exact accessible role and complete static name, the same UX area (except global/shared presentation), the exact source SHA and matching original/public-derivative PNG hashes. Dynamic names, unnamed composites and transitions require manual mapping. Repeated static labels are marked ambiguous. An accessibility-tree entry can be outside the screenshot viewport; even exact matches therefore stay **PARTIAL candidate evidence**, never PASS. Its candidate percentage must never be reported as completed workflow, branch or accessibility coverage.

Semantic workflow and source-branch coverage remain separately reviewed against ordered real journeys. This tool does not mutate `source-journeys.csv` or `source-branches.csv`. Their runtime fields were subsequently synchronized by manual semantic review to task-coverage.csv and branch-coverage.csv; the original source contract columns remain preserved. Values cannot be upgraded merely because a button appears. The summary records the capture count used, allowing a later run to identify whether it needs regeneration after additional evidence. The native IAB original is JPEG bytes named with its correct .jpg extension; the PNG-only candidate parser excludes it, explicitly, rather than inventing accessible text.

Mechanism validation: `python3 audit-results/issue-6/tooling/test_reconcile.py` runs seven temporary-fixture checks for exact matching, dynamic-label refusal, escaped names, private-only exclusion, sanitized-derivative preference and tamper detection, unsafe path/wrong-SHA refusal, excluded-container counting, no automatic PASS, and no raw-snapshot export. Temporary test bytes are explicitly not application screenshots or runtime evidence.
