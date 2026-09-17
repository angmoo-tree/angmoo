# 기억 정리 예약 변경과 지금 기억 정리

2026-09-17 MS0~MS14 로컬 구현 결과. branch `fix/chat-retrieval-debugging`, base HEAD `ae1c824fe54b5e9e56d65d7a747f9b8f3601513d`. 아직 commit/push/main merge/CI를 진행하지 않았다.

**2026-09-17 후속 판정: F1~F4 사용자 수용 기준 PASS.** F4는 실제 사용자 채팅과 기억 정리 AI의 동시 실행·양쪽 완료를 확인했다. F2의 알려진 응답 품질 이슈, F3의 반복 측정 생략, F1의 제한된 사례 범위와 F4의 정량 자원·반복 부하 미측정은 그대로 남는다. [에피소드 운영 안내](episode-memory.md)의 최신 판정과 후속 검증을 따른다.

## 사용자 동작

- 현재 World·캐릭터의 Memory 화면에서 설정을 저장한 뒤 **지금 기억 정리**를 누른다. 다른 캐릭터 전체를 한꺼번에 정리하는 버튼이 아니다.
- 기존 Memory ON·AI 선별 동의·모델/API 준비·용량 조건을 충족해야 한다. 저장하지 않은 설정이 있으면 먼저 저장하도록 표시한다.
- 서버 수락 시점의 미처리 자료가 대상이다. 대기 중 생긴 새 자료는 다음 요청 대상으로 남는다. 처리 이력이 있는 자료를 버튼마다 전부 다시 요약하지 않는다.
- 같은 요청 재전송은 같은 receipt를 반환하고, 진행 중 같은 캐릭터의 유효 요청에는 합류한다. 네트워크 실패 재전송에 새 key를 만들지 않는다.
- 정리할 자료가 없으면 준비 확인 후 ‘새로 정리할 경험이 없어요’를 표시하며 AI를 호출하지 않는다. 자료가 있으나 선별 결과가 없으면 ‘새 기억 0개’로 완료할 수 있다.
- 수동 정리는 예약·종료 설정을 바꾸지 않는다. 예정된 예약이 나중에 도착해도 새 자료가 없다면 AI 0회다.
- 당일 13시 정리 후 14시로 바꾸면 당일14시 실행 가능, 13:10에12시로 바꾸면 다음 날12시다. 같은 설정 재저장은 overdue 예약을 보존하며 토글은 같은 슬롯 재실행 수단이 아니다.
- 예약 OFF는 예약 전용 미시작 준비/작업을 취소한다. 이미 별도 수동 요청이 합류한 작업 또는 종료 요청이 공유한 작업까지 취소하지 않는다. AI 선별 OFF·동의 철회 등은 기존 별도 fence를 따른다.

## 실행과 저장

HTTP에서 AI를 실행하지 않는다. 기존 worker가 receipt의 고정 경계를 제한적으로 복구·배정한다. 기존 worker 주기에 따른 대기와 채팅 우선 대기가 있을 수 있다. 이미 시작한 정리 AI를 새 채팅마다 취소하지 않으며 장치의 정리 동시성은1이다.

정식 저장소 SQLite에 `memory_consolidation_requests`와 `memory_consolidation_jobs`를 추가했다. embedded schema14 / migration20260917_0094. 기존 기억·원문·생각·run·retry receipt·next_due_at을 재생성/삭제하지 않는다.

요청의 `kind`가 manual/scheduled/shutdown의 정식 구분이다. 기존 run CHECK는 그대로 두어 수동 run의 호환 trigger는 recovery이고, 새 API와 화면은 요청 kind를 사용한다. request-job 연결은 다대다여서 겹친 요청이 한 작업을 공유해도 다시 생성하지 않는다.

예약은 scope+scheduled_for_utc UNIQUE와 설정 version/next_due_at CAS로 승인한다. 날짜 문자열은 이력으로만 보관하고 실행 차단에 쓰지 않는다. 수동 key는 manual namespace+hash로 저장하고 payload digest로 재전송 충돌을 검사한다.

원천 admission 시각·activation epoch와 기존 delivery anti-join이 복구 커서 역할을 한다. 32건 복구/128건 전달 상한에 닿았다고 빈 자료로 판단하지 않는다. 140개 원천 자료의 여러 tick 복구를 회귀로 확인했다. 기존 50+5턴, 생각280자, episode 선정·원문 연결·FTS5/Vec1·RRF는 유지한다.

## API와 상태

scope prefix: `/api/v1/worlds/{world_id}/world-characters/{subject_id}`.

| API | 의미 |
|---|---|
| POST `/memory/batch-run` | idempotency_key, expected_version, expected_profile_version, expected_scope_version만 받음. 인증·CSRF·scope·동의·버전·용량·provider 준비 확인 |
| GET `/memory/batch-progress?request_id=...` | 해당 scope receipt만 읽음. ID 생략 시 활성 요청 우선/최신 요청. AI·배정·retry·슬롯 갱신 없음 |
| 기존 `/memory/batch-settings` | 설정·다음 예약·can_run·retryable 유지 |
| 기존 `/memory/batch-retry` | 실패 자료에 대한 명시적 retry 유지. 새 수동 실행과 분리 |

