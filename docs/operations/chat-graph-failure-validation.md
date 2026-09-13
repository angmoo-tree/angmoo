# Graph 실패 진단·호출 집계·사용자 재시도 검증

작성일: 2026-09-12. 작업 브랜치 `fix/chat-retrieval-debugging`, HEAD `ee8eabf7c68e5a7fb7a5c4e9d11dc0e4d2a56a8d` 위의 기존 로컬 변경을 보존했다. 이 문서는 이번 패치의 결과이며 앞선 NA 선택 정확도 평가를 대체하지 않는다.

**현재 상태: 패치 구현, 백엔드·브라우저 회귀 검사 및 contributor 로컬 실행 반영 완료. G5 전체 보존 Gate는 승인된 커밋 증거가 없는 보호 메서드 변경으로 미통과다. G6 직접 USER CHECK 2건을 확인했으며 진단·집계·허용하지 않은 오류의 버튼 차단은 확인됐지만, 관계 조회 성공과 허용 오류의 실제 재시도는 미검증이다.** G7 결과·제한·원복 기록은 완료했다. 전체 G0~G7을 모두 PASS로 표시하지 않는다.

## 바뀐 책임

- `relationships/contracts/graph_diagnostics.py`: 정확한 허용 코드, 발생 단계, first/repair, 관측된 finish reason·문자 수와 실제 provider dispatch 수의 제한된 타입. 원문·인물·검색어·preview는 복사하지 않는다.
- `integrations/llm/graph_retrieval_planner.py`: 완료 응답만이 아니라 timeout·취소·transport 예외에도 실제 전송 tracker를 전달한다. 모델 입력·스키마·출력 상한과 자동 수정 설정은 보존한다.
- `chat/service/graph_retrieval.py`: 처음 거절한 이유를 수정 예산 검사 전에 남기고, 정상·실패·취소의 최신 호출 집계를 전달한다. 확인하지 못한 물리 시도는 `physical_count_complete=false`로 표시한다.
- `chat/service/both_retrieval.py`: 병렬 작업이 모두 끝나거나 취소 정리된 뒤 공통 tracker를 한 번 snapshot한다. 두 snapshot을 더하지 않는다. 양쪽 실패 시 기존 Canonical 우선 실패 전파와 별도의 Graph 진단을 함께 보존한다.
- `runtime/chat/retrieval_tools.py`: BOTH 배치는 호출별 결과를 coordinator에 모두 반환한다. 단독 도구의 예외 전파와 ToolMessage 검증은 유지한다. 실패 결과를 빈 근거로 바꾸지 않는다.
- `chat/contracts/graph_failure.py`, `chat/graph_retry_policy.py`: Chat이 최종 중단 사유와 사용자 재시도 자격을 결정한다. 별도 AI 판단은 없다.
- 기존 lifecycle: 같은 fence·Session·transaction에서 `call_tracker_json`과 선택적인 `node_state_json.graph_diagnostic`을 저장한다. 새 테이블·migration·기존 실패 행 수정은 없다.

## 자동 수정과 사용자 재시도

요청 전체 자동 수정은 여전히 최대 1회다. Selector가 수정 기회를 썼다면 Graph의 첫 계획이 실패해도 같은 요청 안에서 두 번째 계획을 생성하지 않는다.

새 사용자 재시도 허용 목록은 다음 다섯 코드다. 진단에 저장할 수 있는 모든 코드가 재시도 대상은 아니다.

| 원인 코드 | 허용 발생 경계 |
| --- | --- |
| `JSONDecodeError` | `json_decode` |
| `graph_plan_direction_required` | `provider_output` / `schema_validation` |
| `graph_plan_ranking_required` | `provider_output` / `schema_validation` |
| `graph_plan_hops_required` | `provider_output` / `schema_validation` |
| `graph_plan_depth_required` | `provider_output` / `schema_validation` |

