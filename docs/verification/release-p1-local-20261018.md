# 0.1.0 P1 local candidate evidence — 2026-10-18

Status: P1 local candidate validation complete with the PRoot/Android limitations
below. P2 PR/main and P6 publication are separate.

## Identity and scope

- Base main: `12fa53fa04b138b5432d1d865ee1cf17c3c61389`.
- Branch: `feat/release-0.1.0-multiarch-termux`.
- All four image archives were built from clean source
  `aa4a9e9b44ff78005cecf6fea78d43360064f799`.
- Subsequent host adapter, test harness, CI and documentation commits do not change
  Dockerfiles, app source, app lockfiles, entrypoints or Vec1 build inputs. They do
  not relabel these archives as a later source. P3 must fix the final main source.
- Evidence directory on the validation host:
  `E:/angmoo-release-candidates/20261018/aa4a9e9b44ff78005cecf6fea78d43360064f799`.
  This directory contains synthetic local validation artifacts, not a public download.
- Actual AI calls: zero. No installed Windows application or personal database was
  used. No official tag, GHCR image, GitHub Release or draft was published.

## Image measurements

Windows Docker Desktop, amd64 host, 12 vCPU / 7.669 GiB Docker VM RAM.
ARM64 runs use QEMU, not native Android. BuildKit reused dependency layers;
these times are not cold build benchmarks.

| Image | OCI archive bytes | Uncompressed image bytes | Build seconds |
| --- | ---: | ---: | ---: |
| backend amd64 | 143368192 | 595042623 | 153.875 |
| frontend amd64 | 101031424 | 415537181 | 58.719 |
| backend ARM64 | 140936704 | 611996550 | 421.687 |
| frontend ARM64 | 101243904 | 435472092 | 65.891 |

Execution manifest digests:

- backend amd64: `sha256:f30197734bdcf54270229af8bb49924410b96956200a3369916c1725465edfbc`
- frontend amd64: `sha256:08a1cf09c1894bb651e00fbbd99f92334de7a48c72000d08b2faf737fbe8f0d6`
- backend ARM64: `sha256:c613f2dc2278f2e66a4ae2d655df41b7442daf60358e77375fbc0df5a8f4cd3b`
- frontend ARM64: `sha256:c3f60c2190086c54d8be1bcadee0a89c89ba43d052355a4898e44f3adfe1ff8b`

The candidate manifests also bind archive hash, config hash, ordered diff IDs,
base child digest, lock hashes and SBOM/provenance manifests. Actual imported
image contents were verified against these records, including Docker's
containerd image identity representation.

## Verified results and boundaries

| Check | amd64 | ARM64 QEMU |
| --- | --- | --- |
| Actual SQLite FTS5/WAL, Vec1 NN/spawn, LadybugDB write/reopen | PASS | PASS |
| Actual Node/Sharp native execution | PASS | PASS |
| Fixable HIGH/CRITICAL CVE and secret gate, SPDX SBOM | PASS | PASS |
| Selected existing feature tests | 19 PASS (273.43 s) | 19 PASS (369.83 s) |
| Same frontend with Docker DNS and loopback upstream | PASS | PASS |
| Fresh keyless stack, reply persistence, restart DB/media/secret | PASS | PASS |

Runtime versions agree across architectures: Python 3.13.15, SQLite 3.46.1,
Node 22.23.2 and Sharp 0.35.5. SBOM comparison found 66 installed Python
packages per architecture with identical versions. Both frontend SBOMs contain
68 NPM packages; architecture-specific Sharp/libvips binary names differ with
matching versions (0.35.5 / 1.3.4). The 77 external Python lock records and
frontend lock selections are unchanged.

The amd64 measured cold pair start was 23.937 seconds; stop 1.969 seconds and
restart 18.094 seconds. First healthy upper bounds were backend 16.751 seconds
and frontend 5.529 seconds. These include the health probe interval and are not
startup SLAs. Memory in `validation-amd64/runtime.json` is a single sample,
not peak RSS or an Android requirement.

The ARM64 QEMU pair cold start was 155.625 seconds, stop 3.235 seconds and
restart 138.812 seconds. Docker lifecycle events retained the restart readiness
intervals (backend 118.753 seconds; frontend 18.084 seconds), but not the initial
cold-start events. Its per-service cold health values in the runtime report
(221.451 / 93.991 seconds) are late rolling-log upper bounds, not exact startup
durations; the harness now captures these before slow diagnostic imports.
The memory samples were backend 476.3 MiB / frontend 219.2 MiB under QEMU,
versus amd64 305.8 MiB / 56.54 MiB. These are not native ARM64/Android forecasts.

## Corrections discovered by execution

1. Vec1's ARM64 NEON code supplied unsigned vectors to four signed comparisons.
   The build input applies four typed corrections after verifying the pinned
   upstream source hash. Native comparisons cover signed/negative and tail cases;
   the upstream vendor file and SIMD capability remain intact.
2. Docker classic/containerd identities differ; runtime validation now proves
   actual config and rootfs rather than assuming image ID always means config hash.
3. PRoot-Distro's local importer expects a flat OCI index. Its temporary transport
   archive preserves every original blob, execution config/layer and attestation
   hash. The original candidate is unchanged.
4. Process cleanup checks the owned session, boot ID and start ticks. A parent
   exiting before a child no longer lets stop return while that child survives.
   Reused PID/foreign sessions cannot be signalled as old Angmoo children.
