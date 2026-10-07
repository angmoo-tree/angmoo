# 10-08 Chat·SNS 상황기억 구현 및 로컬 검증 기록

## 범위와 판정

workspace의 `10-08 Chat·SNS 상황기억 영속 접수와 일일·종료 일괄 저장·색인 코드 구현 세부 계획.md` I00–I49를 구현한다. 코드·자동 회귀·합성 성능 측정·실제 AI 품질·사용자 확인은 각각 구분한다.

- 브랜치: `feat/0.1.0-release-readiness`.
- 시작 HEAD: `9c1d3868c7a547d1ef3af3c8078ad2684d92060f`, 시작 작업 트리 clean.
- I00–I47 구현·집중 검증 완료. I48 전체 회귀와 I49 최종 기록·로컬 커밋은 진행 중이다.
- 신규 활동 기본 policy는 `activity_situation`. 이미 접수된 request/run의 frozen policy는 덮어쓰지 않는다.
- push·PR·원격 CI·main merge·설치 앱 변경·실제 AI/임베딩/이미지 API 호출은 수행하지 않았다. 개별 `scripts/ci` 명령은 계획 §14가 지정한 로컬 검사다.
- D03은 개발 Compose `angmoo_angmoo_contributor_embedded_data` volume의 `/var/lib/angmoo`만 대상으로 완료했다. 앱 컨테이너는 중지 상태이며 자연 AI 활동으로 검증하지 않았다.

## 최종 구조와 실제 저장 경계

기존 Chat 최종 응답과 SNS DecisionDraft 호출의 마지막에 상황 설명을 받는다. 1,000 Unicode code point 이내의 부가 결과이며, 설명 오류가 정상 답변·활동을 탈락시키지 않는다. 새 policy에는 설명 전용 생성/수선 호출, 중요도 선별, 32개 묶기와 일일 통합 요약이 없다.

활동 결과와 receipt는 같은 Session의 한 transaction에 기록한다. 접수 직후에는 정식 기억이나 신규 색인을 만들지 않는다. 예약 시각, 첫 카드의 `지금 기억 저장`, 인증된 host 종료 요청이 고정 cutoff를 접수한다. 공통 소비자가 최대100개씩 MemoryItem·Evidence·Info·Source와 applied 상태를 함께 저장한다. 같은 logical activity/대상의 최초 기억은 한 번만 만들며 직접 삭제한 기억을 재시도로 복원하지 않는다.

SQLite가 canonical 원본이다. FTS와 768차원 Vec1은 개별 기억의 현재 description만 색인하며, 색인 실패와 무관하게 정식 기억 목록·상세를 읽을 수 있다. 원문은 선택 후 현재 권한·version·digest를 확인하여 제한된 분량만 읽는다. 원문 삭제와 변경/비공개를 구분하고 prior/background를 포함한 전체 입력 범위를 검사한다.

Memory가 접수·저장을 소유한다. Chat·WorldCharacters는 중립 계약과 주입된 port를 사용하고 Runtime이 구체 Memory 서비스/source adapter를 조립한다. 금지 import 예외, 별도 저장소, 가짜 bundle, 후속 독립 commit으로 원자성을 우회하지 않았다.

| writer | 안정 identity | 같은 transaction 참여 |
| --- | --- | --- |
| Chat | scope + response slot + chat + response slot | assistant/thought finalize 뒤, checkpoint/commit 전 |
| Inbox | scope + activity + inbox + conversation target | canonical effect/event/thought의 deferred UoW 안 |
| Feed | scope + activity + feed + post target | immediate publish/event/execution/thought transaction 안 |
| Routine | scope + activity + routine + routine-post | canonical post/beat/execution 저장 UoW 안 |

같은 target의 reply+Like는 하나이고 서로 다른 Inbox 대상은 각각 별도 receipt다. 계획과 확정 효과가 다르면 정상 효과는 보존하되 설명을 차단한다. receipt DB 쓰기 실패는 활동까지 rollback한다. 종료에는 신규 관계/요약 AI를 호출하지 않으며, 이미 적용된 기억의 검색 준비를 남은 시간 동안 관찰한 뒤 late result를 fence한다.

