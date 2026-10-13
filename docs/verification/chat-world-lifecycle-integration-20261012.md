# Chat 이미지·World lifecycle 구현·검증 원장 — 2026-10-12

지정한 **I00–I79** 구현과 관련 기능 검증을 수행했다. 이 원장은 해당 변경을 포함하는 로컬 커밋에 저장하며, 정확한 최종 SHA는 workspace 통합 계획 §15와 최종 응답에 기록한다. 문서가 자기 자신의 commit hash를 포함하도록 강제로 재작성하지 않는다.

- 제품 repository: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- branch: `feat/0.1.0-release-readiness`, 시작 HEAD `5838a8c71769b67f2198ea039d1d3581919bfcb9`; 초기 tree clean.
- 로컬 코드·합성 데이터·필요한 검증만 수행했다. PR/push/원격 CI/main 머지, 원본 Docker 적용, Windows 설치 앱 진단·migration, 실제 사용자 World 삭제는 수행하지 않았다.
- 두 원본 계획은 bytes/hash 그대로 보존했다. 사용자 확정 World 계약 1–8을 재승인 없이 적용했다.

## 구현 결과와 책임

Chat 정상 이미지 인식/답장 pending을 기존 TypingPresence 하나로 표현한다. 약300ms 지연, accepted와 첫 검증 delta의 구분, 같은 generation 재연결·새 scope 분리, 종료/취소/late callback 정리를 보존한다. 실제 EOF가 terminal 없이 끝난 경우에도 기존 canonical request read/reconnect 경로로 복구한다. 이미지 실패/명시 retry/text-only 조건과 NDJSON validation은 유지한다.

실제 현재 첨부가 있을 때만 Supervisor/CRG system prompt에 영어 출처 안내를 한번 합성한다. `untrusted_current_image_observation`과 evidence kind `current_image_analysis`, 현재 사용자 메시지·참가자 연결을 설명하며 촬영자/피사체를 사용자로 추측하지 않는다. 기존 raw payload/analysis/hash/identity/delivery/locale/불신/페르소나 규칙을 재작성하지 않는다. 지원 legacy Router는 constructor 사용이 없는 adapter이므로 조건부 대상에서 제외했다.

World 삭제는 owner/default/name/version/명시 consent/idempotency 검사를 실제 API에서 수행하고202를 반환한다. 같은 UoW에 영속 intent와 새 admission 차단을 기록한다. 별도 lifespan worker가 drain→collect→purge→files/derived cleanup→verify→completed를 작은 단위로 처리한다. API202는 완료가 아니다. 미정산 public effect는 timeout으로 성공 처리하지 않고, 실패/재시작/응답 유실에서 같은 receipt/cursor/journal을 재개한다. 타 World와 전체 scheduler를 중지하지 않는다.

새 요청은 application guard, 오래된 reader/provider의 최종 canonical write는 SQLite INSERT/UPDATE invariant로 차단한다. settled lease에 필요한 operational update는 허용하고 새 lease·scope 이동·ID 재생성을 막는다. 이미지 파일 write 전 canonical writer lock과 최신 gate를 검사한다. Domain별 frozen 정책131개 테이블/11owner를 Runtime이 조립하고 FK를 끄거나 모든 계정 데이터를 지우지 않는다.

대상 World 콘텐츠/등록/현재 설정/활동/SNS/Chat/관계/기억·미저장 경험·keys/managed files/derived data를 제거한다. package shared lineage 때문에 필요한 World identity 행은 이름·본문·태그·이미지·guidance가 모두 비워진 content-free root로만 남고 ordinary reads/launch가 차단된다. 완료 receipt에는 ID/state/time/digest만 남고 file/row journal은 지운다. 원문을 남긴 archive를 삭제 완료로 표시하지 않는다.

캐릭터의 불변 첫 등록 snapshot·identity/owner/origin·초기 이미지·공유 복사 원본은 항상 보존한다. 마지막 registration 삭제 후에는 mutable identity 표시를 첫 snapshot으로 되돌리고 World 없는 owner source read/copy/register를 제공한다. 가짜 actor/ACL, current settings recapture, 다른 World 자동 등록/활동ON, 옛 기억·관계 이관은 없다. 다른 World가 쓰는 shared/current 자료는 유지한다.

FTS physical document/tombstone, Vec1 vector/document/embedding attempt, 모든 retained derived generations, native Ladybug graph와 SDK LangGraph checkpoints를 exact scope로 정리한다. graph·checkpoint content-free fence로 late/rebuild 쓰기도 차단한다. retired social FTS는 새 runtime lane을 되살리지 않고 실제 잔존 managed store만 정리한다. IO/unavailable을 ack 성공으로 숨기지 않는다.

Studio는 visibility 대신 실제 launchability/readiness/status로 사용 가능/작성 중/보관됨을 표시한다. 기존 visibility/ACL/publish/validate/자율활동 설정은 유지한다. 기본 SNS는 binding으로 archive/delete를 막고 이름·세계관·tag·이미지 편집은 유지한다. 삭제 Dialog·선택적 구성 export·actual progress/retry·scope watch는 Worlds가 소유하고 Composition에서 연결한다. ko/en을 같이 반영했다. 네트워크 오류는 삭제 확인이 아니며, 실제 deletion을 확인한 화면만 닫고 다른 World로 자동 이동하지 않는다.

## 실제 실행 결과

