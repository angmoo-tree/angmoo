# World 캐릭터 UI·API 키·SNS/Chat 32활동 상황기억 통합 검증

검증일: 2026-10-06–07, Windows / PowerShell / Python 3.13 / local Chromium.

**이전 실행 판정(HEAD `6c862f04`): I00–I49 50단계의 로컬 구현·기술 검증 완료 — LOCAL TECH PASS.** 마지막 일반 CLI의 backend/API/ORM/assertion 보존 검사도 종료 코드 0으로 통과했다. 실제 AI 품질, 네이티브 검색 성능, 설치판 검수를 로컬 PASS에 포함하지 않는다.

**2026-10-07 후속 재검토에서 수명·오류·준비 상태의 누락을 발견해 보완했다.** 이 문서의 수치와 단계표는 이전 실행의 기록이다. 현재 코드의 보완 내용과 재검증은 [후속 누락 재검토 보고서](./world-ui-memory-batch32-audit-20261007.md)에 기록한다.

## 실행 경계와 기준 보존

- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `feat/0.1.0-release-readiness`. 시작 HEAD `c1fdd2ff7cd4aeb1c6cbd0d20bcf1c9f187fe115`, 시작 working tree clean. 실제 branch guard를 커밋 직전 반복했다. 활성 Git hook은 없고 sample만 있었다.
- upstream `[gone]`은 유지했다. fetch/pull/branch 변경, push, PR, 원격 CI, main 반영을 하지 않았다.
- 사용자 port 3000, 설치판/Docker, 실제 사용자 DB·파일·키·대화·관계 자료, 다른 worktree를 사용하거나 전환하지 않았다.
- backend는 `ANGMOO_DENY_EXTERNAL_NETWORK=1`, 격리 SQLite, 합성 자료, fake provider/SDK로 검증했다. 실제 generation/auth/tokenizer/embedding provider 호출은 0회다.
- browser는 Next `127.0.0.1:3338`, static `127.0.0.1:3339`의 독립 preview와 합성 API fixtures를 사용했다. 검증 후 해당 preview를 종료했다. 사용자 서버로 대체하지 않았다.
- 원본 계획 3개는 수정하지 않았다. SHA256: 통합 `7E2B853880D676A4156E34E276A6F54F9E738A151A041B1534CBE5FEF8F8482C`, Memory 원본 `85B9B17E1F857D2CC2F5296AA44A2F4FB25F469D78410512FA78498AD05C7EC9`, UI 원본 `FB6F1917E0F485F63DD890330EE94FF5CE26891DE541AC6BCABA1D773C2AC400`.
- 공식 domain/runtime/integration 소유권·현재 Session·정식 migration 경로를 사용한다. GET backfill, 전역/다른 캐릭터 키 fallback, 별도 임시 persistence, SDK 중복 호출, 역사 baseline 덮어쓰기를 구현에 사용하지 않았다.

## 구현 결과와 실제 소비자

1. `domains/identity/service/world_credentials.py`, `runtime/world_credential_binding.py`: 여섯 목적의 World/actor/owner 직접 키, write-only 비밀, revision CAS, 접수된 유효한 과거 revision, 명시적 폐기. 키 교체는 이미 접수된 작업을 새 키로 바꾸지 않으며 명시적 폐기는 과거 revision도 폐기한다.
2. `runtime/world_characters/credentials.py`, `runtime/chat/generation_workflows.py`, `runtime/media/world_generation.py`, `runtime/media/world_vision.py`, `runtime/memory/*`, `runtime/relationships/review_credentials.py`: SNS/Chat/image/vision/consolidation/embedding의 실제 접수·provider·복원·적용에 연결했다. 기억·관계 정리는 subject 정리 키, 검색은 별도 embedding 키를 사용한다.
3. `domains/media/service/world_policy.py`: 신규 actor 생성 20회, SNS/Chat 합산 인식 10회와 actor별 예약/시도 ledger. 미제출 해제 예약은 소비하지 않고 제출·불확실·실패는 기존 소비 의미를 유지한다. 키/모델 교체 뒤 당일 소비를 유지하고 GET가 legacy null/0을 기본값으로 바꾸지 않는다.
4. 공식 SQLite v30와 Alembic `20261006_0107`: 160 tables, 7개 additive tables, batch run의 nullable admitted credential 필드. v28/v29와 역사 지문은 그대로다. v30 digest `620b8313a454d3d7be49a24e54c8d0c0e039cf5f92456b5a2299f59de8015032`. 새 tables는 `world_credentials`, `world_credential_revisions`, `world_image_policies`, `world_image_attempts`, `memory_subject_profiles`, `memory_index_preparations`, `memory_episode_restrictions`다.
5. `runtime/world_characters/instance_deletion.py`: 현재 World 인스턴스 하나의 private 자료·여섯 키·준비 자료·늦은 결과를 정식 owner 경계에서 정리한다. 공개 글·답글·첨부·삭제 저자 표시, 다른 World/owner/살아 있는 기준을 보존한다. commit 후 파일 정리 실패는 재시도 가능하다.
6. `contracts/activity_batch.py`, `policies/activity_bundles.py`, `service/episode_manifest.py`, `service/episode_selection.py`: 최대 32활동, Chat 활동당 신규 30턴과 앞선 5턴, 최대 960 신규 턴/160 문맥 참조, 요청 전체 prior 8개, S/C/P coverage, versioned manifest, 정상 1회 fake generation, 예외 계보 합계 자동 3시도.
7. `repository/episode_privacy.py`, `policies/retrievability.py`, `repository/episode_apply.py`, `runtime/memory/vector_projection.py`: 모델이 제외한 private 입력도 모든 결과의 접근 제약으로 유지한다. public split 자식도 원래 root의 모든 source/private 제약을 유지한다. apply/recall/prior/Hot Brief/FTS/vector/cache/export에서 현재 원본과 권한을 다시 검사한다.
8. 공통 `settings-card.tsx`, `status-cards.tsx`와 feature-owned World/Memory 카드: 코랄 원·흰 아이콘·큰 제목·짧은 부제, 기존 semantic status/danger/disabled/focus, 실제 공통 표시 소비자를 유지한다. Device와 World의 상태 표시를 같은 컴포넌트로 연결했다.
9. World sticky 헤더/탭, 상단 back/refresh·빈 gutter 제거, 유형→지역화한 역할 태그, 최근 활동→설명 우선 페르소나→reply/post/like 요약. ON과 실제 running을 구분하고 조회는 SDK나 쓰기를 호출하지 않는다.
10. World 10카드 순서: 페르소나 → 활동 설정 → SNS text 키 → SNS 이미지 생성 → Chat 키 → 인식 키/상한 → 관심 주제 → 활동 방식·현재 상태 → 오늘 하루 계획 → 인스턴스 삭제. 제외한 네 legacy 카드를 가져오지 않는다. 전역 화면 언어는 기존 위치에서 디자인을 정리한다.
11. 카드별 edited-field PATCH/CAS·충돌 시 초안 유지·다른 초안 보존·auth/runtime/owner/World/actor/abort/epoch 수명·비밀 입력 폐기를 연결했다. /memory 두 목적 키는 각각 직접 입력하며 foreign picker/list를 사용하지 않는다.
12. `memory-client.ts`, `memory-embedding-controls.tsx`: 일반 저장/ON/GET는 역사 전체 검색 자료 준비를 실행하지 않는다. 별도 준비 시작은 저장된 snapshot·scoped URL·idempotency·실패/재시도/폐기/삭제 fence를 사용하며 정상 증분 갱신은 유지한다.
13. 기존 5단계 생성 기능·PNG/JSON 카드 원문·복사·external·초안·returnTo·OFF 등록·실제 업로드/자르기/취소/복원을 유지했다. 참고 사진의 API 인증이나 여섯 번째 분석 기능을 추가하지 않았다.
14. 관계망은 기존 query/source/fallback 계약과 모든 avatar/name/방향을 유지한다. 헤더→하루 정리→지도→방향별 목록→조건부 근거로 배치한다. 긴 관계 설명은 목록에 기본 표시하고, 결정적 layout의 실제 DOM bounding boxes로 긴 이름의 겹침을 검사했다.

