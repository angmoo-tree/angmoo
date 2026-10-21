# Termux 시험용 scheduler heartbeat 복구

## 범위

기준 `639eaf80f1cbeb8742a81a7fb4f29923ae494919`의 시험용 Chat·기동·작업자 시간 예산과 실행기 로그 보존을 이어받는다. `test/termux-scheduler-recovery-power` 로컬 브랜치에만 적용하며 push/PR/CI/main 병합을 수행하지 않는다. 새 migration, API 계약, 사용자 문구, frontend 변경은 없다.

## 수정

- 최초 heartbeat부터 대기·큐·DB 재시도에 동일한 monotonic deadline을 전달한다. 최대 2초와 마지막 성공 lease의 drain + 1초 안전 여유를 유지한다.
- 해당 await 경계의 timeout과 writer의 명시적 deadline만 `SchedulerHeartbeatDeadlineExceeded`로 분류한다. 일반 TimeoutError·취소·실행권 상실은 각각 보존한다.
- idle 및 활동 중 heartbeat 실패는 기존 DEGRADED→실제 자식/작업자 회수→실행권 확인→실제 heartbeat 성공을 거친다. 유효하지 않은 owner/epoch는 갱신하지 않고, 만료는 기존 acquire 경로로 새 epoch를 얻는다. 정리가 끝나지 않으면 실패 상태를 유지한다.
- executor의 bounded operation context를 persistence adapter가 SQLite writer의 선택적 deadline으로 전달한다. Domain lease CAS와 기존 SQLite 정책(4회/250ms/50ms)은 유지한다. 만료 후 추가 SQL/commit을 시작하지 않으며, 이미 시작된 commit을 강제 종료한다고 주장하지 않는다.
- operation ID, queue, checkout, BEGIN 잠금 대기, transaction, cleanup, 호출자 취소 및 실제 늦은 종료를 기존 로그에 연결한다. 추가 진단 DB 쓰기·원문/키 로그·새 외부 호출은 없다.

## 오프라인 검증

외부 네트워크를 차단한 상태에서 Python 3.13.12로 실행했다.

1. `tests/test_scheduler_heartbeat_deadline.py`, `tests/test_creator_scheduler_recovery.py`, `tests/routines/test_scheduler_singleton.py`, `tests/test_l3_er2_sqlite_concurrency.py`: **48 passed**, 경고 2개, 118.76초.
2. deadline 테스트와 `tests/runtime/test_sqlite_recovery_contracts.py`: **20 passed**, 13.36초. 첫 검증과 중복 사례가 있으므로 두 결과를 단순 합산하지 않는다.
3. 마지막 잠금 계측 정밀화 후 SQLite recovery 및 pre-commit deadline 테스트: **12 passed**, 4.83초.
4. `git diff --check` 통과.

실제 임시 SQLite 잠금/rollback/commit, 실제 worker Future 생존, queue deadline, 첫 호출/재시도 deadline 동일성, unrelated TimeoutError·취소 보존, idle/active 복구 및 중복 tick 차단을 확인했다. 커밋 후 정리 실패가 성공한 쓰기를 반복하지 않는 기존 회귀도 통과했다. 짧은 TTL fixture는 그에 맞는 drain 1초를 명시하고, fake lease는 실제 계약처럼 owner·유효 만료 시각을 반환하도록 수정했다.

## 실행 검증 경계

로컬 ARM64 후보를 다시 생성하고 기존 데이터로 AVD에서 검증한다. 화면이 켜진 상태에서 준비/진행을 먼저 확인한 뒤 Doze 제어 25분, 보호 설정을 적용한 화면 꺼짐 180분을 별도 판정한다. 자율활동은 OFF이므로 완료된 no_action tick과 heartbeat가 관측 대상이다. 프로세스 생존, scheduler 진행, 실제 자율활동/AI 품질, 실제 ARM64 휴대폰 결과를 구분한다. 이 문서 작성 시점에는 새 이미지의 장시간 시험은 미실행이다.

실행 증거는 `D:/project_code/angmoo-workspace/.task-output/termux-scheduler-power-20261021/run-01`에 남긴다. 기존 데이터와 비밀값을 포함한 백업은 공개 배포하지 않는다.
