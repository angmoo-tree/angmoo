# SNS 이미지 생성 4개 Provider 실서비스 검증 기록 — 2026-10-01

이 문서는 실행 결과와 판정 범위의 저장소 기록이다. 아래 `artifacts/` 링크는 이 작업 환경에 보존한 로컬 상세 증거이며 Git 추적과 Docker 빌드 입력에서 제외한다. 저장소를 clone하면 해당 자료는 포함되지 않는다. 환경별 실서비스 실행 도구도 로컬에 보존하고 Git에서 제외한다. 원 17건 결과·실패·호출·비용·받은 이미지의 증거는 삭제하지 않고 로컬에서 유지하며, 다른 환경에서도 판단할 수 있는 결과 요약과 한계는 이 문서에 남긴다.

## 1. 결과와 판정 범위

사용자가 최종 확정한 **NA01 제외 본 검사 17건을 모두 실제 요청으로 수행**했다. 결과는 **이미지 생성·회수·동일 SNS 게시글 첨부 12 PASS, NanoGPT 5 FAILED**다. 통합 판정은 **PARTIAL**이며 네 Provider 전체 정상 동작이나 상위 F01–F11 완료로 표시하지 않는다.

본 검사 17건과 생성 없는 CT07 조회를 구별한다. 실패한 NanoGPT 사례를 유료 재시도로 다시 생성하지 않았다. Comfy 사전 생성도 0회다. 이미지 생성 제출은 총 17회, 그중 Comfy `/prompt` 4회가 공식 Partner 외부 POST 4회로 이어졌다. 두 층의 요청을 더하여 이미지 21장이라고 집계하지 않는다.

실제 텍스트 호출은 **34회: 초기 준비 2회 + 사례별 daily-preparation 갱신 15회 + Routine 17회**다. 지정 모델 `gemini-3.1-flash-lite`, 추론 수준 `high`, 상한 80회를 준수했다. 그러나 실제 Routine은 현재 contract-v2의 **`RoutineDecisionDraft` 한 번으로 decision·draft·image_prompt를 함께 작성**했다. 계획의 “4회 유지 / 정상 68회”와 다르며 **4회 구조 준수는 미확인/불일치**로 남긴다. 호출 수를 맞추려고 무의미한 LLM 요청을 추가하지 않았다. 이 결과를 사용자의 4회 계약 변경 승인으로 해석하지 않는다.

원본 계획:

- [통합 실서비스 테스트 계획](../../../docs/plan/09-30%20SNS%20이미지%20생성%204개%20Provider%20실서비스%20연동과%20게시글%20첨부%20통합%20테스트%20계획.md)
- [구현·로컬 검증 상위 계획](../../../docs/plan/09-30%20SNS·Chat%20이미지%20생성·인식%20통합%20코드%20구현과%20로컬%20검증%20세부%20계획.md)
- [최종 결과 JSON](../../artifacts/image-live-20261001/results.json)

## 2. 실행 환경과 보존 경계

| 항목 | 실제 사용 환경 |
| --- | --- |
| 제품 저장소 | `D:/project_code/angmoo-workspace/angmoo-tree-angmoo` |
| 브랜치·기준 HEAD | `feat/sns-chat-image-integration`, `daf5fe905eed36e0d28e98fc4a6457deb5134326` + 이번 로컬 변경 |
| 커밋 | 이번 변경은 미커밋. 생성 결과를 baseline HEAD의 무변경 결과로 기록하지 않음 |
| Angmoo | 공식 contributor embedded runtime, 별도 owner/World/캐릭터, canonical v26·정식 scheduler lease/worker/API |
| 격리 데이터 | `D:/project_code/angmoo-workspace/.local-diagnostics/sns-image-live-unified-20261001/data` |
| Backend / Next / Comfy | 이번 전용 포트 18088 / 13000 / 18288. 종료 시 모두 중지 |
| 카드 | 원본 Seraphina V3 카드 400×600, 정상 draft/card/complete와 private media 업로드 API 사용 |
| 별도 캐릭터 | CT06용 이미지 없는 캐릭터. Seraphina 원본이나 기존 사용자 이미지 삭제 없음 |
| ComfyUI | 공식 저장소 commit `33ee2b36d2d6e8f25cfc796b774ca387917b98de`, v0.38.0, Python 3.12.13, CPU torch 2.14.1+cpu |
| Comfy 모델/노드 | 공식 `FluxProUltraImageNode`(FLUX 1.1 Pro Ultra) → `SaveImage`, 참조 경로에는 `LoadImage` |
| 설치하지 않은 것 | 로컬 diffusion checkpoint, GPU 모델, custom API node |
| 이미지 제출 구간 | 2026-09-30 19:39:04–20:10:58 UTC / 2026-10-01 04:39:04–05:10:58 KST. Comfy `/prompt`의 내부 원격 실행은 외부 counters로 구별 |
| 전체 텍스트/이미지 요청 기록 구간 | 2026-09-30 19:20:46–20:10:58 UTC |

