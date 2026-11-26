# SentriFace Edge Issue #6 runtime UI/UX audit report

## 1. Scope, baseline and honesty boundary

- Repository: `suraj-singh12/sentri-face-edge`
- Required branch: `v2-hardening-followups`
- Exact audited commit: `613b352f0d68580356345aea8401ab52dfaf9797`
- Worktree: `/home/ubuntu/sfe-issue6-audit` (detached at the exact SHA)
- Runtime: `http://127.0.0.1:8765`
- Disposable data: `/home/ubuntu/issue6-runtime-audit/data`
- Artifact root: `/home/ubuntu/issue6-runtime-audit/`
- Product source was not modified, and no fixes were implemented.

This was an actual runtime audit. Screenshots were captured from the running UI while browser automation drove real user-facing controls. Backend services/API primitives were used only to seed disposable fixture data or create controlled stale state; audited operator behavior was exercised through the UI.

The audit is substantially broader than the first partial pass, but it is **still not comprehensive Issue #6 acceptance coverage**. It should be treated as a rigorous partial runtime audit with strong evidence for the workflows listed below, not as proof that every screen/action/role/state was exhaustively covered.

## 2. Dataset and fixture boundary

Representative runtime data included:

- multiple people: Asha Rao, Bilal Khan, Carla Mendes, Devika Iyer, Zedekiah Vale, Manual/Analyst fixture person, New Audit Person;
- one shared multi-person Event (`Morning Audit Briefing`);
- additional single-person Events (`Afternoon Audit`, `Check Photo Audit Event`);
- a long person note with an explicit mention;
- manual association fixture data;
- an archived person;
- a person with biometric/photo evidence created through the real Check a photo flow;
- pending/active scan-session state used for reload/restart persistence;
- Viewer, Operator, Custodian, Technician and Administrator/owner accounts.

Important fixture limitation: `Morning Audit Briefing` and `Afternoon Audit` were seeded through low-level backend fixture primitives after ordinary API-created person observations did not appear as finalized Events. Those direct fixture Events did not have a completed review record. Correction/completion attempts against them produced `Event has no completed review`. That outcome is a fixture artifact and is **not** treated as a product finding. Valid product-created/completed-review Events were used for stale-recovery and Attach Media completion verification.

## 3. Evidence inventory

174 screenshots are organized under:

`/home/ubuntu/issue6-runtime-audit/screenshots/`

Machine-readable/supporting files:

- coverage matrix: `/home/ubuntu/issue6-runtime-audit/coverage-matrix.md`
- UI audit event log: `/home/ubuntu/issue6-runtime-audit/ui-audit-log.json`
- role matrix: `/home/ubuntu/issue6-runtime-audit/role-matrix.json`
- server logs: `/home/ubuntu/issue6-runtime-audit/server.log`, `/home/ubuntu/issue6-runtime-audit/server-restart.log`

Key evidence groups:

| Workflow | Evidence directory |
|---|---|
| Bootstrap/onboarding | `screenshots/00-setup/` |
| Empty shell and initial crawl | `screenshots/01-people/` through `07-shell/` |
| Manual person creation | `screenshots/10-people/` |
| Archive lifecycle | `screenshots/11-lifecycle/` |
| Owner populated People/profile/notes | `screenshots/20-owner-populated/`, `21-owner-bilal/` |
| Person Graph keyboard evidence | `screenshots/22-owner-graph/` |
| Event detail/correction dialogs | `screenshots/23-owner-events/` |
| Destructive review confirmations | `screenshots/31-queue-review/` |
| Earlier fixture-limited attach attempt | `screenshots/32-queue-complete/` |
| Valid Attach Media completion | `screenshots/33-attach-real/` |
| Roles | `screenshots/40-roles/` |
| Populated World | `screenshots/40-world/` |
| Check a photo complete journey | `screenshots/50-check-photo/` |
| Settings/backups | `screenshots/50-settings/` |
| Empty-note retirement | `screenshots/60-notes/` |
| Stale correction recovery | `screenshots/70-stale/` |
| Restart/reload persistence | `screenshots/80-restart/` |
| Light/dark theme | `screenshots/90-theme/` |

## 4. Verified runtime behavior

### 4.1 Bootstrap and safety copy

Evidence: `00-setup/post-signin.png`, `00-setup/skip-safety-acknowledged.png`.

The safety-copy skip action remained disabled until the operator explicitly acknowledged the risk. This is strong, predictable safety UX.

### 4.2 Populated People and manual no-photo creation

Evidence: `10-people/add-person-modal-current.png`, `10-people/add-without-photo-filled.png`, `10-people/after-create-without-photo-retry.png`.

