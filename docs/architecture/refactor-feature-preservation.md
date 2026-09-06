# Angmoo 기능 보존과 현재 코드 읽기 지도

기능을 수정할 때는 [Backend ARCHITECTURE](../../backend/ARCHITECTURE.md)의 역할 설명과 [기능 inventory](../../security/refactor_feature_inventory.json)의 현재 경로를 함께 확인한다. 이 문서는 기능별 실제 구현과 그 기능을 보존하는 증거의 관계를 설명한다. 원래 파일이 여러 업무로 나뉜 경우 대표 파일 하나가 원래 기능 전체를 대신하지 않는다.

## 현재 적용 범위와 검증 상태

이 읽기 지도의 코드 기준은 AR-B8 통합 준비 source `7ada864c5a3a77ddd601d0faed81577615b5af0f`다. 백엔드 업무·공통 기반의 실제 소유 위치, 삭제된 집계 파일의 후속 구현, 현재 소비자와 테스트 경로를 반영했다. `MOVED`는 이 코드 이전을 뜻하며 **최종 통합 CI·설치·업그레이드·실패 복원 검증을 새로 통과했다는 뜻은 아니다.** 해당 결과와 정확한 PR·merge commit은 [백엔드 전환 결과](refactor-backend-results.md)에서 확인한다.

Device Home의 기존 `VERIFIED` 파일럿 증거는 유지한다. 프론트엔드의 AR-F2 이후 전환과 AR-X는 별도 단계다. 백엔드가 이전돼도 해당 기능의 `frontend_status`가 `MAPPED`이면 전체 `status`도 `MAPPED`로 남긴다. P8-L-S의 실제 AI 품질·인과·사용자 closeout 또한 이 문서의 코드 이전 판정과 구분한다.

현재 G07에서 별도 source로 준비하는 테스트 6개는 이 기준에 아직 합류하지 않았다. LocalBot 응답·rate limit·atomic quota는 `tests/local_bot`, profile media는 `tests/media`, prompt safety와 context text는 `tests/common`으로 옮기는 후속이다. 현재 inventory는 이 파일들이 실제 존재하는 기준 경로를 유지하며, 부모 통합에서 그 source의 정확한 이동을 연결한다.

## 현재 경로와 역사적 증거를 읽는 방법

| 자료·필드 | 의미 |
| --- | --- |
| inventory의 `current_paths` | 현재 존재하는 구현·지원 파일. 삭제된 빈 marker는 다른 빈 파일로 대체하지 않는다. |
| `target_paths` | 확정된 백엔드의 실제 역할 위치. 프론트엔드의 미전환 목표 경로는 §8.3에서 구현할 대상으로 유지한다. |
| `consumers` | 현재 `backend/app` AST에서 해당 항목의 구현 파일을 직접 import하는 제품 모듈. 기존 프론트엔드·기타 비-app 소비자는 유지한다. 모두 HTTP 호출자라는 의미는 아니다. |
| `test_paths` | 현재 존재하는 연관 회귀 파일. 이 목록만으로 모든 분기·설치 환경이 검증됐다고 판단하지 않는다. |
| 기록된 `entrypoints`·`test_nodes` | 최초 조사 또는 중간 이전 시점의 symbol/node 연결. 현재 위치는 [경로 대응표](../../security/refactor_path_map.json)의 파일·symbol·node 기록으로 확인한다. |
| `historical_transition_evidence` | 이전 slice의 설명·검증·당시 잔여 작업. 현재 미구현 목록이나 현재 검증 결과로 해석하지 않는다. |
| `baseline_commit/tree`·`coverage` | #258 당시 고정 조사 범위와 숫자. 현재 source 수로 덮어쓰지 않는다. |
| [원본 기준선](../../security/refactor_source_baseline.json)·[후속 체크포인트](../../security/refactor_backend_checkpoint.json)·[추가 이력](../../security/refactor_backend_additions.json) | 원본 source·API·ORM·단언·node와 이후 실제 최초 도입 증거. 현재 목록 정리로 다시 생성하지 않는다. |

소비자 목록은 현재 source의 import 관계를 확인해서 작성한다. 삭제된 `services/agents.py`를 `runtime/characters/management.py` 한 곳으로 바꾸는 것처럼 과거 경로의 대표 대응만 반복 적용하지 않는다. 현재 Character·Routines·Identity 서비스와 runtime 조립 중 어느 파일이 실제 해당 기능을 import하는지 구분한다. 더 세밀한 함수 호출과 같은 Session 협력은 source 및 `split_symbols`의 소비자 증거를 따라간다.

