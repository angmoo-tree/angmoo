# SNS 고정 관계 입력의 SQLite 원본 재검증 구현·검증 기록

- 작업일: 2026-10-04, Asia/Seoul
- 구현 브랜치: `feat/0.1.0-release-readiness`
- 시작 HEAD: `7011cfb96c5af9b1265026c52e3ed58fa7d943d7`, 시작 작업 폴더 clean
- 원 계획: workspace `docs/plan/10-04 SNS 관계 스냅샷 재정렬 오판 방지와 SQLite 원본 재검증 코드 구현 세부 계획.md`, P00–P14
- 현재 판정: P00–P14의 제품 구현·격리 검증 완료. 중복 제외 482 PASS / 기존 PostgreSQL 1 SKIP이며, backend/frontend 공식 보존 검사와 아키텍처·design 검사도 통과했다. 운영 적용·실서비스 재관찰·원격 작업은 미수행이다.

## 1. 원인과 변경 결과

기존 SNS guard는 AI에 제공했던 관계 입력과 새로 선정한 입력의 `content_hash/status`를 비교했다. 해시는 실제 입력의 행 순서까지 포함하므로, SQLite의 관계 사실은 같고 LadybugDB projection의 순위만 바뀌어도 `activity_relationship_changed`가 발생할 수 있었다. 이전 관찰의 Elias Finch·Red·Bram 실패에 대응하는 합성 fixture의 두 경계, `BuildDecisionContext`와 `RecallSelected`, 총 6개가 수정 전 실패했다. 실제 버전 변경을 거절하는 보호 대조 1개는 수정 전에도 통과했다.

이번 구현은 처음 선정한 prompt·순서·입력 해시를 유지한다. 같은 snapshot에서 만든 backend 전용 `relationship_validation_receipts`를 준비/체크포인트에 저장하고, guard는 그 참조만 SQLite에서 읽어 비교한다. 새 ranking·출처·조회 시각을 기준으로 바꾸지 않는다. 실제 관계/관점 버전·수치·label·perception·사용한 표시 이름·사건 참조·가시성이 변하면 중단한다. relation 또는 view 버전이 증가한 뒤 값이 되돌아오는 ABA도 신규 기록에서는 감지한다.

관계 검증이 공통 서비스로 바뀌어도 target/recent/tense/positive 선정 정책, 3,000자 입력 한도, 외부/LLM DTO, 출력 schema, AI 호출 예산, SNS 계약 버전 2와 기존 환경·언어·시간대·보존 정책은 유지한다. 새 API·DB table·migration·설정 토글은 추가하지 않았다.

관찰 manifest에서 같은 관계 ID/버전 집합의 순서 변화와 재현 결함은 확인했다. 역사적 입력 전체의 모든 바이트가 같았다고 주장하지 않는다. 이전 세 실패 활동과 별개의 `action_brief_missing` 복구 기록은 변경·재시도하지 않았다.

## 2. 책임과 연결

