# SentriFace Edge documentation map

This directory separates the product overview and current architecture from frozen phase records, historical artifacts, and examples. New contributors and agents should start with the complete project guide, then use the handoff guide and four core documents for implementation work.

## Current status

- P0 through P14 source implementation is complete.
- P10 through P13 are complete and frozen, including all of P11-A through P11-E.
- Historical P14 unsigned Windows 11 x64 installer lifecycle acceptance passed
  for an earlier artifact. The current 2.0.0 unsigned pre-tag candidate passed
  source, build, inspection, and packaged runtime checks.
- Production P14 acceptance remains pending verified signatures, the current
  artifact's disposable-Windows installer and packaged model lifecycle, and a
  clean exact `rc-v2.0.0` or `release-v2.0.0` rebuild.

## Start here

1. [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) — complete product mental model: purpose, problems solved, user features, developer architecture, domain concepts, and safe-change rules.
2. [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) — quick takeover guide, repository map, commands, and release boundary.
3. [`ARCHITECTURE_STATE.md`](ARCHITECTURE_STATE.md) — latest concise implementation checkpoint.
4. [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — phase order, completion state, exit gates, and next work.
5. [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) — current normative entities, authority, lifecycle, evidence, graph, and World contracts.
6. [`ARCHITECTURE_EXPLANATION.md`](ARCHITECTURE_EXPLANATION.md) — detailed reasoning, examples, rejected alternatives, and preserved design evolution.

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

    INDEX -->|"start"| OVERVIEW
    OVERVIEW -->|"implementation takeover"| HANDOFF
    HANDOFF --> STATE
    STATE -->|"phase position"| PLAN
    PLAN -->|"normative rules"| DOMAIN
    DOMAIN -->|"reasoning and history"| EXPLAIN

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
| Development | [`DEVELOPMENT_MODE.md`](DEVELOPMENT_MODE.md) | macOS and Windows source launch, local model onboarding, isolated authority, frontend build, and exact-scope development reset. |
| Current core | [`ARCHITECTURE_STATE.md`](ARCHITECTURE_STATE.md) | Concise stable implementation checkpoint, current authority sources, read behavior, frozen World state, and deferred work. |
| Current core | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Ordered P0–P14 roadmap, completed phases, phase exit criteria, cross-phase gates, and next work. |
| Current core | [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) | Normative identity, observation, note, evidence, canonical, graph, Person Graph, and World domain rules. |
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

- Start with the project overview for the complete mental model, then use the handoff guide and four current core documents for present architecture and project status.
- Use P11 documents for frozen integrity, rebuild, repair, revert, and recovery detail.
- Use P12 and P14 documents for backup/restore and Windows release acceptance detail.
- Use P10 documents for the frozen World acceptance and performance record.
- Historical and superseded artifacts are evidence of prior evaluation, not current architecture authority.
- Preserve safety-stop explanations, failed benchmark baselines, and historical decisions rather than rewriting them as if the final state had always existed.
- When a document moves, update repository references without changing runtime behavior or generated assets.
