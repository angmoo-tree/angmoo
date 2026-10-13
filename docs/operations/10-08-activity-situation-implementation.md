# 10-08 Chat·SNS 상황기억 구현 및 로컬 검증 기록

## 범위와 판정

workspace의 `10-08 Chat·SNS 상황기억 영속 접수와 일일·종료 일괄 저장·색인 코드 구현 세부 계획.md` I00–I49를 구현한다. 코드·자동 회귀·합성 성능 측정·실제 AI 품질·사용자 확인은 각각 구분한다.

- 브랜치: `feat/0.1.0-release-readiness`.
- 시작 HEAD: `9c1d3868c7a547d1ef3af3c8078ad2684d92060f`, 시작 작업 트리 clean.
- I00–I47 구현·집중 검증, I48 전체 node 검증·미수행 구분, I49 최종 이력 보존·기록을 완료했다. 5,568개 중 5,527 pass·40 skip·1 fail·error 0이다. 남은 1개는 아래의 변경 금지된 설치 CI 목록 검사이며 전체 PASS로 표시하지 않는다. 이 기록과 append-only 검증 메타데이터를 후속 로컬 커밋에 함께 보존한다.
- 신규 활동 기본 policy는 `activity_situation`. 이미 접수된 request/run의 frozen policy는 덮어쓰지 않는다.
- push·PR·원격 CI·main merge·설치 앱 변경·실제 AI/임베딩/이미지 API 호출은 수행하지 않았다. CI workflow와 설치 실행 runner는 시작 HEAD와 동일하다. 개별 `scripts/ci` 명령은 계획 §14가 지정한 로컬 검사다.
- D03은 개발 Compose `angmoo_angmoo_contributor_embedded_data` volume의 `/var/lib/angmoo`만 대상으로 완료했다. 앱 컨테이너는 중지 상태이며 자연 AI 활동으로 검증하지 않았다.
- 디자인 참조 분류는 `LOCAL`이다. 기존 Memory 카드·공용 입력·버튼·semantic token과 Next/static 공용 화면을 확장했으며 외부 hosted 화면이나 별도 native 화면을 도입하지 않았다.

## 최종 구조와 실제 저장 경계

기존 Chat 최종 응답과 SNS DecisionDraft 호출의 마지막에 상황 설명을 받는다. 1,000 Unicode code point 이내의 부가 결과이며, 설명 오류가 정상 답변·활동을 탈락시키지 않는다. 새 policy에는 설명 전용 생성/수선 호출, 중요도 선별, 32개 묶기와 일일 통합 요약이 없다.

활동 결과와 receipt는 같은 Session의 한 transaction에 기록한다. 접수 직후에는 정식 기억이나 신규 색인을 만들지 않는다. 예약 시각, 첫 카드의 `지금 기억 저장`, 인증된 host 종료 요청이 고정 cutoff를 접수한다. 공통 소비자가 최대100개씩 MemoryItem·Evidence·Info·Source와 applied 상태를 함께 저장한다. 같은 logical activity/대상의 최초 기억은 한 번만 만들며 직접 삭제한 기억을 재시도로 복원하지 않는다.

SQLite가 canonical 원본이다. FTS와 768차원 Vec1은 개별 기억의 현재 description만 색인하며, 색인 실패와 무관하게 정식 기억 목록·상세를 읽을 수 있다. 원문은 선택 후 현재 권한·version·digest를 확인하여 제한된 분량만 읽는다. 원문 삭제와 변경/비공개를 구분하고 prior/background를 포함한 전체 입력 범위를 검사한다.

Memory가 접수·저장을 소유한다. Chat·WorldCharacters는 중립 계약과 주입된 port를 사용하고 Runtime이 구체 Memory 서비스/source adapter를 조립한다. 금지 import 예외, 별도 저장소, 가짜 bundle, 후속 독립 commit으로 원자성을 우회하지 않았다.

| writer | 안정 identity | 같은 transaction 참여 |
| --- | --- | --- |
| Chat | scope + response slot + chat + response slot | assistant/thought finalize 뒤, checkpoint/commit 전 |
| Inbox | scope + activity + inbox + conversation target | canonical effect/event/thought의 deferred UoW 안 |
| Feed | scope + activity + feed + post target | immediate publish/event/execution/thought transaction 안 |
| Routine | scope + activity + routine + routine-post | canonical post/beat/execution 저장 UoW 안 |

같은 target의 reply+Like는 하나이고 서로 다른 Inbox 대상은 각각 별도 receipt다. 계획과 확정 효과가 다르면 정상 효과는 보존하되 설명을 차단한다. receipt DB 쓰기 실패는 활동까지 rollback한다. 종료에는 신규 관계/요약 AI를 호출하지 않으며, 이미 적용된 기억의 검색 준비를 남은 시간 동안 관찰한 뒤 late result를 fence한다.

## I00–I49 추적

아래 `memory/…`는 `backend/app/domains/memory/…`, `runtime/…`는 `backend/app/runtime/…`다. 테스트는 별도 표기가 없으면 `backend/tests` 기준이다.