| 소유 경로 | 이번 책임 |
| --- | --- |
| `backend/app/contracts/relationship_currentness.py` | 신규 run과 관계 receipt가 공유하는 revision/key 상수만 소유. World Characters → Relationships 순환 의존을 만들지 않음 |
| `domains/relationships/contracts/social_context.py` | scope/binding/basis/ref DTO, 엄격한 타입·revision·크기 검사, 내부 reason |
| `domains/relationships/policies/social_context_validation.py` | 공통 행 표현·display name 정규화, 사실 digest, 원래 ordered hash와 legacy context 증명 |
| `domains/relationships/service/social_context_validation.py` | 유한 canonical batch 결과의 방향·가시성·버전·사실 비교. Session 생성·commit/rollback·graph 재선정 없음 |
| `runtime/graph_projection/relationship_graph_read.py` | 같은 Session의 fresh scoped SQL, 기존 membership/block/observed 정책 입력 조립, native SQLite read deadline |
| `domains/relationships/service/graph_recall.py` | graph의 선정 순서는 유지하고 relation/view 사실은 SQLite canonical 값으로 반환 |
| `world_characters/service/activity_engines.py`, `autonomous_activity/execution.py` | 새 run에서 revision 고정, 저장 값과 checkpoint identity 대조. 기존 run 반환 시 값 추가 없음 |
| `autonomous_activity/inputs.py`, `social_lane.py`, `inbox.py`, `feed.py`, `routine.py` | 동일 snapshot의 prompt/receipt 준비, lane별 검증과 실패 의미 유지 |
| `autonomous_activity/combined_lanes.py`, `contracts.py` | hidden State 채널의 durable 저장/복원, Inbox 후 기존 Feed 갱신 시 prompt/receipt 함께 교체 |
| `autonomous_activity/provider.py`, `combined_provider.py`, `combined_selection.py`, `integrations/direct_llm.py` | quota/semaphore 대기 이후 실제 SDK 제출 직전 검증. 정상·허용 JSON 복구 모두 적용, SDK await 전에 읽기 transaction 종료 |
| `runtime/social/planned_actions.py`, `runtime/routine_posts/sqlalchemy_runtime.py`, `autonomous_activity/feed_effects.py` | 기존 완료 효과를 먼저 재사용. 미완료 공개 쓰기는 기존 SQLite immediate writer 안에서 최종 검증과 같은 commit으로 저장 |
| `runtime/diagnostics/sns_observation.py` | revision/outcome/reason/count allowlist만 기록. receipt·관점·key 원문 추가 기록 없음 |

계획의 P00 호출 추적에서 Feed 공개 효과가 `feed_effects.execute`를 직접 쓰는 것도 확인하여, 계획에 예시로 나온 Inbox/Routine executor와 함께 보완했다. Feed claim과 affordance는 기존 검사 함수를 추출하여 stage guard와 최종 writer 경계 모두에서 사용한다. callback은 명시적인 선택 인자이고 action JSON이나 Session 전역에 넣지 않는다.

## 3. 현재성·legacy·오류 계약

신규 `personalized_graph_v2` run에는 `social-context-currentness.v1`을 고정한다. 이전 run에 key가 없으면 명시적인 `social-context-currentness.legacy.v1`로 읽는다. 신규 기록 누락/손상을 legacy로 우회하지 않는다. OFF, 사실 없음, 조회 불가의 basis는 서로 구분하며 모두 actor scope를 확인한다. 원본 DB 오류와 deadline 초과는 `canonical_unavailable`이고 empty/성공으로 바꾸지 않는다.

legacy 입력은 알려진 intro, 정확한 row/header schema, 원래 row 순서와 scope/text/status를 사용한다. 현재 원본에서 그 row의 state ID와 관계 버전을 넣어 **원래 저장된 hash가 맞는지** 증명한 경우만 통과한다. 현재 버전을 새 baseline으로 저장하지 않는다. 옛 기록에 없는 view version은 복원하거나 ABA 보호를 제공했다고 주장할 수 없다. 그 범위의 한계는 유지한다.

외부 lane 오류는 `activity_relationship_changed`/`routine_relationship_changed`를 유지하며 내부에 `version_changed`, `view_changed`, `facts_changed`, `visibility_lost`, `receipt_invalid`, `legacy_unprovable`, `canonical_unavailable`, `facts_invalid`를 구분한다. 잘못된 타입, NaN, bool을 숫자로 해석하는 입력, 중복 참조, 알 수 없는 policy/revision은 거절한다. 관계 오류를 stale-target/no_action 성공으로 포장하지 않는다.

## 4. 경계·저장·부하 측정

receipt는 snapshot당 최대 12개 참조·16KiB로 제한한다. actor/target/state는 명시적인 scoped ID batch로 읽고, block도 관련 ID 집합으로 제한한다. 다른 관계의 추가/변경이나 다른 actor의 outgoing 변경 때문에 고정 입력을 무효화하지 않는다.

