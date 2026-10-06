# World UI·사용자 반응·SNS 출력 통합 핵심 재검토와 수정 검증

- 요청: 10-05 통합 계획의 핵심을 약 1시간 재검토하고 필요한 부분 수정.
- 시작: 2026-10-05 13:25:31 KST / 04:25:31 UTC.
- 상태: 재현한 제품 문제 6건과 검사 대역 문제 1건 수정, 핵심 backend·Next/static 검사와 최종 전체 소스·계약·테스트 보존 검사 PASS.
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `feat/0.1.0-release-readiness`.
- 시작 HEAD: `b118ef812bc42575f8d1aa57c1441711e7e5ff61`, 작업 폴더 clean.
- backend 수정: `bef447ec1d948afab79454568ede1fdd825240a1`.
- 탐색·검사 대역 수정: `56c80b5e71359302711dc091ce2ec014192bfcf7`.
- 브라우저/native 소유 함수 분리: `77a70d1e0db0270949d936456c5faf3634e4c057`.
- 세 코드 커밋에 sign-off를 추가했다. 원격 push·PR·Hosted CI·main 병합은 수행하지 않았다.

## 1. 재검토 범위와 판정

계획 UI-C01–22, OUT-C01–36, INT-C01–08의 핵심 경로를 실제 코드와 대조했다. 선택한 답글/하위 thread, 사용자 좋아요의 원본·audit event 원자 저장과 재조회, World 대화 제한 해제, 전체 이름 검증 후 보조 출력 정규화, 신규 combined 실행·모델별 전체 입력 계수·선택적 입력 생략·영속 호출 예약·전송 직전 fence를 중심으로 확인했다.

중심 구조와 업무 소유권은 유지할 수 있다. 다만 기존 검사의 PASS만으로 전송 경계와 기록의 정확성까지 충족되지는 않았다. 아래 6개 제품 문제를 재현하여 수정했다. 전체 97개 검사 ID와 모든 source를 처음부터 다시 실행한 재구현 검토가 아니라, 약 1시간 범위의 핵심·경계 동작 재검토다. 기존 전체 backend 기록을 이번 재검토의 전체-suite PASS로 바꾸지 않는다.

## 2. 확인한 제품 문제와 수정

| ID | 실제 문제·증거 | 수정과 검증 |
| --- | --- | --- |
| R01 | 모델 입력 한도를 맞추기 위해 optional memory를 생략한 뒤에도 receipt/manifest의 memory ref가 생략 전 상태였고, 한 물리 요청에 preliminary/admitted receipt가 두 번 전달됐다. JSON attempt hash도 실제 교체 입력과 달랐다. 입력 초과로 전송하지 않아도 receipt가 남았다. | 최종 fence를 통과한 실제 `ProviderRequest`의 submission callback에서 receipt/manifest를 한 번 기록한다. refs/omissions를 실제 입력에서 다시 얻고, JSON 초기·feedback 각각의 hash도 실제 system+user로 계산한다. observer OFF/None 및 기존 start callback을 보존한다. 새로운 회귀 3개. |
| R02 | shared transport의 503 재시도가 같은 JSON attempt 안에서 실행될 때 normal/recovery 영속 예약이 최초 1회만 증가했다. normal 예약 9개 후 10번째 요청의 overload 재전송이 허용됐고, JSON 복구의 overload에서도 recovery 예약이 부족했다. 전체 tracker 상한이 무제한으로 사라진다는 판정은 아니다. | 모든 admitted 물리 제출에 별도 durable key를 예약한다. token-count cache hit와 생성 요청을 구분한다. normal 10 / recovery 5 / total 15 정책과 resume의 최초 key 보호를 유지하고, 한도 소진 시 추가 제출을 차단한다. 새로운 회귀 3개. |
| R03 | admission 예약 후 final scope guard에서 중단되면 adapter 전송 0회인데도 delivery가 dispatched/uncertain으로 바뀌었다. | delivery 전송 표시와 receipt를 공통 transport의 마지막 guard·call allowance 확인 이후 synchronous submission 경계로 이동했다. 취소된 경우 dispatch/receipt/adapter/tracker call이 모두 0이며 예약은 보수적으로 유지한다. 새로운 회귀 1개. |
| R04 | httpx 10초 timeout은 개별 chunk 대기 제한이다. 작은 chunk가 계속 도착하면 models 조회/countTokens 전체 요청은 10초를 넘길 수 있었다. | 같은 10초 정책을 `asyncio.timeout`으로 전체 요청에도 적용했다. models/count 각각 physical attempt 1회, 응답 1 MiB 상한·redirect 금지·typed 오류·stream close를 유지한다. 느린 합성 stream 회귀 2개. |
| R05 | 관찰기 coverage는 실제 공백 `>150초`를 불완전으로 판정하지만 보고 수치는 정수 반올림했다. 150.1/150.49초가 `[150]`으로 기록되어 기존 가속 관찰 검사가 간헐적으로 실패했다. | 판정에 사용한 실제 초 단위 수치를 보고한다. 임계값·coverage 판정·기존 assertion은 변경하지 않았다. 150.0/150.1/150.49초의 결정적 회귀 3개. |
| R06 | static 브라우저 프로필의 query-only 탭 변경이 전체 문서를 다시 열어, 늦게 완료되는 좋아요 HTTP 응답이 끊겼다. 새 탭 조회가 저장 전에 끝나면 그 좋아요가 바로 갱신되지 않았다. | 공통 navigation 소유자에서 같은 origin/path/hash의 query 변경만 기존 History API·static route subscription으로 처리한다. native validation과 다른 경로의 이동은 유지한다. 1.5초 지연 좋아요·document sentinel·조회/새로고침 회귀를 Next/static에서 확인했다. |