| 단계 | 실제 구현·증거 |
| --- | --- |
| I00 | branch/HEAD/clean·구조안·D01–D04·아키텍처·개발 data inventory·AI0 baseline 확인. |
| I01 | 위 네 writer의 안정 identity와 같은 Session commit 경계, runtime Chat/SNS participation. |
| I02 | 중립/Memory `contracts/activity_situation.py`, `policies/situation_output.py`: 독립 parser·target당1개·1,000자·digest. |
| I03 | `memory/models/activity_situation.py` 8테이블, FK/unique/run/request/cutoff·삭제 identity. |
| I04 | 단일 Base 등록·168 ORM 테이블·Alembic `20261008_0108_activity_situation.py`. |
| I05 | embedded v31 delta·frozen DDL/manifest·registry. |
| I06 | `repository/situation_runs.py`: 기존 예약/종료 값 승계, 신규 예약 OFF·22:30·종료 ON, 관계 AI 별도 gate. |
| I07 | populated upgrade·Alembic/embedded parity·기존 v29 secret/rollback 회귀. 역사 revision 본문 보존. |
| I08 | DeliveredInputManifest/DeliveredSourceEntry: source 범위·역할·최종 payload digest. |
| I09 | `runtime/chat/situation_memory.py`: current/recent/frozen evidence 실제 전달 순서. |
| I10 | SNS final target/parent/proposal/relationship/prior/image delivery adapter. |
| I11 | Routine activity/source events/previous success/completed/today 역할, Post와 DTO 구분. |
| I12 | admitted environment locale/activation epoch를 Chat request와 World activity frozen input에 저장. |
| I13 | Chat result/schema/parser와 response step의 상황 설명 결과 전달. |
| I14 | `policies/situation_generation.py` 영어 지침·Chat 마지막 필드·기존 호출/예산 검사. |
| I15 | Combined situations와 독립 parser, graph result의 명시적 manifest/draft. |
| I16 | Inbox/Feed target 대응, Like-only와 복합 행동 fixture. |
| I17 | Routine plan/title/body 다음 설명, 기존 post/image/state 및 recovery writer 연결. |
| I18 | `runtime/test_activity_situation_generation.py`: combined/별도/recovery 최종 결과·기존 호출 수. |
| I19 | `repository/situation_admission.py`: stable unique replay/conflict, 같은 Session, 독립 commit 없음. |
| I20 | 실제 Chat finalize receipt 원자성; 이미지 파일/인식 결과 모두 연결. |
| I21 | 실제 Inbox canonical effects 3대상과 receipt rollback. |
| I22 | 실제 Feed Like/reply receipt, immediate/deferred 참여·재실행 방지. |
| I23 | 실제 Routine Post UoW·replay fixture. |
| I24 | 계획 효과/확정 결과/output digest 대조; partial/unknown/missing 설명 차단. |
| I25 | 네 writer의 실패 주입·commit/replay·설명 오류 독립, 접수 직후 pending만 존재. |
| I26 | `repository/situation_apply.py`: 개별 기억/evidence/metadata/applied 원자 저장, 유효 작은 경험 포함. |
| I27 | `service/situation_management.py`, processing GET/PUT·save POST의 owner/CSRF/CAS/key/cutoff. |
| I28 | `runtime/memory/situation_sources.py`: 현재 scope/actor/epoch/권한/prior/version, 삭제와 변경 구분. |
| I29 | `situation_runtime.py`: 같은 소비자·최대100 page·fair claim·foreground Chat 양보. |
| I30 | shutdown/indexing coordinator: 제한 종료·검색 준비 관찰·late result fence/deferred. |
| I31 | 영속 run/request/cursor/lease 재시작, missed due의 captured-at/sequence 이중 cutoff·시간대/DST, fresh startup 무조건 flush 금지. 예약 시각 이후 접수는 다음 허용 계기에 남긴다. |
| I32 | file SQLite 동시 요청/claim·고정 cutoff·명시 retry·느린 fake provider와 별도 canonical 쓰기. |
| I33 | situation_reads/situation_packets와 episode/canonical reader의 새 representation dispatch. |
| I34 | FTS summary/version만 등록; 순수 scope lock은 전체 색인 rebuild를 유발하지 않음. |
| I35 | 기존 vector eligibility/read_work/projector, version/hash/profile fence, 종료 후 결과 차단. |
| I36 | old/new hybrid currentness·RRF·scope/prior 검사, unknown policy fail closed. |
| I37 | 선택 후 bounded 원문/thought hydration, 불가 원문의 사본/링크 미반환. |
| I38 | Hot Brief/prior/pin/correction/delete/retention, correction 자체 privacy metadata·삭제 receipt identity. |
| I39 | summary-only FTS/Vec, canonical 즉시 표시, 일반 조회/저장/ON과 전체 준비 분리. |
| I40 | frozen policy routing·D03 cutoff/epoch fence 후 신규 기본값 활성화, batch32 이중 접수 금지. |
| I41 | typed retirement·정확한 inventory·실제 개발 데이터 폐기/재실행. 아래 D03 결과 참조. |
| I42 | 관계 미사용 old/new union·core counterpart·삭제 원문의 새 summary 유지. |
| I43 | prepare/manual/refresh/revalidate/apply 동일 scope 선행 저장 fence; 다른 scope 진행·Vec 대기 없음. |
| I44 | 관계 DTO·키/모델/수동/예약 유지, 새 선별/32 요약/종료 관계 생성 제거, 폐기 대상 복구 차단. |
| I45 | 첫 카드 processing controls: 수동 저장·예약/종료 설정·key 재사용·scope abort·dirty 보존. |
| I46 | 새 representation 상세·삭제 원문·생각·canonical 표시와 기존 owner controls. |
| I47 | ko/en catalog·종료 문구·a11y, Next/static 공유 UI와 20개 browser fixture. |
| I48 | 5,568개 수집 node와 실행 결과의 정확한 합집합 대조 완료. 5,527 pass·40 skip·CI 목록 1 fail. V/T 자동 증거·합성 부하와 실제 API/native 실기 보류 분리. |
| I49 | 최종 backend 37항목·frontend 324 source 보존 통과. 현재 branch·CI 무변경·전체 node·정확한 metadata append·이 기록과 재개 명령 확인 후 명시적 stage·로컬 커밋. |

