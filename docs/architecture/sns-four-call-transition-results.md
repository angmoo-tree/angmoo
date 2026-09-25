# SNS 4회 호출 구조 구현·검증과 기본 전환 보류 기록

작성일: 2026-09-26. 사용자 계획의 IC-0~IC-13 실행 기록이다. **새 계약 버전 2를 구현했지만 신규 실행 기본값은 1로 유지한다.** 로컬 코드·자동 회귀와 실제 AI 구성요소 비교를 구분하며, 신규 기본 전환·설치·운영 품질 완료를 선언하지 않는다.

## 1. 작업 기준과 범위

- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `fix/sns-v2-planner-output-contract`.
- 기준 SHA: `f9e328fff2a42b34e254b4cba680dcdbcea71103`. 시작 작업 트리는 clean이었다.
- 실행 계획: workspace `docs/plan/09-25 SNS 4회 호출 구조 전환과 기능·출력 보존 코드 구현 세부 계획.md`.
- 허용 범위: 현 로컬 브랜치 구현·로컬 검사·로컬 커밋. push/PR/CI workflow/act/main merge/release/설치 적용은 수행하지 않았다.
- backend `ARCHITECTURE.md`, frontend `AGENTS.md`·`ARCHITECTURE.md`·`DESIGN.md`와 연결된 보존/디자인 지침을 확인했다. UI 변경의 provenance는 LOCAL이고 Next/static이 같은 feature 컴포넌트를 사용한다.
- 사용자 World에 평가 게시글·관계·기억을 쓰지 않았다. 기존 관찰 세션, 실행 중인 제품 컨테이너, Windows 설치 앱을 변경하지 않았다.
- 09-23 현재 구조 가이드와 09-25 4회 호출 구조 제안 원본은 유지했다.

## 2. 구현한 실행 계약

| 계약 | 현재 동작 |
| --- | --- |
| engine | `personalized_graph_v2` 유지. `current` 엔진은 별도 기존 계약 유지 |
| 지원 계약 | `contract_version=1,2`. 모르는 버전은 명시적 실패 |
| 신규 기본값 | **1 유지**. 기존 run은 저장된 버전 그대로 재개 |
| 버전 1 순서 | Inbox → Routine → Feed, 기존 노드 이름·분리 생성 유지 |
| 버전 2 순서 | 후보 준비 → Inbox·Feed 통합 선택 → Inbox 판단·작성 → Feed 판단·작성 → Routine 계획·작성 |
| 입력 갱신 | 선택은 시작 맥락 고정. Feed 판단은 Inbox 뒤 원본/관계/허용 행동을 다시 확인. Routine 준비·기억 조회는 Feed 뒤 갱신된 맥락 사용 |
| 정상 요청 수 | 두 선택 필요 + 세 경로 작성일 때 4회. 0/1 후보·무행동·Routine 없음은 더 적을 수 있음 |
| 큰 입력 | 선택 `split` 또는 경로 생성 `split`을 요청 전 checkpoint에 고정. 새 실행 순서는 그대로 유지 |
| 출력 예산 | 통합 생성 8,192, 허용 잘림 복구 16,384. 첫 실제 검증 모델은 Gemini 3.1 Flash-Lite 한 가지 |
| 복구 | 유효 결정은 보존하고 초안만 잘못되면 기존 Writer만 복구. 깨진 전체 JSON에서 결정을 임의 추출하지 않음 |
| 예산 | 구간 최대 15 요청, 기존 정상 분리 최대 10/복구 5. 복구 reservation은 DB에 먼저 기록하여 재개로 복구 기회가 되살아나지 않음 |
| 기본 전환/복귀 | 향후 기준을 충족할 때 `activity_engines.CONTRACT_VERSION`을 2로 변경. 복귀는 신규 기본값을 1로 되돌림. 진행 중 run의 버전·checkpoint는 변경하지 않음 |

모드 판정은 현재 보수적 문자 크기 기준이다. 선택 요청 56,000자 초과, 생성 입력 40,000자 초과를 분리 후보로 삼고 실제 전송에는 기존 64,000자 제한을 그대로 적용한다. 모든 provider/model 조합의 한계나 장문 품질을 검증했다는 뜻은 아니다. 이 범위도 기본 전환 전에 확인해야 한다.

## 3. 코드 소유 위치와 출력의 후속 사용

