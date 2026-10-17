# Chat 시간 해석·날짜 조건 실패 복구와 DB 쓰기 진단 로컬 검증

- 기준일: 2026-10-17 / Asia/Seoul
- 범위: workspace 계획 `10-17 Chat 시간 해석 개선과 날짜 조건 실패 시 관련 기억 검색·응답 지속 코드 구현 세부 계획.md`의 I00–I63, V00–V33.
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 브랜치: `feat/chat-temporal-recall-fallback`
- 시작 main: `0b8119644caf3e0d9f38a20eda1efb7575aff010`; 시작 작업 트리 clean.
- 판정: **관련 로컬 구현·검증 완료**. 이 문서는 구현과 함께 로컬 커밋한다. 최종 SHA·종료 Git 상태는 workspace 계획의 실행 결과에 기록한다.
- push, PR, GitHub Actions 실행·재시도, main 병합, 배포를 수행하지 않았다. 사용자 Docker·설치본·운영 DB·키·기존 관찰 세션을 변경하지 않았다.

## 1. 수정한 동작과 유지한 보호

신규 `social_hybrid` Chat은 `selection-args.hybrid.v4` / `hybrid-admission.v4`를 사용한다. 질문 접수 시각과 당시 시간대를 `chat-time-context.v1`으로 고정하고 digest를 검증한다. 최초 선택·1회 보정·Today SNS 입력·명시적 재시도는 같은 기준을 사용한다. 실행 제한 시간과 현행 접근 권한은 현재 상태로 검사한다. 과거 v1–v3 요청 재생과 기존 evidence hash는 유지한다. 명시적 재시도만 검증된 원래 메시지 시각·환경에서 v4를 구성할 수 있다.

전체 입력 크기·금지 자료·검색어·도구·집계·coordination을 먼저 검사한 뒤 시간만 별도로 분류한다. 잘못된 시간을 유효한 `RetrievalTimeMeaning`으로 만들지 않는다. 최초 시간 오류는 기존 보정 한도를 소비하고, 보정도 시간만 실패하면 날짜 필터 없이 기존 한도 내 관련 검색을 한 번 수행한다. 형식이 유효하지만 해석이 모호한 시간도 날짜를 꾸며 내지 않는다. 정상 날짜 검색의 0건 결과는 확대하지 않는다.

`USE_CONTEXT`나 시간 전용 명확화에서 검색으로 전환할 때는 검증한 원래 질문을 명시적인 code-owned query로 사용한다. `query_origin`과 실제 recipe·도구 경로를 함께 기록한다. 잘못된 CANONICAL 검색어를 원문으로 덮어 통과시키지 않는다. 다른 명확화·인사·Memory OFF·권한·World/캐릭터 삭제·취소·deadline 보호를 유지한다.

시간 상태·기준 시각·query origin·실제 날짜 범위·evidence를 intent/resolved/interpretation hash로 묶는다. CRG에는 실제 검색 실행 여부와 제한된 검색의 범위를 전달한다. 사건 시각, 검증된 출처들의 날짜 구간, 기억 저장 시각, 확인 불가를 구분한다. 일반 기억의 `valid_from`을 사건 시각이나 저장 시각으로 추정하지 않는다. 원본 POST/REPLY 등은 기억과 연결되어 있어도 해당 원본의 사건 시각을 유지한다. 새 private 준비 메타데이터는 v4에서만 evidence payload/hash에 포함한다.

최종 provider 입력에 한국어·영어 시간 지침이 들어간다. 날짜 조건 실패만으로 답변을 포기하지 않되, 과거 사건을 오늘로 옮기거나 제한된 검색을 전체 이력으로 설명하지 않도록 한다. 실제 모델의 자연어 품질을 보장한다는 판정은 아니다.

## 2. 소유권과 후속 기억 처리

