# 일반 일과·공동 활동 분리와 Feed 관찰 저장 경계 구현 결과

작성일: 2026-09-29
제품 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
브랜치: `fix/routine-output-contract-cleanup`
구현 전 HEAD: `003d3876d50f6be0b2fd0e8e20a90ebac894feb8`
실행 계획: [09-29 통합 코드 구현 세부 계획](<../../../docs/plan/09-29 일반 일과·공동 활동 분리와 Feed 관찰 SQLite 저장 경계 통합 코드 구현 세부 계획.md>)
증거 폴더: `D:/project_code/angmoo-workspace/.local-diagnostics/daily-joint-feed-integration-20260929`

## 1. 최종 동작과 변경 범위

일반 하루 계획의 AI 출력은 예약 전용 `joint_activity`와 `joint`를 선택할 수 없다. 서버가 완료·사용자 고정·유효한 공동 예약을 보존하고, AI가 새로 만든 미정 시간대와 결합하여 최종 네 시간대를 저장한다. 사용자와 대화하기, 간식을 받고 묘기하기, 돌보기 같은 소재는 일반 일과로 허용한다. 소재만으로 상대의 승낙·출석·완료를 확정하지 않는다.

Inbox는 열린 제안의 원본 댓글을 같은 가지의 후속 일반 댓글과 분리한다. 제안 ID·버전·원본·처리할 알림을 해당 후보에 고정하고 Writer와 실제 공개 응답까지 전달한다. 공동 승낙이 저장되면 기존 공유 예약과 참여자 두 명의 일정 연결을 재사용한다.

Feed는 전달 기록 한 건마다 공통 SQLite `BEGIN IMMEDIATE` 쓰기 단위를 사용한다. 관찰 receipt·관계 관찰 outbox·정산 결과·완료 표시는 함께 commit되거나 함께 rollback된다. 이미 성공한 공개 행동을 DB 저장 재시도로 다시 생성하거나 발행하지 않는다.

SNS 계약 버전 2의 통합 선택 → Inbox → Feed → Routine과 정상 호출 구성을 바꾸지 않았다. DB 스키마와 Frontend도 변경하지 않았다. Docker 운영 서버·watch·자율활동·장시간 관찰을 시작하지 않았으며, 원격 push·이슈·PR·CI·main 병합을 수행하지 않았다.

## 2. 책임과 소유 위치

| 책임 | 코드 소유 위치 |
| --- | --- |
| 신규 일반 생성 타입과 접수 버전 | `backend/app/domains/routines/schemas/daily_generation.py` |
| 일반 생성 지침·요청별 시간대 enum·출력 수 제한 | `backend/app/domains/routines/client.py` |
| 새 결과와 보존 방향의 검증·결합, claim/적용 | `backend/app/domains/routines/service/daily_preparation.py` |
| 기존 job 버전 선조회, 원본·예약·시각 snapshot, Topic-only·원자 적용 | `backend/app/runtime/daily_preparation.py` |
| 생성한 문구만 이름 치환, 기존 고정 문구 보존 | `backend/app/runtime/preparation_names.py` |
| 기존 Topic 생성의 공유 tracker·물리 요청 계수 | `backend/app/runtime/social/topic_preparation.py` |
| 한정된 알림 집합에서 제안 원본별 분리 | `backend/app/domains/social/service/activity_inbox.py` |
| 후보·원본·제안 버전·알림 고정 및 재검사 | `backend/app/runtime/autonomous_activity/inbox.py` |
| 응답 결정의 Writer 전달, 구 snapshot 처리, 성공 공개 행동 재사용 | `backend/app/runtime/autonomous_activity/social_lane.py`, `provider.py` |
| 전달 한 건의 원자적 관찰 저장 | `backend/app/runtime/social/feed_observations.py` |
| 상위 transaction 종료·정상 정산·pending 복구 | `backend/app/runtime/autonomous_activity/feed.py` |
| 원래 오류와 관찰 정리 오류의 연결 | `backend/app/runtime/autonomous_activity/execution.py` |

