# Chat 참가자·과거 관계 근거·Studio World 미리보기 구현 및 검증 결과

작성: 2026-10-11 (Asia/Seoul)
요청 계획: D:/project_code/angmoo-workspace/docs/plan/10-10 Chat 참가자 식별과 World 표시 이름·기억 발화자 연결 코드 구현 세부 계획.md
저장소: D:/project_code/angmoo-workspace/angmoo-tree-angmoo
브랜치: feat/0.1.0-release-readiness
시작 HEAD: 51b73253f73bddc8da3d992e97a52dbb01473007; 시작 working tree clean.

## 1. 판정과 범위

**I00–I51 52단계 구현·필수 검증·결과 기록 완료. 기본 필수 V 20묶음 통과. 선택 V14/V15 미실행.**
I31/I47의 중간 commit은 선택 사항이므로 최종 로컬 commit으로 합쳤다. 이 결과는 구현과 격리/모의 검증이며 실제 AI 품질·원본 Docker/설치 앱 적용·사용자 확인·CI/PR/main 결과를 뜻하지 않는다.

지정 로컬 브랜치에서 작업했다. 실제 API 키·AI·embedding 호출, Docker 재시작/설치 앱 시험, 원본 DB·설정·자율활동을 대상으로 한 변경, remote/push/PR/CI/main merge, 전체 backend/frontend suite 또는 production/static build를 수행하지 않았다. 모든 DB fixture는 격리 시험 자료이며 browser transport도 모의 자료다.

디자인은 **LOCAL**이다. 기존 Memory Dialog·의미 토큰·공용 feature component 및 Studio form/aside를 사용한다. frontend ARCHITECTURE/DESIGN과 backend ARCHITECTURE의 소유권·중립 계약·Runtime 조합·같은 Session/UoW를 적용했다. 권한 검증을 끄거나 전역 설정/새 예외로 검증을 통과시키지 않았다.

## 2. 구현 내용과 보존 계약

- admission에서 NameBinding v1 필드/digest를 그대로 유지하고 typed chat_identity_context.v1을 별도로 고정한다. owner/World/thread/requester/responding 불일치와 존재하는 손상 namespace는 모델/이미지 작업 전에 거부한다. 동일 재시도/재개는 이전 이름, 새 요청은 최신 World 이름이다.
- 최신 질문과 history를 Chat 전용 role/name/content로 전달한다. 사용자 원문에 이미 이름·콜론·코드가 있으면 원문까지 그대로 보존한다. 재직렬화마다 presentation 접두사를 누적하지 않는다. raw source hash와 저장 본문은 변경하지 않는다.
- 선택된 관계·Today SNS·기억 원문을 실제 World 이름과 검증된 작성자로 연결한다. 활동 주체/상대/인용 작성자/생각 소유자를 구분하고, 필요한 실제 선택 항목에만 opaque 참조를 추가한다. 전체 World 인물 map을 모델에 보내지 않는다.
- 하나의 최종 payload가 모델 직렬화와 상황기억/관계 capture에 사용된다. root와 v2 source delivery digest를 실제 serialized prompt에 맞춘다. /latest_user_message/content에서 이름 접두사 제외 raw fragment/span/hash를 인증한다.
- 동일 finalize UoW에 relationship-evidence-delivery.v2를 저장한다. JSON/user-prompt digest와 scope/request/slot/generation/attempt에 결합된 실제 social row/graph excerpt이다. Memory OFF나 receipt 처리 상태와 독립적이다.
- committed 근거의 두 재조회 gate만 교체했다. 전달 proof + 현재 canonical 권한을 확인한 뒤 정상 version/view 상승은 frozen 자료를 available/changed로 표시한다. 생성 중/commit 전 currentness, 권한, source/schema/hash 검사는 유지한다.
- 공개 world-chat-evidence.v1에 상태·안전한 frozen projection·제한 원인만 additive하게 추가했다. 당시 검색 제한/현재 조회 제한/구 응답 원인 미상 안내를 구분한다. 현재 이름/수치/perception으로 당시 자료를 대체하지 않으며 private ID/proof는 노출하지 않는다.
- Studio Home icon 다음 World preview를 모든 폭에서 한 열·내부 가용 전체 폭으로 배치했다. 공용 WorldBanner가 canonical 자산 URL의 인증 조회를 소유하도록 연결했다. 외부 Studio grid·crop/upload/cancel·draft/CAS는 보존했다.

