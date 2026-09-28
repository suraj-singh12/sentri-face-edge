# SentriFace Edge features by tab

This is the current user-facing map. `DOMAIN_MODEL.md` defines authority and `ARCHITECTURE_EXPLANATION.md` explains implementation. **Implemented** means present in the current source; the later Relations and Encounter correction work remains deferred. Every tab reads the same local identity store through the authenticated loopback API.

## Access

| Role | Existing capabilities | Current tabs |
| --- | --- | --- |
| Viewer | `view`, `recognize` | Check a photo, People, Events, World; read-only settings entry if license recovery requires it |
| Operator | Viewer + `add` | Also Review photos and authorized review/Person writes |
| Custodian | Operator + `destroy`, `backups`, `backup_delete` | Also lifecycle and backup controls |
| Technician | Viewer + `backups`, `technical` | Also technical Settings sections; no review finalization |
| Administrator | All listed capabilities | All tabs and Settings sections, including accounts, restore, integrity/recovery, and license administration |

`Events` GET uses the existing `view` capability for all five roles; it has no Events mutation route. Review writes require `add`. The server enforces capabilities even for direct URLs. Settings section visibility follows its more specific capabilities. A restricted license can replace ordinary tabs with the recovery Settings shell.

## Check a photo (`recognize`)

**Meaning and purpose:** upload local media, ask which existing Person each detected face might be, then make an explicit operator decision. **Implemented:** local face detection, quality assessment, candidate ranking, face comparison, Browse People, a one-time Event details modal, New/Existing Person resolution, Sighting Notes, selected-ID mentions, quality warning, and complete review. The preference **Prefer quality photos for recognition** controls stored candidate references; it does not judge or store the incoming face. Normal Browse defaults to **Biometric Available Profiles**, preserving backend rank and percentage; **No Biometric Profiles** deliberately lists only ACTIVE `NO_FACE` people, with no invented score. On Create New Person, a separate proof-only duplicate check can suggest an existing Person; using one or creating anyway remains an operator decision.

**Authority:** pending recognition and review are proposals. Completion atomically writes one finalized observation/Encounter, accepted participants, managed media, embeddings, Sighting Notes, any Person creation/update, permitted evidence, and the journal. Event metadata is entered once and inherited read-only by Person resolution. **Boundary:** a match or duplicate hint alone creates no Person, participant, note evidence, or graph edge. Poor faces remain historical even when `PROOF_ONLY` excludes normal matching. Access: recognition for all roles; finalized changes require `add`.

## Review photos (`queue`)

**Meaning and purpose:** stage and group imported photos/faces for operator review. **Implemented:** batch upload, face grouping, candidate comparison, shared Browse selector, Event modal, New/Existing Person resolution, selected-ID Sighting Notes, quality preference, proof-only duplicate check, and explicit completion. The existing grouping workflow remains; full serial multi-Encounter orchestration is deferred. **Authority:** staged groups are proposals; completion uses the same observation, Person, media, embedding, note, evidence, and journal boundaries as Check a photo. **Boundary:** no group or recognition candidate becomes durable identity or relationship authority before finalization. Access: `add`.

## People (`people`)

**Meaning and purpose:** manage real Persons, including people who have no enrolled face. **Implemented:** browse/search, create without photo, metadata edit, canonical/lifecycle views, selected-ID Person Notes, Add Face, correction/merge controls as permitted, and Person Profile. `NO_FACE` means no enrolled face, not unknown/deleted and not a Person with only `PROOF_ONLY` embeddings. Standalone **Add Face** enrolls an existing Person and records `STANDALONE_ENROLLMENT`; it creates no Encounter, sighting, participant, or co-observation.

Person Profile sub-tabs are:

| Sub-tab | What it shows/does | Authority boundary |
| --- | --- | --- |
| Overview | Person identity, metadata, lifecycle, presence and note controls | General editable `PERSON_NOTE`; Person changes use authorized commands |
| Photos | Effective face/media gallery, recognition quality and origin | `ENCOUNTER`, `STANDALONE_ENROLLMENT`, or `UNKNOWN_LEGACY` are durable provenance reads; a photo does not by itself imply a new Encounter |
| Sightings | Confirmed Person + finalized Encounter history and detail | Derived from effective participants, never mention-only references |
| Events | Newest-first occurrences where the Person is `PRESENT`, `MENTIONED`, or `BOTH`; filters, relevant observed media, Sighting/Event Note context | Read-only; mention-only media is never claimed to depict the Person |
| Associations | Evidence-backed Person relationships/Person Graph entry | Reads `CO_OBSERVED`, `NOTE_REFERENCE`, `MANUAL_ASSOCIATION` distinctly; no UI-owned edges |
| Activity | Existing journaled Person changes | Historical read, not an Event/Encounter list |

