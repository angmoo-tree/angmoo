# 채팅 회상 진단

> 현재 로컬 작업 트리는 2026-09-12 승인한 NA 구성(네 함수 선택 + 코드 조정 값, 인물 참조 변경 B 보류)을 사용한다.
> Graph 실패 진단·집계 보존과 제한적인 사용자 재시도 패치를 구현했다. 실행 반영·USER CHECK 상태는
> [Graph 패치 검증 기록](chat-graph-failure-validation.md)을 따른다. 아래 native 이벤트는 해당 구성으로 실행한 요청에 적용한다.

2026-09-11 초기 native 후보는 당시 실제 모델 Gate에 실패하여 서버 미반영 상태였다.
이는 [이전 구조·호출·실모델 검증 기록](chat-supervisor-native-validation.md)이며,
이후 NA 로컬 적용은 [별도 기록](chat-supervisor-argument-validation.md#11-2026-09-12-사용자-요청에-따른-na-로컬-적용)을 따른다.

채팅의 **검색 진단 · 문제 해결**을 펼치면 해당 대화의 최신 요청 또는 이전 요청에 저장된 조회 과정을 볼 수 있다. RT 패치부터 근거가 없는 실패 요청도 요청 목록에서 시간·상태·ID로 선택할 수 있다. Docker 기여자 환경과 static/Tauri는 같은 Chat 컴포넌트와 공통 백엔드를 사용한다. 진단은 추가 AI 호출이나 검색을 실행하지 않는다.

RT의 내보내기는 `angmoo-query-diagnostics.export.v1` 묶음에 요청 ID·생성 시각·상태와 기본/상세 진단을 함께 담는다. 상세가 만료됐으면 기본만 저장하며 `details=null`을 유지한다. 파일 이름의 다운로드 번호나 현재 캡처 ON 상태만으로 과거 요청의 상세 수집 여부를 판단하지 않는다. 상세 관측 v2와 검증 결과는 [참조 추적 RT 검증 기록](./chat-reference-trace-validation.md)을 따른다.

## 읽는 순서

1. `router`: 실제 선택한 경로. CURRENT_CONTEXT/CLARIFICATION은 검색 미선택이며 검색 실패와 다르다.
2. `planner`와 `step`: 검증된 계획, repair 여부, 실제 실행/의존성 때문에 건너뜬 단계. step의 queries는 primitive 호출 수이며 내부 SQL 문 개수는 아니다.
3. `search`: 실제 FTS5, SQLite fallback, canonical direct, graph projection/canonical fallback. FTS 후보 수와 최종 원본 재검증 결과는 다른 단계다.
4. `validated_result`/`revalidation`: 후보·검증 후 결과·관측 가능한 제외 사유. DB WHERE에서 이미 제외된 행 수는 별도 COUNT 조회를 하지 않으므로 기록하지 않는다. 없는 수치는 0으로 해석하지 않는다. Graph 결과는 관계·근거·노드 등 서로 다른 단위를 포함한다.
5. `both_merge`: 실행 recipe, 병렬 여부, 의존성 중단, 중복·join 제외. 병렬 관측은 CANONICAL 다음 GRAPH 순서로 합쳐 표시한다. 전체 시간순 로그가 아니다.
6. `evidence_deduplication`/`evidence_limit`/`today_selection`: 실제 조립·상한 적용·Today SNS 추가. `crg_input`과 `evidence_kind`가 최종 답변 생성 서비스에 전달한 근거다. 모델이 이를 정확히 활용했다는 보장은 아니다.

요청 상태가 failed/cancelled이거나 중간 단계까지만 있으면 부분 기록이다. `not_recorded`는 도입 전 요청, 기록 실패 또는 정리된 기록일 수 있으며 0 hit가 아니다. `expired`는 아직 남은 행의 만료를 감지한 상태다. 이미 보관 정리로 삭제된 행과 애초에 생성되지 않은 행을 구분하기 위해 영구 tombstone을 추가하지 않는다. `omitted_events`가 있으면 이벤트 상한으로 일부 관측이 생략된 것이다.

## 저장과 개인정보 경계

- 기본: `chat_retrieval_diagnostics`에 versioned JSON. 최대 16KiB/요청, 1,000행, 7일. 다음 쓰기 때 만료/개수 정리를 수행한다. 앱이 꺼져 있는 동안 파일을 물리적으로 지우는 별도 서비스는 없다. 요청 복구 metadata와 분리하며 기존 checkpoint의 SAVEPOINT로 저장한다. 토큰마다 별도 commit하지 않는다.
- 기본 필드: 코드가 정한 경로/operation/상태/이유 코드, 수치와 조건 적용 여부. 질문, 검색어, 메시지·기억 본문, canonical ID, API key, provider raw exception/추론 원문은 넣지 않는다.
- 상세: owner+World+thread에서 명시적으로 켠 뒤 접수되는 다음 10요청 또는 30분. 프로세스 메모리에서만 보관하며 결과는 최대 60분, 20건, 전체 1MiB, 요청별 64KiB이다. TTL은 접근할 때 정리하며 재시작/OFF로 소멸한다. admission snapshot을 사용하므로 실행 도중 켜도 이미 접수된 요청을 소급 수집하지 않는다.
- 상세에는 실제 검색어와 제한된 조건이 포함될 수 있다. 명시적 **상세 진단 파일 저장**만 로컬 파일을 만든다. 다운로드한 복사본은 사용자가 관리한다. 기본 진단, SSE, World Package, 일반 evidence DTO에 상세 값을 넣지 않는다.
- 읽을 때 현재 대화 owner/World/참여자 접근을 재검증한다. 다른 owner·World·thread는 접근할 수 없다. 접근 권한이 사라진 기록은 읽을 수 없으며 기본 보관 정리/상세 TTL도 적용된다.
- migration `20260910_0091`, embedded SQLite v11은 빈 진단 테이블만 추가한다. 기존 요청의 조회 내용을 복원하지 않는다. 기본 진단은 기존 사용자 DB에 있는 로컬 runtime 데이터이며 배포 artifact에 사용자 DB가 포함되는 것은 아니다.

## Docker에서 기본 진단 읽기

브라우저에서 현재 대화의 진단을 보는 방법을 우선 사용한다. HTTP API는 기존 local frontend origin/owner 인증을 그대로 요구한다.

`GET /api/v1/worlds/{world_id}/chat/threads/{thread_id}/diagnostics?request_id={request_id}`

`PUT .../diagnostics/capture` body `{"enabled":true}`로 해당 대화의 상세 수집을 켠다. `false` 또는 DELETE는 해당 scope의 상세 admission과 결과를 지운다.

컨테이너의 실제 active generation DB 경로를 확인한 뒤, 기본 진단만 읽는 read-only 도구도 사용할 수 있다:

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend python /workspace/scripts/diagnostics/read_chat_retrieval_diagnostics.py --database <실제-active-generation-DB-경로> --request-id <request-id>
```

도구는 `mode=ro`와 `query_only=ON`으로 열고 진단 테이블만 조회한다. 임의의 오래된 generation을 현재 DB로 간주하지 않는다. 설치형 Windows의 DB를 조사할 때에는 별도의 물리적 설치 식별 절차를 먼저 수행한다.

## 구조와 검증 원칙

관측 계약은 `app/contracts/retrieval_observation.py`, Chat 저장/권한/API는 Chat 도메인, 실제 검색 관측은 기존 memory/relationships와 runtime adapter가 소유한다. 저장소나 logger가 재검색하지 않는다. UI는 `features/chat`의 기존 World Chat에 조합한다. hosted reference 분류는 **LOCAL**이며 기존 semantic Button·색상 token을 사용한다.

자동 검증은 합성 데이터/fake provider를 사용한다. 실제 질문에 대해 올바른 기억을 찾아 답변하는지와 자연어 Router가 어느 경로를 선택하는지는 별도의 USER CHECK다. 진단 기능 통과를 회상 품질 통과로 간주하지 않는다.

## CANONICAL 조회 계획 거절 진단 보강

### 기억 주체와 원문 의존 조회

`memory_subject_refs`는 백엔드가 현재 대화 캐릭터로 식별한 입력 인물 refs다.
모델이 정한 역할이나 이름 대신 실제 ID 대응으로 결정한다. `search_memory_items`가
이를 `counterpart_ref`로 사용하면 실행 전에 `canonical_plan_memory_subject_as_counterpart`로
거절한다. 기존 한 번의 수정 기회에 같은 코드와 안내를 전달하며, 별도 상대 조건이
없으면 `counterpart_ref`를 생략하도록 한다. 명시적 null은 기존 계약대로 허용하지 않는다.

의존 단계의 `.source_refs`는 검색 항목의 `reference`가 아니라 현재 검증된
`evidence_references`에서 만든다. `dependency_refs` 이벤트의 input·output·duplicates·excluded·truncated로
중복 제거와 최대 50개 제한을 확인한다. 값과 원문 ID는 기본 진단에 기록하지 않는다.
유효한 원본 참조가 없으면 의존 조회를 건너뛰며, 참조가 있어도 상세 조회에서
현재 권한·범위·삭제·숨김·digest를 다시 검사한다. 따라서 검색 성공과 상세 성공을
각 단계 결과 수로 구분해야 한다. 기억 자체의 식별자와 화면 링크는 유지한다.

### 단계 ID 수정 안내

CANONICAL 생성 스키마는 단계 이름을 `step1`~`step6`으로 안내한다. 이 이름은
조회 계획 안의 식별자이며 `search_memory_items` 같은 실행 연산 또는 LangGraph
노드 이름과 다르다. 백엔드는 기존 소문자·숫자·밑줄 ID 계약도 계속 허용한다.
의존 조회는 앞 단계의 실제 이름에 `.source_refs`를 붙여 참조한다.

최초 계획이 거절되면 수정 요청은 허용된 구체적 오류 코드와 고정 수정 안내를
받는다. `canonical_plan_step_id_invalid`가 예외 종류 이름으로 축약되지 않으며,
ID를 바꿀 때 `input_ref`도 맞추도록 안내한다. 오류의 원문·provider payload는
수정 안내나 기본 진단에 추가하지 않는다. 요청 전체 수정 기회와 호출 집계는 유지한다.

형식 검증 통과 후에도 `step`/`search`의 실행 여부와 결과 수를 따로 확인한다.
계획이 거절된 경우, 실제 조회가 0건인 경우, Today SNS만 답변에 들어간 경우를
같은 검색 성공으로 해석하지 않는다. 재시작 뒤에는 상세 수집이 초기화되므로
정확한 검색어·상대 조건을 확인할 새 질문을 보내기 전에 상세 진단을 다시 켠다.

### 실패 시 기록

`planner_validation`은 first/repair별 `validation_code`(허용 목록의 정확한 오류 코드), `failure_stage`(provider_output/json_decode/schema_validation/execution_contract), 관측된 `finish_reason`, `response_chars`, 누적 `logical_calls`/`physical_attempts`를 기록한다. 알 수 없는 오류 원문은 `unknown`으로 남기고 원문 JSON·preview·검색어·키는 복사하지 않는다. 종료 사유가 없으면 토큰 부족 또는 provider 정상 완료로 추정하지 않는다.

수정 계획까지 거절되거나 이미 요청의 수정 기회를 소진한 경우 실제 tracker snapshot을 실패 요청에 전달한다. 기존에 실패한 요청의 누락된 원인/집계는 소급 복원하지 않는다. 이 변경은 검색 정책이나 모델 출력 상한을 바꾸지 않는다.

## GRAPH 실패와 사용자 재시도

Graph의 `planner_validation`에도 first/repair별 정확한 허용 코드·실패 단계·관측된 종료 사유·호출 수를 기록한다. `graph_failure`의 `terminal_code`는 최종 중단 사유이며 처음 계획을 거절한 `validation_code`와 구분한다. 원인 체인에서 알 수 없는 값은 `unknown`으로 남긴다. 기본 진단은 상세 수집 ON/OFF와 무관하게 유지된다.

Graph 단독 실패·취소는 최신 tracker를 상위로 전달한다. BOTH는 두 작업이 끝나거나 취소 정리된 뒤 coordinator가 공통 tracker를 한 번 snapshot한다. 성공·실패 축의 snapshot을 더하지 않는다. 정상 0건·관측 불가를 오류로 바꾸지 않는다. `physical_count_complete=false`이면 표시된 값은 확인된 시도만 포함하므로 전체 실제 비용으로 확정하지 않는다.

`node_state_json.graph_diagnostic`에는 최대 두 거절 원인, 최종 코드, repair 소유 단계와 집계 완전성을 저장한다. 기존 `call_tracker_json` schema는 유지한다. 일반 failed event·채팅 DTO에는 내부 진단을 추가하지 않고 `failure_class`·`retryable`을 사용한다.

자동 수정 소진만으로 사용자 재시도를 금지하거나 허용하지 않는다. 정확히 관측된 `JSONDecodeError` 또는 필수 `direction`·`ranking`·`hops`·`depth` 누락 코드 중 허용한 발생 경계에 해당할 때만 기존 수동 retry를 제공한다. first/repair 중 미확인·권한·binding·금지 연산·방향 위반이 있으면 새 허용 목록으로 재분류하지 않는다. 다른 도메인 실패·provider 설정 복구·취소 정책과 요청당 수정 1회 상한은 유지한다.

기존 실패 행의 코드·집계·retryable은 소급 수정하지 않는다. 새 정책·실패별 테스트와 원복 경계는 [Graph 패치 검증 기록](chat-graph-failure-validation.md)에 있다. 이 패치가 실제 Graph 계획 작성 오류나 도구 선택 오류 자체를 고쳤다는 뜻은 아니다.

## 한국어 공백 보조 검색의 진단

`korean_spacing_fallback`은 기존 두 검색이 모두 비었을 때 실행하는 Memory 전용
보조 경로다. `scanned`는 검사 후보 행 수, `bytes_scanned`는 그 정규화 텍스트의
UTF-8 바이트 수다. SQLite 내부 전체 검사 행 수와 혼동하지 않는다.
`row_budget`, `text_budget`, `time_budget` 및 `truncated=true`는 전체 검색 완료
0건이 아니며 `memory_recall_search_incomplete`로 전달한다.
세부 적용 범위·보존한 초기 성능 실패·재측정 결과는
[한국어 기억 검색 검증](korean-memory-recall-validation.md)을 따른다.

## Supervisor native 후보의 진단

- `supervisor`: 코드 상태 전이. 최초 `route_and_resolve` action에서 AI 선택을 수행한다.
  같은 이름의 독립 graph worker나 두 번째 Router AI 호출은 없다.
- `router`: 기존 호환 의미·guard/resolver 집계다. 새 provider 호출 node는
  `supervisor_selection`이지만 request tracker의 기존 Router 슬롯을 한 번 사용한다.
  로그의 역사적 명칭만으로 별도 AI 호출이 있다고 판단하지 않는다.
- `tool_selection`: 모델이 요청한 축과 selected/suppressed 상태.
  `tool_effective`: 코드 guard/resolver 이후 실행할 축, model/code_guard 출처,
  원시 호출 ID를 대신하는 `call-<sha256 앞 16자>`의 `call_ref`.
- `tool_return`: 호출별 completed/failed/cancelled/skipped_dependency 상태와 attempt.
  완료한 ToolNode 배치 뒤 Supervisor는 코드로 결과를 검사하고 AI를 다시 호출하지 않는다.
- `executor_retry`: request-wide SQLite BUSY/LOCKED 읽기 복구 1회. 새 Planner 호출로
  계산하지 않는다. Planner 수정은 기존 AI repair 집계와 별도다.
- `native_output_incomplete`: MAX_TOKENS·SAFETY 등 정상 완료되지 않은 선택 응답.
  파싱 가능한 일부 호출이 있더라도 실행하지 않는다.

호출 목록 필드 누락·잘못된 ToolMessage·foreign request/scope·artifact 불일치는
정상 0건과 다르다. 의존 결과가 없어 다음 축을 생략한 상태도 실제 실행 성공이 아니다.
실패한 병렬 축은 오류 상태로 남으며 성공한 축을 같은 이유로 재실행하지 않는다.

진단 크기·이벤트 상한과 개인정보 규칙은 기존과 같다. `omitted_events`가 있으면
모든 호출 이벤트가 보존됐다고 가정하지 않는다. raw tool arguments·provider 본문·
thought signature는 기본 진단에 넣지 않는다. 실제 provider 형식 판정과 코드
실행 계약 통과는 검색 적합성·CRG 사실성·직접 USER CHECK를 대신하지 않는다.

## 2026-09-12 Supervisor·Graph 세부 판단 관측

`decision-trace.v1` 추가 행은 최초 선택·자동 수정·실행 검증을 연결한다.
`selection_attempt`는 정상화 전 허용 오류 코드·실제 종료 사유·제공된 사용량을,
`selection_fields`는 필드의 missing/null/type과 허용 enum·참조 상태를 보존한다.
`graph_input`/`graph_step`는 상위 binding, 실제 기대값·반환값, 적용 규칙,
검사에 도달했는지 여부를 기록한다. `graph_provider`의 repair 코드와 지침 digest로
기존 수정 입력을 연결하며, `graph_execution`은 executor 진입과 완료를 구분한다.
원본 질문·모델 응답·인물 이름·ID·전체 도구 인자는 신규 기본·상세 행에 기록하지 않는다.
신규 상세 인물 대응은 요청 내부 alias이며 기본 진단이나 `node_state_json`에 저장하지 않는다.

`decision_summary`의 `detail_captured`, `detail_omitted`, `trace_complete`로 수집·생략을
확인한다. trace_complete는 생략이 관측되지 않았다는 뜻이며, 상세 OFF 상태에서
모든 비교값이 수집됐다는 뜻은 아니다. `not_evaluated`와 실제 불일치, 미제공 사용량과
명시적인 0을 구분한다. executor 진입은 쿼리 성공과 다르므로 기존 graph_query,
validated_result 및 완료 상태도 함께 확인한다.

기존 상한을 유지한다: 기본 16 KiB/48 events·1000행/7일, 상세 24행/64 KiB,
메모리 20결과/1 MiB/60분, 활성 수집 10요청/30분. OFF·재시작 시 상세 캡처가 사라지므로
runtime 갱신 후 새로 ON 해야 한다. 과거 미수집 값은 소급 복구되지 않는다.
기존 인증된 조회·JSON 내보내기 경로와 화면을 사용한다.

구현·검증·USER CHECK 구분과 원인 판정 한계는
[세부 판단 진단 실행 기록](chat-decision-trace-validation.md)에 기록한다.
