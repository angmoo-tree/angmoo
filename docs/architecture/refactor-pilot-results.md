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
| GitHub | #258 post-merge 7/7 SUCCESS 확인. 새 준비 PR의 head/merge 검증은 별도 기록 |

전체 backend 실행 430.87초, Home 웹 53.4초, static export 40.051초, Home static 4.0초. 최초 호스트 Node 20.16/pnpm 11.19에서 저장소와 맞는 실행기를 분리하여 Node 24.19/pnpm 11.22로 검증했다. CI는 원래 Node 22/uv 0.12.5를 유지한다. 제품 lockfile은 변경하지 않았다.

22 skip은 PostgreSQL 전용 환경변수가 없는 동시성 테스트와 public profile에서 제외된 hosted lifespan에 따른 것이다. 이를 SQLite 제품의 실패나 PostgreSQL 검증 PASS로 바꾸지 않는다. 로컬 Docker Desktop 프로세스는 시작됐지만 daemon 연결이 되지 않아 Docker 제품 검증은 아직 수행하지 못했다. 필수 Hosted CI의 Docker/installer 결과와 로컬 실행 상태를 구분한다.

AR-1 실제 정책의 새 scope 목록은 비어 있다. 검사 지원을 먼저 병합하고 각 파일럿이 자신의 코드 이동과 scope 활성화를 함께 수행한다. 기존 public/계층 보호와 module/package cycle 검사는 계속 실행한다. 기존 ARCHITECTURE 두 작성본을 보존하고 적용 상태·기여 지도·AGENTS·기존 architecture-boundary workflow를 연결했다.

## 파일럿 상태와 후속 인계

| 단계 | 상태 | 남은 일 |
| --- | --- | --- |
| AR-0 | 기준선·매핑·로컬 기준 검증 완료 | 준비 PR head/merge 결과 기록 |
| AR-1 | 검사 지원·문서 연결 구현, 로컬 검증 | 준비 PR 필수 CI 및 병합 |
| AR-B1 | NOT STARTED | Device Home backend 역할별 이동·직접 소비자·API/transaction/수집 보존 |
| AR-F1 | NOT STARTED | Home 화면 조립·최소 공용 이동·Next/static·호환 소비자 검증 |

AR-G의 전역 Base/DB/models/Alembic/logging 최종 이전, 다른 업무·화면 전환, AR-X 최종 동일 commit 검증과 P8-L-S 실제 AI/인과/사용자 품질 closeout은 후속 범위다.
