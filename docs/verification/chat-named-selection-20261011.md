# Chat 인물 이름 계약·역할 전달 구현 및 관련 검증 결과

작성일: 2026-10-11 (Asia/Seoul)

계획: `D:/project_code/angmoo-workspace/docs/plan/10-11 Chat 인물 이름 계약과 역할 전달·검색 참조 오류 해소 코드 구현 세부 계획.md`

저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`

브랜치: `feat/0.1.0-release-readiness`
시작 HEAD: `27a9218f53a686079ba91a3fb3a4a4eecdf09c7c` — 시작 working tree clean.

## 1. 구현 판정과 적용 범위

I00–I31의 제품 코드·문서·직접 관련 검증을 수행하며 이 결과를 로컬 커밋에 포함한다. 최종 로컬 SHA와 종료 상태는 workspace 결과 문서 및 작업 완료 보고에 기록한다. PR·push·CI 실행·main merge는 하지 않았다. 원본 Docker 재시작/빌드, 설치 앱 변경, 원본 DB/실패 기록/기억/API 키 수정, 실제 외부 AI·임베딩 호출도 하지 않았다.

`social_hybrid`의 새 Chat 요청은 `selection-args.hybrid.v2`를 사용한다. 첫 Supervisor의 모델 출력에서 검색용 `ref`를 제거했다. 형식이 잘못된 별칭을 허용하거나 고쳐 받아들이는 대신 **모델 출력 계약을 이름·역할로 교체하고 그 계약을 엄격히 검사**한다. 서버 내부 식별·출처·권한·실행 계약은 보존한다.

실제 사건에서 확인된 실패는 `router_schema_rejected` / `entity_ref_invalid`이다. 당시 잘못된 반환 문자열 자체는 보존된 증거로 확인하지 못했다. 시험의 underscore 별칭과 `context_person_1`은 **synthetic 회귀 입력**이며 실제 실패 원문으로 판정하지 않았다.

## 2. 변경한 계약

```json
{
  "entities": [
    {"mention": "Bram", "role": "actor"},
    {"mention": "진구", "role": "target"}
  ],
  "relationship": {
    "perspective": "responding_character",
    "from_name": "Bram",
    "to_name": "진구",
    "dimension": "affinity",
    "requested_polarity": null
  }
}
```

이는 의미 필드의 발췌이며 완전한 native call은 기존 intent/time/aggregation과 CANONICAL의 search_text 계약을 함께 따른다. 인물 항목은 정확히 두 필드, 최대 4명이다. null 관계, 0명·1명, 상대 미지정 질문을 허용한다. 잘못된 role·추가 ref·중복 이름·반쪽 관계·미선언 endpoint·뒤바뀐 계약은 거절하며 관계를 지워 성공시키지 않는다.

검사한 이름을 입력 순서대로 서버가 `entity-1` 등 내부 참조에 연결한다. 기존 intent/실행 arguments와 actual-ID 방향 검사를 재사용하며 model calls와 effective calls를 구분한다. 실제 입력 작성자용 `requester_character`·`context_person_1` 등은 별도 계약이어서 유지했다.

Runtime은 `WorldCharacterConfiguration.profile`의 effective World 이름/handle을 읽는다. 고정된 참가자·선택 작성자 이름의 실제 ID와 현행 이름 후보를 합쳐 중복 ID를 제거한다. 이름은 trim 후 정확 비교하며 case/Unicode/내부 공백을 유지한다. 명시적인 @handle만 기존 정규화를 사용한다. 전역 Character 이름 fallback, 번역·음차·fuzzy 연결은 추가하지 않았다.

World/활성 membership/삭제·moderation/차단 자격을 유지한다. 한 이름은 최대 5개 후보와 초과 sentinel 1개만 반환한다. 손상 profile·권한을 잃은 frozen ID·불완전 후보는 유일한 연결로 간주하지 않는다. 동명이인·같은 actual ID로 향하는 관계를 role 또는 첫 row로 결정하지 않는다. 유효한 미확정 이름은 hybrid에서 해석 자료로 남고, Memory 조회 scope는 허가된 **응답 캐릭터**에 고정된다.

## 3. 지침·해석·역사 호환

- role 5개 의미는 immutable `person_roles.py` 한곳에 있다. 첫 호출의 CANONICAL schema에 한 번 설명하고 다른 control은 그 설명을 참조한다. CRG에는 같은 정의를 한 번 제공한다.
- 첫 호출 전용 **영어** 지침은 현재 사용자를 작성할 때 이미 공급하는 `chat_participants.user.name`을 그대로 사용하게 한다. 기존 공통 발화자·인용·1인칭 해석을 반복하거나 특정 언어 단어 치환을 추가하지 않는다.
- `hybrid-admission.v2`가 이름·role·resolution·요청한 이름 방향을 CRG에 전달한다. actual ID, 후보 ID와 서버 내부 entity ref는 그 해석 payload에 포함하지 않는다. role은 해석 참고 자료이며 사실·권한·관계 방향을 대신하지 않는다.
- CRG에는 원래 질문의 인물·방향과 제공된 관련 근거를 연결하는 영어 안내만 보완했다. 사실·불확실성·페르소나·private-state·직접 도구 호출 금지 규칙은 유지했다. 상상/추측 질문에 관계 쌍이나 근거를 억지로 요구하지 않는다.
- 요청/question/intent/resolved/evidence/역할·이름·방향의 불일치와 해시 변조는 거절한다. v1 해석 payload와 content hash는 소급 변경하지 않는다.
- 서버가 접수한 `_selection_protocol`을 schema/parser/repair에서 요청별로 사용한다. shared provider의 옵션은 수정하지 않는다. marker 없는 요청은 역사 경로를 유지하고, 존재하지만 손상되거나 모드·identity가 맞지 않으면 provider/image 작업 전에 실패한다.
- 같은 idempotency replay는 원래 요청을 유지한다. 명시 retry는 보존된 identity가 있으면 새 v2 요청을 만들며 원래 이름·모델·credential binding·World 설정·환경·상황기억 정책·user message·response slot을 유지한다. identity가 없는 역사 retry는 이름을 추측해서 보충하지 않고 역사 계약을 유지한다. 기존 실패 row는 그대로 남는다.

**상황 설명의 언어 지침은 변경하지 않았다.** `situation_generation.instructions()`의 `Use {locale} for this description regardless of the language of the visible reply or post`가 계속 최종 호출에 포함된다. 기준은 접수 시 고정한 **`memory_search_locale`**이며 UI/페르소나/지침 언어와 구분한다. 실제 adapter 시험에서 `ko-KR` 지침과 한국어 설명 접수·저장을 확인했다. 모의 응답이 언어를 이해했다는 품질 판정은 하지 않았다.

## 4. 검증 중 발견한 수정과 보존 계약

1. **DB 읽기 transaction의 provider await 연장:** scope 확인 및 최종 Memory source capture가 읽기를 열었다. 새 v2 경로는 기존 Runtime UoW의 checkpoint를 두 provider 호출 직전에 사용한다. Session 소유권을 adapter로 넘기거나 pool을 늘리지 않았다. 실제 composition을 가로챈 모든 Supervisor/CRG await에서 `db.in_transaction()==False`였다. source capture는 한 최종 JSON/prompt로 이루어지고 post-provider fence/현재 권한/atomic commit은 유지한다.
2. **clarification 전환 후 해석 상태 불일치:** World 확인이 필요해 실행 방향/시간 필터를 비웠는데 새 해석에는 이전 resolved 상태가 남을 수 있었다. requested names/direction은 보존하고 v2 적용 상태를 최종 resolved envelope에 맞췄다. 엄격한 assertion을 제거하지 않았다. 실패하는 회귀를 먼저 재현한 뒤 통과시켰다.
3. **진단 시점:** 실패 trace를 갱신한 뒤 diagnostic snapshot을 만들도록 순서를 고쳤다. 검사하지 않은 meaning/coordination을 PASS로 기록하지 않는다. v2 named endpoint를 v1 from/to로 오판하지 않으며 raw 이름/질문/키를 failure trace에 추가하지 않았다.
4. **명시 retry의 상황 정책:** 원래 `_situation_policy`도 새 retry에 보존하도록 연결했다. 이를 새 이름 계약 때문에 현재 설정으로 다시 캡처하지 않는다.
5. **기존 시험 fixture:** 기존 `test_response_name_binding.py`는 역사 memory producer/legacy Router를 사용하는 시험이었다. 새 admission과 모의 legacy 실행기를 섞으면 protocol mismatch로 실패하므로 해당 fixture에 `legacy_checkpoint`를 명시했다. 3개 실패 후 해당 파일 4개 모두 통과했다. 새 v2 통합은 실제 production composition으로 별도 시험한다.

새 source schema/table/migration, 기존 receipt/실패 기록 재작성, 전면 색인 재생성은 없다. 최종 serialization·상황 manifest·관계 delivery의 같은 prompt/payload digest, 원문 author/fragment/span/hash 및 UoW를 검사했다. 새 v2 CANONICAL+Memory ON 접수분을 실제 `apply_page`로 처리해 정식 Memory 생성도 확인했다. 정상적인 관계 version 6→7, 변조·접근 회수·원문 변경·rollback은 관련 기존 소비자 시험으로 검증했다.

## 5. 최종 직접 관련 검증

전부 격리 fixture DB, `ANGMOO_DENY_EXTERNAL_NETWORK=1`이다. 전체 backend suite, frontend suite/build, 원격 CI는 수행하지 않았다.

| 묶음 | 최종 결과 | 범위 |
| --- | --- | --- |
| 이름 schema/CRG 및 기존 native·hybrid·trace 회귀 | **285 passed**, 19.39초 | 새 계약, SDK schema 변환, 5 roles, 해시/변조, 동시 v1/v2/no-marker, 관련 legacy/control/positional/graph 의미와 안전 진단 |
| 실제 새 접수/lifecycle와 SQLite resolver | **34 passed**, 32.38초 | replay/retry/손상 metadata, USE_CONTEXT/CANONICAL/CLARIFICATION, Memory ON/OFF, repair·실패·취소·deadline, 다른 World/동명이인/개명/권한/한도 |
| 위 묶음의 v2 Memory 소비 보완 | **1 passed**, 9.56초 | 이미 계산에 포함된 Memory ON+CANONICAL 1개에 정식 저장 assertion을 추가한 후 재검증; 추가 건수로 합산하지 않음 |
| 기존 Chat 이름/실제 serialization/receipt/fence 관련 회귀 | **82개 최종 통과** | 최초 79 passed/3 failed 이후 해당 legacy fixture 파일 **4 passed**, 7.00초; 다른 78개는 변경 영향이 없어 반복하지 않음 |
| Memory 공개 DTO·변조·현재 권한 관련 소비자 | **14 passed**, 72.60초 | HTTP scope/CSRF/extra proof/cursor와 저장 포기 DTO, manifest 변조 8종, 현재 privacy/원문/참가자 회수 4종 |
| 동일 4-person fixture 비용 비교 | **2 passed**, 9.21초 | 32명/256명 World의 실제 SQL·query plan·반환 후보·byte·짧은 resolver 지연 |
| 수정 Python compile / diff whitespace | **PASS** | 수정 app 파일만 compileall, `git diff --check` |
| 이번 import 변경 경계 | **PASS**, 신규 위반 0 | 실제 HEAD AST와 working-tree AST를 동일 policy로 비교; baseline/예외 정책 수정 없음 |

중복 없이 관련 pytest **417개**를 계산했다. HTTP 관련 Starlette/httpx/anyio deprecation warning은 별도 기록이며 실패가 아니고 이번 계약과 무관한 의존성 변경을 추가하지 않았다.

전체 live AST checker는 **PASS가 아니다**. 시작 HEAD에서도 다음 동일한 6개 진단이 있었고 이번 변경 후 증가하지 않았다: Chat evidence_reads→Memory activity_situation 및 Chat relationship_evidence_policy→Relationships social_context_validation의 cross-domain/role 진단 4개, Identity world_credentials↔world_image_credentials와 Memory activity_situation↔situation_source_binding cycle 2개. HEAD 1495 modules/6404 edges, 변경 후 1496/6418; 신규 위반 0, 제거 0이다. 정책 예외나 stale baseline 재생성으로 감추지 않았다.

## 6. 비용과 한계

같은 4명(Bram, 진구, Person 0, Missing), 같은 실제 반환 ID 3개, resolver 반복 3회 median이다. 테스트 머신·SQLite fixture 수치이며 production 지연/토큰/모델 품질 측정이 아니다.

| World 규모 | v1 SQL/반환 | v2 SQL/반환 | v1 median | v2 median |
| --- | --- | --- | --- | --- |
| 32명 | 7 / 3 | 7 / 3 | 6.135ms | 6.027ms |
| 256명 | 7 / 3 | 7 / 3 | 8.281ms | 9.631ms |

| 직렬화 자료 | v1 bytes | v2 bytes |
| --- | --- | --- |
| 첫 호출 tools schema | 11,501 | 12,889 |
| 첫 호출 system prompt | 3,854 | 4,222 |
| 첫 호출 user prompt | 418 | 418 |
| interpretation | 517 | 548 |
| CRG system prompt | 6,169 | 6,981 |
| CRG user prompt | 1,205 | 1,236 |

World roster를 provider 입력이나 앱 메모리로 가져오지 않았다. 이름 읽기는 4회, per-name LIMIT 6(후보 5+sentinel)이고 동일 actual ID 자격/차단 읽기는 요청 내 memoize한다. 실제 query plan은 `ix_world_characters_world_status`로 World/활성 상태를 좁히고 membership/Character/configuration PK index를 사용한다. 정렬에 temporary B-tree가 있으며 JSON 이름 전용 index는 없다. **LIMIT가 DB의 검사 row 수까지 제한한다고 주장하지 않는다.** 256명 fixture의 작은 ms 차이만으로 대형 World 성능을 보장하지 않는다.

실제 composition의 모의 생성 호출은 정상 **Supervisor 1 + CRG 1 = 2**, schema repair 시 **3**, repair 소진 시 Supervisor만 **2**였다. 새 이름 해석 전용 AI/embedding 호출은 추가하지 않았다. Memory ON+CANONICAL의 기존 hybrid executor 호출은 유지하며 모의 embedding 사용량은 0이었다. 실제 provider token/가격/first-pass 비율은 측정하지 않았다. tools/지침 bytes 증가가 비용 tradeoff이며 별칭 생성 실패 책임 제거와 역할 활용 계약을 얻는다.

## 7. V01–V14 ledger

| 검증 | 판정 | 증거 |
| --- | --- | --- |
| V01 | PASS | name schema/parser + native tools/SDK 변환 및 old options |
| V02 | PASS | synthetic v1 invalid alias 거절, v2 ref 없이 변환, strict negative fixtures |
| V03 | PASS | 격리 SQLite World effective names, frozen 개명·다른 World·사용자 이름 |
| V04 | PASS | 이름 충돌/handle/Unicode·내부 공백/sentinel/손상·차단·삭제·탈퇴 |
| V05 | PASS | empty/1-person/null 관계/unknown CANONICAL·USE_CONTEXT, fixed responder scope |
| V06 | PASS | 실제 admission/replay/explicit retry, unknown marker pre-provider 실패, concurrent provider 옵션 |
| V07 | PASS: 전달·지침 | 실제 assembled/native SDK schema, ko/en/es 참가자·인용/Unicode fixture; 언어 이해 품질은 미관찰 |
| V08 | PASS | 5 roles, v2 final payload/freeze/hash/assertions, v1 literal payload/hash 보존 |
| V09 | PASS | actual composition/commit, bounded repair, v2 deadline·취소 + 기존 late/fence/rollback nodes |
| V10 | PASS | 최종 prompt/capture digest, v2 receipt 실제 소비, 기존 원문·author/span·관계 6→7/출처 guard |
| V11 | PASS | 폐쇄 진단·not_evaluated, 실제 공개 Chat/Memory DTO 및 HTTP 관련 회귀 |
| V12 | PASS: fixture 측정 | SQL/rows/query plan/bytes/32·256명/ms/physical calls, 두 provider await의 DB transaction 종료 |
| V13 | 해당 없음 | frontend/public schema/user-facing copy 변경 없음. 전체 frontend 검증 불필요 |
| V14 | 미관찰·선택 | 실제 모델/비용 시험은 별도 승인 범위; 이번 구현에서 호출하지 않음 |

## 8. I00–I31 ledger

| 단계 | 상태 | 구현/확인 근거 |
| --- | --- | --- |
| I00 | 완료 | branch/HEAD/clean 확인, workspace AGENTS와 세 architecture/design 지침, 최근 Chat 결과 확인 |
| I01 | 완료 | failure mapping, social_hybrid 소비자와 model/internal/source refs 추적; 실제 잘못된 ref 문자열 미확인 구분 |
| I02 | 완료 | selection-args.hybrid.v2 / hybrid-admission.v2, legacy와 nullable/bounds, DB/UI 변경 불필요 |
| I03 | 완료 | parser regression을 먼저 추가하여 새 옵션 미구현 실패를 확인한 뒤 구현 |
| I04 | 완료 | immutable person_roles 의미·기존 role enum 연결 |
| I05 | 완료 | 실제 native named schema와 3 control/SDK 변환 |
| I06 | 완료 | exact entry/role/name/endpoint/nullability 검증 |
| I07 | 완료 | 검증한 name→서버 refs 변환과 방향·해시 보존 |
| I08 | 완료 | 기존 effective_calls/executor arguments 재사용 |
| I09 | 완료 | 요청별 admission marker와 strict reader |
| I10 | 완료 | 명시 retry 새 v2 정책, 원래 snapshot/slot/실패 row·idempotency 보존 |
| I11 | 완료 | immutable request-local provider/repair protocol, 동시 격리 |
| I12 | 완료 | NamedEntityRead·completeness typed port |
| I13 | 완료 | Runtime World profile projection, per-name bounded SQL |
| I14 | 완료 | frozen/current 합집합·ID dedupe, 개명/동명이인/selected author |
| I15 | 완료 | 현재 자격·차단·불완전 후보/direction guard |
| I16 | 완료 | hybrid advisory/고정 responder Memory scope/time·aggregation guard |
| I17 | 완료 | 첫 호출 영어 name/user 출력 규칙, common participant 지침 유지 |
| I18 | 완료 | 실제 native assembly/Google SDK schema, 기존 모델·budget 유지 |
| I19 | 완료 | v1 payload/hash 유지, immutable bounded v2 role/name 해석 |
| I20 | 완료 | intent/role/name/resolved/direction 일치 assertion |
| I21 | 완료 | CRG v2 provider payload·role 의미, actual IDs/internal ref 배제 |
| I22 | 완료 | 질문 인물·방향과 근거 연결 영어 안내, 기존 사실·페르소나/권한 제한 유지 |
| I23 | 완료 | closed named failure paths/index/version/trace, bounded repair |
| I24 | 완료 | 같은 UoW/final payload 양쪽 capture, provider await 전 읽기 checkpoint |
| I25 | 완료 | actual accept→runtime→CRG→commit→v2 Memory apply, Memory ON/OFF/repair/cancel/deadline |
| I26 | 완료 | legacy/no-marker/v1/replay/retry, 관련 old native·positional·graph 회귀 |
| I27 | 완료 | Chat API decoder/기존 실패 stream/evidence/Memory DTO 영향 확인, UI 변경 없음 |
| I28 | 완료 | 32/256명 동일 4인 SQL·rows·bytes·ms와 호출 횟수 측정 |
| I29 | 완료 | scoped pytest/compile/diff 및 actual HEAD AST 대비 신규 경계 위반 0; 기존 6건 별도 기록 |
| I30 | 완료 | backend ARCHITECTURE Chat 항목과 이 결과 문서, rollout/locale/미관찰 구분 |
| I31 | 완료(로컬 커밋) | 지정 branch에서 이번 변경 파일만 stage/commit; 최종 SHA·clean 상태는 workspace 결과 문서/종료 보고 |

## 9. 재현 명령과 frontend 영향

다음은 backend 폴더의 PowerShell에서 실행한 **관련 파일/노드만**의 검증이다.

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK='1'
& .venv/Scripts/python.exe -m pytest tests/chat/test_named_supervisor_selection.py tests/chat/test_named_recall_interpretation.py tests/chat/test_supervisor_control_tools.py tests/chat/test_supervisor_native_tools.py tests/chat/test_supervisor_argument_patches.py tests/chat/test_hybrid_admission.py tests/chat/test_hybrid_canonical_guards.py tests/chat/test_reference_trace.py -q
& .venv/Scripts/python.exe -m pytest tests/chat/test_named_selection_lifecycle.py tests/chat/test_named_retrieval_resolution.py -q
& .venv/Scripts/python.exe -m pytest tests/chat/test_named_selection_cost.py -q -s
& .venv/Scripts/python.exe -m pytest tests/chat/test_response_name_binding.py tests/chat/test_chat_identity_delivery.py tests/chat/test_activity_situation_receipt.py -q
```