The no-photo creation form clearly explains that no biometric data is stored. Creation succeeded once the country was explicitly selected from the dropdown. One usability friction was observed: typing `India` and pressing Enter left `Country is required` until the dropdown option itself was selected. Evidence: `10-people/after-create-without-photo.png`, `10-people/country-dropdown-india.png`.

Note: the fixture person created in this test accidentally had rank/name reversed because the automation mapped the rank/name fields incorrectly. The resulting odd labels are test-data error, not a product defect.

### 4.3 Archive lifecycle

Evidence: `11-lifecycle/manual-person-profile.png`, `11-lifecycle/archive-confirmation.png`, `11-lifecycle/after-archive.png`.

Archive used a confirmation explaining that the person is hidden from recognition while everything is retained and can be restored. The success notice stated that a database backup was created first. This is clear destructive/lifecycle communication.

Restore/delete/merge were not completed.

### 4.4 Complete Check a photo journey

Evidence: `50-check-photo/result-1.png`, `50-check-photo/event-details-filled.png`, `50-check-photo/new-person-form.png`, `50-check-photo/new-person-filled.png`, `50-check-photo/review-completed.png`.

A synthetic image was uploaded through the real UI. Dev recognition reported one detected face, no automatic match, and human review. The operator completed Event details, created a new person, filled sighting details and finished with `Review completed`. This is the strongest complete entry-to-completion recognition workflow evidence in this audit.

### 4.5 Notes, mentions and empty-note retirement

Evidence: `21-owner-bilal/notes-editor-mentions.png`, `60-notes/before-empty-selected-mention.png`, `60-notes/note-emptied-chip-still-selected.png`, `60-notes/after-empty-save.png`.

Selected mentions appear as removable chips in the editor. Emptying Bilal’s note while the mention chip was still selected and saving caused the note to retire (`No notes added`) and Associations dropped from 2 to 1. This verifies the PR #85/F20 fixed behavior at runtime.

### 4.6 Long-note reading

Evidence: `21-owner-bilal/long-note-expanded.png`, `40-roles/viewer/bilal-long-note-expanded.png`, `40-roles/operator/bilal-long-note-expanded.png`, `40-roles/custodian/bilal-long-note-expanded.png`, `40-roles/technician/bilal-long-note-expanded.png`, `40-roles/administrator/bilal-long-note-expanded.png`.

`Read full note` expands long note content without requiring edit rights. This verifies the PR #88/F05 fixed behavior.

### 4.7 Person Graph keyboard access

Evidence: `22-owner-graph/bilal-graph.png`, `22-owner-graph/edge-keyboard-focus.png`, `22-owner-graph/edge-evidence-inspector.png`.

A graph edge could be reached by keyboard and activated with Enter, opening the evidence inspector. This verifies the PR #88/F02 fixed behavior. The visual focus indication on the SVG edge is subtle; operability is verified, but visibility of focus could be improved.

### 4.8 Attach Media target context and completion

Evidence: `33-attach-real/event-detail-before.png`, `33-attach-real/scan-review-target-context.png`, `33-attach-real/group-review.png`, `33-attach-real/browse-people-picker.png`, `33-attach-real/person-selected.png`, `33-attach-real/followup-details.png`, `33-attach-real/relations-step.png`, `33-attach-real/after-complete-review.png`.

Attach Media displayed the target context prominently throughout review:

`Attaching media to Check Photo Audit Event · 2026-11-26 · Audit Lab`

A weak/no-match face was manually assigned to New Audit Person through Browse People, sighting details were confirmed, Relations was reached, and completion produced `Media attached to the existing Event`. This verifies the PR #88/F07 fixed behavior and demonstrates a complete successful Attach Media workflow against a valid completed-review Event.

After completion, the UI moved to the next still-active scan session (`Morning Audit Briefing`). That transition is logical, but the successful completion feedback is transient and easy to miss while the target context changes.

### 4.9 Destructive review confirmations

Evidence: `31-queue-review/event-discard-confirmation.png`, `31-queue-review/event-discard-cancelled.png`, `31-queue-review/session-discard-confirmation.png`, `31-queue-review/session-discard-cancelled.png`, `31-queue-review/group-discard-confirmation.png`, `31-queue-review/group-discard-cancelled.png`.

Discard Event, Discard session and group Discard each opened confirmation rather than immediately destroying work. Cancel preserved the review state. This verifies the central PR #86/F14/F16/F38 fixed behavior for those three destructive scopes. Individual selected-face discard confirmation was not separately retested.

### 4.10 Stale Event correction recovery

