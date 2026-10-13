# World UI·API 키·32활동 상황기억 통합 계획 후속 누락 재검토

검토일: 2026-10-07. 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.

사용자 요청은 통합 계획이 누락 없이 수행됐는지 실제 코드와 실행 결과로 다시 확인하고, 발견한 누락을 구현하는 것이다. 이전 보고서의 완료 표시만으로 판정하지 않았다. 시작 HEAD는 `6c862f04b21ad92b5708c01c2b66ce4806de88bb`, 시작 working tree는 clean이었다.

**최종 판정: I00–I49 및 §16의 허용된 로컬 범위 재검토·발견한 누락 보완 완료 — LOCAL TECH PASS.** 최종 backend·Next·static·번역·빌드 검증과 일반 CLI의 전체 보존 검사도 종료 코드0으로 통과했다. 이전 실행 결과와 이번 커밋에서 다시 실행한 결과를 구분한다. 실제 AI 품질과 실사용 자료 전환인 I50/I51은 계속 보류한다.

## 실행 계약과 기준

- 지정 브랜치 `feat/0.1.0-release-readiness`에서만 작업했다. 코드 보완 로컬 커밋은 `df815d238e6ebb5f3e3ade68a1fc8a9d780bc729`, `d9d498edb819f3f98077586132a78b60be81a95c`이다. 두 커밋 모두 Signed-off-by를 포함했다.
- 기존 I00–I49 구현과 §16 관계망 계약이 검토 대상이다. I50/I51의 실제 AI 품질 비교와 실사용 자료 전환은 기존 계약대로 보류한다.
- workspace/Frontend AGENTS, `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md`, `backend/ARCHITECTURE.md`와 디자인·product shell·기능 보존 문서를 기준으로 실제 책임과 소비자를 대조했다. 설치판을 조사하지 않아 설치판 identity 판정은 하지 않았다.
- Python 검증은 `ANGMOO_DENY_EXTERNAL_NETWORK=1`이다. 합성 자료·격리 SQLite·fake SDK와 browser API fixture만 사용했다. 실제 provider generation/auth/tokenizer/embedding 호출을 하지 않았다.
- Next dev `127.0.0.1:3338`과 직접 만든 static preview `127.0.0.1:3339`를 사용했다. 사용자 `3000` 서버, Docker, 설치판, 실제 사용자 DB·키·대화·미디어를 사용하거나 변경하지 않았다.
- push, PR, hosted CI, main merge, fetch/pull, 브랜치 변경, 새 worktree, PostgreSQL 서버 실행을 하지 않았다. 하위 에이전트를 새로 만들거나 작업을 위임하지 않았다.
- 원본 계획 3개, 기존 migration v28/v29/v30, frozen refactor checkpoint/path map/test baseline과 기존 testMatch를 유지한다. 증거는 현재 코드 커밋의 정확한 변경 전후와 새 node를 append한다.

## 실제로 발견한 누락과 보완

