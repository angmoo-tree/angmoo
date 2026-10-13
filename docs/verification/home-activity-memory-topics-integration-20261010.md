# 기기 홈·활동 설정·SNS 기억 출처·World 주제 통합 구현 검증 — 2026-10-10

## 1. 실행 범위와 완료 판정

통합 계획 I00–I63의 제품 코드·관련 로컬 검증·문서·로컬 커밋을 완료했다. 통합 V01–V28, 원본 H 48/S 24 단계와 H 21/S 17 검증, H C01/A01–C72/A72를 아래에 직접 추적한다.

이 문서는 최초 구현 당시의 실행 기록이다. 후속 64단계 재검토에서 등록 연결 정보
실패 시 건너뛰기와 auth/runtime 변경 시 생성·이미지 입력 격리의 누락을 발견해
보완했다. 현재 결과는 [I00–I63 재검토 기록](home-activity-memory-topics-review-20261010.md)을
함께 읽는다. 아래 당시 실행 수·사본·Docker·기존 타입 오류 근거는 그대로 보존한다.

관련 시험의 PASS는 이번 변경에 대한 합성·격리 실행 결과다. 원본 사용자 데이터의 차단 기록 적용, 실제 AI 품질, 설치 앱/실기기, production build/export, 전체 검사·CI·PR·main 완료와 구분한다. 브라우저 시험 파일에 있던 타입 오류 3개는 시작 HEAD에서도 같았으며 제품 타입 검사 실패로 섞지 않는다.

| 항목 | 확인 결과 |
| --- | --- |
| 제품 저장소 | angmoo-tree-angmoo |
| 브랜치 | feat/0.1.0-release-readiness — 같은 브랜치만 사용 |
| 시작 HEAD | 58332ed7b975dd76a6cc9c571d0df73e16351a83 |
| 시작 작업 트리 | clean; 이번 tracked/untracked 변경은 본 작업 소유 |
| 새 스키마 | SQLite v35 / Alembic 20261010_0112, 이전 v34 / 20261009_0111 다음 |
| 원본 데이터 적용 | 0건; 원본 selected generation은 v34 그대로 |
| 외부 AI·이미지·임베딩 API | 0회 |
| Git/실행 경계 | 로컬 커밋만; push·PR·CI·main·설치·배포·전체 build 미실행 |
| 서버 | 시험 전용 Next 3370/static-shell 3371 종료; 원본 Compose 재시작 없음 |

통합 계획의 **수행 기록을 추가하기 전** SHA-256: `4ba3184d9150cdbf2d05f7ccb8e0cc5bdbe1136c72867e6abbf76b5fdd86e651`.

원본 계획의 읽은 버전은 다음과 같다. 이 두 원본 계획은 이번 수행에서 수정하지 않았다.

- 10-10 기기 홈 탐색과 캐릭터 활동 설정·World 주제 정리 코드 구현 세부 계획.md: `0ef85408553f2e5e2c1ef9f9cbdb7f80ad808d1ab8db7c26f4f1c7df44fcd848`
- 10-09 SNS 오늘 활동 부모 글 식별과 상황기억 출처 연결·차단 기록 복구 코드 구현 세부 계획.md: `986300996a8a6ac9bd4864a1d539339212b281deb34b18a31eebd4f9ccc42716`

## 2. 실제 구현과 책임 경계

### 2.1 기본 활동 설정·등록

- GET/PATCH `/worlds/{worldId}/world-characters/{actorId}/activity-settings`는 scope·revision·시간대·ON/OFF·저장 정책·capability/reason을 전달한다. PATCH는 시작/끝 시간, 간격, 게시글/답글 상한, 게시글/답글/좋아요 허용의 8개 정책과 CAS revision만 받는다.
- 기본 화면과 상세 설정은 같은 정책 정규화·WorldCharacterConfiguration·credential·image policy를 공유한다. SNS/image 저장은 기존 purpose/revision·vault·빈 키 유지 계약을 사용한다. 이미지 생성 OFF/20, 인식 10 기본값과 기존 옵션/ComfyUI/Partner 경계는 유지한다.
- claimed local owner → creator 접근 → 소유 캐릭터 → 같은 World의 활성 membership → pending/inactive/active autonomous actor → 삭제/차단 상태를 검증한다. 개시 전 기본 세 카드 조회·저장은 허용하지만 ON 및 기존 Chat/인식/graph/일반 published-entry 권한을 확장하지 않는다.
- read/dashboard/실제 ON은 저장된 정책·SNS 키/모델·World 공개·readiness·maintenance의 공통 판정을 사용한다. DAILY_PREPARATION에서 이미 생성된 오늘 계획을 ON의 선행조건으로 만들지 않는다. 기존 준비/일정/lease/CAS/OFF 뒤 admitted run 정책을 유지한다.
- 등록은 OFF로 원자 저장한다. registration_scope는 durable receipt의 World/actor/character로 반환한다. UI는 등록 후 6단계의 선택 세 카드로 바로 연결하며 응답 유실·중복·새로고침에서 같은 receipt를 복원한다.
- activity/SNS/image의 세 카드 조립은 composition에 있다. feature는 다른 feature를 직접 import하지 않는다. 저장은 카드별로 명시하고 일부 성공·실패를 보존한다. scope/runtime/auth별 editor, abort, dirty/busy leave guard, 최신 값 재조회·같은 항목 충돌 확인으로 입력을 보호한다. 완료/건너뛰기는 저장이나 ON을 암묵 실행하지 않는다.

소유 파일: [management 서비스](../../backend/app/domains/world_characters/service/management.py), [basic DTO](../../backend/app/domains/world_characters/schemas/basic_activity.py), [등록](../../backend/app/runtime/characters/registration.py), [세 카드 조립](../../frontend/src/composition/screens/world-character-basic-settings.tsx), [기본 편집 카드](../../frontend/src/features/characters/components/basic-activity-settings-card.tsx), [생성 조립](../../frontend/src/composition/screens/agent-creation-screen.tsx).

### 2.2 SNS parent 입력과 과거 출처 복구

- TodayActivityRecord의 parent_post_id를 source/target/root ID와 분리한다. SocialEvent와 본인 게시글 두 생산 경로가 이미 읽은 canonical parent를 재사용한다. parent body/title과 ID 쌍은 asdict/최종 projection/name binding/budget 경로를 통과한다. 본문이 있는데 ID가 없는 모순 입력은 Memory OFF라도 SDK 전에 차단한다.
- 새 source capture는 실제 parent ID/전달 범위·payload hash를 사용한다. target_post_id의 기존 행동 대상 의미는 유지한다.
- 과거 복구 후보는 SNS v2 background POST/REPLY의 정확한 `/context?/today_activity/records/<n>/parent_body` 경로와 빈 source/delivered ranges로 제한한다. 같은 record의 정상 `/body` 전달 증거, unchanged child digest와 직접 부모, parent≤child≤capture 시각, 같은 World·현재 접근, 원래 전달된 **전체 UTF-8 부모 본문 SHA-256 일치**를 모두 입증해야 한다.
- `memory_situation_source_bindings`는 manifest+ordinal PK/FK와 고정 policy/original/basis/resolved source/time/resolution digest를 저장한다. raw manifest/receipt/admission/call/payload bytes·hash를 수정하지 않는다. Memory 순수 policy와 같은 Session의 typed Runtime source resolver를 사용한다.
- restore_context는 원본 무결성을 먼저 검증한 뒤 정정 proof view를 복원한다. binding insert와 기억/근거/색인 대상/receipt 적용은 같은 바깥 UoW에 있다. 개별 실패의 savepoint와 전체 실패의 rollback을 검증했다.
- request/run/attempt의 validation revision을 고정한다. v2 진행 작업은 옛 규칙, 새 요청은 v3 규칙을 쓴다. unknown revision은 terminal 오류로 멈추고 같은 요청의 자동 재해석은 거절한다. 기존 완료 결과는 유지하며 새로운 명시적 v3 재검사는 허용한다.
- pending의 manual/scheduled/quit만 정상 저장 경로에서 판단한다. blocked는 기존 owner 개별/전체 재검사로만 복구한다. GET/startup/migration에서 자동 복구하지 않는다. 다시 확인·전체 재검사·저장 포기와 원문 보존은 그대로다.
- 저장 후 detail/correction/hydration/recall/prior/HotBrief는 같은 context와 현재 접근을 검증한다. fixed binding도 현재 child digest/직접 관계·부모 전체 본문 및 접근 변경에서 차단된다. 새 기억은 incremental eligibility로 한 번 등록하며 기존 전체 자료 재색인은 하지 않는다.

