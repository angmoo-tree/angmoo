# World 상태·관계망·생성·이미지 키·기억 설정 구현 검증 기록 — 2026-10-09

- 요청 계획: workspace `docs/plan/10-09 World 상태·관계망과 캐릭터 생성·ComfyUI·기억 설정 개선 코드 구현 세부 계획.md`의 **I00–I39(40단계)**.
- 제품 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 로컬 브랜치: **feat/0.1.0-release-readiness**. 시작 HEAD **f79310d5697ae75d2a594e8b2c26b4e48e6b17aa**, 시작 작업 트리 clean.
- 이 문서는 이번 로컬 구현 제출에 포함한다. 최종 commit SHA와 작업 트리 재확인 결과는 workspace 계획의 실행 기록 및 `git log -1`로 확인한다.
- 범위: **C01–C36/A01–A44/D01–D03 추적, 관련 V00–V15 로컬 검증 완료**. 원래 기능정의서의 선택적 임베딩 바로가기·서버 키 호환·자동 재사용 미추가 정책은 계획 D01–D03으로 대체한다.
- 실제 AI·ComfyUI 모델·Partner 인증·사용자 DB·Docker·설치 앱을 사용하지 않았다. PR·push·CI·main merge·전체 lint/typecheck/build/export·전체 backend/native suite는 실행하지 않았다.

## 구현 결과와 보존 범위

1. 상태 탭에 저장된 계획/관심 주제의 조회 카드를 추가했다. 서버의 실제 실행 상태와 World 날짜를 사용한다. 설정의 생성 controller를 mount하지 않으며 조회·펼침·접기·재시도·탭 이동에서 생성 명령을 호출하지 않는다. 원문 표시를 설정과 공유하고 최근 활동 내부 scroll 및 기존 카드 순서를 보존했다.
2. 신규 캐릭터는 현재 지원하는 직접 만들기/카드/조건부 복사만 선택한다. 신규 `local`/`external` 실행 유형은 DTO와 서버 경계에서 거절한다. 기존 캐릭터/초안/완료 receipt의 읽기 호환성과 입력·media는 유지한다. 이전 외부 초안은 GET만으로 전환하지 않고 사용자의 명시 재선택을 CAS로 처리한다.
3. 관계 탭과 기존 graph 직접 URL은 공용 World 틀에서 동일 관계 본문을 제공한다. 일반 탭은 해당 World owner, 직접 URL은 지정 Character 기준이다. 중간 열기 버튼·추가 identity 생성·AI/rebuild 명령이 없다. 지도/방향/깊이/상한/목록/근거/정리 상태는 유지한다. Phone route 허용은 Rust의 기존 query 경계와 함께 제한했다.
4. World의 실행 선택(current)과 제공사별 암호화 키 보관(vault)을 분리했다. 제공사 복귀/같은 서비스 모델 변경은 저장 키를 재사용한다. 삭제는 해당 vault tombstone과 실행 revision secret 폐기를 같은 UoW에서 처리하여 이력으로 되살아나지 않는다. 다른 provider 및 Partner는 보존한다. ComfyUI 서버 키는 current/history/legacy에서 정식 forward migration으로 폐기하고 신규 입력·resolve·HTTP 전달도 차단했다.
5. 기억 저장→임베딩 모델 API 키→관계 정리 순서와 같은 saved 설정의 안내를 적용했다. 임베딩 카드에는 자료/검색 질의 두 용도와 전송·비용을 설명한다. 임베딩 바로가기를 추가하지 않는다. 실제 기억 접수/검증/저장/예약·종료·FTS5/Vec1·회상 backend 로직은 변경하지 않았다.

현재 데이터가 자동으로 이관 완료됐다는 의미는 아니다. 다음 정상 앱 시작의 정식 migration이 v33→v34를 실행한다. 이 작업에서 실제 데이터의 Comfy 서버 키를 직접 열거나 삭제하지 않았다. 서버 인증이 필수인 Comfy 프록시는 D02의 무서버키 계약으로 지원하지 않으며 Partner 계정 인증은 별개로 유지한다.

## 단계별 완료 근거

