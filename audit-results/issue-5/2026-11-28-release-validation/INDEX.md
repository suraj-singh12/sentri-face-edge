# Issue #5 release-validation evidence — 2026-11-28

This directory permanently preserves non-sensitive evidence for the accepted Milestone 3 engineering validation. It intentionally does **not** contain either installer executable or any model-weight bytes.

## Validated build

- Validation run: https://github.com/suraj-singh12/sentri-face-edge/actions/runs/46130684767
- Exact source commit: `efd6a0c06f8ee532dee611889a7a61e2723a75b4`
- Shared standalone application SHA-256: `9d24338c5c8b6060b9d6d1ad6fe2b1e4f5f0041aaa6d99710197e0e6fa109f74`
- Shared standalone application size: `57547776` bytes
- Commercial installer SHA-256: `26405239ac04e54ab05b9fc13dab03bb1ae76aa76043771920eca299e5b24f98`
- Commercial installer size: `63087878` bytes
- Research installer SHA-256: `fd2e5fc39b4bb324c5c441714cc807938abacf34f9674d06d58be64a2421776b`
- Research installer size: `224658129` bytes
- Research payload: exact pinned `det_500m.onnx` and `w600k_r50.onnx` only; see the inspection JSON files for their hashes.
- Commercial packaged/installed closure: zero ONNX/model-weight files.

The Commercial and Research provenance records independently record the same standalone-application SHA-256 and exact source commit.

## Executed acceptance evidence

Passing evidence preserved here covers:

- packaged and installed artifact inspection for both variants;
- identical application-binary provenance;
- Research first-start automatic provisioning;
- model activation and restart persistence;
- active-model preservation across same-version Research repair and both variant transitions;
- identical packaged licensing enforcement, including HTTP 402 for an unlicensed ordinary person read;
- exact-executable outbound firewall policy and removal after uninstall;
- populated database/configuration preservation across repair, transitions, restart, uninstall and reinstall;
- downgrade refusal on the disposable runner using a simulated newer installed version.

Passing comparison reports:

- `repair-comparison.json`
- `research-transition-comparison.json`
- `research-repair-comparison.json`
- `research-restart-comparison.json`
- `commercial-transition-comparison.json`
- `reinstall-reconnect-comparison.json`

Explicitly not automated in this rehearsal:

- interrupted or failed installation;
- deliberately failed database migration;
- upgrade from a supported earlier release;
- production-license activation or license-state preservation (no production license was issued).

## Working-tree dirty-state determination

The validation provenance records `working_tree_clean=false`. The exact cause is generated frontend line-ending noise, not operator or release-source modification.

Evidence:

1. The validation log's `Validate source whitespace` step names exactly these generated files with LF/CRLF normalization warnings:
   - `src/sentriface/ui_static/assets/index-DDzZSMXK.js`
   - `src/sentriface/ui_static/assets/index-QN-BOvXF.css`
   - `src/sentriface/ui_static/assets/vendor-mantine-DmN2SNem.js`
   - `src/sentriface/ui_static/assets/vendor-mantine-DrLRgAFy.css`
   - `src/sentriface/ui_static/assets/vendor-react-t-ACWIy7.js`
2. A controlled local checkout simulation with `core.autocrlf=true` showed that exactly those five tracked asset files contain newline characters and are checked out with CRLF. The other generated asset bundles are single-line files and have no line endings to convert.
3. Replacing CRLF with LF, as the Vite production build does on Windows, made exactly those five files appear modified and produced the same five Git warnings seen in validation.
4. `frontend/node_modules`, `build/`, `dist/` and `.model-cache/` are ignored; they do not contribute to source-tree dirtiness.
5. The routine installer evidence gate (`scripts/prepare_ci_installer.py`) hard-fails if any dirty path is outside `src/sentriface/ui_static/`. That gate passed in routine CI for the same source content. No evidence indicates any non-generated source change.

Conclusion: no source changes beyond generated `src/sentriface/ui_static/` assets occurred. The five differing files are generated line-ending normalization artifacts. This should still be fixed before canonical release production builds, because canonical provenance should be clean and deterministic.

## Delivery restrictions and separate Commercial candidate

- The exact validated Commercial installer was not retained as an executable artifact by the validation workflow.
- The exact validated Research installer was not uploaded or retained because this public repository's GitHub Actions artifacts are not a controlled/private delivery path. It is unavailable after the ephemeral runner ended; only its checksum/provenance are preserved.
- A separately built routine Commercial engineering candidate exists at GitHub artifact `15258895735` with SHA-256 `93e5e31b853e67afbaad341a8fcac851cdc08e453f6d3f2fb34526949e15eca4` and size `63090268` bytes. It is not byte-identical to the exact validated Commercial installer and must not be represented as that installer.
- No public Research upload, production license issuance, release publication, merge, or `main` change is authorized by this evidence.