| 코드 | 책임 |
| --- | --- |
| [generation_contracts.py](../../backend/app/runtime/autonomous_activity/generation_contracts.py) | decision/draft 외곽, 독립 검증, supplied target ID → 코드 소유 task ID 변환, Routine 초안 검증 |
| [combined_provider.py](../../backend/app/runtime/autonomous_activity/combined_provider.py) | 기존 transport/Planner 입력을 통합 요청에 연결, JSON 재시도와 Writer 복구 예약 |
| [combined_selection.py](../../backend/app/runtime/autonomous_activity/combined_selection.py) | 순차 DB 후보 준비, 0/1 bypass, lane별 독립 선택 검증, 같은 시작 맥락의 통합/분리 선택 |
| [combined_lanes.py](../../backend/app/runtime/autonomous_activity/combined_lanes.py) | 기존 판단·검증·게시·정산 포트 재사용, 초안 복구, Feed 갱신·전달 재조정 |
| [graph.py](../../backend/app/runtime/autonomous_activity/graph.py), [execution.py](../../backend/app/runtime/autonomous_activity/execution.py) | 버전별 그래프, guard, 자식 checkpoint, 경로 실패 격리, 결과 메타데이터 병합 |
| [world_feed.py](../../backend/app/domains/social/service/world_feed.py), [feed_delivery.py](../../backend/app/domains/social/service/feed_delivery.py) | 같은 claim 소유자만 갱신, 무효 대상 종료 요약, 전달 증거 보존 |
| [inputs.py](../../backend/app/runtime/autonomous_activity/inputs.py), [provider.py](../../backend/app/runtime/autonomous_activity/provider.py) | 최신 12건 선택, 분량 초과 시 오래된 기록부터 제외, 기존 Writer 검증 공유 |
| [activity_engines.py](../../backend/app/domains/world_characters/service/activity_engines.py) | 기본값/지원 버전 소유, 기존 run의 버전 고정 |
| [activity_status.py](../../backend/app/domains/world_characters/service/activity_status.py), diagnostics, frontend activity panel | 버전·실행 순서·새 노드·복구 표시. 원문 대신 구조적 진단 정보 기록 |

핵심 후속 소비는 통합 호출 안에 새로 구현하지 않고 기존 경계로 반환한다.

- Social의 `decisions`, `brief`, intent/purpose, proposal/response, state refs와 relationship metrics는 기존 `parse_action`과 실행·정산 경로를 통과한다. comment 대상 집합과 초안 대상 집합이 정확히 같아야 한다.
- LLM은 task ID를 만들지 않는다. 검증된 결정으로 기존 assignment를 만든 뒤 초안을 연결한다. Writer 전용 복구도 그 assignment와 brief를 사용한다.
- Routine의 plan/beat identity/연속성·사건 집합과 draft의 title/body/topic_signature/novelty_basis/thought를 기존 validator/publisher에 공급한다. 기존 result snapshot·다음 장면·상태·기억의 소비 계약을 유지한다.
- 하이브리드 기억은 선택 뒤 기존 selected recall, 원문·thought·정정 재검증을 사용한다. 통합 선택 단계에 임의의 기억 해석을 추가하지 않았다.
- 관계는 기존 방향별 SQLite 원본·영수증·outbox와 LadybugDB projection/fallback 경로를 사용한다. 통합 LLM 출력 자체를 그래프 DB에 직접 쓰지 않는다.
- 정산과 공개 실행의 실패 경계를 유지한다. 유효한 읽기 판단은 Writer 실패와 구분하고, Routine 공통 상태는 기존 성공 게시/재사용 조건을 따른다.

이 표는 코드 연결의 보존 설명이다. 모든 소비 경로를 하나의 실제 AI E2E 실행에서 측정했다는 판정은 아니다.

## 4. Feed 조기 준비와 중단 처리

버전 2에서는 Feed 후보 점유와 `ActivityGraphRun.result.feed_preparation` 복원 자료를 같은 DB 트랜잭션으로 저장한다. parent checkpoint 전에 프로세스가 중단돼도 동일 후보/claim 자료를 읽으며 후보를 다시 검색하지 않는다. 버전 1의 기존 준비 commit 경계는 유지한다.

