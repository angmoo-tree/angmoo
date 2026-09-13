# 채팅 Supervisor·Graph 판단 진단 추가 실행 기록

- 실행일: 2026-09-12
- 상태: **진단 구현·로컬 검증·개발 runtime 반영 완료 / 사용자 5문항 결과·기본 진단 확인 / 1·3 상세값 판정 대기**
- 계획: [09-12 세부 진단기록 추가 계획](../../../docs/plan/09-12%20채팅%20Supervisor·Graph%20판단%20불일치%20원인%20분리를%20위한%20세부%20진단기록%20추가%20로컬%20계획.md)
- 로컬 브랜치: `fix/chat-retrieval-debugging`
- HEAD: `ee8eabf7c68e5a7fb7a5c4e9d11dc0e4d2a56a8d`
- 증거 디렉터리: `D:/project_code/angmoo-workspace/.task-output/chat-decision-trace-20260912-205831`
- 자동 실모델 호출: **0회**. 합성 provider 검증은 실제 모델 정확도나 USER CHECK가 아니다.
- 새 브랜치·worktree·이슈·PR·commit·stage 생성 없음. 기존 dirty tree 보존.

## 1. DT0 기준선과 수정 경계

`before/`, `before-plan.md`, `baseline-hashes.json`, `existing-status.txt`, `existing.diff`, `head.txt`, `branch.txt`에 작업 시작 상태를 보존했다. DT0의 전체 preservation 검사는 기존 `Chat durable command changed: mark_terminal` 및 append-only test introduction 증거 오류가 있는 상태였다. 이것을 이번 진단 패치의 성공으로 덮어쓰거나 보호 기준을 완화하지 않는다.

`backend/ARCHITECTURE.md`, `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md`를 기준으로 공통 관측 운반 계약, Chat 선택 입력 관측, Relationships 검증 관측, provider 입력 관측을 각 책임에 배치했다. 프론트엔드 변경은 없다. 기존 진단 화면의 scalar record 및 JSON 표시·내보내기를 재사용한다. import 정책에는 실제 호출 경계인 Chat의 `selection_diagnostics` 계약 한 개만 명시적으로 추가했고, 자동 생성 import inventory를 갱신했다.

모델, 사고 수준, 선택 도구 스키마, 프롬프트, repair 지침, 검증 순서, 쿼리, CRG·실패·저장·취소 정책은 유지한다. 이 변경은 오류를 복구하는 패치가 아니라 원인을 구분할 관측 패치다.

## 2. DT1 관측 계약

기존 basic 진단 version은 유지하고 추가 관측에는 `decision-trace.v1`을 붙인다. 요청 ID는 기존 인증된 요청 진단 envelope에서 연결한다. 평탄한 상세 행은 기존 `Record<string, string | number>` 표시 계약을 사용한다.

| 상세 행 | 남기는 사실 |
| --- | --- |
| `selection_attempt` | first/repair, 정상화 전 허용된 오류 코드, 기존 정상화 코드, 필드 경로, 실제 finish reason, 수신 여부, 실제 제공된 usage, 설정 출력 한도, 호출 횟수, 실제 validation stage 상태 |
| `selection_fields` | 호출 순서·허용 함수명, 관계·인물·집계 필드 타입과 존재 여부, null/missing 구분, 알려진 enum·참조 유효성, 초과 키 수 |
| `graph_provider` | Planner에 제공된 관계 참조, first/repair, provider 처리 결과, dispatch 수, 실제 repair 코드와 기존 지침의 ID·digest |
| `graph_input` | 검증이 받은 주체 기준 from/to, 인물 ref와 실제 binding의 요청 내부 alias 대응, 계획 단계 수, 검증 pass |
| `graph_step` | 단계 ordinal·alias·종속 단계 alias·연산, 실제 반환 상대·방향, 실제 검증에서 계산된 기대 상대·방향, 각 검사 도달 여부·결과·적용 규칙 |
| `graph_validation` | 최초/수정의 planning 검증과 executor 재검증을 구분한 최종 판정 |
| `graph_execution` | executor 진입, 완료 또는 실패; 진입 전 차단도 구분 |

