# Issue #6 runtime audit — 2026-11-26 pass 1

This directory preserves the complete safe evidence set for the runtime audit pass requested on 2026-11-26. It is additive evidence only; it does not supersede or alter earlier audit passes in `audit-results/issue-6/`.

## Audited product and environment

- Product SHA: `613b352f0d68580356345aea8401ab52dfaf9797` on `v2-hardening-followups`.
- Evidence branch at preparation time: `41165390ea4129eff58d737488c3ded31a1560cb` before this commit.
- Runtime: SentriFace source mode on loopback `http://127.0.0.1:8765`, Linux/Ubuntu VM, Chromium browser automation.
- Recognition mode: development/demo recognition with synthetic images; this does not prove genuine ONNX recognition quality.
- Data: disposable isolated data directory, synthetic/fictional people and generated face-like images.
- Roles exercised through real UI sign-in: Viewer, Operator, Custodian, Technician and Administrator/owner. Role coverage is sampled/partial, not an exhaustive permission matrix.
- Product source was not modified. No fixes were implemented.

## Canonical reports

- [Complete audit report](audit-report.md) — findings, reproduction context, reconciliation and production-readiness verdict.
- [Coverage matrix](coverage-matrix.md) — tested/passed/partial/untested coverage table.
- [SHA-256 evidence manifest](manifest.sha256) — integrity hashes for files in this pass.

## Safety and exclusions

Uploaded screenshots use synthetic/fictional audit data. Credential entry appears only in masked browser fields. Automation scripts under `supporting/automation/` are sanitized copies with disposable passwords replaced by `<REDACTED_TEST_PASSWORD>`. The live session-token file, encrypted database/backups, face/media store and any credential-bearing runtime data were intentionally not uploaded.

## Workflow evidence map

| Workflow / state family | Screenshot directory | Status |
|---|---|---|
| Bootstrap, first owner and safety-copy acknowledgment | [00-setup](screenshots/00-setup) | Verified |
| Empty shell, navigation and initial screen states | [01-people through 07-shell](screenshots/01-people) | Verified/partial initial crawl |
| Manual no-photo person creation | [10-people](screenshots/10-people) | Verified |
| Archive lifecycle confirmation and backup-first behavior | [11-lifecycle](screenshots/11-lifecycle) | Verified |
| Populated People, profile and notes | [20-owner-populated, 21-owner-bilal](screenshots/20-owner-populated) | Verified |
| Person Graph keyboard edge evidence | [22-owner-graph](screenshots/22-owner-graph) | Verified |
| Event detail and correction dialogs | [23-owner-events](screenshots/23-owner-events) | Partial |
| Destructive review confirmations | [31-queue-review](screenshots/31-queue-review) | Verified for Event/session/group discard |
| Fixture-limited Attach attempt | [32-queue-complete](screenshots/32-queue-complete) | Fixture-limited, not a product defect |
| Valid Attach Media target context and completion | [33-attach-real](screenshots/33-attach-real) | Verified |
| Five-role login and permission communication samples | [40-roles, auth](screenshots/40-roles) | Partial |
| Populated World Explore and Connections | [40-world](screenshots/40-world) | Partial |
| Complete Check a photo journey | [50-check-photo](screenshots/50-check-photo) | Verified |
| Backup creation and backup listing | [50-settings](screenshots/50-settings) | Verified |
| Empty-note mention retirement | [60-notes](screenshots/60-notes) | Verified |
| Stale correction recovery | [70-stale](screenshots/70-stale) | Verified |
| Restart/reload persistence | [80-restart](screenshots/80-restart) | Verified |
| Light/dark theme comparison | [90-theme](screenshots/90-theme) | Partial |

## Prioritized findings in this pass