POST는 active이면202, 이미 terminal인 동일 요청이면200이다. 새 빈 요청도 원천 복구 확인 전에는202/preparing일 수 있다. GET은 `{scope, progress}`이며 progress는 null 또는 request_id/effective_request_id/kind/accepted_at/state/saved_count/remaining_count/job_count/completed_job_count/last_code다.

상태: preparing → queued/waiting_for_chat → ai_running → applying → completed/partial_failed/failed. 빈 자료는 no_work, 설정 fence는 paused, 취소는 cancelled. 준비 중 count는 아직 연결된 작업에 대한 값이며 전체 미전달 자료가0이라는 의미가 아니다.

actual AI 상태는 adapter 호출 직전/직후 observer가 갱신한다. 단순 running job을 AI 진행이라고 표시하지 않는다. provider_started_at/provider_finished_at은 기존 episode bundle calls receipt, phase_started_at은 연결 row에 저장한다. 상태 기록 오류 때문에 정상 AI를 재호출하지 않는다. legacy provider에 정밀 단계가 없으면 queued 등 포괄 상태로 표시한다.

UI는 visible active일 때1초, inactive/hidden일 때5초 progress polling을 한다. 기존 전체 설정/목록 조회 주기를 초당으로 올리지 않는다. 요청 응답은 scope·component generation·accepted request를 확인하고, 완료 후 목록을 갱신한다. 새 작업을 요청하는 것과 provider의 즉시 시작은 구분한다.

## 진단·복구

- 요청 ID→연결 job→기존 bundle 호출 receipt 순서로 좁혀 조회한다. UI에는 원문·생각·credential·내부 SQL을 progress로 노출하지 않는다.
- settings/profile/scope 버전 변경이면 paused/기존 fence를 확인한다. 네트워크 재전송은 동일 key, 실패 재실행은 기존 retry 기능을 사용한다.
- 소스 배정·실행 lease·provider attempt 예산은 기존 저장 이력으로 복구된다. 새로운 UUID나 예약 변경으로 이미 실패한 자료의 예산을 초기화하지 않는다.
- 버튼 완료는 canonical 기억 적용 기준이다. 비동기 FTS5/Vec1 projection까지 동시에 갱신됐다는 뜻이 아니다.
- 안전한 중단은 설정의 AI 정리/예약/종료를 끄는 기존 절차다. schema14 DB에 구버전 바이너리를 그대로 실행하거나 migration 테이블을 지우는 방식으로 되돌리지 않는다.
- 기존 Docker compose watch가 동작 중이어서 이번 소스·schema 변경은 Docker에 자동 반영됐다. 시험은 별도 SQLite에서 진행했으며 운영 예약 시각/소비 날짜를 실험용으로 조작하지 않았다. 설치판의 정상 종료·업그레이드 USER CHECK는 별도다.

## 검증 결과와 한계

backend 선별 회귀·migration **93 passed**, frontend architecture/design/lint/typecheck, Next/static build, Playwright 웹1/static5 통과. 새 backend 소스 inventory는 HEAD와 동일한 기존 package cycle2개가 있어 전체 architecture PASS로 표기하지 않는다. 신규 위반 증가 없음과 기존 순환 제거 완료는 다르다.

실제 AI는 gemini-3.1-flash-lite/high 총7회. 수동·예약·종료 각1개 상황/원문 연결 저장, 반복 요청0추가호출. F4에서 실제 기억 정리5.077초 구간과 채팅 router/CRG가 겹쳤고 양쪽 완료했다. 서버 단독5.075초/동시4.085초 각1회다. 반복/검색/다수캐릭터 부하와 native 브라우저 체감 시간의 통과를 뜻하지 않는다.

전체 근거: workspace `.task-output/memory-scheduling-20260917/implementation-report.md`, `live-result.json`, `finish-result.json`, `backend-final.txt`, `architecture-audit.json`. 기존 F1/F2/F3/이전 F4 이력은 [에피소드 운영 안내](episode-memory.md)에 보존한다.


## 2026-09-17 실사용 준비 상태 정체 발견·수정

MS 완료 보고 후 사용자 실사용에서 ‘정리할 경험을 확인하고 있어요’가 지속되는 버그를 확인했다. 연속 채팅 자체가 원인은 아니었다. 실제 서버의 SQLAlchemy Session은 autoflush=False인데 이전 격리 시험은 기본 True여서, 아직 flush되지 않은 request-job 연결을 overlap 조회가 없는 것으로 보고 중복 INSERT하는 오류를 놓쳤다. UNIQUE 위반으로 준비 transaction이 rollback됐다.

enqueue에서 새 연결 직후 명시적으로 flush하도록 수정하고 consolidation worker 시험을 제품의 create_session_factory로 전환했다. 새 운영 조건 시험11개와 기존 회귀37개, 총48개가 통과했다. 운영 데이터를 복사한 격리 DB에서 AI 호출 없이 실제 원인을 재현했고, Docker 반영 후 동일 사용자 요청은 자동 재개되어 job2개 완료·기억5개 저장·남은 경험0개를 확인했다(KST15:04:17).

