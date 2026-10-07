# World 상태·관계망 카드 그림자 적용 검증

- 날짜: 2026-10-07
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 로컬 브랜치: `feat/0.1.0-release-readiness`
- 작업 시작 HEAD: `20a2ef63` (`style(ui): unify settings and creation card elevation`)
- 참조 분류: **LOCAL**. 기존 현재 상태·최근 활동 카드의 공통 Card 및 `--shadow-summary`를 재사용한다.
- 범위: World 상태의 페르소나·활동 요약과 관계망의 바깥 카드 표시.
- 로컬 구현·검증·커밋만 수행한다. push, PR 생성, 원격 CI, main 병합은 수행하지 않는다.

## 구현과 보존 범위

1. 공통 `PersonaStatusCard`와 `ActivitySummaryStatusCard`에 선택적 `elevated` 표시 속성을 추가한다. 기본값은 `false`이며 World 상태의 호출자가 명시적으로 선택한다. 다른 소비 화면의 기본 스타일을 바꾸지 않고 공통 계층에는 기능·권한 판단을 넣지 않는다.
2. 관계망의 World 관계망·하루 관계 정리·방향 관계 지도·접근 가능한 관계 목록·최근 검증된 사건 근거 SettingsCard에서 같은 옵션을 선택한다. 사건 근거 카드는 기존처럼 실제 근거가 있을 때 표시한다.
3. 그림자는 기존 토큰 `--shadow-summary: 0 10px 28px rgb(16 24 40 / 8%)`를 사용한다. 화면별 CSS 복제나 새 색상·자산·의존성을 추가하지 않는다.
4. 카드 순서와 여백, 내부 페르소나/최근 활동 스크롤, 활동 수치와 지원 행동, 그래프의 노드/방향/이름 배치, 관계 설명 펼치기 및 링크를 유지한다. 내부 정보 칸과 관계 목록 행은 기존 평면 스타일을 유지한다.
5. Next와 정적 shell이 같은 기능 컴포넌트를 사용한다. 텍스트와 ko/en 카탈로그, 백엔드·API·스키마·데이터·키·모델·예약 계약은 수정하지 않는다.

## 로컬 자동 검증

| 검증 | 결과 | 범위 |
| --- | --- | --- |
| Frontend architecture boundaries | PASS | 14 features, legacy exact edges 0 |
| Frontend design contract | PASS | raw-color 1167, 35 files, 18 surfaces, route gaps 0, screenshot inventory 41 |
| Frontend lint / typecheck | PASS | ESLint / TypeScript |
| Static production build | PASS | 공통 기능 컴포넌트를 사용하는 정적 shell export |
| 상태 화면 / Next | 9/9 PASS | ko/en, 390/960px, 내부 스크롤, OFF·오류·권한·재시도, Device 소비자, 설명 우선·지원 행동·고정 헤더 |
| 상태 화면 / 정적 앱 | 9/9 PASS | 같은 상태 회귀 |
| 관계망 / Next | 9/9 PASS | 준비·빈 상태·제한·사용 불가·실패 구분과 재시도, 200% 읽기/키보드 펼치기, ko/en 1·7·20 노드 |
| 관계망 / 정적 앱 | 9/9 PASS | 같은 관계망 회귀 |

브라우저 회귀 총 **36/36 PASS**. JSON 결과의 unexpected, flaky, skipped는 각각 0이다. 관계망 배치 회귀는 390·480·960·1440px 및 100%/200% 글자 크기에서 긴 이름, 노드 겹침·화면 밖 배치·방향·가로 넘침을 검사한다. 사용자 Docker와 별도의 Next dev `127.0.0.1:3338`, 정적 preview `127.0.0.1:3339` 및 합성 API fixture로 실행했다. 이 회귀는 실제 AI 품질이나 설치된 Tauri USER CHECK를 대신하지 않는다.

필수 명령은 `uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py`, `uv run --project backend python scripts/ci/check_frontend_design_contract.py --check`, `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend build:static`이다.