Backend `ARCHITECTURE.md`의 domain/runtime/provider 및 commit 소유 경계를 준수했다. Frontend `ARCHITECTURE.md`·`DESIGN.md`의 API 소비·기존 화면 계약을 검토했다. 하위 관찰 domain에는 commit이나 별도 retry를 추가하지 않았다.

## 3. 하루 계획 생성과 보존 계약

### 접수·저장 버전

신규 준비 job의 `input_snapshot.generation_contract`는 `daily-generation-v2`다. 저장되는 하루 계획 계약은 계속 `daily-plan-v1`이다. SNS 실행 계약 버전 2와 이 준비 출력 버전은 서로 다른 계약이다.

먼저 같은 요청 ID의 기존 job을 조회하고, 그 job이 접수한 버전으로 source와 digest를 구성한다. marker가 없는 기존 job은 이전 네 항목 출력 타입·지침·source 모양·digest·이름 binding을 사용한다. 진행 중 요청에 새 규칙을 덮어씌우지 않는다. 알 수 없는 생성 버전은 거절한다.

### 실제 요청과 최종 계획

| 보존 상황 | AI에게 요구하는 일과 출력 | 최종 저장 |
| --- | --- | --- |
| 보존 없음 | 일반 항목 4개 | 네 시간대 4개 |
| 보존 1~3개 | 미정 시간대의 일반 항목 3~1개 | 보존 원본 + 새 결과, 총 4개 |
| 전부 보존·Topic 사용 가능 | 호출 없음 | 기존 계획 그대로 |
| 전부 보존·최초 Topic 미준비 | 기존 Topic 생성 책임으로 Topic만 요청 | 계획 ID·버전·항목 그대로, Topic만 적용 |

신규 출력의 `activity_kind`는 `duty/rest/self_care/hobby/exploration/social/maintenance/challenge`, `social_mode`는 `solo/open_to_interaction/cooperative`다. 요청 schema는 실제 생성 대상 시간대만 enum에 넣고 배열 길이도 그 수로 고정한다. 서버 validator도 같은 대상 집합·중복·누락·장소 권한을 검증한다.

보존 snapshot에는 기존 항목·episode·버전·시각과 공동 예약·참여자 연결을 포함한다. 고정 문구를 AI에게 재출력시키거나 현재 이름으로 다시 치환하지 않는다. 생성 중 새로운 승낙·고정·시각 변경이 들어오면 적용 전 fresh source 검사가 낡은 결과를 거절한다. 최초 Topic과 계획은 둘 다 유효할 때 같은 쓰기 단위에서 적용한다.

지난 시간대는 `skipped`이며 소급 경험을 만들지 않는다. 이미 끝난 미연결 예약은 새 일반 생성의 보존 대상으로 넣지 않는다. 기존 완료·고정·연결된 자료를 삭제하거나 과거 예약을 임의로 완료 처리하지 않는다. 유실·손상된 과거 Topic의 자동 재생성은 추가하지 않았다.

## 4. SNS 제안·승낙과 재개

기존 oldest-first 알림 상한 10개와 통합 선택 상한을 유지한다. 후보 분리 때문에 더 많은 알림을 읽거나 강제 선택하지 않는다. 제안 뒤에 일반 댓글이 있어도 제안 후보의 source·target이 마지막 댓글로 바뀌지 않는다. 한 알림은 한 후보만 소유한다.

발행 전 제안 ID·버전·원본·대상·일정이 유효해야 한다. `accept/reject/counter`, 명시적 `no_action`, 미선택과 실패를 구분한다. 미선택·실패·생략된 결정의 알림은 처리하지 않는다. counter로 만든 다음 제안도 그 원본을 별도 후보로 유지한다. 이미 닫힌 제안을 열린 초대로 제시하지 않는다.

종단 검증에서 추가로 두 연결 누락을 확인하고 보완했다.