기본 누적 원본 조회 기한은 2초이고 service 설정 상한은 10초다. 여러 후보/상대를 확인하는 SocialLane/Routine guard는 하나의 마감 시각을 공유하여 snapshot마다 예산을 새로 시작하지 않는다. runtime은 현재 Connection의 SQLite progress handler와 statement별 남은 `busy_timeout`을 적용하고, 성공/실패 후 적용한 handler를 제거하고 이전 timeout을 복구한다. 새 Connection/Session이나 별도 DB transaction을 생성하지 않는다. 합성 exclusive lock 및 오래 걸리는 recursive SQL은 50ms 테스트 deadline에서 native 중단되고, 이후 Connection을 정상 재사용하는 검사를 통과했다. Connection pool 취득·OS 전체 스케줄링 지연까지 완전한 시간 보장으로 확대하지 않는다.

| 참조 수 | SQLAlchemy canonical 읽기 | native timeout PRAGMA | receipt bytes |
| --- | --- | --- | --- |
| 0 | 3 | 5 | 468 |
| 1 | 12 | 14 | 705 |
| 12 | 12 | 14 | 3,133 |

위 수치는 합성 fixture에서 측정한 값이다. 사건 관찰 증명에 추가 evidence 조회가 필요한 경로는 기존 유한 batch를 사용하므로 이 표의 동일 쿼리 수를 모든 데이터에 보장하지 않는다. guard의 graph open/재선정은 0이며 전체 World scan·관계별 Session·전역 pause를 추가하지 않았다. 이 소규모 측정을 실서비스 성능 개선율로 해석하지 않는다.

SDK 제출 hook은 limiter/semaphore 대기 뒤에 다시 검증한다. 실제 변경을 주입하면 최초 제출은 0회, 잘린 JSON 응답 뒤에는 추가 제출 0회였다. 재검증 읽기는 runtime이 완료하고 SDK 응답 대기 중에는 그 Session의 transaction이 열려 있지 않음을 fake SDK 경계에서 확인했다.

공개 effect 최종 검사와 저장은 기존 writer의 `BEGIN IMMEDIATE` 안에서 이루어진다. 다른 Connection에서 둘 사이의 변경을 주입하면 쓰기가 잠금으로 거절되고, 하나의 공개 효과만 커밋된다. AI await를 writer 안에서 수행하지 않는다. 완료 Inbox/Feed/Routine 효과와 기존 이미지 generation receipt의 재사용 경로를 보존한다.

## 5. C01–C16 / T01–T26 대응

| 계약 | 검사와 판정 근거 |
| --- | --- |
| C01–C03 | T01/T02/T06/T08/T23: 순서 민감 입력 해시는 유지, 실제 lane 순서-only 실패 제거, canonical fact/graph order 분리, outgoing/scope 유지 |
| C04 | T04/T05/T07/T13: 관계·관점 버전/ABA, 실제 수치·label/perception·이름·사건 시각 변경 및 UTC/strict 타입 |
| C05–C06 | T03/T08/T09/T11: 미선정/다른 actor 변경 허용, 참조 교체·삭제·membership·차단·observed·다른 scope 거절 |
| C07–C08 | T11/T14/T25: fresh 다른 Connection, 유한 0/1/12 참조, 16KiB, native deadline, 실제 AsyncSqliteSaver 및 durable 준비 복원 |
| C09–C10 | T10/T14/T15: Feed prompt/receipt 합법적 동시 갱신, 신규 정책 고정, 기존 run 미재작성, unknown/missing revision 거절 |
| C11–C12 | T12/T19/T20/T21: 원래 순서/hash의 legacy 증명, header/row 손상 거절, 옛 view 버전 제한, basis별 scope와 장애 거절 |
| C13 | T17/T18: Inbox/Feed/Routine 최종 쓰기와 완료 receipt 재사용; 기존 이미지 lifecycle·Combined delivery 재개 회귀 |
| C14 | T16/T17/T22/T23/T24/T26: SDK/Writer/Execute fencing, solo Routine 추가 관계 읽기 0, source/claim/lease/proposal/memory/image/출력/언어/시간대/retention 기존 회귀 |
| C15–C16 | T14/T26: LLM wire에 hidden receipt 없음, observer allowlist. 키 없는 검사와 실서비스·배포·CI·main 구분 |

