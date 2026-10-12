# ComfyUI 예시·교체·Partner 전송·Windows 키·CSP·Guide 통합 실행 원장

대상은 workspace의 `10-12 ComfyUI 예시·워크플로 호환과 Partner 키 전송·Windows 보호·CSP·영어 안내 통합 코드 구현 세부 계획.md` I00–I67 및 V00–V33이다. 실행 기간은 2026-10-12–13이며, 제품 시작점은 `feat/0.1.0-release-readiness`, `6d6c6b7487547624365be24dbbd86f20b3707ebf`, clean tree였다. 이 브랜치의 제품 소스와 문서만 수정하고 로컬 커밋한다. push/PR/원격 CI/main merge/fetch/pull/rebase, 설치·배포·사용자 Docker/ComfyUI 재시작은 수행하지 않는다.

필수 구현과 관련 검증을 완료했다. I61은 준비된 격리 ComfyUI가 제공되지 않아 조건 검토를 마치고 실제 custom node/HTTP 실행을 **미측정**으로 남긴다. 설치 앱의 안전성·실모델 품질·USER CHECK·Termux를 fixture PASS로 표시하지 않는다.

## 1. 실제 변경과 보존

- 새 `comfy-api-text.json`/`comfy-api-reference.json`은 독자 builder가 생성하는 순수 graph다. 인증된 `format=api_json`과 UI 다운로드/적용은 같은 UTF-8 JSON을 사용한다. 기존 config 응답과 두 구 파일은 byte/hash를 유지한다.
- 파일/예시 교체는 실제 raw 분석 후 선택 경로를 placeholders/auto output으로 바꾼다. textarea edit/paste는 기존 binding/output을 서버에서 확인하고 보존한다. 같은 graph 재선택, 읽기 실패, duplicate raw, A/B 역전, tab/locale/runtime 수명, CAS 거절을 검증했다. legacy 다른 경로·global CLIP 의미·이미 있는 빈 값/설정·URL/Partner/key draft는 보존한다. 누락된 사용 값만 보완하고 model/VAE 기본값을 만들지 않는다.
- Partner ON 새 전송은 HTTPS 또는 IPv4 127/8, IPv6 ::1, exact localhost만 허용한다. localhost HTTP 새 전송만 127.0.0.1에 고정하고 저장 주소/port/base path는 유지한다. OFF의 keyless HTTP와 허가된 receipt history/view는 유지한다. 저장·활성화·새 키·freeze·최종 HTTP에 정책을 적용하고 key 삭제/OFF/역사 inactive profile 정리를 허용한다. TLS 검증·redirect 금지·일반 서버 key 폐기·owner/scope/lease/credential 폐기 검사를 유지한다.
- 관리 key/helper는 Windows API를 지연 로딩한다. 실제 handle의 물리 경로·DACL·현재 token의 read-open을 확인한다. 필요한 관리 key/디렉터리만 보호하고, temp부터 첫 byte 전에 DACL을 설정한다. 부모 handle을 유지하고 overwrite 없는 hardlink 게시로 동시 생성 winner를 보존한다. 미확인/복잡한 ACL/권한 실패는 원본을 남기고 안전한 오류로 종료한다. 소유권·키·AAD·DPAPI·전체 AppData 정책은 바꾸지 않는다. hardlink가 지원되지 않는 파일시스템에서는 실패를 표시하며 불안전한 덮어쓰기로 전환하지 않는다.
- Next production은 서버 Proxy의 fresh nonce와 enforcing CSP를 사용한다. request/response/HTML bootstrap nonce를 연결하고 client nonce/CSP를 덮어쓴다. HTML은 dynamic/private,no-store다. script unsafe-inline/eval은 production에서 제외하고, 승인된 Google/Cloudflare·style·blob·worker·local WASM 범위는 유지한다. Tauri는 기존 별도 CSP를 유지한다.
- API 안내는 server-only loader/server component와 locale client view를 분리했다. ko/en 원문/미리보기/링크가 일치하고, 기본 KO와 고정 lang whitelist를 유지한다. Guide는 두 literal 파일만 tracing하며 Docker/standalone/static에 포함한다. KO 원문·OpenAPI·bot auth/route/payload·한국어 공개 출력 정책은 유지한다. static의 `/angmoo-api` 미지원 계약도 유지한다.

## 2. 실제 연속 시험의 경계