소유 파일: [Today 계약](../../backend/app/domains/social/contracts/today_activity.py), [SNS capture](../../backend/app/runtime/autonomous_activity/situation_memory.py), [순수 복구 정책](../../backend/app/domains/memory/policies/situation_source_binding.py), [같은 Session 저장](../../backend/app/domains/memory/repository/situation_source_bindings.py), [apply](../../backend/app/domains/memory/repository/situation_apply.py), [Runtime sources](../../backend/app/runtime/memory/situation_sources.py).

### 2.3 World 주제·홈·상태·관계 UI

- World catalog/관계 초기화를 World 추천 생성에서 분리했다. World 생성/개시/재개/과거 marker의 provider dispatch·늦은 apply를 종료했다. World 전용 GET/key PUT/regenerate POST는 기존 인증/접근 검사 후 `410 world_recommendation_topics_retired`다.
- 추천 사전은 유효 캐릭터의 common/World-scoped 관심 출처를 사용한다. OFF/inactive 관심, 공유 ID·최대 6개·cache/history/epoch·기존 PostTopic과 World 입력은 보존하고 World-only/탈퇴/삭제 출처를 제외한다.
- Studio 세 주제 도구/전용 조립을 제거했다. 캐릭터 주제 패널의 Feed 진단·이력·빈 영역을 DOM에서 제거하고 상태/모델/태그/재생성/갱신과 API DTO의 recent_deliveries/feed_status는 유지했다.
- Device Home 자신의 footer 4링크와 전용 reserve만 제거했다. 기존 아이콘/World 순서·single scroll·safe-area·다른 화면의 탐색·World 5탭·직접 URL의 Home fallback을 유지했다.
- 관계 embedded header는 다른 World 탭과 같은 20px padding/12px gap/48px icon 문법을 사용한다. 추가 중심 이름 줄만 제거하고 graph의 노드 이름·깊이·근거·fallback을 보존한다.
- 활동 방식 카드는 실제 engine/출처·캐릭터 상속 null/명시 V2·CAS/전환/busy/오류를 유지하고 감정/최근 실행 UI를 제거했다.
- World 상태 최상단 카드 순서는 상태 → mood/강도 → 메모 원문 → confirmed_at → 이름/소개 → 최근/다음 활동이다. 해당 handle badge만 제거하고 Device 카드는 유지한다. 활성 status 탭의 scoped current_state GET만 사용하고 AI/PUT/polling을 추가하지 않는다.
- 계획 4행은 독립적으로 처음 접혀 있고 관심 태그는 6개 뒤 화살표로 모두 펼친다. 44px chevron·고유 aria-expanded/controls·키보드·원문을 사용한다. 설정 링크/+N/접기 문구는 제거하며 펼침으로 추가 요청/쓰기를 실행하지 않는다.

## 3. 관련 검증 결과와 재실행 경로

| 증거 ID | 실행·결과 | 범위/한계 |
| --- | --- | --- |
| B1 | 핵심 backend 10개 파일 **89 passed**, 305.34s | basic/parent/receipt/binding/migration/World retirement/actor 준비·route·사전. synthetic 임시 DB, 유료 API 0 |
| B2 | 등록·receipt·실제 HTTP·동시 등록·rollback·카드/새 World 복사 **7 passed**, 31.29s | scope 추가 뒤 등록 통합 소비자; 추가 HTTP scope assertion 1회 재확인 **1 passed**, 8.00s. 같은 사례를 두 번 합산하지 않음 |
| B3 | 기존 관련 shared proof/delivery/recovery/relationship/topic cycle **52 passed**, 178.89s; parent/recall/basic 중간 묶음 **43 passed**, 219.59s | 작업 중 영향 사례; B1과 중복이 있으므로 고유 총수로 합산하지 않음 |
| D1 | 격리 Docker 기본 묶음 **39 passed**, 385.69s; 현재 guard/FTS/HTTP/image 추가 묶음 **12 passed**, 113.07s | 일부 중복 실행. 이번 backend를 RO mount, UID/GID10001, network none, 임시 fixture에만 쓰기 |
| U1 | Next와 실제 StaticProductRouter **62 passed**, 3.2m | Next dev3370/static-shell dev3371; 31개 사례를 각 profile에서 실행 |
| U2 | 기존 engine/생성 return/Studio 소비자 **4 passed**, 11.3s | Next 1 + static 3. native invoke는 mock; 실제 설치 앱 증거 아님 |
| S1 | ESLint **29 files, exit0**; 관련 제품 strict tsc **exit0** | 원래 tsconfig extends, 실제 dependency graph; 새 stub/any/ts-ignore 없음 |
| S2 | Python compile/AST **45 files**; backend **33 seeds/836 transitive modules**, frontend **29 seeds/302 transitive files/1141 edges** | 관련 import rules/delta 검토. 전역 layout/CI checker PASS를 표방하지 않음 |
| S3 | raw color 증가0, undefined CSS token0, production any/suppression 증가0, locale 4쌍 key 차이0, dependency 변경0 | 변경 파일과 실제 source token/locale만 검사 |
| S4 | 관련 browser tsc: 시작 HEAD와 현재 모두 TS2322 2개+TS2339 1개 | static-product-shell의 기존 fixture 타입 3개. new error0; 전체 browser typecheck PASS 아님 |
| H1 | 과거 delivery_proof_missing 36건 개별 exact parent 입증 및 사본 적용 **36/36** | 원본 적용0, source copy 불변, provider0, 현재 접근 가능36, incremental eligibility36 |
| P1 | 원본 DB/선택 marker 시작·끝 hash 동일 | 선택 v34, secret 파일 존재·RO mount; 원본 서비스 재시작/키 원문 출력 없음 |

Browser JSON/screenshot은 제품 저장소 ignored `artifacts/home-activity-memory-20261010/`에 있다. `browser-results.json`은 U1, `consumer-final-results.json`은 U2다. 해당 profile의 `static-export`라는 시험 이름은 **development StaticProductRouter**를 뜻하며 production static export build를 실행했다는 뜻이 아니다.

workspace의 `.local-diagnostics/home-activity-memory-20261010/`에는 scope 설정/정적 검사 JSON, 일관된 historical-v34 복사본·복구 사본·개별 classification JSON·original-preservation JSON·로컬 코드 commit 목록을 보존했다. 사본 DB는 사용자 대화/암호화 credential을 포함하므로 Git에 추가하지 않았다. 보고 문서에는 키·원문 대신 안전한 ID/해시/개수만 쓴다.

backend의 실제 핵심 실행 명령(제품 저장소에서):

```powershell
uv run --directory backend python -m pytest `
  tests/world_characters/test_basic_activity_settings.py `
  tests/memory/test_situation_parent_binding_recovery.py `
  tests/migrations/test_situation_parent_binding_upgrade.py `
  tests/migrations/test_world_configuration_v28_recovery.py `
  tests/runtime/test_sns_situation_parent_binding.py `
  tests/social/test_today_activity_parent_identity.py `
  tests/social/test_world_topics_retirement.py `
  tests/social/test_topic_preparation.py `
  tests/social/test_recommendation_routes.py `
  tests/social/test_recommendation_topics.py -q --tb=short
```

