# Concise decision register

| ID | Affected screens | Problem | Proposed change | Rationale | Complexity |
|---|---|---|---|---|---|
| P01 | Review → Event details | `Unknown` context is silently preselected; date presentation conflicts with ISO-style product dates. | Mark context optional, use explicit `Unknown — no context recorded`, present date as `yyyy-mm-dd`. | Makes absence of context intentional without adding unnecessary friction. | Low |
| P02 | Person → Photos → Photo Details | `Added` shows event time rather than import/provenance time. | Split `Event captured` from `Added to system`. | Prevents operators confusing occurrence time with media import time. | Low–medium |
| P03 | Review group detail | `WARN` and `Peek In` are jargon. | Use `Low-quality sample` and `View photo`. | Plain operator language; workflow unchanged. | Low |
| P04 | Person edit drawer | Controlled `Tag` and freeform `Tags` collide. | Rename freeform keywords to `Labels`; update helper and placeholder. | Minimal terminology correction without migrating the controlled Tag concept. | Low |
| P05 | Person profile/header/menu/tabs | Archive/favorite affordances are duplicated, overflow menus differ, and profile `Events` collides with main navigation. | Move archive into the consolidated overflow menu, keep favorite on the star, standardize menu ordering, rename tab `Event history`. | Reduces header crowding and ambiguous accessible names while preserving capability. | Medium |
| P06 | Events list | `Unknown` uses success green; date placeholders conflict with row dates. | Neutral gray unknown chips and `yyyy-mm-dd` date format. | Unknown is neutral absence; one date language reduces scanning errors. | Low |
| P07 | Settings → Machine Accounts | `owner` is duplicated as primary and secondary text. | Keep account name once; use `Current account` metadata. | Removes redundant noise while retaining signed-in context. | Low |
| P08 | World Explore empty canvas | Empty state says nothing about how to begin. | Add compact centered starter card with three concise steps. | Improves discoverability without changing scope or graph semantics. | Low |
| P09 | Owner setup/password creation | 256-character maximum appears only after submit; error is detached. | Show `12–256 characters` before entry and attach validation to Password. | Prevents avoidable submission errors. Final implementation should collapse the space left by the detached banner. | Low |

## Finding disposition

| Finding | Disposition |
|---|---|
| A-05 | Addressed by P04 |
| A-06 | Addressed by P02 |
| A-07 | Addressed by P03 |
| A-08 | Addressed by P09 |
| A-13 | Addressed by P06 |
| A-15 | Addressed by P01 |
| A-16 | No longer reproduces; do not reopen |
| A-17 | Addressed by P05 |
| A-18 | Addressed by P05 |
| A-19 | Addressed by P01/P06 |
| A-20 | No longer reproduces; do not reopen |
| A-21 | Addressed by P07 |
| A-23 | Addressed by P05 |
| A-24 | Full-width banner overlap no longer applies after the merged notification-popover shell. Retain the shell toast-placement rule; no separate visual redesign proposed. |
