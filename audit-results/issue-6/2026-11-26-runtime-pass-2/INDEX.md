# Issue #6 runtime audit — 2026-11-26 pass 2 (independent fresh pass)

Additive evidence only. This pass is an independent fresh audit of the same product SHA as pass 1, with a different dataset, different entry paths and new findings (A-series). It does not supersede pass 1, the F01–F40 register or any earlier evidence in `audit-results/issue-6/`. **AUDIT EVIDENCE — PR #34 MUST REMAIN DRAFT, NEVER MERGED.**

## Audited product and environment

- Product SHA: [`613b352f0d68580356345aea8401ab52dfaf9797`](https://github.com/suraj-singh12/sentri-face-edge/commit/613b352f0d68580356345aea8401ab52dfaf9797) on `v2-hardening-followups` (verified latest HEAD at audit start).
- Runtime: SentriFace dev source mode on loopback `http://127.0.0.1:8765`, Ubuntu Linux VM (UTC timezone), Chromium via Playwright automation at 1440×900 and 760×900, light and dark themes.
- Recognition mode: development/demo (synthetic `WholeImageFaceDetector` + `HashFaceEmbedder`); byte-identical images STRONG MATCH, distinct images never match. Findings depending on recognition *quality* are flagged as dev-mode-amplified where relevant (A-22); workflow and interaction findings are mode-independent.
- Dataset: disposable isolated data directory; 5 finalized multi-person events with deliberate cross-event overlap, 15 committed people (including duplicates for merge testing, a favorite, an archived person), fictional names and synthetic generated face images.
- Roles exercised through real UI sign-in: Viewer, Operator, Custodian, Technician, Administrator/owner — including forced first-sign-in password change for each role account.
- Product source was not modified. No fixes were implemented. No production data touched.

## Operator decisions (authoritative disposition)

**[operator-decisions.md](operator-decisions.md)** — recorded 2026-11-26: A-11's World default minimum relationship strength 2 and A-09's default Event date are **intentional and must remain unchanged**; no fixes approved; all improvement-plan items pending explicit design approval; A-22 and the coverage gaps pending investigation. This register supersedes the report where they disagree.

## Canonical reports

- [Complete audit report](audit-report.md) — production-readiness assessment, A-01–A-24 findings with priorities/impact/recommendations, F-series reconciliation, bounded improvement plan.
- [Coverage matrix](coverage-matrix.md) — per-area × per-role coverage including honest untested items.
- [SHA-256 evidence manifest](manifest.sha256) — integrity hashes.

## Finding → evidence map

| Finding | Priority | Key evidence |
|---|---|---|
| A-11 World defaults hide strength-1 relationships (P1) | P1 | [world canvas: lone node, inspector claims 0 relationships](screenshots/06-world/w-03-canvas-person.png) · [explore defaults](screenshots/06-world/w-01-explore.png) · [evidence-type control](screenshots/06-world/w-04-evidence-options.png) · contrast [profile association exists](screenshots/04-people-profile/pa-09-associations.png) |
| A-01 Country autocomplete exact-match failure | P2 | [india → British Indian Ocean Territory first](screenshots/04-people-profile/d2-02-india-options.png) · [edit drawer pre-filled wrong country](screenshots/04-people-profile/pa-08-edit-form.png) |
| A-02 Mandatory unexplained count; weak validation (corrected — inline message exists) | P2 | review-queue resolution sequence [n-05](screenshots/03-review-queue/n-05-resolution.png) · [n-06 browse](screenshots/03-review-queue/n-06-browse.png) |
| A-04 Disabled unexplained primary action | P2 | [group resolution screen](screenshots/03-review-queue/n-05-resolution.png) |
| A-03 Redundant match messaging + clipped badge | P2 | [resolution screen](screenshots/03-review-queue/n-05-resolution.png) · [queue rows](screenshots/03-review-queue/n-00-review-initial.png) |
| A-12 Notes invisible affordance | P2 | [profile overview — notes card has no control](screenshots/04-people-profile/pa-04-profile-overview.png) |
| A-13 Green "Unknown" context chips | P3 | [events list](screenshots/05-events/ev-01-list.png) |
| A-14 Permanent banner stack | P2 | visible in nearly every capture, e.g. [events list](screenshots/05-events/ev-01-list.png); role-inappropriate variant as viewer: [viewer home](screenshots/09-roles/d6-01-viewer-home.png) |
| A-22 Picker excludes recognition-ineligible people | P2 | [browse picker](screenshots/03-review-queue/n-06-browse.png) · [picker modes](screenshots/03-review-queue/n-07-picker-mode-options.png) |
| A-05 Tag vs Tags collision | P3 | [edit drawer](screenshots/04-people-profile/pa-08-edit-form.png) |
| A-06 Photo "Added" shows event time | P3 | [photo details panel](screenshots/04-people-profile/pa-06-photos.png) |
| A-17/A-18 menu inconsistencies/duplicates | P3 | [card overflow menu](screenshots/08-mutations/m-06-merge-dialog.png) vs [profile More menu](screenshots/08-mutations/m-02-more-menu.png) |
| Destructive-action safety (strength) | — | [archive dialog](screenshots/08-mutations/m-03-archive-dialog.png) · [delete type-to-confirm](screenshots/08-mutations/j-03-delete-dialog.png) · [merge dialog](screenshots/08-mutations/j-04-merge-dialog.png) |
| Forced password change (strength, F39 fixed) | — | [operator forced change + reuse rejection](screenshots/09-roles/r-operator-0-forcedpw.png) |
| Dark theme quality (strength) | — | [dark profile](screenshots/10-themes-responsive/j-05-dark-theme.png) |
| Narrow layout (strength + A-24) | — | [760px home](screenshots/10-themes-responsive/j-06-narrow-home.png) · [760px people](screenshots/10-themes-responsive/j-07-narrow-people.png) |

Some referenced filenames may differ slightly where a capture was not repeated; every screenshot under [screenshots/](screenshots) is timestamped evidence from this pass. Where the table cites a screenshot whose exact content is described in the report rather than a dedicated close-up, the report's reproduction steps are authoritative.

## Workflow evidence map

| Workflow / state family | Directory | Status |
|---|---|---|
| First load, sign-in, password validation | [01-setup-signin](screenshots/01-setup-signin) | Verified |
| Check a photo recognition journey | [02-check-photo](screenshots/02-check-photo) | Verified incl. STRONG MATCH, empty states |
| Review photos full lifecycle (upload→group→details→identity→relations→finalize) | [03-review-queue](screenshots/03-review-queue) | Verified ×5 events; defects A-02/03/04/22 documented |
| People grid, profile tabs, edit drawer, photos panel, associations, activity | [04-people-profile](screenshots/04-people-profile) | Verified |
| Events list, filters, detail, relations provenance | [05-events](screenshots/05-events) | Verified read paths; correction execution not completed |
| World Explore canvas/inspector/filters | [06-world](screenshots/06-world) | Verified; A-11 root-caused |
| Settings all sections, backup creation | [07-settings](screenshots/07-settings) | Verified; backup created as custodian |
| Archive/restore/delete/merge dialogs and state transitions | [08-mutations](screenshots/08-mutations) | Dialogs verified; merge/bin execution incomplete (see gaps) |
| Role-based passes all four non-admin roles | [09-roles](screenshots/09-roles) | Verified gating; forced password change each |
| Dark theme, narrow viewport | [10-themes-responsive](screenshots/10-themes-responsive) | Verified |

## Outstanding coverage gaps (honest register)

Merge execution to completion; bin restore execution; event-correction execution; recognition-reference add/remove; backup import/restore; integrity/recovery execution; deep Connections drilldowns; systematic keyboard-only and screen-reader pass; long-string and dense-data stress; attach-media execution. Previous-audit revalidations not re-verified this pass are itemized in [audit-report.md §4](audit-report.md).

## Safety and exclusions

All captures use synthetic/fictional data; face images are generated noise/smileys. Password entry appears only in masked fields. Automation scripts under [supporting/automation](supporting/automation) are sanitized copies with all disposable passwords replaced by `<REDACTED_TEST_PASSWORD>`. Live session tokens, the encrypted database, backups and the media store were intentionally not uploaded.

## Subsequent evidence

**[videos/defect-demo.webm](videos/defect-demo.webm)** — operator-requested defect demonstration (4:50, 2026-11-26): World default-empty 0:15–1:09 · country autocomplete 1:10–1:38 · duplicate NO MATCH rows 1:54–2:03 · disabled primary action 2:26–2:37 · redundant/clipped messaging 2:37–2:59 · picker omissions (7 biometric entries for 15 people) 3:02–3:34 · count validation 3:37–4:13 · banners/viewer 4:16–4:44. [Timestamps](videos/defect-demo-timestamps.json). Recording surfaced two corrections, applied to the report: (1) A-02 — an inline count validation message DOES appear on first click; the defect is weak guidance/mandatory-data, not silence; (2) F40 — the viewer has no Settings tab at all, strengthening the role-inappropriate-banner finding. Design proposals arising from this audit must reference the A-series IDs and record operator approval status in [operator-decisions.md](operator-decisions.md) before implementation.