```powershell
# Next 상태: 9개
$env:ANGMOO_STATUS_RUN = 'status-relationship-elevation-next'
pnpm --dir browser-tests exec playwright test --config=playwright.world-character-status.config.ts --project=next-preview --grep 'Status cards|World status'

# Next 관계망: 9개
$env:ANGMOO_BROWSER_RUN = 'status-relationship-elevation-graph-next'
$env:ANGMOO_GRAPH_STATIC = '0'
pnpm --dir browser-tests exec playwright test --config=playwright.world-memory-integration.config.ts --project=next-preview --grep 'Relationship map|UI-E Relationship Graph|RI relationship labels' --output ../artifacts/status-and-relationship-elevation-20261007/next-graph

# 정적 상태: 9개
$env:ANGMOO_STATUS_RUN = 'status-relationship-elevation-static'
$env:ANGMOO_STATUS_STATIC_URL = 'http://127.0.0.1:3339'
pnpm --dir browser-tests exec playwright test --config=playwright.world-character-status.config.ts --project=static-export --grep 'Status cards|World status' --output ../artifacts/status-and-relationship-elevation-20261007/static-status

# 정적 관계망: 9개
$env:ANGMOO_BROWSER_RUN = 'status-relationship-elevation-graph-static'
$env:ANGMOO_GRAPH_STATIC = '1'
$env:ANGMOO_INTEGRATION_STATIC_URL = 'http://127.0.0.1:3339'
pnpm --dir browser-tests exec playwright test --config=playwright.world-memory-integration.config.ts --project=static-export --grep 'Relationship map|UI-E Relationship Graph|RI relationship labels' --output ../artifacts/status-and-relationship-elevation-20261007/static-graph
```

Ignored 결과 JSON은 `artifacts/world-character-status-20261007/status-relationship-elevation-{next,static}-results.json`과 `artifacts/world-memory-integration-20261006/status-relationship-elevation-graph-{next,static}-results.json`에 있다. 기존 screenshot inventory, canonical PNG 11개와 허용 오차는 유지한다. 디자인 기준 파일에서는 변경한 관계망 표시 소스의 해시 하나만 다시 계산했다.

## 현재 Docker 화면 확인

프론트엔드에 정상적인 Compose 절차를 적용했다.

```powershell
docker compose -f compose.yml -f compose.dev.yml build frontend
docker compose -f compose.yml -f compose.dev.yml up -d --no-deps --no-build --wait --wait-timeout 120 frontend
```

- backend ID: `0c97596118085c3f9755c2575cb22fb9bb4e8d33e6d95f64fce09959f2a79cfc`
- backend StartedAt: `2026-10-07T06:45:02.724679492Z` — 반영 전후 동일, healthy
- 반영된 frontend ID: `c7f1f35bb88659f2713217bb796a4cd159281e7427ef6d80bd438d44cf773545`
- frontend StartedAt: `2026-10-07T11:01:11.309434753Z` — healthy

사용자가 지정한 Red의 World 상태 URL과 Red의 관계망 URL을 브라우저로 열어 DOM의 계산된 CSS와 실제 화면을 확인했다. 페르소나·활동 요약 2개 카드 및 현재 표시된 관계망 4개 카드 모두 `rgba(16, 24, 40, 0.08) 0px 10px 28px 0px` 그림자를 사용한다. 관계망의 카드 간격은 24px이다. 내부 페르소나 칸·활동 수치 칸·관계 목록 행의 그림자는 `none`으로 유지된다.

현재 관계망 응답에는 사건 근거 카드가 표시되지 않는다. 이 조건부 카드에도 동일한 `elevated` 연결을 구현했으며, 현재 Docker 화면에 해당 카드가 표시됐다고 주장하지 않는다. 실제 화면 확인에서는 저장·정리·AI 실행을 요청하지 않았다. 프론트엔드만 재생성했으며 백엔드와 데이터 볼륨을 보존했다.
