# Issue #6 comprehensive visual design review — 2026-11-27

Design-first proposal package only. No production-code change, implementation PR, generated frontend asset, backend/schema or architecture change is included.

## Baseline and method

- Product baseline: `v2-hardening-followups` at `e9b7ebafc4aed8b251655751213f45988b30f710` (`e9b7eba`).
- Runtime: loopback-only synthetic/dev fixture; no recognition-accuracy claim.
- Every comparison keeps the left side as an actual current-application screenshot and the right side as a high-fidelity editable SVG/HTML-rendered visual proposal with matching dimensions, state, content, theme and scale.
- A-16 and A-20 are treated as no longer reproducing and are not reopened.
- A-24's earlier full-width-banner overlap condition no longer applies in the corrected merged notification-popover shell; shell toast placement is covered as a design-system rule instead.

## Start here

1. Open `index.html` for the organized numbered gallery.
2. Read `docs/DESIGN_SPECIFICATION.md` for the unified visual system.
3. Read `docs/DECISION_REGISTER.md` for proposal rationale/complexity and finding disposition.
4. Read `docs/COVERAGE_MATRIX.md` for reviewed surfaces and retain/refine decisions.
5. Individual proposal folders `p01`…`p09` contain `current.png`, `proposed.png`, `comparison.png`, and editable `proposed.svg`/`comparison.svg` sources.

## Approval gate

Stop after visual review. The operator must explicitly approve, reject or request revision for each proposal before implementation.
