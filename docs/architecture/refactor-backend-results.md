# 백엔드 구조 전환 실행 결과

## 범위와 현재 상태

2026-09-05에 §8.2 AR-G0부터 AR-B8-B까지 실행을 시작했다. 사용자 검증·PR·merge는 이번 실행에서 위임받은 권한으로 수행하며, 각 검증은 실제 수행한 범위와 commit을 기록한다. Release/Production, §8.3 프론트엔드 이전, AR-X와 P8-L-S 실제 AI 품질·인과 검증은 별도 범위다.

출발점은 #263 merge `d7037625a19071eb279ad2ea35c3ace6fe5b5289`, tree `35ded40a2b5fd33d1a54dac3a396e72d24c88714`다. 원격 main과 로컬 HEAD가 일치하고 시작 시 작업 트리는 깨끗했다. 원본 #258 기준과 승인 public test 목록, frozen migration 자료는 계속 보존한다.

| 단계 | 상태 | 범위 |
| --- | --- | --- |
| AR-G0 | PR #265 MERGED · PR CI/POST-MERGE PASS | 후속 체크포인트·부분 scope·단계/소유권·Actions 연결 |
| AR-G1 | PR #266 MERGED · PR CI/POST-MERGE PASS | 설정·개발 환경 경로 |
| AR-G2 | PR #267 및 보안 Hotfix #272 MERGED · Hotfix POST-MERGE PASS | 원래 Security 실패는 역사로 유지하며 후속 수정 검증 완료 |
| AR-G3 | PR #268 MERGED · PR CI/POST-MERGE PASS | logging.ini·초기화·배포 자원 연결 |
| AR-G4 | PR #269 CI 진행 | Alembic 물리 경로·역사 본문 보존; G5 최종 모델 등록 연결 대기 |
| AR-B2 | #270~#276 순차 PR CI · WC workflow LOCAL VERIFIED | Identity·Characters·Worlds·WC 기반 후 profile/setup/lifecycle 통합 및 기존 Package race 수정 |
| AR-B3 | NOT STARTED | World Package→media |
| AR-B4 | CORE PR #281 MERGED · RESIDENT/C7/WRITER FOLLOWUP SOURCE COMPLETE · PR FULL CI PENDING | C7-H까지 실제 소유 합류; local full의 route inventory 1실패를 metadata만 수정하고 focused78 PASS; stock2311 PASS, 최종 PR 전체 CI 대기 |
| AR-B5 | NOT STARTED | social→relationships→projection |

| AR-B4 | ROUTINES A1/A2/A3a/b LOCAL VERIFIED · INTEGRATION/PR PENDING | 실제 계획·guarded lifecycle·실행 claim 이전; joint·routine_posts·resident 후속 |
| AR-B5 | SOURCE PREPARED · INTEGRATION PENDING | Social→Relationships→projection 실제 소유·Community/public 집합 제거 및 G07 18파일 준비. 전체 통합/Hosted는 부모 단계에서 검증 |
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

### Identity PR의 토큰 HMAC 경고와 호환 검증

G4 선행 main merge `d01787b`까지 병합 후 전체 post-merge가 통과했다. Installer `33967365530`의 build·clean·지원 버전 직접 업데이트·실패 복구·aggregate가 모두 SUCCESS이며 22:22:02 KST 종료했다. Identity PR #270의 G4 계보 후보 `86d372e`는 일반 회귀를 통과했지만 CodeQL check `101310868679`가 가입 토큰의 HMAC을 비밀번호용 SHA256 해시로 표시했다. 원래 #263 `app/services/auth.py`와 이동 후보의 key 생성·서명·검증·JTI digest 함수 네 개 AST는 동일하다.

