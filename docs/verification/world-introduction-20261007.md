# World 소개 화면 적용 및 검증 — 2026-10-07

## 범위와 작업 경계

계획: 워크스페이스의 `docs/plan/10-07 World 소개 탭 명칭과 배너·캐릭터 배치 UI 제안서.md`.
사용자가 업로드한 배너 우선형 목업을 **LOCAL** 디자인 참고로 사용했다.
제품 저장소는 `angmoo-tree-angmoo`, 작업 브랜치는 `feat/0.1.0-release-readiness`다.
시작 HEAD는 `a1a68fc9`이고 작업 시작 시 미커밋 변경은 없었다.

로컬 구현·빌드·회귀 검사·로컬 Docker 프론트엔드 반영·로컬 커밋만 수행한다.
PR 생성, push, 원격 CI 및 main 병합은 수행하지 않는다. 경로에 `scripts/ci`가 있는
검사는 저장소 규칙이 요구하는 로컬 검사이며 원격 파이프라인 실행과 구분한다.

## 적용 결과와 구현 소유권

| 단계 | 적용 내용 | 상태 |
| --- | --- | --- |
| W01 | 배너 우선형, 공통 도시 그림, 원형 홈 아이콘, 장르·분위기 태그, 펼친 소개 기준을 적용한다. World 루트가 기본 진입 화면인 계약을 유지한다. | 구현 완료 |
| W02 | 기존 World 상세 읽기와 공개 프로필 읽기를 재사용한다. 미디어는 기존 URL 검증·런타임 인증 경로를 사용하고 원문·목록 순서를 유지한다. | 구현 완료 |
| W03 | 배너 → 이름 → 장르·분위기 태그 → 한 줄 소개 → 소개 → 캐릭터 → 내 프로필 순서의 공통 화면을 조립한다. | 구현 완료 |
| W04 | 표시 명칭은 ko/en 모두 World다. 내부 `home` ID·루트 URL은 유지한다. 정상 소개의 중복 제목·OWNER·실행 가능 배지·기술 경계 안내를 제거하고 실제 차단·복구 동선은 유지한다. | 구현 완료 |
| W05 | 반응형·접근성·정적 앱·회귀 검사 및 실제 Docker 화면을 확인한다. | 검증 완료; 직접 사용자 확인 별도 |

Worlds 기능은 `world-introduction.tsx`에서 상세 읽기, 정의 표시, 태그, 배너 및
소개 펼침을 소유한다. Characters 기능은 `world-character-preview.tsx`에서
공개 프로필 읽기와 자율 캐릭터 미리보기를 소유한다. 상위 composition은
캐릭터·내 프로필 슬롯을 공급한다. 기능끼리 구현 파일을 직접 참조하거나
퇴역한 public/shared 계층을 복원하지 않았다.

`GET /api/v1/worlds/:id`와 `GET /api/v1/worlds/:id/world-characters`의 기존
권한·DTO를 사용한다. 백엔드·스키마·저장 계약을 변경하지 않는다. World ID와
표시 필드의 응답 검증, AbortController 및 기존 인증 요청 범위를 사용한다.
World·세션·런타임 변경 시 이전 화면의 읽기를 폐기한다. 현재 범위를 벗어난
읽기나 취소된 진입으로 프로필 생성이 시작되지 않는 기존 경계도 유지한다.

기본 배너는 업로드한 목업의 하늘·해·도시 형태를 벡터로 옮긴
`frontend/public/world-default-banner.svg`다. 등록되지 않았거나 이미지 표시가
실패하면 같은 높이에 표시한다. 새 미디어 ID·DB 쓰기·AI 생성을 만들지 않는다.
정적 앱의 기존 자산 복사 목록에도 SVG를 추가했다. 그림의 색상은 SVG 내부의
팔레트이며 제품 CSS는 기존 의미 토큰만 사용한다.

태그는 저장된 장르 전체, 분위기 전체 순서이고 철자·대소문자를 변경하지 않는다.
둘 중 하나만 있으면 그 그룹만 표시하고 모두 없으면 행을 생략한다.
소개 원문은 기본 4줄로 표시하고, 한 번의 펼침으로 전체 설명 → 작은 일상 제목·본문 →
장소 → 역할·직업 → 추가 생성 지침을 보여준다. 원문·줄바꿈·목록 순서를 유지한다.
빈 상세 설정은 ko/en 안내로 표시하고 조회 오류를 빈 데이터로 처리하지 않는다.

