# 반응형 공통 화면·일반 Tauri 창·내부 탐색 막대 구현 검증

- 작업: 2026-10-04, Asia/Seoul. 원 계획은 workspace `docs/plan/10-04 Angmoo 반응형 공통 화면·Tauri 일반 창과 내부 탐색 막대 코드 구현 세부 계획.md`, P00–P20이다.
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `feat/0.1.0-release-readiness`. 시작 HEAD `314c594167b9efe4ca07cdc67d3252e88a972878`, 시작 작업 폴더 clean.
- 로컬 source 커밋: `41f05932cb65e1cf8cb39bc72426504cfb1bc592` — `feat: adopt responsive product screens and native desktop navigation` (sign-off). 최종 증거는 source 뒤의 별도 로컬 metadata/결과 문서 커밋으로 고정한다.
- inventory 검증 보완 커밋: `3c56b162aaa5356242f95160edb26ad68936d4b4` — `fix: validate retired chrome consistently in preservation inventory` (sign-off). 원본 inventory와 제품 구현은 유지하고 검증 소비자·회귀 검사·증거를 보완했다.
- 상태: 제품 구현, 로컬 기술·browser·공식 보존 검증과 결과 문서화 완료. 실제 OS 창 조작은 실행 차단으로 **NOT_RUN**, 사용자 Docker·설치판 적용과 직접 USER CHECK도 **NOT_RUN**이다.

## 1. 변경 결과와 소유권

Next root와 static root에 같은 `ProductViewport`를 연결했다. 이 composition이 `100dvh`와 native toolbar의 높이를 배분하고, 일반 DeviceFrame은 남은 높이와 최대 960 CSSpx, Memory·Studio·Graph는 최대 1440 CSSpx를 사용한다. 상한 이전에는 client 폭을 채우고 상한 이후 수평 중앙에 놓는다. 436px/880px 상한, 검은 bezel, device radius/shadow, transparent Phone 표현과 custom caption을 제거했다. 입력 border/focus, content scroll owner, safe area, header/footer, 기존 UI primitive는 유지했다.

Rust의 실제 창 builder는 표준 OS decorations, 불투명 배경, resize/maximize를 사용한다. main 초기 client 목표는 480×850 logical px, 기본 최소 client는 480×480이다. monitor work area, scale, 실제 outer-inner inset에 따라 초기/최소 크기와 위치를 보정한다. 가로·세로를 독립 조절하며 aspect ratio나 최대 크기 제한을 두지 않는다. Memory 1180×780, Studio 1280×820, Graph 1180×780의 기존 초기 목표를 유지한다. `phone` logical kind/`main` label도 유지한다. Phone 전용 subclass/DWM/수동 drag·resize 모듈과 renderer command/listener/cursor를 제거했다.

native에만 네 버튼과 내부 경로 입력을 표시한다. 실제 URL, Next/static router, 창별 실제 history entry의 index/session 및 session tail을 구독한다. 별도 route 배열은 없다. Next의 history 연결 이후 metadata를 붙이고, rejected push는 forward tail을 바꾸지 않는다. metadata 손상/누락 또는 session storage 불가이면 증명할 수 없는 back/forward를 비활성화한다. 저장된 bootstrap은 최초 index 진입에서 소비하며 실제 깊은 URL이 초기 script보다 우선한다.

같은 kind는 기존 실제 router/history로 이동하고, 다른 kind는 검증을 포함하는 `open_product_window`의 singleton을 사용한다. cross-window 성공·실패 모두 source URL/history를 바꾸지 않는다. `StaticNavigationBridge`의 browser fallback은 native 링크를 처리하지 않는다. screen-owned query 오류·provider normalization UI는 정적 resolver에서 유지하고, native 주소 입력/dispatch에는 더 엄격한 query 계약을 적용한다. shared route grammar는 하나이다.