Archive, tombstone delete, and merge retain raw historical IDs; effective reads resolve the canonical survivor. Access to reads uses `view`; create/edit/Add Face uses `add`; destructive lifecycle actions use `destroy` where exposed. The known `Unknown person: <UUID>` after deletion is a tracked high-priority regression.

## Events (`encounters`)

**Meaning and purpose:** read finalized real-world occurrences, distinct from the technical Activity log. **Implemented, read-only:** newest-first bounded pages; occasion, date/range, location, context, participant, and mentioned-Person filters; Event detail with participants, all supporting media, Event Note selected IDs, and Sighting Notes. A selected Event Note ID is structured `Encounter → Person` mention provenance. It is searchable in Events and Person Profile Events, but does not imply attendance or produce Person relationship evidence. Literal unselected `@Name` is inert. An Event with unknown legacy metadata remains unknown. Access: existing `view` capability; no Event edit/delete/attach/correct endpoint or control.

## World (`world`)

**Meaning and purpose:** inspect backend-derived Person-to-Person intelligence from the one global evidence graph. **Implemented:** scoped World overview, deterministic evidence-component clusters, Person/Event/Evidence drilldowns, revision-bound bounded collections, explanations, filters, and read-only media inspection. Event drilldown is an evidence/history view; Events are not World graph nodes. Current relationship strength is an explained evidence count, not a probability or a designed recurrence tier. Current connected-component clustering can join groups through a qualifying bridge. The locked future direction seeks independently supported group-forming relationships without invented thresholds; see `ARCHITECTURE_EXPLANATION.md`. Event Note mentions do not change World edges, recurrence, clusters, strength, or group membership. Access: `view`.

## Settings (`debug`)

**Meaning and purpose:** local operational controls, distinct from domain Events. The current sections are **License & activation**, **Backups & restore**, **User accounts**, **Integrity & recovery**, **System details**, **Activity log**, and **About & support**. Sections appear only under their existing capabilities: license administration, `backups`/`database_restore`, `administer`, `recovery`, and `technical`, respectively. Backup/restore uses the portable authority closure; Integrity & recovery exposes only the frozen guarded P11 commands. Activity log is operational logging, not Encounter history. None of these sections owns graph truth. See `AGENT_HANDOFF.md` and P11/P12/P14 documents before touching release or recovery behavior.

## Terms that prevent mistaken authority

| Term | Meaning and boundary |
| --- | --- |
| Person / canonical Person | Stable raw identity / effective merged survivor. Merge retains raw history. |
| Encounter / Sighting | Finalized observation / one effective participant in it. Media count is not Encounter recurrence. |
| `EVENT_NOTE` / `SIGHTING_NOTE` / `PERSON_NOTE` | Encounter context / Person in one Encounter / general editable Person information. All support selected-ID mentions, but only Person-owned Sighting/Person Notes produce Person→Person `NOTE_REFERENCE`. |
| `CO_OBSERVED` / `NOTE_REFERENCE` / `MANUAL_ASSOCIATION` | Distinct co-presence / selected Person-owned note reference / explicit standing association evidence. Coexistence does not create extra Encounters. |
| `GOOD` / `POOR_ACCEPTED` / `PROOF_ONLY` | Embedding search eligibility, independent of face origin and Person biometric state. Proof-only is never an ordinary recognition reference. |
| `NO_FACE` / `ENROLLED` | Person has zero / at least one stored face, regardless of eligibility. |
| Recognition / proof-only duplicate check | Ordinary candidate proposal / exceptional pre-creation hint for profiles with only proof-only faces. Neither is identity authority. |
| Recurrence / Activity / Cluster | Distinct independent Encounter support / recent ongoing behavior / derived group of evidence-connected people. Current World does not implement the locked future recurrence tiers. |
| Add Face / Review photos | Standalone biometric enrollment of an existing Person / staged multi-photo Encounter review. Add Face creates no Event; Review photos can finalize one. |
| Archive / Delete / Merge | Inactive but restorable identity / tombstoned historical identity / canonical survivor with source history retained. None physically erases old Encounter evidence. |
| Person Graph / World | Identity-centered / scoped intelligence projections of the same evidence graph. Neither owns relationship authority. |
| Face origin / recognition eligibility | How an embedding entered history / whether it may influence matching. They are separate, even after Move Face or merge. |

Every implementation batch must update this map and all affected canonical docs before claiming completion. Planned features must be labelled as planned, and frozen phase records remain historical acceptance evidence.