| 단계 | 계획 작업 | 수행 결과 |
| --- | --- | --- |
| I00 | 브랜치·작업 트리·지침 확인 | 요청 branch, 시작 HEAD f79310d5와 clean 작업 트리 확인; 실제 사용자 데이터와 별도 검증 포트 분리. |
| I01 | 계약·파일·관련 fixture 기준 확정 | C01–C36/A01–A44/D01–D03 우선순위 및 합성 fixture·scope/CAS 기준 확정. |
| I02 | 일과·주제의 순수 표시 계약 정리 | daily-plan-presentation에 World 날짜·준비 상태·plan ID/version·4개 행의 실제 상태 표시 분리. |
| I03 | 요약용 읽기 controller 분리 | use-active-scoped-read가 GET·abort·auth/runtime/scope·retained error를 소유; 생성 controller와 분리. |
| I04 | 설정/상태가 공유할 원문 표시 추출 | DailyPlanRows/RecommendationTopicList를 settings와 status가 같은 feature 안에서 공유. |
| I05 | 관심 주제 조회용 카드 구현 | RecommendationTopicsSummary: 기본 6개·실제 +N·전체 펼침·0개/stale/실패와 설정 callback. |
| I06 | 오늘 하루 계획 조회용 카드 구현 | WorldDailyPlanSummary: 준비/계획 GET·World 날짜/시간대·4행·독립 전체 원문 상세. |
| I07 | 상태 슬롯 조립과 6개 카드 순서 적용 | composition status 슬롯으로 현재 상태→최근 활동→계획→주제→페르소나→활동 요약 6개 카드. |
| I08 | 요약의 조회 수명·날짜 갱신 적용 | active+visibility 수명과 World 자정 timer; auth/runtime/actor 전환 시 이전 응답·timer 폐기. |
| I09 | 상태 요약 관련 검증 | 상태 신규/기존 브라우저 fixture, 원문·개수·날짜·조회 전용·최근 활동 내부 scroll 확인. |
| I10 | 신규 생성 지원 범위 정의 | 신규 생성 DTO는 llm만 지원, 기존 read DTO local/external 및 저장 유형 보존. |
| I11 | 모든 신규 생성·등록 경계 검사 | create_draft/management.create_agent/register_draft가 부수효과 전 차단; 성공 receipt replay 유지. |
| I12 | 이전 외부 초안의 명시 재선택 계약 | 소유/기한/editing/revision/target 검사 후 이전 external 초안의 명시 재선택; v1 adopt 분리. |
| I13 | 생성 UI 선택지 제거와 복원 안내 | 새 external 선택 DOM 제거; 복원 안내·3가지 지원 방법·서버 승인 후 다음 단계, 입력 유지. |
| I14 | 지원 생성 방식·기존 자료 관련 검증 | 생성 정책 신규 11사례 및 기존 원자 등록·카드/복사 관련 사례 통과. |
| I15 | 관계망 본문과 독립 소개 틀 분리 | RelationshipGraphClient의 embedded 본문 재사용; 기존 wide enum은 launch metadata 읽기 호환용 보존. |
| I16 | 기본/명시 관계 기준과 gate 연결 | 일반 관계는 해당 World owner GET 결과, 직접 링크는 명시 Character ID; 관계 진입 ensure 쓰기 0. |
| I17 | 공통 World 헤더·하단바로 관계 탭 구성 | WorldRelationshipsScreen을 WorldAppShell에 조립, 단일 헤더/5탭/관계 active·실제 기준 이름. |
| I18 | Next/static 직접 URL의 공용 screen 연결 | Next graph route와 StaticProductRouter가 같은 World composition; query와 login returnTo 유지. |
| I19 | 관계 진입의 창·제품 탐색 분류 조정 | frontend Phone 분류와 Rust 정확한 관계 route/query 허용 정렬; 다른 창 경계 보존. |
| I20 | 관계 본문의 스크롤·폭·focus 정리 | World outer scroll 1개·카드 16/36px 좌우 여백·지도 내부 가로 scroll 최초 기준 중앙·근거 focus. |
| I21 | 관계 통합 관련 검증 | 일반/직접·reload/back/forward/인증 복귀·권한/빈 관계/fallback·읽기 API 4사례 및 브라우저 확인. |
| I22 | 공통 credential 표시 옵션과 선택 상태 보호 | CredentialFields 중립 옵션/선택 metadata/취소·late 보호; media가 provider 판단, 원문 autofill 없음. |
| I23 | World 서비스별 키 저장소·이관·자동 재사용·폐기 | 제공사별 암호화 vault·current/key/policy CAS·재사용·tombstone·정식 forward SQLite v34/Alembic 0111. |
| I24 | 기존 캐릭터 이미지 설정의 무키 계약 정렬 | legacy Comfy 서버 키 신규 등록/resolve 차단·폐기, 기존 외부 provider 보관 및 별도 Partner 유지. |
| I25 | 두 이미지 설정 화면에 표시·문구 적용 | World/legacy Comfy generic secret DOM 제거·선택 서비스 키 안내·미저장 키 정리·실패/retry 보호. |
| I26 | Partner 전달·기존 workflow 계약 확인 | Comfy HTTP Authorization 없음; Partner extra_data만·누락 시 제출 전 거절; workflow/참조/첫 출력 유지. |
| I27 | ComfyUI 수정 관련 검증 | vault 6·migration 5·Partner 10 관련 사례 및 두 이미지 UI mock 통과; 실모델 미실행. |
| I28 | memory의 saved embedding 설정 controller 추출 | use-saved-embedding 하나로 saved 설정/키 metadata 조회; editor dirty 상태와 분리·같은 범위 공유. |
| I29 | 기억 카드 순서와 임베딩 제목·설명 변경 | 기억 저장→임베딩 모델 API 키→관계 정리 순서; 같은 키의 자료/질의 임베딩 두 용도·비용 ko/en. |
| I30 | 저장 카드의 saved 설정 안내 연결 | 저장 카드가 saved ON/OFF/key/runtime/preparation/read failure를 구분; 미저장 toggle 반영 없음. |
| I31 | 바로가기 미추가와 기존 편집·요청 보호 | 임베딩 바로가기/전용 scroll-focus 없음; 기존 명시 save/delete/prepare·lock·재검사/포기 보존. |
| I32 | 기억 화면 변경 관련 검증 | OFF/no-key 실제 SQLite FTS 2사례·기존 설정/preparation 관련 API와 memory UI 회귀 6사례 확인. |
| I33 | 모든 수정 문구의 ko/en 정합성 | 5개 feature의 ko/en 60개 변경 키 및 placeholder 일치·실제 대표 화면 확인. |
| I34 | 변경 범위 architecture/design 검사 | 32 entry의 277 import·공통 책임·semantic color·main/scroll 검사 및 LOCAL architecture/design 기록. |
| I35 | 변경 파일 lint·타입·정적 검사 | 32 TS/TSX scoped ESLint/tsc·브라우저 scoped tsc·29 Python AST/compile·diff check 통과. |
| I36 | 관련 backend 회귀 묶음 실행 | 미실행 관련 backend node만 보완; 범위 내 실패 해결·재검사, 전체 pytest/네트워크 설치 없음. |
| I37 | 공용 화면의 관련 브라우저 검증 정리 | Next+static-shell dev의 신규 38·기존 status 14·기존 memory 6 = 고유 브라우저 58사례 확인. |
| I38 | 계약 추적과 완료/미관찰 기록 갱신 | 이 기록과 외부 계획/기능정의서에 C/A/D→I/V 연결·완료 및 실환경 미관찰 경계 갱신. |
| I39 | 로컬 커밋과 최종 인계 | 요청 branch의 명시한 task 파일만 로컬 커밋·작업 트리 복구 확인; commit SHA는 외부 계획 실행 기록에 기록. |

