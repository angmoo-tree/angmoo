# 채팅 도구 조정 값·인물 참조 분리 패치 로컬 검증 기록

- 작성일: 2026-09-12
- 현재 상태: **P0~P8 EXECUTED · P6 FORMAT/OVERALL SELECTION PASS / FULL ADOPTION GATE NOT MET · LOCAL COMPOSITION NA ENABLED · USER CHECK PENDING**
- 사용자 결정(2026-09-12): **A 유지 / B 기본 적용 보류**에 이어 **“NA 적용을 해줘”**를 요청했다. 채팅 실행 조립부는 NA를 기본으로 사용하며 B 코드·검사는 비활성 실험 옵션으로 보관한다. 이번 적용은 기존 전체 채택 Gate의 통과 판정을 변경하지 않는다.
- 실행 계획: [09-12 P0~P8 계획](<../../../docs/plan/09-12 채팅 도구 조정 값 누락·인물 참조 오류 분리 개선과 검증·원복 로컬 세부 계획.md>)
- 선행 기록: [네 함수 표현 F0~F7 검증](chat-supervisor-control-validation.md)
- 로컬 브랜치: `fix/chat-retrieval-debugging`, HEAD `ee8eabf7c68e5a7fb7a5c4e9d11dc0e4d2a56a8d`.
- 현재 채팅 composition: `native_controls=True`, `code_coordination=True`, `positional_entity_refs=False`. 인자 없는 provider 생성자는 비교·원복을 위해 세 옵션 false를 유지한다. 저장된 모델 설정·DB는 변경하지 않았으며 서버 실행·직접 사용자 확인은 별도다.

## 1. 현재 판단

**두 패치의 구현·독립 원복·기존 실행 연결과 NA 보류 질문 비교를 완료했다. 후속 사용자 요청으로 채팅 composition에 NA를 적용했고 B는 비활성 실험 옵션으로 보존한다. 실제 채팅 사용자 검증은 대기 중이다.**

첫 유지 결정에서는 사용자가 A 유지·B 기본 적용 보류를 확정했고 기본 옵션을 변경하지 않았다. 이후 NA 적용 요청에 따른 composition 변경은 §11에 구분해 기록한다. B의 기본 적용은 기존 참조 방식보다 추가 이점이 확인될 때 별도로 판단한다.

개발 8문항을 3회씩 비교한 결과 NA는 effective 선택 24/24, NAB는 23/24였다. NAB는 최초 인자 계약 24/24를 통과했지만 영어 과거 기록 질문 1건이 `proposed=CANONICAL`, `effective=CLARIFICATION`으로 끝났다. 이 요청은 인물 목록·관계 참조가 없는 것으로 기록됐다. 따라서 인물 참조 문법 오류로 부르거나 B가 그 전환의 원인이라고 단정하지 않는다.

NA와 NAB 모두 개발 형식·선택 진입 수치와 핵심 사례 기준은 충족한다. 이번에는 변경 범위가 더 작고 개발 effective 선택 오류가 없었던 NA를 후속 후보로 선택한다. B는 자동 검증된 비활성 실험 옵션으로 남긴다. A 없는 B인 NB의 실모델 효과는 평가하지 않았다.

이는 개발 표본에서의 관찰이다. 사용자 전체 질문의 성공 확률, B의 유해성, 다른 모델의 성능 향상, 실제 회상 문제 해결을 증명하지 않는다.

P6 보류 24개×2회에서 NA는 최초 계약 48/48, effective 선택 45/48(93.8%)였다. 기존 M0의 40/48(83.3%)보다 전체 선택은 개선됐으나, GRAPH 기대 질문의 불필요한 BOTH가 2회→3회로 늘어 기존 과잉 조회 Gate를 충족하지 못했다. BOTH 선택 지연도 2개 표본에서 확인 임계치를 초과했다. **수행 완료와 전체 채택 기준 충족을 구분한다.** 같은 보류 질문을 보고 지침을 고친 뒤 재평가하지 않았다.

## 2. 구현과 소유 경계

