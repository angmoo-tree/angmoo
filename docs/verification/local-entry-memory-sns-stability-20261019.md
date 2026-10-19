# Local entry, memory and SNS stability — local implementation evidence

## PR integration follow-up (2026-10-20)

PR #393의 첫 원격 검사에서 committed import/ownership/current-memory inventory와
새 Identity 경로의 route-security 분류 누락, proxy harness의 `module` 변수명,
이전 수동 owner API를 호출하는 SQLite fixture, 환경 확인을 생략한 quickstart
smoke가 발견됐다. 공식 생성기로 현재 사실 목록을 갱신하고 실제 route의 인증
경계 및 pre-auth Origin/Host 보호를 분류했다. frozen predecessor와 정책 예외는
확대하거나 수정하지 않았다.

기본 World 준비의 도메인 오류가 캐릭터 target resolver의 기존 예외 변환 밖에
있던 부분도 함께 수정했다. 환경이 준비되지 않은 요청은 draft validation으로
거절되며, smoke는 보호된 환경 HTTP 확인을 먼저 수행한다. 환경 요구를 제거하거나
확인된 것으로 SQL에 주입하지 않는다. 미사용 예전 진단 fixture도 protocol 2로
연결하고 fixture의 명시적 이름은 유지한다.

관련 inventory/architecture 회귀 30개 통과, proxy lint/회귀/typecheck 및
frontend architecture/design 검사 통과. canonical adapter·등록·smoke·security
회귀의 최초 실행은 30통과/fixture 2실패였고, 누락된 설치 identity 준비와 신규
인증 mutation 수를 바로잡은 해당 2개 재실행은 모두 통과했다. 이 기록은 원격
재실행 완료나 ARM64/설치판 사용자 확인을 대신하지 않는다.

검증일: 2026-10-19 KST. 대상은 소스 checkout과 격리 fixture다. 제품 배포, 기존 ARM64 후보, 설치된 Tauri 및 실제 AI 품질의 완료 기록이 아니다.

## 범위와 최종 계약

- 통합 계획: workspace `docs/plan/10-19 자동 사용자·세션·SNS 진입과 상황기억·근거·자율활동·설정 안정화 통합 코드 구현 세부 계획.md`, I00–I219 / V00–V130.
- 기준: clean local main `268fd33f23eb264ae9f8d94362c29e7c419447fe`.
- 구현 브랜치: `fix/local-entry-memory-sns-stability`. 최종 커밋 식별값은 통합 계획의 실행 기록과 `git log main..HEAD`에서 확인한다.
- 기능 코드 HEAD: `6cac6056` (proxy `d1e720fb`, identity `7e6931fd`, memory/SNS `dc28584c`, settings/media `6cac6056`). 이후 커밋은 이 검증 문서·통합 fixture·architecture 기록을 함께 확정한다. 모든 커밋에 DCO sign-off를 포함한다.
- 최초 화면은 기존 `/` Device Home 앱 목록이다. SNS 자동 이동이나 `/apps`를 추가하지 않았다. SNS는 사용자가 선택하며 기존 안전한 deep link는 보존한다.
- 신규 계정과 World 프로필은 ko 계열 `사용자`, 그 외 `User`. 기존 이름은 대소문자까지 유지한다.
- 자동 사용자/세션/환경/World 준비에는 AI 호출이 없다. 명시적 종료는 해당 client의 자동 재연결을 막으며 Continue만 재개한다.
- frontend ARCHITECTURE.md/DESIGN.md, backend ARCHITECTURE.md 및 static-shell 지침을 적용했다. UI provenance는 LOCAL이다.
- Publish/push, PR, 원격 CI, main merge, 태그/릴리스, 후보 재생성, Docker 재시작, 설치판·실데이터 변경을 수행하지 않았다. 로컬 scripts/ci 검사 실행은 원격 CI와 별개다.

## 구현 내용과 보존 경계

