# Docker embedded 마이그레이션 암호화 키 연결 검증 (2026-10-07)

SQLite v29 → v30 시작 과정에서 발생한 `world_activity_secret_authentication_failed`를 수정했다. 기존 Docker 볼륨으로 전환을 완료했고 backend와 frontend가 모두 healthy이며 `http://127.0.0.1:3000/`은 HTTP 200이다.

## 원인과 구현

Contributor 시작 코드는 앱의 runtime settings를 적용하기 전에 데이터 마이그레이션을 실행한다. 기존 `MigrationSecretInterpreter`는 전역 settings의 기본 개발용 키를 사용하므로 데이터 루트의 `secrets/app-secret`으로 암호화한 자격 증명을 인증하지 못했다.

- 공통 `EmbeddedDataUpgradeCoordinator`가 자신의 resolved data root에 속하는 키 파일을 별도 settings 값에 연결하고 키 reader를 Identity의 interpreter에 명시적으로 주입한다.
- Interpreter는 기존 자격 증명의 인증이 필요할 때 키를 읽고 해당 전환 동안 같은 값을 사용한다. 자격 증명이 없는 과거 전환에서는 불필요하게 키를 읽지 않는다.
- 공통 암호화 구현에 명시적 로컬 키로 읽는 진입점을 추가했다. `local-v2`의 AES-GCM 인증·scope 검증 및 `dev-v1` 읽기 호환성은 유지한다. Comfy 서버·partner 키를 묶을 때도 같은 명시적 키로 새 로컬 envelope를 만든다.
- 기존 일반 실행용 암호화 API는 그대로 사용한다. 마이그레이션은 전역 settings를 임시 변경하거나 기본 키·KMS로 대체하지 않는다.
- 키가 잘못되면 미공개 staging 전환을 중단하고 원본 DB·선택 마커·키 파일·미디어를 보존한다. 인증 검사를 건너뛰거나 manifest/schema 계약을 완화하지 않았다.

별도 암호화 알고리즘을 복제하는 대신 기존 구현을 재사용하고, 의존성을 명시적으로 연결했다. 추가 비용은 작은 키 reader와 전환 동안의 키 보관이며, 서로 다른 데이터 루트와 전역 설정의 혼선을 방지한다.

## 로컬 자동 검증

다음 pytest 검증은 `ANGMOO_DENY_EXTERNAL_NETWORK=1`, `PYTHONPATH=.;tests`로 실행했다. 합계 **50개 통과**다.

| 검증 파일 | 확인 내용 |
| --- | --- |
| `backend/tests/runtime/test_embedded_migration_secret_binding.py` | 서로 다른 두 v29 데이터 루트에서 Contributor 준비 경로를 실행한다. 잘못된 전역 키 파일·KMS 설정에도 각 루트의 키로 SNS·Comfy 자격 증명을 전환한다. 원본 보존, 반복 실행, 잘못된 실제 키의 중단을 검증한다. |
| `backend/tests/identity/test_migration_secrets.py` | local-v2·dev-v1, 잘못된 키·scope, 원격 envelope 거부, 빈 키 거부, 필요할 때 한 번만 읽는 동작을 검증한다. |
| `backend/tests/migrations/test_world_activity_v30.py` | 기존 v30 데이터 이관 계약과 인증 실패를 검증한다. |
| `backend/tests/identity/test_l1_local_v2_credentials.py` | 기존 일반 실행용 로컬 암호화 API의 회귀를 검증한다. |
| `backend/tests/runtime/test_contributor_import.py` | Contributor 시작·import·기존 데이터의 키 누락 처리 경계를 검증한다. |
| `backend/tests/test_embedded_data_migration.py` | 더 오래된 SQLite 버전부터의 전환, 데이터 보존, 생성물 선택, 반복 실행을 검증한다. |
| `backend/tests/test_embedded_data_migration_contract.py` | 기존 마이그레이션 계약을 검증한다. |
| `backend/tests/test_oss_architecture_boundaries.py::test_secret_decryption_is_confined_to_credential_resolver` | 일반 복호화와 새 로컬 복호화 모두 허용된 Identity·보안 소유 경계에 제한되는지 검증한다. |

오래된 v2 테스트 fixture에는 현재 v30 테이블과 임의 문자열 `fixture-ciphertext`가 남아 있었다. 실제 frozen v2 스키마와 유효한 테스트 암호문을 생성하도록 수정했고, 전환 전후 암호문의 정확한 동일성을 계속 검사한다. frozen manifest 및 production 전환 규칙은 변경하지 않았다.

다음 구조 검증도 로컬에서 통과했다.