전달 사실은 기존 `RecommendationDelivery`에 남기고, 버전 2의 전달된 미정산 행은 일반 retention에서 제외한다. Feed 종료 또는 다음 Feed 준비 진입에서 기존 `observe_source`를 통해 정산한다. 기본값을 1로 복귀해도 공통 Feed 진입에서 이전 버전 2의 미정산 전달을 처리한다. 성공은 기존 idempotent receipt로 보존하고, 삭제·숨김 등 `SocialObservationError`는 `not_applied`와 사유로 저장한다. DB/예상치 못한 실패는 전파하여 재시도 가능 상태를 보존한다. prepared/uncertain을 delivered로 추정하지 않는다.

선택한 글의 무효화는 같은 활동에서 재선택하지 않는다. Feed 결과에 선택 ID를 보존하고 cycle summary에도 종료 사유를 기록하며 Routine을 계속한다. 아직 전달하지 않은 claim을 관찰 성공으로 바꾸지 않으며 다른 실행의 claim을 갱신/정산하지 않는다. 전체 scope/실행권 상실·자율활동 OFF·DirectLlmDeferred는 기존 전체 중단 규칙을 따른다. 미정산 전달의 trace를 갱신할 때 원래 전달 시각을 보존하여, 오래된 전달을 최근 전달로 바꾸지 않는다.

## 5. 단계별 판정

| 단계 | 수행 내용 | 판정 |
| --- | --- | --- |
| IC-0 | 브랜치·HEAD·원본 문서·지침·기존 포트/소비자 확인 | 완료 |
| IC-1 | 최신 기록 보존, 실제 입력 잘림 경계 테스트 | 구현·회귀 완료 |
| IC-2 | 통합 외곽·정규 출력 변환·분리 검증·제한 복구 | 구현·회귀 완료. 실제 모델 검증은 한 모델/정상 크기 표본에 한정 |
| IC-3 | 두 계약 dispatch, 기본값/재개/복귀 고정 | 구현·회귀 완료, 기본값 1 |
| IC-4 | 통합 선택·우회 없는 후보 검증·Feed claim/전달/복원 | 구현·관련 회귀 완료 |
| IC-5 | Routine 계획·작성 통합과 기존 publisher 재사용 | 구현·관련 회귀 완료 |
| IC-6 | Feed 판단·작성, 무효 대상 종료 | 구현·관련 회귀 완료 |
| IC-7 | Inbox 판단·작성, 기존 제안/알림 경계 재사용 | 구현·관련 회귀 완료 |
| IC-8 | Inbox → Feed → Routine 부모/자식 그래프와 갱신 | 구현·중간 재개 회귀 완료 |
| IC-9 | observer·status·Next/static 표시 | 구현·로컬 빌드/브라우저 확인 완료 |
| IC-10 | 구/새 실제 어댑터, 게시/정산 재개, 기억/관계/Routine 관련 회귀 | 아래 명시한 자동 회귀 범위 확인. 모든 fault 지점×모든 후속 소비 조합을 망라한 E2E PASS는 아님 |
| IC-11 | 관련·전체 검사, architecture, frontend, 보존 검사 | 검사 수행. 기존 설치 업그레이드 검사 19건과 과거 refactor 보존 검사 불통과를 그대로 기록. 전체 PASS 아님 |
| IC-12 | 8개 합성 사례 비교 + 문제 2개 재확인 | 수행, **기본 전환 보류** |
| IC-13 | 결과·한계·다음 조건 기록과 로컬 커밋 | 최종 SHA는 workspace 결과 문서에 기록 |

## 6. 로컬 자동 검증

검사는 모두 로컬 명령이다. 경로가 `scripts/ci/`인 검증 스크립트를 로컬에서 실행한 것은 원격 CI workflow 실행이 아니다. 중복 실행한 테스트 수를 합산하지 않는다.

