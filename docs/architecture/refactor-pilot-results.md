# 구조 리팩터링 준비·파일럿 실행 결과

## 2026-09-05: AR-0 기준선 및 AR-1 검사 준비

AR-0은 #258 merge `6e56f0837cc11ff42ccbb520050bbd32c5e9bc14`를 고정했다. 구현 파일 956개는 K01~K23/G01~G13 또는 추가 K24(Tree 게시판·공통 UI·조립·호환)의 실제 경로와 후속 소유 단계에 연결했다. K24는 삭제 허가가 아니며, 그 안의 소스도 이전할 때 정확한 목적지와 소비자를 함께 변경한다.

| 검증 | 실제 결과 |
| --- | --- |
| 기준 backend 수집/전체 실행 | 1,867 collected / 1,845 passed, 22 skipped, 26 warnings |
| 기준 계약 | tracked files 1,546 / public API 196 operations / ORM 102 tables / 전체·public OpenAPI component 계약 고정 |
| 기준 Home 웹 | 5 passed: compact·wide·runtime degraded·retry/launchability·PWA |
| 기준 static export | 성공; 별도 static-shell을 frontend/out으로 export |
| 기준 Home static | 5 passed: 단일 frame·Phone/main bootstrap·잘못된 wide 창 route 거부·sidecar media 인증 |
| AR-1 검사 지원 | 관련 회귀 65 passed. 기존 1,867개에 새 검사 사례 32개를 추가했다. 상대 경로·타입·directory import·정확한 incoming bridge·새 조립의 실제 파일 import·모듈 순환·테스트 경유 우회 포함 |
| 현재 import/design 검사 | backend 686 modules / 1,846 edges / 기존 exact legacy edges 312; frontend 13 features; design raw colors 1,408 / route gaps 0 — 기존 기준 유지 |
| GitHub | #258 post-merge 7/7 SUCCESS. 준비 PR #259 exact head `ebfc3440283c1b48c32d946d955e599cd0b6f73b`의 필수·CodeQL·Tauri·installer 검증 성공, merge `3d26f899e72b1297094772153db48a9d591331d9` |

전체 backend 실행 430.87초, Home 웹 53.4초, static export 40.051초, Home static 4.0초. 최초 호스트 Node 20.16/pnpm 11.19에서 저장소와 맞는 실행기를 분리하여 Node 24.19/pnpm 11.22로 검증했다. CI는 원래 Node 22/uv 0.12.5를 유지한다. 제품 lockfile은 변경하지 않았다.

22 skip은 PostgreSQL 전용 환경변수가 없는 동시성 테스트와 public profile에서 제외된 hosted lifespan에 따른 것이다. 이를 SQLite 제품의 실패나 PostgreSQL 검증 PASS로 바꾸지 않는다. 로컬 Docker Desktop 프로세스는 시작됐지만 daemon 연결이 되지 않아 Docker 제품 검증은 아직 수행하지 못했다. 필수 Hosted CI의 Docker/installer 결과와 로컬 실행 상태를 구분한다.

AR-1은 제품 scope 없이 검사 지원을 먼저 병합했고, 각 파일럿이 자신의 코드 이동과 scope 활성화를 함께 수행한다. 기존 public/계층 보호와 module/package cycle 검사는 계속 실행한다. 기존 ARCHITECTURE 두 작성본을 보존하고 적용 상태·기여 지도·AGENTS·기존 architecture-boundary workflow를 연결했다.

## 파일럿 상태와 후속 인계

| 단계 | 상태 | 남은 일 |
| --- | --- | --- |
| AR-0 | COMPLETE — PR #259 병합 | 고정 기준선은 후속 단계에서도 재생성하지 않음 |
| AR-1 | COMPLETE — PR #259 병합 | 전환 범위별 scope만 각 후속 PR에서 활성화 |
| AR-B1 | COMPLETE — PR #260 병합 | PR-head·post-merge 결과 분리 기록 완료 |
| AR-F1 | COMPLETE — PR #261 병합 | PR-head·post-merge 결과 분리 기록 완료 |

AR-G의 전역 Base/DB/models/Alembic/logging 최종 이전, 다른 업무·화면 전환, AR-X 최종 동일 commit 검증과 P8-L-S 실제 AI/인과/사용자 품질 closeout은 후속 범위다.

## 2026-09-05: AR-B1 Backend Device Home

`api/application/domain/infrastructure/ports/public`에 나뉘었던 Device Home 조회를 `router.py`, `schemas.py`, `service.py`, `repository.py`, `contracts.py`, `policies.py`, `exceptions.py`로 옮겼다. 자체 ORM 모델은 만들지 않았고 기존 Base·DB·Alembic·route 순서·OpenAPI·196개 public operation·102개 ORM table은 바꾸지 않았다.

World Package committer는 `service.get_device_home_world`를 직접 사용한다. 이 내부 projection은 호출자의 Session과 미완료 transaction을 유지하고 active membership의 draft/차단 World도 반환한다. HTTP service는 claimed installation owner와 launchability를 계속 검사하고 외부에는 같은 403/404를 반환한다.