## I00–I49 추적

아래 `memory/…`는 `backend/app/domains/memory/…`, `runtime/…`는 `backend/app/runtime/…`다. 테스트는 별도 표기가 없으면 `backend/tests` 기준이다.

| 단계 | 실제 구현·증거 |
| --- | --- |
| I00 | branch/HEAD/clean·구조안·D01–D04·아키텍처·개발 data inventory·AI0 baseline 확인. |
| I01 | 위 네 writer의 안정 identity와 같은 Session commit 경계, runtime Chat/SNS participation. |
| I02 | 중립/Memory `contracts/activity_situation.py`, `policies/situation_output.py`: 독립 parser·target당1개·1,000자·digest. |
| I03 | `memory/models/activity_situation.py` 8테이블, FK/unique/run/request/cutoff·삭제 identity. |
| I04 | 단일 Base 등록·168 ORM 테이블·Alembic `20261008_0108_activity_situation.py`. |
| I05 | embedded v31 delta·frozen DDL/manifest·registry. |
| I06 | `repository/situation_runs.py`: 기존 예약/종료 값 승계, 신규 예약 OFF·22:30·종료 ON, 관계 AI 별도 gate. |
| I07 | populated upgrade·Alembic/embedded parity·기존 v29 secret/rollback 회귀. 역사 revision 본문 보존. |
| I08 | DeliveredInputManifest/DeliveredSourceEntry: source 범위·역할·최종 payload digest. |
| I09 | `runtime/chat/situation_memory.py`: current/recent/frozen evidence 실제 전달 순서. |
| I10 | SNS final target/parent/proposal/relationship/prior/image delivery adapter. |
| I11 | Routine activity/source events/previous success/completed/today 역할, Post와 DTO 구분. |
| I12 | admitted environment locale/activation epoch를 Chat request와 World activity frozen input에 저장. |
| I13 | Chat result/schema/parser와 response step의 상황 설명 결과 전달. |
| I14 | `policies/situation_generation.py` 영어 지침·Chat 마지막 필드·기존 호출/예산 검사. |
| I15 | Combined situations와 독립 parser, graph result의 명시적 manifest/draft. |
| I16 | Inbox/Feed target 대응, Like-only와 복합 행동 fixture. |
| I17 | Routine plan/title/body 다음 설명, 기존 post/image/state 및 recovery writer 연결. |
| I18 | `runtime/test_activity_situation_generation.py`: combined/별도/recovery 최종 결과·기존 호출 수. |
| I19 | `repository/situation_admission.py`: stable unique replay/conflict, 같은 Session, 독립 commit 없음. |
| I20 | 실제 Chat finalize receipt 원자성; 이미지 파일/인식 결과 모두 연결. |
| I21 | 실제 Inbox canonical effects 3대상과 receipt rollback. |
| I22 | 실제 Feed Like/reply receipt, immediate/deferred 참여·재실행 방지. |
| I23 | 실제 Routine Post UoW·replay fixture. |
| I24 | 계획 효과/확정 결과/output digest 대조; partial/unknown/missing 설명 차단. |
| I25 | 네 writer의 실패 주입·commit/replay·설명 오류 독립, 접수 직후 pending만 존재. |
| I26 | `repository/situation_apply.py`: 개별 기억/evidence/metadata/applied 원자 저장, 유효 작은 경험 포함. |
| I27 | `service/situation_management.py`, processing GET/PUT·save POST의 owner/CSRF/CAS/key/cutoff. |
| I28 | `runtime/memory/situation_sources.py`: 현재 scope/actor/epoch/권한/prior/version, 삭제와 변경 구분. |
| I29 | `situation_runtime.py`: 같은 소비자·최대100 page·fair claim·foreground Chat 양보. |
| I30 | shutdown/indexing coordinator: 제한 종료·검색 준비 관찰·late result fence/deferred. |
| I31 | 영속 run/request/cursor/lease 재시작, missed due의 captured-at/sequence 이중 cutoff·시간대/DST, fresh startup 무조건 flush 금지. 예약 시각 이후 접수는 다음 허용 계기에 남긴다. |
| I32 | file SQLite 동시 요청/claim·고정 cutoff·명시 retry·느린 fake provider와 별도 canonical 쓰기. |
| I33 | situation_reads/situation_packets와 episode/canonical reader의 새 representation dispatch. |
| I34 | FTS summary/version만 등록; 순수 scope lock은 전체 색인 rebuild를 유발하지 않음. |
| I35 | 기존 vector eligibility/read_work/projector, version/hash/profile fence, 종료 후 결과 차단. |
| I36 | old/new hybrid currentness·RRF·scope/prior 검사, unknown policy fail closed. |
| I37 | 선택 후 bounded 원문/thought hydration, 불가 원문의 사본/링크 미반환. |
| I38 | Hot Brief/prior/pin/correction/delete/retention, correction 자체 privacy metadata·삭제 receipt identity. |
| I39 | summary-only FTS/Vec, canonical 즉시 표시, 일반 조회/저장/ON과 전체 준비 분리. |
| I40 | frozen policy routing·D03 cutoff/epoch fence 후 신규 기본값 활성화, batch32 이중 접수 금지. |
| I41 | typed retirement·정확한 inventory·실제 개발 데이터 폐기/재실행. 아래 D03 결과 참조. |
| I42 | 관계 미사용 old/new union·core counterpart·삭제 원문의 새 summary 유지. |
| I43 | prepare/manual/refresh/revalidate/apply 동일 scope 선행 저장 fence; 다른 scope 진행·Vec 대기 없음. |
| I44 | 관계 DTO·키/모델/수동/예약 유지, 새 선별/32 요약/종료 관계 생성 제거, 폐기 대상 복구 차단. |
| I45 | 첫 카드 processing controls: 수동 저장·예약/종료 설정·key 재사용·scope abort·dirty 보존. |
| I46 | 새 representation 상세·삭제 원문·생각·canonical 표시와 기존 owner controls. |
| I47 | ko/en catalog·종료 문구·a11y, Next/static 공유 UI와 16개 browser fixture. |
| I48 | 전체 회귀 진행 중. V/T 자동 증거·합성 부하와 실제 API/native 실기 보류 분리. |
| I49 | 최종 검증 뒤 명시적 stage·로컬 커밋·이 기록과 재개 명령 유지. |