## 관련 검증 V00–V15

| ID | 실제 확인한 범위와 결과 |
| --- | --- |
| V00 | 요청 branch/clean 시작; 32 entry의 277 내부 import에서 feature 간 역방향/직접 cross-feature 신규 연결 0; 33 변경 TS/CSS의 raw color 0→0; 공용 카드/route/scroll 책임 확인. 기존 frozen migration/manifest 수정 0, 정책·baseline 완화 0. |
| V01 | scoped ESLint 32 TS/TSX에서 error/warning 0; 임시 scoped tsconfig로 변경 entry와 실제 import 의존성 타입 검사, 브라우저 fixture/spec/config 타입 검사 통과. 변경 Python 29파일 AST/compile 및 신규 cross-domain import 검사 통과. ko/en 60개 변경 key와 placeholder 일치, diff check 통과. 전체 프로젝트 PASS로 확장하지 않는다. |
| V02 | 주제 0/1/6/7/10개, 기존 목록을 유지한 stale/재생성 실패/read error; plan 4행·독립 상세·긴 원문·누락·실제 planned/active/skipped; 이전 날짜·plan version 불일치·Seoul/NY World 날짜·DST 23시간 경계 확인. |
| V03 | status active/inactive·page hidden·설정 왕복·World 자정·late actor·runtime/auth 변경의 격리된 응답·timer 수명 확인. 기존 status 14사례에서 활동 링크/내부 scroll/정책·설정 기능 보존, UI 비명시 쓰기/생성 요청 0. |
| V04 | 생성 정책 신규 11사례: 수동 unsupported create, 신규 external register, explicit reselect, stale/target/registering/expired, commit rollback, foreign owner, v1 adopt/input/media, 완료 external receipt replay. 기존 원자 등록/실패 rollback/카드/복사 관련 node도 통과. |
| V05 | ko/en·Next/static의 external 후보 DOM/접근성 없음·이전 초안 안내/재선택/입력 보존·3지원 radio 확인. 카드/복사 서버의 기존 제한·원본 보호 관련 회귀 유지. |
| V06 | 해당 World owner 기본·다른 자율 캐릭터 explicit URL·reload/back/forward/login returnTo·owner missing/403·late center 확인. explicit 진입을 owner로 교체하지 않고 자동 ensure 쓰기 0. |
| V07 | depth1/2·limit20·arrows·목록/인식·review·근거 링크 보존; empty/unavailable/rebuilding/lagging/canonical fallback 표시 경계. graph 읽기 관련 backend 4사례 통과. 근거 link의 동일 World/원문 target·키보드 focus 확인. |
| V08 | World main 1개·footer 1개·5탭/관계 active·같은 World 링크·끝 근거가 footer 위에 보임·지도 내부 가로 scroll·처음 기준 캐릭터 가시성·back/forward. 관련 native URL 단위 3개 통과(Phone/Ladybug query 강화 사례 재실행 포함). |
| V09 | vault 신규 6사례 + migration 5사례: current/key/policy CAS·scope·commit rollback, 외부→Comfy→외부/다른 서비스/모델 재사용·inactive provider delete·generic delete tombstone·승인 revision 보존·삭제 후 fallback 차단; ORM/Alembic/embedded parity·합성 v33 이관·재실행·wrong secret/corrupt staging rollback. 외부/Partner byte 보존. |
| V10 | World/legacy Comfy generic secret block DOM 없음·Partner 별도·provider saved metadata·무원문 autofill·unsaved key clear·동일 서비스 model dirty 유지·late response·read failure/retry/save disable·명시 provider delete isolation; 선택만의 쓰기/생성 0. |
| V11 | Partner 관련 10사례에서 OFF 무계정키, ON extra_data만, 계정키 누락/폐기 서버키 입력 시 제출 전 거절, credential envelope/snapshot/delete/revision 확인. 기존 workflow 자리표시자/JS key 순서/첫 preview 출력/참조 encode 관련 3사례도 통과. 외부 네트워크/실제 모델 0. |
| V12 | 저장→임베딩→관계 순서·두 용도/비용·same saved controller/한 key read; 미저장 toggle 및 dirty poll 보호·키 없음/조회 실패/회복/runtime 갱신·no shortcut·정확한 준비 안내 확인. |
| V13 | saved GET/ON save로 full preparation 없음·explicit prepare 1회. embedding setting scope/CSRF/CAS·rotation/revoke 관련 기존 API 통과. 실제 FTS5 격리 검색 OFF/no-key 2사례에서 provider/vector 호출 0. 기존 memory UI 대표 6사례에서 수동 저장·예약 dirty·재검사/포기/동일 요청 재시도 보존. 관계 정리 UI/controller 기존 연결 보존. |
| V14 | 5영역 대표 ko/en; 원문 untranslated, keyboard Enter/Space/aria-expanded/focus; 360/390/960 및 memory 200% 글자 확대 overflow 확인·기존 memory 대표 390/1100. 로컬 PNG는 visual inspection 자료이며 canonical pixel baseline/전체 디자인 PASS를 뜻하지 않는다. |
| V15 | Next dev 3347 + tauri-static static-shell dev 3348에서 같은 composition/feature 진입·URL/query·명시 기준·인증 복귀 확인. static document fallback fixture가 주소를 보존하고 StaticProductRouter를 실행. full export/native 창/설치 앱은 미관찰. |