5. Release tool ZIP metadata is deterministic across new checkouts, so a
   partially uploaded draft can resume with the same file hashes.
6. Test fixtures are staged in a disposable Linux container filesystem without
   host bytecode. The test command disables the API healthcheck because pytest
   does not start that API server. App files, production dependencies and test
   deadlines are unchanged.

Earlier QEMU feature attempts are retained as failures: 16/19 and 17/19 passed.
A controlled filesystem-only comparison passed the retained-progress deadline
case but still exceeded the native worker test's 10-second limit. A separate
cold import trace measured 7.936 seconds inside the worker module import
(9.797 seconds including Docker startup). These observations support emulation
startup overhead; they do not prove all original failures have one cause.
The final harness ran all 19 unchanged tests successfully in 369.83 seconds,
with no skipped tests. Its result is recorded separately rather than erasing
these attempts. No application deadline or test deadline was increased.

Scoped Release/container/CI regressions: 25 PASS. They include stable ZIP bytes
after checkout timestamps change, read-only preparation from synthetic Windows
and image artifacts, wrong EXE provenance rejection, exclusion of extra data
files, and fake-API draft resumption. The real attestation CLI options were
checked locally; no real Release was created to exercise these tests.

## PRoot and Android

Actual isolated Linux PRoot-Distro 5.10.0 imported both ARM64 rootfs and verified
source/version/config/layers. Linux host process tests: 10 PASS, including
ownership, lock, port collision, stale PID, partial startup, orphan drain,
invalid manifest and low disk preservation.

The available Debian PRoot 5.1.0/QEMU combination returned inconsistent statx/
access results for the data bind: creating a file succeeded, but the app's
write-access check failed. Canonical startup correctly rejected the directory
with `contributor_data_root_unwritable`. The permission check was not weakened.
PRoot app readiness/browser/restart remain NOT_RUN in this environment.
The owned stopped harness and data volume are preserved for diagnosis.

Android T01–T05/T11 and background/Doze checks remain P4 NOT_RUN. Linux image
build or QEMU success does not certify Android support.

## P2/P3–P7 handoff

P2 must use the final PR head, required checks and explicit CODEOWNERS platform
review. The only platform-owned source change is the development version in
`scripts/dev/desktop-dev.ps1`. Final Windows OS results are required before
requesting that review.

P3 fixes final main source and builds the final candidate; P4 validates a real
Android device; P5 verifies exact Windows EXE/images and user evidence; P6
publishes verified bytes. Existing development tags/images remain preserved
until the separate P7 policy is executed.

## P2 first CI corrections

PR #386 first head `8949fcbff4e6383598621c1297f2bc56aa046830` exposed five
causes: stale deferred-runtime inventory, stale design route inventory (45 to
47 routes), Windows PowerShell 5.1 decoding non-ASCII source through the ANSI
code page, an old fake Compose response missing the new version field, and an
old exact health-response fixture missing version/source/launch identity.
The inventories were regenerated by their existing commands; design thresholds,
frozen evidence, application behavior and test deadlines were preserved.
The launcher uses a UTF-8 BOM and the Windows smoke now rejects non-ASCII
PowerShell source without it, supplies a real-shaped Compose JSON fixture,
and verifies old product-version settings stop before any container startup.
The health test checks exact synthetic source/launch identities and all previous
readiness/data-root assertions.

The dependency-review Action's pinned SPDX dependencies reproduced the license
failure: GPL-3.0-only matched the old GPL-2.0-or-later deny range. The workflow
now uses the project's existing allowed-license IDs with no package exclusion.
An exact-ID check over the Action's JSON output preserves GPL-2.0-or-later and
other forbidden-ID rejection even where the Action's range algorithm accepts
a later choice. Full locked inventories, exact package/version reviews, notices
and the high-severity vulnerability gate remain. A regression rejects drift,
package bypasses and disabled checks. Primary implementation evidence:
https://github.com/actions/dependency-review-action/blob/a1d282b36b6f3519aa1f3fc636f609c47dddb294/src/spdx.ts

Scoped local results: 38 tests passed, then 14 affected policy tests passed after
the exact-ID addition (overlapping counts, not 52 distinct tests). Actual Windows
PowerShell 5.1 launcher smoke passed. Current inventory/design/CI/license policy
checks passed. Image input paths still match the verified `aa4a9e9b...` candidate.
These results are local; final-head hosted CI and platform review remain pending.

The next full Core CI run (`39063560043`, source `adbe71c7...`) passed three
backend partitions; partition 0 exposed one remaining stale assertion: the
current frontend inventory contains 47 routes while its test still expected 45.
The expectation now includes the two new server handlers explicitly
(`/api/runtime-identity` and `/media/[...path]`). The existing generated-source
comparison and notification/static parity assertions remain. All eight scoped
embedded inventory tests passed locally. This changes only the inventory test
and this report; application/image inputs and test deadlines are unchanged.

PR CodeQL alerts 22/23 identified missing HttpOnly/Secure flags on the synthetic
upstream cookie in `frontend/scripts/test-media-proxy.mjs`. That test-only cookie
now carries HttpOnly, Secure and SameSite=Strict. The test still requires the
proxy response to omit Set-Cookie entirely; cookie forwarding, two upstreams,
Range/HEAD, error/path refusal and stream abort checks all passed. No application
authentication or runtime module changed. The test script enters the build
context but is not a runtime image payload; P3 still builds the final main source.
