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
| AR-G4 | NOT STARTED | Alembic 물리 경로·역사 본문 보존 |
| AR-B2 | NOT STARTED | identity→characters→worlds→world_characters |
| AR-B3 | NOT STARTED | World Package→media |
| AR-B4 | NOT STARTED | routines→routine_posts→활동 조립 |
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