## 실행 증거 묶음

숫자는 각 명령의 실제 결과다. 중복 회귀가 있으므로 합산해 고유 테스트 총수로 부르지 않는다. 실패한 중간 실행은 최종 PASS에 섞지 않았다.

| 증거 ID | 실행과 실제 결과 | 근거 |
| --- | --- | --- |
| E-MEM | Memory 전체 **432 PASS / 18 SKIP**, 362초 | `backend/integration-memory-diagnostic-2.log` |
| E-CHAT | Chat 전체 + autonomous graph + resident dependency + activity limits **893 PASS / 6 SKIP**. 최종 native scope port 수정 후 같은 묶음을 189.55초로 재검증 | `backend/integration-chat-runtime-complete-final.log`, `backend/integration-chat-native-port-final.log` |
| E-CONTRACT | 공식 startup/restart·v30/historic/parity·native keys·32활동/960턴·private split·명시 준비 **49 PASS**, 182초 | `backend/integration-final-contracts-3.log` |
| E-AUTO | 실제 SQLite 세션·시간대·ON/OFF·capacity·동시 접수·membership·lease·manual guard **23 PASS**, 152초 | `backend/integration-autonomy-diagnostic-2.log` |
| E-SCOPE | Chat 삭제·World configuration **33 PASS**, 140초 | `backend/integration-chat-scope-diagnostic-2.log` |
| E-DIAGNOSTIC | 별도 opt-in의 fake-provider 성능/동시 진단 **8 PASS**, 43초. 일반 회귀에서 skip했던6건도 포함하며 실제 서비스/AI 성능으로 해석하지 않음 | `backend/integration-diagnostic-fake-benchmark.log` |
| E-LIFE | 기존 World navigation/keyboard/초안·동시 CAS·older GET·runtime 갱신·늦은401·로그아웃 응답 **static 5 PASS**, 7.6초. 카드 분리 후 persona card만 지정하도록 selector 2개를 수정하고 기존 행동 단언을 유지 | `frontend/integration-browser-lifetime-static.log` |
| E-RETIRE | 고정 410·전후 AST·원래 HTTP frame을 검증하는 정상/거부 10건과 원래 SQLite/replay 2건 **12 PASS**, 4.55초. Chat 실제 생성·route·DI·transaction 보존 증명의 전체 실행도 PASS | `backend/integration-chat-retirement-final-tests.log`, `backend/integration-chat-retirement-final-proof.log` |
| E-FOUNDATION | 초기 policy/contract/work/apply **48 PASS**; 이후 E-MEM/E-CONTRACT로 통합 재검증 | 초기 기록 및 위 최종 묶음 |
| E-COMPLETE | 초기 identity/world/media/image/migration 광범위 실행 **894 PASS / 24 SKIP / 11 FAIL**. 11개 최신 metadata count/head/최종 전환 기대는 v30 계약으로 수정 후 E-CONTRACT에서 모두 재검증 | `backend/integration-complete-backend.log`; 전체 PASS로 표기하지 않음 |
| E-NEXT | World9 + 긴 이름 graph6 + 기존 graph3 + creator11 = **29 PASS**. Memory/graph 보완 **7 PASS**, 영어 생성 **1 PASS**, 실제 crop **1 PASS**, 기존 avatar/profile **5 PASS** | `frontend/integration-browser-next-final-complete.log`, `integration-browser-next-completion.log`, `integration-browser-next-english-complete.log`, `integration-browser-next-crop-final.log`, `integration-browser-avatar-next.log` |
| E-STATIC | 초기 **54 PASS / 5 FAIL**. 보존 보완 실행은 **4 PASS / 1 FAIL**이며 남은 생성 제목 기대도 수정했다. 최종 World/graph/title/무제한 생성 **17 PASS**, 영어/crop **2 PASS**, 기존 avatar/profile **5 PASS** | `frontend/integration-browser-static-complete.log`, `integration-browser-static-preservation-complete.log`, `integration-browser-static-final.log`, `integration-browser-static-english-crop-complete.log`, `integration-browser-avatar-static.log` |
| E-FE | 전체 lint **0 errors/0 warnings**, clean tsconfig typecheck PASS, catalog **2609 keys/16 namespaces**, error contracts **53 PASS**, Next production/static build PASS | `frontend/integration-full-lint-complete.log`, `integration-typecheck-clean-complete.log`, `integration-catalog-complete.log`, `integration-next-build-final.log`, `integration-static-build-final.log` |
| E-ARCH | **1434 modules/6045 internal edges/4194 external imports**, legacy exact edges **0**. native scope port 수정 후 공식 generator/checker 재검증 PASS. Frontend14 features/legacy0. Design **1183 raw colors/35 files/18 surfaces/gap0/screenshot calls40** | `backend/integration-architecture-final.log`, `backend/integration-architecture-native-port.log`; 공식 frontend architecture/design checkers |
| E-PRESERVE | 일반 CLI **5478/5478 protected lineages·37 items PASS, exit 0**. Frontend **324 source files 및 기존 browser assertions/fixtures/assets/locks PASS**. Exact AST/assertion/API/ORM/frontend hash 변경과 append-only source/test introduction 검증 | `backend/integration-preservation-canonical-final.log`, `backend/integration-frontend-preservation-native-port-complete.log`; `security/post_refactor_contract_changes.json`, `security/refactor_backend_additions.json` |

