# Issue #6 — executive assessment, design-system review and roadmap

[Audit index](INDEX.md) · [Findings](findings.md) · [Coverage](coverage.md) · [Independent review](review.md) · [Reuse map](reuse-map.md)

Basis: Pass 1/2 runtime evidence at `b457f0a` (macOS, synthetic plus private genuine-ONNX supplement) and Pass 3 at `677bb61` (Linux Chromium, synthetic, J42–J52). Browser regressions for the six mandatory flow families are in [PR #42](https://github.com/suraj-singh12/sentri-face-edge/pull/42) (tests only). These are audit recommendations, **not approved designs**; any UI change still needs a Figcraft-first proposal and operator approval (AGENTS.md).

## 1. Verdict

**Would I approve this UI for a polished, professional v2.0.0 release today? No.**

The data model holds up under hostile use. In every tested path, nothing graph-affecting persisted before explicit completion. Participants deduplicated, stale revisions were refused, and server-side session revocation worked. Archive and delete kept history, and restore kept a safety backup. No P0 data-loss or authorization bypass was found.

The product is still not release-polished. Too many moments leave a careful operator unsure what happened or what will happen:
- **Destructive language:** delete wording contradicts what delete does (F31), and the tombstone has no clear home (F32).
- **Recovery feedback:** access changes and restarts end in a generic error (F34, F30).
- **Evidence clarity:** unknown time is shown as an exact time (F01). A hidden note association survives (F20).
- **Workflow defects:** erase fails after corrections (F18), and Attach retry and Connections paging dead-end (F25, F28).
- **Accessibility:** graph edge evidence cannot be reached by keyboard (F02).

Release acceptance is also not yet possible on evidence grounds:
- The current SHA is unverified on Windows and macOS.
- No screen-reader pass has been done.
- Genuine multi-face ONNX is blocked on this VM.
- #4 (Encounter Split/Merge) is unimplemented.

**Strengths to keep, not redesign:**
- Explicit per-face decisions with a Complete gate.
- Typed DELETE plus a safety backup before archive, delete and restore.
- Correction history with expected-revision refusal.
- Archive history that stays readable.
- Capability-filtered navigation backed by API enforcement.
- Explanatory warnings in Move photo, Move to Deleted Faces and Associations.
- The draft-versus-applied filter scope in World Connections.

## 2. Ten highest-impact UX weaknesses

| # | Weakness | Findings | Why it matters |
|---|---|---|---|
| 1 | Destructive lifecycle language and status are inconsistent (archive/delete/tombstone/Deleted Faces) | F31, F32, F16, F38 | Operators cannot predict reversibility; a tombstone looks archived; some discards need no confirmation while others need typed confirmation |
| 2 | Session end, access change and restart collapse into a generic error | F34, F30, F09 | Users cannot tell outage from revocation; work is lost without a reason |
| 3 | Evidence shown more precisely than it was recorded | F01, F27, F13, F35 | Unknown time shown as exact; mixed measures; required sighting data the user cannot see again |
| 4 | Feedback after consequential actions is missing or covers controls | F36, F04, F09 | Corrections save silently; toasts sit on Discard/Complete |
| 5 | Stale data has no direct recovery action | F08, F15, F36, F10 | Refresh does not refresh the open detail; empty states shown before the first read finishes |
| 6 | Permission boundaries look like broken controls | F06, F33, F29, F40 | Disabled with no reason, or enabled then refused; role descriptions are never shown |
| 7 | Raw identifiers and jargon leak into operator text | F11, F19, F22, F31, F32, F37 | Backup ids, filesystem paths, SQL constraint text, “restricted by the backend” |
| 8 | Recovery dead ends in multi-step workflows | F18, F25, F24, F28, F17, F26 | Erase, Attach retry, nested folders and Connections paging stall |
| 9 | Keyboard and screen-reader access gaps in graph views | F02, F32 | Edge evidence unreachable; deleted nodes are focusable no-ops |
| 10 | Long names and labels truncate exactly where decisions are made | F03, F07, F05 | Wrong-person risk; Attach target not prominent; Notes hard to read |

## 3. Design-system consistency analysis

| Pattern | Current vocabulary (observed) | Inconsistency | Proposed system rule (reuse) |
|---|---|---|---|
| Destructive confirmation | Typed `DELETE` (case-sensitive, rule unstated); simple modal for archive/restore; no confirmation for pending Encounter discard (F16) or Clear with decisions (F38) | Same level of risk gets different friction | Three levels: reversible (no modal plus Undo toast), consequential (modal stating what changes and what stays), irreversible or tombstone (typed confirmation with the case rule stated). Reuse the PeopleView modals |
| Lifecycle status | Badges ARCHIVED, DELETED · HISTORICAL; collections Archived and Deleted Faces; actions Restore person and Restore backup | “Restore” and “Archived” each mean two things | One status vocabulary: Active / Archived (restorable) / Deleted (history only). Rename backup restore to “Restore database…” |
| Feedback | Mantine toasts (top-right, over controls), inline Alerts, silent closes | Success sometimes silent; errors duplicated; toasts cover controls | Toasts for completed actions, kept clear of the decision bar; inline Alert for field or conflict errors; never both for one error |
| Disabled controls | Mantine disabled; red Clear gradient without a disabled override; tooltips that describe the enabled action | Disabled looks enabled; no reason shown | Disabled state token plus reason tooltip and `aria-describedby` (“Requires Custodian”) |
| Terminology | Event / Encounter / Sighting / Observation; Skip / DEFERRED / skipped; Review photos / Complete Review | Several names for one concept | Glossary in `docs/UI_UX_DESIGN.md`: Event (user-facing) = Encounter (domain); Skip = Defer |
| Identifiers | Raw backup ids, session ids (fixed in PR #40), person ids in logs | Machine ids shown as primary labels | Human label first (date · origin · counts), id only behind Copy |
| Primary action color | Teal primary; red for both Clear and ACCEPTED-adjacent tints; teal “Restore Safely” | Red is not reserved for danger | Reserve red for destructive actions; neutral or teal for confirm; check contrast tokens |

Intentional differences to keep: World Explore's dense analytical layout (#13), and Review photos' multi-step queue versus Check a photo's single-image flow.

## 4. Prioritized roadmap (implementation batches)

Each batch is a coherent PR into `v2-hardening-followups` after its own Figcraft-first review and operator approval.

| Batch | Scope (findings) | Priority | Complexity / risk | Acceptance criteria |
|---|---|---|---|---|
| A. Lifecycle language and status | F31, F32, F16, F38, F40; delete only offered after archive explained | P1 | Low–medium; copy and UI state only, no domain change | Delete dialog states what is kept; tombstones in their own labelled view; deleted graph nodes `aria-disabled` with plain name; Clear and pending-discard confirm when decisions exist; browser tests in PR #42 updated |
| B. Session and recovery feedback | F34, F30, F09, F17 | P1 | Medium; frontend `useApiClient` auth-required path, possibly a reason code from the API | Revoked, expired or restarted sessions show “Your session ended” with reason and Sign in; no generic toast; restart recovers without a manual full reload |
| C. Evidence truthfulness | F01, F27, F20, F35, F18 | P1 | Medium–high; touches projections and domain contracts, so needs domain review | Unknown time never shown as exact; World measures labelled; empty note removes its association; no-photo initial sighting policy decided and visible; erase works after corrections |
| D. Feedback and stale-state recovery | F36, F04, F08, F15, F10 | P2 | Low–medium | Every correction shows a success summary; no-op Save disabled; Refresh reloads an open detail; toasts never cover the decision bar; loading is distinct from empty |
| E. Permission communication | F06, F33, F29, F39 | P2 | Low | Every role-disabled control explains why; role descriptions shown in Add account; Viewer Favorite consistent; temporary-password policy decided |
| F. Identifier and jargon cleanup | F11, F19, F22, F37, F13 | P2 | Low | No raw ids, paths or SQL text in primary UI; backup rows show origin, date and counts; duplicate import warned |
| G. Workflow dead ends | F24, F25, F26, F28, F07 | P1/P2 | Medium | Nested folders grouped; Attach retry keeps its target; Connections pages state their scope; Attach target prominent |
| H. Accessibility and layout | F02, F03, F05, F12, F23 | P1/P2 | Medium | Keyboard path to edge evidence; names never truncated in decision rows (wrap or tooltip); keyboard Notes reader; graph focus order verified with VoiceOver/NVDA |

**Quick wins (low effort, high effect):** F31 copy, F38 disabled style and confirm, F33 role reason tooltips, F36 success toast and Refresh reload, F40 banner text, F37 origin labels.

**Foundational shared fixes:**
- A single destructive-confirmation component with three levels.
- A disabled-with-reason wrapper.
- An auth-required session-ended state.
- A toast placement rule.
- A user-facing glossary in `docs/UI_UX_DESIGN.md`.

Together these resolve roughly a third of the findings.

**Recommended order:**
1. A and B, which make destructive actions and session loss trustworthy.
2. C, after a domain review.
3. D and E.
4. F, G and H.

H's keyboard graph fix (F02) can run in parallel with batch A.

## 5. Decisions needing operator approval

1. Should a tombstoned Person open a read-only historical profile, or stay list-only (F32)?
2. Should Delete be offered only after Archive, as it is today, or directly with stronger copy (F31)?
3. No-photo Person: should the initial sighting fields be optional, shown as an unverified note, or create a real sighting (F35)? This is a domain decision.
4. Must administrator-set passwords be changed at first sign-in (F39)?
5. Should access-change sign-outs tell the user the reason, which reveals that an administrator acted (F34)?
6. Should account display-name edits stop revoking sessions? Today any account update revokes them.
7. Should a duplicate backup import be refused, warned, or allowed (F37)?

## 6. Dependencies and ownership

- **#4 Split/Merge:** no Split/Merge entry point is proposed here. Batch D's correction feedback pattern should be reused by #4.
- **#13 World:** F01, F27 and F28 are reported as integration and clarity defects for #13's owners; this audit proposes no World redesign.
- **#5 release acceptance:** needs batches A–C resolved or explicitly accepted, plus the gaps below.

## 7. Release acceptance gaps (for #5)

| Gap | Status | Next step |
|---|---|---|
| Current-SHA Windows and macOS runtime check | NOT RUN at `677bb61` | Rerun J42–J52 on disposable Windows and macOS hosts |
| Screen reader (VoiceOver, NVDA) | NOT RUN | Graph, review decision bar and dialogs |
| Genuine ONNX multi-face, ambiguous and poor-quality | BLOCKED on Linux VM (no licensed models) | Private run on a licensed host; keep it separate from synthetic results |
| Interrupted restore, failure injection, cross-schema backup | NOT RUN | Disposable host with a kill switch during restore |
| Remove or reassign participant; full Correct Relations | NOT RUN | Extend J49 |
| Exhaustive role-denial API matrix at `677bb61` | PARTIAL | Backend test sweep of every protected route |
| Signed installer lifecycle | Owned by #5 | Not part of #6 |
