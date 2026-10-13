# World 삭제 확인 창 개선 — 2026-10-13

작업 저장소는 `angmoo-tree-angmoo`, 브랜치는 `feat/0.1.0-release-readiness`다.
시작 HEAD는 `b1e81e63953283efc725451e51bb6af948322d60`이며 시작 시 작업 트리는 clean이었다.
이 기록은 해당 변경과 같은 로컬 커밋에 저장한다. 정확한 최종 SHA는 최종 응답과 Git에서 확인한다.

## 확인한 원인

- World 이름 확인은 DOM에 있었지만 일반 `<input>`으로 렌더링했다. 공통 Field/Input의
  테두리·전체 폭·label/helper 배치가 없어 reset 스타일 아래에서 입력 영역을 알아보기 어려웠다.
- 선택적 패키지 내보내기 전체 양식을 먼저 렌더링하여 필수 이름/동의 확인이 아래로 밀렸다.
  Dialog 안의 긴 콘텐츠가 전체 창 높이를 늘리면서 제목과 취소/삭제 조작도 같이 스크롤됐다.
- Studio의 `.worldCard p`가 카드에 연결된 Dialog 내부 문단까지 선택했다. 실제 스크린샷에서
  대상 이름과 경고가 카드 소개의 작은 회색 글자로 덮이는 것을 확인하고 선택자를 카드 소개로 좁혔다.
- 펼친 내보내기 영역을 스크롤한 뒤 다시 열 때 이전 본문 위치가 남았다. 새 확인을 열 때 본문을 맨 위로 초기화한다.

## 구현과 보존 경계

- `features/worlds/components/world-delete-control`이 대상 이름, 삭제되는 정보, 유지되는 정보를 분리한다.
  공통 Field/Input으로 이름 입력을 표시하고 44px 이상 확인 체크 행을 제공한다.
- 삭제되는 World별 캐릭터 현재 설정/활동·SNS·Chat·관계·기억·첨부와 보존되는 첫 등록 원본/초기 이미지/연결·
  타 World·공용 설정의 의미를 유지한다. 변경한 안내는 ko/en을 함께 제공한다.
- 패키지 export는 필수 확인 아래의 접힌 native disclosure로 제공한다. 원래 export UI/API는
  composition의 `renderExport` 슬롯으로 연결하고 World feature가 다른 feature 구현을 직접 import하지 않는다.
  export를 전체 기록 백업이나 삭제 필수 조건으로 표시하지 않는다.
- feature CSS가 공통 Dialog의 제목/닫기/하단 조작을 고정하고 본문만 스크롤한다.
  공통 primitive 자체와 다른 Dialog 화면은 변경하지 않았다. 디자인 분류는 **LOCAL**이며 새 asset/font/dependency/raw color가 없다.
- 정확한 저장명 비교, 버전·소유권·기본 SNS 보호, 명시 동의, 응답 유실 시 동일 idempotency key 재사용과
  삭제 receipt/progress/retry는 기존 계약을 유지한다. 백엔드/API/DB/worker는 변경하지 않았다.

## 검증 범위와 재실행

fixture API는 synthetic in-memory 데이터만 처리한다. 미처리 API는 404이며 실제 backend로 fallback하지 않는다.
사용자 포트 3000과 실제 World/설치 앱을 사용하지 않고 3415–3418의 별도 시험 서버를 사용한다.
Next는 새 standalone production build의 실제 server와 checkout dependency로 검증한다.
Windows traced directory link 때문에 새 ignored artifact root에 조립하며 기존 출력/의존성은 변경하지 않는다.
이 시험은 설치 패키지의 dependency/ACL 검증을 의미하지 않는다.

```powershell
$env:ANGMOO_NEXT_DIST_DIR = '.next-world-delete-dialog-prod'
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests exec playwright test --config=playwright.world-delete-dialog.config.ts
```

브라우저 시험은 ko/en × Next/static에서 이름 입력의 실제 크기·테두리·완전한 viewport 표시,
대상 이름의 글자 크기, 잘못된 이름/동의 미확인 시 차단, 정확한 이름과 동의 시 활성화,
선택 export의 접힘/펼침과 mutation 없음, 스크롤 중 제목/footer 유지, 긴 이름과 360px 화면,
키보드 focus trap/취소 복귀, 기본 SNS·capability, 실제 fixture 삭제 접수/완료 및 응답 유실의 동일 명령 재확인을 다룬다.
전체 backend/frontend/browser 시험 corpus와 실제 AI 호출·실제 사용자 World 삭제는 실행하지 않는다.

초기 dev/proxy 시험은 기능 도달 전에 초기 로딩에서 멈춰 중단했다. 소스/정책을 약화하지 않고
fresh production fixture로 전환했다. 그 시험 환경의 정지 원인을 앱 삭제 기능 장애로 해석하지 않는다.

최종 브라우저 결과와 스크린샷은 ignored `artifacts/world-delete-dialog-20261013` 아래에 저장한다.

## 최종 실행 결과

| 검증 | 결과 |
| --- | --- |
| 관련 브라우저, ko/en × Next standalone/static | **32 passed**, 약1.9분; `browser-results.json`, `unexpected=0` |
| 1280×900 / 390×844 화면 캡처 | 8개 생성; ko/en·Next/static의 같은 Dialog, 테두리 입력과 첫 확인 위치를 실제 이미지로 확인 |
| 긴 이름 / 360×640 / 키보드 | 양 언어·양 실행에서 PASS; 본문 scroll과 항상 보이는 header/footer, focus trap·취소 복귀 |
| Next production build / static build | 최종 변경 포함 각각 PASS |
| frontend typecheck / 변경 TSX ESLint | PASS |
| UI 번역 카탈로그 | PASS; 16 namespaces / 2617 source keys, ko/en key·params·plural parity |
| frontend architecture | PASS; features14 / legacy_exact_edges0 |
| frontend design contract | PASS; raw_colors1157 / files35 / surfaces18 / route_gaps0 / screenshot call sites61 |
| fixture JS syntax / `git diff --check` | PASS |
| 전체 frontend lint | **기존 오류1·경고2**. `scripts/test-world-image-contract.mjs:19`의 `module` 변수 이름 금지와 `test-photo-profile-proxy.mjs`의 unused 변수2건. HEAD에도 같은 코드가 있음을 확인했으며 이번 수정에는 포함하지 않았다. |

스크린샷 call site를60→61로 정식 inventory에 추가했고 기존11개 canonical PNG, 픽셀/차이 임계값은 유지했다.
빌드가 자동 추가한 임시 tsconfig include/format만 제거했다. 시험 서버는 모두 종료했으며 사용자 서버 포트3000은 유지했다.
PR/push/원격 CI/main 머지, 설치 앱 교체, 실제 사용자 World 삭제는 수행하지 않았다.
