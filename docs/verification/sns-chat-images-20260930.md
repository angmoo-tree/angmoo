# SNS·Chat 이미지 통합 구현 및 검증 기록

사용자가 지정한 workspace 계획 P00–P12의 로컬 구현 기록이다. 시작 main `1390ca4ddc275d3219b39b389c5368475e013b4c`, 브랜치 `feat/sns-chat-image-integration`, 이슈 https://github.com/angmoo-tree/angmoo/issues/348. PR·push·CI·main 병합·배포·설치 앱 변경은 수행하지 않는다. 도커 없이 임시 SQLite와 테스트 전용 서버에서 검증한다.

## 현행 판정 정정

초기 P00–P12의 누락 없는 전체 완료 판정은 재검토 9건 때문에 철회한다. 동작 문제 6건과 참조 상태·Chat 복구 2건은 수정했고 NovelAI의 정확한 길이 검증은 미입증으로 생성을 차단한다. 현재 source `55d184ca5efdce1ff9f72c3583d119cea56abce1`의 상세 결과는 [후속 수정 기록](./sns-chat-image-review-fixes-20260930.md)과 [후속 JSON](./sns-chat-image-review-fixes-20260930-results.json)을 따른다. 아래 테스트 수·실 인식·전체 보존 결과는 초기 실행의 역사 증거다. 이번 수정의 전체 backend 실행 또는 새 HEAD의 실제 API 검사로 해석하지 않는다.

## 구현 계약

- 네 Provider의 자동 생성은 신규 Routine 글·사용자 활성화·연결·사용량 상한·장면 검증을 모두 통과할 때만 접수한다. 마지막 작성은 image_prompt 장면 하나를 추가하며 기존 4회 LLM 흐름을 유지한다.
- NovelAI V4.5 Full 두 비용 모드, NanoGPT 3개/OpenRouter 3개 모델, ComfyUI API JSON/binding/두 샘플은 공통 request를 각 transport에 맞게 변환한다. 참조는 사용자 지정→PNG 카드 픽셀→프로필→없음 순이며 OFF는 파일 읽기부터 차단한다.
- immutable asset·analysis·intent revision, 원자적 예약, claim/lease, 제출 직전/결과 직전 검증, receipt·결과 spool을 사용한다. 결과 미확정 자동 재생성·무료 실패 시 유료 전환·다른 Provider 대체·과거 글 일괄 생성·다음 날 자동 backlog는 허용하지 않는다.
- 업로드한 SNS/Chat 이미지와 인식 키는 private 소유권을 갖는다. SNS의 이미지 단서는 같은 대상 recall에만 결합한다. Chat 분석은 Router/Planner/CRG 전에 끝나며 별도 image evidence로 전달한다. 본문은 이미지 분석으로 덮어쓰지 않는다.

## 초기 실행에서 확인한 증거

초기 이미지 통합 suite의 최종 실행은 source commit `db1542e2d8774196d13eeabc8bba55e270056051`에서 **110 tests PASS**였다. 마지막 SNS 호출의 scene/잘못된 scene/잘못된 본문/OFF 검사와 두 앱 프로필의 이미지 서비스 격리 검사까지 포함한다. 참조 우선순위·OFF/no read·revision 변경, 네 생성 Provider의 fake physical-call count, 실제 serializer, durable 결과 복구, quota 동시 예약/날짜, v25 populated 업그레이드와 중간 DDL 실패 보존, 공통 Gemini SDK 입력, selected SNS/FTS budget, 실제 Chat LangGraph orchestration, 수동 SNS HTTP 첨부/재전송, private read/World Package exclusion, draft expiry/삭제를 포함한다. 텍스트 LLM 및 생성 transport는 fake이며 paid 생성 실제 품질은 검증하지 않는다.

기존 모든 v1–v25 합성 predecessor 보존 검사는 41 tests PASS. 과거 frozen manifest/DB 원본은 바꾸지 않았고 새로운 v26이 추가되었다. installer의 합성 predecessor 작성과 정적 matrix를 v25까지 확장했으며 실제 NSIS 설치나 hosted workflow는 실행하지 않았다.

