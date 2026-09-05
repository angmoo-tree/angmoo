# 백엔드 구조 전환 실행 결과

## 범위와 현재 상태

2026-09-05에 §8.2 AR-G0부터 AR-B8-B까지 실행을 시작했다. 사용자 검증·PR·merge는 이번 실행에서 위임받은 권한으로 수행하며, 각 검증은 실제 수행한 범위와 commit을 기록한다. Release/Production, §8.3 프론트엔드 이전, AR-X와 P8-L-S 실제 AI 품질·인과 검증은 별도 범위다.

출발점은 #263 merge `d7037625a19071eb279ad2ea35c3ace6fe5b5289`, tree `35ded40a2b5fd33d1a54dac3a396e72d24c88714`다. 원격 main과 로컬 HEAD가 일치하고 시작 시 작업 트리는 깨끗했다. 원본 #258 기준과 승인 public test 목록, frozen migration 자료는 계속 보존한다.

| 단계 | 상태 | 범위 |
| --- | --- | --- |
| AR-G0 | PR #265 MERGED · PR CI/POST-MERGE PASS | 후속 체크포인트·부분 scope·단계/소유권·Actions 연결 |
| AR-G1 | PR #266 MERGED · PR CI PASS · POST-MERGE IN PROGRESS | 설정·개발 환경 경로 |
| AR-G2 | LOCAL VERIFIED · PR/MERGE PENDING | 공통 오류 4개·cursor bytes helper 2개·소비자/테스트 이전 |
| AR-G3 | IMPLEMENTED · LOCAL VERIFICATION · PR/CI PENDING | logging.ini·초기화·배포 자원 연결 |
| AR-G4 | LOCAL VERIFIED · PR PENDING | Alembic 물리 경로·역사 본문 보존; G5 최종 모델 등록 연결 대기 |
| AR-B2 | IDENTITY PR #270 · CHARACTER FOUNDATION INTEGRATION | Identity full backend PASS; Character 기반·Creator 정책 통합 후 HTTP/Worlds/WC 후속 |
| AR-B3 | NOT STARTED | World Package→media |
| AR-B4 | ROUTINES A1/A2/A3a/b LOCAL VERIFIED · INTEGRATION/PR PENDING | 실제 계획·guarded lifecycle·실행 claim 이전; joint·routine_posts·resident 후속 |
| AR-B5 | NOT STARTED | social→relationships→projection |
| AR-B6 | NOT STARTED | Chat transport→generation→retrieval/response |
| AR-B7 | NOT STARTED | Memory read/write→owner→batch→runtime |
| AR-B8-A | NOT STARTED | 잔여 업무·G06 단일 앱 생성·호환·소비자 전환 |
| AR-G5 | NOT STARTED | models.py·단일 Base·database·등록 |
| AR-B8-B | NOT STARTED | G06 검증 후 제거·호환 정리·백엔드 통합 |

## AR-G0: 기준과 검사를 먼저 연결

