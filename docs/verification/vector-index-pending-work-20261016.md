# 벡터 인덱스 변경·미완료 작업과 SQLite 잠금 단축 검증

- 실행일: 2026-10-16, Windows 로컬 개발 환경.
- 기준 main: `117dd3f7ab0359860c88833711c1cdd21200aa50`.
- 구현 브랜치: `feat/vector-index-pending-work`.
- 적용 지침: workspace/repository AGENTS, `backend/ARCHITECTURE.md`, `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md`, CONTRIBUTING의 DCO 지침.
- 범위: 10-16 계획 I00–I55. 로컬 구현·범위 검증·서명된 로컬 커밋. push/PR/Actions/main 병합 없음.
- 제품 상태와 구분: Docker 컨테이너·사용자 SQLite·설치된 Windows 앱을 변경하거나 재시작하지 않았다. 실제 AI 호출 없음.

## 1. 구현과 트레이드오프

| 책임 | 구현 | 보존·제한 |
| --- | --- | --- |
| 변경 전달 | 41개 원본/설정 표의 검토된 열에 123개 SQLite trigger | 원본과 같은 commit/rollback, bulk/cascade 포함. 깊은 조회는 trigger에서 하지 않음 |
| 실행 대상 | eligibility와 별도 work, desired/applied revision, token/lease, due index | 완료 항목을 순환하지 않음. 5초 fallback은 pending/due 작은 조회만 수행 |
| 권한 경쟁 | 명시적 read snapshot + world/owner epoch + 최종 claim/시간 비교 | 기존 출처/권한 정책과 actual recall 검증 유지. epoch는 보수적으로 같은 World 변경을 거절할 수 있음 |
| 의존 관계 | 실제 조회와 명시적 JSON 출처에서 직접 dependency 구성 | prior의 transitive closure를 자손마다 복사하지 않음. 부분 ancestor 관찰은 합집합으로 보존하여 누락 방지 |
| fan-out | 페이지64, tick당 최대4 frontier 페이지, causal root의 visited identity | 큰 DAG·cycle에서도 유한. 신규 변경은 durable ledger에 남음 |
| 최종 효과 | canonical writer 안에서는 짧은 현재성 검사와 Vec1 효과만 | provider, credential 복호화, source hydration, journal fsync, extension load는 밖에서 수행 |
| 재사용 | 내용 hash/profile 동일 vector, metadata 동일 시 완전 no-op | pin·version·metadata 변경은 재임베딩하지 않음 |
| 장애 복구 | 수신 journal + 조건부 receipt 제거 + canonical 물리 호출 예산 | Vec1 저장/ack 실패 뒤 추가 provider 호출 없이 재개. 폐기 generation과 예산 분리 |
| 전환/점검 | 기존 등록만 bootstrap, 고정 상한/cursor, 24시간 identity audit | 새 과금 동의/미등록 과거 기억의 자동 등록 없음. audit 정상 항목은 source/Vec1 읽기만, checkpoint만 쓰기 |
| 삭제 | retained generation 제거 후 정확한 item별 작업/dependency/budget 정리 | World 삭제 전용 owner가 처리. 글로벌 epoch는 ABA 방지를 위해 content-free fence로 보존 |
| 배포 자료 | sidecar에 `vector_mutations.json` 포함 | 설치본/전체 Windows 패키징 실행은 이 로컬 코드 검증 범위에 포함하지 않음 |

6개 표를 추가했다. 계획의 5개 책임 표 외에 `memory_vector_attempts`를 canonical에 두어,
폐기 가능한 Vec1 generation이 손상되거나 바뀌어도 유한 호출 예산을 초기화하지 않는다.
기존 World 삭제·관계 수동 검토 worker의 polling 구현은 변경하지 않았다.

OFF는 정상 벡터의 보존을 뜻한다. 출처 접근이 사라지거나 기억이 만료·삭제되면 OFF 상태에서도
정리한다. legacy generation의 호출 예산 파일이 이미 없어 이관 여부를 입증할 수 없는 경우는
추가 유료 호출을 자동 허용하지 않고 vector unavailable로 남긴다. 손실된 과거 증거를 추정하지 않는다.

## 2. 변경 생산자와 원자성

정확한 표/열/OLD·NEW key/epoch 계산은 `vector_mutations.json`과 `vector_mutations.py`를 기준으로 한다.
호출자별 event hook을 복제하지 않고 실제 canonical 표의 mutation에 연결하므로 ORM·Core SQL·cascade가 같은 계약을 따른다.