- V2 assignment에는 제안이 `source.activity_proposal`에 있었지만 기존 Writer 적용 책임은 직접 `activity_proposal`을 읽었다. 이제 구조화된 응답 결정이 있을 때만 고정 제안을 전달한다. 구 assignment도 이미 고정된 source에서 읽으며 다른 live 제안을 찾지 않는다. 일반 댓글을 자동 승낙으로 바꾸지 않는다.
- 성공한 승낙으로 관계가 바뀌면 Execute 재개의 이전 관계 snapshot 검사가 실패할 수 있었다. 동일 run·캐릭터·lane·행동·원본의 성공 실행을 실행과 guard가 함께 재사용한다. Feed는 기존 실행 signature로 확인한다. scope·권한 검사는 계속 수행하며 미실행 대상의 snapshot 검사를 생략하지 않는다.

양쪽 계획이 모두 있으면 승낙 저장 시 두 일과를 함께 연결한다. 한쪽 또는 양쪽이 없으면 공유 예약과 참여자 두 명을 먼저 저장하며, 이후 계획 생성에서 두 연결이 갖춰지면 `ready`가 된다. 한쪽 계획만 먼저 바꾸는 방식은 추가하지 않았다.

공동 시작 글 claim, 양쪽 episode와 후속 장면, 발행 실패·만료, 공개 근거에 따른 관계·기억 연결은 기존 소유 책임을 그대로 사용한다. 예약 저장이나 생성한 계획만으로 `joint_started`·완료 사건을 만들지 않는다.

## 5. Feed SQLite 저장 경계

상위 Feed lane이 소유한 기존 transaction을 종료한다. 이미 flush된 상위 변경도 commit해 보존한 뒤, 깨끗한 Session에서 공통 `run_sqlite_session_immediate(require_clean=True)`가 쓰기 권한을 먼저 확보하고 전달 자료를 새로 읽는다.

전달 기록 한 건의 관찰과 정산은 한 transaction이다. 글 단위 SAVEPOINT는 삭제·숨김 등 예상 가능한 `SocialObservationError`를 `not_applied`로 기록하는 데만 사용한다. I/O·`SQLITE_LOCKED`·outbox 무결성·프로그램 오류는 전달 전체를 rollback하고 원래 오류를 전파한다.

공통 BUSY 정책은 최대 4회·전체 0.25초를 그대로 사용한다. 지속 경합의 한도 소진은 pending을 보존한다. 복구는 읽기 전용 ID 목록 조회를 닫은 뒤 전달마다 새 쓰기 단위를 실행하고, 첫 소진에서 batch를 멈춘다. 같은 전달·같은 관찰자를 재실행해도 receipt·outbox를 중복 저장하지 않는다.

처음 전달된 `updated_at`을 그대로 유지한다. 이미 settled인 정상 정산 재개도 기존 receipt/outbox 무결성을 검사하고 과거 outcome을 다시 쓰지 않는다. 성공한 Inbox·Feed 댓글은 정산 실패로 취소하거나 다시 발행하지 않는다.

기존 tracker → SNS 관찰 attempt에 `sqlite_write`를 기록한다. `unit=feed_delivery_observation`, `ObserveDelivered/ReconcileDeliveries`, business key hash, 시도·대기·transaction 시간·SQLite code/name을 사용한다. attempt가 run/activity/World/actor를 연결한다. 새 로그에 키·본문·SQL 매개변수를 넣지 않았다. 원래 lane 오류와 관찰 cleanup 오류는 `caused_by_event_id`로 연결한다.

## 6. 로컬 검증

구현 전 관련 baseline은 62 passed였다. 실제 기존 Feed observer 경로의 새 재현은 4 failed·1 passed였으며, 후속 공통 writer 변경으로 잠금·부분 commit·재개 문제가 해소되는지 검증했다. 이 수치는 구현 전 재현이며 최종 통과 수에 더하지 않는다.