## 실행 결과와 재검사 범위

### 브라우저

**고유 사례 58건 통과**: 새 scoped spec 19×2환경=38건, 기존 status spec 7×2=14건, 기존 memory의 선택한 3×2언어×Next=6건이다. 같은 사례 재검사를 추가 통과 수로 합산하지 않는다.

기본 및 보완 기록:

- `artifacts/world-ui-improvements-20261009/browser-improvements-results.json`: 최초 scoped 34건 통과.
- `browser-status-regression-results.json`: 기존 status 14건 통과.
- `browser-scope-key-recovery-results.json`: 보완한 auth/late/key failure 4건 통과.
- `browser-visual-keyboard-results.json`: 16건 대표 화면 재검사 통과.
- `browser-graph-layout-results.json`: 헤더/여백/초기 지도 중앙 수정 후 관련 16건 통과.
- `browser-memory-preservation-results.json`: 기존 기억 대표 6건 통과.
- `browser-evidence-initial-results.json`: 근거 링크 추가 검사 때 Next 2건 통과, static 2건은 정상 trailing slash를 fixture 기대값이 거절하여 실패. 제품 route 변경 없이 `/`의 기존 정규화를 허용하도록 기대값을 정렬했다.
- `browser-evidence-final-results.json`: 수정 후 static 두 언어의 끝 근거/focus/footer 검사 통과.