| 항목 | 이전 구현에서 빠진 경계 | 보완과 실제 소유자 | 확인 방법 |
| --- | --- | --- | --- |
| 관계 정리 조회의 수명 | 같은 경로의 owner/session/runtime 전환 때 이전 private 정리 데이터가 남거나 늦은 응답이 반영될 수 있었다. | `relationship-graph-client.tsx`가 owner/World/character/session/runtime/retry 단위로 패널을 새로 구성하고, `relationship-review-panel.tsx`가 abort와 접수한 auth scope를 성공·실패 모두에서 검사한다. | 기존 static에서 owner 변경·같은 owner 세션 갱신 실패 재현. 현재 Next/static에서 이전 owner, 늦은 200/503, 로그아웃, 같은 owner 세션 갱신을 검사했다. |
| 기억 화면 전체의 수명 | `/memory`의 기존 상위 composition이 auth/runtime 수명을 소유하지 않아 이전 기억·직접 키 초안이 화면에 남았다. 후속 정정/삭제 응답이 화면을 떠난 뒤 route를 바꾸는 코드도 있었다. | `memory-workspace-screen.tsx`가 인증과 owner/session/runtime/World/actor 수명을 소유한다. `memory-workspace.tsx`의 pagination·새로 읽기·고정/정정/삭제·기억 사용 변경은 abort/generation/auth scope를 검사한다. `memory-client.ts`의 기존 mutation에 optional AbortSignal을 전달한다. | 수정 전 Next에서 이전 private 기억·password 초안 잔류 재현. 현재 양 환경에서 owner/runtime 전환, 늦은 list, 화면을 떠난 후 correction 응답을 검사했다. 기존 고정·정정·삭제·동의·재시도·좁은 화면 동작도 통과했다. |
| 로컬 세션 재발급 실패 처리 | local bootstrap의 401이 auth 변경 이벤트를 다시 보내 refresh를 재진입시키고, 원래 refresh의 실패 처리를 무효화할 수 있었다. | `features/identity/api/session.ts`가 기존 `authRequest`의 `suppressAuthFailureEvent`를 사용한다. 재발급 성공/실패의 상태 변경은 기존 AuthProvider 한 곳이 수행한다. | 로그아웃/재발급 실패 fixture에서 bootstrap이 한 번만 호출되고 저장된 owner와 private 패널이 제거되는 것을 양 환경에서 확인했다. |
| 안전한 ko/en 상태·오류 표시 | 관계 정리 job의 raw error code와 fallback 사유가 화면에 노출됐고 fallback 접속 문구 일부가 한국어 literal이었다. | Relationships 소유 컴포넌트와 ko/en catalog가 known code를 설명으로 표시하며 unknown code도 안전한 일반 문구를 사용한다. 원래 이름·관계 label·perception·근거 원문은 번역하거나 삭제하지 않는다. | known/unknown 오류, 비정상 raw 문자열, ko/en 각각 검사. catalog key/params/plural parity 및 UI 오류 계약 검사 통과. |
| 정리 준비 상태와 시간대의 진실성 | Memory ON·동의·예약만으로 준비됐다고 표시하며 실제 subject의 consolidation 키·모델을 확인하지 않았다. 표시 시간대도 오래된 batch 설정을 읽었다. | runtime `SqlAlchemyDiagnosticReferences.review_configuration`이 실제 `review_credentials.snapshot`을 같은 Session에서 재사용해 exact owner/World/actor/purpose/model/thinking을 확인한다. 현재 owner environment의 시간대를 조회하고 미설정 상태에서는 실행 가능 안내를 표시하지 않는다. | 새로운 SQLite node 2개: 다른 World 키·Chat 키·thinking 불일치·폐기·동의/OFF·예약/OFF·현재 시간대. 조회 구간 INSERT/UPDATE/DELETE 0을 검사했다. |
| 인식 상한 초기화 시각 표시 | 인식 카드가 reset UTC ISO 문자열을 그대로 표시했다. | `world-image-policy-controls.tsx`가 생성 카드와 같은 `useUiDateFormatter`를 사용한다. 예약/사용량/상한 값과 초기화 시각 자체는 바꾸지 않는다. | ko/en World 카드, 200% 텍스트, typecheck와 양 build. 단순 표시 변경을 위한 구현 복제 테스트는 추가하지 않았다. |
| 재사용 화면의 동적 번역과 복구 안내 | literal catalog 검사는 통과했지만 상태표·helper 반환문·다섯 생성 단계의 부제·활동 시간 안내 일부는 영어 모드에서 한국어로 남았다. 기억 정리 실패는 별도 consolidation 키 대신 Chat 키를 안내했다. | Memory/Relationships/Characters/Media 소유 ko/en catalog를 보완했다. 활동 시간 validator는 기존 계산·허용 범위를 유지하고 optional `UiText`를 받아 표시 문장을 번역한다. Memory 실패 안내는 이 캐릭터의 기억 정리용 키·모델을 가리킨다. 초기 Memory 읽기의 abort 후 error 반영도 막는다. | 수정 전 영어 Memory 카드·활동 시간 안내 실패를 각각 재현했다. 최종 양 환경에서 동적 상태·복구 안내, 당일/익일 시간, 동일 시간·17시간 초과의 저장 차단, 다섯 생성 단계 부제·Unicode 원문 보존을 검사했다. |

이번 보완은 기존 카드 기능이나 지원 모델을 새로 바꾸는 작업이 아니다. 공통 UI에는 도메인 판단을 추가하지 않았고 cross-feature 조립은 composition/runtime 소유자에서 수행했다. 출처 분류는 **LOCAL**이며 기존 공통 카드·시각 토큰을 재사용했다. 신규 asset/font/dependency와 raw color를 추가하지 않았다.

## I00–I49 및 교차 계약 재검토

