# 다국어 UI 계약 누락 F01–F04 수정과 로컬 재검증

2026-10-04 KST. 작업 위치는 `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`, 브랜치는 `feat/0.1.0-release-readiness`, 수정 시작 HEAD는 `ab15b7b641f875e37b47e84b60d4bfb3cc696a96`다. 사용자 승인 범위는 독립 재검토에서 발견한 UI 계약 누락 세 범주와 필수 디자인 검사 실패 한 건의 제품 코드·기준 파일·원 계획 보완이다. [원 계획](<D:/project_code/angmoo-workspace/docs/plan/10-03 Angmoo 다국어·사용자 시간대와 Gemini SNS 스키마·누락 복구 통합 코드 구현·검증 세부 계획.md>)의 P09/P10/P15/P16/P25/P26 및 P28/P30 판단을 보완한다.

이 문서의 초기 기록은 제품 수정 커밋에 포함되고, 커밋 SHA를 요구하는 공식 보존 검사 결과와 마감 기록을 후속 단위로 추가했다. 이전 계획 실행의 4,917 PASS·52 SKIP, 제품 104 PASS·10 SKIP, canonical visual 36 PASS는 역사 결과이며 이번 실행 수치로 합산하지 않는다.

## 수정한 계약과 소유

| 발견 | 변경과 보존 경계 | 현재 검증 근거 |
| --- | --- | --- |
| F01 — 인증 전 초기 UI 언어 감지 누락 | `lib/i18n/detection.ts`의 표시용 감지를 composition provider의 `useSyncExternalStore`로 연결. SSR와 첫 hydration snapshot은 동일 fallback, 이후 client의 ko/en 선호 적용. 저장 UI 선택과 현재 인증 scope의 canonical 환경을 우선. 표시용 감지만으로 인증 전 환경 API·lease·World 초기화·AI 호출을 시작하지 않음. 이벤트 구독 해제와 기존 auth/session/runtime CAS 경계 유지. | 실제 Next/static 익명 ko-KR/en-US/ja-JP/감지 예외·새로고침·완성된 owner 화면·HTML lang·hydration·환경 API 0건. 기존 실제 SQLite 환경/lease/preference 검사도 유지. |
| F02 — 동적 페르소나·API 검증·이미지 오류 번역 누락 | Persona 길이 오류를 code/limit/excess로 반환하고 현재 locale의 숫자·전체 문구를 alert와 native validity에 사용. Identity/Characters/Social validation은 feature의 authored key와 typed 범위를 공통 HTTP 오류에 전달. 지원 이미지/10MiB/읽기 실패는 typed preflight 오류. 검증 한도·NFC codepoint·입력 원문·status/code/Retry-After 보존. | 실제 PersonaField 렌더/ARIA, 양 언어 6종×3 feature API 검증, 형식·용량·읽기 오류의 전송 0건. 브라우저 native validity·수정 후 오류 해제·handle 422. |
| F03 — World Package 오류의 언어·작업·코드 안내 누락 | API에서 안전한 code/status/Retry-After 및 허용된 persona field/actual/limit만 보존. feature의 오류 표시 owner가 알려진 26개 code와 8개 persona field를 번역. import/export 서버 안내 분리, 미지 응답/개인 body 안전 fallback. typed 실패 상태를 render 때 번역하여 언어 변경 중 추가 package 제출 없음. 승인 digest·정리·전달 확인 재시도 유지. preview의 trust/duplicate authored label도 catalog 연결. | 양 언어의 모든 backend reason code·persona field·미지/서버 오류 검사. 두 production 화면의 persona 422/server 503/manifest 422와 상태를 유지한 ko 전환, stage 1건 유지. |
| F04 — 필수 디자인 보고서의 stale hash | `check_frontend_design_contract.py --write`로 검토한 소스 보고서만 갱신. stale `static-product-shell.spec.ts` hash와 수정한 import/export component hash 반영. | `--check` PASS. raw_colors=1,230, files=36, surfaces=18, route_gaps=0, screenshots=18. 정책·허용치·고정 snapshot PNG 변경 없음. |

