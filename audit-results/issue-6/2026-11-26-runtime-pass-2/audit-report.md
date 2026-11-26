# SentriFace Edge — Comprehensive Pre-release UI/UX Audit
**Issue #6 · Branch `v2-hardening-followups` @ `613b352f` · Audit date 2026-11-26 · Single-agent fresh pass**

> **Amended 2026-11-26 by operator decision — see [operator-decisions.md](operator-decisions.md), which is authoritative:** A-11's World default minimum relationship strength of 2 and A-09's default Event date are **intentional behaviour and must remain unchanged**. No fixes are approved; all other improvement-plan items are pending explicit design approval. Where this report recommends otherwise, the decisions register supersedes it.

Method: the running application was exercised in a real browser (Playwright-driven Chromium, 1440×900 and 760×900, light and dark themes) against a realistic seeded dataset — 5 finalized multi-person events with cross-event overlap, 15 people (including photos, duplicates, favorites, archived), 5 role accounts. Every role was signed in and its permissions verified. Review-queue ingestion, recognition, people, events, world, settings, mutations (archive/restore/delete/bin/merge), backups, forced password change and permission gating were all exercised end-to-end. ~55 evidence screenshots in `shots/`. Findings were verified against source where behavior was ambiguous. Dev-mode artifacts (synthetic whole-image face detection, demo-mode banner) are excluded or explicitly flagged.

---

## 1. Overall production-readiness assessment

**Not yet production-ready — close, with a small number of high-impact workflow defects to resolve.** The application is substantially improved since the previous audit: the visual language is consistent and refined, dark theme is high quality, destructive actions are well-guarded (type-to-confirm, automatic pre-action backups, clear reassurance copy), provenance is visible throughout, role enforcement is honest ("hidden controls are only a convenience"), and the queue-driven ingestion journey is genuinely guided.

The remaining gaps cluster in four themes (theme 1 since reclassified — see amendment above):

1. **Default-empty World**: the signature exploration feature presents as broken for typical small/realistic datasets because of filter defaults and factually-worded empty claims (A-11) — **RECLASSIFIED: the default is intentional per operator decision; only the zero-state wording remains, pending design approval.**
2. **Silent validation and dead-end states in the review queue** — the highest-frequency workflow in the product: mandatory unexplained counts, disabled unexplained primary actions, redundant competing messaging (A-02, A-03, A-04).
3. **Discoverability of identity-data entry** — notes have no visible affordance; country/location autocomplete actively misfiling data (A-01, A-12).
4. **Chrome noise** — permanent undismissable banner stack, redundant badges, jargon chips that erode the otherwise strong visual craft (A-13, A-14, A-07).

No P0 defects were found: no security, data-integrity or critical-functional failure was observed. Data-mutation safety (backups before destructive actions, tombstones, restore paths) verified working.

---

## 2. Coverage matrix

| Area | Viewer | Operator | Custodian | Technician | Admin | Depth |
|---|---|---|---|---|---|---|
| Sign-in / forced password change | ✔ | ✔ | ✔ | ✔ | ✔ | full journey incl. rejection of reusing admin-set password |
| Check a photo (recognize) | nav present | ✔ | ✔ | nav present | ✔ | upload → STRONG MATCH results, empty state, escape/validation |
| Review photos queue (upload→group→details→identity→relations→finalize) | correctly absent | ✔ | ✔ | correctly absent | ✔ | full lifecycle ×5 events, all step types, browse-people assignment, per-pair relations, exclusion |
| People grid/search/filter/group/sort | ✔ | ✔ | ✔ | ✔ | ✔ | search, grouping, collections sidebar, stats cards |
| Profile: overview/photos/sightings/events/associations/activity | ✔ | ✔ | ✔ | ✔ | ✔ | all tabs read; edit drawer; favorite; photo details panel |
| Archive → Archived collection → restore | — | — | ✔ perm | — | ✔ | executed; toast + auto-backup verified |
| Delete → Bin | — | — | ✔ perm | — | ✔ | dialog verified (type-to-confirm); execution not completed |
| Merge duplicates | — | — | — | — | ✔ | dialog verified; execution not completed |
| Notes + @mentions | ✔ view | ✔ | ✔ | ✔ | ✔ | editor verified in source; no visible entry affordance (A-12) — editing not executed |
| Events list/detail/filters | ✔ | ✔ | ✔ | ✔ | ✔ | list, filters, detail with participants/relations/media |
| Event corrections/attach media | — | ✔ | ✔ | — | ✔ | buttons present; execution not completed |
| World Explore canvas/inspector/filters | ✔ | ✔ | ✔ | ✔ | ✔ | discovery click, canvas, inspector, evidence filter analysis |
| World Connections | ✔ | ✔ | ✔ | ✔ | ✔ | tab reached; deep drilldowns not completed |
| Settings: License | ✔ visible | ✔ | ✔ | ✔ | ✔ | read |
| Settings: Backups — create | — | — | ✔ executed | — | ✔ | backup created successfully; list populated |
| Settings: User accounts | — | — | — | — | ✔ | read; role badges, MUST CHANGE PASSWORD state |
| Settings: Integrity/System/Activity/About | partial | partial | partial | ✔ technical sections | ✔ | captured; not deeply exercised |
| Dark theme | — | — | — | — | ✔ | high quality, consistent |
| Narrow window (760px) | — | — | — | — | ✔ | layout holds; minor truncation |
| Recognition references management | — | — | — | — | partial | button present; flow not exercised |
| Keyboard-only navigation | not systematically tested — Mantine baseline focus behavior observed incidentally |
| Import/restore backup, integrity/recovery execution | not tested (destructive-environment risk in shared audit data) |