| 영역 | 구현 | 보존/호환 |
|---|---|---|
| Identity | 보호된 local protocol 2, 신규 설치 판정, 짧은 사용자/owner/session 원자 확정, 설치별 client generation | challenge·Origin·Host·Tauri launch token, 기존 owner 선택/복구, hosted 정책 유지 |
| 세션 | 만료 시 자동 갱신, persistent stop, generation CAS, 늦은 발급·종료 응답 조정, IndexedDB client 단일화 | 토큰은 HttpOnly cookie, client ID는 인증 수단 아님. 다른 client/데이터/자율활동 보존 |
| 첫 화면·설정 | 환경 확인 뒤 default World, 앱 목록 유지, 계정/설치 별명 편집, ko/en 종료·복구 문구 | 최초 form/checkbox/banner 없음, 사용자 지정 이름 보존 |
| DB | additive schema v40, Alembic 20261019_0117, frozen v39 기반 upgrade | v39 manifest/과거 migration 불변, 기존 session/token hash와 FK 보존 |
| 상황기억 | 공통 영어 grounding/구체성 안내, 필드 설명, 출력 v3/검증 v5, 정확히 언어 표기만인 값 차단 | 강제 키워드/문장 길이 휴리스틱 없음. 정상 행동·답변·다른 target 유지. 추가 생성 없음 |
| 과거 상황 | admission 무결성과 현재 적용 자격 분리 | receipt 원문/hash/status·이미 적용된 기억 보존. 미적용 marker는 새 validation에서 차단 |
| 근거 | inspector v2의 bounded label/literal projection과 고정 text/ref 결합, ko/en UI | provider 입력/원문/hash 그대로. 조회 권한/삭제/revision 검사 뒤 표시. v1 평문 임의 해석 없음 |
| SNS 관계 | 동일 activity/lane/decision의 앞선 성공 효과만 canonical proof로 후속 검증에 인정 | 외부 변경·ABA·끊긴 chain·view/perception/source/권한 변화 차단, 공개 효과와 proof 같은 transaction |
| 취소·재개 | typed 취소 원인, run/graph/slot 원자 정리, durable draft 복구 예약, 동일 beat fresh claim | 일반 cadence/한도/OFF/실제 만료/최대 2회 claim 보호 유지. 완료 생성 반복·중복 게시 없음 |
| Proxy | 실제 signal 취소 전파, reader/listener 정리, bounded 오류 body, streaming backpressure | 독립 upstream 실패를 숨기지 않음. 헤더 후 실패를 정상 EOF로 바꾸지 않음. mutation 재전송 없음 |
| API key | stale configuration에 typed 409, 활동 저장 후 카드 재조회, draft와 metadata 분리 | 실제 credential 충돌은 명시 검토. load/save/delete/unknown 구분. key 자동 재전송/노출 없음 |
| PNG | writer 밖 검증·인코딩 1회·staging, fresh draft/owner/CAS apply, lease와 canonical 참조 기반 정리 | 원본 PNG/metadata·입력 한도·이전 파일 보존. caller의 이미 flush된 쓰기도 건드리지 않음 |
| Profile | 업로더의 아바타 외곽만 flex로 변경 | 공통 Avatar, crop, upload, 테두리 의미 불변. 고정 6px 보정 없음 |

기능별 책임과 버전 계약은 [backend architecture](../../backend/ARCHITECTURE.md), [frontend architecture](../../frontend/ARCHITECTURE.md), [product shell](../architecture/frontend-product-shell.md)에 반영했다.

## 실제 실행한 검증

건수는 실행 묶음별 결과다. 겹치는 파일의 재실행이 있으므로 합산해 고유 테스트 수라고 표시하지 않는다. V00–V130은 131개의 검증 계약이며 pytest 131개라는 뜻이 아니다.

T2 실행 뒤 Identity 실패 주입/읽기 비용 검증 5개를 같은 파일에 추가해 T6으로 따로 통과시켰다. 따라서 이후 T2 명령을 재실행하면 수집 건수가 당시 154개보다 늘어난다. 마지막 변경 Python 88파일은 AST 구문 검사도 통과했다. Ruff는 설치되어 있지 않아 실행 결과를 주장하지 않는다.

