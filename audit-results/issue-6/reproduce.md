# Reproduce the current baseline safely

[INDEX](INDEX.md) · [Source development](../../docs/DEVELOPMENT_MODE.md) · [Coverage boundaries](coverage.md)

Use source `b457f0a723e845dd1a92a07a577072c85146c89a`, read AGENTS.md and the actual run.sh first, and create a new disposable authority. Never point capture helpers at an operator or installed-product authority. This library is an audit record; it is not a fixture database to restore over operator data.

The documented entry is `./run.sh dev`, UI `http://127.0.0.1:8765`. In this VM the launcher attempted dependency refresh and could not satisfy its setuptools minimum from installed packages while downloads were deliberately disabled. Existing Python3.12 dependencies and the repository's QA source entry were used instead: `PYTHONPATH=src .venv312/bin/python -m sentriface.ui --runtime dev --data-dir <new-disposable-directory> --port 8765`. Do not make an offline-index workaround into a product dependency change. Build frontend source using the repository's documented command, with audit build output separate from tracked generated assets.

Create the first local account through the real UI, retain its password privately and acknowledge disposable backup risk only for this authority. Helpers expect a private ignored capture root at `qa-fixtures/runs/issue-6-audit`; capture_host.py reads private account/browser state there. Regenerate those files for a new run rather than borrowing operator credentials. Do not print password-input accessibility snapshots or browser storage. The helper uses the application's ordinary session header, not an authorization bypass.

Follow J01–J34 in the INDEX for actual named controls, intermediate states and outcomes. Generated fixture PNGs under fixtures/ are non-biometric patterns; invalid-image.png is intentionally invalid input. Source synthetic mode uses one whole-image face/hash result and cannot validate real recognition quality. Model onboarding J32 used already authorized local files in a separate fresh source authority. J41 reused the repository's existing real-photo QA scenario with reviewed local inputs; those files and declarations are deliberately absent from public Git. No download or privacy permission is implied.

`tooling/role_sweep.py` and viewport_sweep.py execute in the capture helper namespace after the real account/fixture prerequisites. dense_fixture.py refuses a pre-existing authority and uses existing test/store functions while the fresh authority is stopped; it qualifies layout reads only. genuine_supplement.py accepts an explicitly authorized local actor/corpus and delegates to existing QA. Inspect each helper and its preconditions before reuse. They are capture tools, not product dependencies or self-contained acceptance suites.

After capture and individual privacy/visual review, run finalize_library.py, reconcile.py and seal_library.py from the repository root. Do not promote raw snapshots, logs, credentials, models, databases or backups. finalize_library.py copies reviewed public originals or separately identified sanitized captures unchanged. Reconciliation never automatically earns PASS. seal_library.py validates image bytes/dimensions, registered assets, denominator arithmetic, local Markdown links and file hashes; it does not substitute for semantic or visual review.

Relevant checks already passed: source frontend build, 141 frontend tests, 12 focused audit/QA-foundation tests plus two subtests, four role-negative403 checks, and final bounded genuine inference/restart/cleanup. The failed intermediate genuine capture attempt is retained as an automation selector error. No full backend suite, Windows qualification, VoiceOver acceptance or general photographic-volume acceptance is claimed.

The versioned private archive is preserved outside the disposable QA root. Its exact path, archive SHA-256 and remote evidence commit belong to the operator's delivery receipt, avoiding circular identifiers inside the committed manifest. Copy that archive and checksum to a separate physical or off-VM destination, then verify the copied SHA-256 before considering it a second independent backup. No such second backup is currently verified.

## Pass 2 milestone

Resume from the existing non-PASS plan without deleting pass-one capture files. J02, J07, J15, J20, J22, J24 and J33 describe new actual UI interactions and exact limitations. Password updates, account disablement and backup deletion were limited to newly created or existing **audit-only disposable** account/backup objects. The backup deletion prompt is native browser UI and was observed via the Playwright dialog event; raw credential snapshots and private originals must not be committed. The pass-two plan retains all 253 original non-PASS identifiers, including rows now executed; it is not a smaller denominator.

## Pass 2 continuation B

Journey continuations J01/J03/J05/J06/J08/J09/J11/J13/J20/J22/J24/J32/J33/J34 record the disposable source authority, ordered actions, outcomes and limitations. For J11, perform ownership moves and erase only on expendable synthetic data; the observed erase refusal is scenario-specific. For J32, use only already-authorized local models; do not download or bypass the setup gate. Private path-bearing originals and model parsing errors are not public.