Frontend 업무 정책은 각 feature에 두고 공통 lib에는 표시 중립적인 typed HTTP 전송·감지만 둔다. 새로운 dependency, cross-feature 내부 import, DOM 치환, suppression, skip, 느슨한 assertion 또는 broad 보존 예외를 추가하지 않았다. Backend/Frontend ARCHITECTURE와 Frontend DESIGN을 따른다. 시각 provenance는 기존 Field/InlineError/control의 DIRECT 사용과 locale/error 연결의 LOCAL 변경이다.

## 회귀 검사와 증거 보존

로컬 증거는 Git에서 제외된 `artifacts/multilingual-ui-contract-fixes-20261004/`에 보존한다. 다른 clone에서 자동 제공되는 자료가 아니므로 공유할 판단과 명령은 이 문서에 남긴다. 수정 전 독립 재검토의 FAIL 증거 `artifacts/multilingual-plan-review-20261004/`도 유지한다.

- `pnpm --dir frontend test:ui-error-contracts`: 53 PASS. 실제 모듈/렌더/응답을 사용하는 합성 검사이며 외부 전송 없음.
- `pnpm --dir frontend test:ui-catalog`: 16 namespace·2,440 source key와 ko/en key/params/plural parity PASS. 동적 message/context/map 값도 검사한다.
- `pnpm --dir frontend test:user-environment`: 독립 i18next/SSR/escaping/detector/UTC display/typed HTTP와 12개 늦은 session 응답 전환 PASS.
- 두 proxy smoke PASS. 개발 Next 서버의 공유 `.next/dev` lock을 사용하는 두 검사는 순차 실행한다.
- 관련 backend 7개 파일: 98 PASS, SKIP 0. 최초 2개 실패는 Community 전송 이전 뒤 소스 소유 경로를 충분히 따라가지 못한 기존 보안 assertion이었다. 현재 feature→wrapper→공통 transport 연결을 검증하도록 갱신하고, legacy route 부재·같은 origin credentials·사용자 Bearer 금지 조건을 유지했다.
- Next/static 브라우저 36 PASS, SKIP 0. fixture의 실제 cookie 인증·SQLite 환경/preference와 합성 오류를 사용한다. 외부 Provider HTTP는 차단한다. 마지막 persona field catalog 보강 뒤 두 production build를 다시 만들고 36건 전체를 재실행한 최종 결과다.
- lint·typecheck·Next/static build 및 frontend/backend 구조 검사 PASS. 마지막 제품 소스에 대해 두 production build와 관련 backend 98건을 재실행했다. 공식 보존 검사와 Git 마감은 아래 최종 기록에서 구분한다.

이번 검사 중 잘못된 작업 위치로 인한 `app` import 실패, dev proxy 동시 실행의 lock, 영어 test literal/새 DB의 빈 Memory scope 가정, Next route announcer와 제품 alert의 locator 중복은 제품 오류와 구분하여 이전 로그·JSON·trace에 보존했다. 올바른 cwd·순차 dev 실행·실제 catalog 이름·제품 main 안의 alert·빈 상태/선택 URL 분기를 사용한 재검증으로 수용 조건을 확인한다. 이전 실패를 삭제하거나 PASS로 바꾸지 않는다.

소스 보존 검사는 backend의 잠금 Python 3.13 환경에서 실행한다. 전역 Python 3.11의 AST 표현 차이는 제품 코드 실패로 해석하지 않는다. 제품 변경이 커밋 SHA로 기록되기 전의 package hash drift는 정확한 후속 증거로 연결하며, 불변 기준이나 검사 자체를 완화하지 않는다.

최초 introduction 캡처에서 이전 마감의 검증 문서 3개가 아직 등록되지 않은 것도 확인했다. 해당 문서는 `ab15b7b6`에서 처음 추가됐으므로 이번 `b9e6142e`가 최초 추가라고 기록할 수 없다. 정식 캡처 도구로 `ab15b7b6`의 문서 3개를 먼저 등록하고, 이어 `b9e6142e`의 오류 변환 모듈·회귀 검사 스크립트·후속 검증 문서 3개를 등록했다. 두 기록 모두 신규 backend test node는 0이며 과거 배열 항목·불변 checkpoint를 유지한다. 첫 실패 로그와 실제 커밋별 성공 로그를 함께 보존한다.

## 재실행과 범위