## 기능별 현재 구현

아래 경로는 `backend/app/` 기준이다. 같은 기능에 여러 업무가 참여해도 권한·상태 전이·자기 DB의 실제 소유를 유지한다.

| 기능 ID | 현재 시작 위치와 협력 | 보존하는 경계 |
| --- | --- | --- |
| K01 | `domains/identity`·`credentials`·`runtime/account_deletion.py` | 세션·CSRF·credential·동일 Session 삭제/rollback·비공개 미디어 보상 |
| K02 | `domains/device_home` | Local World 목록·진입/실행가능 표면과 runtime 상태 구분 |
| K03 | `domains/characters`·`domains/worlds`·`domains/character_lore` | Creator·초안·정의/readiness·문서·모델 소유 |
| K04 | `domains/world_characters`·`domains/routines/service/plans.py` | 참여·setup 승인·owner control·시간대 후보·flush/commit 순서 |
| K05 | `domains/routines`·`domains/routine_posts`·`runtime/resident`·`runtime/routines` | 계획·episode·beat·cursor·슬롯·claim·실행·로그·provider 예산 |
| K06~K07 | `domains/social/service`·`repository`·`runtime/social`·`runtime/search` | 게시·Inbox·관찰·Feed/FTS·현재 World/공개 범위 |
| K08~K09 | `domains/relationships`·`runtime/relationships`·`runtime/graph_projection` | 사건·관계·outbox 원자 적용과 재구성 가능한 graph |
| K10 | `domains/world_packages`·`runtime/world_packages` | export/preview/import·archive·lineage·same-Session 원자 적용·파일 보상 |
| K11 | `domains/media`·Character/Social 미디어 서비스·`integrations`·`providers` | 공유 변환과 업무별 candidate/공개/할당 정책·credential·호출 수 |
| K12~K13 | `domains/runtime`·`runtime`·`domains/local_bot`·`domains/operations` | sidecar·진단·lease·종료/복구·Bot 권한·설정 의미 |
| K14·K17 | `domains/chat/router`·`service`·`repository`·`runtime/chat` | World chat identity·thread/message·durable generation·취소·동시성 |
| K15~K16 | `domains/memory/service`·`repository`·`runtime/memory` | 후보/항목·동의·원본 재검증·정정/삭제·canonical/graph recall |
| K18 | Chat 응답/근거 서비스·Memory consolidation 서비스 | immutable evidence·CRG NDJSON·모델 snapshot·legacy v1 |
| K19 | `domains/memory/router.py`·소유 서비스 | inspector·owner control·pin/정정/삭제·충돌 응답 |
| K20 | Social Today 활동·Chat Today 근거 서비스 | 실제 성공 source·coverage·숨긴 원본 제외·추가 AI 없음 |
| K21~K23 | Memory batch 준비/선택/예약 서비스·`runtime/memory`·embedded migrations | ON epoch·source 전달·lease/config/model fence·원자 저장·bounded shutdown |
| K24 | Tree·Operations·공유 core/contracts·`runtime/extensions` | 실제 잔여 업무와 지원 확장 계약. 임시 전달층은 제거하고 필요한 역사적 alias만 유지 |

Chat의 전달 전용 `ChatService`, `ChatRuntimePort`, `GenerationLifecycleService`와 집계 `world_generation`은 현재 구현 위치가 아니다. 실제 Thread·Message·Generation·Evidence 서비스와 `runtime/chat/message_composition.py`를 사용한다. 원래 전달 테스트는 실제 owner의 같은 입력·결과·실패 계약 및 좁은 원문 증명으로 승계한다.

## 공통 기반의 현재 위치