최종 사유가 `graph_planner_request_wide_repair_exhausted`이고 실제 repair 소유 단계가 있어야 한다. first/repair로 관측된 모든 거절 원인이 허용 목록에 속해야 한다. finish reason이 있다면 `STOP` 또는 `MAX_TOKENS`여야 한다. `None`은 정상 종료를 추정하지 않고 기존 코드·발생 경계로만 판단한다.

최초 원인이 금지 쿼리·binding 위반·unknown이면 후속 오류가 JSON 형식 오류라고 해도 허용하지 않는다. 원본 범위·방향 위반, 인물 ref, 추가/누락 key를 합쳐 나타내는 포괄 코드, `GraphPlanContractError`, generic `ValueError`는 이번 허용 범위에서 제외했다. transport·provider 설정·기존 Router·Canonical·CRG·취소 정책은 유지한다. BOTH의 다른 축이 주된 실패이면 Graph의 허용 코드를 이용해 그 실패를 재분류하지 않는다.

사용자가 최신 실패의 `[다시 시도]`를 누르면 기존 retry API가 owner·World·최신 요청·in-flight·commit·새 user message·idempotency를 검사한다. 같은 user message·response slot에 새 request·generation·attempt를 만든다. 페이지를 다시 열거나 진단을 읽기만 해서는 실행하지 않는다. 재시도는 응답 흐름 전체를 새로 수행하므로 모델 호출 비용이 추가될 수 있다.

## 진단 읽기

1. `planner_validation`의 `axis=graph`, `phase`, `validation_code`, `failure_stage`에서 계획이 거절된 이유를 확인한다.
2. `graph_failure.terminal_code`에서 수정 예산 소진·deadline·취소 등의 최종 중단 사유를 확인한다. 구체적인 원인과 최종 사유는 서로 다른 값이다.
3. 기본 관측의 `logical_calls`·`physical_attempts`는 Graph 축 집계다. 요청의 최종 전체 집계는 lifecycle의 `call_tracker_json`에 있다. BOTH 병렬의 이벤트 표시 순서를 실제 완료 순서로 해석하지 않는다.
4. 상세 수집을 끄거나 만료시켜도 안전한 기본 오류 코드와 저장된 `retryable`은 유지한다. 원래 물리 시도를 확인할 수 없으면 완전성 표시를 함께 해석한다.

일반 채팅 DTO와 failed event에는 기존 `failure_class`·`retryable`만 전달한다. 새 Graph 진단은 응답 생성 근거나 CRG 입력이 아니며 일반 채팅 bubble에 내부 코드·쿼리를 추가하지 않는다. 기존 owner 진단 화면은 허용된 새 이벤트 필드를 표시할 수 있다.

기본 관측 한도는 48개 이벤트·16 KiB다. 선택적인 종료 진단은 허용된 코드·enum·숫자, 최대 두 거절 항목만 포함하고 최대 크기 2 KiB 미만을 검사한다. 잘못된 타입의 선택 진단은 저장하지 않고 원래 terminal 처리를 유지한다. 이전 행에 새 진단이 없으면 기존 방식으로 읽으며 소급 재분류하지 않는다.

## 자동 검사 기록

모든 테스트는 합성 provider·임시 DB·브라우저 API 대역을 사용한다. 새로운 자동 실모델 호출은 **0회**이며 이전 평가 원장 356/356은 그대로다.