추적 Issue는 [#264](https://github.com/angmoo-tree/angmoo/issues/264), 작업 branch는 `refactor/ar-g0-backend-transition-guards`다. 이 단계는 제품 동작이나 전환 완료 도메인 범위를 바꾸지 않는다.

- K05~K23의 backend 단계를 계획 순서에 맞추고 backend와 frontend 진행 상태를 분리했다. 기존 Device Home 파일럿의 검증 상태는 유지한다.
- K24의 backend source 34개를 Tree, 캐릭터 설정, routine 호환, Social 근거, media 검증, 활동 유지보수, prompt/name 정책, runtime adapter, 공통 transaction/limit, fixture 계약, package/router 조립으로 나눴다. 각 묶음의 목표 경로와 담당 단계가 inventory에 있다.
- #263의 generation 접미사·64자 v8 fixture·충돌/재설치 검증을 #258 원본과 함께 보호할 후속 체크포인트와 검사 지원을 준비한다.
- Chat·Memory의 정확한 module/entry/호환 edge 단위 scope를 추가한다. 아직 옮기지 않은 형제 모듈에는 기존 보호를 유지한다.
- G06의 최종 목표는 `main.py` 단일 앱 생성이다. 현재 Local 기능과 지원 profile별 계약을 보존하고 B8-B에서 임시 `public_main.py`를 제거한다.

검증·PR-head·merge·post-merge 결과는 실제 결과가 나온 뒤 아래에 추가한다. 위 단계의 NOT STARTED/IN PROGRESS는 테스트 시작이나 파일 생성만으로 PASS가 되지 않는다.

### 착수 시 확인한 증거

제품 코드를 변경하지 않은 상태의 초기 전체 backend 실행은 `1,885 passed / 22 skipped / 26 warnings`, 428.00초, exit 0이었다. 전체 실행 동안 G0 검사 지원을 병행 수정했으므로 이 결과를 최종 G0 commit 전체 테스트 결과로 재사용하지 않는다. 기존 skip은 PostgreSQL 전용 환경과 hosted lifespan 조건이며 새 skip을 추가하지 않는다.

기존 live inventory와 경계 검사는 backend 680 modules·1,837 internal edges·기존 exact legacy edges 312, frontend 13 features·legacy exact edges 0을 유지했다. ER0는 PostgreSQL inventory 75 files·migration 87·Neo4j query 24·Next route 44·parity workload 7, CI policy는 required 10·advisory 1·workflow 8로 통과했다. 이는 제품 SQLite 검증을 PostgreSQL 실행 증거로 확대하는 수치가 아니다.

리뷰에서 독립 node를 기존 목적지에 흡수하는 map, 새 skip/xfail, test helper assertion 삭제를 잡지 못하는 초안의 빈틈을 찾아 보완했다. 초안 preservation 결과 `PR258 1,867 / PR263 1,907 / current 1,981`은 그 시점의 검사 통과 기록이며 최종 보완판 결과와 구분한다.

### G0 로컬 검증

새 backend 부분 scope·public node 다단계 이동·체크포인트 검사와 기존 OSS/backend/frontend 경계 검사를 함께 실행해 **174 passed / 14.98초**를 확인했다. 최종 보존 검사는 **#258 1,867 / #263 1,907 / 보존 계보 1,907 / 현재 2,021 nodes, items 37 PASS**이며 full/public API·OpenAPI component·ORM table 계약도 동일했다. 원본 baseline과 승인 public 604 node 파일은 수정하지 않았다.

후속 체크포인트의 고정 digest는 `264aaf30d2534b8b7799a262edf6ff25055a0cfbf900cbb2bb8b11fcb8dd963b`다. source 도입 commit을 먼저 만들고, 그 commit의 새 검사 코드·test 증거를 별도 metadata commit으로 추가하여 PR-head 후보를 검증한다. 아직 PR-head·merge·post-merge PASS는 아니다.

첫 도입 commit `c45edca0dd1d8a2426f47a37219dd740823ab902`에서 새 파일 7개·test node 115개의 증거를 캡처했다. 첫 실제 캡처에서 기존 frontend re-export 파일을 신규 파일로 오판해 실패했으며, 원래 보호 경로와 최종 목적지의 합집합으로 수정하고 회귀 테스트를 추가했다. 이 보완의 focused 검사 65개가 통과했고, 체크포인트 원본은 변경하지 않았다. 증거 추가 전의 미공개 commit은 보완판으로 대체했으며 실패한 캡처 결과를 성공 이력에 넣지 않았다.

### PR 검증 중 발견한 inventory 누락

[PR #265](https://github.com/angmoo-tree/angmoo/pull/265)의 첫 head `0a682d29fa8d99a208cf98dd59a8635781d82087`에서 architecture-boundary는 통과했지만 oss-boundary의 deferred runtime inventory 검사가 실패했다. 새 체크포인트가 보존한 제품 URL·privacy contact 문자열이 live inventory에 빠진 원인이었다. 기존 생성기로 `security/t2_deferred_runtime_inventory.json`을 갱신해 체크포인트 경로 1개를 추가했다. 검사 예외나 frozen 체크포인트 내용은 바꾸지 않았다. 수정 head의 전체 Actions 결과는 별도로 확인한다.

다음 head `de83dae`에서는 위 inventory 검사가 통과한 뒤 secret scanner가 체크포인트의 기존 synthetic Google API key fixture를 감지했다. #263의 `test_langgraph_resident_engine.py::test_generate_json_records_postprocess_error_on_repaired_success` assertion 및 기존 allowlist 4개와 값이 정확히 일치함을 확인했다. 고정 체크포인트를 수정하지 않고 해당 경로·규칙·값에 한정한 예외 1개와 원본 commit/test/blob·값 hash 증거를 추가했다. 기존 24개 항목은 그대로 유지했다. 관련 검사 **21 passed**, metadata **exact_tuples=25 PASS**, 현재 트리와 전체 Git 이력 검사 **fatal=0**이었다. 다른 경로·규칙·값으로 예외가 확대되지 않는 회귀 검사도 포함한다.

Head `88e4269`에서 다음 Gitleaks 단계가 체크포인트의 파일 blob·API/ORM fingerprint를 일반 API key로 감지했다(CI 64건, 같은 버전 Windows 재현 65건). 모든 발견 줄을 고정 체크포인트의 실제 Git blob SHA-1 또는 계약 SHA-256과 대조했고, 중복을 제외한 정확 key/digest 55줄만 해당 체크포인트 경로·해당 규칙에 허용했다. 파일 전체·임의 해시·다른 키는 허용하지 않는다. Gitleaks 8.30.1 디렉터리 및 **302 commits** 이력 검사에서 발견 0건, 실제 도구의 다른 파일/값/키/synthetic credential 음성 대조에서 각 1건 탐지를 확인했다. 관련 Python 회귀는 **12 passed**였다.

같은 head의 전체 backend CI는 **2,007 passed / 22 skipped / 1 failed**였다. 실패한 새 체크포인트 검사는 shallow checkout에서 #263의 경로 지도를 읽지 못했다. 이미 full history인 architecture job과 일치하도록 Core CI backend checkout에도 `fetch-depth: 0`을 연결했다. 테스트·기준 commit은 바꾸지 않았다. 수정 후보의 전체 backend와 Actions 결과로 이 Gate를 다시 판정한다.

### G0 PR 검증과 병합

최종 PR head `4853eab7bf056df332849493fc403a13b9ace925`의 필수 Actions가 모두 SUCCESS였다. Core CI backend는 **2,010 passed / 기존 22 skipped / 26 warnings, 172.18초**였다. public 승인 604 nodes, architecture·보안·license/DCO·frontend·embedded migration·Tauri·Local Smoke·CodeQL을 통과했다. Windows Installer run `33954517762`에서 실제 NSIS/MSI 빌드·clean install·지원 이전 버전 직접 update·주입한 migration 실패 복구·aggregate Gate가 모두 SUCCESS였다.

PR #265는 위임된 권한으로 **2026-09-05 17:45:03 KST**, merge commit `255bd1401c2b925b83b7e2ba9bac790192a1a920`에 병합했다. source 도입 commit의 provenance를 보존하는 merge 방식이다. 이 merge의 post-merge Actions는 별도로 진행 중이며, 완료 전에는 post-merge PASS로 표시하지 않는다. G1은 이 main을 기준으로 연결했고 이후 단계도 순서대로 병합한다.

## AR-G1: 공통 설정과 소비자 전환

작업 branch는 `refactor/ar-g1-global-config`이며 구현 출발점은 AR-G0 `0a682d2`다. `app/core/config.py`의 단일 구현을 `app/config.py`로 옮기고 실제 import 소비자 71개 파일을 전환했다. 설정 원본과 정확 비교하면 `BACKEND_DIR`의 부모 깊이 `2 → 1`만 바뀐다. `Settings` 필드·기본값·타입·validator·설정 객체 생성은 그대로다. `runtime/configuration.py`의 설치 설정 조립과 credential 해석 책임도 유지한다.

- 새 전역 `app.config`만 경계 검사 scope에 등록했다. 미전환 도메인·기존 순환 검사·정확한 legacy edge 보호를 유지한다.
- `app.core.config` 호환 파일을 남기지 않았다. 활성 Python AST import는 0개다. 변경 가능한 Alembic `env.py`도 전환했으며 역사적 revision에는 이 import의 소비자가 없어 본문을 수정하지 않았다.
- 소스 이동 후에도 개발 `.env`, 기본 SQLite·media·graph의 기준 경로는 `backend`다. 다른 작업 디렉터리의 `.env`가 선택되지 않고 환경 변수·생성 인자 우선순위도 유지한다. 설치 설정은 명시적 runtime 조립을 계속 사용한다.
- startup-security suite의 기존 25 nodes를 `tests/config/test_startup_security.py`로 옮겼다. 원본 대비 import 외의 변경은 없고, 다른 업무·runtime 테스트는 원래 소유 경로에서 import만 바꿨다. 이동표는 원본 node마다 목적지를 명시한다.
- 별도 backend 경로와 `.env`를 사용하는 격리 회귀, 실제 main/public/runtime의 cold import·설정 객체 단일성 회귀를 추가했다. 테스트는 개발자의 실제 `.env`를 수정하지 않는다.
- core 실제 파일 목록에서 사라진 config 행을 L0 contract에서 제거하고 현재 architecture/L4/ER0/Memory batch inventory를 갱신했다. 고정 #258 기준·#263 체크포인트·승인 public nodes·역사적 exact secret allowlist는 변경하지 않았다.

### G1 로컬 검증

설정·startup-security·credential·runtime composition·sidecar/browser 보안 집중 검증은 **85 passed / 1 skipped / 1 warning, 44.15초**였다. skip은 기존 hosted lifespan 조건이며 새 skip을 추가하지 않았다. 경계·local runtime·architecture/L4/ER0 inventory·allowlist 메타데이터 집중 검증은 **30 passed, 10.92초**였다.

L0 contract는 services 2·core modules 18, architecture는 modules 680·internal edges 1,837·external imports 2,288·legacy exact edges 312로 통과했다. L4 inventory는 backend modules 680·frontend candidates 14·parity nodes 97이며, ER0는 PostgreSQL files 75·migrations 87·Neo4j queries 24·Next routes 44·parity workloads 7이다. Memory batch inventory도 현재 소스와 일치한다.

API·OpenAPI component·ORM 계약과 test node 보존 검사는 **#258 1,867 / #263 1,907 / 보존 계보 2,022 / 현재 2,024 nodes, items 37 PASS**였다. public baseline 검사는 승인 **604 nodes**를 유지했다. 기존 파일의 정확한 내용 비교와 `git diff --check`도 통과했다.

이 결과는 commit 전 작업 트리의 로컬 검증이다. 새 테스트 도입 증거는 source commit 후 별도 metadata commit으로 기록하며 PR-head·병합·post-merge 결과는 뒤에 추가한다. Docker·Tauri·installer 최종 후보 실행 및 G10·AR-B8-B 종료를 이 단계의 검사 통과로 대신하지 않는다.

G1 도입 commit `fe7c4ef`의 새 회귀 파일 1개·test node 2개를 도입 증거에 추가했다. 준비 branch에는 G0 head `4853eab`의 보안·checkout 보완을 병합했다. 준비 중 전체 suite 실행은 **2,001 passed / 22 skipped / 1 failed**였으나, 실행 도중 G0 보안 메타데이터가 합쳐져 이미 로드된 이전 checker와 새 allowlist가 혼재한 결과였다. 이를 동일 commit의 전체 검증으로 인정하지 않는다. 작업 트리를 고정한 뒤 보안 메타데이터와 설정 경로 검사를 새 프로세스에서 실행해 **14 passed / 10.46초**를 확인했다. 최종 PR의 전체 suite는 고정 checkout의 CI에서 다시 판정한다.

PR #266의 첫 head `3cc9ab7d9ae487a99d1964ef1f8d69392093e233`에서 architecture-boundary는 통과했지만 oss-boundary의 deferred runtime inventory가 옛 startup-security test 경로를 발견했다. 기존 generator로 해당 항목을 `backend/tests/config/test_startup_security.py`로 옮겼으며 marker·소유 단계·전체 파일 22개는 그대로다. 경계 예외를 추가하지 않고 CI와 동일한 공통 정책·배포·launcher·installer·metadata 검사와 inventory를 다시 확인했다. 수정 head의 필수 Actions로 PR Gate를 판정한다.


### 2026-09-05 AR-G0 post-merge 통과·AR-G1 병합

AR-G0 merge `255bd1401c2b925b83b7e2ba9bac790192a1a920`의 post-merge Core CI, Security and Governance, Local Smoke, Windows Advisory, CodeQL 및 Windows Installer run `33956118683`가 모두 SUCCESS였다. 설치 build·clean install·지원 이전 버전 update·migration 실패 복구·aggregate를 포함한다.

AR-G1 최종 PR head `bd43481a61f4b58a0a25b3ffca76343e9a699ba1`의 체크 23개가 모두 SUCCESS였다. Core backend는 **2,012 passed / 기존 22 skipped / 26 warnings, 201.47초**, Installer run `33956388356`은 build·clean·supported upgrade·failure recovery·aggregate 모두 통과했고 Host Tauri Dev도 통과했다. [PR #266](https://github.com/angmoo-tree/angmoo/pull/266)은 **18:35:46 KST**, merge `9a8d5b00998aa70650483d5b7067b53c67b28713`에 병합했다. 해당 merge의 post-merge Actions는 별도 진행 중이다.

다음 AR-G2 후보 `ca9191c`의 로컬 전체 backend는 **2,035 passed / 기존 22 skipped / 26 warnings, 465.32초**였다. G2는 공통 오류·cursor bytes와 현재 topology/역사 기준 검사 구분을 포함한다. G3 logging·G4 Alembic은 소스와 선행 도입 증거를 통합했고, B2 Identity·Characters·Worlds는 별도 준비 중이다. 순차 PR·병합을 이어가며 §8.2 전체 및 AR-B8-B 종료는 미완료다.

## AR-G2: 공통 오류와 cursor bytes 추출

작업 branch는 `refactor/ar-g2-common-contracts`, 준비 기준은 `de83dae2f656a96498064457ca3fc9b8d3dc30df`다. G0/G1의 순차 병합 뒤 통합할 별도 작업 트리에서 구현했으며 현재 기록은 로컬 검증이다. PR·merge·post-merge·설치 실행 완료로 확대하지 않는다.

- `app/exceptions.py`가 `SqliteConcurrencyError`, `SqliteBusyRetryExhausted`, `SqliteTaskQueueFull`, `RequestBodyTooLargeError`를 정의한다. 기존 core/runtime export는 같은 class identity를 유지하며 직접 업무 소비자는 새 정의를 import한다.
- `app/pagination.py`의 2개 함수는 bytes의 URL-safe Base64 encode/decode만 소유한다. Device Home JSON cursor와 Social AESGCM cursor의 JSON·version·AAD·nonce·key·scope·query·limit·오류는 그대로 유지한다.
- 기존 `test_request_body_limits.py`의 3개 node를 `tests/common/test_request_body_limits.py`로 이동하고 새 경로를 승인 map/inventory에 연결했다. 원본 public 604 파일과 PR258/PR263 기준선은 변경하지 않았다.
- 새 회귀는 Content-Length 없는 누적 body 초과의 실제 raise/catch, 공통 오류 identity, Social retry 503와 autonomy retry 409의 차이, 기준 commit에서 synthetic secret·nonce로 만든 이전 cursor, 인증 변조·World/WorldCharacter/tab scope를 검증한다.
- 첫 새 cursor fixture 실행에서 읽기 전용 설정 property에 값을 대입하는 테스트 오류가 발생했다. 제품 코드는 바꾸지 않고 테스트가 사용하는 module settings 객체를 synthetic fixture로 주입해 수정했다.

최종 집중 실행은 **44 passed / 1 warning / 14.98초**였다. 기존 Device Home·Social profile·request-body와 SQLite busy/queue·Social UoW/agent retry 회귀를 포함한다. 경고는 기존 Starlette/httpx deprecation이다.

보존 검사 `--contracts --nodes`는 **PR258 1,867 / PR263 1,907 / 보호 계보 2,022 / 현재 2,042 nodes**, items 37로 통과했다. full/public API·ORM 계약과 기존 테스트/helper assertion 보호를 유지했다. 이 수치는 G2 도입 증거를 추가하기 전 로컬 후보의 수집 결과이며 후속 source commit과 additions 기록을 별도로 연결한다.

Live import 검사는 **682 modules / 1,844 internal edges / legacy exact edges 312**로 통과했다. 두 전역 scope만 추가했고 다른 업무를 완료 범위로 올리지 않았다. ER0는 운영 코드 import 위치 변화로 생긴 source hash/line number만 재생성했으며 **PostgreSQL files 75 / migration 87 / Neo4j queries 24 / Next routes 44 / parity workload 7**을 유지했다. 역사적 revision과 frozen migration 자료는 그대로다.

Sidecar는 기존 PyInstaller의 정적 app import 분석 경로로 새 두 모듈을 참조한다. 특별 hidden import·의존성·빌드 명령은 변경하지 않았다. 실제 새 bundle/installer 실행 증거는 해당 필수 CI 결과에서 별도로 확인한다.

후속 확인에서 기존 closeout와 부분 scope 회귀 **65 passed / 0.24초**, 표준 라이브러리만 사용한 `-S` 공통 모듈 cold import, public 승인 **604 / 현재 2,042 nodes**, deferred runtime inventory **files 22**, 최종 import inventory 재생성과 `git diff --check`도 통과했다. Split 지도는 원본 파일 **4개 / 심볼 연결 43개**를 기록한다.

독립 리뷰에서 오류 class 4개의 동일성, SQLite retry/catch, 기존 body-limit assertion 보존을 확인했다. 이전·이후 cursor의 잘못된 입력·padding·scope·예외 원인을 포함한 **35개 차등 비교**도 일치했다. G1과 최신 G0를 합친 고정 merge commit `882338f`에서 설정·공통 오류·Device Home 검사는 **62 passed / 1 기존 skip / 1 warning, 22.40초**였다. G2 source commit `b5dcdd80f529305f5dffa1dbed2e1900119d20b7`에서 새 파일 3개·새 node 20개를 append-only 도입 증거에 추가했다. metadata 추가 전 보존 검사가 해당 신규 증거 누락을 거부한 것은 예상된 보호 동작이며, 추가 후 후보를 다시 검증한다.

### 현재 구조 수치와 역사적 검사 기준의 분리

후속 도메인 검증에서 L4 검사가 현재 module 수를 과거 **680 / 1,837 edges / 2,288 external imports**로 고정해 비교하는 문제를 확인했다. 이 수치는 G2에서 공통 모듈 2개를 추가할 때부터 달라지므로 G2에 보완을 포함한다. 기존 숫자·소유권 **8 / 74** assertion은 정확한 #263 commit의 Git blob에 대해 그대로 유지한다. 현재 보고서는 별도 AST 재수집 결과의 module·edge·external 수와 소유 module/path/import 목록에 정확히 일치해야 하며, 현재 cycle·허용 cycle·legacy exception 0 검사도 유지한다. Frontend·parity·runtime·installer·금지 변경 assertion은 현재 payload를 계속 검증한다. frozen JSON·원본 assertion·검사 예외는 변경하지 않았다.

관련 L4·보존 guard 집중 검사는 **40 passed, 13.17초**였다. 새 회귀는 현재 source totals 3종의 오염을 거부한다. 독립 리뷰의 별도 정상/오염 probe에서 소유권 행 누락·중복·경로/import 변경·cycle·허용 cycle·legacy exception 추가 **7종을 모두 거부**했다. 전체 graph와 소스의 일치는 기존 architecture inventory test와 필수 CI의 `--check`가 계속 검증한다.

고정 후보 `ca9191c`에서 전체 backend suite는 **2,035 passed / 기존 22 skipped / 26 warnings, 465.32초**로 통과했다. 실행 중 이 작업 트리의 소스·테스트·metadata를 수정하지 않았다. 새 live topology 회귀 3개는 source `581427a96163c9760579fd81b461467ab2dc6cb6`의 도입 증거로 보호한다. Hosted PR-head·실제 설치·merge·post-merge는 해당 단계에서 별도로 판정한다.

PR #267의 첫 head `ab8fa23`에서 Gitleaks가 새 cursor 호환 회귀의 공개 synthetic secret 대입 3줄을 탐지했다. source `b5dcdd80`에서 오직 고정 암호화 cursor 회귀를 생성·검증하기 위해 도입한 값이며 runtime 설정/계정 credential이 아니다. 해당 테스트의 정확한 파일·규칙·대입문·값 조합만 허용한다. 다른 파일·다른 값·다른 대입문은 허용하지 않으며 기존 checkpoint/fixture 범위는 그대로 유지한다. 실제 Gitleaks directory/history 및 음성 대조 검증 뒤 수정 head Actions로 판정한다.

실제 Gitleaks 8.30.1에서 추적 파일 archive와 324 commits 이력은 findings 0이었다. 정확 fixture만 통과하고 다른 파일·다른 값·다른 대입문은 각각 탐지되는 4종 대조를 통과했다.

### 기존 브라우저 검사의 시간 경합 보완

G1 merge의 Core CI frontend에서 Chat 입력 중 표시 검사가 첫 실행·자동 재시도 모두 실패했다. 해당 테스트는 실제 backend 없이 route fixture로 응답하며 650ms 뒤 응답을 끝내므로 CI의 assertion 진행보다 중간 UI 상태가 먼저 사라질 수 있었다. 가상 stream을 입력 중 표시·모델 잠금 확인까지 유지하고 finally에서 완료시키는 동기화로 바꿨다. 제품 UI/API 동작과 기존 expect 표현식 331개는 TypeScript AST로 정확히 같음을 확인했다. 로컬 Chromium에서 해당 시나리오를 재시도 없이 3회 연속 통과했다(1.3분). G1 실패 job은 동일 merge에서 한 번 재실행해 post-merge 결과를 별도로 확인하며, 이후 후보에는 시간 경합을 제거한 검사를 포함한다.

### AR-G2 post-merge 보안 이력 범위 Hotfix

G2 merge `8a72078`의 Security run `33961102583`은 현재 추적 source 검사에 통과했으나 Gitleaks history가 329 commits에서 후속 Character PR의 source Git fingerprint를 탐지해 실패했다. 기본 Gitleaks는 함께 fetch된 다른 ref를 포함하며, 해당 fingerprint의 정확한 허용은 후속 PR 설정에만 있었다. 앞선 후보의 설정으로 미래 PR을 판단하므로 같은 SHA의 결과가 fetch된 refs에 따라 달라졌다.

Gitleaks에 `--log-opts="HEAD"`를 명시해 현재 후보의 **전체 조상 이력**을 검사한다. depth 제한·변경분만 검사·exit-code 무시는 추가하지 않는다. 현재 tracked-tree scan, SHA 고정 binary/checksum, redaction, 기존 별도 Angmoo scanner의 모든 ref·무제한 history 검사는 유지한다. 공개 전 저장소 전체 이력 감사도 이 후보별 Gitleaks 결과로 대체하지 않는다.

실제 Gitleaks8.30.1과 새 synthetic Git fixture에서 (1) 기본값은 무관한 다른 branch의 canary를 탐지, (2) clean HEAD의 전체 이력은 통과, (3) 그 branch를 병합한 뒤 현재 파일에서 삭제된 과거 canary도 HEAD 이력에서 탐지됨을 확인했다. G2 후보 전체 조상 scan은 312 commits·19.65MB·findings0, 기존 CI policy도 PASS다. 원래 G2 post-merge 실패는 역사로 남기고 이 후속 Hotfix의 필수 PR·merge/post-merge 확인으로 종료한다.

## AR-G3: 기존 로그 기본값과 배포 자원 연결

별도 `refactor/ar-g3-logging` 작업트리의 기준은 `de83dae`다. AR-G1·G2의 설정/공통 모듈 이전과 섞지 않고, 현재 진입점에 logging 자원을 연결했다. 이 절은 로컬 구현·검증 기록이며 PR·merge·실제 제품 installer 완료 판정은 아니다.

- `backend/logging.ini`에 기존 root `WARNING`, Uvicorn `INFO`, 기존 formatter 및 stderr/stdout stream을 옮겼다. App factory는 INI를 검증하면서 외부 handler·명시적 level·caplog를 보존하며 `fileConfig`·`dictConfig`나 handler 설치를 수행하지 않는다. 기존 파일 로그/rotation 구현은 없었고 새 정책을 추가하지 않았다.
- `app/runtime/logging_config.py`가 소스의 backend root 또는 PyInstaller `sys._MEIPASS`에서 자원을 읽는다. 작업 디렉터리 fallback은 없으며 누락/손상 자원은 시작 전에 실패한다. Uvicorn CLI/reloader에 제공하는 dictionary는 사용 중인 Uvicorn 기본값과 동일하다.
- 기존 ASGI target과 `create_app` 입력을 유지했다. Sidecar는 계속 `log_config=None`·`access_log=False`를 사용하며 설치 작업의 JSON stdout, content-free fatal stderr, endpoint 파일·health·종료 순서를 유지한다. 기존 redaction 함수도 그대로 사용한다.
- `Dockerfile.backend`의 명시적 `COPY`와 `desktop/scripts/build-sidecar.ps1`의 `--add-data`에 INI를 연결했다. OneFile·OneDir 양쪽에 같은 자원을 제공하며 `--noconsole`은 유지한다.
- `app.runtime`의 기존 경계가 새 logging 모듈을 포함하므로 도메인 전체 scope나 전역 허용 범위를 넓히지 않았다. G12와 path map에 실제 소비자·15개 logging node를 연결했고 architecture/ER0/L4/P8-L-R live inventory를 해당 변경에 맞췄다. 원본/후속 고정 체크포인트는 수정하지 않았다.

로컬 검증에서 새 logging 검사와 기존 sidecar security·typed runtime·public runtime·Docker/Tauri 구조 검사를 함께 실행해 **82 passed / 1 warning / 48.05초**를 확인했다. 실제 sidecar main·Uvicorn transport의 endpoint/인증 health/shutdown/정리와 조용한 stream은 작은 fake composition으로 검증했으며, 이 결과를 실제 AI·전체 제품 lifespan 검증으로 확대하지 않는다. Installer helper는 실제 결과 파일·JSON stdout 경로를 사용하고 데이터 작업만 fixture로 대체했다.

이어 기존 embedded-data migration·installer upgrade contract·startup-security 검사를 실행해 **48 passed / 기존 1 skipped / 86.05초**를 확인했다. 기존 세대 upgrade/재실행 및 보안 시작 검증을 유지했으며, 이 Python 검사를 실제 NSIS 설치·실패 복구의 대체 증거로 사용하지 않는다.

별도의 일시적 `uv --with PyInstaller==6.16.0` 환경에서 최소 logging probe를 **OneDir·OneFile, 모두 `--noconsole`로 실제 빌드·실행**했다. 두 결과 모두 `frozen=true`, packaged `logging.ini`, root level `30`, root handlers `0`, `stdio_none=true`, Uvicorn level `INFO`, exit `0`이었다. 이는 frozen resource resolver와 누락된 stdio 검증이며 **전체 Angmoo sidecar·NSIS installer를 빌드했다는 의미가 아니다**. 저장소 lock/dependency는 변경하지 않았다.

구조 경계는 **681 modules / 1,841 internal edges / legacy exact edges 312**, L4 inventory는 **681 backend modules / parity nodes 97**로 통과했다. 보존 검사는 **#258 1,867 / #263 1,907 / 보호 계보 2,022 / 현재 2,037 nodes, items 37 PASS**이며 API/ORM 계약도 동일했다. G1/G2의 순차 통합 뒤 live inventory를 다시 검증하고, 실제 Docker·Host Tauri·제품 sidecar/installer 및 필수 CI 결과를 확인한 뒤 G12를 닫는다.

G0~G2를 합친 고정 merge commit `114eb43`에서 logging·설정·공통 오류·sidecar 보안·runtime composition 집중 검사는 **94 passed / 기존 1 skipped / 1 warning, 45.75초**였다. source commit `6cd99aa41da5f9b411a7efc31d6a1f90b211cf57`의 새 파일 3개·node 15개를 도입 증거에 추가했다. 통합 live inventory는 **683 modules / 1,848 internal edges / parity nodes 97**이며 ER0의 **75 / 87 / 24 / 44 / 7**을 유지했다.

## AR-G4: Alembic의 물리 경로와 실행 연결

`backend/app/alembic`의 90개 파일을 `backend/alembic`으로 옮겼다. 전체는 88개 revision과 `env.py`·`script.py.mako`이며, ER0가 출력하는 87개는 `20260825_0083`을 제외한 기존 역사 부분집합이다. 경로 대응표는 전체 90개를 보존한다. revision 본문·ID·`down_revision`·embedded SQLite v1~v9 및 frozen JSON은 수정하지 않았다.

`alembic.ini`의 script 경로와 import 경로를 설정 파일 위치에 고정하고, Docker COPY·ER0 현재 경로·현재 migration 테스트·P8 A/B의 현재 파일 탐색을 연결했다. P8 D/F/J/P/R의 역사 기록은 옛 경로·digest를 보존하면서 실제 읽는 revision 위치만 새 경로로 해석한다. D의 현재 업무·migration 계약 검사와 나머지 단계의 기존 frozen successor 검사를 유지한다. 경계 policy에서는 이제 `app` 패키지 밖으로 이동한 `app.alembic.env → app.models`의 exact legacy edge 하나만 제거했다.

새 `tests/migrations/test_alembic_layout.py`는 **8 passed / 9.63초**였다. #263에 기록된 전체 88개 revision의 Git blob이 일치하고 실제 Alembic revision 그래프의 단일 head `20260904_0089`를 확인했다. backend 밖의 임시 작업 디렉터리에서 Alembic CLI를 실행했으며, 실제 SQLite 메모리 연결에서 현재 checkout의 모델과 단일 metadata를 등록했다. 해당 연결은 빈 migration callback을 사용하므로 역사 PostgreSQL upgrade 본문을 실행하지 않는다.

G13은 물리 경로 이전까지 적용했으며 최종 완료가 아니다. AR-G5의 `app/models.py`·단일 Base·model 등록 이전 뒤 같은 Alembic 환경 회귀를 다시 실행한다. 현재 단계의 PR-head·merge·Actions 결과와 최종 백엔드 통합은 별도 기록한다.

기존 권한·migration 경로·P8 A/B/D·ER0 검증은 **50 passed / 1 warning / 25.50초**, embedded·Memory migration 회귀는 **25 passed / 29.81초**였다. 전체 합계는 **83 passed**이며 전체 backend suite를 실행한 결과로 확대하지 않는다. 보존 검사는 API/schema/ORM 계약과 test node에서 **#258 1,867 / #263 1,907 / 보호 계보 2,022 / 현재 2,030 PASS**, 승인 public **604 유지**였다. 새 테스트는 기존 CI backend의 전체 `tests` 실행에 포함된다.

현재 import inventory는 Alembic을 `app` 밖으로 옮겨 **591 modules / 1,827 internal edges / 311 exact legacy edges**다. 이 수치 감소는 업무 삭제가 아니며, 전체 90개 파일은 이동 전 원본 SHA-256도 일치한다. ER0는 기존 **75 PostgreSQL source / 87 역사 migration / 24 Neo4j query / 44 Next route / 7 parity workload**를 보존했다. P8 D의 현재 업무 계약과 F/J/P/R 및 Memory batch의 기존 역사 연결 검사가 모두 통과했다.

Gitleaks의 기존 공개 World 고정 marker 허용에 새 `0072` revision 경로 하나를 추가했다. 옛 경로는 history 검사를 위해 유지했고 marker 값·검사 rule 범위는 넓히지 않았다. 실제 Gitleaks 8.30.1의 새 Alembic 디렉터리 `--redact` 검사는 **0 findings**였다. 작업 디렉터리 전체 scan의 66건은 G4 base에 남아 있는 G0 체크포인트 hash 오탐 65건과 생성된 테스트 pyc fixture 1건이었다. 이 결과를 전체 보안 검사 PASS로 표시하지 않으며, G0 수정 통합 후 추적 source·PR history 검사에서 다시 확인한다.

G0~G3를 합친 고정 merge commit `381ef66`에서 migration layout·logging·설정·인증·World Package UoW·P8-A 검사는 **75 passed / 기존 1 skipped, 40.11초**였다. source commit `960fd4685179c2c48958f18eaa5a9a93d855064c`의 새 회귀 파일 1개·node 8개를 도입 증거에 추가했다. 통합 경계는 **594 modules / 1,838 internal edges / legacy exact edges 311**로 통과했다. `env.py`는 G1의 실제 `app.config`를 소비하며 Docker는 logging 자원과 루트 Alembic 양쪽을 포함한다.

### G4의 잠금 파일 기반 migration 검증 환경

PR #270의 clean CI에서 역사 revision `20260604_0037`이 import하는 `pgvector.sqlalchemy.Vector`가 없어 실제 Alembic 그래프 검사 두 개가 실패했다. 로컬 공용 venv에는 해당 패키지가 이미 있어 선행 집중 검증만으로 누락을 발견하지 못했다. 기존 revision 본문·그래프·검사는 그대로 두고, 역사 migration 도구와 검증에 필요한 `pgvector==0.5.0`을 개발 의존성 및 lock에 명시했다. 새 G4 전용 venv에서 `uv sync --locked --group dev` 후 migration 회귀 **8 passed, 29.73초**였다. 기존 runtime dependencies의 버전과 Local SQLite migration 경로는 변하지 않는다. 이후 PR의 전체 CI는 동일 lock으로 검증한다.

## AR-B2 첫 PR: Identity 역할 이전

Identity 소유 코드를 `router/`, `schemas.py`, `models.py`, `dependencies.py`, `contracts.py`, `exceptions.py`, `policies.py`, `service/`로 옮겼다. 기존 인증·프로필·JWT/session, Local owner bootstrap/claim, BYOK credential 해석·이전, Google 검증 예약, 로그인 실패 제한, Turnstile와 demo 잠금을 유지한다. 도메인 소유 테스트 15개 파일의 기존 133 nodes도 `tests/identity/`로 옮겼으며 기존 assertion·parameter·fixture를 유지했다.

`services/auth.py`의 다른 업무 삭제 코드는 `runtime/account_deletion.py`로 분리했다. Identity service가 계정 삭제 요청을 승인하고, 두 앱 factory가 주입한 runtime workflow에 같은 Session과 User 객체를 전달한다. Runtime은 삭제 실행 순서, 한 번의 commit, 실패 rollback·비공개 media 복구, 성공 후 purge를 소유한다. 실제 SQLite·User·Character를 쓰는 통합 테스트가 같은 Session과 단일 commit을 검증하고, 두 factory의 callback 연결도 각각 검증한다. 이후 G06 앱 생성 통합은 이 연결을 보존한다.

기존 `SqlAlchemyIdentityRepository`에는 실제 업무 규칙과 commit이 함께 있었다. 이를 `LocalIdentityService`로 옮기고 다섯 개의 단순 forwarding wrapper 및 소비자가 없던 repository Protocol을 제거했다. `clock`과 명시적인 `now`는 계속 주입할 수 있다. 잘못된 claim 시도 횟수 저장, race 처리, session 발급 제한의 실패 commit·rollback은 유지했다. Bootstrap 후보 표시는 같은 Session으로 소유자별 Character·World membership·credential 수를 읽는 한정된 조회를 유지하며 다른 도메인의 테이블을 수정하지 않는다.

Browser cookie·CSRF·Origin과 proxy source 해석은 identity의 HTTP 지원 코드에 모았다. 다른 router의 HTTP dependency 연결은 `app.api.identity_dependencies`가 같은 callable 객체를 제공한다. Local Bot dependency는 기존 `api/v1/deps.py`에 남겼다. Google SDK 호출과 bounded HTTP 응답 읽기는 `integrations/`에 있으며, startup 보안 검증 조립은 `runtime/startup_security.py`로 옮겼다.

### 경계와 후속 제거

Identity의 실제 역할 20개 module에 부분 scope를 적용했다. `identity.public`은 아직 다른 업무의 정확한 ORM/type 소비자 22곳이 사용하는 같은 객체의 호환 export여서 전체 도메인 완료로 선언하지 않는다. 새 identity 코드는 이 public이나 이전 services를 가져오지 않는다. 남은 소비자와 제거 단계는 경로 지도에 기록했고, 업무별 후속 PR 및 AR-B8-A에서 닫는다. 기존 model/schema aggregate의 같은 객체 호환은 AR-G5에서 정리한다.

경계 정책은 필요한 14개 정확 bridge를 기록한다. Account deletion이 이전 auth에서 사용하던 다섯 legacy edge는 실행 조립 소유자에게 그대로 이전했으며 넓은 예외를 추가하지 않았다. 기존 legacy exact edge는 312개에서 289개가 됐다. 현재 inventory는 backend **679 modules / 1,860 internal edges**다. 이동 지도에는 파일 이전 42개, test node 이전 133개, 분리 원본 10개와 정의 symbol 198개의 실제 목적지·소비자·검증 경로가 있다.

### 로컬 검증과 남은 Gate

- Identity 및 계정 삭제·Memory batch·World Creator 경로: **171 passed / 15 warnings / 23.55초**. 앞선 혼합 범위 실행은 Identity·privacy 삭제·SQLite·runtime·API·Device Home을 포함해 **210 passed / 16 warnings / 60.45초**였다.
- 보존 검사·Identity architecture·login throttle·OSS 경계 회귀: **55 passed / 15.60초**. 이동한 `__init__.py`의 정확 package import 문자열만 정규화했고, 미매핑 하위 모듈·경로·유사 이름을 허용하지 않는 검사 두 개를 추가했다.
- Public node 기준: **approved 604 / current 2,037 / new 1,463 PASS**. 승인 node 목록은 바꾸지 않았다.
- 기능 보존 검사: **#258 1,867 / #263 1,907 / 보존 계보 2,030 / 현재 2,037 nodes**. 기존 assertion·분리 symbol·API/OpenAPI·ORM 계약의 누락은 없다. 독립 준비 branch의 출발점에 포함된 G0 Gitleaks 회귀 두 개만 introduction metadata가 없다는 오류를 남겼다. 최신 G0 metadata를 합류한 뒤 같은 검사를 통과해야 하며 이 결과를 전체 PASS로 기록하지 않는다.
- Live inventory·부분 scope·L0 계약 검사는 **78 passed / 1 failed / 8.93초**였다. 실패한 `test_l4_pr_a_architecture_and_parity_oracles_are_exact`는 live 결과의 module/edge/import 수를 이전 680/1,837/2,288과 비교한다. 현재 679/1,860/2,281의 실제 결과와 frozen 기준을 구분하는 후속 검토가 필요하며, 기존 숫자 assertion은 바꾸지 않았다.
- 변경·신규 파일 120개에 대해 기존 exact allowlist를 적용한 secret scanner는 **findings 0**이었다. 실제 credential 값이나 새 예외는 추가하지 않았다.

Architecture/L4/ER0/Memory batch의 live inventory를 현재 코드로 갱신했다. 고정 #258 baseline·#263 checkpoint·승인 test node·frozen migration과 선행 Today SNS inventory는 수정하지 않았다. Source commit 후 새 파일·신규 5개 test node의 도입 증거를 별도 capture하며 Git 추적 파일을 사용하는 inventory도 다시 갱신한다. 최신 G0와 G1~G4 통합, 최종 backend 검증, PR-head Actions, merge와 post-merge는 후속 결과를 확인할 때 기록한다. 이 Identity 검증은 전체 AR-B2 또는 설치 앱·실제 AI 검증 완료를 뜻하지 않는다.


## AR-B3 Package foundation — 계약·ORM·registry 첫 source slice

G0~G4와 Identity source가 합류한 `abbd08c`의 별도 작업트리에서 시작했다. Python v1/HTTP schema, 불변 request/result, archive/license/collision 정책과 canonical digest를 새 역할로 옮겼다. JSON `schemas/v1`와 synthetic fixtures·golden bytes, 네 ORM의 table/column/FK/constraint는 변경하지 않았다. Registry의 동일 seed version 재사용·전달 충돌 판단은 service가, 동일 Session SQL·flush는 repository가 소유한다. 두 구현 모두 commit하지 않으며 원래 caller의 commit/rollback 경계를 유지한다.

v1 계약과 UoW/registry 테스트 두 파일을 `tests/world_packages`로 옮기고 fixture·Alembic 상대 경로와 실제 CI suite 경로를 함께 전환했다. 원래 assertion/parametrize/node는 보존했다. Pure-source 검사에는 실제 새 역할 파일을 추가해 빈 옛 폴더를 검사하는 통과를 막았고, public의 역사적 pure-contract assertion은 이동표의 정확한 module 대응만 정규화한다. 임의 prefix 치환은 사용하지 않는다.

- Package 8 suites: **89 passed / 1 warning / 46.50초**. JSON schema golden, deterministic ZIP, managed-media stripping, seed/rollback/concurrent replay, browser/native delivery/cancel, preview/archive limits, import/media recovery와 UI·closeout 계약 포함.
- Architecture boundary: **599 modules / 1,864 edges / legacy exact edges 288, PASS**. 새 계약·정책·ORM·registry **23개 exact module**만 opt-in하며 같은 업무의 옛 소비자 **94개 exact bridge**는 뒤이은 AR-B3 export/staging/import slice에서 제거한다. aggregate ORM 등록은 G5에서 닫는다.
- API/ORM와 원본 assertion/split/node 보존: 변경·누락 오류 없음. PR258 1,867 / PR263 1,907 / 보호 lineage 2,080 / 현재 2,085. 종료 코드 1의 원인은 선행 Identity의 introduction metadata 미합류 9 source·5 test node뿐이며 root의 선형 source→append capture 단계에서 처리한다. frozen checkpoint·기준선·승인 node는 변경하지 않았다.

이 기록은 첫 source slice의 로컬 검증이며 Package 전체·shared media·순차 PR/Hosted Actions·merge 검증 완료를 뜻하지 않는다. 다음은 export/staging, 이어 import UoW/복구/runtime 조립 전환이다.


## AR-B3 Package processing — export·staging·ZIP·media 정제 두 번째 source slice

첫 source `d80e2ed` 위에서 export/staging 실제 서비스, deterministic ZIP writer, bounded ZIP reader, exclusion scanner, staging/export artifact/export-media 저장소를 각 역할 package로 옮겼다. ZIP 제한·이미지 lossless 정제·token 바인딩·expiry·cancel·retry·preview 입력/출력의 구현 조건은 유지했다. 실제 fake/UoW 소비자가 있는 Protocol 10개는 `contracts/interfaces.py`에 모았고, export asset 클래스/Protocol의 호출자 없는 NotImplementedError 메서드 세 개만 제거했다. 실제 import media 파일 보상은 다음 slice 대상이며 삭제하지 않았다.

SQL source snapshot의 portable-key/profile 변환과 preview probe의 trust/duplicate/tamper/collision 판단은 새 service로 분리했다. SQL 조회 class를 먼저 runtime으로 옮기면 옛 router/import committer에서 domain→runtime 역방향이 발생하므로, 이 물리 이전은 마지막 조립 slice와 함께 수행한다. 현재 partial 범위는 36개 실제 역할 module이며 남은 exact bridge는 94→55개로 줄었다. 새 경계 예외는 확대하지 않았다.

- Package 8 suites: **89 passed / 1 warning / 39.41초**. 고정 v1 JSON/ZIP, archive 악성 입력, 이미지 정제, same-session 원자성·replay, 전달/ack/cancel 및 import 복구의 기존 assertion을 유지했다.
- Architecture boundary: **594 modules / 1,850 edges / legacy exact edges 288, PASS**.
- 소유 테스트: export·preview 두 파일을 `tests/world_packages`로 추가 이전하고 fixture와 CI source literal을 함께 전환했다. 기존 test node·parameter·assertion은 보존한다.
- 남은 범위: router/dependencies, import 승인·동일 Session commit/복구 및 startup read projection 조립. source 이후 parent가 선형 introduction capture와 통합/CI/merge 증거를 기록한다.


## AR-B3 Package composition — HTTP·delivery·same-session import 최종 source slice

`d80e2ed`의 계약/registry와 `3205878`의 export/staging/archive 처리에 이어 Package 역할 전환을 연결했다. `router.py`는 HTTP 입력·권한·오류/응답을, `dependencies.py`는 기존 요청 Session과 app state의 저장소·runtime factory를, `service/import_approval.py`는 digest에 바인딩된 승인과 preview 복원을 맡는다. `service/delivery.py`로 export preview/준비/native acknowledgment의 commit·rollback·artifact 정리 책임을 옮겼다. Browser stream은 원래처럼 정상 소진 후에만 전달을 기록하고, native stream은 저장 완료 acknowledgment를 기다린다.

여러 도메인의 읽기 projection, World/Character/참여 관계 생성과 import commit/복구는 `app/runtime/world_packages`로 이동했다. 두 app factory가 constructor callback을 연결하며 Package 도메인이 runtime을 import하지 않는다. 기존 Session/sessionmaker, 행 잠금, bounded replay, commit 결과 불명 관찰, media journal 복구 및 importer의 기본 비활성 상태는 유지했다. `storage/import_media.py`가 파일 promotion·compensation을 소유한다. 원래 pure `public.py` export 집합은 `contracts/__init__.py`로 옮겼고 실제 소비자를 전환했다.

- 고정 제품 source의 Package 93 nodes와 L3/L4·architecture·security-route·보존 guard 집중 검사는 **190 passed / 1 warning / 41.26초**였다. 원래 Package 89 nodes를 보존하고 동일 Session/factory 연결·복구 1회·준비 commit 실패 보상·native ack 실패 시 retry artifact 보존 4 nodes를 추가했다.
- 현재 scope는 `world_packages` 전체다. Package 내부 `api/application/domain/infrastructure/ports/public.py` 파일과 같은 도메인 임시 bridge는 남지 않는다. 네 ORM을 재등록하는 기존 `app.models` aggregate의 incoming edge **1개**만 G5 종료 조건을 갖고 남아 있다.
- 구조 검사는 **594 modules / 1,861 internal edges / legacy exact 288 PASS**, L4는 **parity nodes 97 PASS**다. ER0는 기존 **75 PostgreSQL source / 87 역사 migration / 24 Neo4j query / 44 Next route / 7 parity workload**를 유지했다. v1 JSON schema `--check`도 통과했다.
- API/ORM/schema·원래 assertion·split-symbol/consumer·test node 보존 오류는 **0**이다. PR258 **1,867**, PR263 **1,907**, 현재 보호 계보 **2,080**, 수집 **2,121**이다. guard의 종료 코드 1은 선행 Identity/Package/guard source의 append-only introduction metadata가 이 독립 branch에 아직 합류하지 않은 것만 남으며, parent의 source commit 후 선형 capture로 처리한다. 고정 checkpoint·baseline·승인 node·v1/golden·역사 migration은 변경하지 않았다.
- Route inventory는 Package 9개와 선행 Identity local/auth의 13개 실제 module 경로만 갱신했다. operation·endpoint 이름·접근 분류·권한 assertion은 유지했고 현재 API의 전체 보안 inventory 검사를 통과했다. Windows/Linux CI의 실제 소유 테스트 경로, fixture 상대 경로와 현재 ER0/L4/Memory batch inventory를 함께 연결했다.

보존 guard에서는 고정된 테스트 source의 pathlib anchor·단일 literal binding과 파일 이동표가 정확히 연결된 경우만 chained path를 정규화한다. 임의 root/call/동적 경로·import/함수/클래스/with/except의 재바인딩은 거부한다. Windows 경로는 문자열 전체가 정확히 일치하는 경우만 인정하고 `__init__.py`는 정상 package import 표기를 사용한다. 독립 source `dc3da4b`·`651bded`·`f61cc48`·`1fb943d`에 이를 나눴으며 기존/음성 검사 **67 passed**를 확인했다. 전체 순서 있는 literal tuple에 대한 compiled regex cache만 추가했고, 대표 실제 assertion **122개 출력 동일**, **1.869초→0.057초**를 확인했다. 기존 느린 guard 실행은 중단해 PASS로 사용하지 않았고 최종 수정 이후 전체 검사를 다시 실행했다.

이 결과는 Package의 독립 source 준비와 로컬 회귀 증거다. 선행 B2의 Worlds/Characters/WorldCharacter source가 합류하면 runtime의 해당 지원 import를 canonical 경로로 연결한다. 전체 통합 backend·Docker/Host Tauri/sidecar/NSIS 설치·Hosted Actions·merge는 parent의 순차 검증 대상이며 이 결과로 완료했다고 표시하지 않는다. Shared media 전체는 다음 별도 B3 범위다.

## AR-B4-A1 — routines ORM·입출력·순수 상태·시간 계약

Package 고정 source `a61a0ae`에서 별도 준비한 첫 routines 소스 단위다. 기존 7 DTO, 9 ORM class, 활동 상태 규칙, clock 계약과 구현을 역할 위치로 옮겼다. lifecycle의 안정적인 오류·결과 record·UTC/due 결정은 각각 exceptions/contracts/service로 실제 분할했으며 원래 class/function body를 보존했다. 일일 계획과 전역 activity runtime의 서로 다른 회복 동작은 아직 통합하지 않았다.

- 기존 daily activity 테스트 18 node를 `tests/routines/test_daily_activity_runtime.py`로 옮겼다. proposal 테스트의 공유 helper import를 package 경로로 명시해 단독 collection에서도 찾을 수 있게 했다. test 이름·parametrize·assertion을 바꾸지 않았다.
- daily/proposal/routine post/ER1 집중 검사: **50 passed, 1 skipped / 14.21초**. skip은 원래 PostgreSQL 환경 조건의 single-flight 검사다. PostgreSQL 실행을 대신 통과했다고 적지 않는다.
- 9 ORM class AST body가 기존 source와 모두 동일하다. 최초 개발 중 JSON import 편집 오류로 collection이 실패한 것은 즉시 고쳤고 위 결과는 수정된 tree에서 처음부터 다시 실행한 값이다.
- 현재 경계 검사 **600 modules / 1,867 edges / legacy exact 288 PASS**. L4 parity 97, ER0 75 PostgreSQL 파일/87 migration/24 Neo4j/44 Next route/7 parity workload 유지.
- 실제 역할 12개 module만 부분 scope에 올렸고, 같은 구현을 쓰는 기존 plan/lifecycle·전역 소비자 23 edge에 A2/A3·B/C·G5별 제거 조건을 기록했다. 완료 domain scope나 광역 예외를 추가하지 않았다.

이 기록은 foundation의 로컬 source 검증이다. 실제 plan/lifecycle transaction 분리, B4-B provider·결과와 B4-C scheduler/resident, 실제 파일 SQLite 재시작, 통합 전체 backend/Hosted/installer/merge는 남은 작업이다. 새 source/node의 introduction metadata는 source commit 뒤 parent의 선형 capture로 추가하며 frozen baseline/checkpoint를 바꾸지 않는다.

추가 직접 소비자 검증은 domain boundary map·L3 closeout·현재 L4 inventory·embedded LocalAppData migration **29 passed / 31.80초**다. API/ORM·기존 assertion·split-symbol·node 보존 검사에서 계약 차이는 없었고, 보호 node 2,080/현재 node 2,121을 확인했다. 전체 guard의 exit 1은 별도 source branch가 아직 parent introduction metadata를 포함하지 않은 항목으로 남았다. 기존 PR258 1,867/PR263 1,907 기준선은 유지했다.

## AR-B4-A2a — 일일 계획 결정과 공동 예약 소유권

A1 source `36298ae`에서 다음 원자 단위로 분리했다. 여섯 pure 함수의 실행 body와 공동 예약 파일의 전체 AST는 원문과 같다. 상수 8개와 오류 5개의 이름/값/계층도 유지했다. 기존 계획 파일에는 scope 조회·readiness·plan transaction을 남겼으며 실제로 이전한 symbol과 남긴 symbol을 split 지도에서 모두 명시했다.

- daily/proposal/routine post 회귀: **42 passed, 1 skipped / 12.15초**. PostgreSQL 환경 조건의 기존 skip이며 새로 제외한 테스트는 없다.
- 경계 검사 **602 modules / 1,874 edges / legacy exact 288 PASS**. routines partial role 15개로 확장하고 이전된 joint 구현의 legacy bridge는 제거했다.
- L4 parity 97, ER0 75 PostgreSQL/87 migration/24 Neo4j/44 Next route/7 workload를 유지했다. frozen 자료는 변경하지 않았다.

다음 A2b는 plan references와 HTTP 의존성·기존 동일 Session commit을 연결한다. WC 담당의 `service.runtime_modes.set_activity_runtime_mode`는 attached 객체의 mode와 version만 변경하고 flush/commit하지 않는 선행 협력 함수다. 그 source가 합류하기 전 중복 mutation이나 임시 fallback을 만들지 않았다. A3 lifecycle·B4-B/C와 통합 runtime/Hosted/installer/merge 검증은 남아 있다.

추가 L4 현재 inventory·domain boundary 회귀 **15 passed / 17.58초**. 전체 보존 guard는 API/ORM·기존 assertion·split·node 차이 없이 PR258 1,867/PR263 1,907/보호 2,080/현재 2,121을 확인했다. exit 1의 남은 항목은 parent가 source 뒤에 추가할 introduction metadata이며 상세 로그는 작업 산출물 `routines-a2a-preservation.log`에 있다.
### Identity와 선행 공통 기반의 통합 검증

G0~G4를 합친 후보에서 보존 검사 **#258 1,867 / #263 1,907 / protected/current 2,085 nodes, items37 PASS**를 확인했다. source `9841bdff3c226a1bc9a07a0246b31dda8e8be87b`의 실제 신규 파일9개·회귀5개는 별도 append-only 증거로 기록했다. 부분 경계는 **593 modules / 1,861 internal edges / 288 exact legacy edges PASS**였다.

새 Identity router를 사용하는 API operation 13개의 보안 inventory module 위치를 실제 경로로 옮겼다. URL·method·endpoint 이름·access 분류·검증은 그대로이며 public 목록은 같은 196 operations다. 선행 L4의 현재/역사 topology 구분을 포함해 Identity·config·logging·migration·보안·P8 inventory 집중 검사는 **233 passed / 기존 1 skipped, 62.09초**였다.

고정 commit `0d97e38dab51624b80d2e7a994f25c480bae9c26`에서 전체 backend suite는 **2,063 passed / 기존 22 skipped / 26 warnings, 495.44초**로 통과했다. 실행 중 source·test·metadata를 수정하지 않았다. 이후 합류한 선행 변경은 G2의 browser fixture 동기화와 그 현재 source fingerprint이며 backend 소스는 같다. 공통 CI/OSS/metadata/container/launcher/installer/Host Tauri 계약 7개, 실제 Gitleaks 8.30.1 추적 archive·328 commits history 검사도 PASS/findings0이었다. PR-head·실제 설치·merge·post-merge는 별도 Gate로 남긴다.

### Identity PR의 현재 소스 inventory 보완

PR #270의 OSS 검사는 deferred runtime inventory에 동일한 4개 경로가 각각 세 번 들어간 불일치를 거부했다. 병합 충돌의 Git index 세 stage가 남은 시점에 생성한 것이 원인이며, 해결·stage된 현재 추적 파일로 다시 수집했다. 30개 행은 서로 다른 실제 경로 22개가 되고 marker·owner·경로 내용은 그대로다. Git index가 해결된 뒤 생성하고 `--check`하는 순서를 후속 통합에도 적용한다. 같은 PR의 전체 backend 실패 2개는 G4 Alembic 그래프가 과거 pgvector import를 실제로 읽으면서 드러난 개발 의존성 누락이며 G4 소유 수정으로 통합한다.

## AR-B2-B1: Character 기반의 역할별 구현

`characters/models.py`는 기존 Character·CharacterState의 동일 ORM class와 Base를 유지한다. `contracts.py`와 `service/seed.py`는 World Package 호출자의 Session에서 add·flush만 수행하는 seed 계약을 보존한다. `service/profile.py`에는 핸들 정규화·충돌 처리와 프로필 조회·생성·갱신의 실제 구현을, `service/state.py`에는 기존 deferred-commit 계약의 상태 저장을 옮겼다. 일반 생성·갱신의 기존 commit/refresh를 seed의 flush-only 경계와 합치지 않았다.

`characters/schemas.py`가 Character 기본 입출력과 생성·프로필 입력 DTO를 소유한다. Public activity projection과 나머지 활동 DTO는 아직 기존 Social/활동 소유 파일에 있다. managed-media 경로 검증은 AR-B3 선행 의존성으로 `media/schemas.py`에 원문 그대로 옮겼으며 외부 URL·scheme·netloc 거절, `/media/` 경로 규칙과 오류 메시지를 보존한다. 기존 `schemas/media_security.py` 소비자는 동일 함수 객체를 제공하는 임시 호환 경로를 통해 유지하고 AR-B3에서 전환한다.

기존 `models`, `schemas`, `cruds/community`는 기록된 잔여 소비자에 대해 동일 객체를 제공한다. 새로운 Character service가 기존 수평 service/CRUD 계층으로 돌아가지는 않는다. 기존 `characters/domain`·`infrastructure`의 실제 구현과 빈 marker는 제거했고 출발 경로와 목적지를 보존 지도에 등록했다. 완료 도메인은 계속 `device_home`만이며 Characters와 media는 옮긴 module/entry/bridge만 정확히 검사한다.

현재 focused 검증은 **38 passed / 1 warning / 23.53초**다. 실제 SQLite에서 모델·schema 객체 동일성, 일반 생성 commit, seed caller rollback, 상태 저장의 deferred commit을 확인했고 기존 로컬 생성·프로모션·World Package import commit·owner-controlled WorldCharacter 및 media 참조 보안 검사를 함께 실행했다. API/ORM 계약·기존 assertion·node 보존에는 변화가 없었다. 이 작업 트리의 보존 명령 전체 exit 1은 선행 AR-G4 source commit의 신규 Alembic 테스트 8개 도입 증거가 아직 root 통합에 포함되지 않은 상태로 인한 것이며 전체 보존 PASS로 표시하지 않는다.

`services/agents.py`의 다업무 조립과 Creator·실행·삭제 경로, 남은 소비자·API·테스트 이전은 계속 진행 중이다. 이 기반의 로컬 검증으로 Characters 전체, AR-B2, PR-head, merge 또는 Actions 완료를 선언하지 않는다.

다음 head `de83dae`에서는 위 inventory 검사가 통과한 뒤 secret scanner가 체크포인트의 기존 synthetic Google API key fixture를 감지했다. #263의 `test_langgraph_resident_engine.py::test_generate_json_records_postprocess_error_on_repaired_success` assertion 및 기존 allowlist 4개와 값이 정확히 일치함을 확인했다. 고정 체크포인트를 수정하지 않고 해당 경로·규칙·값에 한정한 예외 1개와 원본 commit/test/blob·값 hash 증거를 추가했다. 기존 24개 항목은 그대로 유지했다. 관련 검사 **21 passed**, metadata **exact_tuples=25 PASS**, 현재 트리와 전체 Git 이력 검사 **fatal=0**이었다. 다른 경로·규칙·값으로 예외가 확대되지 않는 회귀 검사도 포함한다.


G0~G3를 합친 고정 merge commit `381ef66`에서 migration layout·logging·설정·인증·World Package UoW·P8-A 검사는 **75 passed / 기존 1 skipped, 40.11초**였다. source commit `960fd4685179c2c48958f18eaa5a9a93d855064c`의 새 회귀 파일 1개·node 8개를 도입 증거에 추가했다. 통합 경계는 **594 modules / 1,838 internal edges / legacy exact edges 311**로 통과했다. `env.py`는 G1의 실제 `app.config`를 소비하며 Docker는 logging 자원과 루트 Alembic 양쪽을 포함한다.

## AR-B2-B2: Creator 정책과 다업무 조립의 분리

Character 소유 `AgentCreationDraft`, `ProfileImageCandidate`, `ProfileImageQuotaReservation`을 `characters/models.py`에 옮기고 기존 집계 경로는 같은 class를 제공한다. Creator·프로모션 입출력도 `characters/schemas.py`로 옮겼다. 날짜 응답의 기존 `UtcInstantResponseModel`과 UTC 복원 함수는 `core/response_schemas.py`의 동일 구현을 공유한다.

`service/access`는 owner/deleted/suspended/execution-mode 판단, `persona`는 입력 prompt 검사, `promotion`은 동의 시각·철회 시각, `mutations`는 Character 자체 생성·프로필·페르소나·동의 변경을 소유한다. `image_quota`에는 create/profile×avatar/banner bucket, Seoul 날짜와 자정 초기화, PostgreSQL advisory lock, reserved/generated/applied 집계·예약 commit·finalize flush가 있다. `creator`는 draft 응답·persona 결과 파싱·오류·쿨다운의 실제 구현을 소유한다. 모든 변경은 기존 값·오류·write 순서를 유지한다.

기존 `services/agents.py`와 `services/agent_creation_drafts.py`의 나머지 실행 연결은 각각 `runtime/characters/management.py`와 `creator.py`로 이동했다. Character mutation 이후 활동 setting·credential·log·World binding·응답 조립, 파일/provider 작업과 성공/실패 cleanup 순서는 runtime에서 이어간다. 기존 import와 테스트 monkeypatch 대상도 같은 새 module로 바꿨으며 옛 service 경로의 사본이나 forwarding module을 남기지 않았다. exact legacy edge는 기존 importer의 경로만 전환했고 새로운 포괄 예외를 만들지 않았다.

이것은 **중간 상태**다. `/agents`의 혼합 router, AgentDetailRead의 activity 응답 조립, 활성화/readiness/Local Bot의 후속 소유권과 Creator media/provider workflow를 정리해야 한다. B2 Character 전체의 router/service 분리가 끝났다고 표시하지 않는다. 특히 runtime의 남은 업무 판단을 후속 service로 옮길 목록과 B3 media·B4 activity·B8 Bot 담당을 보존 지도에 남긴다.

기존 생성·프로모션·prompt·활동·로컬 생성과 foundation 검사는 **131 passed / 2 warnings / 12.94초**였고, credential privacy·private preview·post image·provider boundary·tendency·캐릭터/계정 삭제·World Package 검사는 **159 passed / 3 warnings / 24.64초**였다. 새 quota/UTC/owner/model/오류·mutation 검사는 **6 passed / 6.59초**다. 실제 activity/credential 테이블이 없는 SQLite에서 Character 자체의 두 생성 commit과 프로필 변경 commit도 검증했다. 기존 활성화 SQLite/PostgreSQL 분기·전역→World lock 순서와 기존 여러 commit을 바꾸지 않았다. 실제 PostgreSQL 환경 검증으로 확대하지 않는다.


### Characters 두 번째 source의 잔여 경계

| 현재 위치·책임 | 현재 구현 상태 | 후속 담당과 완료 조건 |
| --- | --- | --- |
| `characters/service/mutations.py`, profile/state/seed/access/persona/promotion | 실제 Character 모델 변경·판단을 소유. 생성 두 commit과 별도 seed flush-only 유지 | B2-B: 기존 호출자가 canonical 역할 함수를 사용하며 Character API 분리 후 완료 |
| `characters/service/creator.py`, `image_quota.py` | Creator 응답·파싱·쿨다운과 생성 이미지 quota 정책·DB 저장을 소유 | B2-B: draft 생성/갱신/완료의 남은 admission과 DB mutation을 이 소유 서비스로 연결 |
| `runtime/characters/creator.py` | draft/provider 검증·media 생성/적용·취소·만료 정리와 여러 commit을 보존한 실행 조립 | B2-B/B3: Creator 자신의 업무 판단은 service로 이동하고 파일·HTTP client는 B3 실제 소유 adapter로 연결; 기존 commit, 실패별 quota 처리, private preview 권한·cleanup 순서 유지 |
| `runtime/characters/management.py`의 profile 계열 | Character mutation 뒤 activity setting·credential·log·detail을 같은 Session으로 연결 | B2-B: 필요한 callback/실행 의존성 연결을 분리하고 자기 Character 판단을 runtime에 다시 추가하지 않음 |
| 같은 management의 activate/deactivate/run-now/first-greeting/tendency 및 기존 activity readiness | 전역·World capacity lock, SQLite 즉시 transaction, 기존 readiness와 retry를 유지 | B2-D/B4: WorldCharacter readiness·routine activity 정책은 각 소유 service로 이전하고 runtime은 다업무 실행만 연결 |
| 같은 management의 Local key/Bot 연결 | 현재 credential·slot·Local Bot 계약 유지 | B8-A: Bot 실제 소유 모델·service로 분리하고 이전 consumer를 종료 |
| 같은 management의 `_scrub_agent_data`와 quarantine/slot cleanup | Character 삭제가 여러 도메인 데이터·파일을 정리하는 기존 UoW와 실패 처리를 유지 | B2-B/B8-A: 자기 Character anonymize와 각 소유 데이터 cleanup을 역할 서비스로 분리하며 최종 다업무 삭제 순서는 runtime에 유지 |
| `app/api/v1/routes/agents.py` | 지원 URL과 순서를 유지하는 Character·Creator·Activity·Bot의 기존 혼합 router | B2-B/B4/B8-A: 업무별 router와 dependencies로 분리. response/schema·오류·권한과 full/public route 계약을 함께 검증 |
| `app/schemas/agents.py`의 `AgentDetailRead` 및 활동·credential/image DTO | Character·Creator DTO는 canonical로 이전, 나머지 조립 DTO는 기존 응답 유지 | B2-B/B4/B8-A: DTO 실제 소유권을 확정해 service/schema 공개 경로로 연결하며 JSON 모양 변경 없음 |
| `app/services/profile_media.py`, provider/image transport | 공유 저장·private 파일·World/Post 소비자가 계속 사용하는 기존 단일 구현 | B3: 별도 media 감사에 따라 자기 업무의 policy와 공유 I/O를 분리; 같은 구현을 중복 복사하지 않음 |

완료 `refactor.domains` 목록은 여전히 `device_home`만이다. Identity·Characters·media는 실제 옮긴 module/entry/exact bridge로 검사한다. 기존 287개 legacy edge에서 같은 importer의 물리 위치를 전환하고 실제 종료한 5개를 제거해 현재 **603 modules / 1,904 edges / 282 exact legacy edges**다.

### 두 번째 source 검증과 한계

추출한 **76개 class/function body·constant**는 #263 원문과 AST 비교에서 차이가 없었다. 독립 리뷰도 Character 생성/프로필/페르소나/동의의 commit→후속 조립 순서, quota 재조회→동일 lock key→예약 commit/finalize flush, provider 실패별 저장과 prompt 정책의 의미가 같음을 확인했다. 변경·신규 source 49개에 기존 exact secret allowlist를 적용한 검사는 findings 0이었다.

첫 전체 실행은 **2,029 passed / 22 skipped / 8 failed / 26 warnings / 451.10초**였다. 실행 중 제품 코드는 바꾸지 않았지만 실패 테스트·지도·문서를 수정한 이력이 있어 최종 고정 tree의 전체 PASS로 사용하지 않는다. 실패 중 demo monkeypatch 1개·함수 내부 옛 import 1개·OSS 검사 경로 3개와 UTC helper의 core inventory 누락 1개를 보완했다. 해당 회귀와 새 Creator 검사 묶음은 **48 passed / 18.65초**였다. 기존 assertion·예외 기대를 유지했고, public Read schema의 secret-field 검사는 domain 역할 schema까지 확대했다.

남은 2개는 이 준비 branch에 합류하지 않은 상위 통합 사항이다. L4의 live module 수를 과거 680과 비교하던 검사는 G2 source `581427a`에서 frozen/live를 구분하도록 보완됐으며 root에서 통합한다. route-security inventory의 Identity `api.local_routes → router.local` 대응도 Identity 통합에서 처리한다. frozen 수치 assertion이나 보안 분류를 이 Character 변경에서 임의로 약화하지 않는다. source introduction metadata는 root의 선형 통합에서 기존 고정 commit별로 캡처한다.


최종 source 준비 상태의 보존 검사는 **#258 1,867 / #263 1,907 / 보호 계보 2,030 / 현재 2,059 nodes**였다. API·OpenAPI·ORM 계약, 기존 assertion·skip 상태, split symbol·대응표의 오류는 0개였고, 선행 고정 source의 아직 합류하지 않은 introduction metadata만 source 17개·test 23개로 보고됐다. 승인 public **604 / current 2,059 / new 1,485 PASS**이며 승인 목록과 고정 checkpoint는 바꾸지 않았다. 최종 경계 검사와 diff whitespace 검사도 통과했다. root의 G1/G2 통합에서는 두 새 runtime 파일의 `core.config`·SQLite error import를 이미 확정된 `app.config`·`app.exceptions` 경로와 맞춘 뒤 검증한다.

### Characters 선행 기반 통합 전체 검증

고정 후보 `6f18f63`에서 전체 backend suite는 **2,077 passed / 기존 22 skipped / 26 warnings, 492.55초**였다. 실행 중 source·test·metadata는 수정하지 않았다. 별도 보존 검사는 G2의 SQLite 공통 오류 소비자 하나가 삭제된 `services/agents.py`를 가리킨다고 거부했다. 동일 오류를 실제로 import·catch하는 `runtime/characters/management.py`로 그 소비자 기록만 전환하고 재검증한다. 선행 Identity CI에서 발견된 deferred inventory 중복과 G4의 역사 migration 개발 의존성은 해당 소유 PR에서 수정한 뒤 통합한다. 전체 테스트 통과를 PR·설치·머지 완료로 표시하지 않는다.

### Character introduction 증거의 Git fingerprint 검사

PR #271 Gitleaks가 source addition의 `characters/service/access.py` Git blob fingerprint 한 줄을 generic API key로 탐지했다. 실제 source commit `d8780945`의 Git object와 정확히 일치함을 확인하고, 해당 evidence 파일·key·40자리 hash·rule의 조합만 허용한다. 원본/추가 보존 자료는 변경하지 않는다. 다른 경로·key·hash는 계속 탐지하는 대조와 현재 추적 source·commit history를 확인한다.

실제 Gitleaks 8.30.1에서 추적 source 18.54MB와 현재 후보의 329 ancestor commits는 findings0이었다. 정확한 조합은 허용하고 다른 파일·key·hash 세 경우는 각각 탐지됐다.

### AR-B2-B3 — Character HTTP와 같은 Session의 업무 연결

Character 목록·생성·단건 조회·프로필·페르소나·홍보 동의 6개 endpoint는 `app.domains.characters.router`와 `dependencies`를 사용한다. `service.management`는 소유자 조회, 목록 선택/정렬, Character mutation과 후속 호출 순서를 소유한다. `CharacterManagementWorkflows`는 앱 생성 시 연결되며, 활동 설정·credential·활동 기록·상세 DTO 조립만 `runtime.characters.management`가 수행한다. 원래의 여러 commit을 하나로 합치지 않으며, 모든 callback은 동일 Session과 부착된 Character/owner를 받는다.

`api/v1/routes/agents.py`는 미전환 API와 6개 canonical APIRoute를 원래 순서에 조립한다. `/drafts/...`가 `/{character_id}`보다 먼저 매칭되는 순서, URL, operationID, HTTP 오류와 인증 dependency 객체를 유지한다. 실제 중복 endpoint 구현은 없다. 목록/일반 조립의 최근 활동 기본 한도는 20개, 단일 상세 조회는 기존 상수에 따라 200개이다.

`AgentDetailRead`/이미지 설정 읽기 DTO는 Character schemas, credential 읽기 DTO는 Identity schemas, 활동·slot 요약 DTO 6개는 Runtime schemas의 정확한 선행 추출이다. 각 이전 aggregate는 같은 class 객체를 내보낸다. Runtime 전체 실행 로직이 전환 완료된 것으로 보지 않는다.

- 현재 검증: Characters/Creator/promotion/demo lock/activity/L4 **144 passed, 3 warnings (27.87s)**. 신규 4개 노드는 `tests/characters/test_character_http_workflows.py`에 있다.
- 실제 HTTP에서 공통 인증/DB override, drafts 우선순위, 동일 APIRoute를 검증했다. 두 앱 factory 등록, 미등록 오류, 같은 Session과 기존 commit 순서, foreign owner 차단, schema identity와 detail 한도를 검증했다.
- 경계 검사: **610 modules / 1943 edges / legacy exact 282**. 공개 route inventory **196 operations**. 원래 6개 entry의 module 필드만 변경했고 public generator를 갱신했다.
- 남은 B2 책임: Creator draft CRUD/검증/완료와 파일·provider callback 분리. 프로필 이미지 저장·후처리 B3, 활동/성향/자율실행 B4, LocalBot와 복합 삭제 조립 B8을 이 Character HTTP slice의 완료로 간주하지 않는다.
- 통합 보존 검사에서 #258 1,867 / #263 1,907 노드, 현재 2,103 노드가 수집됐고 API/OpenAPI/ORM·assertion·suppression 차이는 없었다. 이후 분할 지도의 원래 source 기준 symbol/consumer를 보정해 split evidence 단독 검사 PASS를 확인했다. 아직 병합하지 않은 Identity/Character source 도입 증거에 대한 append-only 오류는 root의 선형 capture 대상이며, 이 상태를 전체 보존 검사 PASS로 기록하지 않는다.

### AR-B2-B4 — Creator 초안 수명주기와 외부 작업 연결

`service/drafts.py`가 초안 create/get/update/enhance/complete, owned lookup, 만료 초안 정리, 초안 candidate DB 정리 8개 실제 함수의 구현을 소유한다. `CreatorWorkflows`의 LLM 호출·credential 해석·파일 삭제/승격·Character 실행 후처리는 runtime에서 연결한다. 초안별 commit/rollback, media-before-DB 삭제 순서, key 검증 후 초안 저장, 소유권 확인 후 provider 호출, 완료 중 기존 여러 commit을 보존한다.

Creator 조회/수정 2개 endpoint가 canonical router에 추가되었다. 기존 생성·보강·완료 HTTP의 gateway/활동 오류 변환과 이미지 관련 API는 mixed API 조립에 남아 runtime의 얇은 compatibility entry를 통해 canonical lifecycle을 호출한다. 실제 초안 업무 구현이 runtime에 중복되지 않는다. 남은 adapter/provider 오류 정리와 프로필 이미지 작업은 B3/B4/B8의 소유권에 따라 종료하며, 이 단계에서 broad 전체 domain 완료를 선언하지 않는다.

- 신규 `tests/characters/test_creator_workflows.py` **4개 node**: key 확인 전 insert 없음·암호화 scope 동일, foreign owner 은닉, 개별 만료 cleanup rollback·media-first·미만료 유지, persona 보강의 owner/provider/commit 순서, 두 factory와 원래 route 객체/순서.
- Characters/Creator/promotion/private preview/prompt/demo lock 집중 검사 **94 passed, 1 warning (12.98s)**. 기존 테스트의 assertion은 수정하지 않았다.
- 이전 runtime 실제 8개 함수의 본문 AST를 callback 이름·model alias·명시적 workflow 인자만 역정규화해 비교한 결과 **차이 0**. 실제 분기·field·오류·commit/flush 순서가 보존됨을 별도로 확인했다.
- 경계 **611 modules / 1957 edges / legacy exact 282**, 공개 route inventory **196 operations**. 이번 변경은 기존 추가 2개 route의 module 필드만 바꾸고 public generator를 실행했다.

### AR-B2-B5/B6 — Creator HTTP 종료와 Character state 잔여 추출

현재 Character/Creator 기본 업무 HTTP **11개**와 Character state HTTP **1개**는 `domains/characters/router.py`에 실제 구현을 둔다. mixed agents/community router는 기존 APIRoute를 원래 자리에 조립한다. 생성·보강·완료 HTTP를 후속 미디어 단계에 넘기지 않고 이번 B2에서 종료했다. 앞의 B3/B4 기록 중 이 세 endpoint가 미전환으로 남았다는 문장은 당시 source 상태이며 현재는 해소되었다.

- 런타임 중립 오류(`ResidentRuntime*`, `AgentRunServiceError`, `AgentSlotUnavailableError`)는 `runtime/contracts.py`, 관리 미디어의 validation 오류 한 종류는 `media/contracts.py`의 정확한 선행 추출이다. 기존 service alias는 같은 class 객체를 유지한다. slot 실행·adapter registry·파일 저장 정책은 옮기지 않았다.
- Character credential 오류 두 종류는 Character exceptions, 기존 credential 오류 문구 판정은 Character Creator service로 이동했다. HTTP 오류 순서·문구와 400/409/422/429/502를 실제 요청으로 검사했다.
- `services/community.py`의 순수 state admission/응답 조립 2개도 `characters/service/state.py`로 옮겼다. 기존 Community 소비자는 얇은 wrapper에서 기존 `CharacterNotFoundError` 클래스로 전달한다. tool-run 인증·관찰 로그·중복 note 억제는 Social/activity의 실제 조립에 남는다. owner state HTTP의 URL·인증·404 은닉·private 필드와 기존 defer-commit 정책은 유지한다.
- 집중 검증 **203 passed / 4 warnings / 16.78s**. 기존 draft/promotion/private preview/prompt/demo/activity, 권한·삭제, Local Bot 응답, public activity 보안을 포함한다. 신규 `test_creator_http_errors.py` 9개와 `test_character_state_http.py` 2개 node이다. 새 state 테스트의 잘못된 `deferred_commits(db)` 호출은 `deferred_commits()`로 바로잡았고 제품 동작을 수정하지 않았다.
- 경계 **613 modules / 1971 edges / legacy exact 282**, 공개 inventory **196 operations**. 이번 source에서 Creator 3개와 state 1개의 정확한 module 필드만 바꾸었다.

#### B2 Character 종료 범위와 후속 책임 감사

| 실제 업무/잔여 경로 | 현재 책임과 종료 단계 |
| --- | --- |
| Character/State/Creator ORM, profile·persona·promotion·seed·state, 기본 Creator 입력/응답/업무 흐름 | B2 Character canonical models/schemas/service에서 구현. 일반 create의 기존 두 commit과 World Package seed의 flush-only 차이 보존 |
| Character/Creator 기본 API 11개, owner state API 1개, dependencies/factory 연결 | B2 구현 완료. old API에는 같은 route 객체 조립만 있고 endpoint 업무 중복 없음 |
| World binding와 WorldCharacter readiness | B2-D WorldCharacter 담당자가 `service.readiness.evaluate`로 실제 조회/정책을 이전한다. Character runtime은 이 서비스의 동일 반환 계약을 받는다. 독립 B2-D를 Character 완료로 대체하지 않음 |
| `runtime/characters/creator.py`의 profile/draft media 업로드·generate/apply/discard/candidate access·provider/translation | B3 미디어·외부 provider 단계. Character-owned candidate/개인 quota 모델을 Media 전체로 통째 이동하지 않고, Character의 media 정책과 외부 파일/통신 조립을 나눌 범위. 기본 draft lifecycle은 이미 canonical 서비스 호출 |
| `runtime/characters/management.py`의 활동 설정·분석·활성화·run-now·greeting·feed cue·slot/lease | B4 활동/루틴·runtime 조립. capacity/world lock·sqlite retry·provider 호출 횟수·취소를 원문대로 유지 |
| `services/community.py`의 tool state auth/log/dedup, public Character profile/search/activity·follow/feed와 cruds의 Social join | B4/B5 실제 활동/Social 소유. Character state 쓰기만 canonical 서비스로 호출. public activity에서 private memory_note를 노출하지 않는 기존 검증 유지 |
| image settings/credential/local-key/Local Bot, `schemas/agents.py`의 해당 DTO와 `cruds/agents.py` | 계획 §9의 B8-A 실제 잔여 설정/Local Bot·quota 소유 정리(이미지 provider 연결은 B3와 협력). 새 Character 기본 업무를 이 옛 파일에 추가하지 않음 |
| Character 삭제/계정 삭제의 다중 ORM·메모리·WorldCharacter·미디어 정리 | B8-A 복합 runtime UoW. `runtime.characters.management`/`runtime.account_deletion`의 같은 Session, 순서, busy·미디어 복구 계약 유지 |
| `characters/public.py`, `app.models/`, `app.schemas/`, `cruds.community`의 이전 함수 export, runtime lifecycle entry | G5/B8-A 직접 소비자 전환 후 제거할 정확한 단방향 bridge. 새 코드에는 canonical service/schema/contracts를 사용. 현재 partial-module scope를 유지하며 다른 업무의 public/aggregate 소비자가 남은 상태를 whole-domain 종료로 허위 승격하지 않음 |

이번 감사에서 찾은 순수 B2 Character state 잔여는 본문처럼 해결했다. 위에 명시한 다른 업무/후속 단계와 별개로 남겨 둔 미분류 B2 Character 기본 구현은 없다. PR-head CI·전체 병합 후 검증과 후속 domain/bridge 종료는 root의 순차 통합 Gate에서 판정한다.
- 마지막 고정 후보 `--contracts --nodes`는 현재 **2,118 nodes**를 수집했고, #258/#263 대비 API/OpenAPI/ORM·기존 assertion/suppression·source split 증거 오류는 없었다. 미합류 Identity/Character source 도입의 append-only 증거 오류만 root 선형 capture 대상으로 남았다. 이 기록을 전체 CI PASS로 확대하지 않는다.

### Creator 완료 후보의 선형 통합 검증

Creator lifecycle source `63034348e71ab4ae0bd0611a2ad04e1036244d42`와 HTTP/state source `81aa413abaf74655c3b3432a52ce10125d9aec53`를 하나의 후속 PR로 묶었다. 각 고정 source의 신규 파일·테스트 도입 증거를 선행 메타데이터 뒤에 추가했다. 고정 통합 후보 `49c4d214240b4c473eab3a6caf540f876625787d`에서 전체 backend suite는 **2,096 passed / 기존 22 skipped / 27 warnings, 450.38초**, 보존 검사는 **protected/current 2,118 nodes / items 37 PASS**였다. 이 실행 중 source·test·metadata를 수정하지 않았다.

API/OpenAPI/ORM, 기존 assertion·suppression, 분할 source와 테스트 계보 검사가 모두 통과했다. 공통 CI 계약 7개와 architecture/deferred/L4/embedded/P8-R inventory도 통과했다. 실제 Gitleaks 8.30.1은 추적 archive 18.89MB와 후보의 전체 336 ancestor commits 20.83MB에서 findings 0이었다. 이 기록 뒤에는 문서만 추가한다. PR-head CI, 실제 Installer, 순차 병합과 post-merge는 각각 확인하며, 위 B3~B8의 남은 업무를 Character PR의 완료로 표시하지 않는다.

## AR-B2 Worlds: 정의·Creator·배너 역할 이전

`refactor/ar-b2-worlds`는 G0~G4 통합 `bfa6321`에 Identity source `abbd08c`를 fast-forward한 상태에서 진행했다. 아래는 Worlds의 로컬 구현·검증 기록이며 전체 B2, PR·merge·post-merge 또는 설치 앱 완료 판정이 아니다.

- World의 7개 ORM, schema, system-role contract, 업무 오류와 실제 Creator·definition/readiness·generation context·배너 구현을 `models.py`, `schemas.py`, `contracts.py`, `exceptions.py`, `storage.py`, `service/`로 옮겼다. 불필요한 repository 단계를 추가하지 않았다. 원래 Creator의 함수·class 38개 AST 본문은 세 역할 파일로 분리한 뒤에도 모두 일치했다.
- 기존 mixed router의 World endpoint 10개를 `worlds/router.py`로 옮기고 두 앱 조립에서 WC 4개 endpoint 다음에 한 번만 연결한다. WC leave runtime guard와 실제 WC 서비스는 다음 PR 범위로 남겼다. WC leave가 World 오류를 받을 때도 같은 HTTP 변환 함수를 사용한다.
- `seed_world`는 caller Session에서 flush만 하고, 일반 생성·편집·게시·보관의 commit/replay/row version 의미는 그대로다. 배너 commit 실패 시 새 파일만 삭제하고 이전 파일은 성공한 commit 뒤에 제거한다. timezone 변경의 기존 협력 query는 `service/scheduling.py`에서 같은 트랜잭션에 참여하며 active autonomous·enabled activity·idle slot·UTC·dialect row lock 조건을 유지한다. Worker 실행과 runtime 역참조는 없다. 이 활동·scheduler 협력 경계의 후속 소유 전환은 AR-B4다.
- Immutable SQLite v2→v3가 사용하는 옛 World 모델·정의·system role 경로 4개는 새 정의와 같은 객체를 제공하는 정확한 alias로 유지했다. 모델을 중복 정의하지 않으며 migration 본문을 수정하지 않았다. `worlds.public`의 WC/Package/Routines ORM 소비자 및 기존 model/schema aggregate는 후속 소유 단계에서 닫는다. 새 service에는 `World`·`WorldMembership` 같은 ORM class를 export하지 않는다.
- Worlds 12개 실제 새 module에 partial scope를 적용하고 14개 정확 bridge를 기록했다. 분리 원본 3파일의 63개 symbol에 실제 목적지·직접 소비자·검증 node가 있다. 기존 Creator 테스트 2파일·11 nodes는 `tests/worlds/`로 이동했으며 승인 baseline은 그대로다. 두 불필요한 전역 definition/context facade와 빈 Worlds api 초기화 파일은 실제 소비자 전환 뒤 제거했다.

### 검증과 남은 증거

최종 Worlds·timezone·구조 경계·보존 guard·L4 inventory 집중 실행은 **134 passed / 4 기존 deprecation warnings / 33.83초**였다. 새 HTTP 오류 회귀의 첫 실행은 TestClient 기본 `testserver` host 때문에 기존 Local Origin 보호가 403을 반환했다. 제품 보호 규칙을 바꾸지 않고 실제 허용 Local base URL을 fixture에 지정한 뒤 동일 묶음 전체를 통과했다. 새 회귀 7개 node는 frozen import의 동일 객체, 배너 commit 실패 정리, timezone 동일 Session의 성공·실패, seed rollback, 14개 endpoint 조립, WC의 World 오류 HTTP 변환을 직접 검증한다.

별도 Device Home·World Package UoW/import/export·WC setup/leave·embedded migration 소비자 묶음은 **77 passed / 3 기존 warnings / 113.22초**였다. 원자 import rollback, approval과 autonomy의 분리, 명시적 역할·기존 v2→v3 upgrade 계약을 포함하며 전체 backend suite의 결과로 확대하지 않는다.

승인 public node 검사는 **604 유지 / current 2,092 PASS**였다. `--contracts --nodes`는 **#258 1,867 / #263 1,907 / 보호 계보 2,080 / current 2,092**를 수집했고 기존 API·OpenAPI·ORM·assertion·split 검사에서 변경/누락을 보고하지 않았다. 단, 선행 Identity `abbd08c`의 신규 source 9개와 node 5개가 아직 append-only introduction metadata에 없어서 전체 명령은 exit 1이었다. 이 검사 전체를 PASS로 기록하지 않으며, Identity와 Worlds source를 순서대로 capture한 뒤 통합 후보에서 다시 판정한다. Worlds source의 도입 증거도 부모 작업에서 해당 실제 commit을 기준으로 추가한다.

Live architecture는 **598 modules / 1,878 internal edges / 2,021 external imports / exact legacy 287 PASS**다. ER0는 **76 PostgreSQL source / 기존 역사 migration 부분집합 87 / Neo4j query 24 / Next route 44 / parity workload 7**로 통과했다. PostgreSQL source 하나의 증가는 원래 timezone query를 별도 service 파일에 배치한 결과다. L4의 parity 97 nodes, Memory batch live inventory, local-smoke의 이동한 두 테스트 경로도 연결했다. frozen source baseline·checkpoint·승인 node·SQLite/Alembic 본문과 역사 inventory는 재작성하지 않았다. PR-head CI와 최종 G5·G06·백엔드 통합 검증은 별도 절차로 남는다.

### Worlds 선형 통합 검증

Character 완료 source와 모든 선행 introduction 증거 뒤에 Worlds source `38c26102a7d1f576d4eb9686f4cb9fb3585f75f2`의 신규 파일 5개·회귀 7개를 캡처했다. 현재 보안 route inventory는 실제 World router의 module 필드 10개를 반영하며 URL·method·access·endpoint 계약은 그대로다.

Worlds·권한·Package import·WorldCharacter lifecycle/setup·활동 소비자 집중 검사는 **129 passed / 6 warnings, 33.27초**였다. 이 집중 실행 시작과 Git metadata commit 완료가 잠시 겹쳤으므로 해당 실행을 고정 HEAD 전체 증거로 쓰지 않는다. 고정 후보 `6b9e77d`에서 권한/삭제 회귀 **8 passed, 6.19초**, public **196 operations**, 전체 보존 **2,125 protected/current nodes / items 37 PASS**를 다시 확인했다. 후자의 실행 중 source·test·metadata는 수정하지 않았다.

같은 후보에서 공통 CI 계약 7개, architecture **618 modules / 1,988 edges / exact legacy 281**, deferred **22 files**, L4 **97 parity nodes**, ER0 **77/87/24/44/7**, P8-R inventory가 모두 통과했다. 실제 Gitleaks는 추적 archive **18.97MB**와 후보의 전체 **338 ancestor commits / 20.96MB**에서 findings 0이었다. 이후 선행 Creator 결과를 합친 변경은 문서 한 파일뿐이다. PR-head의 전체 backend·실제 Installer와 순차 merge/post-merge 결과는 별도로 확인한다.

## AR-B2 WorldCharacter 기반: 모델·계약·검증·생성기

Worlds source `38c2610`에서 이어서 WC 6개 ORM을 단일 `models.py`로 모으고 HTTP schema, 순수 계약, 업무 오류, provider client, 응답 검증 및 Package seed를 역할별 경로로 옮겼다. provider budget·payload·검증·오류 본문과 seed의 caller Session/flush-only 의미는 유지한다. provider facade는 같은 module 객체를 가리키므로 기존 fake/monkeypatch와 계측 대상도 변하지 않는다. frozen SQLite v2→v3 본문은 변경하지 않고 옛 ORM 경로 두 개가 같은 class를 제공한다.

18개 정확한 새 module에 부분 scope를 적용했다. 현재 실제 owner/setup/profile/lifecycle workflow는 다음 slice로 남으며 이들이 새 기반을 소비하는 bridge 43개를 종료 조건과 함께 기록했다. 5개 원본 분리 파일의 66개 symbol에 목적지·직접 소비자·행위 test node를 연결했다. 기존 contract test 파일은 WC 소유 경로로 이동하며 test assertion은 유지했다.

- setup 계약·생성/승인·Package UoW 집중 회귀: **35 passed / 기존 1 warning / 19.49초**.
- 새 동일 객체 검증과 기존 owner identity·runtime mode repair·embedded migration: **34 passed / 기존 1 warning / 65.61초**. 앞선 묶음과 contract 테스트가 겹치므로 두 수치를 유일 test node 합계로 해석하지 않는다.
- public 승인 node: **604 유지 / 현재 2,094 PASS**.
- 보존 `--contracts --nodes`: 기존 API·ORM·assertion·split·node 누락 없음. 보호 계보 **2,080 / 현재 2,094**. 선행 Identity·Worlds의 아직 capture되지 않은 신규 source 14개·node 12개 때문에 명령 전체는 exit 1이며 전체 PASS로 표시하지 않는다. root의 선형 통합에서 각 실제 source commit의 introduction evidence를 추가한다.
- Live architecture **605 modules / 1,883 internal edges / legacy exact 287 PASS**, ER0 **75 PostgreSQL source / 역사 migration subset 87 / Neo4j 24 / Next 44 / workload 7 PASS**, L4 parity **97 nodes**, Memory batch inventory current. PostgreSQL 파일 감소는 WC ORM 두 파일을 한 파일로 모은 결과이며 table 계약은 그대로다.

이 source slice는 WC workflow·HTTP·readiness의 전체 전환 완료가 아니다. 다음 slice는 기존 트랜잭션·오류 순서·capacity lock·provider retry·budget 및 imported World 경계를 보존하여 실제 업무 구현과 소비자를 이전한다. PR·merge·post-merge와 최종 backend/installer gate는 별도다.

### AR-B2 WC owner identity 실제 서비스

Foundation 이후 Character source `fe022c3`를 merge `7bc58b1`로 합쳤다. 실제 `OwnerControlledIdentityService`가 소유자 조회·생성·수정과 트랜잭션을 소유하며 기존 forwarding application/Protocol을 제거했다. Character의 특수 local seed·프로필 update는 해당 Character 서비스로, 설치 owner 조회는 Identity 서비스로 분리했다. seed의 같은 Session·세 번의 단계별 flush와 일반 create의 commit/IntegrityError rollback/refresh, update commit/refresh 순서는 유지한다. Character update helper 자체에는 새 flush가 없다.

기존 owner identity 6개 node를 `tests/world_characters/test_owner_identity.py`로 이동했다. 새 seed/update 회귀는 실제 Session의 flush/commit 횟수, attached identity, rollback 후 행 제거·이전 값 복구 및 unrelated field 보존을 검증한다. Owner·Package UoW·manual Social 묶음은 **24 passed / 기존 1 warning / 17.97초**였다. 현재 API/ORM 계약은 frozen 기준과 같다. Character 합류로 옛 `app/services/agents.py` direct consumer 한 건이 없어져 G2 split의 현재 소비자를 실제 `runtime/characters/management.py`로 연결했다. Frozen 기준선이나 승인 node는 바꾸지 않았다.

Live architecture는 **618 modules / 1,937 edges / legacy exact 281 PASS**, ER0 **75/87/24/44/7 PASS**, L4 parity **97**, Memory batch current이다. Owner 서비스 3개 exact module만 추가하고 기존 임시 bridge 중 실제로 사라진 연결을 제거했다. WC profile/Studio/entry/setup/runtime repair/readiness와 최종 HTTP 이전은 다음 slice다.

### WorldCharacter 기반·owner 통합 검증

Foundation source `64537c7694819f5840aab9106f969f80c6c82d53`의 신규 파일 7개·회귀 2개, owner source `cb9b18d67daf42fd8c9d93c68108e27a7cbc08e1`의 신규 파일 3개·회귀 2개를 선행 Character/Worlds 뒤에 캡처했다. 고정 후보 `81724a5`에서 WorldCharacter owner/setup, Package import/UoW, runtime-mode repair, 권한/삭제 검사는 **63 passed / 2 warnings, 39.83초**였다. 전체 보존 검사는 **2,129 protected/current nodes / items 37 PASS**이며 API/OpenAPI/ORM·기존 assertion·suppression·source split도 유지했다. 검사 중 source·test·metadata는 수정하지 않았다.

공통 CI 계약 7개, architecture **625 modules / 1,993 edges / exact legacy 281**, deferred 22, L4 parity 97, ER0 **76/87/24/44/7**, P8-R 및 public **196 operations**가 통과했다. 실제 Gitleaks 추적 archive **19.06MB**와 전체 **341 ancestor commits / 21.13MB**도 findings 0이었다. 이후 선행 Worlds PR의 결과를 통합한 차이는 문서 한 파일이다. Profile/Studio/setup workflow·entry/readiness HTTP는 다음 독립 범위이며, PR-head CI·설치·순차 merge/post-merge를 확인하기 전 전체 B2 완료로 표시하지 않는다.

### AR-B2 WC profile·Studio·lifecycle와 동일 SQL 조회 조립

공개 profile/Studio/candidate의 기존 SQL join은 `runtime/world_characters/queries.py`로, 권한 확인·snapshot·typed candidate 이유 및 leave의 row version/state/replay/commit 정책은 WC 서비스로 분리했다. API/runtime에서 조회 collaborator를 주입하며 domain→runtime 또는 외부 ORM deep import를 만들지 않았다. 같은 Session과 attached 객체를 유지하고 selected-World leave의 Character 상태 쓰기도 해당 Character 서비스가 소유한다. 7개 기존 HTTP 경로를 `router/profile.py`로 옮겼으며 operation/schema 계약은 같다. 모든 남은 application forwarder와 repository Protocol을 실제 소비자 전환 후 제거했다. Runtime leave guard의 실제 Protocol은 `contracts/lifecycle.py`에 유지한다.

- WC·owner/manual Social·Memory owner control: **35 passed / 기존 2 warnings / 9.83초**. 새 joined-read 회귀는 4종 read 각각 SQL 1회, 동일 이름 정렬의 tie-break, suspended/pending 필터 차이, outer join의 미연결 null 행, owner scope, 같은 Session/class identity 및 비활성 membership 제외를 검증한다. 첫 fixture는 DB에서 허용하지 않는 membership `inactive` 값을 넣어 실패했으며 기존 제약을 바꾸지 않고 실제 `left` 값으로 수정했다.
- P8-E/R 현재 경로 계약·기존 architecture/partial scope 회귀: **80 passed / 2.16초**. P8-E의 현재 backend path 검사만 새 router로 연결했고 frozen JSON은 바꾸지 않았다.
- Public 승인 **604 유지 / current 2,111 PASS**; 현재 API·OpenAPI·ORM 및 전체 split evidence **PASS**. 이 호출은 immutable Git blob 읽기를 memoize하여 동일 검사 중복 I/O를 줄였으며 검사 규칙/기준선을 바꾸지 않았다. 신규 source introduction capture 및 전체 assertion/node 통합 검사는 root의 선형 증거 절차에서 이어진다.
- Live architecture **617 modules / 1,934 internal edges / exact legacy 281 PASS**, ER0 **75/87/24/44/7 PASS**, L4 parity **97**, Memory batch current. 기존 lifecycle test 3개 node를 WC 소유 경로로 옮기고 local-smoke·ER0·L4 실행 경로도 갱신했다.

이 slice 뒤에도 autonomous setup/entry, runtime mode recovery, readiness, mixed cleanup과 잔여 호환 소비자 종료가 남는다. B2 전체·PR·merge·설치 검증 완료로 확대하지 않는다.


### AR-B2 WC autonomous setup·입장·runtime repair 실제 구현

1,699줄의 기존 setup 구현을 canonical service로 이전하고 동일 오류 계층을 `exceptions.py`로 옮겼다. 전환 전후 서비스 함수 본문 **42개 중 36개 AST가 동일**하며 generate/retry/approve/reject, 두 provider 단계, quota/attempt/실패 기록은 그대로다. 변경한 6개 함수는 Character 조회, World/membership/role 조회·membership seed·contract version 쓰기, Identity credential 조회를 실제 소유 서비스로 호출한다. nullable `db.get`과 scalar 차이, query 실행과 오류 변환 try 경계, 기존 flush/commit 위치를 유지했다. 외부 ORM aggregate는 삭제했다.

runtime mode repair 정책은 WC service, 시작 시 session_factory/SQLite immediate 조립은 runtime으로 분리했다. imported World 제외·source marker·hash/profile/repertoire/daypart 검사 및 실패 사유 순서는 유지한다. cross-owner capacity count SQL은 runtime의 같은 query 경로로 이전했다. 첫 회귀에서 Character runtime의 새 count import 누락을 기존 capacity/활성화 테스트 5개가 잡았으며 연결을 수정한 뒤 같은 전체 묶음을 다시 통과했다.

Setup·runtime repair·Agent capacity/동시 활성화·Package UoW는 **101 passed / 기존 3 warnings / 22.44초**였다. 기존 setup/runtime repair 테스트 두 파일을 `tests/world_characters/`로 옮겼고 assertion을 유지한다. 4개 정확한 module을 scope에 추가하고 실제 사라진 bridge를 제거했다. 현재 architecture **619 modules / 1,946 edges / exact legacy 281 PASS**, ER0 **75/87/24/44/7 PASS**, L4 parity **97**, Memory batch current이다. 잔여 setup/entry HTTP, readiness와 여러 업무 cleanup의 최종 소유 전환은 다음 slice다.

Setup slice의 최종 현재 API·ORM 및 전체 split evidence 검사도 PASS였다. immutable Git blob 읽기 memoization만 사용했고 frozen source/checkpoint 내용은 변경하지 않았다.

## AR-B4 준비 — 선행 Character·World·WorldCharacter 소스 연결

`79c33f6`의 선행 소스를 routines A1/A2a에 연결했다. Character/Creator와 Package 앱 factory 설정을 모두 보존하고, Package의 외부 World·Character·WorldCharacter 소비자 13 import는 해당 실제 소유 model/schema/contract/service로 바꿨다. B2 split 지도에서 옛 Package 테스트를 가리키던 증거는 이미 이전된 같은 test node로 연결했다. 원본 source SHA와 introduction 기록은 그대로 유지했다.

수정된 병합 후보의 Package·routines·WC mode·L4·ER7 회귀는 **163 passed, 1 skipped, 1 warning / 80.86초**, 경계 **635 modules / 2,024 edges / legacy exact 281 PASS**다. L4 parity 97, ER0 76 PostgreSQL 파일/87 migration/24 Neo4j/44 Next route/7 workload를 확인했다. 최초 병합 보조 정규식의 파일 말미 누락은 실패 검증으로 발견하여 Git 양쪽 원문에서 다시 조립했고, 이 163 결과는 수정 후 처음부터 실행했다. 중단한 guard와 최초 실패 후보는 PASS 증거로 사용하지 않는다.

계약/노드 guard는 API·ORM·기존 assertion 차이가 없었으나 merge commit 전에는 합류 branch의 8개 source ancestry가 아직 HEAD의 조상이 아니므로 그 Git 검증이 남았다. 옛 Package test node를 가리키는 B2 split 메타데이터도 이 연결에서 수정했다. merge 소스를 고정한 뒤 provenance와 기존 introduction 미기록 항목을 별도로 검증한다. 이는 B4 계획/활동 전체 완료나 Hosted·installer·merge Gate의 최종 완료를 의미하지 않는다.

## AR-B4-A2b — 계획 서비스·같은 Session의 업무 조회·HTTP

`f541c32`에 이어 일일 계획 생성/조회와 runtime-mode 변경의 실제 판단·응답·저장을 `domains/routines/service/plans.py`로 옮겼다. 과거 선택 이력 SQL은 `repository/plans.py`, 다른 업무의 기존 Character/WC/World/membership/repertoire/credential 조회는 `runtime/routines/plan_references.py`에 있다. `PlanReferences`는 같은 요청 Session과 attached 객체를 유지하며 새 Session·명시적 flush·commit을 만들지 않는다. 기존 SQLAlchemy query의 autoflush와 WorldCharacter FOR UPDATE 조건은 유지한다. WorldCharacter 모드·version 두 대입은 선행 `0c76205`의 WC 소유 함수가 처리하고 마지막 commit은 계획 서비스에 남는다.

계획 HTTP 3개는 `routines/router.py`로 옮겨 원래 mixed router의 prefix·tags·위치에 연결했다. social-memory와 relationship graph의 2개 HTTP는 기존 업무 전환 범위에 남는다. 두 앱 factory는 `runtime/routines/composition.py`를 통해 생성기를 등록하며 HTTP dependencies가 같은 `get_db` Session을 전달한다. 예전 daily-plan usecase·전달 repository·Protocol과 외부 ORM 집계 5파일을 제거했고 실제 plan 함수는 public의 동일 객체 alias로 연결했다. lifecycle public·legacy 소비자는 다음 B4-A3/B4-C 범위다.

- 최종 계획·공동 활동·게시 실행·HTTP security·Local runtime·현재 inventory 묶음: **96 passed / 1 기존 PostgreSQL skip / 1 기존 deprecation warning / 57.84초**. 새 회귀 2 nodes는 실제 SQLite 파일에서 mode/version 변경과 다른 owner 변경이 한 번의 commit으로 함께 저장되며, commit 실패가 전달되고 caller rollback으로 모두 원상 복구되는 것을 확인한다. 이전 assertion과 test 이름은 유지하고 실제 호출에 동일 Session collaborator만 추가했다.
- `_plan_read`와 `_selection_history`의 전체 실행 AST 본문은 원문과 같다. prepare/get/update의 add/add_all/flush/commit/rollback 호출 순서도 각각 기존 8/0/1개와 같다. 준비 단계의 DST·후보 선택·joint reservation 실패 보상·date singleton·추가 public action 없음 검증을 그대로 실행했다.
- 현재 API/OpenAPI/ORM·기존 assertion/suppression·test node 누락 **0**: #258 **1,867**, #263 **1,907**, 보호 계보 **2,129**, 현재 **2,169**. 전체 명령은 선행 B2/B3/B4 source 도입 capture가 아직 합류하지 않아 exit 1이며 전체 PASS로 부르지 않는다. 실제 split symbol·직접 소비자·행위 test 증거는 오류 수정 후 전체 다시 검사해 **PASS**였다.
- 첫 확대 실행은 선행 WC profile 7개 route inventory가 옛 모듈을 가리킨다는 오류를 잡았다. access·operation·assertion은 그대로 두고 실제 `router.profile`로 갱신했다. root의 선행 수정과 같다. split 대응 검사도 선행 파일 연결 helper가 살아 있는 LocalBot `api/v1/deps.py`까지 이동으로 해석한 것을 잡았으며, `79c33f6`의 원래 부분 split을 복원했다. 새 HTTP consumer 이름 2개 오기도 실제 `api/v1/main.py`·`public.py`로 수정했다. guard나 frozen 기준선은 바꾸지 않았다.
- 경계 **639 modules / 2,041 internal edges / legacy exact 281 PASS**; routines의 실제 새 **21개 module**만 부분 scope다. Public route **196**, L4 parity **97**, ER0 **76 PostgreSQL 파일 / 87 migration / 24 Neo4j / 44 Next route / 7 workload**, Memory batch 현재 inventory를 확인했다. 살아 있는 이전 source의 정확 bridge와 제거 단계를 policy에 기록한다.

이 source는 일일 계획 전환의 로컬 검증이며 B4 전체·Hosted CI·설치 앱·PR/merge 종료가 아니다. source 도입 기록은 root의 선형 capture로 이어진다. 이후 claim/lifecycle·provider/result·resident 전환에서도 오류/권한/commit 의미가 다른 기존 함수를 이름만 보고 합치지 않는다.

### AR-B4-A3 선행 hotfix — 만료 소비 기록의 캐릭터 scope

구조 이전 전 실제 복구 경로를 조사하다 기존 guarded `routines.public.recover_expired_claims`가 만료된 `ActivityEventConsumption`을 `row.world_character_id`로 검사하는 오류를 확인했다. 이 ORM의 실제 필드는 `consumer_world_character_id`다. 기존 restart fixture의 최종 복구 호출만 legacy에서 guarded public으로 바꾸고 새 SQLite 파일로 실행하면 `AttributeError`가 재현됐다. 새 autonomous/owner-controlled 회귀 2개도 수정 전 모두 같은 오류로 실패했다.

제품 변경은 해당 참조 **한 줄**이며 기존 `_require_autonomous`와 commit 순서·오류 의미를 유지한다. 만료 consumption과 아직 유효한 beat를 분리한 실제 SQLite 재시작 검증에서, 자율 캐릭터의 consumption은 한 번만 released·version 증가되고 claim 필드가 정리된다. 사용자 조종 캐릭터는 기존 validation 오류로 거부되며 caller rollback 후 원래 claim이 남는다. 두 경우 모두 아직 유효한 beat, Post/AgentRun/SocialEvent 개수를 보존한다. 기존 guarded와 legacy lifecycle을 하나로 합치거나 guarded 경로에 legacy의 약한 admission을 적용하지 않았다.

Hotfix·계획·공동 활동·게시 실행·scheduler/활동 한도 집중 결과는 **121 passed / 1 기존 PostgreSQL skip / 2 기존 SQLite datetime warnings / 29.57초**다. 수정 전 두 실패는 `guarded-recovery-before.log`에 남겼으며, 원본 assertion·frozen checkpoint·API·ORM은 수정하지 않았다. 현재 ER0 source hash만 한 줄 변경에 맞췄다. 이 신규 회귀의 최초 도입 capture는 source 고정 이후 root가 수행한다. 이후 A3 구조 이전은 이 정상 scope 동작을 보존한다.

### AR-B4-A3a — guarded lifecycle의 실제 서비스와 동일 Session 조회

별도 hotfix source `2c0a8a8` 이후, guarded 회복·기간 종료·비활성 World 중단·전체 만료 조정의 실제 구현을 `domains/routines/service/lifecycle.py`로 옮겼다. WorldCharacter/membership 조회와 기존 만료 계획의 autonomous join은 `runtime/routines/lifecycle_references.py`가 caller Session에서 수행한다. 서비스는 `contracts/lifecycle.py`의 실제 조회 계약을 받으며, 자체 ORM의 잠금·상태 전이·flush·commit을 소유한다. 기존 public의 clock 처리는 서비스 입구로 옮겨 `now`·`clock` 동시 거부와 검사 순서를 유지했다.

두 단계 전달만 하던 lifecycle usecase/repository와 빈 이전 layer package를 제거했다. public은 같은 서비스 객체를 제공하며, scheduler는 기존 Session을 새 조회 객체에 명시적으로 전달한다. legacy `services/activity_runtime.py`의 동명 함수는 owner admission과 오류·commit 계약이 달라 이번에 통합하지 않았다. 특히 guarded consumption 회복은 선행 hotfix의 `consumer_world_character_id`를 사용하고 owner-controlled 거부를 유지한다.

- 신규 실제 SQLite 검증 2개는 기존 join이 pending owner 변경을 같은 Session에서 읽고 commit하지 않는 점, 첫 캐릭터의 종료 commit 이후 두 번째 scope 오류가 발생해도 첫 commit이 남는 점을 검증한다. 전체 캐릭터를 새 원자 트랜잭션으로 묶지 않는다.
- 계획·guarded/legacy lifecycle·claim·proposal·게시 runtime·활동 한도·domain map·L4·ER7 집중 검증 **150 passed / 1 기존 PostgreSQL skip / 3 기존 warnings / 75.42초**. 기존 행동 assertion은 유지하고 새 의존성의 전달 및 실제 경로 확인만 연결했다.
- 현재 경계 **633 modules / 2,040 edges / legacy exact 281 PASS**, routines의 실제 **22개 module**만 부분 scope다. L4 parity **97**, ER0 **76 PostgreSQL 파일 / 87 migrations / 24 Neo4j / 44 Next routes / 7 workloads**를 확인했다. frozen checkpoint·원본 test·historical migration은 변경하지 않는다.

A3a는 K05 전체 완료가 아니다. legacy claim/공동 실행, routine_posts provider·결과 처리, resident·lease·worker, 선형 통합 후 backend 전체·Hosted·installer 검증은 후속 범위다. 신규 source/test 도입 증거는 source commit을 고정한 뒤 root가 선형 계보에 append한다.

전체 보존 검사는 PR258 **1,867** / PR263 **1,907** / 보호 계보 **2,129** / 현재 **2,173** node를 대조했다. API·ORM·원본 assertion/exception·suppression·split·기존 node 손실은 없으며, exit 1의 항목은 이 준비 branch에 아직 합류하지 않은 선행 source/test 도입 metadata다. 원본 소스나 frozen 기준을 수정하지 않았고, 상세 결과는 작업 산출물 `routines-a3a-preservation.log`에 보존했다.

### AR-B4-A3b — 실행 claim과 게시 성공 상태의 소유권

A3a source `0945889` 이후 `services/activity_runtime.py`의 실제 beat/consumption claim·release·reject·complete·failure를 `routines/service/execution/claims.py`, 실행기에서 사용하던 복구·종료·중단을 `execution/lifecycle.py`로 나눴다. 상태·오류·재시도 한도·episode→beat 잠금·claim commit·IntegrityError rollback/replay는 유지한다. 기존 실행기의 admission과 guarded 경로의 autonomous 검사는 다르므로 서로 바꾸지 않는다. `execution/__init__.py`는 동일 객체 export만 제공하고, 제품 실행은 실제 역할 모듈을 호출한다. 옛 전역 구현과 compatibility의 해당 export는 제거했다.

외부 Post/WC/membership 조회는 `runtime/routines/activity_references.py`에서 원래 Session으로 실행한다. 기존 nullable 조회와 중단 시 WC FOR UPDATE를 유지하고 새 commit을 만들지 않는다. Post는 이 준비 branch의 실제 `app.models.community.Post`이며, B5-A에서 `social.models.posts.Post`로 전환할 정확 소비자와 종료 조건을 담당자에게 전달했다. 이 기존 read를 옮긴 1 edge만 기한을 명시했고 domain에서 외부 ORM을 직접 읽는 예외는 추가하지 않았다.

공통 open-claim 종료 helper는 두 원문의 executable AST가 같음을 확인했다. UTC/due 함수도 기존 별칭·docstring만 정규화했을 때 AST가 동일하여 실제 단일 구현을 사용한다. trigger/terminal 값은 constants, 업무 간 소비 namespace는 lifecycle contract에 있으며 값은 그대로다.

- 신규 SQLite 파일 기반 2 node는 pending Post를 동일 Session에서 읽는 순서, `complete(commit=False)` 후 observer에게 Post/성공 상태가 보이지 않는 점, caller commit 또는 rollback에 따라 게시물·beat·episode가 함께 확정 또는 복원되는 점을 확인한다.
- 첫 focused 검증 **125 passed / 1 기존 PostgreSQL skip / 2 기존 warnings / 45.89초**. 최초 collection의 미존재 Social public Post import는 이 branch의 실제 모델 경로로 바로잡은 후 처음부터 다시 실행한 결과다.
- 현재 경계 **637 modules / 2,068 edges / legacy exact 280 PASS**, routines partial role **26개**. L4 parity **97**, ER0 **78 PostgreSQL 파일 / 87 migrations / 24 Neo4j / 44 Next routes / 7 workloads**. 파일 수 변화는 실제 SQL 소유 분할 결과이며 역사적 기준을 덮어쓰지 않는다.

공동 활동의 서로 다른 scheduling/runtime, routine_posts provider·context·게시 조립과 resident·lease·worker는 후속 범위다. 이 source의 최종 보존 및 추가 경로 회귀 결과는 아래에 이어 기록한다.

최종 focused 묶음은 **152 passed / 1 기존 PostgreSQL skip / 3 기존 warnings / 81.87초**다. 실제 이전된 15개 함수/class의 AST는 추가 조회 인자와 정확한 기존 read 추출만 되돌려 비교했을 때 원문과 차이가 없다. claim/완료/실패와 실행기 lifecycle의 원래 상태 전이·오류·트랜잭션 순서를 유지한다.

전체 보존 검사도 PR258 **1,867** / PR263 **1,907** / 보호 계보 **2,129** / 현재 **2,175** node를 대조했으며 API·ORM·원본 assertion/exception·suppression·split·기존 node 손실이 없다. exit 1의 나머지는 선형 통합 시 root가 연결할 source/test 도입 metadata다. 상세 로그는 `routines-a3b-preservation.log`이며 이 준비 source를 merge/전체 backend/Hosted/installer 완료로 표시하지 않는다.

### AR-B4-A3c — 기존 공동 예약·대표 게시 claim 계약

실행 claim source `8ef7166` 이후 `services/joint_activity_scheduling.py`를 실제 `routines/service/joint_scheduling.py`로 옮겼다. 네 오류 class는 exceptions, 기존 daypart·active 포함 terminal 상태 값은 이름을 구분한 constants가 소유한다. nullable WorldCharacter/membership 조회는 이미 검증한 동일 Session의 `ActivityReferences`로 전달하고, 나머지 SQL·상태 변경·오류·commit/rollback은 원래 서비스 순서를 유지한다. 별도 전달 facade를 남기지 않고 기존 소비 테스트를 실제 소유 서비스로 연결했다.

이 API는 `accepted_unscheduled` 활동의 exact/window 예약과 representation claim을 처리하며 pending/inactive/active 참여자 및 active membership이라는 기존 조건을 유지한다. 실제 proposal opening의 active-only 입장 조건과 오류 계층이 다르므로 두 서비스를 같은 함수로 합치지 않았다. 현재 제품은 proposal opening 경로를 쓰지만, 이 기존 지원 계약의 행동과 테스트를 임의로 삭제하지 않는다.

- 기존 일일 계획·공동 예약·재시작·proposal·routine 게시 focused 검증 **50 passed / 1 기존 PostgreSQL skip / 39.23초**.
- 조회 인자와 정확한 read extraction을 되돌린 원문 비교에서 scheduling·오류·결과의 **13개 함수/class AST 차이 0**. 양측 예약, 실패 시 부분 변경 금지, claim 충돌·복구의 기존 assertion을 그대로 유지했다.
- 현재 경계 **637 modules / 2,072 edges / legacy exact 279 PASS**, routines의 실제 partial role **27개**. ER0 **78/87/24/44/7**, L4 parity **97**, Memory batch inventory를 갱신했다. 원본 baseline/checkpoint·migration은 변경하지 않았다.

제품 joint opening·publication·completion은 다음 A3d이며, Proposal 실구현의 Relationships 소유 전환은 B5 담당과 협의했다. Social의 Post joint 필드 및 notification은 owner 서비스의 같은 Session 함수로 연결하고 원래 대입·검증·flush·commit 순서를 보존한다.

추가 경계·L4·ER7·OSS 검사에서 **34 passed / 1 failed**를 확인했다. 실패는 선행 WorldCharacter client 이전 뒤 plaintext reveal allowlist가 옛 provider 파일을 가리키던 1개 exact 경로였다. 허용 함수 `generate_community_profile`·`generate_repertoire`와 equality 검사를 그대로 두고 실제 `domains/world_characters/client.py`로 연결한 뒤 해당 회귀 **1 passed / 1.71초**를 확인했다. B4 claim/scheduling에는 credential reveal 이동이나 허용 범위 추가가 없다.

전체 보존 검사는 PR258 **1,867** / PR263 **1,907** / 보호 **2,129** / 현재 **2,175** node를 확인했다. API·ORM·원본 assertion/exception·suppression·split·기존 node 손실이 없으며, exit 1의 남은 항목은 선형 통합에서 root가 연결할 source/test introduction metadata다. `routines-a3c-preservation.log`에 결과를 보존했다.

### AR-B2 WC 통합 중 발견한 Package seed replay 경합 Hotfix

기존 `test_concurrent_same_idempotency_key_commits_one_import`가 간헐적으로 World slug validation 오류를 냈다. Seed UoW의 registry 조회와 World idempotency 조회가 모두 miss한 뒤 `_available_slug`가 후보를 고르고, 그 직후 다른 스레드가 같은 요청의 import를 commit하면 마지막 slug 재조회가 `world_slug_unavailable`을 발생시킨다. 기존 UoW는 IntegrityError/OperationalError만 replay 복구해 이 validation 오류를 놓쳤다.

이 경로는 구조 이전으로 추가된 동작이 아니다. Frozen PR #263 `d7037625a19071eb279ad2ea35c3ace6fe5b5289`의 `worlds/infrastructure/sqlalchemy_world_creator.py`에서 `_available_slug`와 `seed_world`의 전체 함수 AST가 현재 `worlds/service/creator.py`와 동일하며, 수정 전 Package seed UoW 전체 모듈 AST도 해당 checkpoint와 동일하다.

수정은 `WorldDefinitionValidationError` 중 `args == ("world_slug_unavailable",)`인 경우로 제한한다. 이 class의 reason_code는 범용 `world_definition_incomplete`라 reason_code만으로 분류하지 않는다. 원래 Session을 rollback/종료한 뒤 별도 Session으로 같은 local_owner_id/idempotency_key의 registry를 조회한다. 실제 원자 commit으로 보이는 완료 기록이 있을 때만 기존 replay resolver가 package id/version/content digest를 검증해 결과를 돌려준다. 기록이 없으면 원래 validation 오류를 다시 내며 재시도하지 않는다. 다른 validation과 비슷한 문자열도 원래 오류 객체를 그대로 전달한다. 기존 DB 충돌 retry 한도·delay·resolver와 World seed 본문은 유지한다.

결정적 회귀는 실제 file-backed SQLite에서 slug 후보 조회 직후 다른 스레드의 commit을 완료시킨다. 수정 전 **4 failed / 2 passed / 18.49초**로 실패를 재현했다. 수정 후 새 6개 사례와 기존 Package UoW/Import Commit은 **26 passed / 기존 1 warning / 37.76초**였다. 새 사례는 rollback→별도 observer 순서, 한 번의 실행, 동일 replay 결과, digest 충돌, 다른 owner/key의 기록 배제, 다른 validation의 미복구를 검증한다. ASCII 이름을 사용해 fallback UUID 시간 구간과 무관하게 동일 slug 경합이 발생한다.

`local-smoke`에 기존 UoW 전체 파일과 새 결정적 회귀를 명시적으로 연결했다. World API·ORM·historical migration·기존 assertion은 수정하지 않았다. 이 hotfix는 seed UoW의 한 경로이며 `BEGIN IMMEDIATE`를 사용하는 media import commit 흐름의 트랜잭션 설계는 바꾸지 않는다. 후속 Package runtime UoW로 파일이 옮겨질 때도 같은 수정이 유지되어야 한다. Source introduction capture 및 PR/merge 검증은 root의 선형 통합 단계가 담당한다.

최종 고정 구현·CI 목록·현재 inventory에서 새 경합 6개, 기존 UoW/Import Commit/Preview, World 정의·Creator API, CI policy를 함께 실행한 결과는 **60 passed / 기존 2 warnings / 42.29초**다. 현재 경계 검사는 **626 modules / 2,003 internal edges / exact legacy 281 PASS**, L4 parity **97**이다.

### AR-B2 WC entry/setup HTTP·readiness·혼합 삭제 소유권 종료

`router/entry.py`에 입장·역할·퇴장 4개 HTTP를, `router/setup.py`에 설정 6개 HTTP를 이전했다. 기존 setup route는 피드 상태 1개만 계속 소유하고, main/public route 조립은 feed→setup 순서와 WC entry→World Creator의 기존 순서를 보존한다. World 접근 오류의 변환 구현은 `app/api/world_errors.py` 한 곳에 두며 두 도메인 router가 소비한다. Scheduler/AgentRun/Slot/setup busy 판단은 runtime guard로 같은 Session에서 조립한다.

활동 준비 상태는 WC `service/readiness.py`, 공유 응답의 실제 정의는 `schemas/readiness.py`로 이전했다. 기존 schema는 동일 class alias다. Character 후속 HTTP source가 추가한 `runtime.schemas`의 동일 DTO는 root 통합 시 WC 정의의 alias로 맞춘다. World/membership nullable 조회 순서, profile/hash/repertoire/daypart 판단 순서와 읽기 전용 동작을 보존했다. 남은 WC membership helper의 오류는 원래 WorldServiceError 계층을 유지한다.

Character·Account 삭제가 함께 사용하는 여러 업무 SQL은 `runtime/world_characters/cleanup.py`로 이전했다. 해당 함수와 공통 World HTTP mapper는 이전 함수 본문 AST와 정확히 같다. 기존 joint participant ID materialization→관련 행 삭제 순서와 caller commit 계약을 유지했다. 실제 소비자 전환 뒤 옛 World/Setup/Readiness 서비스 파일과 옛 Worlds HTTP 파일을 삭제했다. WC의 frozen SQLite ORM alias와 미전환 외부 public/모델 소비자는 정확한 후속 G5/B4–B8-A 경계로 남긴다.

- World/WC·활동 계획·피드·Today SNS·Agent 한도·Package UoW 및 현재 inventory 묶음: **234 passed / 기존 1 skipped / 기존 6 warnings / 73.34초**.
- 전체 수집이 Package import 테스트의 여러 줄 legacy import 한 건을 발견했다. canonical setup service로 연결한 뒤 해당 Package 회귀 **10 passed / 기존 1 warning / 20.48초**, public 승인 **604 유지 / 현재 2,114 PASS**였다.
- HTTP 설정은 실제 WC 오류 모듈을 직접 사용하며 기존 architecture assertion과 예외 기대를 유지한다. 마지막 설정·membership·경계 회귀 **30 passed / 기존 1 warning / 11.97초**. 이번 변경 test 파일의 모든 이전 assertion/예외 기대를 frozen 및 추가 snapshot에 대조한 검사 **PASS**다.
- 현재 API·OpenAPI·ORM 및 모든 split symbol/직접 소비자/행위 test 증거 **PASS**. 기존 World 14개 route와 Character schema의 전체 split 지도를 최종 실제 소유자에 연결했다. 새 부분 split으로 이전 symbol을 누락하지 않는다.
- 새 readiness 회귀는 동일 DTO identity, World scope 오류가 stale profile보다 먼저 나오는 순서, no flush/commit 및 legacy tendency fallback을 검증한다. B4에 제공한 `set_activity_runtime_mode`의 두 대입 helper는 source `0c76205`이며 실제 Session rollback/no flush/no commit 회귀 **1 passed / 4.11초**다.
- 최종 현재 architecture **624 modules / 1,963 internal edges / exact legacy 272 PASS**. ER0 **75/87/24/44/7**, L4 parity **97**, Memory batch current를 유지한다. Frozen migration/승인 baseline/checkpoint는 변경하지 않았다.

장시간 전체 보존 명령은 위 수집 오류를 발견한 상태에서 중단하고, 수정 후 전체 수집·계약/split·변경 assertion 검사를 개별 완료했다. 모든 선행 source의 introduction capture, 전체 assertion/node 계보 검사와 PR/merge/설치 검증은 root의 순차 통합 단계에서 이어진다. 이 소스의 집중 검증을 전체 AR-B2 또는 §8.2 완료로 확대하지 않는다.


## AR-B5-A Social 모델·계약 기반

- 기준 `e6cfca2e724d6c7f928cc169117d836df3698354`; 실제 소유 원본 13개를 `social/models/`, `contracts/`, `schemas/manual.py`로 이전했습니다. Social ORM 16개, 클래스·함수 69개 전체 AST는 원본과 같습니다. `feed.py`의 JSON/JSONB type는 World ORM의 import 대신 동일 dialect 구성을 로컬 정의하며 table/type 계약은 동일합니다.
- `models/community.py`, `models/world_feed.py`, `social/infrastructure/sqlalchemy_models.py`는 실제 Python 소비자가 canonical 모델로 바뀐 뒤 제거했습니다. frozen SQLite v7→v8/Alembic 0088이 사용하는 subjective-context 경로만 동일 객체 alias로 유지했습니다. revision 본문과 DB schema는 수정하지 않았습니다.
- 수동 owner 요청의 즉시 AI 0회, inbox pending 후보, replay·observation, World별 Today 증거·검증된 자기 설명, 기존 마이그레이션과 registry class identity 회귀: **35 passed, 1 기존 warning / 23.77s**.
- API·schema·ORM fingerprint는 PR #258과 #263 기준 모두 동일합니다. 변경된 기존 테스트 6개 파일의 assertion/raises/warns와 기존 split evidence는 보존됐습니다. 최초 자체 검사 wrapper에서 전체 test_nodes를 남긴 채 일부 assertion만 필터하여 허위 missing evidence가 출력되어, test_nodes와 assertion을 함께 필터한 검사로 다시 확인했습니다. 제품·보존 검사 코드는 변경하지 않았습니다.
- L4 live inventory `backend_modules=634 / parity_nodes=97`, ER0 `postgres_files=77 / migrations=87 / neo4j_queries=24 / next_routes=44` 생성이 통과했습니다. architecture partial Social scope 위반은 없지만 e6 기준의 Character–Runtime–WorldCharacter package cycle이 남아 root WC 통합에서 수정 중입니다. 이 source에서 예외를 추가하지 않았습니다.
- 신규 테스트: `tests/social/test_foundation_contracts.py::test_all_social_models_share_registered_metadata_and_original_tables`, `::test_frozen_subjective_migration_and_public_values_keep_single_definitions`. 기존 테스트 노드를 삭제·완화하지 않았습니다.
- **B5 전체 완료가 아닙니다.** 실제 Social 서비스/SQL/HTTP, Relationship의 원자 갱신, projection/outbox 및 Today 소비 경로 전환은 다음 source 단위에서 계속합니다. source introduction capture·전체 CI·병합은 root 선형 통합에서 진행합니다.

### WC 최종 통합의 응답 소유권 정정

WC 최종 source와 Character HTTP source를 합친 첫 고정 후보의 집중 회귀는 215 passed였지만 package 경계 검사에서 Character→WC→Character 및 Runtime alias가 포함된 순환을 발견했다. 위 최초 WC 응답 위치 기록은 이 통합 전에 해당한다. 최종 배치에서는 Character 상세 API의 `AgentActivityProfileReadinessRead` 정의를 동일 본문 그대로 `characters/schemas.py`로 옮기고 WC readiness 정책이 같은 class를 소비한다. 기존 aggregate도 이 실제 class를 가리킨다. 생산 소비자가 없는 Runtime alias와 WC schema 조각을 제거하고 source map과 실제 소비자를 갱신했다. 경계 예외를 추가하지 않았으며 준비 상태 판단 정책과 HTTP schema는 변경하지 않는다. 이 수정 전 진행 중이던 전체 보존 검사는 중단했으며 PASS로 기록하지 않는다.


## AR-B5-B1 Social SQL·알림 처리·HTTP DTO

- `cruds/community.py` 원본 중 Social 테이블만 다루는 실제 SQL·변환·알림 생성 함수 **61개**를 이전했습니다. 원본 61개 함수 AST와 Community/WorldFeed schema 전체 AST는 그대로입니다. 단순 export를 새 구현으로 만들지 않았으며 SQL 본문은 repository 4개, 알림 수신자/자기 자신 제외 판단과 저장은 `service/notifications.py`, 문자열·정수 cursor 변환은 utils 2개가 실제 소유합니다.
- User/Character/Agent ORM을 함께 사용하는 나머지 조회와 Creator demo/activity 함수는 다음 소유자 분리 범위입니다. 새 SQL 모듈은 Social ORM·schema만 읽으며 외부 도메인 ORM/레거시 service/repository를 import하지 않습니다. 기존 `finish_write`·flush·refresh·락·SQL dialect 분기와 같은 Session을 보존했습니다.
- 기존 AR-B2-B1의 `cruds/community.py` 전체 symbol 지도를 유지하면서 이전한 함수 61개와 정규식 상수 목적지만 갱신했습니다. 별도의 불완전 split을 추가하지 않았습니다. 기존 schema 2개의 실제 Python 소비자를 전환한 뒤 옛 파일을 제거했습니다.
- 게시물 HTTP·abuse·이미지 job/quota·Feed 검색·수동 Social UoW·inbox·World profile·registry 회귀: **90 passed, 1 기존 warning / 20.32s**. 새 테스트 노드 없음.
- architecture 경계 **643 modules / 2037 edges / legacy 263 PASS**, L4 parity97 및 ER0 live generation PASS. root의 WC readiness 순환 수정 `77081dc`는 앞선 merge `3258b69`로 포함했고 순환 예외는 추가하지 않았습니다.
- API/ORM/원본 assertion 및 split 최종 확인과 root source capture는 별도 기록합니다. 게시물 자체의 권한·서비스 흐름, 교차 업무 query/runtime, 관계/관찰/outbox/projection 전체 전환은 아직 진행 중입니다.

- B5-B1 최종 보존 확인: PR258/PR263 API·schema·ORM 모두 동일, 변경 기존 테스트 1개 파일의 assertion/raises/warns PASS, 전체 split evidence PASS. 첫 split 검사에서 root가 이미 발견한 WC readiness 목적지 한 줄만 남아 있어 `4f95df7`과 동일한 metadata 정정을 적용했습니다. split 재검사는 immutable Git read와 순수 AST 해석 함수 결과만 메모이즈한 read-only wrapper로 수행했으며 CI 검사 규칙은 수정하지 않았습니다.

## AR-B3 Package foundation — 계약·ORM·registry 첫 source slice

G0~G4와 Identity source가 합류한 `abbd08c`의 별도 작업트리에서 시작했다. Python v1/HTTP schema, 불변 request/result, archive/license/collision 정책과 canonical digest를 새 역할로 옮겼다. JSON `schemas/v1`와 synthetic fixtures·golden bytes, 네 ORM의 table/column/FK/constraint는 변경하지 않았다. Registry의 동일 seed version 재사용·전달 충돌 판단은 service가, 동일 Session SQL·flush는 repository가 소유한다. 두 구현 모두 commit하지 않으며 원래 caller의 commit/rollback 경계를 유지한다.

v1 계약과 UoW/registry 테스트 두 파일을 `tests/world_packages`로 옮기고 fixture·Alembic 상대 경로와 실제 CI suite 경로를 함께 전환했다. 원래 assertion/parametrize/node는 보존했다. Pure-source 검사에는 실제 새 역할 파일을 추가해 빈 옛 폴더를 검사하는 통과를 막았고, public의 역사적 pure-contract assertion은 이동표의 정확한 module 대응만 정규화한다. 임의 prefix 치환은 사용하지 않는다.

- Package 8 suites: **89 passed / 1 warning / 46.50초**. JSON schema golden, deterministic ZIP, managed-media stripping, seed/rollback/concurrent replay, browser/native delivery/cancel, preview/archive limits, import/media recovery와 UI·closeout 계약 포함.
- Architecture boundary: **599 modules / 1,864 edges / legacy exact edges 288, PASS**. 새 계약·정책·ORM·registry **23개 exact module**만 opt-in하며 같은 업무의 옛 소비자 **94개 exact bridge**는 뒤이은 AR-B3 export/staging/import slice에서 제거한다. aggregate ORM 등록은 G5에서 닫는다.
- API/ORM와 원본 assertion/split/node 보존: 변경·누락 오류 없음. PR258 1,867 / PR263 1,907 / 보호 lineage 2,080 / 현재 2,085. 종료 코드 1의 원인은 선행 Identity의 introduction metadata 미합류 9 source·5 test node뿐이며 root의 선형 source→append capture 단계에서 처리한다. frozen checkpoint·기준선·승인 node는 변경하지 않았다.

이 기록은 첫 source slice의 로컬 검증이며 Package 전체·shared media·순차 PR/Hosted Actions·merge 검증 완료를 뜻하지 않는다. 다음은 export/staging, 이어 import UoW/복구/runtime 조립 전환이다.


## AR-B3 Package processing — export·staging·ZIP·media 정제 두 번째 source slice

첫 source `d80e2ed` 위에서 export/staging 실제 서비스, deterministic ZIP writer, bounded ZIP reader, exclusion scanner, staging/export artifact/export-media 저장소를 각 역할 package로 옮겼다. ZIP 제한·이미지 lossless 정제·token 바인딩·expiry·cancel·retry·preview 입력/출력의 구현 조건은 유지했다. 실제 fake/UoW 소비자가 있는 Protocol 10개는 `contracts/interfaces.py`에 모았고, export asset 클래스/Protocol의 호출자 없는 NotImplementedError 메서드 세 개만 제거했다. 실제 import media 파일 보상은 다음 slice 대상이며 삭제하지 않았다.

SQL source snapshot의 portable-key/profile 변환과 preview probe의 trust/duplicate/tamper/collision 판단은 새 service로 분리했다. SQL 조회 class를 먼저 runtime으로 옮기면 옛 router/import committer에서 domain→runtime 역방향이 발생하므로, 이 물리 이전은 마지막 조립 slice와 함께 수행한다. 현재 partial 범위는 36개 실제 역할 module이며 남은 exact bridge는 94→55개로 줄었다. 새 경계 예외는 확대하지 않았다.

- Package 8 suites: **89 passed / 1 warning / 39.41초**. 고정 v1 JSON/ZIP, archive 악성 입력, 이미지 정제, same-session 원자성·replay, 전달/ack/cancel 및 import 복구의 기존 assertion을 유지했다.
- Architecture boundary: **594 modules / 1,850 edges / legacy exact edges 288, PASS**.
- 소유 테스트: export·preview 두 파일을 `tests/world_packages`로 추가 이전하고 fixture와 CI source literal을 함께 전환했다. 기존 test node·parameter·assertion은 보존한다.
- 남은 범위: router/dependencies, import 승인·동일 Session commit/복구 및 startup read projection 조립. source 이후 parent가 선형 introduction capture와 통합/CI/merge 증거를 기록한다.


## AR-B3 Package composition — HTTP·delivery·same-session import 최종 source slice

`d80e2ed`의 계약/registry와 `3205878`의 export/staging/archive 처리에 이어 Package 역할 전환을 연결했다. `router.py`는 HTTP 입력·권한·오류/응답을, `dependencies.py`는 기존 요청 Session과 app state의 저장소·runtime factory를, `service/import_approval.py`는 digest에 바인딩된 승인과 preview 복원을 맡는다. `service/delivery.py`로 export preview/준비/native acknowledgment의 commit·rollback·artifact 정리 책임을 옮겼다. Browser stream은 원래처럼 정상 소진 후에만 전달을 기록하고, native stream은 저장 완료 acknowledgment를 기다린다.

여러 도메인의 읽기 projection, World/Character/참여 관계 생성과 import commit/복구는 `app/runtime/world_packages`로 이동했다. 두 app factory가 constructor callback을 연결하며 Package 도메인이 runtime을 import하지 않는다. 기존 Session/sessionmaker, 행 잠금, bounded replay, commit 결과 불명 관찰, media journal 복구 및 importer의 기본 비활성 상태는 유지했다. `storage/import_media.py`가 파일 promotion·compensation을 소유한다. 원래 pure `public.py` export 집합은 `contracts/__init__.py`로 옮겼고 실제 소비자를 전환했다.

- 고정 제품 source의 Package 93 nodes와 L3/L4·architecture·security-route·보존 guard 집중 검사는 **190 passed / 1 warning / 41.26초**였다. 원래 Package 89 nodes를 보존하고 동일 Session/factory 연결·복구 1회·준비 commit 실패 보상·native ack 실패 시 retry artifact 보존 4 nodes를 추가했다.
- 현재 scope는 `world_packages` 전체다. Package 내부 `api/application/domain/infrastructure/ports/public.py` 파일과 같은 도메인 임시 bridge는 남지 않는다. 네 ORM을 재등록하는 기존 `app.models` aggregate의 incoming edge **1개**만 G5 종료 조건을 갖고 남아 있다.
- 구조 검사는 **594 modules / 1,861 internal edges / legacy exact 288 PASS**, L4는 **parity nodes 97 PASS**다. ER0는 기존 **75 PostgreSQL source / 87 역사 migration / 24 Neo4j query / 44 Next route / 7 parity workload**를 유지했다. v1 JSON schema `--check`도 통과했다.
- API/ORM/schema·원래 assertion·split-symbol/consumer·test node 보존 오류는 **0**이다. PR258 **1,867**, PR263 **1,907**, 현재 보호 계보 **2,080**, 수집 **2,121**이다. guard의 종료 코드 1은 선행 Identity/Package/guard source의 append-only introduction metadata가 이 독립 branch에 아직 합류하지 않은 것만 남으며, parent의 source commit 후 선형 capture로 처리한다. 고정 checkpoint·baseline·승인 node·v1/golden·역사 migration은 변경하지 않았다.
- Route inventory는 Package 9개와 선행 Identity local/auth의 13개 실제 module 경로만 갱신했다. operation·endpoint 이름·접근 분류·권한 assertion은 유지했고 현재 API의 전체 보안 inventory 검사를 통과했다. Windows/Linux CI의 실제 소유 테스트 경로, fixture 상대 경로와 현재 ER0/L4/Memory batch inventory를 함께 연결했다.

보존 guard에서는 고정된 테스트 source의 pathlib anchor·단일 literal binding과 파일 이동표가 정확히 연결된 경우만 chained path를 정규화한다. 임의 root/call/동적 경로·import/함수/클래스/with/except의 재바인딩은 거부한다. Windows 경로는 문자열 전체가 정확히 일치하는 경우만 인정하고 `__init__.py`는 정상 package import 표기를 사용한다. 독립 source `dc3da4b`·`651bded`·`f61cc48`·`1fb943d`에 이를 나눴으며 기존/음성 검사 **67 passed**를 확인했다. 전체 순서 있는 literal tuple에 대한 compiled regex cache만 추가했고, 대표 실제 assertion **122개 출력 동일**, **1.869초→0.057초**를 확인했다. 기존 느린 guard 실행은 중단해 PASS로 사용하지 않았고 최종 수정 이후 전체 검사를 다시 실행했다.

이 결과는 Package의 독립 source 준비와 로컬 회귀 증거다. 선행 B2의 Worlds/Characters/WorldCharacter source가 합류하면 runtime의 해당 지원 import를 canonical 경로로 연결한다. 전체 통합 backend·Docker/Host Tauri/sidecar/NSIS 설치·Hosted Actions·merge는 parent의 순차 검증 대상이며 이 결과로 완료했다고 표시하지 않는다. Shared media 전체는 다음 별도 B3 범위다.

## AR-B3-M1 — 공유 media 처리와 저장 소유 기반

별도 media 작업트리는 Character source `81aa413abaf74655c3b3432a52ce10125d9aec53`에서 시작했다. `profile_media.py`의 36개 기존 함수/class/상수 본문을 수정 없이 공통 `integrations/media/{images,files}.py`와 Character·Social `service/media_storage.py`에 옮겼다. 실제 Character runtime와 account deletion의 소비자도 새 파일·codec 소유자로 연결했다. 호환 export의 오류와 callable 객체는 같으며 ORM·transaction·provider·HTTP 계약은 이 범위에서 바꾸지 않았다.

- Shared 처리: MIME/base64/기하·frame 검사, WebP 변환, root containment, private 경로 검사, quarantine 복구.
- Character 저장: profile/draft/candidate/seed의 기존 디렉터리와 promotion/delete 순서.
- Social 저장: 이미 승인된 생성 결과의 Post 파일 기록. quota/job/공개 부착은 B5 소유이며 기존 mixed service 소비자의 정확한 bridge 종료 조건을 기록했다.
- 후속 B3: Character 후보 업무·private HTTP·generation transport, Worlds 실제 storage 연결. 직접 사용되지 않는 역사 `save_world_banner`는 그 연결 검증 전까지 기존 export에 남는다.

Frozen 원본과 checkpoint는 수정하지 않았다. 원본 profile_media 전체 symbol split은 기존 AR-B2-B5 기록에서 실제 목적지와 소비자를 갱신했고 Character/Social 저장소만 exact partial scope로 추가했다. PR·병합·설치 및 B3 전체 종료는 별도 기록한다.


M1 집중 검증은 **136 passed / 3 warnings / 14.01s**다. 새 회귀 3개는 Character 원본 upload 한도와 Post encoded 크기 계약의 구별, quarantine 두 번째 파일 이동 실패 시 첫 파일 복원, 기존 export의 동일 함수·오류 객체를 검증한다. 추출한 36개 원본 symbol의 AST 본문 비교 차이는 0개다. Architecture는 619 modules / 1991 edges / 279 exact legacy edges로 통과했다.

`check_refactor_preservation.py --contracts --nodes`는 원본 #258 1867 / #263 1907 / protected lineages 2080 / current 2121을 수집했다. API/ORM·assertion·suppression·node 누락·split 오류는 없고 선행 source 74건의 append-only introduction 기록만 root 선형 통합 대기다. 따라서 전체 CLI 성공이나 신규 source capture 완료로 표시하지 않는다. 이 source의 신규 node 3개는 `tests/media/test_media_storage_boundaries.py`에 있다.


## AR-B3-M2 — 이미지 provider 실제 전송 소유

`services/{image_provider,pollinations_image,replicate_image,provider_http}.py`의 실제 구현을 같은 이름의 `integrations` 파일로 옮겼다. 모든 Python 제품·테스트 import를 전환했으며 옛 파일/새 호환 facade는 남기지 않았다. 모델별 dispatch, required-reference preflight, 안전 필터/relay/fallback, public HTTPS/DNS/redirect/민감 헤더, 응답 byte bound, 오류 redaction, polling/timeout과 요청 횟수는 원래 구현이다. Pollinations logger는 기존 `app.services.pollinations_image` category를 명시적으로 유지한다.

두 Replicate 전용 suite는 `tests/media`로 이동했고 기존 node 이름·assertion을 유지했다. 혼합 Post/provider security suite는 소유 범위를 바꾸지 않았다. 원본 file/node map과 K11/current deferred path를 갱신했으며, 없어져야 할 옛 provider legacy edge 11개를 제거했다. Social quota/job, 서비스 이미지 key 소유, Character 후보 업무는 각각 기존 명시 단계에서 이어진다.


M2 집중 검증은 **135 passed / 2 warnings / 12.49s**이며 전체 **2121 tests collected / 6.43s**, protected mapped node loss 0이다. 네 transport 파일의 기존 함수/class 45개 AST 본문 차이는 0개다. Architecture는 619 modules / 1991 edges / 268 exact legacy edges로 통과했다. 신규 test node는 없으며 기존 Replicate 두 suite의 one-to-one node map을 유지했다. source/메타데이터 도입 capture와 전체 API/ORM 재검증은 root의 선형 통합에서 이어진다.


## AR-B3-M3 — Character 미디어 서비스와 HTTP

기존 Character media 함수 13개(비공개 조회·소유 후보/만료·usage·apply/discard·upload)의 실제 구현은 `characters/service/media.py`로, HTTP 11개는 `characters/router.py`로 옮겼다. Runtime에는 실제 남은 호출자와 테스트용 같은 서명 forwarding만 남겼다. Draft expiry는 기존 Creator lifecycle에 같은 workflow를 전달하고, Profile 시각 정체성/활동/detail 조립은 `CharacterMediaWorkflows`가 같은 Session으로 실행한다.

원래 upload의 commit→log→refresh와 apply의 quota finalize→candidate delete→log→commit→refresh→파일 삭제→detail 차이를 보존했다. 두 factory의 구성, 원래 route 순서/같은 APIRoute·인증 dependency, private no-store/nosniff 및 기존 오류 변환을 유지했다. Root 독립 읽기 리뷰도 이 범위에서 추가 수정 요청 없이 이를 확인했다.

새 회귀 **5 nodes**는 `tests/characters/test_character_media_workflows.py`에 있으며 실제 SQLite transaction과 callback Session, commit 후 파일 정리, private HTTP 헤더와 두 factory 연결을 검증한다. 최초 fixture의 필수 persona_summary/filename 누락을 보완한 최종 혼합 matrix는 **165 passed / 2 warnings / 15.76s**다. 원본 #258·#263 대비 API/ORM contract 차이 0, complete split evidence 오류 0이다. Architecture는 620 modules / 2005 edges / 267 exact legacy edges, public route inventory는 기존 196 operations로 통과했다. 원래 split 목적지 24개(13 service + 11 HTTP)를 갱신했고 frozen 증거는 수정하지 않았다.

이 source는 generate_media/generate_profile_media와 quota 예약/provider 수행을 완료했다고 표시하지 않는다. 두 generation endpoint와 해당 Character 업무는 다음 B3 source에서 이동한다. 활동/settings/multi-domain deletion은 이전에 명시한 B4/B8-A 소유 범위를 유지한다. source introduction capture·통합 CI·PR/merge는 root가 순차 기록한다.


## AR-B3-M4 — Character 이미지 생성·quota·실패 상태

`generate_media`, `generate_profile_media`, `_generate_profile_image_candidate`의 실제 업무와 prompt/seed/size 관련 5개 원래 symbol을 `characters/service/image_generation.py`로 옮겼다. 두 생성 HTTP 함수도 Character router에 놓고 기존 API 조립 위치에 같은 route 객체를 연결했다. Runtime은 기존 model/route 설정, 서비스 key availability/해석과 translation을 `CharacterImageGenerationWorkflows`로 제공한다.

Key 없는 경우 reserve 이전 종료, quota 소진 시 번역/provider 0, 기존 lock/count/reserve commit, 성공 candidate 기록/commit, Pollinations/Replicate/정제 실패별 failed 예약 finalize/commit을 보존한다. Draft 사전 cooldown/설정 저장과 마지막 commit, Profile 생성의 별도 순서를 하나로 합치지 않았다. M2의 실제 provider 객체를 그대로 사용하며 새로운 provider 요청을 추가하지 않았다.

신규 **5 nodes**는 `tests/characters/test_character_image_generation_workflows.py`에 있다. 세 실패 종류의 실제 SQLite failed reservation 저장과 후보 없음, key 없는 경우 quota/provider 0, 두 factory의 원래 callback 동일성을 확인한다. 최종 집중 검증은 **145 passed / 2 warnings / 12.18s**, #258/#263 대비 API/ORM 차이 0이다. Architecture는 621 modules / 2022 edges / 267 exact legacy edges, public route inventory는 196 operations로 통과했다. 기존 complete split의 목적지 10개를 갱신했으며 신규 기준선을 재생성하지 않았다.

Media 후속 정리는 World banner의 공유 codec 연결, 실제 남은 외부 번역·legacy URL-helper, mixed profile_media 호환 소비자 종료다. Social quota/job/publication은 B5, image settings와 multi-domain 삭제는 B8-A의 기존 소유 계획을 유지한다. Source introduction capture·통합 Actions·PR/merge는 root가 순차 수행한다.


## AR-B3-M5 — World 공통 이미지 처리·옛 media 소비자 종료

Worlds 통합 `1213b3063c39e32f2928d0bba9719f32106ab5ac`를 합친 뒤 canonical `worlds/storage.py`를 공통 `integrations/media`에 연결했다. World의 upload decode/encode 오류는 기존 `InvalidWorldBannerMediaError`와 같은 메시지로 변환한다. 업로드 원본 크기·signature·frame·geometry·EXIF·흰색 alpha 처리·1024×384 한도·WebP quality 80/method 6은 같고, World service의 commit 실패 시 새 파일 제거/이전 배너 보존 순서는 수정하지 않았다. Package의 별도 lossless codec은 이 규칙에 합치지 않는다.

역사적 `profile_media.save_world_banner` 본문은 World storage의 `save_legacy_world_banner`가 소유한다. 이전 helper의 `InvalidProfileMediaError` 계약을 보존하는 동일 객체 export이며 생산 호출은 없다. Post 파일 저장과 URL 해석의 실제 소비자도 Social 저장 service와 공통 files로 연결했다. 따라서 `services/profile_media.py`는 함수 본문과 생산 소비자가 없는 옛 테스트용 export만 남으며 B8-A 제거 대상으로 명시한다. Social quota/job/게시 부착 자체는 정확한 B5 잔여다.

신규 8 nodes는 잘못된 World 이미지의 오류/파일 없음, 공유 정제 결과와 thumbnail/alpha, legacy 오류 동일성, root 밖 삭제 방지를 검증한다. 통합 Actions/Installer/새 source 도입 capture는 root의 별도 Gate이며 이 절에서는 그 완료를 주장하지 않는다.

M5 고정 후보의 집중 검증은 **133 passed / 2 warnings / 12.30s**이며 World 배너 교체 commit 실패 복구를 포함한다. #258/#263 API/ORM 차이는 0, architecture는 **626 modules / 2,043 edges / 265 exact legacy edges**였다.


## AR-B3-M6 — Azure 통신·제공자 사용량 분리와 media 잔여 감사

Azure의 실제 통신/응답 크기 제한·monthly usage 파일·Lock을 `integrations/azure_translation.py`로 옮겼다. 기존 6개 함수와 Lock의 내용을 바꾸지 않았고 Character prompt 선택·Hangul 확인·256개 cache는 runtime 조립 callback에 남겼다. 신규 **5 nodes**는 같은 문장 cache/provider 1회, Hangul이 있는 prompt의 변환 조건, quota 초과 시 provider 0, transport/response 실패 시 예약 문자 복구, 비활성 key의 파일/요청 없음, 월 변경과 한도 경계를 검증한다.

M1 뒤 남아 있던 기존 credential privacy 테스트의 monkeypatch 위치 한 곳을 실제 `creator.media_images.validate_profile_media_content`로 고쳤다. 비밀키가 URL에 없고 Authorization에만 들어간다는 원래 assertion은 그대로다. Private preview·계정 삭제·기존 provider 경계와 함께 실행한 집중 검증은 **82 passed / 1 warning / 12.68s**다. Architecture는 **627 modules / 2,047 edges / 265 exact legacy edges**로 통과했다.

### Media 실제 소유권과 후속 단계

| 책임 | 현재 구현 / 후속 종료 |
|---|---|
| 프로필·Draft 입력/권한/정제/후보 apply·discard/만료/비공개 HTTP | Character `router`, `service/media`, `service/image_generation`, `service/image_quota`, `service/media_storage`; 기존 commit·실패·provider 수 보존 |
| World 배너 권한·row version·commit 보상과 파일 위치 | `worlds/service/creator.py`, `worlds/storage.py`; 공통 codec 예외를 기존 World 오류로 번역 |
| 공통 MIME/EXIF/WebP/이미지 한계·containment/private paths/quarantine | `integrations/media/{images,files}.py`; 어떤 owner/공개 정책도 결정하지 않음 |
| 실제 이미지 provider·validated HTTP / Azure | `integrations/{image_provider,pollinations_image,replicate_image,provider_http,azure_translation}.py` |
| Post 파일 기록 / quota·job·공개 부착 | 파일은 `social/service/media_storage.py`; 기존 `services/post_image_generation.py`, `post_image_job_worker.py`의 quota/job/부착은 정확한 AR-B5 업무 소유 |
| World Package export/import 이미지 | Package의 별도 B3 source가 소유; lossless 재인코딩·journal/보상 경로는 profile codec에 합치지 않음 |
| 생산 호출 없는 옛 `services/profile_media.py` export | 함수 본문은 없고 frozen compatibility tests만 남음. AR-B8-A에서 source/test 계보와 함께 제거 |
| Runtime의 옛 Pollinations model-list·URL/download helper 7개 | 기존 model-list/credential/validated-transport 테스트만 직접 호출. 새 생성 흐름에 연결하지 않으며 AR-B8-A가 정확한 테스트 호환 표면을 종료 |
| 이미지 설정·서비스 key·Creator LLM·Local Bot·다중 owner 삭제 | 기존 runtime/credentials·AR-B8-A 실제 조립 소유. 동일 Session/credential/provider/log/cleanup 의미를 바꾸지 않음 |

공개 media mount는 기존 characters/posts/world-package-imports만 유지한다. World/draft/candidate를 anonymous 정적 경로에 추가하지 않았다. 관련 권한/비공개 검증의 통과를 실제 Installer/real-provider 검증으로 확대하지 않는다. 현재 Media M1~M6의 새 nodes는 26개이며 source introduction·통합 Actions·순차 merge는 root가 관리한다.

M6 고정 후보에서 `--contracts --nodes`는 현재 **2,151 nodes**를 수집했다. 보호 계보 2,125개 대비 API/ORM·기존 assertion/suppression·누락 node·source split 오류는 없었다. 실패 목록은 M1~M5의 root 선형 capture를 기다리는 source 12개·test 21개뿐이며 M6 새 5개는 이 검사 당시 미커밋 도입이었다. source 고정 후 root가 M1~M6의 각 첫 도입 SHA에서 append-only 증거를 추가한다.


## AR-B5-B2 — Social 공개 판단·읽기·응답 조립과 소유 조회

기존 Community 오류 13개와 상수 4개를 Social의 `exceptions.py`와 `constants.py`로 옮겼다. 게시물과 thread 읽기, 공개 판단, 응답 조립 함수의 실제 본문은 `service/{posts,visibility,presentation}.py`가 소유한다. 삭제·신고·인용·reply 조상 체인 판단 순서와 숨김 응답은 같으며 기존 service의 남은 기능은 같은 함수 객체를 연결한다.

응답 조립의 User 조회는 Identity `service/profile.py::get_user`, Character 조회와 멘션 SQL은 Character `service/profile.py`가 소유한다. User 조회의 nullable `db.get`와 attached identity, 멘션의 기존 한 번의 SQL/active·not-deleted 조건은 같다. 응답에서 멘션 순서와 중복 제거를 유지하고 새로운 flush·commit·refresh를 추가하지 않았다. 서로 다른 도메인의 ORM을 Social에서 직접 조회하지 않는다.

신규 **2 nodes**는 `tests/social/test_identity_read_collaboration.py`에 있다. 실제 SQLite에서 멘션의 한 번의 조회·입력 순서·삭제/정지 필터·빈 입력 0쿼리, User의 같은 attached 객체·미저장 변경·없는 대상 None·flush/commit 0을 검증한다. 기존 게시물 테스트는 monkeypatch를 실제 새 소유 함수에 연결했고 assertion/raises/warns는 동일하다. 초기 2개 실패는 아직 이전하지 않은 mention notification의 patch 위치를 너무 넓게 바꾼 fixture 문제였으며 실제 남은 caller 위치로 좁혀 수정했다.

최종 집중 검증은 **107 passed / 1 existing warning / 21.68s**다. #258/#263 API·schema·ORM 차이 0, 변경 기존 테스트 1개 파일의 assertion 계약 PASS, 전체 split evidence PASS다. Media/Package 통합 후 기존 B2 split evidence 27개의 Package 테스트 경로만 이미 승인된 exact node map의 현재 목적지로 연결했다. 보호 원본 node, 기준선, 검사 규칙은 변경하지 않았다. Architecture는 **658 modules / 2,129 edges / 247 exact legacy edges**, L4 inventory는 **658 modules / parity 97**, ER0는 **Postgres 78 files / historical migration subset 87 / Neo4j 24 / Next 44 / parity 7**로 통과했다.

Social 쓰기·프로필·Inbox·agent 도구·미디어 job, Relationships 및 projection은 B5 잔여 구현이다. 이번 source 고정과 새 nodes 도입은 root가 선형 capture·통합 Actions·PR/merge로 이어가며 이 기록은 전체 B5 완료를 주장하지 않는다.


## AR-B5-B3 — 공동 활동의 Post 필드 변경 협력

기존 `apply_joint_post`의 Post `joint_activity_id` 1곳과 `opening_post_id` 2곳 대입을 `social/service/joint_posts.py`의 두 한정 함수가 소유한다. 한 함수당 원래 필드 대입만 수행하며 호출 위치는 같다. 공동 활동 validation 전에 joint ID가 기록되는 원래 순서와 이후 opening 분기, 기존 caller의 flush·commit·rollback 책임을 보존한다. Routines의 Joint 자체 필드와 participant/claim 변경은 그대로 Routines 소유에 남는다.

신규 **1 node**는 `tests/social/test_joint_post_links.py::test_joint_links_keep_assignment_stages_and_caller_rollback`이다. 실제 Session의 attached Post에서 두 단계 사이 opening 값이 유지되고 자동 flush·commit이 없으며 caller rollback으로 두 값이 복구되는지 검사한다. 기존 proposal/opening 회귀와 합쳐 **6 passed / 7.58s**다. 초기 신규 fixture는 존재하지 않는 content 인자를 사용해 실패했으며 실제 Post의 body/author_name 필드로 고쳤다. 기존 제품 assertion은 바꾸지 않았다. B4의 실제 joint 서비스가 합류하면 동일 helper를 runtime의 typed collaborator로 연결하고 이 legacy consumer bridge를 종료한다.

## AR-B4 준비 — 공동 게시 소유 함수를 위한 Social 선행 소스 합류

A3c `ac57f1e`에서 B5 source `f8d173d`의 실제 ancestry를 연결했다. 각 factory의 Package·routines·Character management/media·Creator/image generation 등록을 모두 보존하고, 겹친 Package 등록만 같은 한 번의 호출로 정리했다. Post evidence 조회와 그 실제 Session 테스트는 `social.models.posts.Post`로 연결해 A3b의 한시적 legacy Post read edge를 제거했다. 선행 Package replay hotfix와 canonical `runtime/world_packages/seed_uow.py`, Media·WC·Social 계약도 함께 유지한다.

routines·proposal·routine 게시·Social joint 링크·Package seed 경합 집중 검증은 **57 passed / 1 기존 PostgreSQL skip / 56.24초**다. 현재 경계는 **669 modules / 2,192 edges / legacy exact 244 PASS**, ER0 **80/87/24/44/7**, L4 parity **97**이다. JSON 지도 병합은 원본 `old`와 실제 `new` 쌍을 함께 식별하여 하나의 원본 함수가 여러 책임으로 나뉜 증거를 잃지 않게 했다. frozen source와 기존 introduction 기록은 재작성하지 않고 합류한 기록을 보존한다. Notification의 add-only 후속 협력 source를 연결한 뒤 A3d 실제 소유 전환·최종 통합 보존 검증을 이어간다.

### AR-B5-B3 후속 — 공동 활동 알림의 조회·add 책임

`service/notifications.py::ensure_joint_started_notification`은 원래 notification type/joint/recipient의 정확한 조회와 없는 경우 add만 수행한다. 일반 `create_notification`의 finish_write에 합치지 않았다. Routines가 다른 참여자와 actor WC를 같은 순서로 검사한 뒤 원래 ID를 전달하고 마지막 flush를 계속 소유한다. JSON 정렬·구분자·event/Post/World/Character 필드는 동일하다.

새 **1 node**는 `tests/social/test_joint_notifications.py::test_joint_notification_keeps_exact_dedupe_payload_and_caller_write_boundary`다. add-only·정확 중복 기준·기존 event 보존·다른 수신자 분리·caller rollback·원래 JSON을 실제 SQLite로 검증한다. 공동 활동 회귀와 합쳐 **7 passed / 7.42s**다. 원래 성공 source event/claim/participant/plan 상태와 알림의 같은 Session·최종 flush를 유지한다.
routines 준비의 후속 merge `183e73d`는 Notification helper source `8c9133a`를 실제 계보로 연결한다. 합류 후 joint 링크·proposal 6개는 통과했으나 Notification 신규 테스트를 단독 실행하자 참조 ORM이 등록되지 않아 DDL의 NullType 오류가 발생했다. 다른 테스트의 import 순서에 의존하던 fixture이므로 두 joint 테스트에서 기존 모델 등록 조립을 명시하고 재실행하여 **2 passed / 1.23초**를 확인했다. 제품 모델·DDL·기존 assertion을 바꾸지 않았고 B5 담당에게 같은 fixture 보완을 전달했다.

## AR-B4-A3d — 공동 활동의 실제 참가·계획·시작·종료 소유권

옛 `services/joint_activity_runtime.py`의 실제 본문을 Routines `service/joint_activity/{eligibility,planning,execution}.py`로 나누고 옛 파일을 제거했다. 오류는 `exceptions.py`, immutable OpeningClaim은 `contracts/joint_activity.py`, 원래 tuple/set/lease/attempt 값은 `constants.py`가 소유한다. 같은 역할의 package export에는 전달 함수가 없다. 서로 다른 참가 허용 범위와 오류를 가진 기존 `joint_scheduling.py` 및 plan 예약 helper를 이름이 비슷하다는 이유로 통합하지 않았다.

Foreign WC·membership 조회와 차단·장소·게시 수·SocialEvent evidence SQL은 `SqlAlchemyJointReferences`가 호출자의 Session으로 수행한다. Post ID 대입과 notification 조회/add는 Social 소유 함수로 연결했다. 두 참여자 검증, 원래 lock·claim 만료/attempt·commit, 계획 revision·부분 생성 거부, Post joint ID 선대입, 시작 event 후 다른 참여자→actor 조회→알림→최종 flush, 완료 시 양방향 event와 rows가 있을 때만 commit하는 순서를 그대로 유지한다. 원래 20개 class/function 본문은 협력 호출만 원문으로 복원해 AST 차이 0, 별도 추출한 5개 foreign SQL/event 표현도 차이 0을 확인했다.

새 `tests/routines/test_joint_composition.py`의 **2 nodes**는 실제 별도 연결의 SQLite에서 Post·post event·started event·알림·두 participant/item/episode가 하나의 caller commit으로 함께 보이거나 rollback으로 함께 사라지는지 검사한다. 원래 callback 순서와 같은 attached 객체도 검증하며 callback은 새 Session이나 commit을 만들지 않는다. 첫 집중 검증은 기존 공동 활동·일정·Social helper **25 passed**, 이어 신규 UoW와 routine 게시를 포함해 **44 passed / 1 기존 PostgreSQL skip / 19.46초**다.

기존 happy-path의 `assert apply_joint_post(...) is None`은 원문의 인자와 판단식을 유지한다. 해당 테스트에만 실제 서비스 함수의 Session 협력을 `functools.partial`로 미리 연결하고, 다른 호출은 명시적으로 references를 전달한다. 기존 assertion/raises/warns AST 누락은 0이며 보존 검사는 변경하지 않았다. AR-B5 Proposal 소비자 한 개의 legacy→canonical 호출은 정확한 기한 있는 bridge로 기록하고, B5의 실제 Proposal 전환에서 종료한다. RoutinePost provider/context·resident/lease/activity log와 잔여 public/호환은 다음 B4-B/C 범위이므로 routines는 PARTIAL이다. 최종 집중·통합 보존 검증과 부모의 source-introduction 기록은 별도 후속 기록으로 남긴다.

A3d 최종 집중 검증은 **69 passed / 1 기존 PostgreSQL skip / 66.21초**다. 전체 보존 검사는 frozen **1,867/1,907**, 보호 계보 **2,139**, 현재 **2,217 nodes**를 확인했고 API/ORM·기존 assertion/raises/warns/suppression·누락 node의 차이는 0이다. 지도 검사는 최초에 내부 메서드 이름을 top-level symbol 칸에 기록한 11개 형식 오류를 찾았다. 실제 class 이름을 symbol로, 정확한 메서드는 destination_members로 기록해 교정하며 검사 코드는 바꾸지 않았다. 새/선행 source와 node introduction은 부모의 선형 capture가 남아 있다. 현재 경계는 **674 modules / 2,222 edges / legacy exact 241 PASS**, ER0 **81/87/24/44/7**, L4 parity **97**이다.

## AR-B5-B4 — 원본 게시물·반응·팔로우 저장 책임

기존 CRUD의 13개 실제 함수 본문을 Social `service/source_posts.py`, `repository/reactions.py`, `repository/profiles.py`로 옮겼다. 글 생성의 정제·검색 문서·작성자 표시 이름, 반응의 잠금/중복·신고 경쟁 복구, 팔로우 exact 조건과 모든 flush/commit/refresh 순서는 그대로다. 원래 13개 함수 body AST가 동일함을 확인했다. 다른 도메인의 ORM type을 직접 참조하던 annotation은 `contracts/actors.py`의 읽기 값으로 바뀌며 실제 객체를 복제하거나 새 조회를 추가하지 않는다. 남은 기존 caller에는 동일 함수 객체의 임시 import만 남긴다.

새 **3 nodes**는 `tests/social/test_source_write_boundaries.py`에 있다. 실제 SQLite에서 User/Character 테이블 없이 이미 확인된 actor 값만으로 게시물·반응·팔로우가 동작하는지, dedupe·부드러운 삭제와 caller의 deferred commit/rollback이 보존되는지 확인한다. 예외적으로 기존 low-level legacy comment 함수의 명시적 commit도 같은 의미로 보존한다. 신규 팔로우 검증은 첫 이전에서 빠진 `unit_of_work` import를 찾아내어 이를 보완했다. 기존 일반 회귀만으로 놓친 이 실제 소비 경로를 새 테스트로 보호한다.

최종 집중 회귀는 **63 passed / 1 existing warning / 22.93s**다. Architecture는 **662 modules / 2,147 edges / 247 exact legacy edges**, L4는 **662 modules / parity 97**, #258/#263 API/schema/ORM과 전체 split 근거는 동일했다. 신규 joint fixture 2개도 현재 complete ORM 등록을 명시했으며 각각 단독 실행 1 PASS를 확인했다. 제품 DDL이나 기존 assertion을 바꾸지 않았고 테스트 실행 순서에 의존하던 setup만 보완했다. 이 단계는 전체 B5 완료가 아니며 외부 mutation workflow·프로필/Inbox/agent·Relationships/projection은 다음 구현 범위다.


## AR-B5-B5 — 실제 timeline 쓰기·알림·World 범위 판단

`SocialTimelineService`는 기존 Community의 글 생성·대꾸·인용·좋아요/해제·리포스트/해제·신고·삭제 9개 실제 함수를 소유한다. 작성자 권한, 기존 quota 처리 위치, 원본/알림/활동 로그, repost/delete 확장, 관계 이벤트 제외 직후 commit을 원래 순서로 유지한다. Runtime은 이전부터 있던 log_activity·quota·관계 이벤트 처리만 같은 Session으로 연결하고 제품 정책을 결정하지 않는다. 구 서비스의 이 함수들은 새 서비스 인스턴스의 같은 bound method만 참조한다. 기존 low-level legacy comment 저장과 HTTP에서의 comments-disabled 오류도 각각 그대로다.

WorldCharacter는 `service/social_scope.py`에서 기존 WC 작성 범위와 current World→WC→World membership 판단을 소유한다. membership 조회는 Worlds의 기존 nullable same-Session getter를 호출한다. Social 오류 메시지/종류와 응답은 같다. 일반 값 계약으로 primitive owner_id를 먼저 평가하던 초기 후보는 원래 조회 순서를 앞당길 수 있어, 이를 관찰하는 신규 **4 cases**를 먼저 실패(4 FAIL)시킨 뒤 동일 attached 객체의 읽기 계약을 전달하도록 고쳤다. owner_id는 원래처럼 멤버십 조회·앞선 guard 이후 읽으며, 실패 경로에서는 불필요하게 읽지 않는다.

알림의 수신 대상·멘션/자기/중복 제외는 `service/notifications.py`로, 제한된 topic/result 문자열은 `service/activity_results.py`로 이전했다. 40줄 공통 문맥 정제는 `services/llm_context.py`에서 `core/context_text.py`로 whole-file 이동하고 실제 소비 import를 전환했다. 정규식/정제 본문은 동일하다. 기존 멘션 notification fixture 2개는 실제 새 소유 함수를 patch하도록 수정했으며 assertion은 그대로다.

최종 집중 회귀는 **107 passed / 1 existing warning / 23.02s**다. 새 4 nodes는 `tests/social/test_timeline_world_scope.py`에서 원래 오류, 같은 Session의 조회 순서, owner_id 읽기 시점, unscoped 0조회 경로를 검증한다. 수동 작성 AI 0·World/owner 차단·Social event/outbox 원자성·source 삭제·기존 이미지 generation·문맥 정제 검증을 함께 실행했다. Architecture는 **667 modules / 2,175 edges / 241 exact legacy edges**다.

Root와 합의한 잔여가 있다. `CommunityMutationQuotaBucket` 실제 정의와 Identity public/legacy auth/common model의 기존 동일 객체 assertion은 유지한다. 해당 모델과 공개 별칭의 최종 소유는 G5/B8에서 검토한다. 이 때문에 기존 quota 호출과 B4-C의 기존 AgentActivityLog 호출 2개만 정확 runtime 경로로 옮겼으며 원래 다른 도메인의 ORM을 서비스에 재수출하지 않았다. 기존 legacy 검사 형식의 owner_stage L6 아래 removal_condition에 정확 AR-B4-C/G5/B8 소유를 기록했다.

B5-B5 최종 보존 검사: #258/#263 API/schema/ORM 차이 0, 변경 기존 테스트 3개 파일 assertion/raises/warns PASS, 전체 split evidence PASS. 기존 검사 형식의 top-level class 매핑에 각 destination_member를 함께 기록했고 실제 nested method 12개가 존재하는지 별도 AST 확인했다. L4 667 modules/parity97, ER0 Postgres78/migration subset87/Neo4j24/Next44/parity7도 통과했다.

### AR-B4-B 준비 — 공통 context text와 Social timeline 선행 연결

A3d `7ca4e38` 뒤 B5 `c0f3be2` 전체 계보를 합쳤다. `services/llm_context.py`의 동일 함수가 `core/context_text.py`로 이전한 경로를 유지하고, Social timeline의 활동 기록은 현재 AgentActivityLog 구현을 같은 Session callback으로 연결한다. Joint UoW·기존 Proposal·RoutinePost·Social 소유 회귀는 **39 passed / 1 기존 PostgreSQL skip / 16.44초**다. 경계 **682 modules / 2,265 edges / legacy exact 235 PASS**, ER0 **81/87/24/44/7**, L4 parity **97**을 확인했다. `test_timeline_writes.py`라는 존재하지 않는 파일명으로 첫 테스트 수집이 거부되어 실제 `tests/social`의 소유 검증을 포함해 다시 실행했으며 제품 코드는 그 사이 수정하지 않았다. B4-B의 schema·이벤트 제한·context·provider 역할 이전은 이 통합 뒤에 진행한다.


## AR-B4-B1 — RoutinePost schema·상호작용 계약·이벤트 문맥 정책

API 하위의 실제 Pydantic 형식은 `routine_posts/schemas.py`, `RoutineInteractionInput`은 `contracts/interaction.py`로 옮겼다. Social 감정/동기 enum은 같은 canonical contracts 값을 참조한다. `_bounded_events`의 World/consumer/time/replay 필터, source 중복·정렬·범위 정규화·개수/문자/JSON byte 제한은 `service/event_context.py`가 실제 소유하고, 상수·오류·공통 text 표현을 각 역할로 나눴다. 생성기와 context 양쪽의 동일 `_clip`은 실제 구현 한 개로 모았다.

옛 API/domain initializer와 global routine schema alias를 제거하고 schema 등록은 실제 새 클래스를 import한다. 기존 20개 실행 node와 helper/parametrize/skip 조건을 바꾸지 않고 `tests/routine_posts/test_runtime.py`로 이전했다. local-smoke·ER0·closeout과 source/node/split 지도는 현재 경로를 사용한다. 복사한 전체 테스트 AST는 동일하고, 이전한 값·함수/클래스 본문 36개도 차이가 없다. 새 기능이나 추가 회귀 node를 만들지 않았다.

첫 집중 검증은 **75 passed / 1 기존 PostgreSQL skip / 2 failed**였다. 실패는 옛 WC setup/owner-identity suite 경로와 Today inventory generator의 삭제된 Social import였다. WC의 두 문자열을 이미 승인된 정확 경로로 연결하고 원래 inclusion assert를 유지했다. Today JSON은 MemoryBatch의 동결된 predecessor이므로 historical REQUIRED_FILES·JSON·SHA를 재생성하지 않고, 실행에 필요한 동일 Social contract import만 바꿨다. `--check`의 기존 frozen SHA 검사는 통과한다. 두 번째 광역 실행은 **76 passed / 1 기존 skip / 1 경로 실패**였으며 마지막 owner-identity 문자열 보완 후 영향 범위를 다시 검증한다.

전체 보존 검사는 frozen **1,867/1,907**, 보호 계보 **2,139**, 현재 **2,224 nodes**를 확인했고 API/ORM·기존 assertion/exception/suppression·누락 node의 오류는 0이다. split 검사에서 frozen context의 옛 `activity_runtime` alias 한 개의 전달 증거가 빠져 있어 A3b가 이미 연결한 DueTick·namespace·latest_due_tick의 실제 소유 대상으로 추가했다. B1 split 전용 재검증은 **오류 0**이며 검사 규칙은 바꾸지 않았다. 새/선행 소스 등록은 부모의 선형 capture가 남는다.

현재 경계는 **686 modules / 2,274 edges / legacy exact 234 PASS**, ER0 **81/87/24/44/7**, L4 parity **97**이다. RoutinePost는 B1의 정확한 9개 역할 모듈만 PARTIAL 전환 대상으로 관리한다. 실제 foreign query·재시도 context 조립과 provider 검증/prompt/통신, 그 직접 public/서비스 별칭 소비자는 AR-B4-B2/B3에서 종료한다. 전체 B4와 실제 설치/재시작·Hosted CI·merge 완료를 주장하지 않는다.

B1의 마지막 수정은 CI가 요구하는 기존 WC suite 경로 문자열 하나였다. 수정 후 RoutinePost·Proposal·closeout·Today inventory 검증은 **29 passed / 1 기존 PostgreSQL skip / 10.62초**로 통과했다. 앞선 광역 실행의 제품 검증 76개와 이 마지막 영향 범위 결과를 구분해 기록하며, 광역 78개 전체가 마지막 tree에서 다시 통과했다고 표기하지 않는다. source 고정 시 제품 코드와 기존 assertion/조건은 그대로이며 frozen baseline/checkpoint/additions와 Today predecessor JSON 변경은 0이다.


## AR-B4-B2 — RoutinePost 문맥·재시도와 같은 Session 조회

`RoutinePostContext`·source 계약은 `contracts/context.py`, 실제 scope/readiness/이전 성공/claim 만료/재시도/source 순서와 소비 차단 정책은 `service/context.py`로 이전했다. `runtime/routine_posts/context_references.py`는 원래 nullable get·SQL 12개를 호출자의 같은 Session에서 연결하며 consumption 결과를 즉시 list로 바꾸지 않고 기존 iterator로 반환한다. membership/Post의 동일 조회는 이미 존재하는 ActivityReferences 구현을 사용한다. 다른 업무의 attached 객체는 복제하지 않으며 새 Session·commit·명시적인 flush를 만들지 않는다.

업무 함수의 collaborator 호출을 원문 표현으로 복원해 body/order AST 차이 0, runtime으로 추출한 실제 nullable get/SQL 12개도 차이 0을 확인했다. 원래 interaction source factory와 동일 클래스가 같은 위치에서 만들어지고, provider 주입/fake와 원래 db callback을 유지한다. `services/routine_post_context.py`와 옛 `infrastructure/sqlalchemy_context.py`는 실제 소비자를 전환한 뒤 제거했다. Routines 상태 검증·적용은 기존 실제 함수를 service의 같은 객체 export로 제공한다.

새 **2 nodes**는 독립 연결의 SQLite에서 applied/active-claimed 소비 기록과 episode 상태의 미커밋 변경을 caller context가 보고, observer에게는 보이지 않으며 rollback으로 원복되는지 검증한다. 초기 fixture가 자기 자신을 대상으로 한 SocialEvent를 만들어 기존 DB 제약에 걸렸으므로 실제 다른 참여자를 생성하고 FK 검증을 켰다. 기존 제품 정책·assertion·parameter ID·PostgreSQL skip은 바꾸지 않았다. 수정 후 집중 검증은 **26 passed / 1 기존 PostgreSQL skip / 10.81초**다.

Direct LLM 응답 검증·prompt/transport와 그 public/서비스 별칭은 B3, AgentActivitySetting과 canonical interaction adapter는 B4-C의 실제 남은 소유 전환 범위다. 현재 RoutinePost scope에는 실제 전환한 contract/service만 추가하고 bridge는 정확한 남은 consumer/종료 단계로 기록한다. frozen source/checkpoint/approved nodes/Today predecessor JSON은 변경하지 않는다. 최종 보존 검사와 source introduction·통합 Actions·merge는 이어지는 별도 증거로 기록한다.

B2 최종 고정 후보의 집중 묶음은 **67 passed / 1 기존 PostgreSQL skip / 46.67초**다. 보존 검사는 frozen **1,867/1,907**, 보호 계보 **2,139**, 현재 **2,226 nodes**를 확인했고 API/schema/ORM·기존 assertion/raises/warns/suppression·누락 node·모든 split 증거 오류는 0이다. 종료 코드 1의 항목은 선행 source/test의 부모 append-only introduction 기록 대기뿐이다. 현재 구조 경계 **687 modules / 2,289 edges / legacy exact 235 PASS**, L4 parity **97**, ER0 **81/87/24/44/7** 및 MemoryBatch inventory 검증도 통과했다. 원래 활동 설정 조회의 위치가 context에서 runtime으로 바뀐 한 개 edge만 AR-B4-C 종료 조건으로 추적하며 광역 legacy prefix는 허용하지 않았다.


## AR-B4-B3 — RoutinePost 근거 검증·생성 순서·provider 요청 경계

기존 DirectRoutinePostProvider의 실제 계획→검증→게시문 작성 순서는 `service/generation.py`가 소유한다. bounded public context, server-owned identity/continuity/detail/source 검증, Gemini response schema 제한과 상태 효과는 `service/evidence.py`로 옮겼다. immutable RoutineGeneration과 실제 fake/provider 교체 계약은 `contracts/generation.py`, 목적별 credential 해석과 LLM 요청 identity 변환은 `client.py`에 있다. 공유 SDK/transport는 이미 존재하는 `integrations.direct_llm`이며 새 전달 함수를 추가하지 않았다.

원래 값·함수·class 15개의 AST가 foreign read annotation을 제외하고 동일하다. prompt literal/JSON 직렬화, planner 선검증, writer 입력, 2400 token/medium, tracker와 rate-limit callback, error node/lane, runtime의 최종 생성 재검증을 유지했다. 예전 infrastructure provider·initializer, public 및 services/routine_post_planner alias는 직접 소비자를 canonical roles로 연결한 뒤 제거했다. plaintext reveal allowlist의 동일 `_api_key` 항목만 정확 client 경로로 바꾸며 검사 강도/목록 범위는 유지한다. Today inventory의 동결된 predecessor path/SHA는 수정하지 않았다.

기존 검증은 **36 passed / 1 기존 PostgreSQL skip / 20.47초**였고, 새 transport fake 3 cases를 포함한 묶음은 **32 passed / 1 기존 skip / 16.51초**다. 실제 생성 서비스를 호출하여 credential→planner→writer 순서, 잘못된 beat 근거에서 writer 0회, writer 오류 원객체와 node/lane, callback/tracker identity, prompt에 credential 미포함을 검사한다. 생성 성공을 게시 성공으로 기록하지 않으며 새로운 DB write/commit은 없다.

도메인의 실제 역할 모듈만 부분 scope에 추가하고 provider/public의 종료된 bridge는 제거한다. 원래 runtime의 publication/claim·AgentRun/Social 결합, interaction adapter와 활동 설정/lease/log는 AR-B4-C 잔여다. 소스 도입 기록·전체 통합 Actions/installer/merge는 부모 작업에서 순차 확인한다.

B3 최종 집중 묶음은 **70 passed / 1 기존 PostgreSQL skip / 49.02초**다. 전체 보존 검사는 frozen **1,867/1,907**, 보호 계보 **2,139**, 현재 **2,229 nodes**를 확인했고 API/schema/ORM·기존 assertion/raises/warns/suppression·누락 node·모든 split 증거 오류는 0이다. 선행 소스/test의 부모 append-only introduction 기록 대기만 종료 코드 1로 남는다. 현재 구조 경계 **687 modules / 2,295 edges / legacy exact 235 PASS**, L4 parity **97**, ER0 **81/87/24/44/7**, MemoryBatch inventory도 통과했다. 고정된 baseline/checkpoint/Today predecessor는 변경하지 않았다.


## AR-B4-C1 — 활동 설정·실행 기록·로그의 실제 소유 기반

AgentActivitySetting·AgentRun·AgentSlot·AgentPublicActionExecution·AgentFeedCue·AgentActivityLog의 실제 class는 `routines/models/resident.py`로 옮겼다. 기존 계획 모델/schema는 `models/plans.py`와 `schemas/plans.py`로 whole-file 이동하고 같은 객체의 package export를 제공한다. 활동/로그/슬롯 응답 5개와 settings/feed-cue 요청·응답 3개는 `schemas/resident.py`가 소유하며 원래 UTC serialization을 유지한다.

Settings get/ensure/update의 실제 본문은 `service/activity_settings.py`, log/filter/list 본문은 `service/activity_logs.py`, 원래 기본값/제한/hidden9/90초 dedupe 값은 constants가 소유한다. 27개 class/function/value AST와 원래 plan model/schema whole AST의 차이는 0이다. Settings의 commit/refresh 대 flush, log의 deferred finish_write, hidden 제외·created/id DESC·oversampling·state dedupe 순서를 유지했다. global model 등록은 같은 class를 직접 연결하고 삭제된 activity/slot/core limits 및 임시 Runtime 응답 파일은 경로 지도에 기록한다.

최초 기존 집중 묶음은 **135 passed / 1 기존 PostgreSQL skip / 3 기존 warnings / 55.02초**다. 새 file SQLite 검증은 settings commit True/False 및 deferred 로그의 별도 observer 격리·rollback·hidden/state dedupe **3 nodes**다. 최초 신규 fixture가 _seed에 없는 설정을 읽어 실패했으며 실제 ensure_setting을 호출하도록 수정했다. 수정 후 영향 범위는 **86 passed / 3 기존 warnings / 21.07초**다. 기존 assertion/조건을 변경하지 않았다.

AgentRelationshipPoint는 B5, AgentDaypartMemoryEvent는 B7의 실제 소유로 이어지므로 원래 global run model 파일에 남겼다. AgentImageGenerationSetting도 이 활동 설정과 합치지 않았다. Social timeline의 log callback과 RoutinePost의 활동 설정 read는 같은 Session/canonical class로 연결했고 기존 exact legacy 두 edge를 제거한다. 이후 B5 discovery/profile_activity의 ActivityLog/filter/hidden9 소비자는 선행 source 합류 후 같은 소유로 연결한다. Social 별도 hidden6 정책은 합치지 않는다.

현재 scope는 실제 모델/DTO/log/settings만 포함한다. Scheduler/lease·실행 그래프/LLM 정책·FeedCue/slot 쓰기·mixed owner filtering과 HTTP·잔여 호환 종료는 C2+ 범위다. frozen baseline/checkpoint/기존 node/API/ORM 및 historical migrations는 수정하지 않으며 source introduction·통합 Actions/installer/merge는 부모가 선형으로 이어간다.


C1 경계 검사에서 DTO 소유 이전에 따라 Character.schemas→Routines→WC→Character의 순환이 드러났다. 원인은 계획의 한 개 character_contract_hash 직접 import였다. 기존 PlanReferences에 동일 hash 읽기 협력을 연결해 원래 World/WC 준비 확인 이후·repertoire 조회 이전 위치와 같은 attached 객체를 유지했고 별도 core 정책이나 경계 예외를 만들지 않았다. 신규 준비 순서 검증 1개를 추가하여 C1 신규 검증은 **4 nodes**다. 설정/로그/계획·활동 제한 집중 묶음은 **99 passed / 2 기존 warnings / 24.43초**다. 이 변경은 source/member map에 같은 함수 호출의 실행 연결로 기록한다.

C1 최종 고정 후보의 집중 검증은 **158 passed / 기존 PostgreSQL 1 skip / 기존 warnings 3 / 77.68초**다. 직전 실행의 유일한 실패는 B3에서 제거한 `routine_posts/public.py`를 기대하는 옛 구조 검사였다. 실제 `contracts`의 interaction/context/generation 및 package 네 파일 모두를 기존 두 assertion과 같은 금지 import 목록으로 검사하도록 연결했다. 제품 동작이나 검사 predicate를 변경하지 않았다.

경계 검사는 **690 modules / 2,308 edges / exact legacy 232**, cycle 0으로 통과했다. Stock 보존 명령은 아직 append되지 않은 선행 B4 최초 도입 두 파일(`routines/models.py`, `schemas.py`)의 후속 이동에서 중단되므로 전체 PASS로 표시하지 않는다. 별도 읽기 전용 진단은 서명된 최초 도입 commit `869bae55a2e5e665fb731396a7284b53dde8a104`의 정확한 두 Git blob만 메모리 snapshot으로 보충하여 원래 검사 함수를 호출했다. **source/split symbols/assertions/suppressions/API·ORM/missing nodes 각각 오류 0**, 보호된 기존 **2,139 lineages / 현재 2,233 nodes**다. tracked baseline/checkpoint/additions·검사 코드는 변경하지 않았다. 부모의 선형 source 도입 append 후 stock 전체 검사는 여전히 필수다.


## AR-B4-C2 — 활동 시각 정책과 resident 실행 조립

`core/agent_activity_schedule.py`의 실제 active-window/timezone/DST/jitter/retry 계산은 `routines/service/tick_schedule.py`로, resident scheduler의 실제 process lock/lease/heartbeat/cancellation/drain 구현은 `runtime/resident/scheduler.py`로 이전했다. `runtime/component_workers`가 기존 in-process 실행을 연결한다. `services/resident_contracts.py`의 순수 GraphState와 Session/model-rich Context는 각각 Routines 계약과 runtime context로 분리하고 기존 클래스 본문/필드/default를 유지했다. 모든 직접 Python 소비자는 같은 bound name으로 연결했고 옛 실제 파일은 제거했다.

기존 활동 제한·scheduler singleton 테스트 두 파일을 `tests/routines`로 옮기고 원래 assertion/조건/fixture를 보존했다. RoutinePost publish/ER7 종료·OSS 경계 검사와 함께 **126 passed / 기존 PG 1 skip / 기존 warnings 3 / 53.17초**다. SDK/subprocess 검사에는 분할된 실제 계약 두 파일 모두를 포함한다. Live embedded inventory의 실제 scheduler/test 경로만 갱신하고 predecessor/frozen 자료는 유지한다.

ActivityPolicy 값과 agent-run 실행은 아직 후속 C3+ 소유 전환 대상이며 runtime은 기존 동일 구현을 연결한다. Source introduction/capture와 최종 stock 보존·Actions/installer는 부모의 선형 통합 후 확인하므로 이 단계 완료를 전체 B4 완료로 표시하지 않는다.

C2 최종 후보는 **196 passed / 기존 PG 1 skip / 기존 warnings 3 / 125.17초**다. 실제 클래스/함수/상수 **30개 AST가 원문과 동일**하며 경계는 **692 modules / 2,309 edges / exact legacy 227 / cycle 0**으로 통과했다. L4·ER0·Memory batch 현재 inventory도 통과했다. 기존 mixed Context의 models/ActivityPolicy 및 scheduler의 schemas/AgentRun 네 import는 원래 body와 함께 실제 runtime caller로 옮긴 정확한 임시 edge이며, 새로운 대상/범위/실행 동작은 없다. C3+/G5의 실제 소유 전환 때 각 edge를 제거한다.

읽기 전용 보존 진단에서 source/assertion/suppression/API·ORM/node는 각각 오류 0이었다(보호 2,139, 현재 2,233). 같은 진단의 split 검사는 current map 갱신 과정에서 AR-B1/AR-F1의 옛 파일럿 형식 7개를 잘못 다시 계산한 것을 잡았다. 두 detail을 직전 source의 원문으로 복원하고 새 split_symbols 형식만 갱신하도록 수정했다. 복원 후 원래 split 검사도 **오류 0**이다. 이 정정은 현재 경로 지도만 다루며 frozen baseline/checkpoint/additions는 변경하지 않는다. 부모의 선형 도입 append 후 stock 전체 보존 검사를 통과해야 한다.


## AR-B4-C3a — Run 응답·정책 값·세션 규칙 실제 소유

기존 agent_runs schema의 다섯 실제 DTO를 `routines/schemas/runs.py`로 이전하고 global aggregate 및 직접 소비자들을 같은 class로 연결했다. ActivityPolicy의 immutable 결과/should_skip_llm/prompt/result 본문과 tendency prompt, 세션 두 판정 함수, 다섯 상수 및 동일 denied error를 역할 파일로 옮겼다. Runtime Context는 Character/Identity/Routines의 동일 실제 타입을 import하고 scheduler는 canonical Tick DTO를 사용한다. C2 임시 네 edge 중 models/ActivityPolicy/schemas 세 edge를 제거했다. 실제 정책 build/assert/count 및 World/import scope SQL은 C3b에서 계속 이전한다.

C3a 최초 집중 검증은 **200 passed / 기존 PG 1 skip / 기존 warnings 5 / 41.77초**, inventory 갱신 후 최종 후보의 광역 검증은 **268 passed / 기존 PG 1 skip / 기존 warnings 5 / 121.75초**다. 원래 정책의 33개 정의와 Run DTO 5개 정의는 AST 차이 0이며, 런타임 Context의 **21개 resolved type이 전부 같은 실제 객체**다. 경계는 **694 modules / 2,318 edges / exact legacy 222 / cycle 0**, L4·ER0·Memory batch 현재 inventory는 통과했다.

선행 signed 두 경로 blob만 메모리에 보충한 원래 검사 함수의 읽기 전용 진단도 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 기존 보호 **2,139 / 현재 2,233 nodes**다. Source introduction metadata는 부모가 선형 append하며 stock 전체 보존·Actions·installer·최종 B4 완료는 별도로 남아 있다. 기존 테스트의 assertion/parametrize/skip 및 frozen 자료를 수정하지 않았다.


## AR-B4-C3b — 활동 허용 흐름·횟수 SQL 실제 이전

build/assert/count의 실제 허용·차단·제한·cooldown 흐름은 `routines/service/activity_policy.py`, 자기 ActivityLog의 세 실제 SQL 함수는 `repository/activity_counts.py`, log action-type 정규화는 `utils/activity_actions.py`로 이전했다. 기존 World timezone을 읽는 함수는 명시적 lazy collaboration으로 전달하며 ensure_setting → now → timezone의 순서를 유지했다. 호출 표면의 세 임시 함수는 이 연결만 수행하고 정책 본문을 복제하지 않는다. World/Package scope의 기존 네 함수는 C3c에서 실제 역할 분리 후 제거하기 위해 원문을 남겼다.

기존 집중 묶음은 **182 passed / 기존 PG 1 skip / 기존 warnings 5 / 34.92초**다. 새 file SQLite 검증은 처음 설정 생성의 commit 이후 scope 읽기, 기존 설정의 uncommitted 변경/observer 격리/rollback, unsupported action·non-policy 세션의 scope 조회 이전 guard를 검증한다. API/ORM/frozen/test assertions는 그대로 보존한다.

C3b 최종 후보 검증은 **467 passed / 기존 PG 1 skip / 기존 warnings 5 / 156.24초**다. 신규 실제 SQLite 3 nodes와 영향 범위 검증은 **99 passed / 기존 PG 1 skip / 기존 warnings 2 / 22.71초**였으며 설정 commit/동일 Session/격리/rollback과 조회 이전 guard를 확인했다. 원래 실제 함수 10개의 AST는 명시한 timezone reader 전달만 원래 호출로 복원했을 때 차이 0이다. 경계는 **697 modules / 2,332 edges / exact legacy 221 / cycle 0**, L4 parity 97·ER0 81/87/24/44/7·Memory batch 현재 inventory도 통과했다.

읽기 전용 원래 보존 함수 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 기존 보호 **2,139 / 현재 2,236 nodes**다. 앞 단계와 동일하게 signed 최초 도입 두 blob만 메모리에 보충했으며 tracked frozen/checkpoint/additions와 검사 구현은 수정하지 않았다. 부모의 선형 도입 append 후 stock 전체 보존 검사와 통합 Actions/installer 검증은 남아 있다.


## AR-B4-C3c — World 범위 읽기·활성화 판단·실행 연결

World timezone의 fallback과 imported activation 판단은 `routines/service/activity_scope.py`, 실제 nullable get/has_table/두 scalar·join SQL은 `runtime/resident/activity_scope.py`가 소유한다. Attached read Protocol은 기존 ORM 객체를 그대로 전달하며 runtime activity_policy가 caller Session으로 조립한다. Inspector는 첫 table check에서 lazy 생성하므로 enabled WC의 조회 이전 반환과 timezone의 한 inspector 재사용을 유지한다. 이전 네 함수의 서로 다른 active/no-active 조건과 원래 character 확인 위치를 합치지 않았다.

모든 직접 소비자를 canonical 역할에 연결하고 옛 `services/agent_activity_policy.py`를 제거했다. 시간 상수만 쓰는 소비자는 tick_schedule, ActivityPolicy 값만 쓰는 소비자는 계약을 직접 참조한다. 원래 clock export/monkeypatch의 같은 객체와 runtime의 실제 permission construction은 유지한다. 실제 판단 4개 및 scalar/join SQL 2개의 AST는 정확 read 협력/인자 표현만 복원하면 차이 0이다.

신규 SQLite 3 nodes는 enabled WC가 DB transaction/statement를 만들지 않는 조건과 selected World 유무 두 경우의 미커밋 import registry를 검증한다. Caller의 activation guard는 새 기록을 읽고, 별도 observer는 보지 못하며 rollback 후 잠금이 해제된다. 기존 테스트와 함께 **308 passed / 기존 PG 1 skip / 기존 warnings 3 / 111.01초**다. 최종 경계·보존 검사와 부모 선형 source introduction/통합 Actions는 이어서 기록한다.

C3c 최종 확장 검증은 **544 passed / 기존 PG 1 skip / 기존 warnings 5 / 421.71초**다. 경계 **700 modules / 2,340 edges / exact legacy 211 / cycle 0**, L4 parity 97·ER0 81/87/24/44/7·Memory batch 현재 inventory도 통과했다. 읽기 전용 보존 진단에서 split/assertion/suppression/API·ORM/node는 각각 오류 0(보호 2,139 / 현재 2,239)이었고, source 검사는 삭제된 옛 activity-policy 파일의 대표 목적지 한 항목 누락을 잡았다. 전체 symbol 분할 증거는 이미 모두 존재하므로 대표 file map을 실제 canonical activity-policy 서비스로 연결했다. 제품 코드·테스트·frozen 자료·검사 predicate는 수정하지 않았다.

대표 file map 정정 후 영향을 받는 원래 source/assertion/suppression 함수만 다시 실행하여 **각각 오류 0**을 확인했다. 직전 동일 코드의 split/API·ORM/node 오류 0과 함께 C3c 지역 보존 진단을 닫는다. 부모의 선형 source introduction append 후 stock 전체 보존 검사·Actions·installer는 여전히 별도 완료 조건이다.


## AR-B4-C4a — Run·PublicAction·FeedCue 실제 저장 책임

Run create/finish/post 연결 및 public execution create/finish, FeedCue create/consume를 각각 자기 service로 이전했다. 실제 Run 조회 6개·signature 조회·pending cue 조회는 repository가 소유한다. 원래 AgentRunConflictError와 active status 값도 한 정의로 옮겼다. FeedCue의 외부 객체는 identity-only Protocol을 통해 같은 attached 객체를 그대로 읽으며 별도 domain ORM 의존이나 값 복제를 만들지 않는다. 기존 실제 함수·class·값 **17개 AST 차이 0**이며 FeedCue의 두 타입 표기만 원문으로 복원해 비교했다.

기존 직접 소비자와 11개 monkeypatch의 대상 모듈을 실제 역할에 연결하고 원래 CRUD 함수 본문은 제거했다. 테스트의 callback/assertion/parameter/skip은 그대로다. 첫 집중 검증은 **382 passed / 기존 PG 1 skip / 기존 warnings 4 / 28.14초**다. 새 실제 SQLite 3 nodes는 run 생성 commit/중복 실패 rollback·원래 error cause, public execution 생성/완료의 deferred flush/observer 격리·rollback, FeedCue 생성·소비의 commit와 미존재 no-write를 검증한다. 새 검증과 기존 영향 node 묶음은 **12 passed / 12.60초**다.

Slot Character row lock·claim·nested transaction·만료 복구는 C4b, Relationships 후보와 Daypart Memory는 각 소유 source와 별도로 합류한다. Social의 get_execution/set_social_event_id는 같은 서비스의 겹치지 않는 두 함수로 parent 통합 때 보존한다. 현재 단계는 actual persistence 전환이며 전체 resident 실행이나 B4 완료를 표시하지 않는다.

C4a 최종 후보는 **481 passed / 기존 PG 1 skip / 기존 warnings 5 / 151.53초**다. 경계 **707 modules / 2,368 edges / exact legacy 211 / cycle 0**, L4 parity 97·ER0 81/87/24/44/7·Memory batch 현재 inventory도 통과했다. 원래 보존 함수의 읽기 전용 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 기존 보호 **2,139 / 현재 2,242 nodes**다. 동일한 선행 signed 두 경로만 메모리에 보충했으며 tracked source additions/checkpoint/frozen 자료와 검사 구현은 변경하지 않았다. 부모 선형 도입 append 후 stock 전체 보존 및 통합 Actions·installer는 여전히 별도 조건이다.


## AR-B4-C4b1 — Slot pool·복구·반납·lease 실제 소유

외부 ORM을 읽지 않는 슬롯 lifecycle 10개와 실제 query 3개, 원래 상수 12개를 Routines의 역할별 파일로 옮겼다. Pool/state/recovery/assignment release/lease 서비스를 분리하고 assigned/list/active 조회는 repository가 소유한다. **25개 실제 definition의 AST 차이 0**으로 원래 query·with_for_update·skip_locked·commit/rollback/refresh·오류·시간 의미를 유지했다. 기존 SQLite 실제 수동 슬롯 복구·자동 예약·소유자·종료·credential 영향 테스트를 사용하며 새 assertion을 대신 만들어 기준을 바꾸지 않았다.

초기 집중 검증은 **105 passed / 기존 PostgreSQL 전용 18 skip / 기존 warnings 3 / 35.02초**다. PostgreSQL concurrency가 실행됐다고 표시하지 않으며 통합 CI에서 별도로 검증한다. Character/WC를 읽는 배정·선점 네 함수는 원래 CRUD에서 실제 구현을 유지한 채 C4b2로 이어진다.

직접 제품 호출자는 canonical 역할을 사용한다. 기존 activity_limits의 몇몇 assertion은 get_assigned_slot과 서로 다른 업무 조회를 같은 agent_crud 이름으로 검사하므로, 해당 get_assigned_slot 한 개만 원래 파일에서 **동일 repository 함수 객체**로 export한다. 기존 assertion/guard를 변경하거나 새로운 가짜 구현을 만들지 않았다. 정확한 test-only 소비자·bridge·B8-A 종료 조건을 지도와 scope에 기록했으며 이 경로의 폐기를 완료라고 선언하지 않는다.

C4b1 최종 후보 검증은 **415 passed / 기존 19 skip / 기존 warnings 3 / 144.61초**다. Skip은 PostgreSQL 전용 18개와 기존 RoutinePost PostgreSQL 1개이며 실제 PG 동시성 결과를 대신하지 않는다. 경계 **713 modules / 2,395 edges / exact legacy 211 / cycle 0**, L4 parity 97·ER0 84/87/24/44/7·Memory batch 현재 inventory도 통과했다. 실제 SQL이 역할별 파일로 이동하면서 현재 PostgreSQL inventory 파일 수만 81에서 84로 바뀌었고 frozen 원문은 변경하지 않았다.

읽기 전용 보존 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 기존 보호 **2,139 / 현재 2,242 nodes**다. 선행 signed 최초 도입 두 경로만 메모리에 보충했으며 tracked additions/checkpoint/frozen 자료와 검사 구현은 수정하지 않았다. 부모 선형 도입 append 후 stock 전체 검사·Actions·installer 및 C4b2 이후 실행 전환은 남아 있다.


## AR-B4-C4b2 — Slot 배정·선점 실제 정책과 같은 세션 조회

배정/임시 claim과 assigned/due claim 실제 네 함수는 Routines 서비스, 원래 Character 잠금·nullable get 및 correlated WC owner-controlled predicate는 같은 Session의 runtime 협력으로 분리했다. 네 실제 함수 AST는 한정된 조회 다섯 위치를 복원하면 동일하며 세 SQL AST도 같은 class/Session/인자 연결을 적용하면 차이 0이다. Empty allowed set → single-flight → own/owner-control 조건 → ordered/limited/skip-locked 후보 → Character 상태·중복·count 제한 → 상태 변경 → commit/refresh 순서를 유지한다. 임시 hash token, persistent nested transaction replay 및 실패 rollback은 합치지 않았다.

원래 signature의 runtime 표면은 조회 협력을 구성하며 constructor에서 IO를 수행하지 않는다. 기존 직접 소비자는 이 실제 경로로 전환했고 Slot 상수만 사용하던 네 테스트의 local import 이름은 canonical constants에 연결하여 assertion AST를 그대로 유지했다. 옛 CRUD의 Slot 상수와 Run conflict error export는 실제 소비자를 모두 옮긴 뒤 제거했다. 다른 Identity/Relationships 업무의 원문과 기존 get_assigned_slot 테스트용 한정 bridge는 남은 소유 전환으로 명시한다.

신규 실제 SQLite 3 nodes는 slot pool write 뒤 같은 caller Session의 Character lock, explicit commit 유무에 따른 observer 가시성과 rollback, 빈 대상에서 query/transaction이 시작되지 않는 조건을 검증한다. 기존 집중 묶음과 함께 **108 passed / 기존 PostgreSQL 18 skip / 기존 warnings 3 / 42.88초**다. 최종 경계/보존 검증과 부모 선형 도입 append 후 stock·Actions·installer 검증은 별도로 이어간다.

C4b2 최종 확대 검증은 **424 passed / 기존 19 skip / 기존 warnings 3 / 166.39초**다. 경계 **717 modules / 2,406 edges / exact legacy 209 / cycle 0**, L4 parity 97·ER0 85/87/24/44/7·Memory batch 현재 inventory는 통과했다. 읽기 전용 원래 보존 함수의 source/assertion/suppression/API·ORM/node는 **각각 오류 0**, 보호 **2,139 / 현재 2,245 nodes**다. Split 검사는 옛 RunConflictError export 제거 뒤 실제 소비자를 누락한 세 지도 항목을 잡았고, 실제 `routines/service/runs.py`와 `services/agent_runs.py` 소비자를 정확 기록한 뒤 원래 split 검사를 다시 실행해 **오류 0**을 확인했다. 제품·테스트·검사 구현·frozen 자료는 이 보완에서 변경하지 않았다.

Signed 선행 두 경로를 메모리로만 보충하는 동일 지역 진단이며 source introduction metadata는 부모가 선형 append한다. Stock 전체 보존·PostgreSQL CI·installer 및 전체 B4 완료는 별도 조건으로 남겨 둔다.


## AR-B4-C5a — Run 과부하 이력·재시도 시각 정책

실패 문자열/저장 결과의 분류와 재시도 시각은 Routines `service/run_backoff.py`, 자기 Run의 실제 이력 SQL은 `repository/run_backoff.py`, frozen 결정 값은 `contracts/backoff.py`로 이전했다. 실제 정의 9개와 SQL은 한정된 repository 호출을 복원하면 AST 차이 0이다. Character/credential OR, 2시간 구간의 경계, created/id 정렬·limit30·lazy scalar/autoflush 및 rate limit45/overload10·30/timeout10분 의미를 유지했다.

기존 langgraph 검증의 과부하 7 nodes와 helper를 `tests/routines/test_run_backoff.py`로 이전했고 원래 테스트 본문 AST 8개가 모두 동일하다. 새 file SQLite 회귀는 caller의 미커밋 Run 실패 결과 조회·observer 격리·rollback 후 원래 판단 복원을 검증한다. 전체 214개 원래 AgentRun 정의를 검사하는 기존 AR-B2-B5의 완전 source map에 실제 목적지와 추출된 query member를 갱신했으며 중복 전체 지도를 새 단계마다 복사하지 않는다. Frozen/checkpoint/additions와 검사 구현은 유지한다.

C5a 기존 영향 범위와 신규 회귀는 **293 passed / 기존 PG 1 skip / 기존 warnings 2 / 25.08초**, 현재 목록·OSS 경계·실행 조립 추가 검증은 **35 passed / 기존 warning 1 / 44.15초**다. 경계 **720 modules / 2,412 edges / exact legacy 209 / cycle 0**, L4 parity97·ER0 85/87/24/44/7·Memory batch 현재 inventory도 통과했다. 읽기 전용 원래 보존 진단의 **source/split/assertion/suppression/API·ORM/node 모두 오류 0**, 기존 보호 **2,139 / 현재 2,246 nodes**다. 선행 signed 두 경로만 메모리에 보충했으며 tracked frozen/checkpoint/additions·검사 구현을 수정하지 않았다. 부모 선형 introduction append 후 stock 전체·CI·installer는 별도 완료 조건이다.


## AR-B4-C5b — 읽기 전용 단계 재시도·실행 오류 소유

읽기 전용 retry loop와 분류·진단 9함수 및 설정 6개는 `runtime/resident/read_only_lanes.py`, Run/Slot 기본 오류와 retry/deferred 오류 4개는 Routines의 실제 exceptions 정의로 이전했다. 원래 19개 정의와 기존 retry 테스트 8개 본문 AST는 모두 동일하다. Provider gateway error 객체, logger category, redaction, metadata 갱신 순서, 원인 연결, 재시도 상한·지연·first_error·attempt_errors를 유지한다.

기존 retry 테스트는 `tests/routines/test_read_only_lanes.py`로 assertion/raises/monkeypatch 그대로 이전했다. 취소와 영구 오류의 원객체 전달·호출1회·sleep0을 검증하는 새 2 parameter nodes를 추가했다. 기존 `tests/characters/test_creator_http_errors.py`가 Run 기본 오류의 identity와 Slot 오류 parameterization을 사용하므로 runtime contract의 두 이름은 실제 Routines class 재export만 유지한다. 새 조사용 identity 중복 case는 영구 테스트로 고정하지 않고 외부 read-only probe로만 확인하며 기존 Character 회귀를 계속 보존한다.

교차 도메인의 HTTP 오류 처리는 `routines/contracts/execution_errors.py`의 명시적 두 오류 계약을 사용한다. 실제 정의는 `routines/exceptions.py`의 한 객체이며, Character router와 현재 runtime 계약만 이 지원 표면을 통해 사용한다. 기존 service/schema/contract 경계 검사에 예외를 추가하지 않는다.

C5b 최종 현재 후보는 **406 passed / 기존 PostgreSQL 1 skip / 기존 warnings 6 / 61.65초**다. 경계 **722 modules / 2,418 edges / exact legacy 209 / cycle 0**, L4 parity97·ER0 85/87/24/44/7·Memory batch 현재 inventory도 통과했다. 읽기 전용 원래 보존 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 보호 **2,139 / 현재 2,248 nodes**다. Signed 최초 도입 두 경로만 메모리에 보충했으며 tracked source additions·checkpoint·frozen 자료와 검사 구현은 변경하지 않았다. 부모 선형 도입 append 후 stock 전체·통합 CI·installer는 별도 완료 조건이다.


## AR-B4-C5c — Run 결과 정제·사용량·snapshot 실제 소유

결과 정제·사용량 집계·저장 실제 11함수는 Routines service/run_results.py, 반복 nullable Run 조회는 자기 repository/runs.py로 이전했다. 한정된 두 query 호출을 복원하면 원문 11함수 AST가 같고, 기존 결과 테스트 7개 본문 AST도 동일하다. 허용 필드, error1500 제한, perCall/scope/token 집계, writing lanes, redaction→merge 저장 순서와 원래 commit을 유지한다.

새 SQLite 3 nodes는 caller의 대기 중 결과를 포함한 snapshot commit·입력 불변, 없는 Run에서 다른 대기 변경을 commit하지 않는 조건·rollback, attached writing lanes 조회의 no-commit·rollback을 검증한다. 기존 영향 묶음과 **256 passed / 기존 warnings2 / 26.63초**를 확인했다. Memory/B5 branch ancestry는 병합하지 않고 기존 Daypart 책임은 B7 소유 후속으로 유지했다. 현재 목록·원래 보존 검사와 부모 선형 도입 append 이후 stock 전체 검증은 다음 조건이다.

C5c 미커밋 소비자 검토에서 자동 추출의 import 삽입 기준 누락으로 다섯 전역 이름이 연결되지 않은 것을 발견했다. 격리 서비스 검증만으로 실행 본문의 미호출 경로까지 보장할 수 없음을 확인하고 정확 import를 연결했다. Community·individual flow·resident slot 세 실제 실행 함수 및 중첩 code의 LOAD_GLOBAL 의존이 실제 모듈/builtins에 모두 존재하는 영구 회귀 3 nodes를 추가했다. 이 구조 회귀는 실제 provider 성공 경로의 대체 증거가 아니며 기존 실행·기능 검사를 계속 유지한다. 최종 검증은 이 보완 뒤 고정된 후보를 사용한다.

C5c 보완 후 최종 현재 후보는 **422 passed / 기존 PostgreSQL 1 skip / 기존 warnings5 / 81.27초**다. 실제 세 실행 함수의 copied namespace에서 누락 import 다섯 개를 제거한 읽기 전용 음성 대조는 다섯 의존을 모두 검출했다. 경계 **723 modules / 2,421 edges / exact legacy209 / cycle0**, L4 parity97·ER0 85/87/24/44/7·Memory batch 현재 inventory를 유지한다. 원래 보존 함수의 읽기 전용 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류0**, 보호 **2,139 / 현재2,254 nodes**다. 선행 signed 두 경로의 메모리 보충만 사용했으며 tracked frozen/checkpoint/additions·검사 구현은 변경하지 않았다. ER0의 역사적 `<82` 개수 assertion은 현재 파일 분할 수와의 구분을 부모가 별도 검토 중이며 stock 전체·CI·installer를 통과했다고 표시하지 않는다.