Browser 증거는 `artifacts/world-memory-integration-20261006/`, 기존 avatar suite는 `artifacts/world-character-management-20261005/*-integration-final/`이다. 합성 payload와 로컬 진단 사진이며 사용자 실제 자료가 아니다.

## 검증 범위와 미측정 항목

- Memory 18건은 필요한 Vec1 확장이 없어 SKIP했다. durable fake index로 privacy/generation/profile/prepare/delete/lifecycle을 검증했지만 네이티브 확장 실행이나 근접 검색 품질을 PASS로 표시하지 않는다. Chat 6건은 `ANGMOO_DIAGNOSTIC_BENCHMARK=1`을 요구하는 진단이며 일반 회귀에서는 SKIP, 별도 fake-only 실행 E-DIAGNOSTIC에서 모두 PASS했다.
- M-TECH의 문자/UTF-8/추정 token/출력/attempt/timeout 구현 경계는 fake로 확인했다. 실제 Gemini 4모델 capability, 공식 tokenizer, 비용·AI 기억 품질·p95는 **REAL AI NOT MEASURED**다.
- Windows 구조/동작/overflow/실제 bbox/사진은 host 증거다. 공식 Linux pixel baseline은 덮어쓰지 않았고 **CANONICAL PIXEL NOT RUN**이다.
- 추가 E-LIFE의 Next production preview 시작은 실행 도구가 `blocked by policy`로 거부했고 상세 이유는 제공되지 않았다. 그 명령을 재시도하지 않았다. 기존 Next E-NEXT는 PASS이며, 추가 수명 검증은 이미 만든 static을 이용해 E-LIFE로 따로 수행했다.
- I50/I51 보류. **ROLLOUT PENDING / INSTALLED NOT CHECKED / USER CHECK PENDING / Docker·PostgreSQL·PR·remote CI·push·main merge NOT RUN**.
- Deprecation warnings는 별도 기록했다. 테스트의 skip/xfail 조건이나 역사 단언을 완화하지 않았다.

## 발견·수정 후 재검증

- public split 자식이 private root 제한을 놓치는 문제를 root access manifest의 복원/적용/소비로 수정했다. fake 3호출, 결과 2개 모두에 root33 source/private 제약을 보존하는 실제 SQLite 검증을 추가했다.
- embedding 대기 중 원본 삭제 문제를 SDK 밖 canonical writer fence와 같은 Session 재조회로 막았다. 삭제 후 늦은 vector 적용이 private 자료를 복구하지 못한다.
- idle slot에 접수 manifest를 미리 저장하는 문제를 없애고 실제 lease/admission 때만 freeze한다. 기존 실제 세션 23건을 다시 실행했다.
- 부족한 resident exception import를 기존 dependency 검사가 잡았고 수정했다. legacy 테스트 데이터에는 자신의 native 목적 키를 명시 등록했으며 제품에 shared fallback을 복원하지 않았다.
- Memory 준비 시작의 unscoped URL을 feature-owned scoped client로 수정하고 Next/static owner control을 재실행했다.
- crop 합성 PNG decode 실패는 유효한 PNG fixture로 수정했고 실제 canvas→WebP, 취소·저장·reload를 두 환경에서 확인했다. static 영어 생성은 실제 완료 heading을 기다린 뒤 fixture를 확인한다.
- 첫 전체 lint 오류는 생성 `.next-*` 717파일에서만 발생했다. 격리 dist도 일반 Next 생성물처럼 제외하는 제한된 glob을 추가했다. 제품 source 규칙/경고는 억제하지 않고 전체 lint를 다시 실행했다.
- 기존 browser select→radio 계약·짧은 설명·접힌 provider 정보 기대는 실제 UI에 맞췄다. 무제한 생성·raw metadata·provider 정보·scope·원문 등의 기존 행동 predicate는 보존하고 전후 hash/AST를 append-only로 기록했다.
- 최종 Backend 보존 검사에서 Chat 실제 서비스 생성의 불변 계약과 충돌했다. 임의 생성자 reader 주입을 제거하고 기존 Chat scope 조회 포트에 직접 키 모델 조회를 선언·연결했다. 원래 composition AST와 동일함을 확인하고 E-CHAT 893건을 재실행했다. 최초 실패에서 표시된 5468개 introduction 오류는 이 선행 검증 중단으로 보호 대상이 비워져 생긴 연쇄 출력이며 별도 정상 결과로 합산하지 않는다.
- 공용 Chat 키 저장 함수의 계획된 폐기 응답은 고정된 `410 / world_character_settings_required`와 기록된 전후 AST를 함께 검증한다. 원래 함수의 인자·decorator·DI 및 다른 HTTP endpoint/import는 계속 완전히 같아야 한다. 실제 키 쓰기·임의 승인·잘못된 상태/사유·권한 의존성·response model·다른 endpoint·foreign import를 허용하지 않는 보존 계약 테스트 10건을 추가했다. 역사 anchor/checkpoint/path map을 교체하지 않았다.
- 이어진 전체 검사에서 새 assertion 증거가 collected pytest의 `tests/...` 대신 `backend/tests/...` ID를 사용한 생성 도구 오류를 발견했다. 기존 record는 유지하고 core commit의 동일한 source blob·전후 assertion 17개를 canonical ID로 append했다. source 12개의 Git 원본 검증을 통과했으며 단언·코드·역사 기준을 바꾸지 않았다. 이 수정 전 전체 실행도 FAIL 기록으로 보존한다.
- canonical ID 보완 후 동일 전체 검증 논리를 immutable Git 읽기 cache로 실행한 진단은 `integration-preservation-canonical-diagnosis.log`에 PASS로 남겼다. 최종 Gate는 별도 일반 CLI `check_refactor_preservation.py --contracts --nodes`이며 `integration-preservation-canonical-final.log`에서 5478/5478·37 items·exit 0을 확인했다. 진단 실행을 일반 CLI의 종료 결과로 대체하지 않았다.

## 최종 Gate와 로컬 커밋

| Gate | 상태 |
| --- | --- |
| architecture inventory / backend boundaries | PASS |
| frontend architecture / design 현재 측정 | PASS |
| full lint / typecheck / catalog / error contracts | PASS |
| Next production / static build | PASS |
| 격리 SQLite/fake / Next+static 회귀 | 위 증거 범위 PASS; native SKIP 별도 |
| backend/API/ORM/assertion preservation | PASS: 일반 CLI protected lineages 5478/5478, items37, exit0 (`backend/integration-preservation-canonical-final.log`) |
| frontend preservation | PASS: 324 source files, 기존 browser assertions/fixtures/assets/locks 보존. 최종 source 변경 뒤 재실행도 PASS (`backend/integration-frontend-preservation-native-port-complete.log`) |
| diff / 계획 hash / branch / final clean tree | diff/원본 계획3개 hash/지정 branch PASS. 마지막 metadata 커밋 후 actual HEAD와 clean tree는 아래 `final-closeout.json`에 별도 기록 |

