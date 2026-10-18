# Chat 기억 검색 예산 확대와 기존 보호 로컬 검증

- 실행일: 2026-10-18, Asia/Seoul.
- 브랜치: `feat/preparation-output-language`.
- 시작 HEAD: `46f96508c2c983ac07e113b5d10701bdd9abaf04`, 시작 작업 트리 clean.
- 실행 계획: workspace `docs/plan/10-18 Chat 기억 검색 제한 시간 여유 확대와 기존 중단·검증 보호 유지 코드 구현 세부 계획.md`, I00–I23.
- 범위: 좁은 제품 변경, 관련 로컬 회귀, 문서, DCO 로컬 커밋. 기존 브랜치 변경을 보존한다.
- 환경: Windows, 고정 backend Python 3.13.12 / pytest 9.1.1 / SQLAlchemy 2.0.51. `uv run --frozen --offline`과 `ANGMOO_DENY_EXTERNAL_NETWORK=1`을 사용했다.
- 개인 DB·키·대화·관찰 기록을 회귀 자료에 복사하지 않았다. 합성 provider와 임시 SQLite를 사용한다.

## 변경과 보존 계약

Chat 소유 계약 모듈의 `CHAT_HYBRID_SEARCH_TIMEOUT_MS = 10_000`을 실제 Runtime
조립부가 `SOCIAL_HYBRID`에만 주입한다. 기존 Router가 이를 resolved envelope에
담고 기존 `HybridCanonicalService`가 실제 검색 포트의 deadline을 계산한다.
공통 Memory 엔진이나 테스트 helper의 기본값만 바꾸는 방식이 아니다.

| 항목 | 구현 결과 |
| --- | --- |
| 제품 기본 Chat `social_hybrid` 본 검색 | 4초 → 10초 |
| 공통 `RetrievalHardCaps()`·다른 Chat 모드 | 기본 4초 유지 |
| 실제 본 검색 예산 | `min(20초, 전체 요청 잔여 시간 - 15초, 호출자 caps)` 유지 |
| 본 검색 이후 currentness | 호출별 최대 4초, 전체 요청 마감으로 제한 |
| SNS 검색 | 기존 semaphore 대기 포함 15초 유지 |
| 전체 Chat 요청 | 기존 180초 유지 |
| 후보·row·hop·fanout·token·AI 호출 예산 | 기존 값 유지; 검색 자동 재시도 없음 |
| SQLite | 기존 DEFERRED 읽기·짧은 최종 쓰기 UoW 유지; busy timeout·writer retry 정책 변경 없음 |
| UI·한국어/영어 고정 텍스트·lockfile | 변경 없음 |

FTS·벡터 축과 후속 후보 검증·근거 구성은 하나의 절대 마감을 소비한다. 각 단계에
10초를 다시 주지 않는다. 기존 축 종료 여유 계산도 유지한다. 완료한 검색은 즉시
반환하며 10초를 채우는 sleep, 새 background 작업 또는 worker 증설을 추가하지 않았다.

## 검증 결과

관련 pytest **73개 통과, 실패·skip 0개**다. 전체 backend/frontend suite와
GitHub Actions는 실행하지 않았다. 한 차례 저장소 루트에서 실행한 명령은
`ModuleNotFoundError: app`으로 수집에 실패했다. 저장소의 backend 작업 디렉터리
계약에 맞춰 실행 위치를 수정한 뒤 아래 두 실행이 통과했다. 이를 제품 실패나
재시도로 숨긴 테스트 실패로 분류하지 않는다.

| 실행 묶음 | 결과 | 근거 |
| --- | --- | --- |
| Chat admission·budget·timeout 분류 | 51 passed, 11.79초 | `chat-junit-attempt2.xml`, `chat-tests-attempt2.txt` |
| Memory worker·snapshot·currentness 및 Chat 최종 저장 | 22 passed, 70.55초 | `protection-junit.xml`, `protection-tests.txt` |

원본 실행 기록은 workspace의 `.local-diagnostics/chat-search-budget-20261018/`에
보존했다. 로그는 제품 커밋에 포함하지 않는다. 이 실행 시간은 로컬 시험 묶음의
소요 시간이며 실사용 Chat 지연의 측정값이 아니다.

| 계획 항목 | 실제 확인 |
| --- | --- |
| V00–V01 | 기본 설정 및 모든 Chat mode의 실제 `build`를 실행했다. hybrid만 timeout 10,000ms, 나머지는 4,000ms이며 row/hop/fanout/token 값은 같다. Router → envelope → 실제 검색 포트에 10초 deadline이 도달하고 답변 저장이 완료됐다. |
| V02–V03 | 명시적 2초는 2초, 기존 4초는 4초, 요청 잔여 18초는 검색 3초, 큰 caps는 기존 20초 상한을 지킨다. 잔여 15초 이하는 검색·임베딩 포트를 호출하기 전에 기존 오류로 종료한다. |
| V04·V10 | 제어한 시계에서 5.5초 작업은 4초 제한에 실패하고 10초 제한에 성공했다. 25ms 작업은 예산을 채우지 않고 반환했다. 10.5초 작업은 timeout으로 분류됐고 검색은 한 번뿐이었다. production composition은 기존 선택·답변 provider 호출 2회를 유지하며 최종 저장까지 확인했다. |
| V05–V06 | 축 timeout의 cancel/join, 실제 SQLite 장기 SQL 중단, 조기 caller 취소 후 작업 소유·drain·연결 반환·재사용을 확인했다. 취소·권한 계열·BUSY 오류를 검색 timeout으로 재분류하지 않는다. |
| V07 | 대기열의 짧은 deadline이 소진되면 기다리던 reader는 호출되지 않고 Session도 열지 않았다. queue capacity·종료 후 admission 차단·drain을 확인했다. 축과 후속 resolve에 같은 절대 마감을 전달하는 제품 코드는 변경하지 않았다. |
| V08 | 실제 파일 SQLite에서 긴 DEFERRED 읽기 중 독립 쓰기와 event-loop timer가 진행됐다. 다음 읽기는 새 snapshot을 사용했다. 제한된 lock wait 뒤 연결 재사용도 확인했다. |
| V09 | currentness 포트에 별도 4초 또는 더 짧은 잔여 시간을 전달했다. 전달 ID 중복 제거와 같은 이전 결과 참조를 유지한다. Memory OFF·출처·후속 정정·삭제·관련 권한 변경은 차단하고 무관한 변경은 허용하는 기존 회귀를 통과했다. provider 대기 중 기억 삭제·원문 숨김·본문 변경 시 delta·답변 저장·Chat 기억 receipt가 남지 않는 실제 저장 회귀도 통과했다. |
| V11 | 제품 동작 변경은 Chat 정책 상수와 Runtime 주입 두 파일이다. 다른 예산·DB 정책·UI·라이브러리 변경 없이 아키텍처 설명과 생성 import 목록만 정합화한다. |

