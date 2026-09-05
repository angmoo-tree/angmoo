# Angmoo 구조 전환 기능 보존 지도

기존 기능의 API·저장 데이터·화면·실행 방식을 보존하면서 수정 위치를 찾기 쉬운 구조로 옮긴다. 이 문서는 보존 범위와 검증을 읽는 지도이며, 목표 역할은 [frontend ARCHITECTURE](../../frontend/ARCHITECTURE.md)와 [backend ARCHITECTURE](../../backend/ARCHITECTURE.md)가 설명한다.

## 기준과 적용 상태

2026-09-05 AR-0의 기준은 PR #258 merge `6e56f0837cc11ff42ccbb520050bbd32c5e9bc14`, tree `99f679acb9aab1e3b28628d0aee6d71ae0364d74`다. 준비·검사 지원 PR #259, backend Device Home PR #260, frontend Device Home PR #261이 차례대로 병합되어 §8.1 준비와 두 파일럿이 완료됐다. 기준선 JSON은 현재 경로로 재생성하지 않으며, 단계별 결과는 [파일럿 결과](refactor-pilot-results.md)에 누적한다. §8.2는 #263 merge `d7037625a19071eb279ad2ea35c3ace6fe5b5289`를 추가 체크포인트로 삼는다. AR-G1에서 설정 구현·소비자·설정 전용 테스트를 새 경로로 옮겼으며 이후 제품 이전·AR-F2 이후·AR-X는 아직 미착수다. 새 실행 증거와 PR·병합 상태는 [백엔드 전환 결과](refactor-backend-results.md)에 누적한다.

| 자료 | 소유하는 정보 |
| --- | --- |
| [기능 inventory](../../security/refactor_feature_inventory.json) | K/G별 소유자·현재/목표 경로·소비자·보존 계약·테스트·담당 단계 |
| [고정 기준선](../../security/refactor_source_baseline.json) | 기준 commit/tree의 추적 파일 blob, 원래 test node, API·schema·ORM 계약, backend import 연결, 인계 문서 hash |
| [경로 대응표](../../security/refactor_path_map.json) | 검토한 old→new 파일과 test node. 기준선 자체를 새 경로로 재생성하지 않음 |
| [파일럿 결과](refactor-pilot-results.md) | 단계별 실제 변경·검증·잔여 호환·PR/head/merge 결과 — 파일럿에서 작성 |
| [백엔드 체크포인트](../../security/refactor_backend_checkpoint.json) | #263까지 도입된 파일·테스트·계약의 고정 후속 기준. #258 원본과 함께 보존 |
| [후속 추가 이력](../../security/refactor_backend_additions.json) | 이후 처음 도입된 commit·기능 ID별 source/test 보호. 기존 체크포인트 재생성으로 대체하지 않음 |

`MAPPED`는 위치와 책임을 조사했다는 뜻이다. 실제 이전 후 `MOVED`, 해당 기능의 검증 근거가 연결됐을 때 `VERIFIED`로 바뀐다. `backend_status`와 해당하는 `frontend_status`를 구분하며, backend만 완료해서 전체 `status`를 올리지 않는다. 폴더 생성이나 테스트 수집만으로 동작이 검증됐다고 표시하지 않는다. 삭제는 `PROVEN_UNUSED`와 정적·동적·등록·빌드 소비자 부재 근거가 있어야 한다.

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
| G13 | backend/alembic 목표 | 역사적 revision과 embedded SQLite frozen migration 보존·등록/CI/패키징 연결 |

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

AR-G1은 공통 설정을 `app/config.py`로 옮기면서 기존 startup-security 25 nodes를 `tests/config/test_startup_security.py`에 그대로 연결한다. 다른 업무·runtime 테스트는 소유 위치를 유지하고 설정 import만 전환한다. 새 설정 경로·cold import 회귀 2개는 별도 도입 증거에 기록한다. 고정 기준선·과거 secret-scan allowlist·검사 fixture의 옛 경로는 역사 또는 검사 입력이며 실행 호환 파일이 아니다. G01 코드 이전은 AR-G 전체나 설치 앱 최종 검증 완료를 뜻하지 않는다.