기존 [통합 실행 보고서](./world-ui-memory-batch32-integration-20261006.md)의 50단계·124계약·160검증 의무·원본 단계 대응표를 원본 계획과 대조했다. 대응표는 검토 출발점이며 실제 source/consumer와 실행 결과로 확인했다. 숫자는 각각의 의무 ID 수이며 새 독립 테스트 수가 아니다.

| 단계/계약 묶음 | 실제 코드에서 다시 확인한 연결 | 이번 재검토 판정과 증거 범위 |
| --- | --- | --- |
| I00–I03 | 지정 branch/clean 시작, 원본 두 계획의 32활동·UI 범위, domain/runtime/feature/composition 책임, ko/en 공통 카드 | 이번 branch/HEAD 확인과 ARCH/DESIGN 검사. 원본 문서 hash 유지. |
| I04–I10 | 여섯 purpose의 직접 키, 모델 allowlist/default, subject별 memory profile, encryption/AAD/revision, migration/공식 schema 등록, 동의와 정리 설정 | `world_credentials`, `world_credential_binding`, Memory subject/profile consumers와 v30 source 대조. 이번 credentials/migration/embedding/relationship backend 회귀 포함. shared/foreign fallback과 GET backfill을 다시 연결하지 않았다. |
| I11–I14 | edited-field PATCH/CAS, SNS text·일과/관심 주제 실행 binding, image generation cap20/vision cap10, SNS/Chat 합산 인식 ledger와 회전 후 당일 소비 | 실제 World configuration/media/Chat admission과 consumer 대조. 이번 key execution·migration 회귀와 양 환경 World 10카드·직접 키·상한·초안 검사. |
| I15–I16 | embedding 일반 저장/ON/GET와 명시적 역사 준비 구분, 고정 모델, 정확한 scoped key, 현재 World 인스턴스 삭제와 다른 World/private/public 보존 | 이번 embedding preparation·instance deletion 회귀. 원래 승인된 별도 준비 및 공개 삭제 저자 표시 계약 유지. |
| I17–I21 | 후보 cutoff/page/32활동, Chat 30신규턴+preceding5, Unicode 500→350→150 순수 발췌, prior 전체8, frozen manifest/purpose/profile/legacy restore | Activity32 selection/manifest/source/prepare 소비자 대조와 이번 activity32 통합 회귀. 전체 Memory/Chat 과거 실행 결과는 이전 HEAD의 증거로 유지했다. |
| I22–I26 | 전체 요청 예산, fake 정상 generation1과 별도 token count, 예외 split 계보 자동3시도, S/C/P/coverage 검증, 기억·receipt·근거·제약 원자 apply | 현재 정책/processor/apply와 activity32 회귀 대조. 정상1회를 모든 provider network1회나 실제 AI 품질 PASS로 표시하지 않는다. |
| I27–I30 | 사용하지 않은 private 입력을 포함한 root access restriction, split 자식의 원래 root 범위, recall/prior/Hot Brief/FTS/vector/cache/export 차단, content-free diagnostics | episode privacy/retrievability/apply/vector 소비자 source 대조. 변경 없는 이전 Memory432/Chat893 결과와 이번 activity32 검사를 구분했다. native Vec1 검색 성능은 미측정이다. |
| I31–I34 | read-only status/nullable/error, Device/World 실제 공통 표시 consumer, sticky header·back/refresh/gutter 제거, 유형→역할, 최근활동→설명 우선 persona→세 지원 행동 | 이번 양 환경 World status ko/en과 기존 graph UI 검증. 상단 refresh를 다시 추가하지 않았다. |
| I35–I38 | 확정10카드/제외4카드, 이미지/주제/일과/방식 기능 유지, 직접 Chat/vision 키, 공용 카드 제거, 화면 언어 카드 | 실제 composition/card/control consumer 대조, 양 환경 390/480/960 ko/en·200%·edited-field save·초안 유지. reset 시각 표시만 보완했다. |
| I39–I41 | 기억 사용/정리/검색/상세 기능, consolidation·embedding 별도 직접 키, all cards/auth/runtime/scope/request 수명, ko/en/accessibility | 위 Memory·관계망 수명/오류/준비 누락 보완. 기존 Memory owner controls와 새 경계 테스트를 함께 실행했다. |
| I42–I44 | 기존5단계 creator workflow, style-only 재배치, 기존 import/raw/복사/external/returnTo/OFF/업로드/crop/취소/복원 | source와 이전 Next/static creator·crop/avatar 실행 증거 대조. 누락된 다섯 단계 부제를 catalog에 추가하고 기존 영어 생성 검사에 부제 확인 단언5개를 추가해 양 환경에서 실행했다. 원본 Unicode·OFF 등록·AI 부작용0을 유지했다. 사진의 API 확인/분석 기능은 추가하지 않는다. |
| I45–I47 | 동일 Next/static component, 실제 browser DOM/reflow, factory/SQLite/startup, schema/architecture/design/current inventory, lint/typecheck/build/preservation | 이번 backend256·Next39·static42·두 build·정적 검사와 마지막 전체 보존 검사로 후속 보완을 검증한다. |
| I48–I49 | 신규 접수 policy와 frozen 구 작업 공존, rollback 경계, exact append-only evidence, local commit/보고 | source/기존 migration 재실행 회귀 대조. 신규 node/코드 변경 전후를 보존 증거에 append하고 이 보고서로 이전 완료 판정을 보완한다. |
| §16 R-C/R-P/R-T | 실제 관계 source/fallback/status, 모든 이름/avatar/방향과 label/perception, 지도/목록/근거, daily review, scoped read/오류/ko/en | review scope·안전한 오류·실제 준비/시간대와 동적 번역 누락을 수정했다. 기존 1/7/20명 긴 이름6건, graph 상태/복구/reflow, 설치형 static 합성 router와 새 수명·오류·번역 검사19건을 실행했다. |