Evidence: `70-stale/modal-before-external-change.png`, `70-stale/stale-error-with-reload.png`, `70-stale/after-reload-current-event.png`.

A valid completed-review Event (`Check Photo Audit Event`) was opened in Correct Event. The backend revision was then advanced outside the modal as a controlled fixture. Saving the stale modal produced:

`Event changed; reload it before correcting or attaching media`

with explanatory text and an inline `Reload current Event` action. Clicking it discarded the stale unsaved correction and reloaded the current Event. This verifies the PR #87/F08 fixed behavior.

Changing correction action/context after a stale error (F15) was not re-tested at this exact SHA.

### 4.11 Restart, reload and scan-session persistence

Evidence: `80-restart/after-server-restart-reload.png`, `80-restart/post-restart-shell.png`, `80-restart/people-persisted.png`, `80-restart/events-persisted.png`, `80-restart/review-session-resumed.png`.

The server process was restarted. Browser reload required sign-in again, after which people and events persisted. Events showed the Check Photo Event with two media items. The active scan session also persisted and resumed at the Relations step for `Morning Audit Briefing`. This is strong recovery/persistence evidence, though that particular direct-fixture Event cannot complete because it lacks a completed review record.

### 4.12 Backup creation

Evidence: `50-settings/backup-now-flow.png`, `50-settings/after-create-backup.png`, `50-settings/backups-restore-section.png`.

The backup confirmation explained what would be saved and verified. Creating it produced `Portable backup created`; Backups & restore listed it as verified, complete and restorable, alongside the automatic pre-archive safety copy. Import, restore, wrong-passphrase and destination failure journeys remain untested.

### 4.13 World populated projections

Evidence: `40-world/populated-explore.png`, `40-world/populated-connections.png`.

World displayed populated evidence-connected people, clusters, relationships, effective people/events and explanatory inspector empty states. Detailed node/cluster/relationship drilldowns were only partially exercised.

### 4.14 Roles and permission communication

Evidence: `40-roles/viewer/`, `40-roles/operator/`, `40-roles/custodian/`, `40-roles/technician/`, `40-roles/administrator/`, plus auth screenshots under `screenshots/auth/`.

All five roles were logged in through the UI and key screens were captured. Viewer and Technician profile/Event screens showed explicit read-only permission explanations, and Event correction controls were absent. Viewer navigation omitted Settings. Operator/Administrator had broader operational navigation.

Coverage is still partial: the role matrix used visible text heuristics and some fields are false positives because hidden or disabled control text can remain in the DOM. Restricted-click denied outcomes were not exhaustively tested for every role/action.

The backup warning still says “The owner can check it under Settings” for non-owner roles. For Viewer, Settings is absent from navigation, making the warning informative but not directly actionable by that user. This is a remaining communication/discoverability concern rather than a proven authorization failure.

### 4.15 Theme

Evidence: `90-theme/people-light.png`, `90-theme/people-dark.png`, `90-theme/people-light-restored.png`.

The theme toggle worked and the populated People screen remained coherent in light and dark modes. This is not a systematic contrast/accessibility audit.

## 5. Prioritized findings

### High priority

No new high-confidence high-severity product defect was proven in the completed valid workflows. The earlier `Event has no completed review` failure was reproduced only against direct low-level fixture Events and is therefore excluded as a product defect.

### Medium priority

1. **Review person selection has a discoverability gap.**  
   Evidence: `33-attach-real/group-review.png`, `33-attach-real/browse-people-picker.png`, `32-queue-complete/person-picker-filter-open.png`, `32-queue-complete/person-picker-no-biometric.png`.  
   In group review, `Choose a person to accept` is disabled until the operator uses the separate `Browse People` control and selects a person. The disabled primary action does not explain that Browse People is the required next step. Separately, the default biometric-only filter can hide existing no-photo people, requiring the operator to understand and switch the technical filter category.  
   Impact: operators can stall at the exact decision point the workflow is designed to complete.  
   Recommendation: make the primary disabled action explanatory, or have it open Browse People; make the empty picker state explicitly explain how to show no-photo people.

2. **Backup warning is not role-actionable for Viewer/non-owner roles.**  
   Evidence: `40-roles/viewer/landing.png`, role summaries.  
   Viewer sees owner-directed backup warning text but has no Settings navigation or backup action.  
   Impact: persistent alarm without a user-level remediation path.  
   Recommendation: role-aware copy such as “Ask an owner/administrator to check backups” or suppress action guidance when the user cannot act.

### Low priority