| 영역 | 구현 소유권 |
| --- | --- |
| 시간·버전·해시 | `chat/contracts/temporal_recall.py`, retrieval intent/router/interpretation 계약 |
| admission·재시도·경로 | Chat generation/routing/response service, 기존 runtime composition |
| 사건/저장 시각 | Memory의 검증된 source reader·packet hydration → Chat evidence assembly |
| 모델 입력 | 기존 Supervisor/CRG adapter; 새 모델 호출·검색 엔진 없음 |
| DB 계측 포트 | `core/work_observation.py`, `core/session_write_observation.py` |
| 요청별 저장·DTO | Chat `DbWriteCollector`, 기존 `DiagnosticCapture` 및 diagnostics API |
| 사용자 화면 | 기존 Chat 진단·Memory 근거 inspector, feature 소유 번역·CSS |

`ChatSituationMemory.freeze`는 최종 provider payload digest를 보존한다. 검색한 기억은 `prior`, 원본 기록은 `background`, 현재 대화와 실제 저장한 답변은 기존 `core` / `committed_result` 역할을 사용한다. `situation_generation.instructions`도 `recall_interpretation`과 명확화 후보를 확정 사건으로 취급하지 않는다. 기존 기억의 날짜나 본문을 이번 변경으로 rewrite하지 않는다. 새 Chat 활동의 발생 시각과 과거에 검색한 근거의 사건 시각은 별도 의미다.

실제 scope 변경 시험은 v4의 시간 오류→보정→CRG 반환 사이에 World 삭제 접수, membership 해제, 캐릭터 삭제를 각각 넣었다. 세 경우 모두 assistant 저장이 차단됐다. 원본 변경·접근 권한·버전은 기존 Today SNS snapshot validator와 Memory의 selection/hydration 재검증 시험을 함께 확인했다.

## 3. DB 계측의 의미와 비용 경계

계측은 기존 상세 진단 opt-in 안에서만 요청별로 수집한다. admission의 request ID가 생기기 전 자료를 접수 성공 후 연결하고, 중간 checkpoint·내부 진단 SAVEPOINT·최종 응답 commit·취소/실패·실제로 수행된 post-commit 작업을 구분한다. 마지막 commit 반환 후 수치는 메모리에서 완성하며 이를 저장하기 위한 추가 commit은 없다.

- 공통 `BEGIN IMMEDIATE` 처리: 연결 준비, BEGIN 실행+획득 대기, 획득 이후 보유, commit/rollback, 실제 재시도 대기를 구분한다.
- 일반 Session/DEFERRED 처리: 첫 쓰기부터 기존 소유자의 commit/rollback 반환까지 **write span**이다. 실제 SQLite 잠금 획득 시각을 모르므로 hold는 `null`이다.
- commit과 내부 진단 저장은 바깥 구간에 포함된다. SAVEPOINT 종료를 별도 writer 해제로 세지 않는다.
- 가장 긴 단일 hold와 합계를 구분한다. 미측정·누락은 0ms로 만들지 않는다.
- 상세 64개, 기존 공유 64KiB 결과·20개 결과·1MiB 예산·TTL을 유지한다. detail 생략 후에도 제한된 숫자 요약을 유지한다.
- OFF·TTL 만료·재활성화·재시작은 이전 generation 콜백의 수집을 중단한다. 새 파일·DB 테이블·주기 작업·retry 정책·트랜잭션 방식은 추가하지 않는다.
- 요청별 ContextVar listener는 기존 기억/SNS process sink를 교체하지 않는다. collector/시계 오류가 업무를 재실행하거나 실패시키지 않는다.
- SQL·매개변수·경로·대화 본문·키는 새 DB DTO에 넣지 않는다. DB 식별은 경로 hash이며 사용자 경로를 출력하지 않는다.

Windows / Python 3.13.12 / SQLite 3.50.4의 격리 WAL DB에서 각 경로별 OFF 60회·ON 60회를 교대로 측정했다. 준비 10회는 제외했고 직렬화 시간은 포함하지 않았다. BEGIN 획득 반환→commit 반환을 별도 probe로 측정해 동일한 probe 비용을 ON/OFF 양쪽에 적용했다.