허용된 Gemini `gemini-3.1-flash-lite`, medium 실 API: 실제 HTTP 5회, 16.032초, sdk_attempts=1, 대체 key/model 없음. R01 합성 파란 원/빨간 삼각형 묘사, R02 OCR `파란 컵 123` / `ANGMOO 42`, R03 동시 소비자 분석 한 번 공유, R04 실제 Chat workflow 이미지 단독/텍스트+이미지 두 경로, R05 OFF에서 기존 분석 재사용을 확인했다. 입력은 공개 합성 fixture이며 실제 SNS·대화·개인 사진을 사용하지 않았다.

미도리야 이즈쿠의 original scoped key를 검증된 실제 열린 UNC DB/secret에서 read-only로 읽고 메모리의 임시 인식 설정에만 복사했다. source DB·key·모델·활동·사용량 설정 변경 0. 키는 CLI·파일·로그·공개 DTO로 출력하지 않았다. 설치 identity는 identity_verified / running not_observed였다. 설치 앱 실행에 대한 PASS가 아니다.

실 API 공개 fixture 3회 usage는 input 각1172, output69/131/69, total1241/1450/1241, 두 번째 thoughts147. R04 두 임시 Chat DB를 닫기 전 usage를 수집하지 못했으므로 두 건 token 사용량은 미측정이다. 총 physical HTTP 5회는 HTTPX send hook으로 측정했다. 초기 SDK Part adapter 오류 두 번은 실제 wire 이전에 종료되어 physical HTTP 0이었다. 이를 추가 유료 시도나 성공 검사로 세지 않는다.

R 실행은 이후 `13ef6247`에 포함된 미커밋 구현에서 수행했다. 그 실행의 working tree source hash를 별도로 기록하지 않았으므로 최종 HEAD 전체의 실 API 재검증으로 읽지 않는다. 최종 인식 코드·SDK 입력·Chat 조립은 키 없는 110-case suite에서 다시 확인했다.

현재 collection **4,428개**와 전체 domain/runtime/root 분할 회귀 및 수정 후 재검증을 test node별로 대조한 고유 결과는 **4,379 PASS / 49 SKIP / 잔여 실패 0 / 검증 누락 0**이다. 단일 무중단 full-suite 실행 결과가 아니며, 중간 실패를 덮어쓰지 않고 해당 검사들의 실제 재검증 결과로 갱신했다. 원본 JUnit별 해시와 집계는 [결과 JSON](sns-chat-images-20260930-results.json)에 기록한다.

49 SKIP은 실제 Vec1 extension 미제공 21, concurrency 전용 DB 미제공 19, 명시적 성능 실행 6, PostgreSQL graph/scheduler 환경 각1, public profile에 없는 hosted lifespan 1이다. SKIP은 PASS로 집계하지 않는다. 이전 첫 full run의 4208 PASS/117 FAIL/49 SKIP, 뒤의 domain 1/runtime 14/root 3 실패와 closure 검사 1 실패도 원본에 남겼다. schema v26 cold fixture, 레거시 worker, 명시적인 before/after product delta, 기존 Chat 기본 조립 보존, 현재 import/UI 보고서 갱신으로 해결했고 관련 전체 모듈을 다시 검증했다.

최종 이미지 UI는 Next/static **20 PASS**. 기존 static continuity **75 PASS**, Next development **35 PASS/10 SKIP**(실제 HY14 환경 미제공), 마지막 완료 연결 수정 뒤 양쪽 World social core/error 각2 PASS. typecheck, lint, Next production/static build, frontend 구조/design, backend 현재 import inventory 및 구조, L4 현재 보고서, 실제 Next world-package/card proxy도 PASS다. backend 현재 import는 modules 1332 / edges 5400이며 frozen topology의 수치와 구별한다.