## C01–C32 / D01–D04 실제 연결

아래 테스트 이름은 `test_activity_situation_*.py`의 접미사다. `contract/receipt/application/recall/schedule/transition/relationships`는 `backend/tests/memory`, `generation`은 `backend/tests/runtime`, `upgrade`는 `backend/tests/migrations`, `Chat receipt`는 `backend/tests/chat`에 있다. 실행 결과는 아래 전체 node 대조와 집중 검사 로그에 연결한다. C05–C09의 자연어 의미 정확성은 영어 지침·구조·가짜 출력 검증과 실제 AI 관찰을 구분하며 후자는 보류다.

| 계약 | 실제 owner·변경 | 자동 검증·남는 경계 |
| --- | --- | --- |
| C01 | `situation_generation.py`, Chat generation workflow, combined provider의 locale·영어 지침 | contract, generation; 실제 언어 준수 보류 |
| C02 | Chat response step와 Inbox/Feed/Routine 기존 호출의 상황 출력 | Chat receipt, generation, 실제 SNS writer 회귀 |
| C03 | `situation_apply.py`의 receipt별 독립 MemoryItem | receipt, application; 자동 병합 없음 |
| C04 | admission unique identity, request/run key·lease | receipt, schedule의 replay/경합 |
| C05 | `situation_generation.py`의 이번 활동 중심 지침 | contract/generation; 의미 품질 V30 보류 |
| C06 | 인물·사건·장소·시간을 구체적으로 남기는 같은 prompt | contract/generation; 검색 유용성 V30 보류 |
| C07 | prompt의 의도/확정 구분 및 실제 effect 집합 대조 | receipt/generation; 문장 의미 V30 보류 |
| C08 | 중요도 선별·정형 실행완료 문구를 강제하지 않는 prompt | contract; 실제 자연스러움 V30 보류 |
| C09 | backend의 occurred-at·scope·digest·실제 결과 확정 | receipt/application; 코드 증거와 의미 판독 분리 |
| C10 | 8개 ORM·v31과 기존 FTS/Vec projection owner | upgrade, application, 실제 Vec1 회귀 |
| C11 | situation read/packet의 description-only document | application, recall, summary-only 색인 |
| C12 | 기존 vector work의 item/version/hash/profile 연결 | vector projection lifecycle·Vec1 회귀 |
| C13 | `situation_sources.py`와 packets의 선택 후 bounded hydration | recall, application의 삭제/변경 원문 |
| C14 | Chat/SNS/Routine 최종 delivery manifest adapter | generation, Chat receipt, recall의 range fixture |
| C15 | `contracts/activity_situation.py`의 source ID/version/range/order/role | contract, receipt, Unicode/name-binding recall |
| C16 | actual input·실제 결과로 source를 연결하는 runtime adapter | Chat receipt와 실제 Inbox/Feed/Routine 접수 |
| C17 | SNS target별 상황 parser와 canonical writer | generation, receipt의 target 분리 |
| C18 | Like-only 실제 effect의 receipt 접수 | 실제 Feed Like/reply fixture |
| C19 | 네 writer의 같은 UoW 안에서 성공 결과 확정 | Chat/SNS receipt의 commit·rollback |
| C20 | final digest·planned/confirmed effects 일치 검사 | receipt, generation의 partial/recovery 경계 |
| C21 | permissive auxiliary 필드와 base 독립 parser | contract, generation의 잘못된 설명 |
| C22 | `admit_situation`의 caller Session 참여·독립 commit 없음 | 네 writer의 실패 주입·원자성 |
| C23 | canonical 적용 commit과 이후 별도 색인 | application, recall, browser canonical 상세 |
| C24 | episode detail/source owner controls의 새 representation | application, recall, browser 상세·삭제 원문 |
| C25 | 전체 manifest/current source/prior/private 교집합 | application, recall, 기존 private/hybrid 회귀; 의미 품질 별도 |
| C26 | 신규 policy routing·legacy candidate 차단·구 기억 읽기 | transition, 기존 episode 회귀; 개발 작업은 D03 적용 |
| C27 | `review_memories.py`, `situation_ordering.py`의 old/new union | relationships 및 기존 관계 회귀 |
| C28 | processing·관계·의미 검색의 서로 독립된 gate | schedule, relationships, ko/en browser 세 역할 |
| C29 | 삭제 source의 summary 유지·scope/actor 상실 skip | application, recall, privacy/deletion 회귀 |
| C30 | 영속 pending과 일일/수동/host-quit 공통 consumer | schedule, shutdown·restart·cutoff 회귀 |
| C31 | 유효 설명의 크기 제한 외 별도 가치 선별 없음 | contract, receipt/application; 별도 요약 호출 없음 |
| C32 | 짧은 canonical page·foreground 양보·별도 색인 | schedule, vector lifecycle, T17 합성 측정; 지연0 보장 아님 |
| D01 | 기존 schedule 승계·신규 OFF/22:30/종료 ON | upgrade, schedule·calendar·shutdown |
| D02 | stable activity/lane/target당 최대1 receipt/item | contract, Chat/SNS receipt, replay |
| D03 | typed retirement와 실제 개발 volume의 정확한 삭제·fence | transition, 아래 D03 inventory/apply/replay 지문 |
| D04 | 첫 카드 manual save·CAS/key·고정 cutoff·readback | schedule 23개 묶음, browser 20개, GET 무변경 |

