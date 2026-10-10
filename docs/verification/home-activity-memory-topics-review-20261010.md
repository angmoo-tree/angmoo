# 기기 홈·활동 설정·SNS 기억 출처·World 주제 I00–I63 재검토 — 2026-10-10

## 1. 결과와 범위

통합 계획의 I00–I63 64단계, V01–V28 28묶음, 원본 H48/S24 단계·H21/S17 검증·
H C/A72를 현재 코드·기존 실행 자료와 대조했다. 제품 예외 두 가지와 문서 누락을
발견해 보완했다. 아래의 완료는 관련 로컬 구현·검증·문서·커밋 기준이다.
원본 사용자 DB 적용·실제 AI 품질·CI/PR/main·배포·설치 앱 완료와 구분한다.

| 항목 | 이번 재검토 |
| --- | --- |
| 저장소/브랜치 | angmoo-tree-angmoo / feat/0.1.0-release-readiness |
| 시작 HEAD | e9c3538e44fd1598a6d418f310d9646629ec48a5 |
| 시작 작업 트리 | clean |
| 제품 변경 | Characters 등록 예외 처리, 중립 auth/runtime 수명 hook, CredentialFields 및 Media 정책 카드의 수명 연결 |
| backend/DDL 변경 | 없음. SQLite v35 / Alembic 20261010_0112와 과거 schema·migration 그대로 |
| 실제 AI·이미지·임베딩 | 0회. 합성 HTTP fixture만 사용 |
| 원본 사용자 데이터·키·Compose | 접근/적용/재검사/재시작 없음 |
| 허용한 실행 | 시험 전용 Next 3370·static-shell 3371, 관련 브라우저·타입·의존성 검사와 로컬 커밋 |
| 미실행 | push·PR·CI·main 작업, 전체 검사/build/export, 설치/native/실기기, 원본 36건 적용 |

화면 표현의 출처는 **LOCAL**이며 기존 Button·alert·한국어/영어 안내를 재사용한다.
새 색상·폰트·외부 자산·의존성을 추가하지 않았다.

최초 구현의 backend/Docker/브라우저 실행 수와 사본 36건 판독은
[통합 구현 검증 기록](home-activity-memory-topics-integration-20261010.md)에 보존한다.
backend는 재검토 시작 HEAD와 동일해 관련 기존 검증 근거를 재사용했으며,
이번에 전체 backend/Docker를 다시 실행했다는 뜻이 아니다.

## 2. 발견한 누락과 수정

### 2.1 등록 완료와 설정 연결 실패의 분리 — I47–I49 / V05–V06

기존 코드는 등록 완료 응답의 registration_scope가 없거나 World/character가
맞지 않으면 등록 성공 처리를 하기 전에 오류를 던졌다. 실제 등록은 끝났지만
UI는 확인 단계에 남고 선택 단계의 건너뛰기가 없었다. scope 누락을 주입한
브라우저 시험에서 수정 전 실패를 재현했다.

Characters는 성공한 등록 결과와 completed receipt를 먼저 유지한다. scope가
유효할 때만 설정 카드를 조립한다. 연결 실패 시에도 같은 여섯 번째 단계에서
등록 완료·오류·등록 결과 확인·완료·건너뛰기를 제공한다. 등록 결과 확인은
같은 durable receipt의 idempotent 완료 응답을 재조회하며, 초안을 다시 PATCH하거나
캐릭터를 추가 등록하지 않는다. 재시도 실패·새로고침·건너뛰기에도 자동 저장/ON은 없다.

scope 누락, 다른 World, 다른 character를 각각 시험했다. ko/en 안내, 실패 재시도,
성공 복구, 새로고침 후 재실패·Skip, 등록 1회·설정 쓰기 0회를 확인했다.

### 2.2 사용자·실행 환경 전환 시 미저장 입력 격리 — I08 / I45 / I49 / I51

기존 생성 화면과 Media 카드의 key는 World/actor만 포함했다. 여섯 번째 단계에서
auth owner가 바뀌어도 등록 완료 화면과 미저장 외형·Comfy Partner 키가 남았다.
수정 전 브라우저 시험에서 이전 입력이 그대로 남는 실패를 재현했다.