`scripts/diagnostics/verify_comfy_security_flow.py`는 fresh marked root, synthetic owner/session/Character/World, 암호화한 synthetic Partner key, SQLite/media와 **실제 contributor app/API**를 구성한다. 모든 actor의 자율활동은 OFF다. 외부 scene writer만 고정 scene을 반환하고, fixture driver는 UI의 정상 자동 이미지 활성화 후 새 synthetic post를 동일 `MediaRuntime.admit_post`에 전달한다. 이는 전체 자연활동 planner 품질 시험이 아니다.

ComfyUI만 별도 loopback HTTP mock이다. Angmoo analyze/save/credential/admission/freeze/render/worker/media 조회를 성공 stub하거나 최종 graph/result를 주입하지 않는다. mock은 node/class/link, exact positive/negative/model, 수치 type/default, Base64 decoder/PNG metadata 제거, Partner body 위치를 검사한다. 불일치에는 성공하지 않는다.

각 runtime에서 text와 reference는 독립 Character·설정·intent·receipt·결과다. 실제 화면 다운로드 파일을 native file input에 그대로 재입력하고, 실제 save/read/reload를 거친 뒤 worker가 제출한다. 결과는 red/blue의 별도 PNG이며 실제 저장 후 UI canvas의 decoded pixel까지 확인한다. 각 케이스 prompt 1회, same receipt history running→completed 2회, view 1회, placeholder upload 0회다. JSON key insertion 순서를 역전하고 첫 이미지 batch를 여러 장 반환해 JS ordering/첫 image 선택도 확인한다. receipt와 함께 악성 HTML 모양 warning을 반환해 실제 저장된 진단이 안전한 text로 표시되는 것도 확인한다.

Next와 static은 정확한 frontend origin으로 **각각 fresh fixture backend를 구성**한다. static contributor fixture의 CORS는 그 한 주소만 허용하며 실제 session/CSRF/owner/media scope 검사는 그대로다. 테스트는 한국어/영어, 360/1440px, keyboard/44px을 관련 대표 경로에 결합한다.

## 3. 관련 검증 결과

원본 출력은 ignored `artifacts/comfy-security-20261012/`에 보존한다. 실패했던 시험은 원인과 최종 수정 결과를 구분하며 과거 failed report를 전체 PASS로 합산하지 않는다.

| 묶음 | 실제 결과 | 근거 |
| --- | --- | --- |
| Comfy parser/examples/API/placeholder/Partner/HTTP/save/TLS/Guide/staging | 111 PASS | `backend-final.xml`, `transport-final.xml` |
| Windows 실제 AccessCheck/최초 temp/동시 생성/재시작/경로 교체/미확인/portable IO | 7 PASS | `windows-final.xml` |
| embedded root key/AAD/rollback, Proxy 경계, source CSP, loopback token/origin/fatal, release metadata | 29 PASS | `startup-package-final.xml` |
| Tauri/static 공유 소스·실행 토큰·route/media 경계 | 6 PASS, 17 unrelated node 제외 | `tauri-static-source.xml` |
| 기존 Comfy receipt/lifecycle | 1 PASS, 15 unrelated node 제외 | `receipt-lifecycle-final.xml`; 별도 World vault/save 시험도 PASS |
| Next 실제 text/reference 연속·교체/edit/async | PASS | `verified-next-browser.json` 10 PASS |
| 최종 production CSP/Guide/HEIC/crop/World editor | 3 PASS | `verified-next-browser.json` |
| locale/read/runtime 취소·CAS draft 보존 | 2 PASS | `verified-next-browser.json` |
| static text/reference 연속·editor·World·scope/CAS | 8 PASS; Next 전용 CSP 2개는 의도된 skip | `verified-static-browser.json` |
| production CSP에서 기존 Chat stream/typing UI | 1 PASS | `csp-stream.json` (UI fixture seam이며 자연 AI 품질 근거 아님) |
| frontend architecture/design/catalog/typecheck/변경 파일 lint | PASS | source/check command 결과, canonical visual 11개·raw color 기준·diff threshold 유지 |
| backend architecture | 기존 4건 남음, 새 위반 없음 | 아래 기준선 설명 |

