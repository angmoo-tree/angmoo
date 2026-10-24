# Angmoo 0.1.1 verification scope

The fixed product source is `72d2da52418516604025a1efa49aaca2cfdb0304`
(tree `dd646ca41ce9549c1dc7d40208fe3041e5bf45e4`). This release review adds documentation;
it does not rebuild or modify the verified candidate. Publication readiness is
checked separately against the tag, original artifacts and registry manifests.

## Windows acceptance: installation only

On 2026-10-24 (Asia/Seoul), maintainer `jingujeon` requested installation-only
verification and completion of the 0.1.1 release without app execution or AI calls:

> 그럼 Windows는 설치 확인까지 한 것으로 정리하고, 남은 V038~V063 작업을 이어서 진행해줘. 앱 실행이나 AI 호출 없이 0.1.1 정식 배포와 Android 전달 묶음 준비까지 마무리해줘.

The maintainer subsequently chose the public `release-v0.1.1` installer command
instead of a separate Android transfer bundle. Phone installation is outside
this publication task.

The `windows_user_check` PASS is limited to the authorized **installation and
data-preservation scope**. The agent verified the exact new EXE below under that
scope; no direct maintainer runtime/UI use of this new EXE is claimed. Its
`checked_at` records when this evidence was consolidated, not an inferred
timestamp of a user message. Earlier PR approvals, 0.1.0 acceptance and the
superseded 0.1.1 candidate are not reused as verification of these new bytes.

- Original file: `Angmoo_0.1.1_x64-setup.exe`, 278,893,489 bytes.
- SHA-256: `sha256:ea0b022ff7ba8c33df5b257027fa9d4ade7411b3f41ee4cce63675b5836a92d1`.
- The stopped existing installation was backed up privately and updated through
  the normal installer using this exact original file. The **Run Angmoo** option
  was unchecked. GUI completion and the physical transaction record were checked;
  a GUI process exit code was not captured and is not inferred.
- The installed source, desktop/sidecar payload hashes and actual opened physical
  paths were verified. The result was `identity_verified`, installation `verified`
  and running `not_observed`. A redirected AppData/LocalCache view was not used
  to infer an installed version or an installation failure.
- Canonical SQLite bytes and domain rows, persistent secrets, media and selected
  language/timezone were preserved. Data version remained
  41; no new schema migration is claimed.
  The graph byte representation changed; read-only private copies had identical table metadata and rows.
  Logs and installer transaction records were retained privately.
- Installed-app launch, runtime/UI operation and close/restart: **NOT_RUN**.
  External AI calls: **NOT_RUN**. The app was left stopped. Automatic CI checks
  below remain a separate evidence layer.

Windows Authenticode is **NotSigned**. The original EXE's GitHub hosted-workflow
attestation was verified against the exact source, producer and hash. That is
not a Windows publisher code signature.

## Automated candidate checks

All producer/check runs below succeeded at the fixed source:

