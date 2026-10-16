# Device Home 갱신·환경 동기화·기억 처리 관찰 로컬 검증

- 실행일: 2026-10-16, Windows / Python 3.13.12 / google-genai 2.17.0.
- 구현 저장소: `angmoo-tree-angmoo`, 브랜치 `feat/vector-index-pending-work`.
- 시작 HEAD: `de4a71f7a3429a2b48594891ba2a2b3969cac02f`, 시작 작업 트리 clean.
- 범위: workspace의 10-16 Home·환경 통합 계획 I00–I63. 기존 vector pending-work를 보존한 후속 변경이다.
- 원격 게시·PR·CI·main 병합·Docker 배포·설치판 변경·실제 AI 호출은 수행하지 않았다.
- 증거: `artifacts/device-home-refresh-environment-20261016/` (ignored 로컬 산출물).

## 구현 결과

| 영역 | 구현과 책임 |
| --- | --- |
| Home | feature controller/hook이 한 수명의 성공 snapshot, 최초 ensure, GET, 취소·generation·후속 1건을 관리한다. 성공한 빈 목록도 보존한다. |
| 범위 | composition의 auth/runtime key가 사용자·세션·서버 교체 시 controller와 unread ID를 교체한다. 오래된 응답을 적용하지 않는다. |
| 표시 | 처음에는 로딩을 보여 주고 복귀에는 기존 World·배지·포커스를 유지한다. transient 실패는 KO/EN stale 안내·재시도, 권한/schema 거부는 자료 제거다. LOCAL 디자인과 공용 token/button을 사용한다. |
| 환경 | 서버의 `active_owner`에서 token 없는 화면은 GET만 한다. 자신의 token은 실제 감지 값 변경/60초 갱신으로 유지한다. typed 409 재조회와 503의 3회/8초 복구를 보존한다. |
| 계측 | core의 중립 port를 runtime recorder가 기존 opt-in 수명에 연결한다. queue·prepare/apply·brief·FTS·vector·provider·공용 writer 경계에 event/span을 추가했다. |
| 독립 전송 | SDK 공개 HTTPX hook으로 실제 attempt를 기록한다. adapter의 고정 `physical_attempts`나 vector 행 수를 HTTP 원장으로 사용하지 않는다. |
| 수집 | 공식 CLI `memory-preflight`, 상태/내보내기, 읽기 전용 probe와 PowerShell collector를 확장했다. 실행 UID/GID는 Docker의 비root 앱 계정을 읽어 확인한 뒤 사용한다. |

Backend Identity의 API, lease 120초, owner·CSRF·revision·sequence 보호는 변경하지 않았다.
기억 생성 내용·batch 상한·provider retry·canonical fence·스케줄러와 두 확인 작업의 업무 정책도 유지했다.
관찰 중 carry-in claim의 scope를 알기 위한 최대 64개 ID 조회 한 번은 writer 밖에서만 추가한다.

## Home 요청과 화면 전후

기준 코드를 별도로 빌드한 `baseline-browser.log`/`baseline.json`의 KO/EN 2개 재현은
지연된 복귀 응답 동안 기존 World DOM이 사라지고 ensure가 다시 발생하는 것을 확인했다.
활성 lease에 token 없는 감지기가 POST하여 409가 발생하는 기준 동작도 재현했다.

수정 후 Next production·static export의 14개 브라우저 시험은 모두 통과했다.

- 같은 복귀의 focus+visibility: Home GET 증가 **1회**, ensure 증가 **0회**.
- token 없는 활성 lease: 환경 POST **0회**. 기존 성공 목록·99+ 배지·동일 DOM·키보드 포커스 유지.
- 503에서는 기존 목록+재시도, 403/schema mismatch에서는 제거, 성공 빈 배열에서는 빈 상태.
- 환경 재확인 실패로 이미 준비된 Home을 초기화하지 않으며 숨김 중 늦은 응답을 버린다.
- 두 브라우저와 실제 FastAPI Identity router·임시 SQLite: 첫 claim **1회**, 다른 화면과 새로고침 **0회**.
  fixture 시계로 권한자의 60초 갱신과 120초 만료 후 다른 화면의 인수를 검증했다.
  실제 동시 소유 충돌은 409, 비인증은 401, 잘못된 Origin은 403을 유지했다.
- KO/EN, 360px·200% 대표 확대·44px 조작 영역, runtime 범위 교체를 검사했다.

실제 API 시험은 해당 route만 disposable 서버로 전달하며 다른 Home 응답은 기존 합성 fixture다.
실제 설치 앱 또는 사용자 브라우저의 데이터로 수행한 시험이 아니다.

## 계측 계약과 판독

