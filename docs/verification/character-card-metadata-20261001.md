# 실리태번 카드 중복 메타데이터 호환 구현·로컬 검증

2026-10-01. 작업 기준은 workspace의 「10-01 실리태번 캐릭터 카드 중복 메타데이터 호환과 가져오기 오류 수정 코드 구현 세부 계획」 P00–P10과 사용자 확정 계약이다. 제품 저장소 `feat/sns-chat-image-integration`, 시작 HEAD `3fcac2537e0f58bcfd0c6e5bc8bc0437a0d03fe1`에서 진행했다. 시작 작업 트리는 깨끗했다.

`backend/ARCHITECTURE.md`, `frontend/ARCHITECTURE.md`, `frontend/DESIGN.md`, 적용되는 AGENTS·기여 지침을 읽고 기존 parser → domain service → DTO/router → feature API/component 경계를 유지했다. 새로운 카드 실행 엔진·우회 업로드·수동 PNG 재작성·DB migration은 추가하지 않았다. 로컬 테스트와 signed-off 로컬 커밋만 수행하며 PR·CI workflow·push·main 병합·원격 이슈는 범위 밖이다.

## 최종 동작

기존 parser가 PNG의 같은 `chara`/`ccv3` keyword 반복을 모두 거부하던 것이 제공 카드 세 개의 공통 실패 원인이었다. 새 parser는 전체 PNG container를 먼저 검사하고, `ccv3`의 첫 항목을 우선하거나 없으면 `chara`의 첫 항목을 선택한다. keyword는 대소문자를 정규화한다. 자동 선택 정책은 `sillytavern-first-match-v1`, 새 저장 provenance는 `angmoo-card-import-v2`다.

- 선택한 정의가 잘못되면 다음 정의나 다른 keyword로 대체하지 않는다. 최신 설정 추정·병합·잘라내기도 하지 않는다.
- 동일 keyword의 중복은 추가 승인 없는 안내로 표시한다. 보통 `chara` 하나와 `ccv3` 하나인 카드는 중복 안내 대상이 아니다.
- 사용하지 않는 정의의 의미·Base64·JSON은 가져오기에 관여하지 않는다. 해당 chunk의 CRC와 텍스트·chunk 누적량 검사는 유지한다.
- 전체 원본 PNG bytes와 선택 JSON bytes의 SHA-256을 구분한다. 원본의 모든 정의는 그대로 보관하며 표시용 WebP는 별도 파일이다. 편집·등록·조회가 원본 PNG를 다시 작성하지 않는다.
- import와 소유자 전용 source DTO에 선택 요약을 연결했다. `include_document=false`는 선택 JSON 본문을 반환하지 않고 선택·검토 요약을 돌려준다. 기존 기본 조회는 선택된 한 정의의 JSON을 반환한다.
- 화면 복구는 요약만 읽는다. 실패 시 편집 내용을 보존하고 명시적인 다시 불러오기를 제공한다. ‘원문 보기’에서만 JSON 본문을 가져온다. 기존 카드 교체 확인·취소·대상 World 분리·늦은 응답 차단을 유지한다.
- 공개 Character DTO와 준비·SNS·Chat 입력에는 private 원본·선택 요약·raw-only 특수 지침이 자동 주입되지 않는다. 등록 캐릭터는 최종 편집값을 사용하고 키 연결 없이 자율활동 OFF로 저장한다.

검사 과정에서 확인된 관련 경계도 보완했다. 표시 파일 쓰기 도중 실패하면 파일 소유 함수가 이번 시도의 부분 파일을 지운다. DB commit 실패는 기존 service의 rollback과 새 파일 정리를 사용한다. 만료 예외는 상위 NotFound 예외보다 먼저 처리한다. 기존 Next 중계가 source의 `private, no-store`와 `nosniff`를 전달하도록 안전한 응답 헤더 두 개만 추가했다.

파일 20MiB, JSON 2MiB, 개별/누적 PNG 텍스트 3/6MiB, chunk 4096개, JSON 깊이 32·노드 50000개, 이미지 16MP·한 변 8192 상한을 변경하지 않았다. 카드 요청 본문 `28,262,144` bytes와 일반 API 1MiB 한도·Origin 보호도 유지한다. JSON 중복 key, NaN/Infinity와 지수 overflow의 비유한 수, 잘못된 spec 타입·버전·공통 필드는 계속 거부한다.

## 검증 결과

