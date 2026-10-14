# Windows 0.1.0 product version and installer verification

Date: 2026-10-14 (Asia/Seoul). Branch: `feat/windows-installer-i18n`.
Source base: `ffd46dc0c3e6f7a3aca749309604efa7f6cbf0a1`, with uncommitted changes.
The user explicitly authorized aligning the Windows product to 0.1.0 after the
installer language implementation. This is local build verification, not a
published release or evidence that the user's installed application was updated.

## Implemented version contract

- Tauri configuration, desktop package, npm lockfile root, Cargo package and Cargo
  lockfile root agree on `0.1.0`.
- The Windows Installer workflow reads the metadata version from Tauri config.
  The metadata generator rejects disagreement among the product version owners.
- Node and Rust dependency entries are unchanged. Backend/frontend component
  package versions, Docker tags, remote Releases and published tags are outside
  this Windows version transition and remain part of the deployment roadmap.
- Installation identity, paths, downgrade protection and SQLite/Ladybug schema
  compatibility are unchanged. Existing higher-numbered development installations
  are not automatically overwritten by this lower-numbered build.
- The actual host is rebuilt with a fresh target directory. The previously fixed
  sidecar is reused only after verifying its binary hash and unchanged source and
  backend lockfile. Its product identity comes from the bundled payload manifest.

## Evidence and completion

Evidence root: `artifacts/windows-installer-version-0.1.0-20261014/`.
`baseline.json` and `before-version-change/` preserve the previous product version.
`version-dependency-check.json` records unchanged dependency entries.
`build-inputs.json` records the inputs used by this local build.
The related pytest selection passed **112 tests**, including five negative cases
for drift among product version settings. Installer and supply-chain contract
checks passed. Full backend/frontend suites were not run for this version change.

The actual build completed with exit 0 in **618.52 seconds**. The single output is
`artifacts/windows-installer-version-0.1.0-20261014/target/x86_64-pc-windows-msvc/release/bundle/nsis/Angmoo_0.1.0_x64-setup.exe`.
Size: **277,827,413 bytes**. SHA256:
`78ffd5f2b3586080676536e8aa794ef17ee835c7c5529ee0dda89146debd8d76`.
Authenticode is `NotSigned`; this is an unsigned local candidate.

The installer and its extracted `angmoo-desktop.exe` both expose product/file
version `0.1.0`. The generated NSIS script defines version `0.1.0`, numeric version
`0.1.0.0`, language selection enabled and downgrades disabled. The generated
language checker passes with 16 paired resources. The bundled payload manifest
also identifies product `0.1.0`, source base `ffd46dc0c3e6f7a3aca749309604efa7f6cbf0a1`
and generation `83a0c37ddfe244b411f42041336c2eca38aa19f092014bc01f28e81ad4369e7b`.

| Evidence layer | Actual result |
| --- | --- |
| Checksums, SPDX, provenance | One installer subject; exact final SHA; version 0.1.0; dirty source explicitly recorded |
| Extracted payload | Host/sidecar digests match the bundled manifest and the product verifier passes |
| Compiled sidecar preflight | Exit 0, durable compatible result inside runtime, matching payload identity; no canonical/graph DB creation |
| Forbidden result path | Exit 1, no outside result file, prior valid JSON preserved |
| Actual Korean UI | Picker, welcome, license guidance/buttons and cancel before installation observed |
| Actual English UI | English chosen on the Korean OS; welcome, license guidance/buttons and cancel observed |
| Picker cancellation | Closed normally; final owned candidate/fixture window count is zero |
| Prior candidate preservation | Previous 0.4.0-1 EXE SHA remains `60b33433eeee49c61aa9d0d75c1a44a180116181fdb52fbe89326d15b57b2807` |

The exact candidate SHA is shared by `final-artifact-identity.json`,
`final-candidate-runtime-results.json`, `candidate-ui-observations.json` and
`metadata/SHA256SUMS`. Native window observations found no fixture error popup.
The earlier user's no-console exception did not recur in the valid or rejected
preflight cases using this candidate's packaged sidecar. This does not claim that
all installation-failure branches have been executed.

The build emitted one Rust `linker_messages` warning containing the linker's
normal import-library creation message; build and package creation succeeded.
The temporary directory override was scoped to this build process. No OS security
setting or global environment variable was changed.

## Preserved historical evidence and remaining scope

The previous `0.4.0-1` candidate and the
[installer language verification](windows-installer-i18n-20261014.md) remain
historical evidence. Their results are not relabelled as tests of the new binary.
I24–I26 retain the unmeasured full installation/reinstallation/rollback/removal,
English OS and display-scale matrix. Before-installation screens and bounded
preflight checks do not establish those lifecycle outcomes.
R00–R05 commit/PR/hosted CI/platform review/main/release remain separate.