등록 관련 실행 node는 test_local_creator_v2의 atomic_off_and_replayed, registration_detail, registration_failure, two_independent_sessions_register, http_keyless_register와 test_creator_card_registration의 card_final_edits, copy_new_world이다. 실제 전체 함수 이름은 해당 test 파일에 유지했다.

브라우저는 시험 전용 두 서버를 시작한 상태에서 browser-tests 디렉터리의 `playwright.home-activity-memory.config.ts`를 사용했다. API는 fixture가 intercept하고 미등록 요청/외부 network는 차단한다. 원본 3000/8080 서버를 시작할 필요가 없다.

```powershell
pnpm exec playwright test --config playwright.home-activity-memory.config.ts `
  --grep 'integration|status-summary|world-relationships|Status cards|keyless registration|English six-step'
# 기존 직접 소비자만 별도:
node node_modules/@playwright/test/cli.js test --config playwright.home-activity-memory.config.ts `
  --grep 'personalized settings|Tauri Phone retries Creator Studio return|returned Studio preselects'
```

Docker 시험은 기존 runtime image의 Python을 entrypoint로 지정하고 현재 backend를 `/current`에 RO mount/PYTHONPATH로 연결했다. `/current`의 tests를 읽고 network none·기존 UID/GID로 fixture temp directory만 쓴다. 원본 volume은 시험 container에 연결하지 않았다. 원본 보존 비교용 container만 원본 volume을 **RO**로 읽었다. 컨테이너들은 `--rm`, 시험 전용 dev server도 종료했다. 이미지·원본 container/volume·prune·설치 파일은 건드리지 않았다.

## 4. 필수 동작 판독과 수정한 부분

1. 정정은 source guard를 생략하는 방식이 아니다. 동일 payload record의 정상 child 증명과 원래 전달된 전체 부모 hash를 검증해 잘못 붙은 ID만 별도 view로 해석한다. 부분 fragment/유사 문자열/다른 record, child 편집·reparent·미전달·시각 모순, parent 편집·private/삭제/숨김·접근 차단은 거절한다.
2. fixed binding 생성 뒤에도 child·parent의 현재 사실을 다시 검증하도록 보강했다. FTS가 ID를 선택한 다음 parent가 바뀌어도 hydration은 반환하지 않는다. fake 임베딩 provider는 신규 기억에 1회만 호출했고 같은 기억 재색인은 current로 끝났다. 실제 임베딩/의미 품질을 측정한 것은 아니다.
3. 실패 receipt의 binding이 남지 않도록 nested savepoint, 바깥 UoW 실패의 전체 rollback을 확인했다. shared manifest를 사용하는 한 기억 폐기/다른 receipt 저장·마지막 owner 삭제의 FK cascade와 원래 게시글 보존도 확인했다.
4. unknown revision의 replay/resume은 frozen 정책을 해석하지 않고 거절하도록 보강했다. v2 진행 기록은 v2, 새 명시 요청은 v3다. SQL blocked→pending이나 startup/migration 복구는 없다.
5. 기본 editor는 같은 scope의 갱신에서 편집하지 않은 항목만 합치고 같은 항목의 서버 변경은 입력을 보존한 채 확인을 요청한다. runtime/auth/scope가 바뀌면 오래된 editor/응답을 폐기한다. engine select의 label 연결도 명시해 접근 가능한 이름을 보존했다.
6. 기존 v28 recovery test의 최신 목표 v32를 v35로 고쳤다. 과거 v27/29/30/31/32/33/34 schema digest는 그대로다. World 생성 관련 test는 종료된 World 요청의 410·actor 준비의 성공/실패·stale/CAS/동시성 기대를 함께 확인하도록 바꿨으며 negative/rollback 검사를 제거하지 않았다.
7. 초기에 잘못 실행한 static profile/직접 URL의 dev 404는 실제 static-shell 및 production fallback과 같은 document fixture로 바로잡았다. 최종 U1/U2는 실제 StaticProductRouter source를 읽었다. 테스트 전용 fallback을 제품 routing 변경으로 섞지 않는다. draft image 시험의 기존 미지원 Comfy server-key 가정은 지원되는 NovelAI credential 계약으로 바꿔 기존 옵션/blank key/CAS를 시험했다.
8. 등록 시험에서 ORM Character를 DTO 대신 반환하던 monkeypatch를 제거해 실제 결과/receipt/HTTP scope를 검증했다. atomic OFF·중복 방지·동시성·실패 rollback 검사를 유지했다.

pytest의 Starlette/httpx·anyio deprecation warning과 Playwright NO_COLOR/FORCE_COLOR warning은 남아 있다. 이번 기능 실패로 분류하지 않았고 이 작업에서 의존성을 변경하지 않았다.

## 5. 정식 migration과 사용자 데이터 보존

Alembic/embedded migration 모두 v35 DDL을 쓰며 ORM/manifest 동등성과 populated forward upgrade를 검증했다. 새 table은 비어 있어야 한다. raw historical manifest/receipt/run/기억/키는 migration으로 수정하지 않는다. 역사 metadata builder에는 새 table을 섞지 않았고 packaging의 기존 wildcard 자원 경로를 유지했다. staged failure는 기존 DB·키·선택 marker를 보존하고 재시도만 정식 promotion을 수행했다.

사본 classifier는 preserved v34를 새 사본으로 SQLite backup한 다음 **v35 delta를 그 사본에만 적용**해 기존 owner recheck/apply/UoW를 실행했다. 이 사본은 canonical selected-generation promotion이나 원본 앱 DB 업그레이드의 결과가 아니다. 정식 upgrade의 증거는 별도 migration/Docker fixture다.

| 원본 비교 | 시작과 종료 |
| --- | --- |
| selected generation | `generations/contributor-v2-schema-v3-schema-v4-schema-v9-schema-v-schema-v34` |
| DB SHA-256 | `fc150641325b804fbe42501f21281e8bd14c1f8283d67e285316ef8ed46a0b35` — 동일 |
| marker SHA-256 | `639325fcd64d40fb45fe72dfc39d00b0c7a7647687bf52727aeb8bc78b49197d` — 동일 |
| preserved consistent copy SHA-256 | `f9acdb318446268da2224249dea83dbb1823e8d91b971525716dc62afdeb5534` — classifier 전후 동일 |
| secret 파일 | 원본에 그대로 존재; 이번 코드/시험은 원문 출력/키 변경을 하지 않음 |
| 기존 container | backend Exited(0)/frontend Exited(1), 원래 중지 상태 유지 |
| 원본 적용/재검사 | 0 / 0 |

이번 차단 36개는 기술적으로 exact parent 조건을 통과해 **사본에서** 기억 36개와 incremental eligibility 36개를 생성했고 현재 접근 가능36을 확인했다. 36개의 실제 embedding/FTS 작업을 실행한 것은 아니다. 원본 사용자 UI에서 36개가 복구됐다고 보고하지 않는다.

과거 관찰 문서의 situation_description_missing 1건은 당시 snapshot이다. 이번 일관된 사본에는 같은 별도 오류가 **2건** 있다. 이 둘은 위 parent 복구 36개에 포함하지 않고 설명을 만들거나 자동 폐기하지 않았다.

## 6. 과거 36건 개별 분류

각 행의 “입증”은 original integrity + exact record path + 정상 child delivery/digest/direct parent + 전체 parent body hash/time + 현재 scope/access 검사 통과를 뜻한다. classifier가 resolve/verify 후 같은 apply에서 재검사했으며 immutable payload 보존·FK check0·API0을 확인했다. 안전한 ID만 아래에 싣는다.