| Check | Evidence | Attempt | Scope |
| --- | --- | --- | --- |
| Core CI | [40045475059](https://github.com/angmoo-tree/angmoo/actions/runs/40045475059) | 1 | Main-source checks, including 56 Termux host regressions |
| Local Smoke | [40045475279](https://github.com/angmoo-tree/angmoo/actions/runs/40045475279) | 1 | Main-source local profile checks |
| Security and Governance | [40045475065](https://github.com/angmoo-tree/angmoo/actions/runs/40045475065) | 1 | Dependency, license and governance checks |
| Windows Installer full | [40045475052](https://github.com/angmoo-tree/angmoo/actions/runs/40045475052) | 1 | Exact EXE: clean install, rollback and both supported-update partitions |
| Container Candidate | [40045498032](https://github.com/angmoo-tree/angmoo/actions/runs/40045498032) | 1 | Native amd64 and ARM64 backend/frontend originals |

The original Windows artifact is `12541169473`;
its full receipt and hosted attestation were retrieved and checked. The complete
four-image artifact is `12540834753`. P5 records
the exact platform manifest digests. Supported update fixtures are automated
input-state coverage, not a count of previously released product versions.

Native amd64 and ARM64 validation passed FTS5, vec1 nearest-neighbor search,
spawned search workers, Ladybug restart, service/runtime and security checks.
Fresh-data restart checks preserved SQLite state, media and installation secrets,
with zero external provider calls. These are synthetic contract checks, not
real-AI quality or physical-phone performance. Publication promotes these exact
OCI originals without rebuilding them.

The preliminary read-only verify
[40049743371](https://github.com/angmoo-tree/angmoo/actions/runs/40049743371)
verified the originals and packaged assets before reviewed P5, the release tag
and official image indexes existed. Candidate validation passed, publication
was not ready and remote writes were zero. The final publication workflow must
recheck reviewed evidence, the tag and registry instead of treating that result
as a published release.

## Security revalidation

The first 0.1.1 candidate was superseded when a later required audit reported
new advisories for PDF processing and SQLite activity checkpoints. PR
[#408](https://github.com/angmoo-tree/angmoo/pull/408) updated
`pypdf` to 6.21.2, `langgraph-checkpoint-sqlite` to 3.1.2 and its required
`langgraph-checkpoint` dependency to 4.3.0, with locked notices and generated
inventories kept consistent. Targeted PDF/checkpoint regressions passed before
fresh main-source CI and all candidates were regenerated. Checks were not skipped
or weakened. Previously recorded candidates and backups remain preserved.

Existing glib advisories are tracked separately; this record does not claim
that every repository dependency advisory has been resolved.

## Android and other unmeasured behavior

Android remains **experimental-not-certified**. The versioned public installer,
tools ZIP and ARM64 images come from the same product source. No separate Android
transfer bundle is required. Public bytes, hashes and install paths are verified
after publication; the installer is not executed on a phone in this task.

No new phone installation, real autonomous activity, AI-quality observation or
screen-off/Doze test is performed. Earlier observations retain their original
source and device limits. Native ARM64 CI and a ready public download do not
establish phone-runtime or continuous-background-execution success.

## 한국어 검증 범위

제품 소스는 `72d2da52418516604025a1efa49aaca2cfdb0304`로 고정했습니다.
이번 출시 기록은 검증된 후보를 다시 빌드하거나 제품 코드를 바꾸지 않습니다.

사용자는 설치 확인까지만 수행하고 앱 실행·AI 호출 없이 공개하도록 지시했습니다.
이 범위에서 에이전트가 새 보안 수정 소스의 동일 EXE를 실제 설치하고 물리 경로와
payload hash·데이터 보존을 확인했습니다. P5의 PASS는 **설치·보존에 한정**되며
사용자가 이 새 EXE의 화면과 기능을 직접 사용했다는 의미가 아닙니다. 이전 후보의
확인이나 0.1.0 사용자 확인을 새 후보의 검증 결과로 사용하지 않습니다.

설치 완료 후 앱 실행 선택을 해제했습니다. 기존 SQLite 바이트·도메인 데이터,
비밀값·미디어·언어·시간대는 보존됐으며 데이터 버전은
41로 유지됐습니다. 그래프 바이트는 달라졌지만 읽기 전용 복사본의 테이블 정보와 전체 행은 같았습니다.
개인 데이터와 원본 로그·비밀값은 공개 자산에 포함하지 않습니다.

고정 소스 CI, Windows full 설치·롤백·지원 입력 fixture 업데이트와 native
amd64·ARM64 검증은 자동 검증입니다. Windows 게시자 코드 서명은 없으며 GitHub
빌드 증명과 구분합니다. 앱 실행·화면·재시작·새 AI 호출은 **미실행**입니다.

필수 보안 검사에서 확인된 의존성 문제는 PR #408로 수정한 뒤 소스를 다시
고정하고 후보와 설치 검증을 새로 수행했습니다. 검사를 생략하거나 완화하지
않았으며, 저장소의 모든 advisory가 해결됐다고 주장하지 않습니다.

Android는 별도 전달 묶음 대신 공개 `release-v0.1.1` 설치 명령을 사용합니다.
공개 다운로드 경로·해시·같은 소스의 ARM64 이미지 검증과 실제 휴대폰 설치·실행은
구분합니다. 이번 작업에서 새 자율활동·화면 꺼짐·Doze 시험은 수행하지 않습니다.
