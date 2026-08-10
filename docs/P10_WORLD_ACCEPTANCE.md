# P10 World backend acceptance specification

This document is the authoritative PASS/FAIL checklist for freezing the P10 World v2 backend. It translates the existing P10-C, P10-D, and P10-E architecture into testable gates; it does not authorize new product concepts or P10-F UI work.

## Semantics and authority

- **P10-SEM-01 — One graph:** PASS only if World and Person Graph are read projections of the same normalized persons, finalized observations, effective participants, active relationship evidence, saved notes/mentions, manual assertions, corrections, merge history, and journaled operations. World owns no authoritative table or cache.
- **P10-SEM-02 — Authoritative entities:** PASS only if current World topology contains terminal canonical persons and finalized observations. Recognition proposals, unresolved/unknown detections, embeddings, media, evidence, locations, patterns, and clusters do not become person nodes or authoritative topology.
- **P10-SEM-03 — Derived objects:** PASS only if relationships, clusters, ranking, facets, patterns, totals, and explanations are deterministic, revision-bound, and rebuildable from normalized authority.
- **P10-SEM-04 — Lifecycle:** PASS only if active, archived, deleted, and merged historical identities follow the documented lifecycle semantics; archive/delete do not erase history, and merged sources remain raw provenance.
- **P10-SEM-05 — Frontend boundary:** PASS only if the frontend needs to supply request intent and presentation state, but never infer canonical identity, lifecycle, topology, relationship membership/strength, cluster membership, ranking, activity/sightings, evidence counts, explanation, truncation, patterns, or filter semantics.

## Navigation contract

- **P10-NAV-01 — World scope:** PASS only if `WORLD_SCOPE` returns effective totals, truthful facets, ranked canonical people, revision-bound cluster summaries, supported patterns, explanation metadata, typed documented aggregate relationships when present, effective filters, `as_of`, revision, and bounded pagination without fabricating topology.
- **P10-NAV-02 — Cluster:** PASS only if a cluster ID is valid solely for its revision/scope and `CLUSTER` independently pages backend-owned members and qualifying relationships while reporting ranking/activity context, grouping method and limitations, strongest relationships, effective scope, and truncation.
- **P10-NAV-03 — Person:** PASS only if `PERSON` returns the canonical focused person, independently bounded relationships or finalized events, applicable revision-bound cluster membership/context, and authoritative analytics. A partial neighbour projection must mark uncomputed analytics unavailable rather than encode them as zero.
- **P10-NAV-04 — Event:** PASS only if `EVENT` independently pages `PARTICIPANTS`, `EVIDENCE`, or `MEDIA`; an unrequested large child is empty and explicitly marked not requested while scalar/count summaries remain available.
- **P10-NAV-05 — Evidence:** PASS only if `EVIDENCE` returns identity/type, raw provenance, effective endpoints, directionality, occurrence, structured explanation, authoritative source links, and an independently bounded `MEDIA` collection.
- **P10-NAV-06 — Evidence media authority:** PASS only if co-observation evidence links only to media on its supporting finalized observation, while note-reference and manual-association evidence return an explicit empty media page unless their own authoritative source supports media. Endpoint media is never inferred.
- **P10-NAV-07 — Event media:** PASS only if `EVENT → MEDIA` returns bounded references for media attached to that finalized event.
- **P10-NAV-08 — Media payload:** PASS only if World JSON returns media references/provenance and never image bytes, embeddings, recognition history, or unrelated/unbounded metadata.
- **P10-NAV-09 — Public fields:** PASS only if each active public field has implemented semantics or explicitly reports unavailable for compatibility; dormant expansion-token fields that imply unsupported behavior are absent from the active v2 payload.

## Canonical identity and evidence correctness