추가 확인: 마지막 key/startup 조합 9 PASS, 실제 metadata/private-root 조합 13 PASS,
바뀐 소스 67개만 분리한 secret/privacy export 검사 `files=67 binary_audited=1 findings=0 fatal=0`.
합성 reference PNG는 독자 작성한 16×16 green 픽셀과 합성 metadata뿐이며 exact hash를 asset manifest에
등록했다. scanner 예외/secret allowlist나 canonical visual threshold는 완화하지 않았다.

기존 backend 구조 위반은 Chat evidence의 Memory deep import, Chat relationship evidence의 Relationships deep import, Identity credentials↔image credentials cycle, Memory activity situation↔source binding cycle이다. 출력의 refactor role 2줄은 앞의 deep import를 다시 지적하는 항목이다. 해당 import/cycle은 시작 HEAD에 이미 있고 이번 파일 변경에서 새로 생긴 것이 아니다. checker나 예외를 완화하지 않는다.

관련 기존 시험의 과거 v29 fixture는 현재 Memory service의 새 deletion table을 읽고, 최신 target을 32로 고정하거나 폐기된 일반 Comfy server key를 현행 송신 resolver로 읽고 있었다. 과거 schema를 직접 seed하고 현재 manifest target/원본 AAD 복호화/의도된 server-key 폐기를 대조하도록 수정했다. 원본 DB/media/key hash는 그대로 비교한다. static source 시험의 graph marker도 현재 World composition 소유 경로에 맞춰 확인하며 직접 router feature import를 되살리지 않는다.

운영 Next 첫 build의 tracing root 문제를 수정했고, Windows의 generated standalone directory symlink 오류는 원본 출력 보존 후 `stage-comfy-next-fixture.mjs`의 fresh LOCAL runtime에서 project dependencies를 재사용해 검증했다. 이는 Windows packaged dependency payload 인증이 아니다. 최종 literal Guide trace에는 두 Guide만 있다. 관련 source 변경/packaging 추적 수정으로 필요한 build를 다시 수행했으며 blanket backend/frontend/browser suite는 실행하지 않았다.

## 4. 실제 설치·측정·조건부 범위

- read-only installed identity helper에서 설치 실체를 verified UNC 경로로 확인했다. running identity는 검사 때 not_observed였다. 일반 AppData의 Codex LocalCache view를 실제 실행 설치로 해석하지 않았다. 실제 DB의 내용·key byte는 읽지 않았다.
- key 자체도 최종 physical handle 경로를 확인했고 현재 token의 read-open은 가능했다. DACL에는 보호 기준에 맞지 않는 일반 주체 grant가 남아 **unsafe_access=true**였다. 실제 설치 key/ACL/소유자/데이터는 변경하지 않았다. 새 소스/fixture 보호 PASS가 기존 설치본에 적용됐다고 주장하지 않는다.
- Windows ordinary access는 실제 restricted-token AccessCheck로 확인했다. 다른 Windows 계정을 생성하거나 프로세스를 impersonate하지 않았다. portable IO 분리는 real file IO+permission-call port로 확인했으며 실제 Linux filesystem ACL 측정과는 구분한다.
- LOCAL 비용: 관리 key 생성 약 43.307ms, 기존 key inspection 평균 약 0.997ms(10회). helper 호출자는 startup/managed migration이며 Chat/SNS 매 활동에 검사하지 않는다. warm production `/login` 5회 HTTP는 평균 약 16.72ms, nonce는 5개 모두 달랐다. 이 수치는 배포 벤치마크가 아니다. dynamic HTML/no-store에 따른 SSR/cache 비용을 수용한다.
- V31: 이미 준비된 **격리** ComfyUI/custom node가 없어 실제 decoder 실행은 미측정이다. 사용자 ComfyUI/GPU를 호출하거나 노드/model을 설치하지 않았다.
- V32: 실제 GPU 품질, 사용자 node/model 버전, Partner 실제 인증/결제, 설치 native CSP 적용, 현재 후보 Windows payload, 직접 USER CHECK, 전체 공개 보안 감사는 미측정이다.
- V33: Termux 권한/CA/browser/재시작/Doze는 후속 배포 범위다.

## 5. 보존 hash와 출처