| 영역 | 구현 내용 |
| --- | --- |
| `contracts/supervisor_selection.py` | 요청 동안 고정되는 A/B 옵션, 모델 스키마와 실행 스키마 분리, 위치 참조 정규화, 단계별 검증 진단 |
| `contracts/workflow_recipe.py` | 기존 registry를 공유하는 순수 recipe 선택, 조정 출처의 모델/코드 구분 |
| `contracts/retrieval_intent.py` | 내부 `coordination_source` 출처. 의미 payload·hash에는 추가하지 않음 |
| `contracts/retrieval_router.py` | 기존 검증 순서·거부 규칙을 유지하며 단계 도달/실패 기록 |
| `service/retrieval_routing.py` | 기존 guard·scope resolver 이후 최종 route와 코드 조정 값의 정합성 유지 |
| `service/both_retrieval.py` | 코드가 결정한 값을 모델 hint 수락으로 집계하지 않음. 세 실행 recipe는 유지 |
| `integrations/llm/supervisor_selection.py` | 옵션에 따른 모델 인자·작성 안내 연결. 특정 provider 문자열 보정 없음 |
| `runtime/chat/retrieval_tools.py` | 내부 envelope에 맞는 실행 스키마로 실제 StructuredTool·ToolNode 연결 |
| 평가 스크립트·테스트 | P5 세 후보 교차 비교, P6 동결·예산 검사, 네 조합의 계약·실행·원복 검증 |

backend 도메인·service·runtime·integration 책임 경계를 유지했다. frontend `ARCHITECTURE.md`·`DESIGN.md`를 확인했고 frontend 파일·화면·문구는 변경하지 않았다. DB 스키마, S2 검색 완화, 모델 상향, 별도 결과 평가 AI는 추가하지 않았다.

실행 스키마를 분리하면서 모델에 요구하는 고정 `relationship.perspective`와 내부 관계 payload를 구분했다. 내부 payload에는 해당 필드가 없으므로 실행 스키마에서만 제외한다. 모델 입력의 perspective 검증·관계 방향·scope 검증은 유지한다.

## 3. 옵션과 원복

| 조합 | native_controls | code_coordination | positional_entity_refs | 검증 |
| --- | ---: | ---: | ---: | --- |
| 기존 기준·원복 경로 | false | false | false | 기존 회귀·P0 prompt/schema 동등성 |
| N0 | true | false | false | 자동 검사·개발 실모델 24회 |
| NA | true | true | false | 현재 채팅 composition 기본; 자동 검사·개발 24회·보류 48회 |
| NB | true | false | true | 자동 검사만 수행 |
| NAB | true | true | true | 자동 검사·개발 실모델 24회 |

인스턴스 생성 시 옵션을 고정한다. 진행 중인 요청에서 스키마·정규화 조합을 바꾸지 않는다. `native_controls=False`에 A/B를 켜는 조합은 생성 시 거부한다.

- **B만 원복:** 새 요청에 `native_controls=True, code_coordination=True, positional_entity_refs=False`를 사용한다. 모델이 기존 `ref`를 작성하며 조정 값은 계속 코드가 결정한다.
- **A만 원복:** 새 요청에 `native_controls=True, code_coordination=False, positional_entity_refs=True`를 사용한다. 모델이 기존 `coordination_hint`를 작성하며 위치 참조 변환은 유지한다.
- **두 패치 원복:** N0를 사용한다. 기존 제품 기본 경로까지 돌아가려면 세 옵션을 모두 false로 둔다.

네 조합의 스키마·내부 payload/hash·runtime 검사와 병행 요청의 별칭 격리를 통과했다. DB 마이그레이션이나 데이터 원복은 없다. 기존 dirty 파일 전체를 HEAD로 되돌리지 않는다. 물리적 코드 제거가 필요하면 P0 파일 보존본과 이번 작업 diff를 기준으로 해당 변경 구간만 역적용한다.

## 4. P5 실모델 비교

동일한 `gemini-3.1-flash-lite`, thinking `high`, 출력 상한 3072, provider timeout 30초, 요청 deadline 95초, 동시성 2로 비교했다. temperature·seed는 설정하지 않았다. SDK는 google-genai 2.17.0, LangGraph 1.2.2, langgraph-prebuilt 1.1.0이다.

개발 8개×3회×3후보=72회이며 후보를 교차 배치했다. 후보별 의미 선택 지침과 두 도구 description, context·resolver·Today fixture를 유지하고 A/B 인터페이스 작성 안내만 바꿨다. N0의 prompt·schema 및 기존 기본 경로는 P0 보존본과 정확히 같음을 확인했다.