| 구분 | 결과·실제 범위 |
| --- | --- |
| P01 수정 전 합성 회귀 | 13 FAIL / 26 PASS. 새 중복 계약과 숫자·잘못된 타입 경계의 실패를 기록 |
| parser·기존 등록·backend 요청 한도 | 64 PASS; parser 최종 정확한 20MiB 경계 추가 후 51 PASS 재확인 |
| 신규 HTTP·rollback·원본 파일 통합 | 12 PASS, skip 0. 외부 네트워크 차단·AI runner 실패 대역, 실제 원본 세 건 포함 |
| backend 고유 사례 합계 | 76개 통과. 재실행을 새로운 사례로 중복 합산하지 않음 |
| 실제 Next + 격리 contributor backend | 5개 고유 사례 통과: 일반 합성·중복 합성·이번 원본·이전 원본 4개 그룹과 서버 종료 1개. 중복 합성·이번 원본은 아바타 HTTP 200/WebP·실제 img 로드와 화면의 OFF 등록 버튼까지 추가 검사하여 2 PASS |
| static 공유 component | 74개 고유 사례 통과. 전체 실행 73 PASS와 실패한 안내 locator를 수정한 대상 1 PASS를 합친 결과 |
| 카드 Next 프록시 검사 | PASS. 고정/streamed 본문 한도, 413·403, upstream 횟수·bytes·hash, query 및 private 응답 헤더 |
| lint / typecheck | PASS |
| Next build / static build | PASS |
| backend / frontend architecture | PASS. 신규 legacy 경계 0 |
| frontend design contract | PASS. raw colors 1230·36 files, surfaces 18, route gaps 0 |

추가 static fixture는 실제 수집 파일 `static-product-shell.spec.ts`에 연결했다. 실패 대역의 요약 복구·재시도·원문 요청 분리, 교체 실패/취소, 편집 보존, 다른 World 이동 중 대기 응답, 긴 한국어 안내·키보드·200% CSS zoom을 검사했다. 390×844 캡처를 눈으로 확인했으며 안내의 줄바꿈과 입력 포커스가 유지됐다. 이 캡처 한 개를 LOCAL 진단 inventory에 추가하여 screenshot calls를 16→17로 갱신했다. canonical 이미지 11개와 visual diff 허용값은 변경하지 않았다.

브라우저 서버는 임시 contributor 데이터 루트와 임시 loopback port로 실행하고 스케줄러·이미지 worker를 끈다. 소유한 프로세스만 종료하며 Windows의 OS 종료와 Node exit 알림 사이 경합은 PID 존재 검사와 서버 주소 연결 종료 확인으로 검증한다. 사용자가 실행 중인 Docker와 설치 데이터·API 키를 연결하지 않았다.

초기 Next 실행은 private 헤더 누락·이전 원본 manifest의 hash 대소문자 기대값·Windows 종료 경합으로 실패했다. private 헤더는 제품 중계에서 보완했고 hash 기대값과 종료 검증은 테스트 harness에서 수정했다. 일반 합성·이전 원본·종료는 재실행에서 PASS, 중복 합성·이번 원본·종료는 종료 보완 후 별도 실행에서 3 PASS를 기록했다. 아바타의 접근성 컨테이너 대신 실제 내부 `img`의 `complete/naturalWidth`를 검사하도록 locator를 수정한 마지막 UI 실행도 중복 합성·이번 원본 2 PASS다. static 초기의 1 FAIL도 Next route announcer와 카드 오류 안내를 함께 선택한 locator 문제였으며, 정확한 오류 안내로 지정한 대상 재검사가 PASS다. 초기 FAIL을 숨기거나 단일 전체 실행이 모두 통과한 것처럼 합산하지 않는다.

## T01–T24 대응

| 계약 | 근거 |
| --- | --- |
| T01 | V1/V2/V3 × JSON/PNG, Unicode, 기존 mapper·등록 회귀 |
| T02–T04 | 동일/다른 중복, physical order 반전·수정 시각 무시, source/선택 JSON hash |
| T05 | 첫 chara/ccv3 오류·우선 ccv3 오류 시 no fallback, HTTP 실패 후 revision·source 보존 |
| T06–T07 | 4개 정의에서 첫 C 선택, 서로 다른 keyword 하나씩은 무안내, keyword case 정규화 |
| T08–T10 | 전체 CRC·종료·truncation, JSON 중복 key·비유한 수·depth/nodes, 미사용 payload 의미 제외·CRC 포함 |
| T11 | 파일 정확한 20MiB 및 초과, JSON decoded/encoded, 개별·누적 텍스트·chunk·dimension·pixels의 포함 경계 |
| T12 | missing metadata·unsupported/mismatched version·wrong data/spec/common types·빈 이름, 안전한 HTTP 안내 |
| T13 | HTTP import/full source/summary source, 새로고침 요약·선택 JSON·source hash 일치; 예전 provenance 조회 보존 |
| T14 | name/worldview/personality/speech_style 편집 등록, canonical persona·원본 bytes 보존 |
| T15 | owner·expiry·revision 충돌, 기존 completed draft 변경 거부·등록 원본의 만료 제외 |
| T16 | commit 실패의 이전 원본/아바타 보존·새 파일 정리; 부분 write 실패의 DB rollback·파일 정리 |
| T17–T18 | 기존 실제 준비·SNS·Chat 입력 검사와 신규 duplicate raw-only 검사, 네트워크 차단·AI runner 실패 대역·OFF·credential 없음 |
| T19 | Red: 첫 Red, worldview 3362자; 원본 hash·private read·편집 등록 |
| T20 | Raymond: 첫 Raymond, worldview 6847자; 빈 선택 항목·원본 hash·편집 등록 |
| T21 | Elias: 첫 Elias Finch, worldview 6520자; 두 번째의 긴 정의 병합/선택/자르기 없음 |
| T22 | backend body-limit tests와 실제 Next proxy script, 고정/streamed·일반/카드·Origin·upstream 요청 검사 |
| T23 | 실제 Next 중복 안내·요약 복구·카드 교체 확인/취소·모드 변경, static 실패/재시도·World 이동 검사 |
| T24 | 실제 static export의 공유 생성 component, 390×844·200% CSS zoom·키보드·한국어·눈으로 캡처 확인 |