기본 진단에는 허용된 코드·숫자·불리언 요약만 기록한다. 인물·binding·단계의 상세 대응은 상세 ON에서만 요청 내부 `ref-N`, `identity-N`, `step-N`으로 표현한다. 실제 인물 이름·ID·질문·모델 원문·도구 argument JSON·프롬프트는 신규 관측 행에 넣지 않는다. 기존 상세 조회 행에 허용되던 필드와 신규 관측 행의 범위는 구분한다.

`request_pair_direction.v1`은 **현재 구현이 적용하는 규칙의 식별자**다. 해당 규칙이 모든 연산에서 질문의 의미에 적합하다는 판정이 아니다. 기대값을 진단에서 재계산하지 않고 기존 검증이 얻은 지역 변수를 받아 기록한다. 상대 검사에서 먼저 실패하면 방향 검사는 `not_evaluated`다. 동일한 실인물에 두 ref가 연결되면 alias 문자열이 아닌 실제 binding 동일성을 관측하므로 오인하지 않는다.

`expected_values_supplied=no`는 현재 repair 입력에 **백엔드가 계산한 기대 상대·방향을 별도 필드로 추가하지 않았음**을 나타낸다. 기존 의미 입력의 from/to가 전달되지 않았다는 뜻은 아니다. repair 지침은 기존 함수로 생성된 문구의 SHA-256만 기록하며 내용을 변경하지 않는다. 최초·수정 행은 단계 alias로 비교할 수 있고 자동 의미 평가나 자동 원인 확정은 하지 않는다.

`executor_entered`와 기존 `graph_query` 시도, `validated_result`, 최종 `completed`는 구분한다. executor 진입만으로 DB 조회 성공이라고 판단하지 않는다. Supervisor 응답이 수신되지 않으면 실제 종료 사유와 사용량을 만들어내지 않는다. 제공되지 않은 토큰은 필드 부재/`not_reported`, 명시적 0은 0이다. transport 실패에서 dispatch 완전성은 `unknown`이다. 실패 시 stage가 `running`이면 실패가 난 시점의 기존 stage 상태이며 통과를 뜻하지 않는다.

## 3. DT2~DT4 구현 위치와 불변성

- `app/contracts/decision_observation.py`: 허용된 scalar 행, 요청 내부 alias, async ContextVar scope, 예외가 업무로 전파되지 않는 관측 wrapper.
- `app/contracts/retrieval_observation.py`: 기존 저장 envelope에 관측 요약과 생략 여부 연결.
- `chat/contracts/selection_diagnostics.py` + 기존 selection provider: 정상화 전 오류와 실제 provider 응답을 관측. 기존 오류 객체·집계·반환은 그대로 유지.
- `relationships/service/graph_observation.py` + 기존 validator: 계산된 기대값과 반환값 비교, 아직 실행하지 않은 검사를 명시.
- `integrations/llm/graph_decision_diagnostics.py` + 기존 Graph provider: 기존 repair 입력과 시도 관측.
- 기존 Chat Graph orchestration: first/repair/executor scope, 실행 진입·완료·실패 연결. 성공한 결과·기존 예외와 재시도 상한 유지.

기존 `node_state_json`의 실패 DTO에 상세 데이터를 넣지 않았다. 상세 캡처의 동의·TTL을 우회하지 않는다. 신규 DB migration이나 영구 상세 저장소도 없다.

## 4. DT5 합성 검증

`dt5-tests.txt`: **409 passed, 1 skipped, 1 warning**. 건너뛴 한 항목은 opt-in 성능 검사이며 별도 성능 측정을 아래에 기록했다. 경고는 기존 Starlette/httpx deprecation이다.

추가 테스트 `test_decision_diagnostics.py`는 12개 사례를 포함한다. 상대 불일치, 방향 불일치·수정 성공/실패, 정상 실행, 상세 OFF/ON 입력·결과 동일성, MAX_TOKENS와 0/미제공 사용량, 타입 차이, first/repair의 서로 다른 오류와 field path, 미수신 transport, alias 동일 인물, 수집 상한, 관측 helper 실패를 검증했다. 기존 실패 lifecycle·권한·capture OFF/재시작/보관·조회 API·최종 CRG 흐름 검사를 함께 실행했다.

