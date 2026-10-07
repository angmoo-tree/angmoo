# Docker 홈의 잘못된 기능 제한 표시 수정 검증

검증일: 2026-10-07. 작업 저장소는 `angmoo-tree-angmoo`, 로컬 브랜치는
`feat/0.1.0-release-readiness`이며, 수정 전 HEAD는
`0edbb811a9978ba91c37f71ec1c56e93726f0379`이다.

## 문제와 수정

Docker의 선택된 SQLite는 정상적인 v30 / `20261006_0107`이었다. Runtime
진단은 별도로 하드코딩한 `20261005_0106`과 비교하여
`migration_not_current`를 반환했고, 홈은 종합 `degraded` 상태를 받아
`일부 기능 제한`을 표시했다. 수정 전 현재 스키마 진단 회귀 검증의
네 사례가 실제로 실패했다.

Runtime composition이 배포된 `SQLITE_SCHEMA_VERSION`의 동결 manifest에서
`source_revision`을 읽어 `RuntimeStatusService`에 명시적으로 주입하도록
수정했다. 도메인은 전달된 기준과 DB에서 읽은 버전을 비교한다. 도메인에
마이그레이션 구현 의존성을 추가하지 않고, 중복 버전 상수를 제거했다.

실제 DB 마커, 마이그레이션 파일, frontend 배지 및 번역은 변경하지 않았다.
오래된 버전, 알 수 없는 버전, 버전 메타데이터 누락은 계속
`migration_not_current`와 `degraded`를 반환한다. 컴포넌트 실패 처리도 유지한다.
다음 배포 스키마를 모사한 검증은 도메인 코드 변경 없이 새 manifest의 버전이
진단 기준으로 적용되는지 확인한다.

## 로컬 자동 검증

외부 네트워크를 차단한 환경에서 아래 45개 테스트가 통과했다. 기존
Starlette/httpx 및 anyio의 의존성 경고 두 건은 별도로 유지했다.

| 검증 파일 | 확인 내용 |
| --- | --- |
| `backend/tests/runtime/test_current_schema_diagnostics.py` | 실제 factory의 진단 기준, manifest, SQLite baseline과 Alembic head의 일치; 실제 DB의 현재·오래된·미지 버전 판정; 다음 배포 스키마 추종 |
| `backend/tests/test_l2_runtime_diagnostics.py` | 메타데이터 누락 및 기존 상태·실패 진단 |
| `backend/tests/test_l2_runtime_domain_foundation.py` | Runtime 도메인의 상태 계약과 종합 판정 |
| `backend/tests/runtime/test_asgi_preservation.py` | 기존 HTTP/ASGI 계약 보존 |
| `backend/tests/runtime/test_status_query_transaction.py` | caller 소유 Session과 rollback 계약 보존 |
| `backend/tests/test_l3_er4_single_backend_runtime.py` | 단일 backend와 컴포넌트 실패 상태 계약 보존 |

실행 명령:

```powershell
# cwd: angmoo-tree-angmoo/backend
$env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
$env:PYTHONPATH = '.;tests'
uv run --frozen --no-sync python -m pytest -q --tb=short tests/runtime/test_current_schema_diagnostics.py tests/test_l2_runtime_diagnostics.py tests/test_l2_runtime_domain_foundation.py tests/runtime/test_asgi_preservation.py
uv run --frozen --no-sync python -m pytest -q --tb=short tests/runtime/test_status_query_transaction.py tests/test_l3_er4_single_backend_runtime.py
```

첫 묶음 33개, 두 번째 묶음 12개가 통과했다. 첫 검증의 독립적인
factory/Alembic 비교를 강화한 뒤 현재 스키마 파일의 여섯 사례를 다시
실행했고 모두 통과했다. 서로 다른 테스트 수는 45개이다.

아키텍처 경계, 생성된 import inventory 일치 및 embedded 마이그레이션 계약
검사도 통과했다. import inventory는 정상 Runtime composition 의존성
두 개만 추가되었으며, 모듈 1,434개와 내부 import edge 6,052개를 기록한다.

## Docker 적용과 화면 검증

```powershell
# cwd: angmoo-tree-angmoo
docker compose -f compose.yml -f compose.dev.yml build backend
docker compose -f compose.yml -f compose.dev.yml up -d --no-build --wait --wait-timeout 180
```