| 생산자 계열 | 원본/접근 사실 | 소비되는 키와 보장 |
| --- | --- | --- |
| Memory 승인·정정·수동 편집·pin·삭제 | items, evidence, eligibility, episode info/restrictions, situation info/sources | memory ID; 직접 prior와 correction-parent 전파 |
| scope/embedding 설정·명시적 준비 | scope settings, embedding settings, eligibility | World 키; ON/OFF/profile·version·등록 변경. registered_at만 바뀌면 재등록 루프 없음 |
| 키 저장/회전/폐기 | world credentials/revisions, account credentials | World/owner epoch. blocked 항목도 의존 관계를 남겨 새 키에서 재개 |
| SNS/Chat | posts/reply ancestors, likes, messages/threads | source ID + FK/JSON 연결. 원본이 없던 상태에서 INSERT도 전달 |
| 접근 범위 | World/character/membership/block, 관찰 기록 | World 키 또는 post/event parent 키. 존재하지 않았던 block/참여자/관찰의 생성도 반영 |
| 활동/관계·상황 기억 | social events/evidence/context, beats/proposals/plans, joint participants, relationship state/change, situation receipt/bindings | 직접 source/parent 키 + World epoch |
| 이미지·소유자 | media assets, image interpretations, user deletion | source ID + owner epoch |
| World 삭제 | deletion request admission | 새 일반 전달 차단, 기존 proof 무효화. 전용 cleanup owner의 exact-ID 제거 |

lease/queue cursor 같은 관리 상태는 source catalog에 넣지 않는다. 원본의 보호 열이 실제로 바뀌지
않는 UPDATE도 trigger에서 제외한다. 삭제된 identity는 fan-out/정리가 끝날 때 제거하고 글로벌
revision은 내용을 담지 않는 단조 fence로 남긴다. 다른 World 자료를 정리 범위에 포함하지 않는다.

## 3. I00–I55 추적

| 항목 | 구현/증거 |
| --- | --- |
| I00–I02 | 지침·clean main 확인, 새 브랜치 생성, 기존 Docker 진단은 과거 측정으로 분리 |
| I03–I08 | 위 mutation 표, catalog, 6개 스키마, revision/lease/expiry/복구 상태 계약 |
| I09–I14 | Memory 모델/queue/attempt repository, Alembic 0116, SQLite v39 frozen DDL/manifest, 단일 Base |
| I15–I20 | 원자 source trigger, column no-op filter, rollback/cascade, 설정·키·World 삭제 연결 |
| I21–I24 | normalized read graph, causal frontier, time boundary, after-commit hint 및 fallback |
| I25–I31 | vector_proof/delivery/batches, 실제 snapshot, final fence, reuse, journal CAS, 25ms Vec1 admission |
| I32–I37 | pending dispatcher, worker lifecycle, bounded bootstrap/settle/promotion/audit/retirement |
| I38–I41 | exact-item erasure, World composition, truthful health, 공개 API/프론트엔드 문구 변경 없음 |
| I42–I48 | 아래 V 매핑과 범위 pytest, 실제 WAL·Vec1·heartbeat 및 잠금 계측 |
| I49 | V39 운영 사본 비교는 선택 항목으로 미실행. 합성 동일 자료 비교와 구분 |
| I50–I53 | 범위 compile/architecture/embedded migration/diff 검토, 아래 최종 결과 참조 |
| I54–I55 | 최종 범위 검증 후 로컬 Signed-off-by 커밋과 작업 상태 정리. 원격 실행 없음 |

## 4. V00–V39 검증 매핑

| V | 주된 시험/확인 |
| --- | --- |
| V00–V07 | `test_vector_pending_work`: atomic bulk/no-op/rollback, stale claim/lease/ack, 2,112 done rows, source restart/frontier, wake detach; SQLite recovery contracts |
| V08–V12 | `test_canonical_source_dependencies`, `test_lineage_validation_cost`, `test_activity_situation_application`; recovery fan-out cycle, World/source closure |
| V13–V15 | projection lifecycle pin/OFF/delete/key tests, pending-work expiry/snapshot race, recovery OFF source revoke and World erasure admission |
| V16–V18 | lifecycle existing-vector reuse, vector batch delivery and real `test_sqlite_vec1` metadata/filter/profile tests |
| V19–V22 | batch result storage/admission tests, commit-before-ack recovery, real Vec1 busy receipt, terminal budget across retained generations, key rotation |
| V23–V25 | `test_vector_work_v39` populated canonical/vector preservation + rollback + manifests; populated v8 upgrade; observation v19 chain; Alembic layout/model registry |
| V26–V29 | bootstrap cursor/cutoff implementation, restart/frontier and ready-before-promotion replay, real generation file corruption/missing/promotion tests; legacy budget guard |
| V30–V34 | deleted-item exact cleanup, World admission race, retained generation erasure, World original/other-World regression, lifecycle source/current canonical recall |
| V35–V36 | 2,112 completed **work rows** (synthetic), no source hydration/SQL writes/provider; finite audit no-op and missing vector repair |
| V37–V38 | 64-node shared prior DAG, real WAL/independent scheduler heartbeat, actual Vec1 contention/result reuse; bounded fan-out/claim tests |
| V39 | **미실행 — 선택 사항.** 운영 DB를 복사하지 않았으며 실제 2,112개 기억 자료에서의 CPU/잠금 재측정을 주장하지 않음 |