Capability는 `memory-pipeline-observation.v1`, snapshot은 `memory-pipeline-snapshot.v1`이다.
프로세스/session/scope/run/receipt/item/version/hash/profile/generation/batch/logical HTTP/attempt/span/queue ID를 연결한다.
API 키는 세션별 별칭만, 본문은 길이·hash만 기록한다. credential token·원문·vector·SQL parameter는 기록하지 않는다.

- queue 512건, event 16KiB, 프로세스의 session 출력 64MiB, 파일 part 4MiB 상한이다.
  기존 SNS 파일 한도와 별도이며 다중 프로세스 export는 총 64MiB를 읽은 뒤 PARTIAL로 제한한다.
- recorder 스레드가 파일·JSON·watermark를 소유한다. 송신자는 allowlist와 bounded enqueue만 수행한다.
  막힌 파일 flush 중에도 실제 SQLite writer가 완료되는 barrier 시험을 통과했다.
- 공용 SQLite helper와 Vec1/FTS의 실제 BEGIN/commit 경계를 측정한다. 기다림·보유·commit·정리를 구분한다.
  다른 DB나 중첩 구간을 더하지 않는다. 경쟁 후보는 같은 process clock/DB의 획득 대기와 보유가 겹친 경우만
  최대 256건 기록하며, 겹침만으로 지연 원인을 확정하지 않는다. 잘린 요약은 별도로 표시한다.
- prepare·brief·API·journal·item 반영·ack와 idle/yield를 분리한다. 30초는 검토 기준이며 업무 timeout이 아니다.
- canonical의 새 run·적용 receipt·등록 항목 분모, sink 이전 계수, sequence, 최종 watermark를 대조한다.
  누락·열린 span·지원하지 않는 전송·schema 부족·중간 DB 변경은 PARTIAL/UNKNOWN이다.
- probe는 `mode=ro`, `query_only`, canonical/FTS 250ms timeout·전체 2초 progress deadline,
  Vec1 adapter의 기존 읽기 연결 timeout 1초, 테이블별 1,000행 상한이다.
  canonical과 Vec1/FTS 간 원자적 snapshot을 보장하지 않으며 generation/DB 변경을 표시한다.
- `memory-pipeline/`의 capability-check, coverage, timeline, embedding-batches, writer-spans,
  snapshots/canonical-final, KO/EN delay-and-batch-review를 기존 export에 추가한다.
  보조 export 장애는 기존 SNS 자료를 보존하고 `memory_pipeline_export_failed`로 기록한다.

전송 지원은 고정 google-genai 2.17.0의 native async HTTPX 경로다. aiohttp가 설치된 실행본,
다른 provider, legacy sync API는 실제 시도 계수의 지원 대상으로 주장하지 않는다.
공용 helper 밖의 plain Session writer와 다른 프로세스는 미관측일 수 있다.
삭제돼 snapshot에서 사라진 항목, 시작 전 전송·수신, source 파일이 없는 frozen 실행본의 소스 해시는
현재 자료만으로 복원하지 않는다. 기록 완전성은 저장 정합성·실제 기억 검색 소비·AI 품질 PASS가 아니다.

## 관련 검증

아래 수는 실행별 결과이며 중복 실행이 있어 합산한 고유 테스트 수가 아니다.

| 검증 | 결과 | 증거 |
| --- | --- | --- |
| 환경 계약·embedding transport·vector delivery 초기 회귀 | 44 PASS | backend-first.log |
| pending/recovery/SQLite retry·취소·post-commit·delivery | 49 PASS, native 2건 후속 실행 | vector-sqlite-regression.log |
| 실제 Vec1·WAL·scheduler heartbeat·로컬 수신 복구 | 2 PASS | native-contention-final.log |
| recorder·collector·상황기억·공용 writer·계측·전송 | 90 PASS | observer-regression-final.log |
| pending/recovery + 실제 worker/CLI/collector | 18 PASS | pending-preflight-final.log |
| 실제 SDK로 21개 분할·byte·actor·키 revision·설정 구분 | 5 PASS | embedding-groups-final.log |
| 보조 export 장애·privacy·HTTP/응답 계측 | 18 PASS | final-privacy-export.log |
| 최종 source의 M04·outbox checkpoint·보고서 판독 | 9 PASS | final-source-preflight.log |
| 최종 SQLite checkout/transaction 계측·복구 경계 | 13 PASS | sqlite-boundaries-final.log |
| Home controller | 4 PASS | home-unit-reviewed.log |
| 기존 unread controller | 3 PASS | home-notification-unit-final.log 내 해당 3건 |
| 환경·i18n·취소·typed 409/503·lease 단위 | PASS | environment-unit-final.log |
| Next/static 실제 브라우저 | 14 PASS | browser-reviewed.log, browser.json |
| build / build:static / typecheck / KO·EN catalog | PASS | build-next-final.log, build-static-final.log, typecheck.log, catalog.log |
| 변경 파일 ESLint | PASS | frontend-lint.log (진단 없음) |
| backend/frontend 경계·디자인 | PASS | 최종 정적 검사 원장 |