원래 `check_refactor_preservation.main()`의 source/assertion/suppression/API/ORM/node 검사를 모두 실행해 **protected lineages 4428 / current 4428 / items 37 PASS**를 확인했다. 반복적인 immutable Git blob 읽기에만 object ID·길이를 검증하는 cache를 사용했고, 현재 파일 읽기·검증 조건·collection·과거 anchor·baseline은 바꾸지 않았다. product-delta 5개와 introduction 5개를 append-only로 추가했다. 현재 import/UI 보고서는 재생성 가능한 현재 코드 보고서이며 과거 frozen checkpoint를 대체하지 않는다.

## 후속 실서비스 검사

F01–F06: NovelAI 실계정 Opus 무차감·유료/Precise reference 비용, NanoGPT/OpenRouter 각각3개(총6개) API 모델의 실제 인증·지원옵션·참조품질, 실제 ComfyUI 모델/외부 API 노드·receipt/history·reference 품질. 현재 생성 API 요청 0이며 모델 설치도 하지 않는다. NovelAI token budget은 별도 Apache-2.0 T5 SentencePiece 리소스를 이용한 보수적 사전 검사이며 NovelAI의 실제 token 가중치/파서와 동일함을 보증하지 않는다. 실제 positive/negative 한도와 Variety Boost 계산 호환성은 F01에서 비교해야 한다.

F07–F11: 나머지 Gemini 3조합 및 다양한 이미지/OCR 품질, 장기 SNS 자연활동·검색 품질, 재시작/백업 복원·설치 환경, 참조 생성 품질. 일반 백업은 DB+private assets+secret을 함께 보존해야 하며 이번 검사에서 실제 backup/restore를 PASS로 측정하지 않았다.

사용자 직접 화면 확인, 실제 생성 API, 고정 Linux pixel baseline, CI/PR/merge/release는 각각 별도 미수행이다. 외부 서비스 정책의 자동 호출 허용 범위도 실제 계정/서비스 약관에 맞춰 별도로 확인해야 하며 이 기록은 이용 권한이나 법률 판단을 보장하지 않는다.


## P00-P12 실행 추적

| 단계 | 구현 결과와 소유 경계 | 로컬 증거 |
| --- | --- | --- |
| P00 | clean main에서 분기, issue 348, 실행 제한 유지 | main 1390ca4d; 브랜치 feat/sns-chat-image-integration; 로컬 source commits 아래 기록 |
| P01 | typed provider/options/scene/reference 계약, 6 API 모델과 NovelAI 모델 catalog | test_contracts.py; 모델별 snapshot fixture |
| P02 | canonical v26, 9개 신규 table 및 3개 기존 table delta, Alembic 20260930_0104 | test_migration.py; v1-v25 predecessor 41 PASS |
| P03 | owner/scope 자산, 정지 이미지 정규화, private pixel read, 용도별 credential | test_assets_privacy.py; 관리 asset과 secret export 제외 |
| P04 | revision/CAS 설정, 자동 생성 OFF와 참조 선호 분리, 개별/설치/인식 상한 | test_contracts.py; test_generation_lifecycle.py; 설정 UI |
| P05 | backend 내부 NovelAI/ComfyUI/NanoGPT/OpenRouter adapter, API workflow/binding/독립 샘플 | test_providers.py; 실제 serializer와 loopback/stub; 생성 실 API 0 |
| P06 | final Routine scene, post+intent 원자 접수, durable job/receipt/result spool | test_generation_lifecycle.py; SNS 최종 호출/오류 분리 7 cases |
| P07 | 공통 인식/cache/공유 job/usage, 4 model/thinking 조합, 별도 credential | test_interpretation.py; R01-R05 실제 Gemini 한 조합 |
| P08 | selected SNS lazy 분석, immutable visual/query snapshot, hint 조건과 FTS 그룹 budget | test_sns_context.py; 기존 Memory/SNS 회귀 |
| P09 | manual SNS 이미지 1장, Chat admission/실제 LangGraph/stream/evidence/cancel 연결 | test_chat_attachments.py; manual SNS 원자/idempotency HTTP |
| P10 | media feature와 composition view slot, Next/static 동일 UI, 실제 설정/첨부/상태, 완료 후 World Feed 읽기 갱신 | 이미지 20 PASS; static 기존 75 PASS; Next dev 기존 35 PASS/10 skip; 마지막 수정 후 양쪽 World social core/error 각2 PASS |
| P11 | startup/shutdown/maintenance, legacy worker 유지, private export/delete 경계 | test_runtime_references.py; 기존 image 61 PASS; 구조/API 검사 |
| P12 | 키 없는 회귀, 허용된 한 조합의 실 인식, 전체 collection/보존, C/T/R 대응과 F 후속 기록 완료 | 4428 collection; 고유4379 PASS/49 SKIP; 보존4428/4428 PASS; 실제 인식5 HTTP. 생성 실 API·USER CHECK·CI·병합은 완료 의미에서 제외 |