최종 회귀는 **155 passed, 184.86초**다. 정확한 명령과 결과는 증거 폴더의 `final-regression.txt`에 기록했다. 수정 중 fixture·assertion 오류와 중간 실패 로그도 별도 보존했고 최종 전체 명령에서 모두 통과했다. 검증 범위는 다음과 같다.

- 일반 생성 시간대 1~4개와 보존 0~4개, 예약 enum 거절, provider schema와 validator 일치.
- 완료·고정 원본·이름 binding·구 접수 job 재개·Topic 원자 적용·Topic-only·0회 호출.
- A 통합 선택/Feed 제안 → 실제 댓글·알림 → B 통합 선택/Inbox 승낙 → 승낙 사건·두 참여자·즉시/지연 계획 연결.
- 제안 뒤 일반 댓글·역순·별도 가지·counter·10개 페이지 경계, 변경된 제안 거절, 실패·미선택 알림 보존, 구 Writer snapshot.
- 승낙 저장 직후 guard/Execute 재개에서 중복 공개 응답·예약 없음.
- 파일 WAL에서 계획 생성 중 다른 Session의 승낙 저장과 stale 결과 거절.
- 짧은 경합 재시도·지속 경합 pending·중간 글 저장 실패의 전체 rollback·같은 전달과 세 캐릭터 Session 경합·outbox 손상·전달 시각 보존.
- 기존 공동 실행·발행 실패·만료·관계·기억·S1/S2/S3와 SQLite 저장 경계.

Backend 구조 검사: `modules=1302`, `edges=5266`, `legacy_exact_edges=0`, PASS. 변경 Python 파일 compile 및 `git diff --check`도 통과했다. 독립 Python lint/type 도구는 현재 Backend 개발 의존성에 설정되어 있지 않아 해당 도구 실행을 주장하지 않는다.

## 7. 실제 AI 평가와 실패 판독

평가 모델은 Gemini `gemini-3.1-flash-lite`, thinking `high`다. 미도리야 이즈쿠에 연결된 승인 키를 사용했다. 기록 식별 정보는 `credential_id=cred-f131827bc5d5`, fingerprint `8c74e02fe2ab6487`이며 키 원문은 저장하지 않았다.

운영 credential volume은 read-only로 조회했다. 모든 평가 World·캐릭터·계획은 별도 합성 파일 SQLite DB다. 운영 SNS World·설정·키 연결·공개 글·예약을 변경하지 않았다. 서버·스케줄러는 실행하지 않았다. 평가 컨테이너는 종료 후 제거됐다.

물리 요청은 공통 `budget.json`에 요청 전에 예약하고 전체 성공·실패·SDK/repair를 합해 60회로 제한했다. 이번 누적 **34회**로 종료했다. `wire-requests.json`의 응답 기록도 34건이다. 중간 구현 확인 11회, 최종 21개 사례 21회, Sakana 확인 2회다. 각 provider 요청의 SDK 시도는 1회다.

| 평가 구간 | 사례 | 결과 | 실제 요청 |
| --- | --- | --- | --- |
| 최종 일반 준비 | 세 카드 × 최초·다음 날짜·예약 1개·고정 3개·전부 보존·Topic-only = 18 | 18 유효, 전부 보존 3개 사례는 호출 0회 | 15 |
| 최종 Inbox 해석 | Seraphina·Sakana·Flux | 2 유효, Sakana 결정 검증 거절 1 | 6 |
| Sakana 동일 조건 확인 | 별도 fixture 1개 | 유효 | 2 |

최종 및 확인 평가 22개 사례 중 21개가 유효했다. 최초 Sakana 실패를 재평가 성공으로 덮어쓰지 않았다. 정상 Inbox 생성은 선택 1회와 판단·문안 1회이며 강제 추가 Writer 생성이 없었다. 실제 선택은 별도로 기록하고, 제안 원본 해석을 비교할 때 해당 원본에 주의를 두는 조건을 명시했다. 이를 자연 활동의 선택 확률이나 자동 승낙률로 해석하지 않는다.

