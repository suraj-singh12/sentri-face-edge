# SentriFace Edge — Project Handoff for a Planning Agent

**Date:** 2026-11-23 (IST). **Repository:** [suraj-singh12/sentri-face-edge](https://github.com/suraj-singh12/sentri-face-edge).
**Who you are working with:** the operator, `suraj-singh12`, owns the product, approves designs and approves every merge. An engineering agent (Devin) implements what the operator approves.
**Purpose of this file:** to let a planning agent understand the product, its architecture, its rules and its current state well enough to combine deliverables into clear, bounded instructions for the engineering agent.

---

## 1. What the product is, and why it exists

SentriFace Edge is an **offline, CPU-only face-recognition and identity-evidence application**. An operator uses it on a single local machine (Windows and macOS are the supported targets; Linux is a development path). Operators use it to:

- check photos, with the software detecting faces and **suggesting** who each one is;
- confirm who was present at an **Event** (internally called an *Encounter* or *observation*): when, where, which photos, which people;
- keep **People** profiles, with reference photos, lifecycle (Active, Archived, Deleted), merges and corrections;
- investigate the resulting history: People, Events, the **Person Graph** and the **World** view (clusters, connections, recurrence, discoveries).

**Why it is built this way:** the data is sensitive and the setting is often air-gapped. The product therefore has to be:

- **offline:** no cloud, a loopback-only API, and a network guard;
- **encrypted:** SQLCipher database, OS keyring custody, encrypted backups;
- **auditable:** an operation journal, immutable history and correction trails.

Most importantly, it is **evidence-based**. The model only *proposes*. Only explicit operator decisions create durable identity and history.

**Vision for v2.0.0:** a product that is technically correct, secure, dependable, intuitive for first-time users and efficient for experienced operators. It must also be consistent and accessible, reliable when things go wrong, properly tested and accurately documented. The UI standard is **Apple-HIG-inspired**: calm, predictable, plain language, no raw IDs or jargon, and nothing invented.

---

## 2. Architecture

| Layer | Technology | Where |
|---|---|---|
| Backend | Python 3.12, `ThreadingHTTPServer` on 127.0.0.1:8765, OpenCV, ONNX Runtime (SCRFD/ArcFace-compatible, licensed models supplied by the user, not bundled), Argon2, `cryptography`, `keyring` | `src/sentriface/` |
| Storage | Encrypted SQLite (SQLCipher), inline versioned migrations, **schema v36** (v35 `embeddings.erased_at`, v36 `app_users.must_change_password`) | `src/sentriface/storage/sqlite_store.py` (+ `sqlite_*.py` helpers) |
| Service boundary | `FaceEngine` orchestrates detection, embedding, matching, cleanup, indexes | `src/sentriface/engine.py` |
| API + authorization | Loopback HTTP API, capability checks on every route | `src/sentriface/api_server.py`, `auth.py` |
| Frontend | React 19, Mantine 9.3, Vite; controllers in `frontend/src/hooks/`, views in `frontend/src/views/` | `frontend/` → built into `src/sentriface/ui_static/` (generated; never hand-edited) |
| Derived caches | Vector indexes (linear, HNSW): rebuildable, not authoritative | `src/sentriface/components/` |
| Backup | Portable Backup v3: encrypted snapshot plus authenticated media closure | `src/sentriface/backup_service.py` |
| Integrity | `ReadOnlyIntegrityChecker` (P11 invariants), structured repair | `integrity.py`, `structured_repair_service.py` |

**Main tabs:**
- **Check a photo:** single-photo recognition.
- **Review photos:** a multi-photo queue grouped into Events.
- **People**
- **Events**
- **World:** Explore | Connections.
- **Settings:** accounts, backups, recovery, models, license, diagnostics.

**Roles (enforced server-side):**

| Role | Capabilities |
|---|---|
| Viewer | view, recognize |
| Operator | Viewer + add (enrollment, review) |
| Custodian | Operator + destroy (archive, delete, restore, corrections), backups, backup delete |
| Technician | view, recognize, backups, technical diagnostics; no review finalization |
| Administrator | everything: accounts, database restore, recovery, license |

### Core invariants: never break these

1. **Offline only:** loopback API, socket guard, OS network policy checks.
2. **Encrypted local storage:** the SQLite database is the single source of truth.
3. **One global identity graph.** The Person Graph and World are read projections of it. The graph must be rebuildable from authoritative records.
4. **Recognition is a proposal.** Nothing durable changes until the operator explicitly finalizes it.
5. **Multi-face Events finalize atomically.** Every face needs a decision, and the operator must press Complete. Data, graph evidence and the journal entry are written in one transaction.
6. **Every important write** carries an idempotency/operation ID and a journal entry in the same transaction.
7. **Relationship evidence types stay separate:** `CO_OBSERVED`, `NOTE_REFERENCE` and `MANUAL_ASSOCIATION`. Removing one piece of evidence never removes a relationship that other evidence still supports. Event participants are deduplicated by canonical person, and nobody links to themselves.
8. **Archive and delete are identity states, not erasure.**
   - Deleted means a soft delete: a tombstone that keeps all history, cannot be opened, and can be restored.
   - Merge keeps both identities and all history.
9. **Reference Only photos** (Batch 3.7) are contextless biometric samples, capped at 4 active per person. They never create Events, evidence or World activity.
10. **Prefer additive, versioned migrations.** Every migration is tested for fresh install, every upgrade path, rollback, repeat start-up, foreign keys and backup-before-migrate.
11. **React is not an authority.** No durable state lives in the UI.

### Key terms
- **Event / Encounter / observation:** one real-world occurrence. "Event" is the approved user-facing word; "Encounter" is internal only.
- **Embedding:** a stored face vector (biometric sample) belonging to a person.
- **Moved face:** a face reassigned with "Move to another person". This writes durable correction history.
- **Deleted Faces:** a 30-day recovery area for individual faces. It is separate from the person **Bin**.
- **Canonical person:** the surviving identity after a merge.

**Canonical documents (read in this order):**
1. `AGENTS.md`
2. `docs/README.md`
3. `docs/IMPLEMENTATION_PLAN.md`
4. `docs/PROJECT_OVERVIEW.md`
5. `docs/ARCHITECTURE_STATE.md`
6. `docs/DOMAIN_MODEL.md`
7. `docs/FEATURES_BY_TAB.md`
8. `docs/UI_UX_DESIGN.md`
9. `docs/AGENT_HANDOFF.md`

---

## 3. Branches: how the repository is laid out today

```
main                         7e7b4a6  v1.0.0 (2026-08-17). Untouchable without explicit permission.
 └─ release-v2.0.0-hardening b457f0a  v2.0.0 hardening line (33 commits ahead of main)
     └─ v2-hardening-followups 677bb61 operator-directed integration branch (25 ahead, 0 behind)
         ├─ PR #42 test/issue-6-browser-regressions
         ├─ PR #45 fix/issue-43-session-ended-reason
         ├─ PR #46 fix/issue-44-correction-toasts
         ├─ PR #48 fix/issue-47-person-bin
         └─ PR #50 fix/issue-49-face-erase-stub
```

**What `v2-hardening-followups` is:** the operator created it as the integration branch for work coming out of the 2026-11-22 engineering takeover audit. It contains everything on `release-v2.0.0-hardening`, plus merged PRs #38–#41:
- **[#38](https://github.com/suraj-singh12/sentri-face-edge/pull/38):** documentation and Linux development setup brought in line with the code (issue #35).
- **[#39](https://github.com/suraj-singh12/sentri-face-edge/pull/39) and [#40](https://github.com/suraj-singh12/sentri-face-edge/pull/40):** workflow dead-ends, provenance, backup-drive safety, plain language, and no raw IDs in the UI (issue #36).
- **[#41](https://github.com/suraj-singh12/sentri-face-edge/pull/41):** contract tests and a browser smoke test in CI, lock-pinned installs, report-only ruff/eslint, and move-only splits of storage, API and bundle (issue #37).

**Rules for this branch:**
- Every new issue branch starts from `v2-hardening-followups`, and its PR targets that branch.
- `AGENTS.md` names `release-v2.0.0-hardening` as the PR target; the operator's instruction overrides that for this follow-up work.
- Promoting `v2-hardening-followups` into `release-v2.0.0-hardening` later is a separate step that needs approval.

**CI (GitHub Actions) on each PR:**
- backend tests on Ubuntu, macOS and Windows;
- frontend tests and build;
- lint plus a browser smoke test;
- an unsigned Windows package build;
- Devin Review (automated code review).

---

## 4. What is finished

**Merged into `release-v2.0.0-hardening` (historical v2 work):**
- P0–P14 engineering phases, from the original architecture through the Windows packaging foundation.
- Batches 2, 3, 3.5, 3.6 and 3.7: Encounters, corrections, Attach Media, provenance, Reference Only.
- CI repair: [#1](https://github.com/suraj-singh12/sentri-face-edge/issues/1) and [#9](https://github.com/suraj-singh12/sentri-face-edge/issues/9) (staging only; adopting it on `main` is deferred).
- World intelligence [#3](https://github.com/suraj-singh12/sentri-face-edge/issues/3).
- World Explore [#13](https://github.com/suraj-singh12/sentri-face-edge/issues/13).
- Fix for corrected participants in World: [#22](https://github.com/suraj-singh12/sentri-face-edge/issues/22).
- World navigation [#31](https://github.com/suraj-singh12/sentri-face-edge/issues/31) (Explore | Connections).
- QA campaigns [#16–#21](https://github.com/suraj-singh12/sentri-face-edge/issues/16), accepted by the operator.
- The Product Studio UI charter, `docs/UI_UX_DESIGN.md` ([PR #33](https://github.com/suraj-singh12/sentri-face-edge/pull/33)).

**Merged into `v2-hardening-followups`:** PRs #38, #39, #40 and #41 (see section 3).

**Audit (#6, Pass 3):** a full hands-on audit of all six operator flow families on `677bb61`:
- 52 journeys, findings F01–F40, more than 100 screenshots;
- a verdict, a top-ten list, a design-system review and a roadmap.

It lives in **draft [PR #34](https://github.com/suraj-singh12/sentri-face-edge/pull/34)**, which is **evidence only and must never be merged**. Key files are `audit-results/issue-6/assessment.md` and `findings.md`.

**Audit verdict:** the data model held up. No data loss and no authorization bypass were found. The UI is not yet polished enough to release: unclear wording, silent saves, dead ends, raw errors, names cut off, and keyboard and accessibility gaps.

---

## 5. Open PRs: done and waiting for operator review and merge approval

| PR | Issue | What it delivers | Status |
|---|---|---|---|
| [#42](https://github.com/suraj-singh12/sentri-face-edge/pull/42) | [#6](https://github.com/suraj-singh12/sentri-face-edge/issues/6) | Browser regression tests for the six operator flow families (tests only) | Open; CI was green when last checked |
| [#45](https://github.com/suraj-singh12/sentri-face-edge/pull/45) | [#43](https://github.com/suraj-singh12/sentri-face-edge/issues/43) | "Your session ended" with the specific reason (account disabled, access changed, password reset, timeout, restart with a Reload button) instead of "Connection or operation error". Reasons are kept in memory only; no schema change. | Open |
| [#46](https://github.com/suraj-singh12/sentri-face-edge/pull/46) | [#44](https://github.com/suraj-singh12/sentri-face-edge/issues/44) | Success and failure toasts after Event corrections. "No changes to save" sends nothing and adds no history entry. | Open |
| [#48](https://github.com/suraj-singh12/sentri-face-edge/pull/48) | [#47](https://github.com/suraj-singh12/sentri-face-edge/issues/47) | A new **Bin** collection below Archived. Deleted people appear only in Bin, can't be opened, and **Restore** returns them to Active. Wording changed to "Delete Person…" / "Delete "Name"?", with no "permanently". The raw backup ID is removed from the toast. **Delete behavior is unchanged:** it is still a soft delete with a safety backup and a journal entry, and an active person can still be deleted directly. The invalid "Deleted Today" count was removed. | Open; 965 backend and 158 frontend tests pass, plus a browser test |
| [#50](https://github.com/suraj-singh12/sentri-face-edge/pull/50) | [#49](https://github.com/suraj-singh12/sentri-face-edge/issues/49) | **Face erase stub, plus a fix for the 30-day cleanup.** See section 6. | Open; **all CI green**; Devin Review finding fixed |

**Merge notes:**
- The PRs overlap mainly in generated `src/sentriface/ui_static/` assets, and #48 and #50 both touch `PeopleView.jsx`. After each merge, rebase the next PR and **rebuild `ui_static`** rather than hand-merging it.
- PR #42's browser tests may need small updates after #48 changes the delete wording and adds Bin.
- **Suggested merge order:** #42 → #45 → #46 → #48 → #50.

---

## 6. Latest work: Issue #49 / PR #50 (face erase)

**Problem (audit F18, verified):** "Deleted Faces → Erase permanently" failed with `FOREIGN KEY constraint failed` for almost every saved face. Event face lists (`observation_face_assignments`) and correction history (`identity_corrections`) point to the face with `ON DELETE RESTRICT`, so that history is deliberately protected.

The 30-day automatic cleanup was also broken:
- it erased its whole batch in one transaction, so one blocked face failed the entire batch;
- it retried every hour and failed every time;
- it never removed face crops, because the file paths were never passed to it.

**Behavior the operator approved:**
- Erasing a face, manually or through the 30-day cleanup, turns it into a small **"face removed" stub** whenever an Event or correction still references it.
- The stub keeps only the face ID and its owner. The biometric vector, the face crop and the old sighting rows are removed.
- The **Event photo is kept and protected**, because other people in the Event share it.
- Faces nothing references are still deleted outright.
- Erased faces disappear from Deleted Faces and cannot be restored.

**Implementation details:**
- Schema **v35** adds `embeddings.erased_at`; the migration is additive and idempotent.
- `list_all_file_references` now includes Event photos.
- Event review reads report `face_erased`.

**Backups:**
- New backups contain the stub.
- Older backups still contain the full face, and restoring one brings it back.
- Devin Review caught one real bug: after the v35 upgrade, backups verified by the v34 app were rejected. That is fixed, with a test.

**Tests:**
- Backend: 972 passed.
- Frontend: 157 passed.
- Build and browser smoke test pass.
- New file `tests/test_face_erase_stub.py` covers Event faces, moved faces, unreferenced faces, mixed batches, backup and restore, the v34 upgrade and restoring a v34 backup.

---

## 7. Approved by the operator but not yet started

Each item needs its own self-explanatory issue and branch before work starts. Audit finding IDs are in brackets.

| # | Deliverable | Operator decision / detail |
|---|---|---|
| 1 | **No invented times** [F01] | Events show "Time unknown", but World → supporting proof and the Person Graph show the same Event as "12:00 AM", sometimes on the wrong day. Rule: show the time if it's known, otherwise say "Time unknown". Applies to all views. |
| 2 | **Long Person Notes wrap** [F05] | Use the existing styling; full text readable without edit rights. |
| 3 | **One operator, one window** | **Done: issue [#54](https://github.com/suraj-singh12/sentri-face-edge/issues/54), merged in [PR #63](https://github.com/suraj-singh12/sentri-face-edge/pull/63).** A new sign-in, for any account, ends every other session, and a second window shows "SentriFace is open in another window" with **Use this window**; a window silent for 45 seconds counts as closed. Lowers the priority of stale-data findings F08/F15. |
| 4 | **Role limits explained** [F06, F33] | Disabled controls say why, e.g. "Requires Custodian or Administrator". Viewer Favorite consistency. |
| 5 | **Human-readable backups and duplicate import** [F11, F37] | Show origin (Manual / Imported / Safety copy), date and counts, never raw IDs. Re-importing the same backup **warns but is allowed**. |
| 6 | **Rename error** [F22] | Unique names for unknown placeholders are intended. Replace "UNIQUE constraint failed" with "Another unknown person is already called X. Choose a different name." |
| 7 | **Failed Attach recovery** [F25] | After a failed Retry, the Retry and Cancel buttons disappear and the draft is stuck. Keep the targeted Retry and Cancel (Attach ownership rules in AGENTS.md). |
| 8 | **Nested-folder grouping** [F24] | Uploading `Trip/Day1` and `Trip/Day2` should offer "Suggest grouping"; today it stays disabled. Trace the cause. |
| 9 | **Connections page 2** [F28] | Page 2 wrongly says "No qualifying … clusters exist in this scope"; state the page scope correctly and allow going back. |
| 10 | **Names never cut off** [F03, F07] | In Review and People decision rows: wrap the text, or show a tooltip, following the design language. |
| 11 | **One confirmation dialog, three strengths** | Light (Cancel / OK), Medium (shows what changes), Strong (type a word); one shared look. |
| 12 | **Movable toasts** | Top-right stack that moves out of the way of open dialogs, can be dragged, remembers its position and can be reset. Must never cover decision buttons [F04]. |
| 13 | **Apple-style glossary** | **Event** everywhere on screen (Encounter internal only); **Skip for now** replaces Skip/Defer; **Restore** for people; **Restore from Backup…** for backups. Record it in `docs/UI_UX_DESIGN.md`. |
| 14 | **No-photo sighting becomes a real Event** [F35] | "Add without photo" requires date, place and occasion, but today they are stored as hidden profile data and never shown. Save them as a real Event with one participant, no photo and no relationships. **Also convert the existing hidden sightings** (needs a migration). Photo and no-photo people are otherwise identical; the only difference is biometric enrollment. |
| 15 | **Forced password change** [F39] | **Done: issue [#54](https://github.com/suraj-singh12/sentri-face-edge/issues/54), merged in [PR #63](https://github.com/suraj-singh12/sentri-face-edge/pull/63).** Required at first sign-in after an Administrator creates an account **or resets a password** (schema v36 `app_users.must_change_password`); the owner's sign-up and the command-line emergency reset are not flagged. |

**Audit findings not yet decided or scheduled** (see `findings.md` in PR #34):
- F02: keyboard access to graph edge evidence.
- F08 / F15: stale Refresh.
- F09, F10, F12, F14, F16, F17, F19, F20, F21, F23, F26, F27, F29, F38, F40.
- F20, a hidden association that survives an emptied Person Note, is an evidence-correctness issue and should be prioritized.

**Open question never answered:** should editing an account's display name stop signing that user out? Today any account edit ends their sessions.

---

## 8. Larger open issues (v2.0.0 scope)

| Issue | What | State |
|---|---|---|
| [#6](https://github.com/suraj-singh12/sentri-face-edge/issues/6) | Operator UI refinement and end-to-end acceptance. **Mandatory before release.** | Audit done (PR #34); fixes in progress (sections 5 and 7) |
| [#4](https://github.com/suraj-singh12/sentri-face-edge/issues/4) | Encounter Split/Merge: split one Event into two or merge two Events, safely and with history. **Mandatory before release.** | Not started; needs a domain-policy proposal, a Figcraft design and approval first |
| [#5](https://github.com/suraj-singh12/sentri-face-edge/issues/5) | Release acceptance: signed Windows installer lifecycle, macOS/Windows qualification, real ONNX models | Blocked until #6 and #4 are done |
| [#9](https://github.com/suraj-singh12/sentri-face-edge/issues/9) | Adopt the CI workflow on `main` | Deferred until explicitly authorized |
| [#35](https://github.com/suraj-singh12/sentri-face-edge/issues/35), [#36](https://github.com/suraj-singh12/sentri-face-edge/issues/36), [#37](https://github.com/suraj-singh12/sentri-face-edge/issues/37) | Takeover phases 1–3 | PRs merged; issues still open and can be closed when the operator wants |
| [#43](https://github.com/suraj-singh12/sentri-face-edge/issues/43), [#44](https://github.com/suraj-singh12/sentri-face-edge/issues/44), [#47](https://github.com/suraj-singh12/sentri-face-edge/issues/47), [#49](https://github.com/suraj-singh12/sentri-face-edge/issues/49) | Session-ended reasons, correction toasts, Bin, face erase stub | Each has an open PR (section 5) |

**Release gaps that have not been verified at all:**
- Windows or macOS at the current code;
- screen readers (VoiceOver, NVDA);
- real-model ONNX multi-face recognition (no licensed models on the Linux VM);
- an interrupted restore;
- removing or reassigning Event participants;
- a full API matrix of role denials;
- signed installers.

---

## 9. How work is done (process the engineering agent follows)

1. **Self-explanatory GitHub issue first, for every feature:** the problem, verified evidence, the approved behavior, what is unchanged, and the test plan.
2. **One branch per issue**, from `v2-hardening-followups` (`fix/issue-N-…`, `feature/issue-N-…`). The PR targets `v2-hardening-followups`.
3. **Substantial UI changes:** read `docs/UI_UX_DESIGN.md` and `FEATURES_BY_TAB.md`, then present a design proposal and get approval before coding. Figcraft/Figma is not connected in these sessions, so proposals are annotated wireframes. Small wording or behavior fixes the operator has explicitly approved can go straight to code.
4. **Ask only real product decisions,** after understanding the architecture well enough to tell a feature from a bug. Recommend a default with each question.
5. **Verification:** `python -m pytest -q`, `npm --prefix frontend test`, `npm --prefix frontend run build`, plus browser tests when the UI changes. Rebuild `ui_static` from `frontend/`. Never call red CI green.
6. **No merging** without the operator's explicit approval for that exact PR. **Never touch `main`.** Never merge PR #34.
7. **Communication:** plain, short words; scenarios when explaining; no raw IDs. Evidence (screenshots, video) when the operator asks for it.

**Development environment notes (Linux VM):**
- Python 3.12 virtualenv at `.venv312`; from a git worktree, set `PYTHONPATH=src`.
- `./run.sh dev` (synthetic recognition) needs a Secret Service keyring: `dbus-launch` plus `gnome-keyring-daemon`.
- Real recognition needs licensed ONNX models supplied by the operator.

---

## 10. Useful framing for combining deliverables into prompts

**Natural groupings:**
- **A. Evidence truth:** no invented times (1); the no-photo sighting as an Event, with migration (14); F20.
  - Touches domain and projections; needs careful tests and migration.
- **B. Shared UI building blocks:** confirmation dialog (11), movable toasts (12), disabled-with-reason (4), glossary (13).
  - Do these first, because the other UI fixes reuse them.
- **C. Clarity fixes:** rename error (6), backup labels and duplicate warning (5), notes wrap (2), names not cut off (10), Connections page 2 (9).
- **D. Workflow dead ends:** failed Attach (7), nested folders (8).
- **E. Session and security:** one window (3), forced password change (15). Builds on PR #45. Done in PR #63.
- **F. Then:** #4 Split/Merge (design first), and accessibility (F02, screen readers).
- **G. Finally:** #5 release acceptance on real Windows and macOS hosts with real models.

**A good instruction to the engineering agent states:**
- the deliverable;
- the approved behavior, in the operator's words;
- what must not change;
- any decision already made;
- whether a design proposal is needed first;
- whether the work should be one PR or several.