외부 document navigation과 new window를 Rust에서 차단한다. 사용자 HTTP(S) anchor는 credentials 없는 URL만 좁은 host command로 기본 브라우저에 전달한다. 원격/JS shell 권한을 추가하지 않았다. ko/en 이름, 44px target, IME/Esc/Ctrl+L/Alt 탐색/F5·Ctrl+R, visible modal/textarea focus 보호와 address draft/actual route 분리를 구현했다. unsaved/in-progress 확인은 WorldCreator, 카드/캐릭터 생성, SNS composer, Chat, 이미지 설정의 실제 owner에 연결했다. durable 저장 뒤 정상 이동은 owner guard를 해제한다.

backend 업무 코드·API·ORM·migration·키·Provider·SNS 호출 구조·인증·memory/scheduler/shutdown 의미를 바꾸지 않았다. frontend/ARCHITECTURE, DESIGN, backend/ARCHITECTURE와 설치된 Next 문서를 준수했다. 새 dependency, lockfile 변경, remote font/asset, 공통 계층의 feature import, 별도 native용 화면은 없다. 출처는 **LOCAL** 사용자 확정 계약이다.

## 2. 기존 탐색 조작 분류

| 조작과 소유자 | 실제 처리 |
| --- | --- |
| Memory workspace/Creator Studio의 독립 `/` home | `toolbarEquivalent="home"`와 실제 composition capability로 native에서 통합. browser에는 기존 링크 유지 |
| WorldCharacterProfile의 일반 이전 화면 버튼 | 실제 native back 기록이 있으면 toolbar와 통합. 기록 없는 직접 진입에서는 World 캐릭터 목록 fallback 유지. feature에는 optional callback만 전달 |
| World Home·feed·캐릭터 목록·Chat 목록 복귀 | 특정 목적지/scope이므로 유지 |
| 하단 Home/Feed/My Parrots/Settings 4항목 | 별도 UI 작업 범위이므로 유지 |
| 작성 취소·편집 종료·Dialog 닫기·업로드 제거 | 작업 수명과 draft가 있으므로 유지 |
| 데이터 재조회·재시도·인식 복구 | document reload와 다른 동작이므로 유지 |
| native caption의 최소화/닫기/크기 조절 | 일반 OS caption에 위임. 기존 main shutdown과 child window 수명 owner 유지 |

## 3. 검사 환경과 증거 범위

로컬 evidence root는 `D:/project_code/angmoo-workspace/angmoo-tree-angmoo/artifacts/responsive-shell-20261004/`이며 Git ignore 상태로 보존한다. 이 디렉터리의 링크·trace·JSON은 로컬 실행 자료다. 다른 clone에는 이 요약과 committed source/evidence가 제공되며 실제 artifact 파일은 포함되지 않는다.

- task-owned Next production 3300, static 3301/3200, synthetic API 3302를 사용했다. 이미지 회귀는 별도 fixture 포트 3351/3352를 사용한다. 서버 재사용을 테스트 통과 수단으로 쓰지 않았다.
- 합성 World/캐릭터/게시글/Chat/Memory/미디어와 fake native command ledger를 사용했다. opt-in 실제 AI 검사는 실행하지 않았다. 실제 Provider·유료 API 호출 **0**, 사용자 DB·키 접근/복사 **0**이다.
- 시작 `docker ps`에는 실행 중인 사용자 컨테이너가 없었다. 사용자 Docker up/build/restart/watch 변경과 named volume 조작은 하지 않았다.
- canonical 시각 비교는 고정 `mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`에서 task-owned compiled Next/static snapshot만 mount하고 `--network none --rm`으로 실행한다. 이는 local browser fixture이며 Hosted CI나 운영 Docker 적용이 아니다.
- native 준비는 contributor compile profile, bundle/externalBin 없음, fixture origin 3300 및 snapshot-local `.angmoo-dev`를 사용했다. Rust source/lock/config 22개를 해시 manifest로 대조하고 빌드했다. 실제 debug exe 시작은 자동 승인 검토가 `blocked by policy`로 거절했다. 상세 이유가 반환되지 않았고 native process를 시작하지 않았다. 다른 shell/launcher로 우회하지 않았다.
- installed Angmoo를 진단하지 않았으므로 identity helper/설치판/설치 데이터 사용도 없다. 설치판 조작을 이어갈 때에는 workspace AGENTS의 물리 identity check가 선행되어야 한다.