고정 Vec1 Windows DLL: version 0.7, source `8fc7b115a4`,
SHA-256 `4bc0b513e9b6a630159212452ff3fc70b86d89c6ef63f6ea92ae075599e65303`.
기존 검증 자원을 재사용했다. NN 품질·실제 AI 품질 시험은 하지 않았다.

## 5. 잠금 계측

`test_vector_work_contention::test_large_shared_lineage_keeps_writer_free_and_final_effect_short`
는 실제 파일 WAL, 64개 합성 기억의 공통 prior DAG, 실제 Vec1 확장, fake embedding을 사용한다.
같은 자료와 현재 source validator를 대상으로 **예전처럼 깊은 조회를 writer 안에 넣은 형태**와
새 최종 반영 구간을 각각 20회 측정했다. 과거 제품 실행 전체를 재현했다고 표현하지 않는다.

| 구간 | p50 | p95 | max | canonical SQL/구간 |
| --- | ---: | ---: | ---: | ---: |
| 깊은 검사를 writer 안에서 수행한 비교 형태 | 181.949ms | 233.507ms | 249.115ms | 385 |
| 새 final fence (실제 claim 검사 포함) | 6.217ms | 10.764ms | 11.818ms | 9 |

- 깊은 source snapshot을 Event로 정지시킨 동안 **실제 scheduler heartbeat 저장 성공**.
- 동일 벡터 재사용 및 20회 no-op 비교에서 provider 호출은 최초 합성 호출 1회뿐.
- canonical 기본 admission 250ms는 늘리지 않았다. Vec1 write admission은 25ms.
- final 구간에 source traversal이 없음을 SQL로 단언. 시간 SLA/sleep으로 통과시키지 않았다.
- 기존 운영 조사 약 878ms와 위 수치는 자료가 다르므로 직접 비율 비교하지 않는다.
- 로컬 증거: `artifacts/vector-pending-work-20261016/lock-metrics.json`.

## 6. 최종 실행 결과

아래는 이 변경과 연결된 로컬 검증만 선택한 결과다. 반복 실행 건수를 합산하지 않는다.

| 검증 묶음 | 결과 | 로컬 JUnit 기록 |
| --- | --- | --- |
| durable work·source 경합·batch·generation·실제 Vec1·삭제·resource | 51 PASS | `vector-regression.xml` |
| v39 populated upgrade·rollback·Alembic·registry·구버전 chain·삭제 inventory | 38 PASS | `migration-regression.xml` |
| 권한·source lineage·상황기억·SQLite 복구·scheduler·World 원본 보존 | 49 PASS | `policy-recovery.xml` |
| 최종 worker 변경 후 pending/recovery/batch/preparation/lifecycle 재확인 | 34 PASS | `final-worker-regression.xml` |
| 실제 WAL/Vec1 경합과 writer 계측 | 2 PASS | `contention.xml` |
| 현재 L4/hybrid inventory | 4 PASS | `current-inventories.xml` |
| schema mapper 수·typed datetime·v37 fixture 재검증 | 3 PASS | `final-schema-resource.xml` |
| 격리 predecessor fixture v1/v37 및 새 v38 | 3 PASS | `fixture-predecessors.xml`, `fixture-v38.xml` |

JUnit과 잠금 계측은 `artifacts/vector-pending-work-20261016/`에 보존한다. 기존 pytest의
raw sqlite datetime adapter 경고는 시험 fixture를 ORM typed update로 고쳤고 해당 node를
`-W error::DeprecationWarning`으로 재검증했다. 이전 실패/경고 파일도 삭제하지 않았다.

새 스키마의 6개 표가 과거 버전 fixture에 남는 오류를 발견해, 격리 fixture에서만 v39 trigger와
작업 표를 먼저 제거하도록 수정했다. 배포용 forward migration이나 과거 manifest는 바꾸지 않았다.
새 현재 버전에 맞춰 지원 predecessor에 v38을 추가했다. 실제 설치 검증 실행과는 별도다.

현재 architecture import inventory와 경계 검사, embedded migration 계약(`BASE_SHA=117dd3f7`),
Windows supported predecessor 목록 검사, `compileall` 및 `git diff --check`를 통과했다.
과거 frozen manifest/inventory는 유지하고 현재 L4/hybrid inventory만 갱신했다.

전체 backend/frontend corpus, 원격 CI,
실제 설치 파일 생성, Docker 재배포, 유료 AI 실행은 이 작업의 검증 범위가 아니다.
공개 API 및 사용자 문구를 추가/수정하지 않아 frontend·KO/EN 검증은 변경 없음으로 N/A다.