| 검증 | 결과 |
| --- | --- |
| 변경 전 집중 기준 | 46 passed |
| 최신 기록 경계 | 수정 전 4 failed/3 passed로 재현, 수정 후 입력+provider 15 passed |
| 넓은 관련 회귀: runtime 전체, activity_state, Feed 재점유/트랜잭션/정규 실행, relationships, routine_posts | 421 passed, 2 skipped, 578.47초. 후속 변경은 아래 집중 회귀로 확인 |
| 마지막 출력 스키마·guard·진단 관련 집중 회귀 | 50 passed, 72.96초 |
| Feed 준비 복원·관찰 정산/보존·무효 종료 + 구/새 parent | 11 passed, 66.38초 |
| DB 복구 예약·Writer 단독 복구를 포함한 전달 테스트 | 5 passed, 10.13초 |
| episode hybrid reader + memory revalidation + direct planner retry + outbox migration | 27 passed, 40.36초 |
| writer 복구를 별도 집계하는 observer/export 최종 회귀 | 16 passed, 13.94초 |
| 전달·실패 격리·구/새 parent·observer 통합 회귀 | 29 passed, 80.47초 |
| 자율활동 OFF·실행권 만료·다른 claim 소유자 경계 | 4 passed, 20.82초 |
| 전달 시각 보존을 포함한 최종 전달 회귀 | 6 passed, 11.40초 |
| 무효 대상 선택 ID 보존과 그래프 최종 회귀 | 6 passed, 22.17초 |
| 전체 검사에서 확인한 현재 schema 기대값 두 곳 수정 후 해당 파일 전체 | 23 passed, 18.25초 |
| 전송 전 원본 검사와 완료 시 점유권 검사 분리 후 기존 Feed 정규 실행·새 전달 회귀 | 18 passed, 40.00초 |
| 현재 SQLite 부분 인덱스 기대값 수정 후 canonical adapter 파일 전체 | 8 passed, 9.67초 |
| backend 전체 `tests --maxfail=1 -rs` | 첫 검사 1 failed/1361 passed/8 skipped, 223.24초. 아래 live schema 기대값 수정 후 다시 실행 |
| backend 전체 `tests --maxfail=5 -rs` | 5 failed, 2997 passed, 31 skipped, 2245.27초. 실패 상한에서 중단. 아래 수정·집중 재검사와 중단 지점 이후 검사로 구분 |
| 전체 검사 중단 지점 이후 1,049개 노드 | 24 failed, 1007 passed, 18 skipped, 369.25초. 24건 중 현재 기대값/inventory 2건 수정, 실행 보조 스크립트의 Windows spawn 영향 3건은 통상 실행으로 재검증. 설치 관련 19건은 미해결 |
| runtime composition와 L4 inventory 파일 전체 재검증 | 통상 `python -m pytest`로 22 passed, 47.27초 |
| architecture inventory | 공식 `--write` 후 `--check` 통과, modules 1265/internal edges 5017/external imports 3706. 허용 예외 추가 없음 |
| 현재 hybrid episode inventory | 공식 `--write`/`--check` 통과. 불변 predecessor 보존 |
| 현재 embedded runtime inventory | 공식 `--write --check` 통과. postgres_files 100/migrations 89/neo4j_queries 24/next_routes 44/parity_workloads 7 |
| 현재 L4 inventory | 공식 `--write --check` 통과. backend_modules 1265/frontend_candidates 13/parity_nodes 100 |
| backend boundary | 통과 |
| frontend boundary/design | 통과. features 14, route gaps 0 |
| frontend lint/typecheck | 통과 |
| frontend production Next/static build | 둘 다 통과 |
| personalized activity browser fixture | Next 1 passed, static 1 passed. 구/새 순서·새/미지 노드·오류·미기록 표시 확인 |
| `git diff --check` | 작업 파일·staged 검사 통과 |
| 과거 refactor preservation `--contracts --nodes` | **실패**. 아래 별도 설명 |

주요 재현 명령:

```powershell
uv run --directory backend python -m pytest -q tests/runtime tests/world_characters/test_activity_state.py tests/social/test_feed_observation_reclaim.py tests/social/test_feed_cycle_transactions.py tests/social/test_feed_normalized_execution.py tests/relationships tests/routine_posts
uv run --directory backend python -m pytest -q tests/runtime/test_activity_combined_delivery.py tests/runtime/test_activity_combined_failures.py tests/runtime/test_personalized_parent.py
uv run --directory backend python -m pytest -q tests --maxfail=1 -rs
uv run --directory backend python -m pytest -q tests --maxfail=5 -rs
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend build:static
```

### 과거 보존 검사의 실패 해석

검사는 이전 커밋에서 도입한 파일의 append-only introduction 증거 누락, 오래된 계약 기준과 현재 API/ORM의 차이, 기존 test node 보호 이력 부족을 보고한다. 이 실패를 통과로 바꾸기 위해 frozen baseline을 재생성하거나 예외를 추가하지 않았다. 이번 로컬 커밋의 새 파일 증거도 향후 공식 introduction 기록에 포함해야 한다.