전용 config의 `static-export` 이름은 기존 project 식별자이며 **이번 실행은 static-shell dev**다. 테스트 browser의 loopback HMR에만 `--disable-features=LocalNetworkAccessChecks`를 적용했다. fixture가 단일 static document를 응답할 때 Chrome의 socket-origin 판정으로 HMR이 막히는 시험 환경을 다룬 것이다. 제품 코드, 운영 브라우저 보안 설정, Tauri URL/query 정책을 바꾸지 않았다.

검증 전용 프로세스: Next `3347`/임시 `.next-world-ui-20261009`, static-shell `3348`/`NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE=tauri-static`. 시험 뒤 두 프로세스를 종료하고 Next의 자동 tsconfig include/생성 guidance만 원상 복구했다. 실제 사용자 서버는 변경하지 않았다.

실제 선택 명령(제품 repo의 `browser-tests`):

```powershell
pnpm exec playwright test --config playwright.world-ui-improvements.config.ts world-ui-improvements.spec.ts --workers 1
pnpm exec playwright test --config playwright.world-ui-improvements.config.ts world-character-status.spec.ts --workers 1
pnpm exec playwright test --config playwright.world-ui-improvements.config.ts world-ui-improvements.spec.ts --grep 'login recovery|late metadata' --workers 1
pnpm exec playwright test --config playwright.world-ui-improvements.config.ts world-ui-improvements.spec.ts --grep 'six cards|world-relationships|saved notice' --workers 1
pnpm exec playwright test --config playwright.world-ui-improvements.config.ts world-ui-improvements.spec.ts --grep 'owner and explicit center share' --project static-export --workers 1
```

memory 6건은 같은 전용 config의 공통 browser 옵션을 유지한 임시 config로 `memory-situation.spec.ts`와 `memory-situation-recovery.spec.ts`의 `three independent roles|OFF permits discard|recheck whole frozen scope`만 Next에서 선택했다. 임시 config는 제거했다. 반복 실행 시 같은 two-file testMatch/Next/grep 범위를 사용한다.

### Backend 및 native

각 소유 테스트에 필요한 새 사례를 넣고 해당 파일의 task case/node만 실행했다. 전체 backend suite를 수집하거나 실행하지 않았다.

| 관련 대상 | 결과 |
| --- | --- |
| `tests/characters/test_creation_method_policy.py` | 11 PASS(4가지 재선택 실패 parameter 포함). |
| `tests/identity/test_world_image_provider_vault.py` | 6 PASS. |
| `tests/migrations/test_image_provider_vault_v34.py` | 5 PASS(Alembic/embedded 2 + staging 성공/wrong secret/corrupt 3). |
| `tests/memory/test_embedding_keyword_preservation.py` | 2 PASS(OFF / ON이지만 키 없음). |
| `tests/image_integration/test_comfy_partner.py`의 관련 사례 | 10 PASS(폐기 서버키 validate/generate 2 포함). |
| 기존 등록·card/copy·WorldCredential·embedding settings/preparation·read-only graph 관련 node | 선택한 관련 사례 PASS. 다른 기존 suite의 전체 상태를 판정하지 않음. |
| `test_comfy_placeholders.py`의 JS 출력 순서·seed/clip snapshot·참조 metadata encode | 선택한 3 PASS. |
| `product_windows::tests::product_routes_stay_inside_their_window_boundaries` | exact 단위 검사 PASS. |
| `product_windows::tests::relationship_graph_provider_is_ladybug_only` | exact 단위 검사 PASS; Phone/legacy graph의 provider/query 제한 보강 후 재검사 PASS. |
| `product_windows::tests::route_validation_rejects_external_and_traversal_inputs` | exact 단위 검사 PASS. |

backend에서는 `uv run --no-sync python -m pytest <관련 node ID>`를 사용했다. 새 테스트의 재실행 node는 각 파일의 `test_` 함수 및 명시한 parameter로 선택할 수 있다. 설치 앱·Docker·실제 키에 대한 이관은 포함하지 않는다. native는 `cargo test --lib <위 exact node> -- --exact`만 실행했다.

### 정적 검사와 파일 목록

실제 입력/결과는 workspace `.local-diagnostics/world-ui-improvements-20261009-192654/`에 보관했다: `frontend-entries.json`, `eslint-results.json`, `tsconfig.scoped.json`, `tsconfig.browser-scoped.json`, `scoped-source-audit.json`, `scoped-python-audit.json`.