## V01–V37 / T01–T18 증거

로그는 Git에서 제외된 `artifacts/situation-validation/`에 있다. 첫 전체 회귀 `backend-full.txt`에서 이전 기본 policy를 가정한 fixture와 오래된 image Chat 조립을 발견했다. 두 번째 실행 `backend-full-second.txt`는 2,702 pass·30 skip·20 fail에서 중지했다. 스키마 기대값과 World 범위의 키·설정 fixture를 보완했다. 이 실행 도중 source를 보완하여 이미 로드한 모듈과 새 import가 섞인 시작 실패 2건은 새 프로세스에서 재검증한다. 이 실패 기록을 PASS로 바꾸거나 숨기지 않는다.

중간 확인은 실패 20개 재검증과 아직 실행하지 않은 2,793개를 합친 `backend-remaining.txt` 및 변경 후 집중 회귀로 진행했다. `backend-remaining-progress.jsonl`은 node/결과/시간만 남기는 임시 pytest reporting hook이며, 테스트 선택·단언·실행 결과를 변경하지 않는다. `missed-due-verified.txt`는 예약 경계·적용·계약 27 pass, `routine-owner-verified.txt`는 실제 World owner 설정·이름·일과 변경 26 pass다.

`backend-remaining.txt`는 이후의 fixture 수정을 모두 포함하는 최종 증거가 아니므로 실행을 중단했다. 남아 있던 slot fixture는 현재 World별 SNS credential을 실제 owner 경로로 저장하도록 수정했고 `slot-final.txt`의 5개 테스트가 통과했다. 최종 전체 회귀는 `b7624683`의 로컬 Git bundle을 네트워크 없는 일회성 Linux 검증 컨테이너에 복제한 고정 snapshot에서 수행한다. 앱 컨테이너나 사용자 data volume을 이 회귀 컨테이너에 연결하지 않는다. 이 Git 복사본은 제품 작업 브랜치를 전환하거나 원격을 조회하지 않는다.

기존 시작 HEAD `9c1d3868`의 `product-shell.spec.ts`에는 World 소개 화면의 한국어 링크 이름 두 곳이 이미 수정돼 있었다. 해당 commit의 전후 hash만 보존 이력에 추가했고, 이번 작업에서 그 브라우저 테스트나 World 화면은 수정하지 않았다. 이번 계약 변경 역시 `security/post_refactor_contract_changes.json`의 정확한 commit/AST/API/ORM/단언 차이로 기록하며, 고정 baseline·역사 migration·검사 코드를 완화하지 않는다.

추가 보존 기록은 기존 미기록 UI 커밋 네 개의 최초 도입 파일 17개와 이번 `7f975fde`의 새 소스 46개·테스트 node 61개를 원래 append 명령으로 수집했다. 모든 기존 기록의 prefix가 동일한지도 확인했다. Frontend 보존 검사는 source 324개와 browser assertion/fixture/asset/lock 보존으로 통과했다.

첫 격리 backend 보존 검사는 `Chat actual service construction changed`로 실패했다. 이번 `GenerationService`의 `memory_policy=generation_workflows.capture_memory_policy` 주입은 실제 commit/AST 증거가 이미 있었지만, 역사적 Chat forwarder 검사에서 composition 전체를 그대로 비교했다. 이 예외 뒤 보호 대상 목록이 비워져 출력된 다수 node 누락은 그 최초 실패의 연쇄 결과다. `f9842506`은 기존 세 인자·서비스·import·전체 조립 프레임을 유지하면서 정확한 새 keyword 하나와 독립된 commit 증거를 함께 요구하도록 검사기를 확장했다. 임의 승인 callback을 주더라도 fake service/port, 인자 교환, 다른 service 변경, import 변경, 재정의는 거부한다. `chat-construction-proof.txt`의 신규/기존 설정 검사 22개가 통과했으며, 전체 원래 Chat retirement 검사와 backend 보존 검사는 별도 격리 snapshot에서 다시 확인한다. 검사 생략·일괄 허용·고정 baseline 재작성은 하지 않았다.