대신 작업 시작 HEAD의 `backend/app`을 archive로 읽어 **작업 시작 코드와 현재 코드의 `current_contracts()`를 별도 프로세스로 비교**했다. `full`, `public`, `orm_tables`가 모두 같았다. 이는 이번 변경이 API/ORM 계약을 바꾸지 않았다는 추가 증거이며, 전체 역사 보존 검사의 PASS를 대신하지 않는다.

전체 backend의 첫 실패는 `test_hybrid_episode_inventory`가 현재 schema를 19로 기대한 것이었다. 기준 HEAD에도 이미 `SQLITE_SCHEMA_VERSION=20`, source revision `20260924_0098`이 있었고 최초 도입은 `1747feaa`였다. live inventory 테스트의 기대값만 20으로 맞추고 현재 inventory를 공식 생성기로 갱신했다. 불변 predecessor hash나 migration 자체는 수정하지 않았다.

이어 전체 검사에서 `test_manual_relationship_followup`의 fresh schema 비교와 `test_model_registration`의 신규 DB 버전 기대값도 19에 남아 있음을 확인했다. 해당 두 기대값을 20으로 수정하고 두 파일 전체 23개 테스트를 통과했다. v17→v18 마이그레이션의 과거 digest 검증은 유지했다.

또한 이번에 추가한 `FeedDelivery.delivered()`의 재검증이 기존 경로의 전송 전 원본 검증까지 다시 호출하여, 응답 중 게시글이 삭제되는 사례를 `observation_failed` 대신 `planner_failed`로 바꾸는 회귀를 발견했다. `validate_completion`을 별도 점유권 검사로 분리하여 기존 전달 사실·삭제 후 관찰 실패 경계를 복구했다. 다른 실행이 claim을 교체하면 덮어쓰지 않는 새 회귀도 추가했고, 기존 Feed 정규 실행과 새 전달 테스트 18개를 함께 통과했다.

전체 검사의 나머지 두 실패는 `test_l3_er0_embedded_runtime_inventory`의 현재 소스 inventory 불일치였다. 과거 커밋의 0098 migration·관계 outbox 변경과 이번 `world_feed.py` 변경을 공식 생성기로 반영했다. 실제 diff는 `postgres-sql-inventory.json` 한 파일이며, 고정 Git snapshot이나 frozen 계약 기준을 다시 생성하지 않았다. 전체 프로세스는 이미 import한 수정 전 코드를 검사했으므로 위 세 실패가 로그에 남아 있다. 수정한 파일은 별도로 통과를 확인하고, 중단 지점의 inventory 파일부터 남은 노드 전부를 이어 실행했다. 이를 단일 최종 전체 실행 PASS로 표현하지 않는다.

이어 실행한 검사에서는 canonical adapter의 부분 인덱스 기대값 15도 기준 HEAD의 v20 모델과 맞지 않았다. 기대값을 17로 갱신하고 outbox의 observation/source-event 인덱스 이름도 검증했다. 같은 파일 전체 8개 테스트를 통과했다. 분할 실행의 첫 시도는 실행 보조 스크립트의 import 경로 오류로 수집 단계에서 중단됐으며, 제품 테스트 실패와 구분해 로그를 보존한 뒤 경로를 수정해 다시 실행했다.

분할 검사에서는 L4 현재 inventory도 공식 생성기로 갱신했다. 기억 FTS 정책 전달 3건의 실패는 보조 스크립트에 Windows spawn용 `__main__` 진입 보호가 없어 자식 프로세스가 pytest를 다시 시작하는 영향이었다. 보조 스크립트에 진입 보호를 추가했고, 제품 코드는 수정하지 않았다. 일반 `python -m pytest` 명령으로 runtime composition과 L4 inventory 파일 전체 22개를 통과했다.

**남은 전체 검사 실패 19건은 설치 업그레이드 계약이다.** `test_p8_l_d_installer_upgrade_contract`의 source version 1~18 매개변수와 `test_p8_l_d_requires_real_v3_installer_fixture_in_hosted_matrix`다. 대상 데이터 버전 19 기대값, 일부 predecessor fixture의 schema digest 불일치, schema 20에서 요구되는 predecessor 19와 지원 목록 1~18의 불일치가 남아 있다. 작업 시작 HEAD의 app·해당 scripts/tests를 별도 archive로 읽어 대표 source version 1/18 및 지원 목록 검사를 재현했다. 이번 SNS 변경이 API/ORM을 바꾸지 않았다는 비교와 별도로, **기준 코드에서도 같은 실패가 있다는 증거**다. 설치 fixture/지원 CI 행렬은 이번 SNS 구현 범위에서 수정하지 않았으며 설치·workflow도 실행하지 않았다. 따라서 전체 backend green이나 설치 준비 완료를 선언하지 않는다.