핵심 코드: Chat 계약·generation/workflow/response_steps/relationship_evidence_policy/finalize, Runtime의 names/evidence/episode ports, integrations/llm/chat_input_presentation 및 관련 planner/final adapter, Memory decoder/Inspector/ko-en, WorldCreator의 preview container와 WorldBanner 연결.

## 3. 검증 중 발견·수정

제품 수정:
1. 새 관계 정책 경로와 기존 chat/policies.py module 충돌을 별도 relationship_evidence_policy.py로 해결했다.
2. 상황기억 root payload digest는 prompt인데 source delivery digest는 JSON인 불일치를 실제 adapter→접수→저장 시험에서 발견해 실제 같은 prompt로 맞췄다. 원문/source hash는 변경하지 않았다.
3. episode reader의 지역 import가 기존 함수 이름을 가리는 UnboundLocalError를 기존 상단 import 재사용으로 수정했다.
4. 이름·점수가 같은 다른 관계의 text dedupe를 locator/state/revision으로 구분하여 서로 다른 관계를 유지했다.
5. 미확인 과거 작성자를 현재 requester로 대체하지 않고 unlabelled로 유지한다.
6. 제목만 남는 Today 원문도 verified 작성자로 연결한다. 잘림 밖 link를 제외하고 참가자/다른 section 간 동명이인도 구분한다.
7. Studio 부모가 자산을 blob으로 변환한 뒤 공용 WorldBanner의 canonical URL 검사에서 제외되는 기존 문제가 있었다. 원래 자산 URL을 공용 컴포넌트에 넘겼다. URL 검사를 완화하거나 임의 blob 허용을 추가하지 않았다.

Fixture 수정은 제품 수정과 구분한다. canonical profile 초기화 누락, graph mock의 빈 결과, block 시 기존 Thread 403 기대값, 예외 import, 영어 제목 기대값을 실제 계약에 맞췄다. static dev harness는 Chrome local-network-access 시험 권한을 명시했다. 제품 보안/권한 설정을 바꾼 것은 아니다.

## 4. 실제 최종 검증

| 검사 | 결과 | 범위 |
| --- | --- | --- |
| 직접 관련 backend matrix | **387 passed**, 166.92초 | 아래 23개 직접 소비자 파일. 전체 suite 아님. |
| 추가 이름 회귀 | **23 passed**, 7.48초 | NameBinding/World scope와 실제 Chat admission idempotency·새 요청 개명. |
| 마지막 source/link/receipt 회귀 | **63 passed, 1 skipped**, 16.78초 | 최종 identity/source/관계/저장. 비용 case는 명시 실행으로 분리. |
| 명시 비용 시험 | **1 passed**, 8.34초 | skipped 비용 case를 opt-in으로 별도 실행. |
| frontend Node | **5 passed** | 실제 decoder/status helper·안전한 조합·구 응답·경고·ko/en. |
| 관련 frontend ESLint | **exit 0** | 변경한 실제 feature TS/TSX 5개; 전체 lint/typecheck 아님. |
| scoped browser | **24 passed**, 약 1분 | Next12 + fresh StaticProductRouter dev harness12, ko/en. |
| Python syntax/import 검토 | **53개 syntax 통과**, 새 foreign domain ORM **0** | read-only AST/compile 및 변경 import 검토; CI 실행 아님. |
| diff whitespace | **통과** | 최종 stage 전/후 git diff --check. |

검사들이 중복되므로 합계를 더하지 않는다. 과거 실패 로그는 따로 보존했고, 최종 판정은 수정 후 재검증에 근거한다. Browser는 실제 공용 component/decoder를 사용하지만 **production static export 또는 설치 앱 시험은 아니다**. 모바일 Dialog와 1440px Studio screenshot도 직접 확인했다. 기존 3380 Next dev를 재사용하고 이번 시험용 3381 static dev만 종료했다.

## 5. 입력·조회 비용

원본: [chat-identity-costs-20261011.json](../architecture/evidence/chat-identity-costs-20261011.json).

Windows Python3.13, in-memory SQLite, 같은 최대12+12 committed fixture, graph projection 불가를 고정했다. 전후 모두 **24 available**이다. Baseline 서비스는 시작 commit 51b73253에서 read-only로 읽고 같은 Session/fixture로 실행했다. 이 수치는 격리 관측이며 원본 Docker/설치 앱 latency 보장이 아니다.

