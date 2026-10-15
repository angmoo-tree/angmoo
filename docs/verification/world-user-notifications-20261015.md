# World 내 프로필 알림·홈 배지 구현과 로컬 검증

작성일: 2026-10-15 (Asia/Seoul). 실행 상태는 아래 최종 결과 표를 따른다.

## 실행 범위

- 사용자 계획: `10-15 World 피드 알림 진입·미읽음 배지와 기존 알림 화면 재사용 코드 구현 세부 계획`, I00–I55.
- 최신 사용자 지시: **로컬 구현·관련 검증·Signed-off-by 로컬 커밋까지**. 원격 publish, PR, GitHub CI, main 병합과 R00–R08은 수행하지 않는다.
- 저장소: `angmoo-tree-angmoo`, 브랜치 `feat/world-user-notifications`.
- 기준 main/원격 main: `3e5d268d085627f691ee814616f6a1c757dd2c62`.
- 기준 tree: `02718c592734ad8b6a3bd9d308480e89ab9e6751`. 시작 작업 트리는 깨끗했다.
- workspace AGENTS, backend/frontend ARCHITECTURE, frontend DESIGN/AGENTS, CONTRIBUTING/CODEOWNERS와 현재 CI·보존·shell 지침을 적용했다.
- 실제 설치 앱, 사용자 DB/미디어/credential, Docker 컨테이너·볼륨·관찰 실행은 열거나 변경하지 않았다. 실제 모델·유료 AI·생성 요청을 호출하지 않았다.

## 실제 저장·조회 경로

| 종류/진입점 | 같은 UoW 안의 연결 | delivery identity |
| --- | --- | --- |
| 사용자/검증된 자율 post·reply | SocialSourceWriteService → timeline → scoped delivery → RuntimeSourceWriteReferences의 성공 원본 event 연결 | immutable source Post ID |
| quote | 기존 timeline source → 정확한 대상 작성자 → 성공 action event 연결 | source quote Post ID |
| mention | 기존 mention parser와 해당 World effective handle → batch author profile → scoped delivery | source Post ID + 수신 WorldCharacter |
| 수동 좋아요 전환 | OwnerReactionService → audit-only reaction event → RuntimeSourceWriteReferences | 성공 SocialEvent ID |
| Feed like/repost/follow | 기존 timeline/reaction → apply_successful_world_feed_action → 정확한 source/event → scoped delivery | 성공 SocialEvent ID |
| LangGraph public action | 기존 source/event → action_type을 명시한 link → source post의 mention도 같은 event에 연결 | Post ID 또는 성공 SocialEvent ID |

일반 게시글에서 답글로, 답글에서 다시 답글로 반응할 때 직접 대상 작성자가 수신자다.
원글 작성자나 같은 소유자의 자율 캐릭터를 현재 사용자의 프로필로 추정하지 않는다.
원본/알림/성공 event는 호출자의 같은 Session·transaction을 사용하며 helper 내부 commit은 없다.
SQLite ON CONFLICT는 중복을 기존 행으로 수렴시키고 최초 read_at/handled_at을 초기화하지 않는다.
World 리포스트는 성공 이벤트에서 한 번만 생성해 timeline 단계와의 이중 생성을 막는다.
기존 전역 writer/API의 unscoped 호환 행은 보존하지만 World 알림에 추정 편입하지 않는다.

## API·권한·데이터 계약

| API | 계약 |
| --- | --- |
| GET `/api/v1/worlds/{worldId}/notifications` | 기본 20/최대 100, ID keyset, World/현재 프로필에 묶인 cursor, read 여부와 무관하게 보존된 적격 목록 |
| GET `.../notifications/unread-count` | 같은 적격 predicate로 계산한 정확한 전체 unread 수 |
| PATCH `.../notifications/{id}/read` | 현재 수신 범위·원본 접근 재확인, 최초 read_at과 canonical count, handled 상태는 변경하지 않음 |
| GET `/api/v1/notifications/world-unread-counts?world_ids=...` | 표시 World 최대 50개, 중복 제거, 같은 Session의 batch read, 개별 available/unavailable, 미확인 수는 null |

