# 일과·추천 주제 생성 언어 지침 — 로컬 구현·검증 결과

- 확인일: 2026-10-18 / Asia/Seoul
- 상태: **LOCAL VERIFIED**. 구현과 관련 합성 검증 완료. 실제 AI 품질·설치본 확인과 구분한다.
- 시작: clean `main`, `84ae0aaa0f4c9af776eb9c97fc96136b1a3113ec`
- 작업 브랜치: `feat/preparation-output-language` — 위 main에서 새로 생성
- 실행 계획: 작업 공간 `docs/plan/10-18 일과·추천 주제 생성 언어 지침 공통화와 브라우저·Tauri 일관성 보완 코드 구현 세부 계획.md`, I00–I47
- 이 문서와 코드를 포함한 로컬 커밋은 `git log -1 --format=fuller -- docs/verification/preparation-output-language-20261018.md`로 확인한다. 전체 최종 SHA는 작업 공간 계획의 실행 기록에 남긴다.
- Publish/push, PR, GitHub Actions 실행·재실행, main 병합, tag/Release/GHCR 공개는 수행하지 않았다.

## 구현 결과

| 생성 경로 | 적용 내용 | 보존 내용 |
|---|---|---|
| 최초·자동 일과 생성 | 새 `daily_plan.items[].title`, `activity_seed`에 작성 언어 지정 | 기존 schema·시간대·장소·호출 상한 |
| 수동 일과 재생성 | 같은 생성기에 같은 정책 적용 | 완료·고정·예약 항목과 실제 상태·이름 바인딩 |
| 최초 일과+추천 주제 | `recommendation_topics[].name`까지 같은 언어로 지정 | 일과와 주제의 원자 적용 |
| 일과를 모두 보존하는 초기 주제 전용 생성 | 원래 접수한 환경을 주제 생성기에 전달 | 일과 AI 무호출, 기존 일과 그대로 |
| 명시적 주제 재생성 | 새 요청의 환경을 고정하고 `topics[].name`에 적용 | 같은 요청 복구, 기존 ready 주제·내용 출처 digest |

`contracts/language.py`의 순수 계약이 검증된 locale을 매핑한다. 기본 언어가
`ko`이면 `Korean`, `en`이면 `English`, 그 밖에는 유효한 전체 코드를 전달한다.
`en-GB` 같은 원래 코드는 저장소와 provider 입력의 환경 정보에 그대로 남는다.
Identity의 기존 BCP47 입력 검증·정규화를 재사용하고 새로운 locale 라이브러리는 추가하지 않았다.

`preparation-output-language.v1`을 신규 요청에만 기록한다. 동일 요청의
재시도·프로세스 종료 후 복구는 기존 snapshot을 사용하며, 다음 날짜나 새로
접수한 명시적 요청은 해당 시점의 환경을 사용한다. 기존 정책 식별자가 없는
과거 작업은 원래 프롬프트·schema로 처리한다. 과거 주제 생성의 한국어 지침은
그 호환 경로에만 남는다.

신규 표시가 있는 snapshot의 환경 누락·null·부분 정보·잘못된 언어/수정 번호·
알 수 없는 정책은 AI 전송 전에 거부한다. 일과 상태 읽기는 자료를 쓰지 않고
기존 실패 표면을 반환한다. 처리 재개 시 소유 도메인의 짧은 transaction으로
손상된 대기 작업만 실패 처리하여 새로운 명시적 요청이 가능하게 한다.
원본 snapshot, 기존 정상 일과와 주제는 보존한다. 정상 요청이나 과거 계약을
그 이유로 실패시키지 않으며, 현재 언어로 조용히 덮어쓰지 않는다.

주제 환경·정책은 `request_snapshot.source` 밖에 저장한다. 따라서 언어 변경이나
이 변경의 배포 자체가 기존 주제를 stale로 만들거나 자동 재생성을 유발하지 않는다.
원래 persona·World·권한·credential·이름·lease 검사는 그대로 유지한다.

## 수정 파일과 역할

