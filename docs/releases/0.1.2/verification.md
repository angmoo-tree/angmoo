# Angmoo 0.1.2 verification scope

The fixed product source is `6b3b0279d1d96a052c0b737db812a04f3c182204` (tree `8157877c4bcd45f72d1235bdba5ae54a19151b3f`).
PR [#409](https://github.com/angmoo-tree/angmoo/pull/409) integrated the product
changes, followed by the isolated native-test fixture correction in
PR [#410](https://github.com/angmoo-tree/angmoo/pull/410). Both preserved the
implementation history through normal merges. This release review adds records;
it does not rebuild or change the verified product originals.

## Windows acceptance: installation and data preservation only

The maintainer explicitly authorized an agent-performed installation and data-preservation check of this exact 0.1.2 original. The normal File Explorer installer completed, Run Angmoo was unchecked, and physically verified payloads match the fixed source. All canonical SQLite table rows, existing canonical/graph/search files, selected language/timezone and persistent secrets were preserved. This is not a claim of direct human runtime or UI acceptance; installed-app launch, restart and real AI were not performed.

- Evidence consolidated at `2026-10-24T20:40:00.745139+00:00`.
- Original file: `Angmoo_0.1.2_x64-setup.exe`, 278,905,731 bytes.
- SHA-256: `sha256:33960289a245c5633b0791c5d5828861f1bafef356c073c55d8dc18dfeebdc70`.
- The stopped installation was backed up privately and updated with this exact
  original through the normal installer. **Run Angmoo** was unchecked.
  GUI completion and the physical installation record were checked; no GUI
  process exit code is inferred.
- Physical opened paths and installed desktop/sidecar payload hashes verified
  the source above. Installation was `verified`, running was `not_observed`;
  redirected AppData/LocalCache files were not used as installation identity.
- Canonical domain rows, credentials, selected language/timezone and persistent
  secrets were preserved. Data version was 41
  before and 41 afterwards. Canonical database
  byte equality: `True`.
- All existing canonical, graph and search storage files were also identical
  byte for byte after the update. Read-only diagnostics did not open the
  installed graph through a database engine.
- There were 0 existing media files in
  this local data set. Zero files means no live user-media update sample;
  automated media-preservation fixtures are a separate check.
- Installed-app launch, UI/runtime use, close/restart and external AI calls:
  **NOT_RUN**. The application was left stopped. Private backup, data and logs
  are not public release assets.

The EXE is **NotSigned** for Windows Authenticode. Its GitHub hosted-workflow
attestation was verified against the exact source and original file hash;
that attestation is distinct from a Windows publisher code signature.

An initial direct Codex child-process launch saw a stale `0.4.0-1` registration
and was cancelled before installation. The same EXE opened in normal File
Explorer correctly enabled the no-uninstall update path. No registry value,
LocalCache, security setting or installer downgrade check was changed. The
physical installation checks above establish the final result.

## Same-source automated candidate evidence

| Check or producer | Run | Attempt |
| --- | --- | --- |
| ci.yml | [40126685739](https://github.com/angmoo-tree/angmoo/actions/runs/40126685739) | 1 |
| local-smoke.yml | [40126685738](https://github.com/angmoo-tree/angmoo/actions/runs/40126685738) | 1 |
| security.yml | [40126685758](https://github.com/angmoo-tree/angmoo/actions/runs/40126685758) | 1 |
| windows-installer.yml | [40126725611](https://github.com/angmoo-tree/angmoo/actions/runs/40126725611) | 1 |
| container-candidate.yml | [40126734331](https://github.com/angmoo-tree/angmoo/actions/runs/40126734331) | 1 |

The Windows original artifact is `12574900199`;
its full validation receipt covers clean installation, rollback and both
supported-update partitions. These are input-state fixtures, not a count of
past public versions. The four-image original artifact is
`12572788503`. P5 records all four platform
manifest digests. Publication promotes these verified OCI originals without
rebuilding them.

Native candidate feature results: linux/amd64: 20 passed in 78.71s (0:01:18); linux/arm64: 20 passed in 74.52s (0:01:14). Neither architecture skipped
the added real FTS/Vec1 manual-source and downstream-privacy case. Native
module, spawned search worker, Ladybug restart, service/runtime, security and
fresh-data restart checks also passed. Synthetic providers and disabled
external network were used; this is not a real-AI quality or phone performance
claim.

Preliminary read-only verify
[40130218584](https://github.com/angmoo-tree/angmoo/actions/runs/40130218584)
validated the same originals with zero remote writes. It did not establish
publication readiness. Reviewed P5, the official tag and registry indexes
are checked by later verification and publication steps.

## Corrections and preserved evidence

Required CI exposed historical installer fixtures importing new role defaults;
the fixtures now use frozen predecessor values. Existing compatibility and
generated-inventory evidence was updated from exact source without weakening
baselines or adding a permissive bypass. Docker/development version defaults
now agree with the 0.1.2 product version.

The first merged source `5409d49bbb1dd661988c3b09277c513b0766933f`
was superseded after native candidate run `40124245088` failed on both
architectures. A direct pytest fixture had left its result journal at the
default `/app/uploads`, which the unchanged non-root user cannot write.
PR #410 selects the test's own temporary media directory and asserts journal
containment. Production paths, privileges, the real native extension and skip
rejection remain unchanged. On the same local image the original fixture
reproduced 1 failure/19 passes; the corrected fixture passed 20 with no skips.
The 40 related host contracts passed. The hosted originals listed above were
then regenerated from the new final source; the failed originals are not
published. Historical evidence remains available.

Existing separately tracked glib advisories are not represented as fixed by
this release. This record does not claim that every repository advisory has
been eliminated.

## Android and unmeasured behavior

Android remains **experimental-not-certified**. Public Termux bootstrap/tools
and ARM64 images use the same product source. There is no separate phone
delivery bundle. Public bytes and ordinary install paths are checked after
publication, without executing the installer on a phone in this task.

No new phone installation, autonomous activity, real-AI quality, charging or
Doze trial is included. Earlier photo-picker device checks retain their
original source and environment limits. Native ARM64 CI does not certify
continuous background operation on every Android device.

## 한국어 확인 범위

제품 소스는 `6b3b0279d1d96a052c0b737db812a04f3c182204`로 고정했습니다. Windows 원본 EXE와
amd64·ARM64 backend/frontend는 모두 이 소스에서 생산·검증했습니다.
문서 검토는 제품을 다시 빌드하지 않으며 실제 원본의 식별 정보를 사용합니다.

사용자가 이번 원본의 설치·데이터 보존 확인 범위를 승인한 뒤 에이전트가
정상 설치기를 실행하고 물리 경로·payload·데이터를 확인했습니다. 사용자 본인이
이 원본의 앱 화면과 기능을 직접 사용했다는 의미는 아닙니다. 이전 버전의
사용자 확인을 새 EXE의 결과로 복사하지 않았습니다. 앱 실행 선택은 해제했으며
실제 실행·화면·재시작·AI 호출은 미실행입니다. 기존 미디어가 없는 데이터셋은
실제 사용자 미디어 업데이트 검증으로 주장하지 않습니다.

필수 검사에서 발견한 문제는 원인에 맞게 수정했고 검사를 생략하거나 완화하지
않았습니다. 첫 후보의 테스트 저장 경로 오류와 새 소스 후보의 native 검증을
분리했습니다. 공개 본문은 한영 공통 양식에 따라 영어 다음 한국어로 제공합니다.
Android 공개 설치 경로 준비와 실제 휴대폰 동작·화면 꺼짐 보장은 구분합니다.