미리보기는 서버가 허용한 공개 프로필 중 `control_mode=autonomous`만 표시한다.
사진은 모바일 72px, 넓은 화면 80px이고 이름은 두 줄까지 표시한다.
전체 이름은 링크의 접근성 이름에 남는다. 모바일에는 다음 사진 일부가 보이며
가로 스크롤과 키보드 탐색을 지원한다. 전체 보기·각 프로필·내 프로필 링크는
현재 World의 기존 경로다. 사용자 조종 프로필은 작은 별도 내 프로필 링크로 연결한다.
현행 목록 API는 전체 목록이며 페이지 길이를 전체 인원으로 추정하거나 표시하지 않는다.

## 로컬 검증

최종 소스에서 확인한 결과:

| 검사 | 결과 |
| --- | --- |
| 프런트엔드 아키텍처 경계 | 통과 — features 14, legacy exact edges 0 |
| 프런트엔드 디자인 계약 | 통과 — raw colors 1,167 / 35파일, surfaces 18, route gaps 0, 기존 screenshots 41 |
| ESLint / TypeScript | 모두 통과 |
| 한국어·영어 문구 카탈로그 | 통과 — 16 namespaces, 2,642 source keys; key/params/plural parity |
| 정적 앱 빌드 | 통과 — 기본 SVG도 `frontend/out/world-default-banner.svg`에 포함 |
| 소개 화면·기존 World 탐색 브라우저 회귀 | **32개 통과** — Next 17개, 정적 앱 15개; skipped / unexpected / flaky 모두 0 |
| 기존 World shell / 채팅 구조 계약 | **7개 통과** |
| Git whitespace | `git diff --check` 통과 |

최종 브라우저 보고서는 `artifacts/world-introduction-20261007/final-results.json`이며
해당 실행의 첨부 파일은 `artifacts/world-introduction-20261007/final/`에 있다.
초기 실패·중단 실행을 최종 통과 결과에 합산하지 않는다. 테스트를 위해 연
3338/3339 프리뷰는 검사 후 종료했고 두 포트의 Listen 연결이 0개인 것을 확인했다.

필수 검사와 구조 회귀:

```powershell
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build:static
uv run --project backend python -m pytest backend/tests/test_l2_5_world_app_shell_contract.py backend/tests/test_p8_l_d_frontend_world_chat_structure.py -q
```

브라우저 검사는 합성 fixture로 실행한다. 환경 초기화 요청은 기능 쓰기와 별도로
기록하고, 소개·배너 표시의 World/media 쓰기와 제공사 호출이 없음을 검사한다.
프로필 편집 회귀는 fixture 내부에서만 PATCH를 실행한다.

```powershell
# 제품 저장소에서 실행. 별도 터미널 두 개로 프리뷰를 시작한다.
pnpm --dir frontend dev --hostname 127.0.0.1 --port 3338
pnpm --dir frontend preview:static --port 3339

# 프리뷰가 준비된 다음 실행한다.
$env:ANGMOO_INTRO_STATIC_URL = 'http://127.0.0.1:3339'
$env:ANGMOO_INTRO_RUN = 'final'
pnpm --dir browser-tests exec playwright test --config playwright.world-introduction.config.ts --grep 'World introduction|genre and mood|short introduction|character preview|World detail|delayed definition|revoked .* scope|World App keeps|World entry creates|profile edit and return|detail and other World'
```

Next 전용 기존 product-shell fixture 두 개는 Next에서만 실행한다.
공통 새 소개 검사와 기존 피드·탐색 회귀는 Next와 정적 앱에서 실행한다.
다음 동작을 검사한다.

- ko/en 제목·탐색·접근성 이름과 저장 원문·태그의 순서.
- 320/390/480/960px에서 본문 가로 넘침 없음, 태그 배치, 사진 크기,
  다음 사진 일부 노출, 별도 소개 세로 스크롤 없음.
