# 채팅 Supervisor 제어 함수 후보 F0~F7 로컬 검증

- 기록일: 2026-09-11
- 09-11 검증 상태(이력): **F0/F1 COMPLETE · F2 FORMAT GATE FAILED · F3/F4 HELD · F5 AUTOMATED PASS · F6 NOT ADOPTED · F7 RECORDED**
- 최신 후속(2026-09-12): [P0~P8 인자 분리 패치 검증](chat-supervisor-argument-validation.md). NA 개발 Gate 후 M0/NA 보류 96회 완료, NA 형식 48/48·선택 45/48. 전체 채택 Gate는 과잉 조회 기준·BOTH 지연 추가 확인 상태다. 이후 사용자 요청으로 로컬 채팅 composition에 NA를 적용했으며 B는 OFF, 서버 실행·USER CHECK는 별도다. 이 문서의 F2 실패는 당시 이력으로 유지한다.
- 계획: workspace `docs/plan/09-11 Gemini 3.1 Flash-Lite 고정 기반 도구 호출 형식·선택 정확도 개선 검토와 단계별 검증 계획.md`
- 기존 [R0~R9 검증](chat-supervisor-native-validation.md)의 실패 이력을 대체하지 않는 후속 비교다.

## 1. 실제 구현과 적용 경계

`DirectLlmSupervisorSelectionProvider(..., native_controls=True)`에만 네 함수 선언과 필수 native 호출 정책을 적용한다. 기본 생성자는 기존 혼합 출력 프로토콜을 유지한다. F0~F7 종료 시점에는 제품 composition을 활성화하지 않았고, 현재 로컬 composition은 위 후속 기록의 NA를 사용한다.

- CANONICAL·GRAPH는 기존 조회 ToolNode의 두 도구다. BOTH 도구는 추가하지 않았다.
- USE_CONTEXT·REQUEST_CLARIFICATION은 코드 준비 작업이다. 기존 resolver/Today guard 이후 실제 준비가 끝나야 제어 결과를 완료 처리한다. 조회 근거로 합치지 않는다.
- 함수 요청 전체의 이름·인자·조합을 검증한다. 빈 호출, 일반 텍스트, 제어·조회 혼합, 중복 제어는 거부한다.
- 권한·범위·예산·취소·근거 고정·CRG 책임을 유지한다. 결과의 의미적 품질을 평가하는 AI 단계는 추가하지 않았다.
- provider의 `require_tool_call`은 요청별 계약이다. Gemini는 해당 요청만 ANY로 매핑하고 기존 선택적 도구는 VALIDATED를 유지한다. 일반 텍스트·JSON 소비자와 자동 함수 실행 비활성화는 유지한다.

## 2. 비교 조건과 결과

기존 32문항 fixture를 그대로 사용했다. 개발 8문항×3회×M0/M1=48회이며 보류 24문항은 실행하지 않았다. 모델은 `gemini-3.1-flash-lite`, 요청 thinking은 `high`, 출력 상한 3072, provider timeout 30초, 요청 deadline 95초다. 동시성은 2이며 저장된 모델 설정은 변경하지 않았다.

M0는 F0에서 보존한 기존 B2 adapter와 혼합 출력이다. M1은 동일한 공통 의미 지침과 CANONICAL/GRAPH description에 네 함수 반환 프로토콜을 적용한 후보다. M2의 선택 지침은 적용하지 않았다. 이번 결과는 함수 선언 수·제어 표현·필수 호출 정책을 함께 바꾼 후보의 결과이며 각각의 효과를 분리해서 입증하지 않는다.

| 지표 | M0 기존 혼합 출력 | M1 네 함수 표현 |
| --- | ---: | ---: |
| 최초 계약 통과 | 20/24 (83.3%) | 23/24 (95.8%) |
| 재시도 후 유효 결과 | 22/24 (91.7%) | 23/24 (95.8%) |
| 기대 effective 선택 | 18/24 (75.0%) | 21/24 (87.5%) |
| 재시도한 요청 | 4 | 1 |
| physical provider 호출 | 28 | 25 |
| 요청별 provider 시간 합 p95 | 16,900ms | 15,030ms |
| 입력 토큰 합 | 74,338 | 107,864 |

F2 진입 기준은 M1 최초 계약 통과 23/24 이상과 재시도 후 유효 결과 24/24다. 첫 기준만 통과했고 두 번째에 미달했다. **F3·F4 진행 및 제품 채택을 보류한다.** 표본 24회는 일반적인 성공 확률이나 다른 모델의 개선을 보장하지 않는다. 입력 토큰이 증가했으므로 호출 수 감소만으로 비용 감소를 주장하지 않는다. p95 역시 개발 소표본 관찰이며 F4 지연 Gate 통과로 취급하지 않는다.

이전 B2의 20/24와 이번 M0 18/24는 다른 실행이다. 과거 수치와 새 M1만 직접 비교하지 않고 동시대 M0를 기준으로 삼는다.

## 3. 실패와 해석