| 지표 | N0: 패치 없음 | NA: A만 | NAB: A+B |
| --- | ---: | ---: | ---: |
| 최초 계약 통과 | 22/24 (91.7%) | 23/24 (95.8%) | 24/24 (100%) |
| repair 후 유효 결과 | 24/24 | 24/24 | 24/24 |
| 기대 effective 선택 | 19/24 (79.2%) | 24/24 (100%) | 23/24 (95.8%) |
| repair 사용 요청 | 2 | 1 | 0 |
| 실제 provider 호출 | 26 | 25 | 24 |
| 입력 토큰 합 | 112,185 | 98,877 | 99,687 |
| 출력 토큰 합 | 2,842 | 2,181 | 1,704 |
| 요청별 provider 시간 합 p95 | 14,245ms | 9,619ms | 10,499ms |

지연은 요청마다 최초·repair의 provider 시간을 합한 값으로, queue 대기와 실제 검색·CRG 시간은 포함하지 않는다. 후보가 선택한 경로 구성이 다르므로 위 전체 p95만으로 동일 경로 비용 Gate 통과를 주장하지 않는다.

## 5. 오류를 구분한 해석

| 후보 | 계약·선택 관찰 |
| --- | --- |
| N0 | 최초 `entity_ref_invalid` 1회, `coordination_route_mismatch` 1회. 모두 repair로 유효해짐. GRAPH 질문의 과잉 BOTH 4회, 실제 BOTH의 CANONICAL 단독 1회 |
| NA | 두 호출의 전체 의미 인자가 불일치해 `coordination_route_mismatch` 1회; repair로 회복. `coordination_hint` 누락이 아님. effective 선택 오류 없음 |
| NAB | 최초/repair 계약 오류 없음. 과거 기록 질문 1회가 CANONICAL 선택 후 CLARIFICATION으로 전환. raw 출력은 보관·공개하지 않았으며 전환 원인을 참조 문법 오류라고 확정할 근거 없음 |

핵심 case-01/03/04는 NA와 NAB 모두 각 3/3이었다. 개발 사례에 맞는 이름·문장·정규식 분기를 제품 코드에 추가하지 않았다. P5 결과를 본 뒤 prompt·schema·정답을 바꾸지 않았다.

### 5.1 적용 대상·검증 도달 분모

아래는 최초 응답과 repair를 모두 포함한 인자 검사 기록이다. 요청 분모 24와 시도 분모 24~26을 혼동하지 않는다.

| 검사 축 | N0 적용/도달/통과 | NA 적용/도달/통과 | NAB 적용/도달/통과 |
| --- | ---: | ---: | ---: |
| 인물 목록·참조 | 19/19/18 | 17/16/16 | 12/12/12 |
| 관계 필드 | 9/9/9 | 8/7/7 | 9/9/9 |
| 유효 BOTH의 조정 계약 | 6/6/6 | 4/4/4 | 3/3/3 |

NA는 두 호출 일치 검사에서 1회 중단되어 그 시도의 인물·관계 검사는 `not_evaluated`다. N0의 단일 조회에서 조정 계약 위반이 발생한 기록은 전체 단계 실패로 보존하며 유효 BOTH 수에 합치지 않는다. 조정 필드가 없는 A의 통과를 모델 hint 정답률로 집계하지 않는다.

인물 이름을 평가할 수 있는 개발 표본은 각 후보 9개 중 9개, 방향을 평가할 수 있는 표본은 6개 중 6개가 기대와 맞았다. 이는 평가용 합성 resolver의 binding이다. 실제 사용자 DB의 인물 식별 정확도와 동일시하지 않는다. 실제 SQLite의 동일 World·숨김 인물 제외는 별도 자동 fixture 검사로 확인했다.

## 6. 자동 검사와 검증 범위