| 검증 묶음 | 연결 V/T | 실행 증거 |
| --- | --- | --- |
| 계약/parser·원자 접수·고정 cutoff·삭제 identity·epoch | V02–V05/V09–V16/V25/V33/V34/V36, T02/T03/T09 | activity_situation_contract/receipt tests, `all-sns-receipts.txt` 9 pass, `chat-images-final.txt` 6 pass. |
| 최종 provider/복구·locale·manifest/range | V01/V03/V06–V08/V11/V20/V27, T07/T08 | `generation.txt` 6 pass, Unicode/name-binding recall fixture, 기존 Chat response/routing/streaming 회귀. |
| schema/기존 key/예약/구 작업 보존 | V26/V32, T04–T06 | v31/Alembic parity·v29 실제 key fixture·populated migration suites와 `migration-final-fixes.txt`. |
| 수동 HTTP/동시성·일일/종료/시간/재시작 | V14/V29/V32/V34/V35/V37, T06/T09–T11 | situation_schedule, 기존 episode schedule/shutdown/calendar; `remaining-integration.txt` 17 pass. native 실기는 보류. |
| canonical/삭제·변경/private/prior/correction·검색 | V17–V24/V26/V33, T12/T13 | situation_application/recall, episode privacy/hybrid/vector/lifecycle 회귀. |
| late embedding fence·독립 foreground write | V23/V24/V35/V37, T09/T11/T12 | vector_projection_lifecycle·`shutdown-schedule.txt` 11 pass 및 remaining integration. |
| 실제 Vec1 profile/filter/version/삭제/재시작 | V21/V23/V24, T12 | network-none helper `vec1-native.txt` 14 pass. Windows native-extension skip과 별도 증거. |
| D03 폐기·재실행·비대상 불변 | V25/V26, T01/T14 | situation_transition, 실제 `dev-d03-{inventory,upgrade,apply,replay}.json` 및 로그. |
| 관계 old/new union·대상·삭제 원문·처리 순서 | V31, T15 | situation_relationships·기존 관계 suites·`relationship-fairness-final.txt`. |
| 정상/empty/OFF/중복/timeout/draft/scope/detail/모바일/키보드 ko/en | V23/V28/V29/V32, T07/T16 | `browser-readback-final.txt`: Next/static × ko/en 20 pass. 390/1100 screenshot, 실제 AI/native 검증 아님. |
| 경계·타입·디자인·build/static·locale | T07/T18 | frontend lint/typecheck/build/static/catalog, architecture/design 로그. raw-color 1167 유지, route gap 0. |
| backlog/lock/검색/hydration·Vec1 비용 | V30/V37, T17 | `load-01/measurements.json`, `vector-load-linux-01/measurements.json`. |
| 전체 회귀·최종 diff/branch/commit | T01/T18 | `backend-coverage-final.json`: prefix·shard·Chat·변경 후 집중 회귀의 정확한 고유 node 합집합 5,568개. 5,527 pass·40 skip·1 fail·error 0. 원래 실패 보고서도 보존. |

V30 실제 모델 의미 품질은 보류다. 표는 해당 위험을 다루는 fixture의 연결이며 모든 입력·OS·장비를 증명하지 않는다. 실기 확인을 자동 PASS에 합치지 않는다.

추가 확인에서 실제 Chat admission에 필요한 schema 준비를 트랜잭션 테스트 본문에 넣은 부분은 전용 `_create_tables` 준비 함수로 이동했다(`000b3542`). 테스트의 원래 실행·replay·row count 단언 본문은 그대로 유지했고, 실제 lifecycle 2개가 통과했다. 이어 보존 검사가 메모리 부족으로 종료되어 `73204877`에서 큰 역사 manifest의 byte cache 보관만 제거했다. 같은 append-only 비교·commit/source 검증은 모두 수행하며 작은 불변 source cache와 HEAD/후보 재확인은 유지한다. 관련 원본·캐시 안전성 검사 31개가 통과했다. 고정 증거·검증 조건·테스트 선택을 줄이지 않았다.

전체 백엔드 실행은 첫 1,405개(1,398 pass·7 skip·실패0)의 JUnit 결과를 보존하고 중단했다. 중단 직후 pytest tmp-path teardown의 `KeyError`는 이 검증 프로세스 중단 기록으로 남겼으며 제품 실패로 세지 않는다. 최신 수집 목록과 JUnit `(classname, name)`을 대조하여 미실행 node를 별도 격리 실행으로 넘긴다. node 안의 `::`를 포함한 parameter 값도 그대로 보존하고, 전체 node 집합·완료 prefix·집중 검사·분할 실행의 합집합이 일치하는지 검사한다. 이 단계에서 중단된 전체 실행을 전체 PASS로 표시하지 않는다.

`551b2e9e`는 보존 검사기의 파싱된 source/AST cache 개수만 제한했다. 검증 조건이나 대상은 그대로이며, `preservation-backend-closed.txt`는 기존 보호 이력과 현재 5,564개 node·계약 37항목의 보존 검사 통과를 기록한다. `preservation-cache-bounds.txt`의 안전성 검사 31개도 통과했다. 이후 제품 보완의 정확한 commit 증거를 추가하고 보존 검사를 다시 확인한다.

분할 회귀에서는 기존 `test_sqlite_concurrent_world_activation_serializes_capacity_at_one`의 잠금 오류가 발견됐고, `concurrency-repeat-1.txt`의 독립 실행에서도 재현됐다. 이 테스트·활성화 함수·이미지 설정 저장 함수는 시작 HEAD부터 변경되지 않았지만, 성공한 활성화 뒤 응답용 이미지 설정을 잠금 밖에서 추가하던 실제 틈이었다. 새 `prepare_activation_detail` 포트는 필요한 설정을 기존 SQLite 활성화 transaction에 `flush`만 하도록 연결한다. 활성화·설정·slot·기록은 기존 bounded writer가 함께 commit/rollback하고, 실패한 활성화를 테스트에서 성공으로 간주하거나 잠금 대기시간을 늘리지 않는다. `activation-detail-fix.txt`는 원래 동시성 테스트와 transient/persistent busy 실패 주입 3 pass를 기록한다. 전체 관련 suite와 최종 보존 검사는 별도로 기록한다.

`642f3e6b`의 전체 활성화 suite는 `activation-detail-suite.txt` 69 pass다. 관련 소비자 묶음의 최초 결과는 80 pass·19 skip·1 fail(`activation-consumers.txt`)이고, 해당 실패는 가져온 World fixture가 legacy 키만 준비했던 문제였다. `0cb521e8`은 World 전용 SNS 키와 현재 v31 기대값을 반영했으며 `imported-world-owned-key.txt` 10 pass, `final-scope-schema-fixtures.txt` 8 pass, 마지막 공동 활동 단독 확인 `joint-scope-closed.txt` 1 pass로 확인했다. 원래 동시성·암호화·원본 보존 단언은 유지했다.

