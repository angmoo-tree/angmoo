# SNS·Chat 이미지 재검토 9건 수정 및 검증 기록

사용자가 `4ed3e8f96d471f42c7616044a322c18904c5c155`의 재검토에서 제시한 동작 문제 6건과 계약 공백 3건을 보완했다. 제품 코드 source commits는 `69e8de7603ebc290aa66cca43e377bae3b5709c4`, `55d184ca5efdce1ff9f72c3583d119cea56abce1`이며 작업 브랜치는 `feat/sns-chat-image-integration`이다. main `1390ca4ddc275d3219b39b389c5368475e013b4c`에서 분기한 기존 작업을 이어갔으며 main에는 반영하지 않았다.

**현재 판정:** 재현한 6건과 참조 적용 상태·Chat 복구 선택 2건은 수정하고 로컬 회귀를 확인했다. NovelAI 정확한 V4.5 토큰 검증은 아직 입증하지 못해 미검증 상태를 명시하고 생성을 차단했다. 따라서 초기 P00–P12의 “계획대로 누락 없이 전체 구현 완료” 판정은 철회한다. 정확한 NovelAI 검증과 F01–F11 실서비스/품질/환경 검증은 계속 남는다.

## 9건별 변경

| ID | 변경과 결과 | 주요 코드·검사 |
| --- | --- | --- |
| REV01 | 외부 이미지 수신을 `result_received` 시도로 기록하고 로컬 저장 실패를 `result_pending`으로 처리한다. 픽셀과 메타데이터를 한 atomic journal에 기록한다. journal 쓰기 실패는 실행 중인 worker의 제한된 버퍼로 복구하고, 버퍼까지 유실되면 결과 미확정으로 재제출을 차단한다. journal은 있고 별도 pixels 쓰기만 실패한 경우 새 worker가 같은 결과를 복구한다. | `image_intent_generation.py`; 원래 manifest 오류 검사와 새 journal/pixels 실패·재시작 검사. Provider 호출 1회 유지. |
| REV02 | ComfyUI 확정 실패 후 명시적 재시도는 이전 attempt의 receipt를 보존하고 현재 job의 receipt를 비워 새 예약을 만든다. 결과 미확정의 같은 ID 조회는 기존 예약/receipt를 사용하며 새 제출로 바꾸지 않는다. | 원래 확정 실패→재시도 검사, 기존 unknown/receipt 회귀. |
| REV03 | 참조 유무로 실제 workflow를 먼저 선택하고 그 binding을 기준으로 negative 적용 여부를 계산한다. 선택한 workflow를 intent에 고정한다. | 원래 참조 workflow에 negative 없음/텍스트 workflow에 negative 있음 검사. 저장한 `blur`가 실제 텍스트 workflow에 들어간다. |
| REV04 | Chat 메시지 접수 transaction에서 공통 분석 job을 공유하거나 새 인식 attempt를 원자적으로 예약한다. 응답 단계는 이 ID를 소비한다. 접수 후 인식 설정이 바뀌면 새 유료 분석을 몰래 예약하지 않는다. | 원래 접수 직후 예약 1개 검사, 공유/rollback/Chat–SNS 마지막 잔여량 동시 예약/설정 변경과 재시도 시 새 분석 ID에 오래된 snapshot을 재사용하지 않는 검사. 업로드·접수에서 AI 호출 0. |
| REV05 | 모델별 endpoint 옵션과 참조 width/height/MIME/bytes 제약을 `domains/media/api_image_policy.py`의 공통 정책으로 검증한다. 캐릭터 설정은 media의 지원 계약을 통해 이 정책을 사용한다. 저장 단계, intent 준비, adapter 전송 직전에 같은 제약을 적용하고 endpoint 변경도 검사한다. | 1×1 참조 거절, 미지원 resolution 저장 거절, min/max/bytes/MIME 경계, NanoGPT/OpenRouter 대소문자별 옵션 검사. |
| REV06 | 정상 빈 문자열·공백 scene은 intent를 만들지 않는다. 타입 오류·길이 초과·LLM scene 오류는 본문 게시를 보존하면서 blocked로 구분한다. 기존 빈 scene 오류 기대값을 계약대로 정정했다. | 원래 빈 scene 검사와 invalid type/length 분리 검사. |
| REV07 | 공식 문서의 T5 계열/약 512 토큰 설명과 로컬 자원의 해시 일치는 정확한 V4.5 parser·가중치·특수 토큰 계산의 동일성을 증명하지 않는다. `prompt_validation.exact_verified=false`를 서버가 결정하고 catalog·설정·UI에 제공한다. 자동 생성 활성화, 기존 queued job과 실제 adapter 호출을 모두 `novelai_prompt_validation_unverified`로 차단한다. | 실제 기본 client의 HTTP 0 검사, 설정/queued job 차단, 양쪽 화면의 비활성화 검사. **정확성 입증은 미완료.** |
| REV08 | 저장 선호와 참조 출처 `override/card/profile/none`, 적용 가능 상태 `off/forced_off/available/missing/invalid`, 실제 준비 경로 `reference/text/unavailable/unconfigured`, scene-only 여부를 설정 응답과 UI에 제공한다. 조회만으로 새 managed asset을 만들지 않는다. 손상 이미지는 텍스트 생성으로 위장하지 않는다. | 출처 우선순위·읽기 무변경·손상 출처 검사, Next/static 화면의 실제 출처/텍스트 경로/참조 필수 경로 표시. |
| REV09 | 이미지 인식 `waiting/recognized/failed/excluded` 상태를 응답 요청과 UI에 분리한다. 텍스트+이미지 인식 실패에서만 “사진 없이 이 텍스트로 진행”을 제공한다. 명시적 `exclude_attachment=true` 재시도는 같은 원본 메시지·response slot을 사용하고 이미지만 해당 응답에서 제외한다. 원본 첨부/본문은 보존하며 idempotency 충돌과 image-only 복구를 거절한다. | 실패→텍스트만 실제 fake LangGraph 응답 완료, 원본 메시지/이미지/slot 보존, 인식 추가 호출 0, Next/static 버튼 요청·최종 응답·실패 bubble 제거 검사. |