| 항목 | 이전 | 변경 후 |
| --- | ---: | ---: |
| 완성 logical JSON bytes | 15380 | 17482 (+13.7%) |
| 내부 objects/keys/depth | 35/107/4 | 48/182/4 |
| system/user UTF-8 bytes | 3609/15515 | 4613/17617 |
| 실제 Gemini 준비/직렬화 표현 bytes | 20356 | 23756 (+16.7%) |
| native objects/keys/depth | 7/12/5 | 7/12/5 |
| input 조립 median/p95 ms,200회 | 0.086/0.093 | 0.193/0.343 |
| 12+12 GET SQL 수 | 403 | 34 |
| GET median/p95 ms,20회 | 152.008/183.463 | 18.476/20.801 |
| 공개 DTO bytes | 11980 | 11296 |
| available items | 24 | 24 |

새 private proof는 **21526 bytes**다. typed 계약 상한은 24개/80KiB다. 선택 이름 lookup은 1 ID/같은 ID100회/다른12 ID 모두 **2 SQL**이다. 최대20 history/8,000자에 80자 Unicode 이름 접두사 비용을 포함한다.

완성 mixed input에 관계12개, history20개, graph/episode/Today evidence 총12개, 최신 질문을 포함했다. native 이름/message parts나 response/tool schema를 추가하지 않았다. 이 기능의 추가 AI/embedding/provider HTTP 호출은 **0회**다. 실제 token 비용과 AI 답변 품질은 미측정이다.

GET의 INSERT/UPDATE/DELETE 부재, SNS packet 동일성, 원문/source hash, legacy 읽기, 실패 commit rollback, Memory OFF/설명 누락/저장 포기 후 Chat proof 보존을 확인했다. 새 관계 이력 table/migration/과거 DB 재작성/재임베딩은 없다.

## 6. I00–I51 ledger

| 단계 | 상태 | 수행 내용 |
| --- | --- | --- |
| I00 | 완료 | 실제 브랜치·HEAD·dirty 확인 |
| I01 | 완료 | 아키텍처·디자인·검증 범위 |
| I02 | 완료 | raw/name/router/source 전달 경로 추적 |
| I03 | 완료 | typed chat_identity_context.v1 및 legacy 계약 |
| I04 | 완료 | admission의 owner/World/thread/1:1 참가자 고정 |
| I05 | 완료 | 순수 role/name/content presentation |
| I06 | 완료 | Unicode·escape·제어 문자·80자 이름 정책 |
| I07 | 완료 | 선택 ID의 effective World 이름 batch |
| I08 | 완료 | 참가자 override와 요청 내 이름 재사용 |
| I09 | 완료 | 진행 요청·재개·재시도의 frozen 이름 |
| I10 | 완료 | router/Supervisor 참가자 context |
| I11 | 완료 | 활성 검색 모드의 참가자·typed selector 일치 |
| I12 | 완료 | 응답자 관점·인용·출력 본문 지침 |
| I13 | 완료 | 최신 질문·history 객체화와 raw 보존 |
| I14 | 완료 | 관계 snapshot 전 이름 정책 통일 |
| I15 | 완료 | 현재 requester·section 간 동명이인 최소 links |
| I16 | 완료 | Today actor/counterpart·제목/본문/parent/root 작성자 |
| I17 | 완료 | 원본 Post/Thread role의 중립 작성자 port |
| I18 | 완료 | Chat 전용 verified 원문 author_ref |
| I19 | 완료 | 템플릿·생각 소유자·이미지 발신 경계 |
| I20 | 완료 | 최종 payload builder의 공동 사용 |
| I21 | 완료 | 새 질문 경로의 raw fragment/hash/span |
| I22 | 완료 | history/image/episode/Today fragment와 잘림 |
| I23 | 완료 | legacy namespace/hash/normalization/SNS 회귀 |
| I24 | 완료 | 공개 additive DTO·실제 소비자 확인 |
| I25 | 완료 | Memory ko/en 문구 소유권 |
| I26 | 완료 | V01–V10 참가자·출처·저장 모의 회귀 |
| I27 | 완료 | V11 완성 입력·batch 비용 측정 |
| I28 | 완료 | V12 native schema·공유 소비자·import 검토 |
| I29 | 완료 | 실제 변경 frontend 관련 검사 |
| I30 | 완료 | 참가자 구현·비용·미관찰 결과 기록 |
| I31 | 완료 | 참가자 checkpoint diff 검토 — 선택 중간 commit은 최종 로컬 commit으로 합침. |
| I32 | 완료 | 생성/commit currentness와 두 재조회 gate 분리 |
| I33 | 완료 | legacy 복구 가능한 증명과 부족한 기록 구분 |
| I34 | 완료 | 관계 전달·현재 access·변경 상태 typed 계약 |
| I35 | 완료 | 실제 final social row/graph fragment capture |
| I36 | 완료 | 동일 finalize UoW·scope/slot/generation/attempt |
| I37 | 완료 | 손상 거부·retained legacy read-only 복원 |
| I38 | 완료 | 현재 canonical 권한의 bounded 같은 Session batch |
| I39 | 완료 | committed 두 gate 교체·정상 8→9 changed |
| I40 | 완료 | 변경 상태·생성 제한·현재 제한 DTO 분리 |
| I41 | 완료 | 엄격 decoder·두 section·구 응답 fallback |
| I42 | 완료 | frozen 이름·수치·perception만 표시 |
| I43 | 완료 | Memory ko/en·Dialog/scroll/focus 유지 |
| I44 | 완료 | V16–V19 backend 회귀 |
| I45 | 완료 | V13/V20 frontend·수명·언어 회귀 |
| I46 | 완료 | V21 SQL/byte/읽기 지연·추가 호출 0 측정 |
| I47 | 완료 | Chat checkpoint diff 검토 — 선택 중간 commit은 최종 로컬 commit으로 합침. |
| I48 | 완료 | Studio 공용 preview·외부 grid·사진 범위 확인 |
| I49 | 완료 | 모든 폭 한 열 Home icon→World 전체 내부 폭 |
| I50 | 완료 | V22 반응형·등록/실패 배너·사진 기능 검증 |
| I51 | 완료 | 전체 ledger·최종 검토·지정 브랜치 로컬 commit |