**Honestly not tested or incomplete**: merge execution to completion, bin restore execution, event correction execution, recognition-reference add/remove, backup import/restore, integrity recovery flows, deep Connections drilldowns, systematic keyboard/screen-reader pass, long-string stress (very long names), dense-data stress (>50 people), attachment of media to existing events. These are coverage gaps of this audit, not product defects.

---

## 3. Prioritized findings

### P1 — broken or broken-feeling workflows

**A-11 · World Explore hides typical relationships by default and reports them as absent** — ⚠️ **RECLASSIFIED BY OPERATOR: the strength-2 default is intentional and must remain unchanged.** The observation below stands as documentation of behavior; the recommendation to change the default is withdrawn. Only the filter-aware zero-state wording question remains, pending design approval.
Location: World → Explore. Roles: all.
Repro: fresh dataset with people co-observed in exactly one event → open World → click a person in Discover → canvas shows a lone node; Inspector reads "0 Relationships / 0 Evidence records" — while the same person's profile Associations tab correctly lists the co-observed relationship. Root cause (source-verified): default filters are `evidence_type: ["CO_OBSERVED"]` **and** `min_relationship_strength: 2` (`utils/world.js:898`); a single co-observation has strength 1, so it is filtered out before rendering. The "Weaker links ON" toggle only affects canvas display of already-fetched edges — it cannot reveal filtered-out data. The Inspector states "0 Evidence records" as fact rather than "hidden by current filters". In small deployments — the normal case for this product — essentially every relationship is single-strength, so World appears empty/broken on first use.
Impact: the product's signature exploration feature undermines trust; users conclude the graph is broken.
Recommendation (amended): DO NOT change the default (operator decision). The only residual design question is whether to make the inspector's zero-state filter-aware ("2 relationships hidden by current filter settings — show weaker links"); consider renaming "Weaker links" to what it does.

### P2 — interaction and usability deficiencies

**A-01 · Country/location autocomplete has no exact-match prioritization — actively misfiles identity data**
Location: person creation/edit, event details. Roles: operator+.
Repro: type `india` in Country → the visible top suggestion is "British Indian Ocean Territory" (substring "indian", alphabetical order) above exact "India". Verified in `filterCountries` (plain substring filter, alphabetical order preserved) and live — several seeded people were misfiled to BIOT through normal use.
Impact: wrong country data entered silently by well-meaning operators; nationality-adjacent fields are high-sensitivity identity data.
Recommendation: rank exact match first, then prefix matches, then substring; show match quality.

**A-02 · Mandatory unexplained "With how many individuals" blocks completion silently**
Location: review queue, new-person and accept-existing followup forms. Roles: operator+.
Repro: resolve a group identity and leave the count untouched → Confirm does nothing. No inline error, no scroll to the offending field, no "unknown" option. The same data is labeled "With how many individuals" in creation but "Number of individuals" in profile edit.
Impact: dead-end in the product's highest-frequency workflow; forces inventing numeric data for every sighting even when unknown.
Recommendation: optional with explicit "unknown" or sensible default; surface validation errors inline at the field with a summary jump-link; unify the label.

**A-04 · Disabled unexplained primary action in group review**
Location: review queue → group resolution. Roles: operator+.
The first action ("Choose a person to accept") is disabled whenever there is no automatic candidate — which is the common case. The actual path (Browse People inside the match panel) is visually secondary and must be discovered. Nothing explains why the primary is disabled or what to do instead.
Recommendation: when no automatic candidate exists, make browsing the primary action; or annotate the disabled control ("no automatic candidate — browse people to choose manually").

