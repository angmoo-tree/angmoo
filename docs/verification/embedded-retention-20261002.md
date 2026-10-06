# SNS 체크포인트 24시간·canonical DB 2세대 보존 구현 검증

## 범위와 상태

2026-10-02, `feat/0.1.0-release-readiness`의 기존 checkout에서 통합 계획 P00–P14를 수행한다. main 분기 기준은 `8e6e89d69bd9e98938ef587adfc143bc3fc1ec40`, 기존 Gemini 진단을 포함한 작업 시작 기준은 `f90f8109cc58486f73e2037fee1c5e91a4d6fdc6`다. 기존 진단 파일 6개·frontend·역사 migration·schema·원본 보존 baseline을 변경하지 않는다.

원격 이슈는 [#358](https://github.com/angmoo-tree/angmoo/issues/358)이다. 제품 코드·회귀·운영 설명의 최초 로컬 구현 커밋은 `f8b92db9fc99710e17646dc5b532d7edb427d9e8`, 최종 제품 수정 커밋은 `351342def1a23bdc85ed0310ff3691accb3d8442`다. 두 번의 전체 backend 실행은 각각 **4,674 PASS / 3 FAIL / 52 SKIP**, **4,673 PASS / 4 FAIL / 52 SKIP**로 종료했다. 후속 보완·원본 재검사를 합친 현재 case별 결과는 **4,678 PASS / 52 기존 SKIP / 잔여 FAIL 0**이지만, 이를 한 번의 전체 실행이 모두 통과한 결과로 표현하지 않는다. 새 보존 계약 검사는 현재 **75 PASS**이며, 기존 SQLite 동시성의 간헐 실패 안정성은 별도 한계로 남긴다. 신규 predicate 출처 기록 이후 원래 보존 CLI의 최종 결과는 **PASS**다. P00–P14의 실행·구현·계약별 검증·문서화·로컬 커밋 작업과, 계획 §16.7의 안정적인 전체 회귀 PASS에 따른 엄밀한 전체 완료 판정을 구분한다. 후자는 보류한다.

원본 계획은 workspace의 `docs/plan/10-01 SNS 체크포인트 24시간·DB 자동 사본 2세대 보존 통합 코드 구현 세부 계획.md`다. [운영·보호·비활성화 계약](../operations/embedded-retention.md)에 실제 구현의 동작을 설명한다. 새 UI·의존성·schema·별도 정리 서버는 추가하지 않는다.

## 실제 구현

신규 V2 활동 생성 transaction에서 typed policy를 동결한다. 검증된 canonical 완료 결과는 graph·binding·Provider보다 먼저 재사용한다. 완료 결과의 읽기 권한·World·owner·engine/contract·lane/receipt 정합성을 확인하고 내부 정책 필드를 응답에서 제거한다. 잘못된 terminal 결과는 새 실행으로 대체하지 않는다. canonical Finalize commit 이후 SDK 저장 실패도 완료 상태를 덮어쓰지 않는다.

최종 graph snapshot의 next/tasks와 결과까지 확인한 신규 completed/observed 활동만 24시간 경과 후 상세 정리 대상으로 삼는다. 유효 lease·미확정 child·pending 공개 효과·활동 claim·이미지 결과 저장/첨부 복구 의존은 보호한다. startup 1회와 이후 시간당 cycle은 별도 Session·connection·OS lock으로 실행한다. batch 50, 후보 500 또는 새 작업 시작 예산 5초이며 이미 실행 중인 SQL을 강제로 끊지 않는다. `adelete_thread` 전 claim commit과 이후 mark commit을 분리하고 busy/mark 실패를 같은 정리의 재시도로 남긴다.

새 clean DB 또는 실제 migration staging을 생성할 때만 typed ownership을 남긴다. 정상 backup·forward migration·검증·finalize·promotion·승격 후 검사·graph 처리·engine 종료·secret/media 확인 뒤 승격을 확정한다. serving owner가 공유 upgrade OS lock 안에서 current/previous와 실제 use pin을 보호하고, known manifest와 정확한 path·파일 목록을 확인한 신규 obsolete 세대만 제거한다. 외부 removal intent를 먼저 기록하므로 부분 제거도 같은 후보를 마무리할 수 있다.

contributor와 sidecar는 같은 coordinator/composition을 사용한다. engine 전에 use pin을 등록하며 worker와 engine이 닫힌 뒤 해제한다. 부분 시작 실패는 자원을 정리한다. worker 종료를 확인하지 못하면 engine을 참조하는 소비자의 수명 동안 OS pin을 유지한다. diagnostics·installer·직접 coordinator는 삭제 권한이 기본 OFF다. generation 정리는 startup에서만 실행하며 같은 schema 재시작에는 추가 copy/migration을 하지 않는다.

| 실제 소비자 | 사용·보호 경계 | 삭제 권한 |
| --- | --- | --- |
| contributor / sidecar serving startup | 실제 root의 OS serving owner, 공통 coordinator의 migration lock, composition의 engine 이전 use pin | 설정 ON이며 실제 owner가 확인된 startup만 허용 |
| SNS·Chat·image worker·요청 Session | composition engine을 공유하며 worker 종료·engine dispose 전까지 pin 보호. 종료 불확실 시 engine 수명 동안 유지 | 업무 consumer 자체에는 없음 |
| canonical backup·migration·승격 검증 | 기존 공통 upgrade lock 안에서 임시 engine·SQLite backup과 검증 수행, 닫힌 뒤 보존 판단 | coordinator의 명시적인 serving owner에만 따름 |
| diagnostics / direct runtime factory | 같은 composition use pin으로 실제 engine을 보호 | 기본 OFF |
| installer WAL checkpoint / 후속 preflight | 선택한 generation pin을 성공·예외 종료까지 유지. 버전 preflight는 marker를 읽고 legacy fallback만 read-only SQLite 검사 | OFF |
| checkpoint backup | canonical 세대와 별개인 saver DB의 root maintenance OS lock을 공유 | canonical 세대 삭제와 무관 |

installer 작업 중 실제 두 새 세대를 승격시키는 검사에서 선택한 원 DB가 보호되는 것을 확인했다. 정상·예외 종료 뒤 pin을 해제하고 다음 serving 정리에서만 제거한다. 잘못된 previous marker의 타입은 retention 경계에서 안전한 연기로 처리한다. 기존 generation 선택 reader·승격 순서를 교체하거나 손상 marker를 재작성하지 않는다.

serving owner는 기존 typed `RuntimeConfig`의 내부 선택 필드로 전달한다. `create_app`의 기존 공개 인자·기본값은 그대로 유지한다. owner 필드는 repr/비교에서 제외하며 Settings·health·runtime metadata에 직렬화하지 않는다. 삭제 허용은 필드 존재만으로 결정하지 않고 실제 root·OS 소유권·프로세스 시작 식별자가 일치하는 `permits` 검사로 판단한다. generation pin은 정상적인 직접 composition의 아직 생성되지 않은 안전한 경로에도 engine 이전에 등록할 수 있다. pin 등록 자체가 DB 생성·migration·ownership 표시·삭제 권한을 부여하지 않으며 path traversal/reparse 검사는 유지한다.

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
| S14 | CM A/B/C 동시 write/lease/효과·5 MiB thread, `test_three_characters_sdk_busy_cleanup_finishes_without_reexecution`의 SDK busy 1회·다음 cycle 완료·실행 중 checkpoint 보존, cancel·reload·backup·두 maintenance owner, RL 종료 미확정 pin |
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
| G08 | GR 실제 use pin·unreadable pin, RL 진단과 serving lifetime·종료 미확정 보호 및 `test_installer_checkpoint_consumer_pins_selected_generation_without_retention_authority`의 성공/예외 parameter |
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
- 공개 factory signature를 복원한 `351342de` 이후 전체 실행은 위 handshake fixture가 반환하던 일반 `object()`에서 `dataclasses.replace` 타입 오류를 확인했다 (`sidecar-final-failure.xml`, 단독 재현 **1 FAIL**). 제품의 실제 builder는 typed `RuntimeConfig`를 반환한다. fixture도 공식 builder와 임시 TEST root·합성 secret을 사용하도록 보완한 뒤 해당 로그 파일 전체 **15 PASS** (`logging-typed-final.xml`)를 확인하고 `1381fe2caa3286ea05ee07ce424b4ee3dbc4bf87`에 로컬 커밋했다. 기존 health·shutdown·endpoint 제거·무출력 단언과 15초 watchdog을 유지했다. 검사 시작 이후 제품 코드는 바꾸지 않았고, 이 test fixture만 보완했다. 이미 실행한 이전 fixture의 실패는 전체 실행 결과에서 숨기지 않는다.
- installer의 선택 세대 pin 성공·예외 경계: **2 PASS** (`installer-use-pin-final.xml`). 초기 새 fixture의 legacy root·합성 secret 준비 오류를 수정했고 installer 제품 정책을 완화하지 않았다.
- selection record 타입 경계: 추가 재현에서 **1 PASS / 1 FAIL** (`selection-shape-regression.xml`). 기존 reader가 잘못된 previous schema 타입에 `TypeError`를 내는 것을 확인했다. 보존 정리 경계에서 안전한 연기로 변환한 뒤 손상/불명확한 기록 **11 PASS** (`selection-shape-final.xml`).
- 전체 검사에서 발견한 기존 Memory 비용 경계는 동일한 제한값으로 단독 재검사하여 **1 PASS** (`memory-cost-regression.xml`). Memory 코드·fixture·성능 제한을 변경하지 않았으며 최종 전체 실행 결과는 아래에 별도 기록한다.
- 기존 runtime composition 회귀에서 새 pin이 아직 없는 generation 디렉터리를 요구하여 **5 FAIL / 35 PASS**가 발생했다 (`typed-owner.xml`). 이는 제품 호환 문제로 수정했다. 실제 안전 경로에 engine 이전 pin 등록을 허용한 뒤 기존 runtime·sidecar 보안과 serving 경계 **40 PASS** (`typed-owner-final.xml`), 미래 경로 pin/경로 탈출/WAL 수명 경계 **2 PASS** (`preopen-pin.xml`)를 확인했다.
- 최초 전체 backend 실행은 수정 전 모듈 snapshot과 알려진 실패를 포함하여 76%에서 중지했다 (`backend-full.log`). 완료 PASS로 합산하지 않는다. 최종 코드를 동결하여 전체 backend를 다시 실행하고 결과를 아래에 기록한다.
- 현재 import inventory·architecture boundary: **PASS**, 1,338 modules / 5,435 internal edges / 3,962 external imports / legacy exact edges 0.
- 현재 L4 inventory는 추가된 4개 제품 모듈·현재 dependency 수치만 generator로 갱신했다. 현재 Memory inventory도 정책·default·bounds·schema·embedding·frozen predecessor 불변을 확인하고, config/contributor 파일 hash 2개 및 신규 canonical 회귀 파일 1개만 반영했다 (`memory-inventory-review.json`). deferred runtime inventory는 25파일의 현재성 검사 PASS다. 원본 checkpoint·source baseline·과거 manifests는 바꾸지 않는다.
- 전체 회귀의 ER0 검사에서 현재 `embedded-runtime-inventory.json`의 main.py hash 2곳이 이전 값을 유지하던 것을 확인했다. 공식 generator의 현재 출력으로 그 2곳만 갱신했다 (`er0-inventory-review.json`, `cd06f2f62f71781e9858525ff06b94a059b49bc7`). 나머지 JSON 필드·다른 생성 출력·baseline commit·parity oracle·역사 자료는 불변이다. ER0 및 SQLite 동시성 파일 전체 **18 PASS** (`er0-concurrency-final.xml`), scheduler 단독 재검사 **1 PASS** (`new-full-failures.xml`의 다른 1건은 수정 전 stale inventory FAIL)를 확인했다. scheduler·concurrency 제품 코드와 기존 fixture·시간 제한은 변경하지 않았다. 전체 실행의 동시성 실패 상세와 최종 합산은 아래에 별도로 기록한다.
- 공개 `create_app` signature에는 보존 예외를 두지 않는다. 기존 lifecycle chain과 최초 구현의 정확한 인접 커밋 정의, 제거된 30일 prune, contributor/sidecar 준비 helper의 optional owner, saver의 optional busy timeout을 검증했다 (`factory-provenance-final.json`). 신규 파일/node는 공식 capture 도구로 기존 318개 record 뒤에 3개 record만 append했다. product contract 기록은 원래 118개 prefix 뒤에 보존 기능 2개 및 기존 Gemini 진단 1개, 총 3개 exact record를 추가했다. 출처 hash는 구현 커밋의 실제 postimage이며 before AST는 그 부모 커밋이다. 잘못 작성했던 미게시 증거 커밋 2개는 로컬 bundle/patch로 보존하고 그 증거만 교정했으며 제품·사용자·main 커밋은 유지했다. checker 조건·기존 assertion·skip은 약화하지 않는다. 최종 원래 checker 결과는 아래에 별도 기록한다.
- 보존 검사 `preservation-final-corrected.log`는 수집 **4,729개**를 모두 보호했으며 기존 시작 커밋 `f90f8109`의 진단 콜백 단언 1곳만 지적했다. 원래 `len(received) == len(evidence) == 1`이 `len(received) == 1`과 정확한 `sdk_input → sdk_response` 순서로 바뀐 기존 변경이다. SDK 요청 수·기존 입력/개인정보 단언은 유지한다. 두 실제 커밋의 test/Provider 정의와 완전한 단언 목록으로 기록했으며 본 작업은 해당 6개 Gemini 파일을 수정하지 않았다. 기존 Provider adapter **29 PASS** (`gemini-baseline.xml`)가 요청·콜백 실패·응답 메타데이터·비공개 본문 배제를 확인한다. 이 기록은 WIP 진단의 main 반영이나 실서비스 품질 승인이 아니다.
- 최종 **원래 CLI의 `--contracts --nodes` 보존 검사 PASS** (`preservation-final.log`): PR258 1,867개·PR263 1,907개 frozen node와 보호 lineage 4,729개를 유지하고, 현재 수집 4,729개 및 보존 항목 37개를 확인했다. API·ORM·정확한 인접 커밋 출처를 포함한 검사다. checker 구현과 역사 baseline은 변경하지 않았다.
- typed logging fixture 보완 이후 같은 원래 CLI도 다시 **PASS** (`preservation-fixture-final.log`, 4,729개 lineage / 37개 항목). fixture 보완이 기존 단언·API·ORM·출처 계약을 약화하지 않았음을 확인했다. 보완 이후 제품 코드 추가 변경은 없다.

초기 새 fixture에서 잘못된 World FK 변경, Windows path separator 비교, PostLike 필수 user_id 누락을 수정했고 해당 검사 재통과를 확인했다. 이 초기 실패는 제품 코드의 실패를 무시하거나 기존 테스트의 기대값을 약화해 처리한 것이 아니다.

### 전체 회귀와 후속 재검사

`backend-final.xml`의 완료된 전체 실행은 4,729개 수집, **4,674 PASS / 3 FAIL / 52 SKIP / 0 ERROR**, pytest wall time 5,899.60초다. 새 보존 계약의 네 파일은 **74 PASS / 0 FAIL / 0 SKIP**이며 GR 24개·CM 8개·CR 26개·RL 16개다. 전체 실행의 실패는 typed logging fixture, 현재 ER0 source hash, 기존 scheduler 동시성 검사였으며 위 개별 보완·재검사와 구분한다.

52 SKIP은 기존 명시적 performance 6개, public profile 밖 hosted lifespan 1개, 실 Vec1 extension 미제공 21개, PostgreSQL 외부 환경 미제공 21개, 사용자 원본 선택 fixture 미제공 3개다. 새 보존 계약에 skip을 추가하지 않았고 기존 수집·assertion·시간 제한을 줄이지 않았다.

기존 scheduler 검사는 `BEGIN IMMEDIATE`에서 `SQLITE_BUSY` 후 1회의 bounded attempt로 끝난 실패가 전체 실행과 첫 단독 재검사에서 재현됐다 (`scheduler-repeat-1.xml`). 해당 engine은 별도 임시 DB이며 새 maintenance worker가 실행되지 않았다. 이 검사 및 SQLite writer·database·lease의 제품 파일 4개는 작업 시작 커밋과 동일하다. 이후 원래 검사 파일을 포함한 ER0/동시성 회귀 18개와 수정 없는 단독 실행 세 번 (`scheduler-repeat-2.xml`–`scheduler-repeat-4.xml`)은 통과했다.

별도 로컬 진단은 실제 `run_sqlite_immediate` observer와 engine event로 연결 준비/transaction 경계를 관찰했다. 계측 실행 아홉 번은 통과했으며 연결 생성 이후의 쓰기 완료 총 시간이 167–295 ms인 실행도 있었다. 실패 실행의 해당 상세 timing을 포착하지 못했으므로 연결 준비가 확정 원인이라고 단정하지 않는다. 계측이 thread scheduling에 영향을 줄 수 있어 원래 검사 PASS와 구분한다. prewarm·재시도 상한 변경·BUSY를 정상 loser로 처리하는 변경·skip으로 우회하지 않았다. 250 ms retry 정책과 기존 10명 중 정확히 1명/만료 후 fencing epoch/옛 owner heartbeat 거절 단언은 그대로다.

두 보완 뒤 확인용 전체 실행의 기준은 `cd06f2f6`, 출력은 `backend-confirmation.log`와 `backend-confirmation.xml`이다. **4,729개 수집 / 4,673 PASS / 4 FAIL / 52 SKIP / 0 ERROR**, pytest wall time 6,201.83초로 종료했다. 실패 4건은 아래 보완 전 새 workload 1건과 기존 SQLite 동시성 3건이다. 진행 중 결과나 단독 PASS를 단일 전체 PASS로 표현하지 않는다.

확인 실행에서는 새 CM workload가 첫 cycle에서 21건 모두 정리해야 한다는 fixture 단언을 발견했다. 별도 재현 (`workload-diagnostic.xml`)은 A/B/C가 모두 Finalize 완료, 20건 pruned·1건 claimed/deferred였고 로그는 SDK `OperationalError`였다. 이는 계획의 busy 시 다음 cycle으로 연기하는 정상 계약과 첫-cycle 단언이 충돌한 것이다. 제품 코드를 바꾸거나 기다림을 늘리는 대신 첫 cycle의 pruned+deferred 총 21건, 다음 cycle까지 총 pruned 21건 및 각 canonical 정리 상태를 확인한다.

로컬 커밋 `bffaebf349f9baab5fd7568b498b53da07d2a96a`은 이 신규 fixture만 보완했다. 일반 ON/OFF 비교의 기존 4개 지연 제한은 그대로 유지하고, SDK busy를 한 번 주입하는 별도 새 검사를 추가했다. 공개 SDK의 fault injection은 임시 TEST root의 검사에서만 사용하며 제품의 SDK 구현을 패치하지 않는다. 각 캐릭터의 8단계 진행·모델 1회·완료 상태·실제 최종 checkpoint와 공개 효과/receipt 3개를 다음 cycle 뒤에도 확인한다. 실패 측정값은 제한 단언 전에 저장한다. 보완 중 checkpoint의 `dict` root channel을 잘못 가정한 fixture 오류도 실제 `__root__`로 고친 후 CM 파일 전체 **9 PASS** (`workload-contract-split.xml`)를 확인했다. 최초 확인 실행의 이 1건 실패를 지우거나 새 검사 1건이 그 전체 실행에 이미 수집됐다고 합산하지 않는다.

확인용 전체 실행의 기존 `test_l3_er2_sqlite_concurrency.py` 실패는 scheduler lease·같은 manual request·outbox claim의 세 검사다. 모두 `BEGIN IMMEDIATE`의 `database is locked` 이후 기존 250 ms writer policy가 1회 bounded attempt로 소진된 trace다. 해당 파일은 새 maintenance worker를 실행하지 않고 자기 임시 DB를 사용한다. 기존 fixture와 SQLite writer·database·lease 제품 파일은 작업 시작 커밋과 동일하다. 전체 실행과 다른 무거운 검증이 끝난 뒤 해당 원본 파일 전체를 수정 없이 재검사하여 **10 PASS, 18.97초**를 확인했다 (`sqlite-concurrency-isolated-final.xml`). skip·prewarm·시간 상한 조정·실패를 정상 loser로 간주하는 코드는 추가하지 않았다. 이 재통과는 간헐성이 해결됐거나 전체 부하에서 항상 성공한다는 증거가 아니다. 정확한 실패 timing 원인과 안정적인 단일 전체 실행 PASS는 별도 미확정 사항이다.

`final-validation-summary.json`에는 최초/확인 전체 실행, 각 보완 파일, 원본 동시성 파일 및 각 testcase가 마지막으로 검사된 증거 파일을 구분해 기록한다. 확인 전체 4,729개에 새 SDK busy 검사 1개를 추가한 현재 **4,730개**의 마지막 case별 결과는 **4,678 PASS / 52 SKIP / 잔여 FAIL 0**이다. 새 계약의 GR 24개·CR 26개·RL 16개는 확인 전체에서 통과했고 CM 9개는 보완 파일 전체 실행에서 통과했다. 총 **75개 모두 PASS / 신규 SKIP 0**이다. 전체 실행의 실패 기록을 삭제하거나 후속 결과로 덮어쓴 XML을 만들지 않는다.

공식 capture 도구는 `bffaebf3`의 새 SDK busy 검사 1개를 append하여 기존 321개 record를 보존한 322개 record로 만들었다 (`3965611e`, `sdk-busy-capture-final.log`). 이후 원래 preservation CLI가 기존 `_overlap_workload` 단언의 출처 변경 누락을 정확히 거절했다 (`preservation-sdk-busy-final.log`). 첫 cycle의 21건 즉시 완료에서 첫/복구 cycle 총 21건 완료로 바뀐 신규 fixture 계약의 정확한 `bffaebf3^ → bffaebf3` 정의·전체 단언·Git blob을 append-only product change record로 기록하고 `06df6c6eb2898e5c94f8d0824b5f6612e621a517`에 로컬 커밋했다. 기존 121개 record prefix를 그대로 보존한 122개 record이며 수정 전후 단언은 각각 9개·13개다. 원래 `load`와 predicate 검증 함수로 실제 인접 커밋 출처·append-only·네 지연 단언 불변을 검증했다 (`workload-predicate-provenance.json`). 과거 baseline·checker 구현은 그대로 유지하며 최종 CLI 결과를 따로 확인한다.

`06df6c6e` 기준의 최종 **원래 CLI `check_refactor_preservation.py --contracts --nodes`는 exit 0 / PASS**다 (`preservation-sdk-predicate-final.log`). frozen PR258 1,867개·PR263 1,907개 node, 보호 lineage/current 각 **4,730개**, 보존 항목 37개를 확인했다. 신규 source/node의 도입 출처, 정확한 API/ORM·factory·assertion·skip 계약을 포함한 검사이며 checker/역사 baseline은 불변이다. 신규 test 보완 뒤 compileall과 최종 diff whitespace 검사도 통과했다. 기존 frontend 파일과 원본 역사 migration·schema·uv.lock·Gemini 6개 파일은 작업 시작 기준과 동일하다.

재현 명령은 제품 repository root에서 실행한다. 원래 preservation 검사는 완전한 Git 이력과 committed evidence를 사용하며 기존 baseline을 새 snapshot으로 바꾸지 않는다.

```powershell
uv run --locked --directory backend python -m pytest -q tests/runtime/test_checkpoint_retention.py tests/runtime/test_checkpoint_maintenance.py tests/runtime/test_retention_lifecycle.py tests/migrations/test_canonical_retention.py
uv run --locked --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --locked --project backend python scripts/ci/check_architecture_boundaries.py
uv run --locked --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
uv run --locked --project backend python scripts/ci/check_embedded_data_migration_contract.py
uv run --locked --directory backend python -m pytest -q tests
```

## 비교 workload

아래 수치는 전체 backend 회귀의 `backend-final-fixtures`에서 완료한 보존 workload의 실제 출력이다. 전체 suite의 종료 판정과 각 workload의 측정을 분리한다. 임시 SQLite·실제 saver·fake Provider를 사용했으며 사용자 데이터 용량 측정은 아니다.

| 지표 | 정리 OFF/legacy 30일 | 신규 24시간/정리 ON |
| --- | --- | --- |
| 100개 만료 완료 활동 + 보호 실패 1개, checkpoint rows | 201 | 1 |
| writes rows | 201 | 1 |
| 상세 BLOB bytes | 13,145,183 | 1,383 |
| 동일 SQLite physical bytes | 13,377,536 | 13,377,536 |
| A/B/C 동시 활동 완료 시간 | 0.408 s | 0.886 s |
| 최대 canonical write 대기 포함 시간 | 0.088 s | 0.107 s |
| p95 write 시간 | 0.043 s | 0.068 s |
| 최대 tick/lease 간격 | 0.122 s | 0.184 s |

A/B/C는 각각 8단계의 실제 LangGraph checkpoint·canonical write·lease 갱신을 수행하고 fake 모델은 각각 1회, 실제 공개 효과/receipt는 총 3개였다. ON에서는 별도 만료 thread 20개와 5 MiB thread 1개를 정리했다. 해당 cycle은 802.415 ms, 최대 단일 삭제는 75.466 ms였다. 100개 만료 완료 활동 cycle은 1,988.917 ms에 100개를 정리했다. 취소·실패·중복 효과·추가 모델 호출 없이 사전에 정한 bound를 통과했다. 이는 실제 유료 모델의 지연이나 사용자 자연 활동 품질 측정이 아니다. 정리 부하는 0이 아니며 OFF 대비 지연 수치도 함께 남긴다.

보완한 CM 파일 전체 실행에서도 같은 수치를 다시 측정했다 (`workload-contract-split-fixtures`, 각 metrics JSON). 100개 활동의 BLOB와 physical bytes는 위와 같고, 정리 cycle은 2,274.289 ms·최대 삭제 13.674 ms였다. 일반 ON/OFF 비교의 총 시간은 0.458/0.970초, 최대 write는 0.116/0.104초, p95 write는 0.048/0.073초, 최대 tick/lease 간격은 0.131/0.148초였다. 첫 cycle 20건 완료·1건 연기, 다음 cycle 1건 완료이며 A/B/C 결과·실제 SDK 최종 상태·효과는 유지됐다. 별도 결정적인 busy 주입 실행은 첫 cycle 18건 완료·3건 연기, 다음 cycle 3건 완료였고 A/B/C 모두 8단계·모델 각 1회, 총 0.980초였다. 한 건의 의도적인 SDK busy 외의 실제 경합도 정리 연기로 처리하며, 연기 건수를 고정된 성공 수로 감추지 않는다.

main 기준과 이번 코드의 runtime 기본값은 tick 60초, lease 45초, heartbeat 10초, shutdown drain 20초, component startup 10초·shutdown 30초다. canonical writer는 기존 0.25초 제한을 유지하고 별도 saver/candidate read의 busy timeout은 50 ms다. 합성 비교의 최대 write bound는 `max(0.5초, OFF 최대값 × 3)`, p95는 `OFF p95 × 3 + 0.05초`, 최대 tick/lease 간격은 `max(1초, OFF 최대값 × 3)`, 총 시간은 `OFF 시간 × 3 + 1.5초`로 고정했다. 이 간격은 실제 scheduler의 60초 tick 자체를 실행한 측정이 아니라 동일한 DB·saver에서 겹치는 작업과 lease 갱신의 진행 간격이다. active SQL은 예산 때문에 취소하지 않으므로 단일 대형 thread의 삭제 시간과 cycle의 새 작업 시작 예산을 구분한다.

DB workload는 기존 21 legacy 세대의 30,535,680 bytes를 유지하고 신규 managed 세대는 current/previous 2개·4,853,760 bytes였다. 동일 schema 10회 재시작은 21.194 s였으며 copy/migration/새 generation 0, canonical snapshot·legacy hash·secret/media·identity·FK/integrity 불변을 확인했다. 전체 폴더 수는 legacy 21개를 더하므로 2개로 줄었다고 보고하지 않는다.

## 단계 실행과 완료 판정

P00–P11의 지정 브랜치·이슈 생성·구현·계약별 회귀·부하 측정을 수행했다. P12의 구조·migration·원본 보존 검사는 PASS이고 전체 backend 실행 및 실패 보완/원본 재검사도 수행했으나, 단일 전체 0 FAIL과 기존 SQLite 경합의 간헐성 해소는 미확정이다. P13의 운영·되돌림·후속 기록과 P14의 범위/출처/diff 검토·Signed-off-by 로컬 커밋을 마무리한다. 새 보존 기능의 75개 계약 통과를 전체 repository의 안정성 완료로 확대하지 않는다. 계획 §16.7을 포함한 엄밀한 전체 완료 선언은 보류한다.

마지막 구현/단언 출처 검증 기준은 `06df6c6eb2898e5c94f8d0824b5f6612e621a517`이다. 이 검증 문서와 운영 설명의 최종 문서 커밋 SHA·작업 폴더 clean·기존 main/진단 ancestry·commit 목록·Docker 확인은 workspace 계획 §18 및 로컬 `end-state.json`에 기록한다. 큰 임시 DB와 XML·계측 스크립트를 제품 Git에 추가하지 않는다.

## 사용자 실행 환경과 후속

사용자가 watch를 종료하고 watch 없는 `docker compose -f compose.yml -f compose.dev.yml up --build`로 실행했다. 해당 환경을 read-only로 확인한 backend `6321e8d7ab35`와 frontend `3b88fad2e888`의 image·mount·health를 유지한다. 서버 재시작/rebuild·volume exec 테스트·실제 사용자 DB 읽기/삭제·설치 앱 갱신을 하지 않는다. 실제 설치된 Windows Angmoo의 물리 identity·버전을 주장하지 않는다.

이 작업은 원격 이슈 생성 외에는 로컬 구현·검사·커밋만 허용한다. push·PR 생성/수정·Hosted CI dispatch/retry·main 병합은 하지 않는다. 기존 Gemini 진단 커밋과 main 기준 SHA를 보존한다.

적용은 사용자 요청으로 backend에 이 코드를 build/restart한 뒤 실제 startup을 확인하는 별도 작업이다. 정책 미표시 legacy 세대와 checkpoint를 이번 정책으로 소급 제거하지 않는다. 위 21세대 수치는 격리된 회귀 fixture의 수치이며 사용자 volume의 현재 사본 수를 측정한 결과가 아니다. Windows 적용 확인에는 workspace의 설치 identity helper가 먼저 필요하다.

문제가 생기면 `SNS_CHECKPOINT_MAINTENANCE_ENABLED=false`, `CANONICAL_GENERATION_RETENTION_ENABLED=false`로 정리만 중지한다. 신규 태그 중지는 `SNS_CHECKPOINT_POLICY_ENABLED=false`다. 완료 canonical reader·ownership/use pin 해석은 유지한다. 삭제된 상세/obsolete 세대의 자동 복원을 보장하지 않는다. current/previous marker를 자동 과거 전환하지 않는다.

후속 범위는 실제 Docker/Windows 적용·USER CHECK, 자연 활동 지연 관측, 필요 시 별도 승인한 legacy 정리·SQLite VACUUM/VHDX 축소다. 실제 API 키·유료 생성/인식 검사는 이번 보존 정책 검증에 필요하지 않으며 수행하지 않는다. row/BLOB 감소와 파일/VHDX·호스트 여유 공간 회수는 별개다.
