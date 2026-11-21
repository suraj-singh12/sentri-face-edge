# Coverage, equivalence and missed-scope review

[INDEX](INDEX.md) · [Exact totals](execution-summary.json) · [Semantic summary](semantic-summary.json) · [Candidate summary](coverage-summary.json)

**PARTIAL. The requested exhaustive BEFORE acceptance is not achieved.** Every discovered source contract has a recorded result or gap, but recording a gap does not qualify the behavior. The evidence is useful for review and targeted continuation; Gate 1 remains open. No redesign or implementation follows automatically.

## Independent denominators

- The source oracle contains 832 JSX definition sites: 528 control definitions, 58 overlay definitions, 133 feedback/media sites, 101 containers/composites and 12 transitions. These are implementation sites, not 832 unique visible controls.
- The conservative control matrix counts 598 control/overlay/transition sites. Exact accessible-name presence yields PARTIAL candidate attribution only. Dynamic names, shared labels and unnamed composites require manual attribution. Its percentage is not completed coverage.
- The semantic oracle contains 60 operator task contracts and 509 bounded branch/state contracts. [Task coverage](task-coverage.csv) and [branch coverage](branch-coverage.csv) independently map them to ordered runtime evidence. Source oracle runtime columns mirror that reconciliation without changing the original contract columns.
- [Surface register](surface-register.csv) counts semantic pages, collections, profile panes and drilldowns; it excludes dialogs, themes, roles and transient states. [Captured overlays](captured-overlays.csv) counts distinct observed accessible role/title pairs. Neither is a claim that all source components have been rendered.
- A runtime journey is one ordered J record. A sampled visual-state key is UX/state/role/fixture-kind/theme/viewport, excluding rejected audit attributions. Repeated Viewer attempts with the same key are deduplicated; native geometry remains separate. Public image count includes separately labeled sanitized derivatives. Private genuine captures are a separate supplement, never public image evidence.

At pass-one freeze (retained checkpoint `27a0532`), branch results were **256/509 PASS (50.29%)**, **71/509 PARTIAL**, **170/509 NOT RUN**, **11/509 BLOCKED**, and **1/509 FAIL**. Executed evidence, including partial and failure, is **328/509 (64.44%)**. All **60/60 tasks** have some execution evidence, but **0/60 tasks** qualify every branch: **59 PARTIAL, 1 FAIL**. See machine-readable summaries for capture and source-candidate totals.

## Sampled equivalence classes

| Axis | Actual sample | Bound / unsampled behavior |
| --- | --- | --- |
| Roles | Administrator broad workflows; Viewer, Operator, Custodian and Technician real sign-ins, profiles, Event actions and permitted Settings; four independent forbidden requests returned 403 | Does not qualify every mutation under every role. Viewer Favorite exposes an action subsequently refused. Backend holds. |
| Themes / CSS sizes | Six shell destinations at 1366×768 Day, 1280×800 Night, 900×700 Night and 1440×900 Night; 1440×900 Day throughout; compact Explore selectors | Identical shared controls were not repeated in every combination. All nested dialogs at narrow size, browser zoom and systematic contrast remain unqualified. |
| Native macOS | Six full browser windows at actual DPR2; measured 1280×695 outer/1280×608 content; one headed content capture and IAB sign-in | VM clamps larger window requests. CSS emulation is not proof of larger native desktop geometry. No Windows, installer or packaged lifecycle qualification. |
| Data | Empty first-run, UI-created synthetic data, 30-Person/30-Encounter media-free stopped-authority fixture, long Note and names, pagination and dense cluster | Layout fixture is not recognition throughput, volume acceptance, multi-face input or UI creation evidence. Synthetic detector always gives one face. |
| Inference | Whole-image/hash synthetic for broad traversal; existing authorized real ONNX/photo pair privately passed completion, refresh and restart | Genuine multi-Person/multi-face/no-face corpora and visual volume remain unavailable or unrun. No downloaded model/photo. |
| Timing | Actual loaders, toasts, submitting state, stale conflict, restart and import retry | Capture helper waits250ms plus named readiness checks. Source ordinary toast default4500ms is not a measured duration for every frame. No fabricated timing or screenshot manipulation represented as runtime. |