| 파일 | 역할 |
|---|---|
| `backend/app/contracts/language.py` | 검증된 고정 환경의 정책 판독·공통 작성 언어 지침 |
| `backend/app/domains/routines/client.py` | 실제 선택 schema의 필드에 맞는 최종 AI 지침 |
| `backend/app/domains/routines/service/daily_preparation.py` | 손상된 신규 접수 정보의 안전한 종료·기존 결과 보존 |
| `backend/app/runtime/daily_preparation.py` | 일과 접수·복구·초기 주제 전용 분기의 고정 환경 연결 |
| `backend/app/runtime/social/topic_preparation.py` | 주제 접수·재생성·복구·이전 정책 호환 |
| `backend/tests/runtime/test_preparation_language.py` | 최종 provider 입력, canonical 저장, 재생성·재개·손상·DB transaction 경계 86개 |
| `backend/tests/routines/test_ordinary_daily_generation.py` | 주제 전용 분기의 환경 전달 기대값 보완, 기존 보존 검증 유지 |
| `frontend/scripts/test-user-environment.mjs` | 공통 감지·동기화·DTO 전송 20개 조합 추가 |
| `security/architecture_import_baseline.json` | 실제 추가 import 6개와 표준 라이브러리 import 1개 기록 |
| `backend/ARCHITECTURE.md` | 현재 소유·snapshot·호환 계약 설명 |

`security/architecture_import_policy.json`이나 예외 규칙은 수정하지 않았다.
dependency/lockfile, DB schema/migration, frontend 제품 컴포넌트, Rust/Tauri 설정,
워크플로도 수정하지 않았다. 고정 사용자 문구를 추가하지 않았으므로 새 ko/en
번역 키는 필요하지 않았다. 기존 한국어·영어 오류 표면을 그대로 사용한다.

## 검증 환경과 실제 결과

Windows 호스트의 기존 잠금 의존성 환경을 사용했다. Python 3.13.12,
Node v22.22.2, pnpm 10.33.2. 모든 backend 검증 프로세스에서
`ANGMOO_DENY_EXTERNAL_NETWORK=1`을 적용했다. 실제 API 키·설치 DB·Docker 데이터는
사용하지 않았으며 fixture와 fake provider/HTTP transport만 사용했다.

| 검사 | 결과 |
|---|---|
| 신규 언어·저장 경계 + 기존 일과/이름/주제 회귀 | **127 passed, 78.92초** — 새 86개 + 기존 관련 41개 |
| SNS·기억·관계·이미지 provider 언어 경계 | **20 passed** |
| Chat CRG 언어 요청·원문 보존 | **4 passed** |
| 기존 Chat 명시적 언어 요청·영어 기본값 | **1 passed** |
| 위 정책 25개와 DB transaction 3개를 함께 실행한 명령 | **28 passed, 22.00초**. DB 3개는 127개에도 포함되므로 중복 합산하지 않음 |
| 관련 backend 고유 사례 합계 | **152 passed**. 전체 backend suite 결과가 아님 |
| `pnpm --dir frontend test:user-environment` | PASS. 기존 i18n·SSR·환경 소유·충돌·취소 검증과 새 20개 조합 |
| `node --check frontend/scripts/test-user-environment.mjs` | PASS |
| import inventory `--check` | PASS — 1,569 modules / 6,810 internal edges / 4,604 external imports |
| backend architecture boundary | PASS — legacy exact edges 0 |
| frontend architecture boundary | PASS — 14 features / legacy exact edges 0 |
| frontend design contract | PASS — raw colors 1,129 / 34 files / 18 surfaces / route gaps 0 / 64 screenshots |
| 기존 언어 정책 상수의 main 대비 AST 값 비교 | `PERSONA`, `MEMORY`, `QUERY`, `RELATIONSHIP` **4/4 동일** |
| Python 구문·`git diff --check` | PASS |

검증 명령(제품 저장소 root):

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
uv run --frozen --no-sync --directory backend python -m pytest -q `
  tests/runtime/test_preparation_language.py `
  tests/routines/test_daily_preparation.py `
  tests/routines/test_ordinary_daily_generation.py `
  tests/routines/test_preparation_name_binding.py `
  tests/social/test_topic_preparation.py

uv run --frozen --no-sync --directory backend python -m pytest -q `
  tests/runtime/test_preparation_language.py::test_preparation_holds_no_database_transaction_during_provider_wait `
  tests/runtime/test_language_provider_boundaries.py `
  tests/chat/test_chat_image_input_presentation.py::test_crg_uses_frozen_current_image_kind_and_preserves_submitted_payload `
  tests/chat/test_messages_service.py::test_message_system_prompt_uses_one_on_one_chat_guidelines

pnpm --dir frontend test:user-environment
node --check frontend/scripts/test-user-environment.mjs
uv run --frozen --no-sync --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --frozen --no-sync --project backend python scripts/ci/check_architecture_boundaries.py
uv run --frozen --no-sync --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --frozen --no-sync --project backend python scripts/ci/check_frontend_design_contract.py --check
git diff --check
```

