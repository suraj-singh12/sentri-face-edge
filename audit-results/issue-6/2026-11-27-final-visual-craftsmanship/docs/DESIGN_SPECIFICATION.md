# SentriFace Edge — unified visual refinement specification

Baseline: merged `v2-hardening-followups` HEAD `e9b7ebafc4aed8b251655751213f45988b30f710`. Design only: proposed screens are DOM/CSS prototypes injected into the running synthetic/dev application. No product code, generated assets, APIs, schema or architecture changed.

## Principles

1. Evidence before decoration: recognition decisions, provenance, timestamps, warnings and actions remain visible and authoritative.
2. Quiet desktop confidence: refine SentriFace's existing teal/neutral identity, not a generic dashboard redesign.
3. One component language across navigation, cards, inputs, buttons, badges, menus, dialogs and notifications.
4. Calm density: reduce crowding and noise without shrinking controls or metadata merely for cleanliness.
5. Role/risk honesty: critical blocking warnings remain inline; unavailable capabilities are never implied.
6. Responsive composure: narrow layouts wrap actions deliberately and preserve every capability.

## Visual foundation

| Area | Proposal |
|---|---|
| Color | Quieter neutral light/dark surfaces; slightly restrained teal accent; neutral `Unknown` state |
| Surfaces | Mostly opaque cards, lower-alpha borders, consistent 12 px panel radius, low ambient shadow |
| Typography | Existing system/Inter direction retained; clearer hierarchy, tighter headings, sentence-case actions |
| Controls | Consistent height/radius/weight; filled teal only for primary forward action; bordered neutral secondary; light red destructive |
| Inputs | Quiet border, restrained teal focus ring, adjacent help and field-level validation |
| Navigation | Primary and in-page selectors use shared segmented-control language |
| Menus | High-frequency/destructive actions remain visible; long low-frequency commands may move to overflow without losing capability |
| Dialogs/drawers | Quiet overlay, compact hierarchy, validation adjacent to fields |
| Empty states | Explain the next useful action without decorative filler |

## Integrated P01–P09 baseline

- **P01 Event details:** consistent input hierarchy and prominent authoritative event metadata.
- **P02 Photo details:** all existing photo-management actions remain. Event time is explicitly labeled. System-added time appears only when authoritative record metadata exists; missing time is never invented.
- **P03 Review terminology:** plain-language quality labels/actions integrated without extra badge noise.
- **P04 Labels:** freeform operator keywords are Labels; controlled system Tags remain distinct.
- **P05 Profile actions:** preserve useful direct shortcuts and every capability; move only long low-frequency reference management into overflow where space requires it.
- **P06 Events:** neutral `Unknown`; move toward unambiguous ISO-style date display while preserving picker behavior.
- **P07 Machine Accounts:** consolidate duplicate owner-like rows only when they are truly the same account; server authorization remains truth.
- **P08 World:** empty states explain evidence thresholds and next actions; default `CO_OBSERVED` + minimum strength 2 behavior remains unchanged.
- **P09 Owner setup:** remove the detached validation banner/blank gap; keep password requirements and errors readable beside the password field.

Implementation is not authorized by this package. Any approved implementation must happen in `frontend/` source, rebuild generated assets normally, and pass focused regression/CI coverage.