1. Medium — review person-selection discoverability gap: disabled `Choose a person to accept` does not explain that Browse People is required; biometric-only filtering can hide no-photo people. See [finding details](audit-report.md#medium-priority) and evidence in `screenshots/33-attach-real/` / `screenshots/32-queue-complete/`.
2. Medium — backup warning is not role-actionable for Viewer/non-owner roles. See [role evidence](screenshots/40-roles/).
3. Low — exact typed country is not accepted until the dropdown option is selected. See `screenshots/10-people/`.
4. Low — graph edge keyboard focus is operable but visually subtle. See `screenshots/22-owner-graph/`.
5. Low — successful Attach Media completion is transient while the UI switches to another active session. See `screenshots/33-attach-real/`.

## Verified reconciliations

- F02 graph keyboard access, F05 long-note reading, F07 Attach target context, F08 stale correction recovery, F14/F16/F38 destructive confirmations, F20 note-mention retirement and sampled F21 permission explanations were verified at runtime.
- F15 was not retested at this exact SHA; F29 remains partially concerning; F40 appears in a new review-picker form; F26 was not reproduced; #60 remains intentionally unchanged.

## Coverage gaps and honesty boundary

This pass does **not** claim comprehensive Issue #6 acceptance coverage. Explicit gaps include delete/restore/merge, face/reference lifecycle, exhaustive role-denied click matrices, import/restore/wrong-passphrase/interrupted recovery, participant/relation correction mutations, F15 exact switching behavior, individual selected-face discard, multi-window behavior, systematic accessibility/screen-reader/contrast coverage, and genuine ONNX production recognition. See the [coverage matrix](coverage-matrix.md) and [audit report](audit-report.md#7-explicit-untested-or-incomplete-gaps).

## Supporting artifacts

- [supporting/crawl-coverage.json](supporting/crawl-coverage.json)
- [supporting/probe-add.log](supporting/probe-add.log)
- [supporting/probe-add2.log](supporting/probe-add2.log)
- [supporting/probe-correct.log](supporting/probe-correct.log)
- [supporting/probe-notes.log](supporting/probe-notes.log)
- [supporting/queue-button-states.json](supporting/queue-button-states.json)
- [supporting/role-administrator-summary.json](supporting/role-administrator-summary.json)
- [supporting/role-custodian-summary.json](supporting/role-custodian-summary.json)
- [supporting/role-matrix.json](supporting/role-matrix.json)
- [supporting/role-operator-summary.json](supporting/role-operator-summary.json)
- [supporting/role-technician-summary.json](supporting/role-technician-summary.json)
- [supporting/role-viewer-summary.json](supporting/role-viewer-summary.json)
- [supporting/seed-api.log](supporting/seed-api.log)
- [supporting/seed-direct.log](supporting/seed-direct.log)
- [supporting/seed-encounters.json](supporting/seed-encounters.json)
- [supporting/server-restart.log](supporting/server-restart.log)
- [supporting/server.log](supporting/server.log)
- [supporting/ui-add-no-photo-retry.log](supporting/ui-add-no-photo-retry.log)
- [supporting/ui-add-no-photo.log](supporting/ui-add-no-photo.log)
- [supporting/ui-archive.log](supporting/ui-archive.log)
- [supporting/ui-attach-real-finish1.log](supporting/ui-attach-real-finish1.log)
- [supporting/ui-attach-real-finish2.log](supporting/ui-attach-real-finish2.log)
- [supporting/ui-attach-real-finish3.log](supporting/ui-attach-real-finish3.log)
- [supporting/ui-attach-real.log](supporting/ui-attach-real.log)
- [supporting/ui-attach-real2.log](supporting/ui-attach-real2.log)
- [supporting/ui-attach-real3.log](supporting/ui-attach-real3.log)
- [supporting/ui-attach.log](supporting/ui-attach.log)
- [supporting/ui-audit-log.json](supporting/ui-audit-log.json)
- [supporting/ui-backup-create.log](supporting/ui-backup-create.log)
- [supporting/ui-backup-create2.log](supporting/ui-backup-create2.log)
- [supporting/ui-check-complete.log](supporting/ui-check-complete.log)
- [supporting/ui-check-finish.log](supporting/ui-check-finish.log)
- [supporting/ui-check-photo.log](supporting/ui-check-photo.log)
- [supporting/ui-notes-empty.log](supporting/ui-notes-empty.log)
- [supporting/ui-owner-core.log](supporting/ui-owner-core.log)
- [supporting/ui-owner.log](supporting/ui-owner.log)
- [supporting/ui-queue-complete.log](supporting/ui-queue-complete.log)
- [supporting/ui-queue-complete2.log](supporting/ui-queue-complete2.log)
- [supporting/ui-queue-complete2b.log](supporting/ui-queue-complete2b.log)
- [supporting/ui-queue-complete2c.log](supporting/ui-queue-complete2c.log)
- [supporting/ui-queue-complete3.log](supporting/ui-queue-complete3.log)
- [supporting/ui-queue-complete4.log](supporting/ui-queue-complete4.log)
- [supporting/ui-queue-complete5.log](supporting/ui-queue-complete5.log)
- [supporting/ui-queue-destructive.log](supporting/ui-queue-destructive.log)
- [supporting/ui-queue-finish.log](supporting/ui-queue-finish.log)
- [supporting/ui-restart.log](supporting/ui-restart.log)
- [supporting/ui-roles.log](supporting/ui-roles.log)
- [supporting/ui-settings-backup.log](supporting/ui-settings-backup.log)
- [supporting/ui-stale.log](supporting/ui-stale.log)
- [supporting/ui-stale2.log](supporting/ui-stale2.log)
- [supporting/ui-tech-backup.log](supporting/ui-tech-backup.log)
- [supporting/ui-tech-backup2.log](supporting/ui-tech-backup2.log)
- [supporting/ui-theme.log](supporting/ui-theme.log)
- [supporting/ui-theme2.log](supporting/ui-theme2.log)
- [supporting/ui-world.log](supporting/ui-world.log)
- [supporting/ui-world2.log](supporting/ui-world2.log)
- [Sanitized automation scripts](supporting/automation/) — reproducibility helpers with credentials redacted.

## Screenshot index

### `00-setup` (4 screenshots)
- [after-onboarding.png](screenshots/00-setup/after-onboarding.png)
- [owner-create.png](screenshots/00-setup/owner-create.png)
- [post-signin.png](screenshots/00-setup/post-signin.png)
- [skip-safety-acknowledged.png](screenshots/00-setup/skip-safety-acknowledged.png)

### `01-people` (6 screenshots)
- [add-person-dialog-empty.png](screenshots/01-people/add-person-dialog-empty.png)
- [add-person-dialog.png](screenshots/01-people/add-person-dialog.png)
- [filter-popover.png](screenshots/01-people/filter-popover.png)
- [group-menu.png](screenshots/01-people/group-menu.png)
- [home.png](screenshots/01-people/home.png)
- [sort-menu.png](screenshots/01-people/sort-menu.png)

### `02-check-photo` (2 screenshots)
- [home.png](screenshots/02-check-photo/home.png)
- [initial.png](screenshots/02-check-photo/initial.png)

### `03-review` (2 screenshots)
- [home.png](screenshots/03-review/home.png)
- [initial.png](screenshots/03-review/initial.png)

### `04-events` (2 screenshots)
- [home.png](screenshots/04-events/home.png)
- [initial.png](screenshots/04-events/initial.png)

### `05-world` (4 screenshots)
- [connections.png](screenshots/05-world/connections.png)
- [explore-toggle.png](screenshots/05-world/explore-toggle.png)
- [explore.png](screenshots/05-world/explore.png)
- [home.png](screenshots/05-world/home.png)

### `06-settings` (8 screenshots)
- [check-a-photo.png](screenshots/06-settings/check-a-photo.png)
- [events.png](screenshots/06-settings/events.png)
- [home.png](screenshots/06-settings/home.png)
- [initial.png](screenshots/06-settings/initial.png)
- [people.png](screenshots/06-settings/people.png)
- [review-photos.png](screenshots/06-settings/review-photos.png)
- [settings.png](screenshots/06-settings/settings.png)
- [world.png](screenshots/06-settings/world.png)

### `07-shell` (2 screenshots)
- [account-menu.png](screenshots/07-shell/account-menu.png)
- [dark-mode.png](screenshots/07-shell/dark-mode.png)

### `10-owner-people` (2 screenshots)
- [bilal-tab-events.png](screenshots/10-owner-people/bilal-tab-events.png)
- [bilal-tab-photos.png](screenshots/10-owner-people/bilal-tab-photos.png)

### `10-people` (5 screenshots)
- [add-person-modal-current.png](screenshots/10-people/add-person-modal-current.png)
- [add-without-photo-filled.png](screenshots/10-people/add-without-photo-filled.png)
- [after-create-without-photo-retry.png](screenshots/10-people/after-create-without-photo-retry.png)
- [after-create-without-photo.png](screenshots/10-people/after-create-without-photo.png)
- [country-dropdown-india.png](screenshots/10-people/country-dropdown-india.png)

### `11-lifecycle` (3 screenshots)
- [after-archive.png](screenshots/11-lifecycle/after-archive.png)
- [archive-confirmation.png](screenshots/11-lifecycle/archive-confirmation.png)
- [manual-person-profile.png](screenshots/11-lifecycle/manual-person-profile.png)

### `11-owner-events` (3 screenshots)
- [attach-media-dialog.png](screenshots/11-owner-events/attach-media-dialog.png)
- [correct-participants-dialog.png](screenshots/11-owner-events/correct-participants-dialog.png)
- [morning-detail.png](screenshots/11-owner-events/morning-detail.png)

### `15-owner-settings` (1 screenshots)
- [home.png](screenshots/15-owner-settings/home.png)

### `20-owner-populated` (6 screenshots)
- [check-home.png](screenshots/20-owner-populated/check-home.png)
- [events-list.png](screenshots/20-owner-populated/events-list.png)
- [people-list.png](screenshots/20-owner-populated/people-list.png)
- [review-home.png](screenshots/20-owner-populated/review-home.png)
- [settings-home.png](screenshots/20-owner-populated/settings-home.png)
- [world-explore.png](screenshots/20-owner-populated/world-explore.png)

### `21-owner-bilal` (7 screenshots)
- [edit-menu.png](screenshots/21-owner-bilal/edit-menu.png)
- [long-note-expanded.png](screenshots/21-owner-bilal/long-note-expanded.png)
- [notes-editor-mentions.png](screenshots/21-owner-bilal/notes-editor-mentions.png)
- [profile-overview.png](screenshots/21-owner-bilal/profile-overview.png)
- [tab-activity.png](screenshots/21-owner-bilal/tab-activity.png)
- [tab-associations.png](screenshots/21-owner-bilal/tab-associations.png)
- [tab-sightings.png](screenshots/21-owner-bilal/tab-sightings.png)

### `22-owner-graph` (3 screenshots)
- [bilal-graph.png](screenshots/22-owner-graph/bilal-graph.png)
- [edge-evidence-inspector.png](screenshots/22-owner-graph/edge-evidence-inspector.png)
- [edge-keyboard-focus.png](screenshots/22-owner-graph/edge-keyboard-focus.png)

### `23-owner-events` (6 screenshots)
- [attach-media-after-click.png](screenshots/23-owner-events/attach-media-after-click.png)
- [correct-event.png](screenshots/23-owner-events/correct-event.png)
- [correct-participants.png](screenshots/23-owner-events/correct-participants.png)
- [correct-relations.png](screenshots/23-owner-events/correct-relations.png)
- [list.png](screenshots/23-owner-events/list.png)
- [morning-detail.png](screenshots/23-owner-events/morning-detail.png)

### `30-attach-media` (3 screenshots)
- [after-review.png](screenshots/30-attach-media/after-review.png)
- [before-file-selection.png](screenshots/30-attach-media/before-file-selection.png)
- [progress-1.png](screenshots/30-attach-media/progress-1.png)

### `31-queue-review` (8 screenshots)
- [event-discard-cancelled.png](screenshots/31-queue-review/event-discard-cancelled.png)
- [event-discard-confirmation.png](screenshots/31-queue-review/event-discard-confirmation.png)
- [group-discard-cancelled.png](screenshots/31-queue-review/group-discard-cancelled.png)
- [group-discard-confirmation.png](screenshots/31-queue-review/group-discard-confirmation.png)
- [group-review-open.png](screenshots/31-queue-review/group-review-open.png)
- [pending-group-precondition.png](screenshots/31-queue-review/pending-group-precondition.png)
- [session-discard-cancelled.png](screenshots/31-queue-review/session-discard-cancelled.png)
- [session-discard-confirmation.png](screenshots/31-queue-review/session-discard-confirmation.png)

### `32-queue-complete` (12 screenshots)
- [after-confirm.png](screenshots/32-queue-complete/after-confirm.png)
- [count-options.png](screenshots/32-queue-complete/count-options.png)
- [event-completed.png](screenshots/32-queue-complete/event-completed.png)
- [followup-filled.png](screenshots/32-queue-complete/followup-filled.png)
- [followup-form.png](screenshots/32-queue-complete/followup-form.png)
- [person-picker-filter-open.png](screenshots/32-queue-complete/person-picker-filter-open.png)
- [person-picker-no-biometric.png](screenshots/32-queue-complete/person-picker-no-biometric.png)
- [person-picker.png](screenshots/32-queue-complete/person-picker.png)
- [person-selected-asha.png](screenshots/32-queue-complete/person-selected-asha.png)
- [ready-for-relations.png](screenshots/32-queue-complete/ready-for-relations.png)
- [relations-step.png](screenshots/32-queue-complete/relations-step.png)
- [review-start.png](screenshots/32-queue-complete/review-start.png)

### `33-attach-real` (8 screenshots)
- [after-complete-review.png](screenshots/33-attach-real/after-complete-review.png)
- [browse-people-picker.png](screenshots/33-attach-real/browse-people-picker.png)
- [event-detail-before.png](screenshots/33-attach-real/event-detail-before.png)
- [followup-details.png](screenshots/33-attach-real/followup-details.png)
- [group-review.png](screenshots/33-attach-real/group-review.png)
- [person-selected.png](screenshots/33-attach-real/person-selected.png)
- [relations-step.png](screenshots/33-attach-real/relations-step.png)
- [scan-review-target-context.png](screenshots/33-attach-real/scan-review-target-context.png)

### `40-roles` (33 screenshots)
- [administrator/bilal-long-note-expanded.png](screenshots/40-roles/administrator/bilal-long-note-expanded.png)
- [administrator/bilal-profile.png](screenshots/40-roles/administrator/bilal-profile.png)
- [administrator/event-detail.png](screenshots/40-roles/administrator/event-detail.png)
- [administrator/events-list.png](screenshots/40-roles/administrator/events-list.png)
- [administrator/landing.png](screenshots/40-roles/administrator/landing.png)
- [administrator/settings.png](screenshots/40-roles/administrator/settings.png)
- [administrator/world.png](screenshots/40-roles/administrator/world.png)
- [custodian/bilal-long-note-expanded.png](screenshots/40-roles/custodian/bilal-long-note-expanded.png)
- [custodian/bilal-profile.png](screenshots/40-roles/custodian/bilal-profile.png)
- [custodian/event-detail.png](screenshots/40-roles/custodian/event-detail.png)
- [custodian/events-list.png](screenshots/40-roles/custodian/events-list.png)
- [custodian/landing.png](screenshots/40-roles/custodian/landing.png)
- [custodian/settings.png](screenshots/40-roles/custodian/settings.png)
- [custodian/world.png](screenshots/40-roles/custodian/world.png)
- [operator/bilal-long-note-expanded.png](screenshots/40-roles/operator/bilal-long-note-expanded.png)
- [operator/bilal-profile.png](screenshots/40-roles/operator/bilal-profile.png)
- [operator/event-detail.png](screenshots/40-roles/operator/event-detail.png)
- [operator/events-list.png](screenshots/40-roles/operator/events-list.png)
- [operator/landing.png](screenshots/40-roles/operator/landing.png)
- [operator/world.png](screenshots/40-roles/operator/world.png)
- [technician/bilal-long-note-expanded.png](screenshots/40-roles/technician/bilal-long-note-expanded.png)
- [technician/bilal-profile.png](screenshots/40-roles/technician/bilal-profile.png)
- [technician/event-detail.png](screenshots/40-roles/technician/event-detail.png)
- [technician/events-list.png](screenshots/40-roles/technician/events-list.png)
- [technician/landing.png](screenshots/40-roles/technician/landing.png)
- [technician/settings.png](screenshots/40-roles/technician/settings.png)
- [technician/world.png](screenshots/40-roles/technician/world.png)
- [viewer/bilal-long-note-expanded.png](screenshots/40-roles/viewer/bilal-long-note-expanded.png)
- [viewer/bilal-profile.png](screenshots/40-roles/viewer/bilal-profile.png)
- [viewer/event-detail.png](screenshots/40-roles/viewer/event-detail.png)
- [viewer/events-list.png](screenshots/40-roles/viewer/events-list.png)
- [viewer/landing.png](screenshots/40-roles/viewer/landing.png)
- [viewer/world.png](screenshots/40-roles/viewer/world.png)

### `40-world` (2 screenshots)
- [populated-connections.png](screenshots/40-world/populated-connections.png)
- [populated-explore.png](screenshots/40-world/populated-explore.png)

### `50-check-photo` (8 screenshots)
- [event-details-confirmed.png](screenshots/50-check-photo/event-details-confirmed.png)
- [event-details-filled.png](screenshots/50-check-photo/event-details-filled.png)
- [initial-owner.png](screenshots/50-check-photo/initial-owner.png)
- [new-person-confirmed.png](screenshots/50-check-photo/new-person-confirmed.png)
- [new-person-filled.png](screenshots/50-check-photo/new-person-filled.png)
- [new-person-form.png](screenshots/50-check-photo/new-person-form.png)
- [result-1.png](screenshots/50-check-photo/result-1.png)
- [review-completed.png](screenshots/50-check-photo/review-completed.png)

### `50-settings` (4 screenshots)
- [after-create-backup.png](screenshots/50-settings/after-create-backup.png)
- [backup-now-flow.png](screenshots/50-settings/backup-now-flow.png)
- [backups-restore-section.png](screenshots/50-settings/backups-restore-section.png)
- [settings-home.png](screenshots/50-settings/settings-home.png)

### `60-notes` (4 screenshots)
- [after-empty-save.png](screenshots/60-notes/after-empty-save.png)
- [before-empty-selected-mention.png](screenshots/60-notes/before-empty-selected-mention.png)
- [editor-opened-probe.png](screenshots/60-notes/editor-opened-probe.png)
- [note-emptied-chip-still-selected.png](screenshots/60-notes/note-emptied-chip-still-selected.png)

### `70-stale` (5 screenshots)
- [after-reload-current-event.png](screenshots/70-stale/after-reload-current-event.png)
- [afternoon-detail.png](screenshots/70-stale/afternoon-detail.png)
- [correct-event-open.png](screenshots/70-stale/correct-event-open.png)
- [modal-before-external-change.png](screenshots/70-stale/modal-before-external-change.png)
- [stale-error-with-reload.png](screenshots/70-stale/stale-error-with-reload.png)

### `80-restart` (5 screenshots)
- [after-server-restart-reload.png](screenshots/80-restart/after-server-restart-reload.png)
- [events-persisted.png](screenshots/80-restart/events-persisted.png)
- [people-persisted.png](screenshots/80-restart/people-persisted.png)
- [post-restart-shell.png](screenshots/80-restart/post-restart-shell.png)
- [review-session-resumed.png](screenshots/80-restart/review-session-resumed.png)

### `90-theme` (4 screenshots)
- [account-menu-before.png](screenshots/90-theme/account-menu-before.png)
- [people-dark.png](screenshots/90-theme/people-dark.png)
- [people-light-restored.png](screenshots/90-theme/people-light-restored.png)
- [people-light.png](screenshots/90-theme/people-light.png)

### `auth` (11 screenshots)
- [account-menu-before-signout.png](screenshots/auth/account-menu-before-signout.png)
- [custodian1-login-filled.png](screenshots/auth/custodian1-login-filled.png)
- [custodian1-signed-in.png](screenshots/auth/custodian1-signed-in.png)
- [operator1-login-filled.png](screenshots/auth/operator1-login-filled.png)
- [operator1-signed-in.png](screenshots/auth/operator1-signed-in.png)
- [owner-login-filled.png](screenshots/auth/owner-login-filled.png)
- [owner-signed-in.png](screenshots/auth/owner-signed-in.png)
- [technician1-login-filled.png](screenshots/auth/technician1-login-filled.png)
- [technician1-signed-in.png](screenshots/auth/technician1-signed-in.png)
- [viewer1-login-filled.png](screenshots/auth/viewer1-login-filled.png)
- [viewer1-signed-in.png](screenshots/auth/viewer1-signed-in.png)

## Verification notes

- Directory is additive and timestamped; no earlier audit evidence was overwritten.
- PR #34 must remain draft and must never be merged.