첫 로컬 계약 commit 5163ff4c, 구현 commit 13ef6247, World 경계 및 키보드 보정 2bebe219, 최종 SNS scene/비동기 gate 회귀 f5252494, 생성 완료 후 Feed 갱신 0c683b73, 앱별 Chat 이미지 조립 db1542e2. API나 ORM, 함수, 기존 화면의 의도된 변경은 exact committed before/after product-delta 기록으로 검증한다. 새 source/test nodes도 최초 도입 commit의 blob/assertion/suppression을 append-only introduction 기록으로 보호한다. frozen checkpoint나 과거 baseline을 덮어쓰지 않는다.

P01 역사 snapshot에는 nested conftest가 root conftest를 가리는 pytest import 문제가 있었다. 현재 구현은 package marker와 명시적 offline plugin을 제공한다. 역사 evidence collection에서는 immutable Git archive 전체를 importlib 모드와 명시적 test-directory 경로로 수집하며 source/assertion/skip를 바꾸거나 테스트를 제외하지 않는다. Git blob 읽기는 cat-file batch의 object ID와 길이를 검증하여 기존 Git show와 같은 bytes를 제공하는 로컬 cache를 사용했다. 이는 provenance 검사를 생략하거나 현재 tree로 역사 snapshot을 대체하는 절차가 아니다.

## C01-C14 및 T01-T31 자동 검증 대응

아래는 키 없는 계약 검증이다. 실제 생성 품질/비용/서비스 지원 확정은 F01-F06이고, 인식 실 API 한 조합은 다음 R 표에서 별도로 기록한다. 대표 파일 경로는 backend/tests/image_integration 기준이다.