| 테스트 ID | 직접 검사 또는 기존 회귀 |
| --- | --- |
| T01–T03 | `test_social_context_validation`의 order/unselected 검사 및 `test_activity_relationship_validation`의 Elias/Red/Bram × 두 실제 guard 경계 |
| T04–T05 | strict versions, 실제 값 변경, relation/view ABA |
| T06 | 실제 GraphRecallService+SQLite gateway의 stale-view 교체와 원래 graph 순위 유지 |
| T07 | 정규화 표시 이름, 실제 표시/label/perception/metrics/event 시간 변경 |
| T08–T09 | owner/world/actor/lane binding, 방향/삭제/교체/membership/차단/observed |
| T10 | receipt 파손·상한·strict revision, 신규 bind_run/legacy 반환 분기 |
| T11 | file SQLite의 다른 Connection commit, 독립 actor의 outgoing 변경 |
| T12–T13 | no_facts/unavailable/disabled, DB/기한 실패, 동일 UTC instant와 strict 숫자 |
| T14 | 실제 StateGraph/AsyncSqliteSaver roundtrip, hidden 채널과 AI request payload 분리, Combined preparation 회귀 |
| T15 | 실제 CombinedFeedLane refresh와 durable 저장에서 prompt/receipt 동시 갱신 |
| T16 | 실제 Direct LLM+ActivityProvider 경계의 fake SDK, limiter 후/JSON 복구 전 변경과 transaction 종료 |
| T17 | Inbox/Feed/Routine 실제 publisher, commit 전 변경 차단 및 SQLite writer interleaving |
| T18 | Inbox/Feed/Routine의 이미 커밋된 효과 재사용, 기존 Combined delivery/이미지 lifecycle |
| T19–T21 | 원래 행 순서/hash로 legacy 증명, 손상/불명확/신규 누락 거절, view 버전 미복원 |
| T22 | source가 있는 Routine 검증과 source 없는 Routine의 추가 relation read 0, 실제 Routine publish 회귀 |
| T23 | 기존 Chat social context workflow·GraphRecall 보호 회귀 |
| T24 | 기존 Combined 실패/전달, source 변경, proposal, memory revalidation, image generation lifecycle |
| T25 | 0/1/12 참조, 크기/쿼리 수, native exclusive lock/recursive SQL interruption 및 timeout 복구 |
| T26 | 안전한 observer payload, 기존 language provider boundaries와 checkpoint/maintenance/Routine retention |

## 6. 실행 결과와 증거 위치

제품 저장소의 `artifacts/sns-relationship-validation-20261004/`는 로컬 보존·Git ignore 자료이다. clone에 존재하지 않는 로컬 자료이며, 본 문서에 공유 가능한 요약을 남긴다. key·사용자 페르소나·원 Provider 응답을 새 fixture나 문서에 복사하지 않았다.

| 증거 | 결과 |
| --- | --- |
| `before.xml` | 6 FAIL / 1 PASS. 수정 전 실제 lane 순서 오판 재현과 기존 버전 변경 보호 |
| `acceptance-native.xml` | 116 PASS. 신규 Relationships 78개 + 실제 activity 경계 26개 + 기존 Feed 8개 + bind_run 관련 4개 |
| `bounded-measurements.xml` | 3 PASS. 0/1/12 참조 및 native timeout overhead 측정; 같은 acceptance node의 추가 계측 |
| `accumulated-guard.xml` | 49 PASS. 여러 후보의 누적 마감 시각 검사 1개 + 영향받는 기존/new lane 경계의 재검사 |
| `regressions.xml` | 308 PASS / 1 SKIP. 기존 Relationships/Chat/Combined/Routine/재개/SDK/관찰/보존/다국어/이미지 lifecycle |
| `regressions-final.xml` | 308 PASS / 1 SKIP. 마지막 native deadline/SDK transaction 종료 보완 이후 같은 회귀를 재실행 |
| `preservation-gate-regressions.xml` | 57 PASS. SNS 퇴역/소유 검증 28개와 기존 승인 계약·Git 증거 cache 회귀. 원본 정의·연속 변경·동일 소유·위조 출처·미승인 drift 보호 |