| 경로 | OFF 중앙값 / p95 | ON 중앙값 / p95 | SQL / commit |
| --- | --- | --- | --- |
| immediate 전체 저장 | 4.1358 / 4.7547ms | 4.1136 / 5.5014ms | 양쪽 2 / 1 |
| immediate 별도 hold probe | 3.8524 / 4.3418ms | 3.6529 / 4.4504ms | 같은 저장의 부분 구간 |
| 일반 Session 전체 저장 | 4.2653 / 5.4198ms | 4.8631 / 6.2832ms | 양쪽 1 / 1 |

분포 전체는 [합성 계측 결과](chat-temporal-recall-20261017-measurements.json)에 보존했다. immediate의 중앙값 감소는 성능 향상 증거가 아니다. 일반 Session의 중앙값 차이는 약 0.598ms였지만 실제 요청·장비의 고정 오버헤드로 일반화할 수 없다. 일반 Session의 실제 hold와 실제 Chat/SNS 지연·경합 인과관계는 미측정이다.

## 4. 로컬 검증 결과

아래는 서로 일부 겹치는 별도 실행 묶음이다. 중복을 합산한 전체 테스트 수로 보고하지 않는다. 변경 범위의 계약·수명주기·SQLite·UI만 실행했으며 전체 backend/frontend suite, 전체 빌드·설치 시험은 실행하지 않았다.

| 묶음 | 결과 | 보호하는 동작 |
| --- | --- | --- |
| 시간 fallback 실제 adapter/workflow + Today source/current memory revalidation | 31 PASS | initial/repair/CRG 호출 수, 별도 writer, late 권한 변경, 원본 변경 |
| 시간 상태·시각 의미·legacy clarification·실제 situation hydration·hybrid 축 | 23 PASS | 고정 날짜, 어제/오늘/기록/unknown, interval hash, Memory OFF |
| 최종 변경 후 canonical FTS 재검증·packet·DB capture·DB 경계·hybrid admission | 44 PASS | 실제 FTS, 잘못된 후보 배제, opt-in/TTL, busy/rollback/commit, 범위 |
| 기존 advisory/named selection·routing·interpretation·lifecycle·cost | 118 PASS | v1–v3 재생, 잘못된 요청 거부, bounded lookup |
| 최종 commit·진단 SAVEPOINT·API auth·cancel/deadline·삭제 직렬화·기억 receipt·SQLite busy·기존 관찰 보고 | 28 PASS | 늦은 결과 차단, 원자 저장, 계측과 기존 sink 호환 |
| frontend diagnostic script | 8 PASS | 실제 컴포넌트 KO/EN render, null, JSON allowlist, request/attempt 정합성 |
| frontend evidence script | 6 PASS | 시각 의미 표시, legacy/invalid 자료, 현재 접근 불가 처리 |
| 실제 frontend 프로젝트 TypeScript 검사 | PASS | `tsc --noEmit` |
| 변경 TS/TSX만 ESLint | PASS | 관련 진단·근거 표시·export |
| architecture import inventory 및 backend/frontend 경계·frontend design | PASS | 현재 소유권, legacy 예외 증가 없음, semantic UI |
| 정상 날짜 0건·잘못된 서버 시간대·관련 architecture checker 회귀 | 20 PASS | 재검색 없음, 환경 오류를 날짜 fallback으로 숨기지 않음, 경계 검사 자체의 회귀 |

합성 시험의 초기 fixture 오류(enum/hash 구성)는 수정했고, 규칙을 완화하거나 skip/xfail하지 않았다. 실제 회귀에서 발견한 시간 검증 단계의 거짓 `pass`, 정상 Today guard의 query 전환, 최종 저장 단계 누락, generic memory 시각 오표시도 수정 후 관련 시험을 다시 실행했다. capture 만료 후 늦은 저장 허용을 기대하던 시험은 이번에 명시한 종료 계약에 맞춰 변경하고, 완료된 결과의 보관과 늦은 콜백 차단을 각각 검증했다.

### 재실행 가능한 관련 명령

