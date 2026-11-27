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
| P2 | [F15 Stale correction error survives a changed action](#f15-stale-correction-error-survives-a-changed-action--p2) | Participant correction recovery | Confirmed stale feedback; valid correction subsequently succeeds |
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

## F15 Stale correction error survives a changed action — P2

**Problem → runtime evidence:** A last-participant removal is correctly refused inline and by toast. After changing the correction to REASSIGN and choosing a valid target, the old “Cannot remove the last or an absent participant” message remains visible next to the enabled Save correction action ([J15 pass 2](journeys/J15.md)). The reassignment then succeeds and its history is retained.

**Why → direction:** The stale refusal describes an action no longer selected, which can make a valid recovery look invalid. Evaluate clearing or scoping errors when the operator changes the correction intent, while retaining actual failed request context where useful.

**Reuse → tradeoffs:** Reuse the existing Encounter management modal state, server-side last-participant guard and correction-history read. Clearing a visual message must never silently retry or weaken server validation.

## F16 Pending Encounter discard has no confirmation — P1 usability / safety

**Problem → evidence:** In [J08 step 25 and J33 step 17](journeys/J33.md), one click on Discard Encounter removed the pending synthetic Encounter and left an empty queue; no confirmation appeared. The distinct path was absent from the original 509-contract inventory ([extension](discovered-branches.csv)). Group/session discard use confirmations.

**Why → direction:** An accidental activation can lose pending work without a decision point. Evaluate clear consequences, a consistent confirmation or recoverable undo appropriate to actual authority semantics.

**Reuse → tradeoffs:** Reuse existing queue confirmation patterns and controller checks; added interruption must be weighed against reversible recovery and operator frequency. No data-corruption claim is made.

## F17 Recovery setup error requires browser reload — P2 usability

**Problem → evidence:** An invalid destination produced a full-page error with no visible retry or sign-out; browser reload returned to the setup gate ([J01](journeys/J01.md)). The server correctly refused a destination inside its data directory.

**Why → direction:** A recoverable input error leaves the operator without an obvious in-product route back. Consider an explicit retry and safe exit while preserving the guard.

**Reuse → tradeoffs:** Reuse gate state and backend validation; never silently skip recovery or imply a copy exists.

## F18 Permanent erase fails after ownership corrections — P1 functional defect

**Problem → evidence:** After a synthetic face was moved to another Person and back, then placed in Deleted Faces, permanent erase failed twice with “FOREIGN KEY constraint failed”; the face remained and could be restored ([J11](journeys/J11.md)). A safety backup was created before the failure.

**Why → direction:** The operator cannot complete the promised irreversible action in this specific correction scenario. Investigate the retained dependency and transaction behavior; provide an actionable, safe error.

**Reuse → tradeoffs:** Retain existing typed confirmation, backup and history authority. Any fix must protect historical evidence and avoid broad conclusions about other erasures or corruption.

## F19 Model preparation exposes low-level path — P2 privacy / usability

**Problem → evidence:** Supported filenames with invalid synthetic bytes produced a parser error including a local audit-vault path; the original is private ([J32](journeys/J32.md)).

**Why → direction:** Low-level implementation detail is difficult to act on and can expose local layout in shared screenshots. Offer a concise failure and retry, with controlled technical details when needed.

**Reuse → tradeoffs:** Reuse setup validation and error handling; preserve diagnostic detail in appropriately protected support channels.

## F20 Empty Person Note retains hidden mention-linked association — P1 evidence correction

**Problem → runtime evidence:** In [J29](journeys/J29.md), an explicitly selected synthetic Person mention was saved. Clearing the entire note and saving made Overview say “No notes added,” while Associations still showed the other Person as “Mention-linked 1 evidence,” including after reload. No removal control for the selected mention was visible in the tested drawer.

**Why → direction:** An operator cannot see or correct this remaining link from the empty note presentation. Investigate intended history versus active evidence and provide explicit, traceable correction controls and clear status.

**Reuse → tradeoffs:** Reuse selected mention IDs, note revision guards and evidence provenance; do not erase history or equate a mention with attendance. The exact backend retention semantics are not inferred from this UI observation.

## F21 Safety warning opens generic Settings — P2 navigation

**Problem → runtime evidence:** From a Person profile, the safety-copy warning’s Settings button opened License & activation; a second selection was required to reach Backups & restore ([J24](journeys/J24.md)).

**Why → direction:** The urgent warning does not take the operator directly to the relevant recovery context in this observed navigation state. Consider retaining a specific destination while honoring permissions.

**Reuse → tradeoffs:** Reuse existing Settings navigation and backup readiness checks; restricted roles must receive a meaningful explanation rather than an inaccessible action.

## F22 Duplicate placeholder rename shows raw database constraint — P2 usability

**Problem → runtime evidence:** Editing a synthetic no-photo Person to an existing placeholder name was refused with a raw `UNIQUE constraint failed` index message; the editor stayed open and Cancel preserved the original ([J27](journeys/J27.md)). The underlying uniqueness guard was not bypassed.

**Why → direction:** A database index name does not explain the duplicate or how to recover. Translate the refusal into clear, actionable language while retaining server validation.

**Reuse → tradeoffs:** Reuse Person edit validation and existing error handling; do not silently merge identities or disclose private information.

## F23 Preferred profile photo is not initially shown — P2 visual / correctness

**Problem → runtime evidence:** After setting synthetic photo 2 as the profile photo, the gallery returned to photo 1. In a fresh browser session the profile header still displayed photo 1; selecting photo 2 showed its persisted “Profile photo” badge and updated the header ([J10](journeys/J10.md)).

**Why → direction:** The visible identity image conflicts with the saved preference until the operator selects the photo. Investigate default selection and make the saved representative and displayed header consistent.

**Reuse → tradeoffs:** Reuse the representative-embedding authority and existing gallery selector; preserve distinct Reference Only and Encounter origins. This observation concerns the sampled synthetic profile.

## F24 Nested-folder grouping suggestion unavailable — P1 workflow

**Problem → runtime evidence:** Two distinct synthetic subfolder paths were present in actual upload requests, and two face groups became ready, but Suggest grouping remained disabled on two uploads. Manual grouping succeeded ([J08](journeys/J08.md)).

**Why → direction:** Operators cannot use the offered folder-based grouping aid in this observed source workflow and must reconstruct the grouping manually. Trace relative folder provenance through upload, scan and grouping before choosing an interaction change.

**Reuse → tradeoffs:** Reuse the existing folder upload and grouping controller; suggestions remain proposals requiring operator confirmation. Do not infer that folder structure is authoritative Event truth.

## F25 Reference attachment retry loses targeted controls — P1 recovery / functional

**Problem → runtime evidence:** A Reference Only attachment is correctly refused and initially leaves a targeted draft. In two actual attempts, retry produced a different finalized-media error, after which Retry/Cancel disappeared and an empty Review Queue remained after reload ([J17](journeys/J17.md)). In the second attempt the targeted draft had survived a reload before retry.

**Why → direction:** The operator loses the visible targeted recovery path after retry and receives inconsistent failure explanations. Investigate durable draft ownership and surface a clear recoverable state.

**Reuse → tradeoffs:** Preserve the Reference/Encounter admission boundary and existing targeted retry/cancel authority. The screenshots establish UI behavior; they do not independently prove whether underlying session data was deleted.

## F26 Note-driven Person creation reached an error boundary once — P1 workflow / observed functional failure

**Problem → runtime evidence:** Creating a no-photo Person from an unmatched Note mention reached “SentriFace could not display this screen” and `Cannot read properties of undefined (reading 'name')`. Reload returned to sign-in; the first synthetic name was not found in People and the original profile showed no note. A separate creation with another name succeeded and its mention was saved ([J29](journeys/J29.md)). The first request response was not retained, and recurrence was not established.

**Why → direction:** An unexpected full-screen interruption loses the visible editing context at an identity decision. Investigate the failing creation path and preserve recoverable draft context; verify backend consequences independently before asserting data integrity.

**Reuse → tradeoffs:** Reuse the existing error boundary, Person creation and Note mention authority. Recovery must avoid duplicate Persons and must not convert literal text into an unconfirmed mention.

## F27 World location summary pairs different measures — P1 information clarity / confirmed presentation defect

**Problem → runtime evidence:** In the dense scope, the fifth summary tile shows a large `4` above the caption “1 events missing location”; the selected measured pattern states that one of 31 Events lacks location ([J18](journeys/J18.md)). Source defines the large value as the count of location facets, while the displayed caption is the missing-Event count.

**Why → direction:** Two different measures are visually coupled without identifying the large number, inviting an operator to read four as the number of missing Events. Label both values and units explicitly and preserve the distinction between facets and data-quality counts.

**Reuse → tradeoffs:** Reuse the existing World summary and backend totals. A clearer label must preserve the distinction between absent counts and zero, and should not turn data quality into a risk inference.

## F28 Connections page two makes a misleading scope-wide empty claim — P1 workflow / confirmed presentation defect

**Problem → runtime evidence:** In an all-time synthetic scope with one cluster, Overview page one displays that cluster. After Next authoritative page, the summary still reports one cluster while the cluster panel says “No qualifying backend cluster summaries exist in this scope” ([J18](journeys/J18.md)). Reset returns to page one and the cluster. No Previous control was observed on the second page; Reset also resets scope filters.

**Why → direction:** Page-local absence is expressed as a scope-wide absence of evidence, which can mislead an operator reviewing connections. Make the empty message reflect the current page and provide a clear way back while preserving applied scope.

**Reuse → tradeoffs:** Reuse the bounded World controller and authoritative totals/cursors; keep the revision-bound semantics and do not infer cluster membership from pagination. The underlying records were not shown to be deleted or corrupted.

## F29 Non-owner model gate gives an unavailable instruction — P2 interaction / confirmed wording inconsistency

**Problem → evidence:** A Viewer with missing models sees “Choose both model files below to finish setup” immediately above **The owner account is needed**; no file-selection controls are available ([J32](journeys/J32.md#macos-completion-pass-2--continuation-p-non-owner-model-gate)). Sign-out and owner sign-in reach the actual setup controls.

**Why → direction:** The first instruction asks a restricted operator to perform an unavailable action. Give the Viewer a role-specific instruction and retain an obvious sign-out/return path.

**Reuse → tradeoffs:** Reuse the existing owner gate and capability-derived rendering; preserve backend authorization and supplier-license messaging. This is a communication issue, not a demonstrated permission bypass.

## F30 Restarted service can be presented as unavailable when session has expired — P1 recovery / confirmed feedback defect

**Problem → evidence:** After a controlled stop of the disposable source server, the connection warning was appropriate. After the server reported startup, Refresh continued showing “SentriFace is not responding”; a toast separately said “SentriFace session authorization is required” and the actual `/api/profile` response was HTTP 401. Reload returned to sign-in and a fresh sign-in restored the shell ([J02](journeys/J02.md#macos-completion-pass-2--continuation-q-service-interruption-and-session-recovery)).

**Why → direction:** The suggested Refresh action cannot resolve this expired-session condition, and the persistent banner directs the operator to diagnose a server that is responding; the separate transient toast identifies an authorization requirement without an obvious sign-in action. Distinguish authentication expiry from connection failure and provide a clear reauthentication path while preserving unsaved-work safeguards.

**Reuse → tradeoffs:** Reuse existing session and connection error handling and the sign-in flow; keep authorization checks intact. The sample does not establish every disconnect or restart scenario.

## Pass 3 — current source `677bb61` (Linux Chromium, synthetic)

Pass 3 audits [`677bb61e8e9d659db95123871bb2e011cf663a79`](https://github.com/suraj-singh12/sentri-face-edge/commit/677bb61e8e9d659db95123871bb2e011cf663a79) on `v2-hardening-followups` (includes merged PRs #38–#41) in a disposable synthetic source authority on Linux headless Chromium, 1440×900, light theme. J42–J44 use an audit-only multi-face detector seam ([tooling/multiface_server.py](tooling/multiface_server.py)) that splits generated images into vertical synthetic faces; it validates workflow and persistence only, never recognition. Every role named below was a separate real local sign-in.

**Revalidated at `677bb61` (still present):** F04 toasts over Discard Face/Complete Review ([J43 step 6](journeys/J43.md)); F06 Viewer header Favorite enabled then refused while the More-menu item is disabled ([J47 steps 9–11](journeys/J47.md)); F08 stale correction without a reload action, now extended ([J49 steps 13–16](journeys/J49.md)); F09 duplicated import errors, including a misleading “Connection or operation error” title ([J45 steps 7 and 14](journeys/J45.md)); F11 truncated backup table and machine labels ([J45 steps 4 and 11](journeys/J45.md)); F30 restarted service reported as “not responding” ([J52](journeys/J52.md)).

| Priority | Finding | Reach | Classification |
|---|---|---|---|
| P1 | [F31 Delete wording contradicts tombstone semantics](#f31-delete-wording-contradicts-tombstone-semantics) | Every Person delete | Confirmed misleading destructive language |
| P1 | [F32 Deleted people are filed under Archived and dead-end](#f32-deleted-people-are-filed-under-archived-and-dead-end) | Every tombstoned Person | Confirmed lifecycle IA / accessibility defect |
| P1 | [F34 Access changes leave stale sessions and generic sign-out](#f34-access-changes-leave-stale-sessions-and-generic-sign-out) | Disable, role change, password reset, restart | Confirmed feedback/recovery defect; backend revocation holds |
| P1 | [F35 Required initial sighting of a no-photo Person is not surfaced](#f35-required-initial-sighting-of-a-no-photo-person-is-not-surfaced) | Every Add without photo | Candidate data-visibility defect; PARTIAL verification |
| P2 | [F33 Role-restricted controls do not explain themselves](#f33-role-restricted-controls-do-not-explain-themselves) | Viewer, Operator, Technician; account creation | Confirmed affordance/communication issue; API holds |
| P2 | [F36 Encounter corrections save silently and stale detail persists](#f36-encounter-corrections-save-silently-and-stale-detail-persists) | Every Encounter correction | Confirmed feedback/state issue; history correct |
| P2 | [F37 Backup list duplicates imports and mislabels origin](#f37-backup-list-duplicates-imports-and-mislabels-origin) | Import, restore, backup reminder | Confirmed clarity issue; no wrong-restore claim |
| P2 | [F38 Clear discards review decisions and looks enabled when disabled](#f38-clear-discards-review-decisions-and-looks-enabled-when-disabled) | Check a photo | Confirmed lost-work / visual-state defect |
| P2 | [F39 Temporary account passwords are not temporary](#f39-temporary-account-passwords-are-not-temporary) | Every administrator-created account | Confirmed wording/policy mismatch; product decision |
| P3 | [F40 Safety-copy banner is role-unaware](#f40-safety-copy-banner-is-role-unaware) | Every non-configured authority | Confirmed wording issue |

## F31 Delete wording contradicts tombstone semantics

**Problem → evidence (Custodian, J50 steps 10–12):** The confirmation is titled “Delete entire profile permanently?” with button “Delete entire profile”, while its body says “This tombstones the identity … Historical identity, sightings, relationships, and operation provenance remain represented.” The typed confirmation accepts only uppercase `DELETE` without saying so. The success toast exposes the raw safety-backup id `backup_…_before-person-permanent-delete-audit-bravo-…`. The Technician Activity log then records `person-purge … deleted: true, permanent: false` ([J47 step 22](journeys/J47.md)). After deletion the Encounter shows “Audit Bravo (deleted)” and the relationship remains ([J50 step 13](journeys/J50.md)), so the behavior is correct tombstoning.

**Why → direction:** “Permanently” and “entire profile” describe erasure that does not happen, which both frightens careful operators and misinforms them about what history survives. Name the operation for what it does (for example “Delete person (keep history)”), state what leaves active use versus what remains historical, make the case rule explicit or case-insensitive, and describe the safety backup by date rather than id.

**Reuse → tradeoffs:** Reuse the existing PeopleView delete modal, typed confirmation and backup-before-delete flow. Copy change only; the tombstone semantics in AGENTS.md must not change.

## F32 Deleted people are filed under Archived and dead-end

**Problem → evidence (Custodian, J50 steps 14–16):** After deletion, the People “Archived” collection lists the person with a `DELETED` badge, “Historical identity” and a disabled action; there is no profile entry. “Deleted Faces” is a different face-record collection. In the Person Graph the deleted node is an enabled, focusable button whose accessible name is “Audit Bravo is restricted by the backend (DELETED).” Activating it does nothing visible.

**Why → direction:** Archive (reversible, restorable) and delete (tombstone) are different lifecycle states but share one collection, and the graph presents an actionable control with no result and developer wording. Give tombstoned identities their own clearly labelled historical view or filter; decide (operator decision) whether a read-only historical profile should open; render non-interactive graph nodes as `aria-disabled` with plain wording, or open read-only evidence.

**Reuse → tradeoffs:** Reuse existing People collections, `HistoricalIdentity` status data, and graph node rendering. Archived nodes must stay non-clickable per AGENTS.md; whether deleted nodes may open read-only history is a product decision.

## F33 Role-restricted controls do not explain themselves

**Problem → evidence:** Technician Backups shows Import, every Restore and every Delete disabled with no reason; hovering a disabled Restore still shows “Restore this verified backup” ([J47 step 23](journeys/J47.md)). Viewer profile Manage faces/Edit/Archive and More-menu items are disabled without a reason ([J47 steps 9–12](journeys/J47.md)); Operator Event detail simply omits correction actions ([J47 step 16](journeys/J47.md)). When creating an account, the role picker shows bare role names; `ROLE_DESCRIPTIONS` are passed as option descriptions but never rendered ([J47 step 2](journeys/J47.md), `AccountsPanel.jsx`). The Custodian description “archive, delete, restore” refers to Person restore, not database restore, next to backup terms.

**Why → direction:** Operators cannot tell a permission boundary from a broken control, and administrators assign roles without seeing what each allows. Use one shared pattern: disabled control plus a short role reason (“Requires Administrator”) in tooltip and accessible description; render role descriptions in the picker; clarify “Person restore”.

**Reuse → tradeoffs:** Reuse the existing capability set, `ROLE_DESCRIPTIONS`, and Mantine Tooltip/description props. Backend authorization stays authoritative; this extends F06.

## F34 Access changes leave stale sessions and generic sign-out

**Problem → evidence (Administrator + second browser session, J51 steps 9–14):** Disabling a Viewer, changing an Operator to Viewer, or resetting a password revokes that user's sessions on the server (`auth.update_user` and `reset_password` revoke on any change). The affected open session keeps showing its old role, navigation (including Review photos) and cached data until its next request; Refresh then lands on sign-in with the generic toast “Connection or operation error”. Only a new sign-in explains “This account is disabled”. After a service restart, the same open sessions show “SentriFace is not responding — make sure SentriFace is still running, then click Refresh” although the server is up; only a full reload reaches sign-in ([J52 steps 1–4](journeys/J52.md); F30 revalidated).

**Why → direction:** The user cannot tell whether the system failed, their access changed, or the service restarted, and unsaved work is lost without explanation. Map authentication-required responses to a dedicated “Your session ended” state with the reason where known (signed out by an administrator, password changed, service restarted) and a direct sign-in action; suppress the generic error toast for that case.

**Reuse → tradeoffs:** `useApiClient.readResponse` already dispatches `sentriface-auth-required`; reuse it and the sign-in screen. Server revocation is correct and must stay.

## F35 Required initial sighting of a no-photo Person is not surfaced

**Problem → evidence (Custodian, J49 steps 7–8, J50 step 7):** “Add without photo” says “Add only observation details you actually know” but requires Rank, Name, Country, Tag, Date, Time, Place Seen, individual count and Event/Occasion. The API stores the sighting fields as `metadata.initial_observation` (`api_server.py` person-create), not as an Encounter. The entered sighting (“Placeholder seed”, Pune, 10:30) did not appear in the Person's Sightings, the Events list or Activity; only a later Encounter correction appeared.

**Why → direction:** Operators are forced to supply (or invent) occurrence data that they then cannot see, which undermines trust and may create false records. Decide whether these fields are optional, are shown on the profile as an unverified initial note, or create a real sighting. **Verification is PARTIAL:** the profile was not inspected before the later correction, and stored metadata was not read through a UI surface.

**Reuse → tradeoffs:** Reuse the existing Person create form and profile Overview. Any change touching occurrence authority is a domain decision, not a UI tweak.

## F36 Encounter corrections save silently and stale detail persists

**Problem → evidence (Custodian, J49):** Saving Correct Encounter with no changes closes silently yet appends “Encounter interpretation reviewed” history (step 3). Real corrections and participant additions also have no success feedback (steps 4, 12). Browser reload on a detail returns to the Events list (step 5) while re-clicking Events reopens the last detail (step 9). After a two-tab conflict, header Refresh does not reload the open detail; list and detail disagree (“(tab B)” versus “(corrected)”) until the user leaves and re-enters (steps 13–16). The relation choices appear as raw `INCLUDE`/`EXCLUDE` tokens (step 10).

**Why → direction:** Corrections change historical interpretation, so the operator needs confirmation of exactly what changed, and the recovery action (Refresh) must actually refresh. Disable Save until something changed (or say “No changes”), show a success summary, reload the open detail on Refresh and on conflict, and use plain relation labels.

**Reuse → tradeoffs:** Reuse `EncounterManagementModal`, the expected-revision conflict and existing toast system. Correction history semantics stay; this extends F08/F15.

## F37 Backup list duplicates imports and mislabels origin

**Problem → evidence (Administrator, J45; Technician, J47 step 23):** Importing the same encrypted export twice succeeds silently and creates two identical rows, both labelled “Manual backup” with the original creation time. The automatic pre-restore backup's card title is the raw reason `before-restore-backup_2026-11-22_18-19-25`; rows show raw backup ids. Restore confirmation names “the selected backup” without date, size or people count and uses a teal “Restore Safely” button. Right after restoring the newest backup, “You have changes since your last backup” reappears. A backup lists “2 people” while active People shows 1 (tombstoned counted, unexplained).

**Why → direction:** During recovery, operators must identify the right backup quickly. Label origin (Manual, Imported, Automatic before restore/archive/delete), show date, size and counts in the confirmation, warn on duplicate import, and reset the reminder after restore.

**Reuse → tradeoffs:** Reuse DebugView backup rows, existing backup metadata and the restore modal. Extends F11; backup verification and restore safety are unchanged.

## F38 Clear discards review decisions and looks enabled when disabled

**Problem → evidence (Administrator, J44 steps 3, 5–6):** With one face discarded and another undecided, Clear resets immediately with no confirmation; decisions are lost and reload does not recover them (nothing was persisted, which is correct). On the empty page Clear is disabled but renders with the same saturated red gradient as the enabled state because `.recognize-action--clear` has no disabled override (`sentriface-interface.css`).

**Why → direction:** The most visually dominant control is a destructive one that silently drops work. Confirm Clear when decisions exist, and give the disabled state a distinct appearance.

**Reuse → tradeoffs:** Reuse the existing discard-confirmation modal pattern and Mantine disabled styles. No persistence change.

## F39 Temporary account passwords are not temporary

**Problem → evidence (J47 steps 2 and 6):** Add account asks for a “Temporary password”. The Viewer signs in with it and is never asked to change it. Cancelling Change password keeps all three typed values when reopened ([J48](journeys/J48.md), step 5 private).

**Why → direction:** The label implies a security control that does not exist. Either enforce change at first sign-in (product/security decision) or rename the field; clear password fields on cancel.

**Reuse → tradeoffs:** Reuse the existing change-password modal. Enforcement would need a backend flag; that is an operator decision.

## F40 Safety-copy banner is role-unaware

**Problem → evidence:** With no external safety copy configured, every role sees “Your latest external backup is not available. The owner can check it under Settings.” The Administrator/owner sees it too, as do Custodian and Technician, who have Settings but not recovery configuration ([J44 step 1](journeys/J44.md), [J47 step 17](journeys/J47.md)). “Owner” is not one of the five role names, and “not available” is shown when no external backup ever existed.

**Why → direction:** Tell the owner what to do, tell others who can do it, and distinguish “never configured” from “unavailable”. Relates to F21 and F29.

**Reuse → tradeoffs:** Reuse the existing banner and capability set.
