# SentriFace global identity domain model

## Issue #3 — additive World intelligence contract

This extension uses the existing `/api/world-graph?version=2`, `WorldGraphRequest`,
`IdentityStore`, `GraphReadService`, and `FaceEngine` boundaries. It adds no schema,
World authority, graph store, background job, dependency, or frontend change.
Current World remains the default (`view=CURRENT`): all evidence types when no
selector is supplied, effective minimum strength 1. Existing controls and reads
remain valid. Issue #13 owns the optional graphical Explore interface.

Explore sends `view=EXPLORE`, a nonempty `evidence_type` list drawn independently
from `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION`, and a positive integer
`min_relationship_strength` (2 when omitted). Its initial UI request must explicitly
select `CO_OBSERVED`. An empty/blank selection rejects rather than meaning all types.
Example: `version=2&view=EXPLORE&evidence_type=CO_OBSERVED&min_relationship_strength=2&collection=RELATIONSHIPS&include_below_threshold=true`.

Strength sums selected active, scoped evidence records per corrected, canonical,
unordered pair. Connected components still require two or more people and only
qualifying direct edges; a qualifying bridge joins components. There is no inferred
edge between two indirectly connected members. `include_below_threshold=true`
adds real selected-evidence relationships to bounded relationship pages, marked by
`qualifies_for_cluster=false`; they never enter membership or ranking degree.
`selected_evidence_strength`, `evidence_type_counts`, `direction_counts`, and
`note_reference_direction_counts` preserve the selected count and directed provenance.
The weaker-edge display toggle does not alter cluster identity.

`encounter_recurrence` is independent of mixed strength and of the evidence checkboxes:
one distinct finalized Encounter/canonical unordered pair, using active scoped
co-observation evidence. A note/manual-only relationship can thus report actual
Encounter recurrence without counting those notes/assertions as Encounters. It
returns count, first/latest occurrence, bounded supporting Encounter IDs/dates/
locations and truncation state. Previews use `event_limit` (default 25, maximum
100). Further proof uses the existing relationship EVIDENCE collection with
`evidence_type=CO_OBSERVED` and the same date/location scope, revision and `as_of`.
Explore EVIDENCE/EVENT evidence pages additionally return the current exact
`encounter_support` (`SHARED_FRAME` or `SAME_ENCOUNTER_ONLY`) from existing effective
face/media authority. Raw endpoints, source/revision/operation IDs, and retired
source history remain intact. Event Note mentions and Reference Only media never
contribute presence or pair evidence. Strength and recurrence are descriptive
counts, never identity confidence, probability, risk or inferred intent.

Four additional WORLD_SCOPE collections share authorization, hard caps and cursor
validation. `discoveries` contains canonical Person references, counts and bounded
supporting Encounter references; `discovery_context` specifies measurement/time.

| Collection | Meaning / request |
| --- | --- |
| `MOST_FREQUENTLY_SEEN` | Distinct finalized Person–Encounter appearances in a rolling 7/30/90-day window ending at `as_of`; `discovery_period_days` defaults to 30. Inclusive endpoints, highest count first, canonical Person ID tie-break. |
| `MOST_RECENTLY_SEEN` | Every distinct Person in all finalized Encounters on the latest observed UTC calendar day in effective scope, even if that day was several days ago; the actual day is returned, or null with an empty result. |
| `MULTIPLE_LOCATIONS` | At least two distinct known recorded location names over the preceding 30 days. Counts/names compare Unicode casefolded text after whitespace collapse; Delhi and New Delhi remain distinct. Unknown/blank values do not count, and missing-location Encounter counts are separate. |
| `LOCATION_SUGGESTIONS` | `location_query` starts matching after three normalized typed characters (length checked before Unicode case folding). Case-insensitive normalized substring search over effective successfully finalized Encounter locations, deterministic normalized-name order. Suggestions are in `available_facets.locations`; `facet_limit` and the collection cursor page all matches. |

Discovery windows intersect the requested World dates/locations; Person filters and
activity eligibility use the existing effective scope. Presence ignores relationship
checkboxes/thresholds because those cannot change whether a Person appeared.
Discovery results use `people_limit` (25/default, 100/max); each support preview uses
`event_limit` and each location-name preview `facet_limit` (100/default, 200/max).
Exact totals and truncation are explicit. To continue supporting records use bounded
PERSON/EVENTS with the returned discovery date bounds (and the latest day as both
date bounds for most-recent), original scope, revision and `as_of`. To focus a result,
use its canonical ID in PERSON with the original clustering criteria, revision and
`as_of`; its existing `cluster_memberships` identify the authoritative clusters.
Discoveries do not define another cluster model. All top-level discovery pages have
revision-bound cursors; view, weaker-edge flag, period, query, limits and ordinary
scope participate in cursor validation.

Location suggestions intentionally read the full saved effective Encounter location
source independently of investigative Person/time filters. Draft/cancelled/failed
writes register nothing. A successful correction replaces the effective suggestion
value, while immutable original metadata remains historical. There is no separate
location registry and no normalization write-back to free text.

World calculation remains synchronous inside one revision-bound SQLite read
snapshot. SQLite aggregation has no known total work denominator, and the response
cannot publish intermediate updates before it completes. A truthful cancellable
percentage therefore cannot be added safely within this request contract without
an independently designed transport/job lifecycle. Issue #13 must use an honest
indeterminate loading state; no percentage or background-job system is introduced.

Retired co-observation generations may name a formerly corrected participant who
was later removed. Immutable Encounter/face correction targets prove that historical
endpoint in graph validation; current active evidence still undergoes current
participant validation. No evidence or journal history is edited for World reads.

## Reference Only biometric source contract (Batch 3.7)

An embedding is a sample, not a Person identity. Independently inferred unequal vectors remain independent samples; the same Person never causes vector borrowing. Equal serialized vectors may deduplicate, while source assignments remain independent: Reference R→Alice and Encounter F→Alice can share E; correcting F→Bob leaves R→Alice. E is excluded from ordinary recognition while active canonical source owners disagree. Resolving the assignment, retiring R or canonical merging the identities naturally recomputes eligibility. R remains active/countable until explicitly retired.

Reference Only requires a known active canonical Person, a cropped single-person image, exactly one detected face and explicit acknowledgment that no reliable Encounter context exists. Zero/multiple faces reject with cleanup and no queue promotion. Existing GOOD/POOR_ACCEPTED/PROOF_ONLY rules apply. NO_FACE Add Face and ENROLLED management are identical domain mutations. Reference material has no occurrence/date/location, participant, sighting, recurrence, note evidence, graph or World meaning.

Four active Reference source assignments per canonical Person limit exceptional contextless material. PROOF_ONLY counts, Encounter samples and retired sources do not. Count sources, not embedding rows. Exact same media is one effective source; an already-active exact Reference vector for the same Person adds no new biometric value and no slot. Similar vectors are not duplicates. Exact media assigned to another canonical Person and an active exact Reference vector owned by another canonical Person reject admission rather than transferring identity. Exact Reference media cannot enter an Encounter and exact Encounter media cannot become a new Reference; no perceptual crop-parent inference is performed.

Retire is not delete: append a lifecycle revision, retain source/quality/media/journal history and remove active recognition contribution. Restore reactivates that same source after cap/lifecycle/permission validation. Person archive/delete suppress recognition without retiring sources; Person Restore re-enables otherwise eligible sources. Merged source mutation is rejected. Merge evaluates unique effective active sources and blocks above four with an instruction to consolidate first; it never chooses best-four or destroys history. Legacy over-cap backup/restore reproduces truth and prevents further admission until consolidated.

NO_FACE/ENROLLED derives from usable eligible samples. Proof-only or conflicting References can coexist with NO_FACE; Encounter-derived samples can preserve ENROLLED after all References retire. Restore preserves source truth and recomputes the conflict rather than serializing a mutable conflict state.