| ID | 현재 실제 소유 | 확인할 계약 |
| --- | --- | --- |
| G01 | `app/config.py`·`runtime/configuration.py` | 기본값·설정 우선순위·개발 `.env` 경로·설치 독립성 |
| G02 | `app/models.py`·`runtime/persistence/model_registration.py`·각 도메인 models | 단일 Base/metadata와 실제 class identity·모델 등록 |
| G03 | `app/exceptions.py`·소유 도메인 exceptions | HTTP status/code/body·실패/재시도 의미 |
| G04 | `app/pagination.py`·Device Home/Social cursor 소유 파일 | 공유 bytes codec과 독립적인 payload·암호화·scope·정렬 |
| G05 | `app/database.py`·runtime 구성/SQLite 자원 관리 | lazy engine/session·PRAGMA·같은 Session·종료 |
| G06 | `app/main.py`·공식 contributor/sidecar launcher | 단일 factory의 full/public profile·시작/종료·health·기존 기본값 |
| G07 | 소유 도메인·runtime/integrations/common의 tests | 기존 assertion/node·fixture·수집·CI의 정확한 이동 |
| G08 | 실제 `main.py`·`api/v1/public.py`의 JSON/API 조립 | 서버 HTML template 소비가 없어 `templates/`를 만들지 않은 결정 |
| G09 | `pyproject.toml`·`uv.lock`·`.python-version` | 실제 dependency 원본 유지. 수동 `requirements/` 이중 관리 없음 |
| G10 | `.env.example`·설정/명시적 runtime 구성 | 비밀 제외·설치 환경 분리·우선순위 |
| G11 | root `.gitignore`·Docker/installer 배포 설정 | Git 제외와 배포 제외 구분·필수 source/lock/resource 포함 |
| G12 | `logging.ini`·`runtime/logging_config.py` | 기존 handler와 sidecar stdout/stderr·handshake |
| G13 | `backend/alembic`·실제 Base/등록·embedded migrations | 역사적 revision 본문/그래프와 지원 SQLite upgrade·실패 복원 |

`main.py`의 기본 `create_app`/`app`은 full profile이고 `create_public_app`/`public_app`은 public profile이다. `public_main.py`를 삭제했다고 두 profile을 하나의 기본 호출로 바꾸지 않는다. G06 최종 설치·CI 판정은 삭제된 파일이 없는 최종 후보에서 별도로 확인한다.

## 삭제된 집계와 실제 소유자를 대응한 근거

| 옛 source 범위 | 현재 위치 선정 |
| --- | --- |
| `models/agent_runs.py` | 실행·로그·slot·cue는 Routines `models/resident.py`, 관계 point는 Relationships `models/points.py`, Daypart 기억은 Memory `models/daypart.py`로 나뉜다. |
| `models/agent_settings.py` | Character 이미지 설정은 Characters models, 활동 설정은 Routines resident models다. |
| `models/worlds.py` | World 정의/회원/장소/역할은 Worlds models, World 참여/활성 World는 WorldCharacter models다. |
| `models/__init__.py` | 실제 Base는 `app/models.py`, 전체 등록은 runtime `model_registration.py`다. 한 파일로 대체하지 않는다. |
| 나머지 옛 ORM 파일 | 인증/credential은 Identity, Character/초안/프로필 후보는 Characters, Bot/key/quota는 LocalBot, message는 Chat, 계획은 Routines, setup은 WC, 운영 설정은 Operations models다. |
| `services/world_foundation.py` | World seed 규칙은 Worlds, 참여 seed 규칙은 WC, 동일 Session의 혼합 연결은 `runtime/worlds/foundation.py`다. |
| `services/local_bot_quota.py` | LocalBot quota 서비스·조회 repository·오류로 나뉘며 원래 atomic write 의미를 유지한다. |
| `services/maintenance.py`·`operation_settings.py` | Operations service/repository와 해당 constants/contracts/exceptions가 실제 소유자다. |
| `services/image_prompt_safety.py`·`service_image_key.py` | 실제 공유 정책은 `core/image_prompt_safety.py`, 공통 비밀 해석은 `credentials/service_images.py`다. |
| 옛 Chat public·api marker와 compatibility namespace | 실제 업무를 전달하는 집계 또는 빈 marker다. 이미 기록한 실제 역할을 사용하며 부재 경로마다 proxy를 새로 지정하지 않는다. |

활동시간의 5개 순수 함수·4개 상수는 `domains/routines/policies/active_hours.py`에 있다. 게시물 검색 문서 구성은 `domains/social/service/search_documents.py`가 소유하고, 공통 검색 문자열 정규화는 `core/search_text.py`에 남는다. `core/image_generation.py`의 공유 모델 값과 `core/public_media.py`의 마운팅은 실제 공통 역할이므로 유지한다.

역사 migration의 옛 schema/model helper와 별도 배포 Hosted 확장 alias는 제거한 임시 집계와 구분한다. 정확한 잔존 경로·소비자·같은 객체 계약은 [호환 계약](backend-compatibility.md)에 기록하며, 현재 source import 검사에서도 제외하지 않는다.

## 검증과 증거 갱신