| receipt sequence | manifest ID 앞 12자 | candidate ordinal | 입증한 parent ID | 조건/사본 상태 | 사본 memory ID | 원본 적용 |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | f481b3a85bb4 | 9 | post-6b5469068026 | 전부 입증 / applied | c2e3be4e-7f80-4a23-8c2e-b5f88df42a6a | 0 |
| 6 | be6cd6dd93bf | 5 | post-6b5469068026 | 전부 입증 / applied | 4d8efba3-c514-40d5-b304-ed49fe1c2d93 | 0 |
| 15 | 993a55cd449a | 28 | post-6b5469068026 | 전부 입증 / applied | 0add598d-1397-41ee-8d02-07acb5438706 | 0 |
| 16 | 96e43abd6c8a | 23 | post-6b5469068026 | 전부 입증 / applied | b7700aba-44aa-4ce8-8215-a8c057be00b0 | 0 |
| 17 | 0f272fc4a673 | 21 | post-6b5469068026 | 전부 입증 / applied | 96b1efc0-a9c8-44bc-a8cf-8e13cd67a2cf | 0 |
| 20 | 1bf04075378f | 9, 13 | post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 1cab9488-71d7-45ff-a58c-581b281af045 | 0 |
| 21 | a66911dd44c1 | 6, 10 | post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | bb22b5e9-5478-4feb-bddb-5c0b5eb2282d | 0 |
| 24 | 2e01f5d418c1 | 13, 17, 21 | post-2a1d863efedf, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 757f1b43-ea90-4a70-9cd9-fb7e36f61ecd | 0 |
| 25 | 630d42248c44 | 11, 15, 19 | post-2a1d863efedf, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | b289d53f-eda9-4a5e-8ef5-94d3ef6ab342 | 0 |
| 26 | 37902cb46706 | 25, 51 | post-2a1d863efedf, post-6b5469068026 | 전부 입증 / applied | 2e155a43-df1e-4b50-a974-3e7c851f1a80 | 0 |
| 27 | 37902cb46706 | 25, 51 | post-2a1d863efedf, post-6b5469068026 | 전부 입증 / applied | 298aa717-fd6e-42af-b766-283eec58713b | 0 |
| 28 | 93c9576eed6f | 9, 13, 23 | post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | b769303e-9edf-457b-9645-62cea12b8e74 | 0 |
| 29 | 6ecd3d95c311 | 8, 12, 22 | post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | 71a4d032-0f7e-4697-a4bc-c2b41f870e9b | 0 |
| 30 | 05ff6e148125 | 9, 15, 19 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | ffc6677a-27cf-47de-81dd-bb5b2c91d157 | 0 |
| 31 | 2f3e33d0813a | 5, 11, 15 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 77e6cc37-7a8c-499d-8512-03256136c028 | 0 |
| 32 | 0fd182fb2d6f | 24, 28, 40 | post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | ac719c62-3b9f-46aa-b9c8-454f0824b82a | 0 |
| 33 | 0fd182fb2d6f | 24, 28, 40 | post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | 8ed4bc8c-9287-4763-842e-46c0ec6a3d2f | 0 |
| 34 | cda5c43a6fc7 | 13, 22, 26, 38 | post-66f7e7de3d17, post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | f1d26cd2-02b2-4438-b31c-003164bd0f35 | 0 |
| 35 | 2733e26bcee9 | 9, 18, 22, 34 | post-66f7e7de3d17, post-c687fd5bd908, post-66f7e7de3d17, post-2a1d863efedf | 전부 입증 / applied | 3cda6959-ef27-4cd6-934c-33778d3f231b | 0 |
| 36 | 590df0483092 | 10, 16, 27, 33, 37 | post-66f7e7de3d17, post-c687fd5bd908, post-2a1d863efedf, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | bccdc5e6-4326-49c8-b3b6-3355ef91c4cc | 0 |
| 37 | 67500c92e963 | 13, 19, 30, 36, 40 | post-66f7e7de3d17, post-c687fd5bd908, post-2a1d863efedf, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 8c3ce2f3-b005-452e-978e-4d5f1079220f | 0 |
| 38 | cb812f892d80 | 9, 15, 26, 32, 36 | post-66f7e7de3d17, post-c687fd5bd908, post-2a1d863efedf, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 551c18ba-ed45-4782-b71e-8e626093f821 | 0 |
| 39 | 9c64e2478277 | 30, 36, 40 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 3ad139e1-8ca3-4151-9d1d-98b9f819058f | 0 |
| 40 | 9c64e2478277 | 30, 36, 40 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 38ee234b-4428-44c1-860e-89ff63fa95fe | 0 |
| 41 | bafec8614136 | 29, 35, 39 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 7c6d093a-afb3-468c-bc27-dc3146bc2590 | 0 |
| 42 | e4e3c923de40 | 27, 33, 37 | post-66f7e7de3d17, post-db6023a5b377, post-2ade845ce0cf | 전부 입증 / applied | 8f7a55c8-3121-4dec-bca6-d47b74ca58f1 | 0 |
| 43 | 98662fa41229 | 40, 51, 55 | post-66f7e7de3d17, post-c687fd5bd908, post-66f7e7de3d17 | 전부 입증 / applied | 687ba7ed-c2cf-4926-8534-faf32b8f550b | 0 |
| 44 | 98662fa41229 | 40, 51, 55 | post-66f7e7de3d17, post-c687fd5bd908, post-66f7e7de3d17 | 전부 입증 / applied | b335613a-ddff-4944-acd5-dd117497297d | 0 |
| 45 | b512c453d269 | 9, 13, 39 | post-3fe0dc06cc46, post-f53d0283c218, post-66f7e7de3d17 | 전부 입증 / applied | 11d2065e-a82e-4ca3-8779-02828da39585 | 0 |
| 46 | 530e5a4b8c6c | 8, 12, 38 | post-3fe0dc06cc46, post-f53d0283c218, post-66f7e7de3d17 | 전부 입증 / applied | 634df22f-7f6f-4159-998e-ee3e902a1ef1 | 0 |
| 47 | bf1b391cedfb | 21, 37, 43, 54 | post-f53d0283c218, post-66f7e7de3d17, post-c687fd5bd908, post-2a1d863efedf | 전부 입증 / applied | d012a6dc-bb0d-4d4c-a8d6-50ac08fd2340 | 0 |
| 48 | bf1b391cedfb | 21, 37, 43, 54 | post-f53d0283c218, post-66f7e7de3d17, post-c687fd5bd908, post-2a1d863efedf | 전부 입증 / applied | a7117414-fb71-4dfe-9a6b-015b79aa0937 | 0 |
| 54 | b61065e13edc | 31, 35 | post-3fe0dc06cc46, post-f53d0283c218 | 전부 입증 / applied | a5826565-4c24-444e-a9e0-0aad26301a6d | 0 |
| 55 | b61065e13edc | 31, 35 | post-3fe0dc06cc46, post-f53d0283c218 | 전부 입증 / applied | 6c5aced2-2531-4344-8cac-45538205938c | 0 |
| 56 | 6d2f4fce403d | 13, 30, 34 | post-ff89aed62364, post-3fe0dc06cc46, post-f53d0283c218 | 전부 입증 / applied | ae62ab1e-d5fe-460d-bdf6-999f3e664071 | 0 |
| 57 | be1898094078 | 12, 29, 33 | post-ff89aed62364, post-3fe0dc06cc46, post-f53d0283c218 | 전부 입증 / applied | 0e4a129a-c0b6-4e90-abe0-a86574e4bc86 | 0 |

설명 누락의 현재 사본 receipt: 53, 72. 상태 보존, 미적용.

## 7. I00–I63 수행 추적

“완료”는 이 문서와 같이 로컬에 커밋되는 제품 코드·관련 검증·문서 기준이다. I63의 문서 자체 commit SHA는 이 문서 안에서 자기 참조하지 않으며 실제 Git log와 workspace 계획 수행 기록으로 확인한다.