`hooks/use-auth-runtime-identity`는 scope·user·session revision·runtime revision을
React component lifetime key로 만든다. AgentCreateClient, CredentialFields,
WorldImageGenerationCard와 WorldVisionControls가 이를 사용해 이전 입력을 비우고
기존 effect/abort 수명을 종료한다. 같은 scope의 일반 refresh·CAS 충돌 병합·
provider 전환 처리는 각 feature에 그대로 있다. hook은 업무 API·권한·DTO를 소유하지 않는다.

owner/runtime 전환 뒤 이미지 입력과 미저장 Partner 키가 비워지고 자동 쓰기가
없는지 확인했다. 새 owner의 옛 receipt 조회가 403이면 기존 등록 완료 화면/설정
카드를 유지하지 않는지도 확인했다. aggregate busy는 unmount 때 해제한다.

### 2.3 문서 누락 — I56 / I61

계획 머리말과 작업 정의에는 §13의 실제 구현 결과와 모순되는 “미실행/모두 계획”
표시가 남아 있었다. 현재 결과로 바꾸고 §12의 최초 작성 기록은 보존했다.
기능 보존 지도에는 10-10 경로가 없어 기본 설정·SNS 출처 binding·World 주제 종료·
최종 UI·scope 수명을 추가했다. frontend ARCHITECTURE/DESIGN과 최초 verification에
이번 예외 보완을 연결했다. 역사 inventory·schema·기존 실행 수는 덮어쓰지 않았다.

## 3. 이번에 실행한 관련 검증

| 근거 | 결과 | 실제 범위 |
| --- | --- | --- |
| R1 브라우저 | 22 passed, 약 1.1분; 재시도 0·skip 0 | 새 예외 6개 + 기존 관련 5개를 Next/StaticProductRouter 각각 실행. 새 예외 총 12개, 기존 총 10개 |
| R2 ESLint | 제품 TS/TSX 4개, exit0 | 새 hook과 변경 Characters/Media/CredentialFields, max-warnings0 |
| R3 제품 타입 | exit0 | 원래 strict tsconfig를 extends한 변경 파일과 실제 전이 imports, noEmit |
| R4 시험 타입 | exit0 | 변경 browser fixture/config/spec 3개 및 실제 imports. 전체 browser typecheck PASS로 확대하지 않음 |
| R5 의존성·설계 | 4 seed / 63 transitive files / 143 edges, 경계 오류0 | 실제 import 추적. raw color·any·suppression 증가0, undefined token0, 의존성 변경0 |
| R6 추적·보존 | I64/V28, 원본 I72/V38/C·A72, 원본 H/S hash 동일 | 현재 계획·기존 검증 표·소유 파일·소스 대조. backend 변경0, 기존 사본 판독 36행 보존 |

브라우저 기본 설정 시험은 ko/en의 저장 정책·키 등록 후 ON·draft World를 포함한다.
기존 등록 시험은 OFF 등록·응답 유실·receipt 재응답·reload·skip을, 저장 시험은
정책 저장 후 키 실패와 dirty 취소를, 편집 시험은 다른 항목 병합·같은 항목 충돌·
runtime 전환 입력 격리를 확인한다. 네트워크는 fixture가 제공하며 실제 provider 호출은 없다.

첫 보완 시험에서 Next route announcer도 role=alert라 새 시험의 단일 alert locator가
충돌했다. alert를 해당 등록 section으로 한정해 시험을 바로잡았다. 제품 검증을
완화하거나 오류 안내를 제거하지 않았다. 최종 22개는 모두 통과했다.

`static-export`는 프로젝트 이름이며 이번 실행은 **실제 StaticProductRouter를 사용하는
static-shell dev**다. production static export·native bridge·설치 앱 시험은 아니다.
최초 구현의 static-product-shell 타입 오류 3개는 이번 관련 시험 타입 PASS와 별개다.

증거는 workspace ignored `.local-diagnostics/home-activity-memory-review-20261010/`의
browser-results.json, frontend-static.json, scoped-static.json, review-audit.json 및
수정 전 DOM 재현 자료에 있다. 브라우저 artifacts는 제품 저장소 ignored
`artifacts/home-activity-memory-review-20261010/browser/`다. 원본 대화/실제 키를 커밋하지 않는다.

