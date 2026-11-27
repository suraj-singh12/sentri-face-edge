# Coverage matrix

| Surface | Evidence | Disposition |
|---|---|---|
| Authentication/sign-in | `authentication-signin` | Refined shared shell/input/button language |
| Owner onboarding/setup | `22-owner-setup`, `23-owner-setup-validation` | Refined; field-adjacent password validation shown |
| Global shell/navigation | all full-screen comparisons | Refined segmented navigation and quieter header |
| Check a Photo empty | `01-check-photo-empty` | Refined surfaces/controls; workflow retained |
| Notifications | `02-notifications-open` | Refined; critical-warning semantics preserved |
| Review queue/decisions | `03-review-queue-list`, `05-review-recognition` | Refined density and terminology |
| Event details dialog | `04-event-dialog` | Refined dialog/input treatment |
| People grid/list | `06-people-grid`, `07-people-list` | Refined; collections/actions preserved |
| Person overview/nested tabs | `08-person-overview`, `09-person-photos` | Refined; `Event history` integrated |
| Person photos/photo details | `09-person-photos`, `10-photo-details` | Refined; all photo actions preserved; time rule documented |
| Person edit drawer | `11-person-edit-drawer` | Refined forms; Labels terminology integrated |
| Person overflow menu | `12-person-more-menu` | Refined hierarchy; capabilities preserved |
| Events list | `14-events-list` | Refined; neutral Unknown direction |
| World Explore | `16-world-explore` | Refined shared panels/segmented controls; filters unchanged |
| Settings/license/accounts | `18-settings-license`, `19-settings-user-accounts` | Refined cards/forms/account rows |
| Dark theme | `20-settings-dark` | Refined dark surfaces/navigation |
| Narrow layout | `21-people-narrow` | Refined deliberate action wrapping direction |
| Empty/exceptional states | Check empty, World empty, owner validation, dialogs | Representative coverage |
| Person Graph | `13-person-graph` | Refined shared shell/cards/graph canvas presentation |
| World Connections | `17-world-connections` | Refined shared World system and segmented selector |

Limitations: synthetic dev mode tests workflow wiring only, not recognition accuracy. Proposed screens are high-fidelity DOM/CSS prototypes, not production code. Event-list completed-detail variants beyond the representative event dialog should be implementation-verified.