현재 수신자는 claimed local owner의 해당 World 활성 owner-controlled 프로필이다.
World 소유·active owner membership·캐릭터/설정·삭제 접수 상태를 검증한다. GET에 ensure/생성/commit은 없다.
RuntimeWorldNotificationReferences가 제한된 다중 도메인 read를 제공하며 Social repository는 Social ORM만 사용한다.
full/public 공식 app에서 같은 factory를 조립한다. 인증/기존 local frontend Origin 검사와 SQLite immediate/retry 경계를 유지한다.
잘못된 scope/알림 ID는 거절하고, 설정되지 않은 프로필/잘못된 cursor/DB busy를 성공한 빈 목록으로 표현하지 않는다.
post/profile ID와 can_open만 반환하고 임의 href는 제공하지 않는다. 실제 목적지의 기존 읽기 권한도 계속 검사한다.

목록/count/read/batch는 공통 eligibility를 사용한다. 삭제·숨김·비공개·차단된 원본/부모, 취소된 반응은 제외한다.
like/repost/follow 취소 후 새 성공은 새 event key를 가지며, 과거 행은 저장소에 남겨도 현재 반응의 알림만 적격이다.
follow 목적지에 필요한 프로필은 bounded read로 검증한다. 삭제한 행위자가 표시되는 게시글은 기존 placeholder 정책을 따른다.
UTC response model을 재사용해 SQLite의 naive UTC가 API에서 명시적인 UTC instant로 반환된다.

SQLite **v38**, Alembic **20261015_0115**는 nullable delivery_key, unique key index와
`(world_id, recipient_world_character_id, id)` index를 추가한다. 기존 행·읽음·활동 처리 기록은 바꾸지 않는다.
v38 schema digest: `32301150b6b7ad37111fc9b7a9b325d90172a34ce53e32778e4a42d476d71fd7`.
v1–v37 manifest와 과거 migration은 변경하지 않았다. v37 metadata builder를 보존하고,
fence 설치는 현재 ORM 열을 과거 DB에 적용하지 않도록 해당 실제 세대 metadata를 사용한다.
v38은 Notification의 두 write fence만 transaction 안에서 재설치한다. 삭제 접수 뒤 늦은 알림 쓰기도 계속 차단한다.
Windows의 synthetic predecessor builder/matrix는 v37까지 확장한다. 실제 설치 EXE 실행과 hosted Windows CI를 수행한 것은 아니다.

## 화면·수명·재사용

- 기존 알림 avatar/type/time/preview/개별 check를 NotificationList로 추출하고 전역/World controller가 함께 사용한다. 전역 API와 기존 scroll pagination을 유지한다.
- 피드 header의 실제 중앙 로고, 오른쪽 bell → 내 프로필, 44px control과 기존 World 5탭을 유지한다.
- `/worlds/{id}/notifications`는 feed 보조 화면이다. Next wrapper/static router/공통 validator/Phone native allowlist가 같은 화면을 연결한다. 전역 `/notifications`를 static 지원으로 확대하지 않는다.
- 홈 World 아이콘과 Creator Studio의 일반 열기만 worldFeedRoute를 사용한다. neutral worldAppRoute, 명시적 World 소개·게시글·답글·프로필·채팅·관계 경로는 유지한다.
- DeviceHome은 표시 ID callback과 badge/설명 slot만 소유한다. composition이 Social hook을 연결한다. AppIcon 외부 배지와 내부 rounded image clipping/초록 launchability를 분리했다.
- 수는 서버가 계산한다. UI는 0 숨김, 1–99, 100 이상 99+로 표현하고 KO/EN 접근성 이름에 실제 수를 포함한다. 오류/미확인/unavailable/stale를 0으로 만들지 않는다. 401/403/404/409 또는 DTO/scope 불일치는 이전 목록·숫자를 제거한다. 일시적인 통신/503 실패만 이전 수를 stale로 유지하며, 권한/범위 거절보다 오래된 읽음 응답도 mutation epoch로 숫자를 복원할 수 없게 한다.
- 홈 한 batch, 피드/목록 공유 controller는 visible 상태에서 **60_000ms**마다 갱신한다. entry/focus/visibility/manual/read 완료 때 재확인하고 hidden/다른 화면에서는 멈춘다. focus+visibility의 같은 복귀 이벤트는 250ms 동안 합친다.
- 홈은 focus refresh 중 기존 표시 World 집합을 유지해 []→같은 목록 재조립으로 batch가 두 번 실행되지 않게 한다. auth/runtime identity가 바뀌면 component/request scope를 초기화한다.
- 읽음은 명시적인 check 또는 leave/native 검증을 통과한 원본 링크 동작에 연결한다. 읽음 응답을 기다리지 않고 이동한다. 보기 수명과 read command 수명을 구분하고 응답 유실/실패는 재조회·재시도로 확인한다.
- static 문서 전환에서는 transient session journal에 user/session/scope와 미확정 ID만 남긴다. 본문/토큰/키를 저장하지 않으며 임의 count 차감이나 성공 추정에 사용하지 않는다.
- 기존 미저장 글·사진 leave guard와 modifier 기본 동작을 보존한다. 새 처리 문구는 KO/EN 함께 추가했다. 새 라이브러리/폰트/이미지 자산이나 raw-color 예외는 없다.