- 배너 없음·등록됨·표시 실패의 같은 높이와 실제 이미지 로드 완료.
- 짧은 설명·긴 설명·빈 상세 설정의 펼침 규칙과 원문·제목 계층·접기.
- 자율 캐릭터 0명·21명·403·범위가 다른 응답·재시도·전체 이름·키보드 가로 탐색.
- World 상세 403·잘못된 ID에서 정의와 목록을 노출하지 않음.
- 늦은 World/캐릭터 읽기와 세션·런타임 변경 시 이전 데이터가 새 범위에 남지 않음.
- 기존 World 경계, 승인된 프로필 생성, 프로필 편집 후 피드 복귀,
  World 소개에만 shell 헤더가 남는 탐색 구조.

초기 검사에서 발견한 항목은 정식 경로로 수정했다. Next 생성 타입 파일은
`next dev`가 다시 생성하도록 했고 타입 검사에서 제외하지 않았다.
기존 피드 fixture의 관리 GET/PATCH·revision 및 프로필 편집 Dialog·게시글 제목
검사를 현행 UI/API 계약에 맞췄다. 정적 링크의 trailing slash와 동일 출처 절대
이미지 URL은 기존 라우터 표현으로 검증하되 World·캐릭터 경로를 정확히 검사한다.
기본 그림은 URL 존재만 확인하지 않고 실제 로드를 검사하여 자산 복사 누락을 방지한다.

디자인 기준의 수치·허용치를 늘리지 않았다. `frontend-design-baseline.json`은
의도한 파일 변경의 해시만 갱신했다. 확인 시 raw color 1,167개/35파일,
18 surfaces, route gaps 0, 기존 screenshot inventory 41개였다.

## 실제 로컬 Docker 화면

프론트엔드만 일반 Compose 절차로 반영했다.

```powershell
docker compose -f compose.yml -f compose.dev.yml build frontend
docker compose -f compose.yml -f compose.dev.yml up -d --no-deps --no-build --wait --wait-timeout 120 frontend
```

확인 URL: `http://127.0.0.1:3000/worlds/01a0dfcc-4629-7640-8ac0-fc6bc166bb53`.
실제 SNS 제목 아래에는 장르 `modern`, `social`, 분위기 `everyday`, `warm`이
저장 순서대로 표시되었다. 기본 배너, 실제 캐릭터 7명의 사진·이름,
전체 보기·내 프로필 경로, 펼친 소개의 제목 순서를 확인했다.
최종 기본 창(825×764)과 390×844 모바일 배치도 확인하고 임시 viewport를 복원했다.
390px에서는 캐릭터 목록 너비 350px 안에 세 사진과 다음 사진 일부가 보였고,
가로 스크롤 가능한 전체 목록 너비는 720px였다. 본문 전체에는 가로 넘침이 없었다.

화면 증거는 로컬 `artifacts/world-introduction-20261007/`의
`docker-world-introduction-top.jpg`, `docker-world-introduction-characters.jpg`,
`docker-world-introduction-390.jpg`, `docker-world-introduction-390-characters.jpg`다.
모두 최종 Docker 프론트엔드 반영 후 다시 촬영했다. artifacts는 커밋 대상과 분리한다.

백엔드 컨테이너 ID
`0c97596118085c3f9755c2575cb22fb9bb4e8d33e6d95f64fce09959f2a79cfc`와
시작 시각 `2026-10-07T06:45:02.724679492Z`가 적용 전후에 동일한 것을 확인했다.
최종 프론트엔드 컨테이너 ID는
`78460b8ce9b4e60cc298bf0869d34e363ee531345cd3ad8a387bada738297def`,
시작 시각은 `2026-10-07T11:59:14.316143255Z`이며 두 컨테이너 모두 `healthy`였다.
DB·API 키·볼륨 초기화나 백엔드 재시작을 하지 않았다. 이번 UI 검증에서 실제
AI 요청·활동 실행·기억 정리를 시작하지 않았다. 기존 자율 활동은 그대로 동작하며,
그 백그라운드 활동의 제공사 호출 여부를 이번 UI 검증의 결과로 판단하지 않는다.

## 확인하지 않은 범위

실제 AI 품질·이미지 생성/인식·기억 정리·설치된 Windows 앱의 물리적 실행은
이번 UI 변경의 검증 범위가 아니다. 정적 앱의 브라우저 검증은 설치된 Tauri 앱의
실행 검증과 구분한다. 직접 사용자 화면 확인은 사용자 확인으로 남긴다.
원격 CI·PR·push·main 병합은 수행하지 않는다.
