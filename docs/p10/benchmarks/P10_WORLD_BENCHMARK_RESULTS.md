# P10 World v2 benchmark results

Run date: 2026-08-10. These are acceptance diagnostics from `scripts/benchmark_world_v2.py`; they are not a completed freeze artifact.

> **Superseded diagnostic:** The completed authoritative result is `P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json`. This file preserves the earlier incomplete run and its original conclusions for comparison.

## Method

- Dataset A sparse: 100 people, 10,000 finalized observations, one participant per event.
- Dataset A dense-heavy: 100 people, 10,000 finalized observations, four participants per event, 5,000 evidence rows, 10 merges, and 50 corrections.
- Dataset B sparse smoke: 10,000 people, 1,000,000 finalized observations, one participant per event.
- “Cold” means a fresh SQLite connection; the operating-system file cache was not flushed.
- “Warm” means a reused connection.
- Latency is measured without allocation tracing. Peak allocation is measured in a separate pass.
- The completed rows below have one cold and one warm sample and therefore do **not** establish the required p50/p95 distributions.

## Completed diagnostic rows

| Dataset/profile/read | Cold ms | Warm ms | SQL | Peak MiB | Payload bytes |
|---|---:|---:|---:|---:|---:|
| A sparse, unfiltered overview | 13.80 | 13.26 | 7 | 0.14 | 68,934 |
| A sparse, date-filtered overview | 9.40 | 9.01 | 6 | 0.11 | 69,561 |
| A sparse, location-filtered overview | 11.60 | 12.31 | 6 | 0.13 | 67,400 |
| A sparse, person events | 2.87 | 2.53 | 14 | 0.14 | 46,393 |
| A dense-heavy, unfiltered overview | 271.49 | 272.18 | 9 | 3.21 | 73,839 |
| A dense-heavy, date-filtered overview | 142.36 | 141.48 | 8 | 1.51 | 106,740 |
| A dense-heavy, location-filtered overview | 170.27 | 170.75 | 8 | 1.87 | 81,238 |
| A dense-heavy, cluster members | 351.92 | 352.13 | 10 | 3.21 | 72,433 |
| A dense-heavy, person relationships/merge-heavy | 101.55 | 101.81 | 8 | 3.23 | 51,504 |
| A dense-heavy, person events/correction-heavy | 150.98 | 150.95 | 14 | 3.23 | 47,444 |
| A dense-heavy, event evidence | 9.32 | 9.25 | 17 | 0.05 | 5,826 |
| A dense-heavy, event media | 6.35 | 5.94 | 15 | 0.03 | 4,191 |
| A dense-heavy, evidence detail | 1.14 | 1.40 | 6 | 0.02 | 3,756 |
| A dense-heavy, evidence media | 1.24 | 1.17 | 9 | 0.03 | 3,966 |
| B sparse, unfiltered overview | 4,023.23 | 3,708.79 | 7 | 8.76 | 68,984 |

The B sparse smoke is slower than the earlier approximately 2.27-second diagnostic but remains a constant-statement, bounded-payload full normalized scan. A single smoke sample is insufficient to classify regression or acceptance.

## Completed cursor diagnostics

| Profile/walk | Pages | Returned/total | Complete | Elapsed ms | SQL total |
|---|---:|---:|---|---:|---:|
| A sparse people | 1 | 100/100 | yes | 14.12 | 7 |
| A sparse location facets | 3 | 3/3 | yes | 38.86 | 21 |
| A dense-heavy people after merges | 1 | 90/90 | yes | 274.66 | 9 |
| A dense-heavy location facets | 3 | 3/3 | yes | 814.23 | 27 |
| A dense-heavy cluster members | 1 | 90/90 | yes | 352.13 | 10 |
| A dense-heavy event evidence | 1 | 1/1 | yes | 9.58 | 17 |

## Incomplete acceptance run

The requested 3-cold/3-warm Dataset A/B sparse/dense matrix did not produce a consolidated result. Dense Dataset B used one million observations and four million participant rows. Separate `tracemalloc` passes over its Python SQLite aggregate callbacks dominated runtime for more than one hour. The environment did not permit terminating the active process, so no partial result was promoted into an acceptance artifact.

The fixture now records dense-B peak allocation as `NOT_PRACTICAL_DENSE_B_TRACEMALLOC_DISTORTS_RUNTIME` and skips that allocation pass while retaining cold/warm latency, SQL count, payload bytes, and returned counts. A future rerun must complete before P10 freeze. No cache, materialized view, index, schema change, worker, or dependency was introduced in response.
