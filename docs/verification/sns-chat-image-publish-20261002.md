# SNS·Chat 이미지 통합 브랜치 게시 준비와 검증 기록

## 게시 범위

이 기록의 시작 원본은 `feat/sns-chat-image-integration`의 `1d1c961069f2522d19c1438efe8cf6ae55a97258`, 기준 main은 `1390ca4ddc275d3219b39b389c5368475e013b4c`이다. 이미지 생성·인식, SNS·Chat 첨부, MIME 판독과 PNG·JPEG·WebP 형식 보존, ComfyUI Partner 인증, 캐릭터 카드 중복 메타데이터 호환을 게시한다. 원본 작업 폴더의 Gemini 응답·SNS 관측 관련 미커밋 6개와 별도 보존 기간 개선 계획은 포함하지 않는다.

원본은 그대로 보존하고 독립 후보 clone에서 준비했다. 사용자 Docker, 설치 데이터, API 키와 유료 Provider는 이번 검증에 사용하지 않았다. 기존 실서비스 결과는 당시 실행 SHA의 증거이며 이번 후보에서 다시 실행했다는 의미가 아니다.

## DCO와 역사적 출처

최초 18개 커밋 중 7개에는 작성자 Signed-off-by가 없었다. 공개 전 작성자 본인의 sign-off를 추가하면서 부모가 바뀌는 후속 커밋을 함께 재구성했다. 원본 커밋 bundle과 미커밋 파일의 사본·hash, 18개 old/new 대응표는 로컬 진단 자료로 보존했다.

재구성된 초기 후보는 `4a91b383c133adb2805a529e75f1d4603ba6f2eb`이다. 원본 HEAD와 이 후보의 tree 차이는 `security/refactor_backend_additions.json`의 `commit`, `security/post_refactor_contract_changes.json`의 `implementation_commit` 출처 참조뿐이다. 각 역사적 metadata 도입 시점부터 같은 대응표를 적용했다. 제품 소스, 동결 main, PR258/PR263/PR290 checkpoint, 기존 검사 조건, 과거 실서비스 보고서의 실행 SHA는 바꾸지 않았다. 기존 DCO 검사 결과는 원본 7 FAIL, 재구성 후보 PASS다.

## 게시 준비에서 확인한 구조 문제와 수정

형식 보존 구현이 도입한 공통 이미지 검사는 도메인 오류 타입을 상속했다. 미디어 도메인이 그 integration을 호출하면서 `app.domains.media → app.integrations.media → app.domains.media` 패키지 순환이 생겼다. 도메인·설정·소유권에 의존하지 않는 `app.core.image_bytes`로 bytes 검사와 결과 타입을 옮겼다. 도메인과 기존 integration 경계에서 이전 공개 오류 타입으로 변환한다.

MIME 판독, 불일치 거절, bytes·해상도·픽셀·프레임 제한, Pillow verify와 실제 decode 검사는 유지한다. geometry 실패가 decode로 잘못 변환되지 않도록 중립 오류는 `Exception`을 상속한다. 추가 회귀 검사는 core geometry 단계, domain의 `asset_geometry_invalid`, 기존 integration의 `image_geometry_invalid`를 함께 확인한다. API·DB schema는 이 분리 때문에 변경하지 않는다.

현재 import inventory는 실제 소스에서 다시 생성했다. 역사적 source/behavior baseline을 덮어쓰지 않는다. MIME·카드 변경에서 누락된 최초 도입 자료와 정확한 전후 계약은 append-only metadata로 보완한다. 카드 중복을 실패로 기대하던 검사는 합의한 첫 정의 선택 정책과 JSON 중복 키 거절로 분리하고 선택 실패 시 fallback 금지 검사를 유지한다.

CI와 같은 사전 검사에서 L4의 현재 inventory가 오래된 import 수와 static parity test hash를 기록한 점도 확인했다. 원래 generator로 현재 module 1334, 내부 edge 5407, 외부 import 3933 및 실제 static test hash를 갱신했다. 순환과 legacy 예외는 모두 0이다. policy의 baseline commit, 동결 parity oracle·Memory predecessor와 원래 generator/검사 조건은 변경하지 않았다. 격리 contributor diagnostics는 SQLite·LadybugDB 및 v26 migration ready, scheduler stopped, Provider 호출 0을 확인했다.

