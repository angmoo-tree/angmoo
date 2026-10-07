# 설정·기억·생성 카드의 공통 그림자와 여백 적용 검증

- 날짜: 2026-10-07
- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 로컬 브랜치: `feat/0.1.0-release-readiness`
- 작업 시작 HEAD: `c0ff5011` (`fix(characters): reuse status cards in World views`)
- 범위: World 캐릭터 설정, 전체 설정, 기억의 세 설정 카드, 캐릭터 생성, World 생성의 표시 스타일
- 참조 분류: **LOCAL**. 현재 상태 카드가 사용하는 공통 Card와 `--shadow-summary`를 재사용한다. 새로운 hosted 소스나 자산을 도입하지 않는다.
- 로컬 구현·검증·커밋만 수행한다. push, PR, 원격 CI, main 병합은 수행하지 않는다.

## 구현 내용

1. 공통 `SettingsCard`에 선택적인 `elevated` 표시 속성을 추가하고 기존 `Card`에 전달한다. 기본값은 `false`로 유지하고 해당 화면에서 명시적으로 선택한다. 이 공통 속성은 API·World·권한·활동 상태를 판단하지 않는다.
2. World 캐릭터 설정의 10개 카드에 동일한 그림자를 적용한다. 여러 화면이 사용하는 관심 주제·활동 방식·오늘 계획 컴포넌트는 선택적 표시 속성으로 연결하며 World 설정의 호출자가 선택한다. 기존 좌우 여백과 카드 순서를 유지한다.
3. 전체 설정의 화면 언어·설치/세션·삭제 범위 카드에 그림자를 적용한다. 카드 간격은 24px, 좌우 여백은 768px 미만에서 16px, 그 이상에서 36px이다.
4. 기억 사용 상태·기억/관계 정리·의미 검색을 여백을 소유하는 표시 묶음에 넣는다. 카드 간격은 24px, 좌우 여백은 768px 미만에서 16px, 그 이상에서 36px이다. 기존 기억 목록·상세·예약·키·모델·수동 정리·검색 자료 준비 조작을 유지한다. 저장 성공/실패 안내도 같은 묶음 안에 유지한다.
5. 캐릭터 생성의 다섯 단계가 사용하는 SettingsCard와 만드는 방법 선택 카드에 같은 그림자를 적용한다. 단계 순서, 필드, 초안, 등록, 프로필 자르기·업로드 동작은 유지한다.
6. World 생성의 머리 카드, 세계관·운영 기본값·상세 설정·아이콘/배너 패널, 공개 준비와 저장/공개 조작 카드가 같은 그림자 토큰을 사용한다. 기존 반응형 열 배치, 필드와 저장/공개 계약을 유지한다.

그림자는 기존 `--shadow-summary: 0 10px 28px rgb(16 24 40 / 8%)`를 그대로 사용한다. 텍스트와 ko/en 카탈로그, 백엔드·API·스키마·스케줄러·키 저장 계약은 수정하지 않는다. Next와 정적 앱은 같은 기능 컴포넌트를 사용한다.

## 로컬 자동 검증

| 검증 | 결과 | 범위 |
| --- | --- | --- |
| Frontend architecture boundaries | PASS | 14 features, legacy exact edges 0 |
| Frontend design contract | PASS | raw-color 1167, 35 files, 18 surfaces, route gaps 0, screenshot inventory 41 |
| Frontend lint | PASS | ESLint |
| Frontend typecheck | PASS | TypeScript |
| UI catalog | PASS | 16 namespaces, 2617 source keys; ko/en 키·변수·복수형 일치 |
| Static production build | PASS | 동일 기능 컴포넌트를 사용하는 정적 shell export |
| Next 브라우저 회귀 | 15/15 PASS | ko/en World 설정 10개 카드의 독립 저장과 입력 보존, 기억 오류/복구 문구, 360/390/436/1440px 생성, 영어 다섯 단계, 아바타·배너 자르기/취소/초안 재개, 중첩 화면 main landmark |
| 정적 앱 브라우저 회귀 | 14/14 PASS | 같은 World 설정·기억·캐릭터 생성 검증 |
| 전체 설정 브라우저 회귀 | 2/2 PASS | 설치/세션 정보 표시, 미지원 삭제 조작 비노출, 읽기 실패 시 기존 fail-closed 상태 |

