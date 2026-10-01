# NanoGPT MIME 보완·형식 보존과 SNS 첨부 후속 검증

이 문서는 실행 결과와 판정 범위의 저장소 기록이다. 아래 `artifacts/` 링크는 이 작업 환경에 보존한 로컬 상세 증거이며 Git 추적과 Docker 빌드 입력에서 제외한다. 저장소를 clone하면 해당 자료는 포함되지 않는다. 환경별 실서비스 실행 도구도 로컬에 보존하고 Git에서 제외한다. 코드·테스트·검증 요약은 저장소에서 관리하며, 원 실패·호출 횟수·비용·실제 출력 및 화면 증거는 로컬에서 유지한다.

- 실행일: **2026-10-01**.
- 대상: [10-01 구현 계획](../../../docs/plan/10-01%20NanoGPT%20MIME%20누락%20보완과%20이미지%20형식%20보존·SNS%20첨부%20재검증%20코드%20구현%20계획.md)의 **P00–P10**.
- 후속 batch: `run-20261001T032012Z-334b42`.
- 소스: `feat/sns-chat-image-integration`, `daf5fe905eed36e0d28e98fc4a6457deb5134326` + 미커밋 변경.
- 결과: **코드·키 없는 관련 회귀·Next/static fixture 확인 완료; 실제 NG01–NG05 생성·저장·같은 SNS 글 첨부 재검증 5 PASS**.
- 별도 상태: **보존한 실제 NG01–NG05 출력의 Next 게시글 화면·새로고침 5 PASS**, 직접 USER CHECK 미수행. 실제 화면 검사는 fixture 표시 검사와 별도로 기록한다.
- 원래 17건의 **12 PASS / NanoGPT 5 FAILED**는 [기존 기록](./sns-image-live-unified-20261001.md)에 그대로 남는다.

## 1. 처리 변경과 보존

MIME이 빠졌다고 PNG를 지정하던 기본값을 제거했다. 공통 판독기가 PNG/JPEG/WebP signature, 선언 MIME 일치, 용량, 실제 구조·픽셀 decode, 치수·면적, 단일 프레임을 검사한다. 응답 parser는 정확히 한 장의 알려진 `data[0].b64_json` 계약을 유지하고 값 없는 실패 단계를 제공한다. 잘못된 MIME·손상·다중 프레임·URL-only·data URL을 허용하는 우회는 추가하지 않았다.

관리 asset은 판독한 형식으로 저장한다. PNG는 `.png/image/png`, JPEG는 `.jpg/image/jpeg`, WebP는 `.webp/image/webp`다. 정규화할 metadata/회전이 없으면 받은 bytes를 그대로 저장한다. 필요한 회전·metadata 정리에서도 같은 형식을 유지하며, 최종 bytes의 hash·크기·치수와 DB·인증된 HTTP content 응답을 연결한다. 표시용 WebP 파생본이나 사용자 MIME 입력은 추가하지 않았다.

참조 우선순위와 OFF 선호를 유지했다. NanoGPT/OpenRouter는 descriptor가 허용한 실제 MIME으로 전송하고 PNG가 필요한 경로만 전송용으로 변환한다. Comfy multipart의 파일명·MIME은 실제 bytes와 일치한다. NovelAI의 전용 참조 PNG 전처리는 유지한다. 카드 원본·기존 PNG asset·profile/legacy 경로·인식 캐시를 일괄 변환하지 않는다.

주요 제품 파일:

- [공통 판독](../../backend/app/integrations/media/images.py), [직접 Provider parser·참조 전송](../../backend/app/integrations/image_api.py).
- [형식 보존 asset 저장](../../backend/app/domains/media/service/assets.py), [Media 검증](../../backend/app/domains/media/service/pixel_validation.py), [안전 오류 단계](../../backend/app/domains/media/generation_contracts.py).
- [참조 조립](../../backend/app/runtime/media/composition.py), [Comfy 업로드](../../backend/app/integrations/comfy_images.py).

Backend/Frontend ARCHITECTURE, Frontend DESIGN·AGENTS의 소유권과 인증 경계를 유지했다. 이번에 제품 UI 입력·색상·라우팅·CORS/CSRF 정책을 변경하지 않았다.

## 2. P00–P10 대응