현재 경로를 정리할 때는 파일 존재만 확인하지 않는다. 실제 defining symbol과 source split을 대조하고 소비자 AST를 재수집한다. 테스트는 파일 이동 뒤 원래 node·assertion·fixture를 계속 보호하는지 확인한다. 기존 source/test/API/ORM 기준선, 승인 node, frozen migration, 최초 도입 이력은 이 읽기 지도 수정으로 변경하지 않는다.

최종 제품 검증은 Docker Browser Run, Docker contributor, Host Tauri dev, Windows installer의 각 실행 계약에 맞춘다. 현재 코드 위치가 정확하다는 사실은 그 실행 경로에서 최종 후보를 검증했다는 증거와 별개다.

## 역사적 조사·중간 이전 기록

아래는 이 문서의 `7ada864c` 기준 이전 내용을 그대로 보관한 기록이다. 내부의 “진행 중”, “후속”, “목표”와 수치는 각 slice 당시 상태이며 현재 구현·최종 검증 상태를 선언하지 않는다. 현재 위치는 위 설명과 inventory의 현재 필드를 사용한다.

<details>
<summary>AR-0 파일럿부터 B8 LocalBot A5까지의 원문 기록</summary>

# Angmoo 구조 전환 기능 보존 지도

기존 기능의 API·저장 데이터·화면·실행 방식을 보존하면서 수정 위치를 찾기 쉬운 구조로 옮긴다. 이 문서는 보존 범위와 검증을 읽는 지도이며, 목표 역할은 [frontend ARCHITECTURE](../../frontend/ARCHITECTURE.md)와 [backend ARCHITECTURE](../../backend/ARCHITECTURE.md)가 설명한다.

## 기준과 적용 상태

2026-09-05 AR-0의 기준은 PR #258 merge `6e56f0837cc11ff42ccbb520050bbd32c5e9bc14`, tree `99f679acb9aab1e3b28628d0aee6d71ae0364d74`다. 준비·검사 지원 PR #259, backend Device Home PR #260, frontend Device Home PR #261이 차례대로 병합되어 §8.1 준비와 두 파일럿이 완료됐다. 기준선 JSON은 현재 경로로 재생성하지 않으며, 단계별 결과는 [파일럿 결과](refactor-pilot-results.md)에 누적한다. §8.2는 #263 merge `d7037625a19071eb279ad2ea35c3ace6fe5b5289`를 추가 체크포인트로 삼아 AR-G0 검사 지원부터 진행한다. §8.2 공통 기반의 설정·공통 오류·logging·Alembic 이전은 별도 branch에서 구현·집중 검증 후 순차 PR·병합을 준비하고 있다. AR-F2 이후·AR-X는 아직 미착수이며, 새 실행 증거는 [백엔드 전환 결과](refactor-backend-results.md)에 누적한다.

| 자료 | 소유하는 정보 |
| --- | --- |
| [기능 inventory](../../security/refactor_feature_inventory.json) | K/G별 소유자·현재/목표 경로·소비자·보존 계약·테스트·담당 단계 |
| [고정 기준선](../../security/refactor_source_baseline.json) | 기준 commit/tree의 추적 파일 blob, 원래 test node, API·schema·ORM 계약, backend import 연결, 인계 문서 hash |
| [경로 대응표](../../security/refactor_path_map.json) | 검토한 old→new 파일과 test node. 기준선 자체를 새 경로로 재생성하지 않음 |
| [파일럿 결과](refactor-pilot-results.md) | 단계별 실제 변경·검증·잔여 호환·PR/head/merge 결과 — 파일럿에서 작성 |
| [백엔드 체크포인트](../../security/refactor_backend_checkpoint.json) | #263까지 도입된 파일·테스트·계약의 고정 후속 기준. #258 원본과 함께 보존 |
| [후속 추가 이력](../../security/refactor_backend_additions.json) | 이후 처음 도입된 commit·기능 ID별 source/test 보호. 기존 체크포인트 재생성으로 대체하지 않음 |

`MAPPED`는 위치와 책임을 조사했다는 뜻이다. 실제 이전 후 `MOVED`, 해당 기능의 검증 근거가 연결됐을 때 `VERIFIED`로 바뀐다. `backend_status`와 해당하는 `frontend_status`를 구분하며, backend만 완료해서 전체 `status`를 올리지 않는다. 폴더 생성이나 테스트 수집만으로 동작이 검증됐다고 표시하지 않는다. 삭제는 `PROVEN_UNUSED`와 정적·동적·등록·빌드 소비자 부재 근거가 있어야 한다.