- `scripts/ci/check_architecture_boundaries.py`
- `scripts/ci/generate_architecture_inventory.py --check` (추가 import에 맞춰 inventory 갱신)
- `scripts/ci/check_embedded_data_migration_contract.py` (`BASE_SHA=2a776fd9ad5a1d2a294833807af0c896c6961842`)
- `scripts/ci/check_docker_runtime_assets.py`
- `scripts/ci/check_local_runtime_contract.py`
- `git diff --check`

위 경로의 CI 스크립트는 로컬 검사로만 실행했다. 원격 CI 실행은 하지 않았다.

## 실제 Docker 볼륨 검증

대상은 contributor 전용 named volume `angmoo_angmoo_contributor_embedded_data`이다. 설치 앱 데이터는 검사하거나 변경하지 않았다.

수정 전 서버가 중지된 상태에서 원본 DB·키 파일·기존 키 테이블·미디어 해시를 기록했다. 수정 후에는 애플리케이션 UID/GID `10001:10001`, `--network none`, read-only 볼륨으로 별도 검증을 실행했다. 키 원문과 대화·게시글 본문은 출력하거나 검증 기록에 저장하지 않았다.

| 항목 | 결과 |
| --- | --- |
| 선택된 SQLite 스키마·마커 | v29 → v30 |
| 원본 v29 DB | 수정 전 SHA-256과 동일, 그대로 보존 |
| `secrets/app-secret` | 수정 전 SHA-256과 동일 |
| 기존 미디어 205개 | 모두 수정 전 SHA-256과 동일 |
| 기존 `llm_credentials`·`media_credentials` | 전체 행의 digest 동일 |
| 전환된 World SNS 키 | 9개 모두 실제 키 파일로 로컬 인증 성공 |
| 전환된 World 이미지 키 | 4개 모두 실제 키 파일로 로컬 인증 성공 |
| 사용자 / 캐릭터 / World 캐릭터 | 1 / 13 / 13, 검사 시점에 동일 |
| 게시글 / 대화 스레드 / 메시지 / 기억 | 1193 / 2 / 201 / 1349, 검사 시점에 동일 |
| SQLite FK 위반 / quick_check | 0건 / ok |
| Backend health | ok / sqlite / ladybug |
| 컨테이너와 로컬의 수정한 Python 소스 3개 | 파일 SHA-256 모두 일치 |

검증 기록은 workspace의 `.task-output/migration-secret-binding-20261007-144725/`에 `before.json`, `after.json`, `verify_volume.py`로 보존했다. 기록에 암호화 키 원문·API 키 원문·본문은 포함하지 않는다.

## 프론트엔드 기동에서 확인한 별도 문제

백엔드 복구 후 기존 frontend 이미지에서 CSS parsing 오류가 발생했다. 이미지의 `/app`에는 로컬 검증에서 생성한 `.next-integration-production`, `.next-world-memory-integration` 디렉터리가 포함되어 있었다. Tailwind가 빌드 입력을 탐색하는 환경에 생성물까지 섞인 상태였다.

저장소 `.gitignore`가 이미 제외하는 `.next-*` 생성물을 `.dockerignore`에서도 제외했다. 로컬 생성물은 삭제하지 않고 이미지 입력에서만 제외한다. 프론트엔드 UI 코드·기능·디자인은 변경하지 않았다.

Frontend를 다시 빌드하고 기동한 뒤 `/app`에 `.next-*` 생성물이 없고 CSS 오류가 사라졌으며, HTTP 200 및 healthy 상태를 확인했다.

실행한 적용 명령은 다음과 같다.

```powershell
docker compose -f compose.yml -f compose.dev.yml build backend
docker compose -f compose.yml -f compose.dev.yml up -d --no-build --wait --wait-timeout 180
# 위 시작에서 확인한 별도 frontend 생성물 문제를 수정한 후:
docker compose -f compose.yml -f compose.dev.yml build frontend
docker compose -f compose.yml -f compose.dev.yml up -d --no-deps --no-build --wait --wait-timeout 180 frontend
```

## 확인 범위

코드 회귀, 실제 마이그레이션, 로컬 키 인증, 데이터 보존, Docker 기동·HTTP 응답을 확인했다. 자동 검증과 read-only 키 인증은 외부 AI API를 호출하지 않았다. 실제 AI 응답 품질·이미지 생성 품질·자율 활동 관찰 세션은 이번 검증에 포함하지 않았다. 기존 자율 활동 설정은 유지했다.

작업 브랜치는 `feat/0.1.0-release-readiness`다. 결과는 로컬 커밋만 허용하며 push·PR 생성·원격 CI·main 머지는 수행하지 않는다.