## Exact remaining work and blockers

All individual gaps are enumerable in branch-coverage.csv and task-coverage.csv, with the required source capability and starting-state contract. **NOT RUN is work remaining, not an environment blocker.** Significant remaining work includes invalid authentication/sign-out/session expiry; change-password submit; invalid/failed model setup and non-owner gates; recovery setup/error/non-admin states; duplicate identity warnings and Check a Photo defer/discard/explicit-target interruptions; folder import and upload failure/retry; successful group discard after Event metadata; less common review conflicts; collection filter/sort alternatives; edit validation and selected Note mentions; merge reference-cap/conflict boundaries; full destructive/expiry history; Event filters and REASSIGN; all Connections facets/drilldown failures; account updates and backup deletion/error variants; integrity repair plans and successful guarded merge reversion; more tooltip/popover/focus branches and cross-feature refresh/context loss.

The **11 BLOCKED** rows identify actual environment/input boundaries: seven packaged-license states, separate recovery-drive selection, and three absent suitable photographic zero/multiple-face prerequisites. Do not bypass source platform policy or manufacture frontend gates. A source-mode Business model option is selection evidence, not commercial entitlement or signed license activation. At that checkpoint critical/repair findings and safe merge-revert success were NOT RUN; continuation H later establishes one supported synthetic revert, while integrity-repair findings remain unrun.

The **FAIL** is J33's group discard offered before Event details: confirmation proceeds to a server refusal, with both pending groups preserved. Whole-session discard succeeds. This is an affordance/sequence failure, not lost identity authority.

## Final missed-scope answers

Yes, menus/modal and secondary recovery branches remain unexecuted; their source rows are not silently passed. Multiple entry points are preserved in source-map/reuse-map and journey records (Reference Only Add Face/Manage References, Event Attach/Review, profile/global Events, graph/World proofs). Not every warning, tooltip or permission transition was observed. Source definitions without reliable attribution remain NOT RUN in the candidate matrix. Captures link to journey, role, theme, dimensions, fixture and SHA through capture-register and manifest; raw paths/snapshots are private. Six native windows supplement content viewport originals. Windows-specific claims remain blocked/unqualified.

Public preservation is a checkpoint, not a declaration of audit completion. The next audit pass should select the remaining source rows directly, exercise their real prerequisite states, and reconcile outcomes before approving Figcraft's design scope.

## Pass 2 milestone

The current machine-readable semantic summary supersedes the historical pass-one counts above. Explicit actual UI observations qualify selected authentication, queue discard, Event filters/correction, account and backup deletion branches; composite contracts remain PARTIAL where required variants were not demonstrated. The original pre-metadata group-discard FAIL remains. See [the 253-row pass-two plan](pass2-execution-plan.csv) and current [branch ledger](branch-coverage.csv). Unexecuted rows remain planned, not blocked by assumption.

## Pass 2 continuation B

Current original source-contract totals: **291 PASS, 76 PARTIAL, 131 NOT RUN, 9 BLOCKED, 2 FAIL / 509**. One additional discovered Encounter discard path is tracked separately in [discovered-branches.csv](discovered-branches.csv), without changing the original denominator. Actual ONNX zero-face evidence uses generated non-photographic input; multiple-face qualification remains open. Non-owner model setup was not established: the authenticated application API refused the attempted fixture with `models_required`. All remaining NOT RUN rows are outstanding work, not assumed blockers.

## Pass 2 continuation C

The current original 509-contract ledger is **299 PASS, 79 PARTIAL, 119 NOT RUN, 9 BLOCKED, 3 FAIL**. Additional discovered Encounter discard remains tracked separately. The third FAIL is the observed Person Note mention correction path; active versus historical link semantics require engineering investigation. Duplicate attachment validation, retry refusal, reload and cancel were tested; an actual backend planning failure remains partial. Technical log evidence is private.

## Pass 2 continuation D