```powershell
# frontend에서; entry 목록 32개는 아래와 동일
node 'D:/project_code/angmoo-workspace/.local-diagnostics/world-ui-improvements-20261009-192654/scoped-eslint.cjs'
pnpm exec tsc --project 'D:/project_code/angmoo-workspace/.local-diagnostics/world-ui-improvements-20261009-192654/tsconfig.scoped.json' --noEmit --incremental false
pnpm exec tsc --project 'D:/project_code/angmoo-workspace/.local-diagnostics/world-ui-improvements-20261009-192654/tsconfig.browser-scoped.json' --noEmit --incremental false
# product repo에서
node 'D:/project_code/angmoo-workspace/.local-diagnostics/world-ui-improvements-20261009-192654/scoped-source-audit.cjs'
git diff --check
```

임시 tsconfig는 기존 설정을 상속하고 32 entry/필요 선언 또는 browser 4 entry/필요 선언으로 include를 제한했다. 실제 import로 연결된 타입은 검사하며 stub·ts-ignore·ts-nocheck·새 예외를 넣지 않았다. 기존 skipLibCheck 등 저장소 설정을 임의로 강화/완화하지 않았다.

32 frontend entry:

- `frontend/src/app/characters/[characterId]/worlds/[worldId]/relationship-graph/page.tsx`
- `frontend/src/components/ui/credential-fields.tsx`
- `frontend/src/composition/screens/world-app-screen.tsx`
- `frontend/src/composition/screens/world-app.tsx`
- `frontend/src/composition/screens/world-character-management-screen.tsx`
- `frontend/src/composition/screens/world-relationships-screen.tsx`
- `frontend/src/composition/static-product-router.tsx`
- `frontend/src/features/characters/api/agents.ts`
- `frontend/src/features/characters/components/agent-create-client.tsx`
- `frontend/src/features/characters/components/daily-plan-card.tsx`
- `frontend/src/features/characters/components/daily-plan-rows.tsx`
- `frontend/src/features/characters/components/world-character-management.tsx`
- `frontend/src/features/characters/components/world-character-status-cards.tsx`
- `frontend/src/features/characters/components/world-daily-plan-summary.tsx`
- `frontend/src/features/characters/types/agents.ts`
- `frontend/src/features/characters/utils/daily-plan-presentation.ts`
- `frontend/src/features/media/api/media-client.ts`
- `frontend/src/features/media/api/world-image-policy.ts`
- `frontend/src/features/media/components/generation-settings.tsx`
- `frontend/src/features/media/components/world-image-policy-controls.tsx`
- `frontend/src/features/media/utils/image-key-presentation.ts`
- `frontend/src/features/memory/components/memory-credential-fields.tsx`
- `frontend/src/features/memory/components/memory-embedding-controls.tsx`
- `frontend/src/features/memory/components/memory-workspace.tsx`
- `frontend/src/features/memory/hooks/use-saved-embedding.ts`
- `frontend/src/features/relationships/components/relationship-graph-client.tsx`
- `frontend/src/features/social/components/recommendation-topic-list.tsx`
- `frontend/src/features/social/components/recommendation-topics-panel.tsx`
- `frontend/src/features/social/components/recommendation-topics-summary.tsx`
- `frontend/src/hooks/use-active-scoped-read.ts`
- `frontend/src/lib/desktop/product-window.ts`
- `frontend/src/lib/navigation/device-navigation.ts`

## C01–C36 / A01–A44 추적

각 행은 계획 §8의 동일 ID와 I/V 연결을 유지한다. 위 단계별 소유 파일 및 V의 실제 근거를 함께 읽는다. A43의 optional 임베딩 바로가기는 D01로 제외되며 나머지 기존 접근성은 유지한다. C29/A34는 D02가 지정한 Comfy 서버 키에 한해 정식 폐기를 수행한다.

