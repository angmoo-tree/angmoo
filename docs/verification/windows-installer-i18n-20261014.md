# Windows EXE language and MSI retirement verification

Implementation branch: feat/windows-installer-i18n, based on
ffd46dc0c3e6f7a3aca749309604efa7f6cbf0a1. Scope is the requested I00–I31;
R00–R05 (commit/PR/hosted CI/review/main/release) remain separate.

This report preserves the original `0.4.0-1` local candidate evidence. The user's
subsequent Windows product version transition has a separate
[0.1.0 build verification record](windows-installer-version-0.1.0-20261014.md).

## Implemented behavior

- A single NSIS EXE, English/Korean choice and repeat interactive choice via
  official Tauri/MUI options. Installer language does not write app preferences.
- Paired global LangString resources for all 13 owned MessageBox calls and
  the confirmed awkward standard welcome/license guidance (16 pairs in total).
  Numeric Windows language IDs
  1033/1042 work with Tauri's early hook include; LangString inside a Section
  is invalid and was rejected by a real NSIS compiler probe.
- Runtime path uses a dedicated variable. Recovery failure/success and the
  account-wide irreversible deletion scope remain distinct. Existing decision
  IDs, data paths, confirmation, reparse checks, rollback and silent guards stay.
- NSIS-only targets/build, retired unconsumed WiX source, EXE-only metadata and
  CI upload/attestation. Existing lifecycle, Defender and predecessor gates remain.
- Metadata requires the exact current NSIS filename/path and checked-out
  version/commit. Extra/stale/MSI/helper/private/link payloads are refused.
  Dirty local source is explicitly labelled; it is not a final release candidate.

## Evidence layers and limits

Evidence is stored under artifacts/windows-installer-i18n-20261014/.
The focused pytest XML/log, checker outputs, actual build logs, fixture logs,
source snapshot, artifact identity and I00–I31 ledger are recorded there.
The branch changes are local and uncommitted; product/app library locks are
unchanged. No PR, hosted workflow, merge, release or existing installation update
was performed by this scope.

The actual EXE was opened for language selection and preinstallation screens
and cancelled before installation. Separately, an inert compiled probe displayed
the actual 13 custom resource messages in both languages. It contains no
File/Delete/registry/app instructions. Its success is a resource/UI observation,
not successful installation or proof that actual failure branches were exercised.
NSIS page buttons use the chosen language; native Windows MessageBox buttons
use the OS language. The OS language setting is unchanged.

Actual installer payloads were extracted with existing 7-Zip and checked in
an isolated repository-owned fixture. Their frozen manifest digests match.
The initially reported packaged preflight success is withdrawn: the fixture
passed a result path outside the runtime root. The sidecar correctly refused
it, then an unwritable windowed stderr raised a secondary OSError and left a
PyInstaller error dialog open. Exit code alone did not establish success.
The old fixture logs/results remain as superseded evidence; fresh verification
requires process completion, the structured result inside runtime, matching
status/identity, and no error dialog. The runtime path fence is retained.
The raw Cargo output host differs from the host embedded in the NSIS EXE:
an initial raw-host fixture was correctly rejected. Using the exact extracted
installer subject passes without weakening the verifier or rewriting digests.

There is no isolated Windows VM/dedicated test user available in this session.
Full real installation/app launch/reinstallation/uninstallation, both Windows
OS-language rows, repeat language selection on an installed product, recovery
failure dialogs, actual saved uninstaller-language restore and a full DPI matrix
remain unmeasured. I24–I26 must retain partial status. Existing synthetic safety
tests and a compiled probe do not replace these checks.

The local product version remains 0.4.0-1. Official 0.1.0 version/tag/source
coordination and publication belong to the separate distribution roadmap.
No existing MSI artifact or historical verification report was deleted.

## 한국어 결과 해석

EXE 단일 생성·언어 선택·한국어/영어 안내·검사·CI 수집 계약을 구현했고 실제 EXE를
만들었습니다. 본 EXE는 언어 선택과 설치 전 화면을 열어 확인한 뒤 설치 시작 전에 취소했습니다.
자체 안내 13곳은 파일이나 사용자 설정을 바꾸지 않는 별도 시험 프로그램으로 두 언어를
확인했습니다. 새 설치·앱 실행·재설치·제거까지 검증한 결과로 계산하지 않습니다.

