# 백엔드 구조 전환 실행 결과

## 범위와 현재 상태

2026-09-05에 §8.2 AR-G0부터 AR-B8-B까지 실행을 시작했다. 사용자 검증·PR·merge는 이번 실행에서 위임받은 권한으로 수행하며, 각 검증은 실제 수행한 범위와 commit을 기록한다. Release/Production, §8.3 프론트엔드 이전, AR-X와 P8-L-S 실제 AI 품질·인과 검증은 별도 범위다.

출발점은 #263 merge `d7037625a19071eb279ad2ea35c3ace6fe5b5289`, tree `35ded40a2b5fd33d1a54dac3a396e72d24c88714`다. 원격 main과 로컬 HEAD가 일치하고 시작 시 작업 트리는 깨끗했다. 원본 #258 기준과 승인 public test 목록, frozen migration 자료는 계속 보존한다.

| 단계 | 상태 | 범위 |
| --- | --- | --- |
| AR-G0 | PR #265 · CI IN PROGRESS | 후속 체크포인트·부분 scope·단계/소유권·Actions 연결 |
| AR-G1 | NOT STARTED | 설정·개발 환경 경로 |
| AR-G2 | NOT STARTED | 실제 공통 오류·pagination |
| AR-G3 | NOT STARTED | logging.ini·초기화·배포 |
| AR-G4 | LOCAL VERIFIED · PR PENDING | Alembic 물리 경로·역사 본문 보존; G5 최종 모델 등록 연결 대기 |
| AR-B2 | IN PROGRESS · Identity + Characters foundation local verified | identity→characters→worlds→world_characters; 전체 전환은 미완료 |
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

## AR-G4: Alembic의 물리 경로와 실행 연결

`backend/app/alembic`의 90개 파일을 `backend/alembic`으로 옮겼다. 전체는 88개 revision과 `env.py`·`script.py.mako`이며, ER0가 출력하는 87개는 `20260825_0083`을 제외한 기존 역사 부분집합이다. 경로 대응표는 전체 90개를 보존한다. revision 본문·ID·`down_revision`·embedded SQLite v1~v9 및 frozen JSON은 수정하지 않았다.

`alembic.ini`의 script 경로와 import 경로를 설정 파일 위치에 고정하고, Docker COPY·ER0 현재 경로·현재 migration 테스트·P8 A/B의 현재 파일 탐색을 연결했다. P8 D/F/J/P/R의 역사 기록은 옛 경로·digest를 보존하면서 실제 읽는 revision 위치만 새 경로로 해석한다. D의 현재 업무·migration 계약 검사와 나머지 단계의 기존 frozen successor 검사를 유지한다. 경계 policy에서는 이제 `app` 패키지 밖으로 이동한 `app.alembic.env → app.models`의 exact legacy edge 하나만 제거했다.

새 `tests/migrations/test_alembic_layout.py`는 **8 passed / 9.63초**였다. #263에 기록된 전체 88개 revision의 Git blob이 일치하고 실제 Alembic revision 그래프의 단일 head `20260904_0089`를 확인했다. backend 밖의 임시 작업 디렉터리에서 Alembic CLI를 실행했으며, 실제 SQLite 메모리 연결에서 현재 checkout의 모델과 단일 metadata를 등록했다. 해당 연결은 빈 migration callback을 사용하므로 역사 PostgreSQL upgrade 본문을 실행하지 않는다.

G13은 물리 경로 이전까지 적용했으며 최종 완료가 아니다. AR-G5의 `app/models.py`·단일 Base·model 등록 이전 뒤 같은 Alembic 환경 회귀를 다시 실행한다. 현재 단계의 PR-head·merge·Actions 결과와 최종 백엔드 통합은 별도 기록한다.

기존 권한·migration 경로·P8 A/B/D·ER0 검증은 **50 passed / 1 warning / 25.50초**, embedded·Memory migration 회귀는 **25 passed / 29.81초**였다. 전체 합계는 **83 passed**이며 전체 backend suite를 실행한 결과로 확대하지 않는다. 보존 검사는 API/schema/ORM 계약과 test node에서 **#258 1,867 / #263 1,907 / 보호 계보 2,022 / 현재 2,030 PASS**, 승인 public **604 유지**였다. 새 테스트는 기존 CI backend의 전체 `tests` 실행에 포함된다.

현재 import inventory는 Alembic을 `app` 밖으로 옮겨 **591 modules / 1,827 internal edges / 311 exact legacy edges**다. 이 수치 감소는 업무 삭제가 아니며, 전체 90개 파일은 이동 전 원본 SHA-256도 일치한다. ER0는 기존 **75 PostgreSQL source / 87 역사 migration / 24 Neo4j query / 44 Next route / 7 parity workload**를 보존했다. P8 D의 현재 업무 계약과 F/J/P/R 및 Memory batch의 기존 역사 연결 검사가 모두 통과했다.

Gitleaks의 기존 공개 World 고정 marker 허용에 새 `0072` revision 경로 하나를 추가했다. 옛 경로는 history 검사를 위해 유지했고 marker 값·검사 rule 범위는 넓히지 않았다. 실제 Gitleaks 8.30.1의 새 Alembic 디렉터리 `--redact` 검사는 **0 findings**였다. 작업 디렉터리 전체 scan의 66건은 G4 base에 남아 있는 G0 체크포인트 hash 오탐 65건과 생성된 테스트 pyc fixture 1건이었다. 이 결과를 전체 보안 검사 PASS로 표시하지 않으며, G0 수정 통합 후 추적 source·PR history 검사에서 다시 확인한다.