## V01–V37 / T01–T18 증거

로그는 Git에서 제외된 `artifacts/situation-validation/`에 있다. 첫 전체 회귀 `backend-full.txt`에서 이전 기본 policy를 가정한 fixture와 오래된 image Chat 조립을 발견했다. 수정 후 `backend-full-second.txt`로 재검증 중이며 최초 실패를 PASS로 세지 않는다.

| 검증 묶음 | 연결 V/T | 실행 증거 |
| --- | --- | --- |
| 계약/parser·원자 접수·고정 cutoff·삭제 identity·epoch | V02–V05/V09–V16/V25/V33/V34/V36, T02/T03/T09 | activity_situation_contract/receipt tests, `all-sns-receipts.txt` 9 pass, `chat-images-final.txt` 6 pass. |
| 최종 provider/복구·locale·manifest/range | V01/V03/V06–V08/V11/V20/V27, T07/T08 | `generation.txt` 6 pass, Unicode/name-binding recall fixture, 기존 Chat response/routing/streaming 회귀. |
| schema/기존 key/예약/구 작업 보존 | V26/V32, T04–T06 | v31/Alembic parity·v29 실제 key fixture·populated migration suites와 `migration-final-fixes.txt`. |
| 수동 HTTP/동시성·일일/종료/시간/재시작 | V14/V29/V32/V34/V35/V37, T06/T09–T11 | situation_schedule, 기존 episode schedule/shutdown/calendar; `remaining-integration.txt` 17 pass. native 실기는 보류. |
| canonical/삭제·변경/private/prior/correction·검색 | V17–V24/V26/V33, T12/T13 | situation_application/recall, episode privacy/hybrid/vector/lifecycle 회귀. |
| late embedding fence·독립 foreground write | V23/V24/V35/V37, T09/T11/T12 | vector_projection_lifecycle·`shutdown-schedule.txt` 11 pass 및 remaining integration. |
| 실제 Vec1 profile/filter/version/삭제/재시작 | V21/V23/V24, T12 | network-none helper `vec1-native.txt` 14 pass. Windows native-extension skip과 별도 증거. |
| D03 폐기·재실행·비대상 불변 | V25/V26, T01/T14 | situation_transition, 실제 `dev-d03-{inventory,upgrade,apply,replay}.json` 및 로그. |
| 관계 old/new union·대상·삭제 원문·처리 순서 | V31, T15 | situation_relationships·기존 관계 suites·`relationship-fairness-final.txt`. |
| 정상/empty/OFF/중복/timeout/draft/scope/detail/모바일/키보드 ko/en | V23/V28/V29/V32, T07/T16 | `browser-final.txt`: Next/static × ko/en 16 pass. 390/1100 screenshot, 실제 AI/native 검증 아님. |
| 경계·타입·디자인·build/static·locale | T07/T18 | frontend lint/typecheck/build/static/catalog, architecture/design 로그. raw-color 1167 유지, route gap 0. |
| backlog/lock/검색/hydration·Vec1 비용 | V30/V37, T17 | `load-01/measurements.json`, `vector-load-linux-01/measurements.json`. |
| 전체 회귀·최종 diff/branch/commit | T01/T18 | `backend-full-second.txt` 진행 중; 보존 검사·최종 commit 뒤 갱신. |

