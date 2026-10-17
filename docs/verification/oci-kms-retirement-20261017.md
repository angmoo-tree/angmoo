# OCI SDK·이전 hosted KMS 제거와 로컬 암호화 보존 검증

- 실행일: 2026-10-17 / Asia/Seoul
- 범위: 관련 구현·로컬 검증·로컬 커밋. Publish, PR, Actions CI, main 병합 및 배포는 제외.
- 브랜치: `refactor/remove-legacy-oci-kms`
- 분기 기준: `caf75878372c3e4b8070849e4fa66ed536203a81`
- 구현 커밋: `1622cae25fbc4ade20e28524ba51c7cea765f8fe`
- 이 검증 기록은 위 구현과 분리한 후속 로컬 문서 커밋에 보존한다.
- 실행 계획: 작업 공간 `docs/plan/10-17 OCI SDK·angmoo.com KMS 잔재 제거와 로컬 암호화 보존 코드 구현 세부 계획.md`의 I00–I39.
- 시작 시 local main, origin/main 및 읽기 전용 원격 main 조회가 같은 커밋을 가리켰고 작업 트리는 clean이었다.

## 구현 결과와 보존 경계

Oracle SDK, KMS client/cache, instance-principal signer, 원격 암복호화, 시작 시
왕복 probe 및 OCI 전용 설정 4종을 제거했다. `cryptography 50.0.0`, 기존
`local-v2` 형식, AES-GCM/HKDF·nonce·AAD와 `dev-v1` 읽기/이전은 유지했다.
기존 로컬 암호·인증 함수/클래스 19개의 AST는 기준 커밋과 동일하다. 이 비교와
별도로, 수정 전 코드로 생성한 합성 암호문을 수정 후 실제 복호화하는 시험을 통과했다.

`oci-kms-v1:`의 식별은 남는다. configured service key와 저장된 키 모두에서
그 암호문을 평문 API 키로 해석하지 않으며 SDK import나 KMS 요청 없이 거절한다.
일반 로컬 이전은 외부 암호문의 바이트를 보존하고 `external`로 집계한다.
외부 항목이 남은 CLI는 `credential_migration_incomplete`와 exit 78을 반환한다.
직접 지원하지 않는 provider로 실행한 CLI도 DB를 열기 전에 exit 78로 실패한다.
지원하는 로컬 이전의 commit/rollback 책임은 바꾸지 않았다.

Embedded upgrade는 선택한 데이터 루트의 secret으로 인증해야 한다. 과거 KMS
암호문이나 잘못된 root key를 만나면 원본 DB·media·secret·현재 generation marker를
보존하고 staging을 승격하지 않는다. 사용자 데이터를 삭제하거나 키를 재생성하는
복구 동작은 추가하지 않았다.

공식 local/contributor/test `RuntimeConfig`는 각각 소유한 로컬 키를 계속 사용한다.
상위 process에 `production`/OCI 설정이 있어도 명시적 로컬 구성과 루트 키 격리는
유지된다. raw hosted `APP_ENV=production` 진입은 `unsupported_runtime_profile`,
직접 선택한 비지원 provider는 `unsafe_credential_provider`로 거절한다.
Origin·cookie·CSRF·소유권·데스크톱 token·SQLite·docs/signup 보호는 유지했다.

Chat·SNS·기억·이미지의 로직, 검색 인덱스, 스케줄러, DB schema, provider/model 선택,
암호화 secret 파일 형식, UI/KO/EN 문자열 및 frontend source에는 변경이 없다.
현재 credential 저장·목적별 해석·교체·revoke·소유권 경계를 관련 시험으로 확인했다.
실제 외부 AI 품질이나 자연 활동 검증까지 수행했다는 뜻은 아니다.

## 최종 의존성과 크기

`uv lock --offline`으로 제거했으며 `--upgrade`를 사용하지 않았다. 아래 8개가
최종 lock에서 제거됐다. 나머지 third-party package의 버전·출처·파일 hash·조건과
의존성 정보는 기준 lock과 동일하고, 앱 root package의 직접 의존성 목록만 바뀌었다.