## 이번 커밋에서 실행한 검증

모든 로그는 ignored `artifacts/world-memory-integration-20261006/audit-20261007-*`에 보존한다. 새 browser 사진/trace는 `artifacts/world-memory-integration-20261007/`이다. 개별 명령에는 중복 node가 있어 다음 숫자를 고유 전체 테스트 수로 합산하지 않는다.

| 검사 | 실제 결과 | 로그 |
| --- | --- | --- |
| Backend 관계·키·실행·32활동·준비·migration·삭제 | **256 PASS / 1 SKIP / 2 warnings**, 188.55초 | `audit-20261007-backend.log` |
| 준비 상태의 수정 전/후 | 수정 전 **2 FAIL**, 수정 후 파일 전체 **4 PASS** | `audit-20261007-review-config-before.log`, `audit-20261007-review-config-after.log` |
| 최종 Next browser | **39 PASS**, 1.8분: World9 + extra25 + graph3 + 기존 Memory owner controls1 + 영어 creator1 | `audit-20261007-next-final-copy.log` |
| 최종 Static browser | **42 PASS**, 1.3분: World9 + extra25 + 기존 static Memory1 + 기존 static relationship/bootstrap/window6 + 영어 creator1 | `audit-20261007-static-final-copy-2.log` |
| 기존 graph UI를 static transport에서 검사 | **3 PASS**, 4.3초 | `audit-20261007-static-scoped.log` |
| 전체 frontend lint | exit0, errors0/warnings0 | `audit-20261007-lint-copy-final.log` |
| TypeScript / ko-en catalog / UI error contracts | PASS / **16 namespaces·2617 source keys** / **53 PASS** | `audit-20261007-typecheck-copy-final.log`, `audit-20261007-catalog-copy-final.log`, `audit-20261007-ui-errors-copy-final.log` |
| 동적 문구 보조 검색 | Memory/Relationships/Characters/Media의 일반 Korean literal 중 해당 feature/shell catalog에 없는 key **각0개**. 실제 화면 번역은 위 browser 결과로 별도 확인한다. | `audit-20261007-dynamic-copy-scan-final.log` |
| 최종 Next production / static export build | 모두 exit0 PASS | `audit-20261007-next-build-copy-final.log`, `audit-20261007-static-build-copy-final.log` |
| Backend current inventory / boundary | **1434 modules·6049 internal edges·4194 external imports**, legacy exact edges0 | `audit-20261007-architecture-inventory-final.log`, `audit-20261007-backend-architecture-final.log` |
| Frontend boundary / design | **14 features·legacy exact edges0** / **raw colors1183·files35·surfaces18·route gaps0·screenshot calls40** | `audit-20261007-frontend-architecture-final.log`, `audit-20261007-design-final.log` |
| Git patch hygiene | `git diff --check` exit0 | source commit前 확인 |
| Exact code-delta / node introduction | 두 정확한 commit delta append PASS / backend 새 node2 append PASS | `audit-20261007-exact-changes.log`, `audit-20261007-exact-copy-changes.log`, `audit-20261007-node-additions-final.log` |
| 기존 기록 prefix / frozen 파일 / 원본 계획 | 이전 기록 **171/358개 전부 유지**, append 후 **173/359개** / frozen6개·migration/schema·원본 계획3개 hash 유지 PASS | `audit-20261007-preserved-inputs.log` |
| Backend canonical preservation | **protected lineages5480 / current5480·items37 PASS**, frozen PR258 nodes1867·PR263 nodes1907 유지, 일반 CLI exit0 | `audit-20261007-preservation.log` |
| 최종 frontend preservation | **324 source files PASS**, browser assertions/fixtures/assets/locks 보존, exit0 | `audit-20261007-frontend-preservation-final.log` |

