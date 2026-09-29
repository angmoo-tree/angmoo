# SNS V2 Routine 출력 계약과 원본 게시글 발행

2026-09-29 구현 기준. SNS 계약 `2`의 호출 순서는 **통합 대상 선택 → Inbox → Feed → Routine**이며 정상 Routine은 판단과 작성을 한 번에 수행한다. 이 문서는 출력 계약·상태 버전·재개와 발행의 책임을 설명한다. 실제 운영 서버 적용과 자연 관찰은 별도 확인 대상이다.

## 선택과 버전

`ROUTINE_OUTPUT_POLICY=enum_preserved_v1`은 신규 `personalized_graph_v2` / SNS 계약 `2` / `thought_v1` 실행에서 `routine-output.enum-preserved.v1`과 상태 스키마 `2`를 선택한다. 기존 경로나 `legacy` 정책은 `routine-output.legacy.v1` / 상태 `1`을 사용한다.

활동을 만들 때 `ActivityGraphRun.result.routine_policy`에 출력·상태·생각 정책을 저장한다. 자식 identity, prepared checkpoint와 최종 beat도 이 정책을 따른다. 버전 없는 옛 run은 옛 계약이며 환경 기본값으로 새 계약에 끼워 맞추지 않는다.

| 책임 | 소유 위치 |
| --- | --- |
| 공유 정책 값, 버전 일관성 | `backend/app/contracts/routine_output.py` |
| 새 wire DTO와 서버 결합 DTO | `domains/routine_posts/schemas.py` |
| 허용 enum·범위·업무 검증, 고정 문맥 | `domains/routine_posts/service/evidence.py`, `contracts/request_context.py` |
| 영속 run과 engine 선택 | `domains/world_characters/service/activity_engines.py` |
| 실제 호출·복구·재개 | `runtime/autonomous_activity/routine.py`, `combined_lanes.py`, `routine_resume.py` |
| claim·상태 전환·일과 생명주기 | `domains/routines/service/execution/`, `policies/activity_state.py` |
| 성공 답글 조회와 원본 글 발행 | `runtime/routine_posts/original_post.py`, `sqlalchemy_runtime.py` |

## 한 번의 정상 호출

```text
현재 일과·이전 Routine 원본 장면·페르소나·현지 시각
+ 관련 기억·관계·이미 완료된 Inbox/Feed 행동
       ↓
서버가 요청 identity·사건 순서·상태/plan version·원문 fingerprint 고정
       ↓
AI: decision + draft(title/body/topic_signature/novelty_basis/thought)
       ↓
남은 enum·범위·교차 검증 + 고정 요청 문맥 결합
       ↓
실제 성공 답글과 제목·본문 완전 복제 검사
       ↓
실행권·원천 재검증 → 기존 원자 발행 → 상태·생각·기억 후속 소비
```

AI는 `scene_kind`, `scene_brief`, `continuity_facts`, `used_source_event_ids`, `used_detail_keys`, `source_event_effects`와 기존 공통 기분/관계 제안을 반환한다. 서버가 이미 아는 `episode_id`, `beat_id`, `sequence_no`, `considered_source_event_ids`는 wire 출력에서 빼고 같은 요청의 문맥으로 결합한다.

사건 ID와 continuity/detail 토큰의 enum은 유지한다. 첫 장면 `start`, 이후 `continue/conclude`, 필수 연속성, 사건 수에 따른 배열 상한, 중복·used 밖 효과 거부도 유지한다. considered는 실제 전달 목록, used는 AI가 고른 실제 목록으로 각각 저장한다. 모든 considered 사건의 기존 claim/consumption 규칙을 임의로 used만 처리하는 규칙으로 바꾸지 않는다.

새 출력에서 옛 `motivation_*`, `emotion_*` 다섯 선언과 사건의 `effect/intensity` 분류는 요청하지 않는다. 사건 효과에는 유효한 `source_event_id`와 남은 `state_change`만 있다. 최종 글에 연결된 `thought`와 현재 공통 `state_update`는 유지한다.

## 에너지가 없는 상태

상태 `2`는 `mood`, `mood_intensity`, `action_note`만 갖는다. `energy/social_energy` 및 변화량을 새 입력·출력·계산·초기화에 넣지 않는다. 예전 두 값을 0이나 50으로 다시 만드는 호환 처리는 없다. 남은 강도 범위·사건별/beat별 변화 상한·감쇠·공통 상태 우선 규칙은 유지한다.

