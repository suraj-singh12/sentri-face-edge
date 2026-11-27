# Issue #6 runtime audit coverage matrix

Audited commit: `613b352f0d68580356345aea8401ab52dfaf9797` on detached worktree `/home/ubuntu/sfe-issue6-audit`. Runtime evidence only; fixture seeding is identified separately. Product source was not modified.

Legend: **Verified** = exercised through real UI with screenshot evidence; **Partial** = some runtime evidence but incomplete journey; **Fixture-limited** = backend-seeded fixture was unsuitable and must not be interpreted as product behavior; **Untested** = no reliable runtime evidence.

| Area / journey | Status | Runtime evidence | Notes |
|---|---|---|---|
| Owner bootstrap/sign-in/safety-copy acknowledgment | Verified | `00-setup/*.png` | Skip remained disabled until acknowledgment checked. |
| Main shell/navigation/empty states | Verified | `01-people/home.png`, `02-check-photo/initial.png`, `03-review/initial.png`, `04-events/initial.png`, `05-world/*.png` | Initial crawl only; populated coverage added later. |
| Populated People list/collections | Verified | `20-owner-populated/people-list.png`, `80-restart/people-persisted.png` | Multiple active people, enrolled/no-photo states, archived count after lifecycle test. |
| Add person without photo | Verified | `10-people/add-person-modal-current.png`, `10-people/add-without-photo-filled.png`, `10-people/after-create-without-photo-retry.png` | Creation succeeded after explicitly selecting dropdown country. Test fixture accidentally reversed rank/name; not a product defect. |
| Add/create person through Check a photo | Verified | `50-check-photo/new-person-form.png`, `50-check-photo/new-person-filled.png`, `50-check-photo/new-person-confirmed.png`, `50-check-photo/review-completed.png` | Complete photo-check journey ended with `Review completed`. |
| Check photo recognition/review completion | Verified | `50-check-photo/result-1.png`, `50-check-photo/event-details-filled.png`, `50-check-photo/review-completed.png` | Dev recognition runtime reported one face, no automatic match, human review. |
| Archive person lifecycle | Verified | `11-lifecycle/manual-person-profile.png`, `11-lifecycle/archive-confirmation.png`, `11-lifecycle/after-archive.png` | Confirmation explained hidden-from-recognition semantics; archive created safety backup first. Delete/restore/merge untested. |
| Notes editor mention chips | Verified | `21-owner-bilal/notes-editor-mentions.png`, `60-notes/before-empty-selected-mention.png` | Mention chip visible/removable. |
| Empty-note mention retirement (F20/PR85) | Verified fixed | `60-notes/note-emptied-chip-still-selected.png`, `60-notes/after-empty-save.png` | Emptying note with mention still selected retired note; Associations changed from 2 to 1 and `No notes added` appeared. |
| Long-note reading (F05/PR88) | Verified fixed | `21-owner-bilal/long-note-expanded.png`, `40-roles/*/bilal-long-note-expanded.png` | `Read full note` expanded for owner and roles captured. |
| Graph keyboard edge access (F02/PR88) | Verified fixed | `22-owner-graph/edge-keyboard-focus.png`, `22-owner-graph/edge-evidence-inspector.png` | Keyboard Enter on focused edge opened evidence inspector. Visual focus ring remains subtle. |
| Event details and correction dialogs | Partial | `23-owner-events/correct-event.png`, `correct-participants.png`, `correct-relations.png` | Dialogs opened and captured; participant/relation mutation not fully exercised. |
| Stale correction recovery (F08/PR87) | Verified fixed on valid completed-review Event | `70-stale/modal-before-external-change.png`, `70-stale/stale-error-with-reload.png`, `70-stale/after-reload-current-event.png` | Backend revision was externally advanced; stale save was blocked and inline `Reload current Event` worked. Error-context switching not retested. |
| Stale error lifecycle when changing correction action (F15) | Not retested at exact SHA | none | Previously demonstrated in integration demo; no controlled evidence in this exact-SHA run. |
| Attach Media target context (F07/PR88) | Verified fixed | `33-attach-real/scan-review-target-context.png`, `33-attach-real/group-review.png` | Target occasion/date/place remained prominent through scan/review/relations. |
| Attach Media completion to valid completed-review Event | Verified | `33-attach-real/browse-people-picker.png` through `33-attach-real/after-complete-review.png` | Manual weak-match selection, details, relations, completion; toast `Media attached to the existing Event`. |
| Attach Media completion to direct fixture Event | Fixture-limited | `32-queue-complete/event-completed.png` | Direct low-level fixture lacked completed review, producing `Event has no completed review`; not evidence of a product defect. |
| Destructive queue confirmations (F14/F16/F38/PR86) | Verified fixed for Discard Event/session/group | `31-queue-review/*confirmation.png`, `*cancelled.png` | Confirmation appeared and cancellation preserved state. Individual selected-face discard confirmation not separately retested. |
| Review person picker discoverability | Finding / partial | `32-queue-complete/person-picker-filter-open.png`, `32-queue-complete/person-picker-no-biometric.png`, `33-attach-real/group-review.png` | `Choose a person to accept` disabled until separate Browse People selection; default biometric-only filter can hide no-photo people. |
| Reload/restart persistence | Verified | `80-restart/*.png` | Server restarted, browser reloaded, owner signed in again; people/events and active scan session persisted. |
| Backup creation and backup listing | Verified | `50-settings/backup-now-flow.png`, `50-settings/after-create-backup.png`, `50-settings/backups-restore-section.png` | Portable backup created and listed as restorable/verified complete. Import/restore/wrong-passphrase untested. |
| World Explore populated state | Partial | `40-world/populated-explore.png` | People/clusters/evidence summaries visible; detailed drilldowns incomplete. |
| World Connections populated state | Partial | `40-world/populated-connections.png` | Counts/clusters/evidence summaries visible; detailed inspector drilldown incomplete. |
| Viewer role | Partial | `40-roles/viewer/*.png` | Login and key screens captured; read-only explanations visible on profile/Event. Restricted-click outcomes not exhaustively tested. |
| Operator role | Partial | `40-roles/operator/*.png` | Login/key screens captured; permitted mutations not exhaustively tested. |
| Custodian role | Partial | `40-roles/custodian/*.png` | Login/key screens captured; backup/settings permissions not exhaustively tested. |
| Technician role | Partial | `40-roles/technician/*.png` | Login/key screens captured; read-only explanations visible; restricted-click outcomes not exhaustively tested. |
| Administrator/owner role | Partial | `40-roles/administrator/*.png`, owner evidence above | Broad owner workflows tested, but user administration/settings danger zones not exhaustive. |
| Dark/light consistency | Partial | `90-theme/people-light.png`, `90-theme/people-dark.png`, `90-theme/people-light-restored.png` | Theme toggled and People screen captured in both; no systematic contrast audit. |
| Settings nested sections | Partial | `50-settings/settings-home.png`, `50-settings/backups-restore-section.png`, `15-owner-settings/home.png` | License/backups visited; users/integrity/system/activity/about not deeply exercised. |
| Notifications | Partial | visible in multiple screenshots | Success/error toasts captured opportunistically, not systematic lifecycle coverage. |
| Multi-window/session replacement | Untested | none | Not covered. |
