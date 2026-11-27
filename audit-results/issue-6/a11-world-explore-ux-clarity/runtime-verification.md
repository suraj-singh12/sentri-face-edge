# A-11 World Explore UX clarity — runtime verification

## Scope and environment

- Product verified: `suraj-singh12/sentri-face-edge`, `v2-hardening-followups` at `613b352f0d68580356345aea8401ab52dfaf9797`.
- Runtime: source development mode on loopback `127.0.0.1:8765`, Linux, Chromium at 1440×1000, demo/synthetic recognition runtime. No recognition inference was used to create graph evidence.
- Account exercised: owner/Administrator only. This audit targets World read/communication behavior, not role-specific mutation permission.
- Data: isolated disposable authority at `/home/ubuntu/a11-world-authority`; final graph revision `g26`, API as-of `2026-11-26T07:19:10.231516+00:00`.
- No product files, graph calculations, cluster membership, filter defaults or production data were changed.

The fixture uses only authoritative storage records: finalized co-observed Events and one standing manual association. It contains no genuine photographs or biometric claims.

## Fixture states

| State | Authoritative setup | Purpose |
| --- | --- | --- |
| Zero Person | One solo finalized Event; no relationship evidence | Genuine zero state |
| Low Alpha ↔ Low Beta | One co-observed Event | Below default minimum strength 2 |
| High Alpha ↔ High Beta | Two co-observed Events | Qualifying relationship at strength 2 |
| Mixed Person ↔ High Beta | Two co-observed Events | Qualifying relationship at strength 2 |
| Mixed Person ↔ High Alpha | One co-observed Event | Below-threshold edge between displayed cluster members |
| Type Alpha ↔ Type Beta | One standing manual association | Relationship excluded by the default Co-observed-only evidence selection |

## Verified behavior

| Check | Authoritative/API result | Runtime result | Conclusion |
| --- | --- | --- | --- |
| Zero Person at strengths 1, 2 and 3 | Zero relationship rows | Inspector shows `0 Relationships`, `0 Evidence records` | Correct count, but the label does not explain genuine absence |
| Low Alpha at strength 1 | One relationship, strength 1, `qualifies_for_cluster: true` | Qualifies when minimum is lowered | Confirms fixture is valid below-threshold evidence |
| Low Alpha at default strength 2 | Same relationship returned with `qualifies_for_cluster: false` because Explore requests `include_below_threshold=true`; person summary remains 0 qualifying relationships / 0 qualifying evidence | Inspector shows `0 Relationships`, `0 Evidence records`; canvas shows an isolated node even with Weaker links ON | Counts are qualifying-only; current copy does not explain the hidden existing relationship |
| High Alpha at default strength 2 | Person focus returns two selected-type relationships: strength 2 qualifying and strength 1 below threshold; summary remains 1 qualifying relationship / 2 qualifying evidence | Inspector shows `1 Relationships`, `2 Evidence records` | Labels imply totals but are qualifying-only |
| Mixed Person at default strength 2 | One qualifying relationship to High Beta and one below-threshold relationship to High Alpha | Inspector shows `1` / `2`; below-threshold relationship is not explained in person inspector | Mixed-strength state needs compact contextual count |
| Type Alpha at default evidence selection | Manual association absent when evidence selection is Co-observed only, even at strength 1 | Inspector shows `0` / `0` and isolated node | Indistinguishable from genuine zero |
| Type Alpha after selecting Manual associations at strength 1 | Same manual association appears, strength 1, `qualifies_for_cluster: true` | Inspector shows `1` / `1` | Confirms evidence-type exclusion rather than absence |
| Qualifying cluster at default strength 2 | One connected component of High Alpha, High Beta and Mixed Person; two qualifying relationships and four qualifying evidence records | Solid qualifying edges render | Clustering semantics are preserved |
| Weaker links ON | High Alpha ↔ Mixed Person strength-1 edge appears dashed because both endpoints are displayed cluster members | Dashed edge visible | Toggle controls display of below-threshold edges between displayed members |
| Weaker links OFF | Same dashed edge disappears; qualifying solid edges remain | Dashed edge hidden | Confirms control behavior |
| Isolated Low Alpha with Weaker links ON | Low Beta is not a displayed cluster member because neither endpoint qualifies at strength 2 | No edge appears despite toggle being ON | Current label overpromises; “all weaker relationships” are not globally revealed |

## Source-grounded mechanics

Verified in the same product source:

- Explore defaults are Co-observed evidence and minimum relationship strength 2 in `frontend/src/utils/world.js`; they are intentional and unchanged here.
- `exploreRequest()` adds `view=EXPLORE` and `include_below_threshold=true` in `frontend/src/utils/world.js`.
- The toolbar label is `Weaker links` in `frontend/src/views/WorldExploreView.jsx` (`ExploreWeakerControl`).
- Person inspector labels are `Relationships` and `Evidence records` in `frontend/src/views/WorldExploreView.jsx` (`WorldExploreInspector`).
- Canvas rendering filters edges by `weaker || edge.qualifies_for_cluster`, then additionally requires both endpoints to have canvas positions in `frontend/src/views/WorldExploreCanvas.jsx`.
- The focus hook initially receives the person relationship response, but graph edges are replaced by cluster relationship pages when a cluster exists in `frontend/src/hooks/useWorldExplore.js`.
- Backend aggregation marks `qualifies_for_cluster` from `evidence_count >= min_relationship_strength` and only omits below-threshold rows when `include_below_threshold` is false in `src/sentriface/storage/sqlite_world.py`.
- `_world_degree()` skips non-qualifying rows before producing `intelligence_summary.relationship_count` and `relationship_evidence_count`; therefore the inspector numbers are qualifying counts, not absolute totals.

## API support assessment

No API addition is strictly required for the proposed messaging.

1. **Below-threshold relationship count** is already derivable exactly for a focused Person:
   - `pagination.RELATIONSHIPS.total_count` counts selected-evidence relationships returned under `include_below_threshold=true`, regardless of whether the first page contains every row.
   - `people[0].intelligence_summary.relationship_count` counts only qualifying relationships.
   - Difference: selected-type relationships below the minimum strength.
   This needs contract tests because it is a subtle composition of existing fields.

2. **Evidence-type exclusion** can be derived without schema change by one conditional follow-up person-focus read using the same graph revision/as-of and other filters, but with all three currently supported evidence types selected. Comparison:
   - all-types relationship total `0` → genuinely no relationships in the applied non-evidence scope;
   - selected-types total `0`, all-types total `>0` → relationships exist but are excluded by evidence selection;
   - selected-types total `>0` → use the below-threshold calculation above.

This is preferable to a backend addition for the smallest coherent UI refinement. If repeated conditional reads are considered undesirable at scale, a small additive backend summary could be introduced later, for example `relationship_visibility_summary` with `selected_count`, `qualifying_count`, `below_minimum_count`, and `excluded_by_evidence_type_count`. That is optional, not required.

## Limitations

- Only the Administrator/owner role was exercised; the copy is read-only informational and has no role-specific action.
- Synthetic demo runtime was used. This does not affect the tested graph semantics because fixture evidence is authoritative finalized/manual data and no recognition inference was involved.
- The type-exclusion comparison algorithm is source/API reasoning supported by fixture verification; it was not implemented in product code.