일반 계획·날짜별 계획·공동 일과·예약은 버전별 factory로 episode를 만든다. 상태 `1` episode의 새로운 beat를 상태 `2`로 시작할 때 미완료 beat가 없는지 확인한 뒤 episode version 조건부 UPDATE와 새 beat 저장을 같은 transaction에서 수행한다. 과거 beat와 결과 snapshot은 고치지 않는다. 미완료 옛 beat, 경쟁 전환 또는 맞지 않는 상태 버전은 명시적인 conflict로 처리한다.

`ActivityBeat.state_schema_version`을 정상 migration으로 추가했다. embedded SQLite는 `23→24`, Alembic은 `20260929_0102`다. 기존 행은 `1`로 표시하며, 새 스키마 기준과 업그레이드 결과가 같은지 및 기존 컬럼 값이 보존되는지 검증한다. 과거 manifest는 변경하지 않는다.

## 답글 완전 복제와 Writer 수정

이전 Routine 원본은 이어갈 장면이다. 같은 활동에서 이미 발행한 Inbox/Feed 답글은 완료한 상호작용 기록이다. 둘의 역할을 공통 지침으로 구분하여 combined, split, 복구 Writer 모두에 전달한다. 최근 글이나 기억을 숨기는 방식으로 해결하지 않는다.

비교는 같은 canonical 활동 ID·World·actor의 **성공** reply 영수증과 실제 Post를 사용한다. 최근 12건 목록에 포함됐는지는 발행 검증의 기준이 아니다. LF 줄바꿈과 양끝 공백만 정규화하고 제목과 본문이 모두 같을 때 `routine_reuses_published_reply`로 거부한다. `Re:` 단어, 제목만 같음, 본문만 같음 또는 단순 유사성으로 정상 글을 막지 않는다.

유효한 decision은 유지하고 Writer 수정만 최대 1회 허용한다. 기존 영속 `RecoveryLedger`를 예약하며 재시작으로 예산을 초기화하지 않는다. 복구 글도 검사한다. 복구 불가·실행권 상실·원천 변경이면 Routine을 실패로 끝내고 성공한 Inbox/Feed를 보존한다. 성공 Routine 재개는 성공 영수증을 먼저 재사용하며 글이나 AI 호출을 반복하지 않는다.

이 검사는 완전 복제를 확실하게 막는다. 의미만 비슷한 재작성·환각·모든 시간 표현을 판정하는 검사는 아니다. 별도 AI 검사 호출을 추가하지 않는다.

## 후속 소비와 제거 경계

일과 API와 frontend는 이미 상태 버전 및 범용 snapshot DTO를 사용한다. 새 에너지 표시나 가짜 기본값을 추가하지 않는다. 최종 원본 글·SocialEvent·thought·성공 beat는 기존 Memory/Chat 원천 읽기에서 사용한다. 관계의 방향·scope, source revision·접근권한과 기억 검색 경로는 유지한다.

옛 `RoutineBeatPlan`, 상태 `1` validator, 구 생각/선언 reader, 구 engine·split·복구 및 migration을 이번에 파일째 삭제하지 않는다. 옛 pending/checkpoint·지원 설정이 종료되고 공용 저장·claim과 구 자료 reader가 분리돼 유지된다는 증거가 있어야 추가 제거할 수 있다.

`ROUTINE_OUTPUT_POLICY=legacy`는 **새 시작의 정책 선택**을 바꾸는 수단이다. 이미 저장한 상태 `2`와 새 checkpoint를 역변환하지 않는다. 새 데이터가 없는 옛 바이너리로 데이터 경로를 열지 않는다. 상태 `2` episode를 옛 계약으로 새로 실행하려 하면 Routine은 conflict로 대기하며, 이미 저장된 새 실행의 재개 지원은 유지한다.

## 검증 자료

합성 회귀는 `backend/tests/routine_posts/test_output_contract_v2.py`에 있다. 남은 enum/배열 상한, 제거 필드 거부, 상태 이력, file-backed SQLite 경쟁, 고정 원문 변경 거부, combined/split 제한 수정·멱등성, 12건을 넘는 답글 조회와 새 글/생각의 Memory 읽기를 검사한다.

선택 실행 스크립트 `backend/scripts/evaluate_routine_output_contract.py`는 격리된 합성 입력으로 동일 모델의 단계별 스키마를 비교한다. credential DB를 읽기 전용으로 열며 운영 게시글·관계·기억에 쓰지 않는다. 영속 원장으로 물리 요청 60회와 복구 배분 12회를 제한한다. 실제 전환 판정·비용·내용 한계는 workspace의 날짜별 실행 기록에서 확인한다.