V30 실제 모델 의미 품질은 보류다. 표는 해당 위험을 다루는 fixture의 연결이며 모든 입력·OS·장비를 증명하지 않는다. 실기 확인을 자동 PASS에 합치지 않는다.

## D03 실제 개발 데이터

`scripts/diagnostics/retire_activity32_tasks.py`를 앱 컨테이너가 중지된 상태에서 network-none helper로 실행했다. maintenance owner 잠금·정확한 ID/cutoff 재검증·같은 transaction의 typed 삭제·전체 테이블 지문 비교를 사용했다.

1. inspect: 6 scope, 구 job 2개, candidate 115개, request 2개를 inventory에 고정.
2. upgrade: v30 → v31 copy-on-write staging 승격 성공. 실제 data-root 암호화 키 주입, provider 0회.
3. apply: 해당 job 2개·candidate 115개·request 2개와 전용 종속 기록 폐기. 대상 잔여0. queue/fence 9테이블만 변경, 비대상 160테이블의 행 수·지문 동일.
4. replay: 같은 audit key 재실행에서 변경 테이블0, 169테이블 지문 동일, 잔여0. JSON에 다시 표시된 계획상 삭제 수를 두 번 삭제한 결과로 세지 않는다.

선택 DB는 `/var/lib/angmoo/canonical/generations/contributor-v2-schema-v3-schema-v4-schema-v9-schema-v-schema-v31/angmoo.sqlite3`다. 이전 generation·키 파일·미디어·원문·기존 기억·관계·설정을 보존했다. 설치형 Windows Angmoo 데이터/identity는 대상이 아니다. D03을 다시 실행할 필요는 없다.

## T17 합성 측정

10k/100k 인공 기억과 1,000개 pending에 실제 application page·FTS를 실행했다. 같은 원문을 공유하는 낮은 다양성 fixture이고 동시 테스트의 CPU/디스크 경쟁이 있다. 접수 평균은 접수 transaction 비용이며 전체 Chat 응답 시간이 아니다. 처리량은 이 환경의 관측치다.

