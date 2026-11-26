# Coverage matrix — Issue #6 runtime pass 2 (2026-11-26)

| Area | Viewer | Operator | Custodian | Technician | Admin | Depth |
|---|---|---|---|---|---|---|
| Sign-in / forced password change | ✔ | ✔ | ✔ | ✔ | ✔ | full journey incl. rejection of reusing admin-set password |
| Check a photo (recognize) | nav present | ✔ | ✔ | nav present | ✔ | upload → STRONG MATCH results, empty state, escape/validation |
| Review photos queue (upload→group→details→identity→relations→finalize) | correctly absent | ✔ | ✔ | correctly absent | ✔ | full lifecycle ×5 events, all step types, browse-people assignment, per-pair relations, exclusion |
| People grid/search/filter/group/sort | ✔ | ✔ | ✔ | ✔ | ✔ | search, grouping, collections sidebar, stats cards |
| Profile: overview/photos/sightings/events/associations/activity | ✔ | ✔ | ✔ | ✔ | ✔ | all tabs read; edit drawer; favorite; photo details panel |
| Archive → Archived collection → restore | — | — | ✔ perm | — | ✔ | executed; toast + auto-backup verified |
| Delete → Bin | — | — | ✔ perm | — | ✔ | dialog verified (type-to-confirm); execution not completed |
| Merge duplicates | — | — | — | — | ✔ | dialog verified; execution not completed |
| Notes + @mentions | ✔ view | ✔ | ✔ | ✔ | ✔ | editor verified in source; no visible entry affordance (A-12) — editing not executed |
| Events list/detail/filters | ✔ | ✔ | ✔ | ✔ | ✔ | list, filters, detail with participants/relations/media |
| Event corrections/attach media | — | ✔ | ✔ | — | ✔ | buttons present; execution not completed |
| World Explore canvas/inspector/filters | ✔ | ✔ | ✔ | ✔ | ✔ | discovery click, canvas, inspector, evidence filter analysis |
| World Connections | ✔ | ✔ | ✔ | ✔ | ✔ | tab reached; deep drilldowns not completed |
| Settings: License | ✔ visible | ✔ | ✔ | ✔ | ✔ | read |
| Settings: Backups — create | — | — | ✔ executed | — | ✔ | backup created successfully; list populated |
| Settings: User accounts | — | — | — | — | ✔ | read; role badges, MUST CHANGE PASSWORD state |
| Settings: Integrity/System/Activity/About | partial | partial | partial | ✔ technical sections | ✔ | captured; not deeply exercised |
| Dark theme | — | — | — | — | ✔ | high quality, consistent |
| Narrow window (760px) | — | — | — | — | ✔ | layout holds; minor truncation |
| Recognition references management | — | — | — | — | partial | button present; flow not exercised |
| Keyboard-only navigation | not systematically tested — Mantine baseline focus behavior observed incidentally |
| Import/restore backup, integrity/recovery execution | not tested (destructive-environment risk in shared audit data) |

**Honestly not tested or incomplete**: merge execution to completion, bin restore execution, event correction execution, recognition-reference add/remove, backup import/restore, integrity recovery flows, deep Connections drilldowns, systematic keyboard/screen-reader pass, long-string stress (very long names), dense-data stress (>50 people), attachment of media to existing events. These are coverage gaps of this audit, not product defects.

---
