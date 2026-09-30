# NovelAI 실제 API 테스트 준비와 로컬 검증 기록

사용자가 실제 API 키 테스트를 시작하기 위해 기존 차단과 미해결 검증 경로를 보완하도록 요청했다. `feat/sns-chat-image-integration`의 `09f1f77d34f89187680281c1abb94191e2c75df1`에서 이어 작업했다. 제품 코드 커밋은 `c8c7e3736a990c0a816067ec16fa32a2fadb233b`이며 main은 `1390ca4ddc275d3219b39b389c5368475e013b4c`를 유지한다.

**현재 제품 판정:** 정상 입력·키·계정/비용·사용량 조건을 통과한 NovelAI 생성이 실제 API로 진행할 수 있도록 연결했다. `exact_verified=false`는 그대로 유지하며 정확한 서버 tokenizer/parser 동일성을 입증했다고 표시하지 않는다. 실제 서비스 생성·Anlas 사용량·참조 품질·서버 길이 경계는 아직 검증하지 않았다. 이 결과는 수정한 브랜치 코드에 관한 것으로 설치 앱이나 Docker에 배포한 결과가 아니다.

## 변경과 근거

- agent가 추가했던 무조건적인 `exact_verified=false` 생성 차단을 제거했다. 정확성 증거 상태와 로컬 준비 상태 `generation_available`를 분리했다. 계정 확인이나 성공한 생성으로 정확성 상태를 자동 승격하지 않는다.
- 로컬 검사 자원의 고정 SHA-256은 계속 확인한다. 파일 누락·변조는 실제 차단 조건으로 유지하며 다운로드·환경 우회 옵션을 추가하지 않았다.
- 고정 외형·스타일·negative는 활성화 저장과 연결 확인에서 검사한다. 이번 장면까지 포함한 positive/negative는 intent 접수 때 검사해 오류 입력에 생성 시도를 예약하지 않는다. worker와 adapter도 전송 전 검사한다.
- 기존 검사에서 중괄호가 unknown piece로 처리되는 문제를 보완했다. 공식 `{}`, `[]`, 수치 `::` 문법을 독립 작성한 `v4.5-t5-weight-spans-v1`에서 인식하고 각 텍스트 구간을 기존 T5 자원으로 계산한다. EOS 1개를 포함한 로컬 512 한도를 적용한다. 입력은 자동 축약·번역하지 않으며 API에는 원문 가중치 문법을 그대로 전달한다.
- Opus 전용 무차감 모드의 혜택 확인·Steps≤28·면적≤1,048,576·1장·참조 제외와 유료 경로 자동 전환 금지를 유지했다. Anlas 허용 모드는 사용자의 참조 ON/OFF와 설정을 유지한다.
- 실제 provider 오류를 성공으로 처리하지 않는다. 본문을 보존하고, POST 결과 미확정과 수신 후 로컬 저장 실패의 기존 재제출 방지 계약을 유지한다.
- Next/static의 같은 설정 구성요소에서 로컬 검사 미준비와 서버 동일성 미입증을 구분한다. 후자는 안내를 표시하면서 정상 생성 활성화를 허용한다. 디자인 변경은 `LOCAL`이며 기존 폼·의미 토큰을 사용한다.

