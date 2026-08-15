# P10 World performance acceptance

Final run: 2026-08-11.

The historical failed baseline remains `benchmarks/P10_WORLD_BENCHMARK_RESULTS.json`. The authoritative post-optimization matrix is `benchmarks/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json`; the baseline was not overwritten.

## Method

- Dataset A: 100 people and 10,000 finalized observations.
- Dataset B: 10,000 people and 1,000,000 finalized observations.
- Sparse profile: one participant per observation, no merges/corrections/evidence rows.
- Dense-heavy profile: four participants per observation, 5,000 relationship-evidence rows, and representative merges/corrections.
- Each read records three fresh-connection samples and five reused-connection samples. “Cold” does not flush the operating-system file cache.
- Latency is measured without allocation tracing. Allocation is measured separately where practical. Dense Dataset B records `NOT_PRACTICAL_DENSE_B_TRACEMALLOC_DISTORTS_RUNTIME` because tracing Python callbacks materially distorts product latency.
- The fixture directly seeds normalized finalized benchmark rows so million-row preparation remains practical; it does not benchmark writes or create product authority.

## Final matrix summary

Values below are warm p50 milliseconds. The JSON artifact contains cold/warm p50/p95, SQL counts, allocation status, payload bytes, and returned counts for every read.

| Read | A sparse | A dense | B sparse | B dense |
|---|---:|---:|---:|---:|
| World overview | 11.57 | 124.96 | 1,636.64 | 15,728.41 |
| Date-filtered overview | 7.99 | 72.63 | 1,210.80 | 12,915.59 |
| Location-filtered overview | 10.34 | 88.52 | 1,385.58 | 11,507.67 |
| Person events | 1.46 | 70.81 | 34.42 | 1,125.32 |
| Cluster members | — | 172.52 | — | 24,178.83 |
| Merge-heavy person relationships | — | 56.77 | — | 408.76 |
| Correction-heavy person events | — | 71.03 | — | 995.10 |
| Event evidence | — | 7.67 | — | 42.28 |
| Event media | — | 4.68 | — | 28.81 |
| Evidence detail | — | 0.33 | — | 12.94 |
| Evidence media | — | 0.36 | — | 10.87 |

SQL statement counts for corresponding A-dense/B-dense reads are identical: 9/8/8 for the three overviews, 14 for person events, 11 for cluster members, 8 for person relationships, 17 for event evidence, 15 for event media, 6 for evidence detail, and 9 for evidence media. Response payloads remain bounded; the largest measured dense-B read payload is 112,169 bytes.

All cursor walks returned exactly their advertised totals. The dense-B three-page location-facet walk returned 3/3 facets in 53,056.44 ms using 9 statements total; the event-evidence walk returned 1/1 in 41.57 ms using 17 statements.

## Dense Dataset B before and after

Comparison uses warm p50 except cursor walks, which use complete-walk elapsed time.

| Path | Before | After | Improvement |
|---|---:|---:|---:|
| World overview | 206.09 s | 15.73 s | 13.10× / 92.4% |
| Date-filtered overview | 111.06 s | 12.92 s | 8.60× / 88.4% |
| Location-filtered overview | 128.07 s | 11.51 s | 11.13× / 91.0% |
| Person events | 415.76 s | 1.13 s | 369.46× / 99.7% |
| Correction-heavy person events | 418.79 s | 1.00 s | 420.86× / 99.8% |
| Merge-heavy person relationships | 209.27 s | 0.41 s | 511.97× / 99.8% |
| Cluster members | 248.93 s | 24.18 s | 10.30× / 90.3% |
| Location-facet cursor walk | 674.42 s | 53.06 s | 12.71× / 92.1% |

## Acceptance decision

P10-PERF-01 through P10-PERF-05 pass. The matrix covers every required dataset/profile/read, reports every practical measurement, preserves constant bounded statement counts and payloads, and exposes no remaining N+1, observations×aliases/candidates, or avoidable complete-World child-page execution. Remaining dense latency is finite set-based work over one million observations and four million participant rows. No persistent cache, materialized World authority, schema/index change, worker, dependency, or frontend inference is required.