| 규모 | canonical DB | FTS DB | 1,000개 적용 | 최대100개 page | 별도 foreground 쓰기 최대 | 접수 평균 | FTS 검색 / hydrate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10k | 31,006,720 B | 13,672,448 B | 10.99초, 91.0개/초 | 1,298ms | 10.53ms | 8.93ms | 48.08 / 106.30ms |
| 100k | 275,357,696 B | 134,168,576 B | 13.82초, 72.36개/초 | 1,789ms | 68.74ms | 46.67ms | 608.86 / 307.64ms |

Vec1은 Docker 이미지에서 추출한 manifest/SHA 검증된 0.7 확장과 합성 768차원 float32 값이다. Linux `/tmp`에서 측정하고 JSON만 Windows 증거 폴더로 내보냈다. 실제 data volume/provider를 사용하지 않았다.

| 벡터 수 | 실제 index 크기 | 등록 시간 | 검색 평균 / 최대 |
| --- | --- | --- | --- |
| 10k | 33,648,640 B | 6.93초 | 37.44 / 64.78ms |
| 100k | 336,576,512 B | 50.73초 | 375.05 / 442.15ms |

비교용 Windows Docker bind mount의 10k 검색 평균은 약 3.42초였다. 100k 검색은 10초 deadline으로 `memory_vector_cancelled`가 발생했다(`vector-load-01.txt`). 이 환경의 100k 검색 성능은 PASS가 아니며 Linux 수치와 혼합하지 않는다. 단일 검색/page가 수백 ms 이상 걸릴 수 있으므로 지연0이나 전경 무대기 PASS를 주장하지 않는다. 작은 page·foreground 양보·검색 deadline/FTS fallback을 유지한다. 실제 임베딩 API 시간·비용·의미 품질은 측정하지 않았다.

## 재현과 재개

제품 저장소 루트에서 실행한다. 로컬 검사만 수행하며 일반 테스트는 실제 서버를 요구하지 않는다.

```powershell
uv run --directory backend python -m pytest -q tests --maxfail=20 --tb=short
uv run --directory backend python -m pytest -q tests/chat/test_activity_situation_receipt.py tests/memory/test_activity_situation_relationships.py tests/memory/test_vector_projection_lifecycle.py
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests exec playwright test --config playwright.memory-situation.config.ts
uv run --project backend python scripts/diagnostics/measure_activity_situations.py --output artifacts/situation-validation/new-synthetic-run
```

벡터 helper는 현재 app/tests/diagnostics를 읽기 전용으로 연결하고, 패키지의 `vec1.so`/`manifest.json`을 읽는다. network-none이며 사용자 volume을 연결하지 않는다.

```text
python scripts/diagnostics/measure_activity_situations.py --vector-only --vector-resources /evidence/vec1-linux --output /evidence/new-vector-run --data-root /tmp/new-synthetic-vectors
ANGMOO_TEST_VEC1_EXTENSION=/evidence/vec1-linux/vec1.so python -m pytest -q tests/memory/test_sqlite_vec1.py tests/memory/test_vector_generations.py
```

## 보류와 운영 경계

- 실제 AI의 ko/en 준수, 원문↔응답↔설명의 의미 정확성, 검색 유용성: 별도 관찰 전까지 미검증.
- 설치 앱 physical identity, 실제 native quit/skip/강제 종료·자연 활동·사용자 확인: 미수행. host 요청 의미는 유지했고 backend fake coordinator를 검증했다.
- 새 배포 이미지 빌드·앱 재시작·PR·원격 CI·push·main merge: 미수행. 개발 앱 컨테이너는 중지 상태다. 사용자가 시작하면 설정된 키로 자율 활동이 재개될 수 있다.
- 일반 migration은 구 작업을 자동 폐기하지 않는다. 위 개발 volume만 D03 완료이며 다른 data root의 삭제 권한/상태 증거로 재사용하지 않는다.
- 최종 로컬 커밋과 전체 자동 검증 판정은 마지막 확인 후 추가한다.
