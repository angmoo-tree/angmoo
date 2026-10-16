# 관찰 종료 후 계측 해제·파일 갱신 중단 로컬 검증

- 실행일: 2026-10-16, Windows / Python 3.13.12.
- 저장소·브랜치: `angmoo-tree-angmoo` / `feat/vector-index-pending-work`.
- 시작 HEAD: `3274d7ec067435561d642be87b6fe88d852e5a0d`, 시작 작업 트리 clean.
- 범위: 사용자가 요청한 관찰 종료·재시작 수명 수정과 관련 검증, DCO 로컬 커밋.
- 증거 경로: `artifacts/observer-session-finalization-20261016/` (ignored).
- 이전 관찰 자료·업무 DB·계측 미사용 시의 작은 메타데이터 계산·AI 호출 정책은 변경하지 않았다.

## 원인과 구현

기존 memory observer의 `flush(final=True)`는 계측 연결을 해제하지 않고 매번 health JSON을
다시 썼다. SNS recorder는 `active.json`이 가리키는 세션의 종료 시각을 확인하기 전에
연결했으므로, 종료된 세션도 서버 재시작 때 다시 연결했다. 종료 후 갱신하지 않는
heartbeat 기한 때문에 대기 시간이 10ms가 되는 경로도 있었다.

| 경계 | 수정한 동작 |
| --- | --- |
| 수동 종료·tail 기한 도달 | 새 memory event 접수를 닫고 process-local sink를 해제한다. 이미 접수한 event를 저장한 뒤 최종 health를 한 번 기록한다. |
| 동시에 실행 중인 송신자 | 짧은 메모리 잠금으로 접수 종료와 마지막 queue 배출의 순서를 보장한다. 파일 I/O는 잠금 밖이다. 송신자는 잠금을 기다리지 않는다. |
| 종료 후 반복 호출 | 일반 flush·최종 flush·close를 반복해도 완료 파일을 다시 쓰지 않는다. 최종 health 쓰기 실패도 무한 반복하지 않으며 디스크 증거를 완료로 꾸미지 않는다. |
| 늦게 도착한 callback | 연결할 때 세션 ID를 고정한다. 종료된 callback으로 새 세션에 event를 넣을 수 없다. |
| 서버 재시작 | 종료·만료된 세션은 연결 전에 제외한다. 아직 유효한 세션의 재개는 유지한다. |
| 빠른 stop → start | 포인터가 바뀌어도 실제로 소유했던 세션을 마무리한다. 해당 세션의 접수/저장/실패 계수를 기준으로 기다리므로 다음 세션의 queue와 혼동하지 않는다. |
| 종료 후 runtime close | 이미 최종 기록이 있는 SNS/메모리 파일을 다시 갱신하지 않는다. 활성 세션의 정상 close 기록은 recorder 스레드가 남긴다. |
| idle | 새 세션 발견을 위한 기존 1초 간격 manifest 읽기만 남는다. 종료된 세션의 scheduler 조회·계측 파일 쓰기는 수행하지 않는다. |

`active.json`이나 기존 세션 폴더를 삭제해서 문제를 숨기지 않았다. `status`와 `export`는
기존 자료를 계속 읽고, 기록 누락·조기 종료·지원하지 않는 계측의 판정도 유지한다.
파일 내용과 수정 시각을 함께 비교해 종료 후 반복 tick, shutdown, 새 recorder 시작,
새 세션 사용, 이전 세션 export가 완료된 기존 기록을 바꾸지 않는지 검증했다.

## 검증 결과

수치는 실행별 결과이며 서로 겹치는 시험을 포함한다. 전체 backend/frontend 시험과
원격 CI를 실행하지 않았다. 사용자 자료와 외부 AI 대신 임시 DB·합성 event·mock HTTP를 사용했다.

| 실행 | 결과 | 증거 |
| --- | --- | --- |
| 수정 전 신규 회귀 | 7 FAIL / 5 PASS. 종료 연결 유지·오래된 callback 혼입·최종 쓰기 반복·종료 세션 재연결 재현 | `baseline-regression.log` |
| 초기 수명 수정 | 12 PASS | `lifecycle-first.log` |
| 기존 SNS/상황기억/메모리 observer·report·collector·전송·timing 및 신규 수명 회귀 | 100 PASS | `observer-regression.log` |
| 최종 수명·실제 worker/CLI/collector 연결 | 16 PASS | `lifecycle-worker-collector.log` |
| 별도 Python recorder 프로세스의 종료/만료 재연결 차단과 최종 수명 회귀 | 14 PASS | `lifecycle-fresh-process-final.log` |
| 아키텍처 경계 | PASS: modules=1552, edges=6718, legacy_exact_edges=0 | `architecture.log` |

추가 수명 시험은 수동 종료/시간 만료, 재시작, 종료 전에 이미 접수한 기록, 새 세션 시작,
연속 stop/start, 종료 상태에서의 대기 간격, 마지막 파일 쓰기 장애, 늦은 callback을 다룬다.
기존 파일 flush가 막힌 동안 실제 임시 SQLite writer가 완료되는 시험도 유지·통과했다.
관찰 기능을 위해 SQLite 쓰기나 업무 transaction을 새로 추가하지 않았다.

최종 source의 실제 `MemoryVectorProjection`·검증된 Vec1·고정 SDK/MockTransport·공식
start/status/stop/export CLI·PowerShell collector 연결도 다시 확인했다.
같이 준비한 7개는 HTTP 1회/벡터 7개/ack 7개, 순차 1→2→4 준비는 HTTP 3회/벡터 7개/ack 7개였다.
`m04/batch-seven/execution.json`, `m04/sequential-1-2-4/execution.json`에 격리 결과를 남겼다.
실제 유료 API나 사용자 기억을 사용한 결과가 아니다.

별도 Python 프로세스를 시작한 시험에서도 종료/만료된 세션의 연결은 없었고, 기존 파일의
내용·수정 시각·파일 개수가 유지됐다. 운영 서버 자체를 재시작한 시험과는 구분한다.

## 적용 경계와 되돌리기

이 결과는 로컬 소스와 격리 시험에 한정한다. Publish·PR·원격 CI·main 병합·운영 Docker
재시작/배포·설치판 변경·실제 SNS/AI 관찰은 수행하지 않았다. 운영 M04는 계속
`M04_TARGET_NOT_APPLIED` / `M04_SAMPLE_NOT_OBSERVED`다. 기존 사용자 관찰 폴더는 손대지 않았다.

UI/API/DB schema 변경은 없다. 사용자 노출 문구를 추가하지 않았으므로 번역 catalog도 그대로다.
수명 변경을 되돌려야 한다면 이 로컬 후속 커밋만 revert하고 관찰 자료는 보존한다.
되돌리면 종료 후 반복 갱신·재연결 문제도 돌아오므로 종료된 세션에 대한 검증을 함께 확인한다.
최종 로컬 커밋 SHA는 workspace의 10-16 실행 계획 후속 기록과 로컬 완료 증거에 남긴다.