## Batch 3.6 provenance and standing-assertion contracts

An observation media identifier must be nonempty and supported by an independent durable registry-owned source reference (enrollment/crop, recognition, pending/init, or retained review/session media). Its own observation membership is not provenance proof. All photographs retained by a completed review are source authority, including supporting images without a new embedding. Reused embeddings retain enrollment provenance; immutable accepted-face decision JSON binds actual occurrence media by ID to that face's observation. Participant/identity corrections and canonical merges interpret identity without rewriting those historical image facts. P11 validates database provenance/bindings; existing backup verification additionally requires complete registered file closure, safe bindings/paths, byte identity and protected-file authentication. Restore relocates only registry-owned physical paths on its disposable candidate; live completed decisions remain immutable.

Manual Association is one standing assertion per effective canonical unordered pair. Separate pre-merge raw assertions remain distinct history. When a merge collapses them, the existing transaction retires redundant assertions under the merge operation, retaining the oldest by `(created_at, evidence_id)`; canonical self-assertions are retired too. Endpoints, metadata and original creation records are never rewritten/deleted. Retiring the survivor removes this standing support only; independent CO_OBSERVED and NOTE_REFERENCE may remain.

Recognition proposals describe model inference. Accepted existing Person ID or staged new Person name comes from the saved operator decision, and that same record supplies the accepted display after mutation/refresh/resume. SKIP remains deferred. A new staged Person has no committed Person ID until finalization; its profile action remains unavailable until then.


## Batch 3.5 canonical coherence

For a finalized effective Encounter, current canonical pair support is derived from effective accepted face assignments and valid Encounter media. `SHARED_FRAME` means the two canonical participants share at least one Encounter frame; otherwise their support is `SAME_ENCOUNTER_ONLY`. `_encounter_pair_support` owns this finalized interpretation, using the same frame-set intersection as draft candidates. Raw decision-row order never selects factual support. Initial finalization, alias collapse, participant/identity correction and Relations correction use this calculation; effective Encounter reads derive it directly, including after restart or graph rebuild.

Historical Relation/evidence generations retain provenance. Current relationship reads use active evidence, canonical resolution and effective participants; superseded evidence is available only through explicit history/provenance reads. Graph rebuild derives the projection from that current authority and does not resurrect EXCLUDE or retire history to reduce row count. Stored support snapshots describe their generation; they do not override current frame facts.

Face decisions are distinct: unresolved (`null`), deferred (`SKIP`), accepted-existing, accepted-new, and final negative (`EXCLUDE`). Only the two accepted decisions contribute participants. EXCLUDE resolves an item without participation; SKIP stays unresolved, is reviewable again, and cannot permit final completion or Relations progression. Recognition proposals and explicit enrollment targets are separate contracts. Standalone Add Face enters the shared Reference Only command: a cropped upload must contain exactly one detected face, and the operator must acknowledge unavailable Encounter context. Additional detections reject the upload rather than offering a face picker. No Encounter is created.

Archived People cards permit authorized historical profile navigation via `VIEW_HISTORY`. Restore remains a backend lifecycle/capability command; an archived Person is not active merely because its history is open. Deleted/merged cards and restricted graph nodes retain their separate navigation semantics. “Associated people” counts distinct effective counterpart Persons; separate evidence/direction rows retain their own breakdown.

Linux recovery-code custody is an explicit unpackaged source-ONNX extension, using an authority-bound owner-only AES-GCM file under the source root and the existing storage master key. It shares the source key eligibility checks (Linux, explicit intent, Git checkout, not frozen/compiled, isolated non-production authority). Missing configured, corrupt, wrong-authority or unsafe custody fails closed. Normal macOS/Windows and packaged/hardened recovery remain OS-vault based. A verified recovery kit may install its validated master key into a fresh eligible source root; backup key identity/encryption checks are unchanged.

Canonical pair reads reuse frame sets only within one Encounter read snapshot, never as persisted authority or a cross-mutation cache. Dense histories retain current pair/recurrence meaning even when retired evidence generations greatly outnumber active rows.

Completed review decisions remain immutable in live authority. Portable restore may relocate registry-owned physical media paths on a disposable candidate; all non-path fields and the original guard must survive unchanged before commit. Stored correction/history IDs and content are preserved, while read revision/cursor tokens and physical locations are not portable identity.

A staged standalone enrollment can retry completion using its existing operation ID after a lost response. Accepted/excluded face decisions remain the durable input; retry does not generate another enrollment authority.

## Finalized Encounter amendment authority (Batch 3)

An amendment retains the original `observation_id` and finalization time. `photo_reviews.target_observation_id` and `expected_encounter_revision` bind an existing durable review to that authority; no new observation is created at completion. Media references attach once; accepted faces add immutable assignment/embedding/note history. Finalization saves the server-derived `encounter_media_id` in the existing immutable face-decision metadata. This binds each face to its actual occurrence media even when an existing embedding is reused; embedding source ownership is not changed. Older decisions without that field retain the proven enrollment-image fallback. Accepting a previously removed participant appends PRESENT and requires the affected pair decisions again. Finalization saves the server-derived `encounter_media_id` in the existing immutable face-decision metadata. This binds each face to its actual occurrence media even when an existing embedding is reused; embedding source ownership is not changed. Older decisions without that field retain the proven enrollment-image fallback. Accepting a previously removed participant appends PRESENT and requires the affected pair decisions again. Previously settled canonical pairs retain their dispositions. Every newly introduced pair requires an explicit INCLUDE/EXCLUDE decision. Additional shared frames may improve support to SHARED_FRAME but do not add independent recurrence. Zero-face or all-excluded media may extend a finalized Encounter without inventing participants.

`encounter_metadata_revisions` stores corrected observed time, location and context append-only. `effective_observations` overlays the latest revision while original observation metadata remains immutable. Event-selected IDs are corrected with that metadata and remain Encounter→Person mentions. `encounter_participant_revisions` records PRESENT/REMOVED interpretation append-only, independent of physical face ownership. Removal snapshots the current raw canonical component as revision rows; later merges must not erase participation supplied by another raw identity. Reassignment also uses the established face/observation/ownership correction records. A correction cannot remove the last effective participant.

Relations changes retire superseded decisions and append revisions. Only current included canonical pairs generate CO_OBSERVED; retired originals retain provenance. A merge with contradictory pair dispositions refuses and identifies the Encounter requiring correction. After explicit resolution, merge collapses redundant equal pairs and retires self-pairs while retaining their history. Rebuild reproduces the same effective evidence/projection. Independent note and manual evidence is unaffected.

Distinct requests for the same undirected active canonical Manual Association reuse its evidence ID and journal a committed no-op. Retiring and deliberately re-adding it creates a new assertion with the earlier one retained. Exact committed retries return the original result even after endpoint merges. Distinct requests for the same undirected active canonical Manual Association reuse its evidence ID and journal a committed no-op. Retiring and deliberately re-adding it creates a new assertion with the earlier one retained. Exact committed retries return the original result even after endpoint merges. Manual Association commands create active normalized MANUAL_ASSERTION evidence (projected as MANUAL_ASSOCIATION) between distinct active canonical people. Retirement affects exactly that assertion, preserving other manual assertions, CO_OBSERVED and NOTE_REFERENCE. Each command and amendment/correction commits its operation journal with authority and graph in one transaction; retries return the committed result before checking a now-stale revision.


## Architectural rule

SentriFace owns one global identity graph. **Person Graph** is an identity-centred projection and **World** is a spatial/temporal projection of the same authoritative records and relationship evidence. They are not separate graphs or stores.