구현 로컬 커밋:

1. `66995f46a6cca642421ed944c43663b7ca8834f4` — backend 키/schema/실제 소비자/private batch32/회귀.
2. `2b9956766c51a766d3694585839a12fae62948ce` — 공통 UI, World/Memory/생성/관계망, ko/en, browser 검증.
3. `26a2b7d28a6714a8d25280d2c19d5109dd4d900b` — 정확한 introduction/contract 변화·현재 design 측정·통합 보고서. 보고서 최초 introduction도 공식 helper로 기록한다. 최종 Gate 결과는 뒤따르는 로컬 metadata 커밋에 포함하고 최종 HEAD를 별도로 확인한다.

4. `8cfc8dc1f9c397aea08fd66ac65f75bc62479492` — E-LIFE의 기존 테스트 조작 2개를 persona card에 지정했다. 행동 단언은 유지했고 정확한 frontend preimage/postimage를 기록했다. 별도 static 5건으로 검증했다.

5. `4245b9bd707350b3f0a698c0fb850c0eee1a4470` — World Chat native 모델 조회를 기존 scope 포트로 이동해 원래 실제 서비스 생성 계약을 복원했다. 공식 현재 import inventory를 갱신했고 E-CHAT/E-ARCH를 재검증했다.

6. `45357fb93e8e829bd67d54fb861f1baa42b0f931` — 공용 Chat 키 저장 폐기 계약의 고정 410/전후 AST/HTTP frame 증명과 10건의 정상·거부 검증을 추가했다. 원래 durable transaction test 본문은 그대로 복원하고 native key 준비를 같은 caller Session의 fixture로 선언했다. 새 source1/node10을 공식 introduction helper로 기록했다.

7. 최종 metadata 로컬 커밋 — 이 보고서와 기존 두 증거 파일의 append만 포함한다. 검증 후 제품 소스나 테스트 단언을 추가로 변경하지 않았다. 자기 자신의 SHA를 문서에 포함할 수 없으므로 커밋 후 실제 branch/HEAD/clean tree/일반 CLI 종료 결과/계획 hash는 `artifacts/world-memory-integration-20261006/final-closeout.json`에 기록한다. 이 파일과 실행 로그는 ignored 로컬 검증 산출물이다.

증거 변화는 기존 record를 고치지 않고 append했다. backend: source190/definition279/assertion17/API·DTO48/ORM8, introduction45 sources/48 pytest nodes. UI: source78/frontend hash53, introduction22 sources. 공식 helper가 commit의 실제 collection과 source blob을 기록한다. frozen checkpoint/path map/historic migration은 교체하지 않는다.

추가 수명 증거는 source1/frontend hash1, Chat scope 이동은 source6/definition6, Chat 폐기 증명·fixture 정리는 source3/definition1이다. 이 세 추가 변경은 기존 assertion predicate/API/ORM을 바꾸지 않았다. introduction 기록은 보고서 source1과 새 보존 검증 source1/node10도 포함한다. canonical pytest ID 보완 source12/assertion17은 원래 core의 같은 단언이며 새로 바꾼 17개의 단언으로 중복 합산하지 않는다. 총 6개의 신규 contract-change record와 4개의 신규 introduction record를 기존 prefix에 append했다.

시작 HEAD와 JSON 구조를 대조해 contract-change의 기존 165 record와 introduction의 기존 354 record가 각각 현재 171/358 record의 변경 없는 prefix임을 확인했다. 보고서의 I00–I49 50개, 계약 124개, 기술값 7개, 검증 의무 160개의 고유 ID, 원본 단계 68개와 관계망 단계 6개를 따로 확인했다. 이 대응표는 실제 실행 로그와 구현 소유자를 연결하며 160개의 새 독립 테스트가 모두 실행됐다는 뜻이 아니다.

## 재시작과 재검증 명령

```powershell
Set-Location 'D:/project_code/angmoo-workspace/angmoo-tree-angmoo'
if ((git branch --show-current).Trim() -ne 'feat/0.1.0-release-readiness') { throw 'Unexpected branch' }
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
& 'backend/.venv/Scripts/python.exe' scripts/ci/generate_architecture_inventory.py --check
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_architecture_boundaries.py
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_frontend_architecture_boundaries.py
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_frontend_design_contract.py --check
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_refactor_preservation.py --contracts --nodes
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_refactor_frontend_preservation.py
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend test:ui-error-contracts
```

backend를 cwd로 `.venv/Scripts/python.exe -u -m pytest tests/memory`, 또는 `tests/chat tests/runtime/test_autonomous_activity_graph.py tests/routines/test_resident_execution_bindings.py tests/routines/test_activity_limits.py`를 실행한다. 공식 startup은 `tests/test_world_activity_official_startup.py`, 전환은 `tests/migrations/test_world_activity_v30.py`다. 실제 DB/기존 서버 연결을 추가하지 않는다.

Browser는 `playwright.world-memory-integration.config.ts`의 실제 testMatch를 사용한다. Next `NEXT_DIST_DIR=.next-world-memory-integration`·`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:1`·port3338, static은 기존 `serve-static.mjs --port3339`다. `--project=next-preview`/`--project=static-export`; static은 `ANGMOO_INTEGRATION_STATIC_URL`·`ANGMOO_CREATOR_STATIC=1`·`ANGMOO_GRAPH_STATIC=1`을 지정한다. `--list`로 수집하고 사용자 port3000을 대체하지 않는다.

새 접수를 중단→진행 작업 정산→이전 input policy 복귀 fixture를 실행했다. schema/data/private 제약 downgrade는 하지 않는다. 실제 사용자 환경 반영과 AI 측정은 I50/I51의 별도 범위다.

<!-- TRACEABILITY: 실제 증거 대응 -->

## R-P01–R-P06 실제 관계망 작업 대응

| 단계 | 실제 소유자/작업 | 증거 |
| --- | --- | --- |
| R-P01 | Relationships query/client/review + 기존 DTO/state/source utility + 기존 graph/static/avatar specs의 보존 기준 | E-ARCH/E-NEXT/E-STATIC |
| R-P02 | 공통 SettingsCard 표시·헤더·review·map·list의 semantic token/anatomy·간결한 도움말 | E-FE/E-NEXT/E-STATIC |
| R-P03 | feature-owned `graph-layout.ts`·전체 node/name/direction·양방향 관계 목록·실제 bbox 겹침 검사 | world-memory-extra-ui 6cases + 기존 avatar 5cases, 양 환경 |
| R-P04 | 기존 source/fallback/status 우선순위·scoped graph/review 요청 sequence/AbortSignal/auth/runtime 수명·GET 무호출 | relationship-graph/product-shell 3cases + static provider 상태 + E-LIFE |
| R-P05 | ko/en × 1/7/20 nodes × 390/480/960/1440px·200%·원문/목록·overflow·안전 avatar·Next/static 실제 수집 | E-NEXT/E-STATIC 및 artifacts/world-memory-integration-20261006 |
| R-P06 | 공식 architecture/design·catalog/lint/typecheck/build·보존·R-C12/R-T16 대응·로컬 보고 | E-ARCH/E-FE/E-PRESERVE 및 이 통합 보고서 |