- **P10-ID-01 — Resolution order:** PASS only if event/evidence interpretation applies identity corrections before terminal canonical resolution.
- **P10-ID-02 — Current versus historical:** PASS only if current projections canonicalize while raw historical ownership/endpoints remain unchanged and explainable.
- **P10-ID-03 — Effective participation:** PASS only if a canonical person contributes at most once to one finalized event, including repeated detections, merges, corrections, and merge chains.
- **P10-ID-04 — Relationship support:** PASS only if every expanded evidence item resolves to the selected effective endpoint pair and preserves its effective directionality; evidence that collapses to a self-edge is suppressed without deleting raw provenance.
- **P10-ID-05 — Relationship counts:** PASS only if each projected relationship's `evidence_count` equals the complete count of supporting scoped evidence, and a complete cursor walk returns exactly that number.
- **P10-ID-06 — Collapsed evidence:** PASS only if multiple raw relationships may aggregate into one canonical relationship without evidence loss, cross-edge leakage, or self-links.

## Revision and cursor consistency

- **P10-REV-01 — One SQLite snapshot:** PASS only if every authoritative query contributing to one World response runs inside one coherent SQLite read transaction/snapshot.
- **P10-REV-02 — Revision correspondence:** PASS only if the response revision is read inside that snapshot and all returned data corresponds to it. A concurrent committed mutation is either wholly absent from the current response or wholly reflected with its new revision, never mixed.
- **P10-REV-03 — Focused reads:** PASS only if revision-bound `PERSON`, `EVENT`, and `EVIDENCE` reads have the same snapshot guarantee as `WORLD_SCOPE` and `CLUSTER`.
- **P10-REV-04 — Next read:** PASS only if a read begun before a concurrent commit stays coherent and a subsequent new read observes the committed revision/data.
- **P10-REV-05 — Cursor binding:** PASS only if cursors bind revision, detail level, focus type/ID, collection, normalized filters, ranking intent, effective limits, `as_of`, and contract scope/version. Stale or mismatched cursors fail deterministically.

## Explanations

- **P10-EXP-01 — Relationship:** PASS only if the explanation contains evidence types/counts, first/last occurrence, directionality, canonical endpoints, strength method/basis, effective scope, and the non-confidence limitation.
- **P10-EXP-02 — Cluster:** PASS only if the explanation states why members qualify, strongest qualifying relationships, temporal/window and location/context scope, algorithm/version, threshold/sample, and limitations.
- **P10-EXP-03 — Ranking:** PASS only if ranking output states intent, position when ranked, measured inputs and their availability, effective window, deterministic tie-break, reason, and non-confidence semantics.
- **P10-EXP-04 — Pattern:** PASS only if each emitted pattern states calculation, threshold, sample/window, subjects, supporting measurements, and limitations.
- **P10-EXP-05 — Evidence:** PASS only if each item explains the fact represented, authoritative provenance/source, raw and effective endpoints, directionality, and effective interpretation.
- **P10-EXP-06 — No speculative scores:** PASS only if World exposes no risk/threat/intent/affiliation/prediction/identity-confidence or opaque importance score.

## Bounds, pagination, and facets

- **P10-PAGE-01 — Page truth:** PASS only if every bounded collection reports `total_count`, `returned_count`, `has_more`, `next_cursor`, `truncated`, and `truncation_reason`; no cap is silent.
- **P10-PAGE-02 — Independent children:** PASS only if cluster members/relationships, person events/relationships, event participants/evidence/media, and evidence media paginate independently.
- **P10-PAGE-03 — Participant provenance:** PASS only if raw participant provenance has an explicit limit/page state independent of effective participants, so merges cannot expose unbounded raw rows beneath a bounded effective page.
- **P10-PAGE-04 — Facet bounds:** PASS only if dynamic location facets are complete or explicitly bounded with the same truthful truncation metadata. Missing-location semantics remain explicit.
- **P10-PAGE-05 — Empty/unavailable collections:** PASS only if an unrequested or unsupported child distinguishes `not_requested`, `unavailable`, and complete-empty states without claiming silent completeness.
- **P10-PAGE-06 — Payload:** PASS only if every request remains bounded by documented hard limits, including provenance and media references.

## Edge cases and architectural invariants