Recognition output is non-authoritative proposal data. Only explicit operator finalisation may create or change persons, observations/events, accepted participants, notes/mentions, relationship evidence, corrections, or merge state. A multi-person review becomes authoritative only after every detected face has a final decision and the review is explicitly completed in one transaction.

## Current authoritative model

### Person and canonical identity

`Person` is a stable historical identity node with one explicit lifecycle state: `ACTIVE`, `ARCHIVED`, `DELETED`, or `MERGED`. Archived and deleted nodes remain in graph history; graph projections render them inactive/non-clickable. The Archived People collection separately permits authorized historical profile navigation and Restore. A merged source also remains historically addressable.

Raw identity is the person ID stored on the authoritative historical record. Effective identity is that raw ID resolved through the explicit, transitive canonical mapping. A merged source resolves to one active canonical survivor. Current-view reads may group by effective identity, but they do not rewrite the raw owner or participant ID.

Canonical resolution is explicit and transitive. Merge records preserve source, target, actor, time, reason, and affected-record provenance. Merges never delete source history or rewrite away the identity under which evidence was originally recorded.

### Observation/Event

`Observation` (or Event) is the immutable event-history and preferred co-occurrence unit after finalisation. It holds event time/place/context and may reference multiple existing photos without duplicating their media storage. Raw participants retain the originally accepted person IDs. Effective participant reads apply correction history and then canonical resolution, without rewriting the raw participant rows.

Batch 2 stages one Encounter review at a time on the existing photo-review authority. Grouped media, shared Event metadata, Person decisions, Sighting Notes and Relations choices are durable drafts and have no graph authority before explicit Complete Review. Pending Encounters in the same upload wait; completing one activates and re-scores the next. The final transaction is still `review.complete`. A finalized Encounter owns its shared date, time range/precision, location, occasion, context, Event Note, selected Event Note IDs, media, participants and creation provenance once. Exact duplicate retained media cannot create another finalized Encounter merely through reimport.

In the post-Batch-2 Queue stabilization, an uploaded photo already attached to a finalized Encounter is identified individually before grouping and automatically excluded from the new plan. Other photos may continue. Operator media exclusion is durable selection on existing `init_session_media.excluded` (schema v31); restore is allowed before grouping, and selection is locked afterward. Neither action deletes historical or physical media. The Encounter partition is confirmed before identity grouping; optional folder-based suggestions are draft allocations only. Existing `init_groups.status = skipped` means a temporary ordering defer, while a final face `EXCLUDE` means intentional nonparticipation. Skipped faces remain unresolved, return when other pending groups are exhausted, and cannot advance to Relations. The existing scan face boxes mark the current source-photo face. No new Encounter or media authority is created by these review controls.

Active Encounter recognition treats committed embeddings and accepted faces in that active draft as one transient reference view, grouped by canonical Person or draft-created key. The quality preference applies to the combined set: ON uses GOOD when present, otherwise POOR_ACCEPTED fallback; OFF uses GOOD plus POOR_ACCEPTED. PROOF_ONLY never participates in ordinary matching. The existing exceptional pre-creation duplicate check uses the same ownership boundary to compare only otherwise unsearchable proof-only-only Persons, including draft-created Persons. Use Existing reuses the canonical Person or the same draft key; Create Anyway is explicit and retained in decision provenance. `Drafted` identifies a Person created in this draft; an existing Person with accepted draft faces is still an existing Person. Draft vectors never enter the global index or committed history. Final completion retains its existing transaction/journal boundary.

The 2026-09-27 Encounter foundation uses this same `Observation` authority. Review completion resolves one shared `observed_at` (date and optional start time), `location`, and `context` (`occasion`, optional end time, exact/approximate/unknown time precision, ordinary/public/unknown category, Event Notes, selected Event Note person IDs, and creation label) from accepted face decisions. Conflicting face-level event fields refuse finalization atomically. The normalized observation is authoritative; compatibility `recognition_details` mirrors its date/time/place/occasion. Older observations with empty fields remain unknown/legacy. The current UI confirms these shared fields once in an Event modal before Person resolution and shows them read-only in Person/Sighting forms; Batch 2 adds serial operator-confirmed grouping before Queue identity review.

Within one event, a canonical person appears at most once as a participant. Repeated recognition across photos or faces must not create duplicate participants or self-links. Rejected/ignored/unknown decisions remain review history but do not become accepted participants.

### Notes and mentions

Person-owned Notes are revisioned authoritative records. Their mentions are explicit saved occurrences referencing person IDs; display-name parsing alone is not authoritative. A selected mention in a committed Person or Sighting Note becomes directed Person→Person `NOTE_REFERENCE` evidence. Editing/removing that mention retires only its originating evidence. Event Notes are Encounter-owned and follow the distinct rule below.

Person Notes describe a person generally, live in Person Profile, and remain editable. New- and existing-person Sighting Notes linked to `RECOGNITION_DETAIL` describe that person's particular Encounter and are finalized history; their selected mentions produce sighted Person→mentioned Person `NOTE_REFERENCE`. Event Notes and explicitly selected IDs live once in finalized observation context. An `EVENT_NOTE` selected ID is an Encounter→Person structured mention, searchable in Events and Person history; it creates no `relationship_evidence`, `NOTE_REFERENCE`, participation, or `CO_OBSERVED`, and has no World/cluster/recurrence effect. Its lack of a source Person must not be filled by an arbitrary participant. Literal `@Name` without selection is inert in all three scopes. `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` remain distinct. The legacy person-note fallback remains only for review decisions with no recognition detail.

An ACTIVE identified Person with no face has `biometric_status=NO_FACE` and can own notes or be explicitly selected. Add Face uses `identity.face.add` and creates no Encounter. Each embedding has `recognition_state`: `GOOD` (quality passed for new rows), `POOR_ACCEPTED` (poor quality explicitly accepted), or `PROOF_ONLY` (historical face excluded from ordinary matching). Legacy rows migrate to `GOOD` to preserve prior search eligibility, without reconstructing old assessments. This state differs from Person biometric status: `ENROLLED` requires an ordinary-recognition-eligible sample under current source ownership, quality and lifecycle; proof-only, retired or conflicting samples alone leave `NO_FACE`. Face origin is another independent dimension, read from observation face assignments (`ENCOUNTER`) or standalone enrollment history (`STANDALONE_ENROLLMENT`), otherwise `UNKNOWN_LEGACY`. The default **Prefer quality photos for recognition** policy uses GOOD where present; switching it off also permits POOR_ACCEPTED. If a Person has no GOOD but explicitly accepted poor samples, POOR_ACCEPTED is fallback under either setting. PROOF_ONLY never joins normal ranking, but may enter a separate pre-new-Person duplicate check; a result remains a proposal. The preference controls stored candidates only, not input classification or historical storage.

### Relationship assertions, evidence, and projection

For Batch 2 finalized Encounter reviews, `encounter_relation_decisions` records every effective participant pair as `INCLUDE` or `EXCLUDE`, plus `SHARED_FRAME` or `SAME_ENCOUNTER_ONLY` support. It is the minimal negative decision authority: absence of `CO_OBSERVED` could otherwise mean undecided, excluded, or not yet committed. Only an included pair contributes one active `CO_OBSERVED` evidence occurrence from that Encounter. Excluded people remain participants. Corrections append/retire decision revisions and rebuild only included evidence; ambiguous merge pair collapse is refused. Legacy observations without relation decisions retain their historical all-participant-pair interpretation. Distinct `(Encounter ID, effective canonical pair)` remains the future recurrence unit; current World scoring is unchanged.

A manual relationship assertion is an authoritative record, not an edge owned by a UI component. Relationship evidence has a stable ID, type, endpoints, provenance source, actor/time, and active/retired state. Required evidence types are:

- `CO_OBSERVED`: derived from accepted participants in one completed event.
- `NOTE_REFERENCE`: derived from a saved Person-owned Person/Sighting Note revision and exact mention occurrence.
- `MANUAL_ASSOCIATION`: an operator-created association.

A projected relationship exists while at least one active evidence record supports the canonical pair. Evidence is authoritative; `graph_connections` and graph API results are derived projections. Evidence types never overwrite each other. The projection can be cached, but must be fully rebuildable from authoritative persons, events/participants, note revisions/mentions, manual assertions, corrections, and merge history.

**Locked future recurrence direction, not current World scoring:** one finalized Encounter contributes at most one independent `CO_OBSERVED` occurrence for an effective canonical Person pair, regardless of media/frame count. After merge, count distinct `(Encounter ID, canonical pair)` while retaining raw evidence. A shared-frame Encounter and a same-Encounter/no-shared-frame Encounter are different supporting explanations; their counts sum to independent Encounters. Public/group context explains evidence but does not silently multiply or discount it. Recurrence, recent activity, evidence type, and group-forming support are separate measures. `NOTE_REFERENCE` or `MANUAL_ASSOCIATION` may coexist for the pair but never increments independent Encounter count. No recurrence tiers, activity tiers, or bridge thresholds are implemented in this batch.

The Person Graph hover summary counts distinct finalized observation IDs for active canonical-pair `CO_OBSERVED` evidence and reports the latest such occurrence. It also reports active evidence type counts and canonical source→target direction counts for `NOTE_REFERENCE`. This is a read-only explanation of existing evidence; the underlying rows, graph projection, World scoring, and future recurrence policy are unchanged. A selected Event Note mention has no Person→Person edge and cannot inflate these counts.

### Corrections and operation journal

Identity corrections (Move Face, Add Face, and effective participant changes) are first-class historical operations. Original review decisions, raw participants, face assignments, and prior evidence revisions remain preserved; corrections append provenance and rebuild only the affected current projections. Every important write has an immutable operation-journal entry with operation/idempotency ID, type, actor, timestamp, affected entities, before/after or inverse data, and status. A graph-affecting write and its journal entry commit in the same SQLite transaction.

Embedding enrollment ownership is raw provenance. Move Face appends ownership corrections rather than rewriting that original owner. The latest ownership correction, followed by terminal canonical resolution, determines effective embedding ownership for recognition, browse ranking, representative-photo selection, deletion, restoration, and subsequent moves.

### Merge foundation and orchestration

P8-A provides the merge infrastructure. A normalized merge manifest links one source identity and its terminal active canonical survivor to the operation journal. Immutable affected-item records describe what is preserved, reinterpreted under canonical ownership, unioned in the current view, or selected. Typed conflict records retain source and target values, the chosen strategy (`KEEP_SOURCE`, `KEEP_TARGET`, `COMBINE`, or `USER_SELECTED`), the selected value, and inverse data.

P8-B adds a read-only preview and one normalized execution command through the backend service boundary. Canonical survivor rules reject self-maps, missing targets, cycles, deleted identities, and inactive survivors. Execution applies explicit conflict strategies, writes the manifest and canonical mapping, rebuilds and validates the graph projection, publishes canonical index ownership, and commits the journal atomically. Raw ownership and provenance remain unchanged while effective reads resolve to the survivor. P11 permits only the documented guarded merge-revert subset; a merge that revises Encounter Relations is outside that subset.

### P9 intelligence and sightings read models

A current `Sighting` is a derived `(finalized observation, effective canonical person)` pair. It is not a stored identity record and does not own a face, embedding, or recognition-detail row. Repeated accepted faces for one effective person within the same observation collapse to one sighting. Draft observations and recognition proposals never appear. Raw accepted participant IDs, media membership, correction operation IDs, original timestamps, location/context, and source remain attached as provenance while the current person is resolved through corrections and terminal canonical identity.

`PresenceAnalytics` derives observation count, first/last seen, monthly counts, observed locations, and a descriptive 30-day frequency from those sightings. Frequency is appearances divided by the observed span in 30-day units (with a one-unit minimum); its labels are descriptive buckets, not probabilities. A photo or embedding deletion does not remove an authoritative finalized observation, an identity correction moves the effective current sighting while preserving the raw participant, and a merge unions source history under the canonical survivor.

`RelationshipAnalytics` reads active `relationship_evidence` directly and resolves endpoints canonically. It reports evidence counts by type, co-observation count, first/last evidence time, directionality, raw evidence provenance, and an evidence-count strength basis. It does not assign a probabilistic confidence or mutate `graph_connections`. Profile intelligence combines lifecycle/canonical state, current embedding count, the presence read model, evidence-derived relationships, and canonical operation-journal activity. A confidence summary explicitly reports that no probabilistic identity confidence is available from normalized authoritative records.

These models are calculated by the backend read boundary and returned by the API. They introduce no new authoritative table or cache. No-face identities participate normally because sightings, notes, activity, and relationship evidence do not require an embedding.

### P10-A graph intelligence read models

`PersonGraphReadModel` and `WorldGraphReadModel` are UI-ready backend projections over the same active authoritative `relationship_evidence`, canonical person mapping, finalized observations, corrected effective participants, and P9 intelligence reads. They never read `person_associations`, never expose raw evidence rows, and do not make layout decisions.

Both contracts collapse merged aliases into the terminal canonical node. A canonical node includes display, lifecycle and biometric state, representative media reference, backend-owned allowed actions, a current/historical indicator, merged historical IDs, and normalized summary intelligence. Archived and deleted terminal identities remain historical nodes. A request made with a merged source ID reports that requested historical state while rooting the Person Graph at its canonical survivor.

Edges aggregate active evidence by canonical person pair. Self-edges created by canonical collapse are suppressed. Strength is the count of active authoritative evidence items after the requested evidence scope is applied; it is descriptive, not probabilistic. The read model supplies evidence types, relationship-type summary, first/last occurrence, directionality, canonical endpoints, and aggregate provenance counts without returning raw `relationship_evidence` records or compatibility identifiers. For co-observation evidence, occurrence time and location come from the finalized observation; note-reference and manual evidence use their committed evidence time and have no location.

`GraphReadFilter` expresses frontend intent. Date bounds are inclusive and apply to occurrence time. A location filter is an exact case-insensitive match and necessarily limits relationship evidence to co-observations with that location. Lifecycle, country, rank, and priority filter canonical nodes; minimum frequency uses the P9 whole-history descriptive frequency; minimum relationship strength applies after evidence scoping. Person Graph always retains its canonical root, while filters govern connected nodes and edges. World temporal/location scopes retain canonically resolved participants in matching finalized observations plus endpoints of matching evidence. No frontend reconstruction or filtering is authoritative.

`graph_state` holds one local monotonic revision counter, exposed as an opaque `g<number>` token. Graph projection replacement advances it in the same SQLite transaction as finalisation, correction, merge, evidence creation/retirement, or rebuild. Person read-field changes also advance it through local SQLite triggers. Retries that return an already committed operation do not advance it. The token is invalidation metadata rather than distributed versioning and does not identify a particular evidence record.

### P10-B Person Graph UI projection

The People profile opens a dedicated Person Graph workspace backed only by `/api/person-graph`. React renders the returned nodes and edges, maps the returned relationship strength to line weight, and presents the returned evidence and provenance summaries. Its radial multi-ring placement uses only the backend node collection and root ID; it does not inspect edges to decide membership, depth, relationship existence, canonical identity, lifecycle, or strength.

Node navigation consumes `allowed_actions` exactly as supplied by the backend. Restricted historical nodes remain visible and explain that backend access is restricted. The UI retains only ephemeral camera, hover, and selection state.