| 검사 | 결과 |
| --- | --- |
| G0 기존 동작 합성 재현 | Graph Planner 1회 후 실패, 상위 저장 집계 Graph 0회, retryable=false 확인 |
| G1–G2 진단·집계와 기존 회귀 | 58 passed |
| ToolNode/BOTH 확대 검사 | 최초 68 passed / 테스트의 잘못된 snapshot key 단정 4 failed. 올바른 `repair_node` 계약으로 수정 후 해당 4 passed |
| G3–G4 lifecycle·재조회·재시도 | 14 passed. 최초 테스트 입력의 짧은 idempotency key 5개를 기존 최소 길이에 맞춘 뒤 재검사 |
| G5 관련 12개 테스트 모듈 | 214 passed, 1 skipped, 기존 Starlette deprecation warning 1. skipped는 opt-in 진단 성능 benchmark |
| G5 최종 변경 확인 | first/repair 단계 보존 수정 후 관련 9 passed. 취소된 실제 workflow의 terminal·Graph 집계 저장 사례 추가 후 1 passed. 앞의 9개는 기존 통과 수에 중복 합산하지 않음 |
| 아키텍처 inventory | 새 모듈로 stale 확인 후 기존 파일 백업·재생성·check 통과. modules 1,090 / internal edges 4,101 |
| 아키텍처 boundary | 최종 PASS. 실제 Graph 진단 계약 한 개를 지원 contract 목록에 명시. modules 1,090 / internal edges 4,101 / legacy exceptions 0 |
| API/ORM/node 보존 검사 | 전체 FAIL: `Chat durable command changed: mark_terminal`. 아래 별도 설명 참조. frozen 기준선·검사기 변경 없음 |
| 보호 메서드의 이번 변경 대조 | 작업 전 정의가 HEAD와 일치. 선택적 인자 1개·node state 조건 2개·타입 검증된 대입 1개를 제외하면 AST가 작업 전과 동일. 전체 보존 검사 PASS를 대신하지 않음 |
| 브라우저 새 허용/차단 실패 | 2 passed. 최초 Next dev 시작 120초 제한 초과 후 별도 3108 서버를 준비하여 실행 |
| 브라우저 기존 World Chat | 준비 중의 첫 실행 45초 제한 초과 후 같은 테스트를 준비된 서버에서 재실행, 1 passed |
| Graph Planner prompt·catalog | 작업 전과 AST 동일. NA 조립 옵션·모델·자동 수정 예산 유지 |

통과한 검사는 normal 2/3/4 AI 논리 호출, 수정 최대 1회, 단독·병렬·순차의 집계, first/repair 별도 원인, 실제 ToolNode 취소 정리, 성공 0건·관측 불가, scope·fence·원문 검증, failed/replay의 동일성, 이전 실패 읽기, 동일 retry key 중복 요청의 단일 생성, user message 중복 없음, 늦은 결과 차단을 포함한다. 수집된 테스트 수를 실행 통과 수에 더하지 않는다.

### 전체 보존 Gate의 미통과 사유

`scripts/ci/check_refactor_preservation.py --contracts --nodes`는 실행을 완료했으며 exit 1이었다. 첫 오류는 `Chat durable command changed: mark_terminal`이다. 이번 계획에서 요구한 명시적 선택 인자 `graph_diagnostic`과 해당 저장 분기가 보호 대상 정의의 AST를 변경했다.

`scripts/ci/chat_forwarder_retirement.py`는 기존 durable method와 승인된 제품 변경 이력을 정확히 비교한다. `scripts/ci/post_refactor_contract_changes.py`는 그 예외 이력에 실제 조상 implementation commit, source blob 및 커밋 전후 AST 증거를 요구한다. 현재 로컬 미커밋 변경은 그 이력에 등록할 수 없다. 이를 피하려고 기존 기준선·검사기를 바꾸거나 임의 커밋을 만들지 않았다.

이어 출력된 여러 `committed test lacks append-only introduction evidence`는 첫 예외를 처리하면서 checker의 `targets`가 빈 값이 된 뒤 발생했다. 이 출력만으로 기존 테스트들이 모두 삭제되거나 이력이 사라졌다고 판단하지 않는다. API/ORM 변경 오류는 출력되지 않았지만, 중간의 일부 보존 검증은 실행되지 않았으므로 전체 Gate 통과로 해석하지 않는다.