## 관련 로컬 검증

선택한 관련 백엔드 시험의 고유 node **162개 PASS**를 XML로 중복 제거해 집계했다. 전체 backend corpus를 수행한 결과가 아니다. 중간 실패는 수정 전 진단 자료이며 통과 증거로 세지 않는다.

| 검증 | 최종 결과/근거 |
| --- | --- |
| Social actual source·scope·원자성·HTTP·2 World·프로필 전환 | 최종 delivery 묶음 20 PASS, 추가 실제 SQLite lock/삭제 fence/가시성 3 PASS; 중복 node 합산하지 않음 |
| populated migration/삭제/Inbox/공식 app/기존 active contract | 관련 묶음 58 PASS, 현재 계약 41 PASS, full/public app·World 알림 삭제/원본 보존 3 PASS |
| predecessor fixture 및 격리 staged upgrade | 46 PASS: v1–v37 source fixture, 관련 격리 upgrade/보존; 실제 NSIS EXE 실행은 미실행 |
| Next/static notification browser | Next 31 PASS / static 30 PASS + 전역 /notifications 비지원 계약 1 SKIP (권한·범위 거절 및 늦은 읽음 4개 포함) |
| 실제 API/SQLite browser | Next/static 각 1 PASS, auth/environment만 synthetic, scoped API JSON은 실제 HTTP 응답 |
| 기존 Feed header/profile/상세/leave guard 회귀 | 변경 범위에 해당하는 기존 시험 Next 9 PASS / static 9 PASS |
| Rust product_windows | 11 PASS, cargo test --locked --offline product_windows::tests --lib |
| backend/frontend architecture·design·migration/matrix contract | 모두 PASS. baseline SHA 대비 이전 manifest 불변, supported v1–v37 matrix, raw color 1157→1129/35→34 files, 기존 canonical PNG·threshold 보존 |
| frontend lint/type/catalog·Next/static production build | 모두 PASS. catalog 16 namespaces/2603 source keys, key·params·plural parity; 동일 최종 source의 두 production build |

격리 SQLite에서 5 World와 50 World batch는 모두 **4 SQL**이다.
EXPLAIN QUERY PLAN에서 새 복합 index 사용을 확인했다. 사용자 수·실제 DB 크기에 대한 성능 benchmark로 확대 해석하지 않는다.
넓이 320/360/390/436/1280px, KO/EN의 로고 중앙·44px·badge contrast >=4.5:1·keyboard·가로 overflow를 검증했다.
대표 KO 320/EN 390 화면 PNG도 시각 확인했다. 자동 화면 시험은 native USER CHECK나 자연 활동 품질 검증을 대체하지 않는다.

재현 명령은 저장소 root 기준이며 기존 `.venv`와 pnpm 환경을 사용한다:

```powershell
backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_design_contract.py --check
$env:BASE_SHA='3e5d268d085627f691ee814616f6a1c757dd2c62'
backend/.venv/Scripts/python.exe scripts/ci/check_embedded_data_migration_contract.py
backend/.venv/Scripts/python.exe scripts/ci/check_windows_installer_supported_upgrade_matrix.py
```