- 기존 관련 검사 81 passed.
- 계약·provider·기존 chat·실행·아키텍처 회귀: **545 passed, 6 skipped**, 4 warnings. skip은 기존 진단용 benchmark, warning은 Starlette/httpx deprecation이다.
- 마지막 패치·P6 예산/Gate 검사: **135 passed**. 위 545와 중복되는 검사이며 합산하지 않는다.
- import inventory 재생성·검사 PASS: modules 1,087, internal edges 4,090, external imports 3,175. 실제 파일 inventory만 갱신했으며 정책 baseline의 금지 경계를 완화하지 않았다.
- architecture boundary PASS, legacy exact edges 0.
- 전체 refactor preservation PASS: 보호 계보 2,913, 검사 시 수집 3,237, 보존 항목 37. 수집 수는 테스트 실행 통과 수가 아니다.
- P0 대비 기존 혼합 경로·N0 prompt/schema 정확 일치 PASS.
- 실제 ToolNode와 BOTH coordinator의 세 recipe, 빈/정상 결과, call ID·receipt·envelope hash, CRG·최종 저장 연결 검사 PASS. 이 검사는 fake provider/Planner 결과를 사용한 자동 통합 검사다.
- scope·삭제/숨김·부분 실패·취소·deadline·중복 실행·근거 고정·저장 회귀는 기존 chat 검사와 새 네 조합 검사로 확인했다.

초기 검사에서 모델 wire fixture가 내부 관계 payload를 그대로 사용한 문제와 테스트용 ToolPlanningService 연결 누락을 수정했다. 첫 broad 명령의 wildcard 미확장으로 수집 0건·exit 4가 발생한 뒤 실제 파일 경로로 재실행했다. 초기 실패 로그도 보존한다. 이를 실모델 성능 실패나 최종 통과 결과로 섞지 않는다.

## 7. P6 보류 질문 평가와 채택 판단

P5가 완료된 뒤 NA의 source·prompt·schema·fixture와 기존 M0의 adapter·prompt·schema를 동결·대조했다. M0/NA에 보류 24문항을 각 2회 실행해 96회 모두 완료했다. 모델·SDK·출력 상한·동시성·repair 정책은 P5와 같다. M0는 이전 혼합 출력 기준이며, N0로 대체하지 않았다. 따라서 이 비교는 네 함수 표현과 A를 포함한 후보 전체의 효과이지 A만의 기여율이 아니다.

| 지표 | M0: 기존 혼합 출력 | NA: 네 함수+A |
| --- | ---: | ---: |
| 최초 계약 통과 | 36/48 (75.0%) | 48/48 (100%) |
| repair 후 유효 결과 | 43/48 (89.6%) | 48/48 (100%) |
| 기대 effective 선택 | 40/48 (83.3%) | 45/48 (93.8%) |
| 기대 proposed 선택 | 40/48 | 45/48 |
| repair 요청 | 12 | 0 |
| 실제 provider 호출 | 60 | 48 |
| 입력 토큰 합 | 160,676 | 190,954 |
| 출력 토큰 합 | 4,936 | 3,654 |
| thought 토큰 합 | 52,611 | 23,679 |
| 전체 요청 provider 시간 합 p95 | 15,930ms | 8,235ms |
| 전체 요청 elapsed p95 | 22,646ms | 19,012ms |

입력 토큰은 약 18.8% 늘었고 physical 호출은 20% 줄었다. 가격·캐시 과금까지 평가한 자료가 아니므로 실제 비용이 줄었다고 단정하지 않는다. elapsed에는 평가기의 대기·스케줄링·검증 지연이 섞이며 실제 채팅 검색·CRG 지연은 측정하지 않았다.

### 7.1 질문 유형과 언어

유형은 동결 fixture의 기대 route로 나눴다. 과거 질문의 모든 하위 의미를 새로 분류하거나 실패 후 정답을 수정하지 않았다.

| 기대 유형 | M0 정답 | NA 정답 | NA 관찰 |
| --- | ---: | ---: | --- |
| CANONICAL | 17/22 | 22/22 | 조회 누락 0. 기준 M0는 계약 실패 4회·맥락 단독 1회 |
| GRAPH | 3/6 | 3/6 | 나머지 3회가 과잉 BOTH. 기준 M0는 과잉 BOTH 2회·계약 실패 1회 |
| BOTH | 2/2 | 2/2 | 필요한 두 조회 선택 보존. 실모델 표본은 적음 |
| CURRENT_CONTEXT | 14/14 | 14/14 | 추가 조회 0 |
| CLARIFICATION | 4/4 | 4/4 | 잘못된 조회 실행 선택 0 |
| 한국어 전체 | 26/30 | 29/30 | 전체 도구 선택 기준 |
| 영어 전체 | 14/18 | 16/18 | 전체 도구 선택 기준 |