전체 backend/frontend/browser corpus 또는 원격 CI를 실행한 것이 아니다. 이 기능의 실제 owner/gate와 아래 node를 선택했다. artifact 경로는 모두 제품 repo의 ignored `artifacts/chat-world-lifecycle-20261012` 아래이며 합성 자료만 포함한다.

| 실행 | 실제 결과 | 근거 |
| --- | --- | --- |
| 관련 Windows backend batch | **65 passed, 2 skipped**,423.34s | `backend-results.xml`;2skip은 native Windows Vec1 미제공 |
| 변경 후 privacy HTTP·junction/작은 purge page 경계 | 각각2passed, 총4실행 통과 | 실제 owner/익명 삭제read; Windows junction 외부 sentinel; bounded purge 완결/다른 World membership 유지 |
| default edit/archive·Home projection 추가 | **5 passed**,13.50s | `default-home-results.xml`; 실제 서비스/서버 capability·stale readiness |
| 이미지 취소/파일교체/scope revoke 관련 | **4 passed**,8.08s | 기존 `test_chat_attachments.py` 선택node; 첫 batch의2node와 일부 중복 |
| 공식 file-backed bootstrap | **1 passed**,5.50s | 기존 L3 SQLite canonical adapter 선택node |
| Linux native/migration/SDK batch | **10 passed**,88.45s | `docker-final-regression.xml`; Windows에서 skipped된 실제 Vec1두node 포함 |
| ko/en × Next/static 주요 browser | **62 passed**,2.4min | `browser-main-results.json`; 단계 제어/실패복구/World삭제/기존crop/기존room삭제scope |
| 상태·capability·선택 export 추가 | **4 passed**,11.4s | `browser-state-results.json`; safe HEAD prefetch를 mutation과 구분해 실제 API writes0검사 |
| 격리 실제 backend+browser | **1 passed**,19.9s | `real-browser-results.json`; actual auth/API/deletion/content/files/initialGET/copy/register |
| Docker 새 프로세스 같은 deletion 재개 | completed, 같은 receipt | `verify_chat_world_lifecycle.py --mode stage/finish`; 초기 production autoflush 중복 journal 장애를 수정 후 재개 |
| Docker 실제 lifespan health/shutdown | HTTP200;shutdown **1.588s** | 합성 별도 root·autonomyOFF·no credentials·no network |
| Next production/static build | 각각PASS | 같은 feature implementation, local artifact만 생성 |
| 변경 frontend ESLint/typecheck/catalog | PASS | 16namespaces/2595sourcekeys; key/params/plural parity |
| Python 변경59files syntax | PASS | AST parse; 추가 Home projection test도 마지막 syntax 감사에서 포함 |
| frontend architecture/design | PASS | features14/legacyedges0;rawcolors1157/files35/surfaces18/routegaps0/screenshots59 |
| backend architecture | **기존4가지 위반 유지**,새 위반0 | 아래 항목; overall PASS로 보고하지 않음 |

숫자는 각 실행의 결과이고 중복 node를 포함하므로 독립 test 수로 합산하지 않는다. 기존 attachment fixture가 새 Supervisor 인자를 받도록 정렬했으며 실제 production workflow를 stub 성공으로 대체하지 않았다. 브라우저 단계 fixture는 순차 chunked HTTP NDJSON이고 provider·실사용API로 fallback하지 않는다.

백엔드 import 검사에 남은 기존 문제:

1. `chat.contracts.evidence_reads → memory.contracts.activity_situation` deep import.
2. `chat.relationship_evidence_policy → relationships.policies.social_context_validation` deep import.
3. `identity.service.world_credentials ↔ world_image_credentials` cycle.
4. `memory.contracts.activity_situation ↔ situation_source_binding` cycle.

두 deep import의 refactor diagnostics가 중복 출력되지만 서로 다른 문제는4개다. 해당 owner 모듈은 이번 변경 대상이 아니며 검사/baseline을 통과시키려고 완화하지 않았다.

## 환경·migration·보존 감사

- Embedded SQLite **v37** / source Alembic **20261012_0114**. 공식 v36 source table/content/FK/visibility/default/original/key를 유지하고 새 tables2개를 추가한다. target tables174, frozen digest `6745f05e6e0f0b8b9eefcfc5aadd02c104c38dce80a1607e69c3f4a773b5735d`. staged additive DDL 중단/재개를 검증했다.
- 초기 ORM inventory는 v36 metadata172tables이며 migration 후174와 구분한다. `docs/verification/world-deletion-orm-inventory-20261012.json` 및 각 domain `repository/world_erasure.json`에 FK/JSON/special scope·보존 정책을 기록했다. 새 FK만 보고 cleanup scope를 자동 확장하지 않는다.
- 단일 worker page100/lease30s/backoff2·5·15s/3회 제한. 작은 page2 테스트로 부모 FK가 막힌 뒤 다른 page와 타 World admission을 확인했다. 실제 workload 전체 throughput 수치를 추정하지 않는다.
- Docker는 기존 local `angmoo-backend-dev:latest`를 재사용하고 readonly `/src`, 별도 synthetic `/results`,`--network none --rm`만 사용했다. 새 image build/pull·원본 image/container/named volume 정리·원본 app 재시작은 하지 않았다. 종료 뒤 자체 컨테이너는 남지 않는다.
- 실제 contributor test root는 marker를 가진 별도 root다. user/provider credentials를 읽거나 paid AI를 호출하지 않는다. source mode는 production entry eligibility와 일치하는 llm으로 설정하되 API key를 넣지 않고 autonomy는OFF로 유지했다.
- LOCAL screenshot `typing-narrow-ko.png`와 `real-browser/world-deleted.png`를 실제 pixels로 확인했다. 새 canonical11-screenshot approval이나 직접 USER CHECK로 간주하지 않는다. screenshot call inventory만57→59로 갱신했고 pinned environment/25pixel/0.1threshold/rawcolor 허용치는 완화하지 않았다.