설치 identity helper는 지정 Google 키를 읽기 전에 `-IncludeDataPaths`로 실행했고 `identity_verified`를 확인했다. 설치 앱은 running `not_observed`였다. 실제 열린 UNC DB/secret 경로도 읽기 전용으로 확인한 뒤, 지정된 미도리야 이즈쿠의 Google 연결만 메모리에서 해석해 격리 캐릭터에 정상 등록했다. 원래 설치 DB·키·모델·활동 설정은 변경하지 않았다.

모든 게시글은 정상 API 설정/활성화와 scheduler `_tick_once`의 admission·lease 경로로 생성했다. DB job 삽입, fake provider/LLM, 직접 이미지 Provider 우회, 가짜 성공, 시간 변경을 사용하지 않았다. 빠르게 사례를 바꿀 때 정상 owner daily-preparation API로 새 계획을 준비했다. 따라서 장기 자연 활동의 품질이나 자연스러운 시간 분포를 검증한 실행은 아니다.

## 3. 본 검사 17건

PASS는 실제 이미지 bytes의 유효성·저장·같은 새 Routine 게시글의 단일 첨부·정상 GET 재조회 시 새 생성 0을 뜻한다. 얼굴/그림체/장면의 완전한 보존이나 비용 전체 측정의 PASS와 구별한다.

| ID | Provider·모델 | 실제 참조 | 결과 | 실제 이미지 크기 / 실패 |
| --- | --- | --- | --- | --- |
| NA02 | NovelAI `nai-diffusion-4-5-full` | OFF | PASS | 1024×1024, 20 Anlas |
| NA03 | NovelAI 동일 모델 | ON, 직접 지정 Seraphina | PASS | 1024×1024, 25 Anlas |
| NG01 | NanoGPT `krea-v2/turbo` | OFF | FAILED | HTTP 200 이후 `provider_image_invalid` |
| NG02 | NanoGPT 동일 모델 | ON, 직접 지정 | FAILED | HTTP 200 이후 `provider_image_invalid` |
| NG03 | NanoGPT `z-image-turbo` | 강제 OFF, 외형·스타일 비움 | FAILED | HTTP 200 이후 `provider_image_invalid` |
| NG04 | NanoGPT `nano-banana-2` | OFF | FAILED | HTTP 200 이후 `provider_image_invalid` |
| NG05 | NanoGPT 동일 모델 | ON, 직접 지정 | FAILED | HTTP 200 이후 `provider_image_invalid` |
| OR01 | OpenRouter `krea/krea-2-medium-turbo` | OFF | PASS | 1024×1024 |
| OR02 | OpenRouter 동일 모델 | ON, 직접 지정 | PASS | 1024×1024 |
| OR03 | OpenRouter `google/gemini-3.1-flash-image` | OFF | PASS | 1024×1024 |
| OR04 | OpenRouter 동일 모델 | ON, 직접 지정 | PASS | 1024×1024 |
| OR05 | OpenRouter `openai/gpt-image-2.5-flare` | OFF | PASS | 1024×1024, low quality 선택 |
| OR06 | OpenRouter 동일 모델 | ON, 직접 지정 | PASS | 1024×1024, low quality 선택 |
| CT01 | Comfy 공식 Partner FLUX 1.1 Pro Ultra | OFF, text_workflow | PASS | 2048×2048 |
| CT02 | Comfy 동일 노드/모델 | ON, 실제 외부 `image_prompt` 소비 | PASS | 2048×2048, strength 0.4 |
| CT05 | Comfy 동일 노드/모델 | OFF, 외형·스타일 비움 | PASS | 2048×2048, 장면만 사용하는 경로 |
| CT06 | Comfy 동일 노드/모델 | 선호 ON / 이미지 없음 / 실제 OFF | PASS | 2048×2048, 제출 전 text_workflow 선택 |

