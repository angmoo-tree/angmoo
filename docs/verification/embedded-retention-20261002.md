# SNS 체크포인트 24시간·canonical DB 2세대 보존 구현 검증

## 범위와 상태

2026-10-02, `feat/0.1.0-release-readiness`의 기존 checkout에서 통합 계획 P00–P14를 수행한다. main 분기 기준은 `8e6e89d69bd9e98938ef587adfc143bc3fc1ec40`, 기존 Gemini 진단을 포함한 작업 시작 기준은 `f90f8109cc58486f73e2037fee1c5e91a4d6fdc6`다. 기존 진단 파일 6개·frontend·역사 migration·schema·원본 보존 baseline을 변경하지 않는다.

원격 이슈는 [#358](https://github.com/angmoo-tree/angmoo/issues/358)이다. 제품 코드·회귀·운영 설명의 최초 로컬 구현 커밋은 `f8b92db9fc99710e17646dc5b532d7edb427d9e8`이다. 최종 전체 회귀와 보존 검사는 아직 진행 중이며, 이 최초 기록을 전체 완료 보고로 해석하지 않는다. 최종 결과는 아래 검사 결과에 추가한다.

원본 계획은 workspace의 `docs/plan/10-01 SNS 체크포인트 24시간·DB 자동 사본 2세대 보존 통합 코드 구현 세부 계획.md`다. [운영·보호·비활성화 계약](../operations/embedded-retention.md)에 실제 구현의 동작을 설명한다. 새 UI·의존성·schema·별도 정리 서버는 추가하지 않는다.

## 실제 구현

신규 V2 활동 생성 transaction에서 typed policy를 동결한다. 검증된 canonical 완료 결과는 graph·binding·Provider보다 먼저 재사용한다. 완료 결과의 읽기 권한·World·owner·engine/contract·lane/receipt 정합성을 확인하고 내부 정책 필드를 응답에서 제거한다. 잘못된 terminal 결과는 새 실행으로 대체하지 않는다. canonical Finalize commit 이후 SDK 저장 실패도 완료 상태를 덮어쓰지 않는다.

최종 graph snapshot의 next/tasks와 결과까지 확인한 신규 completed/observed 활동만 24시간 경과 후 상세 정리 대상으로 삼는다. 유효 lease·미확정 child·pending 공개 효과·활동 claim·이미지 결과 저장/첨부 복구 의존은 보호한다. startup 1회와 이후 시간당 cycle은 별도 Session·connection·OS lock으로 실행한다. batch 50, 후보 500 또는 새 작업 시작 예산 5초이며 이미 실행 중인 SQL을 강제로 끊지 않는다. `adelete_thread` 전 claim commit과 이후 mark commit을 분리하고 busy/mark 실패를 같은 정리의 재시도로 남긴다.

새 clean DB 또는 실제 migration staging을 생성할 때만 typed ownership을 남긴다. 정상 backup·forward migration·검증·finalize·promotion·승격 후 검사·graph 처리·engine 종료·secret/media 확인 뒤 승격을 확정한다. serving owner가 공유 upgrade OS lock 안에서 current/previous와 실제 use pin을 보호하고, known manifest와 정확한 path·파일 목록을 확인한 신규 obsolete 세대만 제거한다. 외부 removal intent를 먼저 기록하므로 부분 제거도 같은 후보를 마무리할 수 있다.

contributor와 sidecar는 같은 coordinator/composition을 사용한다. engine 전에 use pin을 등록하며 worker와 engine이 닫힌 뒤 해제한다. 부분 시작 실패는 자원을 정리한다. worker 종료를 확인하지 못하면 engine을 참조하는 소비자의 수명 동안 OS pin을 유지한다. diagnostics·installer·직접 coordinator는 삭제 권한이 기본 OFF다. generation 정리는 startup에서만 실행하며 같은 schema 재시작에는 추가 copy/migration을 하지 않는다.

## 검사 파일과 행렬

아래 약칭은 추적된 테스트 파일을 가리킨다.

- **CR**: `backend/tests/runtime/test_checkpoint_retention.py`
- **CM**: `backend/tests/runtime/test_checkpoint_maintenance.py`
- **GR**: `backend/tests/migrations/test_canonical_retention.py`
- **RL**: `backend/tests/runtime/test_retention_lifecycle.py`
- **EM**: 기존 `backend/tests/test_embedded_data_migration.py`와 `test_embedded_data_migration_contract.py`

| SNS ID | 실제 검사 |
| --- | --- |
| S01 | CR `test_creation_marks_once_and_setting_changes_never_backfill`, `test_ambiguous_or_legacy_is_preserved`, `test_sdk_deletes_all_namespaces_and_writes_but_preserves_legacy` |
| S02 | CR `test_utc_retention_boundary`, `test_completed_same_id_ten_reads_need_no_binding_lease_or_provider` |
| S03 | CR `test_incomplete_or_failed_is_preserved`의 상태별 parameter |
| S04 | CR `test_ambiguous_or_legacy_is_preserved`의 시각·policy·결과 parameter |
| S05 | CM `test_recovery_lease_different_id_and_pending_effect_protect` |
| S06 | CR `test_sdk_deletes_all_namespaces_and_writes_but_preserves_legacy`: 실제 SDK root/child/writes, 별도 legacy thread |
| S07 | CR `test_completed_same_id_ten_reads_need_no_binding_lease_or_provider`: 공식 maintenance 뒤 같은 결과·시각·usage·receipt, 추가 Provider/effect/intent 0 |
| S08 | CR `test_finalize_commit_survives_last_checkpoint_failure`: production graph의 마지막 SDK write 주입 |
| S09 | CR `test_mark_failure_is_idempotent_and_never_reexecutes_business`, RL 같은 root 두 정리 실패 검사 |
| S10 | CM lease/pending receipt·backup lock, RL `test_received_image_and_attachment_recovery_protect_then_release_checkpoint`: 실제 image worker와 fake Provider 1회 |
| S11 | CR `test_terminal_bad_scope_or_result_never_constructs_graph`의 owner/World/contract/paths/receipt parameter |
| S12 | CM `test_startup_idle_periodic_and_two_root_isolation`, RL 실제 lifespan 시작 순서 |
| S13 | CM `test_protected_candidate_cursor_advances_past_full_batch`, `test_start_budget_finishes_active_delete_and_defers_next_target` |
| S14 | CM A/B/C 동시 write/lease/효과·5 MiB thread, checkpoint busy·cancel·reload·backup·두 maintenance owner, RL 종료 미확정 pin |
| S15 | CM `test_100_activities_over_virtual_days_limits_detail_blobs`: 10일·100건·legacy 30일과 신규 24시간 비교 |

| DB ID | 실제 검사 |
| --- | --- |
| G01 | GR `test_real_historical_upgrade_chain_21_legacy_generations_and_ten_restarts`: 21 legacy bytes/hash 불변 |
| G02 | 동일 검사: 실제 populated schema 1→23→24→25→26 backup/upgrade, 신규 managed current/previous만 2개 |
| G03 | GR `test_clean_creation_marked_but_existing_marker_recovery_is_not_backfilled` |
| G04 | 10회 동일 schema startup, canonical snapshot 불변·migrated false, intent 실패 검사에서 backup 호출 시 실패하도록 검증 |
| G05 | GR `test_upgrade_failure_preserves_source_and_unconfirmed_final`: source fingerprint/검증 실패, EM staging 실패 회귀 |
| G06 | GR finalize/promote/post-validation fault parameter: source·미확정 final 보호 |
| G07 | GR `test_previous_replacement_then_current_failure_preserves_all_generations`, malformed/동일 marker 검사 |
| G08 | GR 실제 use pin·unreadable pin, RL 진단과 serving lifetime·종료 미확정 보호 |
| G09 | GR `test_partial_removal_intent_retries_without_new_copy_or_promotion`, `test_removal_intent_write_failure_defers_without_copy_or_startup_failure` |
| G10 | GR path traversal·unknown file·bad ownership/digest/schema·Windows junction 검사 |
| G11 | GR `test_reparse_generation_is_refused_and_wal_lifetime_is_whole_directory`: closed obsolete fixture의 DB/WAL/SHM을 같은 세대로 제거 |
| G12 | GR subprocess OS owner 충돌·crash 후 pin 확인, diagnostics 권한 OFF, RL 실제 factory pin |
| G13 | canonical 직접 자식·known file 목록 외에는 정리하지 않음. EM graph degraded/previous 보존 회귀와 GR canonical snapshot 검증 |
| G14 | GR populated identity·secret/media hash·FK/integrity, EM 모든 역사 manifest/expected delta 회귀 |
| G15 | GR 4회 전환·10회 재시작·pin 해제 후 정리, legacy/managed bytes와 미확정 예외 분리 |

| 통합 ID | 실제 검사 |
| --- | --- |
| X01–X02 | RL `test_same_root_generation_and_checkpoint_failures_preserve_completed_result`: 같은 root 실제 graph 결과·DB backup·두 독립 fault·같은 ID 재사용·copy/Provider 추가 0 |
| X03 | RL contributor/sidecar serving·pre-server 준비 실패, EM 두 entrypoint 공통 coordinator |
| X04 | RL startup 부분 실패·정상 수명·종료 미확정 보호, CM SDK I/O cancel/reload·backup lock |
| X05 | branch/ancestry·기존 진단 diff·frontend/migration 무변경, 사용자 Docker ID·image·mount·health를 read-only 확인 |

| 원본/통합 계약 | 대응 근거 |
| --- | --- |
| C01 / I01 | S01·G01·G03, 생성 시 태그만 기록 |
| C02–C04 / I02 | S02–S05·S08·S10, typed completion/graph/lease/receipt/이미지 복구 보호 |
| C05–C06 / I03 | S07·S11, binding/lease/Provider 없는 완료 읽기와 scope 검증 |
| C07–C08 / I04 | S06–S09·S15, 공개 SDK 삭제와 canonical 업무·사용량·예약 보존 |
| C09–C10 / I05 | S08–S14, 실패 분리·동일 정리 재시도·SDK/본문/Provider 계약 유지 |
| D01–D02 / I01 | G01·G03, actual creation provenance와 no backfill |
| D03–D04 / I06 | G02·G06–G08·G12, marker/use pin/staging/미확정 보호 |
| D05·D10 / I07 | G05–G07·G13–G14, EM 역사 migration/graph degraded 보존 |
| D06·D09 / I08 | G04·G09·G15·X02, 동일 schema·정리 fault는 복제/승격 이유가 아님 |
| D07–D08 / I09 | G10–G11, 정확한 소유 세대·reparse/unknown file/WAL 보호 |
| I10 | G08·G12·X03, OS serving owner와 use pin, 진단/installer 기본 OFF |
| I11 | X01–X04·S14, 동일 root·별도 실패·다중 캐릭터 실제 진행/효과 보존 |
| I12 | 전 검사 임시 DB·합성 파일·fake Provider, 실제 사용자 적용/유료 API/CI 분리 |

## 로컬 실행 결과

증거 root는 `D:/project_code/angmoo-workspace/.local-diagnostics/retention-integration-20261002/20261002T053222Z`다. 이 경로의 임시 DB·XML·log는 로컬 증거이며 clone에 포함하지 않는다. 공개 가능한 요약과 재현 테스트는 이 문서·추적 코드에 남긴다.

- 수정 전 관련 baseline: **40 PASS** (`baseline-suite.xml`).
- 완료 canonical 우선 읽기 관련: **12 PASS** (`completion-first.xml`).
- 기존 factory·contributor import·sidecar: **30 PASS** (`lifecycle-existing.xml`), 기존 FastAPI deprecation 2건.
- 중간 통합: **56 PASS / 1 fixture FAIL** (`retention-contract-suite.xml`). 닫힌 세션의 credential 재사용 fixture를 새 Session 기준으로 고쳐 후속 lifecycle에서 재통과했다.
- 확장 lifecycle: **13 PASS / 2 fixture FAIL** (`lifecycle-final.xml`). sidecar fixture의 origin을 기존 정책이 허용하는 `http://tauri.localhost`로 수정했다. 실제 origin 보안 정책은 변경하지 않았다.
- origin 및 strict marker/ownership 재검사: **12 PASS** (`strict-safety-corrections.xml`).
- marker 교체 중간 실패·intent write 실패·canonical busy/두 maintenance owner 추가 검사: **3 PASS** (`retention-failure-supplements.xml`).
- 기존 sidecar logging/실제 HTTP handshake 검사: 최초 fixture의 새 disposer 누락을 보완하고 **1 PASS** (`sidecar-logging-correction.xml`). 원래 health·shutdown·stdout/stderr 단언을 유지하고 disposer 1회 단언을 추가했다.
- 전체 backend: **진행 중** (`backend-full.xml`·`backend-full.log`).
- 현재 import inventory·architecture boundary: **PASS**, 1,338 modules / 5,435 internal edges / 3,959 external imports / legacy exact edges 0.
- 현재 L4 inventory는 추가된 4개 제품 모듈·현재 dependency 수치만 generator로 갱신했다. Memory owner-control/deferred runtime inventory는 현재성 검사 PASS다. 원본 checkpoint·source baseline·과거 manifests는 바꾸지 않는다.
- 원래 preservation checker의 factory 지적은 사용자 승인 계획에 따른 `create_app` optional owner와 shared lifespan 변화의 정확한 committed before/after AST로 기록한다. 신규 파일/node는 공식 immutable capture 도구로 append한다. 기존 기록은 덮어쓰지 않고, checker 조건·assertion·skip을 약화하지 않는다. 최종 원래 checker PASS는 아직 확인 중이다.

초기 새 fixture에서 잘못된 World FK 변경, Windows path separator 비교, PostLike 필수 user_id 누락을 수정했고 해당 검사 재통과를 확인했다. 이 초기 실패는 제품 코드의 실패를 무시하거나 기존 테스트의 기대값을 약화해 처리한 것이 아니다.

## 비교 workload

최종 전체 회귀에서 다시 기록한 수치를 아래에 확정한다. 현재 중간 통합 실행의 측정은 다음과 같다.

| 지표 | 정리 OFF/legacy 30일 | 신규 24시간/정리 ON |
| --- | --- | --- |
| 100개 만료 완료 활동 + 보호 실패 1개, checkpoint rows | 201 | 1 |
| writes rows | 201 | 1 |
| 상세 BLOB bytes | 13,145,183 | 1,383 |
| 동일 SQLite physical bytes | 13,377,536 | 13,377,536 |
| A/B/C 동시 활동 완료 시간 | 0.493 s | 1.109 s |
| 최대 canonical write 대기 포함 시간 | 0.107 s | 0.248 s |
| p95 write 시간 | 0.081 s | 0.186 s |
| 최대 tick/lease 간격 | 0.167 s | 0.277 s |

A/B/C는 각각 8단계의 실제 LangGraph checkpoint·canonical write·lease 갱신을 수행하고 fake 모델은 각각 1회, 실제 공개 효과/receipt는 총 3개였다. ON에서는 별도 만료 thread 20개와 5 MiB thread 1개를 정리했다. 취소·실패·중복 효과·추가 모델 호출 없이 사전에 정한 bound를 통과했다. 이는 실제 유료 모델의 지연이나 사용자 자연 활동 품질 측정이 아니다. 정리 부하는 0이 아니며 OFF 대비 지연 수치도 함께 남긴다.

DB workload는 기존 21 legacy 세대의 30,535,680 bytes를 유지하고 신규 managed 세대는 current/previous 2개·4,853,760 bytes였다. 동일 schema 10회 재시작은 10.360 s였으며 copy/migration/새 generation 0, canonical snapshot·legacy hash·secret/media·identity·FK/integrity 불변을 확인했다. 전체 폴더 수는 legacy 21개를 더하므로 2개로 줄었다고 보고하지 않는다.

## 사용자 실행 환경과 후속

사용자가 watch를 종료하고 watch 없는 `docker compose -f compose.yml -f compose.dev.yml up --build`로 실행했다. 해당 환경을 read-only로 확인한 backend `6321e8d7ab35`와 frontend `3b88fad2e888`의 image·mount·health를 유지한다. 서버 재시작/rebuild·volume exec 테스트·실제 사용자 DB 읽기/삭제·설치 앱 갱신을 하지 않는다. 실제 설치된 Windows Angmoo의 물리 identity·버전을 주장하지 않는다.

이 작업은 원격 이슈 생성 외에는 로컬 구현·검사·커밋만 허용한다. push·PR 생성/수정·Hosted CI dispatch/retry·main 병합은 하지 않는다. 기존 Gemini 진단 커밋과 main 기준 SHA를 보존한다.

적용은 사용자 요청으로 backend에 이 코드를 build/restart한 뒤 실제 startup을 확인하는 별도 작업이다. 기존 21세대와 legacy checkpoint를 이번 정책으로 소급 제거하지 않는다. Windows 적용 확인에는 workspace의 설치 identity helper가 먼저 필요하다.

문제가 생기면 `SNS_CHECKPOINT_MAINTENANCE_ENABLED=false`, `CANONICAL_GENERATION_RETENTION_ENABLED=false`로 정리만 중지한다. 신규 태그 중지는 `SNS_CHECKPOINT_POLICY_ENABLED=false`다. 완료 canonical reader·ownership/use pin 해석은 유지한다. 삭제된 상세/obsolete 세대의 자동 복원을 보장하지 않는다. current/previous marker를 자동 과거 전환하지 않는다.

후속 범위는 실제 Docker/Windows 적용·USER CHECK, 자연 활동 지연 관측, 필요 시 별도 승인한 legacy 정리·SQLite VACUUM/VHDX 축소다. 실제 API 키·유료 생성/인식 검사는 이번 보존 정책 검증에 필요하지 않으며 수행하지 않는다. row/BLOB 감소와 파일/VHDX·호스트 여유 공간 회수는 별개다.