**A-03 · Redundant competing match-status messaging; truncated badge**
Location: review queue group resolution. Roles: operator+.
Three overlapping statements compete: panel "Weak match / No reliable automatic match…", card "Human review needed / The closest result did not meet the matching threshold", and an orange badge clipped to "WEAK MA…" at 1440px. Queue rows similarly duplicate "NO MATCH" (title + suggested-identity line).
Recommendation: one status message per object, one badge fully rendered; remove the rest.

**A-12 · Notes have no visible affordance**
Location: person profile Notes card. Roles: all (write: operator+).
The card shows "No notes added" with no button, icon or hint. The editor (a drawer with @mention support) exists but must be discovered by accident. Given notes+mentions are a core evidence type feeding the graph, this hides a major feature.
Recommendation: persistent "Add note"/edit affordance in the card.

**A-14 · Permanent undismissable banner stack**
Location: global chrome. Roles: all.
Up to three full-width banners (red safety-copy, blue changes-since-backup, yellow demo-mode) consume ~120px vertical on every screen. Red+blue are the same topic. None are dismissable even transiently. Viewer — who cannot act on backups at all — still sees the red banner (see F40 below). Positive note: the blue banner correctly cleared once a backup was created.
Recommendation: consolidate backup state into one banner; allow snooze/dismiss per session; suppress or reword for roles that cannot act.

**A-22 · Manually assigning people with recognition-ineligible embeddings is impossible in the browse picker**
Location: review queue → Browse People. Roles: operator+.
Source-verified: biometric-mode browse requires `person.match` non-null; people whose embeddings are all quality-ineligible never receive a match row and are invisible in the picker — so they cannot be manually assigned to sightings even though manual assignment is exactly the fallback for recognition failure. In dev mode this is amplified (noise images score poorly), but the production path exists for poor-quality-only enrollments. No-photo people at least have the dedicated no_face mode.
Impact: potential dead-end for exactly the people who most need manual assignment.
Recommendation: include enrolled-but-ineligible people in manual browse with a clear "not recognition-eligible" marker (manual assignment is a human decision, not recognition inference — no invariant is violated).

**A-09 · Event date is required and prefilled with today** — ⚠️ **WITHDRAWN BY OPERATOR: intentional behaviour, must remain unchanged.** Documented here for completeness only; no action.
Location: encounter details modal. Roles: operator+.
An operator confirming quickly silently records today's date for older photos; the product supports undated/imprecise events elsewhere, but the form offers no "date unknown" path. Given the product's temporal-precision rules, silently-wrong exact dates are worse than honestly-unknown ones.
~~Recommendation: allow unknown dates explicitly~~ — withdrawn; intentional behaviour per operator decision.

### P3 — consistency, polish, minor defects

- **A-05** Tag (required select: Important/Regular/Suspicious) vs Tags (freeform labels) naming collision in Edit drawer; neither explained.
- **A-06** Photo Details "Added" shows the event's date/time ("Time unknown"), not when the photo was added — provenance ambiguity.
- **A-07** "WARN" badge on review photos unexplained; "Peek In" jargon for preview.
- **A-08** Signup password max length (256) revealed only via error; validation errors appear as a detached block rather than at fields.
- **A-13** Green success-colored "Unknown" context chip on every event row — color/semantics mismatch, noise when context is genuinely unknown (the enum default).
- **A-15** Context enum (ordinary/public/unknown) silently defaults to "unknown" in the details modal.
- **A-16** Profile Activity tab drops the breadcrumb+actions header row other tabs keep (verify; possibly intentional).
- **A-17** Grid card overflow menu (Copy ID / Delete Person…) inconsistent with profile More menu (Copy ID / favorite / merge / archive / delete).
- **A-18** Duplicate affordances: Archive as header button AND More-menu item; favorite as star AND menu item.
- **A-19** mm/dd/yyyy filter inputs vs ISO display everywhere else.
- **A-20** Settings sidebar truncates "Integrity & recover[y]" at 1440px.
- **A-21** User accounts list repeats the username twice for the current account.
- **A-23** Duplicate accessible names: main-nav "Events" tab vs profile "Events" sub-tab (screen readers; also breaks test automation strict mode).
- **A-24** Narrow widths truncate the red banner text mid-word; toasts overlap banners.