| 증거 ID | 실행 범위 | 결과 |
|---|---|---|
| T1 | Identity/browser security/session/logout/environment/admission/local owner/credential/SQLite 회귀 | **78 PASS**, 232.86초. per-request cookie deprecation warning 13개 |
| T2 | 상황 언어 자격·과거 binding·target schema·runtime 생성/query·Chat receipt·local entry·architecture 회귀 | **154 PASS**, 496.60초 |
| T3 | SNS restart→proof→situation→item/FTS/evidence 및 기존 activity receipt/application/contract | **48 PASS**, 40.02초 |
| T4 | PNG 준비·card metadata·creator registration | **30 PASS / 3 SKIP**, 342.84초. SKIP은 선택적 외부 카드 파일 부재; 합성 PNG/JSON 검증은 실행 |
| T5 | bootstrap/credential/PNG/recovery/stop 5 writer 실제 file SQLite 결합 | **1 PASS**, 17.53초. 아래 측정값 참조 |
| T6 | prepare의 user flush/binding/session/commit 실패 및 정상 인증 read 쓰기 0 | **5 PASS / 11 deselected**, 55.01초 |
| T7 | 실제 Next/static 브라우저의 en-US/ko-KR/ja-JP, 2탭, 만료, stop/Continue, 늦은 cookie | **8 PASS**. 추가 설정 시나리오 2개는 최초 실행에서 잘못된 테스트 버튼 이름 때문에 timeout |
| T8 | 실제 PNG 등록→활동 설정→SNS key→commit 응답 유실→명시 검토→fake SNS/Chat/근거→stop/Continue, Next/static | 선택자를 실제 Reload settings로 수정한 뒤 **2 PASS**, 1.1분. 제품 코드를 우회하거나 timeout을 늘리지 않음 |
| T9 | 실제 React CredentialFields + IndexedDB/BroadcastChannel 브라우저 harness | **PASS**: config-only refresh, 입력 유지, 실제 revision 충돌, 결과 불명 후 GET, load 오류, 2탭 ID/stop/install 격리 |
| T10 | 실제 Profile uploader/근거 Dialog + compiled CSS 브라우저 harness | **PASS**: ko/en·100/125/150%·이미지/fallback/배너/overlay 12조합, crop 취소/적용, 늦은 decode·scope 교체, 좁은 화면/키보드/HTML literal |
| T11 | proxy unit + 실제 Next/fake upstream disconnect + 기존 world-package proxy security | **PASS**: header/stream/upload 중단, 단일 POST, broken NDJSON/502, listener/reader 정리 |
| T12 | local-entry/identity-session/user-environment Node harness, ko/en catalog, 변경 파일 ESLint | **PASS**. identity 기존 11 request 계약+명시적 2 protocol 대체, 오류/저장 이벤트; 환경 20 native locale 사례. catalog 16 namespace/2,715 key. 변경 TS/TSX 42파일 lint |
| T13 | Next production 및 static production build | **둘 다 PASS**. Next compile 16.4초+type 3.8초, static compile 14.9초+type 19.4초. 공통 auth/DTO와 실제 Next/static 검증용 빌드가 필요했음 |
| T14 | native route unit | product_windows::tests **11 PASS / 19 filtered**. 실제 WebView/설치 앱 재실행은 미검증 |
| T15 | architecture/design 계약, 변경 Python 구문, diff | frontend 14 feature/legacy 0, backend 1,587 modules/6,907 edges/legacy 0, design raw colors 1,129/34 files/18 surfaces/route gaps 0. git diff --check PASS |
| T16 | 새 evidence projection 및 기존 Chat/관계 정책 추가 회귀 | 새 projection **9 PASS**; 관련 기존 Chat 회귀 **89 PASS**, 관계/공동활동 회귀 **126 PASS**. T2/T3와 일부 책임이 겹침 |

T1 실행(backend cwd):

```powershell
.venv/Scripts/python.exe -m pytest tests/identity/test_browser_session_security.py tests/identity/test_auth_session_contract.py tests/identity/test_session_logout_security.py tests/identity/test_local_environment.py tests/identity/test_environment_admission.py tests/identity/test_l1_local_owner_session.py tests/identity/test_world_credentials.py tests/test_l3_er2_sqlite_concurrency.py -q --tb=short -x
```

T2 실행(backend cwd):

```powershell
.venv/Scripts/python.exe -m pytest tests/memory/test_situation_language_eligibility.py tests/memory/test_situation_parent_binding_recovery.py tests/memory/test_situation_target_schema.py tests/runtime/test_activity_situation_generation.py tests/runtime/test_situation_query_language.py tests/chat/test_activity_situation_receipt.py tests/identity/test_local_entry.py tests/identity/test_l1_identity_architecture.py tests/test_t2_5_architecture_boundaries.py tests/test_l2_5_frontend_architecture_boundaries.py -q
```

T3–T6 실행(backend cwd):

```powershell
.venv/Scripts/python.exe -m pytest tests/runtime/test_stability_memory_integration.py tests/runtime/test_relationship_effect_progress.py tests/runtime/test_interrupted_routine_recovery.py tests/memory/test_activity_situation_contract.py tests/memory/test_activity_situation_application.py tests/memory/test_activity_situation_receipt.py -q
.venv/Scripts/python.exe -m pytest tests/test_card_import_preparation.py tests/test_card_metadata_compatibility.py tests/test_creator_card_registration.py -q
.venv/Scripts/python.exe -m pytest tests/runtime/test_stability_writer_integration.py -q -s
.venv/Scripts/python.exe -m pytest tests/identity/test_local_entry.py -k 'prepare_failure or authenticated_reads' -q -s --tb=short
```

