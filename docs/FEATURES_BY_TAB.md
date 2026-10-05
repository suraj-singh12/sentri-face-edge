# SentriFace Edge features by tab

## Batch 3.7 operator flows

**People:** NO_FACE exposes prominent Add Face. ENROLLED exposes secondary Manage Recognition References, without prominent generic Add Face. Both open the same Recognition References modal and backend mutation. Management shows active/retired sources, quality, Reference Only labels, count /4, Retire/Restore and shared-sample warnings. Upload explains cropped single-person and Encounter-first rules; explicit no-context acknowledgment and exactly-one-face detection precede confirmation. Zero/multiple faces reject without a picker. Proof-only can leave Add Face visible while still consuming a slot. Photos visibly identify Reference Only origin; timed Deleted Faces/global transfer controls are disabled for Reference-backed samples.

**Review Photos / Events:** exact Reference media is rejected with instruction to upload the original occurrence/scene image. Independent Encounter photos retain normal participants/evidence. Attach uploads remain targeted until success or explicit Cancel; rejection exposes Retry/Cancel and survives restart without general queue leakage.

**Settings:** existing encrypted recovery/export/import restores Reference source ownership, quality and lifecycle along with normal authority. Compact backup-card sizing preserves pointer access without redesign. World remains an occurrence/relationship read model, with no Reference Only lifecycle inputs; Batch 4 is not implemented.

## Batch 3.6 current user-facing integrity

Check a photo displays the saved accepted Person or staged new identity, including after refresh/restart. The model's candidate list remains a proposal; an accepted new Person cannot open a committed profile before completion. Deferred faces remain Deferred. Browse People during an active Encounter now correctly includes committed profiles alongside draft candidates.

Associations shows one active standing Manual Association after aliases merge. Redundant raw assertions remain inspectable history with merge-linked retirement; removing the surviving assertion preserves independent Encounter/note support. Settings backup/import/Restore Safely and supported graph rebuild accept valid multi-photo provenance while preserving strict validation. Actual complex fresh restore and normal restart are qualified in IMPLEMENTATION_PLAN; physical file relocation is not a new occurrence or identity decision.


## Batch 3.5 behavior clarifications

- **Check a photo:** Skip displays Deferred and stays unresolved across refresh/restart; Discard is final negative; accepted-existing/new are final positive. Only final decisions permit completion, with at least one accepted participant. Add Face uses the explicitly chosen existing Person and the standalone enrollment command, preserves quality/origin, and creates no Encounter.
- **Review photos:** “remaining” is actionable pending groups, excluding removed or already-finalized media. Background restoration/group refresh cannot replace newer selection/Event editing. A deferred group remains distinct from accepted/discarded work.
- **People:** Archived cards open their historical profile when `VIEW_HISTORY` permits it. Restore remains restricted by existing backend capability and ARCHIVED lifecycle. Deleted/merged cards and historical graph nodes remain distinct. Associated people counts unique effective counterparts, not evidence/direction groups.
- **Events / People / Graph / World:** successful domain mutations reconcile retained current read models from the backend; raw correction and alias history remains provenance. Shared frame support comes from effective Encounter media, not row order.
- **Settings:** admitted source ONNX running status and packaged OS-boundary verification are separate facts. Explicit eligible Linux source development can configure normal encrypted recovery without an OS keyring; production and macOS/Windows custody are unchanged.

This is the current user-facing map. `DOMAIN_MODEL.md` defines authority and `ARCHITECTURE_EXPLANATION.md` explains implementation. **Implemented** means present in the current source; Batch 3 finalized Encounter management and normalized Manual Association controls are implemented; World vNext and Encounter Split/Merge remain deferred. Every tab reads the same local identity store through the authenticated loopback API.

Check a photo exposes **Finish enrollment** only for a staged explicit Person target, allowing an interrupted/lost completion response to retry the existing operation. Successful automatic completion still returns to People. Backups & restore supports fresh Linux source authority recovery with the normal recovery kit, encrypted import and safe restore; it does not package source custody secrets inside backups.

## Access