또한 `test_p8_l_k_retrieval_router.py`의 strict parser/closed failure/direction-time-caps/hidden identity/repair/deadline/same-world SQL nodes, `test_response_supervisor.py`의 cancellation/worker-commit fence/cancel-after-commit/failed reservation/concurrent isolation nodes, `test_p8_l_p_evidence_response_streaming.py`의 send-replay-retry/repair-exhaustion nodes만 선택했다.

```powershell
& .venv/Scripts/python.exe -m pytest tests/memory/test_situation_recovery_http.py::test_recovery_api_rejects_foreign_scope_csrf_extra_proof_and_cursor_and_resolves_exact_request tests/memory/test_situation_recovery_http.py::test_off_discard_works_for_damaged_proof_without_leaking_description_or_reapplying tests/memory/test_situation_proof_guards.py::test_persisted_manifest_tampering_is_not_a_delivery_proof tests/memory/test_situation_proof_guards.py::test_delivery_proof_does_not_override_current_privacy_at_apply_or_hydration -q
```

Import 검사는 `scripts/ci/generate_architecture_inventory.py`의 `build_inventory()`와 `check_architecture_boundaries.check_inventory()`를 로컬 Python에서 호출했다. `git ls-tree`/`git cat-file --batch HEAD:<path>`로 시작 HEAD의 실제 소스 AST를 메모리에서 재구성하여 같은 policy로 비교했다. 기준 파일·policy 예외를 재작성하거나 CI job을 실행하지 않았다.