FLUX Ultra의 4MP 출력은 선정한 공식 노드/모델의 실제 출력이다. 해당 graph는 일반 KSampler의 width/height/steps 입력을 제공하지 않는다. Angmoo에 지원하지 않는 입력 binding을 만들거나 1024 크기가 적용됐다고 주장하지 않는다. positive·seed를 binding하고 1:1 비율을 graph에 지정했다. negative는 저장했으나 이 graph에는 binding이 없어 미적용이다.

각 job/post/asset ID, positive·negative 적용 상태, 옵션, 선택 참조 출처, 실제 요청의 field 이름, 첨부·재조회 결과는 [사례 원본](../../artifacts/image-live-20261001/case-results.json)과 [request counters](../../artifacts/image-live-20261001/request-counters.json)에 남겼다. 이미지 base64·헤더 원문·계정 키는 공개 증거에 넣지 않는다.

### NanoGPT 5건의 실패 의미

NG01–NG05 모두 실제 `/api/v1/images` 요청에 HTTP 200 응답을 받았지만, 현재 adapter의 유효 이미지 회수/검증을 통과하지 못했다. 새 SNS 글은 남고 이미지 첨부는 없다. 키가 없어서 검사를 못 한 사례가 아니며 **실서비스 응답과 현재 adapter의 결과 처리 사이에서 발생한 실패**다.

원 응답 body/이미지 payload는 비밀·대용량 데이터를 기록하지 않는 실행 정책에 따라 보존하지 않았다. 따라서 data URI/MIME/URL/응답 배열 중 어떤 차이가 원인인지 이번 기록만으로 단정할 수 없다. 다섯 실패 모두 과금 가능하며 아래 usage에는 5개 요청과 비용이 표시된다. 더 유료로 요청해 원인을 추측하거나 무조건 성공 처리하는 패치를 하지 않았다. 후속에서는 값 없는 응답 형태·MIME·decode 단계 관측을 준비한 뒤 별도 승인된 재검증 범위로 수행해야 한다.

## 4. 실제 사용량과 비용

| 서비스 | 이번 확인한 사용량 | 근거와 한계 |
| --- | --- | --- |
| NovelAI | **87 → 67 → 42 Anlas**, 총 **45** | active=false/tier=0, fixed Anlas 0. NA02 20, NA03 25. 실제 전후 계정 응답. 이번 선택은 구독/충전 대행이 아닌 기존 Paid Anlas 사용 |
| OpenRouter | **$0.1855655** | 실제 6개 attempt `usage.cost` 합계. OR01 .015 / OR02 .015 / OR03 .068203 / OR04 .0687755 / OR05 .006445 / OR06 .012142 |
| NanoGPT | **$0.1919**, requests 5, refund 0 | 지정 키의 UTC 당일 공식 usage 집계. Krea 2회 .02 / Z 1회 .0119 / Nano Banana 2회 .16. 테스트 고유 transaction ID로 결합한 개별 영수증은 아님 |
| Comfy | 외부 생성 **4회**, 실제 Credits 차감량 **미측정** | 실제 POST 응답의 `X-Comfy-Credits-Used`는 없었음. null을 0/free로 표시하지 않음. 노드 가격표를 실제 차감 증거로 대체하지 않음 |
| Gemini | **34회**, 실제 달러 요금 **미측정** | 지정 모델/추론 수준·요청 횟수 확인. Routine의 tracker와 준비 호출을 이중 합산하지 않음 |

참조 OFF 10건·실제 참조 전달 7건, 본 검사 이미지 제출 17회, 유료 재시도 0회, Comfy 사전 생성 0회다. CT07의 `/history`·`/view`, 설정 확인·공개 endpoint·계정/usage 조회는 새 이미지 생성 횟수와 구별한다. 요청 상한은 정상 이미지 장수가 아니라 제출 시도 기준으로 17개 모두 소비했다.

## 5. Comfy 정식 인증·설정·조회

