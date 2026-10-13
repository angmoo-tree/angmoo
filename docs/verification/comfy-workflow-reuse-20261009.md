# ComfyUI 자리표시자·워크플로 재사용·첫 이미지 출력 구현 기록

대상 계획: workspace `docs/plan/10-09 ComfyUI 자리표시자·SillyTavern 워크플로 재사용과 첫 이미지 출력 선택 코드 구현 세부 계획.md`의 I00–I31, V00–V12.

기준선: `feat/0.1.0-release-readiness`, HEAD `547ef4c75d0ad9eca9c017709cee7bb30b2cb843`, 작업 시작 시 변경 없음. 제품 저장소는 `angmoo-tree-angmoo`이며 workspace 문서 루트와 구분한다. 모든 작업은 이 로컬 브랜치에서 수행한다. 원격 push·PR·CI workflow·main merge·fetch/pull/rebase는 수행하지 않는다.

상태: **I00–I31 총32개 구현 단계와 V00–V12 총13개 필수 검증 묶음 완료 — 2026-10-09.** 재개 시 I00–I29는 완료됐고 I30·I31이 남아 있었다. 기존 백엔드 보존 PASS를 유지한 채 프론트엔드 원본 보존 검사를 재개해 324개 파일 PASS·exit0를 확인하고, 완료 표·사용법·증거·로컬 커밋 기록을 마무리했다. 아래 미측정 AI/native/Docker 범위는 이 완료 판정과 구분한다.

## 1. 최종 동작과 소유권

- `domains/media/generation_contracts.py`: 이전 무버전 직접 binding/단일 출력 계약과 명시적 v2 placeholder/node_binding/자동·직접 출력 계약을 함께 지원한다. 저장된 legacy를 조회하면서 바꾸지 않는다.
- `domains/media/service/comfy_workflows.py`: raw JSON 중복 키·유한 숫자·크기/복잡도, typed 경로, 필요한 역할, 한 번 준비한 seed/CLIP, 출력 정책, 실행 snapshot을 소유한다. `node.inputs` 안의 전체 문자열이 지원 토큰과 일치할 때만 치환한다.
- `domains/media/service/http_workflows.py`: framework가 중복 키를 지우기 전 Character/World Comfy 설정의 raw 요청을 검사한다. 다른 제공사의 기존 JSON decoding 계약을 바꾸지 않는다.
- `runtime/media/composition.py`, `world_generation.py`, `runtime/world_characters/image_policy.py`: 실제 owner/World/credential/ref/revision/한도 확인과 설정·실행 연결을 맡는다. 외부 await 전에 읽기 transaction을 종료한다.
- `integrations/comfy_images.py`: 연결·선택적 후보 조회·제출·history·첫 출력 다운로드를 맡는다. class/input type, link compatibility, 설치된 모델/custom node 등의 실행 조건은 ComfyUI `/prompt`에 위임한다. input 이름의 token/api_key 또는 object_info `api_node`만으로 Partner나 위험을 추정하지 않는다.
- `schemas.py`, `integrations/comfy_diagnostics.py`: bounded DTO와 whitelist/민감값 가림을 맡는다. Social worker가 동일 lease의 receipt·진단·spool/결과를 저장하고 복구한다. 기존 상한/사용량·권한·중복 방지 규칙은 유지한다.
- `features/media/components/comfy-editor.tsx`: Character/World가 공유하는 JSON 가져오기·직접 수정·분석·필요 값·출력·안내 화면이다. 오류 원문은 보존하고 마지막 정상 graph와 별도로 관리한다. 파일 import와 paste가 같은 endpoint를 사용한다. scope별 key/AbortSignal로 늦은 응답을 격리한다.
- `generation-status.tsx`와 Social의 기존 view slot: 이미지가 붙은 작업도 warning을 확인할 수 있다. 이미 표시된 결과의 초기 조회가 다시 feed 갱신을 발생시키지 않는다. 사용자 업로드만 있는 글은 불필요한 작업 조회를 추가하지 않는다.

아키텍처 문서와 디자인 계약을 함께 갱신했다. facade/shared 계층, 별도 앱 서버, 외부 설정 DB, 자체 ComfyUI type engine, 오류 후 자동 workflow 변경을 추가하지 않았다. 신규 Alembic 0110과 embedded SQLite v33만 추가하고 기존 migration/manifest는 그대로 보존한다.