별도의 로컬 AST 대조와 lifecycle·취소·재시도 회귀는 통과했다. 이는 이번 차이가 계획한 추가 저장 필드에 한정된다는 근거이며 승인 이력 Gate의 대체물이 아니다. 따라서 기능 회귀가 확인된 것으로 분류하지 않고 로컬 사용자 검증용으로 적용했으며, G5 상태는 **PARTIAL / 전체 보존 Gate FAIL**로 남긴다. 추후 구현 커밋을 진행하는 범위에서 기존 승인 절차에 맞는 정확한 제품 변경 증거를 추가하고 전체 검사를 다시 수행해야 한다. 이후 검사가 다른 불일치를 발견할 가능성도 남아 있다.

## 로컬 런타임 및 USER CHECK

기존 contributor Docker `angmoo-backend-1`과 `angmoo-frontend-1`은 G6 점검 때 종료 상태였다. 포트 3000에 다른 실행이 없고 contributor data volume을 사용하는 실행 중 컨테이너가 없음을 확인한 뒤, 기존 실패 메타데이터를 읽기 전용으로 기록했다. 현재 소스로 backend 이미지를 빌드하여 backend만 재생성하고 기존 frontend 컨테이너를 다시 시작했다. named data volume은 유지했다. 설치된 Windows Angmoo·다른 Docker 프로젝트는 변경하지 않았다.

| 확인 항목 | 2026-09-12 적용 결과 |
| --- | --- |
| 브라우저 주소 | `http://127.0.0.1:3000/`, HTTP 200 |
| 컨테이너 | backend·frontend 모두 `running / healthy` |
| 백엔드 health | `status=ok`, `persistence=sqlite`, `graph=ladybug` |
| 새 backend container | `9960dd5328df884ddffb5b9c602ae25cda0fd6bfdd269b477e76837c1994dd64` |
| backend image | `sha256:8b9b40d280d0c0cb73920718f31bed8bcf6685e63b43666073462ebbff7b8d96` |
| 실행 파일 대조 | 패치·NA 조립 관련 13개 파일의 SHA-256 모두 로컬과 일치 |
| NA 옵션 | `native_controls=true`, `code_coordination=true`, `positional_entity_refs=false` |
| 실행 import·정책 확인 | 실제 컨테이너에서 새 typed 정책 import, JSON 원인 허용 / unknown 차단 확인. AI 호출 없음 |
| 기존 요청 보존 | 재시작 전후 `committed=35`, `failed=7`. 기존 Graph 실패 2건의 상태·retryable·메타데이터 해시 동일 |

시작 직후의 health 요청은 아직 서버가 열리지 않아 연결 거절을 반환했으며, 이후 startup 완료와 양쪽 health를 확인했다. 성공 후 재시작을 반복하지 않았다. 브라우저 대역 테스트에 쓴 3108 서버는 종료했다.

첫 실행 반영 시점에는 USER CHECK PENDING으로 두었으며, 이후 사용자가 직접 보낸 두 요청과 화면 결과를 아래처럼 대조했다. 오래된 실패 bubble의 재시도 버튼은 소급 변경하지 않았다. 실사용 질문을 자동으로 보내거나 이전 실모델 평가 예산을 다시 사용하지 않았다.

### 직접 USER CHECK 2건과 진단 대조

아래 시간은 2026-09-12 한국 시간이다. 동일한 실행 container/image를 다시 확인하고 contributor DB를 `mode=ro / query_only`로 읽었다. 요청 본문·모델 원문은 진단 산출물에 복사하지 않았다.

| 요청 | 확인된 흐름 | 사용자 결과와 판단 |
| --- | --- | --- |
| 17:09:15 / `request-d5d0e053b21f4f2aa038215b06b06348` | Selector 2회(수정 포함) → BOTH 선택 → Graph first Planner 1회 → `graph_plan_counterpart_binding_invalid` → 공통 수정 소진 → failed | 버튼 없음. 이번 정책의 비허용 binding 오류이므로 `retryable=false`와 일치. Graph 조회 실행·Canonical·CRG까지 진행하지 않음 |
| 17:09:45 / `request-c74690e854a1459484b708e6198fed21` | Selector 1회 → CANONICAL Planner 1회 → 3단계 조회 → 근거 2건 → CRG 1회 → committed | 답변은 저장됐으나 Graph Planner는 0회. 관계 그래프 조회 성공으로 판단하지 않음 |