기존 8개 테스트 node는 `tests/device_home/test_world_surface.py`로 일대일 매핑했다. 내부/HTTP 권한 차이, flush 후 미commit 조회와 rollback, World owner가 아닌 active membership, 같은 시각의 ID cursor, stale readiness, HTTP limit/cursor/local-origin 경계를 추가했다. Device Home 13개와 World Package 직접 소비자 2개가 통과했고, 구조 회귀 65개와 frozen 1,867/current 1,904 node 보존 검사도 통과했다. Backend `device_home` 새 scope를 활성화했으며 legacy alias는 남기지 않았다.

PR #260 exact head `d9c3ed5e8c6c86632988e614171b0d190e622183`에서 Core·Security·Local Smoke·CodeQL·Windows Advisory·Host Tauri와 installer build/clean-install/failure-recovery/supported-upgrade/aggregate를 포함한 23개 체크가 모두 성공했다. 2026-09-05 04:20 KST에 merge commit `a55c521b9adad624ae1342b2a7b270abc2237f79`로 병합했다. 이 merge commit의 post-merge workflow 7개도 재실행 없이 모두 성공했다.

## 2026-09-05: AR-F1 Frontend Device Home

Next route와 static router가 함께 사용하는 `composition/screens/device-home-screen.tsx`를 만들었다. 이 screen은 인증·runtime 상태·Phone shell을 조립하며, `features/device-home/components/device-home.tsx`는 World 목록과 실행 가능성 표현만 소유한다. runtime 상태와 World 목록은 각각 하나의 effect에서 요청하고, 목록 재시도는 runtime을 다시 요청하지 않는다. `public.ts`는 screen이나 shell을 내보내지 않는다.

Device Home의 `api/components/types/utils`를 목표 역할로 옮기고 runtime transport·navigation·media·AppIcon·Button·class names·semantic CSS의 단일 구현을 `hooks/lib/components/utils`에 배치했다. Creator Studio·Memory·World App의 API/type 소비자 4개는 AR-F2/AR-F3 제거 조건과 함께 한시적 `public.ts` facade를 사용한다. 공용 옛 경로에는 명시적 TypeScript re-export 7개가 남고, 기존 semantic primitive 7개는 새 CSS module을 직접 사용한다. facade 소비자는 AR-F2/AR-F3에서, 공용 TypeScript bridge와 semantic primitive 직접 소비자는 AR-F4에서 제거한다.

로컬 검증은 frontend lint/typecheck, World Package proxy, Next production build 14개 정적 페이지, static export를 통과했다. Home 웹 5개, Local Settings 2개, static Home 5개 시나리오가 성공했다. 여기에는 390px·wide shell, World 0개/여러 개, runtime degraded와 목록 실패 분리, retry/launchability, PWA, static Phone/main bootstrap, 잘못된 wide route 차단, launcher token을 사용한 sidecar media blob URL이 포함된다. 추가 소스 계약과 frontend 경계 테스트 18개, frozen 1,867/current 1,905 node 및 API·ORM preservation contract, frontend architecture/design, L4/P8-L-D/P8-L-E/P8-L-R inventory도 통과했다. Windows에서 visual snapshot을 갱신하지 않았으며 canonical visual은 Hosted 고정 환경에서 확인한다.

`src/testing`은 만들지 않았다. 실제 공용 소비자는 backend 소스 계약, Playwright 전용 fixture, Node proxy 검사에 있고 공유 React runner·mock server 소비자가 아직 없기 때문이다. 새 테스트 지원 계층은 실제 소비자와 실행기 등록이 생길 때 함께 도입한다.

PR #261 exact head `31fd5b052e9b910c8ac48027065753faa0a7ab5b`에서 Core·Security·Local Smoke·CodeQL·Windows Advisory와 installer build/clean-install/failure-recovery/supported-upgrade/aggregate를 포함한 등록 체크 22개가 모두 성공했다. Hosted 고정 환경에서는 제품 shell 21개, UI-E 2개, static direct-open 68개와 canonical visual 36개가 통과했다. 별도 Host Tauri workflow는 변경 경로가 그 workflow의 path filter에 포함되지 않아 생성되지 않았고, Core의 `tauri-windows`와 installer가 영향받는 Windows 경로를 검증했다.

Installer 첫 attempt의 clean-install은 제품 실행 뒤 Windows Defender `Start-MpScan`이 runner 장치 스캔 오류를 반환해 실패했다. 동일 head의 실패 job만 재실행한 attempt 2에서 Defender scan과 개발 runtime 없는 설치·실행이 성공했고 전체 installer matrix가 성공했다. 2026-09-05 05:06 KST에 merge commit `5b83fee1625fdd490051b840790683114d7daaab`로 병합했다. 이로써 §8.1 AR-0·AR-1·AR-B1·AR-F1은 완료됐다.

이 merge commit의 post-merge workflow 6개도 exact main에서 모두 성공했다. Windows Installer의 첫 supported-upgrade attempt는 일곱 지원 버전 검증 뒤 `angmoo-sidecar.exe` 파일 잠금으로 fixture cleanup이 실패했으나, 동일 main SHA의 실패 job만 재실행한 attempt 2에서 supported-upgrade와 최종 aggregate가 성공했다. 제품 검증 실패와 Windows runner의 일시적 정리 실패를 구분해 기록하며, 이 재실행 결과를 다른 commit의 증거로 재사용하지 않는다.