Graph revision is an opaque consistency token. In the current offline single-user model, the UI validates it at lifecycle boundaries and after known graph mutations. Continuous polling is intentionally avoided. The initial graph read stores its revision. Leaving the workspace retains that immutable read model; returning validates the token once and reuses the model when unchanged. Successful graph-affecting writes invalidate the retained model, and a changed or invalidated model is replaced by a complete `/api/person-graph` response rather than patched locally. Manual refresh also requests a complete replacement.

### P10-C World product model

World is the backend-owned intelligence projection of the entire identity environment. It answers: “What is happening in this scope, which entities matter, what measured patterns exist, and which authoritative evidence explains them?” It is not a zoomed-out Person Graph, an inferred social network, a geographic map, or a second graph. Person Graph starts from one identity and explains its neighbourhood; World starts from an operator-selected scope and progressively summarizes people, finalized events, evidence-derived relationships, and descriptive change over time.

### P10-D World Intelligence read-model architecture

#### Entity and object taxonomy

World distinguishes authoritative domain entities from derived read objects and supporting provenance:

- A `PERSON` is the terminal canonical projection of an authoritative `Person`. The World object includes canonical and historical IDs, display data, lifecycle, identity and biometric states, allowed actions, explicit operator priority, descriptive activity, relationship summary, and backend-supplied salience reasons. Active, archived, and deleted identities remain representable. Merged sources remain historical provenance but collapse into the survivor in current topology.
- An `EVENT` is an authoritative finalized `Observation`. It deserves first-class World detail because it records what happened, when and where, which accepted effective canonical people participated, which media belongs to it, and which corrections affect its current interpretation. Draft observations and recognition proposals never appear. Events are returned only for focused drill-down, not as peers of people in the initial relationship view.
- A `CLUSTER` is a derived, temporary read-model summary, never an organization, identity, assertion, or durable graph node. It is created only by a documented deterministic grouping algorithm over the scoped evidence-derived person graph. The baseline strategy may use qualifying connected person relationships; any stronger community strategy must be explicitly named, versioned, deterministic, and tested. Location or temporal similarity alone cannot create a relationship or cluster membership. A cluster has at least two members, is bound to the graph revision, effective filters, algorithm/version, parameters, and member set, and receives a revision-bound opaque ID. Its explanation identifies the member relationships and evidence aggregates that caused membership. Singleton results remain people, not one-member clusters.
- A `PATTERN` is a derived explanatory intelligence object attached to a person, relationship, cluster, event set, or World scope. It is not topology and never becomes a graph node or evidence record. Its calculation, comparison window, thresholds, subjects, supporting counts, and limitations are part of the read contract.

The allowed relationships are `PERSON_RELATIONSHIP`, derived from active authoritative relationship evidence; `PARTICIPATED_IN`, derived from accepted effective participants of a finalized event; and `AGGREGATED_RELATIONSHIP`, a Level 0–1 count of scoped person-pair relationships/evidence crossing two summaries. An aggregate edge does not claim that every member is related, and cluster membership is expansion metadata rather than relationship evidence. `CLUSTER` to `CLUSTER` is therefore allowed only as aggregate read-model output. `EVENT` to `EVENT` is excluded: time, location, shared participants, or similar context can support a descriptive pattern, but not an event edge, until a future authoritative event-link model exists.

Evidence items, photos/media, notes and mention occurrences, sightings, face detections, embeddings, recognition scores/proposals, locations, time buckets, journal entries, and pattern cards must never become World graph nodes under the current domain model. Evidence and media are Level 4 provenance. Locations remain metadata and facets because the current value is free text; a normalized place identity and hierarchy would be required before a location could become an entity.

`NO_FACE` is a biometric state, not an unknown identity. `UNIDENTIFIED` is an identity state on an explicitly created person and must be separate from lifecycle and biometric state. An unresolved, rejected, skipped, or finalized-unknown face decision is not identity and cannot become a participant, sighting, node, endpoint, or cluster member. Repeated-unknown similarity remains proposal data. An unknown becomes a person only through explicit operator-finalized creation or resolution with preserved observation and decision provenance. Future repeated-unknown tracking requires its own authoritative, reviewable lifecycle and journaled resolution model; until then World may report aggregate finalized unknown/non-participant decision counts outside graph topology, but never draft or unresolved review state.

#### Detail levels

The five levels are sufficient and intentionally separate entity context from proof. They are semantic request levels, not client zoom thresholds, and a focused request may move directly to the required level:

- **Level 0 — `WORLD_SCOPE`:** scope totals, effective and available facets, time coverage, bounded top people and cluster summaries, bounded pattern teasers, finalized non-participant decision/data-quality counts, and truncation metadata. Draft and unresolved review state is excluded, and the level contains no unbounded topology.
- **Level 1 — `CLUSTER`:** one cluster’s definition, algorithm/version, revision-bound identity, member count, bounded ranked member previews, aggregate links to other clusters/summaries, activity summary, patterns, and membership explanation. It must distinguish explicit priority from computed descriptive salience.
- **Level 2 — `PERSON`:** one canonical person’s identity/lifecycle/biometric state, activity and relationship summaries, bounded scoped neighbours, evidence-derived person edges, relevant cluster memberships for this exact response, patterns, and “why important” factors. This level reuses Person Graph truth but not its root-neighbourhood or layout assumptions.
- **Level 3 — `EVENT`:** one finalized observation’s time, location, source/context, accepted raw and effective/canonical participant references, media summary, correction summary, and links back to the people/relationships it supports. No draft or proposal state is promoted.
- **Level 4 — `EVIDENCE`:** bounded supporting provenance for a selected relationship, pattern, person claim, cluster explanation, or event. It contains typed evidence summaries, source references, occurrence bounds, counts, relevant finalized event/media references, saved note/mention references, manual assertion provenance, correction/merge references, and retirement/current-state information. Evidence is presented as proof, not as topology.

#### Intelligence and pattern model

World intelligence is deterministic descriptive analysis over authoritative normalized records. Useful initial pattern types are:

- `ACTIVITY_CHANGE`: a person’s or cluster’s finalized-event count/rate in a declared current window compared with a declared preceding or historical baseline.
- `RELATIONSHIP_CHANGE`: scoped evidence or co-observation activity for one canonical person pair compared with the same declared baseline.
- `EMERGING_CLUSTER`: a revision-bound set of people whose qualifying evidence-derived connections newly meet a documented grouping/change threshold relative to a baseline window.
- `RECURRING_CONTEXT`: repeated finalized participation by the same person or canonical pair at the same non-missing normalized location facet and/or documented time bucket.
- `DATA_QUALITY`: missing location, sparse baseline, finalized non-participant decision totals, or other factual limitations that materially affect interpretation.

The backend may emit a pattern only when all contributing observations are finalized, participants are accepted and canonically resolved, relevant evidence is active, the current and comparison windows are explicit, a versioned calculation and threshold policy is named, minimum sample/coverage rules pass, and bounded supporting references are available. Each pattern reports metric values, units, window and baseline, absolute and relative change where defined, subject IDs, first/last occurrence, evidence counts/types, calculation version, and an explanation. “Significant”, “emerging”, “unusual”, and activity buckets are deterministic threshold labels, not statistical or model confidence, unless a future reviewed statistical contract defines them.

World must not infer intent, affiliation, organization, threat/risk, sentiment, causation, demographic traits, future behavior, or identity confidence. Mere co-location in different events, temporal proximity, visual similarity, missing data, or a small denominator cannot imply a relationship. Opaque AI summaries and unsupported anomaly scores are excluded.

Person salience and result ranking are also descriptive read-model outputs. Explicit operator priority is always a separate factor. Computed salience may use scoped activity, relationship/evidence counts, recency, and qualified change patterns only through a documented versioned formula or deterministic ordered sort. The response returns the ordered factors and values; it must not collapse them into unexplained “importance” or probability.

#### Explanation contract

