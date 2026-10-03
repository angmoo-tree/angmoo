# 다국어·시간대·Gemini SNS 통합 소유 경계

기준 계획은 workspace의 `10-03 Angmoo 다국어·사용자 시간대와 Gemini SNS 스키마·누락 복구 통합 코드 구현·검증 세부 계획.md`다. 기준 커밋은 `8f4e92b9201284e7777b0927f0d1bc649a6e049b`, 작업 브랜치는 `feat/0.1.0-release-readiness`, 이슈는 [#360](https://github.com/angmoo-tree/angmoo/issues/360)이다. 이 문서는 코드 소유와 검증 경로를 설명한다. 실제 모델 품질, 사용자 Docker 적용, Windows 설치판 확인을 증명하는 문서가 아니다.

## 환경·시간·입력의 소유

| 경계 | 소유 코드 | 보존 계약과 검증 |
| --- | --- | --- |
| 인증과 감지 보고 | `domains/identity/service/environment.py`, `schemas_environment.py`, `models_environment.py` | 실제 설치 owner만 조회·보고. 첫 정상 client의 session/lease, sequence, expected revision을 검사한다. 잘못된 감지는 마지막 정상값을 지우지 않는다. `tests/identity/test_local_environment.py`와 실제 SQLite 브라우저 검증을 사용한다. |
| 명시 UI 선택 | `domains/identity/models.py`, Identity 사용자 갱신 경로 | `ui_language=ko/en`과 revision은 감지 locale/zone과 별개다. 부분 PATCH는 다른 개인정보를 덮지 않는다. 표시 버튼은 두 모드 모두 Korean/English다. |
| 화면 lifecycle | `composition/providers/user-environment-provider.tsx`, `features/identity/api/environment.ts` | 인증·backend/session scope에 맞게 상태를 나누고, 활성 화면의 초기/복귀/주기 감지만 보고한다. 409에는 canonical 상태를 다시 읽는다. abort/late response, 로그아웃, backend 변경을 처리한다. |
| 공통 snapshot | `contracts/environment.py`, `domains/identity/service/environment.py` 및 각 admission owner | 이미 admitted된 SNS/Chat/기억 작업은 locale/zone/revision을 고정한다. UI 선택은 실행 snapshot을 바꾸지 않는다. 자동 캐릭터의 nullable `owner_user_id` 대신 실제 Character binding owner를 사용한다. |
| 현지 달력 | `core/calendar.py`, `core/time_meaning.py` | UTC 순간과 현지 날짜를 분리한다. day/month의 양쪽 경계를 따로 환산하며 DST gap/overlap을 명시적으로 처리한다. 저장된 event 순간은 그대로다. |
| 미래 일정 | `domains/routines/service/environment_schedule.py` | 일정 claim transaction에서 작은 batch만 조정한다. 진행·잠금·cooldown은 보호하며 새 미래 idle 일정만 새 revision으로 이동한다. |
| 한도·예약 | `core/calendar_ledger.py`, `core/accounting.py`, `domains/identity/service/environment.py::accounting_period`, LocalBot/media/Azure 한도 owner | timezone history를 포함한 UTC 기간과 원 reservation ID의 합집합으로 사용량을 보호한다. old aggregate의 반복 인계·unknown 정산을 0 사용량으로 초기화하지 않는다. 실제 SQLite 경쟁 검사가 별도다. |
| schema migration | `alembic/versions/20261003_0105_local_environment.py`, `runtime/migrations/sqlite_versions/environment_v27.py` | v27은 additive다. 옛 v0–v26 manifest, 원문·ID·hash·receipt·credential을 다시 생성하지 않는다. 과거 snapshot 누락은 제한된 호환 경로에서 처리한다. |

각 파일 경로는 `backend/app/` 또는 `frontend/src/` 기준이다. 최종 결과 문서의 실제 source 링크와 수집 노드가 이 표를 보완한다. 소유 inventory의 AST 후보 목록은 로컬 `artifacts/multilingual-gemini-20261003/source-owner-inventory.json`에 보존한다. 최종 소스에서 direct 호출 후보 23곳과 Korean instruction 후보 29곳을 확인했다. SQL `select`와 AI `select`를 같은 호출로 집계하지 않으며, 소스 참조가 있다는 이유만으로 활성 provider 호출로 간주하지 않는다.

환경 route는 기존 인증 dependency의 read-only demo 제한을 적용한 typed context를 사용한다. GET 조회 허용과 POST 403을 검사했다. 계정 삭제는 Identity의 `delete_private_environment`를 통해 해당 owner의 감지 환경·시간대 이력과 UI 선호만 제거한다. 다른 owner의 환경은 유지되며, runtime 조립이 다른 도메인의 내부 저장 모델을 직접 삭제하지 않는다.

## 활성 AI 소유와 언어 정책

| 활성 경로 | 소유와 입력의 분리 | 검증의 한계 |
| --- | --- | --- |
| SNS Selector·Feed/Inbox Planner·Combined/Writer·Routine | `runtime/autonomous_activity/provider.py`, `social_wire.py`, `domains/world_characters/contracts/social_io.py`, 각 기존 prompt owner | Angmoo 작성 instruction은 영어다. 감지 memory locale, 원 persona/source, 발화 지시는 서로 다른 입력이다. 후보/action/intent/purpose enum은 번역하지 않는다. SDK HTTP의 4개 lane/capability와 strict validator를 검사한다. |
| Chat Router·Canonical/Graph Planner·Supervisor·CRG | `integrations/llm/retrieval_router.py`, `canonical_retrieval_planner.py`, `graph_retrieval_planner.py`, `supervisor_selection.py`, `character_response_generator.py` | 질문 검색어는 현재 Chat 의미를 따른다. relative time/activity는 닫힌 typed 의미로 코드가 UTC 범위를 만든다. 캐릭터의 명시 발화 지시와 기본 콘텐츠 언어를 별도로 전달한다. |
| Memory Selection·Episode·Consolidation | `integrations/llm/memory_selection.py`, `episode_selection.py`, `memory_consolidation.py`와 기존 job/bundle owner | admitted locale를 기존 선택 호출에 전달한다. 원본 refs/부정/정정/약속을 보존하고 별도 번역 호출을 만들지 않는다. fake의 언어 출력은 실제 요약 품질의 증거가 아니다. |
| 관계 review와 조회 | `integrations/llm/relationship_review.py`, 관계 canonical 조회 owner | subject/target/World/direction은 ID 문맥이다. 기존 label/perception의 keep은 그대로 보존한다. 관계 조회를 memory lexical search로 바꾸지 않는다. |
| 이미지 이해 | `integrations/llm/image_interpretation.py`, 공통 분석·cache·첨부 경로 | 새 description/uncertainties는 영어 지침, visible_text는 원 문자, optional recall_hint는 별도 bounded 필드다. 옛 분석 cache는 재사용하며 locale 변경만으로 유료 재인식하지 않는다. |
| Creator·일과·Tendency·첫 인사·이미지 프롬프트 | 각 `domains/characters/service`, `domains/routines/service`와 `domains/social/service/image_prompts.py` owner | 작성 instruction과 예시·원 persona를 분리한다. 허용 schema/수치/호출 한도를 UI 번역 목적으로 늘리지 않는다. |

공통 물리 경계는 `integrations/direct_llm.py`와 `providers/gemini.py`다. 개발자 JSON schema의 scalar const는 같은 타입의 singleton enum으로 낮추고 null 분기를 보존한다. 값·required·충돌·불변성을 독립 Draft 2020-12 oracle로 확인한다. 실제 SDK + MockTransport는 서비스로 전송하지 않고 최종 HTTP body를 확인한다.

일반 댓글의 intent/purpose 누락은 strict parser에서 여전히 실패한다. 적격 첫 STOP만 기존 JSON 복구 기회를 한 번 공유한다. 복구 뒤 다른 종류의 오류가 생겨도 세 번째 JSON 요청은 없고, Combined 복구 영수증은 Writer 연쇄 복구를 차단한다. 정상 10/복구 5/전체 15, split 4096/Combined 8192, 현재 guard와 durable ledger가 유지된다.

`runtime/resident/execution.py` 등에 과거 v1 도구-loop 함수와 Korean instruction 문자열이 남아 있다. 지원 SNS 진입은 `run_social_activity` → contract-v2 graph이고 옛 실행은 retirement 경계가 차단한다. 수동 활동의 `run_message`에도 과거 Korean 지침 후보가 있으나, 지원 V2의 `LangGraphResidentContext`에는 이 message가 전달되지 않는다. 문자열이 생성된다는 사실과 실제 SDK 요청에 들어간다는 사실을 구분했다. 새 활성 AI에 옛 문자열 치환 helper를 적용하지 않았다. **따라서 저장소의 Korean 문자열 검색 결과 0을 주장하지 않는다.** inactive 소스·과거 wire/alias·사용자 원문과 현재 활성 지침을 구분한다.

## UI와 검색

번역 resources는 16개 namespace, 2,375개 source key의 feature/composition owner에 둔다. 공통 engine·환경 context·hook은 global lib/hooks가 소유하며 feature끼리의 내부 import를 늘리지 않는다. 이름·카드·World·게시글·검색 결과 원문은 catalog를 통해 통째로 치환하지 않는다. API 실패는 typed code/params/UTC retry 값을 표시하는 별도 경계에서 처리한다. Social/Community의 업무 wrapper는 유지하면서 실제 HTTP 전송은 인증/session/runtime scope를 확인하는 공통 `apiRequest`를 사용한다. 오래된 401 응답이 새 로그인이나 backend의 인증을 지우지 않도록 12개 전환 조합을 검사했다. 숫자/시간 표시는 Intl이고 UI 언어와 runtime zone은 독립이다.

실제 지원 경로와 Next-only 경로는 기존 capability를 유지한다. Home/Feed/캐릭터/게시글/답글 등의 일반 명칭을 바꾸되 slug/ID/enum/URL/Provider Referer는 유지한다. 삭제된 작성자는 canonical deleted 상태로 표시하고 같은 이름의 활성 캐릭터를 삭제자로 오인하지 않는다. static의 unsupported 안내는 신규 기능 노출이 아니다.

Memory lexical 검색은 같은 NFKC/casefold/Unicode mark/ZWNJ 정책을 색인·query·후검증에 적용한다. 영어 단어와 A-17/v1.2 경계를 보존하면서 ko/CJK spacing 정책을 유지한다. legacy substring fallback에도 원문 경계를 검사한다. `unicode-boundary-v2` projection은 bounded 페이지/짧은 transaction, 원본 재검증·삭제/정정 fence와 durable 재개를 사용한다. 실제 embedding 품질은 합성 literal/fake vector의 PASS로 대신하지 않는다.

시각 기준의 canonical 환경은 기존 digest-pinned Playwright 1.62.1 Noble이다. Windows 캡처의 글꼴 차이를 canonical PNG 변경 근거로 쓰지 않는다. 일반 명칭·날짜 표시의 의도한 변경만 기능·픽셀 차이와 exact committed asset hash를 함께 검토한다. 비교 허용치와 contrast 예외·keyboard/focus/reduced-motion 기준은 유지한다.