변경 소유 파일은 `backend/app/integrations/direct_llm.py`, `gemini_input_budget.py`, `backend/app/runtime/autonomous_activity/provider.py`, `combined_provider.py`, `backend/app/runtime/diagnostics/sns_observation_report.py`, `frontend/src/hooks/use-runtime-navigation.ts`다. backend ARCHITECTURE와 frontend ARCHITECTURE/DESIGN의 기존 소유자에서 수정했다. 새로운 adapter나 feature 간 우회 import, quota 완화, legacy 정책 변경, DTO/ORM/migration 변경은 없다.

## 3. 검사 대역의 별도 문제 V01

Next 첫 실행에서 51 PASS/2 FAIL, static 첫 실행에서 51 PASS/2 FAIL을 보존했다. Chat의 NDJSON `completed` 다음에 실제 화면이 조회하는 `/requests/synthetic-request`를 대역이 제공하지 않아 404로 넘어갔다. 짧게 보이는 delta 문구만으로는 검사 타이밍에 따라 통과할 수 있었다. 이 문제는 제품 API의 실제 생성 실패를 입증한 것이 아니다.

`browser-tests/world-social-chat-fixture.ts`에 정식 request 상태 조회와 `committed`·assistant message·마지막 sequence를 연결했다. `browser-tests/world-social-core-review.spec.ts`는 한글/영어 전환 후 사진 포함 메시지가 terminal 상태에 도달하고, 새로고침해도 저장된 답변을 유지하며, 추가 전송이 없는지 확인한다. 기존 assertion과 성공 기대값을 낮추지 않았다.

## 4. 현재 확인된 검사 결과