backend 폴더에서 `tests/social/test_world_user_notifications.py`, 관련 source-write/Feed/Inbox,
`tests/migrations/test_world_notifications_v38.py`, Alembic·model registration·outbox,
World deletion/worker/HTTP, 현재 Studio contract, 지원 predecessor fixture/coverage의 관련 node를 실행한다.
frontend에서 `pnpm run lint`, `pnpm run typecheck`, `pnpm run test:ui-catalog`,
`pnpm run build`, 그 완료 후 `pnpm run build:static`을 실행한다.
browser-tests에서 `playwright.world-notifications{,-static,-backend}.config.ts`와 선택한 기존
`playwright.world-feed-ui{,-static}.config.ts`를 `pnpm exec playwright test -c ...`로 순서대로 실행한다.
frontend production/static build와 해당 server를 동시에 재생성하지 않는다.

명령별 XML/JSON, batch query plan, synthetic HTTP audit, screenshot은 Git에서 제외되는
`artifacts/world-user-notifications-20261015/`에 있다. 기존 피드 회귀 출력은 기존 fixture 전용 artifacts 아래에 있다.
추적 문서는 깨끗한 checkout에서도 코드/시험/명령을 확인할 수 있고 로컬 산출물의 존재만으로 PASS를 주장하지 않는다.

## I00–I55 단계 대응과 원격 인계

| 단계 | 구현/검증의 실제 소유 |
| --- | --- |
| I00–I07 | baseline.json, 깨끗한 기준 branch/tree, 지침·writer/route 지도, 이 문서의 범위별 검증 |
| I08–I15 | Social DTO/model/delivery, v38/0115, source/reaction/mention의 정확한 연결과 legacy 보존 |
| I16–I23 | runtime recipient read adapter, 공유 eligibility, keyset/canonical count/최초 read, 정식 router/full/public 및 실제 SQLite/HTTP |
| I24–I31 | shared NotificationList, Social API/controller, visible polling, bell/header/list, 읽음과 독립된 원본 이동 |
| I32–I39 | World 보조 화면, Next/static/native route, leave guard, KO/EN 및 layout/keyboard 회귀 |
| I40–I47 | bounded home batch/SQL plan, composition slots/AppIcon, 수명·feed 기본 열기, 실제 API 연결 |
| I48–I51 | populated migration/삭제·원본 보존, 구조·번역·빌드, 2 World/다른 사용자 격리 종단 확인 |
| I52–I55 | diff·범위 감사, 문서·로컬 signed commit, 다음 remote 단계 준비만 수행 |

중간에 발견한 이슈는 원인을 분리해 수정했다: v37 frozen schema의 fence/새 열 참조와 v38 fresh/upgrade 열 순서, 리포스트 이중 생성, 홈 focus refresh 중 빈 목록에 의한 중복 batch, 제목·본문 결합/정적 trailing slash/종 버튼 추가에 맞지 않았던 시험 선택자, 실제 HTTP fixture의 Origin/Host 일치 조건, 현재 target version을 기대하도록 남아 있던 시험 상수, 권한/scope 거절 시 이전 미리보기가 남던 분기다. 마지막 항목은 명시적 권한 거절과 일시 장애를 분리하고 늦은 읽음 응답도 차단하는 회귀를 추가했다. 과거 manifest나 검사를 숨기는 방식은 사용하지 않았다.

최신 요청에 따라 **R00–R08은 미실행**이다. PR/CI/main/배포/실제 설치 앱 적용 완료로 표시하지 않는다.
나중에 사용자가 원격 진행을 요청하면 최신 main과 branch diff, CODEOWNERS, native 플랫폼 검토 적용 여부를
다시 확인해야 한다. 이번 변경에는 DB migration/runtime/native source가 포함돼 현재 보수적 CI 분류가
전체 검증으로 확대할 수 있다. 로컬 선택 회귀가 향후 CI 전체 통과를 보장한다는 뜻은 아니다.
Hosted Windows build/실제 EXE 실행/사용자 native 조작/실제 자연 SNS·유료 AI는 별도 미실행 상태다.
중간 자동화 시험의 실패 원인과 수정 결과는 최종 결과 표와 해당 산출물로 구분한다.