| 제거 패키지 | 버전 | 연결 |
|---|---|---|
| oci | 2.184.1 | 폐기한 Oracle SDK 직접 의존성 |
| circuitbreaker | 2.1.3 | OCI 전용 의존성 |
| crc32c | 2.8 | OCI 전용 의존성 |
| PyJWT | 2.15.0 | OCI 전용 의존성 |
| pyOpenSSL | 26.4.0 | OCI 전용 의존성 |
| python-dateutil | 2.9.0.post0 | OCI 전용 의존성 |
| pytz | 2026.2 | OCI 전용 의존성 |
| six | 1.17.0 | OCI 및 python-dateutil 경유 |

실제 최종 삭제 목록을 같은 날 측정한 동일 버전 Linux wheel의 파일 합계와 대조했다.
Windows 실행 전용 격리 환경에는 67개 distribution이 설치됐으며 OCI와 위 전용
의존성은 없고 `cryptography 50.0.0`은 남는다. OS 조건에 따라 설치 수는 다르다.

| Linux wheel 내용 기준 | x86_64 | aarch64 |
|---|---:|---:|
| runtime wheel 수 | 74 → 66 | 74 → 66 |
| 압축 해제 파일 합계 | 351.84 → 145.45 MiB | 351.96 → 145.39 MiB |
| 제거 패키지의 압축 해제 파일 합계 | 206.39 MiB | 206.57 MiB |
| 제거 패키지의 wheel 다운로드 합계 | 35.82 MiB | 35.82 MiB |

이 값은 기존 wheel 측정과 실제 lock 차이를 결합한 의존성 비교다. **완성 Docker
이미지나 Windows EXE 전후 크기는 미측정**이다. OS/Python·bytecode·이미지 layer 압축을
포함하지 않는다. Dockerfile의 frozen/no-dev 설치 연결은 유지되며, Windows sidecar의
기존 `--exclude-module oci`도 유지했다. EXE가 위 크기만큼 더 작아졌다고 해석하지 않는다.

## 관련 로컬 검증

기존 `backend/.venv`와 분리한 `artifacts/oci-kms-retirement-20261017/runtime-env`,
`test-env`에 각각 frozen no-dev 및 시험 의존성을 설치했다. Python 3.13.12,
현재 로컬 uv 0.11.9를 사용했다. runtime 환경에는 pytest도 설치하지 않았다.

| 실행 | 실제 결과 |
|---|---|
| 변경 전 지정 credential/startup/browser/migration/media 시험 | 73 PASS / 기존 1 SKIP |
| 수정 후 전체 지정 범위 + 신규 회귀/공식 bootstrap | 112 PASS / 1 FAIL / 기존 1 SKIP |
| 새 시험의 과거 schema 참조 수정 후 migration 파일 + license 시험 | 16 PASS |
| 갱신한 current inventory 관련 정확한 node 2개 | 2 PASS |
| 중복 node를 제외하고 가장 마지막 결과를 집계 | **128 PASS / 기존 1 SKIP / 남은 실패 0** |

첫 실패는 새 시험이 v29 자료를 준비하고 v30 이후의 `world_credentials`를 수정하려 한
시험 구성 오류였다. v29의 `llm_credentials`에서 원래 SNS 키를 교체하도록 수정했다.
그 뒤 실제 upgrade 실패와 원본 DB/media/secret/marker 보존, staging 미승격을 통과했다.
제품의 보안 검사를 약화시키거나 시험을 skip하여 해결하지 않았다.

기존 SKIP은 `test_hosted_lifespan_registers_runtime_adapter_only_while_running`이다.
공개 runtime에 hosted extension이 없는 기존 조건으로, 변경 전과 동일하다. 신규 skip,
xfail 또는 선택 제외는 없다. XML에 기록된 개별 node와 최신 결과를 집계했다.

