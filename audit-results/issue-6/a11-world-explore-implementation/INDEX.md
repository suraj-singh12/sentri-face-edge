# A-11 World Explore implementation evidence

Implementation commit under review: `06f002f283738fbca24e4c4cde803d90673ee47f` on `feature/issue-6-a11-world-explore-clarity`.

## Runtime evidence

Synthetic development runtime, disposable `a11-world-authority` fixture, graph revision `g26`, Explore default scope (`CO_OBSERVED`, minimum strength 2). This verifies UX wiring and exact backend visibility metadata; it is not recognition-accuracy evidence.

| Scenario | Inspector screenshot | Verified message/metadata |
| --- | --- | --- |
| Genuine zero relationships | `screenshots/zero-inspector.png` | `No relationships in current scope`; all visibility counts 0 |
| Below-threshold isolated Person | `screenshots/below-threshold-inspector.png` | `1 relationship below minimum strength`; selected=1, qualifying=0, below=1 |
| Mixed qualifying/below-threshold Person | `screenshots/mixed-strength-inspector.png` | qualifying=1, below=1; inspector labels counts as qualifying-only |
| Evidence-type exclusion | `screenshots/type-excluded-inspector.png` | `1 relationship uses unselected evidence types`; selected=0, excluded=1, all-evidence=1 |
| Weaker-links wording ON/OFF | `screenshots/weaker-links-in-view-on.png`, `screenshots/weaker-links-in-view-off.png` | `Weaker links in view`; functionality remains visual-only |

Full-window captures and browser text snapshots are beside those images. `data/implementation-api-verification.json` contains the same-revision API visibility metadata for the four focused People.

## Focused regression results

- `npm --prefix frontend test`: 212 passed, 0 failed.
- `npm --prefix frontend run build`: passed; generated `ui_static` rebuilt from `frontend/`.
- `python -m pytest tests/test_world_graph_v2.py tests/test_world_intelligence.py -q`: 102 passed, 17 subtests passed.
- The backend regression uses `relationship_limit=1` while the focused Person has three total relationships and verifies exact counts remain selected=1, qualifying=0, below-minimum=1, evidence-type-excluded=2, all-evidence=3 in both weaker-toggle states. This covers coexistence without deriving totals from a paginated result.

## Boundaries verified

- No graph calculation, cluster membership, evidence semantics or default minimum strength change.
- Explore still defaults to `CO_OBSERVED` and minimum strength 2.
- Weaker links remains a display-only control for below-threshold edges already between visible People.
- The added backend reads are bounded to focused-Person relationship aggregation in the same request/revision scope: at most one selected-scope backfill and one all-evidence comparison.