`check_baseline.py`와 `dt5-baseline-and-performance.json`은 저장된 DT0 코드와 현재 코드를 실제 합성 실행해 네 Graph 흐름의 모델 입력·query 객체·결과/실패·호출 집계가 동일함을 확인한다. 두 provider의 `generate_text`/`generate_json` 호출 AST도 동일하다. Router 계약·provider 계약, routing service, workflow, 상세 capture, Graph execution 계약, Graph 계획 schema 7개 파일은 DT0 바이트와 동일하다.

## 5. DT6 구조·성능·보존 Gate

- import inventory: **1094 modules, 4114 internal edges**.
- architecture boundary: **PASS, legacy exact edges 0**.
- 구조 테스트: `dt6-architecture-tests.txt`, **20 passed**.
- 진단 성능: 각 mode 5회 워밍업 후 100회, 자동 수정 후 성공하는 두 단계 Graph 합성 흐름. p95 baseline **14.256 ms**, 기본 진단 **5.127 ms**, 상세 ON **17.207 ms**, DT0 대비 상세 증가 **2.951 ms**. 계획의 +5 ms 기준 안이다. Windows 로컬 샘플 편차가 있으며 AI 네트워크 지연이나 실제 처리속도 개선을 입증하는 수치는 아니다.
- 전체 preservation: **KNOWN FAIL**. `dt6-preservation.txt`와 DT0의 오류 행이 모두 동일함을 `dt6-preservation-comparison.json`으로 확인했다. 새 수집 테스트 수 증가 외 기존 오류 내용 변화 없음. Gate를 통과로 기록하거나 기준을 완화하지 않았다.
- 수집 상한에서 기존 상세 행 생략도 표시하도록 마지막 보완 후 `dt5-final-targeted.txt`: **27 passed, 1 skipped, 1 warning**. 건너뛴 것은 opt-in 성능 항목이다.
- CI·merge·release는 이번 로컬 요청에 포함하지 않는다.

## 6. DT7 runtime·USER CHECK

개발 contributor Docker의 실제 compose labels 및 `/workspace` 소스를 확인했다. installed Angmoo/AppData 진단이 아니다. 갱신 전 진행 중 요청은 없었고 기존 요청은 committed 43 / failed 16이었다. 마지막 수락 모델은 `gemini-3.1-flash-lite` / `high`, NA는 native_controls=true / code_coordination=true / positional_entity_refs=false였다.

`dt7-build.txt`의 development 이미지 build 완료 후 기존 backend 서비스만 재생성했다. 빌드 중 마지막으로 보완한 수집 생략 계수 파일 `retrieval_observation.py`는 시작 전에 개발 소스로 동기화했다. 실행 소스와 이미지 소스는 구분하며, 다음 재생성 때는 최신 checkout으로 build해야 이 파일도 이미지에 포함된다. `dt7-after-runtime.json`에서 **실행 소스 13개 SHA-256가 로컬과 일치**, backend healthy, NA 세 옵션과 모델 유지, **기존 요청 metadata hash 및 committed 43 / failed 16 보존**을 확인했다. Frontend와 데이터 volume은 재생성·삭제하지 않았다. 상세 캡처는 메모리 기반이므로 프로세스 재시작 후 새로 ON 해야 한다. 기존 기록의 미수집 상세는 소급 복구할 수 없다.

직접 USER CHECK에서는 같은 채팅에서 상세 진단을 ON으로 켠 뒤 다음 질문을 새 메시지로 보낸다. 기존 실패 응답을 재해석하거나 오래된 버튼 상태로 새 코드를 판정하지 않는다.

1. 저장된 관계 정보를 기준으로, 올마이트에서 너를 향한 관계 수치를 알려줘.
2. 저장된 관계 정보를 기준으로, 너와 올마이트가 공통으로 연결된 인물은 누구야?
3. 저장된 관계 정보를 기준으로, 네가 긍정적인 관계를 맺고 있는 인물들을 순서대로 알려줘.
4. 저장된 관계망에서 너와 올마이트는 어떤 경로로 연결되어 있어? 직접 연결인지, 다른 인물을 거치는지도 알려줘.
5. 먼저 저장된 관계 정보에서 네가 가장 긍정적인 관계를 맺고 있는 인물 한 명을 찾고, 그 사람과 너 사이의 직접 관계 수치를 알려줘.