K05의 AR-B4-A2는 일일 계획의 실제 service·repository·HTTP와 같은 Session의 외부 업무 조회를 연결한다. DST·선택 버전·40개 후보·원자 계획 생성·runtime-mode commit은 유지하고, 단순 전달만 하던 daily-plan usecase/repository와 외부 ORM 집계만 제거한다. A3a는 guarded lifecycle의 실제 상태 전이와 commit을 서비스로 옮기고, 같은 Session의 owner 조회·만료 계획 join은 runtime에서 연결한다. 기존 autonomous 제한과 캐릭터별 commit을 유지한다. 서로 다른 legacy claim 동작·provider 결과·resident 실행은 후속 B4 범위이며 K05 전체를 완료로 표시하지 않는다. 실제 원본 symbol·소비자·검증 연결은 경로 대응표의 A2a/A2b/A3a 기록에서 확인한다.

## AR-0 검증

| 대상 | 이번에 확인한 결과 |
| --- | --- |
| #258 post-merge | 기준 merge의 workflow 7/7 SUCCESS를 새로 조회. 새 refactor head의 CI 결과와 별도 |
| backend 수집 | 1,867 nodes. 승인된 M3 public 604 nodes는 별도 유지 |
| backend 전체 회귀 | 1,845 passed, 22 skipped, 26 warnings / pytest 430.87초 / exit 0 |
| Device Home 웹 기준 | 빈 Home·넓은 화면·runtime 장애·재시도/실행 가능성·PWA 공유 Home: 5 passed / 53.4초 |
| 로컬 도구 | Python 3.13, Node 24.19.0, pnpm 11.22.0, uv 0.11.9. CI Node 22·uv 0.12.5와 구분. 제품 lockfile 변경 없음 |
| Docker | 초기 daemon 미기동. 환경 기동과 제품 실행 검증을 구분하여 후속 결과 기록 |

원래 skip은 PostgreSQL 전용 동시성 검증·공개 runtime에서 제외된 hosted lifespan 등 환경/profile 조건에 해당한다. 합성 SQLite/embedded 테스트에서 얻은 결과를 PostgreSQL 실행 결과로 표현하지 않는다. 경고는 기존 FastAPI/Starlette·httpx cookie·SQLite datetime deprecation이며, 리팩터링 중 의존성 업그레이드로 범위를 넓히지 않는다.

전체 검증의 실행 명령·시간·결과는 고정 기준선에, 파일럿의 후속 결과는 결과 문서에 기록한다. 실제 사용자 AppData·credential·World 원본을 fixture나 inventory로 수집하지 않는다.

## K01~K23: 보존할 동작

| ID | 기능 | 보존의 핵심 |
| --- | --- | --- |
| K01 | owner·인증·BYOK·프로필 | session/CSRF·credential 접근·계정 삭제·비밀 노출 경계 |
| K02 | Device Home·Phone·World 목록 | owner 범위·launchability와 runtime 상태 구분·빈 상태·재시도·탐색 |
| K03 | Character·World Creator·Studio | 생성/편집·readiness·membership·definition hash |
| K04 | WorldCharacter 구성 | 수동/자율 구분·4시간대×10 routine 후보·승인·재시작 |
| K05 | 일일 활동 | plan/episode/beat/cursor·continuation·reply·provider 예산·중복 방지 |
| K06 | SNS·Inbox | 게시/답글/reaction/관찰/follow-up·NO_ACTION과 성공 사건 구분 |
| K07 | 검색 | SQLite FTS·scope·예산·원본 재검증·degraded |
| K08 | SocialEvent·관계·outbox | 원자 저장·관계 방향·중복 방지·joint 활동 |
| K09 | 원본/graph | SQLite canonical·Ladybug projection/replay·장애 중 원본 저장 |
| K10 | World Package v1 | export/preview/import·media/license/trust·binding·비활성 import·비밀/runtime 제외 |
| K11 | media/provider | credential·재시도·timeout·취소·예산·안전한 진단·추가 호출 없음 |
| K12 | 설치/runtime | sidecar·scheduler/projector·loopback/AppData·sleep/drain·재시작 |
| K13 | 제품 UI·지원 | Settings·진단·Phone/Studio/Graph·PWA·Local Bot·실제 capability |
| K14 | P8 A~E Chat | World/requester/responder identity·thread/message·role model·legacy 격리·SNS 진입 |
| K15 | F~G Memory 쓰기 | ON/OFF scope·candidate/item/evidence·pin·정정/삭제/tombstone |
| K16 | H~I 회상 | canonical FTS·제한된 graph query·원본 권한 재검증·방향·degraded |
| K17 | J~N 응답 실행 | durable generation·lease/retry/idempotency·5 router 경로·typed planner·BOTH 코드 조립 |
| K18 | O~P 근거/stream | consolidation/HotBrief·legacy v1·immutable evidence·CRG NDJSON·model snapshot/override/thinking |
| K19 | Q~R Memory UI | workspace/inspector/origin·ON/OFF·pin·수정/삭제·보존 기간·충돌 상태 |
| K20 | Today SNS #251 | 실제 성공 source·동기/감정·부분 coverage·숨긴 원본·추가 AI 없음 |
| K21 | #258 A~B 배치 기반 | SQLite v9·6 tables·동의·source→delivery→candidate·ON epoch·OFF 공백 미수집 |
| K22 | #258 C~D 배치/예약 | opt-in v2 retain/skip·source/config/model/lease fence·원자 저장·HH:mm/timezone/catch-up |
| K23 | #258 E 종료 | 전체 앱 종료·제한 시간·skip/finalizer·재시작·중복 방지·동의 상태 |