공개 `WorldChatGenerationRequestRead`/stream failure의 `{failure_class,retryable}`, `world-chat-evidence.v1`, Memory unsaved/processing DTO를 보존한다. 프론트엔드 `features/chat/api/world-chat-client.ts`의 검사와 기존 Chat/Memory 소비자 구조를 확인했고 private protocol/identity/role metadata를 public DTO에 추가하지 않았다. 새로운 사용자 문구/locale key가 없으므로 ko/en 수정과 frontend V13은 해당 없음이다.

## 10. 적용·미관찰·복구

로컬 소스·커밋 완료와 실제 실행 서버 적용은 별개다. 다음 실행에서 새 요청은 v2 admission을 사용하며, 기존 실패 답변은 사용자가 기존 UI의 명시 retry를 해야 새 요청으로 실행된다. 과거 실패를 성공 상태로 바꾸거나 시작 시 일괄 재호출하지 않는다. 원본 Docker/설치 앱 적용, 실제 Chat 모델 첫 통과율·role 적합성·근거 활용 품질, USER CHECK, CI/PR/main 상태는 이번 검증으로 PASS를 주장하지 않는다.

이미 접수한 v2 요청을 v1 parser로 강제 해석하는 되돌리기는 금지한다. 후속 문제는 protocol을 유지한 원인 수정과 사용자의 명시 retry로 처리하며, 원래 실패/채팅/Memory/source proof를 보존한다. 실제 AI 품질 검증이 필요하면 V14의 작은 격리 예산을 별도 실행한다.