관계망 검증 보고는 이 통합 보고서에 포함했다. 별도 계획의 예정 보고서명/예정 config명 대신 실제 수집된 공통 config/spec과 독립 preview/suffix 경로를 기록했다. 공식 pixel/실제 provider/설치판의 미수행 상태는 위 경계와 같다.

## I00–I49 단계별 실제 구현 대응

| 단계 | 실제 내용 | 로컬 상태 | 증거 |
| --- | --- | --- | --- |
| I00 | 지정 브랜치·보존·실행 경계 고정 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I01 | 두 계획의 실제 owner·수집부터 소비까지 조사 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I02 | 통합 scope·read DTO·nullable·오류 계약 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I03 | 원본 UI anatomy·보존 기능·두 언어 기준 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I04 | 목적별 모델·키 계약과 구/신 batch policy | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I05 | 혼합 기억 접근 제약·원문/근거·삭제 fence 설계 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I06 | 하나의 schema/data 전환·보존 계약 확정 | LOCAL IMPLEMENTED | E-ARCH, E-CONTRACT |
| I07 | 공식 forward migration·등록·암호화 전환 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I08 | SQLite migration 재실행·복구·자료 보존 회귀 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I09 | Identity 직접 키 API·binding·rotation/폐기 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I10 | Memory subject 설정·동의/트리거·작업 profile 연결 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I11 | World persona·활동 설정의 patch/CAS 저장 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I12 | SNS text·일과·관심 주제·활동 방식 실제 실행 연결 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I13 | SNS 이미지 생성 설정·actor cap·사용량 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I14 | World Chat·SNS/Chat 인식 키·공동 상한 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I15 | 의미 검색의 명시적 준비 job·고정 임베딩 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I16 | 현재 World 인스턴스 삭제·공개 보존·늦은 결과 차단 | LOCAL IMPLEMENTED | E-AUTO, E-CONTRACT, E-SCOPE |
| I17 | 공통 cutoff 후보 접수·paging·32활동 선택 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I18 | Chat 활동 30턴·preceding5·S/C 연결 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I19 | 500자 순수 발췌·offset·whole-source 보존 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I20 | 요청 전체 prior8·모든 근거 고려 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I21 | 구/신 manifest·frozen purpose/profile·재시작 복원 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I22 | 전체 직렬화 예산·정상1회·결정적 예외 split | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I23 | provider prompt/schema·출력·S/C/P/coverage 검증 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I24 | 자동3시도 계보·unknown·split/재시작 실패 복구 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I25 | canonical 기억·근거·제약·receipt 원자 적용 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I26 | 선택 범위 완료·used/skipped·생략 손실 표시 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I27 | recall·prior·Hot Brief·FTS/vector/cache/export 제한 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I28 | content-free 진단·단위·기억 근거 표시 계약 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I29 | 순수 정책·fake adapter·네트워크0 회귀 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I30 | SQLite 교차 실행·저장·권한·복구 통합 회귀 | LOCAL IMPLEMENTED | E-CHAT, E-CONTRACT, E-MEM |
| I31 | World read-only status API·adapter·client 수명 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I32 | 기존 Device 상태 UI의 실제 공통 표시 추출 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I33 | sticky 헤더·뒤로가기/새로고침 제거·유형/역할 태그 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I34 | 최근 활동·설명 우선 페르소나·지원 행동 요약 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I35 | World persona·활동·SNS 키·삭제 카드 재사용 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I36 | SNS 이미지 생성·관심 주제 카드 정리 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I37 | 활동 방식/현재 상태·오늘 일과 실제 카드 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I38 | Chat/인식 카드·공용 카드 제거·화면 언어 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I39 | 기억 사용·정리 카드·subject 직접 키/모델 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I40 | 의미 검색 준비·기억 상세·발췌/근거 UI | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I41 | 모든 카드·status 수명·ko/en·접근성 통합 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I42 | 기존5단계 생성 프레임·method 선택 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I43 | 기본정보·페르소나·최종확인 배치 | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I44 | 프로필 banner/avatar·upload/crop·생성 lifecycle | LOCAL IMPLEMENTED | E-FE, E-NEXT, E-STATIC |
| I45 | Next/static 브라우저·디자인·기능 보존 통합 | LOCAL IMPLEMENTED | E-NEXT, E-STATIC |
| I46 | 공식 앱 factory·SQLite 기동/health·격리 smoke | LOCAL IMPLEMENTED | E-CONTRACT |
| I47 | 아키텍처·보존·catalog·lint/typecheck·빌드 | LOCAL COMPLETE | E-ARCH, E-FE, E-PRESERVE |
| I48 | 새 접수 정책 연결·구 작업 공존·되돌리기 검증 | LOCAL IMPLEMENTED | E-CONTRACT |
| I49 | 통합 완료 판정·논리별 로컬 커밋·재시작 보고 | LOCAL COMPLETE | E-PRESERVE 및 final-closeout.json |

R-P01–R-P06도 I03/I41/I45/I47/I49에 포함했다. 실제 Relationships owner/query/state 보존, 공통 카드 소비, 결정적 지도/방향별 목록, scoped read 수명, 양 환경 ko/en/긴 이름/실제 bbox/기존 avatar 검증과 구조/보고 증거다.

## 원본 계약112 + 관계망 계약12 = 124개 대응