Backend의 SKIP 1건은 `P7_GRAPH_POSTGRES_DATABASE_URL`을 요구하는 별도 PostgreSQL `SKIP LOCKED` 동시성 검사다. 이번 계약에 따라 PostgreSQL을 실행하지 않았다. Starlette/httpx2 및 anyio alias의 기존 deprecation warning 2건은 오류나 품질 PASS로 바꾸지 않는다.

## 실패 재현과 검사 구성 실패의 구분

- `audit-20261007-before.log`: 수정 전 static에서 owner 변경, 같은 owner 재발급, raw 오류 표시의 **3 FAIL**을 재현했다. max-fail 제한으로 나머지3건은 실행되지 않았으며 runner 종료 메시지도 남았다.
- `audit-20261007-memory-before.log`: 수정 전 Next의 `/memory`에서 다른 owner로 전환해도 이전 private 기억과 키 초안이 남는 **1 FAIL**을 재현했다.
- `audit-20261007-copy-before-corrected.log`: 기존 static에서 영어 Memory 정리 카드의 실제 상태·모델 도움말·실패 문구가 한국어로 남고 Chat 키를 안내하는 **1 FAIL**을 재현했다. 수정 후 ko/en 두 case와 관계 오류4 case는 Next **6 PASS**, 최종 양 환경 묶음에서도 PASS했다.
- `audit-20261007-hours-before-corrected.log`: 영어 활동 설정의 익일 시간 설명이 한국어로 남는 **1 FAIL**을 재현했다. 계산식을 복제하지 않고 기존 validator의 문장만 번역한 후 최종 두 환경에서 당일/익일·동일 시간·18시간30분 초과 결과를 검사했다.
- `audit-20261007-next-review.log`: bootstrap 401 재진입 때문에 logout 검사가 실패했다. `session.ts`를 수정한 후 같은 검사와 최종 양 환경 묶음이 통과했다.
- 늦은 correction 검사 첫 두 구성은 busy Dialog 뒤의 링크를 실제 pointer로 누르거나 Escape로 닫으려 해 실패했다. 기존 modal은 busy 중 그런 조작을 정상적으로 막는다. modal을 약하게 바꾸지 않았고, 실제 링크의 외부 route 활성화를 재현하도록 검사만 바로잡았다. corrected 구성은 기존 static에서도 PASS했고 현재 Next/static에서도 PASS했다. 이를 수정 전 제품 실패 재현으로 주장하지 않는다.
- `audit-20261007-next-final.log`: CLI의 파일 정규식 `product-shell.spec.ts`가 static 전용 파일도 선택해 Next에서 **4 FAIL/31 PASS**가 났다. Next/static의 정확한 파일·transport로 재실행한 최종 **35/38 PASS**와 구분한다. 기존 testMatch나 단언은 줄이지 않았다. 처음 추가한 `^world...` regex가 절대 파일 경로에 맞지 않아 3/4개만 실행한 로그도 보존하며 최종 전체 수로 합산하지 않는다.
- current backend import inventory의 첫 `--check`는 신규 import 4개 때문에 stale이었다. 공식 generator로 현재 inventory만 갱신하고 check/boundary를 다시 통과했다. frozen refactor evidence와 역사 schema 지문은 재생성하지 않았다.
- 추가 번역 검사의 초기 fixture가 영어 선택을 한국어 auth 응답으로 덮어쓴 실패, 새 활동 시간 검사에서 기존 영어 label을 잘못 지정한 실패, static creator의 `ANGMOO_CREATOR_STATIC=1` 누락 실패는 검사 구성 오류였다. 언어·기존 label·해당 transport를 바로잡았으며 기존 기능/단언을 약하게 바꾸지 않았다. static 첫 묶음 **41 PASS/1 FAIL**과 최종 **42 PASS** 로그를 모두 보존한다.
- 추가 KO catalog의 legacy 앵무 표현이 product copy 금지 규칙을 위반해 처음 catalog 검사가 실패했다. source key는 유지하고 KO 표시 값만 캐릭터 표현으로 고쳤다. checker·금지어 기준을 수정하지 않았으며 최종 catalog는 PASS했다.