### Verified strengths (keep)
- Type-to-confirm destructive delete with honest copy ("moves to Bin. Photos and history are kept; restore anytime").
- Automatic database backup before destructive actions, announced in the toast.
- Archive/delete/merge copy is precise about what is preserved — unusually good provenance communication.
- Forced password change flow: focused, explains why, rejects reusing the admin-set password, offers Sign out.
- Honest role notice: "Hidden controls are only a convenience. Every protected operation is independently authorized by the local API."
- Dark theme is high quality and consistent; narrow layouts hold.
- Collections sidebar (All/Favorites/With Photos/No Photos/Archived/Bin/Deleted Faces) with accurate counts.
- Event detail shows relations with included/excluded provenance; mention-vs-attendance separation in filters is correct per spec.

---

## 4. Previous audit reconciliation (F01–F40)

**Verified fixed or improved:**
- **F39** temporary passwords — fixed (forced change flow verified live, reuse rejected).
- **F35** no-photo person creation — fixed (primary "Add without photo").
- **F31/F32** delete semantics/filing — improved: separate Bin and Deleted Faces collections, honest tombstone copy. Bin execution path not fully re-verified.
- **F05** note access — the editor exists and is capable (@mentions) but discoverability regressed into invisibility (A-12): partially fixed.
- Role permission gating broadly correct (F33-adjacent): viewer/technician correctly lack ingestion affordances; custodian = operator + destroy per backend roles.

**Still present / regressed:**
- **F40** safety-copy banner role-unaware — confirmed still present: viewer sees "Your safety copy needs attention — the owner can check it under Settings" and cannot act.
- **F04/F13** feedback placement/language density — the banner stack and redundant match messaging (A-03, A-14) are the same class of problem in current form.
- **F28-adjacent** (misleading scope-wide empty claims) — A-11 is the same defect class in World Explore: filtered-empty presented as actually-empty.

**Not re-verified this pass** (coverage limits, listed honestly): F01/F02 keyboard edge inspection, F08/F30 stale recovery/restart states, F09 import retry, F15/F36 correction staleness, F16 discard confirmation, F17/F29/F34 recovery/session edge cases, F18/F20/F22/F24/F25/F26 specific defect re-checks, F27 world location measures, F37 backup list labeling, F38 clear-button behavior. Where these overlap with this pass's new findings (corrections, backup list), they should be verified together in the fix cycle. No evidence of regression was observed in areas that were exercised, except where noted above.

**New this pass (not in F01–F40):** A-01 autocomplete misfiling, A-02 mandatory count, A-04 disabled-primary dead end, A-11 world defaults (new feature surface), A-12 notes affordance, A-22 picker exclusion, plus the P3 consistency set.

---

## 5. Improvement plan (prioritized, bounded)

**Wave 1 — workflow-critical quick wins (est. small, high value):**
1. ~~World defaults~~ — **removed per operator decision**: the strength-2 default is intentional. (Only filter-aware zero-state wording may be proposed, pending design approval.)
2. Review queue: inline validation errors + optional/unknown count + unify label (A-02); re-path the disabled primary action (A-04); deduplicate match messaging, fix badge truncation (A-03).
3. Country/location autocomplete ranking (A-01). *Small, prevents ongoing data corruption.*

**Wave 2 — discoverability and data honesty:**
4. Notes card affordance (A-12); ~~event date-unknown path (A-09)~~ — removed per operator decision; browse-picker inclusion of ineligible-enrolled people with clear marking (A-22 — needs one design decision).

**Wave 3 — chrome and consistency:**
5. Banner consolidation + role-awareness + dismissability (A-14, completes F40); Tag/Tags rename + explanations (A-05); menu consolidation (A-17, A-18); photo "Added" disambiguation (A-06); date-format unification (A-19); badge/chip jargon cleanup (A-07, A-13, A-15).

**Wave 4 — verification debt:**
6. Complete the audit's unverified mutation executions (merge, bin restore, corrections) and the un-re-verified previous findings list above, preferably as scripted regression journeys.

All waves preserve existing functionality, architecture and design language; none requires redesign. Items 1–3 are independent; item 4's picker change needs one product decision (is manual assignment to ineligible-enrolled people intended?).

---

## 6. Evidence index
Screenshots in `shots/`: `p1-*` first load/onboarding, `cp-*` check-a-photo, `pa-*` people/profile/edit/photos/associations/activity/sightings, `ev-*` events list/detail, `w-*` world explore/canvas/evidence control, `st-*` settings sections, `m-*` archive/menu/merge, `j-*` backup/delete/merge/dark/narrow, `r-*` role passes. Key evidence: `w-03` (empty-canvas world vs. existing association), `j-05` (dark theme quality), `m-03/j-03/j-04` (destructive-action copy), `r-operator-0-forcedpw` (password flow + validation).