3. **Exact typed country is not accepted without dropdown selection.**  
   Evidence: `10-people/after-create-without-photo.png`, `10-people/country-dropdown-india.png`, `10-people/after-create-without-photo-retry.png`.  
   Typing `India` and pressing Enter left a required-field error; selecting the dropdown option succeeded.  
   Impact: minor form friction.  
   Recommendation: accept exact matches on Enter or make the need to choose the dropdown option clearer.

4. **Graph edge keyboard focus is operable but visually subtle.**  
   Evidence: `22-owner-graph/edge-keyboard-focus.png`, `22-owner-graph/edge-evidence-inspector.png`.  
   Impact: keyboard users may not easily see which edge is focused even though activation works.  
   Recommendation: strengthen focus ring/contrast for edge focus.

5. **Successful Attach Media completion is transient while context switches to another active session.**  
   Evidence: `33-attach-real/after-complete-review.png`.  
   Impact: the operator may be uncertain whether the prior target completed before being moved into the next session.  
   Recommendation: use a persistent completion summary or explicit “completed; continuing to next pending session” state.

## 6. Reconciliation with previous findings and merged PRs #85–#88

| Item | Exact-SHA runtime status | Evidence / caveat |
|---|---|---|
| F02 graph keyboard access | Fixed/verified | `22-owner-graph/edge-keyboard-focus.png`, `edge-evidence-inspector.png` |
| F05 long-note reading | Fixed/verified | `21-owner-bilal/long-note-expanded.png`; role equivalents |
| F07 Attach Media target context | Fixed/verified | `33-attach-real/scan-review-target-context.png` |
| F08 stale correction recovery | Fixed/verified | `70-stale/stale-error-with-reload.png`, `after-reload-current-event.png` |
| F14/F16/F38 destructive confirmations | Fixed/verified for Event/session/group discard | `31-queue-review/*confirmation.png`; individual face discard not retested |
| F15 stale error clears when changing correction action | Not retested | Previously verified in integration demo, but not independently re-exercised here |
| F20 note-mention retirement | Fixed/verified | `60-notes/after-empty-save.png` |
| F21 read-only permission explanation | Fixed/verified in sampled Viewer/Technician profile/Event states | `40-roles/viewer/bilal-profile.png`, `event-detail.png`, Technician equivalents |
| F29 backup warning role-awareness | Still concerning/partially reproduced | Viewer sees owner-directed backup warning but no Settings route |
| F40 disabled-without-reason controls | Partially reproduced in new form | Disabled `Choose a person to accept` lacks inline reason |
| F26 note-driven creation crash | Not reproduced in this audit | No crash/error boundary observed in note/person workflows exercised |
| #60 no-photo behavior | Intentionally unchanged / not a finding | Per instruction |

## 7. Explicit untested or incomplete gaps

- Exhaustive every-screen/every-dialog coverage: not achieved.
- Delete, restore, merge, face retirement/restoration, recognition-reference lifecycle.
- Participant and Relation correction mutations beyond opening dialogs.
- F15 exact error-clearing behavior when changing correction context.
- Individual selected-face destructive confirmation.
- Import/restore, wrong passphrase, invalid destination, interrupted backup/restore.
- Model onboarding/license enforcement beyond source-runtime license screen.
- User administration create/reset/disable/delete workflows through UI.
- Technician/Custodian/Operator permitted and denied action matrix in depth.
- Multi-window concurrent operator behavior and session replacement.
- Systematic keyboard-only full-app pass, focus order, screen reader semantics, contrast measurements, reduced motion and viewport/responsive audit.
- Notification lifecycle across all success/warning/error states.
- Genuine production face-model behavior; runtime used dev/demo recognition and synthetic images.

## 8. Production-readiness verdict

A full production-readiness verdict still cannot be responsibly issued. The exact-SHA runtime evidence now shows that the recently merged fixes work in important real workflows, complete Check photo and Attach Media journeys can succeed, destructive actions are guarded, stale recovery is available, data and scan sessions persist across restart, and backup creation produces a verified restorable artifact. However, critical lifecycle, recovery/import, role-denial, correction-mutation, accessibility and multi-window areas remain untested or partial. The appropriate verdict is: **promising runtime evidence, but not yet sufficient for comprehensive Issue #6 acceptance or production readiness.**

## 9. Recommended next audit pass

1. Test delete/restore/merge and face/reference lifecycles with real UI evidence.
2. Build a role-by-action matrix using actual click outcomes and backend-denied messages, not text presence.
3. Complete import/restore/wrong-passphrase/invalid destination and interrupted recovery.
4. Finish participant/relation correction mutations and F15 error-context switching.
5. Conduct a systematic keyboard/focus/accessibility pass across populated dense states.
6. Exercise multi-window/session conflict behavior and notification lifecycle.