주제 추천 fixture의 누락된 World configuration·SNS 키도 실제 생성/credential owner로 준비했다. 예전 credential resolver stub을 사용하지 않는다. `8914a037`의 `topic-scope-final.txt` 47 pass는 GET 무변경·중복·실패·stale 보호를 포함하고, `a253a7e6`의 `approved-topic-scope.txt` 18 pass는 승인된 자료의 provenance 불변을 확인한다. 위 검사들의 겹치는 node를 전체 합계에 중복으로 더하지 않는다.

최종 화면 확인에서 저장 대기 0개일 때 수동 버튼이 남아 있던 차이를 `66c5f2d4`로 보완했다. 버튼 상태와 이벤트 처리 모두 실제 pending·memory ON·running 상태를 확인하며, timeout 재시도의 같은 key와 서버의 empty 응답은 유지한다. `browser-empty-final.txt` 16 pass(Next/static × ko/en), `frontend-empty-{lint,types,build,static,architecture,design}.txt` 통과를 최종 화면 증거로 사용한다. 390px 영문 정적 화면도 직접 확인했다. 새 문자열·색상·전용 Tauri 화면은 추가하지 않았다.

`004034f4`는 수동 POST가 timeout된 뒤 실제로 접수·완료된 요청을 순수 GET으로 확인하도록 보완했다. 동일 scope의 요청 key가 확인됐을 때만 클라이언트의 보류 key를 지워, 나중에 새로 들어온 경험을 저장할 때 완료된 옛 요청을 재사용하지 않는다. polling은 POST를 재전송하지 않는다. `request-readback-final.txt` 23 pass는 소유권·외부 scope 거절·unknown key·입력 길이·SELECT-only 조회를 포함한다. `browser-readback-final.txt` 20 pass와 `frontend-readback-{lint,types,build,static,architecture,design}.txt`를 최종 화면 증거로 사용한다.

`06250d3c`는 World 입력 회귀 fixture의 실제 SNS credential binding과 별도 이미지 정책을 준비했다. legacy fixture도 기존 v28에서 실제 forward delta 검증을 거쳐 현재 schema로 전환한다. 공통 이미지 설정의 변경은 이미 선택한 World 정책에 영향을 주지 않고, 그 World의 연결이 유효하지 않을 때만 실행을 거부한다. `world-inputs-current.txt` 20 pass다.

`6d65b877`은 현재 metadata로 과거 설치 DB를 만드는 fixture에서 v30/v31의 후속 추가분을 제거하여 당시 manifest와 일치시킨다. 실제 사용자 DB를 낮은 버전으로 바꾸거나 역사 manifest를 수정하지 않는다. `historical-predecessors-final.txt` 44 pass는 v1–v28 synthetic 설치 predecessor와 기존 데이터 보존·reserved-role 충돌 거절을 확인한다. 새 목표는 v31·168테이블이다. 별도로 `security-schema-ui-final.txt` 48 pass는 owner-only API 12개의 명시적 등록, 기존 누락분을 포함한 private 테이블 15개의 삭제 책임, 실제 v31 시작과 조회 무변경, 기존 화면 변경 후에도 유지되는 안전한 이동·생성 방식 선택을 확인한다. 이 범위는 새로운 기능을 임의로 허용한 것이 아니라 승인된 기존 World 기능과 이번 상황기억 기능의 inventory 누락을 보완한 것이다.

`chat-retirement-closed.txt`의 기존 Chat 연결·구성·정확한 이력 검증 102개도 통과했다. 전체 합계는 이들 집중 검사를 더한 값이 아니라 최종 수집 목록의 각 node를 대조한 고유 결과로 기록한다.

### 최종 자동 검증 결과와 CI 범위 제한

소스 검증 HEAD는 `6a5291f6b5c3ceedab722ef8191e61f8a761b213`이다. `backend-coverage-final.json`은 5,568개 수집 목록 전체를 JUnit `(classname, name)`과 일대일로 대조한다. 완료 prefix·독립 분할 실행·변경 후 해당 suite 재실행을 합친 결과이며, 하나의 무중단 실행 결과라고 주장하지 않는다. 이전 실패 보고서 99개 항목도 함께 남겨 최종 결과로 바뀐 경로를 추적한다. 동일 node의 재실행을 테스트 수에 중복으로 더하지 않는다.

| 구분 | 결과 | 증거·범위 |
| --- | --- | --- |
| 백엔드 고유 node | 5,527 pass·40 skip·1 fail·error 0 | `backend-coverage-final.json`, `backend-coverage-final.txt`; 집계 exit 1을 유지한다. |
| v1–v30 로컬 predecessor fixture | 31 pass | `installer-v31-matrix.xml/txt`; v31 전환과 기존 데이터 보존. 실제 NSIS 실행 아님. |
| 최종 구조·목록 | 26 pass·CI 목록 1 fail | `live-inventories-authorized.xml` + `live-inventory-ci-preserved.xml`; 후자는 workflow 원상 보존 후 inventory hash 재생성의 재검증이다. |
| 최종 Memory 화면 | 20 pass | `browser-readback-final.txt`; Next/static × ko/en. |
| Frontend 정적 검사 | lint·typecheck·build·static export·catalog 통과 | `frontend-readback-*.txt`, `frontend-catalog.txt`; locale 16 namespace·2,652 key. |
| 아키텍처·디자인 | backend 1,459 module·6,217 edge, frontend 14 feature, legacy exception 0 | `architecture-readback.txt`, `frontend-readback-{architecture,design}.txt`; raw color 1,167 유지·route gap 0. |
| 최종 이력 보존 | backend 37항목·보호 node 5,568개, frontend source 324개 통과 | `preservation-{backend,frontend}-authorized-final.txt`, `authorized-final-proof-result.json`; 각 exit 0. |