Every returned cluster, relationship, ranked person, and pattern has a structured `explanation` containing `summary`, `basis_type`, `factual_factors`, `derived_factors`, `calculation_version`, effective time/scope, evidence counts/types, occurrence bounds, and a bounded `evidence_ref`/expansion target. Factual and derived statements remain visibly distinct:

- Cluster explanations state the grouping algorithm/parameters, qualifying member edges, cross-member evidence counts/types, and the strongest membership reasons. Shared location or time may describe the scoped evidence but cannot independently assert membership.
- Relationship explanations state canonical endpoints, directionality, evidence count by type, co-observation count, first/last occurrence, effective scope, and the exact `EVIDENCE_COUNT_IN_SCOPE` strength basis.
- Person explanations state explicit priority separately from scoped activity, connection counts, recency, and qualified recent changes, including the ranking rule and factor values.
- Pattern explanations state the current metric, baseline metric, windows, threshold, sample/coverage sufficiency, and provenance expansion target.

Factual explanations directly summarize authoritative records. Derived explanations must name their deterministic calculation. Explanations must avoid causal language, human motives, inferred group identity, probabilistic confidence, and prose that cannot be regenerated from returned factors.

#### Filter and scope semantics

The frontend requests intent; the backend validates, normalizes, applies, and echoes meaning. World supports inclusive absolute date/time bounds; named recent windows resolved against an explicit `as_of`; exact case-insensitive normalized location facets plus an explicit `MISSING` facet; lifecycle, identity state, biometric state, priority, rank, and country; evidence and relationship type; minimum evidence-count strength after scoping; descriptive activity bucket; and pattern type/status such as qualified emerging results.

Temporal, location, and evidence-type filters first scope qualifying evidence/events. Canonical resolution and self-link suppression then occur. Person-state/profile filters determine eligible people. Relationship aggregates and strength thresholds are computed next; cluster membership, metrics/patterns, salience, ranking, and facets are computed from that effective scope. The response echoes requested filters, effective filters, `as_of`, effective bounds, missing-value policy, and filter semantics/version. Archived, deleted, and merged history is never erased: current-only projections may omit historical nodes, while history totals and explicit historical queries remain available.

#### Minimum read contract

`GET /api/world-graph` version 1 remains a compatibility-only small-data Level 2 person graph. The minimum clean product contract is a version 2 evolution of that single read route, not five new resource routes. It accepts `level`, typed `focus_type`/`focus_id`, filters, ranking intent, limit, and an optional revision-bound cursor/expansion token. The backend returns one coherent snapshot. Separate `/api/world-overview`, `/api/world-clusters`, `/api/world-person`, and `/api/world-event` routes are unnecessary while they share the same authorization, scope, revision, and response envelope; split endpoints only if later measurements or materially different policies require them.

The version 2 envelope requires contract/version, graph revision, `as_of` and generation time, requested/returned level, focus, requested/effective filters and filter semantics version, scope totals, available facets, ranking/clustering/calculation versions, returned/total counts by object type, limits, truncation/`has_more`, and a revision-bound cursor. The revision used for World pagination advances for every authoritative input admitted to the response; inputs without revision coverage are excluded. A changed revision invalidates the cursor, and pages from different revisions must not be combined.

Typed payloads require:

- person objects with canonical identity, historical IDs, display fields, lifecycle/identity/biometric states, allowed actions, explicit priority, activity/relationship intelligence summary, rank factors, and explanation;
- event objects with finalization state, time/location/context/source, raw and effective canonical participants, media summary, correction/merge provenance, allowed drill-down, and explanation;
- cluster objects with revision-bound ID, members or bounded member preview, total member count, algorithm/version/parameters, ranking factors, grouping strength basis, explanation, and expansion token;
- pattern objects with type/status, subjects, metrics/units, current and baseline windows, threshold/sample policy, calculation version, evidence summary, explanation, and expansion token;
- typed edges with endpoints, relationship type, canonical endpoints, directionality, evidence or member-pair counts, strength/aggregation basis, time bounds, provenance summary, explanation, and evidence expansion token.

Level 4 returns bounded evidence summaries rather than unrestricted raw rows. Pagination, cluster expansion, and evidence expansion remain backend operations: the frontend never canonicalizes, deduplicates, clusters, joins pages to invent an edge, recomputes strength, or decides why an object was selected.

#### Scale and caching rules

Every response has hard backend caps even for small data. With roughly 100 people, a bounded Level 2 response may return the complete scoped person graph when it fits those caps. At roughly 10,000 people, initial loading must be Level 0 summaries plus bounded Level 1 clusters/top people; person and cluster detail is lazy, ranked, and cursor-paginated. At 100,000 observations and beyond, event/evidence detail is always on demand, temporal/location/evidence scoping and aggregation move into indexed SQL, and no request materializes all sightings, observations, evidence, or person intelligence in application memory.

The first implementation step is bounded queries and server-side aggregation using existing SQLite capabilities. Measurements, query plans, deterministic fixtures, and latency/memory budgets must justify any additional index or derived cache. A cache, if later required, is local, revision/filter/calculation-version keyed, invalidated by the graph revision, and fully rebuildable; it is never authoritative. No new dependency or schema change is required by this architecture review.

#### Backend/frontend responsibility boundary

The backend owns World object existence and identity, canonical resolution, lifecycle/biometric/identity state, finalized-event eligibility, participant membership, person relationships, evidence counts/types, strength and aggregation bases, cluster algorithms and membership, salience/ranking, pattern qualification and calculations, explanation factors/text, filter/facet semantics, totals, pagination, truncation, revision consistency, and allowed actions. These values are part of the read contract and are never reconstructed from display data.

The frontend owns visual layout, coordinates, rendering, line/node styling, animation, zoom and pan, selection/hover/focus state, navigation gestures, local control state, and issuing scope/detail/expansion intent. It may format backend facts for display, but it cannot infer missing objects or edges, recompute intelligence, reinterpret explanations, merge pages across revisions, or turn visual proximity into domain meaning.

### P10-E World API v2 read contract

`GET /api/world-graph?version=2` implements the bounded World contract without replacing the version-1 compatibility projection. A typed `WorldGraphRequest` carries one semantic detail level (`WORLD_SCOPE`, `CLUSTER`, `PERSON`, `EVENT`, or `EVIDENCE`), typed focus, one collection/expansion intent, filter and ranking intent, per-object limits, optional `as_of`, an opaque graph revision, and an opaque revision-bound cursor. The response echoes requested and normalized effective filters, the resolved `as_of`, scope totals and facets, returned counts, hard effective limits, and independent per-collection pagination/truncation state.

World v2 returns explicit `WorldPerson`, `WorldCluster`, `WorldEvent`, `WorldEvidence`, `WorldMediaReference`, `WorldRelationship`, and `WorldPattern` read objects rather than storage rows. Events are finalized observations only and separate deduplicated effective participants from typed raw/corrected/merged provenance. Evidence detail is bounded and retains its evidence type, authoritative source reference, operation provenance, occurrence time, and explanation links; media detail is a separately paged reference collection and never embeds bytes. People collapse merged aliases into the terminal canonical identity while retaining historical IDs and lifecycle state.

The initial cluster algorithm is `connected-evidence-components-v1`: a deterministic connected component over relationships that remain after evidence/event scoping, canonical resolution, person filtering, self-link suppression, and minimum-strength filtering. It requires at least two members. Its revision-bound ID, parameters, qualifying relationship count, evidence counts/types, occurrence bounds, and explanation are returned. It is never an organization or durable association. The only initial pattern emitted is a measured `DATA_QUALITY` missing-location summary; unsupported risk, intent, affiliation, prediction, and opaque inference remain excluded.