## 7. V01–V22 ledger

| 검증 | 상태 | 실제 근거·한계 |
| --- | --- | --- |
| V01 | 통과 | owner/World/thread 불일치와 유효 digest 변조도 provider 전에 실패 |
| V02 | 통과 | World override·개명·idempotency는 frozen 이름, 새 요청은 새 이름 |
| V03 | 통과 | role/name/content·인용/colon/code/짧은 발화·20개/8K 제한·raw hash |
| V04 | 통과 | 한국어/영어·Unicode/emoji/따옴표/제어 문자 data 정책 |
| V05 | 통과 | outgoing requester 및 section 간 동명이인 다른 ID를 opaque ref로 구분 |
| V06 | 통과 | Today actor/counterpart와 제목/본문/parent/root 작성자·잘림 link |
| V07 | 통과 | 원본 Thread role/Post author, 다른 현재 requester, changed/missing source |
| V08 | 통과 | 새 객체 질문·응.·반복 이름·이미지에서 접수→수동 저장→원문 확인 |
| V09 | 통과 | router/planner/Supervisor/final participant·typed selector·활성 mode |
| V10 | 통과 | v1/v2 read/replay, NameBinding, SNS packet 및 shared hash |
| V11 | 통과 | 완성 mixed 입력 logical/native 크기·조립·선택 이름 batch SQL |
| V12 | 통과 | Google native 문자열 prompt/parts, response/tool schema·provider mock·새 foreign ORM 0 |
| V13 | 통과 | 실제 변경 TS/TSX 5개 ESLint, Node5, ko/en·공용 browser |
| V14 | 미실행·선택 | 실제 키 사용 요청 없음; 실제 AI의 이름/인식 활용 품질 미관찰 |
| V15 | 미실행·선택 | 실제 Docker/설치 앱 적용/재시작/설치 시험 미실행 |
| V16 | 통과 | current_context/items, 정상 commit 후 8→9/view 변화와 생성 중 변경 차단 |
| V17 | 통과 | 다른 binding의 재계산 digest, 삭제/moderation/membership/block/낮은 version 거부 |
| V18 | 통과 | sufficient/insufficient legacy, Memory OFF/pending/applied/blocked/discarded/rollback |
| V19 | 통과 | changed-only 경고 없음·실제 생성 검색 제한/현재 불가/legacy fallback 분리 |
| V20 | 통과 | ko/en 전환·World/thread/request/닫기 늦은 응답·focus trap/return·내부 scroll |
| V21 | 통과 | 동일12+12 SQL/시간/DTO/proof bytes·read-only·추가 provider/embedding0 |
| V22 | 통과 | Next/static ko/en,360/768/1440+resize,default/registered/failed banner,crop/cancel/409/draft |