5.5초/25ms/10.5초 사례는 긴 sleep 없이 검증한 **제어된 시간 모형**이다.
실제 임베딩 서버가 포함된 검색을 그 시간 동안 실행했다는 뜻은 아니다. 실제 native
중단·취소·읽기/쓰기 공존은 별도의 짧은 제한과 임시 SQLite로 검증했다. 검색 단계
예산 전달, 최종 저장 회귀, 실제 AI 출력 품질을 서로 같은 검증으로 취급하지 않는다.

## 재현 명령

제품 저장소의 `backend` 디렉터리에서 실행한다. `--project backend`만으로
Python의 현재 작업 디렉터리가 변경되는 것은 아니므로 repo root에서 실행하지 않는다.

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
uv run --frozen --offline python -m pytest -q `
  tests/chat/test_hybrid_admission.py `
  tests/chat/test_hybrid_canonical_guards.py `
  tests/chat/test_recall_timeout_classification.py

uv run --frozen --offline python -m pytest -q `
  tests/memory/test_hybrid_recall.py::test_deadline_cancels_and_joins_both_axes `
  tests/memory/test_canonical_worker.py::test_deadline_native_interruption_heartbeat_cleanup_and_reuse `
  tests/memory/test_canonical_worker.py::test_caller_cancellation_keeps_running_future_owned_until_drain `
  tests/memory/test_canonical_worker.py::test_capacity_queued_work_has_no_session_and_stop_closes_admission `
  tests/memory/test_canonical_worker.py::test_exclusive_lock_obeys_remaining_budget_and_reuses_connection `
  tests/memory/test_canonical_worker_lifecycle.py `
  tests/memory/test_hybrid_read_snapshot.py `
  tests/memory/test_recall_delivery_currentness.py `
  tests/memory/test_canonical_resolution_diagnostics.py::test_queued_expired_read_has_unknown_execution_cost_and_does_not_open_session `
  tests/chat/test_recall_delivery_persistence.py
```

import 변경은 repo root에서 `scripts/ci/generate_architecture_inventory.py --write --check`로
실제 목록을 생성하고 `scripts/ci/check_architecture_boundaries.py`로 경계를 확인했다.
두 검사 모두 통과했다: modules 1,574 / internal edges 6,839 / external imports 4,626,
legacy exact exceptions 0. 허용 정책·기존 예외를 추가하지 않았다.

생성 목록에는 이번 Chat import 한 개 외에 시작 HEAD `46f96508`에 이미 커밋됐던
주제 재생성 진단 모듈과 import의 미반영분도 포함됐다. 제품 코드를 다시 수정한 것이
아니며 생성기가 현재 소스를 그대로 반영한 결과다. 수동으로 목록 일부를 숨기거나
기존 기능을 되돌리지 않았다. 로컬 경계 검사와 GitHub Actions 실행은 구분한다.

## 적용 상태와 남는 비용

이번 범위는 로컬 구현과 검증이다. Publish·PR·CI·main 병합은 수행하지 않는다.
실행 중인 Docker를 재빌드·재시작하거나 관찰 설정·자율활동·운영 데이터를 변경하지 않았다.
로컬 소스가 바뀐 사실은 기존 실행 이미지나 설치형 앱에 적용됐다는 의미가 아니다.

정상적인 4초 안의 검색을 느리게 만드는 대기 구문은 없으나, 느린 검색은 기존보다
명목상 최대 6초 더 수행될 수 있다. worker 점유와 읽기 snapshot 수명이 늘 수 있고,
실패 후 cleanup 시간까지 항상 정확히 10초 이내라는 보장도 아니다. 새 쓰기 잠금이나
추가 검색/AI 재시도를 만들지는 않았다. 시간 예산 확대는 기존 병목을 제거한 최적화와 다르다.

새 이미지를 적용한 뒤 실제 Chat의 검색 성공·처리 시간·저장·호출 수를 확인하는 것은
별도 **USER CHECK / 미측정**이다. 이번 시험만으로 실사용 timeout이 모두 해소됐거나
AI 답변 품질이 개선됐다고 판정하지 않는다. 필요 시 이 정책값만 4초로 되돌릴 수 있으며
DB·기억·인덱스 초기화나 데이터 롤백은 필요하지 않다.
