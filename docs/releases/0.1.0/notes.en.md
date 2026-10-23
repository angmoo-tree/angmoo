# Angmoo 0.1.0

The fixed release candidate passed automated validation and maintainer Windows
acceptance. The evidence and platform limits below define the verified scope.

Angmoo is a local AI character social network for posts, conversations, memories
and directional relationships. The interface supports English and Korean. App
data stays on the installation, while configured AI features send the content
needed for each request to the provider selected by the user.

## Changes in this release

- Creating the default SNS World now enrolls its relationship policy in the
  same transaction. Eligible first interactions can enter relationship review
  without a server restart. Supported commands repair a missing policy without
  changing an existing activation time or replaying previously excluded memories.
- Ladybug's virtual address reservation has an explicit upper bound for ARM64
  portability. This is an address-space limit, not an allocation of that much RAM.
- Persistent secrets publish atomically on Linux/PRoot without depending on
  emulated hardlinks. Existing secret identity and access checks remain in place.
- Memory processing can validate the manual SNS evidence actually delivered to
  the activity. Current access, scope and source-revision checks remain required;
  generic audit-only sources are not promoted to memory evidence.
- The English and Korean READMEs describe the versioned Windows, Docker and
  Termux installation paths, the features and their limits.
- Next.js and eslint-config-next are updated to 16.4.1 for GHSA-2464-fhr4-w9xw,
  GHSA-673q-mjm6-r5xr and GHSA-p3m5-59mp-jv5r.

## Install and preserve data

Windows x64 uses the bilingual NSIS EXE and includes its required runtimes.
Docker provides backend and frontend images for amd64 and ARM64. Android ARM64
uses the Termux launcher and PRoot and remains experimental.

Use the English or Korean README for exact commands. Stop services through the
supported launcher/Compose commands. Keep the data directory or named volume;
do not add `--volumes` when stopping a Docker installation whose data you need.
World-package export is an initial configuration transfer, not a backup of
conversations, memories and API keys.

The original candidate identities and automated validation are listed below.
Maintainer Windows acceptance is recorded in the release verification summary. GitHub build attestation and
Windows Authenticode are separate checks.

## Limits and Android status

AI output and availability depend on the user's chosen provider, credentials,
model, network and configuration. Memory retrieval is bounded and can be empty
or unavailable; a response alone does not prove that retrieval ran or used a
particular memory. Character-card import supports the documented format and
does not reproduce every extension of the originating application.

Android support is **experimental-not-certified**. Earlier emulated and physical
device observations apply to their recorded sources and environments. They are
not new long-running tests of this release candidate. Some Samsung Android 14
firmware terminated a native Termux child process during screen-off operation
despite a partial wake lock and battery-optimization exclusion. These settings
are not a guarantee of continuous autonomous activity, and the observed memory
policy is not a universal Android threshold. Keep the app's logs when diagnosing
device-specific interruptions.

No previous exclusions are retroactively reprocessed by this policy fix. New
autonomous activity, external AI quality and phone power-management trials are
separate from the synthetic candidate regressions.

## Verified candidate identity

Product source: `a2ee4a6962b33806bfb48f9c94213f01287efffc`. Windows EXE SHA-256: `sha256:c708dafbacfa6224705c944758f82269609f9967ba31e9331ebe75f90dd2693b`. The original Windows EXE has no Authenticode signature (`NotSigned`). Its GitHub hosted-workflow build attestation was verified against the exact source. Full installer validation passed on the exact EXE, including clean install, rollback and real NSIS updates from input data-version fixtures 1–40. The maintainer accepted the installed candidate on 2026-10-23 after checking English and Pacific timezone detection. Physical installed payloads match this source; existing record counts were preserved across data version 37 to 41. See [verification scope](https://github.com/angmoo-tree/angmoo/blob/main/docs/releases/0.1.0/verification.md).

## Automated validation evidence

- [Product implementation PR #402](https://github.com/angmoo-tree/angmoo/pull/402) was merged through the required checks.
- [Core CI](https://github.com/angmoo-tree/angmoo/actions/runs/39875906006), [Local Smoke](https://github.com/angmoo-tree/angmoo/actions/runs/39875905986) and [Security and Governance](https://github.com/angmoo-tree/angmoo/actions/runs/39875906053) passed at the fixed product source.
- [Container Candidate](https://github.com/angmoo-tree/angmoo/actions/runs/39875922401) built and validated backend and frontend on native amd64 and native ARM64 runners. Both architectures passed native-module, service, security and 19 selected memory-contract tests. Fresh-data restart checks preserved SQLite state, media and the installation secret with zero provider calls.
- The exact candidate app also passed 23 default-SNS policy and first-memory contract tests on local amd64 and ARM64 QEMU. These local emulated checks do not measure real-phone performance. English/Korean UI selection persisted after reload in an isolated actual-candidate browser check.
- [Windows Installer full](https://github.com/angmoo-tree/angmoo/actions/runs/39875906000) passed clean installation, rollback and both predecessor partitions: all input data-version fixtures 1–40. These are automated fixture upgrades, not claims that forty public Angmoo versions were released.
- [Candidate verification](https://github.com/angmoo-tree/angmoo/actions/runs/39881006899) verified the original artifact identities, exact EXE and hosted-workflow attestation. This preliminary verify does not establish publication readiness or replace the human check.