Filter order is normative: resolve `as_of` and recent-window presets; scope finalized events and active evidence by time, location/missing-location behavior, evidence and relationship type; resolve canonical identity and remove self-links; apply lifecycle, identity, biometric, country, rank, priority, and activity eligibility; aggregate strength; then cluster, rank, calculate facets/patterns, and paginate. Ranking is deterministic and exposes separate operator-priority and measured activity/relationship/evidence factors.

World v2 uses the shared graph revision as snapshot invalidation, not as an operation count. The revision changes for World-visible person display/profile/identity/lifecycle/biometric changes, canonical changes and merges, finalized observations, corrections and Move Face effects, evidence creation/retirement/rebuild, and saved-note mention evidence. Draft observation metadata and person metadata outside graph/World fields do not advance it. Schema v28 narrows the existing person metadata trigger to visible profile and representative-media fields; it adds no authoritative World storage. Cursors are rejected when revision, detail level, focus, selected collection, `as_of`, filters, ranking, or limits differ.

### P10-E hardened navigation and explanation contract

World v2 selects one independently bounded collection per request. `WORLD_SCOPE` pages `PEOPLE` or `CLUSTERS`; `CLUSTER` pages `MEMBERS` or `RELATIONSHIPS`; `PERSON` pages `RELATIONSHIPS` or finalized `EVENTS`; and `EVENT` pages `PARTICIPANTS`, `EVIDENCE`, or `MEDIA`. `EVIDENCE` remains a direct bounded provenance read. Every collection reports `total_count`, `returned_count`, `has_more`, a revision/scope/collection-bound `next_cursor`, and an explicit truncation reason. Unrequested child collections are declared lazy rather than silently capped.

Effective event participation is defined by `(observation_id, terminal_canonical_person_id)`. Corrections are applied before canonical resolution and duplicate effective participants are removed before activity, ranking, patterns, event totals, and relationship aggregation. Event participants expose only effective person IDs; a separate provenance mapping labels each raw participant as `ORIGINAL_IDENTITY`, `MERGED_SOURCE`, or `CORRECTED_PARTICIPANT` and identifies its effective identity.

Ranking values are descriptive ordering inputs, never confidence or risk scores. `SALIENCE`, `RECENT_ACTIVITY`, `EVIDENCE_COUNT`, and `DISPLAY_NAME` return criterion-specific reasons, effective scope, supporting metrics, rank position when globally ranked, deterministic tie-break fields, and explicit value semantics. `RECENT_ACTIVITY` requires an absolute or preset time scope. Cluster, relationship, ranking, event, and pattern explanations carry method, scope, strongest factors, threshold/sample information where applicable, and limitations.

Overview reads own global ranking/clustering/summary aggregation. Person reads execute focused relationship and event queries; event reads load only the selected finalized event and requested child page; evidence reads load only bounded evidence. Event summaries do not contain media bytes, embeddings, raw evidence bodies, or complete history. Media remains a separate reference collection. This hardening adds no authoritative World storage, schema migration, cache, materialized view, background work, dependency, or frontend behavior.

#### 2026-08-10 P10-E stabilization status

The correctness and contract gaps found by the freeze review are closed. A World v2 response now begins a deferred SQLite read transaction before reading graph revision, so every contributing query—including focused person, event, and evidence reads—belongs to the same snapshot while WAL writers remain concurrent. Relationship projection and evidence expansion both apply observation correction before terminal canonical resolution; exact effective endpoint predicates suppress self-edges and prevent cross-edge leakage while raw evidence endpoints and source provenance remain visible.

The active contract now supports bounded overview relationships, cluster ranking/activity context, person cluster memberships, exact `EVIDENCE → MEDIA`, independent participant provenance, truthful location-facet pagination, and explicit not-requested children. Partial neighbour analytics are `NOT_LOADED`/`null`, never zero placeholders. Evidence rows carry type, direction, raw/effective endpoints, occurrence bounds, authoritative source references, structured explanation, and media availability. Co-observation evidence may navigate only to its supporting finalized observation's media; note and manual evidence return an explicit unavailable empty media collection. Dormant expansion-token fields are excluded from the v2 JSON payload.

P10-E and P10-F are complete and frozen. The final consolidated sparse/dense cold/warm performance artifact records latency, SQL count, payload, and returned-item measurements; dense-B Python peak-allocation tracing remains explicitly not practical because it distorts runtime. Completion of that gate transfers no authority to the frontend.

## Current repository map (schema version 33)

| Concern | Current implementation |
| --- | --- |
| Domain types | `src/sentriface/models.py`: `Person`, `Note`, `NoteRevision`, `Observation`, `ObservationMedia`, `ObservationParticipant`, `RelationshipEvidence`, `GraphNode`, `GraphConnection`, `GlobalGraphProjection`, plus existing biometric, queue, profile, and legacy-association types |
| Storage boundary | `src/sentriface/contracts.py::IdentityStore` |
| Database and migrations | `src/sentriface/storage/sqlite_store.py`: `SCHEMA_VERSION`, `SQLiteIdentityStore.initialize()`, and the validated `_schema_migrations()` registry through `_migrate_32_to_33`; `_connect()` enables foreign keys and commits/rolls back a connection-scoped transaction |
| Current tables | `persons`, `notes`, `note_revisions`, `note_revision_mentions`, `note_mentions`, `observations`, `observation_media`, historical `observation_participants`, immutable `observation_face_assignments`, append-only `encounter_metadata_revisions` and `encounter_participant_revisions`, the `effective_observations` read view, durable `encounter_relation_decisions`, `identity_corrections`, `biometric_enrollment_history`, normalized `merge_operations`, `merge_affected_items`, and `merge_conflict_resolutions`, revisioned `relationship_evidence`, derived `graph_connections`, plus existing biometric, queue, sighting, journal, auth, settings, and legacy `person_associations` tables |
| Application service | `src/sentriface/graph_service.py::GlobalIdentityGraphService` is the single normalized evidence/projection boundary; `src/sentriface/engine.py::FaceEngine` owns it as `graph` alongside existing recognition and identity services |
| Correction service | `src/sentriface/correction_service.py::IdentityCorrectionService` centralizes P7 observation correction, Move Face, and Add Face commands and routes graph-affecting work through `GlobalIdentityGraphService` |
| Merge service | `src/sentriface/merge_service.py::IdentityMergeService` is the P8-B preview/execution boundary and coordinates transactional storage execution with derived-index publication/reconciliation |
| Intelligence services | `src/sentriface/intelligence_service.py::IntelligenceReadService` is the read-only P9 boundary; `src/sentriface/graph_read_service.py::GraphReadService` is the P10-A boundary for Person Graph, World Graph, backend filtering, and revision reads |
| Recognition/index | `FaceEngine.recognize()` returns proposals; `linear_index.py`/`hnsw_index.py` are rebuilt from active embeddings and are derived caches |
| API | `src/sentriface/api_server.py`; P10-A adds `/api/person-graph`, `/api/world-graph`, and `/api/graph-revision` while preserving the P9.5 `/api/person-relationship-graph` compatibility contract; recognition, queue, merge, lifecycle, and backup routes retain their prior boundaries |
| React shell/controllers | `frontend/src/SentriFaceApp.jsx`; `useRecognizeController.js`, `useQueueController.js`, `usePeopleController.js`, `useAppData.js`; the People controller owns Person Graph fetch/revision invalidation state |
| React views | `frontend/src/views/RecognizeView.jsx`, `QueueView.jsx`, `PeopleView.jsx`, `PersonGraphView.jsx`, and the frozen World views rooted at `WorldView.jsx` |
| Current graph UI | `frontend/src/views/PersonGraphView.jsx` renders the P10-A Person Graph contract; `frontend/src/utils/personGraphLayout.js` positions backend-provided nodes without reading edges; the P9.5 relationship layout utility remains compatibility code only |
| Backup/offline | `src/sentriface/backup_service.py`, `backup_crypto.py`, `secure_storage.py`, `offline_guard.py`, `os_network_policy.py`; packaging policies under `packaging/` |
| Relevant backend tests | `tests/test_graph_evidence.py`, `test_observations.py`, `test_storage.py`, `test_operation_journal.py`, `test_identity_lifecycle.py`, `test_merge_foundation.py`, `test_identity_merge_orchestration.py`, plus existing engine, queue, person, notes, backup, and offline-packaging tests |
| Relevant frontend tests | `frontend/tests/relationship-graph.test.mjs`, `queue-layout.test.mjs`, `people-layout.test.mjs`, `backend-call-discipline.test.mjs` |

