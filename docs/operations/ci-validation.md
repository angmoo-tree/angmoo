# CI validation and release candidates

> **0.1.5 support policy:** Docker (Linux amd64/ARM64, including Windows Docker Desktop) and experimental Termux ARM64 remain supported. New Windows native installers and official native support end with 0.1.5. Existing EXEs, source and manual workflows are retained. No Windows-native-to-Docker data migration tool is provided: Docker starts a separate empty environment. Keep your old installation and backup if you need its data. Existing Docker/Termux 0.1.4 users update with their data preserved; do not run the SQLite migration again. 0.1.5 commands require the corresponding official release to be published.

Automatic PR/main/scheduled full runs select all supported shared tests. Native Tauri/installer/Windows-host/spike/advisory jobs require explicit manual dispatch. `full` does not opt into Windows; Core CI has a separate `native_windows` opt-in. The frontend aggregate requires browser/frontend work, not native compilation. Keep backend, frontend, local smoke, graph, migration-input, security, DCO and architecture gates required. Remove only `windows-installer` from GitHub required checks.


## Selection and result gates

PR and main checks use a source-controlled classifier. Unknown paths, missing
diffs and shared build/security/CI or migration inputs widen selection. Required
workflow results still report through their gates. A justified `not_applicable`
names the omitted scope and is not a full validation pass.

Backend source edits select the full backend corpus because runtime and domain
consumers make a path-only reduction unsafe. Isolated test edits may select their
affected modules and consumers. Frontend source edits retain the production Next
suite. Runtime lock, installation, recovery, data and CI policy changes widen the
supported shared checks, without enabling native Windows jobs.

The frontend result consumes the selected browser/frontend job. Native static
builds and static-only browser cases run only with the manual `native_windows`
opt-in. Mixed image and visual suites always retain their Next cases and add their
static cases only for that opt-in. Their test code and snapshots are preserved.
Unselected work and unsuccessful selected work are different states.

한국어: 일반 PR에서는 Next 웹 경로를 검증합니다. Windows 정적 빌드와 정적
전용 검사는 수동 `native_windows` 선택 시에만 실행하며, 혼합 검사에서도
웹 경로의 기능·화면 검증은 계속 수행합니다.

Active classification is the normal mode. Observe mode evaluates a proposed
selection while running full validation. Manual full and scheduled full runs may
widen the set, never narrow it. Verify actual run SHA, profile and attempt before
reporting success; a workflow definition is not an execution result.

Cross-job environment values carry a small reference containing the source,
checkout, run, policy and selection hashes. Each consumer reconstructs the
complete plan from its checked-out Git diff and the actual Actions event, then
verifies those identities before materializing `.ci/impact.json`. The full path
and reason lists remain available in the plan and reports without exceeding the
operating system's environment-value limit on large changes. The selected tests
and required gates are unchanged by this transport.

## What ongoing checks protect

- Current import ownership, app factory and lifecycle behavior.
- HTTP/schema, authorization, World scope and source-version contracts.
- PostgreSQL initialization, bounded transaction retry, leases, cancellation and recovery; frozen SQLite 0.1.3 input conversion checks.
- Canonical results, provider call limits and data/credential preservation.
- Next consumers, locales, proxy limits and visual interactions; static consumers remain available in the manual native profile.
- PostgreSQL storage and preserved SQLite migration inputs. The historical 0.1.3 installer upgrade, native clean install and module identity remain in manual native checks.
- Live security evidence consumers, dependency licenses and artifact identity.

Do not routinely replay an obsolete refactor's exact source bodies or frozen
test-name census. Preserve its history separately. An old filename does not make
a test obsolete if it protects a current consumer or supported data upgrade.
Do not drop synthetic/fake-provider cases merely because they do not use live AI.

## Build and fixture order

Core CI builds the production Next frontend before proxy/browser fixtures.
With `CI=true`, the fixture launcher serves that build through the supported
production path. Interactive local fixtures may use development mode. Build
first when reproducing production fixture behavior; do not mix generated dev
route files into the production build inputs.

Use pinned tools and lockfiles. Downloaded native inputs must match their
source-controlled hashes and size limits, including cache hits. Cached bytes do
not replace identity verification. Network retries are bounded; invalid bytes,
TLS failures and permanent failures do not silently choose another source.
Target-native binaries must be built for their target.

## Candidate validation

1. Select one main-history product SHA and retain its identity.
2. Require the applicable full Core, Local Smoke, Security/Governance,
   Container Candidate and independent Release Common Assets results from that source.
3. Verify actual run/attempt, artifact ID/digest/expiry, checkout and complete
   selected coverage. Do not combine reports from incompatible attempts.
4. Verify the common source/license assets against their source-bound receipt and
   hosted producer. 0.1.5+ does not produce or require a native Windows EXE.
5. Validate backend/frontend/postgres for both native amd64 and ARM64. Emulator checks
   and real-phone checks have separate meanings.
6. Retain Docker and Termux update evidence separately from synthetic fixtures.
7. Publish only the validated bytes through the reviewed release process.

An already completed full main run from the exact source can supply evidence;
changing its event label is not a reason to rerun all successful work. A later
documentation-only commit does not change the earlier product artifact identity.
Rebuilding or signing creates different bytes and requires renewed reconciliation.

## Failure handling

Diagnose the failed step. Retry transient infrastructure failures in a bounded
way; repair reproducible code or workflow errors. Never disable a required test,
relax a hash, widen a permission boundary or use a merge override to make a check pass.

Coverage belongs to one source/tree and attempt. A backend shard retry needs a
fresh, complete partition report from the Core workflow, not one new partition
combined with old successful reports. Independently successful smoke or installer
workflows do not need to restart solely for that retry. Apply the same identity
rule to selected historical installer qualification reports. Historical 0.1.4 full coverage
requires clean-install, upgrade-013 and failure-recovery with a single native
resource digest. Installer-smoke covers clean-install and upgrade-013 and cannot
supply a full release receipt. Historical SQLite predecessor reports retain their
old schema solely for replaying those frozen releases.

Keep implementation, focused local checks, hosted CI, main checks, candidate
verification, publication and user checks distinct. Publication operations are
described in [release publishing](release-publishing.md).
