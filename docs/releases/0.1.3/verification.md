# Angmoo 0.1.3 verification scope

Product source: `01ef3847c77a890071728b7f618f18fa88b775bf`. Tree: `0aec1e8d76f08d65b3101e1e5b4f57a747e6e7fa`.
PR [#412](https://github.com/angmoo-tree/angmoo/pull/412) integrated the
Termux log-session recovery and 0.1.3 version alignment through required checks.
This record adds release evidence without rebuilding the verified originals.

## Termux recovery

The host now distinguishes inactive interrupted sessions from live or unknown
ownership before startup. Recovery keeps historical end time unknown, capture
completeness false and the original failure. It does not terminate processes or
open the product database. The four-session/64 MiB retention policy is unchanged.
Installation completion and subsequent startup failure are reported separately.

The [implementation verification](../../verification/termux-log-recovery-20261025.md)
records 80 Linux host tests and a native Android ARM64 synthetic sample with
22 passing tests. One native hardlink fixture is unsupported by the device's
Python/Android environment; actual hardlink refusal was verified on Linux.
The phone's 36 checked original launcher/state/log files were unchanged.
This is not an installed-phone update, real AI or background-execution test.
Hosted tests use a private procfs/PID namespace under the ordinary runner UID;
production rejection of unreadable ownership was not weakened.

## Windows: installation and data preservation only

The maintainer explicitly authorized installation and data-preservation verification for this exact 0.1.3 EXE. Codex ran the normal NSIS GUI installer, chose the in-place update without uninstalling, observed successful completion and unchecked Run Angmoo before finishing. A new physical-path/payload check verified the installed product source. The stopped canonical database, all table rows, language/timezone settings and persistent secrets matched the private pre-update backup. All 532 protected files remain present: 529 are byte-identical, two installer runtime records were updated, and the installation log kept its original bytes with three successful transaction records appended. This records an agent-performed installation-only check under explicit maintainer authorization, not direct human runtime/UI acceptance. App launch, restart and external AI were not run.

- Checked at `2026-10-25T01:18:48.661259+00:00`.
- Original: `Angmoo_0.1.3_x64-setup.exe`, 278,906,881 bytes.
- SHA-256: `sha256:e9679b724ad7f8257ae8b0bbf27a67f92793d2aca077c8dce3db4ef97bae319b`.
- The normal installer updated a stopped, privately backed-up installation.
  **Run Angmoo** was unchecked. Physical opened paths and payload hashes match S.
  The installation is verified; running state is not observed. A redirected
  AppData/LocalCache view was not used as installation evidence.
- Canonical table rows, selected language/timezone and secrets were preserved.
  Data version: 41 to 41.
  Canonical database bytes equal: `True`.
  Existing media files in this sample: 0.
  A zero count is not a live user-media update sample.
- Of 532 backed-up non-code files,
  529 remain byte-identical; no protected file is missing.
  Expected installer transaction records and appended installation logs are
  reviewed separately. Existing log content is preserved.
- Installed-app UI/runtime, restart and external AI: **NOT_RUN**.
  No private data, credentials or raw device logs are release assets.

The EXE's actual Authenticode status is **NotSigned**. Its GitHub hosted-workflow
attestation was verified against the exact source and hash. This attestation
does not provide a Windows publisher code signature.

## Exact-source automated evidence

| Workflow | Run | Attempt |
|---|---|---|
| ci.yml | [40146523878](https://github.com/angmoo-tree/angmoo/actions/runs/40146523878) | 1 |
| local-smoke.yml | [40146523842](https://github.com/angmoo-tree/angmoo/actions/runs/40146523842) | 1 |
| security.yml | [40146523823](https://github.com/angmoo-tree/angmoo/actions/runs/40146523823) | 1 |
| windows-installer.yml | [40146523858](https://github.com/angmoo-tree/angmoo/actions/runs/40146523858) | 1 |
| container-candidate.yml | [40146562986](https://github.com/angmoo-tree/angmoo/actions/runs/40146562986) | 1 |

Windows full validation passed on this exact EXE, including clean install,
failed-update rollback and the supported input data-version fixture partitions.
Fixture versions are data-schema inputs, not a count of published products.
The validation receipt binds the original build artifact and EXE digest.

Container Candidate built backend/frontend on native amd64 and ARM64 runners.
Original OCI archives and manifest/config/layer digests, native-module checks,
service startup, security reports, and fresh-data restart preservation passed.
The selected feature receipts report linux/amd64: 20 passed in 78.98s (0:01:18); linux/arm64: 20 passed in 75.00s (0:01:14), with external network
disabled. These are synthetic feature contracts, not real-provider quality tests.

The read-only preliminary publication verification passed on the same original
EXE and four images. It has zero remote writes and is not publication readiness.
Termux tools and bootstrap are packaged from S, with the new recovery module
included in the explicit file profile and immutable checksums.

Android remains **experimental-not-certified**. No new installed-phone upgrade,
autonomous activity, Doze or long-running power test is claimed by this release.
No database schema/data-version change is introduced by this patch.
