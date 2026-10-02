# NanoGPT `provider_image_invalid` 원인 조사 — 2026-10-01

이 문서는 조사 당시 근거와 이후 보완 결과를 구분한 저장소 기록이다. 아래 `artifacts/` 링크는 이 작업 환경에 보존한 로컬 상세 증거이며 Git 추적과 Docker 빌드 입력에서 제외한다. 저장소를 clone하면 해당 자료는 포함되지 않는다. 원 실패·합성 재현·공식 명세 사본과 당시 진단 스크립트는 로컬에 유지하며, 조사 결과·확정할 수 없는 부분·후속 성공 범위는 이 문서에 남긴다.

## 현재 판정

NG01–NG05가 실패한 공통 위치는 Angmoo 이미지 adapter의 응답 JSON/base64/이미지 검증 단계다. HTTP 오류나 게시글 저장 단계에서 발생한 실패가 아니다. 다만 이 다섯 요청의 원 응답 body와 상세 exception cause를 보존하지 않았으므로 **당시 실패의 정확한 필드·인코딩·MIME 차이는 아직 확정하지 못했다.**

추가 유료 요청 없이 현재 코드의 호환성 문제를 재현했다. 유효한 JPEG·WebP를 `data[0].b64_json`으로 보내더라도 `media_type`이 없으면 PNG로 간주하여 `provider_image_invalid`로 거절한다. 이는 확인된 코드 문제지만 **NG01–NG05의 실제 응답이 JPEG·WebP였다는 증거는 아니다.** 다른 envelope, data URL, URL-only도 같은 오류가 되므로 오류 코드만으로 이 가설들 중 하나를 고를 수 없다.

## 기존 실패와 코드 근거

- 기존 실제 요청 5건 모두 사례당 이미지 제출 1회·HTTP 200·job 1개·`provider_image_invalid`·첨부 없음이다. [기존 실패 요약](../../artifacts/nanogpt-response-diagnosis-20261001/original-failure-summary.json)
- 세 모델(Krea 2 Turbo, Z-Image Turbo, Nano Banana 2), 참조 OFF와 ON 모두 실패했다. 참조 없는 NG03에는 외형·스타일도 없었지만 유효한 장면과 실제 이미지 요청은 존재했다. 특정 참조 업로드 문제만으로 전체 실패를 설명할 수 없다.
- `backend/app/integrations/image_api.py:98` 이후 코드는 `body["data"]` → 정확히 한 항목 → `image["b64_json"]` → strict base64 decode → `image.get("media_type") or "image/png"` → signature/픽셀 검증을 순서대로 요구한다. JSON, 필드, base64, MIME, 이미지 검증 실패를 `provider_image_invalid` 한 코드로 묶는다.
- `backend/app/integrations/media/images.py:152` 이후 signature 검증은 선언 MIME과 실제 bytes가 맞는지 검사한다. 이 검증은 정상이며, MIME이 없는 모든 응답을 PNG로 가정하는 adapter 분기가 호환성 문제다.
- `backend/app/domains/social/service/image_intent_generation.py:344` 이후에는 safe error code를 작업에 저장하고 원 exception cause를 보존하지 않는다. 이 경로에서는 `ImageResult`를 받지 못하므로 이미지 저장·게시글 첨부 단계에 도달하지 않는다.
- `backend/tests/image_integration/test_providers.py:64`의 6개 API 모델 모의 응답은 모두 같은 PNG bytes와 `media_type="image/png"`를 반환한다. 이런 검사는 모델별 요청 직렬화에는 의미가 있지만 MIME 없는 JPEG·WebP 응답 호환성을 검증하지 않는다.

## 공식 명세 확인

