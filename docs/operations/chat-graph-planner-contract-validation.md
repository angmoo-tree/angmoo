# Graph Planner 계약 전달 개선 — 로컬 검증 기록

2026-09-12 KST. GP 계획의 단계 ID·상대 지정·repair 피드백 개선 기록이다.

**현재 상태: 제품 변경·합성 회귀·contributor runtime 적용 완료. 직접 USER CHECK 1건에서 Graph 최초 계획·실제 조회·근거·응답 저장을 확인했다. 구조 검사 PASS, 전체 보존 Gate는 기존 보호 메서드 변경으로 미통과. 자동 실모델 평가는 미실행이며 다른 연산·자동 수정의 실사용 검증은 남아 있다.**

## 기준선과 범위

- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 브랜치: `fix/chat-retrieval-debugging`
- HEAD: `ee8eabf7c68e5a7fb7a5c4e9d11dc0e4d2a56a8d`
- 기존 dirty/untracked 작업 위에 제품 파일 3개와 테스트 2개를 변경·추가했다. 새 브랜치·PR·commit·stage는 없다.
- NA와 `gemini-3.1-flash-lite/high`, positional entity refs 보류, 사용자 retry allowlist, 실행 예산·권한·원본 검증을 유지했다.
- frontend 제품 코드와 DB schema·사용자 데이터는 변경하지 않았다.

## 적용한 변경

1. `graph_plan_schema.py`: 생성 ID 후보 `step1`~`step3`을 기존 최대 단계 수에서 만들고 enum·설명에 반영했다. 기존 parser는 valid custom ID를 계속 받으며 종속 참조를 검증한다.
2. 같은 정책 모듈에서 6개 연산의 counterpart binding 설명을 제공한다. Graph adapter 카탈로그는 이를 사용한다. 직접 상대 지정은 `input_ref=null`, 종속 조회는 `counterpart_ref` 키 생략, 상대 없는 2개 연산은 둘 다 사용하지 않는 규칙이다.
3. Graph adapter는 기존 `graph_rejection`의 안전한 cause 분석으로 구체적 코드를 선택한다. Chat 서비스는 이미 기록한 rejection의 코드를 repair에 전달한다. 별도 코드 추출 정책을 중복 구현하지 않았다.
4. `repair.instruction`은 코드별 고정 규칙으로 생성한다. 임의 예외 본문이나 모델 계획 전체는 전달하지 않는다. 시스템 설명은 backend metadata와 비신뢰 user message/entity mention을 구분한다.

새 AI 호출·자동 수정 횟수·ID 자동 재명명·Cypher 수정은 없다. 이번 A/B/C 표기는 이전 NA 조정 값·인물 참조 패치와 별개다.

## GP0~GP5 기술 검증

| 검증 | 결과 |
| --- | --- |
| GP0 작업 전 내용·diff·HEAD·상태 보존 | 새 artifact 경로에 보존 |
| GP1 ID schema·설명 적용 후 기존 Graph 모듈 | 17 passed |
| GP2 상대 지정 설명 적용 후 기존 Graph 모듈 | 17 passed. 이전 실행과 합산하지 않음 |
| GP3~GP4 신규 계약·repair 및 기존 관련 7개 모듈 | **216 passed**, 그중 신규 합성 모듈 54개 |
| GP5 Supervisor·근거 응답·조립 3개 추가 모듈 | **52 passed** |
| 중복 없는 위 최종 두 검증의 합계 | **268 passed** |
| architecture inventory | PASS, modules=1090, internal_edges=4101, external_imports=3178 |
| architecture boundaries | PASS, modules=1090, edges=4101, legacy_exact_edges=0 |
| 원래 parser 함수 AST 비교 | 9개 모두 동일. schema 생성 함수와 신규 설명 helper는 별도 |
| 작업 전 snapshot과 수정 후 합성 비교 | 유효 `s1`은 둘 다 허용. `step-1`·상대 누락은 같은 정확한 코드로 계속 거절 |
| 전체 refactor preservation | **미통과**, 첫 오류 `Chat durable command changed: mark_terminal` |

합성 검증은 실제 JSON adapter→parser→Chat service→repair 요청 경로를 사용했다. ID·중복·상대 동시 지정/누락·잘못된 참조·실행 전 방향 검증 오류에서 정확한 diagnostic을 확인했다. 수정 성공 시 executor로 진행하고, 수정 재실패 시 실행하지 않는다. Selector 1 + Graph Planner 2의 논리·물리 3회와 CRG 0회를 확인했다. 방향 오류는 parser 이후의 서비스 검증 경로도 검증한다.

추가로 6개 연산×4개 binding 조합, valid custom ID·금지 ID·잘못된 종속 참조, provider schema 직렬화, unknown 오류의 비공개 본문 차단을 검증했다. 기존 회귀는 공유 repair 선사용·취소·BOTH·lifecycle·최신 사용자 재시도·정상 경로를 포함한다.