한 기능에 여러 도메인·runtime·화면이 연결될 수 있다. 항목의 상세 경로와 test는 JSON을 참조한다. 실제 source와 test 목록은 고정 기준선으로 함께 보존하므로 예시에 없는 코드가 삭제 대상이 되지 않는다. 새로운 기본값·provider 동작이나 AI 품질 개선은 구조 전환에 포함하지 않는다.

## G01~G13: 공통·지원 구조

| ID | 목표/처리 | 선행조건·보존 의미 |
| --- | --- | --- |
| G01 | app/config로 구현·소비자 이전, core/config 제거 | 설정 기본값·우선순위·개발 .env 탐색 위치. 검증·병합 상태는 백엔드 전환 결과 참조 |
| G02 | app/models.py | 업무 ORM 소비자 이전 후 app/models 패키지 교체. 단일 Base·metadata·class identity |
| G03 | 공통/도메인 exceptions | HTTP status/code/body/retry 의미 |
| G04 | app/pagination | 공통 도구와 업무별 cursor·정렬·scope 구분 |
| G05 | app/database | engine/session·SQLite PRAGMA·transaction·종료. Base 중복 생성 금지 |
| G06 | main.py 단일 앱 생성·public_main 임시 호환 후 제거 | Local RuntimeConfig·profile·복구·Memory 종료·DB/session 보존. B8-A에서 통합/호환/참조 전환, G5 뒤 B8-B에서 검증·제거·삭제 후 실행 확인 |
| G07 | 업무별 tests | test node·conftest·fixture·CI의 old→new 연결과 수집 누락 방지 |
| G08 | templates 조건부 | 실제 서버 HTML 소비가 없으면 미생성. 기존 package resource 보존 |
| G09 | pyproject/uv.lock 유지 | requirements 수동 이중 원본 도입 없음. 개발/CI/sidecar 의존성 유지 |
| G10 | .env.example/개발 .env | 비밀 제외, 설치 앱의 개발 .env 독립성 |
| G11 | root .gitignore | Git 제외와 Docker/installer 배포 제외는 별도. source/lock/migration 추적 유지 |
| G12 | 목표 logging.ini | 명시적 초기화·redaction·stdout/stderr/handshake·중복 handler 방지 |
| G13 | backend/alembic 물리 경로 적용·G5 최종 연결 대기 | 전체 88개 역사 revision 본문·그래프와 embedded SQLite frozen migration 보존. G4는 경로/CLI/등록 검증, G5는 최종 Base·등록 경로 재검증 |

공통 기반의 최종 이전은 AR-G다. AR-B1은 기존 Base/DB를 사용하며 G02/G05 완료를 주장하지 않는다. `runtime`, `integrations`, `providers`, `credentials`도 역할과 소비자가 있으므로 유지한다.

AR-G2는 공통 오류 4개와 cursor byte encoding을 실제 전역 파일에 추출했다. SQLite retry·queue, request-body middleware, Device Home/Social의 payload·암호화·query는 기존 파일에 남으며, 전체 원본 파일을 이동한 것으로 처리하지 않는다. `refactor_path_map.json`의 `details.AR-G2`는 남은 심볼과 추출 심볼의 실제 소비자·행위 테스트를 모두 기록한다. 기존 request-body 테스트는 `backend/tests/common/test_request_body_limits.py`로 이동했고 승인 node map에 연결했다. 새 회귀와 구현의 commit별 증거는 [백엔드 전환 결과](refactor-backend-results.md)에 기록한다.