| 단계 | 계획 작업 | 상태 | 구현/증거 |
| --- | --- | --- | --- |
| I00 | 브랜치·작업 트리·지침 확인 | 완료 | 시작 clean/HEAD·AGENTS·architecture/design·원본 추적표·S2 |
| I01 | 통합 계약·제외 범위 고정 | 완료 | 시작 clean/HEAD·AGENTS·architecture/design·원본 추적표·S2 |
| I02 | 실제 소유 파일·소비자·스키마 조사 | 완료 | 시작 clean/HEAD·AGENTS·architecture/design·원본 추적표·S2 |
| I03 | 관련 합성 fixture와 오류 재현 | 완료 | 합성 old-parent/missing-ID/CAS/권한 fixture; B1/U1 |
| I04 | 기본 활동 설정 DTO·API | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I05 | 개시 전 로컬 기본 설정 관리 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I06 | 기본·상세 활동 정책 저장 공유 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I07 | SNS 모델·credential 목적 연결 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I08 | 이미지 정책·credential 연결 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I09 | 공통 activation eligibility | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I10 | ON/OFF mutation·경쟁 처리 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I11 | 기본 설정 backend 관련 검증 | 완료 | basic DTO/공통 정책·credential·image·activation; B1/D1 |
| I12 | 오늘 활동 parent ID 계약 | 완료 | 두 Today 생산 경로/최종 payload/capture; B1/D1 |
| I13 | 두 오늘 활동 생산 경로 수정 | 완료 | 두 Today 생산 경로/최종 payload/capture; B1/D1 |
| I14 | 최종 provider 입력까지 쌍 보존 | 완료 | 두 Today 생산 경로/최종 payload/capture; B1/D1 |
| I15 | SNS 출처 캡처 부모 연결 | 완료 | 두 Today 생산 경로/최종 payload/capture; B1/D1 |
| I16 | 새 SNS 저장 경로 관련 검증 | 완료 | 두 Today 생산 경로/최종 payload/capture; B1/D1 |
| I17 | 과거 정정 typed 계약·순수 policy | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I18 | canonical 자식·부모 Runtime 어댑터 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I19 | append-only 정정 근거 영속화 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I20 | 다음 정식 migration·자원 연결 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I21 | 원본 복원 후 정정 proof view | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I22 | 동일 저장 트랜잭션 적용 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I23 | 조회·수정·검색의 복원 context 공유 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I24 | 기존 재검사·revision 연결 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I25 | 공유 근거·저장 포기·색인 수명 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I26 | Memory 관련 회귀·backend 중간 판독 | 완료 | typed pure policy/fixed binding/v3/same UoW/current access/수명; B1/B3/D1 |
| I27 | 격리 upgrade·Docker 경로 검증 | 완료 | 정식 v35/Alembic·staged rollback·Docker; B1/D1 |
| I28 | World catalog·관계 초기화 분리 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I29 | World 생성·개시·재개 경로 종료 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I30 | World 전용 API 410 적용 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I31 | 캐릭터 출처 사전·cache | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I32 | 관심 주제 패널 최종 계약 적용 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I33 | Studio 주제 조립 제거 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I34 | 주제 종료·역사 보존 관련 검증 | 완료 | World retirement/410·actor 준비/사전/history·UI 소비자; B1/U1/S2 |
| I35 | 기기 홈 navigation 제거 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I36 | 홈 공간·safe-area·복귀 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I37 | 관계 embedded header 정렬 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I38 | 활동 방식 설정 간소화 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I39 | 감정·확인 시각 표현 변환 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I40 | scoped current_state 읽기 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I41 | 중립 상태 카드와 최상단 조립 | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I42 | 계획·관심 요약 링크 제거·chevron | 완료 | home/header/state/engine/chevron; U1/U2/S1–S3 |
| I43 | 활동 설정 form 재사용 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I44 | SNS 저장 후 최신 eligibility 갱신 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I45 | 세 카드 composition 구성 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I46 | autonomy-setup 기본 설정 route | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I47 | 등록 후 6단계 연결 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I48 | receipt·새로고침·중복 복구 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I49 | 완료·건너뛰기·복귀 보호 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I50 | Studio 활동 설정 진입 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I51 | 개시 후 상세 설정 공유 | 완료 | 공유 form/세 카드/등록6단계/receipt/Studio·상세; B1/B2/U1/U2 |
| I52 | 상태·설정·주제 최종 소비자 확인 | 완료 | 최종 조립/ko·en/accessibility/Next·StaticProductRouter; U1/S1–S4 |
| I53 | 한국어·영어·접근성 문구 | 완료 | 최종 조립/ko·en/accessibility/Next·StaticProductRouter; U1/S1–S4 |
| I54 | 관련 화면 1차 브라우저 검증 | 완료 | 최종 조립/ko·en/accessibility/Next·StaticProductRouter; U1/S1–S4 |
| I55 | 36건 개별 분류·사본 판독 | 완료 | 36개 개별 proof·사본36 applied/원본0; H1/P1 |
| I56 | architecture/design·보존·검증 문서 | 완료 | architecture/design/이 문서·scope 정적/타입·보존; S1–S4/P1 |
| I57 | 변경 범위 정적·타입·경계 검사 | 완료 | architecture/design/이 문서·scope 정적/타입·보존; S1–S4/P1 |
| I58 | 통합 관련 backend 회귀 | 완료 | backend 핵심89 + 등록7; 기존 관련 B3, Docker D1 |
| I59 | 통합 관련 브라우저·시각 확인 | 완료 | 최종 관련 browser62+4, 화면 캡처 시각 확인; U1/U2 |
| I60 | 관련 실패 수정·필요한 재확인 | 완료 | 현재 child/access/revision/editor guard 보강·기존 fixture 갱신·해당 재확인 |
| I61 | 계약·단계·검증 추적 완료 | 완료 | 원본72/38/C·A72 → 통합64/28, 아래 직접 대조 |
| I62 | 최종 diff·보존·로컬 커밋 목록 | 완료 | diff check/명시 staging·원본hash/marker·task 서버 종료 |
| I63 | 로컬 커밋·통합 인계 | 완료 | 로컬 backend/frontend/document commits·workspace 수행 기록·최종 Git 확인 |

## 8. V01–V28 검증 추적