| 보호 항목 | 검증 |
|---|---|
| 과거 local-v2/dev-v1, nonce 비결정성, 잘못된 4개 scope/key/변조 거절 | local-v2·retired credential 시험 PASS |
| configured service key 정상 사용, OCI 및 손상 envelope 비노출 거절 | 실제 합성 암복호화 및 Oracle import/network 차단 시험 PASS |
| SNS/Chat/consolidation/vision/image 목적별 credential, owner/World, 교체·revoke | 기존 Identity credential 시험 PASS |
| dev-v1 이전·재실행·손상 시 rollback·외부 자료 보존 | 일반 migration 및 CLI 시험 PASS |
| 서로 다른 두 root, 잘못된 root key, OCI 외부 key | embedded migration 시험 PASS |
| 공식 프로필 3종, 상위 환경 격리, local security drift, Origin/cookie/CSRF | runtime/startup/browser 시험 PASS |
| OCI 없는 앱 bootstrap/모델 등록/sidecar 구성 | 새 시험 환경의 subprocess 시험 PASS |
| OCI 없는 no-dev contributor diagnostics 및 합성 로컬 암호 왕복 | PASS; SQLite/Ladybug 준비, provider 사용 0, 사용자 서비스 미실행 |

단일 no-dev diagnostics는 앱 조립·임시 DB 준비 확인이다. 장시간 서버 운용,
실제 AI 호출, Windows 설치 또는 Docker 컨테이너 실행 검증으로 대신하지 않는다.

### 정적 검사 및 현행 자료

- Architecture inventory: modules 1568, internal edges 6802, external imports 4601 PASS.
- Architecture boundaries: legacy exact edges 0 PASS.
- Local runtime contract: services 2, core modules 29 PASS.
- `uv lock --project backend --check --offline`: 78개(root 및 dev/platform 포함) 정합성 PASS.
- Project license: GPL-3.0-only PASS.
- Dependency notice: Python 77, Node 67, conditional review 4개 PASS.
- Embedded runtime current inventory: postgres files 111, migration 89, graph queries 24,
  Next routes 45, parity workloads 7 PASS.
- `git diff --check`: PASS.

초기 current inventory 불일치는 기존 생성기로 재생성했다. 정확히 현재 import 목록,
OCI 제거된 dependency 목록, 변경된 manifest/CLI의 scan hash/line만 갱신했다.
`crc32c` 제거에 맞춰 그 exact review, 검사기의 동일 항목, dateutil 전용 metadata override와
고지를 삭제했다. 다른 exact review·라이선스 제한은 유지했다. frozen refactor source,
이전 schema/manifest, 과거 완료 증거를 재작성하지 않았다. 종료된 역사 보존 검사 전체는
현재 검증 계약이 아니므로 실행하거나 예외 원장을 새로 만들지 않았다.

## 시험 재실행 방법

아래 `$taskPython`은 기존 실행용 환경을 변경하지 않는 격리된 시험 환경이다.
제품 저장소에서 시작한다. GitHub Actions 실행 명령이 아니다.