| 검사 | 결과 | 로컬 증거 |
| --- | --- | --- |
| 수정 전 기존 핵심 backend | 130 PASS | `core-existing.xml` |
| R01/R02/R03 재현 | 합계 7 FAIL | `receipt-before.xml`, `physical-before.xml` |
| R04 재현 | 2 FAIL | `deadline-before.xml` |
| R05 경계 재현 | 1 PASS / 2 FAIL | `gap-before.xml` |
| 수정 후 핵심 backend | 224 PASS | `core-all-final.xml` |
| 확대한 원본·권한·combined/이름 복구 | 33 PASS | `ownership-combined.xml` |
| 기존 탐색·sidecar 보안 계약 | 최초 47 PASS / 1 FAIL → 48 PASS | `navigation-security.xml`, `navigation-security-final.xml` |
| Next 화면 | 최초 51 PASS / 2 FAIL → 최종 코드 56 PASS | `next-results.json`, `next-final-results.json` |
| static 화면 | 최초 51 PASS / 2 FAIL → 최종 코드 56 PASS | `static-results.json`, `static-final-results.json` |
| 실제 FastAPI/격리 SQLite와 브라우저 | 1 PASS | `backend-browser-results.json` |
| backend architecture | PASS — modules 1375 / edges 5603 / legacy exact edges 0 | `check_architecture_boundaries.py` |
| frontend architecture·design | PASS — features 14, raw colors 1229 / files 36 / surfaces 18 / route gaps 0 / screenshots 24 | 두 공식 검사기 |
| frontend lint·typecheck | PASS | `pnpm lint`, `pnpm typecheck`의 exit 0 |
| Next production·static build | PASS | `pnpm build`, `pnpm build:static`의 exit 0 |
| backend source/contracts/nodes 보존 | 최종 PASS — inventory 37 / protected lineages 5,245 / current collection 5,245 | `backend-preservation-final.log`, 최종 source HEAD `77a70d1e` |
| frontend source/assertions/fixtures/assets/locks 보존 | PASS — 324 source files | `frontend-preservation-final.log`, 최종 source HEAD `77a70d1e` |

모든 XML/브라우저 결과/trace/log는 `artifacts/world-ui-sns-output-core-review-20261005/`의 Git 제외 로컬 증거다. clone에 포함되는 근거는 본 문서와 실제 커밋·증거 기록이다. 초기 실패와 중간 검사 실패를 삭제하지 않았다. 중간 `core-after.xml`의 217 PASS/1 FAIL은 새 receipt 기록의 observer None 호환 누락을 발견하여 보완한 기록이며, `core-final.xml`의 218 PASS/1 FAIL은 R05 정수 반올림 문제였다. 잘못된 pytest cwd로 발생한 수집 오류는 `post-fix-guard.xml`에 보존하고 backend cwd로 바로잡아 최종 검사를 수행했다.

305개 backend 사례는 서로 다른 테스트 파일의 세 실행 224+33+48개다. 새 결정적 backend 회귀 12개가 224개에 포함된다. UI는 Next/static별 56개씩이며 서로 다른 112개 제품 기능이라는 뜻이 아니다. 새 UI 회귀 3개는 각 실행의 56개에 포함된다. 실제 HTTP·SQLite 브라우저 1개는 API 대역 화면 112개와 구분한다.

기존 탐색 계약 검사의 최초 1 FAIL은 Tauri early return 뒤의 browser query 코드를 문자열로 native 범위에 함께 넣은 소스 추출 때문이었다. browser query 처리를 별도 함수로 분리하여 환경 소유권을 명시했다. 기존 검사·assertion은 그대로 유지했고 48개 계약이 모두 통과했다. 실제 native 실행 결함을 재현한 것으로 기록하지 않는다. 이 마지막 분리 커밋 뒤 Next/static build와 각각 56개 화면을 다시 실행하여 통과했다. 한글 선택 답글 화면과 영어 Chat의 최종 436px 캡처도 직접 읽어 위치·입력·반응·메뉴를 확인했다.

최초 backend 보존 실행은 마지막 frontend 증거 기록이 추가되기 전에 시작했다. 실행 중 기록을 append하여 최초 검증 manifest와 SNS 소유자 재검증에서 다시 읽은 manifest가 달라졌다. `SNS retained change records differ from verified manifest`가 보호 계보 검증을 중단했고, 이어 나온 protected lineages=0·5,245개 도입 증거 없음은 그 중단의 연쇄 보고다. 테스트 코드가 물리적으로 사라졌다는 판정이나 5,245개 동작 FAIL이 아니다. 이 실행 순서 오류의 로그는 보존한다. 세 소스 커밋과 두 최초 도입 capture·세 변경 기록이 모두 고정된 이후, 수정하지 않은 공식 `--contracts --nodes` 전체 검사를 별도 `backend-preservation-final.log`에 다시 실행하여 통과했다. 보호·현재 수집 node가 모두 5,245개이며 누락 0, inventory 37 PASS다. 이 수집은 5,245개 전체 동작 테스트 실행이라는 뜻이 아니다.