브라우저 회귀 총 **31/31 PASS**이며 최종 실행의 flaky/failed는 0이다. 사용자 Docker와 별도인 Next dev `127.0.0.1:3338` 및 정적 preview `127.0.0.1:3339`에서 합성 API fixture로 실행했다. 실제 AI 실행을 요청하는 검증은 수행하지 않았다. 독립적인 Next production 실행 화면이나 설치된 Tauri USER CHECK 완료를 의미하지 않는다.

정적 생성 fixture는 별도 환경 변수 `ANGMOO_CREATOR_STATIC=1`을 요구한다. 첫 정적 실행에서 이를 빠뜨려 생성 화면의 fixture 경로가 맞지 않았으며 그 실행을 중단했다. 제품 코드나 검증 기준을 바꾸지 않고 아래 실행 설정을 맞춘 최종 실행에서 14개 모두 통과했다.

```powershell
# Next: 15 cases
$env:ANGMOO_BROWSER_RUN = 'card-elevation-next'
$env:ANGMOO_CREATOR_STATIC = '0'
pnpm --dir browser-tests exec playwright test --config=playwright.world-memory-integration.config.ts --project=next-preview --grep 'World ten cards|I41: Memory recovery|keyless registration|English five-step creation|Profile avatar|Next nested product pages'

# Static: 14 cases
$env:ANGMOO_BROWSER_RUN = 'card-elevation-static'
$env:ANGMOO_INTEGRATION_STATIC_URL = 'http://127.0.0.1:3339'
$env:ANGMOO_CREATOR_STATIC = '1'
pnpm --dir browser-tests exec playwright test --config=playwright.world-memory-integration.config.ts --project=static-export --grep 'World ten cards|I41: Memory recovery|keyless registration|English five-step creation|Profile avatar'

# Global Settings: 2 cases
$env:ANGMOO_UI_E_SETTINGS_BASE_URL = 'http://127.0.0.1:3338'
pnpm --dir browser-tests exec playwright test --config=playwright.ui-e-local-settings.config.ts
```

최종 Next/static 결과는 ignored `artifacts/world-memory-integration-20261006/card-elevation-next-results.json`, `card-elevation-static-results.json`에 있다. 기존 screenshot inventory와 canonical PNG 11개, 허용 오차는 수정하지 않았다. 디자인 기준 파일은 변경된 표시 소스의 해시만 다시 계산했다.

## 실행 중인 Docker 화면 확인

Compose의 정상적인 `build frontend`와 `up -d --no-deps --no-build frontend`로 프론트엔드만 반영했다. 전후 백엔드 컨테이너 ID와 시작 시각은 동일하다.

- backend ID: `0c97596118085c3f9755c2575cb22fb9bb4e8d33e6d95f64fce09959f2a79cfc`
- backend StartedAt: `2026-10-07T06:45:02.724679492Z`
- 반영된 frontend ID: `910b2abee87f83342398a59730d1af280108511558c463cb5abafbc532b22036`
- frontend StartedAt: `2026-10-07T09:26:33.188319439Z`
- 두 컨테이너 모두 healthy

사용자가 지정한 Elias Finch World 설정 URL 및 전체 설정, Elias Finch 범위의 기억, 캐릭터 생성, World 생성 URL에서 브라우저로 실제 표시를 확인했다. 저장·정리·준비·생성·공개 조작을 실행하지 않고 DOM 표시와 CSS를 읽었다.

| 실제 화면 측정 | 결과 |
| --- | --- |
| World 설정 10개 카드 | 동일한 8% 그림자, 좌우 inset 36px |
| 전체 설정 3개 카드 | 동일한 8% 그림자, 좌우 inset 36px |
| 기억 세 카드 / 기본 넓은 화면 | 동일한 8% 그림자, 좌우 inset 36px, gap 24px, 표시 묶음 가로 넘침 0 |
| 기억 세 카드 / 390px viewport | 좌우 inset 16px, gap 24px, 표시 묶음 가로 넘침 0 |
| 기억 세 카드 / 800px viewport | 두 열 배치의 각 카드/표시 묶음 가로 넘침 0 |
| 캐릭터 생성 | 만드는 방법 단계의 외곽 카드와 방법 선택 카드 그림자 표시; 나머지 단계 동작은 합성 fixture 회귀로 확인 |
| World 생성 | 머리·필수 세계관·운영 기본값·상세 설정·아이콘/배너·공개 준비·저장 조작의 7개 카드에 같은 그림자 표시 |

이 확인은 현재 Docker 화면의 표시 검증이며 실제 AI 활동 품질이나 사용자 직접 확인 완료와 구분한다. 데이터 볼륨을 삭제·재생성하지 않았고 백엔드를 재시작하지 않았다.