T7/T8 실행(browser-tests cwd):

```powershell
node node_modules/@playwright/test/cli.js test --config=playwright.local-entry.config.ts
node node_modules/@playwright/test/cli.js test --config=playwright.local-entry.config.ts --grep 'automatic entry connects'
```

T9–T13 경로(frontend cwd; 사전 설치된 Node/Playwright 사용):

```powershell
node scripts/test-local-entry.mjs
node scripts/test-identity-session.mjs
node scripts/test-user-environment.mjs
node scripts/test-proxy-lifecycle.mjs
node scripts/test-proxy-disconnect.mjs
node scripts/test-world-package-proxy.mjs
node scripts/check-ui-catalog.mjs
# ANGMOO_BROWSER_TEST_MODULES는 사용 가능한 Playwright node_modules 절대 경로.
node scripts/test-entry-settings-browser.mjs
node scripts/test-profile-evidence-browser.mjs
# 변경 TS/TSX 경로만 ESLint에 전달한다. 전체 lint/전체 pytest를 기본 실행하지 않는다.
# Next 빌드는 ANGMOO_NEXT_DIST_DIR=.next-local-stability로 격리한다.
node node_modules/next/dist/bin/next build
node scripts/build-static.mjs
```

architecture/design 검사는 repository cwd의 scripts/ci/check_frontend_architecture_boundaries.py, check_architecture_boundaries.py --inventory <scratch inventory>, check_frontend_design_contract.py --check로 실행했다. fresh scratch inventory에서 실제 경계를 검사했다. 디자인 inventory는 이번 **진단 screenshot 두 호출 추가(64→66)** 및 변경 LOCAL 파일 hash만 반영했다. canonical PNG·허용 오차·색상 규칙을 바꾸지 않았다.

## 실측과 해석 한계

| 작업 | 전체 ms | writer wait ms | writer hold ms | SQL 건수 | bounded retry |
|---|---:|---:|---:|---:|---:|
| 기존 owner bootstrap prepare | 23.024 | 1.165 | 21.096 | 8 | 0 |
| SNS credential | 161.928 | 미계측 | 미계측 | 13 | 0 |
| PNG prepare/apply | 234.106 | 43.273 | 30.359 | 8 | 0 |
| scheduler recovery | 190.155 | 28.928 | 19.576 | 7 | 1 |
| client stop | 110.422 | 19.826 | 87.378 | 6 | 0 |

- 위 값은 이 PC의 합성 file SQLite 5 writer 동시 실행 **한 표본**이다. ARM64 수치·통계적 p95·일반 성능 보장은 아니다. credential의 wait/hold를 0으로 취급하지 않는다.
- 정상 인증 요청 10회: SELECT 20건, 쓰기 0. 재접속에서 유효 세션을 매번 발급하지 않는 것은 별도 controller/browser assertion으로 확인했다.
- PNG encoder를 barrier로 멈춘 동안 다른 연결의 UPDATE가 진행했다(관측 표본 약 15.458ms). 최종 apply만 writer를 사용한다. PNG 인코딩은 요청당 1회다.
- 관계 proof 조회는 앞선 행동당 5 SQL의 bounded lookup으로 측정했다. 판단당 최대 3행동이므로 앞선 proof는 최대 2개다. 전역 관계 scan/AI 재호출을 추가하지 않았다.
- 실제 프로필 baseline 여분은 약 5.333px였으며 수정 후 12조합의 외곽 여분이 반올림 허용 내 0이었다. 과거 관찰의 5.99px을 보정 상수로 쓰지 않았다.
- 관찰 당시 heartbeat 실패 6회의 잠금 소유자·hold 시간은 소급 확정하지 않았다. 이번 변경은 긴 PNG writer 구조와 중복 변환을 해결한 것이다.
- 기존 retry/전역 timeout/SQLite 동시 쓰기 원칙을 확대하지 않았다. 쓰기 경합이 절대 발생하지 않는다고 주장하지 않는다.

## 증거 위치와 환경 분리