| 파일 | SHA-256 (Windows 시작/종료 동일성 또는 새 LF asset) |
| --- | --- |
| 기존 comfy-text.json | `953805b53bc6eb11b02fb977f430118cdda01901a7998323a9711d25cf1908c0` |
| 기존 comfy-reference.json | `81b7b1275065de9e3e624bf55eaae038410ef142302a3d49e8ebf1c877b4c602` |
| 새 comfy-api-text.json | `4e2f10accb455b9cebd640604395de381c319ab7e7f9322c615b2c72419e9c72` |
| 새 comfy-api-reference.json | `140b284d0bb1f4ef4138538217cc4db1687bf54e3b840fcd308dda49a5ed0f5d` |
| 기존 Korean Guide | `ca25514ada855edc157bd843f9c6a98b1a16c827076bd2a387e918172f3fa6a3` |
| English Guide | `abe6c16264c2f4a979d53300452269449cc608d545adf7d7d94e33b21faa4c91` |

기존 sample의 Git LF checkout hash도 별도 테스트에서 확인하며 원본 Windows bytes의 baseline을 바꾸지 않는다. 새 sample만 eol=lf다.
ETN 계약은 [공식 nodes.py](https://raw.githubusercontent.com/Acly/comfyui-tooling-nodes/b3ae4aa2d98f6ac4284ddbe261e3559c94bd652b/nodes.py)의 STRING image, IMAGE output 0을 읽어 확인했다. source SHA-256은 `296330305db27e8b457c7b26856dff2fb5fcdf232612a1a7b3ca3c2a85124474`다. 외부 코드/JSON을 복사·실행·설치하지 않았다. `samples/README.md`에 독자 graph provenance를 기록했다.

원본 SEC/WF 계획 SHA-256은 각각 `10016b65c6acc83cf8e89f49b9811391e79a87cfce131d1ec081ffb9e5eaa7a6`, `1c0e148eae45fed459a0f72d2cb2b528e755a0c14132d14d6b762270da806eaa`이며 원본은 수정하지 않는다. 원본 단계 대응은 통합 계획 §13의 SEC 40개/WF 36개 매핑을 그대로 사용한다.

## 6. 재현 절차와 범위

제품 root에서 관련 pytest 파일만 선택한다. `backend-final.xml` 그룹은 `test_comfy_samples`, `test_comfy_placeholders`, `test_comfy_partner`, `test_comfy_http_contracts`, `test_comfy_transport_security`, `test_comfy_security_saves_tls`, `test_comfy_guide_contract`, `test_comfy_packaging_privacy`다. Windows/startup/metadata는 위 해당 node만, lifecycle은 `-k comfy`를 사용한다.

```powershell
$env:PYTHONPATH='backend'
uv run --project backend --no-sync python scripts/diagnostics/verify_comfy_security_flow.py --root artifacts/comfy-security-20261012/fresh-next
# Next: a fresh marked data root, frontend origin 3440. Static must use another
# fresh root with --origin http://127.0.0.1:3441 after stopping ONLY this helper.

$env:ANGMOO_NEXT_DIST_DIR='.next-comfy-security-locked'
$env:ANGMOO_API_BASE_URL='http://127.0.0.1:3443'
pnpm --dir frontend build
pnpm --dir frontend build:static
node frontend/scripts/stage-comfy-next-fixture.mjs .next-comfy-security-locked artifacts/comfy-security-20261012/fresh-next-runtime
$env:HOSTNAME='127.0.0.1'
$env:PORT='3440'
node artifacts/comfy-security-20261012/fresh-next-runtime/frontend/server.js
# Separate owned terminal: node frontend/scripts/serve-static.mjs --port 3441
pnpm --dir browser-tests exec playwright test --config playwright.comfy-security.config.ts --project next
pnpm --dir browser-tests exec playwright test --config playwright.comfy-security.config.ts --project static
pnpm --dir browser-tests exec playwright test --config playwright.comfy-csp-smoke.config.ts
```

fixture server는 fresh root만 받으며 재사용/사용자 설치 root를 거절한다. AAD/user-key/source를 실제 사용자 데이터에서 가져오지 않는다. exact origin 때문에 Next/static fixture backend는 별도로 시작한다. locale/scope/CAS/World 시나리오는 유료 생성 없이 실행한다. 빌드가 추가한 일회성 tsconfig dist 항목은 커밋하지 않는다. 원본 process/3000/Docker/ComfyUI/설치 앱은 중지하지 않는다.

아래 단계/V 원장은 각각 68개/34개 ID를 정확히 한 번 기록한다. 로컬 Git commit 및 최종 clean 상태는 외부 통합 계획의 실행 결과와 최종 응답에 기록하며 원격 상태와 섞지 않는다.

## 7. I00–I67 단계 원장

| ID | 수행 작업 | 상태 | 근거 묶음 |
| --- | --- | --- | --- |
| I00 | 지정 product 브랜치·HEAD·dirty/untracked·병행 작업을 확인한다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I01 | §2의 설계·AGENTS·현재 Next 버전·지원 route·설치 identity 절차를 읽는다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I02 | §1.1의 8개 확정과 모든 SEC S/WF C 계약을 fixture·입력/출력 기준으로 고정한다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I03 | 현행 file 교체 binding/output 잔존, remote HTTP Partner, 오래된 설정, 현재 CSP/영어 기준 회귀를 마련한다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I04 | 두 예시 연속 시나리오의 실제 app 경로와 외부 AI/ComfyUI mock 경계를 설계한다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I05 | 관련 backend/browser/packaging baseline·원본 asset hash·원본 계획 ID 대응을 기록한다. | 완료 | 시작 Git/8계약/원본 hash·fixture 설계 |
| I06 | 순수 Partner 주소 분류와 조건부 localhost 송신 target을 구현한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I07 | Character/World 저장에 새/변경/활성 profile 검사와 안전한 OFF/key 삭제를 조립한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I08 | 새 admission/freeze/readiness에 동일 전송 규칙을 적용한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I09 | integration의 upload/submit callback/prompt 앞 guard와 일시 target을 적용한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I10 | receipt 복구 분기를 신규 key 필요·전송 검사와 분리한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I11 | Media ko/en 오류·HTTPS/loopback·서버 신뢰 안내를 기존 draft 수명과 연결한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I12 | 정책·송신·CAS·정리·IPv6/Docker alias·receipt 기준 회귀를 수행한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I13 | 예시/raw 분석과 실행 보안의 API 경계를 확인·고정한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I14 | legacy 읽기·불변 snapshot·credential/key revision의 공통 보존 계약을 정리한다. | 완료 | Partner target/save/freeze/HTTP/receipt/API 계약 및 회귀 |
| I15 | 기존 예시 builder legacy 출력을 보존하고 새 순수 graph builder를 분리한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I16 | 새 `comfy-api-text.json`의 연결·토큰을 작성한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I17 | 새 `comfy-api-reference.json`의 decoder·scale·VAEEncode·텍스트 조건을 작성한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I18 | builder 결정성·hash·core/custom node·독자 작성 근거를 확인한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I19 | 인증된 sample API의 고정 kind/format·legacy 응답을 구현한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I20 | frontend ApiGraph 조회·AbortSignal·공통 raw 직렬화를 연결한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I21 | sidecar/Docker의 새 sample 포함 경로와 구 파일/provenance 보존을 확인한다. | 완료 | 독자 pure graph builder/assets/auth format/packaging/provenance |
| I22 | Media 경로별 raw/source/edit-replace/revision/last-good 상태를 구성한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I23 | 파일 입력을 명시적 교체와 실제 raw 분석에 연결한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I24 | 두 예시 적용을 파일과 같은 교체 경로에 연결한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I25 | textarea edit/paste와 명시적 mode 변경의 설정 보존을 구현한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I26 | legacy의 명시적 교체 시 v2 전환·다른 경로 보존을 구현한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I27 | 누락 값 보완·global CLIP mode·seed 준비 의미를 연결한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I28 | 자동 output 초기화·고급 명시적 output·삭제 노드 오류를 연결한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I29 | invalid raw·read/analysis 실패·두 경로·CAS·dirty/leave guard를 연결한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I30 | read/sample/analysis의 scope/revision·abort·debounce를 통합한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I31 | 같은 raw 문자열의 예시 JSON 다운로드를 추가한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I32 | 기본 placeholder·고급 binding·legacy 안내를 기존 control에 정리한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I33 | 참조 예시의 추가 노드·PNG Base64·파일명 방식·model 요구 안내를 적용 전에 표시한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I34 | 기존 번역 key를 재사용하고 새 ko/en·label/error·기술 용어를 함께 반영한다. | 완료 | 공통 editor 교체·편집·legacy·scope·download·ko/en |
| I35 | 합성 Windows 환경에서 key 생성/임시/이전·staging 경로와 접근 기준을 조사한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I36 | 가능한 실제 설치본은 identity 확인 후 정확한 key 경로를 read-only 점검한다. | 조사/대조 완료 · 설치 적용/후보 별도 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I37 | 안전/부족/미확인 분기를 결정하고 조건부 구현 범위를 고정한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I38 | 부족한 경우 Windows DACL·보호된 최초/임시 생성 helper를 구현한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I39 | 필요한 startup/migration 호출자에만 helper를 조립한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I40 | staging·metadata·진단의 managed-secret/temp/runtime 경로 검사를 보완한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I41 | 합성 key/DB의 재시작·동시 생성·권한 오류·legacy/local-v2 복호화 회귀를 수행한다. | 완료 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I42 | 실제 설치 ACL과 후보 payload 검사 결과를 별도로 기록한다. | 조사/대조 완료 · 설치 적용/후보 별도 | Windows 실제 접근/atomic·migration·staging·설치 read-only 결과 |
| I43 | Next 서버 전용 nonce/CSP helper와 Proxy를 구현한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I44 | 필요한 Next HTML 동적 렌더링을 연결한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I45 | 중복 CSP·nonce HTML cache·nosniff·dev 정책을 정리한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I46 | 승인 script/frame·API·crop style·blob·WASM을 필요한 최소 범위로 연결한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I47 | 새 JSON/Guide/diagnostic·이름/메시지의 합성 XSS 회귀를 작성한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I48 | Tauri hash/nonce·loopback 인증의 기존 정책/관련 시험을 보존한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I49 | production Next CSP 검증 harness와 assertion을 완성한다. | 완료 | 최종 production nonce/CSP·bootstrap·XSS·WASM·Tauri source |
| I50 | 기존 API 안내 Support 번역을 locale view에 연결한다. | 완료 | Support locale/영문 Guide/fixed lang/packaging·의미 보존 |
| I51 | 영어 Guide를 작성하고 KO의 auth/route/필드/예시/AI 언어 의미와 대조한다. | 완료 | Support locale/영문 Guide/fixed lang/packaging·의미 보존 |
| I52 | 고정 lang reader/route와 같은 언어 preview/download·packaging을 연결한다. | 완료 | Support locale/영문 Guide/fixed lang/packaging·의미 보존 |
| I53 | Media `service agreement` 및 관련 generic key/Partner 용어를 ko/en으로 수정한다. | 완료 | Support locale/영문 Guide/fixed lang/packaging·의미 보존 |
| I54 | 관련 locale·draft·scope·지원 route·keyboard 시험을 완성한다. | 완료 | Support locale/영문 Guide/fixed lang/packaging·의미 보존 |
| I55 | 관련 graph/API/render/legacy/Partner/Windows/privacy backend 시험을 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I56 | 관련 replace/edit/download/invalid/async/CAS·scope 브라우저 회귀를 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I57 | 최종 변경 기준으로 production Next를 한 번 준비하고 필요한 static artifact를 준비해 관련 시나리오를 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I58 | graph 가져오기와 Partner 정책·keyless HTTP·OFF/key 삭제·receipt의 교차 회귀를 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I59 | 텍스트 예시의 필수 연속 사용자 시나리오를 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I60 | 참조 예시의 필수 연속 사용자 시나리오를 독립 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I61 | 이미 준비된 격리 ComfyUI에서 추가 노드의 실제 decoder 통신 검증 가능 여부를 판단·수행한다. | 조건 검토 완료 · 실제 V31 미측정 | 관련 backend/browser/두 연속 사례·구조검사 |
| I62 | 관련 구조·디자인·catalog·typecheck·변경 파일 lint·diff·privacy 검사를 실행한다. | 완료 | 관련 backend/browser/두 연속 사례·구조검사 |
| I63 | 실제 설치 identity/ACL·후보 payload/CSP와 미확인 출시 근거를 재검토한다. | 조사/대조 완료 · 설치 적용/후보 별도 | 설치/조건부 근거·아키텍처/LOCAL·실행 원장·선별 로컬 Git |
| I64 | architecture/design/LOCAL·사용자 안내에 실제 구현과 출처·Termux 유예를 기록한다. | 완료 | 설치/조건부 근거·아키텍처/LOCAL·실행 원장·선별 로컬 Git |
| I65 | 통합 verification 문서에 단계·명령·시험·두 연속 결과·hash·비용·미측정을 기록한다. | 완료 | 설치/조건부 근거·아키텍처/LOCAL·실행 원장·선별 로컬 Git |
| I66 | 이번 제품 파일만 선별 로컬 커밋하고 branch/HEAD/diff/다른 dirty 보존을 확인한다. | 완료본 · 최종 로컬 Git/보고 대조 | 설치/조건부 근거·아키텍처/LOCAL·실행 원장·선별 로컬 Git |
| I67 | I00–I66·V matrix·원본 대응·조건부/유예를 대조하고 결과를 보고한다. | 완료본 · 최종 로컬 Git/보고 대조 | 설치/조건부 근거·아키텍처/LOCAL·실행 원장·선별 로컬 Git |

## 8. V00–V33 판정

| ID | 판정 | 관찰 경계 |
| --- | --- | --- |
| V00 | 관련 계약 PASS | 독자 graph/source hash/builder 재생성 |
| V01 | 관련 계약 PASS | 인증 sample format/read-only API |
| V02 | 관련 계약 PASS | strict raw duplicate/nonfinite/wrapper/limits |
| V03 | 관련 계약 PASS | 14 exact typed token·metadata/link/fixed graph |
| V04 | 관련 계약 PASS | text 실제 render·원문 보존 |
| V05 | 관련 계약 PASS | 참조 metadata 제거·decoder·owned scope 거절 |
| V06 | 관련 계약 PASS | JS output/receipt/history/view/malformed terminal |
| V07 | 관련 계약 PASS | legacy/v2/seed/CLIP/frozen snapshot |
| V08 | 관련 계약 PASS | 실제 download 파일/동일 파일/예시 replace |
| V09 | 관련 계약 PASS | edit/output deletion/duplicate raw/CAS 입력 보존 |
| V10 | 관련 계약 PASS | A/B/tab/locale/runtime·Character/World scope |
| V11 | 관련 계약 PASS | body key 위치/진단 redaction/참조·limits·draft |
| V12 | 관련 계약 PASS | ON/OFF·loopback/HTTPS/alias/위장 host |
| V13 | 관련 계약 PASS | 각 reference/fallback guard의 외부 요청0 |
| V14 | 관련 계약 PASS | 실제 TLS CA/hostname 실패·no redirect |
| V15 | 관련 계약 PASS | Character/World 활성·새 키·정리·CAS rollback |
| V16 | 관련 계약 PASS | freeze/admission·unsafe historical new submit 거절 |
| V17 | 관련 계약 PASS | keyless receipt·원래 endpoint·원래 owner/lease/폐기 |
| V18 | fixture PASS · 설치 DACL 부족 실측/무변경 | native Windows AccessCheck·physical installed key read-open/DACL |
| V19 | 관련 계약 PASS | atomic/concurrent/temp/parent race/unverified/AAD·portable IO |
| V20 | 관련 계약 PASS | 실제 metadata sentinel 거절·public assets/Guides staging |
| V21 | source/static PASS · 실제 적용 미측정 | Tauri CSP source/정적 build·실제 packaged 적용 미측정 |
| V22 | 관련 계약 PASS | 기존 launch token/origin/fatal/metadata |
| V23 | 관련 계약 PASS | 최종 production CSP/fresh nonce/all bootstrap/404/header spoof |
| V24 | 관련 계약 PASS | 실제 React JSON/진단·CSP script/onerror·Guide/stream/crop/HEIC WASM |
| V25 | 관련 계약 PASS | ko/en Guide preview/raw/link/whitelist/동등 meaning |
| V26 | 관련 계약 PASS | World/Character Next/static·ko/en·360/1440·keyboard·44px·draft |
| V27 | frontend PASS · backend 기존 4건 유지 | 구조/design/catalog/type/lint/diff/privacy·기존 4건 분리 |
| V28 | 관련 계약 PASS | ON unsafe/OFF keyless·세 ref mode·withdrawal/receipt 교차 |
| V29 | 관련 계약 PASS | Next/static text download→file→real save→admit→render→PNG pixels |
| V30 | 관련 계약 PASS | Next/static reference의 독립 실제 연속·Base64/scene·PNG pixels |
| V31 | 조건 검토 완료 · 미측정 | 준비된 격리 Comfy/custom node 없음; 실행/설치/GPU 없음 |
| V32 | 미측정 경계 기록 완료 | 실모델/Partner 결제/설치 CSP·후보·USER CHECK·전체 감사 분리 |
| V33 | 명시적 유예 | Termux 후속 배포/권한/CA/Doze 범위 |