제품 검사만 중복을 제외하면 425 PASS / 기존 PostgreSQL 1 SKIP이다. 신규 제품 보호 검사 105개와 관련 기존 검사 320개가 통과했다. 여기에 보존 도구 회귀 57개를 포함한 최종 합계는 **482 PASS / 1 SKIP**이며, 신규 보호 검사 116개와 관련 기존 검사 366개로 구성된다. `accumulated-guard.xml`의 49개 중 48개는 앞선 결과의 재검사이고 새 누적 마감 시각 검사는 1개이므로, 49개를 합계에 다시 더하지 않는다. 실제 XML의 node ID를 대조한 집계는 `test-summary.json`에 보존했다.

유일한 기존 SKIP은 `routine_posts/test_runtime.py::test_same_tick_is_single_flight_across_twenty_postgres_sessions`이다. `SECURITY_CONCURRENCY_DATABASE_URL`이 필요하며 이 작업은 별도 PostgreSQL 서버/실제 운영 DB를 시작하지 않았다. SQLite single-flight와 이번 final writer interleaving은 실행했다. 이 SKIP을 PASS로 합치지 않는다.

중간 구현·fixture 실패 XML도 보존했다. fixture의 membership enum, block ID, observer 클래스, node list 취급을 실제 계약에 맞추었으며 보호 assertion 삭제·test skip 추가·mock 관용화로 합격시키지 않았다. backend 경계 검사에서 확인한 World Characters → Relationships cycle은 공통 revision 상수만 `app/contracts`에 두어 수정했다. 현재 import inventory는 실제 source 관계를 다시 생성한 것이며 허용 policy·frozen API/ORM/test baseline을 재생성하지 않았다.

최종 정적 검사 `generate_architecture_inventory --check`, backend/frontend architecture boundary, frontend design contract, `git diff --check`는 모두 통과했다. 현재 backend inventory는 modules 1,364 / internal edges 5,537 / external imports 4,019이며, backend 허용 경계 검사는 legacy exact edges 0을 확인했다. frontend 경계는 features 14 / legacy 0, design 검사는 raw colors 1,230 / files 36 / surfaces 18 / route gaps 0 / screenshots 18을 확인했다. frontend 코드 수정은 0이므로 브라우저 화면·Next/static build를 이 결함의 합격 근거로 새로 추가하지 않았다. 공식 backend/frontend source/node/API/ORM preservation 결과는 아래 종료 기록에 있다.

## 7. 운영 적용·후속 재관찰 경계

Docker backend/frontend는 조사 시 named volume만 사용하고 source watch sync가 없었다. 이 작업에서 서버 stop/build/restart·설치판 변경·사용자 DB/Ladybug 수정·과거 활동 재시도는 0이다. Windows 설치판을 진단하지 않았으므로 설치판 버전/반영 상태도 판정하지 않는다.

원격 이슈·push·PR·Hosted CI·main 작업은 수행하지 않는다. 작업 시작 전의 부모 변경은 없었으며 이번 소유 파일만 로컬 stage/commit한다.

추후 사용자가 운영 적용을 요청하면 정상 종료 후 기존 Docker 시작 가이드에 따라 `docker compose -f compose.yml -f compose.dev.yml up --build`로 해당 checkout을 재빌드하여 적용할 수 있다. watch 재개 여부는 사용자가 선택한다. 그 다음 별도 요청으로 기존 2시간 SNS 관찰 가이드를 사용하여 새 활동을 검증한다. recording coverage, 활동 성공, 실제 Feed 발생 여부, 중복 공개 효과/불필요 AI 재요청을 각각 판정한다. 새 관찰의 성공을 이전 세 실패 활동의 복구로 기록하지 않는다.

## 8. 최종 로컬 종료 기록

다음 세 source 커밋은 sign-off를 포함한 로컬 커밋이다.

