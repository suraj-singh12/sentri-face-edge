# Current-experience findings — Issue #6

[Visual INDEX](INDEX.md) · [Independent review](review.md) · [Architecture reuse](reuse-map.md) · [Coverage and limits](coverage.md)

This is a BEFORE audit of source `b457f0a723e845dd1a92a07a577072c85146c89a`. Recommendations are directions to evaluate in the later approved design phase, not approved designs or implementation. Severity denotes operator impact in this audit, not roadmap issue priority. No authorization bypass or authoritative identity corruption was established. A source hypothesis is not a confirmed defect; [source-risk-review](source-risk-review.md) retains those distinctions.

| Priority | Finding | Frequency / reach | Classification |
|---|---|---|---|
| P1 | [F01 Unknown time becomes exact previous-day time in World/Graph](#f01-time-precision) | Every unknown-time occurrence crossing views | Confirmed presentation/domain-meaning defect |
| P1 | [F02 Person Graph edge evidence lacks keyboard access](#f02-keyboard-edge-inspection) | Every keyboard graph inspection | Confirmed accessibility/operability defect in sampled graph |
| P2 | [F03 Identity names and draft labels truncate during decisions](#f03-identity-disambiguation) | Frequent recognition/review/People tasks | Confirmed usability issue |
| P2 | [F04 Toasts cover decision controls](#f04-feedback-placement) | Upload, review, correction and genuine inference | Confirmed layout/interaction issue |
| P2 | [F05 Viewer Notes lack an obvious full-reading path](#f05-full-note-access) | Every long Person Note | Confirmed visual access issue; AT coverage limited |
| P2 | [F06 Viewer Favorite is enabled but forbidden](#f06-capability-affordance) | Common profile control; Viewer/Technician class | Confirmed permission-affordance mismatch; API holds |
| P2 | [F07 Attach review does not identify its target prominently](#f07-attach-context) | Every Attach workflow and resume | Confirmed context/discoverability issue |
| P2 | [F08 Stale correction lacks a direct recovery action](#f08-stale-recovery) | Conflicting edits | Confirmed recovery friction; refusal is correct |
| P2 | [F09 Import errors duplicate and discard retry context](#f09-import-retry) | Wrong export passphrase | Confirmed feedback/recovery issue |
| P2 | [F10 Initial reads can look like authoritative empty results](#f10-loading-versus-empty) | Startup/slow reads/dense collections | Confirmed transient presentation; no lost-data claim |
| P2 | [F11 Backup eligibility/target text loses useful identity](#f11-backup-identification) | Restore/export/recovery | Confirmed readability issue; no wrong-target claim |
| P2 | [F14 Group discard offers an action before its prerequisite](#f14-group-discard-prerequisite) | Queue cleanup before Event details | Confirmed interaction/sequence defect; data retained |
| P3 | [F12 Sighting thumbnail and opened photo can differ](#f12-sighting-media-context) | Multi-media Encounters | Confirmed presentation ambiguity; source contract explained |
| P3 | [F13 Evidence counts, people counts and jargon compete](#f13-cross-feature-language-and-density) | Associations/World/small windows | Confirmed consistency/density issues |

## F01 Time precision

**Problem → evidence:** The same unknown-time `Synthetic paired review` appears in Events as `2026-11-10 · Time unknown` ([J15](journeys/J15.md)), but World source Encounter/Evidence/Media and Person Graph show `Nov 9, 2026, 04:00 PM` or an exact occurrence interval ([J18](journeys/J18.md), [J19](journeys/J19.md), [J25](journeys/J25.md)). The VM is America/Los_Angeles. This is a confirmed cross-view display discrepancy; it is not proof of changed stored occurrence authority.

**Why → direction:** Operators comparing evidence can infer a different day and unwarranted exact time. Evaluate one precision-aware presentation of occurrence date, unknown/approximate/exact time and timezone across those views. Keep operational timestamps distinguishable from occurrence facts.

**Reuse → tradeoffs:** Reuse `EventsView.eventDateTime`, existing `event_details.time_precision`, shared World/date helpers and the existing Encounter DTO/read owners. Domain review must decide presentation/DTO propagation; do not silently reinterpret stored historical dates or invent #4 correction semantics. Exact technical timestamps may remain available in provenance disclosure.

## F14 Group discard prerequisite

**Problem → runtime evidence:** Queue exposes Discard and a destructive group confirmation before Event details are complete. Confirming produces `Request failed` / `Complete Event details before deciding identities`, and both groups remain ([J33 steps1–3](journeys/J33.md)). The misleading original capture filename is explicitly corrected in metadata and the journey. Whole-session discard then succeeds.

**Why → recommended direction:** Cleanup appears available but unexpectedly requires occurrence metadata. Evaluate an accurate prerequisite explanation and available-action state before confirmation; separately determine whether the existing domain contract intends to require metadata for group exclusion. No change to that contract is approved by this audit.

**Existing reuse → tradeoffs:** Reuse QueueView's existing active Encounter readiness, discard confirmation, controller and backend decision guard. Disabling without explanation can strand cleanup; silently removing a guard could alter draft authority. Preserve explicit whole-session cancellation and reference-aware cleanup.

## F02 Keyboard edge inspection

**Problem → evidence:** Forty actual Tab presses in a two-Person Graph cycle through shell, camera controls and Person nodes but never the relationship edge. Pointer selection exposes its evidence ([J25](journeys/J25.md)); `PersonGraphView.jsx` provides the hit line pointer/click handlers without a focusable role or keyboard handler. This is bounded runtime plus source evidence, not full screen-reader certification.

**Why → direction:** Keyboard operators cannot complete the same evidence inspection. Evaluate reachable relationship selection with visible focus and equivalent Enter/Space behavior.

**Reuse → tradeoffs:** Explore already has focusable edges and Enter/Space handlers in `WorldExploreCanvas.jsx`. Reuse that interaction and current evidence owner. Dense graphs need a bounded, meaningful navigation order or equivalent relationship list; blindly tabbing hundreds of edges is also poor usability.

## F03 Identity disambiguation

**Problem → evidence:** Browse People truncates names, Weak match and Drafted labels even at 1440px ([J06](journeys/J06.md), [J08](journeys/J08.md)). Long-name fixture cards and canvas labels amplify the problem ([J31](journeys/J31.md)). The accessible name can be longer than the visible label; not every hover variant was qualified.

**Why → direction:** Identity selection must remain unambiguous before accepting a proposal. Evaluate a complete selected identity label and a consistent route to full name, distinguishing metadata and stable ID.

**Reuse → tradeoffs:** Reuse `profileBrowse`, `AssociationIdentity`, existing candidate cards/inspector and profile reads. Wider cards or more text reduce visible candidates and canvas space; retain rank, quality, draft status and proposal-vs-decision distinction.

## F04 Feedback placement

**Problem → evidence:** Upload/decision toasts cover Confirm Event, Complete Review and Confirm Encounter grouping in timed captures ([J06](journeys/J06.md), [J08](journeys/J08.md)). It repeats in private real-inference frames ([J41](journeys/J41.md)). Ordinary notifications default to 4.5 seconds; the frames prove overlap at their capture times, not that it persists indefinitely.

**Why → direction:** The next decision is obscured exactly when the operator needs it. Evaluate feedback positioning, deduplication and local progress/status that preserve access to dialog footers.

**Reuse → tradeoffs:** Reuse the single Mantine Notifications provider, `useApiClient.showToast` and existing busy/error state. Do not suppress important committed/refused/recovery messages to make screens look quieter.

## F05 Full Note access

**Problem → evidence:** The Person Note summary cuts a line mid-glyph without an expand affordance ([J04](journeys/J04.md)); the Viewer profile repeats the clipping while Edit is disabled ([J24](journeys/J24.md)). Source summary styling limits height/overflow. The DOM may retain the text, so no claim that every assistive technology loses it is made.

**Why → direction:** Readers should not need edit authority to read a complete saved Note or its mention context. Evaluate a read-only expansion or complete reading surface.

**Reuse → tradeoffs:** Reuse `ProfileNoteSummary`, the existing saved Note/selected-ID mention model and drawer anatomy. Keep summary density useful, and keep reading separate from mutation permission.

## F06 Capability affordance

**Problem → evidence:** Viewer profile Favorite remains enabled; clicking produces `Your account is not allowed to perform this operation` ([J24](journeys/J24.md)). Four independently authenticated forbidden-operation probes returned HTTP 403. The backend boundary holds.

**Why → direction:** A common visible control offers an action this role cannot perform. Evaluate consistent unavailable-action presentation and explanation across profile/collection controls.

**Reuse → tradeoffs:** Reuse the current `canEdit`/capability matrix and server authorization; do not redefine roles. Hiding everything can impede learning, while unexplained disabled controls are also weak feedback.

## F07 Attach context

**Problem → evidence:** Attach opens an ordinary-looking Review Queue/Encounter 1 of 1 without a prominent target Event name ([J17](journeys/J17.md)). Restart/resume and completion retained the existing occurrence; the independent Encounter count stayed two. This is presentation friction, not an ownership failure.

**Why → direction:** Operators should be able to verify which existing occurrence receives the media before reviewing or completing it. Evaluate a persistent target/context cue and predictable return path.

**Reuse → tradeoffs:** Reuse `queueAttachment`, active review `target_observation_id`, the existing Event read and current queue controller. Do not offer regrouping into new Encounters or create a second Attach authority.

## F08 Stale recovery

**Problem → evidence:** Two real browser views produced a stale correction refusal with the unsaved edit retained ([J16](journeys/J16.md)). The message says reload, but the dialog offers Cancel and Save correction. Recovery required Cancel → Back to Events → reopen Event.

**Why → direction:** Correct conflict refusal needs an obvious, safe next step. Evaluate a reload/review-current action with explicit handling of the unsaved draft.

**Reuse → tradeoffs:** Reuse `expected_revision`, current detail loading and mutation reconciliation. Automatically retrying against a newer revision could apply intent the operator has not reviewed; never make that an implicit overwrite.

## F09 Import retry

**Problem → evidence:** Wrong-passphrase import closes the unlock dialog and emits both `Backup was not imported` and a generic `Connection or operation error`, repeating the same passphrase/damage explanation ([J22](journeys/J22.md), private error frame). A reopened import with the correct passphrase succeeded, then Restore Safely succeeded with a safety-copy notice.

**Why → direction:** Duplicate errors add noise and require reselecting the same file. Evaluate one actionable error and a retained safe retry context.

**Reuse → tradeoffs:** Reuse `DatabaseBackupsPanel` local dialog/file state and `useAppData` import handling. Never retain or expose the entered passphrase beyond the authorized operation or weaken encrypted-import verification.

## F10 Loading versus empty

**Problem → evidence:** The initial thirty-Person fixture view shows zero counts and `No people match` while the first read is pending; its next page shows all thirty records ([J31](journeys/J31.md)). Recently seen also has an explicit loading frame retaining prior selection. These are real intermediate captures, not data-loss evidence.

**Why → direction:** An unqualified empty message can be mistaken for missing data. Evaluate loading/settled-empty distinctions and retained context indicators.

**Reuse → tradeoffs:** Reuse existing controller loading/generation state and backend totals. Avoid introducing polling or discarding a valid prior selection merely to display a spinner.

## F11 Backup identification

**Problem → evidence:** Backup status truncates to `RESTORA…` in a 1440px table, timestamps ellipsize, and restore confirmation can identify only `the selected backup` ([J22](journeys/J22.md)). Actual import/restore passed for the selected disposable backup; no wrong-target execution is claimed.

**Why → direction:** Recoverability and target identity should be readable before replacement. Evaluate a clear backup name/date/status/file summary in both collection and confirmation.

**Reuse → tradeoffs:** Reuse existing backup reason, timestamp, `restorable`, verification and file-count fields plus the current restore modal. Keep long technical IDs available without letting them dominate the confirmation.

## F12 Sighting media context

**Problem → evidence:** A multi-media Sighting card uses the first generic Encounter image; selecting it opens the Person Photos view showing that Person's different source image ([J10](journeys/J10.md)). The current Sighting read intentionally includes all occurrence media. Source review explains the mismatch; it does not establish wrong face assignment or corruption.

**Why → direction:** A thumbnail in a Person history implies person-specific evidence unless labeled otherwise. Evaluate explicit Encounter-media context or the existing person-specific media projection with honest unavailable-image fallback.

**Reuse → tradeoffs:** Reuse the current Sighting/Encounter reads, `_encounter_person_media`, `SightingImage` and photo-selection owner. People present without a face may have no person-specific photographic crop; do not invent one.

## F13 Cross-feature language and density

**Problem → evidence:** Associations (2) can mean evidence-type groups while Associated people (1) means unique counterparts; the same Person appears in separate source rows ([J29](journeys/J29.md)). World mixes operator labels with raw IDs, ranking methods and navigation-intent explanation. Sighting unknown time appears as `date & -`, while Events says Time unknown. At 900×700, People metrics and Event filters push results below the first fold ([J26](journeys/J26.md)).

**Why → direction:** Consistent vocabulary, counts and hierarchy reduce interpretation work. Evaluate precise count labels and progressive disclosure of technical provenance while keeping common tasks/results apparent.

**Reuse → tradeoffs:** Reuse the existing independent evidence groups, unique-counterpart calculation, shared identity labels, provider/CSS tokens, scope controllers and compact Explore panel selector. Do not collapse evidence authorities or remove expert/recovery access to reduce density. These are usability/consistency findings, not a mandate for a new navigation system or aesthetic reskin.

## Patterns worth retaining

Explicit Relations Include/Exclude selected states; Reference Only origin, cap and retire/restore explanation; independent co-observed/Note/manual evidence; deliberate integrity preparation/refusal; verified safety backup and Restore Safely; Explore compact panels and nested proof/media Escape behavior; source-controlled capability enforcement; current Explore/Connections naming. These are design inputs, not approval to implement changes.