| Role | Existing capabilities | Current tabs |
| --- | --- | --- |
| Viewer | `view`, `recognize` | Check a photo, People, Events, World; read-only settings entry if license recovery requires it |
| Operator | Viewer + `add` | Also Review photos and authorized review/Person writes |
| Custodian | Operator + `destroy`, `backups`, `backup_delete` | Also lifecycle and backup controls |
| Technician | Viewer + `backups`, `technical` | Also technical Settings sections; no review finalization |
| Administrator | All listed capabilities | All tabs and Settings sections, including accounts, restore, integrity/recovery, and license administration |

`Events` GET uses `view` for all five roles. Attach Media uses `add`; finalized metadata/participant/Relations correction uses `destroy`; Manual Association create/retire uses `add`. Review writes require `add`. The server enforces capabilities even for direct URLs. Settings section visibility follows its more specific capabilities. A restricted license can replace ordinary tabs with the recovery Settings shell.

## Check a photo (`recognize`)

**Meaning and purpose:** upload local media, ask which existing Person each detected face might be, then make an explicit operator decision. **Implemented:** local face detection, quality assessment, candidate ranking, face comparison, Browse People, a one-time Event details modal, New/Existing Person resolution, Sighting Notes, selected-ID mentions, quality warning, and complete review. The preference **Prefer quality photos for recognition** controls stored candidate references; it does not judge or store the incoming face. Normal Browse defaults to **Biometric Available Profiles**, preserving backend rank and percentage; **No Biometric Profiles** deliberately lists only ACTIVE `NO_FACE` people, with no invented score. On Create New Person, a separate proof-only duplicate check can suggest an existing Person; using one or creating anyway remains an operator decision.

**Authority:** pending recognition and review are proposals. Completion atomically writes one finalized observation/Encounter, accepted participants, managed media, embeddings, Sighting Notes, any Person creation/update, permitted evidence, and the journal. Event metadata is entered once and inherited read-only by Person resolution. **Boundary:** a match or duplicate hint alone creates no Person, participant, note evidence, or graph edge. Poor faces remain historical even when `PROOF_ONLY` excludes normal matching. Access: recognition for all roles; finalized changes require `add`.

## Review photos (`queue`)

The 2026-10-01 correction persists Remove/Restore selection across restart before grouping; selection is locked after grouping. Already-finalized photos show a muted red excluded state with no removal action required. The recognition preference is left-aligned above the review workspace and applies to committed plus accepted active-draft references as one canonical Person set. ON prefers GOOD; when none exists POOR_ACCEPTED is fallback, while OFF admits both. PROOF_ONLY is never ordinary recognition; the shared Create New Person guard can suggest committed or draft proof-only-only identities. Only draft-created Persons show `Drafted`. Each incoming face card has Peek In, a 250×250 transient crop/coordinate preview with close control. New-Person validation uses current Name/Rank/Country/Tag/Added by values; individual count and Sighting Notes remain. Ordinary notifications default to 4.5 seconds; explicit decisions remain modal.

**Meaning and purpose:** group imported media into real-world Encounters, then review people and their co-presence. **Current flow:** upload → inspect per-photo finalized-media conflicts → confirm one or multiple Encounter buckets → enter Event details once → resolve or temporarily defer each identity group → decide every effective participant pair in Relations → Complete Review. One Encounter draft is active at a time and resumes after restart. Multiple Encounters requires a bounded count; distinct uploaded subfolders can suggest, but never confirm, a grouping. When no such local hint exists, the suggestion control explains why it is unavailable. Already-finalized photos are highlighted and excluded so unrelated photos can continue; the same retained bytes cannot create another independent occurrence. Skip means defer and automatically return after other pending groups; Discard/`EXCLUDE` is final. The current source photo marks the face being reviewed. The shared proof-only duplicate check guards face-based Create New Person in Recognize and Review Photos. Relations INCLUDE/EXCLUDE has visible selected state. **Authority:** drafts remain nonauthoritative; final completion uses one existing observation/Person/media/embedding/note/evidence/graph/journal transaction. Draft recognition never enters the global index. Access: `add`. Authenticated synthetic-media development UI was exercised in the 2026-10-01 correction; production-model and full-role walkthroughs remain separate verification limits.

## People (`people`)