## 2. 설정과 기존 데이터 사용법

1. Character 또는 World 이미지 생성 설정에서 ComfyUI를 선택한다. 서버 기본 URL, 필요한 경우 서버 접속 키를 입력한다. Partner 인증은 명시적으로 ON한 경우에만 별도 계정 키를 사용한다.
2. ComfyUI의 API 형식 JSON을 파일로 불러오거나 편집창에 붙인다. 일반 UI workflow 형식은 API 형식 안내로 거절한다. 토큰 없는 고정 프롬프트 workflow도 저장·제출할 수 있다.
3. `%prompt%`, `%negative_prompt%`, `%model%`, `%vae%`, `%width%`, `%height%`, `%steps%`, `%scale%`, `%sampler%`, `%scheduler%`, `%seed%`, `%denoise%`, `%clip_skip%`, `%char_avatar%`의 사용 위치만 채운다. 부분 문자열, 파일명 날짜 표현, 미지원 변수, `_meta`와 graph 링크는 바꾸지 않는다. SillyTavern 사용자 설정을 가져오는 기능은 없다.
4. 사용하는 값만 입력한다. 후보 조회가 실패해도 직접 입력할 수 있다. 연결 확인은 `/system_stats`와 앱 입력 준비를 확인하며 이미지 생성·upload·seed 추첨을 실행하지 않는다. 실행 가능성은 제출 시 ComfyUI가 판단한다.
5. seed -1은 접수 시 한 번 추첨한다. 신규 skip_count의 CLIP 1/2는 실제 노드 -1/-2다. legacy와 명시적 node_value는 그대로 전달한다. 기존 설정 전환 버튼은 node_value를 유지하며 부호를 추측하지 않는다.
6. 참조는 지정 이미지 → 카드 PNG → 프로필 순서다. OFF이면 찾지 않는다. placeholder 참조는 metadata를 제거한 픽셀 PNG의 bare Base64다. legacy/direct binding의 참조는 기존 파일명 upload 계약이다. 참조가 없으면 제출 전에 등록된 텍스트 대체 경로를 선택한다. 실행 실패 후 경로를 바꾸지 않는다.
7. 신규 기본은 첫 이미지 자동 선택이다. 고급 출력에서 지정 노드 첫 이미지로 바꿀 수 있다. legacy는 해당 노드에 정확히 한 장이어야 한다. 첫 이미지의 오류/다운로드 실패가 두 번째 이미지로 대체되는 일은 없다.

실제 값·경로·graph digest·output·seed/CLIP은 기존 intent JSON에 고정된다. 키와 참조 바이트/Base64는 snapshot에 저장하지 않는다. credential/ref revision과 World admission 경계는 기존 요청 필드로 검사한다. 이전 receipt 작업은 history로만 회수하고 미제출 작업만 lease transaction에서 snapshot을 보완한다.

## 3. 구현 단계별 증거