## 실행 경로와 테스트 소유권

| 경로 | 확인할 책임 |
| --- | --- |
| Docker Browser Run | 배포 frontend·embedded backend·API/asset/세션/재시작 |
| Docker contributor | 공식 Next dev·CONTRIBUTOR_EMBEDDED·source sync·개발 volume |
| Windows Host Tauri dev | 공식 wrapper의 Docker backend 재사용·Phone/Studio/Graph 창·탐색 |
| Windows installer | 정적 frontend·bundled sidecar·합성 설치/재시작/upgrade/failure recovery |

웹 standalone build와 static-shell export는 서로 다른 산출물이다. 웹에서 성공한 Home이 정적/native에서도 같은 동작을 하는지 따로 검증한다. 모든 파일 이동마다 전체 installer 검증을 반복하지 않으며, 단계 위험과 필수 CI에 따라 증거를 확보한다. 최종 동일 commit 전체 검증은 AR-X에 남는다.

pytest는 backend 동작과 frontend 소스 계약도 소유한다. `browser-tests/playwright.config.ts`는 `product-shell.spec.ts` 패턴만 수집하며 relationship-graph 하위 파일도 포함한다. static·visual·local-settings는 각 설정/명령이 소유한다. World Package proxy는 `frontend/scripts/test-world-package-proxy.mjs`의 Node 테스트다. 실제 공통 소비자가 없는 `src/testing`과 Vitest/MSW 등 새 실행기는 만들지 않는다. 제품이 test helper를 import하는 것은 허용하지 않는다.

## 두 파일럿에서 옮기는 경계

Backend Device Home은 router/schemas/service/policies/repository로 역할을 모은다. 자체 table이 없는 조회 기능이므로 ORM 모델을 새로 만들지 않는다. `World Package` import/replay가 쓰는 내부 World 조회는 호출자가 전달한 같은 session에서 수행하며 commit/rollback을 추가하지 않는다. HTTP의 owner 확인·404 은폐 계약과 내부 projection 반환 계약을 혼동하지 않는다.

Frontend Home은 World 목록을 소유하고, 인증·runtime-status·device-shell 연결은 `composition/screens/device-home-screen.tsx`로 분리한다. Next/static 진입점이 그 screen을 공유한다. Creator Studio·Memory·World App의 기존 API/type 소비자는 정확한 한 방향 호환 export와 제거 단계를 기록한다. feature의 public에서 composition을 역으로 export하지 않는다.

필요한 runtime transport·navigation·media·AppIcon·Button·class names·semantic CSS만 공용 새 위치로 옮긴다. 미전환 소비자는 구현을 복제하지 않고 좁은 bridge를 사용한다. 기존 marker를 읽는 backend 소스 계약 테스트·디자인 정책·CSS 직접 소비자도 이동표의 일부다.

AR-1은 새 규칙 지원과 허용/거부 fixture를 먼저 제공한다. 실제 코드 이동과 해당 scope 활성화를 같은 PR에서 수행한다. 미전환 영역의 기존 보호 규칙과 전체 순환 검사를 유지하며 넓은 예외로 통과시키지 않는다.

AR-B1은 PR #260에서 legacy alias 없이 병합됐다. AR-F1은 PR #261에서 Home의 화면·공용 코드를 옮겼고 네 feature facade 소비자, 공용 TypeScript bridge 7개, semantic CSS 직접 소비자 7개를 제거 단계와 함께 기록했다. AR-0/1과 두 파일럿의 완료는 전체 리팩터링 완료가 아니다. AR-G·AR-B2 이후·AR-F2 이후·AR-X가 남으며, P8-L-S 실제 AI 품질·인과·사용자 closeout도 별도로 남는다.


### AR-B2-B1 Character 기반의 현재 연결

Character·CharacterState는 `app.domains.characters.models`, seed 요청은 `contracts`, flush-only seed는 `service.seed`, 기존 생성·프로필·핸들 처리는 `service.profile`, 상태 저장은 `service.state`가 실제 구현을 소유한다. 기존 집계 경로는 동일 객체의 한 방향 호환 export이며 종료 담당과 제거 조건은 `architecture_import_policy.json`의 exact bridge에 있다. 부분 추출한 수평 파일의 남은 함수도 `refactor_path_map.json`의 symbol 대응표에 그대로 남는다고 기록했다.