제품 저장소의 backend에서:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/chat/test_temporal_recall_fallback.py tests/chat/test_temporal_recall_response.py tests/chat/test_db_write_diagnostics.py tests/chat/test_db_write_capture_lifecycle.py
.\.venv\Scripts\python.exe -m pytest -q tests/memory/test_activity_situation_recall.py tests/memory/test_episode_packet_repository.py tests/memory/test_p8_l_h_canonical_recall.py::test_canonical_service_revalidates_stale_fts_candidates_and_memory_off
```

frontend에서:

```powershell
node scripts/test-chat-diagnostics.mjs
node scripts/test-chat-evidence.mjs
node node_modules/typescript/bin/tsc --noEmit
```

기존 회귀의 정확한 파일/노드는 workspace 실행 결과 V 표와 각 테스트의 의미를 따른다. 영속 benchmark 결과는 합성 측정 원본이고, 실행 스크립트·DB·JUnit·화면 fixture는 무시되는 로컬 `artifacts/chat-temporal-recall-20261017`에 있다. 운영 자료를 시험 fixture로 복사하지 않았다.

## 5. 화면 확인과 남은 직접 확인

실제 `TemporalDbDiagnostics`와 `useUiText`/i18next, 변경 CSS를 렌더링한 독립 fixture를 loopback에서 열어 Headless Edge로 확인했다. 한국어·영어 모두 390px 폭에서 `scrollWidth=390`, 상세 열기 target 높이 44px였고 Tab→Enter로 펼칠 수 있었다. PNG도 직접 확인했다. CUA는 환경의 kernel asset 경로 오류로 초기화되지 않아 이미 설치된 Edge와 번들 Playwright를 사용했다. 새 브라우저 profile로 합성 페이지에만 접근했다.

이 검증은 전체 Angmoo 화면·Tauri 설치본 E2E가 아니다. 실제 사용자 채팅에서 표현이 자연스러운지, 원래 실패 질문이 현재 선택 모델에서 어떻게 답변되는지, 실사용 Chat/SNS 부하에서 잠금이 어떤 지연을 만드는지는 **USER CHECK / 미측정**으로 남긴다. 실제 AI·임베딩·이미지 모델은 호출하지 않았다.

## 6. 계획 항목 판정

I00–I06 기준/재현, I07–I13 시간 계약, I14–I20 모델 입력/해석, I21–I27 fallback/권한/hash, I28–I34 evidence/응답/후속 기억, I35–I41 진단/UI/지침, I42–I49 DB 계측, I50–I60 관련 검증/검토를 구현·확인했다. I61–I63은 이 문서를 포함한 signed local commit, workspace 계획 갱신, 최종 Git 상태 인계로 완료한다.

V00–V33은 계획의 로컬 fake-provider/격리 SQLite/화면 fixture 기준으로 판정한다. V05와 V14는 provider에 전달되는 입력과 deterministic 계산의 검증이며 실제 AI 의미 해석 성공률이 아니다. V21은 기존 feature의 component/browser fixture, V31은 위 합성 표본, V32는 병렬 요청과 기존 process sink 공존 시험이다. 실제 자연 활동이나 실사용 서버의 품질 PASS로 확대하지 않는다.

## 7. 후속 수정: 비어 있지 않은 시간 근거의 최종 저장

사용자 진단에서 검색·CRG는 완료됐지만 최종 저장이 rollback되고
`generation_conflict`로 끝난 요청을 확인했다. 원인은 v4에서 추가한
`time_provenance`를 `evidence-inspector.v1` 저장 검사가 허용하지 않은 계약
불일치였다. AI가 이 필드를 작성한 오류가 아니다. 최초 구현의 실제 workflow
회귀는 검색 결과가 빈 fixture였고, 비어 있지 않은 근거는 별도 payload/hash
시험으로 확인했으므로 이 연결 구간을 놓쳤다. 위 최초 결과가 이 경로까지
검증했다는 뜻으로 해석되지 않도록 후속 결과를 별도로 기록한다.

수정은 기존 item 필수 6개 필드에 `time_provenance` 하나만 선택적으로
추가한다. 내부는 `kind`, `event_from`, `event_to`, `recorded_at` 네 필드를
정확히 요구한다. timezone을 명시한 실제 ISO 날짜, 문자열 길이, 구간 순서와
종류별 조합을 Chat 계약 코드가 검사한다. 사건 시각을 모르는 `unknown`에도
별도로 확인한 저장 시각은 남길 수 있지만 사건 시각으로 승격하지 않는다.
생성 시 binding·최종 저장·근거 조회가 같은 검증을 사용한다. 기존 형식과 hash,
출처·권한·locator 검사, 트랜잭션·재시도·모델 호출 수는 유지한다. 새 migration,
AI 지침 수정, 필드 제거, 추가 모델 호출이나 오류 무시는 없다.

추가 회귀는 다음 경로를 보호한다.

- 격리 SQLite에 실제 게시글 4개를 저장하고, 검색 경계의 결정적 대역이 그중
  1개의 canonical 근거를 반환한다. 실제 Today SNS reader·admission·routing·
  CRG adapter·최종 저장·근거 조회를 사용한다. 외부 AI·벡터 API는 차단한다.
- 정상 날짜 경로와 시간 오류 보정 실패 후 관련 검색 경로 모두 최종 CRG에
  canonical 근거 1개와 Today SNS 근거 4개를 전달한다. 수정 전 두 경우 모두
  최종 `committed` 검사가 실패했다. 수정 후 답변 1개와 상황기억 receipt 1개가
  저장되고, 실제 근거 조회 5개 모두 available이며 재접속은 추가 호출·저장 없이
  완료 결과를 재생한다. 이후 원본을 수정하면 해당 근거의 본문·시간을 숨긴다.
- 실제 lifecycle repository에서 episode memory 1개와 Today SNS 4개를 포함한
  snapshot을 저장한다. legacy 필드 부재, event, 동일 시작·끝 시각, interval,
  recorded, unknown 및 unknown+recorded를 보존한다. 수정 전 legacy만 통과하고
  새 시간 payload의 정상 6개 경우는 `response_evidence_inspector_invalid`로 실패했다.
- 잘못된 날짜·시간대 부재·숫자/boolean 날짜·추가/누락 필드·역전 구간·종류별
  모순은 assistant를 추가하기 전에 거부한다. 같은 검사를 공유하는 social-context
  snapshot도 확인한다. 손상된 조회 자료를 임의 날짜로 변환하지 않는다.

최종 관련 실행은 **210 PASS / 실패·skip 0 / 116.29초**다. 이 수에는 새 회귀
**65개**와 기존 시간 해석·응답 수명주기·관계 근거·상황기억·권한 회귀가 포함된다.
초기 수정 확인 58개는 이 최종 실행에 포함되는 항목이므로 중복 합산하지 않는다.
CONTRIBUTING의 architecture checker 회귀는 별도 **18 PASS**였고, import inventory
갱신(1,564 modules / 6,785 internal edges / 4,602 external imports), backend/frontend
경계 검사와 `git diff --check`도 통과했다. legacy 예외는 양쪽 모두 0이며 완화하지
않았다. 전체 backend/frontend suite·빌드와 UI 검증은 이번 변경 범위에 포함하지 않았다.
재현 스크립트와 수정 전 결과, 최종 JUnit은
`artifacts/chat-temporal-finalize-diagnosis-20261017`에 보존하고, 수정 전 재현의
실패 기대값을 성공으로 덮어쓰지 않는다.

재실행 명령(제품 저장소 backend):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/chat/test_temporal_evidence_persistence.py tests/chat/test_temporal_evidence_storage_contract.py tests/chat/test_temporal_recall_fallback.py tests/chat/test_temporal_recall_response.py tests/chat/test_p8_l_j_response_generation_lifecycle.py tests/chat/test_p8_l_p_evidence_response_streaming.py tests/chat/test_response_lifecycle_owner.py tests/chat/test_evidence_ownership.py tests/chat/test_activity_situation_receipt.py tests/chat/test_social_context_workflow.py tests/chat/test_chat_identity_delivery.py
```

이번 수정도 현재 브랜치의 관련 검증·signed local commit 범위다. 실제 사용자
Docker 재빌드·재시작, 설치본 변경, 실제 AI 응답 품질 확인, PR/CI/main 병합은
수행하지 않는다. 사용자가 제공한 진단 원본과 운영 DB는 변경하지 않는다.