| 단계 | 구현·증거 |
|---|---|
| I00 | 위 Git 기준선과 branch 확인. 원본 DB/키·앱/컨테이너를 작업 대상으로 사용하지 않음. |
| I01 | backend/frontend ARCHITECTURE, DESIGN, AGENTS 및 관련 shell/design/preservation 문서 읽기. 역할/소비자 지도는 §1·§8. |
| I02 | 공식 release commit/blob 2개와 고정 커뮤니티 3개 hash·출처·수집 방식 기록. §5. |
| I03 | legacy/v2 discriminant·output·diagnostic·snapshot DTO, serialize/restore, 유한 숫자와 snapshot 오염 회귀. |
| I04 | strict raw 분석 endpoint와 raw 쓰기 guard. duplicate/depth/API 형식/auth 회귀. |
| I05 | 14 exact 토큰, 반복·중첩 typed 위치, literal 점/슬래시 키, 링크/metadata/원본 보존 회귀. |
| I06 | 공통 required_roles와 실제 positive/negative. no-token/no-prompt 및 사용하지 않는 역할 요구 없음. |
| I07 | seed 1회와 CLIP 1회 변환, legacy 그대로, snapshot round-trip, World admission의 추첨 1회. |
| I08 | 픽셀 PNG Base64 1회, 반복 참조·임의 노드 이름, metadata 제거, 권한/크기/legacy 파일 형식 회귀. |
| I09 | primary/text 경로의 독립 입력 모드·역할, 실제 ref 상태로 제출 전 선택. 결과 오류 후 fallback 없음. |
| I10 | HTTP(S)·Docker host 이름·base path, userinfo/query/fragment/잘못된 port 거절. 실제 Docker DNS는 미측정. |
| I11 | system_stats/candidate 상태 분리. 후보 503에도 ready; check의 GET 외 제출/upload 0회. 늦은 UI 응답 fence. |
| I12 | 명시적 Partner ON/OFF, 별도 purpose/credential revision, 서버 key와 Partner payload 분리. |
| I13 | Character/World profile 저장·참조/ready·revision 계약, 기존 무전환과 명시 전환 회귀. |
| I14 | 두 runtime 실제 admission·저장 JSON 재로드·frozen 입력·key/ref/World fence와 기존 receipt 복구. |
| I15 | 공통 제출 payload. token_normalization/union/custom/link 실행 조건의 서버 위임. |
| I16 | JS index key 경계/일반 key·Unicode·5,000자리 숫자 문자열 순서, auto/direct/legacy 출력, MIME/size/pixels/path 검증. |
| I17 | HTTP 400·5xx·valid receipt+warning, bounded errors/redaction·history terminal/pending 구분. |
| I18 | nullable provider_diagnostic_json, Alembic 0110·embedded33 registry/manifest와 frozen32 빌더. 이전 row/원본 staging 보존. |
| I19 | worker CAS receipt/diagnostic, 정상·미확정·terminal·spool 복구, 미제출 enrichment·재제출 방지. |
| I20 | bounded 조회 DTO, 저장된 오염 진단 미노출, frontend 안전한 오류/진단 types와 plain text 표시. |
| I21 | 기존 image suite. 서버 검사 위임으로 바뀐 full-graph 거절 기대만 변경하고 legacy/upload/privacy/다른 제공사 회귀 유지. |
| I22 | 합성 mock 회귀, 실제 HTTP adapter, actual Character/World 저장과 worker 호출·입력 일치. |
| I23 | 공통 import/paste/editor, invalid 원문 유지·수정·save gate, legacy 무전환. Next/static 회귀. |
| I24 | 필요 값/수동 후보/CLIP/참조 안내와 접힌 고급 출력. 고정 prompt·미지원 표현 보존. |
| I25 | Character/World 공통 editor, 이미지 첨부 후 warning·불필요한 갱신 없음·scope fence. |
| I26 | ko/en paired catalog/error, 44px/focus/semantic 토큰, label/오류 ARIA와 내부 scroll. |
| I27 | Next/static build 및 두 UI의 import/edit/save·legacy·late response·warning·반응형 회귀. |
| I28 | 고정 외부 자료 5개를 제품 DTO/renderer/capture/client/HTTP mock 경로로 시험. 5/5 PASS, AI0. |
| I29 | 실제 ComfyUI no-model LoadImage→ImageScale→SaveImage, HTTP 오류, receipt/history/view, AI0. |
| I30 | 완료. 최종 소비자 검색·architecture/design/inventory 및 backend/frontend 보존 검사 PASS, V00–V12 취합. 최종 결과는 §4. |
| I31 | 완료. 이 기록·아키텍처·계획의32단계/13검증 완료 표와 정확한 출처·보존 ledger를 저장하고 별도 로컬 문서 커밋으로 마무리. 커밋 기록은 §9. |

## 4. 로컬 검증

최종 코드의 image/World/migration 묶음 **352 PASS**(228.25초, 기존 TestClient deprecation warning 2개)다. 마지막 출력 ID 수정 후 다시 실행한 결과이며 앞선 실행을 합산하지 않는다. Next/static 브라우저 **56 PASS**와 ko/en·360/1440px 시각 캡처·확인 전후 상태의 후속 **4 PASS**를 얻었다. lint·typecheck, 16 namespace/2,705 key 번역 검사, 53개 UI 오류 계약, Next/static 빌드와 개별 architecture/design/embedded migration 검사도 통과했다. 기존 11개 canonical PNG와 tolerance는 변경하지 않았다. 백엔드 source/API/ORM/test 보존은 37개 항목·5,684개 test node, 프론트엔드 원본 보존은 324개 source files·browser assertions/fixtures/assets/locks로 모두 통과했다.