NA 오선택 3회는 case-19 첫 회차와 case-27 두 회차다. 모두 `proposed=BOTH`, `effective=BOTH`, guard 추가 없음이다. 계약 오류나 코드가 검색 도구를 추가한 결과가 아니다. M0의 terminal 실패 5회는 모두 최종 `json_decode_failed`였으며, 이를 평가에서 제외하지 않았다.

### 7.2 동일 경로의 정상 선택 지연

정답인 effective 경로이면서 repair 없는 요청만 묶어 provider 시간 p95를 비교했다. 두 후보에서 성공한 문항 구성이 다를 수 있어 엄밀하게 짝지은 지연 실험은 아니며, 작은 표본은 재확인이 필요하다.

| 경로 | M0 표본/p95 | NA 표본/p95 | 기존 확인 임계치 비교 |
| --- | ---: | ---: | --- |
| CANONICAL | 10 / 12,588ms | 22 / 7,675ms | 초과 없음 |
| GRAPH | 3 / 14,573ms | 3 / 8,762ms | 초과 없음, 표본 부족 |
| BOTH | 2 / 6,301ms | 2 / 7,729ms | +1,428ms, 허용 증가 +1,260.2ms 초과 |
| CURRENT_CONTEXT | 14 / 5,794ms | 14 / 4,460ms | 초과 없음 |
| CLARIFICATION | 4 / 11,547ms | 4 / 7,745ms | 초과 없음, 표본 부족 |

BOTH p95는 표본 2개에서 사실상 최대값이다. 비교 대상은 최초 선택 provider 호출 시간이며 실제 두 조회의 병렬/순차 실행 시간이나 코드 Supervisor 처리 시간을 잰 것이 아니다. 추가 AI 호출·SDK retry는 해당 두 요청에서 없었다. 이 자료만으로 새 코드가 느려졌다고 원인을 확정하지 않으며, 지연 Gate는 추가 확인 필요로 남긴다. 평가 예산이 소진됐으므로 재측정하지 않았다.

### 7.3 기존 Gate 적용

| 기준 | 결과 |
| --- | --- |
| 전체 보류 96회 완료 | PASS |
| 최초 계약 95% 이상·terminal 형식 실패 0 | PASS: NA 48/48 |
| 전체 선택 90% 이상·M0 정답 수 이상 | PASS: 45/48 ≥ 40/48 |
| CANONICAL 기대 질문 90% 이상·조회 누락 증가 없음 | PASS: 22/22, 누락 0 |
| 일반 맥락·GRAPH 단독의 과잉 조회 증가 없음 | **NOT MET:** GRAPH 과잉 2→3 |
| 필요한 BOTH·기존 실행 규칙 보존 | 자동 실행 검사 PASS, 보류 선택 2/2. 실모델 일반화는 표본 부족 |
| 비용·동일 경로 지연 | 입력 토큰 증가 기록. **BOTH 지연 추가 확인 필요**, 예산 소진으로 재측정 보류 |
| P6 종료 시점 제품 기본 활성화·직접 USER CHECK | NOT PERFORMED / DEFAULT OFF; 후속 로컬 적용은 §11 |

과잉 조회가 늘지 않아야 한다는 기존 기준을 전체 정확도 상승으로 대체하지 않는다. 관련성 평가 AI·모델 상향·선택 지침 재튜닝으로 이번 실패를 보정하지 않았다.

## 8. 예산

P5가 사용한 최초 선택은 72회, 실제 provider 호출은 75회다. 기존 사용·중단 예약 188회에 더한 P6 시작 전 원장은 **started=260 / maximum=312, remaining=52**였다. 기존 중단 예약 5회는 돌려놓지 않았다. 별도 개발 probe 호출은 0회다.

P6은 **기존 M0 대 NA, 보류 24개×2회×2후보=96회**로만 실행하도록 준비했다. P5 후보 source·prompt·schema·fixture hash를 검사하고 기존 F2 M0 adapter·prompt·schema hash까지 대조하는 사전 검사가 통과했다. 사전 검사는 자격증명 읽기·모델 호출·예산 변경이 모두 0이다.