- **P10-EDGE-01 — Empty database:** PASS only if totals/facets are valid and zero, topology/clusters/events/patterns are empty, and no `DATA_QUALITY` pattern/facet is fabricated.
- **P10-EDGE-02 — No relationships:** PASS only if topology and clusters are cleanly empty without invented links.
- **P10-EDGE-03 — Locations:** PASS only if no locations and all-unknown locations produce correct totals, explicit `MISSING` semantics, and data-quality explanation only when finalized scoped events exist.
- **P10-EDGE-04 — Merge/correction order:** PASS only for all-identities-merged, correction-then-merge, merge-then-correction, and chained-merge cases with terminal safe resolution and preserved raw history.
- **P10-EDGE-05 — Lifecycle history:** PASS only if deleted and archived persons remain historically explainable while current actions and topology obey lifecycle rules.
- **P10-EDGE-06 — Event deduplication:** PASS only if repeated detections and multi-person events contribute each effective participant once and each event location once.
- **P10-EDGE-07 — Unknown detections:** PASS only if no unknown face detection automatically creates a Person, participant, relationship endpoint, cluster member, or World node.
- **P10-EDGE-08 — Rebuildability:** PASS only if World/graph projections contain no authority unavailable from normalized authoritative records and projection rebuild remains equivalent.
- **P10-EDGE-09 — Focus isolation:** PASS only if focused reads do not run global ranking/clustering unless the selected contract requires it.

## Performance acceptance

- **P10-PERF-01 — Matrix coverage:** PASS only if the benchmark records Dataset A (about 100 people/10,000 observations) and Dataset B (about 10,000 people/1,000,000 observations), sparse and dense multi-participant data, unfiltered/date/location overviews, cluster expansion, person relationships/events, event evidence/media, evidence detail/media, merge-heavy and correction-heavy reads, and complete cursor walks.
- **P10-PERF-02 — Measurements:** PASS only if practical runs report cold and warm p50/p95 latency, SQL statement count, Python peak allocation, serialized payload bytes, and returned item counts. Any omitted measurement has an explicit justification.
- **P10-PERF-03 — Query scaling:** PASS only if representative bounded focused evidence and relationship reads use set-based/batched queries and SQL statement growth is not O(people) or O(returned evidence).
- **P10-PERF-04 — Pathology gate:** PASS only if the matrix exposes no unbounded/pathological behavior at intended scale. A roughly 2.27-second large sparse overview alone is not a blocker when correctness, bounds, and focused reads are healthy.
- **P10-PERF-05 — Architecture gate:** PASS only if acceptance requires no persistent cache, materialized World authority, worker, dependency, or schema redesign. If measured evidence proves one necessary, P10 freezes as failed pending a separately reviewed architecture change.

## Freeze gate before P10-F

P10-F may begin only when every BLOCKER is `FIXED`, every HIGH required by the existing contract is `FIXED`, all criteria above are PASS or explicitly inapplicable with evidence, the invariant/full relevant suites pass, navigation and authority boundaries are complete, snapshot/evidence/pagination correctness is proven, and the performance matrix is sufficient to expose intended-scale pathologies. MEDIUM/LOW items may be deferred only with a written justification that they do not violate the existing P10 contract, correctness, authority, bounds, or intended scale.

## Defect register

At freeze, every entry must be `FIXED`, `DEFERRED WITH JUSTIFICATION`, or `NOT A DEFECT`; no partial state is permitted.