## 기능·증거 보존

기존 backend 테스트 2개와 기존 extra UI 긴 이름 테스트 6개는 유지한 채 새로운 backend node 2개와 browser case19개를 추가했다. 기존 영어 creator case의 부제 단언5개도 추가했다. 서버 DTO/route/ORM/schema/default/cap/provider 기능은 이 audit에서 바꾸지 않았다. API helper의 optional signal과 시간 validator의 optional 번역 인자는 기존 call sites를 유지한다.

`security/architecture_import_baseline.json`은 **현재 import inventory**이며 실제 import4개에 맞춰 official generator로 갱신했다. `docs/architecture/frontend-design-baseline.json`은 **현재 design inventory**의 변경 source hash2개만 갱신했다. frozen PR258/PR263/backend/frontend checkpoint·path map·migration·기존 기록 prefix는 그대로 보존한다.

Exact append 증거는 `df815d23`의 source blob14·기존 definition2·frontend hash12·기존 assertion 변경0·route/ORM 변경0, `d9d498ed`의 source blob14·definition0·frontend hash14·기존 backend assertion 변경0·route/ORM 변경0이다. node 소개 증거는 첫 코드 커밋의 실제 신규 node2에만 추가했다. 이전 JSON prefix와 frozen6개, migration/schema 및 원본 계획3개 hash가 유지되는 것을 별도로 검사했다.

최종 일반 CLI `check_refactor_preservation.py --contracts --nodes`가 **protected lineages5480 / current5480·items37**, exit0으로 종료했다. 기존 판정의 5478개 계보와 이번 신규 node2개를 유지하며 frozen PR258/PR263 수집도 유지했다. 최종 frontend 보존 CLI는 source324·browser assertions/fixtures/assets/locks 보존, exit0이다. checker의 predicate나 기존 testMatch·단언을 수정하거나 검사를 우회하지 않았다. 코드 보완 두 커밋 이후에는 문서·현재 inventory·append 증거만 정리했다.

최종 branch는 `feat/0.1.0-release-readiness`이다. 코드 마지막 HEAD는 `d9d498ed`; 이전 완료 HEAD `6c862f04`에서 두 코드 보완 커밋을 이어 쌓았다. 문서/현재 inventory/증거를 별도의 Signed-off-by 로컬 커밋으로 보존하고 `git status --short`로 clean을 확인한다. 이 보고서 자신의 커밋은 마지막 `git log -3`으로 확인할 수 있다. push/PR/hosted CI/main 작업은 수행하지 않는다.

호스트 screenshot에서 영문 World 카드와 200% 관계망 제목·코랄 원/흰 아이콘·부제·버튼 배치를 확인했다. DOM/SVG 회귀가 읽기 순서·모든 이름/방향·겹침과 overflow를 별도로 검사한다. Windows screenshot을 공식 pixel baseline으로 대체하지 않았다. 검증에 직접 만든 두 preview의 process/port 소유자를 확인하고 해당 process tree만 종료했으며 3338/3339 listening 수0을 확인했다.

## 재시작과 검증 경계

재개할 때 지정 branch와 실제 HEAD/working tree부터 확인한다. 합성 browser fixture는 `browser-tests/playwright.world-memory-integration.config.ts`의 같은 feature 화면에 연결하며 Next/static 전용 transport를 서로 바꿔 실행하지 않는다. 사용자 port3000이나 설치판으로 결과를 대체하지 않는다.

```powershell
Set-Location 'D:/project_code/angmoo-workspace/angmoo-tree-angmoo'
if ((git branch --show-current).Trim() -ne 'feat/0.1.0-release-readiness') { throw 'Unexpected branch' }
git status --short
git rev-parse HEAD
$env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_refactor_preservation.py --contracts --nodes
& 'backend/.venv/Scripts/python.exe' scripts/ci/check_refactor_frontend_preservation.py
```

실제 AI 품질/비용/지연, tokenizer/provider capability 실측, native Vec1 검색 성능, 공식 Linux pixel baseline, 설치판/Tauri 직접 검수, USER CHECK, 실사용 자료 전환, hosted CI/PR/main/배포는 이번 검증의 PASS 범위에 포함하지 않는다. I50/I51은 계속 보류한다.