```powershell
$taskPython = (Resolve-Path 'artifacts/oci-kms-retirement-20261017/test-env/Scripts/python.exe').Path
$taskNetworkGuardBefore = $env:ANGMOO_DENY_EXTERNAL_NETWORK
Push-Location backend
try {
    $env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
    & $taskPython -m pytest -q tests/identity/test_l1_local_v2_credentials.py tests/identity/test_l1_byok_ownership_privacy.py tests/identity/test_credential_resolver.py tests/identity/test_world_credentials.py tests/identity/test_migration_secrets.py tests/identity/test_retired_kms_credentials.py tests/config/test_startup_security.py tests/identity/test_browser_session_security.py tests/runtime/test_embedded_migration_secret_binding.py tests/runtime/test_local_credential_startup.py tests/runtime/test_canonical_bootstrap.py tests/test_l3_er7_runtime_composition.py::test_poisoned_parent_environment_cannot_change_embedded_composition tests/test_l3_er7_runtime_composition.py::test_create_app_owns_explicit_embedded_session_and_runtime_state tests/test_post_image_generation.py::test_service_image_key_helper_accepts_raw_key tests/test_post_image_generation.py::test_service_image_key_helper_decrypts_envelope tests/test_post_image_generation.py::test_service_image_key_helper_hides_invalid_envelope
    & $taskPython -m pytest -q tests/test_t1_5_project_license.py tests/test_t1_5_dependency_license_policy.py tests/test_m4_dependency_licenses.py tests/test_l3_er0_embedded_runtime_inventory.py::test_generated_embedded_runtime_inventory_is_current tests/test_l3_er0_embedded_runtime_inventory.py::test_storage_frontend_runtime_and_parity_corpora_are_complete
} finally {
    $env:ANGMOO_DENY_EXTERNAL_NETWORK = $taskNetworkGuardBefore
    Pop-Location
}

& $taskPython scripts/ci/generate_architecture_inventory.py --check
& $taskPython scripts/ci/check_architecture_boundaries.py
& $taskPython scripts/ci/check_local_runtime_contract.py
& $taskPython scripts/verify_embedded_runtime_inventory.py --check
& $taskPython scripts/check_project_license.py
& $taskPython scripts/check_dependency_licenses.py --check-notice THIRD_PARTY_NOTICES.md
uv lock --project backend --check --offline
```

실행 증거는 로컬 추적 제외 경로 `artifacts/oci-kms-retirement-20261017/`에 있다.
`baseline-tests.xml`, `scoped-tests.xml`, `migration-and-license-tests.xml`,
`inventory-tests.xml`, `test-summary.json`, `verified-test-nodes.json`,
`lock-diff.json`, `dependency-parents.json`, `final-runtime-and-dependency-audit.json`,
`runtime-bootstrap.json`, frozen 설치 로그로 구분했다. 합성 fixture만 사용했고 실제
사용자 키·암호문·DB는 읽거나 첨부하지 않았다.

## 기존 자료의 의미와 후속 범위

- `oci-kms-v1:`: 지원 종료된 암호문을 안전하게 인식하기 위해 남는다.
- 시험의 `oci_kms`: 상위 설정 오염·잘못된 provider·퇴역 암호문 거절을 확인하는 부정 입력이다.
- sidecar의 `--exclude-module oci`: 기존 방어적 packaging 설정을 유지했다.
- 과거 검증 기록과 고지 이력의 OCI: 당시 사실을 보존한다.
- Docker/GHCR의 OCI(Open Container Initiative): Oracle SDK와 별개이므로 변경하지 않았다.

운영 안내(KO): 기존 로컬 데이터를 계속 사용할 때 해당 루트의 app-secret을 그대로
보존한다. 과거 KMS 키는 기존 설정 화면에서 API 키를 다시 등록해야 한다. 기존 외부
암호문은 자동 삭제하거나 로컬 키로 자동 변환하지 않는다. `OCI_*` 환경변수는 기존
Settings의 unknown-field 무시 정책 때문에 남아 있어도 기능을 활성화하지 않는다.

Operator guidance(EN): Keep the original app-secret for each existing local data
root. Re-register a retired KMS credential through the existing settings flow.
External ciphertext is neither deleted nor automatically converted. Old `OCI_*`
variables are ignored by the existing settings policy and do not enable KMS.

UI source 변경이 없어 V14는 N/A다. 전체 backend/frontend suite, hosted CI,
amd64/ARM64 이미지 빌드, Termux, Windows EXE 설치·업그레이드 matrix, 실제 AI/사용자
기능 검증은 수행하지 않았다. 사용자 설치본·DB·secret·Docker·관찰 세션을 변경하지
않았고, main·원격 branch·tag·Release·GHCR에는 이 변경을 반영하지 않았다.
