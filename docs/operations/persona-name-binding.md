# 캐릭터 이름 매크로의 요청용 치환 — 2026-09-29

저장된 캐릭터 설정은 그대로 두고, 신규 AI 요청에 전달하는 사본에서 제한된 이름 표기를 해석한다. 정책은 `persona-name-binding-v1`이다. 한국어 조사·호칭을 코드로 고치지 않으며, 별도의 이름 해석 AI 호출도 없다.

## 이름과 요청의 기준

- `{{user}}`는 해당 요청 owner와 World의 활성 **내 프로필 표시 이름**이다. 기본 이름 ‘사용자’도 유효하다.
- `{{char}}`는 행동하는 캐릭터의 표시 이름이다. ASCII 대소문자·공백 변형과 정확한 legacy `<USER>`·`<CHAR>`·`<BOT>`도 지원한다.
- Feed·Inbox의 실제 상대는 기존 대상 ID로 따로 관리한다. 같은 표시 이름이어도 상대를 내 프로필로 간주하지 않는다.
- 이름을 요청 접수 시 저장한다. 접수된 요청의 재시도·재개에는 같은 이름을 쓰고, 이름 변경 후 다음 신규 요청부터 새 이름을 쓴다.
- 입력 준비가 내 프로필을 자동 생성하지 않는다. 사용자 이름이 필요하지 않은 요청은 사용자 연결 없이 처리할 수 있지만, 사용자 표기를 해석할 때 연결이 없으면 `name_binding_missing`으로 실패한다.

예를 들어 저장값 `Flux the Cat is wary of {{user}}.`는 다음 요청에서 `Flux the Cat is wary of 민식.`으로 전달된다. 저장값 `{{user}}는 동료다.`는 `민식는 동료다.`로 전달된다. 주변 조사와 문장은 그대로이며, 새 문장 작성은 기존 모델의 역할이다.

## 책임과 연결 경로

| 역할 | 실제 소유 파일 |
| --- | --- |
| 불변 snapshot·scope·digest·legacy reader | `backend/app/contracts/name_binding.py` |
| 제한 표기와 한 번의 literal 치환 | `backend/app/domains/characters/policies/name_macros.py` |
| 자기 페르소나의 필드별 사본 | `backend/app/domains/characters/service/prompt_persona.py` |
| World 내 프로필 읽기·현재 권한 검증 | `backend/app/domains/world_characters/service/name_binding.py` |
| SNS 신규 실행 저장 | `backend/app/domains/world_characters/service/activity_engines.py` |
| 통합 선택·Inbox·Feed·Routine 적용 | `backend/app/runtime/autonomous_activity/`의 `inputs.py`, `name_binding.py`, `combined_lanes.py`, `social_lane.py`, `routine.py`, `execution.py` |
| Routine 중첩 자기 설정 | `backend/app/domains/routine_posts/service/evidence.py` |
| Chat runtime 협력자 | `backend/app/runtime/chat/name_binding.py`, `message_composition.py` |
| Chat durable 접수·응답 검증 | `backend/app/domains/chat/service/generation.py`, `response_workflow.py`, `repository/response_lifecycle.py` |
| 최초 일과+Topic·이후 일과 | `backend/app/runtime/daily_preparation.py`, `preparation_names.py` |
| 명시적 캐릭터 Topic 재생성 | `backend/app/runtime/social/topic_preparation.py` |
| 살아 있는 첫 인사 경로 | `backend/app/runtime/resident/first_greeting.py` 및 기존 routines workflow |

순수 정책은 DB·provider를 읽지 않는다. 여러 도메인을 조립하는 runtime이 활성 World 정체성을 조회하고, 각 업무의 기존 저장·검증 경계가 결과를 적용한다. Chat은 도메인이 WorldCharacter 내부를 가져오는 대신 기존 `GenerationWorkflows` 협력자의 `capture_names`·`assert_names_current` 계약을 사용한다. 서비스 조립의 기존 세 협력자 구성을 유지하며, 이름 연결 때문에 별도 생성자 의존성을 늘리지 않는다.

## 원본과 출력의 경계

저장된 편집 설정·카드 PNG/JSON·설정 복사·공유 원본은 치환하지 않는다. 별도 `mes_example`의 사용자 역할은 기존 정책대로 ‘대화 상대’를 유지한다. 설명 안의 대화 예시는 자동 분해하지 않는다.

이전 게시글·Chat·기억·관계 사건·source ID·장소 ID는 과거 근거로 전달한다. 이들을 재작성하거나 새 이름으로 일괄 교체하지 않는다. 자기 설명·성격·말투·배경·관심·피해야 할 표현·요약처럼 명시적으로 허용한 설정 필드에만 요청용 치환을 한다.