## Pass 2 continuation C

J17/J23/J15/J07/J10/J24/J04/J29 capture duplicate-attachment recovery, private activity filters/export, Event mentions, safety navigation, Person edit and note correction. Use only synthetic disposable records; do not publish activity logs or exports. The note-link observation must not be interpreted as permission to change historical authority.

## Pass 2 continuation D

J12/J14/J07/J20/J23/J21/J28/J27/J10 describe the synthetic manual-association, delete cancellation, contrasting filters, role gating, recovery destination refusal, integrity, guarded revert and profile-photo experiments. System details and recovery paths remain private. Do not bypass identity uniqueness or modify storage to force a supported revert.

## Pass 2 continuation E

J08/J17/J19/J18 record generated non-biometric folder inputs, grouping and attachment recovery, Explore and Connections. Folder upload paths observed in requests are synthetic relative paths. Do not replace Reference Only media with Encounter authority or bypass the targeted-draft guard. The generated noise is for the source synthetic detector only and says nothing about real inference.

## Pass 2 continuation F

Use generated non-photographic images in a disposable synthetic authority. For the cancellation path, use enough images to keep processing visible and select Cancel Processing. The Note creation error occurred once and a separate retry succeeded; its precise trigger and backend consequences remain unresolved. Continue from the existing execution plan, and preserve the original Pass 1 and later milestones.

## Pass 2 continuation G

J03, J06, J12, J18 and J19 describe new synthetic UI paths. The local source application can display an absolute upload path; withhold any capture that exposes one. The three published J06 form viewports were checked individually and have no visible path despite legacy filenames. Do not publish raw accessibility snapshots.

## Pass 2 continuation H

J27 documents a supported guarded revert using two same-name synthetic profiles with identical initial observation metadata, one with an approved generated Reference, created and merged through product controls. The earlier default observation times differed and were correctly refused. Use only disposable authorities; never force database state or weaken server preflight. A changed plan or dependent operation can still be refused.

## Pass 2 continuation I

Use the existing dense synthetic authority and its QA fixture; do not use operator data. World Explore and Connections each have more than one People page. For the measured-pattern case, create and finalize a generated-image Event through the normal workflow, then clear its location in Correct Encounter. Connections displays the resulting missing-location data-quality measurement. A path-bearing Check a Photo frame remains private.

Continuation J: on a disposable authority, create more than 10 Activity entries by signing in through the UI, choose page size 10 and use Next and Previous. Populated logs are private.

Continuation K: use a generated 12×12 flat non-photographic PNG in source synthetic mode, enter synthetic Event details and select the explicit low-quality acceptance choice. Complete a disposable synthetic Person decision and inspect recognition coverage. Do not treat this as real biometric inference.

Continuation L: use the generated [proof-only duplicate fixture](fixtures/proof-duplicate-synthetic.png) on a fresh disposable synthetic authority. Create a Person as proof-only, then use the same generated scene in separate synthetic Events to exercise the existing-profile hint, reuse and explicit override. Never use Reference Only material as an occurrence upload or bypass the admission guard.

Continuation M: import a generated scene already finalized in the disposable authority and observe exclusion; discard that session. Import the distinct [queue quality fixture](fixtures/queue-poor-synthetic.png), group, enter synthetic Event details and choose a low-quality decision before completion.

Continuation N: use a disposable source authority without portable backups; Settings → Backups & restore shows the empty state. Create a first portable backup; immediately capture a second Create Backup to sample its brief progress state and then the verified result. Keep backup artifacts private.

Continuation O: use a fresh dedicated source authority. Submit an empty owner form, then a deliberately invalid account name with a temporary test password; correct the name and immediately capture submission. Keep all credential-bearing frames and raw accessibility snapshots private.

Continuation P: create a Viewer on a dedicated disposable authority in synthetic source mode; stop it and launch the same authority with `./run.sh onnx` with no models installed. Sign in as Viewer to see the owner gate, then sign out and sign in as owner. Do not use or modify operator model files.

Continuation Q: with a signed-in synthetic source application on a disposable authority, stop only its source server and click Refresh. Restart the same server, wait for its startup message, retry Refresh, then reload and sign in. Record the actual response and do not interpret a stale-session 401 as server downtime.
