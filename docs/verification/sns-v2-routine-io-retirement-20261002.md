# SNS 계약 2 Routine 복구·입출력 정리·구 실행기 퇴역 구현과 로컬 검증

계획 작성일: 2026-10-02. 실행·검증일: 2026-10-03. 제품 저장소: `angmoo-tree-angmoo`.
브랜치: `feat/0.1.0-release-readiness`. 시작 HEAD: `7da83fb8ff611f969600aea959dfa4b20092441d`, 시작 작업 폴더 clean.
이슈: [#359](https://github.com/angmoo-tree/angmoo/issues/359). 이슈는 OPEN으로 유지한다.

수행 기준은 workspace의 `10-02 SNS 계약 2 Routine 잘림 복구·입출력 정리·구 실행 구조 제거 통합 코드 구현 세부 계획.md` P00–P19, C01–C33, T01–T50이다. 이 문서의 검사 결과는 격리된 로컬 결과이며 실제 API·Docker·설치판 적용·자연 활동 품질·Hosted CI 결과가 아니다.

## 1. 실제 구현과 소유권

| 대상 | 실제 변경 |
| --- | --- |
| 계약 2 부모 | `runtime/autonomous_activity/graph.py`가 기존 Combined 네 호출과 Inbox → Feed → Routine 순서를 소유. 불필요한 V1 부모 조립·dispatch 제거 |
| 공통 진입 | `runtime/autonomous_activity/gateway.py`에 수동·예약 공통 진입. 완료 ID는 canonical reader의 권한·receipt 검증을 먼저 사용하고 새 bind/전환/Provider를 시작하지 않음 |
| 공통 공개 효과 | `runtime/social/planned_actions.py`로 기존 실제 executor의 7개 함수 본문을 그대로 이동. 도메인의 Post·제안·관계·영수증·같은 Session 계약 유지 |
| 공통 Feed workflow | `runtime/social/feed_workflows.py`에 실제 workflow·execution ports. Provider는 호출자가 명시적으로 주입하며 퇴역 Provider의 암묵적 기본 생성을 제거 |
| 작성 의미 | `domains/routines/contracts/reply_writing.py`, `domains/social/contracts/proposal_plan.py`가 실제 Writer·판단 DTO의 공통 의미를 소유. 캐릭터 데이터/본문/역사 기록의 저장 형식은 바꾸지 않음 |
| credential 문맥 | `runtime/autonomous_activity/llm_context.py`에 실제 credential resolver와 안전한 호출 식별자. SDK provider와 runtime 객체는 checkpoint에 저장하지 않음 |
| 역사 읽기 | `runtime/resident/history.py`가 실제 resident 문맥의 일과 역사 읽기를 소유. 기존 독립 도메인 정책과 `routine_resident_v1`, `topic_recommendation_v1` 같은 현행 runtime mode는 유지 |
| 순수 시간 정책 | `aware_utc`의 기존 본문을 `domains/routines/utils/clock.py`로 이동. planning이 service 패키지를 역방향으로 초기화하는 cold import 순환을 제거하고 기존 service 읽기·호출 호환과 clock의 기존 `__all__` 유지 |
| 구 실행 포기 | `runtime/autonomous_activity/retirement.py` + `domains/routines/service/legacy_claims.py`가 기존 row·claim·episode·beat·slot의 지원 종료와 정산을 담당 |
| UI/API | 신규 engine 입력은 V2 또는 상속 null만 허용. 과거 current와 abandoned는 읽기/표시 가능. 전환 상태는 backend 실제 응답에서 읽으며 ON/OFF·예약·승인을 임의 변경하지 않음 |

물리적으로 제거한 세 제품 모듈은 `runtime/resident/langgraph.py`, `runtime/social/feed_cycle.py`, `runtime/social/feed_reaction_provider.py`다. 이름에 v1/current가 들어간 모든 독립 업무 파일을 일괄 삭제한 것이 아니다. OpenClaw, claim/slot 관리, 현재 split·Writer repair, 검색·기억·이미지·관계·공동 일정·하루 계획은 각각의 실제 소유자에 남는다.

## 2. 출력·입출력 정책

신규 V2/2 activity 생성 시 `social_io_policy=social-io.lane-scoped.v1`와 `routine_output_policy=routine-split-output.bounded.v1`를 독립적으로 고정한다. 기존 V2/2에서 메타데이터가 없으면 common/legacy로 읽는다. 기존 정책은 재개 중 새 기본값으로 바꾸지 않는다. 계약 3을 신설하지 않았다.

`bounded`의 split `RoutineActionPlanner`는 처음 8,192, 기존 좁은 불완전 JSON + MAX_TOKENS 판정에서만 16,384로 전체 재생성 1회를 허용한다. 유효 MAX_TOKENS·STOP·업무 enum/대상/권한 실패에 이 정책의 추가 호출을 적용하지 않는다. 다른 Planner/Writer와 combined의 기존 정책은 유지한다. 정상 10·복구 5·총 15는 노드 목록 길이와 분리한 상수이며 요청 전 영속 CAS 장부에서 예약한다. 재시작·같은 키의 경쟁 호출로 예약을 보충하지 않는다.

| 항목 | 신규 모델 출력/입력 | 유지하는 canonical 의미 |
| --- | --- | --- |
| R01 | 판단 proposal_response의 task_id 제거 | 서버가 만든 실제 Writer task·assignments·target 연결 |
| R02 | 판단 proposal_response의 body=null 제거 | Writer가 쓴 실제 body로 게시·알림 |
| R03 | 판단 proposal의 임시 text 제거 | 검증된 제안 계획 + 최종 Writer 본문으로 공개 제안 구성 |
| R04 | Feed preview의 4키, selected의 3키와 Inbox의 2키만 deepcopy view에서 제외 | 원천 Candidate·revision·checkpoint·다른 lane·image/source와 Chat/Memory 입력 |
| R05 | Feed 응답/Inbox 신규 제안 및 capability 없는 출력·초안 필드 제외 | 제안 가능 Feed, 받은 제안 있는 Inbox의 실제 accept/reject/counter·일정·target별 검증 |

금지 키는 null이어도 신규 wire parser가 거절한다. 혼합 Inbox에서 한 target의 응답 capability를 다른 target에 적용하지 않는다. 관계·상태 optional 결과의 오류는 유효 공개 행동을 무조건 실패시키는 근거로 바꾸지 않는다.

## 3. 구 기록·전환·보존

포기 대상은 `current` 또는 `personalized_graph_v2/contract_version=1`의 미완료 SNS identity다. 살아 있는 owner/claim·미확정 공개 효과·전달·관계 반영이 있으면 해당 actor를 보류하고 old graph/SDK를 실행하지 않는다. 만료된 claim은 episode/beat/event/slot의 실제 소유자에서 정산하고 ActivityGraphRun은 `abandoned`, 실행 중 AgentRun은 `aborted`로 종료한다. 이미 성공한 결과·usage·영수증·원장·역사 identity와 상세는 유지한다. completed/observed로 위장하거나 retention 태그를 소급 부여하지 않는다.

명시 `current` 설정은 old 처리 종료 + 실제 승인 pair·World hash + 기존 하루 계획·추천 준비의 readiness를 모두 확인한 지원 경로에서만 V2로 전환한다. 공유 world/global 설정의 실제 상속 대상이 모두 준비되어야 하며 더 구체적인 override는 제외한다. revision 충돌은 `pending_conversion`으로 남기고 최신 설정을 덮어쓰지 않는다. null 상속·활동 OFF·동의·예약·승인은 유지한다.

전환은 ORM/schema 버전 변경이 없는 데이터 절차다. startup은 실제 runtime composition의 canonical session factory를 사용하고 scheduler 시작 전에 처리한다. gateway와 복원 이후 진입도 같은 절차를 사용한다. 같은 schema 재시작·전환으로 새 DB 세대를 만들지 않는다. 선행 24시간 체크포인트 정리와 기본 2세대·pin·serving owner·업그레이드 lock 보호는 유지한다. 완료 결과는 상세가 정리되거나 OFF·lease/binding이 없더라도 권한 내에서 canonical 우선 재사용한다.

## 4. 로컬 검사와 증거

증거 폴더는 `artifacts/sns-v2-routine-io-retirement/`이며 Git ignore된 로컬 자료다. 다른 clone에 이 폴더가 존재한다고 가정하지 않는다. 제품 코드·회귀 검사·이 문서·정확한 보존 manifest는 Git 관리한다.

| 검사 | 확인 결과/범위 |
| --- | --- |
| 기존 선행 보존 4파일 | 삭제 전 같은 새 정책 코드에서 `preservation-final-v2.xml`: 75 PASS. 최종 소스의 전체 결과는 아래 실행 종료 기록에서 별도 갱신 |
| 실제 split Routine | `test_routine_bounded_integration.py`: 실제 그래프·검증·장부·게시, 첫 성공/한 번 복구/복구도 실패/STOP/유효 MAX_TOKENS/OFF 6 사례. SDK와 key 해석만 합성 seam |
| Finalize 수신·확인 경계 | `routine-retention-verified.xml`: 2 PASS. 실제 새 split 복구 완료 후 SDK 최종 write 또는 confirm_graph 실패. canonical 보존·정리 금지·완료 ID 재사용·추가 Provider/LLM 0 |
| 포기·실제 readiness·공유 scope/revision | `activity-transition-ready.xml`: 13 PASS. 합성 캐릭터·실제 정책/승인 pair/계획/정산을 사용. 다른 actor와 명시 override 보존 |
| 복원·pin | `retirement-restore-verified.xml`: 5 PASS, marker까지 포함한 `paired-generation-restore-verified.xml`: 6 PASS. 원본 archive 불변·SDK 상세와 canonical의 paired 복원·같은 세대·old 포기·완료 재사용 검사 |
| 퇴역 증거 checker의 거절 검사 | `test_sns_execution_retirement_gate.py`: committed preimage/source/owner/누락·skip/직접·로컬·상대·동적 import 위반 거절. 정상 기능 검사를 대체하지 않음 |
| 실제 신규 Feed SDK seam | `v2-feed-sdk-probe.xml`: 7 PASS. 실제 V2 Provider/JSON parser·schema·thinking/usage·엄격한 thought 검사 |
| frontend | lint/typecheck, 일반 build, static build PASS. 실제 소유 컴포넌트의 Next/static personalized fixture 각 1 PASS. current 입력 제거·상속 null·API revision·OFF·abandoned·전환 상태·390px/focus/44px 확인 |
| 전체 backend | 최종 **4,747 PASS / 0 FAIL / 52 SKIP**, 종료 코드 0. 첫 전체·중단 실행·단독 후속은 §7에서 구분 |

### 스키마 전체 측정(T41)

`schema-measurement.json`은 실제 `generate_text`에 전달된 32개 전체 schema를 저장한다. 두 lane × capability 두 경우 × 후보 1/3개 × common/lane 정책 × split/combined다. 모든 anyOf·array items를 재귀로 방문하고 enum 값의 **발생 합계**·properties·required·날짜/길이/수치/배열 제약·중첩·hash를 기록했다. 압축 snapshot의 추정값이 아니다. 깊이는 JSON dict/list의 모든 하강을 포함하는 측정값이다.

후보 1개의 combined 출력 비교:

| lane/capability | enum 값 발생 합계 common → lane | properties common → lane | required common → lane | schema 문자 수 common → lane |
| --- | --- | --- | --- | --- |
| Feed 일반 | 66 → 39 | 50 → 26 | 26 → 21 | 3,927 → 2,124 |
| Feed 제안 가능 | 66 → 47 | 50 → 34 | 26 → 26 | 3,927 → 2,745 |
| Inbox 일반 | 66 → 39 | 50 → 26 | 26 → 21 | 3,928 → 2,125 |
| Inbox 응답 가능 | 66 → 59 | 50 → 39 | 26 → 21 | 3,928 → 3,165 |

이 숫자는 코드의 출력 계약 축소 근거다. 실제 모델 품질·지연·과금 개선을 측정한 수치가 아니다.

## 5. T01–T50 대응 지도

아래는 실제 검사 소유 경로다. 테스트명 변경/퇴역은 §6의 정확한 증거와 구분한다. 실행 완료 결과는 §7에서 판정한다.

| 계약 | 실제 검증 경로 |
| --- | --- |
| T01–T04 | `tests/runtime/test_autonomous_activity_graph.py`, `test_activity_combined_contracts.py`, `test_activity_combined_selection.py`와 기존 mode/skip/선택 고정 검사 |
| T05–T13 | `test_social_wire_policies.py`, `test_routine_bounded_integration.py`, 기존 `test_activity_output_recovery.py`와 `tests/routine_posts/test_output_contract_v2.py` |
| T14–T17 | 실제 Routine OFF 사례, `test_social_request_budgets.py`의 재개·2개 실제 Session 경쟁 CAS, 기존 claim/scope/target 검증 |
| T18–T19 | 실제 부모·Inbox/Feed 정산 및 Routine 결과, 기존 `tests/image_integration`·`tests/routine_posts`의 image_prompt/중복 intent·첨부 검사 |
| T20 | `tests/runtime/test_sns_observation.py`, RoutineActionPlanner 성공·복구·wrapper 중복·최종 실패 집계 |
| T21–T29 | `test_social_wire_policies.py`, `tests/social/test_feed_reaction_provider_contract.py`, 실제 공동 활동 판단·작성·게시 검사 |
| T30–T31 | `test_joint_daily_integration.py`, `tests/relationships`·`test_activity_settlement_sqlite.py` 및 기존 proposal/state/source/metric 범위 |
| T32 | 새 독립 정책 4조합·메타데이터 부재, 기존 부모의 V2/2 common/legacy 재개. 기존 ID의 metadata/CAS 보존 |
| T33–T36 | `test_activity_retirement.py`, `test_retirement_restore.py`, actual gateway 및 제품 AST import closure, Next/static engine fixture |
| T37–T39 | 기존 `tests/chat`, `tests/memory`, `tests/routines`, `tests/relationships`, `tests/image_integration`, 공동 계획/실제 정산/다른 actor 검사 |
| T40 | `browser-tests/personalized-activity-fixture.ts`, Next/static 각 실행, frontend architecture/design/lint/typecheck/build |
| T41–T42 | full schema 32개 측정, committed 7da preimplementation 4,730 test-node snapshot와 최종 collection/원본 predicate 비교·exact provenance gate |
| T43–T47 | 기존 `test_checkpoint_retention.py`, `test_checkpoint_maintenance.py`, 새 `test_routine_retention_boundary.py`, `test_social_request_budgets.py`, `test_retirement_restore.py` |
| T48–T49 | 실제 contributor canonical root·serving/use pin·정식 SQLite/checkpoint backup·generation marker/manifest와 복원. 같은 schema 새 copy 0·원본 archive 불변 |
| T50 | 기존 보존 4파일 전체: 위 retention 2파일 + `test_retention_lifecycle.py` + `tests/migrations/test_canonical_retention.py`. busy 연기/다음 cycle·3캐릭터·종료 pin 원래 단언 유지 |

## 6. 테스트 퇴역과 불변 보존 증거

구 graph/SDK/StateRecorder·Supervisor·root Writer에만 적용되던 테스트는 **해당 기능을 여전히 실행하는 PASS로 취급하지 않는다**. 원래 node 이름·parameter 수집을 보존하면서 committed 원본과 실제 퇴역·대체 동작을 검사하는 종료 증거로 전환했다. `security/sns_retirement_evidence.json`의 46개 함수 중 resident 42개와 routine_posts 3개는 이 종료 증거를 검사하며, World import의 1개는 실제 지원 gateway 활성화·import 동작으로 전환했다. 원래 함수 본문은 7da Git 객체에 보존된다. 독립 pure 도메인 정책 검사는 test-owned `policy_ports.py`에서 실제 현재 도메인 함수를 사용한다. 삭제한 제품 실행기의 소스는 테스트에서 재실행하지 않는다.

`security/refactor_source_baseline.json`과 `security/refactor_backend_checkpoint.json`은 덮어쓰지 않는다. source ownership·API/UI·factory·test predicate의 의도된 제품 변경은 구현 commit의 정확한 Git blob/전후 AST/전후 assertion·API hash로 append-only manifest에 등록한다. 새 기능·검사는 실제 committed introduction만 추가한다. 퇴역 checker는 지정 세 모듈의 committed 삭제·모든 소유 심볼의 정확한 이동/퇴역·새 테스트·제품 import 차단을 검증한다. 임의 missing source 허용·skip·baseline 재생성·옛 제품 facade 재생성으로 통과시키지 않는다.

## 7. 실행 종료 기록

P00–P19의 로컬 구현·검증·문서 동기화를 완료했다. 아래 최종 전체 backend와 보존 Gate는 각각 종료한 실행의 결과다. 개별 검사를 합산해 전체 PASS로 바꾸지 않았다.

아래 표의 실행 시간은 완료한 JUnit suite 기록을 따른다. 최종 전체의 콘솔 전체 실행 시간은 5,188.87초이며 JUnit suite 시간 5,188.06초와 수집·마무리 시간만큼 차이가 난다.

| 실행 | 결과·소스 시점 |
| --- | --- |
| 시작 Git 객체 기준 | `pristine-baseline.xml`: 96 PASS, 0 SKIP, 409.90초. 시작 커밋 `7da83fb8`의 `git archive`에서 실행했고 현재 작업 폴더의 app import가 아님을 검증했다. 구현 후 수행한 사후 기준 검사이며 수정 전 실행이라고 소급하지 않음 |
| 구현 중 초기 기준 | `baseline.xml`: 96 PASS. 이미 초기 코드 변경이 있는 작업 폴더에서 실행했으므로 위 pristine Git 객체 기준과 구분 |
| 첫 전체 backend | `backend-full-first.xml`: 4,691 PASS / 25 FAIL / 52 SKIP, 5,362.60초. 개발 중 4,768개를 수집한 실행이며 이후 소스·정확한 변경 근거가 추가됐음 |
| 중단한 전체 실행 | `backend-full-second-interrupted.json`, `backend-full-third-interrupted.json`: obsolete current 생성 검사와 보존 소유권 증거 보완을 최종 실행 전에 고정하려고 중단. PASS 판정 없음. 원본 로그는 별도 보존 |
| 첫 실패 항목 후속 | `first-failure-followup.xml`: 139 PASS / 0 SKIP, 660.82초. 클래스/factory·원본 export·소비자 거절·실제 구조·inventory·역사 engine 정책 검사를 그대로 수행 |
| 실제 소유 회귀 | `final-owned-regressions.xml`: 227 PASS / 0 SKIP, 166.28초. 종료 증거와 지원 V2 실제 행동 검사를 구분하여 해석 |
| 최종 제품의 선행 보존 4파일 | `retention-final.xml`: 75 PASS / 0 SKIP, 372.49초. busy/후속 cycle·다른 캐릭터·pin·정리 보호의 원래 단언 유지 |
| cold import | `planning-cold-import-verified.xml`: 2 PASS. 새 프로세스에서 planning 먼저/service 먼저 import, 같은 순수 시간 함수·naive/offset 변환과 daypart 확인 |
| 닫힌 제거 증거 | `closed-introduction-proof.xml`: 17 PASS. 증거 없는 삭제·원본 재등장·실제 소유 함수 변경·잘못된 import를 거절. 다른 신규 미기록 소스는 계속 실패 |
| 보존 도구 지원 회귀 | `preservation-support-regressions.xml`: 147 PASS / 0 SKIP. 원본 baseline 불변·증거 첫 도입·같은 경로 변경·서로 독립인 노드 합침 거절 유지 |
| 최종 전체 backend | `backend-full-frozen.xml`: **4,747 PASS / 0 FAIL / 0 ERROR / 52 SKIP**, 4,799개 수집, 5,188.06초. 종료 코드 0. 제품·테스트 소스 기준 `3fc8728515821de3b20c6dfe7b5498f244a00308`; 이후는 증거/문서 추가 커밋이며 실행 시작 이후 해당 소스 변화 0 |
| 최종 보존 Gate | `preservation-gate-closed-complete.log`: `--contracts --nodes` PASS, exit 0. Frozen PR258 1,867·PR263 1,907에서 보호 계보 4,799 = 현재 수집 4,799. 37개 기능 항목, 정확한 API/ORM·기능 단언·추가 증거·실제 소유 경계 확인 |

첫 25개 실패는 클래스 1, factory 14, 삭제 경로를 가리키던 구조 검사 4, 현재 inventory 3, 새로 current를 생성하던 engine 검사 3이었다. 클래스/factory의 첫 실패는 전체 실행 중 먼저 읽은 변경 근거와 이후 소스가 달랐던 결과이며, 기존 체크를 완화하지 않고 새 프로세스에서 정확한 committed 근거로 재검사했다. engine 검사는 과거 행을 DB fixture로 복원해 역사 읽기·frozen identity·scope/revision·원장 보존과 신규 current 거절을 함께 검사하도록 전환했다.

보존 Gate의 소유권 목록 6곳은 실제 이동된 symbol이 없는 이전 destination을 제거했다. 과거에 도입됐다가 이번에 제거한 세 SNS 모듈은 Git preimage·전체 이동/제거 symbol·현재 행동 검사·import closure를 다시 확인한 경우에만 도입 소스의 정산 근거로 사용한다. frozen baseline/checkpoint를 새 결과로 덮어쓰거나 임의 삭제를 허용하지 않았다.


### 최종 판정과 로컬 커밋

최종 52개 SKIP은 첫 전체 실행과 `(classname, name, message)` 집합이 동일하다. 이번 변경을 통과시키기 위해 새 skip을 추가하지 않았다. 원본 로그/XML·첫 실패·두 중단 기록·정확한 schema 측정·최종 receipt를 `artifacts/sns-v2-routine-io-retirement/`에 로컬 보존한다. 이 경로는 Git ignore이며 clone에 포함되는 요약은 이 문서다.

전체 실행의 `faulthandler_timeout=180`은 오래 실행되는 검사의 현재 stack을 출력하는 진단 옵션이다. 로그의 `Timeout (0:03:00)!` stack 출력만으로 FAIL/ERROR로 판정하지 않으며, 해당 검사 종료와 최종 XML·프로세스 종료 코드로 판정했다. 실제 테스트 시간 제한을 늘리거나 검사를 생략해서 통과시키지 않았다.

최종 보존 Gate는 보호 테스트 계보 4,799개와 현재 수집 4,799개, 37개 기능 항목에서 PASS다. frozen baseline/checkpoint는 시작 HEAD와 같다. 퇴역 전용 45개 함수는 삭제·대체·소비자 차단의 종료 증거이며 옛 graph를 실행하는 기능 PASS가 아니다. 나머지 World import 1개는 실제 지원 gateway 행동을 검사한다. 실제 V2·Chat·Memory·하루 계획·이미지 및 선행 보존 기능의 동작 검사는 최종 전체 suite에 별도로 포함된다.

최종 제품·테스트 소스는 `3fc8728515821de3b20c6dfe7b5498f244a00308`다. 검증 중 이후 backend/frontend/scripts/browser-tests의 committed 변화가 없음을 확인했다. 다음은 이 문서를 최종 정리하기 전까지의 작업 로컬 커밋이다. 이 문서의 최종 정리도 Signed-off-by 로컬 커밋으로 저장하며 마지막 커밋은 `git log -1 --oneline`으로 확인한다.

| 로컬 커밋 | 내용 | DCO |
| --- | --- | --- |
| `49adc7b4` | feat(sns): bound Routine recovery and retire unsupported engines | Signed-off-by 확인 |
| `efac1ffe` | test(sns): inspect supported gateway and shared module boundaries | Signed-off-by 확인 |
| `62181d71` | fix(routines): make planning clock independent of service import order | Signed-off-by 확인 |
| `ccab20bc` | fix(routines): preserve the existing advertised clock exports | Signed-off-by 확인 |
| `c53a3be0` | chore(sns): record committed retirement and regression provenance | Signed-off-by 확인 |
| `a6d490ef` | test(sns): distinguish restored engine history from new admission | Signed-off-by 확인 |
| `83d993b6` | chore(sns): record historical engine test contract migration | Signed-off-by 확인 |
| `3fc87285` | fix(sns): reconcile committed source evidence with proven retirement | Signed-off-by 확인 |
| `ef7b58b5` | chore(sns): preserve closed source accounting regression provenance | Signed-off-by 확인 |

Workspace의 실행 계획·두 원문·빠른 참조·교차 검증 보고서 5개도 같은 결과로 최신화했다. 해당 문서는 제품 저장소 밖의 `D:/project_code/angmoo-workspace/docs/plan/`에 저장된 자료이므로 제품 repo의 커밋에 포함됐다고 표현하지 않는다. 문서 커밋 이후 확인하는 지정 branch·HEAD·clean·이슈 상태는 로컬 `artifacts/sns-v2-routine-io-retirement/final-local-state.json`에 기록한다.

## 8. 후속 경계

실제 API를 통한 Routine 잘림/복구 관측·내용 자연스러움·호출 latency/비용과 사용자 확인은 미측정이다. 현재 실행 중인 사용자 Docker/Windows 설치판·사용자 DB의 old row 수/전환은 확인하거나 적용하지 않았다. 운영 자료·API 키·원 카드·기존 관찰 원본은 테스트에 쓰지 않았다.

원격에는 이번 이슈만 생성했다. 브랜치 publish/push·PR·Hosted CI·main 전환/pull/병합·Docker build/deploy·설치 교체는 수행하지 않는다. 적용하려면 검증한 로컬 commit을 포함한 제품을 별도 승인된 절차로 다시 실행해야 한다.