| 단계 | 완료 근거 |
| --- | --- |
| P00 | branch/HEAD/main/기존 dirty 기록 및 private baseline 사본. 기존 변경 13개를 기준으로 보존 |
| P01 | 수정 전 분류 회귀에서 16 FAIL / 14 PASS 확인, 거절·형식 보존 기대 정의 |
| P02 | 공통 bytes 판독과 제한된 구조·실제 decode, MIME 일치 검사 연결 |
| P03 | PNG 기본 MIME 제거, 두 직접 Provider의 엄격한 parser 및 안전 단계 회귀 |
| P04 | 세 형식 저장·인증 content·필요한 정규화·기존 PNG/expiry/orphan/backup fixture 검증 |
| P05 | 실제 MIME 참조, 최종 전송 한도, Comfy multipart, NovelAI 전용 PNG 전처리 회귀 |
| P06 | 세 형식 spool/asset/DB/첨부 실패 주입과 수신 결과 복구, 새 Provider 호출 0 확인 |
| P07 | 격리 정상 API/Routine/worker runner, durable 횟수 guard, private 후보, 3형식 화면 fixture |
| P08 | 최종 관련 backend 271 PASS + 종료 재개 회귀 1 PASS; Next/static browser 40 PASS; 정적 검사/build PASS |
| P09 | 실제 NanoGPT 각 사례 최초 제출 1회, 5 PASS, 동일 글 단일 첨부, 재조회/worker 복구 새 제출 0 |
| P10 | 이전/후속 분리, 비용·한계·privacy/정상 종료 기록 및 상위 문서 동기화. 새 커밋 없음 |

로컬 커밋은 계획 §2.2의 허용 항목이며 필수 조건이 아니다. 기존 변경과 이번 변경이 겹치는 네 파일을 포함해 작업 트리를 보존했고, 이번 작업에서는 stage/commit하지 않았다. 현재 결과는 HEAD 단독의 결과가 아닌 미커밋 작업 트리의 결과다.

## 3. 로컬 검증

| 검증 | 결과·증거 |
| --- | --- |
| 관련 이미지·캐릭터 workflow 최종 suite | **271 PASS**, dependency deprecation warning 2개, [XML](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/offline-final.xml) |
| guard/종료 재개 보완 | **14 PASS**; 그중 13개는 위 suite와 중복, 신규 종료 재개 회귀 1개 추가. [XML](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/guard-cleanup.xml) |
| Next/static image browser | **40 PASS**, 실제 작은 PNG/JPEG/WebP 파일을 사용한 preview/Feed·blob MIME·natural dimensions·reload·수명·제출 0 검사. [log](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/browser-final.log) |
| Backend 경계 | PASS, modules 1333 / edges 5404 / legacy exact edges 0 |
| Frontend 경계·DESIGN | PASS, features 14 / legacy exact edges 0; raw colors 1230 / files 36 / surfaces 18 / route gaps 0 / canonical manifest 16 |
| lint / typecheck / Next build / static build / diff check | PASS, 로컬 실행. 원격 CI 아님 |

[T01–T28 대응 JSON](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/test-coverage.json)에 새 검사와 기존 검사 재사용의 범위를 기록했다. 관리 이미지 백업/복원은 fixture 확인이며 전체 운영 backup 복원을 뜻하지 않는다. 브라우저 초기 static 3건 실패는 새 문서로 이동한 뒤 예전 blob을 명시 revoke한다고 기대한 검사 문제였다. 문서 unload 후 접근 불가를 검사하도록 수정하고 최종 40개를 통과했다. 원 실패 증거도 보존했다.

## 4. 실제 NG01–NG05

정상 카드 가져오기·키/설정 API·일과 준비·현행 combined Routine·생성 worker·Media 저장·Social 첨부를 거쳤다. 수동 DB 성공 상태/첨부 작성이나 fake Provider로 실서비스 결과를 만들지 않았다. 모든 출력은 **1024×1024, 요청당 1장**이다.

| 사례 | 모델 | 참조 | 관측 응답 / 저장 | 최종 bytes | 결과 |
| --- | --- | --- | --- | ---: | --- |
| NG01 | `krea-v2/turbo` | OFF | MIME 없음, JPEG / `.jpg` | 334,726 | PASS |
| NG02 | `krea-v2/turbo` | 직접 지정 ON, PNG 1개 | MIME 없음, JPEG / `.jpg` | 347,818 | PASS |
| NG03 | `z-image-turbo` | 강제 OFF, 외형·스타일 비움 | MIME 없음, JPEG / `.jpg` | 401,386 | PASS |
| NG04 | `nano-banana-2` | OFF | MIME 없음, PNG / `.png` | 2,622,959 | PASS |
| NG05 | `nano-banana-2` | 직접 지정 ON, PNG 1개 | MIME 없음, PNG / `.png` | 2,713,208 | PASS |

세 JPEG에는 EXIF 없이 comment metadata가 있었다. privacy 정리로 comment를 제거하고 **JPEG로 한 번 재인코딩**했으므로 bytes/용량은 수신 파일과 다르다. 크기·형식은 유지하며 최종 hash/bytes를 저장 기준으로 검증했다. PNG 두 건은 metadata 정리가 필요 없어 **수신 bytes 그대로** 저장했다. 세 형식 보존은 파일 형식을 유지하는 계약이지 privacy 처리까지 금지하는 계약이 아니다.