| 원본 ID | 통합 위치 | 실제 증거/범위 | 구체 연결 |
| --- | --- | --- | --- |
| M-C01 | I02, I04, I17, I21, I25 | E-ARCH, E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C02 | I17, I18 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C03 | I18, I19 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C04 | I18, I22 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C05 | I17, I18, I22 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C06 | I18, I19 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C07 | I19, I29 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C08 | I19, I21, I26, I40 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C09 | I22, I23, I29 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C10 | I23, I25 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C11 | I22, I23, I29 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C12 | I23, I26 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C13 | I05, I25, I27 | E-ARCH, E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C14 | I07, I08, I21, I48 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C15 | I22, I24 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-C16 | I10, I17, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| U-C01 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C02 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C03 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C04 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C05 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C06 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C07 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C08 | I31, I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C09 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C10 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C11 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C12 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C13 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C14 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C15 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C16 | I02, I30, I31, I34 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C17 | I31, I41, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C18 | I31, I41, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C19 | I31, I41, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C20 | I31, I41, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C21 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C22 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C23 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C24 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C25 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C26 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C27 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C28 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C29 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C30 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C31 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C32 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C33 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C34 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C35 | I35, I38, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C36 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C37 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C38 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C39 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C40 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C41 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C42 | I04, I09, I11, I15, I21 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C43 | I13, I14, I30, I36, I38 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C44 | I13, I14, I30, I36, I38 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C45 | I13, I14, I30, I36, I38 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C46 | I06, I08 | E-ARCH, E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C47 | I06, I08 | E-ARCH, E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C48 | I06, I08 | E-ARCH, E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C49 | I16, I25, I30 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C50 | I16, I25, I30 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C51 | I35, I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C52 | I35, I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C53 | I35, I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C54 | I35, I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C55 | I49 | E-PRESERVE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C56 | I38, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C57 | I38, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C58 | I38, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C59 | I38, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C60 | I38, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C61 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C62 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C63 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C64 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C65 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C66 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C67 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C68 | I39, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C69 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C70 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C71 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C72 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C73 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C74 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C75 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C76 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C77 | I42, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C78 | I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C79 | I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C80 | I34, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C81 | I06, I09, I16, I25, I30 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C82 | I11, I41 | E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C83 | I07, I09 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C84 | I10, I21, I23, I30 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C85 | I07, I08, I46, I47 | E-ARCH, E-AUTO, E-CONTRACT, E-FE, E-PRESERVE, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C86 | I32, I35, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C87 | I10, I30, I39, I40 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C88 | I09, I39, I40 | E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C89 | I09, I35, I38, I40 | E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C90 | I07, I08, I21 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C91 | I10, I15, I27, I40 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C92 | I14, I38 | E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C93 | I15, I40 | E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C94 | I04, I09, I14, I23, I39 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C95 | I04, I07, I14, I39 | E-ARCH, E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-C96 | I04, I09, I10, I15, I21, I30 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| R-C01 | R-P01/R-P04 / I03,I41 | E-ARCH, E-NEXT, E-STATIC | 기존 Relationships query/client/DTO/state/source 및 scoped 읽기 소비자 보존 |
| R-C02 | R-P02 / I41 | E-ARCH, E-FE, E-NEXT, E-STATIC | 공통 SettingsCard와 relationship-graph-frame의 카드 anatomy/semantic token |
| R-C03 | R-P02/R-P05 / I41,I45 | E-NEXT, E-STATIC | frame의 헤더→정리→지도→방향별 목록→조건부 근거와 복귀/depth 조작 |
| R-C04 | R-P02/R-P04 / I41 | E-FE, E-NEXT, E-STATIC | 짧은 안내·보조 provider 정보·정리 상태/이력의 기존 의미 |
| R-C05 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | graph-layout/node/frame 및 기존 ProfileAvatar·방향별 목록 회귀 |
| R-C06 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | 결정적 layout·화살표 label 제거·목록의 전체 관계 설명·실제 bbox 검사 |
| R-C07 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | 관계 목록의 label/perception/지표/상호작용/시각/버전 표시 |
| R-C08 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | review 상태/예약/시간대/jobs/제외 안내와 조건부 사건 근거 |
| R-C09 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | 기존 relationship-graph utility 및 graph/static provider 상태 회귀 |
| R-C10 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC, E-LIFE | scoped graph/review client의 sequence/abort/auth/runtime 수명과 GET 조작 |
| R-C11 | R-P02–R-P05 / I41,I45 | E-FE, E-NEXT, E-STATIC | ko/en·Next/static·긴 이름·390/480/960/1440px·200% 및 동등 목록 |
| R-C12 | R-P06 / I47,I49 | E-ARCH, E-FE, E-PRESERVE | 이 보고서의 branch/로컬 커밋·사용자 자료/외부 실행 경계 및 원본 계획 hash |

## 기술 시작값7개와 실측 경계

| 원본 ID | 통합 위치 | 실제 증거/범위 | 구체 연결 |
| --- | --- | --- | --- |
| M-TECH01 | I22, I23, I29, I50 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH02 | I22, I23, I29, I50 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH03 | I22, I23, I29, I50 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH04 | I22, I23, I29, I50 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH05 | I20, I29, I30 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH06 | I24, I29, I30 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |
| M-TECH07 | I24, I30, I46 | E-CHAT, E-CONTRACT, E-MEM | local fake/policy 경계 확인; 실제 모델 capability/tokenizer/비용/지연 I50 미측정 |

다음160행은 원본126 + 교차18 + 관계망16의 **증거 대응 목록**이다. 행마다 별도 test 한 개를 새로 실행했다는 의미가 아니며, native Vec1/공식 pixel/실제 서비스 모델/설치·직접 검수의 미측정 범위는 위 제한을 따른다. 기존 회귀와 새 경계 검증의 전체 묶음을 연결한다.

## 원본 검증126 + 교차18 + 관계망16 = 160개 대응