현재 Hybrid/episode inventory도 기존 v25 기록에 머물러 있어, 이미지 계약·실제 source hash·v26 schema 147개 table과 revision `20260930_0104`를 원래 generator로 반영했다. 이전 파일은 모두 유지했고 새 이미지/migration 소스만 추가했다. bounds, defaults, embedding, 기능 계약, 별도 Gate, 동결 Memory predecessor와 generator는 변경하지 않았으며 원래 P8-L-R 검사가 통과했다.

전체 Backend의 L0 runtime 검사에서도 새 공통 module의 inventory 등록 누락을 재현했다. `app.core.image_bytes`의 중립 검사 책임을 기존 core 목록에 명시했다. core가 domain/integration/runtime을 import하지 못하는 원래 조건과 Docker 서비스·host publication·storage·release/supply-chain 계약은 유지한다.

ER0의 현재 runtime/SQL inventory에는 `main.py`·Chat model hash와 패치 전 dependency 버전이 남아 있었다. 원래 generator로 해당 현재 값만 갱신했고 기존 89개 migration, 24개 graph query, 44개 route 및 동결 parity corpus는 유지한다. 원래 8개 검사는 수정된 현재 소스의 전체 scan과 count·omission·hash·new-source 거절을 포함해 통과했다. 현재 PostgreSQL marker 목록은 역사적 schema/호환값/재도입 guard를 설명하는 것이며 PostgreSQL runtime을 추가하지 않는다.

## Hosted CI 연결

첫 PR CI에서 기존 캐릭터 request 검사의 명시 export 목록이 새 `getAgentCardMetadata`를 포함하지 않아 실패했다. 동결된 45개 endpoint·failure·session 검사는 그대로 두고 여섯 번째 추가 API의 encoded draft ID, metadata 전용 query, GET과 빈 body를 확인하도록 보완했다. Frontend session·state·Social·error parity도 함께 실행한다.

같은 PR의 보존 검사에서는 Pillow가 생성한 PNG bytes를 자동 parameter ID로 사용해 Windows와 Linux의 압축 결과 차이가 test node 이름으로 전파되는 문제가 확인됐다. MIME 불일치·손상 PNG·미지원 GIF의 기존 값과 assertion을 그대로 유지하고 세 parameter에 명시적인 의미별 ID를 부여한다. 이전 정확한 node에서 새 ID로 일대일 lineage를 기록하며 이전 introduction evidence나 동결 node 수를 덮어쓰지 않는다. 이는 제품 이미지 bytes를 통일하는 변경이 아니다.

원래 보존 검사는 이름을 바꾼 카드 테스트의 수집 node뿐 아니라 assertion helper lineage도 요구한다. 두 연결을 모두 명시하고 정확한 전후 기대값 기록으로 확인한다. 원래 보존 검사 조건과 immutable checkpoint는 유지한다.

Gitleaks 8.30.1의 현재 tree/949개 커밋 검사에서 17개의 비밀 오탐이 확인됐다. 공개 source Git blob 8개는 각 도입 커밋의 `commit:path`로, T5 checksum은 번들 bytes의 SHA-256으로 확인했다. 나머지는 두 합성 idempotency 식별자와 두 SQLAlchemy lease 만료 계산식이다. `generic-api-key`의 정확한 경로와 전체 line 조건만 추가한다. 다른 field·값·경로·추가 credential literal·폴더 단위 예외는 허용하지 않는다. 관련 회귀 검사로 값 변경과 다른 파일이 허용되지 않음을 확인한다. 기존 실제 비밀 탐지와 과거 fixture 예외는 유지한다.

기존 frontend job에 `playwright.image-integration.config.ts`를 연결한다. Next와 static의 동일 SNS·Chat 이미지 흐름 40개 검사를 실행하고 JUnit·실패 screenshot·trace를 artifact로 남긴다. 합성 fixture와 fake Provider를 사용하며 유료 API 키, 과거 로컬 DB·게시글·개인 캐릭터 카드에 의존하지 않는다. 기존 검사와 required context는 제거하지 않는다.

## 로컬 확인 범위

구조 분리 이후 이미지·미디어·캐릭터 HTTP 경계 회귀 검사는 **319 PASS**다. 의존성 패치 후 lint, typecheck, 카드 proxy, Next/static 빌드와 이미지 browser **40 PASS**를 다시 확인했다. 카드 browser는 **4 PASS / 1 SKIP**이며 SKIP은 개인 원본 fixture가 없는 선택적 검사다. 합성 카드·공유 화면 검사는 실행했다.