## 7. 실제 AI 비교 결과

사용자가 정한 최대 120회 안에서 `gemini-3.1-flash-lite`, thinking `high` 하나로 수행했다. 같은 합성 사례를 두 계약에 공급하고, 같은 최신 기록 수정이 적용된 코드로 비교했다. 사용자 데이터 volume은 별도 평가 컨테이너에서 read-only로 읽어 기존 credential을 사용했고 합성 Routine DB는 메모리에 만들었다. credential/API 키는 결과에 출력하지 않았다.

**종류는 frozen component 비교**다. 실제 hybrid 검색, 실제 게시/관계 저장, 앞 경로의 실제 committed effects를 다음 AI 요청에 전달하는 전체 실행, 검색/게시 포함 전체 지연은 이 AI 측정에 포함하지 않는다. 이를 manifest에 호출 전 명시했다.

사례: 부정, 정정, 끝난 대화 반복, 일반 대화, 초대, 불명확한 과거, 도움 요청, 의견 충돌. 각 버전 1회씩, 순서를 교차 배치했다. 별도 화폐 비용 상한은 지정되지 않았으며, 요청 상한을 적용했다.

### 최초 유효한 8쌍 비교 — 최종 스키마 보강 전

| 지표 | 기존 계약 1 | 새 계약 2 |
| --- | ---: | ---: |
| 사례 수 | 8 | 8 |
| 실제 요청 합계, 복구 포함 | 61 | 40 |
| 사례별 요청 | 8/8/6/7/8/8/8/8 | 4/5/4/5/5/4/5/8 |
| 중앙 구성요소 처리 시간 | 39.46초 | 25.32초 |
| 최장 사례 시간 | 45.60초 | 76.50초 |
| 입력 토큰 | 81,604 | 69,531 |
| 응답 토큰 | 12,346 | 26,424 |
| 생각 토큰 | 62,673 | 39,149 |
| 기록된 총 토큰 | 156,623 | 135,104 |

요청은 약 34.4%, 중앙 시간은 약 35.8%, 총 토큰은 약 13.7% 줄었다. 그러나 토큰 종류별 단가가 다르고 실제 화폐 비용을 계산하지 않았으므로 **비용이 13.7% 줄었다고 해석하면 안 된다.** 전체 runtime 처리 시간도 아니다.

처음에는 8개 중 5개 새 구조 사례에서 Writer 복구가 발생했다. 의견 충돌 사례는 잘림 재시도와 Writer 복구가 겹쳐 8회·76.50초까지 늘었다. 초대 사례에서는 다음 주를 이번 주로 바꾸거나 일정 미확인 상태에서 과한 동행 약속을 하는 표현이 나타났다. 기존 구조에도 완벽하지 않은 표현이 있어, 어느 쪽도 단순 schema 통과를 의미 품질 통과로 간주하지 않았다.

실험 도중 잘못된 합성 scope guard로 실패한 새 구조 2건(각 4회)은 제품 품질 비교 표본에서 제외하고 같은 쌍을 다시 실행했다. 이 8회와 중단된 2회도 전체 요청 예산에서 차감했다. 일반 모델 실패를 임의로 제외한 것은 아니다.

### 최종 본문 스키마 보강 뒤 추가 확인

통합 Social 초안의 body를 필수 비어 있지 않은 문자열로 만들고, target ID를 실제 입력 집합 enum으로 제한했다. task ID와 다른 conversation ID에 부적절한 길이 제약을 상속하지 않도록 정리했다. 초안을 조용히 채우거나 검증을 완화하지 않았다.

남은 예산 안에서 새 구조의 초대·충돌 2개만 다시 실행했다.

| 사례 | 요청 | 시간 | 확인 |
| --- | ---: | ---: | --- |
| 초대 | 4 | 22.47초 | 복구 없음, 일정 확인 후 대화를 이어가자는 표현 |
| 충돌 | 4 | 23.65초 | 복구 없음, 의견을 인정하고 대안을 함께 검토하는 표현 |

최종 스키마로 8쌍 전체를 다시 평가한 것은 아니다. 위 2개 재확인을 최초 비교에 선택적으로 섞어 최종 전체 PASS로 표시하지 않는다.