## 재현 명령

```powershell
# cwd D:/project_code/angmoo-workspace/angmoo-tree-angmoo
$env:PYTHONPATH='backend'
uv run --project backend --no-sync python -m pytest backend/tests/chat/test_chat_image_input_presentation.py backend/tests/worlds/test_world_deletion.py backend/tests/worlds/test_world_deletion_http.py backend/tests/worlds/test_world_erasure_scope.py backend/tests/runtime/test_world_deletion_migration.py backend/tests/runtime/test_world_deletion_worker.py backend/tests/runtime/test_world_erasure_checkpoints.py backend/tests/memory/test_world_erasure_index.py -q
pnpm --dir browser-tests exec playwright test --config playwright.chat-world-lifecycle.config.ts
pnpm --dir frontend typecheck
pnpm --dir frontend test:ui-catalog
python scripts/ci/check_frontend_architecture_boundaries.py
python scripts/ci/check_frontend_design_contract.py --check
python scripts/ci/check_architecture_boundaries.py
```

위 backend 명령은 신규 기능 core이고 실제65batch에는 기존 identity/attachment 선택node도 포함했다. 최종 default/Home 추가 node는 별도 실행 원장으로 남겼다. 신규 브라우저 config의 전체 기능 scope는 이제66tests(62+4)다. 실제 backend browser config는 이미 지운 synthetic World를 대상으로 반복 실행하지 말고 **새 marker root**에서 fixture를 시작한다. `verify_chat_world_lifecycle.py`는 unmarked/nonempty root를 거절한다. 원본 data root에 연결하지 않는다. 구조 검사는 local validator이며 remote CI 실행이 아니다.

## P/B/D/U/X coverage — 50개

machine 원장 `chat-world-lifecycle-coverage-20261012.json`은50IDs·실제 file/node/환경과80stage 원본 대응을 포함한다. legacy Router 조건부 제외와 native Windows 미측정은 완료된 다른 플랫폼 시험과 구분했다. 각 ID의 복잡한 모든 사용자 데이터 조합/실제 모델 성능까지 PASS로 확장하지 않는다.