공식 근거는 [NovelAI 모델 문서](https://docs.novelai.net/en/image/models/)의 V4.5 T5/약 512 토큰 안내와 [가중치 문서](https://docs.novelai.net/en/image/strengthening-weakening/)의 연산자다. 이 설명은 현재 포함한 Google 자원 해시나 서버의 정확한 parser를 확정하는 근거가 아니다. 로컬 검사 자원·버전·한계는 `backend/app/integrations/novelai_resources/NOTICE.md`에 기록했다.

## 이번 로컬 검증

| 검사 | 결과와 범위 |
| --- | --- |
| 전체 이미지 통합 suite | **155 PASS**. 기존 140개와 새 NovelAI 준비 검사 15개. 원래 재검토의 7개 재현은 AST까지 동일하게 보존했다. |
| 집중 회귀 | **66 PASS**, 전체 suite에 포함되는 중복 실행이므로 다시 합산하지 않는다. |
| 실제 구현 경로를 사용하는 synthetic HTTP | 키·계정 연결 확인→활성화 저장→접수→요청 직렬화→ZIP/JSON 결과 처리→게시글 첨부. 실제 tokenizer/adapter/worker를 사용하고 `exact_verified=true` monkeypatch는 사용하지 않는다. 실제 서비스 결과는 아니다. |
| 로컬 입력 경계 | EOS를 포함한 511/512 통과·513 거절, 가중치 연산자·unsupported text·고정 입력·예약 0을 확인한다. 이 숫자는 로컬 자원의 경계이며 서버와 비교한 결과가 아니다. |
| 결과 미확정·원격 거절 | HTTP 400/500 합성 응답, 본문 보존, 500 재제출 금지, 동일 작업 중복 실행 시 POST 1회. |
| Next/static 브라우저 | **32 PASS**. 정상 로컬 준비+정확성 미입증 상태의 활성화와 저장, 자원 미준비 비활성화, 기존 참조·SNS·Chat 동작 포함. API는 fixture로 응답한다. |
| frontend | typecheck·lint·Next build·static build PASS. |
| 구조·디자인 | backend 1333 modules/5404 edges/legacy 0, frontend 14 features/legacy 0, raw colors 1230/files 36/surfaces 18/route gaps 0/screenshot calls 16 PASS. 디자인 보고서의 해당 구성요소 SHA만 갱신했으며 색상·시각 정책을 완화하지 않았다. |
| 원래 보존 검사 | **protected lineages 4473 / current 4473 / items 37 PASS**. 제품 코드 커밋 `c8c7e373`에서 정확한 product delta·최초 도입 근거를 append하고 원래 전체 checker의 `--contracts --nodes`를 통과했다. Git의 불변 객체 읽기만 캐시했으며 검사 규칙·frozen 자료·현재 소스 읽기는 변경하지 않았다. `preservation.log`에 결과를 보존했다. |

첫 실행의 `143 PASS/9 FAIL`은 `artifacts/novelai-test-readiness-20261001/image-suite.xml`에 보존했다. 새 검사에서 잘못 참조한 `Post.content`를 실제 `body`로 수정하고, 두 조각으로 tokenize되는 `a` 대신 한 조각인 `hello`를 경계 fixture로 사용했다. 이 실행에서 확인한 실제 중괄호 preflight 문제도 제품 코드에서 보완했다. 수정 후 최종 `155 PASS`는 `image-suite-final.xml`이다. 최초 Playwright 실행의 PowerShell reporter 인자 문제는 별도 `browser-launch-failed.log`로 보존했으며 따옴표로 정확히 전달한 재실행 32개가 통과했다.

주요 실행 명령은 다음과 같다. backend 명령은 `backend` 디렉터리, frontend/구조 명령은 제품 저장소, browser 명령은 `browser-tests`에서 실행했다.

```powershell
./.venv/Scripts/python.exe -m pytest -q -p tests.offline_guard tests/image_integration --tb=short --junitxml=../artifacts/novelai-test-readiness-20261001/image-suite-final.xml
pnpm --dir frontend typecheck
pnpm --dir frontend lint
pnpm --dir frontend build
pnpm --dir frontend build:static
./backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py
./backend/.venv/Scripts/python.exe scripts/ci/check_frontend_architecture_boundaries.py
./backend/.venv/Scripts/python.exe scripts/ci/check_frontend_design_contract.py --check
pnpm exec playwright test --config=playwright.image-integration.config.ts --output=../artifacts/novelai-test-readiness-20261001/browser '--reporter=json,list'
```

## 실제 키 테스트의 재개 위치

1. 이 구현 브랜치의 코드를 사용하는 개발 환경에서 NovelAI 키를 비공개 입력으로 저장한다. 설치 앱·Docker에 이 수정이 자동 반영되었다고 가정하지 않는다.
2. 선택한 비용 모드에서 `연결·입력 확인 및 저장`을 다시 수행한다. 과거 차단 때문에 저장된 `ready=false`를 성공으로 간주하거나 DB를 직접 바꾸지 않는다.
3. 캐릭터와 설치 전체의 생성 시도 상한을 확인한다. Opus 모드에서는 혜택을 확인하고 참조 제외를 유지한다. 테스트용 짧은 영어 장면으로 생성·저장·첨부를 우선 확인한다.
4. 실제 요청 수·결과·Anlas 전후 값·실패 분류를 별도 증거로 기록한다. Anlas 사용 허용/참조 경로와 토큰·가중치 경계는 각각 후속 테스트로 구분한다. 한 번의 성공을 정확한 tokenizer 검증이나 모든 설정·품질의 PASS로 확대하지 않는다.

이 기록을 작성한 작업에서 실제 키 읽기/실제 생성·인식 API 호출은 **0회**다. 외부 네트워크를 차단한 임시 DB와 합성 이미지/HTTP만 사용했다. 공식 공개 문서를 확인한 요청은 제품 생성 API 호출과 구분한다. 전체 backend 회귀, 실제 계정 비용, 참조 동일성, 정확한 서버 경계, 설치/배포, USER CHECK는 이번 PASS에 포함하지 않는다. CI·push·PR·main 병합·Docker·설치 데이터 변경은 수행하지 않았다.

기계 판독 요약은 [결과 JSON](novelai-test-readiness-20261001-results.json), 최신 실행 계약은 workspace의 `docs/plan/09-30 SNS·Chat 이미지 생성·인식 통합 코드 구현과 로컬 검증 세부 계획.md` §21이다. 과거 09-30 재검토 검증 문서와 결과 JSON은 당시 결과로 보존한다.