실제 데이터는 서버 app_secret에서 context를 분리한 MAC key와 Google sub/email/만료/random JTI이며 사용자 비밀번호 저장은 `core/security.py`의 PBKDF2를 유지한다. 경고를 무시하거나 검사 설정을 줄이지 않았다. 네 one-shot HMAC을 Python 공식 동등 API인 `hmac.digest(key, message, "sha256")`와 필요 시 `.hex()`로 명시하여 목적을 분명히 했다. [Python HMAC 문서](https://docs.python.org/3/library/hmac.html#hmac.digest). 기존 토큰 일회성 소비 테스트에는 이전 HMAC 생성 API로 독립 계산한 key·서명·JTI digest 바이트의 일치도 추가했다. 기존 assertion을 제거하지 않았다.

고정 source `bac98ec321e854c866fa842522b82bbbbb346346`에서 정책/Google 가입·browser cookie 보안 **19 passed / 5.23초**, 전체 보존 **2,085 protected/current nodes / items37 PASS**다. 서명 형식·compare_digest·만료·일회성 grant·DB/KDF 계약은 유지하며 새 CodeQL 및 전체 PR-head CI 결과는 별도로 확인한다. 문법 변경이 검사 통과를 보장한다고 미리 판정하지 않는다.

후속 CodeQL의 상세 alert #14는 verified Google ID-token의 `sub`/`email` 추출과 `google_identity.verify_id_token` 반환을 password source로 분류했다. 실제 sink는 해당 공개 식별 정보를 포함하는 토큰의 keyed MAC이며 사용자 비밀번호 저장이 아니다. byte 호환·비밀번호 PBKDF2 유지·원래 #263 AST 근거를 첨부하여 **이 alert 한 건만 false positive로 review/dismiss**했다. query·workflow·심각도·scanner 제외 규칙은 바꾸지 않았다. 이 기록은 검사 자체를 끈 PASS가 아니며 후속 동일 후보의 검사를 다시 확인한다. HMAC import 제거와 줄 변경으로 생긴 current import/SQL inventory drift도 생성기로 맞췄다. Frozen 계약은 유지한다.

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
### WC workflow 통합 검증과 보존 검사 성능

고정 제품 source `0c9deff`에서 WC·World·Package replay/UoW·활동 회귀 **178 passed / 6 warnings / 53.93초**를 통과했다. API module inventory의 기존 profile 7개도 실제 canonical module로 연결했으며 권한과 HTTP 계약은 유지했다. CI 계약 7개 및 architecture **626/2003/legacy281**, source archive Gitleaks **19.14MB**, 전체 HEAD 조상 **353 commits/21.27MB**는 PASS/findings0이다.

전체 보존 검사 중 명시적 경로 쌍이 526개로 늘면서 Python 정규식 캐시 한도를 넘겨 같은 표현식을 반복 컴파일하는 CPU 병목을 확인했다. 진행 중이던 검사는 중단했고 완료로 기록하지 않았다. `_compiled_path_literals`는 완전한 순서 있는 경로 튜플만 키로 사용해 정규식 컴파일을 최대 8종 재사용한다. 실제 source·assertion·테스트 수집·Git 증거는 캐시하지 않고 경계식·치환 순서·예외·기준선은 그대로 유지한다. 실제 frozen assertion 64개와 순서/부분 경로/숫자/오류 24개 비교는 AST가 모두 같았고 3.885초→0.099초였다. 기존 guard 회귀 **149 passed / 1.74초**를 통과했다. 신규 파일/test node는 없으며 전체 계보 검증은 이 수정이 포함된 고정 후보로 다시 실행한다.
### WC workflow 고정 후보 보존 완료

source `36fd4748cb55744d3effbcfb9d18eb921e0fd8d9`의 기본 전체 검사 `check_refactor_preservation.py --contracts --nodes`가 **protected/current 2,137 / items37 PASS**로 종료했다. #258/#263 API·OpenAPI·ORM·frozen source·assertion/suppression 및 원본 commit별 신규 source/node 계보를 그대로 검사했다. 앞선 오래 실행한 미완료 검사는 이 고정 후보의 stock 검사 결과로 대체하며, 결과 캐시나 검사 생략은 없다. 실제 WC entry/setup HTTP·readiness·혼합 cleanup 종료는 다음 최종 slice이며 workflow의 로컬 PASS를 AR-B2 전체 완료로 확대하지 않는다.

### WC workflow Hosted CI의 현재 구조 검사 정합성 수정

첫 PR #277의 Core/architecture/Local autonomy 검사가 기존 경로를 계속 기대하던 세 테스트를 발견했다. 비밀 키 reveal 위치는 WC `client.py`, 실제 setup 함수는 `service/autonomous_setup.py`, Local Smoke 필수 실행 파일은 WC 소유 setup/owner identity 테스트로 맞췄다. allowlist 함수 집합·실제 함수 존재·필수 suite 존재 assertion을 유지한다. 해당 실패는 기능 검사 삭제로 해결하지 않았다.

경로 결합식 assertion도 같은 원본/목적 파일임을 확인하도록 후속 Package에서 이미 검토한 strict literal-path 검사 구현을 기존 checker 파일에 먼저 반영했다. 원본 constructor·단일 binding·shadowing·전체 파일 경로만 인정하며 부분 prefix나 임의 호출을 허용하지 않는다. 검사 구현은 Package `cc95b50` Git blob과 동일하고 CRLF만 정규화하여 대조했다. 기존 guard와 위 current 검사 **168 passed / 10.69초**, 같은 checker의 Package 고정 테스트 source에서 literal/path/initializer 관련 **33 passed / 34 deselected / 0.30초**다. 신규 회귀의 최초 도입 source/node 계보는 원래 순서인 Package PR에 유지하고 앞선 기록에 삽입하지 않았다.

고정 source `f88c2af55f27be8777e7624208ff2e42e654c10a`의 stock 전체 보존은 **2,137 protected/current nodes / items37 PASS**다. 기존 checkpoint·source·assertion·API/ORM을 유지하고 현재 경로만 바로잡았다. 새 PR-head CI·Installer 결과를 다시 확인한다.

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

### WC 최종 후보의 보존·경계 검증 완료

응답 소유권을 수정한 source `77081dcd3e4e9c284ef415622b69d9004d9815fe`에서 readiness·Character HTTP·Agent 한도·M3 권한/비밀 보호 집중 **96 passed / 3 warnings / 14.03초**를 통과했다. 기존 split 증거의 목적지도 실제 Character schema로 연결한 `4f95df7`에서 stock `check_refactor_preservation.py --contracts --nodes`가 **2,139 protected/current nodes / items37 PASS**로 종료했다. API·OpenAPI·ORM, 원본 assertion/suppression, source와 새 test의 최초 도입 commit 계보를 모두 유지한다. 수정 전 검사의 stale split destination 실패는 이 조정과 재검증으로 닫았으며 기준선·기대 결과를 재생성하지 않았다.

동일 코드의 문서 통합 후보 `aa4f51e`에서 CI 계약 7개와 architecture **630 modules / 2,019 edges / exact legacy 272**, current inventory/public196을 확인했다. 추적 archive **19.17MB** 및 HEAD의 전체 조상 **360 commits / 21.33MB** Gitleaks는 findings0이다. 이 기록 뒤의 변경은 결과 문서뿐이다. PR #277 뒤의 순차 PR·merge·post-merge 및 실제 Installer 검증을 별도로 확인한다. WC의 미전환 외부 aggregate/ORM 소비자와 frozen migration용 동일 객체 alias는 B4~B8/G5의 명시된 범위에 남으며 이 로컬 결과를 B2 전체 완료로 확대하지 않는다.



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

### Package 선형 통합과 전체 백엔드 보존 완료

Worlds·Character·WC의 실제 소유 서비스를 runtime UoW/seed/import/export/preview 조회에서 사용하도록 연결했다. 선행 WC의 동시 replay Hotfix `1666c495`는 이동한 `runtime/world_packages/seed_uow.py`에서 비-import AST 전체가 동일하다. 기존 관찰용 테스트도 실제 registry repository의 같은 Session을 보도록 연결했다. 원래 replay 결과·rollback·digest 충돌·중복 생성 방지 assertion을 유지했으며 집중 **99 passed / 1 warning / 46.12초**다.

source `d80e2ed`·`3205878` 및 guard `dc3da4b`·`651bded`·`1fb943d`, 조립 `a61a0ae`를 선형 introduction 기록에 추가했다. 컴파일 캐시 source `f61cc48`는 새로운 파일/node가 없어 별도 추가 snapshot을 만들지 않았다. `ed89fde`의 stock 전체 보존은 **2,175 protected/current nodes / items37 PASS**다. 첫 검사의 split behavior-test 참조 27개는 모두 원본 Package import test의 이동 전 경로였으며, 기존 source/symbol map을 유지하고 실제 `tests/world_packages/test_import_commit.py`의 같은 node로 연결한 뒤 통과했다.

WC current 구조 검사 보완을 합친 고정 source `1f74549`의 **전체 백엔드 2,153 passed / 기존 22 skipped / 27 warnings / 481.15초**가 통과했다. API·OpenAPI·ORM, JSON v1·deterministic ZIP·미디어 staging/복구·caller transaction·기존 기능의 보존 검사를 유지한다. current architecture **631/2028/legacy272**, public196 및 ER0/L4/Memory batch 현재 경로 검사를 앞선 통합에서 확인했다. 추적 archive **19.30MB**, HEAD 전체 **371 commits / 21.69MB** Gitleaks findings0이다. 이 source 이후 final WC 결과 합류는 문서 한 파일뿐이다.

Package의 application/domain/infrastructure/ports/public.py 생산 구현은 실제 역할 파일로 이전했고, 같은 업무의 불필요한 전달 계층은 제거했다. G5의 등록을 위한 원래 aggregate ORM 소비자는 그 종료 조건으로 추적한다. Media provider/Character·World 이미지 업무 전체는 다음 PR 범위다. 선행 #278 다음 순차 PR-head Actions·실제 Installer·merge·post-merge를 확인하며 이 로컬 결과만으로 §8.2 전체 종료를 선언하지 않는다.

### Package 준비 커밋의 DCO 보완과 보존된 원본 계보

PR #279의 DCO job `101316333023`은 원래 Package 준비 커밋 7개에 Signed-off-by가 없어 실패했다. CONTRIBUTING의 모든 human commit 자체 서명 규칙과 `check_dco.py`는 그대로 유지했다. 미병합 commit의 누락 trailer만 같은 author의 서명으로 보충하고, 후속 Git DAG의 parent와 additions 기록의 구조화된 `record.commit` 참조를 새 SHA로 연결했다. 원 author/committer/date, 7개 이외 메시지 byte, parent 순서와 merge topology는 그대로다.

| 원래 source commit | 서명 보완 후 같은 source commit |
| --- | --- |
| `1fb943d3cef9bfc2aed59406cfc69b188293aff6` | `0e7481added543ce52710c9c0b9e0e0894541c5e` |
| `320587830a054a2c0b05a354348ea14669f7dace` | `91ddee0caa053412599ca6503e1840ddbf608d1e` |
| `651bded4f3bd15d92043c008286e7307769c423f` | `9f7f4338cc128a870844db883fac8c4e710a8299` |
| `a61a0ae5c8a0d10b0bb5bdaf27e190cea7ffefa3` | `6e52d89644f5faa5e0732af1eb015f1ee5085c18` |
| `d80e2ed495f1388e58a693837ca5309e84d92c07` | `b07fa003f83002d086775d90fa3abbb8fc5072fb` |
| `dc3da4beba804b623ce8691ee9e754b16bb0663c` | `beca573986f5e2135f798334e54b5fbe3bc9c7fa` |
| `f61cc48d36c6c9134940671587306aabf173efbb` | `9779c059a8a8e69344526ba00edafd8d95bf0608` |

50개 old/new DAG commit을 구성한 최종 후보에서 전체 source/test blobs는 동일하다. 유일한 tree 차이는 기존 additions JSON의 commit 참조이며, tracked_files blob·test_nodes·assertion·suppression·기록 순서·원래 snapshot 내용은 보존했다. 원본 refs는 로컬 `refs/archive/ar-dco-20260905/`에 따로 보관했다. main `38229fa`와 #258/#263 및 동결 baseline/migration은 바꾸지 않았다. 이전 절의 source SHA는 서명 보완 전 실제 검증 기록이며 위와 같은 내용으로 이어진다.

기존 DCO checker는 Package 및 Media 후보 각각 PASS다. 별도 detached Media 후보 `252a8f02f1745cb19f2f7f6a94a60ed3f19c7842`의 stock 전체 보존은 **2,201 protected/current nodes / items37 PASS**이며, 실제 Git의 최초 source 도입·blob·assertion·append-only prefix·API·ORM까지 원래 검사로 통과했다. 별도 독립 검토에서도 각 후보의 기록과 parent/메시지/source 불변식을 확인했다. 새 source/test 의미가 없으므로 앞선 기능 회귀 증거를 유지하며 게시한 새 PR head의 DCO·전체 필수 checks·Installer는 다시 확인한다. 검사 예외·allowlist·DCO remediation 허용 규칙을 추가하지 않았다.

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

### Media 선형 통합 보존과 공개 PR 후보

Package의 실제 owner·같은 Session seed replay 복구와 WC readiness DTO 소유권을 합친 `5c93020186475cf7d175866e920f1e7a0a2ce2e4`는 Media·Character·World·Package·이미지 생성·권한/비밀 보호 집중 **280 passed / 3 warnings / 56.69초**다. 뒤따르는 통합은 선행 current 구조 테스트와 검증 문서·원래 source introduction 기록을 연결했다.

Media M1 `660651d`, M3 `baeaefb`, M4 `9a66655`, M5 `99fb396`, M6 `dd78da6`의 원래 source와 신규 **26개 node**를 고정 commit에서 추출했다. M2 `ea4a7f4`는 기존 파일의 명시 이동이며 새 source/node가 없어 중복 snapshot을 추가하지 않았다. 최종 고정 `e9ffdb83bbebdb784b9c7ebc6ffea1b0bb517cf5`에서 stock 보존은 **2,201 protected/current nodes / items37 PASS**다. API·ORM·원본 test/assertion·symbol split과 최초 도입 계보를 모두 확인했다. 별도 현재 구조 회귀 **69 passed / 15.54초**, HEAD 전체 **381 commits / 21.90MB**, tracked archive **19.42MB** Gitleaks findings0이다.

공유 codec·path·quarantine은 integrations/media, Character·Social별 파일 저장은 각 owner service, Character 이미지 생성의 권한·quota·오류 처리와 HTTP는 해당 owner, World 이미지 변환/commit·rollback은 Worlds owner, SDK 통신/Azure 응답 변환은 integrations가 담당한다. 기존 quota·timeout·image limits·MIME·restore·provider call·usage lock 본문을 보존했다. Social mutation/job, profile_media의 test-only alias 및 사용하지 않는 URL helper, 전역 ORM 등록은 B5/B8/G5의 실제 종료 항목으로 추적한다. 이 PR로 backend 전체 전환 완료를 선언하지 않는다.


### AR-B7-A0 Memory 입출력·오류 기반 준비

기존 Memory 입출력 schema는 `schemas/__init__.py`, 배치 설정 입출력은 `schemas/batch.py`, 다섯 오류 class는 `exceptions.py`로 이전했다. 세 파일의 class 본문 AST는 import 경로를 제외하고 그대로이며 28개 실제 소비자를 연결했다. 기존 domain aggregate는 같은 오류 class를 제공한다. 입출력 검증, 버전·owner/World scope, batch consent/model/일정 필드와 extra-forbid 설정은 바꾸지 않는다.

전체 Memory 완료를 선언하지 않고 세 실제 역할 module만 partial scope로 추가했다. 미전환 Memory 서비스·repository·policy·HTTP의 정확 bridge 18개를 기록했다. Schema 두 module만 외부 entry이며 예외를 임의의 service entry로 올리지 않았다. 현재 architecture **640 modules / 2,087 internal edges / exact legacy 256 PASS**, L4 parity97 및 current Memory batch inventory를 갱신했다. Frozen predecessor inventory와 SQLite migration은 유지한다.

실제 write/recall/consolidation/selection 정책과 SQL·FTS·maintenance queue, batch admission·예약·종료·provider 및 HTTP 서비스 소유권은 다음 B7 범위다. 이 기반 source의 집중 검증·원본 도입 계보 통합·순차 PR/merge는 별도로 기록하며 기존 구현 전체가 이전됐다는 의미가 아니다.

Memory 기반 source `70b74395cb91f383c5f48a530af1cf2a173cb397`의 기존 write/recall inspector/consolidation/owner 제어·batch API/정책/안전·frozen inventory 집중은 **105 passed / 기존 2 warnings / 31.13초**다. 실제 Memory 정책과 SQL 구현은 이 세 파일 이동에서 바꾸지 않았다. 전체 source/node 계보는 선행 B4~B6와 함께 순차 통합하며 B7 전체 완료로 판정하지 않는다.

### AR-B7-A1 Memory 값·정책의 실제 소유권

source `67f5178c3ce5d2dcde41700f4ddd251c01300721`에서 owner/World/subject 범위·저장 항목·회상·retrieval plan·닫힌 source vocabulary는 `contracts/`의 실제 값 정의로, 유효기간·검증·정리 eligibility·provider 출력 검증·배치 일정과 선택 예산은 `policies/`의 실제 판단으로 배치했다. 13개 모듈의 함수/클래스 83개는 import 경로만 정규화하면 원래 AST 전체와 동일하다. 별도 forwarding service를 추가하지 않았다.

같은 고정 후보에서 `pytest -q tests -k 'memory or canonical_retrieval_planner or today_sns'`는 **190 passed / 2,011 deselected / 2 warnings / 67.41초**다. 이는 실제 기억 저장·회상·owner 제어·scope/CSRF·배치 consent·selection 실패·migration·Today SNS 회귀를 포함한다. 경계 **640 modules / 2,087 edges / legacy256**, ER0 **76/87/24/44/7**, L4 parity97 및 현재 Memory batch inventory를 확인했다. 원래 P8-L predecessor JSON과 migration 본문은 재생성하지 않았다. 이동하여 사라진 여덟 old consumer의 exact bridge는 제거하고 아직 전환 전인 실제 Memory consumer만 후속 B7/B8 제거 조건으로 기록했다.

이 단계는 값과 정책의 실제 배치다. SQL·FTS·queue repository, 저장/회상/정리 service, HTTP와 startup/shutdown 조립, 남은 domain/public aggregate 종료는 후속 B7 범위이며 전체 전환 완료로 표시하지 않는다. 최초 도입 기록은 선행 B4~B6 source와 선형 통합 후 고정 commit 기준으로 연결한다.

### AR-B7-A2 Memory 실제 업무 서비스와 사용 중인 협력 계약

고정 source `a131115`에서 실제 scope CAS/replay·item lifecycle·근거 검증·canonical recall·retrieval plan·consolidation·batch selection의 실행 본문을 `service/`에 배치했다. repository/source/provider/queue/transaction의 기존 typed 협력 계약은 `contracts/`에 두며 실제 repository·provider·worker·회귀 fake가 사용하는 계약만 승계한다. 18개 role 파일의 클래스·함수·메서드 **145개 AST가 import 연결만 정규화하면 원문과 동일**하다. 새 전달 service를 추가하거나 provider/DB 호출·commit·rollback 순서를 변경하지 않았다.

동일 source의 Memory·retrieval planner·Today SNS 회귀는 **190 passed / 2,011 deselected / 2 warnings / 54.73초**, 경계 **640/2087/legacy256**, L4 parity97·Memory batch·ER0 **76/87/24/44/7** PASS다. 이 단계에서 application/ports의 원래 파일을 실제 역할로 옮겼으며 공통 SQL 등록과 원래 source snapshot은 보존했다. `Port`가 붙은 기존 구조적 type 이름은 소비자/fake 호환을 위해 유지한다. SQL/FTS/queue 구현과 같은 Session의 외부 업무 조회, HTTP·runtime 조립 및 public/domain aggregate 제거는 다음 단계다.

### AR-B7-A3 Memory ORM 소유와 역사적 migration 연결

Source `7fcecd27fc155242819c3172357da1f8429f3dbf`에서 Memory ORM 13개와 기존 schema 생성 함수의 원문 AST를 유지하면서 `models/items.py`와 `models/batch.py`로 이전했다. 현재 소비자 22개를 연결했고, 고정 Alembic 0085/0089와 SQLite v4→v5/v8→v9의 본문은 변경하지 않았다. 역사적 두 import 경로는 필요한 상수·schema 함수 5개의 같은 객체만 export하며 ORM 구현을 중복하지 않는다.

동일 source의 Memory·retrieval planner·Today SNS·embedded data migration 회귀는 **213 passed / 1,988 deselected / 2 warnings / 102.96초**다. 현재 경계 **642/2089/legacy256**, L4 parity97, ER0 **76/87/24/44/7**과 현재 Memory batch inventory가 통과했다. 원본 API/ORM·기존 assertion·suppression·후속 source/node 계보 보존은 **protected/current 2,201 nodes / 37 items PASS**다. SQL 저장·동일 Session의 타 업무 조회·HTTP/runtime 연결은 다음 전환 대상이며 B7 전체 완료로 표시하지 않는다.

### AR-B7-A4 Memory 저장과 같은 Session의 scope 조회

고정 source `b285eb1db57abdd23ff8a2e24f279683c8b2a9f9`는 item/batch/consolidation/leased queue/activation의 실제 SQL 구현을 `repository/`로 이전한다. 사용자·World·WorldCharacter의 세 조회와 timezone 조회는 `runtime/memory/scope_queries.py`에서 원래 SQL과 호출자 Session을 유지하며, invalid-scope 및 timezone 판단은 Memory repository에 남는다. `composition.py`는 이 같은 Session을 사용하는 typed read 협력을 구성하며 독립 transaction이나 도메인의 runtime 역참조를 추가하지 않는다. 기존 소비자 13개는 실제 factory에 연결했고 원래 constructor-site 이름과 테스트 assertion은 유지했다.

기존 method/module **65개 AST**와 외부 조회 두 본문 AST가 같음을 확인했다. 신규 file SQLite 테스트 4개는 caller의 flush 가시성·observer 비노출·rollback 및 잘못된 owner/World/subject에서도 세 SQL의 원래 순서와 동일 오류를 확인한다. 집중 **33 passed / 19.17초**, Memory·Today SNS·embedded migration 확대 **217 passed / 1,988 deselected / 2 warnings / 111.69초**다. 현재 경계645/2095/legacy256·L4 parity97·ER0 76/87/24/44/7·현재 Memory batch inventory PASS다. Commit 직전 전체 보존은 **기존 2,201 protected / 현재 2,205 nodes / 37 items PASS**다. 신규 source 4개와 신규 test nodes 4개는 B4~B6 이후 순차 통합에서 이 source commit의 도입 증거를 append한다. B7 HTTP·worker 및 나머지 compatibility 종료는 아직 수행 중이다.

### AR-B7-A5 Memory owner 업무·HTTP·실행 조립

Source `17854b02cb5103e9c5a685be982159babe6758a9`에서 Memory HTTP10개는 `router.py`, 실제 설정·consent·pin·correction·delete와 commit/rollback은 `service/management.py`, inspector 표현은 `service/presentation.py`가 소유한다. 실제 서비스·repository를 필요한 시점에 만드는 같은 Session 협력과 profile/credential 조회는 상위 `runtime/memory_http.py`에 둔다. 두 앱 factory와 독립 HTTP fixture 모두 같은 builder를 등록한다. Identity 인증/CSRF는 기존 `api/identity_dependencies`의 동일 callable/object를 사용한다.

기존 HTTP의 10개 업무 본문을 명시적 DI/오류 변환 분리만 정규화하여 비교했고, parameter·decorator·response AST 및 presentation7함수 AST가 같다. API 집중20 PASS 뒤, 관련 profile 읽기가 실패하면 pin이 rollback되는 새 회귀1개를 포함해 **218 passed / 1,988 deselected / 2 warnings / 129.05초**를 확인했다. 경계가 처음 잡은 잘못된 직접 인증 import와 Chat/Memory package cycle은 기존 공통 HTTP 연결 및 패키지 위의 실제 조립으로 해소했으며 **650 modules / 2,122 edges / legacy256 PASS**다. L4 parity97, ER0 76/87/24/44/7, current batch inventory도 통과했다.

전체 보존 검사에서 API/ORM·원본 assertion·skip·split·node 손실은 없고 **기존 protected2,201/current2,206**이다. 검사 exit1은 앞선 A4에서 새로 commit한 source4개/node4개의 introduction capture를 B4~B6 순차 통합 뒤로 남긴 결과다. A5의 새 역할 파일과 새1node도 고정 source의 도입 기록으로 후속 capture하며 guard를 완화하지 않는다. 새 batch/provider 호출·기능 삭제·schema version 변경은 없다. Worker·source/projection·Daypart Memory와 마지막 public/aggregate 정리는 다음 범위다.


### AR-B7-A6 Memory source admission 저장

Source `8fa9871f81b8b2b534bdd77baae6243326e0a7c6`에서 실제 ON epoch 동기화 및 delivery 저장 두 함수는 `repository/delivery.py`로 옮겼다. 두 함수의 전체 AST와 동일 Connection·SQL·version/시간·dedupe를 유지한다. Runtime은 Social/Chat 이벤트를 해석하여 해당 저장을 호출하는 SQLAlchemy hook 조립을 담당한다. 기존 commit/rollback과 provider 호출은 추가하지 않았다.

배치 runtime·안전·owner 제어 **33 passed / 1 warning / 14.30초**, 경계 **651/2124/legacy256**, L4 parity97, ER0 76/87/24/44/7 및 current Memory batch inventory PASS다. 새 source1개는 이 고정 commit을 기준으로 후속 순차 capture한다.

### AR-B7-A7 Memory candidate 전달·배치 준비·brief 재생성

Source `e9f881ae4fea642c6c7b4a754fcfe71ac2ba3b7c`에서 `deliver_candidates`, `enqueue_scope`, `rebuild_briefs`의 실제 실행 본문은 `service/batch_preparation.py`가 소유한다. 같은 Session의 저장/원본 근거 조회 네 협력을 명시적으로 받아 기존 candidate 검증, thread별 묶음, byte/candidate 예산, queue 등록, hot brief의 현재 근거 검증과 dirty flag/commit 흐름을 유지한다. Worker는 실행·중지와 실제 협력 연결을 맡는다. 테스트의 기존 직접 호출은 test 지원 모듈에서 실제 runtime builder를 partial로 연결하며 원래 assertion은 유지한다.

세 실제 업무 본문은 명시 factory 주입만 역변환하면 원문 AST와 같다. 배치 runtime·안전·API·owner 제어 **41 passed / 2 warnings / 15.19초**, 경계 **654/2142/legacy256**, L4 parity97·ER0 76/87/24/44/7·current batch inventory PASS다. 새 역할 source와 test 지원 파일은 후속 선형 capture 대상으로 남기며 보호 기준을 재생성하지 않는다. 예약/종료 정책·외부 World join, source reconciliation·canonical recall·Daypart Memory의 실제 책임과 마지막 legacy bridge는 다음 범위다.


### AR-B7-A8 Memory 예약·종료 trigger 업무

Source `989cccadc2c36597311d6e112809a238304d6536`에서 consent·종료 cutoff 허가·날짜/시간대/예약·queue admission의 실제 흐름은 `service/batch_scheduling.py`가 소유한다. World timezone과 Memory 설정의 join은 같은 Session의 runtime query로 연결했다. 명시적 협력 추출을 다시 펼치면 전체 workflow와 join AST가 원문과 같고, 종료 허가 한 SQL·flush·조회 순서/limit·예외 시 scope 회전·commit과 provider-free 조건을 유지한다.

집중 **41 passed / 2 warnings / 14.51초**, 경계655/2155/legacy256·L4 parity97·ER0·current batch inventory PASS다. 전체 guard는 기존 API/ORM/assertions/node 손실 없이 protected2201/current2206을 확인했고, 새 source15개/node5개가 아직 선형 introduction capture 전인 점을 보고했다. 최초 A8 split 기록의 불완전한 symbol/test 목록 두 오류는 실제 전체 소유 목록·정확 test node로 보완했으며 원래 `check_split_evidence`를 다시 실행하여 **0 errors**다. 검사 구현과 frozen 기준을 이 보완에서 바꾸지 않았다.

### AR-B7-A9 Memory canonical recall 실제 조회·근거 재검증

Source `9133d7a709f473755aeff149281f80c6794ceefc`에서 실제 item/evidence SQL과 canonical 회상/projection record hydration은 `repository/recall.py`·`recall_records.py`가 소유한다. Query 검증·허용 연산 선택·결과 상태는 기존 Memory recall 서비스가 맡고, 저장소는 모든 projection 후보의 최신 scope·enabled·valid-time·digest·visibility·observation·block을 다시 검증한다. 실제 Character/World membership/block join은 `runtime/memory/recall_queries.py`, 같은 Session source reader 연결은 `recall_composition.py`로 명시했다. 옛 runtime SQL 구현 파일은 제거했고 현재 소비자를 실제 factory에 연결했다.

Read method 본문10개와 canonical helper10개, 외부 join·block SQL 본문은 명시된 factory/query 추출만 역변환하면 AST가 같다. 회상·retrieval planner·consolidation·inspector 집중 **44 passed / 1 warning / 19.10초**, 신규 SQLite 회귀2개를 포함한 canonical 묶음 **7 passed / 26.07초**다. 새 회귀는 Character summary의 caller flush가 같은 Session에서 보이고 observer에는 보이지 않는 점, 원본 Chat 내용을 그 Session 안에서 바꾸면 저장 digest와 달라져 문서가 제외되고 Session 종료 후 두 변경 모두 rollback되는 점을 확인한다. 경계659/2170/legacy256·L4 parity97·ER0 및 current/frozen-chained Memory inventory PASS다.

초기 파일 분류에서 ORM 기반 record hydration을 pure policies로 둔 오류는 경계 검사에서 발견하여 실제 저장 snapshot을 다루는 repository에 배치했다. 일반 pure 정책의 framework 금지 규칙과 외부 entry 허용을 완화하지 않았다. 전체 source/node 계보 capture·B4~B6 합류·최종 B7/백엔드 통합은 별도 진행 중이다.


### AR-B7-A10 Memory 원본 근거 판정의 실제 소유

Source `a0b72a97bbabfb1fc2a5d1055ac992fed6c5414d`에서 성공/공개/관찰/차단/active 참여자/주관적 선언/digest 판단의 실제 구현은 `memory/service/source_evidence.py`가 소유한다. 외부 Chat·Social·Relationships·Routines 원본 SQL은 `runtime/memory/source_queries.py`에서 기존 raw row/result를 같은 Session으로 읽고, `source_composition.py`가 둘을 연결한다. 옛 `runtime/memory/sqlalchemy_source_reader.py`는 제거하고 현재 소비자를 실제 factory로 전환했다. Subjective source의 lazy 조회 시점과 현재 응답 형태는 유지한다.

최종 가독성 formatting 이후에도 명시된 query 추출을 역변환하면 **13개 method 본문·16개 SQL 표현식·모든 digest/summary helper AST가 원문과 동일**하다. 기존 성공/노출/실제 관찰/수정·차단 판단, early return, 조회 결과 소비 순서, digest와 summary byte 범위, caller Session 및 commit/rollback 부재를 유지한다. 기존 write lifecycle/canonical recall/Today SNS와 같은 Session 신규 회귀를 포함한 집중 **41 passed / 81.05초**다.

경계 **662 modules / 2177 edges / exact legacy256 PASS**, L4 parity97·current Memory batch 및 frozen chained G/P inventory PASS다. ER0 현재 inventory가 실제 SQL 소유 파일 변경으로 stale인 점을 발견하여 현재 inventory만 재생성했고 **76/87/24/44/7 PASS**를 확인했다. Frozen migration/기능 계약/checkpoint JSON은 재생성하지 않았다.

이 source 고정 직전 stock 전체는 보호2,201/현재2,210 nodes와 API/ORM·assertion/suppression·split을 보존하고, 이미 준비한 새 source/node의 선형 introduction capture 대기만 보고했다. B4~B6 합류 및 실제 도입 commit의 append-only capture 전이므로 전체 B7/§8.2 종료는 아니다.

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


## AR-B5-B6 — 프로필·팔로우 업무 흐름

기존 Community의 실제 프로필 함수 17개와 페이지 크기 helper 1개를 `social/service/profiles.py`·`utils/limits.py`로 이전했다. 소유 Character 조회와 User 조회는 기존 nullable 결과를 반환하는 각 소유 서비스로 연결하고, Post·follow SQL은 이미 이전한 Social repository를 사용한다. 원래 함수 18개의 AST 본문은 import 대상과 읽기 계약의 타입 표기만 정규화했을 때 모두 같았다. 분기·조회·권한 확인·알림 생성·응답 순서는 변경하지 않았다.

새 `tests/social/test_profile_workflows.py`의 **2 nodes**는 실제 SQLite에서 팔로우 중복 요청의 동일 결과/알림 1개, 해제 상태와 caller rollback, 소유하지 않은 follower와 self-follow의 쓰기 전 거절, 없는 User 오류, 삭제된 Character의 기존 표시 가림과 신규 팔로우 거절을 검증한다. 기존 관련 회귀와 함께 **44 passed / 1 existing warning / 7.55s**다. 같은 Session과 deferred commit 동작을 유지하며 추가 provider 요청은 없다.

#258/#263 API·schema·ORM 차이 0, 기존 보호 테스트 변경 0, 전체 split evidence PASS다. 원래 AR-B2-B6의 전체 Community symbol 지도를 유지하면서 정확히 18개의 목적지를 갱신했다. 경계 검사는 **669 modules / 2,189 edges / 241 exact legacy edges**로 통과했다. 신규 source 도입 capture와 통합 Actions/PR/merge는 root의 후속 검증이며 전체 B5 완료를 의미하지 않는다.


## AR-B5-B7 — Feed 목록·Inbox 조회와 읽음 처리

Feed 목록·following의 실제 함수 4개, Inbox 업무 함수 4개를 Social service로 이전했다. 사용자 Inbox의 Character 소유 subquery와 Notification 조회 2개는 `runtime/social/inbox.py`에서 같은 Session·한 번의 SQL로 연결한다. 읽음 상태의 실제 대입·commit·refresh는 `service/notifications.py`가 소유한다. 원본 11개 함수의 본문은 소유 import/collaborator 이름을 정규화했을 때 동일하며 조건·정렬·cursor·오류·commit 순서도 같다.

신규 `tests/social/test_inbox_workflows.py`의 **3 nodes**는 한 번의 owner subquery·삭제/다른 owner 제외·cursor/잘못된 cursor의 기존 처리, 없는 대상의 쓰기 전 차단, 원래 명시적 read commit이 같은 Session의 미저장 변경까지 확정하는 계약, Character inbox의 명시적 recipient OR 범위를 검증한다. 첫 집중 실행은 **56 passed / 1 failed**였다. 실패는 Feed helper의 monkeypatch가 옛 module을 대상으로 한 경우였으며 실제 새 소유 함수로 옮겼고 assertion은 변경하지 않았다.

수정 후 **57 passed / 1 existing warning / 13.63s**, #258/#263 API·schema·ORM 차이 0, 변경 보호 테스트 1개 파일의 assertion PASS, 전체 split evidence PASS다. 원래 Community CRUD/서비스 전체 symbol 지도를 갱신하고 새로운 source/test capture는 root가 순차 수행한다. Today·검색·agent/resident·미디어 job, Relationships/projection과 최종 HTTP·호환 소비자 종료는 아직 B5 잔여다.


## AR-B5-B8 — 기본 검색·Today 집계와 순위

검색 입력/공개 응답·Today 점수와 정렬은 Social discovery service로, Character 자체 검색 SQL은 Character service로 이전했다. Post/Character 검색과 Character/AgentActivityLog 집계는 기존 SQL 그대로 runtime query가 소유한다. 인기 root Post의 SQL은 Social repository로 추출하고 공통 LIKE helper 2개는 core/search_text.py로 옮겼다. 새 공유 정의를 만드는 과정에서 같은 함수를 도메인마다 복제하지 않았다.

원본문과 추출 SQL의 AST **11 checks PASS**이며 SQL 수·조건·outer join·순서·cursor/offset·자정 범위·점수/동점 규칙이 같다. 신규 `tests/social/test_discovery_workflows.py`의 **3 nodes**는 빈 검색 0쿼리, literal `%`/`@handle` 검색·삭제 Character/비공개/숨김 Post 제외, KST 경계 직전 제외·당일 포함·원래 점수/동점 순서·단일 집계 SQL/commit 0, 인기 root의 경계·삭제·대꾸·숨김·동점 ID 순서를 검증한다.

집중 검증 **33 passed / 5.35s**, #258/#263 API/schema/ORM 차이 0, 기존 보호 테스트 변경 0, 전체 split evidence PASS다. 경계는 **677 modules / 2,239 edges / 243 exact legacy edges**다. 두 legacy edge 증가는 기존 활동 로그/hidden-action 읽기가 명명된 runtime으로 이동한 사실만 기록하며 AR-B4-C가 소유 이전 후 종료한다. B4 담당자가 timezone은 아직 core.agent_activity_schedule의 같은 객체임을 확인했다.

전역 Today 순위와 World 범위 Chat Today SNS snapshot은 구분한다. 후자의 source/관찰/World/coverage와 Relationships/projection, agent/resident, media job·HTTP 전환은 여전히 B5 잔여다. Source introduction capture·통합 Actions·PR/merge는 root가 진행하며 이 source의 집중 PASS를 전체 B5 완료로 확대하지 않는다.


## AR-B5-B9 — 공개 활동 projection과 비공개 필드 경계

공개 활동 schema 정의 5개, action/요약/숨김 상수 4개, admission·응답·event 변환의 실제 함수 3개와 댓글/활동 조회를 해당 역할로 이전했다. 원본 schema/constants·함수 본문·추출 SQL의 AST **14 checks PASS**이며 원래 댓글 → state → 활동 조회 순서와 limit/dedupe를 그대로 사용한다. `app/schemas/characters.py`는 관련 정의가 없는 동일 객체 alias이며 full split의 실제 목적지에서는 제거하고 호환 소비자로만 추적한다.

신규 `tests/social/test_profile_activity_workflows.py` **2 nodes**는 실제 SQLite의 댓글20개·동점순서, lazy state를 포함한 쿼리 순서, hidden activity 제외·state_saved 중복 제거, private field와 로그 원문 마스킹, 없는/삭제 대상의 활동 조회 전 차단을 검증한다. 신규 fixture의 Comment 필드 이름과 identity-map 조건을 수정한 뒤 **25 passed / 4.49s**다. 제품 로직 수정 없이 fixture만 실제 모델·lazy read 조건에 맞췄다.

#258/#263 API·schema·ORM 차이 0, 기존 보호 테스트 변경 0, full split PASS, architecture **682 modules / 2,257 edges / 244 exact legacy edges**다. 원래 로그 읽기 두 의존이 runtime으로 옮겨지고 사용하지 않는 이전 CRUD→agent import 하나를 제거했으며 AR-B4-C의 정확한 후속 소비자를 공유했다. 일반 HTTP·agent/resident·World Feed·media job 및 Relationships/projection 전환은 아직 남아 있고 source capture·Actions·PR/merge는 root가 진행한다.


## AR-B5-B10 — Social HTTP 실제 소유와 실행 연결

기본 Social HTTP 31개의 실제 handler는 `social/router.py`로 옮겼다. 입력·오류 변환·응답은 HTTP가, 업무 판단은 기존에 이전한 service가 소유한다. 요청 dependencies는 공통 인증의 동일 함수 객체와 앱에 연결된 서비스를 사용하며 runtime을 import하지 않는다. 두 앱 생성 경로의 `runtime/social/composition.py`는 원래 네 service 인스턴스를 연결한다. 옛 Community API는 Social과 Character state 경로를 원래 순서로 조립하는 공통 HTTP 책임만 남는다.

원본 31개 함수 body/decorator AST는 실제 서비스 소유 이름을 정규화했을 때 동일하다. #258/#263 API/schema/ORM 차이 0이며 변경 보호 테스트 1개 파일의 assertion도 같다. 신규 `tests/social/test_http_ownership.py`의 3 nodes는 두 factory의 정확 서비스 연결·route 순서·동일 인증 함수, 미구성 요청의 명시적 실패, PATCH 입력/404/422/동일 Session 전달을 검증한다. 초기 신규 fixture의 중첩 라우터 순회와 POST/PATCH 불일치를 수정한 뒤 집중 **40 passed / 1 existing warning / 7.75s**다. 제품 동작이나 기존 assertion은 바꾸지 않았다.

전체 split evidence PASS, architecture **685 modules / 2,277 edges / 241 exact legacy edges**, L4 **685 modules / parity97**, ER0 **Postgres78 / migration subset87 / Neo4j24 / Next44 / parity7**다. Agent/resident·World Feed·media job 및 Relationships/projection의 실제 전환은 아직 남아 있다. 신규 source/tests 첫 도입 capture와 통합 Actions/PR/merge는 root가 순차 수행한다.


## AR-B5-C1 — Relationships 모델·응답 후보의 실제 저장과 상태 변경

8개 ORM class와 13개 candidate 함수·7개 상수의 실제 소유를 Relationships models/service/repository/utils/constants로 이전했다. SocialEvent/Evidence/State/Change/Proposal/Outbox와 replay의 두 원본 모델 파일은 whole-file 이동하며 실제 runtime reader와 등록 소비자를 전환했다. AgentRelationshipPoint는 기존 AgentRun 모델에서 실제 class만 추출하고 동일 객체 alias를 남겼다. B4-C의 AgentRun/로그 등 소유와 구분하며 해당 원문은 수정하지 않았다.

후보 입력 판단·상태 변경은 service, signature/expiry/pending/count SQL은 repository, ID/payload 변환은 utils가 소유한다. 원래 explicit commit/refresh, 충돌 rollback 후 winner 조회, expiry의 전체 활성 후보 범위와 pending recipient/order/limit은 같다. 13개 함수·7개 상수·8개 ORM의 본문 및 추출 query AST를 확인해 차이가 없었다.

신규 `tests/relationships/test_point_write_boundaries.py` **2 nodes**는 잘못된 입력의 SQL0, 기존 duplicate SELECT1/commit0/선택 상태 보존, 첫 조회 뒤 외부 Session이 저장한 경쟁 winner를 실제 UNIQUE 실패→rollback→재조회로 복구하는 흐름을 검증한다. 기존 Resident 전체·SocialEvent·projection commands/replay·삭제와 함께 **230 passed / 13.83s**다. #258/#263 API/schema/ORM 차이0, 보호 구조 테스트1파일의 경로 전환 assertion PASS, 전체 split PASS다. 경계는 **694 modules / 2,292 edges / 241 exact legacy edges**, L4 694/parity97, ER0 Postgres78/migration subset87/Neo4j24/Next44/parity7이다.

B4-C의 실제 residual 소비자 연결과 G5 공통 model 등록에서 정확 legacy alias를 종료한다. Graph service/계약, event/proposal/projection의 나머지 실제 정책과 Social agent/media/World Feed 작업은 이어지는 B5 범위다. 이 source의 capture/통합 Actions/PR/merge는 root가 별도로 진행한다.


## AR-B5-C2 — Graph 계약·규칙과 실제 읽기·회상·계획 실행

기존 Graph read/recall/plan의 실제 실행 본문을 `relationships/service/graph_read.py`, `graph_recall.py`, `graph_planning.py`로 이전했다. 응답 schema와 오류는 `schemas.py`·`exceptions.py`, immutable 값/조회 callback/실행 결과는 `contracts/`가 소유한다. GraphRecall의 방향·근거·공개·bounded 결과 함수와 provider-plan strict 파서는 IO 없는 `policies/`로 분리했다. 서비스마다 전달 전용 중간 클래스를 추가하지 않았으며 graph storage/provider와의 실제 typed callback 계약은 유지한다.

원래 정의 **144개**의 AST 본문·상수·class 메서드가 같음을 확인했다. 기존 공통 schema와 public 소비자는 같은 클래스/함수 객체를 사용하고, `application/domain/graph_read/graph_recall/ports/projection/infrastructure`의 사용하지 않는 old package 모듈7개는 import 소비자0과 기존 공개 이름의 보존을 확인한 뒤 제거했다. `public.py`는 기존 Chat/Memory/runtime/test의 정확한 호환 표면으로만 남으며 각 import별 bridge에 최종 전환·종료 조건을 명시했다.

Graph 읽기·six primitives recall·strict planner·commands/replay/worker/metrics 검증은 **58 passed / 12.29s**, 기존 inventory/port/architecture 회귀는 **24 passed / 3.28s**다. 새로운 test node는 없으며 기존 permission/World/방향/누락 근거/관찰 여부/차단/삭제/실패 fallback/provider 한도 assertion을 유지한다. #258/#263 API/schema/ORM 차이0, 변경 보호 테스트7파일 assertion PASS, 전체 split evidence PASS다. 최초 한 차례 root cwd의 collection은 app import를 찾지 못했으며 이후 모든 실제 검증은 backend cwd에서 수행했다.

Architecture **693 modules / 2,304 edges / 241 exact legacy edges**, L4 693/parity97, ER0 Postgres78/migration subset87/Neo4j24/Next44/parity7이다. 역사 frozen JSON은 수정하지 않았다. 관계 event 생성·proposal과 projection runtime의 SQL/상태 변경 소유, Social agent·World Feed·media jobs는 B5 잔여로 남는다. Source 도입 capture·통합 Actions·PR/merge는 root가 진행한다.


## AR-B5-C3-A — 성공 source의 변화량·상태 상한·outbox와 원본 제외

기존 runtime의 실제 정의20개를 Relationships의 오류/constants/contracts/policies/service로 이전했다. EvidenceInput/EventApplyResult는 같은 값/attached ORM을 유지하고, 시간대와 snapshot은 원래 객체의 값이 읽히는 시점을 유지하는 protocol을 사용한다. Social event type tuple은 constraints와 admission이 같은 constants 객체를 사용한다. 실제 방향별 상태 생성·하루/원본별 변화량 상한·projection payload 선택/서명/중복·원본 삭제 제외를 service가 소유하며 query6개는 repository가 원문 그대로 실행한다.

원본문과 추출 query를 결합한 **20 AST checks PASS**다. `FOR UPDATE`, 조건/정렬/순서·same Session·flush-only source 원자성, 명시적 caller commit 책임을 바꾸지 않았다. Delta cap이 적용돼도 event/evidence/interaction count가 남는 의미, 방향·World 격리, source exclusion의 dedupe와 감사 row도 그대로다.

기존 SocialEvent·manual/observation UoW·owner 수동 작성·proposal·projection·삭제 검증은 **57 passed / 1 existing warning / 26.37s**다. 새 test node나 보호 assertion 변경은 없으며 #258/#263 API/schema/ORM·전체 split evidence PASS다. Architecture **700 modules / 2,329 edges / 241 exact legacy edges**, L4 700/parity97, ER0 **Postgres80 / migration subset87 / Neo4j24 / Next44 / parity7**다. Postgres 분류 파일 수 증가는 실제 query 소유 파일2개의 추출로 생겼으며 schema 변경은 없다.

최종 record_successful_social_event와 외부 source/WC 검증·실행기록 연결은 다음 C3-B 실제 이전 범위로 남겼다. Source capture·통합 Actions·PR/merge는 root가 순차 진행한다.


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


## AR-B4-C5d — ActivityLog 실행 근거·관찰·결과 표현

실행 근거 12함수와 공백 압축 1함수·상수5개를 실제 Routines 역할로 이전했다. Repository는 원래 SQL 아홉 개를 독립 소유하고 service는 원래 expire_all 시점·nullable/JSON fallback·상태 판정·표현을 유지한다. Exact query를 복원하면 실제 함수13개·상수5개 AST가 같으며, sanitize 이벤트 값만 기존 caller가 같은 시점에 명시 전달한다. 외부 ORM이나 Daypart 기억 책임은 옮기지 않았다.

새 SQLite 회귀는 동일 세션의 미커밋 로그·정수 PK 최신 순서·JSON 기본값·rollback, expire_all이 미저장 변경을 폐기한 뒤 조회하는 원래 의미, 공개 행동20개 제한·숨김9유형·사실에 맞는 관찰 문장 선택을 검증한다. 초기 데이터 fixture의 로그 ID를 실제 정수 PK에 맞춰 수정했으며 제품 모델·기존 assertion은 변경하지 않았다. 최종 현재 검증과 부모 선형 통합은 별도로 기록한다.

C5d 최종 현재 후보는 **429 passed / 기존 PostgreSQL 1 skip / 기존 warnings5 / 103.90초**다. 경계 **726 modules / 2,429 edges / exact legacy209 / cycle0**, L4 parity97·ER0 85/87/24/44/7·Memory batch 현재 inventory가 통과했다. 읽기 전용 원래 보존 진단은 **source/split/assertion/suppression/API·ORM/node 각각 오류0**, 보호 **2,139 / 현재2,257 nodes**다. 선행 signed 두 경로의 메모리 보충만 사용했고 tracked frozen/checkpoint/additions·검사 구현은 변경하지 않았다. 부모 source 도입 append 및 ER0 역사·현재 수치 구분 보완 후 stock 전체·CI·installer는 별도 조건이다.


## AR-B4-C5e — Resident 실제 프롬프트·글감 지시 소유

기존 prompt29함수·상수4개를 공통 문맥/읽기/행동/상태/실행 역할의 Routines 파일로 분리하고, services/agent_briefs의 실제5함수·4상수를 action_briefs로 이전했다. 기존 준비 글감15줄도 같은 실제 정책 파일에 있다. 원문29함수는 Character/State의 한정된 입력 타입명을 복원하면 AST가 같고, 상수4개·brief9정의도 동일하다. SQL/SDK 호출이나 값 복제·새 provider 요청은 없다.

독립적인 기존 테스트8개는 원래 본문 그대로 소유 파일로 이전했으며, 공통 helper를 함께 사용하는 다른 테스트는 실제 원래 호출과 assertion을 유지했다. 초기 묶음 **254 passed / 기존 warnings2 / 5.68초** 및 실제34함수의 import 후 전역 의존 누락0을 확인했다. 큰 실행 조립의 줄 수는 종료 조건이 아니며 실제 정책·SQL 소유를 마친 뒤 runtime workflow로 배치한다. Memory Daypart와 다른 소유업무 합류 조건은 그대로 유지한다.

원래부터 호출되지 않던 `_build_tool_recovery_message`·`_build_tool_recovery_prompt`는 실제 consumer를 허위로 추가하지 않고 기존 파일에 원문 그대로 남겼다. 현재 C5e 실제 이전은 **29 prompt 함수**다. 두 미호출 정의의 정리 여부는 B8-A가 원문 보존 조건과 함께 검토한다. 활성 실행 경로에는 새 미사용 alias를 추가하지 않았다.

Social의 지원 schema를 prompt 타입으로 직접 사용했을 때 기존 Social→Routines 협력과 package cycle이 만들어지는 것을 원래 경계 검사가 검출했다. Post/Comment도 실제 읽는 값만 입력 계약으로 받아 같은 원래 객체를 사용하는 방식으로 바꾸어 **cycle0**을 복원했다. 경계 규칙/예외는 넓히지 않았고 프롬프트 본문·기존 테스트 AST는 그대로다.


C5e 최종 고정 tree 검증: **429 passed / 기존 PostgreSQL 전용1 skipped / 기존 warnings5 /102.78초**. 현재 boundary **732modules /2457edges /exact legacy206 /cycle0**, L4 **732/14/97**, ER0 **85/87/24/44/7**, Memory batch inventory PASS. 읽기 전용 원래6검사(source/split/assertion/suppression/API·ORM/node)는 전부 오류0이며 **보호2139/current2257**이다. 최초 signed869bae의 두 실제 도입 경로를 메모리에서만 복원하여 비교했으며 frozen/checkpoint/additions는 수정하지 않았다. 따라서 stock 전체 게이트는 root의 순차 최초도입 원장 연결 후 검증 대상이며 현재 전체 PASS로 표시하지 않는다. 원본29함수/4상수/brief9정의 및 기존8테스트 AST 동일 확인. 새 bridge는 실제 구독자만 기록했으며 원래 미호출2함수는 후속B8-A 대상으로 원문을 유지했다.


## AR-B4-C5f — Resident 응답 판단·실제 provider 연결

기존15함수·4상수를 응답 제약과 fallback/성공 근거/자기 활동 로그의 실제 Routines 서비스와 provider 요청·외부 payload/trace의 runtime 역할로 이전했다. 공개 행동을 만든 원본 결과에만 근거를 연결하며, 두 읽기 전용 호출의 인자·idempotency key·시각·예외를 바꾸지 않았다. canonical ActivityLog 함수를 동일 인자로 연결해 원래 finish_write 및 deferred commit 의미를 유지한다. 기존 독립 evidence 테스트2개를 본문 그대로 옮겼으며, 신규3개는 no-call/one-call/원래 오류와 실제 SQLite transaction을 검증한다. 최종 검사 결과는 아래에 이어 기록한다.


C5f 검증은 초기 **73 passed /기존 warnings2/22.28초**, 최종 고정 tree **432 passed /기존 PostgreSQL1 skipped/기존 warnings5/101.48초**이다. 처음 경계 검사가 runtime의 annotation-only app.models·services.runtime_boundary 의존을 잡아냈다. 해당 생성자를 실제 생성하지 않고 주입된 client만 사용하므로 실제 필요한 `DecisionClient`·`DecisionCredential` 계약과 기존 Character/State readview로 타입을 표현했다. 동작과 인자 전달은 그대로이며 새 legacy 예외는 추가하지 않았다. 현재 boundary **738modules/2483edges/exact legacy206/cycle0**, L4 **738/14/97**, ER0 **85/87/24/44/7**, Memory batch PASS. 원래15함수·4상수는 네 한정 타입명을 복원하면 AST가 같고 이동2테스트 본문도 동일하다. 읽기 전용 원래6검사는 오류0, **보호2139/current2260**이며 최초 signed869bae의2경로만 메모리로 보충했다. frozen/checkpoint/additions 불변, stock 전체 게이트는 root의 선형 최초도입 원장 연결 뒤 검증한다.


### AR-B4 첫 통합 — Routines·Routine Posts·resident 준비와 실행 정책

Media 후보 위에서 signed source `aa183ecec887d08c31f172c68bd7c40b22492c19`까지 `b4e43cdaac01a96abfa57c07a08404b59dacc00b`로 합류했다. 실제 schema/model, plan/일정, 같은 Session의 Context/Joint/Slot/실행 claim, prompt/brief/provider 결정 역할을 옮긴 단계다. AgentRun 마지막 context·실행 조립 및 LangGraph·Character 활동 관리의 남은 업무 이전은 다음 B4 source에서 계속 진행하며 B4 전체 종료가 아니다.

원래 signed 31개 source commit 각각을 Git archive로 검사해 pytest collection·assertion·suppression·OpenAPI/ORM을 수집했다. 기존33개 additions를 보존하고64개로 append했으며 원래 addition_errors의 first-introduction/blob/ancestry 검사를 통과했다. 원래 models.py/schemas.py 중간 목적지가 나중의 split source가 된 두 경로도 최초869bae55 커밋의 정확한 blob으로 기록했다. 현재 tree나 변경된 기대값으로 기준선을 다시 만들지 않았다. **stock 보존 검사 PASS: frozen1867/PR2631907/protected2260/current2260, items37**이다.

최초 전체 backend 실행은2235 PASS/3 FAIL/22 SKIP/27 warnings,1265.51초였다. 실제 실패와 후속 처리: (1) L0 core inventory에 이미 이전한 activity schedule/limit 두 모듈이 남고 새 공통 context_text가 빠졌으므로 실제16개 목록으로 수정했다. 기존 L0 6 tests와 원래 CLI PASS다. (2) isolated docx parser가 부하 중 기존15초 제한을 초과했으나 동일 코드/동일 제한으로 원래 검사 재실행 PASS다. (3) Memory observation fixture의 Post·Observation 동시 add_all이 ORM 등록 순서에 따라 FK를 위반하므로 부모 Post add/flush 후 Observation add로 고쳤다. FK나 assertion은 그대로이며 원래 검사 PASS다. 마지막 두 검사는 함께2 PASS/21.97초다. 초기 실패를 전체 PASS로 바꾸어 기록하지 않으며 PR 전체 CI와 머지 후 설치 검증을 별도로 확인한다.

PR #281 첫 head51b6ee4의 architecture-boundary는 실제 import/경계 통과 뒤 frontend portable-contract 목록이 삭제된 social/api/schemas.py를 가리켜 실패했다. 실제 동일 스키마 소유 social/schemas/manual.py로 정책과 보고서 경로 두 곳만 전환했다. 원래 frontend design 검사 PASS(raw_colors1408/files33/surfaces18/route_gaps0/screenshots11)이며 색상·UI·스크린샷 기대값은 그대로다. 최신 PR head의 전체 검사를 다시 확인한다.

## AR-B4-C6a — Resident 후보·도구·세션·실행 오류 소유

기존 순수 candidate8/tool정책4/session키·시간대6/request옵션3/오류클래스8 총29정의와 active상수19개를 실제 소유로 이전했다. 호출되지 않는 과거 action_menu178줄·recovery2함수와 unused상수2개는 원문보존 및 B8-A 검토 대상으로 남겼으며 허구 소비자나 새 지원경로를 만들지 않았다. 기존 세션3테스트 본문과 KST/settings 객체를 그대로 유지했다. 최종 검증을 아래에 이어 기록한다.


C6a 초기 **142 passed /기존warnings6/12.42초**, 최종 고정 tree **441 passed /기존 PostgreSQL1 skipped/기존warnings6/103.78초**. 원문29함수·클래스/19상수 AST 정확동일, 기존 세션3테스트 본문동일이며 새 동작·테스트 node 추가는 없다. 현재 boundary **742modules/2495edges/exact legacy206/cycle0**, L4 **742/14/97**, ER0 **85/87/24/44/7**, Memory batch PASS. 읽기 전용 원래6검사는 오류0이며 **보호2139/current2260**. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions 불변; root의 선형 최초도입 원장 연결 뒤 stock 전체 게이트를 다시 확인한다. 기존 class alias 소비자는 실제 HTTP/runtime의 동일객체 참조를 기록했으며 신규 타입간 상속·오류 메시지·처리순서를 바꾸지 않았다.


## AR-B4-C6b1 — Resident의 실제 Social 조회 소유

원래5 query helper와 `_profile_following_status`의 nullable scalar 한 개만 Social repository/resident_context.py로 이전했다. Social 담당과 파일 충돌 및 소유권을 확인했다. 모델·조건·정렬·limit1·BFS frontier/seen·숨김/삭제 제외·같은 Session을 바꾸지 않았고 별도 commit을 추가하지 않았다. 실제 활성 소스의 조회함수를 이동했으며 정책·HTTP·provider 동작은 그대로다. 후속 C6b2에서 실제 후보/table 규칙과 typed runtime read 협력을 연결한다. 신규 SQLite2노드는 pending 데이터의 caller/observer 차이와 rollback, visible 답글 경로 및 direct-reply 의미를 검증한다.


C6b1 초기 **55 passed /기존 warnings2/25.07초**, 최종 고정 tree **443 passed /기존 PostgreSQL1 skipped/기존 warnings6/259.37초**. 실제5 query 함수와 follow scalar·주변 정책의 원래 AST를 확인했고, 경계 **743modules/2498edges/exact legacy206/cycle0**, L4 **743/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2262**다. 최초 signed869bae의2경로만 메모리에서 보충했으며 frozen/checkpoint/additions는 변경하지 않았다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 뒤 확인한다. C6 이후에도 settings/활성화·capacity/수동 실행/첫인사의 실제 Routines 정책과 HTTP 전환을 완료해야 하며, runtime/characters/management에 남은 업무를 완료로 간주하지 않는다.


## AR-B4-C6b2 — Resident 행동 허용·실제 후보 표

실제 정책5함수와 원래2개 메뉴 테스트를 Routines 소유로 이전했다. 조회9개는 caller의 같은 Session을 가진 runtime collaborator가 소유별 실제 함수로 연결하고, 원래 conditional 호출·autoflush·객체 identity·예외와 provider0을 유지한다. 정확 협력 인자를 복원하면 정책5개와 모든 남은 AgentRun 본문 AST가 같고 기존2테스트의 assertion도 같다. 초기57 PASS/기존warnings2/39.49초이며 추가2SQLite는 caller pending/observer/rollback 및 미커밋 숨김의 후보 제외를 검증한다.

검사기는 parent가 검토한 signed6d9e342의 `check_split_evidence` 함수 본문만 반영했다. 각 검사 위치에서 파일을 계속 읽고 동일 invocation의 동일 source text parsing만 재사용한다. Memory 테스트2개·추가원장·제품 소스는 가져오지 않았다. 기존 검증 의미와 동결자료를 유지하며 최종 검증을 이어 기록한다.


C6b2 최종 고정 tree는 **538 passed /기존 PostgreSQL1 skipped/기존warnings4/187.22초**이며 기존 checkpoint·node 검사도 포함했다. 경계 **747modules/2520edges/exact legacy206/cycle0**, L4 **747/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2264**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions 불변이다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 뒤 다시 확인한다. 호출 token만 바꾸어 원문의 여러 줄 서식을 유지했고 실제5정책과 남은 전체 AgentRun의 AST 및 원래2테스트 assertion을 대조했다.


## AR-B4-C6c1 — Resident 알림·게시물·자기 실행 이력 SQL

원래7개 SQL 조각과 스레드 루트 함수1개를 실제 소유로 분리했다. 동일 알림 SQL 두 곳은 원래30/20을 인자로 유지하는 한 함수로 묶었고 나머지 조건·정렬·limit·nullable·Session은 그대로다. 실제 업무 선택과 표현은 원래 위치에서 후속 C6c2로 이어진다. 신규3SQLite는 알림 type/recipient/unread와30/20, 게시물 숨김·삭제/시각/정렬·8/5/200, 스레드 cycle, pending 관계검토와 observer/rollback을 검증한다. 원문7SQL 및 helper와 모든 남은 AgentRun 본문은 exact query를 복원하면 AST가 같다.


C6c1 초기 **60 passed /기존warnings2/25.78초**, 최종 고정 tree **455 passed /기존 PostgreSQL1 skipped/기존warnings4/211.47초**. 경계 **748modules/2522edges/exact legacy206/cycle0**, L4 **748/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2267**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions는 수정하지 않았다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 이후 별도로 확인한다.


## AR-B4-C6c2 — Resident 피드·알림·관계 문맥의 실제 정책

실제11개 선택·표현 함수를 feed_context/social_context로 이전했다. Runtime은 기존Session의 owner SQL과 제한된 Character/Identity 값을 연결하며, 아직 B5 원문인 Social3기능은 기존caller가 typed협력으로 전달한다. 새legacy import나예외를 만들지 않았다. Strict Post isinstance는 같은 실제 Post class로 유지하며 입력을 복제하지 않는다. 순수UTC helper는 이름만 다른 기존 tick_schedule.aware_utc와 AST가 정확 같아 실제함수 하나를 재사용했다. 원문11함수와 남은AgentRun본문 전체는 한정된read호출을 복원하면 AST가 같다. 초기63PASS/기존warnings2/37.62초, 추가3SQLite는 원래행identity·pendingvisibility·수신자·잘못된review입력·상호답글→pendingfollow제외와observer/rollback을 검증한다.


C6c2 최종 고정 tree **458 passed /기존 PostgreSQL1 skipped/기존warnings4/164.50초**. 경계 **752modules/2546edges/exact legacy206/cycle0**, L4 **752/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2270**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions는 수정하지 않았다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 이후 별도로 확인한다.


## AR-B4-C6d1 — 슬롯 상태·준비 조건·예약 재시도

실제4함수를 Routines 서비스로 옮기고 due6 parameter/readiness1 원문node를 원래decorator·본문·fixture·assertion 그대로 이전했다. LG 담당과 readiness1node의 정확 소유를 협의했다. 슬롯 목록 API는 실제owner service로 직접 연결했으며 원래route본문/응답은 같다. 첫264PASS/기존warnings2/19.04초와 route/transaction 집중10PASS/14.43초를 확인했다. 신규3SQLite는 early return에서 timezone 읽기0, 제공된setting의 pending/rollback과 없는setting의 원래ensure commit→timezone순서, 실제 API 함수의 소유자필터·공개형식·pending변경을 검증한다. 원문4함수와 전체남은AgentRun본문은 한정timezone callback만 복원하면 AST가 같고 원래7testnodes와 routebody도 정확동일하다.


정확 소비자 확인 결과 AgentRun의 `_has_tendency_analysis`는 제품 호출이 없고 기존 테스트1개만 소비한다. 실제 관리 흐름의 동명 함수와 통합하지 않고 원래 AgentRun helper를 B8-A 검토 대상으로 보존했다. 이번 실제이전은 **4함수**이며 기존 readiness테스트는 소유 위치만 옮겨 원래 helper를 계속 검사한다. 허구 실행 소비자나 신규 지원 API를 추가하지 않았다.


C6d1 최종 고정 tree **461 passed /기존 PostgreSQL1 skipped/기존warnings4/176.92초**. 경계 **754modules/2556edges/exact legacy205/cycle0**, L4 **754/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2273**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions 불변이다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 이후 별도로 확인한다.


## AR-B4-C6d2 — 실행 권한·인증 프로필 연결

원래3함수의 실제 책임을 Routines 실행 권한과 Runtime 인증 IO로 나눴다. 캐릭터 missing/deleted·ownership 뒤에만 credential을 읽고 기존 Social CharacterNotFoundError class를 유지한다. 등록 proxy는 호출자가 같은 객체를 전달하므로 추가 registry lookup이 없다. Match이면 reveal0, 아니면 resolve/reveal→bind→reload→inspect와 release→reload가 원래 순서다. 원래3함수 및 전체남은AgentRun본문 AST는 한정주입/타입만 복원하면 정확 같다. 초기85PASS/기존warnings2/23.39초. 신규SQLite2+auth5는 attached객체·pending/rollback·오류순서와실패단계·비밀정제를 검증한다. Reveal allowlist는 실제 정의 경로/함수 pair만 옮겼으며 기존 assertion을 유지했다. Identity c2cd2a6의 실제 query는 parent 후속통합 시 현재typed lookup에 연결한다.


C6d2 최종 고정 tree **476 passed /기존 PostgreSQL1 skipped/기존warnings4/192.06초**. 경계 **758modules/2570edges/exact legacy205/cycle0**, L4 **758/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2280**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions는 수정하지 않았다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 뒤 별도로 확인한다.


## AR-B4-C6d3 — 실행 대상·상태 조회 소유권

원래Social SQL2와 실제대상정책2를 분리했고 CharacterState5/활동설정2/슬롯2의 원래nullable9읽기를 실제owner로 연결했다. 원문2SQL 및 전체남은AgentRun본문은 exactbinding 복원 후 AST동일하다. 기존scoped/fallback2node는 실제owner test로옮겼으며 원래assertion/exception/expected를 유지하고 테스트 호출배선만 실제새서비스+같은Session references로 조립했다. 제품호환wrapper/검사예외를 만들지 않았다. 초기72PASS/기존warnings2/17.78초; 신규SQLite2는 필터/nullableauthor/정렬/우선순위/fallback·pending/rollback 및 loaded객체identity/no flush/no commit을 검증했다. Social·LG담당과한정새query/Character상태helper소유를협의했다.


C6d3 최종 고정 제품 tree **478 passed /기존 PostgreSQL1 skipped/기존warnings4/231.18초**. 마지막 정적 검사에서는 repo를 entry가 아닌 scope module로 등록하고 새기존get_setting소비자 한edge를 기한있는 bridge로명시했다. 경계 **761modules/2576edges/exact legacy205/cycle0**, L4 **761/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2282**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions 불변이다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 뒤 확인한다.


## AR-B4-C6d4a — 실행 진입 판단·credential 대기 시각

실제admission3block을 Routines로 옮기고 동일available Character3문장은 두원래caller에서같은정책을사용한다. 명시credential검증과기본owner+character조회는기존차이를유지하며 post조회→owner판단순서도그대로다. Identity의boundedcooldown은4원래대입만담당하고Caller의flush/commit/rollback은변경하지않았다. log_activity8호출은C1의samefunction actualowner로직접연결했다. 원문3block·전체남은AgentRun본문 AST는exact호출복원후동일하다. 초기72PASS/기존warnings2/21.90초. 신규SQLite2는기본queryscope·실제행identity·pending/rollback과cooldownSQL증분0을확인한다.


C6d4a 최종 고정 tree **480 passed /기존 PostgreSQL1 skipped/기존warnings4/192.09초**. 경계 **763modules/2582edges/exact legacy205/cycle0**, L4 **763/14/97**, ER0 **85/87/24/44/7**, Memory batch 현재 inventory PASS. 읽기 전용 원래6검사는 오류0, **보호2139/current2284**다. 최초 signed869bae의2경로만 메모리에서 보충했고 frozen/checkpoint/additions 불변이다. Stock 전체 게이트는 root의 순차 최초도입 원장 연결 뒤 확인한다.


## AR-B4-C6 — 슬롯 요청 정책·Resident 실행 연결

슬롯 요청 2개의 원래 업무 판단을 Routines 서비스로 옮겼다. 런타임은 같은 Session에서 원래 유지보수 제한 → 캐릭터·credential 검증 → 설정 저장 → 최초 시각 → 슬롯 lock 순서를 지연 평가로 연결한다. 신규 SQLite 2개는 commit=False/True 각각 pending 행, observer 가시성, clock/lock 호출 시점과 rollback을 검사한다. 임시 claim의 원래 정책 본문은 AST 대조와 기존 회귀로 확인한다.

Resident 실행 10개 함수는 실제 provider·lease·run_created·보상 순서를 그대로 `runtime/resident/execution.py`로 옮겼다. Scheduler의 lifecycle 연결은 원래 실제 서비스를 직접 참조한다. HTTP의 실행 오류는 동일 Routines 오류 클래스를 사용한다. 기존 소스 경계 검사는 execution/post_selection/scheduler의 정확한 세 파일을 모두 검사하고 원래 positive/forbidden assertion을 유지한다. 보안 소스 검사는 새 실행과 기존 Memory 잔여를 모두 포함한다. 초기 집중 152개 통과 뒤 mock 대상 2개와 실제 scheduler 연결을 수정했고, 해당 3개 재검사는 통과했다. 최종 확대 검증은 아래에 별도로 기록한다.

B7 Memory 7개 실제 정의와 원래 미호출/검사용 5개 정의는 아직 제거하지 않았다. Social·Memory·Identity·Operations·Runtime·LangGraph의 독립 source 합류까지 필요한 기존 구현 연결은 정확한 7개 edge와 제거 조건으로 기록한다. 이는 해당 후속 단계나 전체 B4 완료 주장이 아니다.

최종 고정 대상 검증은 **490 passed, 1 skipped, 4 warnings / 209.73초**이다. skip은 기존 PostgreSQL 환경 표식이며 경고도 기존 항목이다. 경계는 766 modules / 2609 edges / exact legacy 202 / cycle 0, L4 766/14/97, ER0 85/87/24/44/7 및 Memory batch current이다. 읽기 전용 원래 6개 검사는 오류 0, 보호 2139개·현재 2286개 노드로 확인했다. 선행 source 최초 도입 원장 합류 전이므로 이 진단은 stock 보존 gate나 Hosted CI 통과를 대신하지 않는다.


## AR-B4-C7-A — 활동 설정·성향 분석의 실제 소유

원래 management에 있던 성향 schema 6개, 프롬프트·정규화 11개, 상태 4개, 활동 설정 4개, 오류 15개와 상수 8개를 역할별 Routines 코드로 이전했다. 공유 `AgentServiceError` 원래 클래스 1개는 공통 오류 기반으로 옮기고 기존 Character 경로는 같은 객체를 제공한다. 원래 48개 정의/상수와 공유 기반 1개의 AST는 정확한 type/callback 복원 뒤 동일하다. 초기 관련 153개 통과 후 실제 schedule 구현 위치로 mock 1곳만 전환했으며 해당 1개 재검사는 통과했다. 기존 tendency 검사 파일 전체는 Routines 소유 경로로 옮기고 assertion·fixture·parametrize를 유지한다. 후속 관리 실행/HTTP/credential owner 전환은 남아 있다.

최종 집중 검증은 **155 passed / 기존 경고 6개 / 12.96초**이다. 신규 실제 SQLite 검사는 같은 Session의 pending Character/Setting/Slot을 유지하며, schedule callback 시점의 다른 Session에는 이전 값이 보이고 최종 commit 뒤 새 값이 보이는 것을 확인한다. 공통 기반으로 이동한 오류는 기존 Character catch에서 같은 동작과 오류 필드를 유지한다.

최종 소스 경계는 771 modules / 2636 edges / exact legacy 202 / cycle 0이다. L4 771/14/97, ER0 85/87/24/44/7과 Memory batch가 현재 코드와 일치한다. 최초 진단에서 남은 generic parametrized 테스트 경로 9개를 실제 이전 경로로 고쳤고, 최종 원래 6개 읽기 전용 검사는 모두 오류 0(보호 2139개 / 현재 2287개)이다. assertion, suppression, API/ORM 및 원래 노드는 모두 보존했다. 선행 최초 도입 원장이 합류하기 전의 진단이며 stock gate·Hosted CI와 구분한다.

## AR-B4 LG-A — Resident provider 응답 스키마와 단계 규칙

B4 C5e `b71c0e3`를 기준으로 LangGraph의 25개 실제 Pydantic 모델·버전 상수와 Topic Arc 단계 검증을 Routines schemas/policies로 이전했습니다. JSON schema 전체 25개가 원문과 같고, 27개 정의 AST는 validator의 역할 전용 입력 Protocol 타입명 한 곳을 복원하면 같습니다. 기존 caller는 실제 동일 class/function 객체를 사용하며 새로운 DB/provider 호출은 없습니다. LG 테스트 186개는 기존 assertion 그대로 초기 PASS입니다. 최종 source 검증 결과를 아래에 기록합니다.

전체 원본 294개 정의의 위치·직접 소비자·기존 검사 대응을 명시했습니다. LG-A는 응답 계약의 실제 소유 이전이며 업무 결정·SQL·graph 조립 전체 완료가 아닙니다. LG-B/LG-C와 이미 고정된 B7 Daypart 및 B5 RelationshipPoint의 root 통합이 남습니다. 불변 checkpoint와 append-only 원본은 수정하지 않으며 신규 4파일의 최초 source 증거는 signed source 이후 root가 순차 캡처합니다.

계획과 Social이 함께 사용하는 동기·감정 enum 두 개의 실제 정의는 `app/contracts/action_subjective_context.py`에 있습니다. Social의 subjective DTO·출처·텍스트 검증·저장 규칙은 Social에 유지하며, 값 enum의 같은 객체를 import합니다. 따라서 enum 값·identity·provider schema를 바꾸지 않고 두 업무의 공유 값만 연결합니다.

LG-A 최종 고정 후보 검증: 관련 **372 passed / 기존 warnings2 / 111.95초**. 전체 provider JSON schema25개 동일, 원문27정의와 공유enum2정의 AST 동일(validator 입력 Protocol 타입명1곳 정규화). 경계736모듈/2463edges/206legacy, L4 736/14/97, deferred22 PASS. 원래 보존 6검사 진단은 sources/split/assertions/suppressions/API·ORM/missing-nodes 모두0이며 protected2139/current2257입니다. signed 최초869bae55의 두 Routines 파일 blob만 읽기 메모리 보충한 진단으로, stock 전체 PASS나 신규 도입 캡처를 주장하지 않습니다. 기존 테스트 수정·노드 추가0, 신규 제품 파일4개이며 root가 source 고정 후 순차 도입 증거를 합칩니다.


## AR-B4 LG-B1 — Resident 계획·출력의 실제 순수 판단

원래43함수와11상수를 날짜/이월·문맥 충족·행동 대응·필수 출력·writer 결과 역할의 Routines policies로 이전했다. 전체 본문 AST는 원문과 같고 관계 허용 함수의 입력 타입만 기존 `activity_policy`를 읽는 구조 계약으로 표현한다. 응답 필터·순서·중복 제거·문자열·source-copy 판단을 바꾸지 않았고 실제 함수의 전역 의존을 검사해 누락0을 확인했다. 정책을 호출하는 실행 조립은 아직 옛 resident 모듈에서 실제 같은 함수를 import하며 LG-C에서 runtime으로 옮긴다.

보존 검사에는 부모가 이미 검증하고 고정한 `6d9e342`의 invocation 내부 동일 내용 parse cache 19줄 diff만 적용했다. 모든 경로는 원래 시점마다 다시 읽고, 같은 경로의 바뀐 내용은 다시 분석한다. 원래 frozen·assertion·error 규칙과 추가 도입 ledger는 바꾸지 않았고 부모 source의 테스트나 snapshot을 복사하지 않았다.

LG-B1 최종 후보 검증: 기존 LangGraph·Today·Routines와 보존 검사 회귀 **553 passed / 기존 warnings2 / 137.22초**. 경계742/2470/206legacy, L4 742/14/97, deferred22 PASS. 원래6검사 진단 sources/split/assertions/suppressions/API·ORM/missing-nodes 모두0(protected2139/current2257)이며 stock은 부모 최초 source 도입 캡처 대기입니다. 새 도입6제품 파일, 새 테스트 노드0, 기존 테스트 본문 변경0입니다.


## AR-B4 LG-B2 — TopicArc 실제 진행·복구와 시각 규칙

TopicArc 실제14함수와 시각5함수·요일상수를 소유 service/policies로 옮겼다. 원래 본문 AST는 narrow 입력 타입·같은 APP_TIMEZONE·명시 workflow 인자/nullable callback만 복원하면 일치한다. 실행부는 기존 clip과 두 조회 함수를 `TopicArcWorkflows`로 구성하여 실제 함수에 바인딩하고, 조회를 미리 호출하거나 다른 Session을 만들지 않는다. 기존 LangGraph **186 passed / 26.18초**. 새 회귀는 DB read 순서/같은 Session/commit0과 날짜만으로 결정한 분기의 추가 조회0을 검증한다.

원래 Memory 이벤트 구현/clip은 B7 고정 소스를 부모 통합에서 받아야 하므로 이 작업에 같은 helper 파일을 다시 도입하지 않는다. 현재 기존 함수의 실제 callback만 유지하며 전체 LG-B/LG-C 완료나 부모 도입 ledger 완료를 주장하지 않는다.

LG-B2 최종 고정 후보: **376 passed / 기존 warnings2 / 225.61초**, 원래6보존진단 모두0(protected2139/current2261). 경계744/2482/206legacy, L4 744/14/97, deferred22 PASS. 신규 제품2파일(`service/topic_arcs.py`, `policies/resident_clock.py`)과 신규 테스트1파일, 신규 수집노드4개(동일 Session/order1 + 날짜 admission3)이다. 기존 테스트 본문/assertions/노드 변경0. 부모의 source 최초 도입 ledger 합류 전 stock 전체 완료로 표시하지 않는다.


## AR-B4 LG-B3a — 실제 주제 선별·확률과 성공 글 조회

원래 자율 주제/확률8함수·날짜 범위2함수·SQL 조회2함수와 선택 상수2개를 역할별 service/repository/clock으로 옮겼다. 전체14정의 AST는 구조 입력 타입·같은 clip·같은 ORM 객체·직접 repository 경로만 복원하면 동일하다. SQL의 Character id/성공 post 필터, created_at/id 역순, 40/120개 한도와 오늘 현재 시각까지의 포함 경계, 오류시 빈 결과를 유지한다. 조회 함수는 새 commit/flush를 하지 않는다.

기존 monkeypatch 준비7곳만 실제 조회/선별 모듈로 연결하며 assertion·skip 계약과 수집 노드를 바꾸지 않는다. 실제 행위 판단을 옮긴 것이며 전체 ActionPlan/Writer/Graph 전환 완료나 부모 도입 ledger 완료를 뜻하지 않는다.

LG-B3a 최종 후보 검증: **376 passed / 기존 warnings2 / 168.59초**. 원래6보존진단 모두0(protected2139/current2261), 경계746/2489/206legacy, L4 746/14/97, deferred22 PASS. 신규 파일은 실제 `service/independent_topics.py`·`repository/independent_topics.py` 두 개이며 새 수집노드0. 기존 테스트7곳은 monkeypatch 준비 대상만 실제 소유자로 바꾸고 assertion·suppression 전체 동등을 확인했다. 부모의 최초 source 도입 증거 캡처와 다른 owner source 최종 합류는 별도이다.


## AR-B4 LG-B3b — 실제 행동 계획·쓰기 의도·예산

원래25함수(1359줄)와 상수3개를 action_plans/writing_plans/action_budgets 실제 서비스로 옮겼다. 원문 AST는 좁은 context 타입과 명시 clip/read 협력 인자만 복원하면 같다. 관찰 항목 선택·필수 글 복원·관계 행동의 증거 판단·unfollow 충돌·하루 글/댓글 제한·멘션/알림 우선순위와 bucket 한도는 그대로다. 기존 LangGraph **186 passed / 6.64초**를 확인했다.

설정 callback은 실제 Routines activity_settings로 연결하고 원래 테스트8개 mock 대상만 해당 모듈로 바꾼다. source/Memory 읽기는 기존 same-Session runtime 협력이며 부모 B5/B7에서 정확히 합류한다. 새 회귀2개는 같은 Session/시각/설정→count 순서, 무제한 count 생략, 추가 commit0을 검사한다. graph/provider 실행은 아직 LG-C의 남은 실제 소유 책임이다.

LG-B3b 최종 고정 후보 검증: **378 passed / 기존 warnings2 / 176.55초**. 원래6보존진단 sources/split/assertions/suppressions/API·ORM/missing-nodes 모두0(protected2139/current2263), 경계750/2507/206legacy, L4 750/14/97, deferred22 PASS. 실제 서비스3개·협력 계약1개와 회귀1파일이 최초 도입되며 새 노드는2개다. 기존 assertion·suppression은 그대로이고 mock 준비 대상8곳만 실제 설정 소유자로 연결했다. 부모의 source 도입 증거 캡처와 B5/B7/runtime 최종 합류는 별도이다.


## AR-B4 LG-B4 — 작성 결과와 상태 근거·복구 규칙

원래22함수와 상수2개의 실제 본문을 writer task id, post writer plan/result, 상태 근거·복구 역할로 이전했다. 좁은 입력 타입과 같은 clip/순수 변환 함수 인자만 복원하면 원문 전체 AST가 같다. 원래186 LangGraph 검사 **186 passed / 6.07초**, 기존 테스트 수정0, 실행 전역 함수 누락0을 확인했다.

DirectLlmJsonError인 경우만 자체 validation_summary를 읽는 원래 isinstance 분기는 runtime에 그대로 두며 실제 서비스가 명시적으로 연결된 변환기를 호출한다. 실제 성공·재사용 행동만 fallback 기억 근거에 쓰고, 허용된 필드의 길이 오류만 정제한 뒤 원래 StateWrite 전체 검증을 다시 통과해야 한다. provider 호출·재시도 횟수·기존 prompt payload는 변경하지 않았다. 남은 prompt 판단과 graph/provider 조립은 후속 LG 전환이다.

LG-B4 최종 후보 검증: **378 passed / 기존 warnings2 / 125.78초**. 원래6보존진단 모두0(protected2139/current2263), 경계754/2519/206legacy, L4 754/14/97, deferred22 PASS. 신규 실제 제품4파일이며 새 테스트 노드0·기존 테스트 변경0이다. 원본 frozen과 append-only ledger를 변경하지 않았으며 부모의 source 첫 도입 캡처 후 stock 통합 검증을 진행한다.


## AR-B4 LG-B5 — 실제 프롬프트·작업 구성·planner 결과

원문17함수를 resident_prompts/writing_tasks/planner_results로 이전했다. 좁은 persona/state 입력과 같은 도메인의 실제 helper를 연결하는 kwargs만 복원하면 전체 AST와 문구가 같다. provider 호출은 없다. 원래 선택·task id·TopicArc 날짜/근거 조회·writer 순서·JSON 필드를 유지한다.

기존 source inspection의 writer prompt 준비 대상1곳을 runtime partial에서 실제 defining service 함수로 바꿨다. 모든 기존 assertion과 suppression은 동일하며 행동 검사를 삭제하지 않았다. 현재 LG source 전체 소유 지도는 원래294정의의 실제 위치를 이어간다. Memory/Lore/Relationships의 이미 구현된 소유 코드는 복제하지 않으며 부모 합류에서 기존 읽기 협력을 교체한다.

LG-B5 최종 후보 검증: **378 passed / 기존 warnings2 / 115.77초**. 원래6보존진단 모두0(protected2139/current2263), 경계758/2548/206legacy, L4 758/14/97, deferred22 PASS. 신규 제품4파일이며 새 테스트 노드0이다. 원본 frozen·append-only ledger는 유지하며 최초 source 캡처와 다른 소유 구현의 순차 합류는 부모 통합에서 수행한다.


## AR-B4 LG-B6 — 관계·대화·쓰기 문맥의 실제 판단

원래16함수와 상수4개를 relationship_context/writing_context/conversation_context의 실제 본문으로 옮겼다. 조건 분기·필터·순서·개수·문자열은 원문과 같고, 구조 값 입력과 동일Session 조회 callback·자기 ActivityLog/시각 구현 경로만 정규화하면 전체 AST가 일치한다. 원래 LangGraph **186 passed / 6.77초**, 기존 테스트 수정0이다.

읽기는 원래 판단 지점에서 수행하며 follow가 허용되지 않거나 source가 없으면 후속 읽기를 생략한다. 대화 부모 순환 차단·조회 실패·마지막6turn과 전날문맥 충족은 원래의 실제 함수에 남는다. B5 Point 상태와 B7 Memory 저장/조회 구현은 복제하지 않고 부모 통합 대상이다. nullable state의 타입만 기존 getattr 동작에 맞게 표현했다. 남은 foreign SQL projection과 graph/provider 조립은 LG-C 실제 소유 전환에서 마무리한다.

LG-B6 최종 후보 검증: **378 passed / 기존 warnings2 / 113.50초**. 원래6보존진단 모두0(protected2139/current2263), 경계762/2564/206legacy, L4 762/14/97, deferred22 PASS. 최초 도입은 실제 제품4파일이며 신규 노드0·기존 테스트 변경0이다. 원본 frozen과 source ledger는 그대로 유지했고 부모의 첫 도입 증거 캡처는 별도로 남아 있다.


## AR-B4 LG-C — 실제 조회·graph 실행과 테스트 소유 전환

실제 foreign read/projection10함수는 runtime/resident/langgraph_queries로, 순수 실행 식별자·결과 대응10함수는 Routines execution_results로 이전했다. 같은 구체 모델·Character lookup·timezone 및 명시 helper 인자만 복원하면 원문 전체 AST가 같다. 남은 graph/provider/여러 업무 실행53개 정의는 runtime/resident/langgraph.py에 원문 AST 그대로 있으며, 기존 로깅 category는 명시 문자열로 유지한다. 옛 services/langgraph_resident.py를 제거하고 실제소비자는 runtime/context/GraphState 계약의 defining 경로를 사용한다.

원래 테스트의 LG 관련153함수와 공통 helper10개를 tests/routines/test_resident_graph.py로 옮겼다. 수집된 LG cases166개와 옛 파일의 foreign-owner20개가 원래186개를 보존한다. 원래 DirectLlm fixture18개·AgentWriting1개와 sibling f751611의 readiness1개는 합류 전 원래 파일에 둔다. 따라서 credential synthetic fixture/allowlist/immutable checkpoint 증거를 옮기거나 늘리지 않는다. 원래 assertion과 suppression은 유지하며, 이미 고정된 overload helper/node 지도도 보존한다. 초기 기존 LG·소유별6회귀를 합쳐 **192 passed / 6.72초**다.

보존지도는 원래294LG 정의의 실제목적지를 모두 잇는다. 기존 Memory/공통clip과 Point의 원문 잔여는 함수명·소유·종료조건으로 고정하며 부모 B5/B7 통합이 이미 구현된 서비스를 연결해야 닫힌다. LG source 준비와 GitHub 머지/전체B8 완료를 구분한다.

LG-C 최종 검증: 확장 기존 회귀 **428 passed / 기존 PostgreSQL1 skipped / 기존 warnings3 / 189.69초**. 당시 실패3개는 제거한 LG 파일의 검사 경로2곳이었으며 실제 runtime 경로로 수정한 뒤 해당 아키텍처 검사 **8 passed / 6.20초**를 확인했다. 매개변수 테스트2함수는 frozen에 수집된 정확15노드로 이동지도를 보완했다. 원래6보존진단 source/split/assertion/suppression/API·ORM/node는 전부0(protected2139/current2263), 경계764/2579/205legacy·L4 764/14/97·deferred22 PASS다. 신규 노드0이며 graph 테스트166case는 기존 노드의 위치만 이전했다. 비밀 예외 metadata25개도 그대로 PASS다.

`scripts/verify_m4_contracts.py`의 GraphState 소비는 실제 계약으로 연결했지만, 독립 실행의 옛 148operations/120paths/182schemas snapshot은 현재196/160/266과 달라 실패한다. 이 역사적 baseline을 재작성하지 않았고 현재 source의 API·ORM 보존은 위의 원래6검사에서 따로 동일함을 확인했다. stock 전체 게이트는 부모 최초 source 도입 증거의 선형 합류 뒤에 수행한다.

### AR-B4 후속 통합 — C6 실행·C7 설정·LangGraph LG-C

검증된 main `0e50e0c` 위에 C7-A `3c0fc4a`(C6 `b643b6b` 포함)를 signed merge `0ff08ea`로 합류하고, LG-C `c3c14c03`의 실제 Routines/runtime 소유를 연결했다. `runtime/resident/execution.py`의 두 import는 기존 단일 LangGraph 구현을 `runtime/resident/context.py`와 `langgraph.py`에서 사용한다. 실행 10정의 본문과 두 source가 독립 추가한 context_reads의 16정의는 원래 AST와 동일하다. 같은 파일 이름 때문에 한쪽 계약을 버리지 않았다.

LG 테스트는 원래 node map을 유지하며 Routines 경로로 옮겨졌고, f751의 AgentRun readiness 1node는 tests/routines/test_execution_readiness.py에만 남긴다. 이전 LG 파일에는 아직 별도 소유인 19정의만 유지한다. 원장 JSON은 실제 3-way base로 병합했으며 원래 symbol별 단일 목적지와 실제 multiple destination의 identity를 구분해 경로 변경·소비자 정렬을 함께 보존했다. 자동 inventory는 index 해결 후 실제 tree에서 재생성했다.

최종 고정 tree의 Routines·LangGraph·Social UoW·Package import 회귀 **460 PASS / 5 warnings / 248.61초**. 현재 경계 **802modules / 2758edges / exactlegacy201**, L4 **802modules / 97parity**, deferred runtime **22files** PASS. 원래 source/split/assertion/suppression/APIORM/node 진단은 모두0오류, **protected2260/current2293**이다. main에 이미 기록된 signed869bae 두 경로의 원형을 확인했으며 새 snapshot을 메모리에 추가하지도 않았다. Frozen/checkpoint/additions는 불변이다. 전체 stock capture/Hosted CI/PR/머지는 parent의 순차 통합 단계이며 이 focused 결과로 승격하지 않는다.

C7-B 이후 실제 활동 관리·HTTP와 B5/B7/Lore/Point 최신 협력, G5/G06은 각각 원래 소유 source에서 합류한다. 미전환 협력은 기존 실제 구현을 유지했고 다른 source의 업무 로직을 복제하지 않았다.


## AR-B4-C7-B — 자율활동 활성화·비활성화

실제 활성화·비활성화·준비 정책 7개를 Routines 서비스로, 전역 transaction lock 1개를 Routines repository로, 원래 두 집합을 합산하는 cross-owner query 1개를 runtime aggregate로 옮겼다. Character.status의 원래 대입 3개는 Character mutations의 동일 객체 대입으로 연결했다. 전역→World 잠금, 이미 활성화된 경우의 반환, credential sync 실패 보상, commit/flush와 rollback 후 거절 로그의 원래 순서는 그대로이다. 원래 9개 본문은 정확한 collaborator/type/status 복원 뒤 AST가 동일하다. 초기 95개 통과 후 SQLite 재시도 mock을 실제 service 위치로 바꿨고 해당 1개와 tendency48 검사는 모두 통과했다. 관리 HTTP와 나머지 provider 실행 조립은 후속 C7 범위이다.

최종 C7-B 관련 176개 통과, 기존 PostgreSQL 환경 1개 skip, 기존 경고 5개를 확인했다. 네 테스트의 원래 namespace를 실제 소유 함수에 명시 바인딩한 뒤 해당 4개도 재통과했다. 원래 assertion AST는 그대로이고 제품 alias나 검사기 예외는 추가하지 않았다. 현재 경계는 775 modules / 2662 edges / exact legacy 202 / cycle 0이다. 기존 여섯 보존 검사의 읽기 전용 진단은 모두 오류 0, 보호 노드 2139 / 현재 2287이다. 선행 도입 원장 연결과 원래 stock gate는 root의 순차 통합에서 처리한다.

### C7-B의 후속 통합 검증

LG-C까지 합류한 `60def90`에 원래 signed C7-B `50d50ed`를 병합했다. 제품 충돌 없이 같은 활성화·잠금·Character 상태 변경 협력을 유지했고, 문서와 symbol별 지도는 양쪽 원래 기록을 보존했다. 실제 통합 tree의 활동 한도·tendency·resident 실행 바인딩 회귀는 **116 passed / 4 warnings / 18.32초**이며 경계는 **806modules / 2784edges / exactlegacy201**, L4는 **806modules / 97parity**다. 원래 첫 도입 소스의 archive 수집은 별도 고정 입력에서 진행 중이며, 아직 원장 append·전체 backend·stock 보존·Hosted CI 완료를 의미하지 않는다.

## AR-B4-C7-C — 수동 실행과 모이 요청

실제 수동 실행·슬롯 안전·쿨다운 10개, 모이 조회·입력·프롬프트 정책 3개, 수동 실행 상수 3개를 Routines로 이전했다. UTC 변환은 기존 동일한 3문장 함수 하나를 재사용했다. 정확한 callback·타입 연결을 원래 이름으로 복원하면 17개 본문/상수가 동일하다. 기존 배정 슬롯/임시 슬롯의 서로 다른 실행, claim 경쟁, provider profile의 cleanup, BaseException 원래 오류 우선순위를 보존했다. 관련 기존 회귀 154개가 통과했고, source inspection 2개도 원래 assertion을 실제 정의 함수로 연결했다. HTTP와 혼합 entry는 후속 C7에서 실제 조립 위치로 연결한다.

C7-C 현재 경계는 777 modules / 2691 edges / exact legacy 202 / cycle0이다. L4는 777/14/97, ER0은 86/87/24/44/7, Memory inventory는 current이다. 원래 보존 진단은 source/assertion/suppression/API·ORM/node 오류0이다. 지도 갱신 때 불필요하게 재계산된 기존 AR-B1/AR-F1의 legacy split metadata 7개를 원래 HEAD 값으로 복구했고, 동일 원래 split 검사도 오류0으로 확인했다. 보호2139/현재2287이며 동결/검사기/additions 변경은 없다. stock 통과는 root의 순차 도입 연결 후 확인한다.

### C7-C의 후속 통합 검증

`339cda2`에 원래 signed C7-C `05691bb`를 병합했다. 수동 실행·모이 요청·활동 한도·tendency·실행 바인딩 회귀 **117 passed / 4 warnings / 18.28초**, 경계 **808modules / 2813edges / exactlegacy201**, L4 **808modules / 97parity**를 확인했다. 처음 검사 명령은 존재하지 않는 `test_run_observations.py` 경로를 지정해 테스트를 실행하지 못했고, 실제 `test_activity_management.py`를 포함한 위 명령으로 수정했다. 선행 C7-B tree에서는 CI 구조·보존 회귀 **209 passed / 21.13초**, public route **196operations**와 Memory·deferred inventory도 통과했다. 이 통합은 원래 소스 증거 수집과 뒤따르는 전체 stock·전체 backend·최종 C7 HTTP 검증을 대신하지 않는다.

### B4 후속 원본 도입 증거 연결

`a93e724`까지 들어온 원래 signed 소스 22개를 각각 독립 Git archive에서 기존 `committed_snapshot`으로 수집했다. 저장한 commit과 tree ID를 대조하고 기존 main `0e50e0c`의 원장 64개를 불변 prefix로 유지한 채, 원래 **91개 파일과 33개 추가 노드**의 증거를 최초 도입 순서대로 기록해 원장을 **64→86개**로 확장했다. 추가 노드의 함수가 처음 정의된 source SHA도 각 기록과 일치했다. 임시 중간 목적지가 뒤의 split 원본이 되는 경우도 그 첫 blob을 기록했다.

원장 쓰기 전 변경 없는 production `checkpoint_errors`와 `addition_errors`가 원래 blob·단언·suppression·첫 source 도입·append-only 이력을 검증해 통과했다. 기준 baseline/checkpoint는 변경하지 않았다. 이후 현재 코드의 전체 stock 보존·전체 backend 및 남은 C7 실제 HTTP/실행 조립 검증은 별도 진행 상태다. DCO·CI 정책·OSS 경계·비밀 예외 metadata25개·컨테이너/launcher/설치/Tauri 개발 계약도 이 통합본에서 통과했다.

### 전체 C7-C 통합 검사에서 확인한 경로 보완

`cf142ac` 전체 backend 실행은 **2269 passed / 22 skipped / 27 warnings / 2 failed / 685.81초**였다. 두 실패는 실제 실행 기능이 아니라 이동된 소스에 대한 검사 연결이었다. L3 경계 검사는 삭제한 `services/langgraph_resident.py` 대신 실제 `runtime/resident/langgraph.py`를 읽는다. 저장 개수 제한 부재 검사는 management의 실제 분리 소유인 `routines/service/autonomy_management.py`도 명시 source group으로 읽어 원래 검사 범위를 유지한다. 실제 파일 내용만 읽으며 원래 금지 문자열·capacity 설정 단언은 모두 그대로다. 수정 후 두 검사 파일은 **11 passed / 7.06초**다.

첫 stock 전체 검사는 보호/current **2293/2293**으로 source/split/단언/suppression/API·ORM/node 손실이 없었으나, G07.test_paths의 옛 tendency 파일 참조 한 건으로 실패했다. 이 한 항목을 이미 검증된 file/node map의 `tests/routines/test_tendency.py`로 연결했다. 원본 node 목록·frozen/checkpoint·원장 내용은 바꾸지 않았다. stock 재검사와 최종 C7/작성 경로 합류 뒤 전체 backend 재실행은 별도 게이트로 남긴다.

`70b238c` 고정 tree에서 stock `--contracts --nodes` 재검사는 **PASS(37items / protected2293 / current2293)**다. 실패 원인인 실제 경로만 보완했으며 원래 단언과 86개 append-only 기록은 그대로다. 최종 C7/작성 책임 합류와 이후 전체 backend·Hosted CI는 계속 진행 상태다.

## AR-B4-C7-D — 첫 인사 정책·실행 기록·provider IO

첫인사 eligibility/claim/result/prompt4, PostgreSQL owner lock1, request/writer DTO2를 실제 Routines 역할로 이전했다. Social.PostDetail을 포함하는 복합 HTTP 응답 DTO1은 api/schemas에 실제 정의하고, 원래 두 생성자를 런타임에서 연결했다. writer/image IO2와 원래 credential resolution try1은 runtime에 두었다. 기존 14개 본문·상수는 원래 추출문을 정확히 되붙이고 callback/type을 복원하면 AST가 동일하다. 관련156회귀가 통과했고, 기존 claim-before-provider source assertion과 실제 PostgreSQL claim 호출은 actual service에 연결했다. 공개 응답 schema와 전체 secret reveal equality 검사도 통과했다. first greeting은 수동 실행과 별개 세션/쿨다운을 유지하며 이미지 실패를 전체 post 실패로 바꾸지 않는다.

복합 응답의 직접 도메인 참조로 발견한 순환은 API 응답 조립과 typed value/factory로 제거했고 경계 예외는 추가하지 않았다. 최종 연결 후 같은 관련156회귀를 다시 통과했다. 현재784 modules / 2735 edges / exact legacy203 / cycle0이다. 추가 legacy1은 원래 image IO가 이동한 정확1 import이며, 이미 별도 작성된 B5 Social image source의 순차합류 때 제거한다. 새 API schema도 기존 모든 schemas 경로의 비밀 필드 검사 범위에 포함된다.

C7-D 최종 원래 six 읽기 전용 진단은 모두 오류0, 보호2139/현재2287이다. API/ORM·원본 assertion·기존 노드가 보존됐고 검사기/동결/additions 변경은 없다. L4 784/14/97, ER0 86/87/24/44/7, Memory current이다. stock 증명은 root의 순차 source introduction 연결 뒤 확인한다.

C7-D `b0a8a8d`를 LG/C7-C 통합본에 병합한 tree는 첫 인사·활동 한도·tendency·경계 회귀 **121 passed / PostgreSQL 환경 18 skipped / 4 warnings / 18.50초**, public route **196operations**, 경계 **815modules / 2857edges / exactlegacy202**, L4 **815modules / 97parity**다. 원래 소스의 archive도 commit/tree ID와 2287개 수집 노드로 확보했다. 기존 split record의 테스트 목록 순서 차이는 목록 내용이 동일한 경우에만 동등하게 판정해 실제 새 policy·credential 두 소유 행을 모두 유지했다. 제품 검사기와 보존 원본은 변경하지 않았다.

## AR-B4-C7-E — 성향 분석 준비·저장·provider 실행

기존 준비7문장과 양쪽 provider의 동일한 설정 저장/로그 부분을 Routines 실제 서비스로 이전했다. Direct/OpenClaw 호출·오류·profile release·slot release는 실제 runtime에 두었다. 원래 함수의 전체 AST는 추출된 두 구간을 되붙이고 callback을 복원하면 동일하며, 원래 오류 class와 tool allowlist도 같은 정의이다. 객체 ID를 선평가하지 않고 원래 붙어있는 User/Character를 전달하여 commit 뒤의 지연 SELECT를 유지했다. result_factory는 원래 마지막 log 인자 위치에서만 평가한다. 실제 SQLite의 Direct/OpenClaw 두 회귀는 setting commit → 만료된 User/Character 조회 → result → log 순서와 별도 connection의 durable 값을 검증한다.

최종 관련 검증은 **68 passed / 기존 경고3 / 28.53초**이다. 현재 경계는 787 modules / 2764 edges / exact legacy204 / cycle0이며 L4 787/14/97, ER0 86/87/24/44/7, Memory inventory는 current이다. 원래 여섯 보존 검사의 읽기 전용 진단은 모두 오류0, 보호2139/현재2289이다. 실제 provider gateway의 정확한 기존 import1은 별도 작성된 Runtime 소유 source 합류 때 연결한다. 원래 frozen/checkpoint/additions는 수정하지 않았으며 stock gate는 root의 순차 도입 원장 연결 후 확인한다.


### B4 후속 통합 — C7-E 성향 결과 소유

원래 signed 2abe379의 실제 성향 결과 정책·provider IO 및 같은 Session의 결과 저장을 합류했다. 신규 direct/OpenClaw SQLite 2노드와 기존 성향·활동 제한·OSS 회귀를 함께 실행하여 **123 passed / 4 warnings / 18.08초**다. 현재 경계는 818 modules / 2886 edges / 203 exact legacy edges다. 원본 도입 archive는 고정됐고 이 단계의 신규 ledger append 및 전체 backend 재검증은 C7 잔여와 Writer 합류 뒤 진행한다. 이전 whole backend 2실패와 수정/stock PASS 이력은 유지한다.
## AR-B4-C7-F — 자격 증명 업무·World 권한·Character HTTP

키와 모델 변경·metadata·삭제·World scope4를 Identity 실제 서비스로 이전하고, 기존 Character 리소스 HTTP3을 Character router에서 직접 연결했다. request schema와 원래 오류도 실제 소유에 두었다. World/WC의 원래 scalar 조회2, Routines의 optional 설정 disable, Character의 한 대입은 각 소유에 있으며 같은 Session으로 호출한다. 전체 원문4함수·HTTP3·DTO/오류 및 추출 SQL/대입은 정확 callback 복원 후 AST가 동일하다. 초기 기존49검사가 통과했으며 신규 SQLite2는 flush된 슬롯과 설정이 최종 commit까지 다른 Session에 보이지 않고, World 처리 실패 시 전체 rollback되는 것을 검증한다. 새 테스트의 필수 auth_profile_id fixture를 보완한 뒤 두 검사가 통과했다. 제품 동작·기존 assertion·원래 오류 순서는 변경하지 않았다.

C7-F 최종 검증은 **80 passed / 기존 경고2 / 19.63초**이다. 경계792 modules /2778 edges / exact legacy204 / cycle0, L4 792/14/97, ER0 86/87/24/44/7, Memory current이다. 두 실제 앱 생성 함수는 같은 typed credential workflow를 연결한다. 처음 runtime.routines에서 Character factory를 역으로 조립하여 드러난 package cycle은 앱 생성의 기존 Character 조립 위치로 연결을 옮겨 해소했다. 경계 예외는 늘리지 않았다. 읽기 전용 원래6검사 모두 오류0(보호2139/current2291), frozen/checkpoint/additions 불변이다. stock gate는 root의 선형 최초 도입 연결 뒤 확인한다.


### B4 후속 통합 — C7-F Character credential 소유

원래 signed 0299586의 실제 credential 업무 4개·HTTP 3개·같은 Session 설정/조회 협력을 합류했다. 두 app factory의 실제 workflow 등록을 유지했다. 신규 commit/rollback 2노드와 기존 성향·활동 제한·OSS 회귀는 **123 passed / 4 warnings / 18.13초**이며 경계는 823 modules / 2900 edges / 203 exact legacy edges다. 이 source의 원본 archive 수집은 완료했고 신규 ledger append와 전체 검증은 남은 C7 HTTP/Writer 합류 뒤 순서대로 수행한다.


B4 C7-D/E/F의 원래 signed 최초 도입 3개 source archive를 순서대로 append했다. 실제 새 source 17개와 새 테스트 4노드의 첫 도입을 Git history에서 확인했으며 원래 production provenance 검증을 통과했다. 기존 main 64개 및 직전 86개 기록은 불변 prefix이고 ledger는 **86 → 89 records**다. frozen checkpoint와 source baseline은 바꾸지 않았다.
## AR-B4 Writer — 작성 정책과 provider·업무 조립의 실제 소유

원래 `services/agent_writing.py`의 29개 함수·클래스 및 5개 상수·타입·logger 정의를 모두 대응했다. 그중 함수·클래스 28개는 Routines의 실제 prompt/result/error 역할과 runtime의 provider·다중 업무 조립으로 이전했다. Memory 이벤트 저장 1개는 이미 고정된 B7 source의 중복 구현을 만들지 않기 위해 원래 파일에 같은 본문으로 남겼다. 정확한 남은 함수·소비자·종료 조건은 소유 지도에 기록했다. 공통 logger 이름, 서울 시간대, 모델·사용량·토큰 제한과 provider 호출 조건을 변경하지 않았다.

원래 34개 정의의 전체 AST를 비교했으며, 실제 동일 nullable 조회 소유 경로와 명시적 문맥 읽기 인자만 복원하면 모두 동일하다. 기존 테스트 4개 파일의 모든 assertion과 suppression도 그대로다. 새 테스트 8노드는 1회 provider 호출, 실행 중 event loop 거절, 같은 Run/Session의 사용량 commit, JSON 검증 전 사용량 기록, Social 게시·답글 저장 뒤 Memory 기록, 원래 Daypart의 날짜·source IDs·단일 commit을 확인한다.

첫 확대 검사에서 신규 fixture가 읽기 전용 Settings property에 대입하여 2개가 실패했다. 제품 코드는 바꾸지 않고 실제 설정 필드 `OPENCLAW_GATEWAY_TOKEN`과 SecretStr를 사용하도록 fixture를 수정했다. 이후 기존 79개와 신규 8개를 함께 실행한 결과는 **87 passed / 2 warnings / 13.34초**다. 현재 경계는 **812 modules / 2833 edges / 200 exact legacy edges**다. 다음 원본 source·assertion·API/ORM·node 보존 검사를 별도로 확인하며, 현재 source 준비 결과를 GitHub 또는 전체 B4 완료로 표현하지 않는다.

이 작업트리는 `cf142ac`에서 분기했으므로 후속 통합의 구조 경로 회귀 2개 수정 `70b238c`를 포함하지 않는다. G07의 실제 tendency test 경로 수정은 같은 값으로 반영하며 원래 test node를 재기준화하지 않는다. 원본 checkpoint·기존 additions 86개는 수정하지 않고 최초 source commit의 archive를 통합 후 순서대로 수집한다.


Writer 최종 고정 tree의 원래 6개 보존 진단은 source·split·assertion·suppression·API/ORM·node 모두 **0 errors**다. 기존 보호 2293 / 현재 2301로 기존 손실 없이 신규 8개가 수집된다. 이 읽기 진단은 source introduction metadata를 만들지 않으며, source commit 뒤 원래 archive를 append한 stock 통합 gate와 구분한다.


### B4 후속 통합 — Writer 실제 정책·provider 조립

원래 signed Writer 3c398f3를 C7-F까지 포함한 tree에 합류했다. C7의 greeting/tendency 상수·오류와 Writer 상수·오류를 각각 보존했고, tendency 테스트는 두 실제 owner의 import를 함께 사용한다. 기존 테스트 4파일의 assertion·suppression과 원문 Writer34 정의 AST를 합류 후 재확인했다. 서로 다른 Community query/service의 정확 legacy edge 두 개가 같은 표시 id를 사용하던 metadata 충돌은 각 full module 이름으로 구분해 해결했으며 edge·소유·종료조건은 바꾸지 않았다.

Writer8신규·credential2·tendency2 및 기존 activity/Daypart/구조경로/OSS를 함께 실행한 결과는 **167 passed / 4 warnings / 20.03초**다. 이전 전체 검사에서 실패했던 L3 실제 LG 경로와 local-capacity 실제 source 묶음 2개 검사도 포함해 통과했다. 현재 경계는 827 modules / 2920 edges / 202 exact legacy edges다. Writer 원본 Git archive2301nodes는 수집했으며 신규 source4파일/testfile1/8nodes의 ledger append와 다음 stock 전체 gate를 별도로 수행한다.


Writer 원래 signed 최초 도입의 5파일/8노드를 순서대로 append하여 ledger는 **89 → 90 records**다. 기존 main64·직전89 불변 prefix 및 원래 provenance checker를 모두 통과했다. 현재 후보의 최종 C7 HTTP/상세 응답 후속은 아직 준비 중이며 전체 backend·최종 stock·GitHub CI는 모두 합류한 exact head에서 진행한다.


### B4 후속 후보 현재 검증 — 30c7e77 source tree

CI architecture 8파일 **209 passed / 13.06초**, DCO, required10/advisory1/workflows8 CI 정책, exact allowlist25, container·launcher·installer·Windows Tauri dev 계약이 통과했다. 현재 Git tree secret scan은 files1880 / binary15 / audit11 / **fatal0**이며 전체 로컬 Git refs 이력 scan은 files9889 / binary26 / audit22 / **fatal0**다. audit 항목은 기존 공개 자산 검토 대상이며 새 비밀 허용 예외를 추가하지 않았다.

현재 상태 표의 AR-B4를 실제 #281 core 병합 및 후속 source 준비 상태로 갱신했다. 마지막 C7 HTTP와 상세 응답 후속의 signed 소스, 후보 전체 backend·stock, GitHub CI·후속 PR/merge는 아직 완료로 기록하지 않는다. 최초 전체 검사 실패 2건과 수정·재검증 이력은 유지한다.
## AR-B4-C7-G — 활동 리소스 HTTP와 실행 연결

Character HTTP9를 실제 Routines service와 typed tendency runner에 직접 연결하고 중간 management 전달9함수를 삭제했다. route 순서·응답 class·상태/detail·오류 순서를 유지했고 원문 HTTP9와 상수/오류 AST가 같다. 남은 management 함수들의 원문 AST도 모두 동일하다. 초기 구조 추출 중 발견된 문법 오류는 원래 source snapshot에서 정확9함수만 제거하도록 수정했고, 이후 기존178회귀가 통과했다. 신규 요청2는 실제 resource route9의 정의 소유와 같은 request Session/인증 객체, durable 설정 및 내부 parse 상세를 숨기는 원래 오류 응답을 확인했다.

검토된 root source `1565688ffa8095b37ec8fb843f5547c6c87705ae`의 정확한 예외 entry 지원만 선행 반영했다. 해당 원본 negative3은 byte 동일한 임시파일에서 기존 partialscope63/HTTP2와 함께68통과한 뒤 임시파일을 제거하여 원래 최초 도입 계보를 보존했다. 새 blanket exception이나 계약 alias는 추가하지 않았다. 실제 Operations 오류 한 클래스만 부분 이전하고 기존 service는 같은 객체를 import한다. root Operations 서비스 source 합류 시 이 정확 bridge가 제거된다.

C7-G 최종 검증은 **245 passed / 기존 경고5 / 32.45초**이다. 현재 경계795 modules /2805 edges /exact legacy204 /cycle0, L4 795/14/97, ER0 86/87/24/44/7, Memory current이다. Social 오류 직접 import로 발견된 Character→Social→WC→Character 순환은 기존 workflow에 원래 오류 class 두 객체를 전달하여 해소했으며 순환 예외를 추가하지 않았다. 정확한 Operations/Routines 오류 entry만 등록한다. 원래 여섯 검사의 읽기 전용 진단은 모두 오류0(보호2139/current2293)이며 frozen/checkpoint/additions는 그대로이다. stock gate는 root의 선형 도입 원장 연결 뒤 확인한다.


### B4 후속 통합 — C7-G 실제 활동 HTTP

원래 signed 6faae3c의 Character 활동 HTTP9·실제 Request/app.state workflow 연결 및 중간 전달9 제거를 합류했다. 원래 위치에 같은 APIRoute를 조립하며 same-Session·오류 catch순서·status/detail을 보존했다. 정확한 exceptions role 허용은 root 최초1565688의 checker 변경만 공유하며 root 신규 negative test파일을 중복 도입하지 않았다.

신규 Request/Session2 및 Writer·성향·credential·기존 Activity/Package/WC/OSS 회귀는 **171 passed / 5 warnings / 36.64초**다. 현재 경계는 830 modules / 2947 edges / 202 exact legacy edges다. C7-H의 실제 활동 log/상세 응답과 잔여 정리, 최종 전체 backend/stock/PR gate는 아직 남아 있다.


C7-G 최초 signed archive의 source3파일/testfile1/2노드를 원래 commit에서 확인하고 순차 append했다. 원장 **90 → 91 records**, 기존 main64·직전90 불변 prefix, 원래 provenance checker PASS다. 후속 H source는 별도 집중/원문 보존 검증 뒤 최종 확대 실행 중이며 이 후보에는 아직 합류하지 않았다.
## AR-B4-C7-H — 활동 표현·가져온 World 실행 제한·최종 실제 소유

활동 로그3·summary 생성식·가져온 World guard를 실제 Routines 서비스로 이전했다. Character/Identity의 nullable 조회는 같은 Session으로 연결하고, 기존 설정/로그 조회도 actual 소유 서비스를 사용한다. 상세 응답 자체는 여러 업무를 조립하는 runtime 책임으로 남는다. 원래 전체 detail 본문은 추출 표현식을 정확히 복원하면 AST가 동일하다. 실행 준비 여부의 원래 None→False도 유지하며 이미 동일한 성향 판단을 재사용한다. 기존 profile readiness 단순 전달 함수는 실제 서비스와 명시적 runtime 협력 연결로 제거했다. 초기 관련118검사/기존PG1skip이 통과했고 원문 AST7이 동일하다. 신규4는 실제 attached 프로필/별도 Session의 미커밋 가시성·rollback, 시간대/댓글/글/좋아요 조회 순서와 원래 필드 평가 시점, 없는 설정의 준비 거절을 검증한다.

현재 호출되지 않는 AgentRun 메뉴/복구4와 old CRUD3은 원문 그대로 보존하며 B8에서 실제 소유에 배치한다. 현재 호출0만으로 기능 삭제를 판단하지 않는다. Memory Daypart7 및 다른 담당자가 이미 작성한 Identity/Character image/LocalBot/Relationships 구현은 root의 선형 합류에서 원래 callback/alias를 actual 소유로 연결한다. 소유가 없는 구현을 일반 runtime 이름으로 옮겨 종료하지 않는다.

C7-H 최종 관련 검증은 **689 passed / 기존 PostgreSQL 조건1 skipped / 기존 경고22 / 265.67초**이다. 최종 검사 동안 제품/테스트 source는 고정했다. 현재 경계798 modules /2817 edges /exact legacy204 /cycle0, L4 798/14/97, ER0 86/87/24/44/7, Memory current이며 원래6검사 읽기 진단은 오류0(보호2139/current2297)이다. 동료 읽기 검토에서도 lazy 평가 순서·같은 Session의 nullable 프로필·World guard4연결에 차단 문제는 발견되지 않았다. 보존할 AgentRun11/CRUD3의 본문도 이전 signed source와 AST가 동일하다. frozen/checkpoint/additions 및 기존 단언은 그대로이며 stock gate는 root의 순차 도입 연결 뒤 검증한다.


### B4 후속 통합 — 최종 C7-H 소유와 잔여 경계

원래 signed c2ceac3의 실제 활동 summary/log presentation과 imported World 실행 guard를 합류했다. 시간대·comment/post/like 수·설정 필드의 lazy 평가 순서, nullable profile의 같은 Session attached 객체, 원래 setting=None 결과를 유지한다. Character 상세 화면의 여러 업무 조립은 runtime의 실제 책임으로 남긴다.

최종 H 담당 source는 기존 관련 **689 passed / PostgreSQL 1 skipped / 22 warnings / 265.67초**이며, 합류 tree의 H4신규·HTTP2·Writer8·credential2·성향2 및 Activity/RoutinePost/OSS 회귀는 **167 passed / 기존 PostgreSQL 1 skipped / 5 warnings / 27.79초**다. 현재 경계는 **833 modules / 2959 edges / 202 exact legacy edges**다.

원래 AgentRun의 Memory7과 서로 다른 dormant 메뉴/복구4, old CRUD의 별도 commit 계약3은 삭제하지 않았다. 각 실제 소유 source와 합류한 뒤 B7/B8에서 처리하며, no-current-caller를 근거로 구현이나 단언을 지우지 않는다. 기존 Social/Relationships/Identity/Lore/LocalBot 협력과 module aliases도 정확한 소비자·소유·제거 조건으로 추적한다. 이 PR은 후속 B5/B6/B7/B8 전체 source를 포함하지 않는다.

C7-H 원본 archive2297nodes는 준비됐고, source3파일/testfile1/4노드의 최초 도입 ledger append 뒤 고정 head에서 전체 backend와 원래 stock 보존을 실행한다. 현재 상태 표는 최종 C7 source 합류 완료와 통합 gate 대기를 구분하도록 갱신했다.


최종 C7-H 원래 최초 도입 4파일/4노드의 순차 append 및 원래 provenance 검증이 완료됐다. ledger는 **91 → 92 records**, main의 기존64와 직전91은 불변 prefix다. 이 metadata commit 이후 파일을 고정하여 전체 backend와 source/API/ORM/단언/suppression/수집노드 stock 검증을 실행한다.

### B4 후속 최종 전체 검사와 HTTP 보안 목록 보정

고정 `71493c5`의 전체 backend 검사는 **1 failed / 2288 passed / 22 skipped / 27 warnings / 726.47초**다. 유일한 실패는 `test_m3_security_harness.py::test_security_inventory_explicitly_covers_every_openapi_operation`에서 C7의 실제 HTTP 소유 이동 뒤 보안 목록의 module이 이전 `app.api.v1.routes.agents`로 남은 불일치였다. 같은 커밋의 stock `--contracts --nodes`는 **PASS: items37, 보호2311 / 현재2311**이며 원래 #258의1867 / #263의1907 및 모든 원래 최초 도입을 보존했다.

실제 route 객체를 대조해 정확한 12개 module 필드만 `app.domains.characters.router`로 변경했다. URL·method·endpoint·access와 다른 필드는 모두 동일하며, public inventory196개도 기존 생성기로 갱신했다. 제품 코드·테스트 source·원래 assertion/suppression·동결자료·92개 원장 기록은 바꾸지 않았다. 원래 실패 M3/M4와 활동 HTTP·관리·성향·credential transaction6파일은 **78 passed / 3 warnings / 15.29초**다.

이 보정은 metadata만 변경하므로 이미 실행한 전체 검사의 실패 이력은 그대로 보존하고, 최종 전체 gate는 PR exact head의 Core backend CI에서 확인한다. local 전체 PASS로 바꾸어 기록하지 않는다. 원래 stock와 inventory를 보정 head에서 다시 확인한 뒤 PR을 생성하며, PR checks·merge·post Actions·Installer gate는 각각 별도 상태다.

### PR #282 — Gitleaks의 원본 Git fingerprint 오탐과 한정 보정

PR #282의 `e20c9d9`에서 Core backend, frontend, architecture-boundary, dependency-license, DCO, embedded migration 검사는 통과했다. `oss-boundary`는 Gitleaks directory 검사에서10개를 감지해 실패했다. 원문 검사기를 재현한 결과 전부 `security/refactor_backend_additions.json`의 실제 파일 Git blob SHA-1이었다. 원래 signed `526a939c`, `f34de9bd`, `2a89dc80`, `0299586c`의 해당 파일 object와10개를 각각 대조해 실제 런타임 비밀이 아님을 확인했다.

기존 방식과 같은 `generic-api-key` 규칙 AND 정확한 additions 경로 AND 전체 key/hash 행 일치만 적용했다. 다른 key/hash·접두/접미 문자열은40개 음성 검증에서 모두 거절되며 원래10개/공백·쉼표 변형20개만 일치한다. 동결·원장·제품·테스트 source·기존 custom scanner25 tuple은 바꾸지 않았다. 동일 Gitleaks8.30.1의 tracked tree 및 HEAD 조상459commits 재검사 모두0 findings이며 기존 scanner/allowlist 회귀는 **23 passed / 2.01초**다. 최종 push head에서 모든 PR checks를 다시 확인한다.
## AR-B5 준비 — Routines C3a 소유 코드 합류

Signed Social `2761e35`에 Routines `6beec5d`를 합쳤다. 활동 로그·기록 모델과 tick timezone의 실제 Routines 소유를 Social의 검색·프로필 활동·Feed에서 소비하도록 연결하고, joint runtime의 RelationshipState를 실제 Relationships 모델로 연결했다. 같은 Session의 호출 순서와 factory의 각 configure 호출 1회를 유지한다. 원본 `agent_runs.py`의 Daypart 모델 본문은 그대로 두고 Point는 Relationships의 동일 class를, 나머지 실행 모델은 Routines의 동일 class를 등록한다.

집중 검증 **232 passed / 기존 warning 1 / 106.03초**. 첫 collection은 새 joint adapter의 옛 모델 경로 1건을 발견했으며 실제 소유 import만 수정한 뒤 같은 검증을 통과했다. API·응답 스키마·ORM는 PR258/263과 동일하며 변경된 보호 테스트 14개 파일의 assertion과 전체 기존 split evidence가 모두 통과했다. 구조 검사는 **727 modules / 2,472 edges / exact legacy 218**로 통과했다. 현재 L4(727/97)·ER0(Postgres83/migration87/Neo4j24/Next44/parity7) inventory를 재생성했으며 frozen baseline/checkpoint/additions는 변경하지 않았다. Source capture·Hosted CI·installer 및 전체 B5 완료는 부모의 후속 선형 통합에서 검증한다.


## AR-B5-C3-A1 — 활동 실행의 동일 Session 연결 협력

`routines/service/public_action_executions.py`가 기존 nullable `Session.get`와 `social_event_id` 한 필드 대입을 실제 소유한다. Relationships runtime은 기존 오류 판정과 마지막 flush를 계속 담당한다. 추가 검증·commit·flush·값 복사 없이 원래 attached 객체를 전달하며 이후 이벤트 workflow 이전에서 이 계약을 재사용한다. 기존 signature/create/finish는 B4-C4 소유로 별도 전환한다.

집중 검증 **14 passed / 13.15초**. 신규 2개 parameter node는 실제 SQLite와 두 Session으로 정상/조회 실패 주입을 검사한다. 기존 성공 실행 ID를 FK evidence로 유지하고 reader가 없는 레코드를 읽도록 제한적으로 주입하여 원래 `execution_evidence_invalid` 분기를 검증한다. 대입 함수는 SQL을 추가하지 않고, 외부 Session에서는 미커밋 event/link를 볼 수 없으며 caller rollback 뒤 event/evidence/outbox/link가 전부 되돌아간다. 기존 12개 SocialEvent 회귀의 assertion은 변경하지 않았다. Source 도입 capture는 부모의 선형 통합 단계에서 진행한다.


## AR-B5-C3-B — 성공 이벤트의 실제 업무 흐름과 소유별 근거 조회

`relationships/service/events.py`가 event admission·idempotency replay·evidence·상태 변화·outbox·실행 연결의 원래 순서를 소유한다. 재실행 3개 SQL은 자체 repository, 근거의 존재/범위 조회 흐름은 service/evidence, 순수 공개 판단은 policies/events로 분리했다. WorldCharacter 서비스는 기존 active/member 검사와 actor FOR UPDATE를 소유하며, World의 기존 nullable 조회와 Social의 unfiltered Post/숫자 source/상호 차단 및 Routines의 Joint/Execution 조회를 runtime의 같은 Session collaborator가 연결한다. 기존 runtime entry는 이 Session 조립만 담당한다.

기존 event 함수와 replay SQL 3개·상호 차단 SQL·WC 검증/잠금·공개 근거 판단·source 분기 등 **8개 AST 계약**은 정확한 소유 함수 호출만 원래 표현으로 확장했을 때 동일하다. 기존 성공 source/관찰/NO_ACTION·delta 상한·원본 삭제·projection replay·수동 요청·공동 활동의 집중 검증은 **57 passed / 기존 warning 1 / 34.76초**다. 신규 owner 협력 2개 node는 재실행도 현재 membership을 먼저 검사하며 actor만 잠그고, 이후 동일 idempotency가 확인된 경우에만 evidence 읽기를 생략한다는 순서를 실제 SQLite에서 검증한다. 첫 collection의 타입 import 누락을 수정했고, 테스트 경로 오타로 1회 no-tests 종료 후 확인한 실제 파일 목록으로 실행했다.

API·응답 스키마·ORM는 PR258/263과 동일하고 기존 보호 테스트의 assertion은 변경하지 않았다. 실제 composition wrapper를 유지한 두 이전 split 기록의 목적지를 보완했다. Root가 별도로 발견한 Memory fixture의 Post+관찰 동시 add 문제도 production constructor를 감사했다. 현재 유일한 `claim_feed_observations`는 기존 관찰 SELECT 다음 `begin_nested()`의 선행 flush 뒤 observation을 add/flush하며, Post+observation 동시 add_all을 하지 않는다. 모델/FK/transaction 의미를 변경하지 않고 fixture가 이 선행 조건을 표현하도록 root에서 검증한다. Source capture·Hosted CI·전체 B5 종료는 후속 통합에서 수행한다.

C3-B 최종 구조 검사는 **734 modules / 2,500 edges / exact legacy 217**, 변경된 event split 기록 3개와 L4·ER0 current inventory가 통과했다. 다른 full split 기록은 직전 검사에서 오류가 없었고 이번 정정은 이 3개 기록에 한정된다.


## AR-B5-C4-A — 활동 제안 값·오류·자체 조회·문구 규칙

원래 activity_proposal_runtime의 상수 7개·오류·결과 dataclass 3개·자체 조회 3개·daypart marker/문구 판단과 기존 동일 UTC 함수를 실제 Relationships 역할 경로로 연결했다. **17개 정의 AST 동일**이며 외부 Joint ORM 반환 타입만 attached 값의 read-only 구조 계약으로 표현한다(객체를 변환하거나 복사하지 않는다). 나머지 제안 생성·응답·일정 workflow는 C4B에서 소유 이전하며, 원래 서비스의 6개 정확한 임시 import만 다음 단계 제거 조건과 함께 기록했다.

집중 검증 **19 passed / 14.61초**. 기존 Proposal·SocialEvent·공동 실행의 assertion은 변경하지 않았고 신규 node는 없다. Source capture/Hosted CI와 전체 B5 종료는 후속 단계다.


## AR-B5-C4-B — 제안 생성·응답·예약의 실제 업무 소유

Relationships `service/proposals.py`가 제안 한도·cooldown·preview·발행·일정 탐색·수락·거절·역제안의 원래 흐름과 상태 변경을 소유한다. 자체 Proposal/evidence 조회는 repository로 분리하고, Joint 조회는 Routines repository에 두었다. World/Social/Routines의 실제 함수는 `runtime/activity_proposals`가 같은 Session으로 연결하며, 각 Routines 호출의 기존 JointReferences 생성 시점도 유지한다. 기존 `services/activity_proposal_runtime.py`는 제거했고 caller 5개를 실제 runtime 구성에 연결했다. C4-A의 정확한 임시 bridge 6개도 모두 종료했다. 기존 Proposal 테스트 5개는 `tests/relationships/test_activity_proposals.py`로 옮겨 실제 소유와 일치시켰다.

기존 업무 흐름 **6개와 SQL 5개 AST**는 정확한 소유 함수 호출만 원문으로 확장하면 동일하다. 최초 새 transaction test는 datetime fixture의 인자 타입 오류 2개를 수정했고 제품 코드나 기존 assertion은 바꾸지 않았다. 수정 후 신규 정상/예약 직후 실패 주입 2개를 포함한 집중 **21 passed / 21.13초**, 수동 요청·삭제·projection까지 **47 passed / 기존 warning 1 / 31.39초**를 확인했다. 실제 2개 Session에서 같은 attached Proposal을 예약에 전달하고, 예약을 만든 직후 실패해도 caller rollback으로 제안·Joint·참가자·근거를 함께 되돌린다.

구조 검사가 `runtime.relationships`와 `runtime.routines`의 역방향 조립 의존을 발견했다. 제안+예약 상위 조립을 독립 `runtime/activity_proposals`로 분리하여 각 runtime에 대한 의존을 단방향으로 만들었다. 검사 예외를 추가하지 않았으며 최종 **740 modules / 2,517 edges / exact legacy 214 / cycle 0**으로 통과했다. 경로 정정 뒤 같은 집중 **21 passed / 24.32초**, 변경된 Proposal split 2개도 통과했다. API·응답 스키마·ORM는 PR258/263과 동일하고, 이동한 보호 test assertion과 full split 역시 정정 전 검증에서 오류 0이었다. 최종 source 도입/전체보존/Hosted CI/installer는 부모 선형 통합에서 별도로 검증한다.


## AR-B5-C5-A — Outbox 상태 전이와 World readiness 조회

기존 SQLAlchemy outbox의 claim/finalize 실제 업무는 Relationships `service/projection_state.py`, claim 후보/World 집계/nullable row 조회는 repository, GraphOutboxCounts는 contracts가 소유한다. 원래 runtime/sqlalchemy_state.py는 제거하고 실제 consumer 5개를 역할별 구현에 연결했다. 같은 Session·claim flush·finalize의 caller commit·rebuild 제외·정렬·batch bound·skip_locked·owner 검사·retry/dead 전이 순서를 유지한다. canonical SQLite CAS 구현은 이 source에서 바꾸지 않고 다음 책임 전환 대상으로 둔다.

원문 **6개 실제 body/query 계약 AST 동일**, 집중 **37 passed / 기존 PostgreSQL 연결 gate 1 skip / 21.94초**. 새 transaction node는 SQLite에서 이 Session 기반 구현의 claim/재시도 rollback과 stale owner 차단을 검사한다. 이 테스트를 PostgreSQL skip_locked 동시성 검증으로 표시하지 않는다. canonical SQLite의 기존 10-worker claim/reclaim 회귀도 함께 통과했다. 기존 테스트 assertion은 바꾸지 않았고 source capture/Hosted PostgreSQL gate/전체 B5 종료는 부모 통합에서 수행한다.

C5-A 최종 경계는 **741 modules / 2,520 edges / exact legacy 213**으로 통과했고 API·응답 스키마·ORM는 PR258/263과 동일하다. 변경된 보호 테스트 2개 파일의 assertion과 전체 기존 split evidence도 오류 0이며 L4·ER0 current inventory를 갱신했다.


## AR-B5-C5-B — canonical SQLite lease 정책과 CAS의 실제 소유

Relationships service가 원래 worker/batch/시간 검증·lease·retry/dead/cancel 정책을, repository가 원래 candidate SELECT·rebuild 제외·정렬·UPDATE CAS를 소유한다. Runtime은 기존 engine·retry policy와 `run_sqlite_immediate` executor를 그대로 가진다. 동일 callback 안에서 조회→판단→CAS가 진행되며 BEGIN IMMEDIATE/commit/rollback/재시도 범위는 바꾸지 않았다. 기존 TTL 60초와 UTC 함수는 동일 canonical 정의를 사용한다.

기존 class의 constructor·load_command·_write를 포함한 **10개 policy/SQL/executor AST 계약이 동일**하다. 실제 10-worker claim/reclaim 및 scheduler/projector 경쟁·worker 실패/종료·명령/replay 집중 회귀는 **37 passed / 19.31초**다. 기존 assertion이나 신규 test node는 변경하지 않았다. B5의 mutable feature navigation도 실제 이동 경로에 맞췄으며 frozen baseline/checkpoint/additions와 기능 완료 상태는 유지한다. Source capture/Hosted CI/installer 및 잔여 command/replay/observation·Social agent/media 전환은 후속 통합과 slice에서 진행한다.

최종 canonical TTL 연결과 실제 트리의 같은 회귀도 **37 passed / 17.82초**이며, 경계 **743 modules / 2,529 edges / exact legacy 213**, API·응답 스키마·ORM 및 전체 split evidence 오류 0을 확인했다. L4·ER0 current inventory도 통과했다.


## AR-B5-C5-C — canonical source 기반 명령·서명·범위 판단

Relationships가 payload 버전/서명/형식, source 적격성·삭제/숨김, 관계 방향과 replay snapshot의 실제 판단을 소유한다. 자체 event/relationship/evidence 조회는 repository, WorldCharacter의 원래 nullable 조회와 membership World 확인은 해당 서비스, Social Post는 기존 unfiltered owner query에 연결했다. Runtime은 caller Session을 전달하며 별도 Session·flush·commit을 만들지 않는다. 비활성 membership도 과거 관계 복구에 사용할 수 있었던 기존 의미를 active-author 정책과 합치지 않았다.

원래 **11개 정의와 nullable 조회 2개 AST 계약이 동일**하며, 집중 **47 passed / 14.94초**다. 기존 Command 테스트 7개 node를 `tests/relationships/test_projection_commands.py`로 이동하고 workflow/ER0 실제 소비자와 정확 node 지도를 갱신했다. 새 3개 node는 같은 Session·attached identity·숨김 pending write 감지·caller rollback·inactive 과거 membership 허용 및 missing/다른 World membership을 target 조회 전에 차단하는 오류를 검증한다. 첫 추출 실행은 이미 존재하는 동일 source-exclusion 상수를 확인해 정지했고, 중복 정의 대신 기존 같은 값에 연결한 뒤 진행했다. 기존 assertion/DDL/frozen 승인 범위는 변경하지 않았다. Source capture와 전체 B5/Hosted CI/installer는 후속 통합에서 검증한다.

C5-C 최종 경계는 **748 modules / 2,545 edges / exact legacy 212**이며 더 이상 필요 없는 runtime→global models 예외 1개를 종료했다. PR258/263 API·응답·ORM와 full split evidence가 통과했고, 옮긴 기존 7개 node의 assertion/parametrize 계약도 직접 동일 비교했다. L4·ER0 current inventory가 통과했다.


## AR-B5-C5-D — replay lease·high-water·완료 감사와 source 조회

Relationships의 service가 생성/시작/lease 갱신/실패/성공 다섯 실제 상태 흐름을, repository가 active-run·source·잠금·high-water·정렬·dead·nullable 조회를 소유한다. 기존 ReplayStore는 canonical projection parent를 참조하는 같은 계약, GraphReplayError는 같은 오류 본문이다. World의 정렬된 식별자와 Relationships의 정렬된 outbox ID도 각각 실제 소유에 두었다. runtime의 Session 생성·clock 호출 위치·sidecar 실행·metrics 및 예외 순서는 그대로 유지한다. 생성은 flush-only, start/renew/finalize의 명시 commit/refresh 의미도 원래와 같다.

원문 replay **5개 정의와 SQL 10개 및 outbox class 3개 AST 계약이 동일**하다. 집중 **39 passed / 18.74초**이며 기존 high-water 재개·delta tail 보존·삭제 원본 관계 복구·parity fail-closed·10-worker claim 경쟁을 유지한다. 새 node 없이 기존 replay 6개를 업무별 tests 경로로 옮겼으며 workflow/ER0 소비자와 full split 지도를 같이 갱신했다. 소유 코드에서 전역 model aggregate를 읽던 정확한 임시 edge 2개를 종료했다. Source capture/Hosted CI/installer와 잔여 Social/Relationship read·observation 전환은 부모 통합 및 다음 slice에서 진행한다.

C5-D 최종 경계 **751 modules / 2,558 edges / exact legacy 210**, API·응답·ORM 및 full split evidence 오류 0을 확인했다. 이동한 기존 replay 6개 assertion도 직접 동일 비교했으며 최종 경로의 replay·구조 집중 **18 passed / 2.59초**다. L4 current inventory에서 옛 테스트 경로 한 건을 발견해 실제 policy 경로만 전환한 뒤 parity 97개를 유지하여 통과했다. ER0 current inventory도 통과했다.


## AR-B5-C6-A — 진단 응답·오류와 실제 소유별 조회

기존 canonical 진단 조회 다섯 개를 Relationships repository, Joint/participant 조회 하나를 Routines repository로 이전했다. join/행배수·방향·정렬·limit·참가자별 후속 조회를 그대로 보존하고 옛 혼합 repository 모듈을 제거했다. 진단 응답 여덟 class와 오류 세 class도 Relationships가 실제 소유한다. JointActivityRead는 진단 화면의 기존 투영 응답이며 실행 ORM/쓰기 소유는 Routines에 남는다. 전역 schema는 같은 class를 내보내는 정확한 임시 alias로 추적하며 runtime의 나머지 진단 workflow는 다음 C6-B에서 옮긴다.

원문 **17개 정의/조회 AST 동일**, 기존 사건/World격리·현재 source 공개·소유 진단/그래프/replay 집중 **24 passed / 12.23초**다. 새 node나 기존 assertion 변경은 없다. Routines 담당과 실제 새 query 경로가 겹치지 않음을 확인했다. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.

C6-A 최종 경계 **752 modules / 2,562 edges / exact legacy 208**과 API·응답·ORM 및 full split evidence 오류 0을 확인했다. 단일 목적지 schema 이동은 full split 대신 실제 파일 이동 map으로 명시했다. 임시 bridge의 정확 target 필드도 검사 규약에 맞췄으며 검사 예외를 넓히지 않았다. L4·ER0 current inventory가 통과했다.


## AR-B5-C6-B — 소유 진단 workflow와 Relationships HTTP

Relationships가 진단 소유권·현재 evidence source 상태·공개 응답·graph 비교 순서를 실제로 소유한다. Character nullable get, WC의 같은 next(query)/membership 확인, Social block/Post, Routines Joint 조회와 runtime graph gateway를 같은 Session collaborator로 연결했다. 기존 nullable/read 순서·반응 없는 source·World 격리·차단·삭제/숨김 의미와 clock 위치를 유지하며 별도 commit을 만들지 않는다. 진단/관계 그래프 HTTP 두 개도 실제 Relationships router로 옮겼고 옛 world_activity_runtime는 Routines와 Relationships router의 prefix/tags/등록 순서 조립만 남는다. main/public_main에는 reader factory 구성을 각각 한 번 연결했다.

원문 진단 **4개 및 HTTP 4개 정의 AST 계약이 동일**하다. 첫 검증은 새 test가 hosted factory의 startup 전 runtime_settings를 항상 존재한다고 가정한 1건 때문에 28 PASS/1 FAIL이었다. 제품의 기존 fallback을 그대로 두고 새 test가 실제 전역 fallback과 요청 설정 교체를 확인하도록 고친 뒤 **29 passed / 기존 warning 1 / 17.01초**를 확인했다. 새 HTTP 두 node는 두 factory 등록/같은 객체 설정과 Session, 실제 200 응답/403·404 오류/깊이 422/disabled graph fallback을 검증한다. 기존 assertion은 바꾸지 않았다. Source capture/Hosted CI/installer와 잔여 Social·observation 전환은 후속 통합에서 수행한다.

C6-B 최종 경계 **758 modules / 2,586 edges / exact legacy 205**와 PR258/263 API·응답·ORM 및 전체 split evidence 오류 0을 확인했다. 외부 공개 entry에는 service/schema/contract만 등록하고 router/dependencies는 실제 검사 module과 정확한 기존 API 조립 bridge로 구분했으며 경계 검사를 완화하지 않았다. L4·ER0 current inventory도 통과했다.


## AR-B5-C7 — 실제 관찰 receipt·관계 상태·outbox 소유

Relationships가 관찰 원본 적격성·방향·중복 receipt·친숙도 1 증가·outbox 저장을 실제로 소유하고 자체 SQL을 repository로 분리했다. 기존 성공 source를 또 만들거나 affinity/trust/tension을 추론하지 않는다. WC의 실제 active scope 서비스와 Social의 nullable Post/원래 LIMIT 1 양방향 block query를 같은 Session으로 연결했다. 잠금·읽기 순서·flush·caller commit/rollback을 보존하며 동일한 시간/snapshot/clamp/outbox 중복 query는 기존 canonical 구현을 공유한다.

기존 관찰·SQL·공유 정책·WC 검증 12개와 남은 source writer 13개 AST 계약이 동일하다. 첫 범위 회귀는 관찰 추출 중 남은 source 작성이 사용하는 UTC import를 제거한 오류로 30 PASS/10 FAIL이었으며 원래 import를 복원했다. 기존 assertion을 바꾸지 않고 최종 **44 passed / 기존 warning 1 / 22.74초**를 확인했다. 추가 네 node는 같은 Session/attached 객체/lock→Post→target→block 순서와 실제 caller rollback, 비활성 observer·membership 및 역방향 block을 관계 저장 전에 차단하는 동작을 검증한다. Source capture/전체 B5/Hosted CI/installer는 후속 통합에서 검증한다.

C7 최종 경계 **762 modules / 2,607 edges / exact legacy 205**, PR258/263 API·응답·ORM 및 전체 split evidence 오류 0을 확인했다. 전체 원문 분할 지도에는 임시 runtime export의 `__all__`도 포함했고 검사 규칙을 완화하지 않았다. L4·ER0 current inventory도 통과했다.


## AR-B5-C8-A — 성공 source·evidence와 Social 중복 쓰기 기반

Relationships가 source 성공 기록과 evidence digest/저장 두 flush를 실제로 소유한다. `audit_only`와 stage failure injection 순서를 그대로 유지하며 관찰·관계 delta·projection을 추가하지 않았다. Social의 입력 digest·기존 ledger 검증·공개 root 정책 및 candidate 조회도 실제 역할로 이전했다. 기존 runtime UoW는 원래 함수 객체를 직접 호출하며 다음 단계에서 남은 전체 쓰기 정책을 이전한다. 원문의 실제 source 본문/SQL과 기존 runtime 나머지 정의를 비교하고 기존 동시성·중복·실패 롤백·provider-free 회귀를 검증했다. 새 test node나 보호 assertion 변경은 없다. Source capture/전체 B5/Hosted CI/installer는 후속 통합에서 검증한다.

C8-A 집중 **31 passed / 기존 warning 1 / 16.80초**다. 이전한 다섯 함수 본문(ledger SQL 복원 비교 포함)과 남은 runtime 아홉 정의를 원문과 동일 비교했다. 최종 경계 **767 modules / 2,620 edges / exact legacy 205**, API·응답·ORM·전체 split evidence와 L4·ER0 current inventory도 통과했다.


## AR-B5-C8-B — Social 실제 source 작성 정책과 runtime 트랜잭션 분리

SocialSourceWriteService가 수동/자율 actor·target 허용, idempotency replay, 실제 Timeline 호출, source/evidence·inbox 후보 순서, 최종 응답을 소유한다. Runtime은 기존 BEGIN IMMEDIATE/timeout 복원/재시도·최종 commit을 그대로 유지한다. WC nullable query와 Character/Identity/membership 및 Relationships source 쓰기는 같은 caller Session의 typed references에서 연결한다. 각 조회의 원래 시점과 nullable 결과, 객체 identity를 유지하며 불필요한 조회/사전검증/commit을 추가하지 않았다.

실제 정책·helper·executor 15개 AST와 기존 관찰 composition class 본문이 동일하다. 먼저 기존 집중 **34 passed / 17.58초**를 확인했다. 추가 source ownership 회귀는 생성 시 조회 없음, BEGIN 이후 같은 Session/attached row, source evidence의 audit_only·관계/graph 없음, 요청당 최종 commit 1회와 replay 중 source 재생성 없음을 검증한다. 기존 assertion은 유지했다. Source capture/전체 B5/Hosted CI/installer는 후속 통합에서 검증한다.

C8-B 최종 집중 **35 passed / 기존 warning 1 / 19.61초**, 경계 **771 modules / 2,638 edges / exact legacy 203**다. Runtime executor의 전역 ORM/옛 Community 서비스 임시 edge 두 개를 종료했다. PR258/263 API·응답·ORM와 전체 split evidence, L4·ER0 current inventory도 통과했다.


## AR-B5-C9-A — 임시 Social ORM aggregate 종료와 실제 소비자 연결

행동이 없는 `_SocialPersistenceModels`와 instance export를 제거하고 실제 다섯 runtime 소비자가 각 소유 도메인의 같은 ORM 클래스를 직접 import하도록 전환했다. 프로필/Today/선언된 자기 설명/Memory 근거의 SQL·암호화 cursor·bounded query·공개 범위 로직은 바꾸지 않았다. 다섯 소비자와 남은 read adapter의 31개 완전한 정의를 import 이름 정규화 후 원문과 동일 비교했다. Memory의 이 branch `sqlalchemy_source_reader.py` import 수정은 root A10/A12 통합 시 실제 `source_queries.py`로 연결하며 Memory 실제 service에는 ORM을 추가하지 않는다.

처음 집중은 **43 PASS/1 FAIL**이었다. 실패는 root가 이미 확인한 기존 Memory fixture의 Post+observation add_all 시 observation INSERT가 먼저 실행된 FK 오류로, 실제 reader 호출 전이었다. 원래 FK/DDL/assertion을 유지하고 fixture만 Post add→flush→observation add 순서로 명시했다. Production은 기존 source 조회 및 begin_nested pre-flush 후 observation을 저장하며 정책을 변경하지 않았다. 신규 node는 없고 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.

C9-A 최종 집중 **44 passed / 기존 warning 1 / 9.36초**, 경계 **771 modules / 2,651 edges / exact legacy 203**다. 변경한 기존 fixture의 보호 assertion은 모두 동일했고 PR258/263 API·응답·ORM·전체 split evidence 및 L4·ER0 current inventory가 통과했다.


## AR-B5-C9-B — 수동 World 피드·스레드 실제 조회 책임

원래 6개 읽기 정책은 Social service, 원래 4개 Social SQL은 repository, active WC/Character/membership의 동일 join은 runtime references로 나누었다. 같은 Session에서 owner→WC→Character→membership 조회 순서와 profile capability 판단, 공개 root/reply 정렬·한도·오류를 유지한다. 원래 읽기는 User를 별도로 읽지 않으며 `owner_membership_inactive`를 사용하므로 작성 정책의 추가 검증/다른 오류를 재사용하지 않는다. Runtime의 기존 두 entry는 실제 service와 구체 references를 조립한다.

SQL·협력 호출을 원문으로 확장한 **6개 정책 AST 동일**. 기존 집중 **13 PASS/7.03초**, 새 동일 Session/조회 순서/변경 관찰/commit 없음 회귀 포함 **14 PASS/8.83초**. 신규 1개 node는 호출자의 미commit Character moderation 변경이 profile capability에 반영되지만 기존 feed 결과를 새로 필터하지 않고 rollback으로 복원됨을 검증한다. 모든 기존 assertion은 유지했다. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.


## AR-B5-C10-A — 이미지 프롬프트·결과·quota 실제 정책

원래 35개 정의/상수를 Social의 실제 contracts/schema/프롬프트 service/quota service/오류/결과 정책으로 나누었다. Character 모델 import 대신 읽는 prompt 사실만 정의한 구조적 계약을 사용한다. 날짜별 사용량과 service 무료 quota 정책은 원래 Social media SQL과 같은 settings·APP_TIMEZONE 객체를 쓰고 lock/count/예약/commit/refresh/종료 순서를 유지한다. 원래 provider 호출·Character 설정 저장은 다음 실제 workflow 단계에서 연결하며 전역 Operations 설정을 Social로 옮기지 않는다.

기존 이미지/provider/Local Bot 집중 **72 PASS/5.67초**. 신규 실제 SQLite quota 회귀는 KST 자정·naive UTC 입력·한도 초과 시 추가 commit 없음·release 후 미사용·attached는 사용량 유지와 기존 commit 횟수를 검증한다. 최종 **73 PASS/6.06초**, 기존 assertion 수정 없음. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.

C10-A 최종 확인: 원래 57개 모든 함수/class 본문 동일, API/schema/ORM·기존 assertion·전체 split evidence PASS. 경계 780 modules / 2690 edges / legacy 202, L4/ER0 PASS.


## AR-B5-C10-B — 이미지 queue 상태·처리 정책과 워커 연결

claim/stale/완료 3개 원래 상태 정책을 Social service로 이동하고 기존 PostgreSQL skip_locked·정렬·limit 및 stale cutoff query는 repository로 나누었다. 워커의 실제 Character/Post 검사→prepare→attach→finish 정책도 같은 service에 두며 원래 Session 생성/시각 계산/취소/실패 로그/대기 loop는 worker에 유지한다. Character는 같은 Session의 nullable 실제 소유 조회를 callback으로 연결하며 Social은 외부 ORM에 의존하지 않는다.

원래 query를 확장한 상태3·처리1 AST 동일. 신규4 node는 실제 worker를 통해 claim commit 이후 attached Character/Session/처리 시각, 제거된 Character/Post에서 provider0, 최종 commit·실패, stale cutoff의 strict < 및 조건부 commit을 검증한다. 기존 이미지/quota/provider/Local Bot 포함 **77 PASS/9.23초**. 기존 assertion 변경 없음. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.


## AR-B5-C10-C — 이미지 첨부·reference·실패 결과 책임

실제 첨부2/reference6/provider 실패 결과2 정의 본문을 그대로 Social 서비스에 이전했다. 저장 기술은 기존 Social media storage가 처리하고, 수락된 결과를 PostMedia와 quota에 어떤 순서로 기록하는가는 attachment service가 판단한다. 미디어 참조 판단은 공개 URL만 읽는 구조적 계약을 사용하며 외부 ORM을 import하지 않는다.

최종 집중 **79 PASS/22.03초**. 신규2 parameter node는 실제 DB에서 저장 성공 시 media commit→quota attached commit, 저장 실패 시 media 없음·quota failed commit과 원래 변환 크기/품질 전달을 확인한다. 기존 assertion과10개 원래 함수 본문 동일. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.


## AR-B5-C10-D — 실제 이미지 요청·생성 준비 정책

원래 request/prepare/model·mode/허용 7개 정의를 Social service로 옮겼다. Character 설정/비밀/운영 설정/LLM/활동 로그는 기존 구현을 같은 Session의 명시적 협력으로 제공한다. Service는 기존 provider integration을 호출하지만 외부 ORM과 옛 services/CRUD 모듈을 직접 사용하지 않는다. 동일 BotImageRequestRead class와 provider 실패/작업량/processing 시각/참조 fallback 의미를 유지한다.

원래7 정책의 협력 호출을 확장한 AST 및 남은11 정의 본문 동일. 첫 생성 코드의 keyword 배치 문법 오류를 compile 단계에서 수정했다. 집중에서 원래 positional fake callback을 keyword로 바꾼 차이와 이전 quota monkeypatch 대상을 확인해 호출 형식과 실제 새 대상만 바로잡았다. 신규 request fixture는 Post당 job unique 제약을 유지하며 서로 다른 두 Post에 요청해 queued가 다음 요청 한도에 반영되는지를 검증한다. 기존 assert·DB 제약을 변경하지 않았다. 신규1 node는 실제 same-Session 설정·동일 응답 class·요청 AI0·queued job 집계와 commit을 확인한다. 전체 B5/source capture/Hosted CI/installer는 후속 통합에서 검증한다.

C10-D 최종 집중 **80 PASS / 28.12초**. 원래7 실제 정책 확장 및 남은11 본문 AST 동일, API/schema/ORM·기존 test1 assertion·전체 split evidence PASS. 경계 787 modules / 2727 edges / legacy 200, L4/ER0 PASS.


## AR-B5-C10-E — 시각 정체성 캐시·응답 검증·참조 선택

원래4 정책을 Social 실제 service로 이전했다. Credential 해석과 raw LLM 요청2는 concrete runtime binding에 남고 Social은 동일 출력 schema로 검증한다. Character 저장은 원래 strip→hash 대입→commit→refresh→return5문장과 같은 attached Session을 유지한다. 별도 Character owner source의 실제 repository 함수에 선형 통합할 callback을 준비했으며 ORM/동일경로를 복제하지 않았다.

원래4 정책을 협력 호출로 확장한 AST, raw LLM2 본문, owner write5문장, 남은 정의 본문 동일 PASS. 새 SQLite3node는 정상 저장/observer 가시성·cache provider0·unusable/empty/invalid 응답의 저장0/추가 commit0을 검증한다. 기존 image 및 OSS 경계 집중 **68 PASS / 33.75초**. 기존 테스트의 monkeypatch 실제 대상 및 plaintext reveal의 정확 client 함수명만 바꿨으며 assertion과 strict allowlist 비교는 보존했다. 전체 B5/source capture/Hosted/installer 완료를 뜻하지 않는다.

API/schema/ORM·기존 protected test2 assertion·전체 split evidence PASS. 경계 **788 modules / 2733 edges / legacy 200**, L4/ER0 PASS. 별도 Character owner source `734492bf6551fdb5dea24d2b9140e4ac2d97ef18`의 `repository/image_settings.store_image_visual_identity`에 같은 callback을 연결하는 선형 통합이 남아 있다.


## AR-B5-C10-F — 이미지 실행 조립·워커의 실제 runtime 소유

업무 판단을 앞선 C10-A~E에서 분리한 뒤 남은 concrete runtime15 정의와 worker2 정의를 `runtime/social`로 옮겼다. 각 본문 AST는 원문과 동일하다. 사용하지 않는 private wrapper4와 정책/상수/모델을 모아 재수출하던 import를 제거했다. LocalBot/Character/LangGraph는 동일 이미지 workflow를, 첨부·quota 종료는 실제 Social image_attachment를 호출한다. 기존 테스트 역시 실제 prompt/reference/constants/credential/provider 소유자를 사용하고 plaintext reveal의 정확 파일 경로를 전환했다.

기존 image/LocalBot/provider 보안/OSS 및 실제 SQLite 회귀 **91 PASS / 26.26초**. 새 테스트 노드는 없으며 기존 assertion을 유지한다. Character 설정·visual write, Operations, DirectLlm 및 공통 이미지 문구 정책의 독립 선행 source는 최종 선형 통합에서 canonical import로 연결한다. 현재 혼합 image 테스트는 Character 설정/외부 provider/공통 키/Social 사례가 섞여 있어 전체를 Social로 잘못 분류하지 않고 G07 실제 소유별 분리 대상으로 기록했다. 전체 B5/source capture/Hosted/installer 종료는 아니다.

보존 검사는 기존 assertion의 receiver 이름도 보호하므로 5개 기존 테스트에서 그 이름을 현재의 실제 정책/상수 모듈에 대한 local import alias로 유지했다. 제품 재수출을 되살리지 않았고 assertion을 삭제·완화하지 않았다. 이동 지도 갱신 중 무관한 역사 split 설명을 재계산한 변경은 검사에서 발견해 원본으로 복구했다. 최종 집중 **91 PASS / 31.19초**, API/schema/ORM·protected test3 assertion·전체 split evidence PASS. 경계 **788 modules / 2726 edges / legacy 197**, L4/ER0 PASS.


## AR-B5-C11-A — 프로필의 암호화 커서 소유

원래 runtime profile reader에서 cursor3함수·상수3을 실제 Social service로 이전했다. 전체 함수/상수 AST와 나머지 reader 본문이 동일하다. G2의 동결 AESGCM ciphertext 및 잘못된 key/tag/scope, World별 프로필 탭·count 회귀 **24 PASS / 7.61초**, 기존 Starlette 경고1. 새 node는 없고 기존 테스트는 동일 alias로 실제 cursor 모듈을 import한다. 이 단계는 커서의 실제 소유만 전환했으며 profile 조회 정책·SQL 분리는 다음 단계다.

API/schema/ORM·기존 protected test1 assertion·전체 split evidence PASS. 경계 **789 modules / 2728 edges / legacy 197**, L4/ER0 PASS.


## AR-B5-C11-B — World 프로필의 실제 정책·조회 소유

Social 실제 service는 원래 입력4검증·프로필/차단/탭/페이지 판단 및 snapshot/mention 정책3을 소유한다. 원래 own-query4와 분리한 reply/like/media SQL3은 Social repository가, mixed Character/WC/World query5는 runtime이 소유한다. 같은 Session·attached 행·query 실행 순서와 tuple/nullable/cardinality를 보존했다. 별도 application/reader port와 옛 runtime reader를 제거하고 유일한 HTTP caller를 실제 service로 연결했다.

확장 AST 전부 동일. 원문 reader와 현 실제 서비스의 실행 SQL·bound parameter·순서는 posts16/replies15/likes15 각각 동일하며 동일 snapshot/cursor를 반환했다. 신규 SQLite1node는 입력 오류 SQL0, pending WC 로컬 프로필의 즉시 반영, commit0 및 rollback을 검증한다. 기존 프로필/Chat entry/cursor/역사 inventory와 함께 **33 PASS / 9.36초**(기존 Starlette 경고1). P8-L-E 현재 source 검사만 실제 역할 경로로 연결했으며 frozen JSON은 변경하지 않았다. 전체 B5 및 source capture/Hosted/installer 종료는 후속 단계다.

API/schema/ORM·기존 protected assertion·전체 split evidence PASS. 경계 **791 modules / 2733 edges / legacy 197**, L4/ER0 PASS. 새6 파일의 읽기 편의를 위해 임시 도구 환경의 Ruff 0.12.0으로 포맷했으며 저장소 의존성 파일은 바꾸지 않았다.


## AR-B5-C12 — 수동 Social HTTP·요청 세션 연결

기존 World profile/feed/thread/post/reply HTTP5 및 오류 매핑6개 본문을 Social router의 실제 책임으로 이전했다. 요청 factory3은 같은 Session으로 기존 프로필·read references·BEGIN IMMEDIATE executor를 연결하며 생성 IO0을 유지한다. 원래 API 조립 위치·URL·query/header·상태·오류·응답·멱등성 및 provider0은 그대로다. 실행 계약3method는 같은 class 본문으로 contracts에 이동했고 옛 API와 ports 파일을 제거했다.

선언한 collaborator 주입만 확장하면 기존6본문/5decorator/request 인자 AST가 동일하며 기존 Social HTTP31과 transaction protocol3은 AST 그대로다. 신규 SQLite2node는 두 앱 factory의 요청 Session 동일성·constructor SQL0·manual route5 순서 및 외부 frontend 요청5의 업무 IO 전 차단을 검증했다. 최초 신규 fixture는 read가 Origin만 검사한다고 잘못 가정하여42PASS/1FAIL이었고, 원래 host 기반 읽기 규칙에 맞춰 Host도 외부 값으로 고정했다(제품 변경 없음). 최종 기존 HTTP/멱등성/provider0/프로필/Chat entry/cursor/history inventory 포함 **43 PASS / 14.49초**, 기존 Starlette 경고1. 전체 B5 및 source capture/Hosted/installer 종료는 후속 단계다.

최종 Worlds 오류 계약을 기존 승인된 `worlds.service`의 같은 클래스 객체로 연결한 뒤 요청/HTTP/공통 오류 **25 PASS / 8.36초**를 확인했다. 구조 경계790 modules/2739 edges/legacy197, API·schema·ORM, 보호된4 test파일 assertion 및 전체 split evidence가 통과했고 L4/ER0 현재 inventory도 갱신했다.


## AR-B5-C13 — 성공 행동의 명시적 동기·감정 저장 소유

원래 subjective-context policy2/error1의 실제 소유를 Social service/exception으로 옮겼다. own SQL2는 Social repository, World/WC/Relationship 사실 query3은 runtime의 같은 Session collaborator에 두었다. readonly 계약은 원래 attached row를 그대로 사용하며 생성 IO·추가 commit/flush가 없다. 기존 Run/WorldFeed/RoutinePost 행동 호출과 Today digest 소비자의 비-import 본문은 전부 동일하고 옛 adapter 파일은 제거했다.

확장 policy2/error1 AST, 실제 ownSQL2/foreignSQL3 AST가 모두 동일하다. 신규 SQLite2node는 attached row flush/commit0/caller rollback과 naive UTC normalization, declaration 없음 no-op 및 실패/다른 event 실행의 SQL 이전 거절을 검증한다. 최초 신규 마지막 비교에서 빈 SQLAlchemy IdentitySet을 Python set과 비교해215PASS/1FAIL이었으며 빈 크기0으로 올바르게 확인하도록 고쳤다(제품 변경 없음). 최종 Today·원래 SNS/Chat 근거·LangGraph·World Feed·RoutinePost 포함 **245 PASS / 1 기존 PostgreSQL skip / 23.56초**. 전체 B5 및 source capture/Hosted/installer 종료는 후속 단계다.

API·schema·ORM, 보호된 기존 Today assertion, 전체 split evidence를 통과했다. 구조 경계794 modules/2750 edges/legacy197 및 L4/ER0 현재 inventory PASS. Frozen source/checkpoint/additions/승인 nodes는 변경하지 않았다.


## AR-B5-C14-A — Today SNS 값·조회 제한의 실제 소유

활동 종류·성공 실행 일치·source/chain revision·digest/watermark·UTC helper8, 상수6 및 오류1을 실제 Social service/constants/exceptions로 이전했다. 각각 원문 AST가 동일하며 현재 reader class 전체와 runtime의 원래 export도 변경하지 않았다. 역사 generator는 상수의 실제 소유 경로만 import한다. 기존 batch/scan/branch/record 상한과 public/unlisted, event type, digest field는 같다. 새로운 테스트나 판단 규칙은 추가하지 않았다. 실제 reader orchestration·scope·SQL의 역할 전환은 다음 slice로 남는다.

Today·기존 응답 streaming·명시적 저장 focused37 PASS/14.38초. API·schema·ORM와 전체 split evidence, 경계795 modules/2754 edges/legacy197 및 L4/ER0 현재 inventory PASS. Frozen baseline/additions/승인 nodes는 유지했다.


## AR-B5-C14-B — Today SNS 조회의 실제 책임 전환

범위·owner·활성 scope·차단·조상/근거·명시적 context 검증 및 레거시 fallback 제외·종류·count/coverage/revision 조립은 Social 실제 service에, Social bounded batching/post/block/declaration SQL은 repository에 두었다. mixed World/WC/membership/event/execution 사실은 같은 Session runtime callback이며 ORM을 service나 응답 계약으로 우회 재수출하지 않는다. 앱/Chat/Memory 소비자는 원래 read 호출 그대로 실제 factory에 연결했고 옛 reader 파일을 제거했다.

확장 read/scope/subjective policy3과 query execution/block3·active query1 AST가 원문과 동일하다. 원래 reader와 새 서비스의 **실행 SQL13개·bound parameters·순서 및 전체 records/count/coverage/watermark 값이 동일**하다. 신규 SQLite1node는 factory/range reject SQL0·sameSession, 다른 Session에서 숨긴 원본을 기존 캐시 대신 다시 확인하여 원본/자손 제외, commit0을 검증했다. 기존 Today·응답 streaming·declared context와 함께 **38 PASS / 12.41초**다. 전체 B5·원본 최초도입 capture·Hosted/installer·G07 최종 종료는 후속 단계다.

고정 후보의 전체 Social 역할 회귀와 Today/streaming/수동 게시·프로필을 함께 실행해 **95 PASS / 33.62초 / 기존 Starlette 경고1**를 확인했다. API·schema·ORM, 보호된2개 원래 테스트 파일 assertion, 전체 split evidence, 경계799 modules/2763 edges/legacy197 및 L4/ER0 현재 inventory PASS.


## AR-B5-C15 — 성공 행동의 원본·알림·범위·제안 응답 소유 전환

Social의 source/notification 정책과 자기 ORM query/mutation, WC의 활성/current/target scope 확인, Relationships의 제안 응답 허용, Routines의 실행 scope/intent 실제 대입을 소유 서비스로 분리했다. 같은 Session의 event/evidence/idempotency·proposal·attached result와 flush 순서는 runtime 조립이 연결하며 기존 services 두 파일을 제거했다. 전환은 정책을 통째 runtime으로 이름만 옮기는 방식이 아니다.

원문 정책·조회·오류·전체 트랜잭션 **19개 AST 확장 비교가 동일**하다. 기존 event/WorldFeed/LangGraph/RoutinePost와 새 SQLite2 회귀가 **239 PASS / 기존 PostgreSQL 전용 1 SKIP / 27.85초**다. 신규 검증은 잘못된 NO_ACTION 입력의 SQL0·sameSession·관계/event0·rollback 및 attached 반응의 caller flush/rollback을 확인한다. 최초 실행의 새 reaction fixture가 필수 user_id를 빠뜨려 **238 PASS / 신규 fixture 1 FAIL / 1 SKIP**였고, fixture에 원래 owner_id만 채운 뒤 위 결과를 얻었다. 제품 DDL·nullable·기존 assertion을 바꾸지 않았다. 전체 B5·G07·원본 도입 capture·Hosted/installer 종료는 후속 범위다.

최종 C15 소유 계약과 canonical ORM import 기준 확대 검증은 **255 PASS / 기존 PostgreSQL 전용 1 SKIP / 26.74초**다. PR #258/#263 API·schema·ORM 계약 동일, 변경된 보호 테스트 1개 파일 assertion과 전체 split evidence 검사가 통과했다. 경계 검사는 **807 module / 2810 edge / legacy exact edge 189**로 통과했고 L4/ER0 현재 inventory도 통과했다. Event 이름 판단은 읽기 전용 응답 값 계약을 소비하여 Social↔Relationships package cycle을 만들지 않는다. 검색 profile 역시 실제 attached 객체의 읽는 속성만 계약으로 표현하므로 옛 Search module 예외를 추가하지 않았다.


## AR-B5-C16 — Resident Feed·Inbox 가능 행동과 응답 정제 소유

Community 원래 함수 23개를 Social repository/service로 이전했다. 반응 존재·visible reply BFS, self-author·target·대꾸 중복 및 actionable Inbox 정렬/상한, 원본을 바꾸지 않는 agent 응답 복사와 정제가 실제 소유 대상이다. 동일 Character profile 조회와 Social nullable/visible SQL을 직접 연결하며, 활동 정책 자체는 이미 Routines가 결정한 allowed_actions를 그대로 받는다. 외부 LangGraph/AgentRun/writing 소비자도 실제 Social service로 연결했다.

직접 관련 기존 회귀와 새 SQLite 1개는 **228 PASS / 12.27초**다. 신규 검증은 allowed_actions 비활성 SQL0, 같은 Session의 pending like가 원래 autoflush를 거쳐 already_liked에 반영됨, 새 commit 없음, rollback 후 원래 행동 가능 상태 회복을 확인한다. Community 나머지 102개 actual 함수와 G07·full B5·capture/Hosted 통합은 후속 범위로 남는다.

C16 확대 Social·Relationships·LangGraph·WorldFeed·follow/public activity 검증은 **298 PASS / 67.60초 / 기존 Starlette warning 1개**다. 원래 23개 body와 남은 102개 정의의 AST는 동일하고 PR #258/#263 API/schema/ORM 및 전체 split evidence도 통과했다. 최초 split 검사에서는 기존 Community의 retained/이전 소유 정의 행이 빠져 1개 metadata 오류가 발생했고, 원래 AR-B2-B6의 236개 추적 행을 동일하게 승계해 전체 원본을 포함했다. 구조/검사/보호 assertion을 완화하지 않았고 최종 경계는 **810 module / 2828 edge / legacy189**, L4/ER0도 통과했다.


## AR-B5-C17 — Resident Feed 이력 값 정책·입력 소유 전환

원래 history 정제/metadata merge/경고/길이·개수 제한/format15 함수와4 상수·regex는 Routines에, 원래 입력2 class는 Routines schemas에 두었다. Social와 공유하는 bounded neutral text2 함수는 core의 같은 함수로 연결해 package cycle 없이 재사용한다. DB·provider 호출은 추가하지 않았고 기존 Community/AgentRun caller는 실제 함수를 호출한다.

직접 관련 기존 history/tendency/LangGraph/daypart/WorldFeed 회귀는 **281 PASS / 6.14초 / 기존 Starlette 422 warning 2개**다. 신규 assertion/node를 만들거나 기존 assertion을 바꾸지 않았고, 입력 schema class identity와 API 계약을 별도 확인한다. Parent Search 감사가 찾은 옛 `runtime/relationships/sqlalchemy_social_read_repository.py` source map 누락은 실제 `domains/relationships/repository/diagnostics.py`로 정확히 연결했다. Community의 나머지87 actual 함수, G07, full B5·Hosted·capture 종료는 후속 범위다.

C17의 원래 history15/input2/common2/constant4 AST가 동일하며, 입력2 class의 Routines·Social·기존 aggregate import가 같은 객체임을 확인했다. PR #258/#263 API/schema/ORM·보호 assertion·전체 split evidence가 통과했고, 경계 **813 module / 2838 edge / legacy189** 및 L4/ER0 현재 inventory가 통과했다.

## AR-B5-WORLD-SEARCH — 키워드 검색·관찰·공개 재검증의 실제 소유

`e83f320` 기반에서 WorldFeed 검색의 실제 업무 판단·자기 업무 SQL·다른 업무 조회를 나눴다. 기존 예외4·결과 dataclass4·함수17의 **25개 전체 AST**가 정확한 조회 협력과 타입 이름만 복원하면 원문과 같다. SQL, 조건 순서, FTS 이후 canonical 검증, 순위·상한·중복 방지, row lock·savepoint·flush·rollback과 트랜잭션 종료 주체를 보존했다. 검색 인덱스 capability는 실제 사용하는 hit 속성3개만 읽고 기존 Runtime hit 객체를 변환하지 않는다. 실제 단일 RLock과 process binding은 runtime/search로 이동했다.

첫 집중 실행은 readiness 함수 한 개의 협력 인자가 누락되어12FAIL/6PASS였다. 실제 함수 서명을 수정한 뒤 기존 **18 PASS**를 확인했고, 추가2회귀를 포함해20PASS, World Package import의 실제 호출까지 확대하여 **30 PASS / 1 warning / 29.38초**다. 새 회귀는 생성 시 SQL0·같은 attached 객체·커서 변경의 호출자 rollback, 숨겨진 후보에서 foreign read 전에 행동 재검증 중단과 원래 값 복원을 검사한다. 기존 assertion·skip 조건은 유지했다.

기존 source 보존 진단에서 선행 Relationships reader의 실제 이동 경로 누락1건을 발견해 `runtime/relationships/sqlalchemy_social_read_repository.py → domains/relationships/repository/diagnostics.py`를 명시했다. 같은 원래 source 검사 재실행은0오류다. 다른 원래 split/assertion/suppression/API·ORM/기존 node 검사는0오류, 보호 **2,139 / 현재 2,285**다. 현재 경계 **804 modules / 2,801 edges / exact legacy190 PASS**, L4 parity99, ER0 **84/87/24/44/7**을 확인했다. 원래 signed source의 append-only capture 및 전체 stock/Hosted/Installer Gate와 구분한다.

옛 world_feed_search 구현·keyword_feed application·search_runtime application·search_index port 네 파일은 실제 소비자를 전환한 뒤 제거했다. 남은 Community/WorldFeed 실행·G07 전체 소유권 정리·B5 최종 종료는 계속 진행한다. 현재 aggregate/옛 실행 소비자의 제한된 연결은 제거 조건을 명시했고, 새로운 범용 우회 예외를 만들지 않았다.

C17과 Search source 49c0f1f의 실제 합류 검증은 **303 PASS / 31.36초 / 기존 warning 3개**다. 경계 **818 module / 2876 edge / legacy183**, L4 99 parity와 ER0 84/87/24/44/7, PR #258/#263 API/schema/ORM·변경 보호 테스트4파일 assertion·전체 split evidence 모두 통과했다. 삭제된 WorldFeed apply의 stale bridge와 직접 소비자 항목만 제거했고, 원래 Search 신규2개 회귀와 각 소유 역할을 함께 보존했다. 본 합류는 source 준비이며 parent의 capture·Hosted·전체 통합 Gate와 구분한다.


## AR-B5-C18 — World Feed 실행 판단·반응 검증의 실제 소유

WorldFeed 원래9함수와 반응 검증2/error/provider 계약을 Social service/contracts로 옮기고 runtime에는 기존 Session의 실제 타 업무·provider 연결을 두었다. 값7/공개 dispatch/전체 주기 정책이 실제 책임을 나눠 소유하며, 기존 async 전체 흐름과 retained client를 포함한18개 정의의 AST가 정확한 조회·lazy callback 복원 후 동일하다. nullable 조회2는 원래 db.get 의미 그대로다.

기존 반응·Search·World Package 집중 회귀는 **27 PASS / 31.50초 / 기존 warning 1개**다. 새로운 실패 주입 회귀의 첫 실행은 기존7 PASS/신규1 FAIL이었으며, 새 테스트가 잘못 참조한 observation 필드·상태 이름을 실제 post_id/retryable_failed로 고쳤다. 제품/기존 assertion/상태 모델은 변경하지 않았다. Community87·provider client/prompt 마무리·G07·full B5·capture/Hosted는 후속 범위다.

C18 최종 확대 검증은 **330 PASS / 83.41초 / 기존 Starlette warning 1개**다. 새 실패 주입 회귀가 반응·실행·성공 이벤트 rollback, 이전 관찰/친숙함 유지, retryable_failed claim 저장을 확인했다. 경계 **823 module / 2904 edge / legacy179**, L4 parity99와 ER0 84/87/24/44/7, PR #258/#263 API/schema/ORM·변경 보호 테스트2파일 assertion·전체 split evidence도 통과했다. 기존 L6 네 client/owner 연결만 runtime의 정확한 새 위치로 승계했고, 옛 runtime과 aggregate 의존 등 stale8개를 제거했다. 부정확한 테스트 파일명을 지정한 확대 명령은 수집 전 중단돼 실행0이었고, 실제 경로를 확인한 최종 명령의330 PASS만 결과로 사용한다.


## AR-B5-C19 — World Feed prompt 정책·provider 연결 종료

원래 prompt 값2와 planner/writer prompt 조립2를 Social service에, credential·trace·직접 LLM provider 실제 구현은 runtime에 두고 옛 services/feed_reaction_planner를 제거했다. 기존3 provider 정의/2 값 정의/4 상수는 prompt block 복원 후 전체 AST가 동일하다. Direct provider의 네트워크만 대체한 새 회귀는 context/tracker/schema 동일 객체와900/1000 token·medium·planner JSON 재시도 금지·writer 기본값 및 원래 공개 근거 구성을 검사한다.

최초 자동 추출은 multi-line 문자열 내부 들여쓰기 때문에 syntax 수집3오류가 났다. AST statement를 그대로 추출해 문자열 값까지 보존하도록 수정했으며, 새 텍스트나 검증 완화는 추가하지 않았다. Community87 및 G07/full B5/capture/Hosted 종료는 후속이다.

C19 최종 직접/검색/Package/보안 검증은 **37 PASS / 35.38초 / 기존 Starlette warning 1개**다. 경계 **824 module / 2908 edge / legacy177**, L4 parity99·ER0 84/87/24/44/7과 PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence가 통과했다. 첫 split 진단의 이전 단계 실제 이동4정의 누락은 원래 C18 전체 추적 행을 승계해 보완했다. 같은 원래 검사 재실행0오류이며 보호 baseline·assertion은 변경하지 않았다.


## AR-B5-C20 — 소비 이력·게시물 주제·활동 로그 실제 소유

Community 실제28함수를 Routines 이력 서비스/조회, Social Post/주제/공개 판단, 공통 JSON 값으로 나눴다. 남은59함수와 이동28함수 전체 AST는 정확한 SQL/callback 복원 후 동일하다. Routines service는 foreign ORM/query import 없이 readonly Social 협력을 사용하고, 컬럼 우선/로그 fallback·cutoff/order/limit·로그 저장/rollback 의미를 보존했다.

최초 기존69개 집중 회귀는64 PASS/5 FAIL로, 모두 옛 Community helper를 monkeypatch하던 대상이 실제 새 소유 함수에 연결되지 않은 문제였다. 정확11개의 receiver를 이동했고 기존 assertion은 유지했다. 확대285 중284 PASS/1 FAIL 역시 Character lore의 옛 history mock 대상이어서 실제 runtime history로 연결했다. 최종 새 SQLite 포함 집중은 **90 PASS / 6.49초 / 기존 warning 2개**다. 새 회귀는 구성 IO0·attached Post/log·owner roots·추가 SQL 없는 컬럼 우선·caller rollback 후 로그 복원을 확인한다. Community59·G07·full B5/capture/Hosted는 계속한다.

C20 최종 확대 검증은 **454 PASS / 54.81초 / 기존 warning 5개**다. 처음 경계 검사에서 Social이 Routines 상수를 직접 참조하고 repository를 업무 진입점으로 노출한 문제를 발견했다. 원래 cutoff·상한·이미 소비했는지 판단은 Routines service가 소유하고, Social repository는 전달받은 값으로 원래 SQL만 수행하도록 정리했다. 검사 예외를 추가하지 않았으며 최종 경계 **833 module / 2951 edge / legacy178**, L4 parity99·ER0 84/87/24/44/7, PR #258/#263 API/schema/ORM·변경 보호 테스트2파일 assertion·전체 split evidence가 통과했다. 기존28개 이전 함수와59개 잔여 함수의 전체 AST는 정확한 SQL/callback 복원 후 동일하다.


## AR-B5-C21 — Social 도구 권한·Run 범위 판단 소유

원래 권한9함수는 Social service/contracts로 옮기고 기존 Routines 조회·활동 허용 검사/Identity nullable 조회는 runtime이 같은 Session으로 연결한다. 이동9개와 잔여50개 함수의 전체 AST는 정확한 readonly 타입/조회 협력 복원 후 동일하다. 원래 Social 오류 class·진단 문자열·시크릿 대신 fingerprint·auth key 우선/daypart 차단/fallback 순서를 유지한다.

첫 집중 검증은78 PASS/1 FAIL로, nullable User 조회 한 곳이 잘못된 Protocol을 db.get에 전달한 실제 연결 오류를 새 SQLite 회귀가 잡았다. 해당 위치를 원래 User 조회 협력으로 바로잡았으며 최종 직접 회귀는 **79 PASS / 6.36초 / 기존 warning2개**다. 새2개 회귀는 attached Run/User, pending 상태 조회/autoflush, commit 없음/caller rollback과 daypart 즉시 거절·지정 오류만 변환을 검사한다. 기존 assertion을 변경하지 않았다. Community50/G07/full B5 및 capture/Hosted는 후속이다.

C21 최종 확대 Social·Relationships·Daypart·Tendency·LangGraph·Feed 검증은 **369 PASS / 47.75초 / 기존 warning3개**다. PR #258/#263 API/schema/ORM·보호 assertion·전체 split evidence가 통과했고, 경계 **836 module / 2962 edge / legacy180**, L4 parity99·ER0 84/87/24/44/7도 통과했다. Agent writing의 기존 권한 조회 소비자만 실제 owner/runtime으로 연결했으며 그 별도 writing 업무 구현은 이 단계에서 이전하지 않았다.


## AR-B5-C22 — Social 도구 게시·답글·반응·팔로우 실제 소유

Community 실제10개 행동은 AgentToolActionService로 옮겼다. 같은 Social timeline과 주제 메타데이터를 직접 호출하고, Routines의 실제 권한·로그·cue는 runtime 협력으로 연결한다. 10개 전체 함수와40개 잔여 함수 AST는 self/정확 협력 호출 복원 후 동일하다. Agent writing/LangGraph/RoutinePost/WorldFeed 실행의 실제 소비자도 구성된 서비스로 연결했다.

첫 수집은 RoutinePost의 future import보다 새 import가 앞에 놓여1오류였으며 올바른 import 위치로 수정했다. 이후 기존88개 중86 PASS/2 FAIL은 옛 Community monkeypatch 대상이어서 실제 함수/연결 대상으로10개 receiver만 변경했다. 기존 assertion은 유지했고 **88 PASS / 8.12초**, 새 SQLite/권한/반응/Search 집중은 **20 PASS / 6.84초**다. 새 회귀는 실제 World 게시/주제/성공 로그를 원래 deferred_commits 아래에서 실행하고 caller rollback으로 함께 취소함을 검증한다. Community40 및 G07/full B5/capture/Hosted는 계속한다.

C22 확대 첫 실행은386 PASS/7 FAIL/기존 PostgreSQL 전용 skip1이었다. LangGraph7개 mock receiver와 RoutinePost의 실제 실패 주입2개 참조를 새 실행 instance로 연결했고 원래 assertion·skip은 유지했다. 최종 확대는 **393 PASS / 1 기존 skip / 59.32초 / warning3개**다. PR #258/#263 API/schema/ORM·보호 변경3파일 assertion·전체 split evidence와 경계 **838 module / 2987 edge / legacy180**, L4 parity99·ER0가 통과했다. split 지도는 기존 형식대로 실제 top-level class와 destination_member를 함께 명시해10개 원래 함수의 정확한 메서드 소유를 기록했으며 검사 코드는 변경하지 않았다.


## AR-B5-C23 — Social 도구 피드·Inbox·관찰 읽기 소유

실제15개 읽기/Inbox/관찰 함수는 AgentToolReadService로 옮기고 Routines 활동로그 SQL1개는 해당 repository로 분리했다. 원래15개/잔여25개 전체 함수와 SQL이 정확한 self/타입/협력 복원 후 동일하다. 공개/캐릭터·Run 범위, scan500/페이지100/Inbox10 제한, neutral 응답, 전달기록 fingerprint/ID 처리 및 로그·읽음 쓰기 순서를 유지했다.

최초 기존81개 중79 PASS/2 FAIL은 Post author mock의 옛 대상이었다. 실제 service의2개 receiver만 연결했고 기존 assertion은 그대로다. 새 SQLite 및 관련 소유 회귀 포함 **83 PASS / 6.71초 / 기존 warning2개**다. 새 테스트는 attached 로그·created/id 정렬·다른 Character/이전 Run 제외, malformed/boolean ID 처리, 일치한 잘못된 최신 payload에서 fallback 금지, pending autoflush와 caller rollback을 확인한다. Community25/G07/full B5/capture/Hosted는 계속한다.

C23 최종 확대 Social·Relationships·Tendency·LangGraph·Feed·RoutinePost 검증은 **394 PASS / 기존 PostgreSQL skip1 / 59.10초 / warning3개**다. PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence가 통과했고, 경계 **840 module / 3017 edge / legacy181**, L4 parity99·ER0도 통과했다. 실제15개 메서드와 Routines 조회1의 소유 경로/직접 소비자/동작 검증을 현재 지도에 기록했으며 기존 저장 모델·SQL 정렬·상한·오류 계약을 변경하지 않았다.


## AR-B5-C24 — 활동 계획용 feed note·정제·진단 소유

기존 note2/diagnostics4 실제 함수는 Routines로 옮기고 planning 입력/응답 DTO3도 원문 그대로 같은 schema 객체로 연결했다. 원래6함수/잔여19함수/DTO3의 전체 AST가 정확한 협력 복원 후 동일하다. Routines가 Social 내부 ORM/저장소/서비스를 직접 참조하지 않으며, 원래 canonical visibility·권한과 같은 Session의 history 데이터를 runtime이 제공한다.

최초 기존69개 중59 PASS/10 FAIL은 note 테스트의 옛 mock receiver였다. 해당10함수 내부의35개 receiver를 실제 함수/바인딩으로 연결했고 원래 assertion은 그대로 유지했다. 최종 직접 회귀는 **71 PASS / 6.41초 / 기존 warning2개**다. 새 테스트나 실행 제한을 추가하지 않았으며 existing note 회귀의 immutable metadata·기록 상태·raw payload 비노출·오류 분류를 유지했다. Community19/G07/full B5/capture/Hosted는 후속이다.

C24 최종 확대 검증은 **394 PASS / 기존 PostgreSQL skip1 / 70.11초 / warning3개**다. PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence가 모두 통과했다. 경계 **843 module / 3037 edge / legacy182**, L4 parity99·ER0도 통과했다. 처음 runtime/resident 배치에서 생긴 실제 runtime package 순환은 Social-facing 실행 조립을 runtime/social로 옮겨 해결했고 검사 예외는 추가하지 않았다. 옛 schema 소비자 지도62개는 이미 삭제된 app/schemas/community.py 대신 실제 app/schemas/__init__.py로 정확히 연결해 동일 검사0오류를 확인했다. DTO3는 실제 정의/공통 aggregate/Social 소비자에서 동일 class 객체다.


## AR-B5-C25 — 캐릭터 상태·도구 저장 의미 보존

Community 실제6함수는 Characters의 메모 값 정책3, runtime의 Character 오류 변환2/Social 도구 실행1로 옮겼고 nullable state lookup은 Characters 실제 소유에 추출했다. 원래6/잔여13 전체 AST와 LG/LocalBot caller 전체 함수는 정확한 callback/self/type 복원 후 동일하다. auth→캐릭터 일치→nullable 조회→관찰→중복 억제 또는 저장→성공 로그 순서를 유지했다.

첫 실제 확대는 **219 PASS / 9.52초**였다. 기존 LG6개·LocalBot1개 mock receiver만 실제 소유로 연결했으며 assertion은 변경하지 않았다. 새 SQLite 회귀는 공백/casefold 동일 메모에 대해 mood/summary까지 기존값을 유지함, 로그 원래 순서, 실제 새로운 상태와 로그의 caller rollback을 검사한다. 최초 테스트가 rollback된 로그 객체를 보유해 SQLite ID 재사용 warning이 발생했으므로 검증 완료된 임시 로그 참조를 해제해 fixture 수명을 정리했다. Community13/G07/full B5 및 capture/Hosted는 계속한다.

C25 최종 확대 검증은 **422 PASS / 기존 PostgreSQL skip1 / 81.68초 / 기존 warning3개**다. 새 상태 회귀의 로그 객체 수명 정리 후 추가 SQLAlchemy warning은 없다. PR #258/#263 API/schema/ORM·보호 변경2파일 assertion·전체 split evidence0, 경계 **846 module /3057 edge /legacy182**, L4 parity99·ER0가 통과했다. Character 오류의 실제 변환2함수는 runtime에 두어 Social→Character exceptions deep import 없이 원래 예외 종류/메시지를 보존했다. 실제 업무·호출 순서나 검사 예외를 완화하지 않았다.


## AR-B5-C26 — Social tick 후보·사전 검증·완료 실제 소유

Community 마지막13개 실제 함수와4개 상수를 Social tick service/policy로 옮겼다. Social Inbox SQL1개와 Routines thread-view 증거 SQL1개는 각 owner repository에 추출했다. 원래13/상수4 전체 AST와SQL2가 정확한 self/callback/type 복원 후 동일하다. Community에는 실제 함수/class가0개이며 남은 compatibility 연결과 실제 소비자 종료는 후속이다.

최초 직접73개 중72 PASS/새1 FAIL은 신규 테스트가 기존 좋아요 로그명을 post_liked로 잘못 예상한 문제였다. 실제 원래 값 liked를 새 테스트에 반영했으며 제품/기존 assertion은 변경하지 않았다. 새 SQLite2개는 전체 사전 검증 전 partial action 금지, 반응/상태/성공 로그의 caller rollback, 원래 cutoff/scope/order/limit·pending autoflush를 검증한다. G07/full B5/capture/Hosted는 계속한다.

C26 최종 확대는 **424 PASS / 기존 PostgreSQL skip1 /72.57초 /기존 warning3개**다. PR #258/#263 API/schema/ORM·보호 assertion·전체 split evidence0, 경계 **849 module /3089 edge /legacy183**, L4 parity99·ER0가 통과했다. 기존 함수/class와 상수는 실제 owner에 모두 정의되어 있으며 Community는 임시 같은객체 수출만 남았다. 신규 SQLite2개는 실제 좋아요/상태/로그 전체 rollback과 중복 payload의 사전 차단, 읽지 않은 답글30개 정렬 및 Run 이후 thread 증거 원래 필터를 확인했다.


## AR-B5-C27 — 수동 답글 Inbox 상태·claim 실제 소유

원래 runtime Inbox 실제11함수/오류는 Social service·repository·값/계약으로 옮겼고 기존 runtime 파일을 제거했다. 소유 SQL5 및11함수/오류 전체 AST가 정확한 self/query/foreign-read 복원 후 동일하다. 기존 수동 답글/후속 beat/L4 집중은 **35 PASS / 기존 PostgreSQL skip1 /20.81초**, 새 SQLite 및 실제 후속 beat 회귀는 **2 PASS /5.81초**다.

새 회귀는 활성 다른 claim 거절, claim/release의 실제 commit과 consume의 flush-only/caller rollback을 확인한다. pending 상호 차단을 같은 Session으로 읽어 무효 후보 거절과 함께 원래 commit하는 의미도 검증한다. 원래 assertion이나 DB 제약은 변경하지 않았다. Canonical RoutineInteraction3·G07/full B5/capture/Hosted는 후속이다.

C27 최종 Social·Relationships·RoutinePost 검증은 **130 PASS / 기존 PostgreSQL skip1 /63.73초 /기존 warning1개**다. PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence0, 경계 **852 module /3099 edge /legacy182**, L4 parity99·ER0가 통과했다. 기존 L4 구조 검사의 단일 실제 소유 파일 경로를 Social service로 연결했으며 검사 조건은 유지했다. 사라진 runtime→전역 ORM 정확1개 임시 예외도 제거했다.


## AR-B5-C28 — 성공 Social 이벤트의 RoutinePost 후보 실제 소유

Canonical interaction의 후보 실제 메서드/관계 band/상호 차단은 각각 Relationships service와 Social repository로 옮겼고 event/evidence/방향별 관계 SQL2도 Relationships가 소유한다. 기존 compatibility 본체와 services의 module alias를 제거했다. 원래 후보 전체 AST·band/block·SQL2·constructor factory가 정확한 callback/query 복원 후 동일하다. 기존 Social/RoutinePost 집중은 **34 PASS /기존 PostgreSQL skip1 /18.09초**다.

신규 회귀 최초는 기존13 PASS/새1 FAIL로, SQLite rollback 재조회에서 datetime timezone 표시가 naive로 복원되기 때문에 새 테스트의 dataclass 전체 비교가 달랐다. 새 테스트에서 UTC 시간 표현을 정규화한 뒤 같은 전체 후보 값으로 비교하며 제품 시간/SQL/기존 assertion은 변경하지 않았다. 최종 호환/G07/full B5/capture/Hosted는 계속한다.

C28 최종 확대는 **131 PASS /기존 PostgreSQL skip1 /63.62초 /기존 warning1개**다. PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence0, 경계 **855 module /3108 edge /legacy181**, L4 parity99·ER0가 통과했다. 첫 지도 검사가 legacy의 단일 factory 이전을 다중 분할로 기재한1항목을 거절했으므로, 실제 단일 구현 이전과 남은 임시 import aggregate로 구분해 같은 검사0오류를 확인했다. DTO·업무·SQL·assertion은 변경하지 않았다.

C28 독립 리뷰 후속: `RuntimeRoutineInteractionReferences.get_post`가 원래 `db.get` 대신 공개/댓글 eager-load 조회에 연결된 차이를 발견했다. 신규 SQLite 회귀가 숨김 attached 객체 조회에서 **1 FAIL**로 결정적으로 재현했다. 이미 존재하는 실제 `social.repository.event_evidence.get_post`의 동일 `db.get`로 연결하여 identity-map hit의 SQL/flush0, miss의 숨김 객체/단일 SELECT/no eager-load, caller rollback·없는 ID를 확인했다. 직접 Social·RoutinePost 회귀는 **36 PASS /기존 PostgreSQL skip1 /19.50초**다. 앞선 AST 보존은 callback 호출 복원까지의 증거였으며 이 후속 검증이 실제 callback SQL 의미도 보완한다. 기존 판단/SQL/회귀 assertion은 변경하지 않았다.


## AR-B5-C29 — Social 잔여 계층·집합 종료

소비자가 없는 전달 계층4함수와 public/API/infrastructure/ports 집합을 제거하고 현재11소비자를 실제 service/contracts/UoW로 연결했다. 기존 쓰기 테스트는 원래 단언을 유지한 채 실제 실행기 메서드에 이름을 연결한다. 관찰 Protocol은 contracts로 원문 이동, subjective migration/helper도 실제 동일객체로 연결했다. 두 Feed runtime의 concrete Resident context 타입을 readonly contract로 바꾸어 원래 context/credential/콜백 객체를 그대로 전달한다. provider/cycle 전체 구현 AST는 타입 복원 후 동일하다.

기존 Social·RoutinePost·UoW·오류/커서·Feed 검증은 **138 PASS /기존 PostgreSQL skip1 /50.69초 /기존 warning1개**다. 실행기를 건너뛰거나 새 provider/commit 경계를 만들지 않았으며 새 테스트 노드나 검사 예외를 추가하지 않았다. Community 소비자·G07/full B5/capture/Hosted는 후속이다.

C29 보존 검사: PR #258/#263 API/schema/ORM·보호 변경4파일 assertion·전체 split evidence가0오류이며, 경계848 module/3089 edge/legacy181 및 L4 parity99·ER0도 통과했다. 실제 subjective migration·Windows supported-upgrade verifier·Today inventory 회귀5개와 동결 Today inventory --check가 통과했다. 동결 JSON/역사 migration 본문은 다시 쓰지 않았다.


## AR-B5 순차 통합 준비 — main B4 후속과 Social C29

검증된 main `8f58d95`에 signed Social C29 `e56e645`의 실제 소유 변경을 합쳤다. 이미 B4에서 옮긴 Resident graph/작성/실행의 본문은 새 위치에 유지하고, Social actions/reads/state/subjective context와 Routines Run·FeedCue를 실제 소유 함수에 연결했다. 옛 LangGraph·작성 실행 파일과 이동된 테스트 블록을 복원하거나 중복 도입하지 않았다. Public action의 기존 생성·완료 함수와 새 evidence 대입 네 함수를 같은 실제 Routines 서비스에 합치고 runtime은 해당 서비스와 원래 조회 함수를 조립한다.

첫 수집에서 삭제된 activity policy/brief import를 발견하여 실제 역할 경로로 수정한 뒤 **2,379 nodes 수집**이 통과했다. 첫 집중 검사는 **431 PASS /6 FAIL /기존 skip1 /84.91초**였다. 실패는 FeedCue actual owner 연결, Writer 권한 모듈의 동명 alias 충돌, 첫 인사·작성 테스트의 이전 namespace 세 종류였으며 assertion을 바꾸지 않고 호출 대상/monkeypatch를 실제 소유 객체로 연결했다. 해당 네 파일 재검사는 **123 PASS /11.53초**다.

Social의 activity admission이 Resident runtime을 역참조하는 순환은 root의 독립 signed `a85a63d`와 byte-identical인 `runtime/routines/activity_policy.py`·`activity_scope.py` 두 실제 파일 이동으로 제거했다. G5 ancestry를 합치지 않고 원래 Session·lazy World 조회·정책 함수를 그대로 공유한다. 이 변경의 집중 검사는 **11 PASS /23.75초**다. 실제 사라진 exact 예외 26개만 제거하고, 남은 미호출 action-menu/allowed-tool helper의 동일 visibility 소비는 AR-B8-A 종료 대상으로 정확히 기록했다.

현재 단계는 C30 이후 Community/CRUD 소비자 종료, 원래 signed introduction 수집 및 append, stock 보존 전체·전체 backend·Hosted CI·설치 검증 이전의 통합 준비다. main의 원장 92 records와 PR258/263 동결 자료는 수정하지 않았다. 앞선 실패 이력은 최종 통과와 별도로 남긴다.

## AR-B5-C30 — Community 임시 서비스 집합 제거

실제 함수/class0인 Community 집합을 삭제하고18소비자의129참조를 소유 서비스/실행 instance/오류/상수로 연결했다. 제품742개 전체 함수/class AST가 정확한 import 해석 후 동일하다. 기존 test 단언은 실제 owner의 지역 import로 기존 표현을 유지하며 namespace 복제나 범용 facade를 추가하지 않았다.

최초 집중은350 PASS/9 FAIL/기존 PGskip1로 LocalBot의 옛 mock receiver가 원인이었다. LocalBot10·Routines2 receiver를 실제 owner로 옮긴 후 같은 집중은 **359 PASS /기존 PostgreSQL skip1 /22.54초 /기존 warning3개**다. 기존 Community25임시bridge/17legacyedge를 제거하고, 현재 branch의 미합류 AgentRun/Writer/LocalBot 실제consumer13개만 정확한 종료 조건과 함께 기록했다. parent의 이미 구현된 runtime/resident 및 LocalBot 합류에서 이 임시 oldconsumer들을 제거한다. CRUD별칭/G07/full B5/capture/Hosted는 후속이다.

C30 최종 보존은 PR #258/#263 API/schema/ORM·보호 변경12파일 assertion·전체 split evidence0, 경계847 module/3050 edge/legacy164, L4 parity99·ER0 PASS다. 실제 첫인사 receiver2개가 쓰이는 기존 회귀1개도 PASS다. 지도 생성 첫 시도에서 역사 pilot 형식을 일반 split으로 재작성한7항목은 원래 HEAD의 정확 AR-B1/AR-F1을 복구해 동일 검사0오류로 종료했다. 부모 strict 지도 검사가 C29의 한 번도 추적되지 않은 infrastructure/__init__.py 가상 항목을 발견했고 전체 Git 도입 이력0을 확인하여 그 항목만 제거했다. 원본 snapshot이나 테스트 단언은 변경하지 않았다.


## AR-B5-C31 — 데모 데이터 초기화 실제 runtime 소유

CRUD의 마지막 실제 seed 함수는 runtime/bootstrap으로 옮겼다. 실제 Identity·Character·Routines·Social 모델을 직접 명시하며 원래 전체 AST는 모델 import 복원 후 동일하다. 기존 factory 기본 콜백/실행 설정·데모 본문/기본값·기존 user 보완·credential/setting 추가·flush/commit 순서를 유지한다. 새 SQLite2개는 최초1회 commit 및 반복 no-op, 기존 user→credential→setting의3개 commit 순서와 password 검증을 확인한다.

초기22 PASS 뒤 factory/runtime/logging는45 PASS/1 FAIL이었다. 실패는 선행 Relationships router 이동의 옛 mock 대상으로, 실제 router·runtime gateway 및 같은 request/db DI를 연결하고 원래 단언을 유지했다. 최종 **46 PASS /44.97초 /기존 warning1개**, 같은 DB object 명시 후 해당1개도 PASS다. CRUD별칭/Relationships public/G07/full B5/capture/Hosted는 후속이다.

C31 PR #258/#263 API/schema/ORM·보호 변경1파일 assertion·전체 split evidence0을 확인했다. 남아 있는 public_main도 같은 실제 seed 콜백으로 연결했으며 parent G06 최종 통합에서는 main의 동일 콜백을 보존한다. 실제 initializer 새 경로 외에 데모 활성 설정이나 factory 본문은 변경하지 않았다.


## AR-B5 C30–C31 순차 통합 검증

B4가 이미 소유한 실제 Resident 실행·graph·작성 본문을 유지하면서 C30의 Community 집합 제거와 C31의 실제 데모 초기화를 연결했다. 원래 수집은 **2,381 nodes**, Social·Relationships·Resident·RoutinePost·실제 factory/초기화 집중은 **434 PASS /기존 skip1 /148.11초**다. 첫 테스트 명령의 존재하지 않는 파일 인자는 실행 전 오류였으며 제품 실패나 통과로 계산하지 않았다.

실행 context의 세 Social 협력은 `runtime/resident/feed_context_references.py`의 `ResidentSocialContextBindings`가 호출 시 실제 함수를 선택한다. 원래 같은 Session과 지연 호출을 유지하며, 부모의 독립 `55d1c2f9` 구현과 해당 파일이 정확히 같다. 이 연결 뒤 context·daypart·실행 검사는 **12 PASS /28.45초**다. 사라진 정확 legacy edge 10개만 제거했고 현재 경계 **987 modules /3,695 edges /legacy134 /cycle0**, ER0 및 deferred inventory 검사를 통과했다.

원장 main의 92 records와 PR #258/#263 동결 자료는 그대로다. C32의 CRUD 별칭 제거와 G07 테스트 소유권 이전, 원래 최초 도입 증거 append, stock 보존·전체 backend·PR/설치 검증은 이어서 수행한다.

## AR-B5-C32 — Community CRUD 집합 제거

실제 함수/class0인 CRUD 집합을 삭제하고11개 소비자의68참조를 실제 소유 서비스·조회에 연결했다. 제품660개 전체 정의는 import 해석 후 동일하며, Post의 원래 공개 필터/댓글 eager-load 조회를 다른 내부 조회로 바꾸지 않았다. 기존 assertion 표현은 실제 owner import로 유지하고 LG/Resident mock2개도 실제 Post repository를 향한다.

집중 회귀는 **342 PASS /기존 PostgreSQL skip18 /29.97초 /기존 warning3개**다. 신규 테스트 노드는 없고 부모의 이미 전환한 Resident/Tree/Lore 실제 소비자에 연결할 정확한 지도와 임시 bridge 종료 조건을 남겼다. Relationships 집합/G07/full B5/capture/Hosted는 후속이다.

C32 최종 보존은 PR #258/#263 API/schema/ORM·보호 변경7파일 assertion·전체 split evidence0, 경계848 module/3037 edge/legacy154 및 L4 parity99·ER0 PASS다. 실제 도입 원본과 역사 pilot 기록은 유지했으며 새 테스트 노드를 추가하지 않았다.


## AR-B5 C32 순차 통합 검증

삭제된 `cruds/community.py`의 원래 실제 소유 함수들을 B4의 현재 Resident graph·작성·미전환 Daypart 소비자에 연결했다. 이미 옮긴 실행 본문을 복원하지 않았으며, monkeypatch 두 receiver도 실제 조회 모듈을 선택한다. 기존 CRUD 조회가 수행하던 필터·eager-load·동일 Session 의미를 바꾸지 않고 같은 실제 함수를 호출한다.

현재 집중은 **244 PASS /기존 PostgreSQL skip18 /9.44초**, 경계 **986 modules /3,667 edges /legacy126 /cycle0**다. ER0 및 L4 현재 inventory를 갱신했고 사라진 exact 예외 10개만 제거했다. 새 테스트 노드나 원본 assertion 변경은 없으며 G07·원래 source 증거 append·stock 전체 검증은 후속이다.

## AR-B5-C33 — G07 Social·Relationships 테스트 소유 위치

Social11개·Relationships7개 파일을 업무 폴더로 옮겼다. 전체18개 원문 Git-text는 두 `__file__` 부모 깊이를 원래 위치로 복원하면 동일하며,92개 parametric node가 새 위치에 정확히 한 번씩 대응한다. 공유 fixture22개 import와 CI8개 실행 경로·L4/ER0/frontend portability 목록을 실제 새 위치로 연결했다. 옛 API schema를 가리키던 frontend portability1개도 원래 source map의 실제 `schemas/manual.py`로 연결했다.

초기 collection의22개 오류는 옛 root fixture import였고 실제 업무 package로 수정했다. 최종 집중은 **188 PASS /기존 PostgreSQL skip1 /114.33초 /기존 warning1개**이며 승인된 공개604개/current2303 수집과 원래92개 정확 대응이 통과했다. API/schema/ORM·보호19파일 assertion·전체 split evidence0, 경계848/3037/legacy154, L4/ER0 generator와 frontend designcheck도 통과했다.

추가 CI/inventory/factory26개 중24개는 통과했다. 두 기존 고정 수치 검사는 각각 PostgreSQL marker84 `<82`, parity99 `==97`에서 실패했다. Git로 이동 전 C32의 동일 값84/99를 확인했으며, G07 때문에 늘거나 누락된 항목은 없다. 원래 단언을 완화하지 않고 부모의 잔여 source집합·동결97/현재99(검색 회귀2추가) 검증 항목으로 인계한다. Relationships public 제거와 복합 Chat/Today/image 테스트 위치·전체 B5 통합/Hosted는 후속이다.


## AR-B5 C33 순차 통합 — G07 및 현재 parity 검사 후속

Social11·Relationships7개 파일의 원래92개 노드와 fixture import/CI 경로를 현재 B4 main에 합쳤다. 최초 집중은 **201 PASS /기존 skip1 /1 FAIL /107.99초**다. 실패는 원래97개를 단언한 L4 parity 수량이 현재99개로 늘어난 점이다. 기존 단언이나 source 기준을 덮어쓰지 않고, 후속에서 #263 원래97 근거와 현재 전체 source parity 목록·수량·counter를 각각 검증한다. 이 시점은 전체 통과가 아니며 original source 수집 및 전체 Gate도 진행 중이다.


### L4 parity 고정 수량과 현재 source의 분리 검증

기존 `behavior["parity_test_node_count"] == 97` 단언은 #263 immutable inventory의 원래 behavior에 그대로 적용한다. 현재 behavior는 policy가 가리키는 모든 파일의 SHA256·무필터 top-level test AST 목록·전체 수량과 직접 비교하고, 원래97개가 명시적 이동 후 모두 포함되는지 확인한다. Counter의 이름/값/노드도 원래 frozen 계약을 실제 경로로 연결한 결과와 전체 비교한다. 최신99를 새 고정 숫자로 쓰거나 검사에서 테스트를 제외하지 않는다.

기존 검사와 stale 수량·누락 node·counter 변조 음성3개를 포함한 검증은 **10 PASS /15.93초**다. 이 후속의 신규3개 노드는 `tests/test_l4_parity_current_source.py`에 실제 최초 source 커밋으로 기록하며, 원장 append와 stock 검증을 이어서 수행한다. 앞선201 PASS/1 FAIL 이력은 그대로 유지한다.

## AR-B5-C34 — Relationships public 집합 제거

원래 public 이름70개 모두가 실제 계약·오류·schema·service 객체와 동일함을 제거 전에 대조했다. 18개 소비자의163참조를 실제 소유 모듈로 연결했고 제품61개 전체 정의는 정확 import 해석 후 동일하다. 순수 import 집합만 제거했으며 모든 실제 정의와 Graph 방향·권한·근거·fallback 처리는 유지한다. 구조 membership 단언은 `public.py`→`service/graph_read.py`의 정확 file/module 지도에 따라 바뀌며 기존 normalizer로 통과한다. 검사 변경이나 범용 예외는 없고 기존 public bridge18개를 제거했다.

Relationships·Graph recall/planner/Both·경계·동결 I/K/M inventory 집중은 **123 PASS /기존 PostgreSQL skip1 /48.36초 /기존 warning1개**다. PR #258/#263 API/schema/ORM, 보호 변경8파일 assertion 및 전체 split evidence는0오류, 경계847 module/3027 edge/legacy154와 현재 L4/ER0 generator도 통과했다. frozen JSON과 역사적 정책 설명 문자열은 다시 쓰지 않았다.

B5 준비 branch의 실제 업무 이전·옛 Social/Relationships 계층·Community service/CRUD/public 집합 제거와 G07 18파일은 source로 준비됐다. 부모 통합은 이미 별도로 전환된 Resident·Chat·LocalBot·Character image·공통 DB/모델 등록 소비자를 합류하고 전체 gate 및 Hosted/설치를 검증한다. 복합 Chat/Today/image 테스트의 최종 소유 위치와 앞선 G07 고정 수치 검사는 부모의 정확 통합 검증 대상으로 남는다.


## AR-B5 C34 순차 통합 검증

Relationships 공개 집합의 실제 정의70개·원래 실제 소비자 전환을 현재 B4 실행과 합쳤다. C34 제품61개 AST 동일 근거와 정확 public→graph_read 경로 대응을 유지하고, 기존 Graph Recall·Planner·Both·response streaming 및 경계/L4 검사는 **156 PASS /기존 skip1 /65.47초**다. 현재 경계 **985 modules /3,657 edges /legacy126 /cycle0**, ER0 및 L4 현재 inventory도 통과했다. 전역 facade를 다시 만들거나 호출 순서·provider·Session을 바꾸지 않았다.

B5 source 통합이 준비되었으며 원래 signed source 증거 append, stock 전체 보존과 전체 backend, PR required CI·설치 Gate를 이어서 실행한다. 이후 B6/B7/B8 및 G5/G06 완료를 이 결과로 앞당겨 선언하지 않는다.

## AR-B5 최초 전체 검증과 통합 연결 보정 — 2026-09-06

첫 전체 backend 검사는 **20 FAIL /2,342 PASS /기존 skip22 /752.72초**였다. 실패는 `runtime/characters/management.py`의 실제 Social media 조회 import 누락, 불변 Alembic 0088이 사용하는 schema helper 경로 삭제, 현재 core/source/HTTP inventory 경로 미갱신으로 분류했다. 원래 migration 본문과 ORM 구현은 바꾸지 않고 역사 경로에 실제 schema helper 두 개만 같은 함수 객체로 복구했다. 클래스 export나 새 infrastructure marker는 추가하지 않았다. 나머지는 기존 조회를 실제 모듈에 연결하고 현재 core 두 항목, HTTP module 필드 38개와 실제 검사 입력 경로를 갱신했다. 관련 마이그레이션·생성/활성화·패키지 가져오기·보안·tendency 확대 회귀는 **158 PASS /기존 warning5 /30.56초**다.

첫 stock 보존 검사는 API/ORM/원장/2,384개 노드의 원본 보존을 확인했으나, 이동 후 split 증거의 현재 소비자/노드 경로와 tendency 단언의 지역 이름 네 개를 거절했다. 원래 단언은 같은 실제 owner의 지역 import에 연결해 복원했다. 현재 경로 참조 543개를 검토된 file/node 지도에 따라 연결하고, AR-B5-C1에서 원래 위치에 보존했던 Run 정의 42개는 실제 후속 B4-C4b2의 기존 분할 증거를 승계했다. 역사 pilot의 상대 경로 설명과 원본 source 키·원본 정의·단언은 유지했다. 수정 후 원래 **`check_refactor_preservation.py --contracts --nodes` 전체 PASS**, PR258 1,867 /PR263 1,907 /현재 보호·수집 **2,384 /2,384**, K01–K23/G01–G13 **37항목 PASS**다. 현재 경계는 **986 modules /3,659 edges /legacy126 /cycle0**, L4·ER0·deferred·public HTTP inventory도 통과했다.

원장은 main의 **92개 기록을 불변 prefix**로 유지하고 최초 signed source **52개 기록**을 추가해 **144개**로 준비했다. 각 source는 고립된 원본 Git archive에서 수집하며 현재 구현으로 기준선을 재생성하지 않았다. 추가 파일 증거 211개와 신규 노드 73개를 최초 정의 커밋까지 대조했고, RoutineInteraction 조회 회귀 한 개는 후속 C31이 아닌 실제 최초 `696ada3` 기록에 배치했다. World Feed 검색 회귀 두 개도 최초 `49c0f1f` 기록과 기존 경로에서 C33 이동 지도로 이어진다. PR258/263 동결 source/checkpoint/승인 목록은 바꾸지 않았다.

보안 사전 검증은 Gitleaks 8.30.1로 history 519 commits와 추적 source+원장 draft를 각각 검사했다. C33 지도의 공개 테스트 파일 SHA256 한 줄이 generic-api-key로 감지되어 원래 signed `f977215` 테스트 blob의 SHA256과 동일함을 검증했다. exact path/rule/전체 line 한 개에만 예외를 추가했고 변경 hash/key/path/prefix/suffix 음성 6개를 거절했다. 후속 history 및 source draft 검사에서 **0 leaks**이며 기존 secret allowlist 25개는 그대로다. 최종 source 기준 전체 backend·PR required CI·병합 후 실행 Gate는 다음 결과로 기록한다.

### 최종 B5 후보 전체 검증

수정 source `9a7f76d`와 최초 도입 원장 metadata `0108a3a`를 signed로 고정한 뒤 전체 backend가 **2,362 PASS /기존 skip22 /warning27 /733.18초**로 통과했다. 동일 source의 원래 stock 검사도 **보호2,384 /현재2,384 /37항목 PASS**다. 원래 tendency 단언의 중복 import만 정리한 별도4개 회귀도 통과했으며, 전체 실행 중 source/test/metadata를 편집하지 않았다. 최초20개 실패 이력은 위 기록에 유지한다.

같은 커밋의 Gitleaks 추적 source와 HEAD 전체 조상 history는 모두0 leaks, DCO·secret metadata25·Local OSS/CI policy·frontend design은 PASS다. 원래 custom scanner의 현재 Git tree는2,081파일/치명0이다. 공유 개발 저장소의 `--history`는 `--all`을 읽기 때문에 미합류 B8 `3500f3f`의 신규 `tests/integrations/test_direct_llm.py`에서3개 synthetic fixture 오탐을 발견했다. 그 경로와 blob `a464aad`는 B5 HEAD 조상에 없고 해당 B8 source가 자기 경로의 기존 exact allowlist를 이미 이전했다. B5에 미래 예외를 추가하지 않고, 후보 전체 조상만 있는 별도 bare 저장소에서 원래 history 검사를 그대로 실행해 PR 범위 결과를 분리한다. PR required CI와 병합 후 실행·installer Gate는 아직 완료로 표시하지 않는다.

## AR-B6-A1 Chat 모델 정책·요청 계약 준비

고정 source `9c1ad0f07cb824c158e07618d7b2ec1eca5f3135`에서 Chat의 schemas·exceptions·policies·model_binding 계약 네 파일을 실제 역할 경로로 옮겼다. 함수·클래스 본문 AST와 정책 상수는 동일하며 20개 실제 소비자와 기존 테스트의 module 참조를 바꿨다. Gemini HIGH/LOW, Gemma의 미설정 reasoning, token cap 및 lease 정책은 그대로다. 신규 행위나 신규 test node를 추가하지 않았다. Frozen migration 및 과거 inventory branch는 변경하지 않았다.

- Chat B/D domain·identity/migration·모델 Hotfix·쪽지 회귀: **83 passed / 16.37초**, 고정 source에서 완료.
- Live architecture **627 modules / 2,003 edges / exact legacy 281 PASS**. Deferred 22, L4 parity 97, ER0 76/87/24/44/7, P8-R current inventory PASS.
- 정확한 기반 module 5개·entry 3개와 임시 소비 연결 8개만 scope에 반영했다. Thread repository/service, generation lifecycle 및 HTTP endpoint 구현은 아직 이전하지 않았다.

이는 AR-B5 후 순차 통합할 독립 준비 source다. 전체 보존 계보 capture·통합 회귀·PR·merge·post-merge 및 AR-B6 완료로 표시하지 않는다.



## AR-B6-A1 — Chat 계약·모델과 실제 thread SQL 기반

Media `dd78da66`에서 새 Chat 작업트리를 만들고 계약 준비 `4def2b5`를 합친 merge `8e6be936dce66626119a43d4fe0a55632dd91c9d`를 먼저 고정했다. B5 이후 순차 병합할 준비 구현이며 Chat 전체 완료가 아니다.

남은 순수 값/검증 계약 9개 파일과 package export를 `contracts/`로, Chat ORM 5개와 DDL helper를 `models.py`로 옮겼다. 함수/class **85개 AST 본문은 동일**하고 모든 class는 같은 Base/metadata를 사용한다. immutable v5→v6와 Alembic 본문은 수정하지 않았으며 이전 models module만 같은 객체 alias로 유지한다. 실제 소비자와 살아 있는 검사기의 물리 경로를 새 역할로 연결했고 frozen 역사 inventory·source/checkpoint·승인 node를 다시 만들지 않았다.

`repository/threads.py`에는 실제 SQL query 9개와 원래 advisory lock/tuple lookup 함수 4개를 옮겼다. requester/deleted/ambiguous scope·정렬·limit 2·joinedload·같은 Session은 유지하고 repository에서 commit/rollback하지 않는다. World/legacy count는 동일 requester/deleted 조건의 하나의 query를 사용한다. thread admission·mutation/commit·오류 판단은 아직 원래 실행 service에 있으며 A2에서 교차 owner/credential 협력과 함께 이전한다.

새 회귀 1개는 실제 SQLite에서 owner/삭제 필터·정렬·중복 후보 최대 2개·동일 attached 객체·caller rollback을 검증한다. 첫 집중 134개 실행은 generated inventory 명령 후반과 겹쳤으므로 고정tree 통과 증거로 사용하지 않고, 모든 명령 종료 뒤 동일 범위를 다시 실행한다.

고정 tree 재실행은 **134 passed / 기존 4 warnings / 22.26초**였다. 모델/계약 85개와 원문에서 온 lock/lookup 함수 4개의 AST가 같고 현재 API·ORM 계약은 원래 baseline와 후속 checkpoint 모두 차이가 없었다. Live architecture는 **638 modules / 2,064 edges / exact legacy 265 PASS**, ER0 **77/87/24/44/7 PASS**, L4 parity **97**, Memory batch 및 World Chat identity inventory current다.

전체 assertion 보존 검사는 많은 이동 경로의 정규식 재컴파일 병목으로 종료 전에 중단했으므로 PASS로 표시하지 않는다. 별도 검증된 검사기 성능 수정의 적용 뒤 source·assertion·node 통합 검사를 다시 실행한다. 신규 source/test introduction capture와 PR·merge·설치 Gate는 root의 선형 통합에서 진행한다.

검사기 성능 수정은 root source `36fd4748cb55744d3effbcfb9d18eb921e0fd8d9`의 해당 파일 diff만 그대로 적용했다. 경로 순서와 정규식 경계는 유지하고 컴파일된 immutable pattern만 재사용한다. 기존 보존/partial-scope 회귀 **149 passed / 1.24초**를 통과했다. 이후 전체 보존 명령이 종료되어 source 목적지·split·assertion·skip/xfail 억제·API·ORM·수집 node 누락은 없음을 확인했다. 최초 실행에서 K17/K18/K20 등 중복 feature 행의 옛 계약 경로를 찾아 현재 경로만 정확히 수정했고 feature inventory 재검사는 차이 0이었다.

보호 계보 **2,129 / 현재 2,158**이며 source 29개·node 29개는 선행 Media/WC 및 이번 A1의 실제 첫 도입 commit capture를 root에서 이어가야 하므로 명령 전체 exit 1을 완료 PASS로 바꾸지 않는다. 원래 frozen 기준과 승인 node는 그대로다.


## AR-B6-A2 — 실제 스레드·설정·쪽지 서비스와 같은 Session 협력

A1 `2f36a6af` 및 보존 보완 `abbf2647` 뒤 실제 runtime SQL 업무 57개를 `ThreadService` 27개, `MessageSettingsService` 14개, `MessageService` 11개, 프로필 변환·조회 5개로 분리했다. HTTP는 각 실제 소유 인스턴스를 직접 호출하며 Any port와 SQL forwarding adapter는 production 호출 경로에서 제거했다. 골격만 옮긴 것이 아니라 권한·model/quota·lease·provider/commit·재시도 구현이 서비스 파일에 있다.

명시적 `self`·소유 service binding을 제외한 함수 본문은 **46/57 AST 동일**하다. 바뀐 11개는 같은 Session의 join 6개, Character nullable/profile picker 읽기, Identity credential 조회·flush-only 쓰기·clear 협력으로 분리한 부분이다. provider/send/retry 11개 함수는 모두 AST 본문이 같다. 기존 World/installation 확인과 오류 순서, PostgreSQL lock 조건·join·필터·정렬·limit, 재검증과 IntegrityError 1회 재시도, preference flush/commit 차이 및 plaintext reveal 지점은 유지한다.

새 회귀는 실제 owning instance를 쓰는 HTTP 연결, 설치 owner 거부의 선행 순서와 lock 전달, 실제 SQLite join의 같은 attached 객체·단일 query·scope 필터, credential envelope scope·flush-only/caller rollback, 예기치 않은 전송 실패의 같은 lease 해제를 검증한다. 기존 tests의 assertion은 그대로 두고 test-only helper가 monkeypatch를 실제 소유 인스턴스로 전달한다. 옛 구조 전용 node는 원본 forwarder를 compatibility에 한 번만 보존하고 새 직접 서비스 경로 회귀와 B8 퇴역 조건을 정확히 지도에 적었다.

첫 59개 집중 검사는 **58 passed / 1 failed**였고 실패는 선행 WC source의 이미 옮겨진 provider에 대한 reveal 허용 경로 한 건이었다. 해당 경로만 `world_characters/client.py`로 맞춘 뒤 신규 회귀·모델 Hotfix를 포함해 **74 passed / 기존 4 warnings / 19.01초**를 통과했다. 보존 기준선·허용 동작을 넓히지 않았다. 최종 inventory/보존·확장 집중 검사는 이 기록 이후 별도로 수행한다.

최종 고정 tree의 Chat·World Chat·generation·Today SNS·credential/deletion 집중 묶음은 **170 passed / 기존 4 warnings / 38.56초**, 보존/부분 scope 회귀는 **149 passed / 0.97초**였다. 전체 보존 `--contracts --nodes`는 source 목적지·분리 symbol/소비자·assertion·억제 표시·API·ORM·기존 node에서 오류 0이며 보호 **2,129 / 현재 2,166**을 확인했다. 선행 Media/WC/A1의 아직 capture되지 않은 source 29개·node 29개 때문에 명령은 exit 1이다. 이번 미커밋 slice의 신규 node 8개와 helper/서비스 파일은 이 source의 첫 introduction SHA로 root에서 추가 증거를 남긴다.

Live architecture **645 modules / 2,103 edges / exact legacy 265 PASS**, ER0 **79/87/24/44/7 PASS**, L4 parity **97**, Memory batch current, 공개 route inventory **196**이다. Root의 독립 읽기 리뷰에서도 query의 owner/World/WC/membership 조건·limit 2/FOR UPDATE·nullable 반환과 같은 Session, credential flush-only·clear/envelope 경계에서 추가 문제는 발견되지 않았다. 이 결과를 generation/retrieval 전체 전환이나 Hosted CI·설치 Gate 완료로 확대하지 않는다.


## AR-B6-B1 — 검색·근거·응답 실행 서비스와 실제 lifecycle 저장소

A2 `57528d22072f7541e7f1f1b982071afd5c1d537c` 뒤 실제 검색 계획·근거 조립·답변 생성 업무를 `service/`로, 실제 provider/UoW/Memory 협력 형식을 `contracts/`로, lease·CAS·최종 저장 구현을 `repository/response_lifecycle.py`로 이전했다. 이전 경로 21개의 명시적 대응을 남겼으며 Today SNS snapshot과 reader/validator가 같은 이름의 파일로 합쳐질 때 기존 snapshot 검증·hash·serialization을 모두 보존했다.

기존 함수/class 본문은 **76개 AST 동일**하다. 나머지 3개 class 차이는 workflow 생성자 annotation 1개와 repository/Protocol에 같은 함수 alias를 추가한 2개다. runtime의 accept/retry/stream/expired recovery/사전 실패 처리 5개 함수는 원래 `GenerationLifecycleService(...)` 외부 전달 생성자만 제거하면 AST가 동일하다. 실행은 실제 repository를 직접 사용하며 원래 wrapper는 기존 공개 계약과 streaming 테스트 helper `_request`·`_workflow` 때문에 compatibility 한 곳에 보존한다. 이 승인 테스트의 실제 workflow 검증을 없애지 않고 B8에서 원래 assertion과 새 실제 저장소 경로 대응을 확인한다.

새 회귀 2개는 옛 wrapper 생성 시 실패하도록 막은 실제 accept/replay 경로와 같은 SQLite 메시지·요청 한 건, 오래된 lease fence 거부, 최종 assistant 한 건과 재실행 중복 방지를 검증한다. 고정 tree 집중 검사는 **187 passed / 기존 4 warnings / 23.77초**다. 신규 검사 최초 실행도 **2 passed / 3.86초**였다.

전체 `--contracts --nodes` 검사에서 source 목적지·분리 symbol/소비자·assertion·억제 표시·API·ORM·기존 node 오류는 0이었다. 보호 계보 **2,129 / 현재 2,168**이며 선행 Media/WC 및 A1/A2의 아직 캡처되지 않은 committed source 36개·node 37개 때문에 명령 전체는 exit 1이다. 이번 source의 신규 2 nodes와 실제 소유 파일의 첫 도입 SHA는 root가 선형 통합에서 캡처한다. Frozen 원본·checkpoint·승인 node는 바꾸지 않았다.

Live architecture **641 modules / 2,094 edges / exact legacy 265 PASS**, ER0 **79/87/24/44/7 PASS**, L4 parity **97**, Memory batch current, 공개 route inventory **196**이다. 후속 B6-B2/C에서 runtime의 generation admission·evidence 읽기·provider/다중 업무 조립과 HTTP 진입점을 이어서 정리한다. B5 합류·전체 Chat 완료·Hosted CI·설치 Gate 완료를 의미하지 않는다.


## AR-B6-B2A — 생성 접수·재시도·상태와 실패 기록의 실제 서비스

B1 `408a29e0306aa9b95b08e3ed383032eebf4c6f8c` 뒤 runtime의 실제 업무 12개를 `GenerationService`로, 같은 thread의 active/latest SQL 2개를 `repository/response_requests.py`로 이전했다. HTTP 네 동작은 실제 서비스 인스턴스를 직접 호출한다. 기존 stream/evidence의 동일 인스턴스 메서드 alias는 남은 실제 호출을 위해서만 유지하며, API·runtime·repository·새 service를 원래 source의 완전한 symbol 분리 지도로 연결했다.

12개 메서드는 명시적 self·ThreadService·repository binding을 원래 이름으로 되돌리면 **모두 AST 동일**하고 SQL 2개도 동일하다. user message flush→request 생성→commit→refresh, 같은 idempotency 키·내용 재확인, 최신 실패 요청과 같은 user message/response slot 재시도, 모델 PATCH와 같은 tuple 잠금·scope 재검증, 만료 복구 commit, accepted/failed sequence·lease fence 및 terminal 오류 저장 순서를 유지했다.

첫 집중 검사 **46 passed / 3 failed**에서 모델 snapshot 함수를 SettingsService로 잘못 연결한 부분을 찾아 실제 ThreadService 소유로 수정했다. 기존 Hotfix 잠금 회귀는 monkeypatch 대상만 실제 owning instance로 옮기고 assertion은 그대로 유지했다. 수정 뒤 **56 passed / 기존 4 warnings / 14.10초**, 고정 tree 확장 묶음은 **194 passed / 기존 4 warnings / 24.95초**였다. 신규 node는 추가하지 않았으며 B1의 실제 accept/replay·fence 회귀와 기존 전송·재시도·재연결·모델 Hotfix 검증을 사용했다.

전체 보존 검사에서 source/split/assertion/억제 표시/API/ORM/기존 node 오류 0, 보호 **2,129 / 현재 2,168**을 확인했다. 선행 source 37개·node 39개의 append-only capture가 root 순차 통합에 남아 있어 명령 전체는 exit 1이다. 이번 실제 service/repository 2개 파일의 첫 도입 SHA도 그 순서로 캡처한다. Live architecture **643 modules / 2,109 edges / exact legacy 265 PASS**, ER0 **79/87/24/44/7 PASS**, L4 **97**, Memory batch current, public **196**이다.

근거 inspector의 현재 원본·revision/공개 상태 재검증과 provider/Memory/graph/Today 실행 조립은 후속 B2B/C 범위다. 전체 Chat·B5 순차 통합·CI·설치 완료로 표시하지 않는다.


## AR-B6-B2B — 근거 공개 상태·revision 정책과 같은 Session 읽기 협력

B2A `f4a5ddc74eb7651d91a100272a21dc26cb41543c` 뒤 근거 inspector의 실제 정책을 `service/evidence.py`로 이전했다. `contracts/evidence_reads.py`는 필요한 Memory/Today/관계/이름 읽기 결과를 명시하며, runtime의 `evidence_reads.py`는 기존 reader 구성·nullable Relationship 조회·World 이름 join만 수행한다. HTTP 근거 조회는 실제 EvidenceService 인스턴스를 직접 사용한다.

두 업무 메서드는 self 및 명시된 reader 협력을 원래 표현으로 복원하면 **전체 AST 동일**하고 순수 helper 3개 본문도 동일하다. source reader는 요청에서 한 번 만들고 같은 객체와 Session을 Memory detail에 넘긴다. Today의 ±1초 구간과 composite revision, canonical 원본의 World/revision/성공/공개/관찰/참여/차단, Memory 활성·version·현재 evidence, 관계 version/방향/참여·차단 검증과 기존 오류 catch 순서를 유지했다.

새 회귀 5개는 정상·다른 World·비공개·비활성 참여·revision 변경의 현재 원본을 재조회해, 허용된 경우에만 500자 excerpt와 연결을 반환하고 그렇지 않으면 과거 본문과 이름을 노출하지 않음을 확인한다. 최초 근거/Memory/Today/stream 집중 묶음은 **44 passed / 기존 1 warning / 12.39초**, 고정 tree 확장 묶음은 **199 passed / 기존 4 warnings / 23.75초**다.

전체 보존 검사는 source/split/assertion/억제 표시/API/ORM/기존 node 오류 0, 보호 **2,129 / 현재 2,173**이다. 선행 committed source 38개·node 39개의 append-only capture가 남아 명령 전체는 exit 1이다. 이번 신규 5 nodes의 첫 도입 파일은 `tests/chat/test_evidence_ownership.py`이며 실제 service/contracts/runtime 읽기 3개 파일과 함께 source SHA별로 root에서 캡처한다. Live architecture **646 modules / 2,133 edges / exact legacy 265 PASS**, ER0 **78/87/24/44/7 PASS**, L4 **97**, Memory batch current, public **196**이다.

남은 provider/Memory/graph/Today 생성 조립, recent-context SQL과 실제 streaming 입장 판단은 B2C에서 이어간다. 전체 B6·B5 합류·CI·설치 완료는 별개다.


## AR-B6-B2C — 실제 stream 입장 판단과 순서를 보존한 실행 조립

B2B `4694b5dc6eaa81e3c01ddb41ea01e5732cbe636c` 뒤 stream의 실제 요청·상태·기한·context·로컬 runtime·credential/model 판단과 최종 command 생성을 GenerationService로 이전했다. Character/World nullable 조회는 해당 소유 서비스의 같은 `db.get` 구현을 사용한다. recent-context SQL은 repository로, 같은 20개/8,000자 선택 정책은 생성 서비스로, Character 응답 profile 변환은 기존 Chat profiles 파일로 옮겼다.

`contracts/execution.py`의 실제 입력/결과 형식을 통해 runtime의 `generation_workflows.py`가 기존 canonical provider/executor → graph gateway/provider/executor → World 이름 목록 → router/CRG/UoW/Memory/Today 객체를 원래 순서로 만든다. 원래 생성 블록과 UoW는 **AST 동일**하고 서비스의 stream은 명시된 소유 조회 및 실행 조립을 원래 표현으로 펼치면 **전체 AST 동일**하다. 최근 context 선택도 SQL 이전을 제외한 본문은 동일하다. Provider 호출·budget·credential reveal 횟수를 늘리지 않았다.

새 회귀 2개는 실제 builder의 provider 생성 순서·동일 material/Session/lifecycle/label과, Memory 실행이 불가능한 경우 실제 repository에 accepted→failed와 retryable 상태를 저장하고 provider builder를 호출하지 않는 경로를 검증한다. 첫 집중 묶음 **62 passed / 1 failed**는 A2 구조 전용 테스트의 옛 module attribute가 제거되어 발생했다. 해당 attribute는 같은 기존 module을 가리키는 검사 전용 alias로 B8까지 보존했으며 실제 HTTP 동작은 실제 service instance를 직접 호출한다. 기존 assertion을 약화하지 않았다. 신규·서비스 소유 회귀 **10 passed / 5.07초**, 최종 고정 tree 확장 묶음은 **209 passed / 기존 4 warnings / 34.47초**다.

전체 보존 검사는 source/split/assertion/억제 표시/API/ORM/기존 node 오류 0, 보호 **2,129 / 현재 2,175**이다. 선행 source 42개·node 44개 append-only capture가 남아 명령 전체는 exit 1이다. 이번 신규 파일 `contracts/execution.py`, `runtime/chat/generation_workflows.py`, `tests/chat/test_generation_composition.py`와 신규 2 nodes는 이 source의 첫 SHA로 root에서 캡처한다. Live architecture **648 modules / 2,148 edges / exact legacy 265 PASS**, ER0 **78/87/24/44/7 PASS**, L4 **97**, Memory batch current, public **196**이다.

남은 실제 canonical preflight/entity resolution과 Today snapshot hash 판단을 소유 service로 이어서 이전하고, 그 뒤 Request→app.state 기반 service 주입·두 factory 등록·동일 standalone router 테스트 구성을 통해 HTTP owner를 마무리한다. runtime Memory 성공 후보는 실제 after-commit UoW 협력이며 원래 한 번의 제안·commit/rollback 의미를 유지한다. 전체 B6·B5 통합·CI·설치 완료로 표시하지 않는다.



## AR-B6-B2D — 검색 사전 정책·Unicode 재확인·Today snapshot 소유

Source `4d1f0f4836e913251f7fa92c091e93d8b1ce3409`에서 preflight의 실제 거부 순서와 entity 후보 판단을 `service/retrieval_policy.py`로 이전했다. 같은 Session의 교차 업무 SQL 5개는 `runtime/chat/retrieval_queries.py`, Chat thread 조회는 자체 repository에 있다. `contracts/retrieval_reads.py`는 필요한 값과 read 계약이다. Today snapshot의 complete-through/hash 검증은 기존 Today 서비스의 실제 validator가 수행하고 runtime은 같은 reader를 구성한다.

사전 판단 3개 메서드는 명시된 읽기 협력을 원래 표현으로 펼치면 전체 AST 동일하다. 새 교차 SQL 5개와 Chat thread 조회의 표현 AST도 원래 query와 동일하며 Today assert_current 본문은 변경하지 않았다. Unicode casefold 재확인, 활성·공개·차단 후보의 observable 조건, 소유자→World→thread→역할→차단→Memory 조회 순서와 오류를 보존한다. 새 회귀 3개는 잘못된 설치 소유자에서 후속 조회가 실행되지 않는 두 경우와 Unicode/차단 후보의 실제 정책을 검증한다.

고정 tree 확장 검증 **212 passed / 기존 4 warnings / 22.49초**. 전체 보존은 source/split/assertion/억제 표시/API/ORM/기존 node의 실질 오류 0, 보호 **2,129 / 현재 2,178**이며 선행 source/node introduction은 root의 선형 capture 전까지 미완료다. Live architecture **651 modules / 2,155 edges / exact legacy 265 PASS**, ER0 **78/87/24/44/7**, L4 **97**, Memory batch current, public **196**이다. 신규 실제 contract/service/runtime queries와 `tests/chat/test_retrieval_policy_ownership.py`의 첫 도입 SHA는 위 source commit이다.

HTTP Request 기반 service 주입·두 앱 factory와 standalone route 테스트 구성은 다음 B6-C 범위다. B5/B7 합류 시 새 Social/Memory reader·models·factory로 정확히 연결하고, 이전 constructor 이름과 구조 검사용 alias는 B8 종료 대상으로 추적한다. 전체 B6/CI/설치 완료로 승격하지 않는다.



## AR-B6-C1 — 실제 Chat HTTP 소유와 Request 기반 서비스 주입

기존 쪽지/설정 11개, World thread/진입 5개, 생성/근거/NDJSON 6개 HTTP 함수는 `chat/router/messages.py`, `world_chat.py`, `world_chat_response.py`로 이전했다. 같은 domain의 schema/error와 `dependencies.py`가 제공하는 typed 실제 service를 사용한다. 두 factory는 같은 concrete service를 등록하고 standalone 기존 API fixture 세 곳도 같은 연결을 사용한다. 요청마다 새 service/provider/Session을 만들지 않는다.

22개 원래 함수의 body·decorator·기존 인자는 **새 typed Depends 인자 하나와 errors 모듈 alias를 복원하면 전체 AST 동일**하다. 실제 API 조립의 순서·prefix·URL·operation ID·schema와 기존 get_db/get_current_user 함수 identity를 보존했다. route_security_inventory의 Chat module 22필드만 실제 소유 경로로 바꿨다. 선행 WC 7필드 지연은 별도 `581b4b61440cc6dbe49dc1024f1147e3737872a9`에서 수정했으며 HTTP 업무 변경을 포함하지 않는다.

새 회귀 5개는 두 factory의 동일 service/route 함수와 인증 callable, 실제 HTTP의 같은 Session/user 전달, 원래 runtime 설정·recall 협력 및 UTF-8 NDJSON bytes/no-store/nosniff, 미등록 시 암묵적 fallback을 만들지 않는 것을 검증한다. 신규 fixture의 초기 실패는 잘못 쓴 contract import와 FastAPI의 nested route 열거/기존 max_threads=5 응답을 반영해 수정했다. 최종 확장 묶음은 **253 passed / 기존 4 warnings / 47.89초**다. 이전 검사에서 드러난 P8-L-E 정책 검사 경로는 실제 ThreadService로 연결했으며 frozen JSON을 다시 쓰지 않고 --check PASS다.

전체 보존 실행에서 기존 API/ORM·assertion·억제 표시·node 계약은 유지됐고 보호 **2,129 / 현재 2,183**이다. 해당 실행의 C1 mapping 형식 오류는 실제 파일 전체 이전을 여러 구현 분할로 잘못 기록한 3건이었다. 모든 22개 actual symbol은 canonical 파일 하나에 있으므로 파일 전체 이전으로 기록하고 같은 함수의 옛 import-only alias는 별도 B8 bridge로 남겼다. 수정 후 전체 split evidence 검사도 PASS다. 선행 미캡처 **48 sources / 49 nodes** 때문에 보존 명령 전체의 완료는 root의 선형 introduction capture 뒤 확인한다. 신규 `dependencies.py`, router 4파일(패키지 marker 포함), `tests/chat/test_http_ownership.py` 및 5 nodes는 이 구현 source의 최초 SHA로 캡처한다. Live architecture **656 modules / 2,171 edges / exact legacy 265**, ER0 **78/87/24/44/7**, L4 **97**, Memory batch current, public **196**이다. 독립 읽기 리뷰에서 stream·same Session·runtime 설정·두 factory DI에 추가 차단 문제를 발견하지 못했다.

남은 실제 통합/호환 책임은 다음과 같다.

| 경로/책임 | 실제 현재 용도와 종료 |
| --- | --- |
| runtime/chat/{scope_queries,retrieval_queries,evidence_reads,generation_workflows,memory_producer} | 같은 Session의 여러 업무 조회·provider 조립·성공 후 Memory propose→commit/rollback. 실제 협력이며 이름만 바꾸기 위해 삭제하지 않는다. B5/B7 canonical read/model/factory 합류는 root 순차 통합에서 연결한다. |
| runtime/chat/sqlalchemy_service.py, services/messages.py | 동일 서비스 메서드 alias. 남은 실제 소비자는 runtime/memory_selection_provider의 credential 함수와 과거 테스트이며 B7/B8에서 canonical service와 원래 monkeypatch 계약에 대응해 종료한다. |
| runtime/chat/world_generation.py와 api/v1/routes의 옛 Chat 3파일 | 실제 workflow/HTTP body 없음. 기존 검사 alias이며 제품 API는 canonical router를 사용한다. A2 구조 node와 새 HTTP 동작 회귀의 대응을 기록하고 B8에서 제거한다. |
| compatibility/chat_service.py, chat_runtime_contract.py, chat_generation_lifecycle.py | 원래 forwarding 전용 구조 검사 보존. 신규 제품 호출 없음. B8에서 원래 assertion/node와 실제 서비스·repository 회귀를 일대일로 대응한 뒤 퇴역한다. |
| chat/public.py·schemas/messages.py·models/messages.py·runtime/chat/model_bindings.py·옛 api marker | 동일 객체 집합/미사용 표면. B8/G5에서 import 및 frozen source/test 대응을 확인해 제거한다. 전체 모델 집합으로 새 소비자를 연결하지 않는다. |
| chat/infrastructure의 model alias와 migration helpers | 과거 Alembic/embedded migration과 baseline rebuild의 실제 소비가 있다. G5/B8의 정확한 등록/역사적 helper 승계와 별개이며 파일명 정리 때문에 migration 본문/DDL을 바꾸지 않는다. |

이 source는 Chat 자체의 역할 이전과 HTTP 연결을 준비한 상태다. B4/B5/B7 합류·G5·G06·B8 호환 제거·Hosted CI·신규 installer·설치 데이터 업그레이드 및 전체 백엔드 종료는 완료로 표시하지 않는다.


### PR #283 첫 원격 Gate와 실행 경로 검사 보완

Head `39efec7`의 Security 전체는 PASS였으나 Core backend는 pytest 전 현재 Memory batch inventory hash 5개에서, Local autonomy는 옛 `tests/test_activity_proposal_runtime.py` 실행 인자에서 실패했다. 제품 소스/원래 테스트 단언을 추가 수정하지 않고 검토된 실제 `tests/relationships/test_activity_proposals.py`를 실행하도록 연결하고 현재 inventory만 원래 generator로 갱신했다. immutable Today predecessor와 모든 schema/budget 계약은 유지했다.

전체 pytest 수집만으로 별도 smoke 명령의 사라진 파일을 발견하지 못했던 점을 보완했다. 기존 CI policy가 실제 workflow pytest step의 literal Python 테스트 경로를 읽어 파일 존재를 확인하며, POSIX/Windows·backend 상대 경로를 지원한다. 실제 새 위치가 존재해도 옛 위치를 거절하고, 유효했던 파일을 삭제하면 거절하는5개 신규 사례와 기존 CI/활동/Memory inventory 관련 검증은 **18 PASS /9.59초**다. 동적 shell 표현과 실제 실행 결과는 해당 workflow가 계속 검증하며 이 정적 검사가 대신하지 않는다. 초기 집중 명령의 존재하지 않는 inventory 테스트 인자는 실행 전 오류로 별도 남기며, 수정 명령의18개 결과만 PASS로 계산했다.

Custom history도 후보 `0108a3a`의 전체786 ancestor만 가진 별도 bare 저장소에서 **8,718 blobs /치명0**을 확인했다. 공유 저장소의 미합류 B8 경로3건과 구분했으며 원래 scanner·exact allowlist25·검사 범위 규칙은 변경하지 않았다. 원격 backend 전체·Local/Host/installer는 수정 head에서 다시 확인한다.


## AR-B6 Chat 순차 통합 후보 — 2026-09-06

검증된 B5 PR 후보 `32d27461`의145개 원장 prefix에 Chat 실제 source `74f6c06`까지를 합쳤다. 별도 merge `da73211f`와 CI 경로 회귀 승계 `6845f7d2`에서 B5 실제 Social/Relationships 계약을 Chat의 generation/evidence/Today reader에 연결했다. 두 앱의 기존 Package·Routines 조립과 새 Chat DI를 함께 유지했으며 Health/URL/operation ID 및 같은 Session·raw NDJSON·provider/rollback 순서는 원래 source를 따른다.

고정6845의 Chat·쪽지·Planner·Both·근거/Today·권한 집중44파일은 **273 passed / 기존1 warning / 98.33초**다. 현재 구조는 **1007 modules / 3769 edges / legacy126**, public196 operations이며 route 보안 module은 Chat 원래 source에서 이미 정확히 전환돼 추가 변경이 필요 없었다. 이전 helper가 '수정할 항목 있음'을 가정한 검사에서0항목을 보고 중단한 것은 제품 실패가 아니며 실제 module/endpoint/access 비교는 일치한다.

원본 Chat signed8개의 snapshot은 고립된 Git archive에서 수집한 기존 자료의 commit/tree를 대조했다. 새27파일 증거와26노드를145개 불변 prefix 뒤에 append해 총153개 기록을 보유한다. 원래 checkpoint/baseline/단언/skip은 그대로이며 stock 전체 Gate와 최종 backend/PR/installer는 다음 확인 항목이다. Chat의 두 runtime collaborator는 B5에서 실제 소유한 Social block query의 동일 함수에 직접 연결해 옛 Relationships 집합을 경유하지 않는다.

이 후보에는 B7 Memory·Runtime·G5·G06 제거 ancestry를 합치지 않았다. 해당 후속 owner로의 실제 연결과 기록된 Chat 역사 테스트 alias 종료는 계획한 다음 PR에서 수행한다.

최종 Social block query 연결은 두 runtime collaborator가 실제 같은 함수 객체를 사용함을 확인했고, 실제 경로의 preflight·HTTP 보안 회귀 **11 PASS / 7.58초**다. 앞선 명령의 존재하지 않는 테스트 파일명은 pytest 수집 전에 종료됐으며 제품 실패로 집계하지 않는다. 원래153개 source 기록 뒤의 API/ORM/assertion/node 및 backend 전체 검증을 이어간다.


### AR-B6 최종 로컬 전체 및 보존 연결 보정

고정 `618ca6222fadad6457732616bda00336cc65c601`의 전체 backend는 **2393 passed / 기존22 skipped / 27 warnings / 729.45초**다. 첫 stock은 API/ORM·단언·suppression 및 보호2415=현재2415를 유지했지만 현재 split 소비자 경로3곳에서 종료했다. Character source 조회는 실제 `chat/service/profiles.py`, Graph Validator는 실제 `chat/service/graph_retrieval.py`, Executor는 그 서비스와 `runtime/chat/generation_workflows.py`의 현재 import/call로 목록을 맞췄다. 원본 symbol/파일 및 테스트 이동 지도, 원래 단언과 source 내용은 바꾸지 않았다.

Gitleaks current tree의1건은 최초 signed `57528d22072f7541e7f1f1b982071afd5c1d537c`에서 도입한 Identity message_credentials source의 Git blob40이었다. 원장 key/value와 실제 Git object를 대조한 뒤 metadata 경로·generic-api-key 규칙·정확한 전체 key/hash 행1개에만 적용한다. 같은 행 comma 유무2개는 통과하고 hash/key/prefix/suffix/path 변형5개는 실제 Gitleaks에서 계속 검출됐다. 검토 설정으로 후보의 원래 tree와 HEAD 전체 history는0 findings이며 제품·원장·기존 assertion을 수정하지 않는다. 처음 실패한 stock/Gitleaks 결과는 이력으로 남기고 보정 head의 stock/집중을 확인한다.

## AR-B7 Daypart — 활동 관찰·행동 기억의 실제 소유 이전

Memory A9 기반과 B4 signed `6beec5d`를 병합한 뒤 AgentDaypartMemoryEvent의 실제 class를 `memory/models/daypart.py`로 옮겼다. 기존 단일 Base/table/FK/column/default/relationship은 같다. Daypart 저장·조회·요약, feed/inbox 중복 admission과 실제 제공 기록은 Memory의 service/repository/policies가 소유한다. Resident prompt와 Memory가 함께 쓰는 중립화 clipping은 원문 함수 하나를 `core/context_clipping.py`로 옮겼다.

기존 Daypart/LangGraph **204 passed**이며, 새 file SQLite 회귀는 **4 passed / 5.20초**다. 독립 observer로 개별 commit이 보이는지, 같은 timestamp의 ID 정렬과 64/20/12 한도·Character/session/source ID 범위, inbox commit 다음 author 오류·재시도 admission, summary 그룹별 실패 rollback·다음 그룹 진행·재시도를 검증한다. 첫 새 조회 회귀의 기대 목록에 다른 Character ID를 포함한 fixture 오류가 있었으며 실제 기존 Character 필터를 반영하도록 그 새 목록만 수정했다. 기존 test/assertion/skip은 수정하지 않았다.

실제 source 정의 16개는 함수 이름과 지원 Protocol annotation 외 전체 AST가 같다. 나머지 7개는 caller timezone·동일 Session author callback·두 query의 인자 및 summary UoW 분리를 명시적으로 비교한다. 관계 point expiry를 먼저 처리하고 Memory가 이후 summary를 저장하는 순서, 각 commit/rollback, 시간대 시작 직전 1microsecond timestamp, 3일 조회, source IDs, 문자열/문자수·prompt 형식과 provider 호출 위치는 원래 의미를 유지한다.

| 남은 책임 | 소유·종료 단계 |
| --- | --- |
| 활동 flag/allowlist·시간대 session key·행동 선택·LangGraph/provider 실행 | AR-B4 resident; 새 Memory 동작을 원래 위치에서 호출 |
| 관계 Point 상태·만료 | AR-B5 Relationships; 실행 조립에서 Memory 저장 전에 호출 |
| Post/Character 작성자 읽기 | AR-B4 실행 소유의 same-Session callback; Memory는 외부 ORM을 import하지 않음 |
| global ORM export·기존 계정/캐릭터 삭제 SQL | AR-G5/AR-B8의 정확한 등록·다중 업무 UoW 소비자 정리 |

현재 부분 경계 **720 modules / 2,426 edges / exact legacy 222**, cycle 0과 L4 parity97·ER0·Memory batch live inventory가 통과했다. 전체 보존·확대 회귀 및 signed source 고정은 진행 중이며 최초 source/node capture, 순차 통합, Actions/installer/PR/merge는 별도 단계다. frozen source/checkpoint/승인 node/API/ORM 및 역사 migration은 변경하지 않았다.


Daypart 최종 고정 후보의 확대 회귀는 **265 passed / 66.73초**다. 실제 정의 16개 전체 AST와 명시적으로 분리한 본문·SQL 7개 모두 원문과 동치임을 확인했다. Stock 전체 보존은 아직 append하지 않은 선행 B4 두 파일의 최초 도입 경로에서 중단한다. 읽기 전용 진단은 signed `869bae55a2e5e665fb731396a7284b53dde8a104`의 정확한 두 blob만 메모리에 보충하여 원래 checker 함수를 실행했고 **source/split/assertion/suppression/API·ORM/node 각각 오류 0**, 보호 **2,201 / 현재 2,246 nodes**다. merge history simplification을 피한 `--full-history --no-merges`로 실제 최초 도입을 확인했다. 이 진단은 additions capture나 stock 전체 Gate PASS가 아니다.

A9에서 이미 제거한 recall source를 가리키는 feature inventory의 K12/K15/K16/K22/K23 현재 경로 다섯 곳도 actual `repository/recall.py`·`recall_records.py`로 연결했다. Root의 후속 Memory current-path 정리와 동일한 소유 기준으로 통합한다. 이번 source에 처음 들어오는 파일은 제품 7개·회귀 1개, 신규 test는 4 nodes다. 각 source의 최초 SHA 및 capture는 signed source 고정 후 부모의 선형 통합에서 기록한다.


### Memory Daypart/B4 합류의 관찰 fixture 순서 정합성

Signed merge `299d7043a64e0eb888d3fc3fdf31af24ce8b1ef4`는 Daypart source `d83ef86c8c9e4acbec3c4d47b37b9738f7924fdf`와 선행 실제 Routines 타입·일부 Social 소유 source를 합류했다. A10 근거 판정은 그대로 두고 실제 외부 Routines 모델 import만 runtime source queries에 적용했다. 현재 source/table·서비스와 외부 SQL을 서로 반대로 덮어쓰지 않았다.

첫 합류 회귀는 **44 passed/1 failed**로 기존 Memory source reader의 fixture commit이 FK 오류를 냈다. SQL trace는 `Post` INSERT 전에 `WorldCharacterFeedObservation` INSERT가 실행됨을 확인했다. 두 모델의 실제 module 위치가 분리되며 SQLAlchemy mapper 정렬이 바뀌었고, 원래 fixture가 관계 없는 두 mapper를 `add_all`로 동시에 저장하는 순서에 기대고 있었다. 해당 테스트는 게시물을 add/flush한 뒤 관찰을 add하도록 준비 순서만 명시했다. API/ORM/FK·기존 assertion은 유지한다. 실제 production 관찰 생성은 existing Post를 조회하고 `begin_nested()` 진입 시 pending flush 후 관찰 add/flush를 수행하므로 같은 simultaneous add_all 경로가 없다. 수정 후 같은 합류 묶음 **45 passed/16.06초**다.

### AR-B7-A11 Memory 누락 원본 복구와 동의 epoch 소유

Source `bc1a7c18997034b6f96965943323a617b3f9feef`에서 복구 순서·epoch 스캔 진행·최종 commit은 `memory/service/reconciliation.py`, 실제 Memory epoch/anti-join/delivery SQL은 `repository/reconciliation.py`가 소유한다. 외부 Post/Reaction/Social/Chat/Observation의 기존 다섯 source catalog는 `runtime/memory/source_catalogs.py`가 구성하고 Memory가 전달받아 같은 Session에서 조회한다. Runtime worker는 실제 서비스를 실행한다.

최종 formatted 함수의 네 repository 본문과 foreign catalog를 다시 펼치면 **전체 원래 workflow AST와 정확히 동일**하다. missing epoch32·회전 scope16·source별32 제한, `[opened_at, closed_at)` 동의 기간, 원본별 누락 anti-join, late row 복구, 기존 kind/source ID·단일 commit을 보존했다. 이전에는 worker에 있던 같은 복구를 서비스가 실제 소유하며 새 policy나 provider 호출은 없다.

배치 runtime/안전/API 및 rollback 회귀 **37 passed / 2 warnings / 14.97초**, 원래 전체 split 검사 **0 errors**, 경계 **726 modules/2442 edges/exact legacy222 PASS**, L4 parity97·current batch·ER0 81/87/24/44/7 PASS다. 초기 부분 scope 기록에서 repository를 외부 entry에 잘못 넣은 항목은 검사에 거부되어 제거했고, repository는 실제 내부 소유 모듈로만 검사한다. 검사 규칙을 완화하지 않았다. Source introduction capture와 B4~B6 순차 합류/전체 B7 Gate는 계속 남아 있다.


### AR-B7-A12 Memory 집합 import 종료와 실제 역할 연결

Source `2056bce963e7bae027dfc73265c060f4be390604`는 기존 집합 모듈의 이름 273개가 가리키던 실제 값·타입·함수 객체를 `is`로 확인하고 25개 소비자를 해당 정의 파일로 연결했다. 사용하지 않는 public/domain/API 집합 파일을 제거했고 service/contracts/runtime package는 일반 namespace marker로 남긴다. 기존 Unit of Work 구현은 본문 AST를 유지한 채 `repository/transaction.py`로 이동했다. 불변 SQLite/Alembic revision이 참조하는 다섯 schema export만 정확한 역사적 alias로 유지한다.

Memory·회상·Chat 근거·배치·실행 조립 **295 passed / 2 warnings / 118.57초**, 경계 **723 modules / 2420 edges / exact legacy222 PASS**, L4·current batch inventory도 통과했다. 기존 검사 본문이나 API/ORM 계약은 변경하지 않았다.

전체 stock 보존 실행은 **FAIL/PENDING**으로 남긴다. 최초 오류는 선행 Routines에서 처음 생성된 `models.py`와 `schemas.py`의 이후 이동을 아직 도입 원장에 연결하지 못한 것이다. 둘의 실제 최초 signed source는 `869bae55a2e5e665fb731396a7284b53dde8a104`로 확인했다. 이 오류 이후 protected0/current2246 및 다수 introduction 오류가 출력되므로 이를 전체 보존 PASS나 단순 신규 테스트 누락만으로 해석하지 않는다. 순차 B4~B6 합류와 원본 commit별 source/node capture 뒤 stock gate를 다시 통과해야 한다. 실제 이동 map이나 frozen baseline을 삭제하여 통과시키지 않는다.
B7 순차 후보는 B6 제품 후보 `ef71ceae`에 Memory `16f70f30`을 합친다. 이 source는 Daypart `d83ef86c`를 이미 포함한다. G5·G06·Runtime 후속 ancestry는 앞당기지 않고 기존 두 앱의 Character credential/activity·Package·Routines·Chat 초기화와 새 Memory workflow 등록을 함께 유지한다.

Memory가 소유하는 실제 repository/service와 명시적인 source/scope/recall runtime factory를 새 Chat 소비자에 연결했다. 같은 Session의 canonical 읽기·flush/commit/rollback 순서는 원래 source를 따른다. 원래 A12의 export ledger로18개 소비자를 실제 정의로 연결하고, B5의 실제 Social 모델6개와 B4 LG의 실제 Memory SQL/정책을 각 owner로 승계했다. 원래 Daypart에 남겨 둔498개 다른 업무 symbol은 검토된 기존 B4 decomposition을 그대로 이어받으며 원본 source/test map을 삭제하지 않았다. 현재 destination/consumer/test navigation907건을 실제 경로에 맞췄다.

첫 수집은 옛 Social 모델 집합과 Memory router import 때문에 중단됐고 실제 경로 연결 뒤 **2428개 collection PASS**다. 고정67파일 검사는 **608 PASS / 2 FAIL / 5 warnings / 523.58초**였으며 두 실패는 기존 테스트의 concrete repository 생성에 필요한 same-Session factory와 inspector inventory generator의 옛 Memory contract import였다. 단언/fixture의 업무 의미를 바꾸지 않고 두 import를 연결한 뒤 실패 파일과 Memory scope/source/daypart 회귀는 **29 PASS / 32.43초**다. 존재하지 않는 보조 테스트 경로를 포함한 중간 명령은 수집 전에 종료됐으며 결과에서 제외했다.

별도 읽기 진단의 첫 입력 구성 오류도 기록한다. archive의 전체 test 목록을 희소 assertion 자료에 직접 붙이거나 assertion 자료가 없는 #258 source baseline을 단언 비교에 포함한 진단은 중단했다. 제품 checker와 같은 원래 #263/additions 구성 및 원래 수집기 방식으로9개 signed source의 신규 증거를 메모리에서 계산한 최종 진단은 **assertions0 / split0**이다. baseline/checkpoint/원장·원래 test assertion/skip은 변경하지 않았다. 현재 구조 **1036 modules / 3872 edges / legacy124**, API public196·현재 L4/ER0/Memory batch inventory도 확인했다. 다음 metadata commit에서 B6 원장153개를 불변 prefix로 유지해 원래9개 도입을 append한 뒤 공식 stock·backend 전체·PR Gate를 수행한다. 이 상태를 B7 최종 완료나 전체 backend 종료로 표시하지 않는다.

## AR-B8 G06-A — B7 순차 후보의 실제 factory 통합

기준은 signed B7 `274f90e7bd811d1715f4e6dc2c1e423115ec4671`이다. 원래 G06 준비 `90d7fd7f2332b2b27cf2f1bd92ed0e206427e6f7`·`cc513f4bc078f0547d626d97bbf2210e424b27cb`의 실제 factory와 실행 참조 변경만 현재 B7에 적용했다. 미래 Runtime·Tree·Lore·LocalBot callback이나 G5 Base/database를 앞당기지 않았다.

실제 제품 변경은 `main.py`, `public_main.py`, `runtime/contributor_backend.py`, `runtime/desktop_sidecar.py` 네 파일이다. `main.create_app`과 `main.create_lifespan`이 실제 구현 하나를 소유하고 `main.app`·`main.public_app`은 원래 full/public health와 lifecycle 기본값을 선택한다. 임시 `public_main.py`는 원래 53줄·15개 export의 바이트를 유지하며 public partial 및 동일 객체만 가져온다. 두 launcher는 기존 모델 등록→upgrade→설정→앱 생성 순서를 유지하고 실제 public factory를 import한다.

현재 B7의 Character·World Package·Routines·Chat·Memory·Social·Relationships 연결 26문장의 순서와 내용이 그대로다. 원문 비교 15항목에서 정의7개, lifespan 본문·기존 인자, 명시 profile 선택 외 factory 전체, CLI의 exact ASGI 문자열 외 본문, launcher 두 파일 전체 AST가 같음을 확인했다. 기존 19개 테스트 파일의 155함수/509단언·예외 기대와 suppression은 보존되며 새 3개 테스트 파일(21 nodes)은 원래 `cc513f4` 소스와 바이트가 같다.

초기 집중 검증은 **230 PASS / 3 timeout / 1 warning / 388.53초**다. 같은 제한으로 직접 관련 15개를 재실행해 **13 PASS / 2 timeout / 216.60초**였고 contributor·sidecar의 실제 DB 초기화(기존 60초)는 통과했다. 남은 lazy import·sidecar HTTP의 기존 30초 probe만 단독 재실행한 결과도 처음에는 **2 timeout / 87.54초**였다. 실패 뒤 해당 probe 자식 프로세스 잔존은 없었다.

저장소 코드와 timeout을 바꾸지 않고 외부에서 정확한 cold 입력을 실행하면 16.74초, 시스템 임시 폴더에서는 18.28초에 정상 종료했다. 25초 stack dump를 예약한 진단 실행도 dump 없이 두 검사가 통과했다. 진단 삽입을 제거한 **원래 두 검사의 최종 실행은 2 PASS / 30.82초**이며 각 case는 10.93초·11.15초다. 이 기록은 앞선 시간 초과를 없던 결과로 바꾸지 않으며, 원인을 특정 제품 결함이나 단순 동시 부하라고 단정하지 않는다. 별도 실행들의 PASS를 합쳐 동일 후보 전체 suite PASS로 표시하지 않는다.

최종 읽기 delta 검증은 기존 단언·suppression, G5 미변경, frozen 문서 미변경, ASGI profile, API/ORM 모두 오류0이다. full/public 각 **196 operations**, ORM **102 tables**가 #258/#263 계약과 같다. Public 승인 **604 / 현재 2449 nodes** 검사가 통과했다. 현재 구조는 **1036 modules / 3854 edges / legacy123 PASS**이며 ER0·L4·deferred·public route·현재 Memory batch inventory를 실제 후보로 연결했다. frozen predecessor inventory, baseline/checkpoint/additions는 바꾸지 않았다.

이 단계는 G06-A source 준비다. 원본 source/node의 append-only capture·공식 stock·순차 PR/CI는 부모 통합에서 수행한다. G5 이후 alias가 있는 고정 후보의 삭제 전 검사, AR-B8-B의 실제 alias 제거·엄격 원문 증명과 제거 후 fresh bundle/installer·전체 backend 검증은 별도 완료 조건으로 남는다.