| ID | Severity | Finding | Required disposition |
|---|---|---|---|
| P10-D01 | BLOCKER | Multi-query World responses are not held to one SQLite snapshot and can pair revision R with newer data. | FIXED — explicit deferred SQLite read transaction pins revision and all contributing queries; concurrent-writer invariant test passes. |
| P10-D02 | BLOCKER | Relationship evidence expansion can include canonical self-edge evidence or evidence supporting another surviving edge. | FIXED — correction-before-canonical endpoint resolution is shared by projection and expansion; exact-pair and self-edge invariant tests pass. |
| P10-D03 | HIGH | Exact `EVIDENCE → MEDIA` navigation is absent. | FIXED — typed evidence focus independently pages authoritative supporting-event media; unsupported source types return explicit unavailable/empty media. |
| P10-D04 | HIGH | Overview omits documented typed aggregate topology/relationships. | FIXED — `WORLD_SCOPE/RELATIONSHIPS` returns bounded typed evidence-derived relationships and page truth; no topology is fabricated. |
| P10-D05 | HIGH | Cluster detail omits documented ranking/activity context. | FIXED — cluster summaries carry deterministic rank measurements/reason/tie-break and exact activity contribution context. |
| P10-D06 | HIGH | Person detail omits applicable World cluster membership/context. | FIXED — focused canonical people carry revision/scope/algorithm-bound membership summaries. |
| P10-D07 | HIGH | Neighbour `WorldPerson` objects use zero for analytics that were not computed. | FIXED — partial neighbours use `NOT_LOADED` and `null`; authoritative zeros remain zeros. |
| P10-D08 | HIGH | Raw participant provenance can exceed effective-participant bounds after canonical collapse. | FIXED — `PROVENANCE` is an independent event collection with its own hard limit, cursor, and page state. |
| P10-D09 | MEDIUM | EVENT evidence/media reads include an unrequested participant page. | FIXED — unrequested event children are empty and report `collection_not_requested`; scalar/count summaries remain. |
| P10-D10 | HIGH | Location facets silently cap at 100. | FIXED — `LOCATION_FACETS` has a hard limit and revision/scope-bound cursor with truthful total/returned/truncation state. |
| P10-D11 | HIGH | EVENT evidence materialization performs per-row canonical and observation reads (measured 78 SELECTs/25 items). | FIXED — canonical/correction/occurrence/media data is preloaded/batched; representative 25-item page is 17 statements including event summaries. |
| P10-D12 | HIGH | Empty relationship evidence expansion resolves every person individually (measured 1,004 SELECTs/1,000 people). | FIXED — one canonical map and SQL effective-endpoint function replace per-person resolution; invariant threshold is at most 6 statements. |
| P10-D13 | MEDIUM | Empty scope advertises a `DATA_QUALITY` pattern facet despite returning no pattern. | FIXED — pattern facet count derives from emitted supported patterns and is empty for empty scope. |
| P10-D14 | MEDIUM | Dormant expansion-token fields imply unavailable behavior. | FIXED — compatibility fields remain internal only and are removed recursively from the active v2 JSON payload. |
| P10-D15 | HIGH | Required cold/warm sparse/dense filtered/focused/cursor benchmark matrix is incomplete. | DEFERRED WITH JUSTIFICATION — A profiles and a B sparse smoke completed, but dense-B Python allocation tracing remained active for over one hour and the environment denied termination. The consolidated 3/3 matrix artifact was not produced, so freeze remains blocked. The fixture now records dense-B allocation as not practical on future runs. |
| P10-D16 | MEDIUM | Relationship evidence `evidence_count` can disagree with a complete supporting-evidence walk after canonical collapse/filtering. | FIXED — count and rows use identical exact effective-pair predicates; self-edge, chain, correction/merge, and collapsed-raw-edge walks agree. |

## Final adversarial review record

Review date: 2026-08-10.

- **BLOCKER:** none. Snapshot coherence and relationship-evidence correctness are fixed and proven by focused concurrency/invariant tests.
- **HIGH:** P10-D15 only. The required consolidated cold/warm sparse/dense acceptance artifact is incomplete; this is a mandatory existing freeze gate, not a feature request.
- **MEDIUM:** none unresolved. Dense cluster/activity scans are finite, bounded, and set-based, but their final p95 classification remains part of P10-D15.
- **LOW:** the existing frontend production-build chunk-size warning remains unrelated to World backend behavior and does not block P10.
- **DEFERRED:** dense-B `tracemalloc` peak allocation is not practical because callback instrumentation dominates runtime. Future matrix runs record this field unavailable with that reason while still measuring API latency, SQL count, payload, and returned items.

Final gate result: **FAIL** solely because P10-PERF-01/P10-PERF-02 and defect P10-D15 are not complete. P10-F remains blocked. All other criteria are implemented and verified.