- `ddb2200b9bdc54b79b9607664e7430813316c85e`: 고정 관계 입력의 canonical 검증과 실제 SDK/공개 효과 경계 연결. 이번 소유 33개 파일만 커밋했다.
- `60ae6cb1aa45c42a98c33dcca9681f177d56bbcb`: 여러 후보/상대가 같은 guard 마감 시각을 공유하는 보완과 추가 회귀 검사. 소유 5개 파일만 커밋했다.
- `ee6dc3bf75580623b64f11e98350a870618b3b7a`: SNS 퇴역 소유 검증이 같은 함수의 승인된 연속 변경을 확인하도록 연결하고 미승인·위조 변경 보호 검사 11개를 추가했다. 소유 3개 파일만 커밋했다.

공식 도입 도구로 첫 커밋의 신규 source 6개·test node 104개, 둘째 커밋의 추가 test node 1개, 셋째 커밋의 추가 test node 11개를 기록했다. 기존 계약 변경 기록 139개와 source/node 도입 기록 334개는 변경하지 않고 각 파일에 정확한 커밋 증거 3개씩을 추가했다. prefix 대조 결과는 `closeout-scope.json`에 보존했다. 현재 import inventory만 실제 import에 맞게 갱신했으며 frozen API/ORM/source/test baseline과 원래 SNS 퇴역 증거는 변경하지 않았다.

Frontend 공식 보존 검사는 source 324개와 browser assertion/fixture/asset/lock 보존을 확인하고 통과했다. 둘째 source의 도입 기록을 추가하기 전에 시작된 중복 backend 검사는 해당 작업 소유 프로세스만 취소하고, 모든 source 증거가 준비된 최종 `--contracts --nodes` 검사로 대체했다. 취소를 PASS 또는 제품 코드 실패로 판정하지 않는다. 이 경위는 `superseded-check.json`에 기록했다.

최종 backend 공식 `--contracts --nodes` 검사는 **exit 0**으로 통과했다. 원래 PR258 1,867개·PR263 1,907개 node를 바탕으로 검증한 protected lineages 5,085개와 current nodes 5,085개가 일치했으며 보존 항목 37개가 통과했다. 실제 결과는 `backend-preservation-complete.log`와 `preservation-complete-results.json`에 보존했다. 셋째 커밋의 공식 도입 검사 역시 exit 0이다.

종료 커밋에는 `security/post_refactor_contract_changes.json`, `security/refactor_backend_additions.json`, 본 검증 문서만 명시적으로 stage한다. source 구현 3개와 종료 증거 커밋을 분리하며, 최종 HEAD와 clean 확인은 workspace 원 계획 §15 및 로컬 `final-git-state.json`에 기록한다. 전체 작업 소유 변경 경로는 37개이고 frontend·workflow·migration 변경은 0이다. 로컬 완료는 배포/실서비스/원격 반영과 분리한다.

첫 최종 backend 검사에서 `SNS retained symbol differs from exact reviewed ownership`가 발생했다. `_execute_planned_action`은 공개 효과 직전 관계 검증과 SQLite writer 경계가 추가된 실제 소유 함수이지만, SNS 퇴역 검증은 옮긴 당시 AST와 현재 AST가 영구히 같은지만 검사했다. 원래 퇴역 기록·기준의 재작성이나 실행 함수의 복제/전역 hook으로 우회하지 않았다. SNS 검증이 기존 승인 계약 도구의 append-only 역사·Git ancestry/blob·정확한 전후 AST 검증을 거친 **같은 소유 함수의 연속 변경**만 인정하도록 연결했다. 다른 소유·미승인 공백·미커밋 변경·위조 출처·원래 퇴역 정의 변경은 계속 실패한다. 57개 관련 검사가 이를 대조했다.

첫 실패의 보호 목록 0과 뒤따른 전체 test-node 오류는 이 선행 오류로 목록 계산이 중단된 결과이며, 제품 검사 실패 5,074건으로 해석하지 않는다. `backend-preservation-final.log`와 첫 판정 JSON은 원형 보존하고 별도 파일에 전체 재실행 결과를 남긴다. 보존 도구의 이 수정도 별도 source 커밋·정확한 append-only 증거로 보호한다.