사용자가 요청을 보낸 뒤 요청 ID와 실제 메시지를 연결해 판단한다. 응답 실패도 진단 대상이다. 재현되지 않은 오류를 해결됐다고 표현하지 않는다. 초기 인계 시 USER CHECK PENDING이었다. 이후 사용자가 다섯 문항을 실행했고 아래 §8에 기본 진단 확인 결과를 추가했다. 메모리 상세 행은 아직 직접 열람하지 못했다.

## 7. DT8 원인 분류와 인계

| 이전 사례 | 보존된 관측 사실 | 이번에 준비한 판단 근거 | 현재 확신 범위 |
| --- | --- | --- | --- |
| 1 | counterpart 불일치, 실제 Graph 실행 전 차단 | 상위 binding, 기대/반환 identity, 첫 실패 검사 | 차단 경계 확인; 실제 질문에 대한 원인 귀속은 새 요청 대기 |
| 2 | direction 불일치, 실제 Graph 실행 전 차단 | 연산, request pair 규칙, 실제 기대/반환 방향 | 규칙 적용과 모델 반환 비교 가능; 연산별 기대값의 의미 적절성 미확정 |
| 3 | relationship_invalid로 정상화 | 정확한 허용 코드·필드 경로·타입·참조 상태 | 합성 분리 PASS; 기존 실제 원인 소급 추정 금지 |
| 4 | 최초 방향 오류 뒤 자동 수정·실행 성공 | first/repair 별 계획 필드·repair digest·executor/query 결과 | 합성 복구 PASS; 새 실제 복구 사례는 미재현 |
| 5 | native_output_incomplete | 실제 종료 사유·수신 여부·함수 수·제공된 usage·한도 | 합성 MAX_TOKENS/transport 구분 PASS; 이전 실제 종료 사유 미확정 |

후속 지침·기대값 계산·연산 계약·종료 사유별 복구 변경은 새 증거를 보고 별도 범위로 판단한다. 이번 결과를 모델 성능 개선, Graph 오답 해결 또는 1·2·3·5의 근본 원인 확정으로 해석하지 않는다.

원복은 `before/`와 이번 작업만의 차이를 대조해 관측 코드만 제거한다. 기존 미추적 파일을 지우거나 전체 Git reset/restore를 하지 않는다. detailed OFF는 수집 중단이며 코드 원복과 다르다. runtime 반영 후 원복하면 소스 hash도 다시 확인해야 한다.


## 8. DT7·DT8 사용자 재시험 수신 및 기본 진단 확인

사용자 보고: 1·2 실패/재시도 버튼 없음, 3 실패/재시도 버튼 있음, 4·5 답변·근거 정상. 다음 다섯 contributor 요청의 기본 진단을 read-only로 확인했다. 모두 `detail_captured=true`, `detail_omitted=0`, `trace_complete=true`, `omitted_events=0`이다. 이는 수집 당시 상세 ON·생략 없음의 증거이며, 분석자가 상세 행을 모두 열람했다는 의미는 아니다.

원본 기본 진단: `.task-output/chat-decision-trace-20260912-205831/dt7-user-check-basic.json` (workspace 기준). 아래 접수 시각은 DB UTC이며 화면의 World 시간과 구분한다.