| 계약/기준 | 구현 | 검증 | 완료 해석 |
| --- | --- | --- | --- |
| C01 | I03–I07 | V02/V03 | 완료: 위 해당 I/V 근거. |
| C02 | I07 | V03/V14 | 완료: 위 해당 I/V 근거. |
| C03 | I02/I05 | V02 | 완료: 위 해당 I/V 근거. |
| C04 | I02/I06 | V02 | 완료: 위 해당 I/V 근거. |
| C05 | I06 | V02/V14 | 완료: 위 해당 I/V 근거. |
| C06 | I02/I06 | V02 | 완료: 위 해당 I/V 근거. |
| C07 | I04/I07/I34 | V00/V14 | 완료: 위 해당 I/V 근거. |
| C08 | I07/I08 | V03 | 완료: 위 해당 I/V 근거. |
| C09 | I03/I08/I09 | V03 | 완료: 위 해당 I/V 근거. |
| C10 | I33 | V01/V14 | 완료: 위 해당 I/V 근거. |
| C11 | I10/I13 | V05 | 완료: 위 해당 I/V 근거. |
| C12 | I13/I14 | V04/V05 | 완료: 위 해당 I/V 근거. |
| C13 | I10/I11 | V04 | 완료: 위 해당 I/V 근거. |
| C14 | I12/I13 | V04/V05 | 완료: 위 해당 I/V 근거. |
| C15 | I10/I11/I12/I14 | V04 | 완료: 위 해당 I/V 근거. |
| C16 | I16/I17 | V06 | 완료: 위 해당 I/V 근거. |
| C17 | I15/I17 | V08 | 완료: 위 해당 I/V 근거. |
| C18 | I15/I17 | V08/V14 | 완료: 위 해당 I/V 근거. |
| C19 | I15/I20/I21 | V07 | 완료: 위 해당 I/V 근거. |
| C20 | I16 | V06 | 완료: 위 해당 I/V 근거. |
| C21 | I18/I19 | V06/V15 | 완료: 위 해당 I/V 근거. |
| C22 | I20/I21 | V07/V08 | 완료: 위 해당 I/V 근거. |
| C23 | I22/I25 | V10 | 완료: 위 해당 I/V 근거. |
| C24 | I23/I24/I25 | V09/V10/V11 | 완료: 위 해당 I/V 근거. |
| C25 | I22/I23/I24/I25 | V09/V10 | 완료: 위 해당 I/V 근거. |
| C26 | I24/I25/I26 | V09/V11 | 완료: 위 해당 I/V 근거. |
| C27 | I23/I26 | V11 | 완료: 위 해당 I/V 근거. |
| C28 | I22/I23/I24/I25/I33 | V09/V10/V15 | 완료: 위 해당 I/V 근거. |
| C29 | I23/I24/I26/I27 | V09/V11 | 완료: 위 해당 I/V 근거. D02의 지정 서버 키 폐기 및 D03 재사용을 우선 적용. |
| C30 | I29 | V12/V14 | 완료: 위 해당 I/V 근거. |
| C31 | I29/I33 | V12/V14 | 완료: 위 해당 I/V 근거. |
| C32 | I28/I31 | V12/V13 | 완료: 위 해당 I/V 근거. |
| C33 | I28/I30 | V12 | 완료: 위 해당 I/V 근거. |
| C34 | I30 | V12 | 완료: 위 해당 I/V 근거. |
| C35 | I28/I31/I32 | V13 | 완료: 위 해당 I/V 근거. |
| C36 | I29/I31/I33/I34 | V00/V14/V15 | 완료: 위 해당 I/V 근거. |
| A01 | I07 | V03/V14 | 완료: 위 해당 I/V 근거. |
| A02 | I05 | V02 | 완료: 위 해당 I/V 근거. |
| A03 | I02/I05 | V02 | 완료: 위 해당 I/V 근거. |
| A04 | I06 | V02 | 완료: 위 해당 I/V 근거. |
| A05 | I02/I06 | V02 | 완료: 위 해당 I/V 근거. |
| A06 | I02/I06/I08 | V02/V03 | 완료: 위 해당 I/V 근거. |
| A07 | I07 | V03 | 완료: 위 해당 I/V 근거. |
| A08 | I03 | V03 | 완료: 위 해당 I/V 근거. |
| A09 | I03/I08 | V03 | 완료: 위 해당 I/V 근거. |
| A10 | I03/I08 | V03 | 완료: 위 해당 I/V 근거. |
| A11 | I04/I07 | V03/V15 | 완료: 위 해당 I/V 근거. |
| A12 | I05/I06/I33 | V14 | 완료: 위 해당 I/V 근거. |
| A13 | I10/I13 | V05/V15 | 완료: 위 해당 I/V 근거. |
| A14 | I11 | V04 | 완료: 위 해당 I/V 근거. |
| A15 | I12/I13 | V04/V05 | 완료: 위 해당 I/V 근거. |
| A16 | I13/I14 | V04/V05 | 완료: 위 해당 I/V 근거. |
| A17 | I10/I11/I12 | V04 | 완료: 위 해당 I/V 근거. |
| A18 | I17 | V06 | 완료: 위 해당 I/V 근거. |
| A19 | I15/I17 | V08/V14 | 완료: 위 해당 I/V 근거. |
| A20 | I17/I19 | V08 | 완료: 위 해당 I/V 근거. |
| A21 | I16 | V06 | 완료: 위 해당 I/V 근거. |
| A22 | I18 | V06/V15 | 완료: 위 해당 I/V 근거. |
| A23 | I15/I20 | V07 | 완료: 위 해당 I/V 근거. |
| A24 | I16/I17/I21 | V06/V07 | 완료: 위 해당 I/V 근거. |
| A25 | I20 | V08/V14 | 완료: 위 해당 I/V 근거. |
| A26 | I16/I18/I21 | V06/V08 | 완료: 위 해당 I/V 근거. |
| A27 | I18/I33 | V14/V15 | 완료: 위 해당 I/V 근거. |
| A28 | I22/I25 | V10 | 완료: 위 해당 I/V 근거. |
| A29 | I23/I24/I26 | V09/V11 | 완료: 위 해당 I/V 근거. |
| A30 | I23 | V09 | 완료: 위 해당 I/V 근거. |
| A31 | I22/I23/I24/I25 | V09/V10 | 완료: 위 해당 I/V 근거. |
| A32 | I24/I25/I26 | V09/V11 | 완료: 위 해당 I/V 근거. |
| A33 | I26 | V11 | 완료: 위 해당 I/V 근거. |
| A34 | I23/I24/I26/I27 | V09/V11 | 완료: 위 해당 I/V 근거. D02의 지정 서버 키 폐기 및 D03 재사용을 우선 적용. |
| A35 | I25/I33 | V10/V14/V15 | 완료: 위 해당 I/V 근거. |
| A36 | I26/I27 | V11 | 완료: 위 해당 I/V 근거. |
| A37 | I29 | V12/V14 | 완료: 위 해당 I/V 근거. |
| A38 | I29/I33 | V12/V14 | 완료: 위 해당 I/V 근거. |
| A39 | I28/I30 | V12 | 완료: 위 해당 I/V 근거. |
| A40 | I30 | V12 | 완료: 위 해당 I/V 근거. |
| A41 | I30 | V12 | 완료: 위 해당 I/V 근거. |
| A42 | I28/I31/I32 | V12/V13 | 완료: 위 해당 I/V 근거. |
| A43 | I28/I31/I33 | V12/V14/V15 | 완료: 위 해당 I/V 근거. D01의 바로가기 미추가; 기존 접근성 유지. |
| A44 | I28/I31/I32 | V13 | 완료: 위 해당 I/V 근거. |

