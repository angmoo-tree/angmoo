# World SNS 피드 UI 통일 로컬 구현·검증 기록

- 실행 계획: `D:/project_code/angmoo-workspace/docs/plan/10-04 World SNS 피드 UI 통일과 사용자 프로필·제목·본문·이미지 첨부 코드 구현 세부 계획.md`, P00–P17.
- 제품 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`.
- 브랜치: `feat/0.1.0-release-readiness`.
- 출발 HEAD: `2806ff6a0fd876e3e987fac4dd1c313441bd53b2`, 출발 작업 폴더 clean.
- 기록 상태: P00–P14의 제품 구현·기능·시각·정적 검증 완료. P15 구현 커밋과 P16 정확한 커밋 보존 증거는 이후 기록으로 확정한다.
- 원격 push·PR·Hosted CI·act·main 전환/병합·pull: **미수행**.

## 1. 구현 결과와 책임

World 피드 목록은 왼쪽 `피드`/`Feed`, 중앙 기존 Angmoo 로고, 오른쪽 현재 World의 사용자 프로필을 표시한다. 오른쪽 프로필은 실행 중인 자율 캐릭터 대신 기존 ownerActor의 실제 사진/이니셜과 `world_character_id`를 사용한다. 같은 World의 실제 프로필 화면으로 이동하며 활동 점선은 없다. 기본 SNS와 생성 World가 같은 목록 컴포넌트를 사용한다.

수동 작성은 필수 제목 160자·본문 4000자를 유지한다. 사용자 아바타/실제 이름·지원되는 handle, 제목, 본문, 첨부 미리보기, 왼쪽 사진 아이콘과 오른쪽 코랄색/흰 Send 아이콘 순서다. 사진/게시 버튼은 글씨 없는 48×48 CSSpx 원형이며 접근성 이름·title·focus·busy/disabled와 native file chooser/submit 의미를 보존한다. 제출 중 제목/본문은 readOnly로 현재 제출 내용과 편집 내용이 엇갈리는 것을 막는다.

목록의 World App/context 안내, 작은 World 이름, 헤더 갱신 버튼, Follow/repost 필터는 렌더링하지 않는다. 최초·World 전환 조회, 게시 성공 후 갱신, 실패 화면의 명시적 다시 시도, 당겨 새로고침, 이미지 생성 완료 후 갱신은 기존 loadFeed에 남아 있다. 기존 상세·답글·다섯 World 메뉴와 글로벌의 캐릭터 선택·Feed Cue·필터·desktop 갱신은 유지한다.

| 소유 위치 | 변경과 유지 경계 |
| --- | --- |
| `frontend/src/components/layout/feed-header.tsx`, `.module.css` | neutral title/center/right 슬롯. World 조회·feature 업무 로직 없이 공통 표시·정렬만 소유 |
| `frontend/src/composition/screens/post-list-screen.tsx` | 기존 글로벌 헤더 anatomy만 추출. 활성 캐릭터·Cue·필터·갱신은 composition에 유지 |
| `frontend/src/composition/screens/world-app.tsx`, `.module.css` | 실제 ownerActor로 World 헤더·프로필 경로 구성. Media/Social의 표시 슬롯 연결 |
| `frontend/src/composition/shells/world-app-shell.tsx` | Feed 목록에서만 content-owned header. 상세와 다른 section은 기본 shell header 유지 |
| `frontend/src/features/social/components/world-social-feed.tsx`, `.module.css` | 제목/본문/form·게시 action·idempotency·기존 조회/재시도 소유. 기존 SocialPostRow 재사용 |
| `frontend/src/features/media/components/image-picker.tsx`, `media-settings.module.css` | 선택적인 renderLayout(trigger/preview/feedback) 추가. 기존 upload·abort·인식 preflight·draft·인증된 URL은 단일 Media 소유. Chat/설정 기본 표현 유지 |
| Social/Media ko/en catalog, `social-write-contract.ts` | 실제 handle의 좁은 presentation 계약과 사진/저장 안내 번역 |
| architecture/design/product-shell 문서·policy·design baseline | 승인한 LOCAL/ADAPTED 표시 변경과 정확한 현황·hash 반영 |

Backend 소스·API schema/router·ORM·migration·scheduler·Compose·dependency/lockfile 변경은 **0**이다. 새 서버·직접 DB 쓰기·고정 owner 대체·외부 image/LLM 호출을 추가하지 않았다. `backend/ARCHITECTURE.md`, `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md` 및 canonical design/reference/product-shell 소유권을 따른다.

## 2. 실행한 검사

최종 결과만 아래 PASS 수에 포함한다. 앞선 실패·중단 로그는 삭제하지 않고 로컬 artifacts에 남겼다.

| 검사 | 최종 결과 | 확인 범위 |
| --- | --- | --- |
| 새 World Feed 공통 fixture, Next production | **23 PASS, 0 FAIL/SKIP/flaky** | owner/link, 글쓰기·첨부·재시도, 늦은 응답·복귀, 좌표·다국어·focus/zoom |
| 같은 fixture, static export | **23 PASS, 0 FAIL/SKIP/flaky** | 동일 기능, 인증된 이미지 URL, static의 정상 trailing slash 포함 실제 목적지 |
| 기존 product-shell/continuity, Next production | **35 PASS, 10 SKIP, 0 FAIL/flaky** | World/Chat/Memory/관계/탐색/글로벌/PWA. 10 SKIP는 기존 opt-in HY14 실제 workflow 사례이며 PASS로 계산하지 않음 |
| 기존 static product-shell/continuity | **77 PASS, 0 FAIL/SKIP/flaky** | 직접 진입·owner/권한·답글·프로필 capability·Chat·Memory·Creator·World 메뉴 |
| 기존 image-integration, Next/static | **40 PASS, 0 FAIL/SKIP/flaky** | Chat/참조 설정 기본 picker, 인식 preflight·복구, PNG/JPEG/WebP 첨부/인증/원본 pixels·완료 갱신 |
| 지정한 backend 수동 작성/소유권/검색/기억 source 계약 | **18 PASS** | 임시 DB, 실제 수동 API의 idempotency·provider-free write·World/author·검색/기억 evidence |
| 추가 API 상한/필수 검증 + 기존 media privacy/format | **101 PASS** | 160/4000 포함 상한·초과·누락·빈 값·다른 World 주입 거절, 인증·권한·draft·MIME·형식 보존 |
| 고정 Linux canonical visual, 두 project | **36 PASS, 0 FAIL/SKIP/flaky** | 승인한 World 화면과 나머지 10개 기준 PNG, 글로벌/다른 화면·공통 UI/접근성 회귀 |
| UI error contract | **53 PASS** | ko/en 오류·인식/첨부 설정 계약 |
| catalog | **16 namespaces / 2457 keys PASS** | ko/en 누락·중복·placeholder 계약 |
| lint·typecheck·일반/static build | **PASS** | 실제 제품 코드·양쪽 배포 산출물 |
| frontend architecture | **PASS, 14 features, legacy edges 0** | feature 간 직접 업무 import 없음 |
| backend architecture/inventory | **PASS, 1364 modules / 5537 internal edges** | 기존 canonical 경계와 inventory 유지 |
| frontend design | **PASS, raw colors 1229 / 36 files / 18 surfaces / route gaps 0 / 23 screenshot calls** | 새 neutral 슬롯 LOCAL 등록, 기준 PNG 수 11과 기존 tolerance 유지 |

검사는 합성 World/owner/이미지·임시 DB와 비어 있는 로컬 포트만 썼다. Next 3330/fixture 3332, static 3331, image fixture 3351/3352, Linux 컨테이너 내부 3300/3301/3302를 사용했다. 브라우저 외부 통신은 차단하고 Linux visual은 `--network none`이었다. 실제 API 키·운영 데이터·실제 생성/인식 요청은 사용하지 않았다. fixture의 기존 `/auth/local/environment` bootstrap 보고와 Social/Media writes는 별도로 audit하여 숨기지 않는다.

최종 일반/static build는 순차적으로 수행했다. 같은 안정된 산출물을 읽는 Next/static 기능 검사만 별도 포트에서 실행했다. 개별 검사 프로그램의 `scripts/ci` 경로명은 CI workflow 실행을 뜻하지 않는다.

## 3. C01–C16 / T01–T21 대응

| 계약·검사 | 실제 근거 |
| --- | --- |
| C01 / T01 | 두 World 진입/identity 검사와 World 종류로 분기하지 않는 공통 WorldSocialFeed 연결 |
| C02 / T03 | 같은 게시글·viewport의 글로벌/World header·composer·행 geometry JSON, x/폭·font·line-height·반경·clamp 높이 비교 |
| C03–C04 / T04 | ko/en 실제 owner header, 글로벌 자율 캐릭터와 구분, 정확한 World 프로필 link와 click |
| C11 / T05 | 없는 owner의 기존 ensure, 권한 없는 World의 ensure 0, 조회 실패의 global fallback 0, 사진 없음의 이니셜 |
| C04·C13 / T06 | World A 응답 지연 후 B 유지, 실제 프로필 PATCH·복귀 후 header/composer 이름/handle/사진 함께 반영 |
| C05 / T07 | 공백 UI submit 비활성·maxlength·readOnly, 실제 API의 상한 포함 성공/초과·빈/누락 422 |
| C06 / T08 | 실제 제목/본문 payload와 단일 manual write, provider calls 0, 임시 DB의 실제 ledger/source 계약 |
| C07·C15 / T09·T21 | 실제 native chooser 1개·single file·취소, 사진은 button/게시는 submit, ko/en name·caption 없음·tooltip·48px·busy/focus/disabled |
| C08 / T10 | PNG/JPEG/WebP 원본 업로드 bytes/MIME·preview·authenticated URL·reload, 기존 backend media format/privacy 검사 |
| C07·C08 / T11 | 업로드 pending/실패·교체·제거·취소·draft 정리, 기본 picker와 abort/인식 코드 보존 |
| C12 / T12 | 실패의 입력/asset 유지·같은 idempotency key·중복 저장 1건, backend 실제 replay·atomic write 검사 |
| C12 / T13 | 실패 후 본문 변경은 새 key, 같은 선택 asset 유지·낡은 요청과 분리 |
| C02 / T14 | 같은 SocialPostRow의 제목/본문·clamp/더보기·공통 앵커, 기존 0/1/many media와 원본 pixels 회귀 |
| C13 / T15 | 상세 thread·답글·프로필 capability·letter CTA·정확한 World Chat·다섯 메뉴 기존 Next/static 회귀 |
| C16 / T16 | 최초·전환·게시 후 조회, 명시적 실패 retry, 사진+제목+본문 상태의 touch pull refresh, dirty link 취소, 완료 이미지 갱신·blob 정리와 기존 탐색 회귀 |
| C08 / T17 | 기존 image-integration의 Chat·reference 기본 picker·requireRecognition·실패/사진 제거·text recovery |
| C14 / T18 | ko/en 긴 owner, 360/390/436/480/768/960/1440 폭·200%·focus, 기존 timezone formatter/catalog 회귀 |
| C14 / T19 | 동일 23개 spec을 양쪽 config의 testMatch로 실제 수집·실행. Next/static 각각의 실제 route/media adapter |
| C09–C10·C16 / T02 | 정상 목록 DOM의 큰/작은 World 표시·header button·숨은 대체·필터 부재, 상세/다른 shell은 유지 |
| C14 / T20 | 아키텍처·inventory·design·정확한 frozen/append-only 보존. API/ORM/source 변경 없음 |

원본 corpus·기존 기능 assertion을 빼거나 테스트를 skip시키지 않았다. 기존 product-shell 두 spec과 image-integration spec에서 승인한 UI의 header/사진 trigger locator만 변경했다. 실제 payload·업로드·MIME/pixels·World 경계·idempotency·draft·blob 정리 검사는 유지한다.

## 4. 위치·시각 대조와 기준 변경

같은 글/사용자·시간대·viewport의 글로벌과 World를 비교했다. 좁은 390px에서 제목 x=20, 로고 x=171/48px, 우측 끝 x=370, 작성 아바타 x=20/52px, 본문 입력 x=88/282px·font 16/line 24/radius 18, 게시글 아바타 x=16/48px와 본문 x=76/298px가 일치했다. 480/768/960/1440 폭에서도 공통 x·폭·font·행 clamp 높이를 검사했다. 글로벌 desktop에서 기존 중앙/캐릭터 trigger가 숨겨지는 계약은 유지하고 World는 desktop에서도 사용자 프로필을 표시한다.

제목 줄은 World에 추가되며 두 글로벌 필터 행은 World에 없다. 이 차이에 따른 composer/첫 게시글의 절대 y는 같다고 주장하지 않는다. 본문은 글로벌의 실제 computed 16px에 맞췄다. 제출/업로드 중에도 두 action은 48px을 유지한다.

ko/en 각 7개 viewport 및 200% focus 캡처를 저장하고 개별 좁은/넓은/zoom 이미지와 Next/static contact sheet를 직접 검토했다. 긴 이름은 말줄임되고 로고/사용자 프로필/action이 겹치지 않는다. 가로 넘침 0·단일 scroll owner·화면 중앙 최대 960px 계약도 자동 검사했다.

Canonical은 Playwright 1.62.1, Ubuntu 24.04, Chromium 151.0.7922.34/revision 1234의 다음 고정 컨테이너에서 검증했다.

`mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`

- 수정한 PNG: `browser-tests/snapshots/ui-f/world-feed-composer-phone-436x880.png` 한 개.
- 이전 SHA256: `97c16d1cc23a59e97d4e35f5aa6829b501f96c9135b70a8fce5b9477dad8f9bf`.
- 이후 SHA256: `92cbf1e56575da0a09937ad620c4972747d31caeaafa9d85ae9f2e276d2446c0`.
- `--grep "persistent World composer" --project next-production --update-snapshots`로 대상 한 개만 갱신하고 실제 화면을 검토했다. 이후 업데이트 옵션 없이 전체 36개를 재통과했다.
- 나머지 10개 PNG·visual fixture·11개 snapshot 목록·maxDiffPixels 25·threshold 0.1은 유지했다. screenshot 호출 수 21→23은 새 로컬 responsive/focus capture 두 지점이며 기준 이미지 추가가 아니다.
- 현재 design baseline은 지원되는 `--write`로 승인 UI의 실제 hash를 반영한 후 `--check`를 통과했다. 고정 refactor baseline/checkpoint/path map/feature inventory 5개는 출발 HEAD와 같다.

## 5. 앞선 실패와 수정한 검증 조건

최초 fixture에서는 기존 환경 bootstrap POST를 Social write와 합쳐 세었고, 여러 heading의 위치를 한 번에 찾았으며, 저장 직후 사라지는 프로필 편집 안내를 기다렸다. 실제 결과·명확한 영역/주체를 검사하도록 고쳤다. static은 기존 canonical trailing slash까지 정확히 검사한다. 글로벌 geometry용 캐릭터는 실제 선택 가능한 fixture로 만들고 사용자와 비교할 때만 같은 프로필 데이터를 썼다.

기존 Next 회귀의 Memory 진행 검사에서는 검증용 config가 원래 `expect.timeout=10000`과 PWA service worker 허용을 이어받지 않아 실패했다. 원래 조건을 복원한 뒤 35 PASS/10 opt-in SKIP였다. Memory 제품 코드·기존 fixture·assertion·시간 상한을 변경하지 않았다.

기존 image-integration에는 World의 노출된 파일 input과 제거된 Device Home 헤더를 찾는 두 locator가 남아 있었다. 승인한 실제 사진 버튼과 중앙 로고의 홈 링크로 검사 대상을 바꾸고, 이전 실행을 중단 기록으로 남긴 뒤 전체 40개를 새로 실행했다. 단순히 테스트만 실패에서 제외하거나 보이지 않는 대체 UI를 만들지 않았다.

첫 canonical 검사 34 PASS/2 FAIL은 Next/static에서 같은 World 화면의 의도한 시각 차이였다. 해당 PNG 한 개만 검토·갱신한 후 전체 36 PASS였다. 모든 초기 실행은 최종 PASS와 구별한다.

## 6. 단계·증거·운영 경계

| 단계 | 기록 |
| --- | --- |
| P00 | clean branch/HEAD·watch 승인·격리 환경·글로벌 이전 geometry 확보 |
| P01–P04 | canonical 지침·neutral header·목록 shell·실제 owner/profile 연결 |
| P05–P09 | 필수 작성창·Media 표시 슬롯·공통 행·조회/재시도·다국어/접근성 |
| P10 | 지정 18개 + 추가 101개 임시 API/media 검사 PASS |
| P11 | Next/static 새 46개·기존 112개·image 40개 PASS, 기존 opt-in 10개는 별도 SKIP |
| P12 | 앵커와 반응형/zoom 직접 검토, 대상 한 개 canonical 갱신 뒤 36개 PASS |
| P13 | 정적 경계·design/catalog/error·lint/type·inventory·두 build PASS; 최종 exact preservation은 P16에서 확정 |
| P14 | 이 문서·C/T 대응표·실패 원인·증거 범위 저장 |
| P15–P17 | 구현 커밋·append-only 증거·최종 상태·사용자 확인 인계를 후속 기록으로 확정 |

재현에 사용하는 추적 파일은 `browser-tests/world-feed-fixture.ts`, `world-feed-ui.spec.ts`, `playwright.world-feed-ui.config.ts`, `playwright.world-feed-ui-static.config.ts`다. 제품 저장소에서 일반 build 후 `pnpm --dir browser-tests exec playwright test --config playwright.world-feed-ui.config.ts`, static build 후 같은 명령의 static config를 실행한다. backend 지정 검사는 backend cwd에서 `uv run python -m pytest tests/social/test_l3_owner_manual_social_inbox.py tests/social/test_source_write_ownership.py tests/social/test_world_feed_search.py tests/memory/test_episode_social_sources.py`로 실행했다.

기존 회귀의 로컬 config는 원래 spec/testMatch·45/60초 test·10/15초 expect·service worker 조건을 유지하면서 production build·합성 SSR fixture·분리 port로 실행했다. Linux visual은 task-owned staging의 compiled build와 동일 버전 dependency를 사용했고 사용자 named volume을 연결하지 않았다.

원자료는 `D:/project_code/angmoo-workspace/angmoo-tree-angmoo/artifacts/world-feed-ui-20261004`와 그 아래 `20261004T131329Z`, `next`, `static`, `linux-visual`에 보존한다. artifacts는 기존 ignore 대상이므로 다른 clone에는 없다. 이 문서의 결과/조건/명령·추적 fixture·승인 canonical PNG가 저장소의 재현 가능한 요약이다.

사용자가 관찰 서버 유지·frontend watch 자동 반영을 승인했다. 실행 컨테이너 `/app/src`의 header/Social/Media 주요 파일 3개가 로컬 SHA256과 같고 frontend/backend 모두 기존 2026-10-04T11:56–11:57Z 시작 시각으로 healthy였다. 사용자 3000 서버는 유지했다. 운영 서버 재빌드/재시작·사용자 DB의 테스트 글/사진 생성·볼륨/키 변경은 하지 않았다. 개발 소스 동기화 확인을 운영 데이터 기반 end-to-end PASS 또는 설치판 적용으로 표현하지 않는다.

직접 **USER CHECK**, 설치판 빌드/교체/실행, 실제 API·자연 활동 관찰 품질은 **NOT_RUN**이다. 사용자는 현재 브라우저에서 기본 SNS/생성 World의 Feed를 열어 오른쪽 사용자 사진→내 프로필, 제목+본문, 왼쪽 사진/오른쪽 게시 버튼과 실제 게시글 표시를 확인할 수 있다. 일반 reload/HMR의 draft 영구 보존은 약속하지 않는다.