**Meaning and purpose:** manage real Persons, including people who have no enrolled face. **Implemented:** browse/search, create without photo, metadata edit, canonical/lifecycle views, selected-ID Person Notes, Add Face, correction/merge controls as permitted, and Person Profile. `NO_FACE` means no usable ordinary-recognition sample; it does not mean unknown/deleted. A Person with only PROOF_ONLY or conflicted samples may remain NO_FACE. Standalone **Add Face** uses the shared Reference Only operation for an existing Person and records `STANDALONE_ENROLLMENT`; it creates no Encounter, sighting, participant, or co-observation.

Person Profile sub-tabs are:

| Sub-tab | What it shows/does | Authority boundary |
| --- | --- | --- |
| Overview | Person identity, metadata, lifecycle, presence and note controls | General editable `PERSON_NOTE`; Person changes use authorized commands |
| Photos | Effective face/media gallery, recognition quality and origin | `ENCOUNTER`, `STANDALONE_ENROLLMENT`, or `UNKNOWN_LEGACY` are durable provenance reads; a photo does not by itself imply a new Encounter |
| Sightings | Confirmed Person + finalized Encounter history and detail | Derived from effective participants, never mention-only references |
| Events | Newest-first occurrences where the Person is `PRESENT`, `MENTIONED`, or `BOTH`; filters, relevant observed media, Sighting/Event Note context | Compact rows open Global Encounter detail; mention-only media is never claimed to depict the Person |
| Associations | Evidence-backed Person relationships/Person Graph entry | Reads independent evidence; Add Association and per-assertion removal use normalized commands; no UI-owned edges |
| Activity | Existing journaled Person changes | Historical read, not an Event/Encounter list |

Archive, tombstone delete, and merge retain raw historical IDs; effective reads resolve the canonical survivor. Access to reads uses `view`; create/edit/Add Face uses `add`; destructive lifecycle actions use `destroy` where exposed. Historical summary reads now include named tombstones; deleted identities remain inactive and unavailable to active selection/recognition.

### Profile surfaces and actions (implemented now)

Photos distinguishes reference-face enrollment from accepted Encounter photos; it uses managed references and unique image tiles, not copied assets. A reused embedding does not substitute its original reference photo for the accepted Encounter photo. Read uses `view`; Add Face uses `add`; Move Face/delete use `destroy`. Face origin is displayed once with understandable labels. Mention-only Events supply no observed photos.

Events answers where the Person is PRESENT, MENTIONED or BOTH and opens the shared Encounter detail. Sightings answers confirmed participation and Person-specific Sighting Notes, excluding mention-only history. Both are newest-first backend reads under `view`; they change no authority. Search/date/location/context/status filters belong to the existing Events query.

Associations explains independent evidence and opens Person Graph. Add Association chooses a distinct active Person and creates one standing manual assertion under `add`; another request for the same active canonical pair reuses it. Remove manual association uses `add` and retires only that assertion. Encounter/note evidence can keep the relationship visible. A blocked identity merge offers Open conflicting Encounter, where `destroy` permits explicit Relation correction before retry.

## Events (`encounters`)

**Meaning and purpose:** read finalized real-world occurrences, distinct from the technical Activity log. **Implemented:** newest-first bounded pages; occasion, date/range, location, context, participant, and mentioned-Person filters; Event detail with participants, all supporting media, Event Note selected IDs, and Sighting Notes. A selected Event Note ID is structured `Encounter → Person` mention provenance. It is searchable in Events and Person Profile Events, but does not imply attendance or produce Person relationship evidence. Literal unselected `@Name` is inert. An Event with unknown legacy metadata remains unknown. Detail includes explicit Relations, support and bounded human-readable correction history. Attach Media (`add`) reuses Review Photos, skips duplicate finalized media and keeps the same occurrence. Correct metadata/selected mentions, reassign/remove/add participants and revise Relations require `destroy`. Changed Encounters require reload; competing attachment drafts must finish or be discarded. Encounter Split/Merge remains deferred.

## World (`world`)