| 추가 계약 | 구현/검증 | 결과 |
| --- | --- | --- |
| D01 | I29–I33 / V12–V14 | 임베딩 바로가기/전용 scroll-focus 없음; saved 안내와 카드 바로 아래 배치. |
| D02 | I23/I24/I26/I27 / V09/V11 | forward migration 및 모든 실행 경계의 서버 키 폐기/차단; Partner/다른 서비스 보존. |
| D03 | I22–I25/I27/I33 / V09–V11 | 제공사별 vault·metadata·왕복/모델 재사용·명시 삭제/tombstone/CAS, 이력 복원·평문 autofill 0. |

## 검증 중 수정한 부분과 남은 관찰 경계

- legacy 이미지 UI의 초기/선택 metadata를 auth/runtime scope 및 abort에 연결했다. 늦은 metadata/read failure가 다른 제공사의 저장 키로 표시되거나 미저장 값을 덮지 않게 했다.
- 일반 image credential 삭제도 vault CAS/tombstone으로 연결해 과거 provider key 재사용을 차단했다. 비활성 provider 삭제는 다른 current policy에 영향을 주지 않도록 유지했다.
- 관계 embedded 헤더의 확정 명칭과 settings 수준의 좌우 여백을 맞췄다. 좁은 지도에서는 전체 graph를 축소하지 않고 내부 scroll을 기준 캐릭터 중앙으로 초기화했다.
- 이전 test 기대값 두 곳을 새 D02 서버키 거절 순서로 정렬했다. Partner 목적/암호화/원본 보존 assertion을 삭제하지 않았다.
- v1 media 보존 검사의 DTO URL 기대를 실제 기존 preview proxy 계약으로 정렬하고 raw DB/파일 bytes 보존을 별도로 검사했다.
- browser fixture의 실제 enum/공용 선언, static document fallback 및 trailing slash 기대를 정렬했다. 이는 제품 기능/정책 완화가 아니다.

필수 관련 검사에서 남은 실패는 없다. 다만 이 결과는 **로컬 source+합성 fixture+scoped unit/browser 검증**이다. 실제 새 API 인증, 모델 품질, 실제 사용자 데이터 이관, 자연 활동, Docker 운영, 실제 static export artifact, native 창 전환, Windows packaging/설치 앱, canonical pixel diff, PR/CI/main 상태는 이번 실행으로 확인하지 않았다. 로컬 commit은 실제 배포·앱 서버 갱신을 뜻하지 않는다.