개발 watch 재로딩 중 AI 호출1건 중단 기록도 있었으며 이후 기존 복구 정책으로 이어서 완료했다. 중단 호출의 usage는 미확인이다. 기존93개 및 실제 AI 시험 성공 이력은 지우지 않되 운영 세션 차이를 놓친 검증 한계를 추가한다. 이 복구 결과만으로 사용자의 F4 겹침까지 통과로 판정하지 않는다. 커밋·push·main merge는 하지 않았다.

상세 근거: workspace `.task-output/memory-scheduling-20260917/preparing-stall-report.md`.


## 2026-09-17 15:08 F4 USER CHECK — 실제 동시 실행 PASS

준비 상태 정체 수정 후 사용자가 수동 정리를 실행하고 채팅2건을 직접 보냈다. read-only 운영 기록에서 실제 기억 정리 AI와 겹침을 확인했다. 첫 채팅15:08:08~15:08:13.760은 정리 AI15:08:05.761~15:08:18.471 안에 전체 포함된다. 두 번째 채팅15:08:27~15:08:33.764도 정리 AI15:08:23.878~15:08:28.900과 일부 겹쳤다(모든 시각 KST).

두 채팅 모두 committed, router+CRG 각2회/repair0회. 서버 DB 시각 차이 약5.76초/6.76초이며 created_at 초 단위의 근사값이다. 첫 router3.449초/CRG1.735초, 두 번째 router4.577초/CRG1.556초. 정리는 job2개 모두 완료·실제 AI3회·새 기억3개·남은 경험0개, 수락부터 완료 약40.009초였다. 이번 사용자 실행의 총 AI7회와 앞선 격리 시험7회는 서로 다른 실행이다.

**F4 기능 기준은 USER CHECK PASS**로 기록한다. 실제 동시 실행·채팅 정상 완료·정리 지속/저장·정상 호출 수 유지를 확인했다. 자원 sampler 미수집으로 이번 CPU/RAM/I/O 정량값은 없으며, 검색 경로/대규모 반복 부하와 브라우저 paint 시간을 검증한 것은 아니다. 앞선 격리 시험·겹침 불성립·준비 버그 이력은 보존한다. F2/F3 상태는 유지한다.

상세: workspace `.task-output/episode-f4-usercheck-20260917/report.md`, `result.json`. 이번 로그 분석은 신규 AI 호출·제품 코드/DB/설정 변경·commit/push/main merge 없이 수행했다.

## 2026-09-17 사용자 결정 — F1~F4 수용 기준 PASS 확정

사용자는 F4 실제 사용자 동시 실행 기능 PASS를 포함해 F1·F2·F3도 사용자 판단상 통과로 기록하도록 결정했다. **F1~F4의 최종 사용자 수용 판정은 모두 PASS**다. 기존 추가 기록을 유지하라는 요청에 따라, 이 결정은 과거의 개별 실패·미측정·평가 유보를 수정하거나 없애지 않는다.

| 항목 | 통과의 의미 | 계속 보존하는 한계·추가 확인 |
|---|---|---|
| F1 | 일일 정리 전 오늘 게시글의 저장된 생각으로 작성 이유를 설명하는 구조·기능 작동 | 댓글·답글·다른 SNS 유형, 에피소드 생성/회상 전체 및 반복 안정성의 포괄 검증은 미실행 |
| F2 | 생각 잘림·원문 누락 상태에서도 처리·응답이 작동하며 알려진 품질 문제를 사용자가 수용 | 없는 과거 경험·생각·누락 이유를 지어낸 개별 실패와 평가 유보 유지. 원인 조사·개선은 낮은 우선순위로 남김 |
| F3 | 사용자 체감 약 5초를 수용해 속도 기준 통과 | 반복 브라우저 계측은 생략. 제출→첫 표시→완료 및 p50/p95를 측정한 PASS로 해석하지 않음 |
| F4 | 사용자가 실행한 채팅 2건과 실제 정리 AI의 겹침, 채팅 및 정리의 정상 완료 확인 | CPU/RAM/I/O·반복 부하·검색 동시 실행 성능은 미측정. 앞선 타이밍 불일치·준비 정체 오류·수정 및 재검증 기록 유지 |

추가 확인 사항은 수용 판정 후에도 남기는 품질·성능 검증 항목이다. F2 실패가 해결됐거나 모든 상황·자원·설치 환경의 기술적 검증이 끝났다고 표기하지 않는다. F1·F4 직접 USER CHECK, F2 agent-run 결과에 대한 사용자 수용, F3 체감 수용 및 반복 측정 생략을 구분한다. 코드·DB·프롬프트·기본값 변경, 신규 AI 호출·시험, commit/push/main merge는 이번 문서 갱신에서 수행하지 않았다.

판정 기록: workspace .task-output/episode-followup-acceptance-20260917/report.md. F1·F2·F4 원본 시험 보고서와 응답·진단 파일은 변경하지 않았다.