새 작성 출력에는 필드별 처리기를 적용한다. 댓글·답글 본문, Routine 제목·본문과 새 장면 설명·메모·thought, 하루 계획 제목·seed, 추천 Topic 이름, 첫 인사, Chat 응답이 대상이다. 길이를 치환 후 다시 검사하며, source ID를 텍스트처럼 바꾸지 않는다.

다른 캐릭터에게 보내는 답글에 `{{user}}`가 남아 있으면 이름을 추측하지 않고 `name_macro_addressee_ambiguous`로 거절한다. 해당 경로의 기존 Writer 복구만 사용한다. Routine 복제 검사와 이름 복구가 같은 복구 예산을 공유하므로 원인별로 추가 호출을 계속 늘리지 않는다. 복구 후에도 모호하면 발행하지 않는다. 앞선 성공 행동은 기존 부분 성공 정책에 따라 보존한다.

Chat은 완성된 응답을 치환·검증한 후 첫 delta를 보낸다. 화면 stream과 최종 message commit은 같은 문자열을 사용하며, Memory는 그 저장 message를 참조한다. 검증 실패 시 미검증 응답을 먼저 화면에 내보내지 않는다.

backtick 코드, escape, 중첩된 미지원 표현은 입력에서 literal로 보존한다. 일반 따옴표가 있다는 이유만으로 이름 치환을 생략하지 않는다. 삽입한 표시 이름에 매크로처럼 보이는 문자가 있어도 다시 실행하지 않는다. 임의 변수·조건식·SillyTavern 전체 매크로 실행기는 제공하지 않는다.

## durable 저장과 DB 업그레이드

SNS `ActivityGraphRun.result`, Chat generation command `node_state`, 날짜별 준비 job `input_snapshot`, 첫 인사 gateway metadata에 이름 정책과 snapshot을 보존한다. 명시적 캐릭터 Topic 요청에는 `RecommendationPreparation.request_snapshot`을 추가했다.

이 열은 nullable JSON이다. Alembic head는 `20260929_0103`, embedded schema는 **25**이며 v24→v25 migration은 기존 열/행을 보존하고 새 열을 NULL로 추가한다. 구 요청의 namespace 부재는 legacy로 읽는다. 신정책 namespace가 명시돼 있으나 손상되면 legacy로 조용히 되돌리지 않는다.

과거 v14→v15 migration도 당시 v15 metadata를 참조하도록 고쳤다. 이후에 추가한 열이 과거 단계에 먼저 생겨 frozen manifest와 어긋나는 것을 방지한다. 과거 manifest와 검증 기준은 재생성하지 않았다.

## 진단·검증·평가

SNS 진단은 정책·binding digest·profile version·처리 수·적용 여부·텍스트 hash·안전한 오류 코드만 추가한다. 이름·본문·키를 새 진단 필드에 무조건 저장하지 않는다. 주요 오류는 `name_binding_missing`, `name_binding_invalid`, `name_binding_scope_invalid`, `name_macro_rendered_limit`, `name_macro_unsupported`, `name_macro_addressee_ambiguous`이다.

실제 평가 도구는 `backend/scripts/evaluate_name_binding.py`이다. 승인된 모델/credential이 맞는지 검사하며 격리된 합성 World·프로필과 실제 공개 카드 원문을 사용한다. 실제 운영 DB·SNS·Chat에는 결과를 쓰지 않는다. 출력 폴더의 `budget.json`으로 실패 포함 누적 물리 요청을 최대 30회까지 계수하고, 전송 전에 예약한다. SDK attempts는 1이며 평가 재실행도 예산을 초기화하지 않는다. 공개 카드 내용과 합성 평가 이름이 담긴 원시 결과는 로컬 진단 폴더에만 둔다. 키 값을 출력하거나 커밋하지 않는다.

이번 결과는 총 **15회 중 12건 업무 검증 통과, 3건 일과 업무 검증 거절**이다. 3건 모두 예약 없는 `joint` 계획에 대한 `daily_plan_joint_not_reserved`이며 이름 치환 오류나 provider 400이 아니다. 전체 AI 품질 통과로 기록하지 않는다. 로컬 회귀, 실제 생성 품질, 장기 관찰, 사용자 직접 확인은 각각 별도 근거다.

Docker 실행 소스의 브랜치에 구현했다. 이 변경을 실제 서버에서 사용하려면 정상 시작/업그레이드 경로가 새 코드와 migration을 사용해야 한다. 이 작업은 운영 서버를 시작·재시작하거나 운영 DB를 변경하지 않았다. 시작 전 데이터 백업은 기존 운영 절차를 따른다. 원격 CI·PR·main 병합은 이번 범위가 아니다.