```powershell
Set-Location 'D:\project_code\angmoo-workspace\angmoo-tree-angmoo'
pnpm --dir frontend test:ui-error-contracts
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend test:user-environment
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test:world-package-proxy
pnpm --dir frontend test:character-card-proxy
pnpm --dir frontend build
pnpm --dir frontend build:static
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_refactor_frontend_preservation.py
uv run --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
Set-Location '.\browser-tests'
pnpm exec playwright test --config playwright.internationalization.config.ts
```

Frontend Next/static build와 두 dev proxy 검사는 같은 checkout의 임시 source/cache를 사용하므로 순차 실행한다. Browser config는 이전 결과를 덮어쓰지 않는 후속 artifact 경로를 사용하며 backend fixture DB는 기존 보호 boundary 안의 `artifacts/multilingual-gemini-20261003/ui-contract-fixes-20261004/browser-data`에 둔다. 작업 소유 fixture는 종료하고 자료는 보존한다. 실제 사용자 Docker·Windows 설치형·DB에는 접근·적용하지 않는다.

P27/R01–R06의 실제 AI·embedding·자연 활동은 계속 `NOT_RUN / FOLLOW_UP`, R07/R08은 `EXCLUDED_SCOPE`다. 실제 API 전송·원격 CI·push/PR/main 병합과 사용자 실행본 배포를 이번 로컬 PASS에 포함하지 않는다.

## 최종 마감

제품 소스의 signoff 로컬 커밋은 `b9e6142e826fba5a7110d8ffcb422003142df261` (`fix(i18n): complete initial locale and validation error contracts`)이다. 마지막 제품 소스에 대한 Next/static build, 브라우저 36 PASS·0 SKIP·0 flaky, 관련 backend 98 PASS·0 SKIP, UI 오류 계약 53 PASS 및 앞의 lint/typecheck/catalog/환경/proxy/구조/design 검사를 완료했다.

| 마지막 공식 검사 | 실제 결과 |
| --- | --- |
| frontend 보존 | exit 0. 고정 소스 파일 324개와 browser assertions/fixtures/assets/locks 보존 |
| backend 보존 `--contracts --nodes` | exit 0. 보호 lineage 4,969개·현재 수집 4,969개 일치, API/ORM·검증식·source/retirement·inventory 37항목 보존 |
| 최종 증거 대조 | browser JSON 36 PASS·0 SKIP·0 flaky, backend XML 98 PASS·0 FAIL/ERROR/SKIP, 두 보존 exit 0 확인. 디자인 보고서 차이는 SHA256 3개뿐 |
| 과거 기준/추가 근거 | 과거 metadata 배열 prefix와 기타 root 속성 동일. 제품 변경의 정확한 source blob 35개·definition 2개·assertion 2개·frontend whole-file 변화 26개, 커밋별 introduction 3+3개를 append-only로 연결 |

정식 검사 구현과 CLI 옵션을 유지하고 잠금 Python 3.13에서 해당 entrypoint를 실행했다. 커밋 원본 수집·보존 검사 orchestration은 같은 process의 immutable Git cache를 공유하며, 검사 단계·조건·수집을 생략하지 않는다. 상세 결과는 `preservation-results.json`, `frontend-preservation-final.log`, `backend-preservation-final.log`, `verification-summary.json`에 보존한다. 이번 전체 테스트 수집 대조를 4,969개 테스트의 새 실행 PASS로 해석하지 않는다.

보존 metadata 2개와 이 문서를 별도 signoff 로컬 마감 단위로 관리한다. 검증 소스 이후의 제품 코드 변화는 없고, 실제 최종 SHA·두 로컬 커밋의 signoff·clean 및 검사 때 metadata hash 일치는 `artifacts/multilingual-ui-contract-fixes-20261004/local-closeout.json`과 최종 결과에 기록한다. 원 workspace 계획의 §21과 관련 수용 조건도 동기화했다.

F01–F04의 구현과 관련 필수 로컬 재검증은 완료다. 외부 유료 Provider 전송은 0회이며 P27/R01–R06의 실서비스·자연 활동 품질과 R07/R08의 제외 범위는 앞의 구분을 유지한다. 작업 소유 backend 18399·Next 3361·static 3362 listener는 종료됐고 격리 DB·기존 실패·최종 PASS 증거는 로컬에 보존한다.
