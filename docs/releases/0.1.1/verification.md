# Angmoo 0.1.1 verification scope

The fixed product source is `bfd63c2440d5d1d2f33898407fd329404f1b2359`
(tree `f7c3a46414ada8b65fbd78c301d0d8880283022a`). This review adds documentation;
it does not change or rebuild that candidate. Public release readiness is checked
separately against the tag, original artifacts and registry manifests.

## Windows acceptance: installation only

On 2026-10-24 (Asia/Seoul), maintainer `jingujeon` explicitly requested that
Windows be recorded as installation verification only and that publication
continue without launching the app or making AI calls. The instruction was:

> 그럼 Windows는 설치 확인까지 한 것으로 정리하고, 남은 V038~V063 작업을 이어서 진행해줘. 앱 실행이나 AI 호출 없이 0.1.1 정식 배포와 Android 전달 묶음 준비까지 마무리해줘.

The maintainer subsequently chose the public `release-v0.1.1` installer command
instead of a separate Android transfer bundle. Neither instruction authorizes
phone installation, app execution or an AI trial in this publication task.

The `windows_user_check` PASS in `p5.json` means acceptance of the following
**installation and data-preservation scope only**. It is not a runtime/UI PASS.
Its `checked_at` records when this scoped acceptance was recorded, not an
inferred exact timestamp of the user's message. Earlier source-review approvals
and the 0.1.0 user check are not reused as acceptance of this EXE.

- Original file: `Angmoo_0.1.1_x64-setup.exe`, 278,883,518 bytes.
- SHA-256: `467ad3c72c7f32c025c91ae0da12f97abd8837038a54cb7df1d700c170ff2456`.
- The stopped existing installation was backed up privately, then updated with
  that exact original EXE through the normal Windows installer. The transaction
  completed at `2026-10-23T20:28:50.7833882Z`; the final **Run Angmoo** option was
  unchecked. The GUI showed completion; an installer process exit code was not
  captured for this GUI invocation and is not inferred.
- The installed desktop and sidecar payload hashes and opened physical paths
  were verified against the manifest and fixed source. The read-only check
  reported `identity_verified`, installation `verified` and running
  `not_observed`. A redirected AppData/LocalCache view was not used as the
  installed-version source.
- The existing canonical SQLite file, domain rows, persistent secrets, media
  and preferences were preserved. Data version remained 41; no new migration is
  claimed. The graph file's byte representation changed, but read-only private
  copies had identical table metadata and rows. Logs and installer transaction
  records were retained. Private data and raw logs are not release assets.
- Installed-app launch, UI operation, sidecar lifecycle and close/restart
  acceptance: **NOT_RUN**. External AI calls: **NOT_RUN**. The installed app was
  left stopped. Automatic CI checks below remain a separate evidence layer.

Windows Authenticode is **NotSigned**. The GitHub hosted-workflow EXE attestation
was verified against the exact source, producer and original hash; that is not
a Windows publisher code signature.

## Automated candidate checks

All listed producer runs completed successfully on the fixed source, attempt 1:

| Check | Evidence | Scope |
| --- | --- | --- |
| Core CI | [40011355001](https://github.com/angmoo-tree/angmoo/actions/runs/40011355001) | Main-source required checks |
| Local Smoke | [40011354950](https://github.com/angmoo-tree/angmoo/actions/runs/40011354950) | Main-source local profile checks |
| Security and Governance | [40011354990](https://github.com/angmoo-tree/angmoo/actions/runs/40011354990) | Main-source security/governance checks |
| Windows Installer full | [40011355070](https://github.com/angmoo-tree/angmoo/actions/runs/40011355070) | Exact EXE: clean installation, rollback, both supported-update partitions |
| Container Candidate | [40011443936](https://github.com/angmoo-tree/angmoo/actions/runs/40011443936) | Native amd64 and ARM64 backend/frontend originals |

Windows input data-version fixtures 1–40 were covered by the full update
validation. This is fixture coverage, not forty released product versions.
The original Windows artifact is `12528530909`; its full validation receipt and
hosted attestation were retrieved and checked. The complete four-image artifact
is `12526013514`. P5 records the exact per-platform manifest digests.

Both native container architectures passed module/runtime/security checks and
19 selected memory-contract tests. FTS5, vec1 nearest-neighbor search, spawned
workers, Ladybug restart and fresh-data persistence were checked without
external provider calls. These checks establish the recorded synthetic
contracts, not real-AI quality or phone performance. Original OCI bytes are
promoted rather than rebuilt for publication.

The initial read-only combined verify
[40017787353](https://github.com/angmoo-tree/angmoo/actions/runs/40017787353)
verified candidate identities and packaged assets before reviewed P5, the tag
and official images existed. It reported candidate PASS but publication not
ready and made zero remote writes. Final publication must recheck the reviewed
records, tag and registry instead of treating that preliminary result as a
published release.

Existing glib dependency advisories are tracked separately from the successful
required and image-security checks. This release record does not claim that
every repository dependency advisory is resolved.

## Android and other unmeasured behavior

Android remains **experimental-not-certified**. The public installer, tools and
ARM64 artifacts are prepared from the same product source. No new physical-phone
installation, autonomous activity, external AI-quality check or screen-off/Doze
trial is performed here. Previous phone observations retain their original
source and device limitations. A ready download is not a phone-runtime PASS.

## 한국어 검증 범위

제품 소스는 `bfd63c2440d5d1d2f33898407fd329404f1b2359`로 고정했습니다.
이 기록은 후보를 다시 빌드하거나 제품 코드를 바꾸지 않습니다.

관리자는 2026-10-24 Windows 확인을 **설치 확인까지만** 수행하고 앱 실행·AI
호출 없이 정식 공개를 마무리하도록 명시했습니다. 따라서 P5의 사용자 확인
PASS는 동일 EXE의 실제 설치·기존 데이터 보존에 한정됩니다. 실행 화면,
sidecar 시작·종료, 닫기·재실행은 **미실행**이며, 이전 PR 승인이나 0.1.0의
실사용 확인을 이번 버전의 실사용 결과로 사용하지 않습니다.

동일 원본 EXE로 기존 설치를 업데이트한 뒤 실제 열린 파일 경로·payload hash와
제품 소스를 확인했습니다. 설치 완료 후 앱 실행 옵션은 해제했습니다. 기존 SQLite
파일·도메인 데이터·비밀값·미디어·설정은 보존됐으며 데이터 버전은 41로 같았습니다.
그래프 파일은 바이트가 달라졌지만 읽기 전용 복사본의 테이블 정보와 전체 행이
같았습니다. 개인 데이터·원본 로그·비밀값은 공개 자산에 포함하지 않습니다.

위 표의 고정 소스 CI, Windows full 설치·롤백·데이터 버전 1–40 fixture 업데이트,
native amd64·ARM64 컨테이너 검증은 자동 검증 근거입니다. Windows 코드 서명은
없으며 GitHub 빌드 증명과 구분합니다. 모든 의존성 advisory가 해결됐다고 주장하지
않습니다. 후보 검증과 공개 준비, 실제 공개도 각각 별도로 확인합니다.

Android는 별도 전달 묶음 대신 공개 `release-v0.1.1` 설치 명령을 사용하도록
준비합니다. 이번 작업에서 실제 휴대폰 설치·앱 실행·새 AI 호출·자율활동·Doze
시험은 수행하지 않습니다. native ARM64 CI 성공을 휴대폰 실행이나 장시간
백그라운드 동작의 보증으로 바꾸지 않습니다.