실행 시 환경변수는 각 별도 PowerShell 자식 프로세스 안에만 설정하여 기존 환경을
바꾸지 않았다. 최초 inventory 확인은 파일 재생성이 끝나기 전에 시작되어 stale을
보고했다. 쓰기 완료를 확인하고 실제 import diff를 검토한 뒤 순차 재실행해 통과했다.
제품 시험 실패를 skip하거나 판정 기준·retry 예산을 바꾼 경우는 없다.

## 확인된 기능·실패 경계

- 11종 언어 입력 × 4개 provider 경로에서 실제 최종 system/user prompt와 schema를
  확인했다. `KO-kr`는 기존 Identity 정규화 후 `ko-KR`로 전달된다.
- 일반/초기 일과, 수동 재생성, 다음 날짜 자동 생성, 주제 전용 초기 생성,
  주제 재생성이 canonical 결과까지 저장된다. fixture는 언어의 유창성을 검사하지 않는다.
- 완료·고정 일과의 ID·원문·상태, 원래 이름, 기존 주제·digest가 보존된다.
- 동일 request ID 완료 후 중복 요청은 provider를 추가 호출하지 않는다.
  중단·만료 후 복구에는 처음 접수한 언어와 원문이 그대로 전달된다.
- 고정 항목뿐인 일과/이미 준비된 주제는 기존 무호출 경로를 유지한다.
  별도 번역 호출이나 추가 주기 작업을 만들지 않았다.
- 일과·주제·초기 주제 전용 세 경로에서 provider 직전 budget reserve 이후와
  응답을 기다리는 동안 해당 준비 Session의 `in_transaction()`이 모두 false임을 확인했다.
  실제 운영 부하의 잠금 시간이나 지연 수치를 측정한 결과는 아니다.
- 손상된 신규 입력은 호출 0회로 실패하고 기존 자료를 보존한다. 과거 요청의
  prompt/schema·name binding·digest는 유지하며, 외부 오류 원문은 사용자에게 반환하지 않는다.

## 브라우저·Tauri와 검증 한계

Next와 static layout은 같은 `AuthProvider → UserEnvironmentProvider`를 사용한다.
같은 `detectUserEnvironment → synchronizeEnvironment → synchronizeUserEnvironment`
경로로 검증할 전체 언어 코드를 backend에 전달한다. 새 매핑은 backend 한곳에만 있다.

브라우저/네이티브 runtime 설정 각각에 ko, ko-KR, en, en-US, en-GB, en-AU,
ja-JP, fr-FR, zh-Hant-TW, ar-AE를 넣은 **20개 합성 전송 사례**를 확인했다.
UI 언어를 반대로 수동 선택해도 보고하는 환경 코드는 변하지 않는다.
transport는 mock이므로 실제 Windows WebView 언어 감지나 실행된 설치본을
검증했다고 해석하면 안 된다. 실제 감지 값은 브라우저와 Tauri에서 다를 수 있다.

실제 AI의 한국어·영어·기타 언어 문장 품질, 사용자 Windows 설치본, 실행 중 Docker,
기존 P3 ARM64/amd64 이미지·EXE는 이번에 재빌드·실행·교체하지 않았다. 실제 AI 출력이
언제나 지정 언어를 지킨다는 보장도 하지 않는다. 향후 변경이 반영된 실행 환경에서
생성·재생성을 눌러 문장 품질을 확인하는 사용자 검증은 별도다.

frontend 제품 UI를 바꾸지 않아 전체 lint/typecheck/build/static/visual/installer
검증을 추가하지 않았다. 전체 backend·frontend suite 및 원격 CI도 실행하지 않았다.
이 범위는 계획의 관련 검증 지침과 일치한다. 되돌릴 때는 해당 로컬 코드 변경을
역변경하고 같은 회귀를 확인한다. 기존 DB·일과·주제·환경 설정을 삭제하지 않는다.