기존 named volume `angmoo_angmoo_contributor_embedded_data`로 기동했다.
backend와 frontend는 모두 `running / healthy`, 홈 응답은 HTTP 200이다.
컨테이너의 수정된 product source 세 파일은 로컬 소스의 SHA-256과 일치한다.

읽기 전용 DB 진단 결과:

| 항목 | 수정 후 값 |
| --- | --- |
| 종합 상태 | `ready` |
| 현재 DB revision / 진단 head | `20261006_0107` / `20261006_0107` |
| 마이그레이션 상태 / 사유 | `ready` / `null` |
| 스케줄러 | `running` |
| 관계망 projector | `ready`; pending / failed / dead-letter 모두 0 |
| backend / SQLite / LadybugDB | 모두 `ready` |

로그인된 실제 브라우저의 `http://127.0.0.1:3000/`에서 홈 배지가
초록색 **준비됨**으로 표시되는 것을 확인했다. 기존 네 World도
모두 실행 가능한 상태로 표시됐다. 이는 테스트용 응답을 주입하지 않은
실제 Docker HTTP/UI 결과이며, 사용자 직접 확인과는 구분한다.

## 데이터 보존과 검증 범위

검사용 프로세스는 `--network none`, UID/GID `10001:10001`, 데이터 볼륨
읽기 전용 마운트를 사용했다. 키 원문이나 대화·기억 본문을 출력하지 않았다.

- 원래 v29 DB와 기존 app-secret의 hash가 수정 전 기준과 동일하다.
- 기존 미디어 205개의 hash가 모두 동일하다.
- 기존 credential 행의 digest가 동일하며, 이관된 SNS 키 9개와 이미지 키
  4개가 모두 기존 app-secret으로 로컬 인증에 성공했다.
- 기존 캐릭터 13개, World 캐릭터 13개, 채팅방 2개, 메시지 201개, 기억
  1,349개를 포함한 기존 행 수가 보존됐다. 원래 기준 게시글 1,193개 대비
  확인 시점에는 1,199개이며, 검증이 게시글을 생성하지는 않았다.
- SQLite `quick_check`는 정상이며 foreign-key 위반은 0개이다.

검증 목적의 외부 AI 호출은 0회이다. 사용자의 자율 활동·예약 설정은
변경하지 않았다. 기존 자연 활동의 실제 AI 품질은 이 진단 수정의 검증
결과에 포함하지 않는다. Windows 설치 앱에 대한 판정도 수행하지 않았다.

검증 산출물은 workspace의
`.task-output/runtime-diagnostic-manifest-target-20261007/`에 저장했다:
`status-after.json`, `data-preservation-after.json`, `home-after.jpg`.
기존 데이터 보존 기준은
`.task-output/migration-secret-binding-20261007-144725/before.json`이다.

## 로컬 Git 검증 이력

구현 커밋은 `08616293ab7bec32f3919b3745a289c1077bd605`이다.
기존 동결 checkpoint와 모든 이전 metadata record는 그대로 유지하고,
두 수정 커밋의 정확한 source blob, 변경 전후 AST·assertion 및 새로운
테스트 출처를 append-only record로 추가했다. 이전 감사 보고서의 출처
누락도 최초 도입 커밋 `2a776fd9ad5a1d2a294833807af0c896c6961842`에
연결했다. 문서·테스트를 뒤의 수정 커밋에서 새로 도입한 것으로 처리하지 않는다.

저장소의 `committed_snapshot` helper로 두 구현 커밋을 수집하여, 이전
암호화 수정의 새 테스트 일곱 사례와 이번 진단 수정의 새 테스트 두 사례를
원래 커밋에 연결했다. 추가 record의 최초 도입 커밋, source blob,
assertion·suppression 원본, 정확한 변경 전후 조건과 이전 record의
불변성을 별도로 검증했다.

이력 검사의 통과 범위는 새로 추가한 metadata의 정확성이다. 저장소 전체
과거 이력을 순회하는 보존 스캔은 완료하지 않았으며 전체 보존 검사
PASS로 산정하지 않는다. 위 45개 회귀 테스트, 구조 검사와 실제 Docker/UI
검증은 각각 완료된 결과이다.

작업은 지정된 로컬 브랜치와 로컬 커밋으로 제한한다. push, PR 생성,
원격 CI 실행, main 병합은 수행하지 않는다.