| ID | 실제 node/file | 확인한 경계 |
| --- | --- | --- |
| P01 | `backend/tests/chat/test_chat_image_input_presentation.py::test_supervisor_submits_conditional_current_attachment_once`<br>`backend/tests/chat/test_chat_image_input_presentation.py::test_crg_uses_frozen_current_image_kind_and_preserves_submitted_payload` | 실제 제출 system/user prompt・현재 이미지・중복0・본문 동일 |
| P02 | `backend/tests/chat/test_chat_image_input_presentation.py::test_crg_uses_frozen_current_image_kind_and_preserves_submitted_payload`<br>`backend/tests/image_integration/test_chat_attachments.py::test_image_only_and_text_image_reach_real_workflow_after_analysis` | image-only와 text+image 실제 workflow; 기존 participant/role 유지 |
| P03 | `backend/tests/chat/test_chat_image_input_presentation.py::test_supervisor_submits_conditional_current_attachment_once`<br>`backend/tests/chat/test_chat_image_input_presentation.py::test_crg_uses_frozen_current_image_kind_and_preserves_submitted_payload` | current=False: 설명0, 제출 payload와 호출 인자 보존 |
| P04 | `backend/tests/chat/test_chat_image_input_presentation.py::test_previous_observation_is_not_a_current_attachment` | 이전 message observation과 현재 첨부 설명 구분 |
| P05 | `backend/tests/chat/test_chat_image_input_presentation.py::test_previous_observation_is_not_a_current_attachment`<br>`browser-tests/image-integration.spec.ts::accepted analysis failure offers explicit text recovery only with original text` | 이전-only·명시적 제외 복구의 기존 capability 유지 |
| P06 | `backend/tests/chat/test_chat_image_input_presentation.py::test_supervisor_submits_conditional_current_attachment_once` | native/repair 조합 실제 제출. legacy DirectLlmRetrievalRouterProvider는 app 내 constructor 참조 없음(조건부 제외); 클래스/export를 실제 사용이라고 계산하지 않음 |
| P07 | `backend/tests/chat/test_chat_identity_delivery.py::test_adapter_builds_once_and_binds_both_receipts_to_actual_serialization`<br>`backend/tests/image_integration/test_chat_attachments.py::test_attachment_evidence_is_rejected_after_file_replacement`<br>`backend/tests/image_integration/test_chat_attachments.py::test_scope_revocation_during_analysis_never_routes` | identity 실제 serialization/delivery; 변경된 pixels·권한 폐기 기존 거절 |
| P08 | `backend/tests/chat/test_chat_image_input_presentation.py`<br>`backend/tests/image_integration/test_chat_attachments.py::test_image_only_and_text_image_reach_real_workflow_after_analysis` | 영어 출처·기존 불신/페르소나/상황 설명 언어 규칙 전달. 모델 품질은 미측정 |
| B01 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing remains in one slot through accepted and delta`<br>`browser-tests/image-integration.spec.ts::Chat typing shows one pending indicator before any image stream result` | 느린 이미지 waiting 단일 TypingPresence, 정상 분석 문구0 |
| B02 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing fast reply avoids a flash and leaving the scope discards old events` | 새 텍스트 요청의 빠른 delta, MutationObserver로 typing flash0 |
| B03 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing remains in one slot through accepted and delta` | waiting→accepted→delta→completed 각각 관찰; accepted 유지/첫 delta 제거/답장1 |
| B04 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing reconnect refresh and deleted World do not revive the slot` | genuine EOF 재연결 후 기존 typing1, 생성 POST/attempt 추가 없음 |
| B05 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing reconnect refresh and deleted World do not revive the slot` | page.reload로 같은 활성 generation 복원 |
| B06 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing fast reply avoids a flash and leaving the scope discards old events` | 첨부 없는 정상 메시지·stream·canonical reply |
| B07 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing analysis failure has ordinary retry without terminal revival`<br>`browser-tests/image-integration.spec.ts::accepted analysis failure offers explicit text recovery only with original text`<br>`backend/tests/image_integration/test_chat_attachments.py::test_cancellation_during_analysis_preserves_terminal_state_and_never_routes` | 실제 failed terminal·이미지-only/text-only capability·취소 시 router0 |
| B08 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing analysis failure has ordinary retry without terminal revival`<br>`browser-tests/image-integration.spec.ts::accepted analysis failure offers explicit text recovery only with original text`<br>`backend/tests/image_integration/test_chat_attachments.py::test_cancellation_during_analysis_preserves_terminal_state_and_never_routes` | 실패/취소/명시 retry 및 reload에서 종료된 표시 부활0; 기존 timeout/terminal 분기는 source audit로 보존 |
| B09 | `browser-tests/world-chat-dialog-delete.spec.ts`<br>`browser-tests/chat-world-lifecycle.spec.ts::Chat typing fast reply avoids a flash and leaving the scope discards old events` | 기존 T38–39/T46/T47 중 cancel·runtime·logout·late401·다른 World navigation 선택 회귀 |
| B10 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle narrow keyboard reduced motion preserves labels` | 390×844·keyboard·Cancel focus·aria-hidden dots·overflow0·reduced motion |
| D01 | `backend/tests/worlds/test_world_erasure_scope.py::test_default_binding_survives_rename_and_missing_legacy_binding_is_not_guessed`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_every_owned_nondefault_stage_uses_same_erasure_contract` | 실제 update_world로 이름/소개/tag 수정, binding 유지·archive/delete 거절·일반 SNS 이름 삭제 허용·유실 legacy 오류 |
| D02 | `backend/tests/worlds/test_world_deletion.py::test_confirmation_acl_default_and_version_are_not_bypassed`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_membership_role_does_not_grant_world_deletion`<br>`backend/tests/worlds/test_world_deletion_http.py::test_real_cookie_auth_and_origin_do_not_accept_unauthorized_erasure`<br>`backend/tests/worlds/test_world_deletion_http.py::test_consent_is_an_explicit_boolean_not_a_coerced_value` | owner/editor/member/타 사용자/익명·real cookie/Origin·정확 name/version/명시 true |
| D03 | `backend/tests/worlds/test_world_erasure_scope.py::test_every_owned_nondefault_stage_uses_same_erasure_contract`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_package_lineage_is_minimal_shared_and_old_import_replay_cannot_restore_world` | draft/published private-public-unlisted/archived·import 모두 같은 작업 lifecycle |
| D04 | `backend/tests/worlds/test_world_deletion.py::test_owner_receipt_idempotency_and_durable_empty_world_cleanup`<br>`backend/tests/worlds/test_world_deletion.py::test_archived_owner_can_delete_and_conflicting_replays_are_rejected`<br>`backend/tests/worlds/test_world_deletion_http.py::test_real_api_intent_closes_world_but_receipt_remains_owner_only`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle response loss GET failure and same job retry` | 같은 body/key replay1·active conflict·완료 replay·응답 유실 동일 key |
| D05 | `backend/tests/worlds/test_world_deletion.py::test_world_characters_posts_chat_and_first_original_are_separate`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | 최초 payload/digest·identity/owner/origin·초기 파일·실제 source 조회/복사/등록·타 owner 차단·autonomy OFF |
| D06 | `backend/tests/worlds/test_world_erasure_scope.py::test_populated_memory_unsaved_experiences_image_and_received_files_are_erased`<br>`backend/tests/worlds/test_world_deletion.py::test_world_characters_posts_chat_and_first_original_are_separate`<br>`backend/tests/runtime/test_world_erasure_checkpoints.py` | 실제 target Chat/SNS/관계/Memory/미저장 경험/manifest/활동/SDK thought/첨부 query 및 file erasure. 131 frozen policies 별도 audit |
| D07 | `backend/tests/worlds/test_world_deletion.py::test_old_writer_and_new_world_id_cannot_resurrect_accepted_scope`<br>`backend/tests/worlds/test_world_deletion_http.py::test_intent_blocks_send_retry_text_only_media_memory_and_new_registration`<br>`backend/tests/runtime/test_world_erasure_checkpoints.py`<br>`backend/tests/runtime/test_world_deletion_worker.py` | 최종 canonical fences·old reader·late SDK/native graph·신규 image/send/retry/등록 차단. file apply는 writer lock+latest gate |
| D08 | `backend/tests/worlds/test_world_erasure_scope.py::test_expired_worker_lease_resumes_same_request_and_stale_commit_is_rejected`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_only_target_slot_is_cleared_and_new_target_lease_is_fenced`<br>`backend/tests/worlds/test_world_deletion.py::test_old_writer_and_new_world_id_cannot_resurrect_accepted_scope` | lease epoch·stale commit·새 target slot lease 차단/다른 World 보존 |
| D09 | `backend/tests/worlds/test_world_erasure_scope.py::test_unsettled_public_effect_is_not_completed_by_timeout_and_can_resume`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_missing_file_and_permission_failure_keep_exact_journal_and_retry`<br>`backend/tests/worlds/test_world_deletion.py::test_cleanup_failure_stays_failed_until_same_receipt_is_retried` | 미정산 effect는 timeout fake 완료 없음·권한/IO 실패 cursor/journal 유지·same request 재개 |
| D10 | `backend/tests/worlds/test_world_deletion.py::test_file_paths_cannot_escape_or_follow_links`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_managed_child_link_cannot_erase_an_external_directory`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_shared_managed_file_and_external_download_survive_target_cleanup`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_missing_file_and_permission_failure_keep_exact_journal_and_retry`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | Windows 실제 junction·외부 sentinel 보존·없는 파일·shared reference·initial media 실제 GET |
| D11 | `backend/tests/memory/test_world_erasure_index.py`<br>`backend/tests/runtime/test_world_deletion_worker.py::test_native_graph_erasure_is_bounded_durable_and_fences_late_commands` | FTS text/tombstone·모든 retained Vec1 generations·rebuild rollback·native graph/late writer·ack |
| D12 | `backend/tests/runtime/test_world_deletion_migration.py` | 공식 v36→v37 frozen schema/DDL·기존 내용/FK·중단 additive DDL 재개 |
| D13 | `backend/tests/worlds/test_world_erasure_scope.py::test_populated_memory_unsaved_experiences_image_and_received_files_are_erased`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_small_batches_allow_other_world_admission_and_receipts_contain_no_confirmation_text`<br>`backend/tests/worlds/test_world_deletion.py::test_world_characters_posts_chat_and_first_original_are_separate`<br>`backend/tests/runtime/test_world_erasure_checkpoints.py` | target private data 제거 query·내용 없는 receipt·World root scrub·불변 original 별도 보존 |
| D14 | `backend/tests/worlds/test_world_erasure_scope.py::test_package_lineage_is_minimal_shared_and_old_import_replay_cannot_restore_world`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_shared_managed_file_and_external_download_survive_target_cleanup` | package shared lineage/원본 basis·외부 export 파일 보존·import/create old replay 차단 |
| D15 | `backend/tests/worlds/test_world_erasure_scope.py::test_small_batches_allow_other_world_admission_and_receipts_contain_no_confirmation_text`<br>`backend/tests/runtime/test_world_deletion_worker.py::test_scope_signal_closes_target_stream_and_keeps_other_world_running` | 2-row pages와 타 World read/write admission·target-only stream cancel. 장시간 자연 활동 부하 성능은 별도 미측정 |
| D16 | `backend/tests/worlds/test_world_deletion_http.py::test_real_api_intent_closes_world_but_receipt_remains_owner_only` | World/member purge 뒤 immutable receipt owner만 read/list/retry,타 사용자404·익명401·원문 없음 |
| U01 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle ready private grouping and cancellation`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle state groups capabilities and optional export`<br>`backend/tests/device_home/test_world_surface.py::test_stale_readiness_remains_hidden_from_home_and_explained_in_studio` | ready private/public·draft/stale/archived 그룹 및 actual launchability |
| U02 | `browser-tests/chat-world-lifecycle.spec.ts`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | ko/en use-state·원본/초기 파일 보존·삭제/완료·placeholder/a11y; 2595 catalog key parity |
| U03 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle state groups capabilities and optional export`<br>`backend/tests/device_home/test_world_surface.py::test_owner_membership_cannot_forge_root_deletion_capability`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_membership_role_does_not_grant_world_deletion`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | default/editor/unknown disabled·root owner mismatch cannot forge capability·actual server 거절 |
| U04 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle ready private grouping and cancellation`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle permanent confirmation accepted and completed`<br>`browser-tests/creator-copy-ui.spec.ts` | stored name/version/consent·Cancel focus/요청0·dirty 유지·DELETE1 |
| U05 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle response loss GET failure and same job retry`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle permanent confirmation accepted and completed` | 202≠complete·GET failure≠fake failed/completed·same key/same job retry |
| U06 | `browser-tests/chat-world-lifecycle.spec.ts::Chat typing reconnect refresh and deleted World do not revive the slot`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle focus requires actual deletion before closing open content`<br>`browser-tests/world-chat-dialog-delete.spec.ts` | refresh/nav/auth/runtime/late callbacks·genuine deletion만 scope 닫음,URL/다른 World 자동 변경0 |
| U07 | `browser-tests/creator-copy-ui.spec.ts::world crop cancel, dimensions, conflict retention and latest revision`<br>`browser-tests/creator-copy-ui.spec.ts::World image transport failure and removal preserve unsaved definition`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | World media/dirty profile 경로 유지·완료 후 다른 World/default·source 선택/initial GET/copy/등록·autonomy0 |
| U08 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle state groups capabilities and optional export` | 실제 exportable preview에서 기존 export panel/config-only 안내·선택하지 않은 export/publish mutation0. 기존 export 권한/전송 구현 재사용 |
| U09 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle narrow keyboard reduced motion preserves labels`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle ready private grouping and cancellation` | 넓은 화면+390×844·keyboard·initial Cancel focus/복귀·안전 UI 공통 구현 |
| U10 | `browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | 실제 contributor lifespan/auth/API202→complete·target actors/posts/media gone·초기 image200·sourcecopy/explicit register201 |
| X01 | `backend/tests/worlds/test_world_deletion_http.py::test_intent_blocks_send_retry_text_only_media_memory_and_new_registration`<br>`backend/tests/worlds/test_world_deletion.py::test_old_writer_and_new_world_id_cannot_resurrect_accepted_scope`<br>`browser-tests/chat-world-lifecycle.spec.ts::Chat typing reconnect refresh and deleted World do not revive the slot` | waiting target HTTP admission+canonical late final writer fences·typing/late slot 부활0 |
| X02 | `backend/tests/runtime/test_world_deletion_worker.py::test_scope_signal_closes_target_stream_and_keeps_other_world_running`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_unsettled_public_effect_is_not_completed_by_timeout_and_can_resume`<br>`browser-tests/chat-world-lifecycle.spec.ts::Chat typing remains in one slot through accepted and delta`<br>`browser-tests/chat-world-lifecycle.spec.ts::Chat typing reconnect refresh and deleted World do not revive the slot` | accepted/stream lease 정산과 scoped cancellation·실제 event/terminal 검증·late callback 차단 |
| X03 | `browser-tests/image-integration.spec.ts::accepted analysis failure offers explicit text recovery only with original text`<br>`backend/tests/worlds/test_world_deletion_http.py::test_intent_blocks_send_retry_text_only_media_memory_and_new_registration`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle focus requires actual deletion before closing open content` | 정상 World text-only/retry 유지,accepted deletion 차단·network503는 삭제 아님 |
| X04 | `backend/tests/worlds/test_world_deletion.py::test_world_characters_posts_chat_and_first_original_are_separate`<br>`backend/tests/worlds/test_world_erasure_scope.py::test_only_target_slot_is_cleared_and_new_target_lease_is_fenced`<br>`browser-tests/chat-world-real.spec.ts::real isolated backend erases World and keeps reusable first source` | 동일 원본/초기 파일·타 World actor/slot 유지,원본만 explicit registration,옛 기억 전송0 |
| X05 | `backend/tests/runtime/test_world_deletion_migration.py`<br>`backend/tests/runtime/test_world_erasure_checkpoints.py`<br>`backend/tests/memory/test_world_erasure_index.py`<br>`backend/tests/runtime/test_world_deletion_worker.py`<br>`scripts/diagnostics/verify_chat_world_lifecycle.py` | 격리 Docker stage 후 fresh process same receipt finish·실제 health200/shutdown1.588s·native rebuild/late fences |
| X06 | `browser-tests/chat-world-lifecycle.spec.ts::World lifecycle response loss GET failure and same job retry`<br>`browser-tests/chat-world-lifecycle.spec.ts::World lifecycle focus requires actual deletion before closing open content`<br>`browser-tests/world-chat-dialog-delete.spec.ts` | GET failure state 합성0·scope abort/auth/runtime/keyed controller·stale callback 새 화면 반영0 |

## I00–I79 실행 원장과 원본 대응

- **G1**: `backend/app/integrations/llm/{chat_input_presentation,supervisor_selection,character_response_generator}.py`
- **G2**: `frontend/src/features/chat/components/world-chat.tsx; browser-tests/fixtures/chat-world-lifecycle-server.mjs`
- **G3**: `backend/app/domains/worlds/{contracts_deletion,models_deletion,router_deletion}.py; service/deletion.py; runtime/world_deletion/{inventory,fences,http_gate,worker,composition}.py`
- **G4**: `backend/alembic/versions/20261012_0114_world_deletion.py; runtime/migrations/sqlite_versions/{world_deletion_v37.py,world_deletion_v37_ddl.json,manifests/v37.json}; model_registration/sqlite_database/sqlite_schema`
- **G5**: `backend/app/runtime/world_deletion/ports.py; domains/*/repository/world_erasure.json (11 owners,131 tables); domains/characters/service/{preserved_originals,import_snapshots}.py`
- **G6**: `backend/app/runtime/memory/{hybrid_runtime,recall_projection,sqlite_fts5_recall,sqlite_vec1}.py; runtime/search/{social_projection,sqlite_fts5}.py; integrations/ladybug_projection.py; runtime/autonomous_activity/checkpoints.py`
- **G7**: `frontend/src/features/worlds/{api/world-deletion,types/world-deletion,components/world-delete-control,components/world-deletion-progress,hooks/use-world-deletion-watch}; Composition Studio/Creator/World/Memory; CreatorStudio/DeviceHome/Memory; ko/en catalogs`
- **G8**: `backend/tests/{chat,worlds,runtime,memory,device_home,image_integration}; browser-tests/{chat-world-lifecycle,chat-world-real}.spec.ts; playwright.chat-world-{lifecycle,real}.config.ts; scripts/diagnostics/verify_chat_world_lifecycle.py`
- **G9**: `backend/ARCHITECTURE.md; frontend/ARCHITECTURE.md; frontend/DESIGN.md; docs/verification/*20261012*; security/frontend_design_policy.json; docs/architecture/frontend-design-baseline.json`

| 단계 | 원본 | 실제 작업 | 모듈·검증 근거 |
| --- | --- | --- |
| I00 | C00 W00 | 브랜치·HEAD·AGENTS·세 아키텍처/디자인·실행 환경 확인 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I01 | C01 W01 | 현재 Chat/World 경로와 표시·입력·기본 공간·원본 재판독 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I02 | C02 W02 | 확정 계약과 통합 수명 기준 적용 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I03 | W03 | 삭제·보존 authoritative dependency inventory 작성 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I04 | W04 | 기존 instance/account/privacy/원본-copy/helper 계약 감사 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I05 | C01 W01 | 기존 표시/지침/World 삭제 부재와 검증 진입점 확인 | G1 G2 G3 G5 G9; 사전 branch/HEAD/AGENTS·source/contract/inventory audit |
| I06 | C03 | Chat 단계 제어 NDJSON/ReadableStream fixture와 새 표시 단언 준비 | G8; P01–P08/B01–B10 fixtures |
| I07 | C08 | 실제 provider 입력 캡처·중복/언어/source fixture 준비 | G8; P01–P08/B01–B10 fixtures |
| I08 | C04 | 정상 이미지 waiting 전용 문구 분기 제거 | G1 G2; P01–P08/B01–B10 |
| I09 | C05 | 같은 pending 요청의 이미 보이는 표시 유지 | G1 G2; P01–P08/B01–B10 |
| I10 | C06 | 300ms·accepted·delta·terminal·타이머 수명 보완 | G1 G2; P01–P08/B01–B10 |
| I11 | C07 | Chat ko/en 정상 인식 대기 key 정리·접근성 보존 | G1 G2; P01–P08/B01–B10 |
| I12 | C09 | 공통 영어 현재 첨부 설명·순수 조합 구현 | G1; P01/P03/P08 |
| I13 | C10 | Supervisor/CRG 실제 system_prompt에 연결 | G1; P01–P06; unused legacy adapter exclusion |
| I14 | C11 | P01–P08과 관련 attachment/identity delivery 검증 | G1 G2; P01–P08/B01–B10 |
| I15 | C12 | B01–B03 정상 대기/빠른 응답/단계 전환 검증 | G1 G2; P01–P08/B01–B10 |
| I16 | C13 | B04/B05 재연결·복원 검증 | G1 G2; P01–P08/B01–B10 |
| I17 | C14 | B06/B07 일반 Chat·인식 실패 복구 검증 | G1 G2; P01–P08/B01–B10 |
| I18 | C15 | B08 terminal·timeout·명시 retry 검증 | G1 G2; P01–P08/B01–B10 |
| I19 | C16 C17 | 기존 B09/B10 scope·언어/Next/static·접근성 대표 검증 | G1 G2; P01–P08/B01–B10 |
| I20 | W05 | World deletion typed request/state/error/capability 계약 구현 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I21 | W06 | Request/CleanupItem 모델·index·lease/CAS 구현 | G3; D04/D08/D09/D16 |
| I22 | W07 | 다음 공식 Alembic·embedded SQLite additive migration 연결 | G4; D12; v37 digest/FK/staged replay |
| I23 | W08 | 삭제 owner gate·preview·기본 SNS/archived 정책 구현 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I24 | W09 | DELETE 접수·status/active list/retry·same-key replay 구현 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I25 | W10 | World canonical lifecycle read/guard 구현 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I26 | W11 | Studio/Home/World default·deletion projection batch 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I27 | W12 | World edit/validate/publish/image/my-profile 최종 gate 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I28 | W13 | 생성/참가/선택/config/credential admission gate 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I29 | W14 | SNS scheduler/run-now/일일 준비·slot 대상 정산 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I30 | W15 | Chat send/retry/final response·memory/relationship gate 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I31 | W16 | Media 인식/생성/reference/spool/public attach final gate 연결 | G3 G5; D07/D10/X01; image final writer lock |
| I32 | W17 | Memory 접수/일일·종료 batch/review/embedding/index gate 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I33 | W18 | package export/import/replay gate·순서 연결 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I34 | W19 | 삭제 worker·app lifespan·lease/recovery 조립 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I35 | C06 W15 | Chat stream/상태 read와 삭제 lifecycle 결과 연결 | G2 G3; B04/B05/B09/X01/X02 |
| I36 | W22 | 원본 보존 정책과 read/write 접근 경계 준비 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I37 | W20 | file/projection durable cleanup journal 구성 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I38 | W19 | stage cursor·재시작·busy/미정산 처리 보완 | G3 G4; D01–D04/D07–D09/D12/D16; X01–X06 |
| I39 | W21 | World 정의·등록·configuration target batch 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I40 | W22 | 첫 등록 원본·identity/owner/origin·초기 이미지 보존 구현 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I41 | W22 | 삭제 World 없이 source 선택·설정 복사 read 구현 | G5; D05/U07/U10; source copy/candidates |
| I42 | W23 | SNS posts/replies/reactions/observations/media/추천 target 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I43 | W24 | Chat threads/messages/requests/events/proofs/attachments 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I44 | W25 | Memory scoped 자료·저장하지 못한 경험 batch 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I45 | W26 | 관계·활동·plan/checkpoint/준비·review 원장 정리 | G5 G6; D06/SDK checkpoint late-write fences |
| I46 | W27 | World/actor keys·Partner/policy/quota/attempt 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I47 | W28 | package target mapping/temp·전용 basis 정리 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I48 | W29 | 안전한 root·실제 unlink·원본 참조·실패 ledger 구현 | G5; D09/D10; native Windows junction sentinel |
| I49 | W30 | FTS5/Vec1/graph/cache/outbox target 삭제·ack 연결 | G6; D11; actual Linux Vec1/native graph |
| I50 | W31 | verify·보존 목록/tombstone·completed 판정 구현 | G5 G6; D05–D15/U10; Linux native/SDK/file |
| I51 | W22 W31 | 원본 파일 GET/복사·명시적 등록 연결 보완 | G5 G8; D05/U07/U10; real image GET/copy/register |
| I52 | W39 | Worlds frontend deletion DTO/API/controller 구현 | G7; U01–U10/B09–B10/X01–X06 |
| I53 | W40 | 서버 preview 기반 exact-scope 확인 Dialog 구현 | G7; U01–U10/B09–B10/X01–X06 |
| I54 | W41 | Studio/Creator deletion control을 Composition slot로 조립 | G7; U01–U10/B09–B10/X01–X06 |
| I55 | W42 | 진행/실패/GET 실패/retry/completed·새로고침 복구 UI 구현 | G7; U01–U10/B09–B10/X01–X06 |
| I56 | W43 | World 사용 상태 그룹·badge·validate/publish copy 변경 | G7; U01–U10/B09–B10/X01–X06 |
| I57 | W44 | Worlds/CreatorStudio ko/en 문구·원본 보존 안내 갱신 | G7; U01–U10/B09–B10/X01–X06 |
| I58 | W22 W46 | 기존 Characters 원본 선택 UI/등록 연결 보완 | G7; U01–U10/B09–B10/X01–X06 |
| I59 | C16 W46 | World 삭제 확인 시 Chat Typing/stream/retry 수명 정리 | G7; U01–U10/B09–B10/X01–X06 |
| I60 | W46 | Home/편집/Chat/Memory/media open scope 삭제 반영 | G7; U06/U07/X06; liveness known delete only |
| I61 | W32 | D03–D06 삭제 범위·원본 재사용/공유 보존 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I62 | W33 | D01/D02/D04/D16 권한·default·CAS·replay/status 회귀 | G8; D01/D02/D04/D16; real default edit/archive and real auth |
| I63 | W34 | D07/D08 provider/reader/final-writer·lease 경합 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I64 | W35 | D09/D10 stage/file/process 장애·재개 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I65 | W36 | D11/D13 index/rebuild·privacy/원본 구분 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I66 | W37 | D12/D14 migration·package/export/import 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I67 | W38 | D15 bounded 동시성·응답성 회귀 | G8; D15; bounded2 other-World admission |
| I68 | W45 | U01–U05 상태 문구·권한·Dialog·진행 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I69 | W46 C16 | U06/U07 scope·기존 편집/이미지/Home·원본 재사용 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I70 | W47 C17 | U08/U09·B10 언어/Next/static/좁은 화면/a11y 검증 | G8; ko/en × Next/static;390×844 keyboard |
| I71 | W48 | U10 격리 backend+브라우저 실제 삭제/원본 재사용 연결 | G8; 1 real browser PASS; actual contributor/API/initial-image/copy/register |
| I72 | W49 | 최소 격리 Docker migration/worker/파일·pending recovery 검증 | G8; Docker native10 PASS; same-job restart finish + health200/shutdown1.588s |
| I73 | C16 W34 W46 | X01–X06 교차 수명·retry·원본·재시작·상태 전환 회귀 | G8; 50-ID 실제 node 원장·아래 실행 결과 |
| I74 | W52 C21 | P/B/D/U/X·실제 gate coverage 누락 점검 | G9; 50 checks +80 stages +C00–C23/W00–W55 machine assertions |
| I75 | W50 C18 | 세 architecture/design·LOCAL provenance·통합 결과/inventory 작성 | G9; 원장/문서/검사/commit/최종 외부 계획 기록 |
| I76 | W51 C19 C20 | 변경 lint·catalog·typecheck·frontend 구조/디자인·backend import 감사 | G9; changed ESLint/type/catalog/frontend architecture/design PASS; backend existing4 separated |
| I77 | W53 C21 W52 | final diff·contract/coverage·branch·자료/process 소유 최종 확인 | G9; 원장/문서/검사/commit/최종 외부 계획 기록 |
| I78 | W54 C22 | 자신의 파일만 명시적으로 stage하고 로컬 커밋 | G9; 이 원장을 포함하는 지정 branch의 local commit;외부 계획에 SHA |
| I79 | W55 C23 | 통합 계획/결과 원장·실제 완료와 미측정 최종 보고 | G9; 외부 통합 계획 §15의 최종 SHA/Git 상태와 사용자 보고 |

## 원본 계획과 미측정 구분

| 원본 | bytes | SHA-256 |
| --- | --- | --- |
| C 계획,24단계 | 44020 | `1AE29A70A7FFBAC62E588E38B13F785428833C6F4983AB7D8BDD813B8021288B` |
| W 계획,56단계 | 76635 | `A20F8FAC63663EA0EF3440764EDC206393C5169C2A2A86B56CF22B94A57291D0` |

불변 원본과 관련 synthetic model-input/automatic/backend/browser/Docker 검증을 완료했다. 실제 유료 모델의 답변 개선·자연 자율활동 장기 관찰·원본 Docker deployment/사용 DB migration·Windows native Vec1 DLL·Windows 설치 앱 payload/migration·물리 모바일·직접 USER CHECK는 수행/측정하지 않았다. narrow browser layout을 모바일 실기기 결과로 보고하지 않는다.

최종 SHA·git 상태와 시험용 process 종료는 workspace 통합 계획 §15와 최종 응답에서 실제 commit 후 확인한다. 전체 suite/PR/push/원격 CI/main 작업을 이번 완료 판정에 추가하지 않는다.