**Meaning and purpose:** inspect backend-derived Person-to-Person intelligence from the one global evidence graph. **Implemented:** scoped World overview, deterministic evidence-component clusters, Person/Event/Evidence drilldowns, revision-bound bounded collections, explanations, filters, and read-only media inspection. Event drilldown is an evidence/history view; Events are not World graph nodes. Current relationship strength is an explained evidence count, not a probability or a designed recurrence tier. Current connected-component clustering can join groups through a qualifying bridge. The locked future direction seeks independently supported group-forming relationships without invented thresholds; see `ARCHITECTURE_EXPLANATION.md`. Event Note mentions do not change World edges, recurrence, clusters, strength, or group membership. Access: `view`.

## Settings (`debug`)

**Meaning and purpose:** local operational controls, distinct from domain Events. The current sections are **License & activation**, **Backups & restore**, **User accounts**, **Integrity & recovery**, **System details**, **Activity log**, and **About & support**. Sections appear only under their existing capabilities: license administration, `backups`/`database_restore`, `administer`, `recovery`, and `technical`, respectively. Backup/restore uses the portable authority closure; Integrity & recovery exposes only the frozen guarded P11 commands. Activity log is operational logging, not Encounter history. None of these sections owns graph truth. See `AGENT_HANDOFF.md` and P11/P12/P14 documents before touching release or recovery behavior.

## Terms that prevent mistaken authority

| Term | Meaning and boundary |
| --- | --- |
| Attach Media | Review additional photographs as evidence of the existing Encounter. Requires `add`; finalization preserves the occurrence ID and does not increment recurrence. |
| Correct Encounter | Revise occurrence metadata and selected Event Note IDs; requires `destroy`. Original values remain history. |
| Participant Correction | Reassign, remove or add effective attendance under `destroy`. Original assignments remain; newly affected pairs require explicit Relations. |
| Relation Correction | Deliberately revise INCLUDE/EXCLUDE under `destroy`; evidence and graph update atomically without changing attendance. |
| Manual Association | Standing independent Person↔Person assertion; create/retire requires `add`, not merely view access. It is neither attendance nor a note reference. |
| Historical / effective value | Originally saved or earlier revision / current interpretation after explicit corrections and canonical resolution. |
| Person / canonical Person | Stable raw identity / effective merged survivor. Merge retains raw history. |
| Encounter / Sighting | Finalized observation / one effective participant in it. Media count is not Encounter recurrence. |
| `EVENT_NOTE` / `SIGHTING_NOTE` / `PERSON_NOTE` | Encounter context / Person in one Encounter / general editable Person information. All support selected-ID mentions, but only Person-owned Sighting/Person Notes produce Person→Person `NOTE_REFERENCE`. |
| `CO_OBSERVED` / `NOTE_REFERENCE` / `MANUAL_ASSOCIATION` | Distinct co-presence / selected Person-owned note reference / explicit standing association evidence. Coexistence does not create extra Encounters. |
| `GOOD` / `POOR_ACCEPTED` / `PROOF_ONLY` | Embedding search eligibility, independent of face origin and Person biometric state. Proof-only is never an ordinary recognition reference. |
| `NO_FACE` / `ENROLLED` | Person has no / at least one usable ordinary-recognition sample, according to current source authority and quality. |
| Recognition / proof-only duplicate check | Ordinary candidate proposal / exceptional pre-creation hint for profiles with only proof-only faces. Neither is identity authority. |
| Recurrence / Activity / Cluster | Distinct independent Encounter support / recent ongoing behavior / derived group of evidence-connected people. Current World does not implement the locked future recurrence tiers. |
| Add Face / Review photos | Standalone biometric enrollment of an existing Person / staged multi-photo Encounter review. Add Face creates no Event; Review photos can finalize one. |
| Archive / Delete / Merge | Inactive but restorable identity / tombstoned historical identity / canonical survivor with source history retained. None physically erases old Encounter evidence. |
| Person Graph / World | Identity-centered / scoped intelligence projections of the same evidence graph. Neither owns relationship authority. |
| Face origin / recognition eligibility | How an embedding entered history / whether it may influence matching. They are separate, even after Move Face or merge. |

Every implementation batch must update this map and all affected canonical docs before claiming completion. Planned features must be labelled as planned, and frozen phase records remain historical acceptance evidence.