설치 파일에서 실제 추출한 호스트와 사이드카는 payload 해시 검증을 통과했습니다.
최초 사전 검사 성공 기록은 철회합니다. 시험 결과 경로를 runtime 밖에 잘못 지정해
정상 거절됐고, 콘솔 없는 EXE의 오류 출력이 다시 실패해 팝업이 남았습니다.
종료 코드만으로 성공을 판정한 기록을 보존하고 새 검증으로 대체합니다.
정식 runtime 결과 파일·상태·실행 완료·오류 창 부재를 함께 확인해야 합니다.
처음에 원본 빌드 폴더의
호스트를 사용한 시험은 설치 파일에 포함된 바이트와 달라 거절됐습니다. 검사나 해시를
완화하지 않고 실제 설치 파일에서 추출한 대상에 연결해 검증했습니다.

관련 로컬 검사와 산출물 생성, 실제 화면 확인, 원격 CI·병합·공식 공개는 서로 다른
결과입니다. 격리 Windows 환경이 필요한 I24–I26의 미측정 항목과 R00–R05를
남겨두었으며, 전체 계획 완료나 0.1.0 공개 완료를 주장하지 않습니다.

## Additional correction from the user's screenshot

Both observed error windows belonged to repository-owned fixture executables,
not a verified installed Angmoo process. The mandatory physical identity helper
was run; its running identity conclusion was incomplete. No installed-version,
installation-failure or data-corruption claim is derived from that output.
The two fixture dialogs were closed normally. Installed data was not altered.

The process boundary now treats console diagnostics as best effort and retains
a nonzero exit on failure. Installer success is represented by its durable
result, even with absent, closed, invalid-write or invalid-flush console streams.
The normal desktop readiness pipe remains required and unchanged. Related tests
cover all four console conditions, content-free fatal codes and rejection before
data preparation. Both the actual sidecar and NSIS EXE were rebuilt. The final
extracted executable completes valid preflight with exit 0 and a compatible
durable result; an outside-runtime result is refused with exit 1, without creating
that file or changing the previous successful result. No fixture error window
remained in the live computer-use inventory after those checks.

## Final local results

- 88 focused installer/runtime/security/translation/supply-chain tests passed;
  55 metadata privacy and CI-policy tests passed (143 total, no failures/skips).
  Two existing dependency deprecation warnings were recorded separately.
- Installer, supply-chain, generated-page/language, backend architecture import
  inventory/boundaries, frontend architecture/design, secret metadata and the
  supported-predecessor contract checks passed. Actual hosted v1–v36 upgrades
  were not executed in this local scope.
- The final EXE has SHA256
  `60b33433eeee49c61aa9d0d75c1a44a180116181fdb52fbe89326d15b57b2807`,
  size 277,827,911 bytes, product version 0.4.0-1, Authenticode NotSigned.
  Checksums, SPDX SBOM and provenance agree on that single subject. Dirty local
  source is labelled and separately hashed in final-build-inputs/source-snapshot.
- The same final EXE displayed Korean and English Welcome/license guidance.
  English was selected by keyboard on the Korean OS. License text/consent were
  unchanged; the awkward Korean installer guidance was corrected with official
  MUI options. Both flows were cancelled before installation. Language-picker
  cancellation also closed the candidate, with zero remaining candidate windows.
- Current output contains one NSIS EXE. The old EXE and MSI still match their
  recorded hashes. Initial full Tauri build: 693.62s; rebuilt sidecar: 342.66s;
  final incremental NSIS bundle: 167.53s. These are distinct operations, not a
  hosted CI or before/after performance benchmark.
- I00–I31 ledger: 29 complete, I24/I25/I26 partial due to the full isolated GUI
  and installation lifecycle limits above. R00–R05 not started. No local commit,
  PR, remote CI, main merge, official release or installed-user update occurred.

The first rebuild's temporary cleanup failed in an externally selected TMPDIR.
The successful rebuild used a process-local, repository-owned temporary root
for TMPDIR/TEMP/TMP without changing system settings or bypassing source hashes.
Initial invalid fixture paths/environment were corrected rather than weakening
the payload verifier. Superseded logs remain available.

Evidence: artifacts/windows-installer-i18n-20261014/implementation-ledger.json,
final-artifact-identity.json, final-candidate-runtime-results.json,
final-candidate-ui-observations.json, final-focused-tests.xml,
metadata-ci-regression.xml and final-metadata/.

최종 설치 파일을 실제 추출해 사전 검사 exit 0·compatible 결과와 경계 밖 경로의
exit 1·파일 미생성을 확인했습니다. 실제 한국어·영어 시작/사용권 화면과 선택 창
취소도 확인했고 오류 창은 남아 있지 않습니다. 관련 시험은 143개가 통과했습니다.
I24–I26의 실제 설치·재설치·제거 전체 행렬은 격리 Windows 환경 부재로 부분 완료이며,
기존 사용자 설치판에는 적용하지 않았습니다. 로컬 코드·후보와 공식 릴리스를 구분합니다.