P02의 before는 시작 HEAD의 source/Git blobs와 기존 canonical PNG 17개 파일을 보존한 역사 기준이다. 이번 실행에서 수정 전 앱을 새로 띄워 촬영한 before screenshot은 아니다. 신규 screenshot·geometry는 구현 이후 격리 실행 결과다.

## 4. 실제 검사 기록

| 검사 | 실행 경로/명령 | 상태 |
| --- | --- | --- |
| frontend lint | `pnpm --dir frontend lint`, 마지막 owner 변경은 해당 파일 eslint 추가 확인 | PASS |
| frontend types | `pnpm --dir frontend typecheck` 및 두 build의 TypeScript | PASS |
| UI locale catalog | `pnpm --dir frontend test:ui-catalog` | PASS, 16 namespaces/2448 source keys |
| 사용자 환경 | `pnpm --dir frontend test:user-environment` | PASS, i18next/SSR/escaping/detector/UTC/HTTP 오류와 12 late session transitions |
| frontend 구조 | `check_frontend_architecture_boundaries.py` | PASS, features 14/legacy edges 0 |
| backend 구조·inventory | `check_architecture_boundaries.py`, `generate_architecture_inventory.py --check` | PASS, 1364 modules/5537 internal edges/4019 external imports, inventory 변경 없음 |
| design | `check_frontend_design_contract.py --write`, 별도 `--check` | PASS, raw colors 1230/36 files, 18 surfaces/0 route gaps, screenshot callsites 21 |
| Next production build | `pnpm --dir frontend build` | PASS |
| static build | `pnpm --dir frontend build:static` | PASS |
| 보호된 backend shell/security/package 계약 | 계획 §14.3의 8개 pytest 파일, backend cwd | **77 PASS** |
| Rust default/contributor | `cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml --lib`, 동일 `--features contributor-docker-bridge` | 각각 **30 PASS** |
| 격리 contributor debug build | snapshot Rust manifest + task-owned Tauri config, `cargo build --locked --features contributor-docker-bridge` | PASS, 실제 OS 실행과 구분 |
| 신규 Next 반응형·탐색 | `playwright.responsive-shell.config.ts` | **42 PASS** |
| 신규 static 반응형·탐색 | `playwright.responsive-shell-static.config.ts` | **42 PASS** |
| 기존 Next product shell | `playwright.shell-regressions.config.ts`, production metadata | **30 PASS/10 SKIP**, 기존 실제 AI opt-in 10개 미실행 |
| 기존 static product shell | `playwright.static.config.ts` | **74 PASS** |
| 기존 Memory/Chat/수명 | `playwright.refactor-lifecycle.config.ts` | **2 PASS** |
| 기존 이미지 입력/표시/설정 | `playwright.image-integration.config.ts` | **40 PASS**, Next/static 각 20개 |
| canonical product/semantic visual | pinned Linux의 원래 36개 node/원래 screenshot 허용 오차 | **36 PASS** |
| 정확한 퇴역·evidence 도구 회귀 | 관련 pytest + 신규 style/native retirement 검사 | **172 PASS**, inventory 보호 7개 추가 |
| frontend 공식 보존 | source 커밋의 exact 변화·퇴역 증거, `check_refactor_frontend_preservation.py` | **PASS, 324 원본 파일** |
| backend 공식 보존 | source/보완 커밋의 exact additions append 후 공식 `check_refactor_preservation.main --contracts --nodes` | **PASS, 보호/현재 node 5107/5107, 37 items** |