| 번호 | request ID | UTC 접수 | 상태·retryable | 확인한 흐름 |
| --- | --- | --- | --- | --- |
| 1 | `request-cc27ddbfeaf442a296aa8072d714badd` | 12:29:49 | failed / 0 | Supervisor 최초 entity_ref_invalid → 자동 수정 통과 → Graph direct_relationship counterpart_direction_mismatch → 공유 repair 사용 완료로 종료 |
| 2 | `request-d7afa21a1a7240b6be96d3379e56174c` | 12:30:01 | failed / 0 | Supervisor 통과 → shared_neighbors 최초·수정 모두 expected outgoing / returned either → 실행 전 차단 |
| 3 | `request-68c84a374fe74d85a6a98ed715b406cd` | 12:30:33 | failed / 1 | Supervisor 최초 entity_ref_invalid → 수정 relationship_unbound → Graph Planner 미진입 |
| 4 | `request-f9296826962448a0a7c54667da580360` | 12:30:53 | committed / 0 | shortest_path 최초 either 불일치 → 수정 outgoing 통과 → 실제 Graph 결과 ready, path 1·관계 1 → 근거 1·CRG·저장 |
| 5 | `request-8fed61ce293d48509e44b43e400f8095` | 12:31:34 | committed / 0 | Supervisor MAX_TOKENS → 수정 STOP → rank_related_characters(limit 1) → direct_relationship 종속 실행 → 근거 중복 제거 후 2개·CRG·저장 |

### 8.1 확정된 원인과 아직 필요한 정보

1. **1번:** 추가적인 선행 실패가 확인됐다. Supervisor가 먼저 인물 참조 형식을 잘못 작성했고 수정 호출이 request-wide repair 1회를 사용했다. 이후 Graph 상대 불일치가 발생했으므로 Graph에는 자체 수정 기회가 없었다. 총 물리 호출은 Supervisor 2 + Graph Planner 1, CRG 0. 전체 최대 호출 수의 여유와 공유 repair token은 다른 제약이다. 실제 기대 identity와 반환 identity를 아직 열람하지 못했으므로, 상위 의미 해석·기대 상대 계산·Planner 상대 작성 중 어느 쪽이 질문 기준으로 잘못됐는지는 유보한다. 반환 방향 outgoing도 보이지만 상대 검사에서 먼저 중단되어 방향 검증은 not_evaluated다.
2. **2번:** 직접 실패 조건은 확정됐다. shared_neighbors의 either가 request pair 기반 outgoing 강제와 충돌한다. 현재 `GraphPlanExecutionContext.expected_direction`은 from이 주체면 outgoing, to가 주체면 incoming으로 계산하고, Validator는 연산 구분 없이 그 값을 강제한다. 반면 관계 조회 서비스/쿼리 catalog는 shared_neighbors와 shortest_path에도 either를 지원한다. 따라서 방향을 명시하지 않은 공통 연결 질문에서 Planner의 either를 단순 모델 오답으로 단정하지 않는다. 관계 두 끝점의 표기와 해당 연산의 탐색 방향을 같은 의미로 취급한 계약을 우선 검토할 근거다. 기존 규칙을 임의로 수정하지 않았다.
3. **3번:** 이번 실패는 포괄적인 관계 입력 오류에서 더 좁혀졌다. 최초는 entity ref 정규식 위반, 수정 후에는 relationship.from/to 중 하나가 허용된 ref 집합에 바인딩되지 않았다. 같은 오류를 그대로 반복한 것은 아니다. 구체적 문자열·어느 끝점인지는 상세 행이 필요하다. durable call_tracker_json은 빈 객체지만 두 selection_attempt에 각각 physical_attempts=1이 보존되어 두 호출을 확인했다. 이 집계 표현 차이도 후속 점검 항목으로 기록한다.
4. **4번:** 자동 수정·실제 조회·근거·답변 저장 모두 확인했다. 다만 either를 outgoing으로 바꿔 계약에 통과한 것이므로, 일반 경로 질문에 outgoing만 적용하는 것이 의미상 최적이라는 증거는 아니다. 이번 반환 근거가 맞다는 사용자 확인과 계약 자체의 적절성 검토를 구분한다.
5. **5번:** native_output_incomplete의 이번 실제 종료 사유는 **MAX_TOKENS**로 확인됐다. 최초 max_output_tokens=3072, thought_tokens=2946, output_tokens=121. 수정은 STOP으로 완료됐고 Graph의 두 단계 의존 조회가 정상 실행됐다. 이는 이전에 미확정이던 종료 사유를 이번 새 사례에서는 구분한 성과다. 과거 모든 incomplete가 같은 원인이라고 일반화하지 않는다.

### 8.2 재시도 버튼 차이