각 사례마다 생성 intent의 장면과 positive 조합, ref 출처·전송 수/MIME, 단일 `PostMedia`, 파일 확장자/DB MIME/최종 hash/dimensions, 인증 content bytes·MIME·nosniff, post/job 재조회와 worker 복구 시 새 제출 0을 확인했다. [결과](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/case-results.json), [응답 관측](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/response-shapes.json).

이 batch에서 **MIME 없는 JPEG 3건**을 실제로 확인해 보완 경로의 유효성을 입증했다. 원 5개 실패 응답을 보존하지 않았으므로 과거 실패 모두가 이 원인이라고 확정하지 않는다. 실제 WebP 출력은 없었고 WebP는 로컬·화면 fixture로 검증했다. 얼굴·의상·그림체·장면 재현 품질은 별도 평가이며 연동 PASS에 포함하지 않았다.

## 5. 호출·비용·실행 차이

- NanoGPT: **5 POST**, 각 사례 1회. 추가 진단 생성/자동 유료 재시도 0.
- Gemini: **10회**, 일과 준비 5 + combined Routine 작성 5. `gemini-3.1-flash-lite`, `thinking_level=high`. 사용자 확정에 따라 이번 테스트에서 1회 combined 호출을 사용했으며 제품 전체의 4회 계획을 변경하지 않았다.
- NanoGPT UTC 당일 동일 키 aggregate: 실행 전 requests 0 / net $0, 실행 후 requests 5 / net **$0.1919**, refund 0. [usage 대응](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/usage-summary.json). 이것은 사례별 영수증이 아닌 공식 usage 집계의 차이다.
- Gemini 실제 달러 비용은 **미측정**. 0/free로 채우지 않았다.

최초 NG01 사전 실행에서는 config import 이전 timing 적용이 누락되어 정상 scheduler의 due/started가 0이었다. 이미지 제출은 0, 일과 준비는 1이었다. timing 적용 위치를 수정한 격리 서버에서 그 준비 결과를 재사용했고 Routine/image를 한 번 실행했다. 빈 실행 기록은 `NG01-routine-before-due.json`에 유지한다. 횟수 guard는 restart 전후 전송을 모두 센다.

최초 실제 이미지 브라우저 검사에서는 static → contributor backend의 `auth/me` 요청이 실패해 이미지 화면까지 도달하지 못했다. 새 Next 미리보기 실행도 당시 자동 승인 검토에서 `blocked by policy`로 거부됐다. [당시 미완료 증거](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/before/ui-evidence.json)는 보존한다. 이후 사용자가 기존 게시글의 Next 화면 확인을 요청해 아래 §6.1의 별도 읽기 검증을 완료했다. static과 packaged Tauri의 실제 화면은 이 결과로 완료 처리하지 않는다.

## 6. 종료·보존·재개

정상 API로 격리 캐릭터 활동/자동 생성을 OFF하고 이미지 key와 Google key를 제거했다. DB에는 비활성 credential 행 각 1개가 남지만 **enabled credential 0 / encrypted secret 0**이다. 정상 삭제 경로의 tombstone이며 사용 가능한 키가 남은 상태가 아니다. 5개 job은 모두 succeeded, 진행/미확정 job 0. 최초 종료 검사의 column/count 가정을 수정하고 반복 종료에서 이미 제거한 profile을 재검증하지 않는 회귀도 추가했다.

격리 backend는 인증된 종료 API로 정상 종료하고 이 작업 소유 static preview만 중지했다. 마지막 PID/port 확인은 [정리 기록](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/cleanup.json)에 기록한다. 원본 key JSON·Seraphina 카드·기존 설치/DB·Docker·이전 증거는 변경하지 않았다. private 수신 후보·spool·관리 이미지·시험 DB는 재개 자료로 보존한다. 공개 metadata에는 키/부분 키/credential fingerprint/base64/raw response/signed URL/실제 대화 본문을 넣지 않았다.

**이미 끝난 다섯 case를 유료 재생성하지 않는다.** 새로운 Routine/image 요청은 이 batch의 5/10 상한을 모두 사용해 차단된다. 기존 결과의 읽기·저장·첨부 복구만 가능하다. 공개 proof와 private root는 분리되어 있으며 private 데이터는 Git에 추가하지 않는다.

브랜치와 main HEAD는 착수 시점과 동일하다. 로컬 커밋 없음. PR·push·원격 CI·main 수정/병합·배포·설치 교체·결제/충전 없음.

### 6.1 기존 실제 출력의 Next 화면 후속 검사

사용자의 후속 지시에 따라 격리 시험 DB·기존 게시글·기존 관리 이미지를 다시 열었다. 새 이미지 생성·일과 준비·Routine·이미지 분석은 요청하지 않았고 시험 credential은 제거된 상태로 유지했다. review ID는 `ui-review-20261001T052846Z`다.