| ID | 판정/증거 |
|---|---|
| V00 | PASS. backend/frontend architecture·inventory·semantic design, lint/typecheck/catalog/errors, Next/static build. 백엔드 보존37개 항목·5,684개 test node, 프론트엔드 보존324개 파일 PASS. |
| V01 | DTO·raw decoder·auth·duplicate/depth/size·legacy 읽기·migration 회귀 PASS. |
| V02 | 합성 14토큰·typed 경로·원본/연결/metadata·부분/미지원 표현 보존 PASS. |
| V03 | Character/World actual 입력·snapshot·한 번 seed/CLIP·고정 graph PASS. |
| V04 | ref privacy/OFF/권한/형식/PNG Base64/fallback/legacy 회귀 PASS. |
| V05 | URL·GET-only 확인·후보 실패·scope fence PASS; 실제 Docker DNS 미측정. |
| V06 | 서버 graph 검사·명시적 Partner와 키 계약 mock PASS. |
| V07 | 출력 순서·첫 결과·legacy-single·파일/pixels 제한 PASS. |
| V08 | receipt·HTTP/history·bounded/redacted/nullable 진단·worker/spool·unknown PASS. |
| V09 | 기존 Provider·profile/privacy/worker·migration 포함 최종 백엔드 352 PASS. |
| V10 | Next/static 브라우저 56 PASS, ko/en 좁은/넓은 화면 캡처 후속 4 PASS. PNG 확인과 키보드·내부 scroll·import/edit/legacy/late response/warning 포함. |
| V11 | 외부 고정 자료 5/5 mock PASS. 원본의 실제 AI/custom-node 실행 미측정. |
| V12 | 실제 ComfyUI no-model PASS. 모델 다운로드·모델 추론·외부 AI 0회. |

로컬 명령은 repository root에서 실행한다. `scripts/ci` 파일의 로컬 실행은 GitHub CI 실행과 구분한다.

최종 실행 증거는 제품 저장소의 `artifacts/`에 보존한다. 이전 중단·실패 로그와 최종 성공 로그를 구분하고, 로그가 없는 상태를 통과로 해석하지 않는다.

| 최종 증거 | 확인 내용 |
|---|---|
| `comfy-final-backend.txt` | 마지막 출력 ID 수정 후 352 PASS, 228.25초. |
| `comfy-browser.txt` | Next/static 전체 56 PASS. |
| `comfy-final-browser-readiness.txt` | 확인 전후 표시·ko/en·시각 캡처의 기존 시나리오 후속 4 PASS, 22.8초. |
| `comfy-final-architecture.txt` | 1,469 modules/6,268 edges, legacy exact edges 0. |
| `comfy-final-lint.txt`, `comfy-final-typecheck.txt` | 마지막 화면 수정 후 lint/typecheck 성공. |
| `comfy-final-next-build.txt`, `comfy-final-static-build.txt` | 마지막 화면 수정 후 Next/static 빌드 성공. |
| `comfy-preservation.txt` | 백엔드 원본 보존 검사 PASS: 37 items, protected/current nodes 각5,684. 이어진 프론트엔드 결과는 기록되지 않아 이 로그만으로 통과를 주장하지 않는다. |
| `comfy-final-frontend-preservation.txt` | 재개한 원본 프론트엔드 보존 검사 PASS·exit0: 324 source files; browser assertions/fixtures/assets/locks preserved. |

```powershell
uv run --directory backend python -m pytest -q tests/image_integration tests/social/test_world_configuration_inputs.py tests/migrations/test_comfy_diagnostics_v33.py tests/migrations/test_situation_recovery_v32.py
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
uv run --project backend python scripts/ci/check_embedded_data_migration_contract.py
uv run --project backend python scripts/ci/check_refactor_preservation.py --contracts --nodes
uv run --project backend python scripts/ci/check_refactor_frontend_preservation.py
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test:ui-catalog
pnpm --dir frontend test:ui-error-contracts
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests exec playwright test --config=playwright.image-integration.config.ts
```