첫 요청의 안전한 새 진단에는 `phase=first`, `failure_stage=schema_validation`, `finish_reason=STOP`, `response_chars=659`, `physical_count_complete=true`가 남았다. 최초 원인은 `graph_plan_counterpart_binding_invalid`, 최종 중단 코드는 `graph_planner_request_wide_repair_exhausted`, 수정 기회를 사용한 단계는 `retrieval_router`다. 최종 논리·물리 호출 모두 Selector 2 + Graph 1 = 3으로 저장됐다. 예전의 Graph 0회 유실과 달리 실사용 실패에서도 새 집계가 보존된다.

`relationships/policies/graph_plan_schema.py::_validate_step_shape`에서 상대가 필요한 연산은 `counterpart_ref`와 `input_ref` 중 정확히 하나만 있어야 한다. 둘 다 없거나 둘 다 있으면 이번 코드로 거절한다. 현재 진단으로 어느 쪽이었는지는 구분할 수 없고, 잘못된 특정 인물 ID나 권한 침범까지 입증된 것은 아니다. 이 binding 오류는 이번 재시도 허용 목록에서 의도적으로 제외했으므로 버튼이 없다는 이유로 패치 미적용으로 해석하지 않는다.

두 번째 요청의 실제 조회 결과는 다음과 같다.

1. `list_relationship_changes`: 0건.
2. `get_character_summaries`: 1건.
3. `search_memory_items`: FTS5 1건.

반환 계약 검증은 정상이고 근거 2건을 CRG에 전달했다. 저장 시 `evidence_capability=available`, `partial_axes=[]`, `degraded_reason=null`이다. 그러나 첫 근거의 inspector `locator`는 null, 두 번째만 `memory_item` 참조를 갖는다. `evidence.py`는 locator가 없으면 해당 항목을 `unavailable`로 읽고, 항목 하나라도 확인 불가이면 현재 inspector capability를 `degraded`로 만든다. 프런트엔드가 모든 degraded에 “일부 검색 축을 사용할 수 없어…”라는 같은 문구를 표시하므로, 이번 문구가 Graph DB 실행 실패를 뜻하지는 않는다. 캐릭터 요약을 재조회할 locator가 없는 기존 조립·재확인 계약과 포괄적인 안내 문구의 문제다.

**G6 USER CHECK PARTIAL:** 실제 실패의 구체적 진단·집계·비허용 오류 차단은 확인했다. 허용 오류에서 버튼을 누르는 실제 복구는 발생하지 않아 합성 검사 근거만 유지한다. 관계 질문의 도구 선택, Graph binding 계획 작성, 요약 근거 locator·degraded 안내는 별도 후속 사항이며 이번 진단 패치에서 임의로 완화하지 않았다. 안전한 관측은 `g6-user-check-safe.json`에 남겼다.

## 2026-09-12 18:39~18:44 추가 Graph 질문 검증

같은 채팅의 새 요청은 9건이며, 앞서 제공한 질문 목록의 1~7번·11~12번과 일치한다. 17:09의 두 요청과 분리했다. 실제 container/image는 기존 패치 실행과 동일하다. 성공적인 응답 저장은 5건이지만 확인 질문·현재 맥락·Canonical을 포함하므로 Graph 성공률로 사용하지 않는다. 이번 구간에서 Graph 조회 실행 성공은 0건이다.