검사 준비·중간 실패도 삭제하지 않는다. backend cwd가 잘못된 첫 collection, dev/production metadata 차이, 기존 scrollbar 규칙 누락, old Phone drag/resize assertion, stale init route fixture, strict renderer query, native/browser 두 링크 owner 충돌, Next async route commit 전에 연속 Enter한 검사, image decode 전에 readiness를 확인한 검사를 각각 수정/재실행했다. scrollbar와 native 링크 충돌은 제품 owner에서 수정했다. 유효한 이미지 predicate는 `expect.poll`로 실제 decode를 기다리며 약화하지 않았다. 실제 route commit을 확인한 뒤 다음 조작을 수행한다. source build와 test server가 같은 mutable 산출물을 사용한 준비 중 실행은 최종 증거로 쓰지 않는다.

기존 lifecycle/image fixture에는 언어 설정이 없어 영어 화면에서 한글 조작을 찾는 실패가 있었다. 합성 인증/사용자 환경에 `ui_language="ko"`, `ui_preference_revision=1`, `Asia/Seoul`을 명시하고 외부 요청을 차단했다. 이미지 설정의 네 종류 기대값은 다국어 텍스트 노드 사이의 공백을 가정했던 것이므로, 같은 상태·참조 출처·사용량과 상한을 검사하는 role/정규식으로 수정했다. 기능 기대값을 제거하지 않았다. 중간 image **32 PASS/8 FAIL**과 최종 **40 PASS** JSON을 각각 보존한다.

최종 browser 합계는 **266 PASS/10 SKIP**이다. 이 합계에 Rust·backend pytest·기술 검사·native OS·운영 적용·실제 AI 품질 판정을 섞지 않는다.

첫 공식 backend 실행은 inventory의 K12/K13/K23에 기록된 두 장식 파일의 삭제를 인정하지 않아 **FAIL**이었다. 같은 실행에서 보호/현재 node는 **5100/5100**, API/ORM 차이와 다른 오류는 없었다. 이 실패는 `backend-preservation-inventory-failure.log`에 보존한다. `check_sources`와 inventory가 같은 검증된 retirement 집합을 사용하도록 하고, inventory는 change proof를 검증한 뒤 항상 검사한다. 원본 inventory를 수정하거나 항목을 지우지 않았다. 추가 7개 회귀는 정상 proof 외의 미승인 삭제·무관한 누락·경로 탈출·기능/소유자/baseline 누락을 거절한다. 제품 source와 266개 browser 결과는 그대로이며 전체 보존 검사를 재실행했다.

최종 실행은 `backend-preservation-final.log`에 **exit 0**, PR258 frozen **1867**, PR263 frozen **1907**, 보호/현재 계보 **5107/5107**, **37 items PASS**로 기록됐다. 로컬 `finish-inventory-preservation.py`에서 공식 `capture_refactor_backend_checkpoint.main --append`와 `check_refactor_preservation.main --contracts --nodes`를 모두 실행했다. 하나의 Python 프로세스에서 기존 immutable Git-object read cache를 공유했으며 validator 교체·검사 생략·결과 주입은 없다. mutable 입력은 공식 코드가 다시 읽고 source/assertion/suppression/API/ORM/node 검사를 모두 수행했다.

## 5. 시각·frozen 보존 계약

`device-home-centered-1440x1000.png` 하나만 의도한 새 geometry로 변경했다. 1440 client에서 960 본문 중앙 정렬과 device 장식 제거를 확인했고 Next/static 실제 이미지가 일치했다. 기존/새 PNG를 직접 열어 검토했다. 다른 canonical PNG와 screenshot 허용 오차는 유지한다. 전체 snapshot 자동 갱신을 하지 않았다.

- 이전 SHA256: `320e85cae48798674f9ac7e44876ece22894f4ccfd6b0ca0db87ba6b5a4e3210`.
- 새 SHA256: `038e93bab2e4da599e97c510baf8572f36146d7b4d930a11400645b1f9e638e3`.
- tool의 신규 screenshot callsite 3개는 geometry/native-renderer 진단이며 canonical oracle 수 확대/허용 오차 확대가 아니다.