- [초기 브라우저 8통과·선택자 2실패 기록](../../../.task-output/local-stability-validation/browser-initial-8-pass-2-selector-fail.json)
- [선택자 수정 후 Next/static 2통과 기록](../../../.task-output/local-stability-validation/browser-final-2-pass.json)
- [프로필 치수 측정](../../../.task-output/profile-evidence-browser-1792414389531/measurements.json)
- [프로필 한국어 좁은 화면](../../../.task-output/profile-evidence-browser-1792414389531/profile-ko-small.png)
- [영어 근거 Dialog](../../../.task-output/profile-evidence-browser-1792414389531/evidence-en-small.png)
- [credential 오류·검토 UI](../../../.task-output/entry-settings-browser-1792414382834/credential-error.png)
- 최종 registration/settings 진단은 artifacts/local-entry-browser/{next,static}-registered-settings.png에 저장했다. 모두 합성 데이터이며 커밋된 canonical visual baseline은 아니다.

실제 브라우저 통합은 포트 3490/3491/3492와 일회용 SQLite/media를 사용했다. identity/environment/default World/profile/PNG 등록/활동 설정/credential 저장은 실제 backend 경로다. SNS feed·Chat streaming·evidence API는 같은 합성 ID에 결합한 **fake provider-boundary payload**를 사용한다. 실제 SNS effect→receipt→item→FTS→evidence 연결은 T3의 backend integration에서 별도로 확인했다. 이 두 증거를 실제 모델/실제 자율활동의 하나의 관찰 세션으로 합쳐 주장하지 않는다.

T9는 실제 CredentialFields/IDB를 구동하되 transport와 auth hook 일부를 fixture로 대체한다. T10은 실제 uploader/Dialog/CSS를 구동하되 network/runtime hooks를 fixture로 대체한다. 실제 설치 앱의 직접 USER CHECK가 아니다.

## I00–I219 처리와 원문 대응

- I00–I11: 기준선·소유권·통합 계약·새 로컬 브랜치 확인.
- I12–I27: Next 요청 취소·stream·오류 구분 구현·확인.
- I28–I87: Identity/migration/자동 준비/세션/환경/World/계정·설치명 구현·확인.
- I88–I123: 상황 지침/validation/과거 receipt/근거 projection/ko-en 표시 구현·확인.
- I124–I159: SNS 관계 현재성과 취소·재개 구현·확인.
- I160–I189: credential/PNG 경계 구현·확인.
- I190–I195: Profile 최소 레이아웃 및 실제 CSS 치수/crop 확인.
- I196–I211: 범위 검증·측정·영역 간 연결. I199는 native unit PASS와 실제 WebView 미검증을 분리하는 계획의 예외를 적용했다.
- I212–I219: architecture·검증 문서·변경 review·DCO 로컬 커밋·main 불변·최종 보고.

원문 A는 자동 사용자·세션·World 준비 문서, 원문 B는 상황기억·근거·관계·안정화 문서다. 통합 계획 §20의 I/V 대응표를 적용한다. A의 수동 진입/화면 이동 해석과 B의 최초 수동 이름·확인 UI는 통합 계약으로 대체했다. 특히 **기존 앱 목록 첫 화면**, **신규 이름 사용자/User 통일**, **첫 안내 배너 없음**이 우선한다. 기존 문서/관찰 근거를 수정 완료 증거로 재작성하지 않는다.

## 검증 계약별 판독

PASS는 적힌 격리 단위/HTTP/브라우저 또는 계층별 회귀 범위의 결과다. 모든 조합을 한 실환경 세션에서 검증했다는 뜻이 아니다. 실제 Tauri/ARM64/AI 품질은 미검증 목록을 따른다.