| 검증 | 상태 | 실제 판독/증거 |
| --- | --- | --- |
| V01 | PASS | U1/U2: 홈 footer·reserve 없음, icon/World 탭/직접 Home keyboard 복귀·single scroll 보존 |
| V02 | PASS | U1: header20/12/48·추가 center line 없음; 실제 graph name/depth/evidence/fallback 유지 |
| V03 | PASS | U1/U2: onlyCharacter·inherit null/V2·source/version/CAS·needs_preparation/error/retry·old state/run DOM 없음 |
| V04 | PASS | U1: mood/강도/raw note/confirmed/null/OFF/error·late scope/runtime/auth·GET만/AI·PUT·polling0 |
| V05 | PASS | B2/U1/U2: real atomic OFF/registration_scope/duplicate race/rollback·lost reply/reload·sixth step/return retry |
| V06 | PASS | U1: skip no-write·각 카드 save/partial SNS failure·dirty/busy guard·saved 값 유지; U2 return 오류 후 retry |
| V07 | PASS | B1: owner/creator/World/actor/membership/delete/moderation·draft 세 카드 read/save·ON/vision 권한 거절; U1 |
| V08 | PASS | B1/U1: saved SNS model/key/default policy·read/actual ON·key delete·CAS/env lock·DAILY 준비 연결. 기존 admitted OFF 경계 유지 |
| V09 | PASS | B1/U1/B2: purpose/key revision·blank preserve·image options20/vision10·draft image no vision grant·shared full settings |
| V10 | PASS | U1: 계획4 independent raw detail·0/1/6/7/10 topics·44 chevron·aria/focus/keyboard·no link/+N/새 요청 |
| V11 | PASS | U1/B1/S2: Studio tool assembly 및 character Feed 진단 DOM 제거, DTO/모델/주제·준비 소비자 유지 |
| V12 | PASS | B1/D1: World lifecycle/marker/late result provider0·auth 우선410·catalog/관계/actor route 유지 |
| V13 | PASS | B1: actor common/world-scope/OFF·World-only/left/deleted 제외·shared IDs/cache/history/epochs/PostTopic |
| V14 | PASS | B1/D1: 이벤트/본인글 root/직접·중첩 부모 ID/body/source/target/root 분리 |
| V15 | PASS | B1: visibility·empty/body-title pairing·bounded/projection/name/budget·모순 provider0·기존 parent 재사용 |
| V16 | PASS | B1/D1: 실제 parent 전달 범위/해시·성공result/receipt·manual/scheduled/quit와 blocked 분리 |
| V17 | PASS | B1/B3/H1: frozen original bytes/hash/admission/call/result·manifest integrity·tamper 거절·v1/v2 유지 |
| V18 | PASS | B1/D1/H1: exact path/same-record child/current digest/direct parent/전체 body hash/time/access 전부 입증 |
| V19 | PASS | B1/D1: child/parent edit/private/delete/hide/reparent/future·부분·다른 record·child no-range·설명 누락·unknown revision 거절 |
| V20 | PASS | B1/B3/D1: fixed unique/shared binding·savepoint/outer rollback·frozen revision/replay/CAS·recheck/discard/delete |
| V21 | PASS | B1/B3/D1: restore_context 공유·현재 child/parent access·recall hydrate·기존 private Chat/Inbox/관계 스냅샷 관련 회귀 |
| V22 | PASS | B1/D1: incremental eligibility·실제 FTS hit·fake embedding1/재작업0·recall 후 source change 거절·shared/cascade/posts 보존 |
| V23 | PASS | B1/D1: v35 ORM/Alembic/embedded/manifest·populated old rows·과거 builder digest·빈 table/staged failure DB·key·marker 보존 |
| V24 | PASS | D1: 현재 소스RO 실제 load/UIDGID10001/network none/임시fixture39+12; 원본 서비스/AI 변경0 |
| V25 | PASS — 사본 | H1/P1: delivery proof 오류36개 exact/applied36·현재 accessible/eligibility36; 설명 누락 현재2/과거1 별도; 원본0 |
| V26 | PASS — 관련 브라우저 | U1/U2: ko/en·360/390/436/960/1440·200%·44px·aria/Enter/Space/focus·직접URL/reload·same StaticProductRouter; native 실제 측정 없음 |
| V27 | PASS — 관련 제품 검사 | S1–S3: strict production tsc/lint/import/token/locale delta. S4 기존 browser 타입오류3/새0은 별도; 전역 checker 미실행 |
| V28 | PASS — 로컬 | 이 문서/architecture/design/원본72·38·C/A72 추적·P1·명시 staging/local commits. 원본 적용/CI/native와 구분 |

## 9. 원본 72단계·38검증·72계약 직접 추적

원본 표를 통합 계획에서 대조했으며 누락/중복 없이 H48+S24, H21+S17, H C/A72다. 통합 단계/검증의 결과는 §7–8을 참조한다. 같은 검증을 중복 수행한 총합으로 집계하지 않는다.

### 9.1 원본 단계

| 원본 단계 | 원본 작업 | 통합 단계 | 로컬 결과 |
| --- | --- | --- | --- |
| H-I00 | 브랜치·작업 트리·지침 확인 | I00 | 완료 |
| H-I01 | 원본 계약과 변경 범위 고정 | I01 | 완료 |
| H-I02 | 소유 파일·API·소비자 조사 | I02 | 완료 |
| H-I03 | 관련 fixture·검증 입력 준비 | I03 | 완료 |
| H-I04 | 홈 navigation slot 제거 | I35 | 완료 |
| H-I05 | 홈 공간·safe-area·복귀 확인 | I36 | 완료 |
| H-I06 | 관계 embedded header 정렬 | I37 | 완료 |
| H-I07 | 활동 방식 설정 카드 간소화 | I38 | 완료 |
| H-I08 | 감정 표현 변환과 locale 정리 | I39 | 완료 |
| H-I09 | scoped current_state 읽기 연결 | I40 | 완료 |
| H-I10 | 중립 상태 카드 표현 확장 | I41 | 완료 |
| H-I11 | 최상단 상태 카드 조립 | I41 | 완료 |
| H-I12 | 탐색·상단·상태의 관련 검증 | I54, I59 | 완료 |
| H-I13 | 기본 설정 DTO·API 계약 | I04 | 완료 |
| H-I14 | 개시 전 로컬 기본 설정 관리 | I05 | 완료 |
| H-I15 | activity 정책 저장 공용화 | I06 | 완료 |
| H-I16 | SNS credential 목적별 연결 | I07 | 완료 |
| H-I17 | 이미지 설정의 같은 scope 연결 | I08 | 완료 |
| H-I18 | 저장 사실 기반 eligibility 구현 | I09 | 완료 |
| H-I19 | 기존 ON/OFF 요청 연결 | I10 | 완료 |
| H-I20 | backend 기본 설정 관련 검증 | I11 | 완료 |
| H-I21 | activity form 재사용 | I43 | 완료 |
| H-I22 | SNS 저장 결과와 최신 판정 연결 | I44 | 완료 |
| H-I23 | 세 카드 composition 구현 | I45 | 완료 |
| H-I24 | autonomy-setup route 기본 설정으로 개편 | I46 | 완료 |
| H-I25 | 생성 등록 후 6단계 연결 | I47 | 완료 |
| H-I26 | receipt·새로고침·중복 복구 | I48 | 완료 |
| H-I27 | 완료·건너뛰기·복귀 보호 | I49 | 완료 |
| H-I28 | Studio 활동 설정 진입 | I50 | 완료 |
| H-I29 | 개시 후 상세 설정과 공유 | I51 | 완료 |
| H-I30 | 생성·Studio·상세 설정 관련 브라우저 검증 | I54 | 완료 |
| H-I31 | World 초기화 협력 분리 | I28 | 완료 |
| H-I32 | World 개시·생성 경로 종료 | I29 | 완료 |
| H-I33 | World 직접 요청의 410 계약 | I30 | 완료 |
| H-I34 | actor 출처 기반 사전과 cache | I31 | 완료 |
| H-I35 | 공용 주제 패널의 캐릭터 소비자 보존 | I32 | 완료 |
| H-I36 | Studio 주제 관리 조립 제거 | I33 | 완료 |
| H-I37 | 역사 데이터·키·World 원본 보존 | I34 | 완료 |
| H-I38 | 주제 종료·사전 관련 backend 검증 | I34 | 완료 |
| H-I39 | 모든 변경 문구 ko/en 적용 | I53 | 완료 |
| H-I40 | architecture/design·보존 문서 갱신 | I56 | 완료 |
| H-I41 | 변경 파일 정적·타입·경계 확인 | I57 | 완료 |
| H-I42 | 관련 backend 회귀 묶음 | I58 | 완료 |
| H-I43 | 관련 브라우저·시각·접근성 확인 | I59 | 완료 |
| H-I44 | 관련 실패 수정과 필요한 재확인 | I60 | 완료 |
| H-I45 | 계약·증거 추적 완료 | I61 | 완료 |
| H-I46 | 최종 diff·범위·보존 확인 | I62 | 완료 |
| H-I47 | 로컬 커밋·인계 | I63 | 완료 |
| S-I00 | 현재 브랜치·변경·관련 지침 확인 | I00, I02 | 완료 |
| S-I01 | 기존 실패를 최소 fixture로 재현 | I03 | 완료 |
| S-I02 | 오늘 활동 계약에 부모 식별자 추가 | I12 | 완료 |
| S-I03 | 두 입력 생산 경로의 부모 쌍 연결 | I13 | 완료 |
| S-I04 | 최종 provider 입력까지 쌍을 보존 | I14 | 완료 |
| S-I05 | SNS source capture의 ID·본문 연결 수정 | I15 | 완료 |
| S-I06 | 과거 부모 연결 정정 계약·순수 정책 구현 | I17 | 완료 |
| S-I07 | Runtime의 canonical 자식·부모 basis 연결 | I18 | 완료 |
| S-I08 | Memory 정정 근거의 영속화 구현 | I19 | 완료 |
| S-I09 | 다음 정식 migration과 자원 연결 | I20 | 완료 |
| S-I10 | 원본 복원 뒤 정정된 검증 view 구성 | I21 | 완료 |
| S-I11 | 저장 소비자의 같은 트랜잭션에 통합 | I22 | 완료 |
| S-I12 | 저장 후 조회·검색 근거에 동일 proof 적용 | I23 | 완료 |
| S-I13 | 기존 owner 재검사와 revision 연결 | I24 | 완료 |
| S-I14 | 공유·삭제·검색 준비 수명 유지 | I25 | 완료 |
| S-I15 | 필요한 회귀만 실행하고 실패 지점 수정 | I16, I26, I58 | 완료 |
| S-I16 | 격리된 migration·Docker 경로 확인 | I27 | 완료 |
| S-I17 | 기존 36건의 개별 분류와 사본 복구 판독 | I55 | 완료 |
| S-I18 | 관련 계약·검증 문서 갱신 | I56 | 완료 |
| S-I19 | 백엔드 변경 범위 검토·로컬 커밋·결과 보고 | I26, I62–I63 | 완료 |
| S-I20 | 상태 카드의 설정 링크 제거와 화살표 펼침 적용 | I42 | 완료 |
| S-I21 | 관심 주제 설정 카드의 Feed 진단 표시 제거 | I32 | 완료 |
| S-I22 | UI의 한국어·영어·접근성·관련 검증과 문서 반영 | I53–I54, I57, I59 | 완료 |
| S-I23 | 추가 UI 범위 검토·로컬 커밋·통합 결과 보고 | I52, I61–I63 | 완료 |