| 질문 번호 | KST | 최종 경로 | 관측 결과 |
| --- | --- | --- | --- |
| 1 | 18:39:57 | CANONICAL | 기억 검색 6건·관계 변경 0건·캐릭터 요약 1건, 근거 7건으로 답변. Graph 미실행 |
| 2 | 18:40:20 | CURRENT_CONTEXT | 검색 없이 답변. 직전 질문과 같은 인물을 다루므로 맥락 사용 자체를 곧바로 오류로 판정하지 않음 |
| 3 | 18:40:34 | BOTH | Graph first/repair 모두 `graph_plan_step_id_invalid`, 실패 |
| 4 | 18:41:43 | CLARIFICATION | AI 제안은 GRAPH였으나 인물·방향 해석이 ambiguous, `entity_identity` 확인 질문으로 전환 |
| 5 | 18:42:03 | GRAPH | Graph first/repair 모두 `graph_plan_step_id_invalid`, 실패 |
| 6 | 18:42:44 | CLARIFICATION | AI 제안은 GRAPH였으나 방향 해석이 ambiguous, `relationship_direction` 확인 질문으로 전환 |
| 7 | 18:43:18 | CANONICAL | 기억 검색·관계 변경 모두 0건, 근거 없는 답변 저장. 관계 부재를 증명하지 않음 |
| 11 | 18:43:49 | GRAPH | Graph first/repair 모두 `graph_plan_step_id_invalid`, 실패 |
| 12 | 18:44:07 | GRAPH | Graph first/repair 모두 `graph_plan_counterpart_binding_invalid`, 실패 |

실패한 네 요청은 모두 Selector 1회 + Graph Planner 2회(최초·자동 수정)로 논리·물리 3회가 보존됐다. first/repair 모두 `schema_validation / STOP`, Graph DB 조회·CRG 실행 전에 종료했다. 이번에는 Selector가 수정 기회를 소진한 것이 아니라 Graph가 수정 기회를 사용한 뒤에도 같은 오류가 반복됐다. 네 요청 모두 현재 재시도 허용 목록 밖이어서 버튼이 없는 정책과 일치한다.

### 확인된 계약 전달 문제와 후속 수정 제안

1. **단계 ID:** 내부 `GraphPlanStep`은 `^[a-z][a-z0-9_]{0,47}$`를 요구한다. parser도 비어 있지 않은 최대 48자 문자열을 요구하지만 provider schema의 `id`는 `type=string`뿐이고 시스템 설명에 ID 규칙이 없다. 실제 잘못된 ID 값은 현재 진단에 없어 특정 표기를 원인으로 단정하지 않는다. 합성 `step-1`은 동일 코드로 거절되고 `s1`은 통과하는 것을 확인했다. 우선 같은 계약에서 스키마·설명·수정 안내를 생성해 일치시키고, 필요하면 임의 ID 작성 자체를 줄이는 설계를 별도로 검증한다. 코드 재명명은 고유성·모든 종속 참조의 일관성을 증명할 수 있을 때만 고려한다.
2. **상대 binding:** 연산별 직접 `counterpart_ref` 또는 이전 단계 `input_ref`의 배타적 선택 규칙이 provider schema에 표현되지 않았고 설명도 어느 필드를 비워야 하는지 충분히 명시하지 않는다. 직접 조회는 `input_ref=null`, 선행 결과 사용 시 `counterpart_ref`를 생략하는 규칙과 범용 예시를 제공한다. 두 필드가 모두 있거나 없는 상태를 코드가 임의로 추측해 통과시키지 않는다. 향후 단일 binding 구조로 정리한다면 provider 호환성·기존 내부 계획 변환·참조 검증을 함께 검증한다.
3. **자동 수정의 구체성:** DirectLlmJsonError는 parser 예외 타입을 `parse_error_type`으로 전달하고, Graph adapter는 이를 `GraphPlannerOutputError.diagnostic`으로 사용한다. 따라서 이 사례의 repair 입력은 구체적 코드가 아닌 `GraphPlanContractError`가 된다. 새 진단 기록은 cause에서 구체적 코드를 추출하지만 기존 repair prompt 전달은 그대로다. 관측용 안전한 구체적 코드와 코드별 기대 규칙을 repair 입력에도 전달하는 것이 우선이다. raw 모델 출력·임의 예외 본문을 전달하거나 호출 예산을 늘릴 필요는 없다.
4. **확인 질문:** 4번은 인물 해석, 6번은 방향 해석에서 코드가 경로를 바꿨다. 최종 CLARIFICATION만 보고 AI가 처음부터 조회를 포기했다고 판단하지 않는다. `requester_character`·`responding_character` 처리와 한 인물의 관계 목록에 불필요한 두 끝점이 요구되는지 점검한다. 실제 중의성이 있으면 확인 질문을 유지한다.
5. **Canonical 선택:** 1·7번은 AI가 처음부터 Canonical을 선택했다. 관련 과거 기록과 현재 관계 구조의 용도를 분리해 평가하되, 앞선 대화가 다음 질문에 영향을 준 이번 연속 테스트를 독립 정확도 표본으로 해석하지 않는다.