Sakana의 최초 실패는 `accept`인데 `counter_target_daypart/date_policy/target_date`를 함께 반환한 경우다. 기존 validator의 `counter fields require proposal_decision=counter`에 걸렸다. **HTTP 400이나 DB 저장 오류가 아니며 공개 응답·예약은 수행하지 않았다.** 실패 원문과 재평가 결과를 별도로 보존했다. validator 완화·대안 필드 삭제·강제 승낙으로 통과시키지 않았다.

중간 구현 확인에는 참여자 복합 PK를 `id`로 읽은 새 snapshot 결함이 있어 예약 fixture 세 개가 AI 호출 전 실패했다. 이를 `joint_activity_id/world_character_id`로 고쳐 최종 예약 사례와 종단 회귀를 통과했다. 중간 Seraphina Topic-only에서는 한 글자 Topic `숲`이 기존 최소 길이 검증에 걸렸고 기존 계획은 유지됐다. 최종 Topic-only 세 사례는 통과했다. 중간 자료를 최종 새 계약의 통과 자료로 합치지 않았다.

성격 소재는 Seraphina의 숲 보호·돌봄, Sakana의 코딩·게임·장난스러운 비서 말투, Flux의 룸바·참치·새 관찰·울음 표현에서 확인했다. 사용자와의 대화·돌봄도 예약 enum 없이 일반 `social/cooperative`로 생성됐다. 의미 품질을 완전히 보장하는 평가는 아니다. 카드의 시나리오 가정이 계획에 남거나, Sakana의 thought가 초대한 다른 캐릭터를 비서의 주인처럼 해석하는 경향이 보였다. 계획을 실제 이력으로 취급하지 않는 기존 경계는 유지하며, 운영 자연 활동 품질은 이번 격리 평가와 구별한다.

주요 자료: `real-ai-final/manifest.json`, `summary.json`, `inbox-Sakana-failure-analysis.json`, `real-ai-sakana-followup/summary.json`, 공통 `real-ai/budget.json`·`wire-requests.json`. 카드 SHA256은 각 manifest에 고정했다.

## 8. Frontend·호환·운영 반영

**Frontend 수정 불필요.** 기존 `DailyActivityPlanRead.items`의 네 항목 제약·공동 ID·예약 시각·episode·상태를 유지했다. 종단 테스트는 실제 `plans.get_activity_plan` DTO에서 두 캐릭터 각각 최종 네 항목과 공동 연결을 확인한다. `DailyPreparationRead`의 준비 상태·실패·request 상태도 그대로다.

기존 `daily-preparation-panel.tsx`는 새벽/오전/오후/저녁 네 시간대를 표시하고 예정·진행·완료·skipped를 구별한다. 계획은 실제 경험이 아니라는 안내도 유지한다. 신규 부분 AI 결과가 화면에 전달되지 않는다. UI 변경이 없어 Frontend lint/typecheck/Next/static/브라우저 재검증은 이 변경에 대한 적용 대상이 아니며, 운영 UI 직접 확인은 미실시다.

새 열·제약·테이블이 없고 marker는 기존 job JSON에 들어가므로 migration이 없다. 기존 구 job·계획·reservation·episode·게시글·관계·기억을 삭제·변환하지 않았다.

이전 reader의 제거는 별도 작업이다. marker 없는 pending/running/waiting job 및 구 checkpoint가 더 이상 재개 대상이 아니고, 과거 자료 열람/내보내기 소비자를 확인한 뒤 제거한다. 예약 전용 enum·공동 실행·구 저장 자료 읽기는 일반 생성에서 제외됐다는 이유로 삭제하면 안 된다.

최종 확인에서 운영 Docker 컨테이너와 Compose watch는 실행 중이 아니었다. 현재 실행 폴더의 소스는 새 코드지만 기존 Docker 이미지에는 이 로컬 커밋이 자동으로 빌드된 것으로 볼 수 없다. 사용자가 같은 폴더에서 기존 `docker compose -f compose.yml -f compose.dev.yml up --build --watch`를 시작하면 빌드·watch 조건에 따라 새 코드가 반영된다. 이번 작업은 그 서버를 시작하지 않았다.

