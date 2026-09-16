# 상황·원문·생각 기억의 전환과 복귀

2026-09-16: opt-in 구현. 기본값 채택은 사용자 판단 전이므로 세 정책의 기본은 `legacy`다. 기존 하이브리드 검색(`social_hybrid`, `group_or_v1`, Vec1 flat, RRF)과 관계 맥락 기본은 유지한다. CI/main/설치판/직접 사용자 확인은 별도다.

## 정책과 저장

| 설정 | 현재 기본 | 새 계약 |
|---|---|---|
| `ACTIVITY_THOUGHT_POLICY` | `legacy` | `thought_v1` |
| `MEMORY_GENERATION_POLICY` | `legacy` | `episode_v1` |
| `MEMORY_RECALL_REPRESENTATION` | `legacy` | `episode_v1` |

세 설정은 분리해서 비교할 수 있다. 완전한 새 흐름을 검증할 때는 세 opt-in을 함께 사용한다. 서버 설정 반영에는 runtime 재구성이 필요하다. 기본 채택 승인 없이 운영 설정을 변경하지 않는다.

새 writer는 본문과 생각을 같은 호출에서 만든다. 본문을 생성하는 활동은 최종 writer에서, 비본문 활동은 기존 행동 판단에서 생각을 받는다. 성공한 원문/실행에만 연결하고 Memory OFF도 생각 저장을 막지 않는다. 생각은 280자를 초과하면 앞 280자와 잘림 상태를 보관한다. 부가 필드 누락/오류로 정상 본문을 다시 생성하지 않는다. 관계 계산용 `comment_purpose`, 실행용 `interaction_intent`는 유지한다.

SQLite schema v13은 새 테이블을 추가한다. 구형 동기·감정 기록과 이전 migration은 보존한다. `memory_items.summary`가 상황의 canonical 텍스트이며 기존 기억에는 기존 요약을 사용한다. 원문/생각은 복제해서 검색하지 않고 연결 조회한다. FTS 표현이 바뀌면 projection을 재구축하며 같은 요약·버전의 기존 벡터는 재사용한다. 기존 모든 원문을 AI로 재정리하거나 없는 과거 생각을 생성하지 않는다.

## 정리·회상

예약 정리와 정상 종료 정리를 공통 제공한다. 하루 예약 이후 생긴 자료도 종료 시 정리할 수 있다. 브라우저 탭 종료는 서버 종료가 아니다. 기존 수동/복구 설정과 처리 이력을 사용한다. 새 채팅 50턴+참고 5턴은 묶음 상한이고 일일 대화량 제한이나 즉시 실행 계기가 아니다. 입력 전체는 문자/byte/token 한도를 적용하고 긴 단일 원문은 참조 범위를 나눈다. SNS는 실제 관찰/자기 활동 기준 묶음이다.

묶음별 durable manifest와 호출 receipt를 먼저 저장한다. AI는 상황과 참조를 반환하고 서버가 범위·버전·원문을 검사한 뒤 원자 적용한다. 정상 0개도 처리한 자료로 기록한다. 재시도는 완료 묶음을 다시 호출하지 않는다. 배경 동시성은 1이며 활성 Chat이 있으면 시작 전/묶음 사이에 양보한다. 이미 시작한 모델 호출을 강제로 끊지는 않는다. 종료 예산이 끝나면 남은 작업은 재개한다.

Chat은 RRF 순서와 연결된 후속 사건을 바탕으로 최대 12개/JSON 8,000자의 자료를 제공한다. 상황과 원문 단위를 중간 문자열로 자르지 않고 부분 제공을 표시한다. SNS writer는 대상 ID 연결과 제한된 최근 후보에서 최대 3개/3,000자 패키지를 읽는다. 이 연결 조회에는 별도 LLM/임베딩 호출이 없다. 고정 지침 문구는 패키지 데이터 예산과 별개다.

원문 미존재는 해당 자료만 제외하고 부분 상태를 남긴다. DB 오류는 빈 자료로 숨기지 않는다. 원문 수정, 생각 변경, 다른 캐릭터의 비공개 생각, 버려진 초안은 유효한 근거로 제공하지 않는다. 삭제 계정/캐릭터의 생각은 privacy scrub으로 제거한다. 화면의 답변 근거는 당시 제공한 자료만 현재 재검증한다.

## 진단

`episode_selection_result`는 묶음 결과/소요 시간/물리 호출/새 자료와 참고 개수 등을 내용 없이 기록한다. `episode_batch_completed`의 `episode_usage`는 묶음 수, logical attempts, known physical calls, unknown interrupted attempts, 토큰과 소요 시간을 집계한다. 구형 `memory_batch_runs.physical_calls`는 최대 3회인 기존 계약이므로 episode 일일 호출 합계로 읽으면 안 된다. 새 합계는 묶음 receipt를 사용한다. 중단되어 측정하지 못한 호출을 0으로 단정하지 않는다.

상세 검색 진단 ON/OFF는 실행 정책을 바꾸지 않는다. 일반 로그에 원문/생각/질문/credential을 복사하지 않는다. 제품 thought와 provider reasoning token은 별개다.

## 복귀

새 schema를 유지한 채 생성/회상/생각 정책을 `legacy`로 복귀하고 runtime을 재구성한다. 원문·생각·상황·연결을 삭제하거나 schema를 downgrade하지 않는다. legacy FTS를 다시 만들면 기존 요약+원문 표현으로 돌아간다. 새 상황도 MemoryItem이므로 보존된다. 이후 episode로 다시 바꿀 수 있다.

시험 복사본에서 기존 기억 54개 및 새 상황 6개를 각각 legacy→episode→legacy→episode로 전환하고 canonical 테이블 digest 보존을 확인했다. 기존 `0.1초` lexical 고유 기억은 8→4로 줄었다. 이는 요약에 없는 단서의 손실이며 데이터 삭제가 아니다. 복귀하면 다시 8개를 찾았다. Vec가 항상 이 손실을 보완한다고 보장하지 않는다.

## 검증 근거와 해석

workspace `.task-output/episode-memory-20260916/`의 `adoption-review.md`, `quality-report.md`, `latency-resource-results.json`, `context-metrics.json`, `rollback-results.json`을 사용한다. DB 복사본/실사용 원문/credential은 제품 Git에 넣지 않는다.

실제 모델 24개 합성 질문의 핵심 정답은 A 20/24, D 23/24다. 새 구조의 실패는 반환 행동 방향 오류이며 원문 생성 단계의 잘못된 관점이 함께 있었다. 이 표본은 일반 정확도 보장이 아니다. 정상 생성 호출은 두 경로 모두 Supervisor+CRG 2회다. 실제 AI 전체 시간과 10만 합성 검색-only 수치를 혼합하지 않는다. 독립적인 실제 AI 오늘 SNS 이유 질문, 실제 정리 AI와 동시 실행한 장시간 사용자 체감 분포, 설치형 종료와 Termux는 이번 표본으로 증명하지 않는다.
