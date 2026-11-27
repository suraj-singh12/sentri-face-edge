# SentriFace Edge unified visual design specification

Baseline reviewed: `v2-hardening-followups` at `e9b7ebafc4aed8b251655751213f45988b30f710` in the synthetic/dev runtime. This is design evidence only; no product code, schema, generated asset or architecture change is included.

## Principles

1. **Calm authority:** a dependable offline professional tool, not a decorative dashboard.
2. **One decision per visual unit:** one dominant interpretation and one clear next action.
3. **Plain-language evidence:** no internal jargon where operator-facing wording is possible.
4. **Preserve the existing language:** retain the teal accent, soft neutral surfaces, compact desktop density, radii and quiet borders.
5. **Progressive disclosure:** metadata remains available without duplicating primary scanning information.
6. **Permission and safety honesty:** blocking safety conditions stay visible; unavailable or destructive actions are never disguised.

## Typography

Retain the current system sans-serif stack.

| Role | Size | Weight | Use |
|---|---:|---:|---|
| Product/page title | 20–24 px | 700 | product name and primary page headings |
| Section/dialog title | 14–16 px | 700 | cards, dialogs, inspectors |
| Body/action | 12–14 px | 500–700 | controls, rows, card content |
| Metadata/helper | 10–12 px | 400–500 | captions, dates, explanations |
| Compact badge | 9–10 px | 700 | short status labels only |

Use sentence case for user-facing copy. Do not repeat the same status in a title, subtitle and badge. Dates and counts should align and use tabular numerals where practical.

## Spacing and rhythm

Use the existing 4 px spacing unit: 4 px for icon/text gaps, 8 px inside compact controls, 12 px for dense card/form rhythm, 16 px between sections, 24–32 px for major separation. Dense data cards generally use 10–14 px inner padding; dialogs may use 20–28 px. Empty states should be intentionally composed, not merely unused whitespace.

## Colour and semantic states

| Purpose | Rule |
|---|---|
| Primary/selected | Existing saturated teal/green and pale teal selected fill |
| Neutral or unknown | Gray/tinted neutral, never success green |
| Quality caution | Amber tint/text; not an alarm unless blocking |
| Destructive | Red or red tint, visually separated from primary actions |
| Local/privacy information | Blue tint, sparingly |

`Unknown` means missing or unspecified information; it is not a positive result. Colour is never the only signal.

## Component rules

- **Shell/navigation:** retain the compact header, notification bell and account menu. Nonblocking warnings stay in the popover; critical blocking states may remain inline. Toasts must not cover navigation or persistent notices.
- **Cards/rows:** one title, one primary action and at most one status badge per decision unit. Overflow menu order: utility/identity, relational actions, separator, state-changing/destructive actions.
- **Forms:** constraints are visible before submission; validation attaches to the responsible field. Meaningful optional fields say `(optional)`. Helper copy is one or two short lines.
- **Dialogs/drawers:** one task per surface, explicit required/optional state, primary confirmation bottom-right. Drawers remain narrow working panels.
- **States:** empty states explain the next useful action. Errors identify scope and recovery. Loading preserves layout shape where practical.

## Product-specific language

- Review quality uses `Low-quality sample`; inspection uses `View photo`.
- Person freeform keywords are `Labels`; they do not collide with controlled `Tag`.
- Person profile event history is distinct from main navigation `Events`.
- World empty states guide the first selection without changing evidence scope, minimum strength, cluster membership or weaker-links behavior.
- Machine account names appear once; current-account state becomes metadata.

## Accessibility and responsiveness

Maintain WCAG-AA-oriented contrast, visible focus states and at least approximately 28–32 px pointer targets in dense desktop controls. Narrow layouts should wrap toolbar groups before truncating critical labels. Duplicate visible names must not create ambiguous accessible names.

## Non-goals

No change is proposed to recognition thresholds, graph calculations, evidence semantics, backup/restore behavior, authorization, schema, offline architecture or generated frontend assets.