### 9.2 원본 검증

| 원본 검증 | 통합 검증 | 해당 관련 결과 |
| --- | --- | --- |
| H-V01 | V01 | §8의 해당 PASS/사본 한계 |
| H-V02 | V01, V26 | §8의 해당 PASS/사본 한계 |
| H-V03 | V01, V05, V07, V26 | §8의 해당 PASS/사본 한계 |
| H-V04 | V26 | §8의 해당 PASS/사본 한계 |
| H-V05 | V05–V07, V26 | §8의 해당 PASS/사본 한계 |
| H-V06 | V27–V28 | §8의 해당 PASS/사본 한계 |
| H-V07 | V02, V26 | §8의 해당 PASS/사본 한계 |
| H-V08 | V03 | §8의 해당 PASS/사본 한계 |
| H-V09 | V04 | §8의 해당 PASS/사본 한계 |
| H-V10 | V04, V26 | §8의 해당 PASS/사본 한계 |
| H-V11 | V03–V04, V21, V27 | §8의 해당 PASS/사본 한계 |
| H-V12 | V05–V06 | §8의 해당 PASS/사본 한계 |
| H-V13 | V08–V09 | §8의 해당 PASS/사본 한계 |
| H-V14 | V07–V08 | §8의 해당 PASS/사본 한계 |
| H-V15 | V08–V09 | §8의 해당 PASS/사본 한계 |
| H-V16 | V06, V09, V26 | §8의 해당 PASS/사본 한계 |
| H-V17 | V11 | §8의 해당 PASS/사본 한계 |
| H-V18 | V12 | §8의 해당 PASS/사본 한계 |
| H-V19 | V13 | §8의 해당 PASS/사본 한계 |
| H-V20 | V09, V11, V13 | §8의 해당 PASS/사본 한계 |
| H-V21 | V11–V13, V27 | §8의 해당 PASS/사본 한계 |
| S-V01 | V14 | §8의 해당 PASS/사본 한계 |
| S-V02 | V15 | §8의 해당 PASS/사본 한계 |
| S-V03 | V16, V22 | §8의 해당 PASS/사본 한계 |
| S-V04 | V15–V16 | §8의 해당 PASS/사본 한계 |
| S-V05 | V17 | §8의 해당 PASS/사본 한계 |
| S-V06 | V18 | §8의 해당 PASS/사본 한계 |
| S-V07 | V19 | §8의 해당 PASS/사본 한계 |
| S-V08 | V20 | §8의 해당 PASS/사본 한계 |
| S-V09 | V20, V22 | §8의 해당 PASS/사본 한계 |
| S-V10 | V21 | §8의 해당 PASS/사본 한계 |
| S-V11 | V21–V22 | §8의 해당 PASS/사본 한계 |
| S-V12 | V23 | §8의 해당 PASS/사본 한계 |
| S-V13 | V24 | §8의 해당 PASS/사본 한계 |
| S-V14 | V25, V27–V28 | §8의 해당 PASS/사본 한계 |
| S-V15 | V10 | §8의 해당 PASS/사본 한계 |
| S-V16 | V11 | §8의 해당 PASS/사본 한계 |
| S-V17 | V10, V26–V27 | §8의 해당 PASS/사본 한계 |

### 9.3 H C/A72