초기 네이티브 2건 skip은 기존 fixture에 DLL 환경변수를 전달하지 않은 실행이었다. 이후
`ANGMOO_TEST_VEC1_EXTENSION`을 지정하여 **두 건 모두 실제 실행했다**. skip/xfail을 추가해 통과시키지 않았다.
브라우저의 시험 서버 Windows 경로와 route 전달 Content-Type 누락은 fixture에서 수정했다.
Unicode byte 분할은 UTF-8 길이 외에 JSON escape/envelope 상한이 적용되어 20건이 5+5+5+5로 나뉜다.
이는 기존 정책이며 정책을 넓혀 시험의 예상 숫자에 맞추지 않았다.

구조 검사의 이전 Home marker는 인증과 환경 준비를 한 변수로 취급했다. 현행 두 prop 및 auth/runtime
key 보호를 요구하도록 갱신했으며 import 예외/권한 완화는 없다. 디자인 baseline은 변경된 component의
SHA와 KO/EN Next/static 진단 screenshot 호출 한 곳(63→64)을 갱신했다. 기존 canonical PNG 11개·
시각 허용 오차는 유지했고 raw color 수는 **1,129로 동일**하다.

## M04 격리 실행과 운영 적용

검증한 Vec1 DLL SHA256: `4bc0b513e9b6a630159212452ff3fc70b86d89c6ef63f6ea92ae075599e65303`.
검증된 기존 artifact와 manifest를 임시 source/runtime에 복사했다. 제품 resource나 사용자 DB를 교체하지 않았다.
실제 `MemoryVectorProjection.start()` 작업자, SNSObserver, 고정 SDK/MockTransport, 공식 start/status/stop/export
CLI와 PowerShell collector를 연결했다. 시험 코드가 event 파일을 대신 작성하지 않았다.

| 준비 조건 | 독립 HTTP 요청 | 실제 Vec1 identity | 완료 ack | 증거 종류 |
| --- | --- | --- | --- | --- |
| 같은 그룹의 7개 준비 | 1 | 7 | 7 | isolated_fixture |
| 이전 묶음 완료 뒤 1→2→4 준비 | 3 (1+2+4) | 7 | 7 | isolated_fixture |

순차 사례는 준비된 subset을 기존 explicit preparation과 같은 enqueue 계약으로 접수한 시험이다.
임의 저장 7건이 언제나 이 순서로 나뉜다는 의미가 아니다. 일반 outbox 도착/준비 시점에서는
더 작은 묶음도 정상이다. raw 등록만 한 초기 fixture의 1건씩 분할 결과도 호출 정책 변경으로 덮지 않았다.

**M02 로컬 구현, M03 관련 회귀, M04 격리 실행은 완료했다. 운영 실행본은
`M04_TARGET_NOT_APPLIED` / `M04_SAMPLE_NOT_OBSERVED`다.** 현재 자료로 Bram의 이전 지연 원인이나
그때의 HTTP 횟수를 소급 확정하지 않는다. 다음 운영 관찰 전에 승인된 방법으로 실행본을 적용한 뒤
기존 세션 절차의 `memory-preflight`, fresh process health, 실제 sample, 종료 watermark/export를 확인한다.
설치 앱을 확인하게 되면 workspace 설치 identity 절차를 먼저 따른다.

## 재실행 범위

backend의 새 memory_pipeline/embedding_observation 시험, 기존 pending/recovery/contention,
준비 페이지·SQLite helper·SNS/상황 observer·collector 시험만 실행했다. 프론트엔드는 Home/환경/알림
controller와 전용 Playwright 설정을 사용했다. 전체 backend/frontend suite, remote CI, Windows
패키징, 실제 SNS/유료 AI/사용자 설치 확인은 이 작업의 검증으로 실행하지 않았다.

최종 로컬 commit SHA와 I00–I63 체크리스트는 workspace의 해당 실행 계획에 기록한다.

## 관찰 종료 수명 후속 보완

I00–I63 완료 뒤 종료된 세션의 계측 연결·health 반복 쓰기·재시작 재연결 결함을 별도로 확인했다.
동일 로컬 브랜치에서 수행한 수정과 수명/기존 기능 회귀는
[관찰 종료 후 계측 해제 검증](observer-session-finalization-20261016.md)에 구분해 기록한다.
앞선 검증이 이 종료 경계까지 증명했다고 소급 해석하지 않는다.