로컬 구현·모의 종단/WAL 회귀·실제 AI 평가는 서로 다른 검증이다. 장시간 운영 관찰, 사용자의 직접 확인, 원격 CI/PR/main 병합은 미실시다.

## 9. 커밋·검증 식별

이 문서·제품 코드·회귀 테스트·명시적 opt-in 평가 도구를 현재 브랜치에 지정 stage하여 로컬 커밋한다. 최종 SHA와 테스트 수는 작업 종료 시 실행 계획 §10 및 증거 폴더의 `completion.json`에 기록한다. 이 문서를 포함한 커밋은 `git log -1 -- docs/verification/daily-joint-feed-20260929.md`로 확인할 수 있다.

## 10. 공개 전 이력·검증 자료 보완

위 결과는 로컬 구현 당시의 기록이다. 2026-09-29 후속 공개 단계에서는 동일 제품 코드에 DCO trailer를 보완하면서 미공개 커밋 SHA가 변경됐다. 구현 전 `003d3876d50f6be0b2fd0e8e20a90ebac894feb8`은 `f7b7499d4e14cd933b8f8c7eec3fab1f18af9778`, 구현 완료 `480d3bca8cfdd47c71ca5fffda4f3a339d939cd6`은 `eb8473cc0b3aff0eead24fb6196b1f711642c45b`에 대응한다. 두 이력의 제품 소스·테스트는 같으며, source/test 도입 근거와 제품 변경 manifest는 새 선행 커밋을 정확하게 참조한다. 원래 이력은 로컬 backup ref와 bundle에 보존했다.

이 단계에서 Feed 저장 모듈이 누락된 현재 import inventory를 정상 생성기로 갱신했다. 최신 목록은 `modules=1303`, `internal_edges=5269`, `external_imports=3818`, `legacy_exact_edges=0`이다. 위 §6의 이전 목록 수치는 당시 기록으로 남긴다. 고정 checkpoint는 갱신하지 않는다.

이번 PR은 앞선 Routine 출력 책임 분리·에너지 제거·답글 복제 방지와 World 프로필 이름의 요청용 치환까지 함께 포함한다. 이름·상태·실행 버전과 이전 자료 읽기 경계, embedded schema v24/v25 및 설치 업그레이드를 최종 후보 CI에서 검증한다. 로컬 회귀 155건과 과거 승인된 실제 AI 평가를 새 원격 CI의 결과로 표시하지 않는다. 공개·CI 작업에는 추가 실제 AI 호출이 없고, 사용자 Docker 관찰의 소스·DB·컨테이너를 변경하지 않는다.

