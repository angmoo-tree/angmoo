# SNS·Chat 이미지 통합 구현 및 검증 기록

사용자가 지정한 workspace 계획 P00–P12의 로컬 구현 기록이다. 시작 main `1390ca4ddc275d3219b39b389c5368475e013b4c`, 브랜치 `feat/sns-chat-image-integration`, 이슈 https://github.com/angmoo-tree/angmoo/issues/348. PR·push·CI·main 병합·배포·설치 앱 변경은 수행하지 않는다. 도커 없이 임시 SQLite와 테스트 전용 서버에서 검증한다.

## 구현 계약

- 네 Provider의 자동 생성은 신규 Routine 글·사용자 활성화·연결·사용량 상한·장면 검증을 모두 통과할 때만 접수한다. 마지막 작성은 image_prompt 장면 하나를 추가하며 기존 4회 LLM 흐름을 유지한다.
- NovelAI V4.5 Full 두 비용 모드, NanoGPT 3개/OpenRouter 3개 모델, ComfyUI API JSON/binding/두 샘플은 공통 request를 각 transport에 맞게 변환한다. 참조는 사용자 지정→PNG 카드 픽셀→프로필→없음 순이며 OFF는 파일 읽기부터 차단한다.
- immutable asset·analysis·intent revision, 원자적 예약, claim/lease, 제출 직전/결과 직전 검증, receipt·결과 spool을 사용한다. 결과 미확정 자동 재생성·무료 실패 시 유료 전환·다른 Provider 대체·과거 글 일괄 생성·다음 날 자동 backlog는 허용하지 않는다.
- 업로드한 SNS/Chat 이미지와 인식 키는 private 소유권을 갖는다. SNS의 이미지 단서는 같은 대상 recall에만 결합한다. Chat 분석은 Router/Planner/CRG 전에 끝나며 별도 image evidence로 전달한다. 본문은 이미지 분석으로 덮어쓰지 않는다.

## 확인한 증거

신규 이미지 통합 suite는 101 tests PASS. 참조 우선순위·OFF/no read·revision 변경, 네 생성 Provider의 fake physical-call count, 실제 serializer, durable 결과 복구, quota 동시 예약/날짜, v25 populated 업그레이드와 중간 DDL 실패 보존, 공통 Gemini SDK 입력, selected SNS/FTS budget, 실제 Chat LangGraph orchestration, 수동 SNS HTTP 첨부/재전송, private read/World Package exclusion, draft expiry/삭제를 포함한다. 텍스트 LLM 및 생성 transport는 fake이며 paid 생성 실제 품질은 검증하지 않는다.

기존 모든 v1–v25 합성 predecessor 보존 검사는 41 tests PASS. 과거 frozen manifest/DB 원본은 바꾸지 않았고 새로운 v26이 추가되었다. installer의 합성 predecessor 작성과 정적 matrix를 v25까지 확장했으며 실제 NSIS 설치나 hosted workflow는 실행하지 않았다.

허용된 Gemini `gemini-3.1-flash-lite`, medium 실 API: 실제 HTTP 5회, 16.032초, sdk_attempts=1, 대체 key/model 없음. R01 합성 파란 원/빨간 삼각형 묘사, R02 OCR `파란 컵 123` / `ANGMOO 42`, R03 동시 소비자 분석 한 번 공유, R04 실제 Chat workflow 이미지 단독/텍스트+이미지 두 경로, R05 OFF에서 기존 분석 재사용을 확인했다. 입력은 공개 합성 fixture이며 실제 SNS·대화·개인 사진을 사용하지 않았다.

미도리야 이즈쿠의 original scoped key를 검증된 실제 열린 UNC DB/secret에서 read-only로 읽고 메모리의 임시 인식 설정에만 복사했다. source DB·key·모델·활동·사용량 설정 변경 0. 키는 CLI·파일·로그·공개 DTO로 출력하지 않았다. 설치 identity는 identity_verified / running not_observed였다. 설치 앱 실행에 대한 PASS가 아니다.

실 API 공개 fixture 3회 usage는 input 각1172, output69/131/69, total1241/1450/1241, 두 번째 thoughts147. R04 두 임시 Chat DB를 닫기 전 usage를 수집하지 못했으므로 두 건 token 사용량은 미측정이다. 총 physical HTTP 5회는 HTTPX send hook으로 측정했다. 초기 SDK Part adapter 오류 두 번은 실제 wire 이전에 종료되어 physical HTTP 0이었다. 이를 추가 유료 시도나 성공 검사로 세지 않는다.

전체 회귀·보존 검사와 최종 UI evidence는 마감 검증 결과를 아래에 추가한다. 이전 첫 full run은 4208 PASS/117 FAIL/49 SKIP였으며 이 결과를 최종 PASS로 사용하지 않는다. 발견된 v26 신규 table identity delta, 레거시 이미지 worker 복원, fixture의 첨부 테이블/소유자 context/현재 schema 기대값, 정확한 product delta 기록을 수정했다.

## 후속 실서비스 검사

F01–F06: NovelAI 실계정 Opus 무차감·유료/Precise reference 비용, NanoGPT/OpenRouter 각6모델의 실제 인증·지원옵션·참조품질, 실제 ComfyUI 모델/외부 API 노드·receipt/history·reference 품질. 현재 생성 API 요청 0이며 모델 설치도 하지 않는다. NovelAI token budget은 별도 Apache-2.0 T5 SentencePiece 리소스를 이용한 보수적 사전 검사이며 NovelAI의 실제 token 가중치/파서와 동일함을 보증하지 않는다. 실제 positive/negative 한도와 Variety Boost 계산 호환성은 F01에서 비교해야 한다.

F07–F11: 나머지 Gemini 3조합 및 다양한 이미지/OCR 품질, 장기 SNS 자연활동·검색 품질, 재시작/백업 복원·설치 환경, 참조 생성 품질. 일반 백업은 DB+private assets+secret을 함께 보존해야 하며 이번 검사에서 실제 backup/restore를 PASS로 측정하지 않았다.

사용자 직접 화면 확인, 실제 생성 API, 고정 Linux pixel baseline, CI/PR/merge/release는 각각 별도 미수행이다. 외부 서비스 정책의 자동 호출 허용 범위도 실제 계정/서비스 약관에 맞춰 별도로 확인해야 하며 이 기록은 이용 권한이나 법률 판단을 보장하지 않는다.