이 단계는 seed와 일반 생성의 서로 다른 transaction 정책을 보존한다. WorldCharacter와 Social activity projection, credential·Creator·활동 실행·다업무 삭제는 담당 전환이 완료될 때까지 기존 책임을 유지한다. media 참조 검증만 Character schema에 필요한 AR-B3 선행 의존성으로 `app.domains.media.schemas`로 옮겼다. 전체 Characters 전환과 source 도입 증거 캡처·통합 검증은 진행 중이다.

AR-G1은 공통 설정을 `app/config.py`로 옮기면서 기존 startup-security 25 nodes를 `tests/config/test_startup_security.py`에 그대로 연결한다. 다른 업무·runtime 테스트는 소유 위치를 유지하고 설정 import만 전환한다. 새 설정 경로·cold import 회귀 2개는 별도 도입 증거에 기록한다. 고정 기준선·과거 secret-scan allowlist·검사 fixture의 옛 경로는 역사 또는 검사 입력이며 실행 호환 파일이 아니다. G01 코드 이전은 AR-G 전체나 설치 앱 최종 검증 완료를 뜻하지 않는다.

AR-B2의 identity 구현은 15개 소유 테스트 파일·기존 133 nodes와 함께 역할 파일로 이전했다. Auth의 계정 삭제 부분은 runtime의 같은 session/UoW workflow로 분리했고 실패 시 DB rollback·비공개 media 복구, 성공 후 purge 순서를 유지한다. Local owner의 실패한 claim 시도 횟수 commit과 session 발급 제한도 보존한다. 두 factory의 callback 연결, HTTP dependency의 같은 객체 identity, 기존 model/schema aggregate 호환은 G06·G05 후속 단계에서 이어받을 계약이다. 현재 적용·검증·PR·병합 결과는 [백엔드 전환 결과](refactor-backend-results.md)에 별도로 기록한다.

AR-B2 Worlds는 정의·생성·readiness·배너를 12개 실제 역할 module로 이전한다. 기존 Creator 테스트 2파일·11 nodes는 `tests/worlds/`로 옮기며 local-smoke·ER0·L4의 실제 실행 경로도 연결한다. Mixed Worlds router의 14개 endpoint 중 World 10개는 새 router로, WorldCharacter 4개와 leave runtime guard는 기존 경로에 남긴다. 두 앱의 router 순서와 WC에서 전달된 World 오류의 HTTP 변환도 보존한다.

Worlds 부분 전환은 K03 전체 또는 WC·Package·활동·frontend 완료가 아니다. Package seed의 flush-only, 기존 World mutation의 commit, 이전 배너 정리, timezone 재예약의 같은 Session을 유지한다. `worlds.public`의 미전환 ORM 소비자와 immutable v2→v3 import 호환 4개는 정확한 bridge·후속 종료 조건으로 관리한다. 새 서비스에서 ORM 클래스를 export해 다른 업무의 저장 접근을 위장하지 않는다. 원본 3파일을 분리한 63개 symbol에는 실제 목적지·소비자·검증 node가 있으며, frozen migration과 기준선 본문은 바꾸지 않는다.


AR-B2 WorldCharacter 기반 slice는 6개 ORM과 두 schema 묶음, 입력 계약·오류, 생성기 client, 응답 검증 및 flush-only seed를 새 역할 경로로 옮긴다. 기존 setup contract 테스트는 `tests/world_characters/test_setup_contracts.py`로 이동하며 test node·symbol map이 원본 assertion을 계속 보호한다. provider monkeypatch 호환은 같은 module 객체로 유지하고, frozen v2→v3의 옛 ORM import 두 개도 새 class와 동일한 객체다. 원본 5파일의 66개 symbol 분리를 기록했으며 setup·entry·owner·Studio workflow는 아직 후속 slice다.


AR-B8 LocalBot A5는 실제 18행동/읽기와 18HTTP를 own service/router로 닫는다. 이전 LocalBot 72정의 split의 실제 목적지·소비자와 Identity deps 원본의 Authorization 2/Bot 인증 1 분할을 갱신했다. 기존 원본 snapshot/assertion은 불변이며 typed 협력은 같은 Session·nullable 조회·오류객체·deferred commit·quota/rollback·aftercommit image 요청을 보존한다. G07 route inventory는 module 필드 26개만 현재 owner로 전환했다. B5/G5/G06 최종 합류와 원본 source introduction은 root 순차 통합 범위다.

</details>