| 계약/검사 | 대표 자동 검증과 확인한 내용 |
| --- | --- |
| C01 / T01 | test_contracts.py 최종 combined SNS transport 4회, 마지막 routine draft에만 scene, OFF schema, 무효 scene과 무효 본문 분리; 기존 combined/routine graph 회귀 |
| C02 / T02 | 빈 외형/스타일/scene, 선택 문자열 조립, provider option 누출 거절; 유효 scene 필수 |
| C03 / T03 | test_runtime_references.py 우선순위/카드 픽셀/프로필/명시 override/손상/없음; OFF는 파일 읽기 0 |
| C04 / T04 | test_providers.py Opus/Tablet/Scroll/만료/credential fresh 검증, 무료 실패 시 유료 대체 0. 실계정 무차감은 F01 |
| C04 / T05 | 무료 필드/steps/면적/1장, paid precise reference, ZIP 픽셀·경로 추출 방지 |
| C05 / T06 | typed API binding, JSON 원본 보존, 입력/출력 노드와 object_info, 텍스트/참조 샘플. img2img 샘플이 얼굴 동일성을 보장한다는 의미는 아님 |
| C05 / T07 | Comfy prompt_id recovery 조회, 불확실 재제출 0, 서버 전체 interrupt 0 |
| C06 / T08 | 각6개 model+endpoint profile의 참조 5개/텍스트/옵션 거절, 빈 endpoint 이용 불가 |
| C06 / T09 | 검증된 provider route pin, fallback 제한, redacted transport 오류, retries 0. 실요금은 미측정 |
| C12 / T10 | 네 provider 접수/동시 worker, 중복 idempotency, lease/attempt, outcome_unknown 무재생성 |
| C12 / T11 | 받은 픽셀 후 DB 실패/recovery, 결과 spool 재사용으로 추가 physical 요청 0 |
| C12 / T12 | source/settings/reference revision 변경, cancel/권한 철회, 늦은 결과 무첨부 및 spool 정리 |
| C07 / T13 | 네 Gemini model/thinking 조합 actual SDK Part shape, 기본 medium; 기존 SNS/Chat high 보존 |
| C08 / T14 | 동시 소비자 job/cache 1회, OFF cache 재사용, 다른 scope/credential 공유 차단 |
| C08 / T15 | 무효 hint에도 설명 유지, failure/unknown 명시, 비신뢰 OCR/시각 evidence 경계 |
| C08 / T16 | upload/후보 목록 인식 0, selected 필요한 문맥만 인식; B/C 분석 공유 |
| C09-C10 / T17 | 선택 때 받은 문맥/late/omitted/fallback/의도-only 분기, query freeze와 hint 1회 |
| C10 / T18 | FTS 24+8/공유 미사용분/총32, 완결 그룹 중복 제거, 128 token/8192 byte/1000 char 한도 |
| C09 / T19 | 기존 hybrid/canonical/graph partial/empty, 재개와 인가 회귀; 신규 immutable snapshot |
| C11 / T20 | 실제 Chat workflow text+image/image-only, 분석 선행, 오류/취소/파일 변경/권한 철회 |
| C13 / T21 | bytes/pixel/위장 MIME/animation/EXIF, owner/World/thread, private StaticFiles 접근 거절 |
| C13 / T22 | 용도별 encrypted key, DTO key 부재, asset/설정/credential World Package snapshot 제외, account scrub |
| C14 / T23 | fresh/v25 populated/v1-v25, 중간 DDL 실패 원본 파일 보존, table digest/FK/legacy 값 |
| C14 / T24 | worker start/stop idempotence, Public 기본 OFF/legacy worker 보존, Next/static stream 기존 검사 |
| T25 | 설정 mode/model/reference/workflow/common recognition/usage와 업로드·제거·전송 사전 차단. 20 browser checks; 완료 후 해당 World Feed GET 한 번, 추가 generation POST 0 |
| T26 | 360/390/436/1440 viewport, 200% body zoom, reduced motion, semantic 폼/접근성, 기존 UI 회귀. 고정 Linux pixel 측정은 제외 |
| C04 / T27 | 네 provider 조건 만족 새 글만 자동 접수, 빈 scene/설정 저장/과거 글 backfill 없음 |
| T28 | 캐릭터/설치/공통 인식 상한 원자 예약, physical attempts/unknown, 날짜 변경 후 backlog 금지 |
| C11 / T29 | OFF/no cache admission 거절·draft 보존, OFF/valid cache 실제 workflow, 분석 중 조건/취소 변경; browser 명시 첨부 제외 |
| C03 / T30 | supported 신규 reference ON, NovelAI free/Z-image OFF, 기존 사용자 선택과 auto OFF 독립 |
| C02-C03-C05 / T31 | reference/외형/스타일 없음의 scene-only path, 필수 reference/text path 없음·손상 오류와 무제출, 자동 provider 대체 없음 |

## R01-R05 승인된 실제 인식 검사

| ID | 실제 결과 | 범위 |
| --- | --- | --- |
| R01 | 파란 원/빨간 삼각형 설명 PASS | public synthetic image; HTTP 1 |
| R02 | 한글·영문 OCR PASS | 파란 컵 123 / ANGMOO 42; HTTP 1 |
| R03 | 동시 소비자 공통 분석 1회 PASS | 동일 analysis ID와 cache; HTTP 1 |
| R04 | 실제 Chat image-only/text+image workflow PASS | 두 임시 Chat DB, Text LLM은 fake; HTTP 2. 이 두 call의 returned usage 미수집 |
| R05 | OFF에서 유효 분석 재사용 PASS | 추가 HTTP 0 |