시험 도중 발견한 문제는 JSON label이 textarea 값을 포함하던 부분, 접힌 고급 입력의 locator, 생성 이미지 부착 후 warning을 숨기던 조건, 새 참조 프로필 확인과 체크박스가 서로 기다리던 초기화, DTO와 워크플로 선택의 순환 의존이다. label-for, 실제 UI 상태의 locator, generated-image 상태 slot, 요청한 프로필·실제 참조와 분석 기반의 선택, 실제 service/schema 역할 분리로 수정했다. 서비스 이동 뒤 World 시험의 import 두 경로도 정리했다. 마지막 화면 점검에서 고급 안내의 확인 완료 문구가 미확인 상태에도 보이던 부분은 실제 연결·입력 상태 조건으로 수정했다. 기존 ko/en 수정·저장 시험에서 확인 전 미확인/완료 문구 부재와 확인 후 완료 문구를 함께 검증한다. 인식 UI 시험은 더 이상 사용하지 않는 전역 설정 대신 현재 World 카드에서 medium·키·일일 상한·용도 격리를 검증한다. 기존 보호된 백엔드 시험 이름·권한 단언을 유지하고 timeout/skip/원본 snapshot을 낮추지 않았다.

## 5. 공식·커뮤니티 고정 자료 5개

공식 기준 commit: `06bde939fb1e9c4c8d8641d810f0a916b5bce127` (SillyTavern release).

| 자료 | bytes/노드/토큰 위치 | SHA-256 | 제품 경로 mock |
|---|---|---|---|
| Default_Comfy_Workflow.json | 1760/7/10 | 18f3e44cdedb1bbc4e9597ce5f759b95f2dfc18f887d3614ff619792366c4fab | PASS |
| Char_Avatar_Comfy_Workflow.json | 2236/9/12 | 1f802ab459038f9f3a3d29b79946e55df4900e3ac5306b7edf23fd60a860ebdf | PASS |
| Anima standard | 1490/9/12 | e3205cc492dc65020a9adba874a3d2b1ab8be6001d15c4d1b6bf2574feb8c59f | PASS |
| Z-Image standard | 2777/11/9 | 7353fcc854031d179201d3bae960cad283de05390a30380fad414c25a0de47ce | PASS |
| SDXL Detailer | 8873/18/15 | 2add63d44f37f3709a7ad51d3e9dac455dfa459a43ba5cc9675b81213448f2dc | PASS |