건너뛴 40개는 명시적 performance 실행 6개, public profile 밖 hosted lifespan 1개, 별도 World configuration DB 3개, concurrency DB 19개, 회귀 컨테이너 안 Docker CLI 부재 6개, graph Postgres DB 1개, 선택 사용자 원본 미제공 3개, scheduler Postgres DB 1개다. 해당 조건을 임의로 제공하거나 skip을 PASS로 바꾸지 않았다. T17 합성 성능과 실제 Vec1 fixture 결과는 별도 표의 증거다.

남은 실패는 `tests/test_p8_l_d_world_chat_inventory.py::test_p8_l_d_requires_real_v3_installer_fixture_in_hosted_matrix`다. 현재 v31의 readable predecessor는 v1–v30인데, 기존 `.github/workflows/windows-installer.yml`과 `scripts/ci/run_windows_installer_supported_upgrade.ps1`의 실제 설치 fixture 연결은 v28까지다. 정적 검사기는 `windows_installer_hosted_predecessor_missing:v29`로 실패하며 v30도 같은 연결이 없다. 로컬 builder와 데이터 전환 자체는 위 31개 테스트로 통과했다.

`ci-matrix-scope-limitation.json`은 시작 HEAD의 schema v30에서도 v29 hosted 연결이 빠져 있었음을 Git 원본으로 확인한다. 이번 v31에서는 v30까지 필요하다. workflow와 runner의 버전 집합은 시작·최종 HEAD가 동일하며, 기존 누락에 새 schema의 후속 연결 요구가 더해진 상태다.

계획 §2.1.4가 **CI 설정 변경을 금지**하므로 workflow/설치 runner에 잠시 작성했던 미커밋 확장은 시작 상태로 되돌렸다. 삭제된 변경의 검토용 diff만 ignored evidence의 `unapplied-installer-ci-matrix.patch`에 보존했다. 이 중간 변경을 포함했던 `live-inventories-closed.txt`의 27 pass를 최종 PASS 증거로 사용하지 않는다. hosted 검사 자체를 수정·건너뜀 처리하거나 현재 버전의 predecessor 요구를 낮추지 않았다. CI 목록 확장·실제 CI/NSIS 검증은 별도 허용 이후의 작업이다.

`6a5291f6`은 v29/v30 로컬 fixture와 현행 source inventory를 보완한다. 역사 schema manifest·migration 본문·보존 baseline은 변경하지 않는다. 기존 World 소유 credential 경로의 네 reveal 함수도 owner/purpose/revision 확인 뒤에만 transport용으로 복호화한다는 실제 소스를 확인하여, 보안 검사의 개별 함수 inventory 누락을 보완했다. 임의 함수·경로 wildcard를 허용하지 않는다.

`authorized-final.bundle`의 고정 source snapshot과 검증 메타데이터 SHA를 network-none 일회성 helper에서 확인했다. `introduction-proof-v31-predecessors.txt`는 v29/v30 두 node만 추가했고 기존 이력 prefix·source 목록이 그대로임을 확인한다. 최종 backend 검사는 보호 lineage와 현재 수집 목록이 모두 5,568개이며 37항목이 통과했다. Frontend는 324 source와 browser assertion/fixture/asset/lock 보존에 통과했다. helper는 사용자 data volume을 연결하지 않았으며 완료 후 자동 제거했다. 이 검사 후 제품 소스는 바꾸지 않고 이 기록과 두 검증 메타데이터 파일만 커밋한다.

최종 커밋 확인 명령은 `git log -1 --oneline`과 `git status --short`다. 구현 시작부터 제품·회귀 보완 커밋까지는 `git log --oneline 9c1d3868c7a547d1ef3af3c8078ad2684d92060f..6a5291f6b5c3ceedab722ef8191e61f8a761b213`로 확인할 수 있다. 원격 ref나 다른 branch로 전환할 필요가 없다.

## D03 실제 개발 데이터

`scripts/diagnostics/retire_activity32_tasks.py`를 앱 컨테이너가 중지된 상태에서 network-none helper로 실행했다. maintenance owner 잠금·정확한 ID/cutoff 재검증·같은 transaction의 typed 삭제·전체 테이블 지문 비교를 사용했다.

1. inspect: 6 scope, 구 job 2개, candidate 115개, request 2개를 inventory에 고정.
2. upgrade: v30 → v31 copy-on-write staging 승격 성공. 실제 data-root 암호화 키 주입, provider 0회.
3. apply: 해당 job 2개·candidate 115개·request 2개와 전용 종속 기록 폐기. 대상 잔여0. queue/fence 9테이블만 변경, 비대상 160테이블의 행 수·지문 동일.
4. replay: 같은 audit key 재실행에서 변경 테이블0, 169테이블 지문 동일, 잔여0. JSON에 다시 표시된 계획상 삭제 수를 두 번 삭제한 결과로 세지 않는다.