## Current semantics and compatibility boundaries

- `persons` now has explicit `lifecycle_status`, `canonical_person_id`, `identity_status`, `biometric_status`, and `lifecycle_changed_at`. Existing live rows migrate to `ACTIVE`; legacy archived rows remain historical, and valid `metadata.merged_into` sources migrate to `MERGED` mappings.
- Ordinary archive, restore, and delete paths now use atomic lifecycle transitions plus the global operation journal. The compatibility `permanently_delete_person()` entry point tombstones as `DELETED` and retains linked history; the former destructive implementation remains isolated as the storage-only `physically_purge_person()` exceptional capability.
- `observations`, `observation_media`, and `observation_participants` provide draft events, existing-media membership, and canonical-aware participant deduplication while retaining original person IDs. Standalone domain finalisation remains gated; P6 review completion is the exposed atomic finalisation path.
- Existing `recognition_details` rows remain unchanged and accessible. Their nullable `observation_id` remains the compatibility bridge; migration does not invent or backfill events from ambiguous legacy rows.
- `photo_reviews` and `photo_review_faces` hold non-authoritative staged face decisions. `SQLiteIdentityStore.complete_photo_review()` is the single P6 transaction that creates accepted identities/embeddings, finalizes the observation and media/participants, saves review notes, records co-observation evidence, rebuilds/validates the projection, commits one `review.complete` journal operation, and only then marks the review complete. `FaceEngine` gates the legacy per-face pending/Queue confirmation paths.
- Completed P6 reviews also retain immutable face-to-observation assignments. P7 corrections leave original review decisions and `observation_participants` untouched, append `identity_corrections`, expose effective participants on current reads, retire only the affected observation's active co-observation evidence, and create a new evidence revision before rebuilding the global projection.
- Profile notes retain immutable revisions and explicit person-ID mention snapshots. Active mention occurrences own directed `NOTE_REFERENCE` evidence; edit or retirement deactivates only evidence from that occurrence. Merge conflict resolution appends a survivor note revision in the merge transaction. `persons.notes` is refreshed only afterward as a compatibility mirror; profile reads use normalized notes.
- Legacy profile and recognition-detail note text migrates into revision history without parsing `@` text or fabricating mention records/evidence. Existing legacy `automatic_mention` associations are not promoted when their exact note provenance cannot be established.
- Queue confirmation routes selected faces through the same P6 `review.complete` transaction boundary; the controller sends one intent for the selected group subset rather than maintaining durable participant or graph state.
- Check Photo stages decisions and sends one explicit `/api/photo-review-complete` intent after every face has a final decision.
- `relationship_evidence` now retains every immutable raw participant pair and source provenance for `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION`; only finalized-observation evidence is produced in P4. Canonical resolution and self-edge suppression happen only in the replaceable `graph_connections` projection.
- Legacy `person_associations` remains unchanged for historical/raw compatibility. Current profile and relationship-graph reads use the normalized `graph_connections` projection. Legacy rows are not speculatively copied into evidence when accurate provenance cannot be established.
- `_create_note_associations()` remains only for explicit-ID legacy compatibility paths; name matching no longer infers new associations. Normal profile-note saves use the global graph service and normalized evidence instead.
- Current Manual Association retirement deactivates exactly one normalized assertion. Legacy compatibility-row removal is not used by the operator UI and must not be mistaken for evidence-aware removal.
- The current Person Graph UI reads the P10-A contract and maintains only layout, camera, hover, and selection state. The complete, frozen World UI reads the World v2 contracts and likewise owns only presentation, navigation, and interaction state.
- The P2 canonical resolver and constrained `MERGED` mapping are present. P8-B exposes normalized merge preview and execution through `IdentityMergeService`, `FaceEngine`, and the loopback API. P11 exposes only its frozen guarded merge-revert subset.
- P8-A provides the caller-owned, connection-scoped canonical update primitive and immutable normalized `merge_operations` / `merge_affected_items` manifests linked to the global operation journal. P8-B executes those primitives in one transaction; legacy merge snapshots are not imported as normalized truth.
- Merge execution preserves source-owned embeddings, recognition history, raw participants, corrections, notes/revisions/mentions, evidence, and prior operation history. It changes the source lifecycle/canonical mapping, applies selected survivor profile values, rebuilds the derived graph projection, and publishes canonical index ownership. A failed transaction leaves no manifest or canonical/profile/graph change and records a durable failed attempt under a non-reusable operation ID.
- Identity, embedding, note, and observation read models retain raw IDs while exposing current canonical resolution. Observation APIs now separate immutable raw participants from corrected/canonical effective participants, and existing raw note mentions remain editable after their referenced identity becomes merged while new mentions remain active-only.
- Move Face appends current embedding-ownership and affected face-assignment corrections and recalculates only affected observations. It does not rewrite raw embedding enrollment ownership. Historical `photo_review_faces`, `recognition_details`, base participants, and inactive evidence revisions retain their original person IDs. The former destructive reassignment remains private as `_legacy_move_embedding()` with no production caller.
- Add Face uses a completed staged review targeting one active existing identity. It creates no person, observation, participant, or graph evidence, records immutable enrollment history, and atomically recomputes biometric status from eligible source samples; PROOF_ONLY alone does not enroll the identity.
- `operation_journal` is the current activity authority and profile activity resolves affected person entities canonically. `person_operations` remains unchanged only for historical compatibility and legacy idempotency; it is not merged into the current activity feed because its rows lack reliable actor and lifecycle data.
- Storage methods are generally transaction-scoped through `_connect()`. Normalized review, correction, and merge commands provide their phase-owned atomic boundaries; remaining legacy workflows that span several engine/API calls are not implicitly atomic.
- Current sightings and People metrics use finalized observations plus corrected/canonical effective participants. `recognition_details` remains available only as legacy recognition/photo-detail history and cannot determine sightings, presence, relationship strength, or identity.
- The People UI renders backend-provided sighting counts, first/last seen values, frequency values/labels, and normalized sighting rows. It no longer derives sightings or frequency from recognition details or client time calculations.

## Projection rules

Graph rebuild reads only authoritative durable records, resolves endpoints through canonical identity, groups active evidence by unordered canonical pair, drops self-links, and retains evidence details for explanation. Archived/tombstoned persons remain nodes with inactive presentation state. Recognition scores, temporary queue grouping, frontend state, and vector-index contents are never graph inputs.

## Issue #3 timestamp QA correction

World compares instants using exact integer microseconds derived through the existing
UTC parser (naive timestamps retain the established UTC interpretation). A bounded
request-local 4,096-entry memoization per parser/key avoids repeated parsing in
participant/evidence joins and collection queries; it is discarded with the read
connection. No schema or historical timestamps change. SQL keeps bounded filtering,
pagination and aggregation; chronological MIN/MAX retain the original timestamp
text using an instant collation. Discovery queries normalize once per effective Encounter before participant joins
and reuse the exact integer key for filtering, ordering and UTC ordinal-day grouping,
including microseconds immediately before midnight. Chronology participates in cursor
fingerprints so pre-correction pages cannot be mixed with corrected ordering.
