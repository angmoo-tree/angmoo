# SNS·Chat 기억 검색 조회·재검증 최적화 로컬 검증

- 기준일: 2026-10-17, Asia/Seoul.
- 작업 브랜치: `feat/chat-temporal-recall-fallback`.
- 기준 커밋: `c3649d013348968097dbb337f31d57f9b027f3bc`.
- 실행 계획: workspace `docs/plan/10-17 SNS·Chat 기억 검색 조회·재검증 최적화와 시간초과 개선 코드 구현 세부 계획.md`, I00–I63.
- 범위: 제품 코드, 관련 합성 회귀, 비용 측정, 문서, 로컬 DCO 커밋. 시작 작업 트리는 깨끗했다.
- 실행 환경: Windows, 고정 backend `uv run --frozen` Python 3.13 환경, frontend의 기존 pnpm/Node 환경. 개인 DB·대화·키·원본 진단 파일을 시험 자료나 커밋에 포함하지 않았다.

## 구현과 보호 경계

| 경로 | 구현과 유지한 계약 |
| --- | --- |
| SNS / Chat → `HybridRecallService` | 후보 50, RRF k=60, 기존 중복 제거와 결과 제한을 유지하고 canonical 검증·선택·후속 정정·조립을 `resolve_async` 한 번으로 실행한다. 검색 축과 임베딩을 추가 호출하지 않는다. |
| Runtime canonical worker | 한 queue item 안에서 Session, 시각, `BEGIN DEFERRED` 읽기 스냅샷을 소유한다. 기존 queue 용량 8, deadline/취소/interrupt/rollback/connection 반환/shutdown drain을 유지한다. 쓰기 예약을 잡지 않는다. |
| Memory 권한·출처 정책 | 날짜상 제외가 확실한 후보의 무거운 출처 확장만 앞에서 피한다. legacy 다중 출처 시간과 손상 situation 거부, Memory OFF, owner/World/캐릭터/thread, version/digest, prior/cycle 정책을 유지한다. |
| Runtime 외부 도메인 사실 | SocialEvent, event evidence, observation, 실행·주관적 기록을 고유 식별자 단위로 묶는다. 400개 SQL chunk, source별 8개 제한 후 사건 종류 필터라는 기존 정책을 유지한다. 여러 observation 중 기존 SQL이 선택한 identity가 필요한 경우 그 선택을 한 번 조회해 재사용한다. |
| 작업 내부 재사용 | row와 missing 사실, manifest, prior, thought, 후속 정정 조회는 같은 Session/시각/작업 안에서만 재사용한다. 전역 TTL 캐시, 새 background 작업, 스키마 변경은 없다. |
| SNS 최종 재검증 | 기존 `assert_memories_current`의 실제 전달 자료·snapshot 비교를 유지한다. 새 follow-up, 원본/권한/유효 시각의 변경을 감지한다. 동일 guard 안의 출처 조회만 공유한다. |
| Chat 최종 재검증 | 검색 결과의 immutable snapshot을 요청에 보존한다. provider 직전, provider 반환 후 delta 전달 전, streaming await 이후 최종 저장 전에 새 worker 읽기로 전달 기억과 제한된 seed/follow-up 의존성을 비교한다. 검색 50개를 다시 찾거나 임베딩하지 않는다. guard는 요청 마감 안에서 최대 4초이며 읽기 캐시를 넘겨받지 않는다. |
| 최종 저장 | World·lease·이름·이미지·관계·Today SNS의 기존 fence와 상황기억 admission을 유지한다. 변경된 기억은 `source_context_changed`로 차단하며 근거를 삭제하고 성공으로 저장하지 않는다. 비싼 검사를 write UoW 안으로 옮기지 않는다. |
| 진단 | 한 resolve의 검증/조립 비용과 실패 직전 관측 비용을 제한된 수치로 보존한다. 실행 전 queue 마감은 unknown이다. `metrics_complete=false`는 그 시점까지 일부만 관측했음을 뜻한다. FTS 준비 상태는 worker transport 성공과 별도다. |
| UI | 기존 공용 검색 진단과 export allowlist에서 선택적 필드만 표시한다. 한국어·영어를 함께 제공한다. `retrieval_timeout` 안내를 검색 실패로 구분하고 provider 실패·권한 거부·BUSY·취소를 같은 오류로 바꾸지 않는다. |