프론트는 `http://127.0.0.1:13000`의 기존 production Next build를 `pnpm start --hostname 127.0.0.1 --port 13000`으로 실행했다. `ANGMOO_API_BASE_URL`을 설정해 18388로 연결하는 결합 실행 명령은 자동 승인 검토가 `blocked by policy`로 거부했다. 원인을 더 구체적으로 제공하지 않았으므로 특정 보안 이유로 단정하지 않는다. 이후 승인된 기본 시작 명령과 기존 proxy의 기본 backend 주소 `http://127.0.0.1:8080`을 사용했다. 18388의 작업 소유 backend를 정상 종료한 뒤 같은 격리 데이터로 8080에 시작했으며, 제품 환경 설정·인증·CORS·CSRF·CSP를 수정하지 않았다. `/api/backend`의 정상 owner session·이미지 content 경로를 사용했다.

검사는 기존 NG01–NG05 게시글을 각각 열고 실제 `<img>`의 표시·픽셀 decode·natural dimensions를 확인했다. 제품이 `URL.createObjectURL`에 전달하는 실제 Blob을 값 변경 없이 관측해 MIME·용량·SHA-256·URL 수명을 검사하고, 정상 인증된 HTTP content의 status/MIME/bytes hash와도 대조했다. 새로고침 뒤 같은 검사를 반복했다. route mock·fixture 이미지·응답 교체는 사용하지 않았다.

| 사례 | 실제 표시 MIME | 처음 열기 / 새로고침 | 저장 파일·HTTP·표시 Blob | 결과 |
| --- | --- | --- | --- | --- |
| NG01 | `image/jpeg` | 각각 1024×1024, decode 완료 | MIME·334,726 bytes·hash 일치 | PASS |
| NG02 | `image/jpeg` | 각각 1024×1024, decode 완료 | MIME·347,818 bytes·hash 일치 | PASS |
| NG03 | `image/jpeg` | 각각 1024×1024, decode 완료 | MIME·401,386 bytes·hash 일치 | PASS |
| NG04 | `image/png` | 각각 1024×1024, decode 완료 | MIME·2,622,959 bytes·hash 일치 | PASS |
| NG05 | `image/png` | 각각 1024×1024, decode 완료 | MIME·2,713,208 bytes·hash 일치 | PASS |

검사 도구의 초기 body/Blob 재조회 방식에서는 bytes 회수 실패가 있었다. 당시 실패 JSON은 같은 review 폴더에 보존했다. 원본 Blob과 독립적인 인증 HTTP 응답을 함께 확인하도록 검사 도구를 보완했고, 최종 다섯 사례는 모두 통과했다. 제품의 이미지 검증이나 hash·MIME·decode 기대값을 완화하지 않았다. 검사 도구 targeted lint 및 기본 dry run도 통과했다.

이 화면 후속 검사의 **새 image 제출 0 / 새 Gemini 요청 0**이며 기존 batch 총계는 **5 / 10**으로 그대로다. 기존 다섯 asset의 bytes hash도 불변이다. 정상 API로 활동/자동 생성 OFF와 enabled credential/암호화 secret 0을 재확인했고, job은 succeeded 5개·진행/미확정 0개다. backend는 인증된 종료 API, Next는 해당 시작 세션의 Ctrl-C로 종료했다. 소유 PID 및 8080/13000/18388 listener가 남아 있지 않다.

[실제 화면 5 PASS](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/ui-evidence.json) / [호출·파일 보존·로컬 검사](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/checks.json) / [키 정리](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/cleanup.json) / [프로세스 종료](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/shutdown.json).

화면 캡처는 작업 소유 `.local-diagnostics`의 private review 폴더에만 보관한다. 공개 artifact에 실제 본문·이미지 bytes·인증 값·raw Provider body를 복사하지 않았다. 검사자가 NG01과 NG04 캡처를 직접 열어 이미지 표시도 확인했다. 이것은 직접 USER CHECK나 캐릭터·장면 품질 평가가 아니다.

## 7. 남은 범위

F03의 **선택한 세 NanoGPT 모델 다섯 생성/첨부 경로**는 후속 5 PASS로 갱신하며, 기존 출력의 **Next 화면·새로고침 다섯 경로도 별도 PASS**다. F03의 전체 모델 옵션/출처/장기 품질까지 완료한 것은 아니다. F01 Opus 무차감, 정확한 NovelAI server parser/tokenizer 경계, 다른 Provider 추가 유료 회귀, custom/로컬 Comfy, 실제 WebP API 출력, 실제 출력의 static 화면, 설치 Tauri·Linux canonical visual·직접 USER CHECK·장기 SNS/Chat·운영 backup/실장애는 미측정/후속으로 유지한다.