| 원본 ID | 통합 위치 | 실제 증거/범위 | 구체 연결 |
| --- | --- | --- | --- |
| M-V01 | I22, I23, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V02 | I18, I22, I23, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V03 | I18, I22, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V04 | I17, I29, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V05 | I02, I17, I25, I30 | E-ARCH, E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V06 | I18, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V07 | I19, I29 | E-CHAT, E-CONTRACT, E-MEM | test_excerpt_preserves_exact_unicode_ranges_and_whole_identity / test_omitted_middle_change_invalidates_manifest_even_when_excerpt_matches |
| M-V08 | I19, I21, I25, I30 | E-CHAT, E-CONTRACT, E-MEM | test_excerpt_preserves_exact_unicode_ranges_and_whole_identity / test_omitted_middle_change_invalidates_manifest_even_when_excerpt_matches |
| M-V09 | I22, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V10 | I20, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V11 | I23, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V12 | I22, I23, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V13 | I23, I24, I29 | E-CHAT, E-CONTRACT, E-MEM | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-V14 | I23, I26, I29 | E-CHAT, E-CONTRACT, E-MEM | test_activity_batch32 / test_activity32_integration / test_episode_contracts / test_episode_selection_service |
| M-V15 | I05, I25, I27, I30 | E-ARCH, E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V16 | I27, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V17 | I21, I24, I25, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V18 | I25, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V19 | I24, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V20 | I26, I30 | E-CHAT, E-CONTRACT, E-MEM | test_activity32_integration / test_episode_apply / test_episode_runtime_restart / test_vector_projection_lifecycle; native Vec1 SKIP 별도 |
| M-V21 | I21, I30, I48 | E-CHAT, E-CONTRACT, E-MEM | test_pause_settle_previous_admission_policy_and_restore_without_schema_downgrade / legacy manifest 회귀 |
| M-V22 | I07, I08, I30 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| M-V23 | I46 | E-CONTRACT | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| M-V24 | I10, I17, I39, I40, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | test_consolidation_requests / test_episode_schedule_shutdown / test_p8_l_r_memory_batch_api / product-shell Memory controls |
| M-V25 | I28, I40 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| M-V26 | I40, I41, I45 | E-FE, E-NEXT, E-STATIC | 전체 E-MEM/E-CONTRACT 및 Memory 소유 source; 실제 AI 품질 별도 |
| U-T01 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T02 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T03 | I30, I31, I34 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T04 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T05 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T06 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T07 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T08 | I30, I31, I45 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T09 | I30, I31, I34 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T10 | I32, I33, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T11 | I32, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T12 | I34, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T13 | I32, I34, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T14 | I31, I34, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T15 | I31, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T16 | I31, I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T17 | I31, I33, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T18 | I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T19 | I32, I33, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T20 | I33, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T21 | I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T22 | I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T23 | I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T24 | I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T25 | I02, I30, I31, I41, I45 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T26 | I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T27 | I31, I33, I41, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T28 | I35, I36, I37, I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T29 | I35, I36, I37, I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T30 | I36, I37, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T31 | I04, I05, I06, I08, I09, I10, I12, I13, I14, I15, I21, I30, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T32 | I07, I08, I09, I30, I38, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T33 | I08, I09, I10, I12, I13, I14, I15, I21, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T34 | I08, I09, I10, I12, I13, I14, I15, I21, I30, I38, I41, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T35 | I07, I08, I09, I10, I11, I12, I13, I14, I15, I21, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T36 | I08, I13, I30, I38, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | test_world_image_policy / test_world_key_execution / 기존 image_integration 회귀 |
| U-T37 | I07, I08, I13, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_image_policy / test_world_key_execution / 기존 image_integration 회귀 |
| U-T38 | I08, I10, I14, I15, I21, I30, I38, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T39 | I07, I08, I10, I14, I15, I21, I30, I38, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | test_world_image_policy / test_world_key_execution / 기존 image_integration 회귀 |
| U-T40 | I08, I12, I30, I37, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T41 | I08, I12, I30, I36, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T42 | I08, I12, I30, I37, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T43 | I08, I09, I10, I11, I12, I13, I14, I15, I21, I30, I37, I38, I41, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T44 | I08, I16, I30, I35, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_instance_deletion / test_world_chat_delete / test_activity32_integration |
| U-T45 | I08, I16, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_instance_deletion / test_world_chat_delete / test_activity32_integration |
| U-T46 | I07, I08, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| U-T47 | I07, I08, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| U-T48 | I08, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| U-T49 | I35, I36, I37, I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T50 | I38, I41, I45, I47, I49 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T51 | I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 기존 언어 선호 계약 + 실제 ko/en World/Memory/생성/profile browser; catalog/error 검사 |
| U-T52 | I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 기존 언어 선호 계약 + 실제 ko/en World/Memory/생성/profile browser; catalog/error 검사 |
| U-T53 | I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 기존 언어 선호 계약 + 실제 ko/en World/Memory/생성/profile browser; catalog/error 검사 |
| U-T54 | I38, I41, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 기존 언어 선호 계약 + 실제 ko/en World/Memory/생성/profile browser; catalog/error 검사 |
| U-T55 | I38, I41, I45, I47, I49 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 기존 언어 선호 계약 + 실제 ko/en World/Memory/생성/profile browser; catalog/error 검사 |
| U-T56 | I01, I03, I39, I40, I45 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T57 | I39, I45 | E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T58 | I01, I03, I08, I09, I10, I14, I15, I21, I30, I39, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T59 | I39, I45 | E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T60 | I01, I03, I08, I09, I10, I14, I15, I21, I30, I39, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T61 | I40, I45 | E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T62 | I40, I45 | E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T63 | I40, I45 | E-FE, E-NEXT, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T64 | I01, I03, I07, I08, I09, I10, I14, I15, I21, I30, I39, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T65 | I40, I45, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T66 | I01, I03, I42, I43, I44, I45, I47 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T67 | I42, I43, I44, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T68 | I42, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T69 | I43, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T70 | I43, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T71 | I44, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T72 | I43, I44, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T73 | I42, I43, I44, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T74 | I01, I03, I42, I43, I45, I47 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T75 | I44, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T76 | I45, I47, I49 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | local-creator: keyless/import/raw/copy/external/recovery/cancel/return/English/crop; Next/static |
| U-T77 | I32, I34, I45 | E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T78 | I02, I31, I34, I45 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | test_world_key_execution / test_world_character_configuration / 기존 실제 world/chat scope 회귀 |
| U-T79 | I02, I31, I34, I45 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T80 | I30, I31, I32, I41, I45, I47, I49 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui status/profile/sticky ko/en + profile-relationship-avatar Next/static |
| U-T81 | I04, I05, I06, I08, I09, I13, I16, I30, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_instance_deletion / test_world_chat_delete / test_activity32_integration |
| U-T82 | I11, I35, I41, I45, I47 | E-ARCH, E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T83 | I07, I08, I09, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T84 | I01, I03, I04, I05, I06, I08, I09, I10, I14, I15, I21, I30, I39, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T85 | I07, I08, I30, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_activity_v30 / test_world_configuration_v28_recovery / test_world_activity_official_startup |
| U-T86 | I32, I35, I45, I47, I49 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | world-memory-integration-ui 10cards/edited-field conflict/draft/keys + 기존 E-AUTO/E-SCOPE/E-FE |
| U-T87 | I04, I05, I06, I07, I08, I09, I10, I14, I15, I21, I30, I39, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T88 | I08, I09, I10, I14, I15, I21, I30, I39, I40, I45, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T89 | I01, I35, I36, I38, I39, I40, I45, I47 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-PRESERVE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T90 | I04, I05, I06, I08, I09, I10, I14, I15, I21, I30, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T91 | I07, I08, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T92 | I04, I05, I06, I07, I08, I10, I14, I15, I21, I30, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T93 | I04, I05, I06, I08, I09, I10, I14, I15, I21, I30, I38, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_image_policy / test_world_key_execution / 기존 image_integration 회귀 |
| U-T94 | I04, I05, I06, I07, I08, I10, I14, I15, I21, I30, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | test_world_image_policy / test_world_key_execution / 기존 image_integration 회귀 |
| U-T95 | I04, I05, I06, I07, I08, I10, I14, I15, I21, I30, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T96 | I04, I05, I06, I08, I10, I14, I15, I16, I21, I30, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T97 | I04, I05, I06, I08, I09, I10, I14, I15, I21, I30, I38, I39, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T98 | I04, I05, I06, I07, I08, I09, I10, I14, I15, I21, I30, I38, I39, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| U-T99 | I04, I05, I06, I07, I08, I09, I10, I14, I15, I21, I30, I40, I45, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | product-shell Memory owner controls / test_world_embedding_preparation / E-MEM; native Vec1 품질 미측정 |
| U-T100 | I04, I05, I06, I08, I09, I10, I14, I15, I21, I30, I39, I40, I45, I46, I47 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-PRESERVE, E-SCOPE, E-STATIC | test_world_credentials / test_world_key_execution / test_world_chat_configuration / test_world_activity_v30 |
| X-T01 | I09, I10, I21, I23, I30, I39 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T02 | I02, I09, I14, I15, I21, I30 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T03 | I11, I21, I30, I41 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T04 | I09, I21, I24, I25, I30 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T05 | I06, I07, I08, I30, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T06 | I05, I25, I27, I30, I40 | E-ARCH, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T07 | I16, I27, I30, I40 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T08 | I17, I18, I20, I22, I29, I30 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T09 | I19, I21, I23, I25, I26, I28, I40 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T10 | I04, I09, I10, I14, I15, I21, I23, I30 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T11 | I04, I07, I13, I14, I24, I30, I36, I38, I44, I46 | E-ARCH, E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T12 | I10, I15, I25, I27, I30, I40 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T13 | I16, I24, I25, I27, I30, I35 | E-AUTO, E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T14 | I35, I41, I45 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T15 | I38, I41, I43, I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T16 | I04, I07, I42, I45 | E-ARCH, E-AUTO, E-CONTRACT, E-FE, E-NEXT, E-SCOPE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T17 | I02, I31, I38, I41, I46 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| X-T18 | I45, I51 | E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| R-T01 | R-P02 / I41,I45,I47 | E-ARCH, E-FE, E-NEXT, E-STATIC | world-memory-extra-ui/card anatomy + 공식 design 검사 |
| R-T02 | R-P02/R-P05 / I41,I45 | E-NEXT, E-STATIC | world-memory-extra-ui/relationship-graph product shell의 DOM 순서·복귀/depth 조작 |
| R-T03 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | 기존 relationship-graph/product-shell·static-product-shell의 review 상태/이력 표시 |
| R-T04 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | 기존 product shell의 depth/retry scoped GET 및 합성 요청 기록 |
| R-T05 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | world-memory-extra-ui의 중앙 node·방향별 목록 및 기존 graph 회귀 |
| R-T06 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | ko/en×1/7/20 nodes·실제 bbox pairwise 비겹침·label 목록·overflow |
| R-T07 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | product shell/extra UI의 전체 label·지표·perception details |
| R-T08 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | 기존 relationship-graph/product-shell·static-product-shell의 조건부 사건 근거/링크 |
| R-T09 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC | 기존 graph/static provider 상태·source/fallback 우선순위 회귀 |
| R-T10 | R-P04/R-P05 / I41,I45 | E-NEXT, E-STATIC, E-LIFE | scoped graph/review 요청 수명 구현·기존 늦은 응답/runtime/avatar 회귀 |
| R-T11 | R-P02–R-P05 / I41,I45 | E-FE, E-NEXT, E-STATIC | 2609키/16namespace parity 및 두 언어 graph 원문 표시 |
| R-T12 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | extra UI의 390/480/960/1440px·200%·bbox/overflow와 semantic 관계 목록 |
| R-T13 | R-P03/R-P05 / I41,I45 | E-NEXT, E-STATIC | profile-relationship-avatar 기존 5건을 두 환경에서 재실행 |
| R-T14 | R-P04/R-P05 / I10,I27,I39,I45 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-NEXT, E-STATIC | 동일 subject 정리/예약 조회와 native key·memory32·scoped graph consumer |
| R-T15 | R-P05 / I45 | E-NEXT, E-STATIC | 실제 integration config의 두 환경 spec 수집/실행·기존 graph/static/avatar 회귀 |
| R-T16 | R-P06 / I47,I49 | E-ARCH, E-FE, E-PRESERVE | 이 보고서의 R 계약/단계/검증 대응·로컬 branch/commit·미수행 경계 |