- case-01 과거 기록 확인: M0/M1 모두 CANONICAL 3/3. 이전 형식 오류가 이번 M0에서 재현되지 않았으므로 이 사례만으로 해결을 확정하지 않는다.
- case-03 GRAPH 단독: M0는 불필요한 BOTH 3/3, M1은 BOTH 2/3·GRAPH 1/3. 이번 오류는 모델의 최초 선택이며 코드 guard의 추가 조회가 아니다.
- case-04 실제 BOTH: M1은 정상 BOTH 2/3, 계약 실패 1/3. 실패한 첫 응답은 native 두 호출을 반환했지만 `both_coordination_missing`; 허용된 repair 1회 후 `entity_ref_invalid`로 종료했다. 일반 텍스트로 함수를 대신한 실패는 아니며, native 표현 통일이 인자 유효성을 보장하지 않음을 보여준다.
- M1의 다른 개발 질문은 기대 선택 3/3이다. 현재 맥락과 확인 질문 제어는 정상 반환했지만 보류 질문에서의 일반화는 검증하지 않았다.

오류를 성공으로 바꾸는 fallback, BOTH 조정 값 추측, 실제 인물 ID에 대한 임의 보정은 추가하지 않았다. 다음 후보에서는 두 호출의 조정 계약과 entity ref 제약을 별도로 점검해야 한다. 보류 질문을 열기 전에 수정 후보의 개발 형식 Gate부터 다시 통과해야 한다. 기존 실행의 결과나 정답을 바꾸지 않는다.

## 4. 자동 검사와 미실행 범위

- 최초 통합 검사 90 passed. 이후 실험 옵션의 기본 비활성화와 adapter 연결을 포함한 검사 92 passed.
- 채팅 전체·provider·아키텍처 회귀: 412 passed, 6 skipped, 4 warnings. 6 skipped는 별도 활성화가 필요한 진단 성능 벤치마크다. 기존 라이브러리 deprecation 경고는 유지됐다.
- 실제 LangGraph 제어 분기에서 준비→근거 고정→CRG 1회, 조회 미실행을 검사했다. 기존 단일/병렬/의존 조회, 부분 실패·취소·저장 관련 테스트도 회귀 범위에 포함한다.
- 전체 보존 검사 PASS: 보호 대상 계보 2,913개, 현재 수집 3,110개, 보존 항목 37개. 3,110개는 테스트 수집 수이며 전체 테스트 실행 통과 수가 아니다.
- 이 평가는 합성 질문의 최초 선택만 실행했다. 실제 DB 기억 검색, CRG 실모델 답변, 사용자 채팅, 설치 앱, CI, release를 검증한 결과가 아니다.

## 5. 예산과 재현 자료

최초 선택 승인 상한 312회 중 기존 사용·중단 예약 140회에 이번 48회를 더해 **188회 사용·예약, 124회 잔여**다. 이번 physical 호출은 53회이며 최초 선택 예산과 별도로 집계한다. 기존 중단 예약 5회는 반환하지 않았다. 후속 계획의 원래 전체 배치를 무조건 다시 실행할 수 있는 예산은 아니다.

workspace `.task-output/chat-supervisor-controls-20260911/`:

- `baseline.json`, `baseline/app/`, `plan-before.md`: F0 기준 및 기존 사용자 변경 보존 자료.
- `source.tar`, `f2-evaluator-frozen.py`: 실제 Docker 격리 평가에 사용한 후보 소스와 실행 스크립트. 이후 기본 비활성화 변경과 구분한다.
- `f2-development/metadata.json`: fixture·source·prompt·schema hash, 모델·SDK·예산 조건.
- `f2-development/results.jsonl`, `summary.json`, `f2-analysis.json`: 실패를 포함한 전체 결과와 집계.
- `global-budget.json`: 누적 최초 선택 사용 원장. 과거 완료 필드는 이력이며 이번 총사용은 `started=188`이다.
- `f1-tests-retest.txt`, `f5-regression.txt`, `f5-opt-in-tests.txt`, `f5-preservation.txt`: 로컬 자동 검사 출력.

Docker의 `/tmp/chat-supervisor-controls-evaluation/` 격리 소스를 사용했다. 운영 app 디렉터리 교체, 서버 재시작, 사용자 설정 변경, 채팅·기억 쓰기는 수행하지 않았다. 원래 R8의 Docker 채택·직접 USER CHECK는 계속 보류한다.

## 6. 종료 기록

F5 관련 자동 검사와 전체 보존 검사를 완료했다. F0 hash 기준 기존 파일 중 이 작업 대상 8개만 변경됐고 삭제된 파일은 없다. 신규 후보 테스트·평가 스크립트·검증 문서를 추가했다. 기본 혼합 출력, 기존 사용자 변경, 원래 R7/R8 실패·보류 이력을 보존했다. F3/F4는 미수행이며, 실패 Gate를 통과한 것으로 바꾸거나 새 후보를 제품 기본값으로 채택하지 않았다.