frozen checkpoint/path map/node/API/ORM/migration 원본을 재생성하지 않는다. source commit의 parent/after Git blobs, Python definition AST와 assertion fragments, 바뀐 browser oracle의 exact text hashes, 위 PNG의 raw hashes를 post-refactor manifest에 append한다. 새로운 tracked source/test node는 공식 `capture_refactor_backend_checkpoint.py --append <source commit>`으로 introduction evidence를 추가한다. append는 원본 checkpoint를 바꾸지 않으며 committed snapshot의 collection/API/ORM을 읽는다.

구 caption CSS와 `phone_resize.rs`는 빈 파일/죽은 소스/임의 destination map으로 보존하지 않고 정식 삭제한다. 승인 증거는 exact committed preimage/삭제/current absence/남은 consumer와 대체 owner를 검증해야 한다. CSS는 활성 import가 없어야 하며 native 퇴역 허용 경로는 옛 `phone_resize.rs` 하나뿐이다. `lib.rs`, 일반 window policy, 기존 behavior test의 committed blobs가 필요하다. 다른 stock의 누락, 재등장, 틀린 preimage, 여전한 consumer는 회귀 검사로 거절한다. 공식 checker의 보호 기준을 무조건 완화하는 예외는 없다.

실제 source 커밋의 exact record는 source blob **69개**, 바뀐 Python definition **8개**, assertion **4개**, frontend/browser text **38개**, PNG **1개**, 퇴역 **2개**다. 첫 공식 append는 새 tracked 파일 **16개**와 backend test node **15개**의 introduction을 기록했다. inventory 보완 커밋의 두 번째 record는 source blob **5개**, 바뀐 Python definition **3개**, 기존 assertion 변경 **0개**다. 두 번째 공식 append는 새 파일 **0개**와 회귀 node **7개**를 기록했다.

기존 post-refactor record **142개 → 144개**, additions **337개 → 339개**이며 두 원본 record prefix가 그대로임을 확인했다. source baseline·backend checkpoint·frontend checkpoint·path map·feature inventory **다섯 frozen 파일**의 Git bytes는 시작 HEAD와 동일하고, 실제 working 파일도 줄바꿈을 정규화하면 같은 내용이다. 재생성하지 않았다. `final-summary.json`은 이 보존 조건, 최종 browser/XML 결과와 실제 공식 backend exit 0을 다시 검증한 요약이다.

## 6. P00–P20 실행 대응

| 단계 | 결과/증거 |
| --- | --- |
| P00 | branch/HEAD/clean·AGENTS/ARCHITECTURE/DESIGN/Next SDK·실제 source/test 소유와 운영 영향 확인 |
| P01 | C01–C22, 확정 geometry, 별도 하단 메뉴/SNS 작업 범위와 canonical LOCAL 문서 동기화 |
| P02 | synthetic fixture/분리 포트/원본 source·PNG before manifest. 수정 전 새 live capture는 미수행으로 구분 |
| P03 | 공통 ProductViewport와 두 root 연결 |
| P04 | DeviceFrame/shell의 장식·고정 높이 제거, scroll/header/footer 유지 |
| P05 | Memory/Studio/Graph 1440 cap와 remaining height, 일반 screen flex chain |
| P06 | ordinary builder·480×850 initial/480×480 min·monitor/DPI/outer-inset 계산 |
| P07 | native subclass/DWM/pointer hooks/cursor/custom caption 제거, 종료/package 기능 유지 |
| P08 | typed route grammar/native validation/document·popup boundary/narrow external opener |
| P09 | actual history indices/tail/session, fail-closed availability와 Next/static/link owner |
| P10 | deep route reload·bootstrap 소비·runtime/auth/언어 복원·owner guard |
| P11 | native-only toolbar·ko/en·44px·IME/modal/textarea/key/draft/busy 오류 |
| P12 | 명시적 Home/back capability와 직접 진입 fallback, 목적지/메뉴/취소/재조회 유지 |
| P13 | 정적/타입/catalog/environment/backend/Rust/퇴역 증거 회귀 |
| P14 | Next/static build, 새 spec/config collection와 실제 실행 |
| P15 | Next/static geometry/history/routes/scope/media/visual 격리 검사, final 결과로 판정 |
| P16 | contributor source 격리·빌드 PASS. **실제 창 시작이 승인 검토로 차단되어 OS/WebView 조작 NOT_RUN** |
| P17 | source/보완 로컬 commit·exact 변화/addition append 완료, frontend 공식 324 files PASS·backend 공식 5107/5107 nodes 및 37 items PASS |
| P18 | **운영 Docker·설치판 적용/USER CHECK NOT_RUN**, 별도 요청 후 수행하도록 후속 기록 |
| P19 | 이 결과 문서·canonical 계약·source/보완/evidence 로컬 commit으로 정리. artifact ignore/보존 |
| P20 | 최종 branch/status/SHA·C/T/V 대응·frozen 5개/두 record prefix·task-owned 환경 종료·미측정 후속 gate 확인 |