## AR-B2-B1: Character 기반의 역할별 구현

`characters/models.py`는 기존 Character·CharacterState의 동일 ORM class와 Base를 유지한다. `contracts.py`와 `service/seed.py`는 World Package 호출자의 Session에서 add·flush만 수행하는 seed 계약을 보존한다. `service/profile.py`에는 핸들 정규화·충돌 처리와 프로필 조회·생성·갱신의 실제 구현을, `service/state.py`에는 기존 deferred-commit 계약의 상태 저장을 옮겼다. 일반 생성·갱신의 기존 commit/refresh를 seed의 flush-only 경계와 합치지 않았다.

`characters/schemas.py`가 Character 기본 입출력과 생성·프로필 입력 DTO를 소유한다. Public activity projection과 나머지 활동 DTO는 아직 기존 Social/활동 소유 파일에 있다. managed-media 경로 검증은 AR-B3 선행 의존성으로 `media/schemas.py`에 원문 그대로 옮겼으며 외부 URL·scheme·netloc 거절, `/media/` 경로 규칙과 오류 메시지를 보존한다. 기존 `schemas/media_security.py` 소비자는 동일 함수 객체를 제공하는 임시 호환 경로를 통해 유지하고 AR-B3에서 전환한다.

기존 `models`, `schemas`, `cruds/community`는 기록된 잔여 소비자에 대해 동일 객체를 제공한다. 새로운 Character service가 기존 수평 service/CRUD 계층으로 돌아가지는 않는다. 기존 `characters/domain`·`infrastructure`의 실제 구현과 빈 marker는 제거했고 출발 경로와 목적지를 보존 지도에 등록했다. 완료 도메인은 계속 `device_home`만이며 Characters와 media는 옮긴 module/entry/bridge만 정확히 검사한다.

현재 focused 검증은 **38 passed / 1 warning / 23.53초**다. 실제 SQLite에서 모델·schema 객체 동일성, 일반 생성 commit, seed caller rollback, 상태 저장의 deferred commit을 확인했고 기존 로컬 생성·프로모션·World Package import commit·owner-controlled WorldCharacter 및 media 참조 보안 검사를 함께 실행했다. API/ORM 계약·기존 assertion·node 보존에는 변화가 없었다. 이 작업 트리의 보존 명령 전체 exit 1은 선행 AR-G4 source commit의 신규 Alembic 테스트 8개 도입 증거가 아직 root 통합에 포함되지 않은 상태로 인한 것이며 전체 보존 PASS로 표시하지 않는다.

`services/agents.py`의 다업무 조립과 Creator·실행·삭제 경로, 남은 소비자·API·테스트 이전은 계속 진행 중이다. 이 기반의 로컬 검증으로 Characters 전체, AR-B2, PR-head, merge 또는 Actions 완료를 선언하지 않는다.

다음 head `de83dae`에서는 위 inventory 검사가 통과한 뒤 secret scanner가 체크포인트의 기존 synthetic Google API key fixture를 감지했다. #263의 `test_langgraph_resident_engine.py::test_generate_json_records_postprocess_error_on_repaired_success` assertion 및 기존 allowlist 4개와 값이 정확히 일치함을 확인했다. 고정 체크포인트를 수정하지 않고 해당 경로·규칙·값에 한정한 예외 1개와 원본 commit/test/blob·값 hash 증거를 추가했다. 기존 24개 항목은 그대로 유지했다. 관련 검사 **21 passed**, metadata **exact_tuples=25 PASS**, 현재 트리와 전체 Git 이력 검사 **fatal=0**이었다. 다른 경로·규칙·값으로 예외가 확대되지 않는 회귀 검사도 포함한다.

Head `88e4269`에서 다음 Gitleaks 단계가 체크포인트의 파일 blob·API/ORM fingerprint를 일반 API key로 감지했다(CI 64건, 같은 버전 Windows 재현 65건). 모든 발견 줄을 고정 체크포인트의 실제 Git blob SHA-1 또는 계약 SHA-256과 대조했고, 중복을 제외한 정확 key/digest 55줄만 해당 체크포인트 경로·해당 규칙에 허용했다. 파일 전체·임의 해시·다른 키는 허용하지 않는다. Gitleaks 8.30.1 디렉터리 및 **302 commits** 이력 검사에서 발견 0건, 실제 도구의 다른 파일/값/키/synthetic credential 음성 대조에서 각 1건 탐지를 확인했다. 관련 Python 회귀는 **12 passed**였다.

같은 head의 전체 backend CI는 **2,007 passed / 22 skipped / 1 failed**였다. 실패한 새 체크포인트 검사는 shallow checkout에서 #263의 경로 지도를 읽지 못했다. 이미 full history인 architecture job과 일치하도록 Core CI backend checkout에도 `fetch-depth: 0`을 연결했다. 테스트·기준 commit은 바꾸지 않았다. 수정 후보의 전체 backend와 Actions 결과로 이 Gate를 다시 판정한다.

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