### 실제 저장 회귀에서 확인해 수정한 누락

기존 `SituationSources.describe`는 공개 MemoryItem의 `thread_id=None`을 현재 Chat의
`private_thread_id`로 대체했다. 그 결과 공개 SNS 기억을 참고해 저장한 Chat 상황기억은
다음 기억 정리 때 원본 기억의 thread와 다르다는 이유로 `situation_prior_changed`가 됐다.
원본 MemoryItem의 thread identity는 그대로 보존하고, 새 Chat 기억의 비공개 범위는
manifest에 별도로 유지하도록 수정했다. 다른 비공개 thread의 기억을 허용하는 변경은 아니다.

이 문제와 Chat의 provider 대기 후 memory currentness 연결 부족은 I25–I31의 실제
저장·삭제·권한 보호를 검증하면서 확인했다. 기존 검증 제거, timeout 증가, 자동 provider
재시도로 해결하지 않았다. 이미 차단된 운영 receipt를 수정하거나 재처리한 것은 아니다.

## 비용 측정

개인 데이터 대신 `recall_cost_fixture.py`가 만든 파일 SQLite WAL을 사용했다. 후보 50개,
후보별 SocialEvent 출처 10개이며 shared는 255개 고유 출처, unique는 500개 고유 출처다.
seed/admission/application은 실제 저장 코드를 사용하며 검색 축/임베딩은 합성 응답이다.
각 조건은 warm-up 후 20회 비프로파일 실행했다. p95는 보수적인 상위 order statistic을
사용하며 표본 20회에서는 최댓값과 같다. 실패를 성공 표본에서 누락하지 않았다.

baseline은 기준 커밋의 `backend/app`을 `git archive`로 ignored artifact에 추출하고
같은 fixture·harness·의존성 환경에서 import했다. 현재 브랜치/제품 checkout을 바꾸지 않았다.

| 측정 구간 / 각 20회 | SQL 전 → 후 | 중앙값 ms 전 → 후 | p95 = 최댓값 ms 전 → 후 | 실패 |
| --- | --- | --- | --- | --- |
| 전체 hybrid / 공유 출처 | 1,854 → 68 | 1,202.337 → 172.174 | 1,360.643 → 320.639 | 0 / 0 |
| 전체 hybrid / 고유 출처 | 3,205 → 73 | 1,868.457 → 258.875 | 2,140.584 → 436.787 | 0 / 0 |
| 후보 검증만 / 공유 출처 | 1,297 → 27 | 539.834 → 98.480 | 826.123 → 277.734 | 0 / 0 |
| 후보 검증만 / 날짜 전부 제외 | 1,292 → 8 | 530.105 → 18.507 | 717.905 → 26.360 | 0 / 0 |
| 기존 SNS fresh guard / 공유 출처 | 380 → 62 | 261.952 → 105.020 | 414.248 → 220.821 | 0 / 0 |
| 기존 SNS fresh guard / 고유 출처 | 380 → 62 | 189.693 → 98.091 | 317.168 → 237.330 | 0 / 0 |

전체 hybrid의 SQL은 각각 **96.3% / 97.7%**, 중앙 시간은 **85.7% / 86.1%** 감소했다.
같은 고비용 fixture에서 가설인 SQL 75%·canonical 시간 40% 감소를 충족했다.
기존 문자 예산에 따른 반환 6개와 payload 의미가 전후 일치했다. 비교 digest는
무작위 fixture reference만 정규화한
`a65024cec45d5a0515ea69adb033c6dd47de00951cecd38e19fe69da6d8b901a`다.
identity·순위·후속 연결은 별도 구조 회귀로 확인하며 무작위 ID까지 byte 동일하다는 뜻은 아니다.