## 검증 범위

- 이미지 통합 suite: **140 PASS**. 기존 110개에 원래 재현 7개와 새 경계/복구 23개를 추가했다. 테스트 수를 합산할 때 중복 실행은 다시 더하지 않는다.
- 7개 원래 재현과 23개 새 계약 검사 별도 경계 실행: **23 PASS**, 원래 7개는 최종 suite에서도 PASS. 원래 재현의 단언은 보존했다.
- 관련 Chat·media·기존 이미지/소유권 회귀: **871 PASS / 6 SKIP**. skip은 모두 기존 `explicit performance run` 조건이다. 전체 backend suite를 이번에 재실행했다는 의미가 아니다.
- 구조·기존 경계·앱 factory 회귀: **105 PASS**. 원래 검사/단언을 유지했다.
- Next/static Playwright: **30 PASS**. 기존 20개와 신규 10개를 포함한다. 재시도 없이 통과했다. 이미지 실패 후 명시적 복구는 stream의 일시적 delta만 보지 않고 committed 요청 조회·thread 갱신·실패 bubble 제거까지 확인했다.
- `typecheck`, `lint`, `build`, `build:static`, backend/frontend architecture, 현재 import inventory, frontend design 계약 PASS. UI는 기존 구성요소·의미 토큰을 재사용한 `LOCAL` 변경이다. 보호된 색상/시각 기준과 역사 checker를 완화하지 않았다.
- 원래 전체 보존 checker의 `--contracts --nodes`: **protected lineages 4458 / current 4458 / items 37 PASS**. 정확한 product delta와 최초 도입 근거를 포함하며 원래 검사 규칙을 변경하지 않았다. 결과는 최종 JSON과 `preservation-final.log`에 기록했다. 과거 checkpoint와 원본 DB/migration은 변경하지 않는다. 누락된 역사 검증 JSON은 실제 최초 커밋 `4ed3e8f9`의 원본 blob로 추가 기록하고 과거 파일은 그대로 유지했다. 새 소스 3개/재현·경계 29개는 `69e8de76`, 추가 cache-binding 경계 1개는 `55d184ca`의 정확한 최초 도입으로 append했다.

