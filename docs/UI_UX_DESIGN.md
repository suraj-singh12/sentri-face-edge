# SentriFace Edge — Product Studio and UI/UX design authority

**Status:** Operating charter approved by operator on 2026-11-04. **Source inventory v0.1 only**; no individual screen redesign, interaction specification, Figcraft mockup, or UI implementation is approved by this document.
**Source baseline:** `release-v2.0.0-hardening` at `0c5d451424f56ca236f921c08e3e4d6e09236458`.
**Durable work:** [#6 UI/UX refinement](https://github.com/suraj-singh12/sentri-face-edge/issues/6), [#4 Encounter Split/Merge](https://github.com/suraj-singh12/sentri-face-edge/issues/4), then [#5 release acceptance](https://github.com/suraj-singh12/sentri-face-edge/issues/5).
**Complementary authority:** [FEATURES_BY_TAB.md](FEATURES_BY_TAB.md) owns implemented user features and permission boundaries; [DOMAIN_MODEL.md](DOMAIN_MODEL.md) owns identity/evidence semantics; [AGENTS.md](../AGENTS.md) owns contributor rules. This document is the **one canonical home for design process, accepted UI decisions, design coverage, and UI review evidence**, not a second issue tracker or source of domain truth.

## Product aim and design rules

Make SentriFace **calm, professional, attractive, legible, efficient, reachable, predictable and dependable**. Common tasks should be effortless, advanced controls accessible when relevant, and the learning curve small. A clean interface is not one that hides capabilities or historical evidence.

1. **Extend existing work.** Inspect real running screens and repository sources; reuse existing React/Mantine components, navigation, controllers, backend commands, state, design tokens and correction/graph/provenance machinery before proposing anything new. Prefer to refine or relocate over duplicate. New surfaces require a justified user task and no viable existing owner.
2. **Optimize workflows.** Make the primary action and next step clear, use concise task-language labels, useful defaults, strong information hierarchy, appropriate density, stable placement, immediate feedback, and progressive disclosure. Never trade away recoverability, permissions or evidence to make a screenshot look minimal.
3. **One coherent system.** Use consistent hierarchy, spacing, typography, control anatomy, states, focus behavior and navigation across People, Review, Recognition, Events, World, Settings and onboarding. Treat macOS and Windows with equal care; use platform conventions where relevant rather than copying Apple visuals blindly.
4. **Accessible by design.** Keyboard traversal, visible focus, screen-reader labels, contrast, zoom, reduced motion, resizable windows and realistic laptop dimensions are part of design—not late QA.
5. **Preserve trust.** Clearly distinguish suggestions from decisions, drafts from final authority, original history from corrected state, view-only controls from mutations, and reversible from destructive operations. The application is offline and security/authority boundaries stay unchanged unless separately approved.
6. **Make completeness inspectable.** Every entry point, command, nested state and failure mode gets an explicit preserve/refine/move/defer decision and a test or justified gap. No silent disappearance of features, permission-based paths or secondary recovery controls.
7. **Design first, implement only after approval.** #6 sets common UI language and inventories safe entry points for #4; #4 separately owns Split/Merge domain policy and implementation. Both are mandatory for v2.0.0 before #5.

**Reference principles:** Apple's [design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles/), [macOS guidance](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/), [menus](https://developer.apple.com/design/human-interface-guidelines/menus), and [layout](https://developer.apple.com/design/human-interface-guidelines/layout). Adapt familiarity, agency, purpose, simplicity, platform fit, craftsmanship and safe recovery—not visual imitation.

## Product Studio: roles and accountability

This is an **operating model of review disciplines, not a claim that actual Apple employees or continuously running independent agents exist**. A single assistant/Codex run may perform several documented perspectives; independence must be earned with separately stated evidence, counterexamples and failure tests, not eight fictional votes.

| Responsibility | Owns the review question | Required evidence |
| --- | --- | --- |
| **Operator / product owner (human)** | Are purpose, scope, priorities and final design right? | Explicit approval of each bounded screen/interaction design and its material tradeoffs |
| **Product and engineering lead (coordinator)** | Is there one coherent product, complete scope and a traceable decision? | User-journey inventory, conflict resolution, approved issue scope, issue/PR gates |
| **Product/interaction design** | Are tasks discoverable, flows clear, controls correctly placed? | Current-vs-proposed flow, navigation hierarchy, user task steps, exception paths |
| **Visual/interface design** | Are typography, density, contrast, rhythm and states coherent? | Screen variants, existing token/component reuse, visual comparisons |
| **Accessibility/usability** | Can every operator understand and reach it without a mouse or visual guesswork? | Keyboard/focus/label/contrast/zoom, realistic laptop and role-state cases |
| **Frontend/platform engineering** | Can existing components/state deliver it reliably across Windows/macOS? | Source-backed reuse map, responsiveness, rendering, persistence, performance |
| **Domain/data architect** | Does it respect canonical identity, Encounter, evidence, corrections, journaling and provenance? | Authority map, read/write separation, cross-feature effects, rebuild/restart risks |
| **Privacy/security engineering** | Are destructive actions, permissions, offline data and recovery safe? | Capabilities, threats, least privilege, confirmation and failure boundaries |
| **QA/red team** | What breaks under real users, long data, stale state, errors, conflicting operations or recovery? | Independent counterexamples, test matrix, actual-run screenshots/traces, regressions |

**Operating constraints:** The coordinator consolidates findings; the operator makes product decisions; Codex inspects/implements only an approved scope; QA challenges claims before acceptance. Roles do not independently alter GitHub, merge code or silently approve one another. For consequential domain and security changes, apply explicit adversarial review and record the evidence that could falsify the proposal. Prefer a small number of strong reviews over process theater.

## Decision and delivery gates

| Gate | Evidence/outcome | Stop condition |
| --- | --- | --- |
| **0 — Baseline** | Latest hardening SHA, canonical docs, existing screens/components/controller graph, relevant issue | Cannot identify current implementation or safe source authority |
| **1 — Complete inventory** | All routes, nested surfaces, actions, roles, states and cross-feature journeys mapped to source + real screenshot | Unmapped feature, permission path or consequential missing state |
| **2 — Multi-role design** | Coherent IA, Apple-inspired patterns, actual-screen-first editable Figcraft proposal, reuse map and #4 placement | An unreviewed policy, duplicative interface or unsafe consequence |
| **3 — Red team + decision** | Accessibility, domain, security, engineering and QA critique; disagreements and scope/alternatives resolved | Material risk unresolved; no operator approval |
| **4 — Operator approval** | Explicit signed-off design/interaction scope in #6 or #4; mark accepted decisions here | **No UI code before approval** |
| **5 — Implementation** | Issue branch from latest hardening, one coherent PR, tests, docs, self-review, no accidental scope creep | Diff deviates from approved design/authority |
| **6 — Actual application acceptance** | Source-run/macOS/Windows as relevant, laptop screenshots, role/state/journey checks, CI and risk matrix | Feature orphaned, evidence obscured, state/performance/accessibility regression |
| **7 — Merge/release** | Explicit operator permission for PR merge; #5 qualifies the final integrated release | No automatic merge, release, tag or `main` change |

Each issue stays the **only task/work-status authority**. This page contains reusable design rules, approved decisions, evidence links and coverage—not a duplicate backlog. Codex updates existing canonical docs only when a decision changes; version only conceptual changes.

## Source-mapped UI inventory v0.1 — #6

This first pass inspected tracked source and [FEATURES_BY_TAB.md](FEATURES_BY_TAB.md) at the source SHA above. **It does not certify runtime completeness or visual quality.** Labels below describe implemented code paths, not approved redesign. Every row remains **runtime/role/state audit pending**, and any `Candidate` treatment is only a question to review.

| ID | Existing surface / task | Source owner and known paths | Preserve/consider in #6 | Audit state |
| --- | --- | --- | --- | --- |
| UX-00 | Startup, account sign-in, model admission, backup-readiness gate, license restriction | `SentriFaceApp.jsx`, `AuthGate.jsx`, `ModelGate.jsx`, `RecoveryGate.jsx` | Preserve safety barriers, blocked/ready/error/retry and primary next action | Source mapped; runtime pending |
| UX-01 | Global shell/nav, theme, refresh, quick backup, account menu, change password, sign out, alerts | `SentriFaceApp.jsx`, `constants.js` | Refine hierarchy and responsive reachability; retain all permission-gated paths | Source mapped; runtime pending |
| UX-02 | **Check a photo**: input, face choice, quality, identity accept/new/browse, defer/discard, finish, gallery | `RecognizeView.jsx`, `RecognitionFollowupForm.jsx` | Preserve proposal-vs-confirmed authority, image/face correspondence and follow-up states | Source mapped; runtime pending |
| UX-03 | **Review photos**: image/folder sessions, progress, group selection, removed/finalized media, one/multiple Encounter plan | `QueueView.jsx`, queue controller | Simplify task progression without hiding consent, exclusions or resume | Source mapped; runtime pending |
| UX-04 | **Review photos** continued: Event form, per-face compare/resolve/defer, Relations include/exclude, complete/cancel, Attach retry/cancel | `QueueView.jsx`, `EncounterDetailsModal.jsx` | Preserve serial draft, independent decisions and atomic finalization | Source mapped; runtime pending |
| UX-05 | **People library**: all/favorites/with or no photos/archived/deleted faces, search/filter/group/sort, grid/list, pagination | `PeopleView.jsx` | Make browsing efficient with no missing collections or hidden permission paths | Source mapped; runtime pending |
| UX-06 | **People profile**: Overview, Photos, Sightings, Events, Associations, Activity, Person Graph | `PeopleView.jsx`, `PersonGraphView.jsx` | Preserve every sub-tab and cross-feature drilldown/return context | Source mapped; runtime pending |
| UX-07 | **People mutations**: create without photo, edit, Person Notes, favorites, reference-only enrollment/retire/restore, move/delete/restore faces | `PeopleView.jsx`, `RecognitionReferences.jsx` | Unify patterns and verify action/capability availability and originals | Source mapped; runtime pending |
| UX-08 | **People identity/lifecycle**: archive, restore, tombstone, canonical merge, conflict navigation, standing associations | `PeopleView.jsx`, `PersonGraphView.jsx` | Preserve confirmations, evidence lineage, historical read paths and recovery | Source mapped; runtime pending |
| UX-09 | **Events**: global search/filter/pagination, detail, participants/media/Notes/Relations/history, Attach Media | `EventsView.jsx`, `EncounterDetailsModal.jsx` | Preserve occurrence semantics, permission gate and return navigation | Source mapped; runtime pending |
| UX-10 | **Events correction**: metadata, participant reassignment/add/remove, Relations INCLUDE/EXCLUDE | `EncounterManagementModal.jsx`, `EventsView.jsx` | Reuse existing correction forms; coordinate safe #4 entry point, not new policy | Source mapped; runtime pending |
| UX-11 | **World > Explore**: Discover, Canvas, Inspector, evidence criteria, period, weaker links, clusters, proof/selection | `WorldWorkspace.jsx`, `WorldExploreView.jsx`, `WorldExploreCanvas.jsx` | Retain Explore default and focused canvas/inspector controls | Source mapped; runtime pending |
| UX-12 | **World > Connections**: original Current UI, Overview/Clusters/Relationships/Patterns, scopes/facets, nested Person/Event/Evidence and media views | `WorldWorkspace.jsx`, `WorldView.jsx`, `World*DrilldownView.jsx` | Keep full original functionality, separate UI/API default semantics | Source mapped; runtime pending |
| UX-13 | **Settings**: License & activation, Backups & restore, User accounts, Integrity & recovery, System details, Activity log, About & support | `DebugView.jsx`, settings panels | Keep every capability-gated secondary destination; no false “all” view | Source mapped; runtime pending |
| UX-14 | **Support dialogs/overlays**: backup confirmation, corrections, recognition/Reference, media preview, deletion, gallery, tooltip/popover | Shared components, `SentriFaceApp.jsx`, tab views and CSS | Audit overlay placement, focus trap/return, clipping, escapes, stacking | Source mapped; runtime pending |
| UX-15 | **Cross-feature transitions**: Person → Graph/Events, Event → Person, World → proof/Event/Person, Attach → Review, Settings → recovery | Shell/People/World/Queue controllers | Keep state, back path, permissions, unsaved edits and refresh/restart behavior | Source mapped; runtime pending |

**Top-level navigation verified in source:** `recognize`, `queue` (requires `add`), `people`, `encounters`, `world`, `debug` (permission or license-gated). `world` opens Explore, then offers **Explore | Connections**; internal World API `view=CURRENT` remains the omitted-view default, not the UI default. `debug` Settings contains separately gated sections. The profile's implemented sub-tabs and action authority are listed in [FEATURES_BY_TAB.md](FEATURES_BY_TAB.md). This map is a **coarse register**; it must be expanded into a complete command/state ledger against the running application before Gate 1 is passed.

## Required coverage ledger for each ID (Gate 1 still open)

For every control, submenu, dialog, panel and journey record: **UI ID → task → entry point/back path → existing code/component → required capability → source data/authority → normal/empty/loading/disabled/error/success/stale/recovery state → role/laptop/theme/keyboard case → current screenshot → design decision (preserve/refine/move/defer, with rationale) → proposed Figcraft frame → implementation test → actual acceptance evidence**.

Must enumerate and test at least:
- Role variations: viewer/operator/admin capabilities, unavailable commands, license restrictions, model-not-ready, safety-copy requirements, disconnected/offline state, archived/deleted Persons and pending drafts.
- Layout/input variations: representative 1280×800, 1366×768 and 1440×900 laptop viewport (plus narrower resizable), light/dark, long names/notes/lists, keyboard-only, focus return, dialogs/popovers, scroll and zoom. Treat actual host/window size separately from CSS viewport size.
- Task variations: create/accept/cancel, repeat or retry, stale revision, conflict, restart/refresh, pending operation, destructive confirmation, source evidence, undo/repair when supported. Never promise undo where domain history does not support it.
- Cross-feature proof: identity corrections affect effective reads/World/Events/Person Graph without rewriting source history; Reference Only never creates an occurrence; Event note mentions do not imply presence; Attach does not invent a new Encounter.
- Live screenshot proof: default/selected/empty/dense/overlay states. Both Windows and macOS; note any unavailable environment or genuine data. Do not use a mock screenshot as acceptance evidence.

**Source findings, not approved design changes:** `PeopleView.jsx` is a large surface with multiple profile modes; `QueueView.jsx` contains nested multi-step review; `WorldView.jsx` has advanced filters in a popover; `WorldExploreView.jsx` has Discover/Canvas/Inspector and supporting proof; `DebugView.jsx` gates sections by capabilities; `sentriface-interface.css` includes multiple responsive breakpoints. These warrant review for information density, overlap, focus and consistency; source alone does **not** prove defects.

### Open verification gaps (must not be marked complete)

1. No fresh in-session runtime screenshot traversal of every UX-00…UX-15 state on Windows/macOS is evidenced by this design audit. The previous World screenshots cover only that narrow view.
2. Deep-link behavior for World was not independently tested in #31 and is not inferred here.
3. Accessibility keyboard/screen reader/zoom and small/large desktop acceptance are not yet systematically audited across all controls.
4. Exact per-role control coverage and failure/recovery journey enumeration require running the app and reviewing executable acceptance evidence.
5. #4 split/merge UI and domain semantics are **not implemented**; current Event correction and Queue grouping are the reusable starting points. No design of new mutations is approved.

## Initial multidisciplinary review and next proposal

- **Interaction:** Start with a feature-and-role inventory, top frequent tasks and information hierarchy; prevent an overdecorated redesign. Candidate: fewer competing primary actions per step. Must show how every existing action remains discoverable.
- **Visual:** Evaluate component tokens, hierarchy, compact density, responsive views and overlay anatomy against current screenshots. Candidate: align surfaces; do not impose a wholesale Apple clone.
- **Accessibility:** Audit keyboard, focus, headings and reduced window sizes before accepting hover/overlay designs. State evidence is missing today.
- **Frontend/platform:** Preserve React/Mantine shell, shared controllers, state retention and macOS/Windows source-development behavior; avoid duplicated graph/filter authorities.
- **Domain/security:** Do not redesign evidence meaning, biometric consent, rollback, permission gates or Split/Merge policy by inference.
- **QA red team:** Challenge “minimal” proposals that strand recovery, history, permission states or advanced graph controls; check long data and failure transitions.

**Original next #6 deliverable:** current laptop screenshots and a complete expanded UX-00…UX-15 control/state ledger; priority-by-impact UX findings, an architecture/component reuse map, Figcraft-first coherent proposal, red-team results and operator decision points. The evidence checkpoint below advances this work but does not pass its completeness gate. For #4, subsequently present an independent domain correction policy and UI interaction approval using this design language. No automatic coding, PR merge or release follows from this charter.

## Current-experience evidence checkpoint — November 2026

The dedicated **audit/issue-6-current-experience** evidence branch extends the existing UX-00–UX-15 register at source `b457f0a723e845dd1a92a07a577072c85146c89a`. [Browse the visual INDEX](../audit-results/issue-6/INDEX.md), [coverage and exact gaps](../audit-results/issue-6/coverage.md), [prioritized findings](../audit-results/issue-6/findings.md), [architecture reuse](../audit-results/issue-6/reuse-map.md), and [independent multidisciplinary review](../audit-results/issue-6/review.md). This supersedes the initial runtime-pending status only for the specifically evidenced paths; the historical coarse register above is not a claim of current complete qualification.

**Gate 1 remains open.** All 60 source task contracts have some execution evidence, but no broad task qualifies every branch. The branch ledger records256PASS/71PARTIAL/170NOT RUN/11BLOCKED/1FAIL out of509 contracts. Public synthetic captures, private genuine ONNX evidence, media-free dense layout, native macOS geometry and CSS viewport samples are explicitly separated. Windows and packaged-license acceptance are not inherited from source-mode macOS evidence. No design or implementation is approved.

Reusable conclusions: preserve suggestions versus saved identity decisions, precision-aware occurrence facts, independent evidence provenance, Reference Only lifecycle/cap, targeted Attach ownership, stale-revision refusal, capability enforcement and encrypted restore protections. Prioritize unknown-time/date consistency and keyboard relationship evidence access; then decision-name clarity, feedback placement, full Note reading, unavailable-action explanation, Attach target context and recoverable error/loading patterns. Reuse existing React/Mantine tokens/components and controllers rather than introducing new domain or graph authorities. Explore | Connections remains the operator naming.

The later Figcraft phase should propose a bounded cross-feature interaction language and demonstrate that all existing secondary/recovery paths survive, using the evidence library as BEFORE comparison. Resolve or explicitly accept the important remaining audit gaps first. #4 candidate entry points are current Event correction/detail and Queue grouping/review; Split/Merge mutation semantics remain separately unapproved and unimplemented. Screenshot assets stay on the evidence branch and must never be merged into hardening/main. Future approved PRs may carry forward a clean textual conclusion only.