우선순위는 구체적인 repair 안내와 Graph 스키마·검증 규칙 정합성, 이후 인물·방향 해석과 도구 선택이다. 질문 문구·인물 이름을 하드코딩하지 않고 모델 공통 계약으로 개선한다. 지침 보완은 완전한 준수를 보장하지 않으며, ID 자동화·binding 구조 변경은 종속 참조와 provider 호환성의 트레이드오프가 있다. 개선 효과는 이 질문들 외의 새 인물·방향·단계 조합에서도 확인해야 한다.

이번 진단 작업에서는 제품 코드·프롬프트·재시도 정책을 변경하거나 추가 실모델 요청을 보내지 않았다. 안전한 증거는 `g6-graph-test-batch.json`, `g6-graph-test-question-map.json`, 합성 계약 대조는 `g6-graph-contract-gap-probe.json`에 보존했다. 진단 패치의 실사용 관측은 추가로 확인됐지만 G5 전체 보존 Gate 및 G6의 허용 오류 재시도 실사용 검증 상태는 변경하지 않는다.

## 보존·원복

작업 전 원문, 기존 diff, G0 재현, G1–G2 독립 checkpoint와 테스트 출력은 workspace의 `.task-output/chat-graph-failure-20260912-162417/`에 있다. 기존 dirty/untracked 변경은 전체 reset/restore/clean으로 되돌리지 않는다.

주요 산출물은 `current-patch.diff`, 재시도 정책만 분리한 `manual-retry-policy.diff`, 파일 해시의 `patch-summary.json`, `g5-preservation.txt`, `g5-terminal-delta-audit.json`, `g6-runtime-source.json`, `g6-data-before.json`, `g6-data-after.json`이다. `record_patch.py`로 현재 패치와 작업 전 내용을 대조할 수 있다. root 계획 파일은 제품 Git 저장소 밖에 있으며 별도로 상태를 갱신했다.

- 사용자 재시도만 원복: `response_workflow._classify_failure()`의 새 Graph 분류 분기와 해당 policy import를 이번 diff 기준으로 제거한다. 진단·집계·이미 저장한 실패 행은 유지할 수 있다. 기존 retry API는 바꾸지 않았다.
- 진단·집계까지 원복: 작업 전 `before/`와 이번 patch를 비교하여 해당 변경만 역적용한다. 새로운 진단 JSON을 기존 코드가 읽는 데 migration은 필요하지 않다. NA 조립 옵션·모델·DB 데이터는 원복 대상이 아니다.
- 새 기본 진단 누출·집계 중복·terminal/fence 회귀가 발견되면 로컬 적용을 멈추고 해당 계층의 패치부터 되돌린다. 오류 검증이나 호출 상한을 제거해서 통과시키지 않는다.

이 패치는 Graph 오류의 관측과 명시적 사용자 복구를 개선한다. Graph 계획 작성 오류 자체, 도구 선택 정확도, `coordination_route_mismatch`, 과잉 BOTH를 해결했다고 주장하지 않는다. CI·merge·release·배포 완료와 구분한다.
