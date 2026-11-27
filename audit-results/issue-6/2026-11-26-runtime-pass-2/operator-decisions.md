# Operator decisions register — runtime pass 2 findings

Recorded 2026-11-26, operator decision message of 2026-11-26 ~11:50 IST. This register is the authoritative disposition of the A-series findings. It amends [audit-report.md](audit-report.md); where the report text and this register disagree, **this register wins**.

## Intentional behaviour — must remain unchanged

| Finding | Decision |
|---|---|
| **A-11** (World Explore default minimum relationship strength 2) | **Intentional. The default of 2 must remain unchanged.** No fix may alter the default filter. The only residual question — whether zero-state wording should become filter-aware — is *pending design approval* (below); even that may not be implemented without explicit operator design approval. |
| **A-09** (Event date required, prefilled with today's date in the encounter details modal) | **Intentional. Must remain unchanged.** No fix, no redesign, no "date unknown" path work. This finding is withdrawn as a defect. |

## Approved fixes

*None approved yet. No design or implementation work is approved. The operator has approved no item from the improvement plan so far.*

## Pending investigation

| Item | Notes |
|---|---|
| **A-22** picker exclusion of recognition-ineligible enrolled people | Requires a product decision: is manual assignment to enrolled-but-recognition-ineligible people intended? Dev-mode amplification noted in the report; production-path impact unconfirmed. |
| Un-reverified previous-audit findings | Items listed in audit-report.md §4 as not re-verified this pass (F01/F02, F08/F30, F09, F15/F36, F16, F17/F29/F34, F18/F20/F22/F24/F25/F26, F27, F37, F38). |
| Audit coverage gaps | Merge execution, bin restore execution, event-correction execution, recognition-reference management, backup import/restore, integrity/recovery, deep Connections drilldowns, systematic keyboard/screen-reader pass, long-string/dense-data stress, attach-media execution. |

## Pending design approval

Everything else in the improvement plan — including but not limited to:

- A-01 country/location autocomplete exact-match prioritization
- A-02 mandatory individual count validation surfacing
- A-03 redundant match messaging / clipped badge
- A-04 disabled unexplained primary action
- A-12 notes affordance discoverability
- A-14 banner consolidation / role-awareness (incl. F40 remainder)
- The filter-aware zero-state wording question in World (see A-11 above — the default itself is settled and must not change)
- All P3 consistency/polish items (A-05, A-06, A-07, A-08, A-13, A-15, A-16, A-17, A-18, A-19, A-20, A-21, A-23, A-24)

**No item in this section may be designed or implemented until the operator explicitly approves a design proposal.** Design proposals, when prepared, must reference the A-series IDs, be preserved under this audit directory, and record their approval status here.

## Constraints restated

- PR #34 remains draft and must never be merged.
- Evidence preservation is additive only; runtime-pass-1 and earlier evidence must not be altered.
- No product code changes under this audit scope.