## 원본 구현68단계 대응 및 범위 밖 실행

| 원본 ID | 통합 위치 | 실제 증거/범위 | 구체 연결 |
| --- | --- | --- | --- |
| M-P00 | I00 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P01 | I01, I05 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P02 | I04, I21 | E-ARCH, E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P03 | I19 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P04 | I17 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P05 | I18 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P06 | I20 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P07 | I05, I06 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P08 | I07, I08 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P09 | I21 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P10 | I22 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P11 | I23 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P12 | I23 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P13 | I24 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P14 | I25 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P15 | I26 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P16 | I27 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P17 | I28 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P18 | I28, I40 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P19 | I29 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P20 | I30 | E-CHAT, E-CONTRACT, E-MEM | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P21 | I46 | E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P22 | I47, I49 | E-ARCH, E-FE, E-PRESERVE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P23 | I50 | scope 밖 / 별도 실행 | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| M-P24 | I48, I51 | E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P00 | I00 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P01 | I01, I03 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P02 | I02, I31 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P03 | I31 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P04 | I31 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P05 | I32 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P06 | I31, I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P07 | I33 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P08 | I34 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P09 | I34 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P10 | I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P11 | I30, I31 | E-CHAT, E-CONTRACT, E-FE, E-MEM, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P12 | I45 | E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P13 | I47 | E-ARCH, E-FE, E-PRESERVE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P14 | I34, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P15 | I01 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P16 | I04, I05, I06 | E-ARCH, E-CONTRACT | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P17 | I07, I08 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P18 | I11 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P19 | I09 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P20 | I12 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P21 | I13 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P22 | I10, I14, I15, I21 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P23 | I16 | E-AUTO, E-CONTRACT, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P24 | I35 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P25 | I36 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P26 | I37 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P27 | I38 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P28 | I41 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P29 | I08, I30, I46 | E-AUTO, E-CHAT, E-CONTRACT, E-MEM, E-SCOPE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P30 | I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P31 | I38, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P32 | I01, I03, I39 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P33 | I39 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P34 | I40 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P35 | I45 | E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P36 | I40, I49 | E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P37 | I01, I03, I42 | E-ARCH, E-CONTRACT, E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P38 | I42 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P39 | I43 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P40 | I44 | E-FE, E-NEXT, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P41 | I45, I47 | E-ARCH, E-FE, E-NEXT, E-PRESERVE, E-STATIC | 구현 단계의 실제 owner/source와 위 증거 묶음 |
| U-P42 | I49 | E-PRESERVE | 구현 단계의 실제 owner/source와 위 증거 묶음 |
