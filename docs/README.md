# SentriFace Edge documentation map

## Current source and qualification (2026-10-29)

- **Product baseline:** Schema v34 / Batch 3.7 remains authoritative. [World intelligence #3](https://github.com/suraj-singh12/sentri-face-edge/issues/3) was merged into `release-v2.0.0-hardening` at `f907073edc3375dbfd15b8bb39cc6d32bc60f6b6`. It adds backend evidence criteria, recurrence, discoveries and saved-location suggestions. The **Current World UI remains unchanged**; the optional Explore UI is still under [#13](https://github.com/suraj-singh12/sentri-face-edge/issues/13).
- **QA foundation:** [Issue #17](https://github.com/suraj-singh12/sentri-face-edge/issues/17) completed its defined macOS QA-J01 acceptance: two genuine browser/ONNX journeys, independent People/Events/World and restart checks, negative controls and isolated cleanup. [PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23) at `b81d451` has [five passing CI jobs](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40905213311) and is **merged as `6a9ec82`**. Runbooks and private fixture policy live in [DEVELOPMENT_MODE](DEVELOPMENT_MODE.md#qa-foundation-17), not in the root README.
- **Known integrity issue:** [#22](https://github.com/suraj-singh12/sentri-face-edge/issues/22) tracks a confirmed pre-existing finalized FACE_ASSIGNMENT correction mismatch in World discoveries. [Period fix PR #15](https://github.com/suraj-singh12/sentri-face-edge/pull/15) remains draft/held; do not conflate its code change with the pre-existing defect.
- **Remaining:** Foundation #23 is merged; review the #22 correction separately; approve/complete World Explore #13; then QA expansion [#18–#21](https://github.com/suraj-singh12/sentri-face-edge/issues/16). [#4](https://github.com/suraj-singh12/sentri-face-edge/issues/4) Split/Merge and [#6](https://github.com/suraj-singh12/sentri-face-edge/issues/6) UI refinement remain planned. [#9](https://github.com/suraj-singh12/sentri-face-edge/issues/9) main-branch CI adoption is explicitly deferred. Production release/signing and current Windows installer acceptance [#5](https://github.com/suraj-singh12/sentri-face-edge/issues/5) remain open.
- GitHub Issues and their linked PRs track **live work**; the implementation plan and historical phase records preserve engineering provenance. Roadmap P0–P4 labels are distinct from historical phases P0–P14.

## Historical implementation checkpoints

- Batch 3.6 repairs shared registered provenance, canonical standing-manual collisions and accepted recognition display. Complex real rebuild and fresh supported restore/restart are qualified; IMPLEMENTATION_PLAN owns exact results and limits. Batch 4 remains unimplemented.

- Batch 3.5 converges effective pair support, enrollment/decision contracts, mutation read reconciliation and operational completion/custody. `IMPLEMENTATION_PLAN.md` owns targeted qualification and final gates; the next three-phase clean-room reaudit was separate from that historical checkpoint.

- The 2026-10-01 correctness pass extends existing staging to schema v31 for durable pre-grouping media exclusion, unifies committed/active-draft recognition and duplicate prevention, and fixes stale group/form state. `IMPLEMENTATION_PLAN.md` owns current verification and remaining work. No new Encounter, media, note or recognition-index system is introduced.

- P0 through P14 source implementation is complete.
- P10 through P13 are complete and frozen, including all of P11-A through P11-E.
- Historical P14 unsigned Windows 11 x64 installer lifecycle acceptance passed
  for an earlier artifact. Its source, build, inspection and packaged runtime
  results remain historical; the latest unsigned CI result is linked above.
- Production P14 acceptance remains pending verified signatures, the current
  artifact's disposable-Windows installer and packaged model lifecycle, and a
  clean exact `rc-v2.0.0` or `release-v2.0.0` rebuild.
- The 2026-09-27 stabilization and pre-Batch-2 integration extend finalized observations with shared Encounter metadata, add embedding eligibility to schema v29, preserve no-face selection and face-origin provenance, and expose bounded read-only Events. The reduced managed upload is historical media. See `IMPLEMENTATION_PLAN.md` for verification and remaining risks.
- Batch 2 established serial durable Encounter drafts and explicit Relations decisions in schema v30; a later historical correction extended that staging to v31. Final completion remains the existing atomic observation/person/evidence/journal command. The canonical tracker records automated gates and the authenticated synthetic-media development walkthrough; production-model and full role walkthroughs remain separate. Do not treat this source checkpoint as release acceptance.

## Start here

1. Repository-root `AGENTS.md` — product and safety rules.
2. [Repository README](../README.md) — newcomer overview and first run; this map owns deeper reading.
3. [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — canonical tracker, current batch and next work.
4. [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) — complete product mental model.
5. [`ARCHITECTURE_STATE.md`](ARCHITECTURE_STATE.md) — implemented checkpoint.
6. [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) — current normative entities and authority.
7. [`FEATURES_BY_TAB.md`](FEATURES_BY_TAB.md) — current user-facing tabs, permissions and boundaries.
8. [`ARCHITECTURE_EXPLANATION.md`](ARCHITECTURE_EXPLANATION.md) — detailed rationale.
9. [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) — operational takeover and release boundary.

Human entry path: this map → `PROJECT_OVERVIEW.md` → `FEATURES_BY_TAB.md` → `DOMAIN_MODEL.md` → `ARCHITECTURE_EXPLANATION.md`. Both paths converge on the same authority.

These documents are complementary rather than successive revisions. `ARCHITECTURE_STATE.md` answers what is implemented now; `IMPLEMENTATION_PLAN.md` answers where that sits in the sequence; `DOMAIN_MODEL.md` defines the current rules; and `ARCHITECTURE_EXPLANATION.md` explains why those rules exist.

## Documentation relationship and implementation recency

In the phase-history chain below, arrows mean **newer represented implementation state → older represented implementation state**. The four core documents remain current together and therefore use reading/dependency arrows rather than age ordering.

```mermaid
flowchart TD
    INDEX["docs/README.md<br/>Documentation index"]
    OVERVIEW["PROJECT_OVERVIEW.md<br/>Complete product mental model"]
    HANDOFF["AGENT_HANDOFF.md<br/>Fast takeover path"]

    STATE["ARCHITECTURE_STATE.md<br/>Latest checkpoint"]
    PLAN["IMPLEMENTATION_PLAN.md<br/>Phase sequence and next work"]
    DOMAIN["DOMAIN_MODEL.md<br/>Current normative model"]
    FEATURES["FEATURES_BY_TAB.md<br/>Current UI and roles"]
    EXPLAIN["ARCHITECTURE_EXPLANATION.md<br/>Rationale and evolution"]

    P11I["P11_INTEGRITY_MODEL.md<br/>P11-A/A1/C2A/B/C"]
    P11R["P11_STRUCTURED_REPAIR_DESIGN.md<br/>Frozen R01/R02 catalog"]
    P12["P12 design + acceptance<br/>Backup/restore"]
    P14["P14 design + acceptance<br/>Packaging/licensing"]

    P10A["P10_WORLD_ACCEPTANCE.md<br/>Frozen backend gate"]
    P10P["P10_WORLD_PERFORMANCE.md<br/>Final performance acceptance"]
    P10FINAL["Post-optimization benchmark<br/>Final benchmark artifact"]
    P10OLD["Earlier P10 benchmarks<br/>Superseded diagnostics"]
    HIST["Historical engineering assessment<br/>Obsolete architecture snapshot"]

    INDEX -->|"current work"| PLAN
    PLAN -->|"product model"| OVERVIEW
    OVERVIEW -->|"implemented checkpoint"| STATE
    STATE -->|"normative rules"| DOMAIN
    DOMAIN -->|"user-facing implementation"| FEATURES
    FEATURES -->|"reasoning and history"| EXPLAIN
    EXPLAIN -->|"operational takeover"| HANDOFF

    STATE -->|"release boundary"| P14
    P14 -->|"older frozen phase"| P12
    P12 --> P11I
    P11I --> P11R
    P11R --> P10A
    P10A --> P10P
    P10P --> P10FINAL
    P10FINAL --> P10OLD
    P10OLD --> HIST
```

The historical engineering assessment was written later in wall-clock time than some P10 records, but it describes a much older schema and implementation state. Its position reflects the state represented, not its file timestamp.

## Document catalog

| Category | Document | Contains |
| --- | --- | --- |
| Overview | [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Complete narrative introduction covering the product purpose, user workflows, architecture, domain concepts, security, reliability, repository map, development model, and AI-safe change rules. |
| Handoff | [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) | Fast takeover path, current checkpoint, code map, invariant summary, development commands, and release/support cautions. |
| Development and QA | [`DEVELOPMENT_MODE.md`](DEVELOPMENT_MODE.md) | macOS, Windows and Linux source notes, local model onboarding, isolated authority, exact-scope reset, and QA-J01 setup, fixtures, reports and acceptance limits. |
| Current core | [`ARCHITECTURE_STATE.md`](ARCHITECTURE_STATE.md) | Concise stable implementation checkpoint, current authority sources, read behavior, frozen World state, and deferred work. |
| Current core | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Ordered P0–P14 roadmap, completed phases, phase exit criteria, cross-phase gates, and next work. |
| Current core | [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) | Normative identity, observation, note, evidence, canonical, graph, Person Graph, and World domain rules. |
| Current core | [`FEATURES_BY_TAB.md`](FEATURES_BY_TAB.md) | Complete current tab and Person Profile sub-tab inventory, permissions, workflows, boundaries, and terminology. |
| Current core | [`ARCHITECTURE_EXPLANATION.md`](ARCHITECTURE_EXPLANATION.md) | Long-form architectural memory, design rationale, examples, rejected alternatives, performance decisions, safety stops, and future boundaries. |
| P11 | [`p11/P11_INTEGRITY_MODEL.md`](p11/P11_INTEGRITY_MODEL.md) | State-authority map, fixed invariant registry, read-only checker, note/evidence refreeze, deterministic rebuild, and completed P11 sequence. |
| P11 | [`p11/P11_STRUCTURED_REPAIR_DESIGN.md`](p11/P11_STRUCTURED_REPAIR_DESIGN.md) | Exact R01/R02 whitelist, finding-bound preconditions, execution/refusal rules, safety-stop history, tests, and P11-D boundary. |
| P12 | [`p12/P12_BACKUP_RESTORE_DESIGN.md`](p12/P12_BACKUP_RESTORE_DESIGN.md) | Format-v3 authority closure, registry-owned media, staged restore, failure recovery, and API boundary. |
| P12 | [`p12/P12_BACKUP_RESTORE_ACCEPTANCE.md`](p12/P12_BACKUP_RESTORE_ACCEPTANCE.md) | Frozen backup/restore verification matrix and acceptance result. |
| P14 | [`p14/P14_PACKAGING_LICENSING_DESIGN.md`](p14/P14_PACKAGING_LICENSING_DESIGN.md) | Offline license authority, Windows package layout, installer lifecycle, release versioning, and signing boundary. |
| P14 | [`p14/P14_RELEASE_ACCEPTANCE.md`](p14/P14_RELEASE_ACCEPTANCE.md) | Passed unsigned Windows acceptance and the remaining production release gates. |
| P10 | [`p10/P10_WORLD_ACCEPTANCE.md`](p10/P10_WORLD_ACCEPTANCE.md) | Frozen P10-E World backend PASS/FAIL gates, defect-resolution record, and acceptance decision. |
| P10 | [`p10/P10_WORLD_PERFORMANCE.md`](p10/P10_WORLD_PERFORMANCE.md) | Final performance method, before/after results, scale conclusions, and passing performance decision. |
| P10 benchmark | [`p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json`](p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json) | Authoritative machine-readable post-optimization benchmark matrix. |
| P10 benchmark | [`p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS.md`](p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS.md) | Superseded human-readable incomplete benchmark diagnostics retained for comparison. |
| P10 benchmark | [`p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS.json`](p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS.json) | Historical machine-readable failed/pre-optimization benchmark baseline. |
| Historical | [`historical/engineering_assessment_prepackaging_branch.md`](historical/engineering_assessment_prepackaging_branch.md) | Obsolete schema-v12 packaging/security assessment retained as a non-authoritative snapshot. |
| Examples | [`examples/model-onboarding/README.md`](examples/model-onboarding/README.md) | Instructions for the local model declaration and calibration examples. |
| Examples | `examples/model-onboarding/*.example.json` | Placeholder research, commercial, permissive-license, and calibration inputs. |

## Authority and maintenance rules

- Follow the reading order above. GitHub Issues and linked PRs are the durable current-work tracker; `IMPLEMENTATION_PLAN.md` preserves implementation sequence, qualification and historical phase decisions.
- Update every affected canonical document in each implementation batch; revise obsolete current-state statements rather than layering contradictory patch notes.
- Use P11 documents for frozen integrity, rebuild, repair, revert, and recovery detail.
- Use P12 and P14 documents for backup/restore and Windows release acceptance detail.
- Use P10 documents for the frozen World acceptance and performance record.
- Historical and superseded artifacts are evidence of prior evaluation, not current architecture authority.
- Preserve safety-stop explanations, failed benchmark baselines, and historical decisions rather than rewriting them as if the final state had always existed.
- When a document moves, update repository references without changing runtime behavior or generated assets.