예산 장부는 **119/120 예약**이다. 완료 행의 요청 합계 117회와 중단 시도 2회가 포함된다. 중단 시도는 예약을 되돌리지 않아 상한을 보수적으로 지켰다. 남은 1회를 불필요하게 소모하지 않았다.

## 8. 전환 판정과 다음 작업

판정은 **버전 2 구현 / 신규 기본 전환 보류**다. 다음 조건이 남아 있다.

1. 최종 스키마 상태에서 대표 전체 표본을 다시 비교한다. 현재 승인된 120회 예산을 새 실행에서 초기화하거나 초과하지 않는다. 추가 실제 평가의 범위·예산은 별도로 정한다.
2. 장문 Inbox, 실제 제안 accept/reject/counter, 기억 부족·정정, Routine 연속 장면·반영 사건을 포함한 격리 전체 그래프 비교로 확장한다. 현재 평가의 합성 초대 문장은 실제 활동 제안 원장 E2E 검증과 다르다.
3. 하이브리드 기억 조회 → 입력 → 게시 → 에피소드/관계 원본·projection → 다음 회상/다음 일과까지의 실제 AI 후속 소비와 캐릭터성·연속성을 판독한다. 자동 테스트의 계약 보존과 모델의 적절한 사용을 분리한다.
4. 모든 필수 중단 지점과 전체 scope/claim/기억/상태 변화 조합을 새 계약에서 추가 확인하고, 장문 split 및 실제 모델별 출력 한도를 검증한다. 현재 개별 회귀의 존재만으로 전체 조합을 망라했다고 선언하지 않는다.
5. 오래된 refactor 보존 증거는 원래 최초 도입 커밋을 기준으로 보수한다. 이번 코드의 실제 계약과 별개인 역사 불일치를 새 baseline으로 덮지 않는다.
6. 복구 포함 전체 비용/지연, 특히 느린 꼬리와 Routine 지연·완료율에 큰 손실이 없고 품질 기준을 만족하면 신규 기본값만 2로 전환한다. 진행 중 1/2 작업의 재개를 유지한다.
7. 별도 설치 작업에서 schema 20의 predecessor fixture 재구성·지원 버전 목록·관련 기대값을 일치시키고 설치 업그레이드 회귀 19건을 해결한다. 이번 실행에서는 기존 문제를 진단했고 설치 구성 변경은 하지 않았다.

자연 활동 120분+후속 구간, observer completeness, 설치 앱 USER CHECK는 이번에 실행하지 않았다. 운영 관찰은 별도 가이드와 승인된 범위에 따라 진행해야 한다. Windows 설치 앱의 버전/DB 상태에 대한 판단도 이번 결과에 포함하지 않는다.

## 9. 증거 위치

작업 workspace의 `.local-diagnostics/sns-four-call-evaluation-20260926/` 아래에 보존했다.

- `second/manifest.json`: 비교 조건·모델·thinking·상한·한계.
- `second/budget.json`: 전체 요청 예약 119/120.
- `second/results.jsonl`: 합성 결과와 요청별 usage/진단. 실제 사용자 게시글이 아닌 합성 자료.
- `second/probe-manifest.json`: 마지막 2개 probe의 소스 hash와 잔여 예산.
- `contracts-before.json`, `contracts-after.json`: 시작 HEAD와 후보의 API/ORM 비교.
- `backend-full-tests.log`: 전체 backend 테스트 실행 결과.
- `backend-full-tests-final.log`: live schema 기대값 수정 뒤 전체 검사 결과.
- `backend-remaining-tests.log`: 실패 상한 중단 뒤 inventory 파일부터 남은 1,049개 노드 검사.
- `backend-remaining-setup-error.log`: 분할 실행 보조 스크립트의 최초 import 설정 오류. 제품 테스트 실패로 집계하지 않음.
- `runtime-composition-inventory-retest.log`: 일반 pytest 진입으로 재검증한 22개 통과.
- `baseline-installer-failures.log`, `baseline-installer-target-version.log`: 작업 시작 HEAD에서도 재현되는 설치 업그레이드 검사 실패.
- `preservation-audit.log`: 역사 보존 검사 실패 원문.

진단 파일·source archive·credential volume 내용은 로컬 코드 커밋에 넣지 않는다. 소스 및 합성 평가 스크립트·회귀·본 문서만 커밋한다.