최종 상세 진단 표본은 공유 출처에서 queue 대기 0.192ms, resolve 133.813ms,
검증 27 SQL / 76.290ms, 조립 40 SQL / 50.829ms였다. 고유 출처는 queue 대기
0.200ms, resolve 278.462ms, 검증 32 SQL / 174.932ms, 조립 40 SQL / 90.324ms였다.
각 resolve는 unique node 50, memo hit 12, cleanup 완료였다. SQL 합계에는
`BEGIN DEFERRED` 1회가 포함되며 하위 단계와 총계를 중복 합산하지 않는다.
이 수치는 상세 진단 ON인 단일 표본이며 위 비프로파일 반복 중앙값과 구분한다.

새로 연결한 Chat fresh guard는 공유/고유 조건 각각 SQL 66회,
중앙값 **133.597 / 130.381ms**, 최댓값 **156.083 / 160.711ms**였다(각 20회, 실패 0).
이 guard는 기존 검색에 없던 provider 이후의 보호 연결을 보완하므로 동일한 baseline
비교값은 없다. 정상 Chat에서 provider 전·후와 최종 저장 전의 읽기 비용은 추가된다.
그 비용을 숨기지 않으며, 전체 후보 재검색·임베딩·새 쓰기 잠금은 추가하지 않는다.

실제 제공자 대신 vector fake에 **650ms 지연**을 추가한 검색은 공유/고유 조건
각 20회 모두 기존 4초 deadline 안에서 끝났다. 중앙값은 **881.598 / 918.770ms**,
최댓값은 **1,034.814 / 1,103.864ms**, 실패는 **0 / 0**이었다.
실제 provider 응답 생성까지 포함한 end-to-end 지연은 아니다.

근거 JSON은 ignored artifact의 `baseline.json`, `optimized-final.json`,
`baseline-extended.json`, `optimized-extended.json`이다. baseline extended의 JSON은
명시적 max/failures 필드 추가 전 형식이지만 20회 모두 성공했고 그 표본 정의상 p95가 max다.
수정 전 작은 fixture는 SQL 33회가 유지되며 시간 변동이 있었으므로 모든 요청에서
동일한 비율의 시간 개선을 주장하지 않는다. 추가 비용은 작업 내부 자료의 메모리,
제한된 read snapshot 수명, 필요한 fresh guard다. 읽기 중 WAL checkpoint 비용까지
없어진다는 뜻은 아니며 provider 대기 중에는 읽기 Session을 유지하지 않는다.

현재 비용 측정은 로컬 합성 자료의 결과다. 실제 임베딩 서버, 사용자 자료 규모, OS 부하,
queue 경합에 따른 모든 시간초과가 사라졌다는 의미가 아니다. 기존 Chat 검색 4초,
SNS semaphore 포함 15초, CRG 예약, 후보·결과 예산은 늘리지 않았다.

## 관련 검증과 재현 명령

명령은 별도 표시가 없으면 제품 `backend`에서 `uv run --frozen python -m pytest`로
실행했다. 전체 backend/frontend suite, 전체 Next/static build, installer/release 시험을
실행하지 않았다. 아래는 관련 범위를 선택한 검증이며 개수는 중복 합산하지 않는다.

| 관련 실행 묶음 | 실제 결과 | 보호하는 내용 |
| --- | --- | --- |
| hybrid / worker lifecycle / composition / follow-up / packet / SNS revalidation / proof | 56 PASS, 238.64초 | 기존 선택·취소·정리·scope·후속 연결·SNS 전달 보호 |
| early-date / activity situation / source cost / canonical read cost / event source | 13 PASS, 24.21초 | 같은 결과·날짜 선별·공유 prior·출처 조회량 |
| fresh guard / source batch / event source / WAL snapshot / observer lifecycle | 20 PASS, 40.29초 | root version이 안 바뀐 권한·출처·시간 변화, 독립 writer, 관찰 종료 |
| 실제 Chat 저장 / time provenance / situation proof / canonical diagnostics | 30 PASS, 198.54초 | 정상 응답→상황기억→실제 기억 저장, provider 대기 중 변경 차단, timeout/queue 진단 |
| Chat 시간 해석·fallback·저장 규격·오류 분류·진단 | 121 PASS, 기존 1 SKIP, 85.34초 | 정상 날짜 조건 보존, typed timeout, 상세 진단과 이전 계약 |
| 마지막 public/private thread 저장 assertion + source batch | 4 PASS, 10.74초 | 공개 원본 thread 보존, 다른 비공개 thread 거부, 마지막 chunk 변경 |
| 최종 20회 검증 비용 fixture | 1 PASS, 14.21초 | SQL 27 / 8, 기존 후보 수와 날짜 의미 유지 |
| frontend 진단 script | 10 PASS | 선택적 resolve 필드, 실패 비용, export 제한, ko/en·구버전 |
| 변경 TS/TSX lint·typecheck | PASS / exit 0 | 공용 타입 연결·실제 변경 파일 |
| backend 최신 import inventory / boundary | PASS / exit 0 | 1,568 modules, 6,803 internal edges, 4,609 external imports; legacy exact edges 0 |
| frontend architecture / design | PASS / exit 0 | features 14, legacy 0; 기존 디자인 정책 유지 |