서버 접근용 USER_IMAGE credential과 Comfy 계정 COMFY_PARTNER_IMAGE credential을 분리했다. 계정 키는 소유 캐릭터/owner/purpose/revision을 검증해 메모리에서 해석하고, Partner 제출의 **`extra_data.api_key_comfy_org`**에 전달한다. HTTP Bearer는 서버 접근 키만 사용한다. 이번 실제 서버에는 Bearer 인증이 없어 실제 제출은 account=true/server=false였으며, 두 키를 동시에 쓰는 분리는 fake transport 회귀로 확인했다.

Next 화면에서 계정 키 저장·입력 비우기·JSON 파일 가져오기·positive/seed/reference binding·output node·text_workflow·reload를 실제 source API로 확인했다. 정적 빌드는 통과했지만 browser static export→contributor API의 cross-origin 연결은 현재 개발 profile의 동일 출처 proxy 정책 때문에 실패했다. 출처/인증 검사를 제거하지 않았다. **CA02의 static 실제 연결·삭제 화면은 미완료**이고 USER CHECK 및 설치 Tauri 실행도 미실행이다.

| CA | 확인 상태 |
| --- | --- |
| CA01 | 별도 암호화 scope·revision·삭제 회귀 PASS, 실제 저장·격리 키 정리 PASS |
| CA02 | Next 저장/파일/binding/reload PASS, static build PASS, static live browser/삭제 UI 미완료 |
| CA03 | 실제 4개 Partner 요청의 공식 account field, 서버 키 없음 확인. 두 키 동시 분리·비Partner 미전달은 offline PASS |
| CA04 | snapshot/revision 변경 거절 회귀 PASS, 같은 실제 receipt 재회수 CT07 PASS. 실제 중단/재시작 복구 제외 |
| CA05 | 키 없음·인증 모드 불일치 전송 전 차단 회귀 PASS. 실제 인증/잔액 오류를 고의로 유료 유발하지 않음 |
| CA06 | 최종 산출물 privacy 검사 PASS. optional Comfy debug body 로그는 제거하고 status만 보존. UI/설정 저장의 새 생성 0 |

[CT07 기록](../../artifacts/image-live-20261001/CT07-requery.json)은 성공한 Comfy 4개 prompt_id를 실제 GET으로 다시 회수해 정규화 픽셀 hash와 기존 SNS asset hash의 일치를 확인한다. **새 `/prompt` 0, 외부 Partner POST 0**, 실제 history에 계정 키 없음. 이 검사를 프로세스 장애/재시작 복구로 확대하지 않는다.

## 6. 수행 중 정식 코드 보완

| 변경 | 이유와 검증 |
| --- | --- |
| Comfy Partner 별도 credential·API·UI·요청 전달 | 기존 구현은 서버 키만 있었다. 위 CA와 실제 Partner 4건으로 기본 경로 확인 |
| NovelAI 계정 확인 host | 실제 이전 endpoint는 HTTP 400. 공식 image API의 `image.novelai.net/user/subscription`으로 보완 후 실제 Anlas 조회 성공 |
| SharedImageHttp decoded response 처리 | httpx가 이미 압축을 해제한 bytes를 새 Response에 넣으며 압축 헤더를 유지해 다시 decode하는 오류를 수정. gzip 회귀 추가 |
| Comfy 참조 ON에서 키 삭제 | 삭제로 connection을 무효화할 때 기존 참조 선호 ON 때문에 삭제 자체가 거절됨. 동일한 이전 검증 workflow·선호를 유지하고 auto OFF인 키 삭제만 허용. 자동 생성 ON·새/변경 workflow의 검증 조건은 유지 |
| 진단 기록의 private field 제거 | Routine tracker의 key fingerprint를 최종 JSON/응답에서 제거. optional Comfy logger의 참조 base64/서명 URL debug body도 보존하지 않음 |

마지막 키 삭제 수정 후 **실제 CT06 테스트 설정의 참조 선호 ON을 보존하며 정상 PUT 삭제·OFF·credential 삭제를 확인**했다. 생성 17건은 그 전에 수행한 원 결과다. 마지막 수정은 credential 삭제 동작이며 추가 유료 생성으로 17건을 반복하지 않았다. 변경 후 이미지 회귀는 아래 165개로 재검증했다.