Original 509 source contracts: **308 PASS, 76 PARTIAL, 112 NOT RUN, 9 BLOCKED, 4 FAIL**. Additional discovered Encounter discard remains separate. The newly tested profile-photo preference persists as a gallery badge but is initially displayed inconsistently; the resulting FAIL is scoped to that synthetic profile. A fresh merge was refused by the real guarded-revert check; a supported prepared/successful revert was then NOT RUN; continuation H later executed one supported synthetic case.

## Pass 2 continuation E

Original 509 contracts: **324 PASS, 77 PARTIAL, 93 NOT RUN, 9 BLOCKED, 6 FAIL**. Additional discovered Encounter discard remains separate. Nested subfolder suggestion and a Reference-only attachment retry are newly observed FAILs; see [F24 and F25](findings.md). Explore background click did not clear selection, while Reset canvas did; source has no background-clear handler, so that original inventory contract remains PARTIAL pending clarification.

## Pass 2 continuation F

The unchanged 509-contract denominator now contains 334 PASS, 79 PARTIAL, 81 NOT RUN, 9 BLOCKED and 6 FAIL. A successful retry and one earlier error are both preserved for no-photo Note creation. Concurrent correction refusal does not qualify the unobserved stale-attachment revision branch. See the [branch ledger](branch-coverage.csv) and [execution plan](pass2-execution-plan.csv).

## Pass 2 continuation G

The unchanged 509 source contracts now contain 343 PASS, 79 PARTIAL, 72 NOT RUN, 9 BLOCKED and 6 FAIL. One PASS is a documented correction of the previously captured J17 duplicate-finalized-media refusal; the other eight reflect newly executed branches. See [the ledger](branch-coverage.csv).

## Pass 2 continuation H

The unchanged 509 source contracts now contain 346 PASS, 79 PARTIAL, 69 NOT RUN, 9 BLOCKED and 6 FAIL. Four of 60 task contracts are fully covered. The three newly passed branches cover one supported guarded merge-revert plan, confirmation/cancel and execution; arbitrary merge shapes remain outside that evidence.

## Pass 2 continuation I

The unchanged 509 source contracts now contain 349 PASS, 78 PARTIAL, 66 NOT RUN, 9 BLOCKED and 7 FAIL. Four of 60 task contracts are fully covered. Connections overview pagination is FAIL because its page-two cluster empty message contradicts the scope total and earlier page; navigation itself advanced and Reset returned to page one. The independently created missing-location Event supports a measured pattern, not a general inference claim.

Continuation J qualifies Activity log next/previous on 13 generated sign-in/startup events. Source contracts: 350 PASS, 78 PARTIAL, 65 NOT RUN, 9 BLOCKED, 7 FAIL of 509.

Continuation J also qualified the Person Event date, location, context and search filter contract on contrasting synthetic Events. Current source contracts: 351 PASS, 78 PARTIAL, 64 NOT RUN, 9 BLOCKED, 7 FAIL of 509.

Continuation K qualifies the explicit low-quality acceptance alternative with a generated synthetic input. Current contracts: 352 PASS, 78 PARTIAL, 63 NOT RUN, 9 BLOCKED, 7 FAIL of 509. Refresh in the initial Event dialog was sampled but does not fully qualify all interruption stages.

Continuation L qualifies the proof-only duplicate hint, existing-Person choice and explicit new-Person override using a generated synthetic fixture. Current source contracts: 355 PASS, 78 PARTIAL, 60 NOT RUN, 9 BLOCKED, 7 FAIL of 509. An earlier fixture was separately refused as Reference Only material; the guard was respected.

Continuation M qualifies finalized-media exclusion and the Review Photos low-quality decision on disposable synthetic inputs. Current contracts: 357 PASS, 78 PARTIAL, 58 NOT RUN, 9 BLOCKED, 7 FAIL of 509.

Continuation N qualifies empty portable-backup state and creating feedback. Current source contracts: 359 PASS, 78 PARTIAL, 56 NOT RUN, 9 BLOCKED, 7 FAIL of 509. The distinct separate-drive safety copy remains unqualified.