위 묶음은 일부 파일을 공유한다. 합산해서 고유 테스트 수로 표시하지 않는다.
기존 SKIP 1개는 `ANGMOO_DIAGNOSTIC_BENCHMARK=1`일 때만 수행하는 별도 성능 시험이며,
이번의 독립 고비용 측정은 위 JSON으로 완료했다. 삭제된 원본의 보존 허용 summary를
fresh guard가 유지하는 추가 회귀도 통과했다. 마지막 assertion 이전 실패로 드러난
공개 prior thread 문제는 실제 저장 경로를 고쳐 통과시켰다. 실패 검사를 삭제하지 않았다.

```powershell
uv run --frozen python -m pytest -q tests/memory/test_recall_source_batch.py tests/memory/test_episode_social_sources.py tests/memory/test_hybrid_read_snapshot.py tests/memory/test_recall_delivery_currentness.py
uv run --frozen python -m pytest -q tests/chat/test_recall_delivery_persistence.py tests/chat/test_temporal_evidence_persistence.py tests/memory/test_situation_proof_guards.py tests/memory/test_canonical_resolution_diagnostics.py
uv run --frozen python -m pytest -q -rs tests/chat/test_hybrid_canonical_guards.py tests/chat/test_temporal_recall_response.py tests/chat/test_temporal_recall_fallback.py tests/chat/test_temporal_evidence_storage_contract.py tests/chat/test_recall_timeout_classification.py tests/chat/test_search_diagnostic_capture.py tests/chat/test_search_diagnostic_lineage.py tests/chat/test_retrieval_diagnostics_limits.py
uv run --frozen python -m pytest -q tests/memory/test_hybrid_recall.py tests/memory/test_canonical_worker.py tests/memory/test_canonical_worker_lifecycle.py tests/memory/test_canonical_read_composition.py tests/memory/test_episode_candidates.py tests/memory/test_episode_packet_repository.py tests/runtime/test_activity_memory_revalidation.py
uv run --frozen python -m pytest -q tests/runtime/test_observation_session_lifecycle.py
uv run --frozen python ../scripts/ci/generate_architecture_inventory.py --check
uv run --frozen python ../scripts/ci/check_architecture_boundaries.py
```

수동 비용 측정은 `ANGMOO_COST_REPEATS=20`과 ignored 위치의 `ANGMOO_COST_OUTPUT`을
설정하고 `tests`를 PYTHONPATH에 둔 뒤 `tests/memory/recall_cost_measurement.py`를 실행한다.
`ANGMOO_COST_SIMULATED_LATENCY=1`은 실제 모델 대신 vector fake에 650ms를 추가한다.

프론트엔드에서는 다음 관련 검사만 실행했다.

```powershell
node scripts/test-chat-diagnostics.mjs
pnpm exec eslint src/features/chat/components/search-trace-details.tsx src/features/chat/components/world-chat.tsx src/features/chat/types/search-trace.ts src/features/chat/utils/diagnostic-export.ts
pnpm typecheck
```

영문 실제 렌더에서 기존 동적 진단 키 일부가 한국어 fallback을 쓰는 문제가 드러나
해당 키의 영어·한국어 catalog를 함께 보완했다. 공유 `SearchTraceDetails`를 실제 React로
ko/en 렌더하고 기존 parent/module CSS를 적용한 로컬 Chromium에서 320/390/1280 폭,
수평 overflow 없음, Tab/Enter disclosure 동작을 확인했다. 영어 접두어·수치 사이 공백도
보완했다. Next/static은 같은 컴포넌트를 import하는 경로를 확인했다.
두 앱 전체를 실행한 브라우저 E2E 또는 canonical pixel 승인은 수행한 것으로 기록하지 않는다.