개발 중 기존 테스트 1개가 임의 `malformed_json` 문자열의 repair 전달을 기대해 실패했다. 새 안전 코드 계약에 맞춰 `unknown`을 기대하도록 변경했다. 신규 테스트의 잘못된 ranking fixture와 실제 dispatch counter 누락도 바로잡은 뒤 위 최종 결과를 얻었다. 실패한 개발 실행을 통과 횟수에 합산하지 않는다.

전체 보존 검사의 첫 오류는 선행 진단 패치에서 기록한 것과 같다. 이후 test introduction 오류 목록은 해당 예외 이후 targets가 비워지는 경로의 영향이 있어 독립적인 테스트 삭제로 단정하지 않는다. 이번에 `mark_terminal`, 보호 baseline, 승인 evidence, checker를 변경하지 않았다. **이 검사 전체가 통과한 것으로 보고하지 않는다.**

## GP6 실모델 평가

**NOT RUN — 새 자동 실모델 호출 0회.** 계획의 기본 예산 0회를 유지했다. 이전 평가의 추가 허용분을 이월하지 않았다. 합성 테스트 통과는 모델 성공률이나 실제 Graph 응답 품질 향상 수치가 아니다. 선택적 실모델 평가에는 별도 입력·비용 승인이 필요하다.

## GP7 contributor 실행·사용자 검증

실행 반영 준비 시 `committed=41`, `failed=12`였고 진행 중인 Chat 요청은 없었다. 마지막 accepted request 모델은 `gemini-3.1-flash-lite/high`다. 기존 NA 옵션은 `native_controls=True`, `code_coordination=True`, `positional_entity_refs=False`다.

| 실행 확인 | 결과 |
| --- | --- |
| backend | `5f225b03efa84e24879fbc41e1498e9ead541722ecb3f6e81d3abde6e9ab18d3` |
| image | `sha256:032d9d714b94213773ae8f4f88167abad15b68b60f3004230559b380a16f20fd` |
| frontend | 기존 `bfbc52cb114e955768f5f0402e8b8184f35e101a1fe8412942a92c5c7e176e50` 유지 |
| source | 실행 중 파일 6개의 SHA256이 현재 로컬 파일과 일치 |
| 동작 설정 | 생성 ID enum·6연산 binding 설명 확인, NA 옵션·모델 기준 유지 |
| 기존 데이터 | 재시작 전후 `committed=41`, `failed=12`. 53개 요청 상태·retryable·call_tracker·node_state 전체 metadata hash 동일 |
| health | backend healthy, `/health`에서 `status=ok`, `persistence=sqlite`, `graph=ladybug` |
| 브라우저 주소 | `http://127.0.0.1:3000` HTTP 200 |

backend만 `compose.yml`·`compose.dev.yml`의 기존 contributor 설정으로 빌드·교체했다. 기존 named volume을 유지하고 새 user message나 실모델 호출을 자동 생성하지 않았다. 실행 반영은 **PASS**이며 모델의 실제 새 답변 성공을 뜻하지 않는다.

최초 반영 직후에는 USER CHECK PENDING으로 기록했다. 이후 사용자가 새 질문의 응답과 근거를 전달했고 아래 1건을 확인했다.

### 2026-09-12 직접 USER CHECK — 최초 Graph 조회 성공

요청 `request-bec4707163af472abadc6c32ff6e268c`의 질문이 사용자가 제시한 질문과 정확히 일치함을 DB에서 비교했다. 본문을 진단 산출물에 복사하지 않고 일치 여부만 저장했다. 동일 backend/image와 고정 모델·thinking에서 실행됐다.

- Supervisor AI가 GRAPH만 선택하고 인물·방향을 정상 해석했다. 최초 선택 검증 통과, 수정 없음.
- Graph Planner `first_pass_valid=true`, `repair_used=false`, 계획 1단계가 통과했다.
- `direct_relationship`, `outgoing`, counterpart filter 활성 상태로 실제 graph projection 조회 1회를 실행했다.
- 관계 1건, 제외 0건, ready 상태였다. 검증된 `graph_relationship` 근거 1건을 조립·고정했다.
- CRG 입력 근거 1건, Canonical Planner 0회, 추가 Today SNS 선택 0건. 최종 `committed`, `relationship_used`, degraded reason 없음, partial axes 없음.
- 논리·물리 호출 모두 Supervisor 선택 1 + Graph Planner 1 + CRG 1 = 3회. `repair_node=null`.
- 원본 관계 version 12: familiarity 15, affinity 2, trust 0, tension 0, interaction_count 11. 사용자가 보여준 근거 수치와 모두 일치한다.
- DB 생성~terminal 간격 약 21.05초. 선택 AI 8.673초, Graph Planner 6.219초, CRG 5.112초. 관측된 조회 단계는 66.52ms이며 이를 순수 DB 쿼리 시간으로 해석하지 않는다.

**판정: 단일 직접 관계·outgoing USER CHECK PASS.** 실제 최초 계획에서 ID·상대 지정 오류가 발생하지 않았다. 자동 수정이 필요하지 않았으므로 repair 피드백의 실모델 회복 효과는 이 요청으로 검증하지 않았다. 다른 연산·다단계·전체 모델 성공률도 이 1건으로 확정하지 않는다. GP6 자동 평가 0회와 기존 전체 보존 Gate 상태는 그대로다.