DB retryable 값이 사용자 화면 보고와 일치한다. `chat/graph_retry_policy.py`는 제한된 missing-field/JSON 오류만 재시도를 허용하고 상대·방향 불일치는 허용하지 않으므로 1·2가 false다. `response_workflow._failure_profile`은 Router 입력 오류에는 별도의 router diagnostic.retryable을 사용하므로 3은 true다. 따라서 이번 버튼 차이는 프론트엔드 표시 누락의 증거가 아니라 현재 백엔드 정책의 차이다. 이것이 사용자 경험상 적절한지는 별도의 정책 검토 대상이다.

### 8.3 상세 열람 제한 및 다음 단계

현재 브라우저 연결 도구가 `failed to write kernel assets` / OS error 3으로 두 차례 초기화에 실패했다. 인증 우회나 세션 비밀 추출을 시도하지 않았다. 메모리 상세값은 별도 Python 프로세스나 SQLite 기본 진단에서 복원할 수 없으므로 사용자에게 **1·3번 상세 JSON**을 요청했다. OFF·프로세스 재시작·TTL 만료 시 상세 기록이 사라진다. 2번의 기대/반환 방향과 5번의 실제 종료 사유는 기본 진단만으로도 확인됐다.

DT7의 사용자 5문항 실행 및 기본 진단 확인은 완료다. DT8은 위와 같이 확인된 원인을 분류·인계했으며 1·3의 정확한 인물 참조 귀속은 상세값 대기다. 이번 후속 확인에서는 제품 코드·지침·모델·예산·실패 정책을 변경하거나 추가 실모델 요청을 생성하지 않았다.


## 9. 두 문항 재시험·첨부 파일 대조

사용자 보고는 첫 문항 성공, 두 번째 문항 실패다. 첨부 상세 JSON과 contributor 기본 진단의 시도별 코드·토큰 수·연산을 대조했다. 상세 내보내기에는 request ID가 없으므로 파일 번호를 요청 번호로 취급하지 않았다.

- `angmoo-query-diagnostics (4).json`: 새 성공 요청 `request-e97e7ff5dd5442b4bf73c35f0f53d799`(UTC 12:45:31)의 기록과 일치. Supervisor 최초 entity_ref_invalid 후 수정 통과. 인물 배열 2개(actor/target)에서 1개(counterpart)로 변경. 상위 from=identity-1, to=responding_character; Graph 반환 counterpart와 기대 identity가 일치하고 방향도 incoming/incoming 일치. direct_relationship 실행 완료. raw ref는 alias로 치환되어 최초 형식 위반의 구체적 문자열·문자는 이 파일로 복원할 수 없다.
- `angmoo-query-diagnostics (5).json`: 새 실패 기록이 아니라 **이전 성공 요청** `request-8fed61ce293d48509e44b43e400f8095`와 시도별 토큰·종료 사유·두 단계 연산이 일치한다. MAX_TOKENS 후 수정 STOP, rank(limit 1) → direct 관계 조회 완료 기록이다. 이 파일을 최신 실패의 증거로 사용하지 않는다.
- 새 실패 요청은 `request-5118f43b00874ef4b7f2d56a5b934adf`(UTC 12:46:07)다. 기본 진단에서 최초 entity_ref_invalid → 수정 **retrieval_intent_relationship_self_invalid**를 확인했다. 두 응답 모두 STOP이며 이번 최종 오류는 MAX_TOKENS가 아니다. 현재 계약은 from_ref == to_ref일 때 정확히 이 오류를 발생시킨다. 따라서 수정된 관계의 출발·도착 참조가 같아서 차단된 것은 확정되지만 실제 참조 문자열은 새 상세 파일 없이는 미확정이다. Graph 조회 없음, retryable=true.

이번 인물 목록 질문의 실패는 이전 relationship_unbound와 다른 구체적 오류다. 공유되는 문제 영역은 Supervisor 인물·관계 인자 작성이며, Graph Planner나 실제 DB 조회 오류로 분류하지 않는다. 사용자에게 재시험을 반복 요청하기보다 내보내기 요청 식별 정보 개선과 목록/순위 질문의 관계 입력 표현 계약을 후속 검토할 근거로 남긴다. 제품 코드·모델·정책 변경 없음.