## V00–V31 증거 연결

| 검증 ID | 관련 증거 |
| --- | --- |
| V00–V01 | `test_episode_hybrid_reader`, `test_activity_situation_recall`, 날짜 전부 제외 비용 fixture; 손상 origin은 기존 proof 회귀로 거부 |
| V02–V05 | `test_recall_source_batch`, `test_canonical_read_cost`, `test_recall_source_cost`, shared/unique 비용 harness; scope 혼용·negative cache·400 chunk·source별 cap 비교 |
| V06–V08 | `test_hybrid_recall`, `test_episode_candidates`, `test_episode_packet_repository`, `test_canonical_read_composition` |
| V09–V10 | `test_situation_proof_guards`, `test_activity_situation_recall`, `test_episode_social_sources` 및 관련 owner/prior 보호 회귀 |
| V11 | `test_hybrid_read_snapshot`: 독립 writer가 MemoryScopeSetting만 변경, 첫 read는 일관된 snapshot, 다음 guard는 거부 |
| V12–V15 | `test_recall_delivery_currentness`, `test_recall_delivery_persistence`, 기존 `test_activity_memory_revalidation`: root version 불변의 권한/원본/만료, 새로운 follow-up과 무관한 자료 구분 |
| V16 | 이미 삭제된 원본의 보존 허용 summary guard, 기존 partial axis 시험; forbidden을 missing으로 대체하지 않음 |
| V17 | 실제 episode 근거 → Chat 저장/time_provenance → 상황기억 admission → 기억 정리 적용, 원본과 새 private thread 구분 |
| V18–V20 | canonical worker/worker lifecycle/read composition, `test_canonical_resolution_diagnostics`: queue 미실행·deadline·cancel·rollback·pool 재사용 |
| V21–V22 | canonical 실패 전 axis_reason, FTS 준비 중+vector 사용 가능, typed retrieval timeout와 provider/계약/취소 예외 분리 |
| V23 | temporal response/fallback/storage/persistence 회귀. 정상 날짜 필터를 timeout 때문에 버리지 않음 |
| V24–V26 | search diagnostic capture/lineage/limits, resolve diagnostics, observer 종료 lifecycle, frontend allowlist/old receipt 시험 |
| V27 | ko/en 공유 React 렌더·좁은 화면·키보드·eslint·타입·frontend architecture/design |
| V28–V29 | 동일 기준 SHA/고정 환경/20회 비용 측정과 임시 파일 WAL 독립 writer/async timer 시험 |
| V30–V31 | 현재 소스로 재생성한 import inventory와 architecture policy 검사, scoped diff·문서·로컬 커밋 |

## 상태와 한계

- **LOCAL COMPLETE:** I00–I63에 해당하는 코드·관련 합성 회귀·비용 비교·문서를 완료했다.
  로컬 커밋 식별자와 최종 작업 트리는 workspace 계획 §12와 Git에 기록한다. 이 문서를
  포함한 커밋의 부모가 위 기준 SHA다. 공유·비공유 고비용 fixture에서는 기존 제한 시간
  안에 완료했으며 실제 사용자 환경의 모든 timeout 해결을 의미하지 않는다.
- 상세 계측 OFF는 새 SQL·파일 갱신·상시 작업을 만들지 않는다. 기존 observer 종료 시험에서
  종료 뒤 연결/파일 갱신 중지와 재시작 시 종료 세션 미연결을 별도로 확인한다.
- 실제 AI 응답 품질·자연스러운 SNS 활동·사용자 데이터의 체감 성능: 미측정.
- 운영 Docker·설치본 반영, 사용자 직접 확인: 미수행.
- publish/push·PR·GitHub Actions CI·main merge·배포: 요청에 따라 미수행.
- 산출물: ignored `artifacts/recall-validation-optimization-20261017/`의 전후 JSON,
  기준 app archive, 합성 UI HTML/PNG. 이 기록을 공개 배포·실제 AI 품질 PASS로 합치지 않는다.