## 재현 명령과 증거

저장소 루트의 로컬 검사 명령이다. Python 환경은 repository backend `.venv`를 사용한다. `ANGMOO_CARD_ORIGINAL_DIR`는 사용자 원본을 복사하거나 수정하지 않고 읽는 선택 입력이다. 일반 clone에서는 원본이 없는 선택 사례만 skip하고 필수 합성 사례는 실행한다.

```powershell
Set-Location '.\backend'
& '.\.venv\Scripts\python.exe' -m pytest -q tests/integrations/test_character_cards.py tests/test_creator_card_registration.py tests/common/test_request_body_limits.py
$env:ANGMOO_CARD_ORIGINAL_DIR = 'C:\Users\wlsrn\Downloads'
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_card_metadata_compatibility.py
Set-Location '..'
pnpm --dir frontend test:character-card-proxy
pnpm --dir browser-tests exec playwright test --config playwright.card-upload.config.ts
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend build:static
$env:ANGMOO_STATIC_E2E_PORT = '13220'
pnpm --dir browser-tests exec playwright test --config playwright.static.config.ts
& '.\backend\.venv\Scripts\python.exe' scripts/ci/check_architecture_boundaries.py
& '.\backend\.venv\Scripts\python.exe' scripts/ci/check_frontend_architecture_boundaries.py
& '.\backend\.venv\Scripts\python.exe' scripts/ci/check_frontend_design_contract.py --check
```

이 PC의 상세 증거는 workspace `.local-diagnostics/character-card-implementation-20261001/`에 보관했다. JUnit, 초기 실패와 수정 후 로그, local static capture, 실제 서버 종료 확인을 포함한다. 이 폴더는 clone에 포함되지 않는다. 재현 가능한 합성 fixture·검사 코드와 이 문서의 요약은 Git으로 관리하며, 사용자 PNG·본문·화면 캡처·테스트 DB·키는 커밋하지 않는다.

## 検証境界

사용자의 실제 Docker 화면에서 가져오기와 Windows native/설치형 배율은 별도 USER CHECK다. local commit이 Docker image를 재빌드하는 것은 아니지만, 개발용 watch가 활성화돼 있으면 컨테이너 파일은 동기화될 수 있다. 이번 작업에서 agent는 Docker build/restart, 설치·사용자 DB migration, 실제 AI 호출·과금, PR·CI workflow·push·main 병합을 수행하지 않았다. 개별 `scripts/ci/` 검사는 로컬 정합성 도구 실행이며 CI workflow 실행이 아니다.

## Docker watch 확인 후 정정

사용자가 현재 실행 명령을 `docker compose -f compose.yml -f compose.dev.yml up --build --watch`로 알려준 뒤 실제 실행 구성을 다시 확인했다. 기존 완료 보고의 ‘소스 mount가 없으므로 코드 미반영’ 판정은 watch를 확인하지 않은 잘못된 추론이었다. 컨테이너 ID·image·mount가 그대로라는 사실만으로 컨테이너 내부 파일이 그대로라고 판정할 수 없다.

실행 컨테이너의 Compose label은 이 저장소의 두 compose 파일과 작업 경로를 가리킨다. `compose.dev.yml`은 backend/app → `/workspace/backend/app`, frontend/src → `/app/src`를 `action: sync`로 동기화한다. backend dev 실행은 `--reload`, frontend는 Next dev를 사용한다. 의존성·Dockerfile 변경에는 별도의 rebuild 규칙이 있다.

현재 컨테이너 안의 변경된 제품 파일 9개(parser/router/schemas/card_import/media_storage 및 frontend 생성 화면/API/types/중계)의 SHA-256이 로컬 파일과 모두 일치했다. backend 로그에서도 수정 파일 감지 → Reloading → server process 시작 → Application startup complete를 확인했고 두 서비스는 healthy였다. 따라서 현재 개발 Docker 컨테이너의 수정 코드 반영은 확인됐다. 이미지 자체 재빌드 완료나 사용자 화면에서 세 카드 모두 성공했다는 검증으로 확대하지 않는다. 사용자 데이터·키를 읽거나 추가 재빌드/재시작을 수행하지 않았다.
