# World 캐릭터 상태 카드 재사용 수정 및 검증 — 2026-10-07

## 작업 범위와 기준

현재 로컬 브랜치 `feat/0.1.0-release-readiness`의 시작 HEAD는 `a3eb7a72`였고, 작업 전 제품 저장소의 변경 사항은 없었다. 사용자가 제공한 Device 캐릭터 상태/최근 활동 사진과 World 설정 탭의 좌우 여백을 기준으로 World 상태 탭을 수정했다. 원격 push, PR 생성, 원격 CI 실행, main 병합은 수행하지 않았다.

- **ADAPTED**: 기존 `agent-detail-parts.tsx`의 아바타·상태 배지·핸들·이름·설명·최근/다음 활동 카드와 568px 내부 스크롤 최근 활동 카드의 배치. `agent-activity-list.tsx`의 아이콘·활동 종류·시간·제목·설명·관련 글 버튼과 구분선.
- **LOCAL**: World의 프로필, 실제 활동 상태, 권한, revision, 조회 취소/인증 범위, 원문 활동 제목, World 게시글 경로. Device의 데이터나 API 응답을 World 응답처럼 만들어 사용하지 않는다.
- frontend `ARCHITECTURE.md`, `DESIGN.md`, 설계 참조/제품 shell/기능 보존 문서와 해당 Next CSS 가이드를 기준으로 공통 표시와 Characters 기능의 데이터 연결을 분리했다.

## 구현 결과

1. 제품 중립적인 `CurrentStateStatusCard`, `RecentActivityStatusCard`, `ActivityTimeline`을 canonical `components/ui`와 `components/content`에 분리했다. Device와 World가 같은 표시 컴포넌트를 사용한다. 공통 컴포넌트에는 World/API/권한 타입과 분기 로직을 넣지 않았다.
2. World 상태 카드에는 기존 관리 응답의 이름·아바타·핸들·소개와 해당 World 상태 응답의 실제 상태 및 최근/다음 활동 시간을 연결한다. 자율활동 ON을 실행 중으로 단정하지 않으며 OFF/시간 대기/실행 오류 등 기존 상태 의미를 유지한다.
3. 최근 활동의 전체 카드 높이는 목록 길이에 따라 무한히 늘어나지 않는다. 목록만 최대 568px에서 스크롤하며 표시 시간대 행은 내부 상단에 유지된다. 최초 최대 10개를 표시하고 끝에 가까워지면 기존 incremental hook으로 5개씩 추가한다. 카드 안에서 스크롤할 때 외부 화면으로 스크롤이 전달되지 않으며, 탭 이동 후에도 기존 DOM과 스크롤 위치를 유지한다.
4. 성공한 게시글·답글·좋아요는 기존 Device의 표현과 아이콘을 사용한다. 실패/보류는 성공으로 표시하지 않으며 기존 원문 활동 제목을 보존한다. 게시글 링크는 해당 World의 경로를 사용한다.
5. 상태 탭의 네 카드 모두 설정 탭과 같은 좌우 여백을 갖는다. 모바일 16px, 768px 이상에서 36px이며 위쪽 여백은 24px이다. `이 World에서만 적용되는 활동 상태예요.` 안내를 제거했다.
6. 페르소나의 캐릭터 설명 우선 배치와 필드 내부 스크롤, 활동 요약의 실제 수치 및 답글/게시글/좋아요만 표시하는 계약을 유지한다. 활동 요약 우측에는 활동/휴식 시간대 라벨과 실제 시간 범위를 표시한다.
7. UI 문구는 기존 ko/en Characters 카탈로그를 함께 사용한다. 사용자 원문과 페르소나는 번역하거나 수정하지 않는다. API, 백엔드, 스키마, 스케줄러 및 키 저장 계약 변경은 없다.

## 로컬 검증

| 검증 | 결과 | 확인 내용 |
| --- | --- | --- |
| frontend architecture boundaries | PASS | 공통 표시/기능 데이터 소유권 경계 |
| frontend design contract | PASS | raw-color 1183→1167, 35개 파일; 기존 색상 기준을 늘리지 않고 16개 제거 |
| frontend lint | PASS | ESLint |
| frontend typecheck | PASS | TypeScript |
| UI catalog | PASS | 16 namespaces, 2617 source keys; ko/en 키·변수·복수형 일치 |
| Next production build | PASS | 격리된 `.next-status-reuse-production` 출력으로 빌드; 화면 기능 검증과 구분 |
| static build | PASS | 동일 기능 컴포넌트를 사용하는 static shell export |
| Next/static 브라우저 회귀 | **18/18 PASS** | ko/en, 390/960px, 실제 프로필·시간·World 링크, 20개 활동의 내부 스크롤, 바깥 스크롤 보존, 탭 이동 후 위치, 설명 우선, 지원 행동, sticky header, OFF/빈 목록/403 후 재시도, 기존 Device 카드/링크 보존 |

브라우저 검증은 사용자 서버와 분리한 Next dev `127.0.0.1:3338`과 static `127.0.0.1:3339`, 합성 API fixtures로 실행했다. 실제 AI 호출을 수행하는 검증이 아니며 테스트의 provider call과 설정 mutation 기록은 빈 배열이다. Next production 실행 화면이나 설치된 Tauri의 USER CHECK로 간주하지 않는다.

```powershell
$env:ANGMOO_STATUS_STATIC_URL = 'http://127.0.0.1:3339'
$env:ANGMOO_STATUS_RUN = 'verified-next-static'
pnpm --dir browser-tests exec playwright test --config=playwright.world-character-status.config.ts --grep 'Status cards|World status'
```

결과는 ignored `artifacts/world-character-status-20261007/verified-next-static-results.json`과 `browser/`에 있다. 신규 진단 캡처 지점 1개를 반영해 screenshot inventory는 40→41로 갱신했다. 기존 canonical PNG 11개와 허용 오차를 바꾸지 않았다. 생성 과정에서 Next가 임시 출력 경로를 넣은 `tsconfig.json`은 원래 내용으로 정리했으며 제품 설정 변경으로 남기지 않는다.

## 실행 중인 Docker 화면 반영 및 확인

정상적인 Compose frontend build와 `up -d --no-deps --no-build frontend`로 프론트엔드만 교체했다. 백엔드 컨테이너 ID `0c97596118085c3f9755c2575cb22fb9bb4e8d33e6d95f64fce09959f2a79cfc`와 시작 시각 `2026-10-07T06:45:02.724679492Z`가 전후 동일하며, 교체 후 두 컨테이너 모두 healthy다. 백엔드를 재시작하지 않았고 데이터 볼륨을 삭제·재생성하지 않았다.

사용자 지정 Elias Finch의 World 상태 URL에서 직접 새로고침하여 아바타 상태 카드와 최근 활동을 확인했다. 실제 목록의 측정값은 `clientHeight=568`, `scrollHeight=1924`, `overflowY=auto`, `scrollbarGutter=stable`, 최초 표시 10개였으며 상태 탭 네 카드 모두 좌우 inset이 36px였다. 이는 해당 시점 Docker 화면의 확인이며 실제 AI 활동 품질 판정이나 사용자 직접 확인 완료를 의미하지 않는다.