공식 [Default](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/default/content/Default_Comfy_Workflow.json) blob `10bb0cc3c15528d3d367893e733bda4592ba6db4`, [Char Avatar](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/default/content/Char_Avatar_Comfy_Workflow.json) blob `c40bd8fb8b6227ea1f7bd84b9133ffbc82557d23`. 커뮤니티는 계획에 고정된 [Anima](https://pastebin.com/raw/qcZePZuA), [Z-Image](https://pastebin.com/raw/NqQ6KZgB), [SDXL Detailer](https://files.catbox.moe/ytrr74.json) 및 workspace 원본 sources manifest를 따른다. SDXL Detailer는 원격 직접 다운로드 실패 후 확인한 전체 JSON을 저장한 재구성 자료이며 원격 다운로드 bytes 동일성을 주장하지 않는다.

제품 strict analysis·값 렌더링·snapshot serialize/restore·ImageHttp mock submit·JS 첫 이미지 선택을 사용한다. 모든 자료의 원본/links/metadata와 미치환 위치를 비교하고 참조는 metadata-free PNG로 확인한다. `/object_info` 503에도 입력 준비 가능하며 graph 설치 가능성은 mock 서버 결과를 따른다.

외부 JSON과 ST 소스는 제품/repository에 배포하지 않는다. 격리 fixture와 보고서는 workspace `.local-diagnostics/comfy-placeholder-20261009/{fixtures,official-sources.json,external-reuse.json,external-reuse-final.json}` 및 기존 `.local-diagnostics/comfyui-builtin-workflows-20261008-161347`에 있다. `external-reuse-final.json`은 마지막 출력 ID 수정 뒤 다시 얻은 5/5 PASS·AI0 증거다. 재현 도구는 [check_comfy_workflow_reuse.py](../../scripts/diagnostics/check_comfy_workflow_reuse.py)이다. 원본 모델/custom node 품질·설치 호환성은 이 시험의 PASS 범위가 아니다.

## 6. 실제 ComfyUI, 무AI 통신

기존 격리 ComfyUI 설치 HEAD `33ee2b36d2d6e8f25cfc796b774ca387917b98de`, Python/torch CPU 환경을 사용했다. 신규 모델·custom/API node 설치를 하지 않았다. 기존 프로세스와 충돌하지 않는 18289 port를 사용하고 input/output/user/temp/models/database를 모두 이번 전용 `live` 경로로 지정했다. 자동 브라우저·custom nodes·API nodes를 비활성화했다.

- 합성 128×64 PNG를 LoadImage→ImageScale→SaveImage로 64×32 변환했다. 제품 client의 system_stats/object_info/prompt/history/view가 성공했다.
- receipt `cb1004a5-bad8-49bb-bfdf-8ee5702ea4be`; graph SHA-256 `56daead91094739ad6aeb18412164870c32fe265c1746c27fe876f65f6476e37`.
- 출력 PNG SHA-256 `2f899924d6c7f407b35dce05e7ee5183adf95d8fa87897c9589315bc9feceff8`, 64×32.
- 별도 존재하지 않는 합성 노드 요청은 실제 HTTP 400 `missing_node_type` 진단을 받았다. `comfy_prompt_rejected`로 알려진 접수 실패를 반환했다.
- 모델 추론·외부 AI 호출·외부 5개 AI workflow 실제 실행·모델 다운로드는 모두 0회다. 실제 custom Base64 decoder의 모델 실행 성공은 측정하지 않았다.
- 자신이 띄운 launcher PID1888/서버 PID23672만 queue 비어 있음 확인 후 종료했다. 18289 port가 이후 LISTEN하지 않는 것도 확인했다. 사용자 ComfyUI·Angmoo 설치 앱·Docker/원본 DB/키/기존 모델은 작업 대상으로 사용하지 않았다.

증거는 workspace `.local-diagnostics/comfy-placeholder-20261009/live-result.json`, `live-result.png`, `live/process.json`, `live/{stdout,stderr}.log`에 남긴다. 이 증거를 실제 AI 품질 또는 모든 환경 실행 보장으로 확대하지 않는다.

## 7. 상한과 오류 정책

계획의 초기값을 그대로 적용했다. 실제 원본 5개는 최대 18노드/8,873 bytes이며 무모델 출력은 64×32로 상한 변경의 근거가 없었다. 값의 단순화 또는 숨은 무제한 fallback을 추가하지 않았다.

| 경계 | 적용값/회귀 |
|---|---|
| API JSON | 2 MiB, 256 nodes, depth64, 100,000 items. raw duplicate/nonfinite/shape/complexity/size 거절. |
| 설정 raw envelope | 4 MiB. 기존 설정 용량과 두 workflow를 유지하며 개별 graph 상한을 별도 검사. |
| 제출 본문 | 32 MiB bounded iterencode; 초과를 제출 전에 거절. 반복 Base64도 최종 본문 크기로 판정. |
| 참조 | 원본/정규화 PNG 각10 MiB. 픽셀 검증·metadata 제거·1회 Base64, 기존 upload bytes 보존. |
| 출력 | 12 MiB, PNG/JPEG/WebP, 한 변4096, pixels≤16,777,216, 단일 frame, 안전한 filename/subfolder/type. |
| 오류 응답 | 32 KiB 읽기 상한은 Comfy 경로만 opt-in. 다른 제공사 HTTP 계약 유지. |
| 진단 | 20 messages, 각 whitelist field≤2048 chars, 전체≤16 KiB, truncated 표시. 저장/조회도 DTO로 검증. |

known HTTP400 거절·history 실행 실패·완료/no-image·잘못된 첫 출력은 terminal이다. transport/5xx/receipt 없는 불명 응답은 outcome_unknown이며 무조건 재제출하지 않는다. receipt+node_errors는 receipt를 먼저 저장하고 warning을 보존하며 history를 조회한다. interrupt/queue 전체 삭제를 사용하지 않는다.

## 8. 마지막 소비자 점검과 보존

`.bindings`, `output_node`, `reference_required`는 무버전 legacy와 명시적 node binding/출력 호환 위치에 남긴다. required_roles/output_policy를 통해 신규 경로와 구분한다. runtime은 object_info class 존재/type 검사 없이 앱의 graph/value/ref/owner 계약만 확인한다. object_info는 integration과 editor 후보 표시만 사용한다. `api_node`, `comfy_remote_requires_https`, input-name secret gate의 제품 실행 차단은 제거했다.

공통 기존 제공사, 원본 JPEG/WebP 업로드와 출력 형식, quota·lease·receipt·result spool·credential/ref revision·owner/World와 DTO의 privacy 회귀는 유지한다. 새 기능 때문에 바뀐 테스트는 full graph 검사의 서버 위임, 명시적 Partner, raw JSON HTTP body, schema33 target 및 warning 표시 후 조회 횟수다. 기존 보호된 백엔드 test node 이름/권한/다른 제공사 검증을 삭제·skip/xfail하지 않는다. 새 narrow/wide·ko/en 캡처의 참조 분류는 LOCAL이다.

정확한 변경 출처는 append-only 보존 ledger에 별도 로컬 구현 commit의 before/after AST·assertions·schema/ORM hash·source blob을 기록한다. 기존 checkpoint·원본 보존 snapshot·과거 ledger records를 바꾸지 않는다. 디자인 정책은 새 LOCAL 캡처 호출 1개(41→42)만 명시하고 기존11 canonical PNG와 diff tolerance를 보존한다.

미측정: 실제 AI workflow 실행/생성 품질, 실제 Partner 결제/API 인증, 실제 Docker DNS/ComfyUI 통신, native/설치 Angmoo USER CHECK. 사용자와 이전 대화에서 유예한 `windows_installer_hosted_predecessor_missing:v29`의 hosted predecessor/CI 수정은 이번 작업에 포함하지 않았다.

## 9. 최종 로컬 커밋과 증거

| 로컬 commit | 내용 |
|---|---|
| `9a861df468e886f77e7b6e67f2b764bd29d61a46` | ComfyUI 입력/출력·snapshot·진단·migration·공통 UI·ko/en·회귀·아키텍처 구현. |
| `67d72193db436f183c7fa2c5bb46ae6bd019edc6` | 정확한 구현 보존 증거: 62 definition, 5 assertion 전후, 4 폐기 binding, 14 frontend 파일, 18 API 계약, 1 ORM delta, 13 새 파일, 60 새 test node. |
| `59022f6275524d4314334b8f06e9cd202f63ee2f` | 확인 완료 안내를 실제 연결·입력 준비 상태에 맞춤. 기존 ko/en browser 시나리오에 확인 전후 표시 검증. |
| `90cf2ff4c30389ec993d78f651ea4697ee22a30e` | 후속 editor/browser 2개 파일의 정확한 before/after 보존. |
| `2dbc450c6f8ebbdf53b7af6043702f6b88cf3440` | 매우 긴 숫자 출력 ID를 일반 문자열 키로 유지. Python 정수 변환 안전 상한을 바꾸지 않음. 기존 출력 순서 시험에 5,000자리 ID 회귀 추가. |
| `bb52051489b90526a70b17fb22ebfcade7eea88e` | 후속 2개 definition과 1개 assertion 전후 보존. 이전 199 records 무변경. |

확인 완료 안내 수정 뒤 lint/typecheck·Next/static 빌드·semantic design과 ko/en Next/static 4개 기존 시나리오가 4 PASS(22.8초)로 통과했다. 출력 ID 문제는 수정 전 ValueError를 재현했고, 수정 뒤 placeholder 회귀 41개가 모두 통과했다. 마지막 경계 수정 전 실행 중이던 자신의 보존 검사는 중단 로그를 보존하고 확정 소스·증거에서 재시작했다. 이전 ledger records·frozen evidence·pytest node 이름은 변경하지 않았고 앞선 전체 시험과 반복 실행을 합산하지 않는다.

재개 시 제품 소스/보존 증거 HEAD는 `bb52051489b90526a70b17fb22ebfcade7eea88e`였고 제품 저장소의 미커밋 파일은 이 보고서뿐이었다. `comfy-preservation.txt`에서 백엔드 보존 PASS를 확인했으나 이어진 프론트엔드 최종 결과와 실행 프로세스가 남아 있지 않아 성공으로 간주하지 않았다. 원본 `check_refactor_frontend_preservation.py`만 재개해324개 파일 PASS·exit0를 확인했다. 이 재개 중 제품 소스·시험·보존 정책은 변경하지 않았고 이미 통과한 기능 검사를 반복하지 않았다.

I31의 완료 기록은 이 보고서만 선별한 `docs(media): finalize ComfyUI workflow reuse verification` 로컬 문서 커밋으로 마무리한다. 자기 자신의 SHA를 본문에 넣기 위한 amend는 하지 않으며, 최종 문서 커밋 SHA와 clean 브랜치 상태는 저장소 밖 workspace 계획 §14.3에 기록한다. 계획 문서는 제품 Git 저장소 밖에 있어 파일로 저장하고 제품 커밋에 혼입하지 않는다. 원격 push·PR·CI workflow·main merge는 수행하지 않았다.