1. [NanoGPT Image API](https://docs.nano-gpt.com/api-reference/image-generation)와 [Generate Images](https://docs.nano-gpt.com/api-reference/endpoint/image-api-generate)는 이번에 호출한 `POST /api/v1/images`의 JSON 입력, 모델 옵션, `input_references`를 문서화한다. 확인한 페이지에는 성공 이미지 응답 필드의 명세/예시가 없다.
2. [OpenAI-compatible 이미지 생성](https://docs.nano-gpt.com/api-reference/endpoint/image-generation-openai)은 다른 호환 경로인 `/v1/images/generations`의 `data[].b64_json` 기본 응답과 `data[].url` 선택 응답을 명시한다. 확인한 schema에는 항목의 `media_type`이 없다. **이 schema를 이번 normalized `/api/v1/images`의 실제 응답이 동일했다는 증거로 쓰지 않는다.**
3. 공개 [서비스 OpenAPI](https://nano-gpt.com/openapi.json)와 [문서 OpenAPI](https://docs.nano-gpt.com/api-reference/openapi.json)를 GET으로 저장했다. 전자는 `/api/v1/images/generations`, 후자는 `/v1/images/generations`의 응답을 제공하며, 두 파일 모두 이번 normalized `/api/v1/images`의 성공 응답 schema가 없다. [저장한 서비스 spec](../../artifacts/nanogpt-response-diagnosis-20261001/nanogpt-public-openapi.json) · [저장한 문서 spec](../../artifacts/nanogpt-response-diagnosis-20261001/nanogpt-docs-openapi.json)
4. [Usage API](https://docs.nano-gpt.com/api-reference/endpoint/usage)는 aggregate만 반환하고 원 요청/응답을 반환하지 않는다. [Request Billing](https://docs.nano-gpt.com/api-reference/endpoint/request-billing)은 보존한 `X-Request-ID`의 비용·토큰 조회다. 이미지 본문 복구 경로가 아니며 기존 실행은 해당 header도 보존하지 않았다. 이번 조사에서 인증 키를 읽거나 usage 요청을 다시 보내지 않았다.

## 네트워크 없는 재현

[재현 스크립트](../../artifacts/nanogpt-response-diagnosis-20261001/probe_response_shapes.py)는 외부 socket 연결을 금지하고 현재 제품 `ImageApiClient.generate`에 합성 응답만 공급한다. 실제 키를 읽지 않는다. 독립적인 공통 검증으로 PNG·JPEG·WebP가 모두 유효한 이미지임을 먼저 확인했다.

| 합성 응답 | 현재 adapter 동작 | 해석 |
| --- | --- | --- |
| PNG base64, MIME 없음 | 성공 | PNG 기본 가정과 맞음 |
| JPEG base64, MIME 없음 | `provider_image_invalid` | 정상 JPEG를 PNG로 선언하여 거절 |
| WebP base64, MIME 없음 | `provider_image_invalid` | 정상 WebP를 PNG로 선언하여 거절 |
| 같은 JPEG, 올바른 `media_type` 추가 | 성공 | bytes 손상이 원인이 아님 |
| 같은 WebP, 올바른 `media_type` 추가 | 성공 | bytes 손상이 원인이 아님 |
| 호환 API 문서의 URL-only | `provider_image_invalid` | `b64_json` 필드 없음. 현 계획에서 URL-only를 거절하는 계약과 별개로 실제 응답 확인이 필요 |
| `b64_json`에 data URL 전체를 넣은 가설 | `provider_image_invalid` | strict base64 decode 실패. 실제 NanoGPT 응답이라는 주장은 아님 |
| 다른 envelope인 가설 | `provider_image_invalid` | `data` 없음. 실제 NanoGPT 응답이라는 주장은 아님 |
| 이미지 2개 | `provider_image_invalid` | 요청당 1장 계약에 따른 의도된 거절 |

9개 재현 결과는 [offline-response-probes.json](../../artifacts/nanogpt-response-diagnosis-20261001/offline-response-probes.json)에 저장했다. 이는 코드 진단 결과이며 실제 원 응답의 재현이나 5개 실서비스 테스트의 PASS 전환이 아니다.

## 정확한 응답 차이를 확인할 준비

[단일 응답 진단 스크립트](../../artifacts/nanogpt-response-diagnosis-20261001/capture_one_response.py)를 준비하고 기본 dry run과 합성 응답의 안전한 구조 기록을 검증했다. **기본 실행에는 외부 요청과 키 읽기가 없다. 유료 실행은 아직 하지 않았다.**

별도로 1회가 승인되면 Krea 2 Turbo `krea-v2/turbo`, 참조 OFF, `resolution=1k`, `aspect_ratio=1:1`, `n=1`로 현재 adapter를 통과시킨다. 현재 공식 endpoint의 1k 공개 가격이 $0.01 이하임을 GET으로 확인한 경우만 제출한다. 별도 LLM 호출과 SNS 활동은 없다. 유료 POST 전에 로컬 guard를 작성하며 같은 진단을 다시 실행해도 두 번째 제출을 허용하지 않는다.

응답 body·base64·URL·API 키는 저장하지 않고 HTTP 상태/Content-Type, 알려진 필드명, 데이터 항목 수, base64 strict 검증 여부, 실제 PNG/JPEG/WebP 형식·크기, 실패 단계와 exception 종류만 저장한다. 이는 원인 조사용 transport 검사이며 SNS 첨부 통합 테스트의 성공으로 계산하지 않는다.

추가 제출을 별도로 확인하는 근거는 외부 테스트 계획 §3.5의 “실패 재시도나 추가 모델 실험의 허용 수량이 아님”과 §18의 17회 제한이다. 기존 본 검사 제출 17회를 모두 사용했다. [테스트 계획](../../../docs/plan/09-30%20SNS%20이미지%20생성%204개%20Provider%20실서비스%20연동과%20게시글%20첨부%20통합%20테스트%20계획.md)

## 수정 방향과 완료 경계

- 실제 normalized 응답을 관측한 뒤 Provider별 응답 계약을 고정한다. 공유 입력 형식이 같다는 이유로 응답 형식까지 같다고 가정하지 않는다.
- MIME 누락은 제한된 이미지 디코더로 PNG/JPEG/WebP 형식을 검증해 결정한다. 명시된 MIME과 bytes가 불일치하거나 손상·용량·크기 제한을 위반하면 계속 거절한다.
- 응답 거절 시 값 없는 단계별 진단을 남겨 유료 재요청 없이 JSON 구조/MIME/base64/픽셀 검증 실패를 구별한다.
- 제품 코드와 기존 17건 결과를 이번 조사에서 수정하지 않았다. 추가 유료 검사, Docker/설치 앱/DB 변경, CI/PR/push/merge도 수행하지 않았다. 실제 수정과 같은 Provider의 정상 생성·첨부 재검증은 별도 완료 판단이 필요하다.

## 2026-10-01 별도 구현·실제 재검증 결과

이 문서의 조사 당시 실행/실패 기록은 보존한다. 이후 사용자 수행 요청에 따라 [10-01 구현 계획](../../../docs/plan/10-01%20NanoGPT%20MIME%20누락%20보완과%20이미지%20형식%20보존·SNS%20첨부%20재검증%20코드%20구현%20계획.md) P00–P10을 수행했고 [새 검증 기록](./nanogpt-mime-format-retest-20261001.md)에 결과를 저장했다. 여기서 제안한 추가 단독 진단 1회는 실행하지 않았으며, 허용된 별도 SNS batch의 NG01–NG05 각 최초 제출 1회만 사용했다.

정식 parser의 PNG 기본 MIME을 제거하고 공통 제한 decode와 실제 PNG/JPEG/WebP MIME/형식 보존 저장·참조 전송을 연결했다. 새 실제 응답은 **다섯 건 모두 MIME 생략**, 그중 **JPEG 3건/PNG 2건**이었다. 같은 Routine 글의 저장·단일 첨부·인증 content·조회/복구 새 제출 0을 모두 확인해 **5 PASS**다. JPEG comment metadata를 제거하면서 형식을 유지했고 PNG는 원 bytes 그대로다. 원 다섯 실패 응답이 없으므로 그 실패 모두의 원인 확정까지 주장하지 않는다.

실제 WebP 및 실제 출력의 화면/USER CHECK는 미완료로 남긴다. 로컬 고유 backend 272개/Next-static fixture 40 PASS와 image 5/Gemini 10회·usage 차이 $0.1919·정상 키/프로세스 정리·새 커밋 없음은 새 기록을 따른다.

### 기존 실제 출력의 Next 화면 후속 확인

위 기록 이후 사용자 지시로 기존 NG01–NG05 게시글·출력을 정상 Next `/api/backend` 인증 경로에서 열고 새로고침해 **실제 화면 5 PASS**를 확인했다. JPEG 3장·PNG 2장 모두 1024×1024로 decode됐고 표시 Blob·인증 content·저장 파일의 MIME/용량/hash가 일치했다. 추가 image/Gemini 호출 **0/0**, 기존 5/10 총계 및 파일 hash 불변이다. 자동 생성 OFF·키 제거를 재확인하고 소유 서버를 종료했다. [화면 증거](../../artifacts/nanogpt-mime-retest-20261001/run-20261001T032012Z-334b42/ui-review-20261001T052846Z/ui-evidence.json)와 [최신 상세 §6.1](./nanogpt-mime-format-retest-20261001.md)을 따른다. 초기 실패·원 응답 원인 확정의 한계는 보존하며 실제 WebP·실제 static·설치 Tauri·직접 USER CHECK·품질 평가까지 완료한 것은 아니다.