## 4. I00–I63 전체 대조

아래 B/U/D/H/S 번호는 최초 verification의 해당 실행 근거다. R은 위 새 검사이며
변경되지 않은 backend 근거를 이번 실행으로 다시 합산하지 않는다.

| 단계 | 대조한 구현·증거 | 재검토 결과 |
| --- | --- | --- |
| I00 | 현재 branch/시작 HEAD/clean, workspace·하위 지침 | 확인 |
| I01 | H48/S24·V38·C/A72와 통합 범위·제외 계약 | 확인 |
| I02 | 소유 DTO/service/repository/runtime/composition·schema 경계 | 확인 |
| I03 | 기존 부모 오류 합성 fixture와 새 scope/owner 오류 재현 | 확인·보완 |
| I04 | narrow basic activity DTO·GET/PATCH, B1 | 확인 |
| I05 | 로컬 owner·draft 세 카드 관리와 실행 권한 분리, B1/D1 | 확인 |
| I06 | basic/full settings의 공통 정책 저장·read 무쓰기, B1 | 확인 |
| I07 | SNS purpose/revision·scope·빈 키 보존, B1/U1/R1 | 확인 |
| I08 | image 정책/credential·OFF/20·vision10·입력 수명, B1/D1/R1 | 확인·수명 보완 |
| I09 | read/dashboard/ON의 실제 저장 eligibility 공유, B1/R1 | 확인 |
| I10 | ON/OFF·key 회전·policy revision·환경 경쟁, B1 | 확인 |
| I11 | basic backend 관련 권한/저장/gate 검증, B1/D1 | 기존 근거 확인 |
| I12 | Today parent/source/target/root ID 계약, B1 | 확인 |
| I13 | 이벤트·본인 게시글 두 Today 생산자, B1 | 확인 |
| I14 | 최종 projection/name/budget 입력 쌍·모순 SDK 전 차단, B1 | 확인 |
| I15 | 실제 전달 parent의 capture·범위/hash, B1/D1 | 확인 |
| I16 | 새 SNS receipt/저장·성공 결과·negative, B1/D1 | 기존 근거 확인 |
| I17 | typed binding·exact path/same-record/전체 본문 hash 순수 정책 | 확인 |
| I18 | 같은 Session의 canonical 자식·부모 Runtime source resolver | 확인 |
| I19 | append-only fixed binding/ordinal·원본 proof 불변 | 확인 |
| I20 | v35/0112 새 binding table와 등록·과거 builder 불변 | 확인 |
| I21 | 원본 integrity 확인 후 같은 restore_context proof view | 확인 |
| I22 | receipt savepoint·memory/outbox/binding 동일 UoW rollback | 확인 |
| I23 | detail/correction/hydration/recall/prior/HotBrief·현재 접근 | 확인 |
| I24 | 접수 v2/v3 revision 고정·명시 owner recheck·unknown 거절 | 확인 |
| I25 | 공유 근거/delete/discard·incremental eligibility·Chat 원문 | 확인 |
| I26 | Memory·공통 Chat·관계 관련 회귀, B1/B3/D1 | 기존 근거 확인 |
| I27 | staged upgrade/실패 보존·격리 Docker UID/network, D1 | 기존 근거 확인 |
| I28 | World catalog/관계 초기화와 추천 marker 분리, B1 | 확인 |
| I29 | World create/publish/startup/늦은 result 종료, B1/D1 | 확인 |
| I30 | 기존 access 뒤 World GET/PUT/POST 410, actor 요청 보존 | 확인 |
| I31 | valid actor common/World·OFF·shared ID/cache/history 사전 | 확인 |
| I32 | character panel 기능·DTO 유지, Feed 진단 DOM 제거 | 확인 |
| I33 | Studio World/actor 관심 도구·state/effect 조립 제거 | 확인 |
| I34 | topic 역사/원문/관계/key·새 actor 준비 관련 회귀, B1 | 기존 근거 확인 |
| I35 | Device Home만 footer composition 제거, U1/U2 | 확인 |
| I36 | 기존 icon/World·single scroll/safe-area/직접 복귀, U1/U2 | 확인 |
| I37 | 관계 header 20/12/48·graph/depth/evidence 보존, U1 | 확인 |
| I38 | engine/source/inherit/CAS·오류 유지, state/run DOM 제거 | 확인 |
| I39 | 저장 mood/강도/원문/confirmed_at·null/error/OFF 표현 | 확인 |
| I40 | active scoped GET·auth/runtime/abort·late response, U1 | 확인 |
| I41 | 상태 최상단 순서·World handle만 제거·다른 소비자 | 확인 |
| I42 | 독립 계획/6개 주제·44px aria chevron·요청0, U1 | 확인 |
| I43 | basic/상세 ActivityPolicyFields·dirty/reconcile/leave guard | 확인 |
| I44 | SNS 저장 후 actual eligibility 갱신·입력만 ON 불가, R1 | 확인 |
| I45 | feature slot의 세 카드 조립·auth/runtime 수명, R1/R5 | 확인·수명 보완 |
| I46 | autonomy-setup의 basic 경로·draft·Next/static, U1 | 확인 |
| I47 | OFF 등록과 같은 여섯 번째 선택 단계, B2/R1 | 확인·예외 보완 |
| I48 | scope 실패 분리·같은 receipt 재조회/reload·중복0, R1 | 확인·예외 보완 |
| I49 | 완료/Skip·dirty/busy·성공 저장 보존·이전 owner 차단, R1 | 확인·예외 보완 |
| I50 | Studio Activity settings의 같은 scope/route, U1/U2 | 확인 |
| I51 | 개시 후 같은 정책/SNS/image·다른 상세 카드·키 수명 | 확인·수명 보완 |
| I52 | 상태/설정/Studio 최종 조립·불필요 DOM/콜백 제거 | 확인 |
| I53 | 기존 ko/en의 등록 오류·재확인/Skip와 accessible alert, R1 | 확인 |
| I54 | 합성 scope/receipt의 실제 두 라우터 조작, U1/R1 | 확인·추가 검사 |
| I55 | 36개 exact parent 사본 적용 표·원본0·설명 누락 별도 | 기존 근거 확인 |
| I56 | architecture/design·기능 보존 지도·최초/재검토 기록 | 확인·문서 보완 |
| I57 | 변경 strict type/lint/import/token·시험 타입, R2–R5 | 재검사 통과 |
| I58 | backend 변경0, 관련 B1/B2/B3/D1 근거 유지 | 기존 근거 확인 |
| I59 | 최초 폭/글자/키보드와 새 ko/en·Next/static 예외, U1/R1 | 확인·추가 검사 |
| I60 | 제품 예외 두 건 수정·해당 회귀22와 정적 재검사 | 완료 |
| I61 | 64/28·72/38·C/A72, H/S source hash·기존 link, R6 | 확인 |
| I62 | 해당 diff·명시 staging·생성 설정파일 복원·시험 서버 종료 | 완료, 최종 결과는 workspace §14 |
| I63 | 같은 로컬 브랜치의 보완 commit·최종 HEAD/clean | 이 기록을 포함한 로컬 커밋, 실제 SHA는 workspace §14 |

## 5. 로컬 완료와 남은 확인 경계

최초 로컬 backend/frontend/docs 커밋은 각각 05685aa2, 14e288fd, e9c3538e다.
이번 보완은 제품·시험·관련 문서를 같은 브랜치의 추가 로컬 커밋으로 보존한다.
이 문서 자신의 commit SHA는 자기 참조하지 않으며 실제 Git log와 workspace 계획
§14에서 확인한다. 최종 diff·포함 파일·clean 상태도 종료 기록으로 확인한다.

시험 서버가 자동 변경한 tsconfig는 실행 전 내용으로 복원하고, 시험 dev가 새로
생성한 static-shell AGENTS/CLAUDE 파일만 제거한다. 기존 소스/사용자 자료와
historical 사본은 보존하며 원본 Compose 서비스에는 조작하지 않는다.

추가 backend 누락은 발견하지 않았다. 36건은 기존 **사본에서만** 복구 판독된 결과다.
이번에 원본 저장이나 재검사를 실행하지 않았다. 실제 API/자연 활동, 전체 CI,
production static export, native/installer·실기기, 원본 DB upgrade/기억 적용은
이 로컬 재검토 결과와 별도로 확인한다.