## 7. 로컬 자동 검증

| 검사 | 결과 |
| --- | --- |
| 이미지 통합 suite | **165 PASS**, 실패 0, third-party deprecation warning 2 |
| Partner 관련 subset | **8 PASS**, 위 165에 포함. 별도 합산하지 않음 |
| 관련 identity/credential 회귀 | **24 PASS** |
| Backend architecture | PASS, modules 1333 / edges 5404 / legacy_exact_edges 0 |
| Frontend architecture | PASS, features 14 / legacy_exact_edges 0 |
| Frontend design | PASS, raw_colors 1230 / files 36 / surfaces 18 / route_gaps 0 / screenshots 16 |
| typecheck / lint | PASS |
| static build | PASS |
| 이번 진단 `.mjs` lint | PASS |
| Next 실 API 설정 브라우저 | PASS, USER CHECK 아님 |
| static 실 API 브라우저 | BLOCKED, source profile의 동일 출처/CORS 경계. UI 성공으로 대체하지 않음 |
| Git diff whitespace | PASS |
| CI / push / PR / main merge / release / 설치 교체 | 미수행 |

주요 명령은 제품 root에서 `backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py`, frontend 두 boundary/design checker, backend에서 `python -m pytest tests/image_integration -q --junitxml=../artifacts/image-live-20261001/image-regressions-final.xml`, frontend의 typecheck/lint/build:static이다. `scripts/ci`의 checker를 로컬로 실행한 것이며 원격 CI workflow를 실행한 것은 아니다.

증거:

- [165 PASS XML](../../artifacts/image-live-20261001/image-regressions-final.xml)
- [24 PASS XML](../../artifacts/image-live-20261001/credential-regressions.xml)
- [Next 설정 브라우저](../../artifacts/image-live-20261001/ui-evidence.json) / [static 상태](../../artifacts/image-live-20261001/static-ui-evidence.json)
- [최종 privacy 확인](../../artifacts/image-live-20261001/privacy-check.json)

## 8. 제한·품질 관찰·후속

1. NanoGPT 5건의 유효 이미지 회수와 첨부는 실패다. 응답 형태를 안전하게 관측하고 adapter를 보완한 뒤 별도의 실제 재검증이 필요하다.
2. 현재 contract-v2 combined Routine과 계획의 4회 구조는 불일치다. 기존 구현의 [combined provider](../../backend/app/runtime/autonomous_activity/combined_provider.py)와 [contract-v2 선택](../../backend/app/runtime/autonomous_activity/execution.py)을 근거로 기록한다. 이번 작업에서 SNS 호출 구조를 바꾸지 않았다.
3. 첫 NA02의 고정 appearance 입력은 silver hair/blue eyes였으나 카드/장면은 pink hair/amber eyes였다. NA03부터 카드에 맞춰 pink/amber/black dress로 수정했다. NA02의 생성·첨부 PASS는 유지하되 엄밀한 동일 fixture 품질 비교의 PASS로 사용하지 않는다. 원 결과/장면/설정은 보존한다.
4. NA02의 로컬 이미지 증거 복사 경로 오류와 OR02 runner 중단은 이미 받은 결과만 회수해 기록했다. 각각 새 생성 0, 기존 job/post/pixels 보존이며 유료 재시도가 아니다.
5. 검사자가 NA02/NA03/OR02/OR04/OR06/CT02 이미지를 직접 확인했다. 분홍 머리·검정 드레스 등 주요 특징은 보이지만 얼굴/의상의 완전 동일성이나 통계적 품질 순위를 측정하지 않았다. CT02에서는 장면에 있던 잠든 방문객이 보이지 않아 장면의 모든 요소 재현을 보장하지 못한다.
6. 참조 실제 전달 사례는 직접 지정 Seraphina 경로다. 카드/프로필 우선순위의 기존 local 회귀와 이번 live 전송을 구분하며 모든 출처의 live 품질로 확대하지 않는다.
7. NovelAI 성공 2건은 정확한 서버 tokenizer/parser/가중치/512 경계 동일성을 입증하지 않는다. `exact_verified=false`를 유지한다.
8. NA01/F01 Opus 무차감, CT03/CT04 custom, F05 로컬 모델, 실제 장애/재시작, broad options/출처/다른 인식 조합·SNS/Chat 품질·장기 활동·backup/restore·Linux·USER CHECK는 후속으로 유지한다.