생성 결과 복구 검사는 임시 SQLite·합성 이미지·fake transport를 사용했다. backend 실행은 `tests.offline_guard`로 외부 socket을 차단했다. 브라우저는 테스트 서버와 fixture API만 사용했다. 이번 수정 작업의 실 생성 API·실 인식 API 요청은 각각 **0회**이며, 이전 승인된 Gemini 실 인식 결과를 새 HEAD의 실서비스 PASS로 재사용하지 않는다.

NovelAI 기존 wire/Opus/ZIP 검사는 테스트에서만 합성 `exact_verified=true`를 주입하여 serializer·계정 규칙을 독립적으로 확인한다. 이는 실제 토큰 검증 성공을 뜻하지 않는다. **실제 API 키를 나중에 넣어도 현재 NovelAI 생성은 gate가 차단한다.** 제품에는 사용자 설정·connection 응답으로 이 gate를 해제하는 우회 경로가 없다. 런타임 다운로드나 임의 글자수 환산도 추가하지 않았다.

## 실행과 원본 증거

명령은 제품 저장소에서 실행했고, backend의 `PYTHONPATH`는 해당 backend와 `backend/tests`, `APP_SECRET`은 합성 값만 사용했다.

```powershell
# backend에서, 저장소의 기존 venv 사용
.\.venv\Scripts\python.exe -m pytest -q -p tests.offline_guard tests/image_integration --junitxml=../artifacts/image-integration-fixes/image-suite-complete.xml
# 관련 검사 범위/고유 결과는 related-regressions.xml에 보존

# 제품 저장소에서
pnpm --dir frontend typecheck
pnpm --dir frontend lint
pnpm --dir frontend build
pnpm --dir frontend build:static
backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_design_contract.py --check
backend/.venv/Scripts/python.exe scripts/ci/generate_architecture_inventory.py --check

# browser-tests에서, 두 테스트 서버를 Playwright가 기동/종료
pnpm exec playwright test --config=playwright.image-integration.config.ts --output=../artifacts/image-integration-fixes/browser-verified '--reporter=json,list'
```

기존 `artifacts/image-integration-review`의 7 FAIL 원본·기존 110 PASS·finding JSON은 수정하지 않았다. 새 증거는 `artifacts/image-integration-fixes`에 별도로 보존한다. 도중 실패 원본도 보존한다: 처음에는 ComfyUI 확정 실패를 unknown으로 분류한 1건, 신규 테스트의 잘못된 이벤트 필드 1건, NovelAI gate를 적용한 뒤 serializer 단독 검사 분리를 하기 전 6건이 있었다. 모두 실제 수정 후 재검증했다. browser CLI의 쉼표 전달 오류는 제품 테스트 실행 전의 명령 오류이며 별도 로그에 남겼다.

Git에 포함한 재현 검사는 `backend/tests/image_integration/test_plan_review_regressions.py`, 새 계약 검사는 `test_plan_recovery_contracts.py`다. 원래 재현 스크립트와 비교한 차이는 module docstring뿐이다. 결과 JSON은 보고서 해시와 정확한 commit·test/node 결과를 기록한다.

## 후속과 제한

NovelAI V4.5의 정확한 token resource/parser revision·특수 토큰/가중치 처리·Variety Boost 길이 계산을 공개 근거와 고정 경계 fixture로 입증해야 한다. 근거가 확보되어도 모델별 한도와 실제 요청 비교 검증을 거쳐야 하며 단순히 `exact_verified`를 true로 바꾸는 것은 완료 방법이 아니다.

공식 근거: [NovelAI 모델 설명](https://docs.novelai.net/en/image/models/), [강조/약화 문법](https://docs.novelai.net/en/image/strengthening-weakening/), [NovelAI T5 tokenizer 비교](https://github.com/NovelAI/t5/blob/main/docs/tokenizers.md). 이 문서들은 T5/기능 설명의 근거이고 Angmoo 로컬 parser의 정확성 인증 자료가 아니다.

F01–F11, 생성 실제 계정의 인증·비용·참조 품질, ComfyUI 실제 모델/외부 API 노드, 나머지 인식 조합·장기 자연활동·backup/restore·설치환경·Linux pixel baseline·USER CHECK는 계속 별도다. Docker/설치 데이터/기존 키를 읽거나 변경하지 않았고 push·CI·PR·main 병합·배포는 수행하지 않았다. 로컬 source와 기록 commit만 만든다.