## 7. C01–C22와 T01–T35 / 원 제안 V01–V20 대응

| 계약 | 구현/검증 범위 |
| --- | --- |
| C01/C02 | current branch only, common feature/composition, backend 업무 변경 0; 구조/소유 검사 |
| C03/C04/C05 | 960/1440 semantic caps/remaining height/scroll, Next/static geometry·workspace·기존 Feed/Chat 검사 |
| C06/C07/C08/C09 | 장식 퇴역·ordinary OS builder·순수 geometry/Rust compile·unit. 실제 OS resize/Snap/DPI는 NOT_RUN |
| C10 | logical label/kind/singleton 및 runtime/security/package unit/기존 shell 검사 |
| C11/C12/C13 | native-only toolbar/actual vs draft/typed route·encoded ID/query/alias/privacy 입력 검사 |
| C14/C15/C16 | 실제 history/cross-kind ledger/deep reload/runtime-auth 복원 및 미지원 metadata 대응 |
| C17/C18 | ko/en/200%/keyboard/IME/modal·외부 입력 단위/JS/native 문서 정책. 실제 OS/WebView 경계는 NOT_RUN |
| C19/C20 | 명시적 slot/back capability·cold fallback·기존 메뉴/draft/media/late response/lifecycle·overlay 검사 |
| C21 | 정확한 committed 변화·additions, frozen prefix/API/ORM/migration 보존 및 공식 도구 |
| C22 | 기술/browser/native/운영/설치/USER CHECK 상태 별도 기록 |