상위 F 대응: **F02 선택한 Anlas 텍스트/참조 경로 확인**, **F03 실패**, **F04 선택 세 모델 6개 경로 확인**, **F06 Partner 생성/회수/첨부 확인하되 실제 Credits/static UI 등 잔여**. 이를 F01–F11 전체 완료로 표시하지 않는다.

## 9. 종료와 재개 경계

두 테스트 캐릭터는 정상 API로 deactivate하고 자동 이미지 생성을 OFF했다. 격리 데이터의 이미지 credential은 정상 설정 삭제 경로로 비활성화/삭제했고 텍스트 credential의 encrypted key도 정상 삭제했다. **진행/미확정 image job 0, Comfy queue running/pending 0**을 확인했다. 이번 backend는 인증된 종료 endpoint로 정상 종료했고, 이번 Comfy·Next/static 프로세스만 중지했다. 포트 13000/18088/18288 listener 없음.

원본 키 JSON·Seraphina·설치 앱/DB·Docker·기존 사용자 자료를 보존했다. 테스트 DB·게시글·이미지·receipt·실패 자료도 보존한다. 키를 정리한 격리 환경을 재개할 때는 정상 API로 재등록해야 하며, **17건 runner를 처음부터 재실행해 유료 생성을 반복하지 않는다**. 지금 원 결과의 복구/조회만 하면 새 이미지 제출은 필요 없다. NanoGPT 새 실생성은 이번 17회 제한의 후속이며 별도 범위를 정해야 한다.

[정리 기록](../../artifacts/image-live-20261001/cleanup.json) / [종료 기록](../../artifacts/image-live-20261001/shutdown.json) / [Comfy 실제 외부 요청](../../artifacts/image-live-20261001/partner-external-requests.json) / [usage 원본](../../artifacts/image-live-20261001/generation-attempts.json).

## 10. 별도 NanoGPT MIME 후속 batch

원 17건의 12 PASS/5 FAILED는 이 문서의 실행 당시 사실로 유지한다. 이후 사용자 지시에 따른 [10-01 MIME·형식 보존 구현/재검증](./nanogpt-mime-format-retest-20261001.md)에서 별도 batch `run-20261001T032012Z-334b42`의 **NG01–NG05 생성·저장·같은 SNS 글 단일 첨부 5 PASS**를 확인했다. 이번 후속 image 5회/Gemini 10회와 공식 usage 차이 $0.1919는 원 17건/34회의 반복 기록이 아닌 별도 실행이다.

MIME 없는 JPEG 3장/PNG 2장을 실제로 판독·저장했으며, 재조회/worker 복구의 새 생성은 0이다. 원 실패의 body가 없으므로 모두 같은 원인이라고 확정하지 않는다. 실제 WebP·실제 출력의 브라우저 화면/USER CHECK·다른 F 잔여는 후속으로 유지한다. 새 관련 backend 고유 272개 및 Next/static fixture 40 PASS, 격리 키 정리/프로세스 종료, commit/PR/CI/push/main/설치 교체 미수행의 상세 근거는 새 검증 문서를 따른다.

### 기존 실제 출력의 Next 화면 후속 확인

위 화면 미완료 상태 이후 사용자 지시로 기존 NG01–NG05 게시글을 정상 Next `/api/backend` 인증 경로에서 각각 열고 새로고침해 **실제 화면 5 PASS**를 확인했다. 다섯 이미지가 두 번 모두 1024×1024로 decode됐고, 표시 Blob·인증 HTTP content·저장 파일의 MIME/용량/hash가 일치했다. 추가 이미지/Gemini 요청은 **0/0**이며 기존 MIME batch 총계 5/10과 파일 bytes는 그대로다. 최초 화면 실패 기록은 보존하고 실제 static·설치 Tauri·직접 USER CHECK·품질·실제 WebP 등은 잔여로 둔다. 키 제거·자동 생성 OFF를 재확인하고 작업 소유 backend/Next를 종료했다. [실제 화면 증거](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/ui-evidence.json)와 [새 검증 §6.1](./nanogpt-mime-format-retest-20261001.md)을 최신 근거로 사용한다.