관련 구현 문서는 [요청용 이름 치환](../operations/persona-name-binding.md), [이슈 #345](https://github.com/angmoo-tree/angmoo/issues/345)에서 확인할 수 있다. 위 workspace 계획·증거 경로는 원래 로컬 재현 자료의 위치이며 공개 저장소에 해당 자료를 포함한다는 의미가 아니다. 최종 PR·CI 결과와 main 병합 대기 상태는 PR 본문에 별도로 기록한다.

공개 전 설치 검증에서는 v25의 새 `request_snapshot` 열이 합성 이전 버전 fixture에 남아 v23 재현의 schema digest가 어긋나는 누락을 실제 테스트로 확인했다. fixture builder만 해당 열을 제거해 이전 manifest와 일치시키고, 지원하는 v24도 hosted NSIS 업그레이드 입력에 추가했다. 실제 사용자 자료는 기존 forward migration으로 처리하며 재구성하지 않는다. 기존 테스트 단언은 유지하고 이전 버전 열 부재와 v24 상태 열 존재 검사를 추가했다. `tests/test_p8_l_d_installer_upgrade_contract.py` 및 `tests/migrations/test_topic_request_v25.py`는 **26 passed**, desktop installer 안전 계약·CI 정책·v1~v24 matrix 정합성·PowerShell 문법·workflow YAML 검사도 통과했다. 실제 hosted installer 설치·실패 복구 결과는 최종 head CI에서 별도로 확인한다.

첫 PR CI에서는 전체 Backend suite 전의 현재 L4 inventory 검사와, 카드 업로드 후 production build의 개발 생성 타입 문법 검사가 실패했다. 정상 생성기로 현재 L4·hybrid closure의 소스 해시·소유 모듈을 갱신했으며 frozen predecessor·기능 계약·범위는 그대로다. 관련 inventory 테스트 10건과 public route 226개 검사를 통과했다. 브라우저 fixture의 기존 POSIX 종료 helper가 부모만 종료해 자식 서버를 남기는 결함은 Node 22.23.2 격리 재현으로 확인했다. 테스트 소유 process group 전체를 종료하고 close·제한된 강제 종료를 확인하도록 바꿨다. 같은 재현에서 수정 전 자식 서버는 살아 있었고 수정 후에는 종료됐다. 기존 카드 업로드 단언은 모두 유지하고 자식 서버 종료 회귀를 추가했다. TypeScript 검사를 끄거나 소스·출력 계약을 완화하지 않았다. 생성 타입 오류의 최종 해소는 새 후보의 전체 frontend CI로 확인한다. [Node 공식 자식 프로세스·종료 안내](https://nodejs.org/docs/latest-v22.x/api/child_process.html#subprocesskillsignal).

두 번째 후보의 Frontend는 전체 검사를 통과했다. Backend 전체 suite에서는 **4,280 passed·9 failed·28 skipped**를 확인했고, 실패 9건을 같은 조건의 선택 회귀에서도 재현했다. 일일 계획용 Topic source에는 `persona`가 있지만, 보존한 승인 프로필용 source에는 해당 키가 없으므로 그 source의 기존 모양·승인 provenance를 유지하도록 렌더링 대상을 구분했다. 이름의 범위·digest 검증, 요청 snapshot, 새 출력 검증은 그대로다. 공통 입력의 기록 제한 테스트에는 실제 저장 형식의 이름 snapshot과 run 조회 fixture를 제공해 새 요청 경계를 확인하며 기존 기록·누락·원본 보존 단언을 유지한다. 현재 PostgreSQL 잔재 목록은 정상 생성기로 새 Feed 저장 모듈과 두 변경 source의 hash를 반영했고, 불변 ER0 기준과 원래 검증기는 유지했다. installer 출력 기대값은 v1~v23에서 **v1~v24 전체 목록**으로 확장했다. v3 fixture·자료 생존·반복 설치 조건을 없애거나 범위를 줄인 변경이 아니다. 관련 기존·이름 준비·Topic 회귀는 **46 passed**이며, 정확한 source와 단언 전후를 정상 append-only 근거로 남긴다. 새 후보의 전체 CI 결과는 별도 확인한다.

세 번째 후보의 Backend 전체 suite는 **4289 passed·28 skipped·0 failed**였고 Frontend, Security, Local Smoke, Windows Host, CodeQL도 통과했다. hosted Windows Installer에서 빌드·충돌 실패 복구·clean install은 성공했다. 지원 업그레이드 job은 `windows_installer_supported_upgrade_pass`를 **24회** 출력해 v1~v24 각각의 실제 NSIS 업그레이드를 확인했지만, 마지막 표식 직후 job의 **20분 제한**이 반복 설치의 불변성 검사와 최종 성공 표식 전에 실행을 취소했다. 따라서 전체 Installer 검사를 통과로 보지 않는다. 검증 루프·버전 범위·실패 처리는 유지하고, 이 job에만 상한 30분을 주어 남은 반복 설치·정리를 수행하도록 한다. 이후 후보의 실제 hosted 전체 결과는 별도 확인한다.