당시 잔여보다 44회가 부족하여 계획 §12에 따라 사용자에게 추가 허용 여부를 요청했다. 사용자가 **“추가 44회 허용하고 P6 진행”**을 명시한 뒤 상한을 312→356으로 변경하고 보류 96회 비교를 시작했다. 승인 전후 원장을 별도 보존했다. 각 요청 repair 최대 1회, 각 논리 호출 physical 최대 2회인 기존 상한은 유지한다. 0건/불완전 결과를 성공 처리하거나 반복 수를 줄여 F4 PASS를 만들지 않는다.

P5 동결 source는 그대로 보존하고 P6 runner 준비는 별도 heldout-source에 둔다. P6 결과를 보고 후보를 수정하거나 같은 보류 입력으로 합격할 때까지 재실행하지 않는다.

P6은 최초 선택 96회·실제 provider 108회로 완료했다. 이번 P 실행 합계는 **최초 선택 168회, 실제 provider 호출 183회**다. 최종 원장은 **started=356 / maximum=356, remaining=0**이다. 승인된 상한을 넘기지 않았고 transport retry로 인한 추가 physical 호출은 관찰되지 않았다. 최초 선택과 repair 15회를 구분한다.

## 9. 증거·재현 파일

workspace 로컬 산출물 root: `.task-output/chat-supervisor-arguments-20260912/`.

| 경로 | 내용 |
| --- | --- |
| `baseline.json`, `baseline.diff`, `baseline/`, `plan-before.md`, `budget-before.json` | P0의 2,315개 파일 hash, 기존 dirty/untracked 55개와 작업 전 원장·계획 |
| `source/`, `source-manifest.json` | P5에서 실행한 동결 소스 1,117개 파일 |
| `p0-protocol-parity.json` | 기본/네 함수 N0의 prompt·schema P0 동등성 |
| `p3-regression-retest.txt`, `p3-patches.txt` | broad 회귀 및 패치 초기 통과 기록 |
| `p3-inventory-refresh.txt`, `p3-boundaries.txt`, `p3-preservation.txt` | 아키텍처·보존 검사 |
| `evaluation/development/metadata.json` | 모델·SDK·옵션·prompt·schema·source·fixture hash |
| `evaluation/development/results.jsonl`, `summary.json`, `p5-analysis.json` | 최초/repair·세부 분모·proposed/effective·비용·개발 결과 |
| `heldout-source/`, `p6-preflight.txt` | P5 후보를 변경하지 않은 P6 실행 준비·동결 검사 |
| `heldout-source-manifest.json`, `evaluation/heldout/metadata.json` | 동결 후보·M0 기준·SDK·예산·입력 hash |
| `evaluation/heldout/results.jsonl`, `summary.json`, `p6-analysis.json` | 보류 96회와 Gate·오류·언어·동일 경로 지연 |
| `budget-before-p6-approval.json`, `budget-after-p6-approval.json` | 사용자 추가 44회 승인 전후 원장 |
| `implementation-review.json`, `implementation-from-p0.diff` | P0 대비 작업 범위·기존 파일 보존·앱 소스 동결 일치 |
| `budget-final.json`, `p8-closure.json` | 최종 356/356 원장, 중복/상한/링크/브랜치·HEAD/동결 소스 일치 확인 |

원장은 기존 `.task-output/chat-supervisor-controls-20260911/global-budget.json`을 계속 사용한다. 평가에 필요한 자격증명은 기여자 Docker volume을 읽기 전용으로 연결해 사용했다. 설치된 Angmoo 데이터 경로는 조회하지 않았다. 대화 본문·실제 인물 ID·키·raw provider 출력은 이 문서나 평가 일반 로그에 남기지 않았다.

## 10. P8 종료와 재개 조건

P8 종료 시점에는 로컬 구현·자동 검사·최초 선택 실모델 평가까지 완료했고 제품 기본값은 OFF였다. 이후 §11의 사용자 요청으로 로컬 composition을 NA로 변경했다. 실제 DB 검색과 실제 Planner·CRG를 모두 사용한 사용자 회상 검증, 직접 USER CHECK, CI는 별도이며 이번 선택 평가로 완료 처리하지 않는다.