| 원본 계약/수용 기준 | 원본 요약 | 통합 단계 | 통합 검증 | 상태 |
| --- | --- | --- | --- | --- |
| H-C01/A01 | 홈 전역 nav 제거 | I35 | V01 | 완료 |
| H-C02/A02 | footer/빈 공간/숨은 링크 없음 | I35–I36 | V01, V26 | 완료 |
| H-C03/A03 | 홈 시작 기능·대체 메뉴 없음 | I35–I36 | V01 | 완료 |
| H-C04/A04 | 아이콘/World 정보·순서 보존 | I36 | V01, V26 | 완료 |
| H-C05/A05 | 설정/World 진입 유지 | I36 | V01, V05, V07, V26 | 완료 |
| H-C06/A06 | 전역 feed/목록 진입만 제거 | I35–I36 | V01, V05, V07, V26 | 완료 |
| H-C07/A07 | World 5탭·scope 보존 | I36 | V01, V05, V07, V26 | 완료 |
| H-C08/A08 | 다른 화면 복귀/탐색 보존 | I36, I49 | V01, V05, V07, V26 | 완료 |
| H-C09/A09 | 직접 URL 홈 fallback | I36, I46, I49 | V01, V05–V07, V26 | 완료 |
| H-C10/A10 | footer 전용 공간과 safe-area | I36 | V01, V26 | 완료 |
| H-C11/A11 | main/단일 scroll | I36 | V01, V26 | 완료 |
| H-C12/A12 | 폭·Phone·기존 icon 문법 | I36, I59 | V01, V26 | 완료 |
| H-C13/A13 | 기존 read/runtime·추가 쓰기 없음 | I35–I36 | V01, V27–V28 | 완료 |
| H-C14/A14 | 접근성·focus·터치 | I36, I59 | V26 | 완료 |
| H-C15/A15 | Next/static 동일 source | I35, I59 | V05–V07, V26 | 완료 |
| H-C16/A16 | ko/en·사용자 원문 보존 | I53 | V26 | 완료 |
| H-C17/A17 | composition slot·중립 shell | I35, I57 | V27–V28 | 완료 |
| H-C18/A18 | 데이터·전역 route/API 보존 | I34, I36 | V01, V05, V07, V26–V28 | 완료 |
| H-C19/A19 | 대화/캐릭터 기준 관계 header | I37 | V02, V26 | 완료 |
| H-C20/A20 | 관계 추가 중심 이름 줄 제거 | I37 | V02, V26 | 완료 |
| H-C21/A21 | 아이콘/글 문법·자연 높이 | I37 | V02, V26 | 완료 |
| H-C22/A22 | graph/중심/본문/World nav 보존 | I37, I59 | V02, V26 | 완료 |
| H-C23/A23 | 지역 JSX/token·ko/en | I37, I53, I57 | V02, V26 | 완료 |
| H-C24/A24 | 활동 방식 제목/설명/적용 엔진 | I38, I53 | V03 | 완료 |
| H-C25/A25 | 캐릭터 범위·저장/CAS·ON 분리 | I38 | V03 | 완료 |
| H-C26/A26 | 실제 engine 출처/저장 범위 | I38, I53 | V03 | 완료 |
| H-C27/A27 | null 상속·명시적 V2 | I38 | V03–V04, V21, V27 | 완료 |
| H-C28/A28 | 지원 선택·새 engine 미추가 | I38 | V03–V04, V21, V27 | 완료 |
| H-C29/A29 | 정상 긴 안내 제거·오류/전환 유지 | I38 | V03 | 완료 |
| H-C30/A30 | 감정/최근 진행 표현 제거·기록 보존 | I38 | V03–V04, V21, V27 | 완료 |
| H-C31/A31 | 감정 직접 표시·이동 버튼 없음 | I39–I41 | V04 | 완료 |
| H-C32/A32 | 상태→감정→메모→시각→이름 순서 | I41 | V04 | 완료 |
| H-C33/A33 | 해당 handle badge만 제거 | I41 | V04 | 완료 |
| H-C34/A34 | 저장 mood/강도/원문·no AI | I39–I41 | V03–V04, V21, V27 | 완료 |
| H-C35/A35 | 비조작 태그·긴 메모 | I41 | V04, V26 | 완료 |
| H-C36/A36 | confirmed_at·known/null/실패 | I39–I41 | V04 | 완료 |
| H-C37/A37 | owner/scope/active/abort·부분 실패 | I40–I41 | V04, V26 | 완료 |
| H-C38/A38 | OFF 감정·실제 최근 활동 보존 | I41 | V04 | 완료 |
| H-C39/A39 | V2/SNS/Chat 기존 정책 보존 | I38–I41 | V03–V04, V21, V27 | 완료 |
| H-C40/A40 | 같은 생성 디자인 6단계 | I45, I47 | V05–V06, V09, V26 | 완료 |
| H-C41/A41 | 등록 문구·실제 OFF | I47 | V05–V06 | 완료 |
| H-C42/A42 | 직접 6단계·receipt/실패 분리 | I47–I48 | V05–V06 | 완료 |
| H-C43/A43 | 세 카드 모두 선택 사항 | I45, I47, I49 | V05–V06, V09, V26 | 완료 |
| H-C44/A44 | 기본 정책/키 없음/image OFF/보존 | I06–I08, I45 | V08–V09 | 완료 |
| H-C45/A45 | activity 카드 ON/OFF와 save 분리 | I10, I43, I45 | V08–V09 | 완료 |
| H-C46/A46 | 저장 사실·유효 기본값 판정 | I09, I44 | V08–V09 | 완료 |
| H-C47/A47 | ON의 동일 backend 기준 | I05, I09–I10 | V07–V09 | 완료 |
| H-C48/A48 | 부족/개시 전 사유·실인증 미표방 | I09, I45, I53 | V07–V09 | 완료 |
| H-C49/A49 | 카드 save만 수행·no AI | I06–I08, I45 | V08–V09 | 완료 |
| H-C50/A50 | 완료/skip·saved/dirty 보존 | I49 | V05–V06 | 완료 |
| H-C51/A51 | 실제 schedule/자동 준비 유지 | I09–I10, I34 | V08–V09, V11, V13 | 완료 |
| H-C52/A52 | 기본 화면에 plan/topics/engine/log 없음 | I45–I46, I50 | V06, V09, V26 | 완료 |
| H-C53/A53 | default inherit·SNS V2 유지 | I47, I51 | V08–V09 | 완료 |
| H-C54/A54 | Studio 명칭/같은 세 설정 | I50 | V06, V09, V26 | 완료 |
| H-C55/A55 | draft 설정/ON 차단·publish 자동ON 없음 | I05, I09–I11, I50 | V07–V08 | 완료 |
| H-C56/A56 | Studio 기본 설정만·단계 표시는 생성만 | I45, I50 | V06, V09, V26 | 완료 |
| H-C57/A57 | 같은 저장소/키/purpose 재사용 | I06–I08, I51 | V08–V09 | 완료 |
| H-C58/A58 | 로컬 사용자 개시 전 기본 설정 관리 | I04–I08 | V07–V08 | 완료 |
| H-C59/A59 | busy/CAS/scope/부분 실패 | I09–I11, I43–I45, I48–I49 | V08–V09 | 완료 |
| H-C60/A60 | 공용 source·locale·소유 경계 | I45–I51, I53–I54, I56–I59 | V06, V08–V09, V26 | 완료 |
| H-C61/A61 | World 카드 전체 제거 | I33 | V11 | 완료 |
| H-C62/A62 | 선택란/actor 카드/Feed 내부 제거 | I33 | V11 | 완료 |
| H-C63/A63 | World 생성/marker/publish 종료 | I28–I29 | V12 | 완료 |
| H-C64/A64 | World 직접 요청 종료·actor API 보존 | I30 | V12 | 완료 |
| H-C65/A65 | 유효 actor 사전·OFF 관심 유지 | I31 | V13 | 완료 |
| H-C66/A66 | actor 자동 준비/개별 관리/Feed 보존 | I32, I34 | V09, V11, V13 | 완료 |
| H-C67/A67 | World 출처와 actor world-scope 구분 | I31, I34 | V13 | 완료 |
| H-C68/A68 | 과거/공유 ID·실제 키·데이터 보존 | I34 | V13 | 완료 |
| H-C69/A69 | ID/매칭/선정·history/epoch 보존 | I31, I34 | V09, V11, V13 | 완료 |
| H-C70/A70 | original World/세 기본 설정 유지 | I34, I50–I51 | V09, V11, V13 | 완료 |
| H-C71/A71 | catalog/관계 초기화·helper 보존 | I28, I34 | V11–V13, V27 | 완료 |
| H-C72/A72 | 전용 effect 정리·공용 소비자/locale·추가 범위 | I32–I33, I53, I56–I57 | V11–V13, V27 | 완료 |

## 10. 로컬 Git·인계와 남은 확인 경계

- `05685aa2582fab3c1121f61c819c79c9515e62c7` — backend, 명시한 47개 변경 파일.
- `14e288fd82e5ea66f4993a43249b7d7830b83adc` — frontend, 명시한 48개 변경 파일.

[backend ARCHITECTURE](../../backend/ARCHITECTURE.md), [frontend ARCHITECTURE](../../frontend/ARCHITECTURE.md), [frontend DESIGN](../../frontend/DESIGN.md)에 실제 책임/표시/검증 한계를 반영했다. 이 검증 기록과 세 문서는 별도 로컬 문서 커밋에 포함한다. 통합 계획은 workspace 문서이므로 제품 저장소로 복사하거나 새 Git 저장소를 만들지 않고 수행 기록만 추가한다.

전체 diff/staged 경계·문서 표/링크·브랜치를 검토했으며 코드 commit 이후 기능 변경은 없다. 이 문서도 로컬 문서 커밋으로 보존하고 실제 최종 commit SHA와 clean 작업 트리는 workspace 계획 수행 기록 및 Git log로 확인한다.

실제 사용은 업데이트된 코드를 기존 방식으로 시작한 다음 원본 기억 화면에서 owner가 선택한 blocked 경험을 개별 또는 전체 재검사하면 된다. 원래 blocked는 자동으로 pending으로 바뀌지 않는다. 통과하지 않는 경험은 계속 blocked로 남고 사용자가 저장 포기할 수 있다. 기존 SNS/Chat 원문은 보존한다. 아직 원본 사용자 데이터에 재검사를 실행하지 않았다.

이번에 미실행한 것은 실제 AI/embedding/ComfyUI 모델 호출·자연 활동 품질, 전체 frontend/backend/CI·production build/export, native/installer/실기기, 원본 DB upgrade/재검사와 서비스 배포다. 이전 windows_installer_hosted_predecessor_missing:v29 확인은 별도 installer/CI 범위로 남기며 이번에 해결됐다고 주장하지 않는다.