답변의 스승·멘토 표현은 관계 수치 자체가 제공하는 관계 유형은 아니다. 이번 Graph 근거가 직접 뒷받침하는 값과 페르소나·대화상의 표현을 구분한다.

안전한 요청 진단: artifact의 `gp7-user-check-104118.json`.

## GP8 산출물·원복

### 추가 사용자 검증 5건 — 2026-09-12 DB 시각 10:50~10:52

질문 5개를 저장된 user message와 정확히 비교해 모두 일치함을 확인했다. 동일 수정본 backend에서 실행됐고, 새 자동 모델 호출 없이 기존 진단을 읽었다.

| 번호 | 요청 | 결과·직접 원인 |
| --- | --- | --- |
| 1 | `request-42792b8285e74716a87f14e305051417` | Graph 최초·repair 모두 `graph_plan_counterpart_direction_mismatch`. 확정된 방향에 따른 상대와 계획의 상대가 불일치. executor 미실행 |
| 2 | `request-4456fc4b8edc4a2d9c6312754e4ae439` | Graph 최초·repair 모두 `graph_plan_direction_mismatch`. 확정된 방향과 계획 방향 불일치. executor 미실행 |
| 3 | `request-0ae21acf42a540b2b5284961a8be3774` | Supervisor 최종 `relationship_invalid`, repair 소진. Graph Planner 미진입 |
| 4 | `request-88ebd20474ed40f29a1874699017e7fe` | 최초 `graph_plan_direction_mismatch` 후 repair 성공. `shortest_path/outgoing` 실제 조회, 관계 1·노드 2·경로 1, 근거 1, CRG committed |
| 5 | `request-2bc52278d2874144b95b6827a79b6628` | Supervisor 최종 `native_output_incomplete`, repair 소진. Graph Planner 미진입 |

1·2번은 논리·물리 3회(선택1+Graph2), 4번은 4회(선택1+Graph2+CRG1)다. 3·5번의 전체 call_tracker는 비어 있으나 router_diagnostic에 physical_attempts=2와 repair_used/exhausted가 남아 있다. 이를 호출 0회라고 해석하지 않는다. 1·2번 retryable=false, 3·5번 true다.

이번에 Graph에 진입한 1·2·4번에서는 이전 ID·배타적 binding 오류가 기록되지 않았다. 이것이 전체 해결율을 보장하지는 않는다. 4번은 실모델 repair 회복을 관찰한 사례지만 정확한 안내만의 인과 효과나 모든 repair의 성공을 증명하지 않는다.

`counterpart_direction_mismatch`는 상대 값과 확정된 방향의 불일치이며 `counterpart_binding_invalid`와 다른 오류다. 원본 잘못된 ref·방향과 상위 의미 해석 값은 이 진단에 없어 어느 값이 틀렸는지 단정하지 않는다. `relationship_invalid`는 여러 세부 오류를 합친 코드이고, `native_output_incomplete`는 finish_reason이 STOP/None 이외인 경우다. 3번의 정확한 세부 필드, 5번의 실제 finish_reason 및 각 최초 오류는 현재 저장된 진단만으로 확정할 수 없다.

후속 우선순위는 상대·방향 확정값의 Planner 전달/수정 계약 비교, 관계 목록의 Supervisor 입력 계약 점검, Supervisor 세부 오류·finish 상태의 안전한 보존이다. 이번 진단에서는 제품 코드를 변경하거나 재시도 요청을 보내지 않았다. 산출물은 `gp7-five-question-check.json`이다.

산출물: `D:/project_code/angmoo-workspace/.task-output/chat-graph-planner-contract-20260912-192305/`

- `before/`, `existing.diff`, `status.txt`, `head.txt`: 이번 시작 시점의 기존 변경 보존.
- `gp1-schema.py`, `gp1-adapter.py`, `gp2-schema.py`, `gp2-adapter.py`: 단계별 source snapshot.
- `current-patch.diff`, `patch-summary.json`, `record_patch.py`: 이번 변경만의 diff·hash·parser AST·합성 대조.
- `gp4-tests.txt`, `gp5-extra-tests.txt`, `gp5-inventory.txt`, `gp5-boundaries.txt`, `gp5-preservation.txt`: 검증 결과.
- `gp7-*`, `runtime_probe.py`: contributor source·상태·설정 및 읽기 전용 데이터 증거.

원복은 `current-patch.diff`와 시작 snapshot을 기준으로 해당 hunk만 되돌린다. 기존 NA·Canonical·Graph 진단·집계·retry 정책을 `HEAD`로 되돌리지 않는다. ID 설명(A), 연산 입력 설명(B), repair 전달(C)의 공통 helper 참조도 함께 확인한다. 저장한 사용자 대화·실패 기록을 삭제하지 않는다.

남은 과제는 실제 모델의 전체 최초/수정 성공률, 다른 연산·자동 수정 USER CHECK, 기존 전체 보존 Gate와 별도 도구 선택·CLARIFICATION·근거 표시 문제다. 이 구현으로 해당 후속 문제가 모두 해결됐다고 주장하지 않는다.