| ID | 계약 | 판독 | 증거와 실제 범위 |
|---|---|---|---|
| V00 | ko 신규 설치 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V01 | en 신규 설치 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V02 | 다른/누락 언어 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V03 | claimed 재접속 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V04 | legacy 연결 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V05 | 복구 상태 | PASS · 계층별 회귀 | T1/T2/T7: 신규/기존/복구·locale·소유 데이터 |
| V06 | 오류 구분 | PASS · 계층별 회귀 | T1/T2/T12: typed 오류·challenge·보호된 HTTP 경로 |
| V07 | 초기 중복 | PASS · 계층별 회귀 | T1/T2/T12: typed 오류·challenge·보호된 HTTP 경로 |
| V08 | challenge | PASS · 계층별 회귀 | T1/T2/T12: typed 오류·challenge·보호된 HTTP 경로 |
| V09 | 출처·Tauri | PASS · 계층별 회귀 | T1/T2/T12: typed 오류·challenge·보호된 HTTP 경로 |
| V10 | prepare 응답 유실 | PASS · 계층별 회귀 | T7/T8/T12: commit 후 응답 유실과 상태 재확인 |
| V11 | prepare rollback | PASS · 계층별 회귀 | T6: 4개 실패 경계에서 부분 owner/session 0 |
| V12 | 명시적 stop | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V13 | 발급 먼저 commit | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V14 | stop 먼저 commit | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V15 | stop 응답 유실 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V16 | resume·응답 유실 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V17 | 역순 전이 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V18 | 여러 탭 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: generation·중복·역순 응답·여러 탭 |
| V19 | 앱 재실행 | 부분 확인 · 실제 Tauri 미검증 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V20 | 다른 client | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V21 | 저장소 제약 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V22 | 자연 만료 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V23 | 복수 401 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V24 | mutation 보호 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V25 | 기존 session 업그레이드 | PASS · 계층별 회귀 | T1/T2/T7/T9/T12: persistent stop·다른 client·만료·legacy session |
| V26 | 환경 선후 관계 | PASS · 계층별 회귀 | T1/T7/T12: 환경 confirmation/lease 뒤 World 준비 |
| V27 | 환경 동시 보고 | PASS · 계층별 회귀 | T1/T7/T12: 환경 confirmation/lease 뒤 World 준비 |
| V28 | World 중복·유실 | PASS · 계층별 회귀 | T1/T7/T12: 환경 confirmation/lease 뒤 World 준비 |
| V29 | 기존 World 보존 | PASS · 계층별 회귀 | T1/T7/T12: 환경 confirmation/lease 뒤 World 준비 |
| V30 | 기존 앱 목록 첫 진입 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V31 | 기존 탐색 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V32 | deep link | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V33 | 늦은 UI 결과 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V34 | 계정 이름 편집 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V35 | 설치명 편집 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V36 | 데이터 보존 | PASS · 계층별 회귀 | T7/T8/T12/T14: 앱 목록·기존 목적지·이름 편집·데이터 보존 |
| V37 | ko/en UI | PASS · 계층별 회귀 | T7/T9/T10/T12: ko/en·실제 DOM/CSS·semantic controls |
| V38 | 작은 화면·조작 | PASS · 계층별 회귀 | T7/T9/T10/T12: ko/en·실제 DOM/CSS·semantic controls |
| V39 | migration | PASS · 계층별 회귀 | T1/T2/T7/T12: v39→v40·cookie·protocol 2 호환 거절 |
| V40 | HTTP 계약·proxy | PASS · 계층별 회귀 | T1/T2/T7/T12: v39→v40·cookie·protocol 2 호환 거절 |
| V41 | 버전 혼합 | PASS · 계층별 회귀 | T1/T2/T7/T12: v39→v40·cookie·protocol 2 호환 거절 |
| V42 | writer 경계 | PASS · 계층별 회귀 | T1/T4/T5/T6/T11/T12: SQLite 경계·bounded busy·read 쓰기 0·합성 네트워크 |
| V43 | 비용 측정 | PASS · 계층별 회귀 | T1/T4/T5/T6/T11/T12: SQLite 경계·bounded busy·read 쓰기 0·합성 네트워크 |
| V44 | 원자성·busy | PASS · 계층별 회귀 | T1/T4/T5/T6/T11/T12: SQLite 경계·bounded busy·read 쓰기 0·합성 네트워크 |
| V45 | 비밀·외부 호출 | PASS · 계층별 회귀 | T1/T4/T5/T6/T11/T12: SQLite 경계·bounded busy·read 쓰기 0·합성 네트워크 |
| V46 | 실제 Tauri 구분 | 부분 확인 · 실제 Tauri 미검증 | T14/T7: native unit과 static browser만 실행 |
| V47 | 변경 범위 | PASS · 계층별 회귀 | T13/T15: 변경 경계·타입·디자인·Git 범위 |
| V48 | 기준 fixture | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V49 | 언어 안내 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V50 | 값 검증 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V51 | 기존 구조 검사 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V52 | SNS 보조 출력 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V53 | Chat 보조 출력 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V54 | 저장 원자성 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V55 | 과거 receipt | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V56 | 기억·인덱스 | PASS · 계층별 회귀 | T2/T3: 현행/과거 상황 출력·접수·자격·적용/검색 |
| V57 | 근거 projection | PASS · 계층별 회귀 | T3/T16: projection 조립·고정 digest·최종 저장/조회 보호 |
| V58 | 잘림·악성 유사 입력 | PASS · 계층별 회귀 | T3/T16: projection 조립·고정 digest·최종 저장/조회 보호 |
| V59 | 최종 저장 | PASS · 계층별 회귀 | T3/T16: projection 조립·고정 digest·최종 저장/조회 보호 |
| V60 | 접근 회수 | PASS · 계층별 회귀 | T3/T16: projection 조립·고정 digest·최종 저장/조회 보호 |
| V61 | 이름·시간 binding | PASS · 계층별 회귀 | T3/T16: projection 조립·고정 digest·최종 저장/조회 보호 |
| V62 | 화면 ko/en | PASS · 계층별 회귀 | T7/T10/T12: 영어/한국어 label과 literal 원문 분리 |
| V63 | 다른 locale | PASS · 계층별 회귀 | T7/T10/T12: 영어/한국어 label과 literal 원문 분리 |
| V64 | 기본 이름 생성 | PASS · 계층별 회귀 | T1/T7/T12: 신규 User/사용자와 기존 이름·환경 순서 |
| V65 | 기존 이름 보존 | PASS · 계층별 회귀 | T1/T7/T12: 신규 User/사용자와 기존 이름·환경 순서 |
| V66 | 환경 준비 | PASS · 계층별 회귀 | T1/T7/T12: 신규 User/사용자와 기존 이름·환경 순서 |
| V67 | 자기 변경 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V68 | 외부 변경 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V69 | 별도 보호 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V70 | 증명 오염 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V71 | 재시작 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V72 | 부분 성공 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V73 | 관계 정책 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V74 | 비용·잠금 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V75 | 통합 계약 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V76 | 호환 경계 | PASS · 계층별 회귀 | T3/T16: canonical effect proof·외부 변경/ABA/오염 차단·재시작 |
| V77 | 지침 통합·범위 | PASS · 계층별 회귀 | T2/T3: 공통 prompt/field 안내·합성 자연어 보존 |
| V78 | 자연어 자유·맥락 보존 | PASS · 계층별 회귀 | T2/T3: 공통 prompt/field 안내·합성 자연어 보존 |
| V79 | proxy 기준 재현 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V80 | 취소 식별 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V81 | 업로드·오류 본문 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V82 | 응답 streaming | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V83 | 장애 계약 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V84 | proxy 보안·개인정보 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V85 | mutation 불확정 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V86 | proxy 자원·다국어 | PASS · 계층별 회귀 | T11: 실제 Next/fake upstream 취소·장애·stream·자원 수명 |
| V87 | 복구 예약 재현 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V88 | 재생성 금지 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V89 | 정리 원자성 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V90 | lease·실제 drain | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V91 | 정상 간격·설정 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V92 | 영속 재시작·claim | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V93 | 실제 만료·외부 변경 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V94 | commit 뒤 취소 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V95 | 판단 보호 결합 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V96 | checkpoint 제한 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V97 | 복구 비용·공정성 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V98 | 시간 경계 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V99 | 관측 일치 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V100 | 범위 통합 | PASS · 계층별 회귀 | T3/T5: 유효 시간 내 durable 초안 재개·멱등 게시·기존 claim/만료 보호 |
| V101 | Profile 치수 | PASS · 계층별 회귀 | T10: 실제 CSS 12조합·crop 취소/적용·늦은 decode |
| V102 | Profile 소비자 | PASS · 계층별 회귀 | T10: 실제 CSS 12조합·crop 취소/적용·늦은 decode |
| V103 | 오류 안내 분류 | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V104 | 정상 키 저장 | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V105 | 입력 보존 | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V106 | 같은 화면 순서 | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V107 | 갱신 race | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V108 | 실제 충돌 | PASS · 계층별 회귀 | T8/T9/T12: 오류 상태·미저장 입력·configuration/credential 충돌 분리 |
| V109 | HTTP·원자성 | PASS · 계층별 회귀 | T1/T8/T9/T12: typed 409·rollback·결과 불명 GET·ko/en 오류 |
| V110 | 통신 결과 불명 | PASS · 계층별 회귀 | T1/T8/T9/T12: typed 409·rollback·결과 불명 GET·ko/en 오류 |
| V111 | 키 보호·공통 소비자 | PASS · 계층별 회귀 | T1/T8/T9/T12: typed 409·rollback·결과 불명 GET·ko/en 오류 |
| V112 | 오류 ko/en·접근성 | PASS · 계층별 회귀 | T1/T8/T9/T12: typed 409·rollback·결과 불명 GET·ko/en 오류 |
| V113 | PNG 변환 계약 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V114 | 쓰기 경합 경계 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V115 | 최종 현재성 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V116 | 파일·commit 실패 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V117 | 중단·정리 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V118 | Session 경계 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V119 | 제한·권한 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V120 | 제한된 비용 | PASS · 계층별 회귀 | T4/T5: 1회 encode·fresh apply·canonical 파일 보존·writer 경계 |
| V121 | 새 범위 통합 | PASS · 계층별 회귀 | T8/T4/T11: 실제 등록/설정/키와 응답 유실·writer/이름 계약 연결 |
| V122 | 기존 설계 연결 | PASS · 계층별 회귀 | T8/T4/T11: 실제 등록/설정/키와 응답 유실·writer/이름 계약 연결 |
| V123 | auth+proxy | PASS · 계층별 회귀 | T7/T11: 실제 Next cookie 지연+generation와 disconnect 별도 결합 |
| V124 | auth+credential | PASS · 계층별 회귀 | T7/T8/T9/T12: 만료·입력 scope·실제 commit 응답 유실을 계층별 확인 |
| V125 | auth+PNG | PASS · 계층별 회귀 | T4/T10: 늦은 UI decode/scope와 fresh apply/commit 결과 불명 파일 보호 |
| V126 | session+SNS | PASS · 계층별 회귀 | T3/T5: 동시 stop/recovery·자율활동/다른 client 보존 |
| V127 | 관계+기억+재개 | PASS · 계층별 회귀 | T3/T10: restart effect→receipt→item/FTS→projection, UI는 별도 fixture |
| V128 | 언어 세 경계 | PASS · 계층별 회귀 | T2/T7/T12: en-US/ko-KR/ja-JP 신규 이름과 UI/생성 locale 구분 |
| V129 | 전체 기능 연결 | PASS · 계층별 회귀 | T8/T3: 실제 entry/등록/설정+fake SNS/Chat UI, 실제 기억 적용은 backend 별도 |
| V130 | writer 결합 | PASS · 계층별 회귀 | T5: 5개 writer의 실제 file SQLite 동시 진행·측정 |