| 검사 | 실제 대응과 남은 범위 | 원 제안 |
| --- | --- | --- |
| T01/T02/T03/T04 | general 9폭×4높이, workspace 6폭, 실제 bounding box/overflow/remaining height·단일 scroll·장식·focus | V01–V04 |
| T05/T06 | 27 route/alias corpus 직접 진입+reload 및 기존 성공/빈/오류/권한 상태, ko/en·긴 값·200%·포커스 | V05/V06 |
| T07 | 순수 unit의 work area·caption/outer inset·잘못된 scale·음수 좌표·100/125/150/200% 계산 | V07/V08 계산 부분 |
| T08/T09 | **실제 OS 시작·독립 resize·max/restore/Snap·실제 DPI/다중 모니터 NOT_RUN** | V07/V08 실제 부분 |
| T10/T11/T12 | draft/Esc/IME·외부/malformed/traversal/private/unsupported·정상 encoded/query/alias/reserved new | V09/V13 |
| T13/T14 | push/replace/back/forward/new tail·original router state·rejected push·corrupt/missing/storage denial | V10 |
| T15/T16 | cross-kind success/failure command/source history·child Home main·deep URL가 stale init보다 우선 | V11/V12/V20, 실제 singleton focus는 native 후속 |
| T17/T18 | JS toolbar/reload/keyboard와 unsaved confirmation, draft/durable/job/message 처리. 실제 WebView 키 조작·모든 in-progress accepted reload 조합은 후속 | V12/V15 |
| T19 | 잘못된/external 주소 입력·Rust document/new-window/external-opener unit. 실제 redirect/popup/IPC WebView 동작 NOT_RUN | V13 |
| T20/T21 | shutdown 상태/host lifecycle/Rust unit·renderer child reload·late scope/unmount. 실제 OS X/Alt+F4/child X NOT_RUN | V14 |
| T22/T23 | 기존 PNG/JPEG/WebP·SNS/Chat attachments·scroll·draft·lifecycle 및 Dialog/focus/contrast/motion visual | V15 |
| T24/T25 | 44px/좁은 toolbar/ko/en200%·copy/select address·synthetic key/IME/modal/textarea. 실제 WebView Ctrl+L 등은 후속 | V18/V09 |
| T26/T27/T28 | Home/back 통합과 native direct-entry World fallback, 주요 메뉴/취소/재조회/인식 실패 복구 | V19/V20 |
| T29/T30/T31/T32/T33 | 기존 late scope/runtime/collection/media/security/package·boundary/design·exact source/node/API/ORM·two builds·mutation ledger | V05/V11/V12/V14/V15와 기능 보호 |
| T34/T35 | **사용자 Docker/설치판 실제 적용과 USER CHECK NOT_RUN** | V16/V17 |

이 표의 native 제한은 unit/browser PASS로 대체하지 않는다. 실제 이미지·AI 품질이나 자연 SNS 활동 품질도 이번 결과에서 판정하지 않는다.

## 8. 후속 적용과 종료 기록

이번 범위는 로컬 source/evidence commit까지다. push/원격 issue/PR/Hosted CI/act/main 전환·병합·rebase/pull을 수행하지 않는다. 운영 build/restart와 설치판 교체·업데이트도 수행하지 않는다.

후속 native USER CHECK는 격리 contributor fixture에서 최초 창, 독립 resize/min/최대화/복원/Snap, DPI/다중 모니터, Ctrl+L/Alt/F5/Ctrl+R, same/cross-kind 창, HTTP(S) 기본 브라우저, 악성 document/popup 차단, main X/Alt+F4 shutdown과 child X/reload를 확인한다. 실제 설치판 확인은 identity helper로 물리/running identity를 검증한 뒤 진행한다. 사용자 Windows 배율·보안 설정·설치 데이터는 이 검사를 위해 변경하지 않는다.

source commit은 시작 HEAD의 직접 자손이며 이번 명시적 71개 파일만 포함한다. 이후 inventory 보완은 명시적 5개 파일, 마지막 metadata/검증 문서 커밋은 증거 manifest 두 개와 이 문서만 포함한다. API/ORM 업무 source와 dependency lockfile 변경은 없다. 마지막 커밋의 정확한 SHA와 clean 상태는 workspace 원 계획 §20과 로컬 `final-summary.json`, 최종 보고에 기록한다.

종료 확인 `shutdown.json`에는 fixture 포트 3200/3300/3301/3302/3351/3352의 listener **0**과 task-owned visual 컨테이너 **0**이 기록되어 있다. task-owned 서버는 종료했고 로컬 artifact/build/source snapshot은 ignore 상태로 보존했다. 실제 native exe는 시작되지 않았다. `next-collection-list.json`/`static-collection-list.json`과 실제 Next `next-final-results.json`/static `static-results.json`을 구분한다.

최종 보존 검사 종료 뒤 `final-shutdown.json`으로 같은 포트 listener **0**, task-owned visual 컨테이너 **0**을 다시 확인했다. 사용자 runtime을 중지하거나 데이터·볼륨을 정리하지 않았다.