## 5. 보존·운영 경계와 후속 검증

- 기존 frozen source/backend/frontend checkpoints와 identity inventory를 재생성하지 않는다. 과거 승인/추가 기록은 그대로 두고 실제 구현 커밋과 부모의 blob/AST/text digest만 append한다.
- `AR-WORLD-UI-SNS-CORE-REVIEW-20261005`: backend source blob 9개, 정의 변경 9개, 기존 assertion/API/ORM 변경 0. 공식 append capture로 신규 regression 파일 4개·node 12개의 최초 도입을 연결했다.
- `AR-WORLD-UI-SNS-CORE-UI-REVIEW-20261005`: source blob 3개, frontend/fixture의 정확한 text 변경 2개. 기존 assertion 변경 0. 공식 append capture로 신규 browser regression 파일 1개의 최초 도입을 연결했다. 두 capture의 신규 source 합계는 5개, backend node 합계는 12개다.
- `AR-WORLD-UI-SNS-CORE-NAV-REVIEW-20261005`: source blob 1개, browser/native 함수 분리에 따른 hook의 정확한 text 변경 1개. 기존 assertion·API·스키마 변경 0. 신규 파일/node가 없는 커밋이므로 별도 최초 도입 capture는 필요하지 않다.
- 보존 검사기의 검증 조건은 변경하지 않는다. 기존 공식 검사기를 실행하는 로컬 helper는 순수 AST memo를 주기적으로 비워 같은 Git/source에서 다시 계산하게 할 뿐, checker를 대체하거나 판정 조건을 줄이지 않는다.
- 시작 시 Docker 실행 컨테이너와 검사 포트 listener가 없었다. 작업은 synthetic credential/fake provider·token counter/임시 DB/합성 이미지/loopback preview에서 수행했다. 기존 관찰·운영·설치 데이터와 API 키를 읽거나 쓰지 않았다.
- 운영 Docker와 Windows 설치판 적용, 실제 Tauri 실행, 직접 USER CHECK, 실제 Gemini 계수·한도 일치와 AI 품질/시간/비용 F-AI01–05는 이번에 NOT_RUN이다. 한글/영어 browser·fake 생성 성공을 실제 모델 품질 검증으로 부르지 않는다.
- 원격 push·PR·Hosted CI workflow·main 병합·rebase·과거 commit 수정·`--no-verify`는 0회다.

## 6. 최종 마무리 기록

- 핵심 소스 검토와 제품 수정·동작 검사는 요청한 약 1시간 범위에서 진행했다. 증거 추가 중 시작한 보존 검사를 고정된 상태에서 재실행하여 전체 마무리에 약 85분이 걸렸다. 최종 보존 결과를 집계한 시각은 2026-10-05 14:49:45 KST / 05:49:45 UTC, 시작 이후 84.23분이다.
- 최종 검사 대상 제품 소스 HEAD는 `77a70d1e0db0270949d936456c5faf3634e4c057`다. 초기 실패를 포함한 결과·최종 PASS·commit·보존 경계는 같은 이름의 [기계 판독 JSON](world-ui-sns-output-core-review-20261005.json)에 연결한다.
- 기존 frozen source/backend/frontend checkpoint와 identity inventory의 실제 Git diff는 0이다. 기존 변경/도입 증거 record prefix도 동일하며 새 변경 기록 3개와 최초 도입 기록 2개만 append했다. 기존 단언·API·ORM 변경 0을 다시 확인했다.
- Next/static 및 실제 HTTP·SQLite 검사용 서버는 종료됐다. `preview-shutdown.json`의 3330·3331·3332·3340·3342 포트 listener는 0이다. 로컬 원자료·합성 DB·스크린샷은 보존한다.
- 이 검증 문서·JSON과 두 append 증거 manifest를 별도 sign-off 로컬 증거 커밋에 포함한다. 원격 push·PR·Hosted CI·main 변경과 사용자 운영·설치 데이터 작업은 실행하지 않았다.