## 별도로 남기는 미검증·호환 제한

1. **실제 Tauri/WebView 앱 실행·종료 후 재실행·native cookie partition은 미검증**이다. native route unit 11개와 static browser 통과로 대체하지 않는다(V19/V46, I199).
2. 현재 실행 중인 Docker/ARM64 후보, 설치판, Android/Termux 및 실제 AI 품질·새 4시간 관찰은 수행하지 않았다. 이번 소스 수정이 기존 실행 이미지에 자동 반영되지 않는다.
3. browser SNS/Chat 내용은 합성 payload다. 실제 모델이 항상 자연스러운 상황 설명을 출력한다거나 관계 판단 품질이 개선됐다고 단정하지 않는다. 검증은 부적절한 언어 표기 단독 값의 저장 차단과 정상 경로 보존을 입증한다.
4. 과거 v1 근거에는 label/literal 경계가 없다. 원문을 자동 번역하거나 한국어 고정 안내를 임의 파싱하지 않고 제한 안내와 함께 보존한다.
5. protocol 2가 필요한 local 요청은 구 client/server 혼합에서 명시적으로 실패한다. 구 발급 endpoint로 조용히 우회하지 않는다. 기존 유효 legacy session의 편입은 token/TTL을 보존한다.
6. 오래 중단되어 실제 유효 시간이 지난 SNS 초안은 계속 실패한다. durable output이 없으면 이전 응답을 보존했다고 주장하거나 무료 재생성으로 숨기지 않는다.
7. PNG 테스트의 선택적 외부 카드 fixture 3개는 미제공으로 SKIP이다. 기존 실제 사용자 카드·개인 데이터는 사용하지 않았다.
8. auth+PNG와 auth+credential의 scope/응답 유실은 UI·HTTP·DB 계층에 나눠 검증했다. 실제 native 프로세스 중단과 모든 timing 조합을 포괄한 검증은 아니다.
9. fixture DROP 단계에서 SQLite 순환 FK 정렬 SAWarning, Next test server의 standalone 안내, Node 색상 환경 경고가 있었다. 일회용 fixture/검증 실행의 경고로 분리했으며 실패를 숨기기 위해 제품 로그를 억제하지 않았다.