정상 경로의 AI 호출 2/3/4 구조와 코드 기반 결과 계약 검사, 별도 CRG 역할을 유지한다. 도구 조회 뒤 결과의 의미를 평가하는 AI 호출이나 CRG의 재검색 권한을 추가하지 않았다.

P0~P8의 구현·자동 검사·개발 비교·보류 비교·부분 원복·종료 기록을 수행했다. 원래 로컬 브랜치·HEAD와 기존 변경을 보존했고 새 브랜치·worktree·이슈·PR·commit은 만들지 않았다. 평가 전용 Docker 컨테이너는 종료 시 제거했으며 기존 frontend/backend 컨테이너를 시작하지 않았다.

선행 F2 실패와 원래 R7 미달은 날짜별 이력으로 유지한다. 후속 NA가 형식·전체 선택 기준을 통과한 사실은 별도로 연결한다. F4 전체 채택 기준과 실제 런타임·사용자 검증은 미충족 상태다.

재개할 때에는 이 보류 집합을 독립적인 새 보류 자료로 재사용하지 않는다. 필요한 후속 작업은 과잉 도구 선택의 원인 검토, 일반화 가능한 새 검증 입력·별도 예산 확정, BOTH 지연 재확인이다. B의 실모델 채택은 별도 판단으로 남긴다. P 계획 수행 완료를 제품의 회상 오류 해결이나 배포 완료로 표시하지 않는다.

## 11. 2026-09-12 사용자 요청에 따른 NA 로컬 적용

사용자가 기본 적용 절차와 남은 검증 범위를 확인한 뒤 **“NA 적용을 해줘 그럼”**을 요청했다. 이 요청에 따라 `backend/app/runtime/chat/generation_workflows.py`의 실제 채팅 provider 생성에 아래 옵션을 명시했다.

```python
DirectLlmSupervisorSelectionProvider(
    material,
    native_controls=True,
    code_coordination=True,
    positional_entity_refs=False,
)
```

네 함수 선택과 코드 조정 값 결정은 활성화하고 인물 참조 변경 B는 비활성으로 유지한다. provider 생성자 자체의 기본값, Supervisor 판단 지침·도구 description, 모델·thinking 설정, 검색 정책과 기존 호출·저장 계약은 변경하지 않는다. 적용 범위는 현재 로컬 브랜치의 실행 조립부이며 배포·CI·직접 USER CHECK 완료를 뜻하지 않는다.

기존 조립 검사는 실제 builder가 생성한 selector에서 LLM 전송 경계까지 실행하도록 보완했다. 합성 native 제어 응답을 전달하여 네 함수 선언, 필수 함수 호출, 조정 필드 제거, 기존 인물 ref 스키마, `selection_mode=native_control`, `argument_protocol=selection-args.v1.a1b0`를 확인한다. 외부 AI 호출은 사용하지 않는다.

- 변경 후 자동 검사: **254 passed (23.11초)**. 실제 runtime 조립, 인자 A/B 옵션, 제어 함수, native 도구, Supervisor, BOTH coordinator, 근거·CRG·저장 흐름을 포함한다. 합성 provider·임시 테스트 DB를 사용하는 자동 검사이며 실모델 사용자 검증이 아니다.
- 아키텍처 inventory·boundary: **PASS**, modules 1,087 / internal edges 4,090 / legacy exact edges 0. frontend 소스 변경·UI 검증은 없다.
- 기존 API·ORM·테스트 보존 검사: **PASS**, protected lineages 2,913 / 수집된 테스트 3,245 / 보존 항목 37. 수집된 테스트 수를 실행 통과 수에 합산하지 않는다.
- 새 실모델 호출: 0회. 기존 선택 평가 원장 356/356을 늘리지 않는다.
- 개발 서버 실행·실제 사용자 채팅: 이번 소스 적용과 구분하며 아직 확인하지 않았다.
- 원복: 채팅 조립부의 세 옵션을 false로 돌리거나 기존 인자 없는 생성자 호출을 사용한다. DB 원복은 필요하지 않다.
- 기존 P6 전체 채택 Gate: 과잉 BOTH 및 지연 추가 확인 상태를 유지한다. 로컬 적용 승인으로 평가 결과를 PASS로 바꾸지 않는다.

작업 전 파일 보존본과 이번 자동 검사 결과는 workspace `.task-output/chat-supervisor-na-activation-20260912-152835/`에 기록한다.