전체 Backend 실행은 `f72f0e4694e404ad63dd2125e49514b709d2b225`에서 시작해 **4,603 PASS / 31 SKIP / 4 FAIL**로 끝났다. 실행 중 현재 inventory를 보완했으므로 이를 최종 단일 SHA의 전체 PASS로 기록하지 않는다. 세 실패는 새 core module 등록과 현재 runtime/SQL source·dependency 목록 누락이 원인이었다. 나머지는 child transport 단계에 도달하기 전 5초 대기가 만료된 경우다. 원래 timeout과 테스트 조건은 변경하지 않았고, 해당 cancel/deadline 검사 두 건은 별도 재실행에서 통과했다. 최종 inventory 수정 후 실패 파일들과 Gitleaks 회귀를 함께 실행한 **23개 검사가 모두 PASS**다. 실패 결과와 재실행을 따로 보존하며 최종 고정 head의 전체 Backend 판정은 Hosted CI에서 확인한다.

원본 object·개인 카드·키 파일이 없는 clean clone의 `f3c0db69e06118d397a2b8337da3ba18e98796bf`에서 원래 DCO, import inventory, Frontend 보존, Backend 계약·node 보존 검사를 모두 통과했다. Backend 보존 검사의 보호 lineage와 현재 node는 **4,645개로 일치**했고 전후 계약 기록 37개를 검증했다. 이후 변경은 검토한 현재 runtime/SQL inventory와 이 요약이며, gate가 읽는 source·test·lock·출처 기록·동결 checkpoint의 변경 여부를 공개 전에 별도로 확인한다. 검증한 SHA와 이후 변경 영향 확인을 서로 다른 근거로 기록한다.

PR CI와 병합 후 main push CI는 각 SHA·run을 별도로 기록한다. 최종 PR·merge SHA와 main CI는 workspace 실행 receipt에 남기며 main에 결과만 직접 push하지 않는다.

## 남은 실서비스·사용자 확인

게시 전 의존성 감사에서 Python lock의 PyJWT 2.14.0·pypdf 6.16.1·urllib3 2.7.0과 Next 16.3.3의 알려진 취약점이 확인됐다. [PyJWT 공식 공지](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v), [pypdf 공식 release](https://github.com/py-pdf/pypdf/releases/tag/6.19.0), [urllib3 공식 release](https://github.com/urllib3/urllib3/releases/tag/2.8.0), [Next 공식 공지](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j)에 따라 PyJWT **2.15.0**, pypdf **6.19.0**, urllib3 **2.8.0**, Next와 대응 ESLint config **16.3.6**으로 정상 업데이트했다.

Python lock에서 바뀐 패키지는 앞의 3개뿐이며 PyJWT·urllib3는 기존 OCI SDK의 간접 의존성이다. 기존 Next OpenGraph 구현은 고정 SVG를 사용한다. 공지의 공격 조건과 현재 앱의 실제 노출을 구분하면서 패치 버전으로 갱신했다. `sentencepiece 0.2.2`는 이번 업데이트 전에 이미 이미지 브랜치 lock에 있었고 NOTICE 누락만 보완했다. 기존 취약점 감사 조건을 낮추거나 ignore하지 않았으며 갱신된 lock의 uv audit, frontend production audit와 license/NOTICE 검사가 통과했다. 패치 후 Backend와 Next/static 결과는 위에 구분해 기록했다. 갱신 전 중단된 전체 Backend 실행은 완료 PASS로 기록하지 않는다.

- NovelAI Opus 무차감 NA01/F01은 이번 사용자의 Anlas 소비 테스트 선택으로 실행하지 않았다.
- NovelAI 모델 전용 tokenizer/parser와 정확한 길이 계산 동등성, 캐릭터 일관성·이미지 품질, 자연 SNS 활동과 개인 환경 USER CHECK는 별도다.
- 실제 Routine contract-v2는 게시글·장면을 함께 만드는 1회 호출이다. 예전 4회 유지 계획이나 준비 호출 포함 사용량과 혼동하지 않는다.
- 최초 실서비스 17건의 12 PASS/5 NanoGPT FAIL 및 후속 NanoGPT 5 PASS·Next 표시 5 PASS는 이전 검증 문서의 해당 실행 범위다.
- 이슈 #348은 `Refs #348`로 참조한다. 남은 항목을 통합 CI PASS로 확대하거나 자동 종료하지 않는다.

로컬 raw evidence, DB, 키 JSON, 개인 이미지·카드·대화·화면은 공개하지 않는다. 이 문서의 요약과 저장소에 추적된 합성 회귀 fixture만 clone 가능한 자료다.