선택 DB는 `/var/lib/angmoo/canonical/generations/contributor-v2-schema-v3-schema-v4-schema-v9-schema-v-schema-v31/angmoo.sqlite3`다. 이전 generation·키 파일·미디어·원문·기존 기억·관계·설정을 보존했다. 설치형 Windows Angmoo 데이터/identity는 대상이 아니다. D03을 다시 실행할 필요는 없다.

## T17 합성 측정

10k/100k 인공 기억과 1,000개 pending에 실제 application page·FTS를 실행했다. 같은 원문을 공유하는 낮은 다양성 fixture이고 동시 테스트의 CPU/디스크 경쟁이 있다. 접수 평균은 접수 transaction 비용이며 전체 Chat 응답 시간이 아니다. 처리량은 이 환경의 관측치다.

| 규모 | canonical DB | FTS DB | 1,000개 적용 | 최대100개 page | 별도 foreground 쓰기 최대 | 접수 평균 | FTS 검색 / hydrate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10k | 31,006,720 B | 13,672,448 B | 10.99초, 91.0개/초 | 1,298ms | 10.53ms | 8.93ms | 48.08 / 106.30ms |
| 100k | 275,357,696 B | 134,168,576 B | 13.82초, 72.36개/초 | 1,789ms | 68.74ms | 46.67ms | 608.86 / 307.64ms |

Vec1은 Docker 이미지에서 추출한 manifest/SHA 검증된 0.7 확장과 합성 768차원 float32 값이다. Linux `/tmp`에서 측정하고 JSON만 Windows 증거 폴더로 내보냈다. 실제 data volume/provider를 사용하지 않았다.

| 벡터 수 | 실제 index 크기 | 등록 시간 | 검색 평균 / 최대 |
| --- | --- | --- | --- |
| 10k | 33,648,640 B | 6.93초 | 37.44 / 64.78ms |
| 100k | 336,576,512 B | 50.73초 | 375.05 / 442.15ms |

비교용 Windows Docker bind mount의 10k 검색 평균은 약 3.42초였다. 100k 검색은 10초 deadline으로 `memory_vector_cancelled`가 발생했다(`vector-load-01.txt`). 이 환경의 100k 검색 성능은 PASS가 아니며 Linux 수치와 혼합하지 않는다. 단일 검색/page가 수백 ms 이상 걸릴 수 있으므로 지연0이나 전경 무대기 PASS를 주장하지 않는다. 작은 page·foreground 양보·검색 deadline/FTS fallback을 유지한다. 실제 임베딩 API 시간·비용·의미 품질은 측정하지 않았다.

## 재현과 재개

제품 저장소 루트에서 실행한다. 로컬 검사만 수행하며 일반 테스트는 실제 서버를 요구하지 않는다.

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
$env:APP_ENV='test'
$env:DATABASE_URL='sqlite+pysqlite:///:memory:'
uv run --directory backend python -m pytest -q tests --maxfail=20 --tb=short
uv run --directory backend python -m pytest -q tests/chat/test_activity_situation_receipt.py tests/memory/test_activity_situation_relationships.py tests/memory/test_vector_projection_lifecycle.py
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests exec playwright test --config playwright.memory-situation.config.ts
uv run --project backend python scripts/diagnostics/measure_activity_situations.py --output artifacts/situation-validation/new-synthetic-run
```

벡터 helper는 현재 app/tests/diagnostics를 읽기 전용으로 연결하고, 패키지의 `vec1.so`/`manifest.json`을 읽는다. network-none이며 사용자 volume을 연결하지 않는다.

```text
python scripts/diagnostics/measure_activity_situations.py --vector-only --vector-resources /evidence/vec1-linux --output /evidence/new-vector-run --data-root /tmp/new-synthetic-vectors
ANGMOO_TEST_VEC1_EXTENSION=/evidence/vec1-linux/vec1.so python -m pytest -q tests/memory/test_sqlite_vec1.py tests/memory/test_vector_generations.py
```

## 보류와 운영 경계

이 문서는 최초 v31 구현 당시 기록이다. 이후 관찰 증명·관계 snapshot·owner 재검사/저장 포기와 v32의 구현 및 최종 검증은 [상황기억 검증·복구 구현 결과](<../verification/10-08 Chat·SNS 상황기억 관찰 검증과 차단 기록 복구 구현 결과.md>)를 참조한다. 아래 당시 결과를 최신 구현 결과로 대신 판독하지 않는다.

- 실제 AI의 ko/en 준수, 원문↔응답↔설명의 의미 정확성, 검색 유용성: 별도 관찰 전까지 미검증.
- 설치 앱 physical identity, 실제 native quit/skip/강제 종료·자연 활동·사용자 확인: 미수행. host 요청 의미는 유지했고 backend fake coordinator를 검증했다.
- 새 배포 이미지 빌드·앱 재시작·PR·원격 CI·push·main merge: 미수행. 개발 앱 컨테이너는 중지 상태다. 사용자가 시작하면 설정된 키로 자율 활동이 재개될 수 있다.
- 일반 migration은 구 작업을 자동 폐기하지 않는다. 위 개발 volume만 D03 완료이며 다른 data root의 삭제 권한/상태 증거로 재사용하지 않는다.
- 설치 CI predecessor 목록의 v29/v30 연결은 계획의 CI 설정 변경 금지로 미적용이다. 전체 자동 검증은 위 1개 실패를 남기며, 향후 CI 허용 시 이 목록을 확장하고 해당 원래 검사를 통과시켜야 한다.