## 8. 재현 명령

backend 디렉터리에서 직접 실행했다. 아래 matrix 실행 당시 비용 case 포함 387 passed였다. 이후 일반 회귀/향후 CI가 과거 Git baseline을 요구하지 않도록 비용 case는 명시 opt-in으로 분리했다. 아래 비용 명령으로 그 case를 별도 실행한다.

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
& '.venv/Scripts/python.exe' -m pytest tests/chat/test_chat_identity_delivery.py tests/chat/test_chat_identity_sources_costs.py tests/chat/test_activity_situation_receipt.py tests/chat/test_response_name_binding.py tests/chat/test_evidence_ownership.py tests/chat/test_social_context_workflow.py tests/chat/test_p8_l_p_evidence_response_streaming.py tests/chat/test_response_supervisor.py tests/chat/test_p8_l_k_retrieval_router.py tests/chat/test_p8_l_l_canonical_retrieval_planner.py tests/chat/test_p8_l_m_graph_retrieval_planner.py tests/chat/test_p8_l_p_high_reasoning_hotfix.py tests/chat/test_episode_activity_thought.py tests/test_p8_l_r_today_sns_activity.py tests/relationships/test_social_context.py tests/relationships/test_social_context_validation.py tests/memory/test_episode_packets.py tests/memory/test_episode_packet_repository.py tests/memory/test_episode_hybrid_reader.py tests/memory/test_episode_social_sources.py tests/memory/test_situation_proof_guards.py tests/test_provider_adapters.py tests/integrations/test_direct_llm.py -q
& '.venv/Scripts/python.exe' -m pytest tests/chat/test_response_name_binding.py tests/characters/test_name_binding.py tests/characters/test_name_binding_scopes.py -q
& '.venv/Scripts/python.exe' -m pytest tests/chat/test_chat_identity_delivery.py tests/chat/test_chat_identity_sources_costs.py tests/chat/test_activity_situation_receipt.py -q
$env:ANGMOO_MEASURE_CHAT_IDENTITY_COSTS='1'
& '.venv/Scripts/python.exe' -m pytest tests/chat/test_chat_identity_sources_costs.py::test_bounded_input_and_relationship_read_costs -q
```

frontend:
```powershell
node scripts/test-chat-evidence.mjs
& './node_modules/.bin/eslint.cmd' src/features/memory/api/memory-client.ts src/features/memory/types/memory-contract.ts src/features/memory/utils/chat-evidence-presentation.ts src/features/memory/components/world-chat-evidence-inspector.tsx src/features/worlds/components/world-creator-client.tsx
```

browser-tests:
```powershell
& './node_modules/.bin/playwright.cmd' test --config=playwright.chat-identity.config.ts
```

3380 Next dev와 3381 static-shell dev가 필요하다. 후자는 frontend/static-shell에서 NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE=tauri-static 설정 후 ../node_modules/.bin/next.cmd dev --hostname 127.0.0.1 --port 3381로 준비한다. 시험 config의 browser permission 및 fixture의 root document fallback을 사용하며 실제 StaticProductRouter가 원래 URL을 읽는다. API/provider는 전부 synthetic transport다.

로그/screenshot/비용 원본: D:/project_code/angmoo-workspace/angmoo-tree-angmoo/artifacts/chat-identity-20261011/. 핵심은 final-backend.log, name-readiness.log, final-source-links.log, explicit-costs.log, frontend-node.log, frontend-eslint.log, browser-verified.log, changed-sources.log다. artifacts는 ignored이며 이 결과 문서와 비용 JSON은 로컬 commit에 보존한다.

## 9. 미관찰

V14 실제 AI 답변 품질, V15 실제 Docker/설치 앱 적용, 실제 사용자 화면 확인은 수행하지 않았다. 실제 모델이 requester/perception을 자연스럽게 활용한다는 품질 판정은 모의 검증으로 대체할 수 없다. 계획의 기본 구현 단계에 남은 필수 작업은 없다.