총 HTTP 5, 16.032초, SDK attempts 1. 허용된 6회/600초 안에서 종료했고 유료 이미지 생성이나 다른 Gemini model로 대체하지 않았다.

## 마감 실행과 재현

최종 제품 source HEAD는 `db1542e2d8774196d13eeabc8bba55e270056051`이다. 이 이후의 마감 변경은 architecture 설명, 재생성 가능한 현재 import/L4 보고서, append-only 보존 근거와 검증 기록이다. 실제 테스트 원본은 저장소의 `artifacts/image-integration/`에 로컬 보존하며 Git에는 작은 sanitized 결과 JSON을 포함한다. 원본 실패 로그를 지우거나 성공 로그로 바꾸지 않았다.

키 없는 backend 실행은 APP_ENV=test, DATABASE_URL=sqlite+pysqlite:///:memory:, GRAPH_PROVIDER=ladybug, LOCAL_RUNTIME_COMPONENT_MODE=in_process, RESIDENT_TICK_SCHEDULER_ENABLED=false, POST_IMAGE_JOB_WORKER_ENABLED=false 및 `tests.offline_guard`를 사용했다. 모든 domain test directory, runtime directory, root-level test file을 각각 전부 실행했다. 그 뒤의 source 변경/실패에 대해 아래 검사를 실행했다.

| 실제 명령/검사 | 원본 결과 |
| --- | --- |
| `uv run --directory backend python -m pytest -q -p tests.offline_guard tests/image_integration` | image-closure.xml; 110 PASS |
| 같은 pytest의 `tests/test_chat_forwarder_retirement.py tests/test_l4_pr_a_inventory.py tests/runtime/test_public_factory_retirement.py` | closure-regressions.xml; 104 PASS/1 현재 import report FAIL; 아래 7-case 재검증으로 해당 node 해결 |
| 같은 pytest의 `tests/test_l4_pr_a_inventory.py` | inventory-closure.xml; 7 PASS |
| `world-scope-final.xml`의 asset/World/cold model registration 대상 검사 | 23 PASS; domain의 cold schema 기대값 실패 해결 |
| `tests/runtime/test_public_factory_retirement.py` 이전 단독 재검증 | factory-last.xml; 51 PASS; runtime 14개 metadata 실패 해결. 최신 app composition 이후 closure run에서도 해당 module PASS |
| `backend/.venv/Scripts/python.exe scripts/ci/generate_architecture_inventory.py --write --check` 및 `check_architecture_boundaries.py` | modules1332/edges5400; 위반0 |
| `generate_l4_pr_a_inventory.py --write --check` | 현재 source와 일치; frozen runtime/installer anchors 보존 |
| 원래 `check_refactor_preservation.main()`의 `--contracts --nodes` | preservation-closure.log; 4428/4428; items37 PASS. 실제 호출은 로컬 `.codex-temp/verify_image_preservation.py`의 immutable Git read cache wrapper |
| `pnpm --dir frontend typecheck`, `lint`, `build`, `build:static` | 각각 completion.log; PASS |
| `pnpm --dir browser-tests exec playwright test --config=playwright.image-integration.config.ts` | browser-completion.log; 20 PASS |
| continuity Next/static config의 `--grep 'UI-D .* World social'` | social-next/static-completion.log; 각각2 PASS |
| `check_frontend_architecture_boundaries.py`, `check_frontend_design_contract.py --check` | features14/legacy edges0; raw colors1230/files36/surfaces18/route gaps0/screenshots16 |

분할과 재검증의 고유 node 합집합은 현재 collection 4428과 정확히 일치한다. 결과 JSON은 각 원본 XML의 SHA-256과 중간 결과를 포함한다. 직접 사용자 확인·Linux pixel 비교·실계정 생성·CI·배포의 결과로 사용하지 않는다.
