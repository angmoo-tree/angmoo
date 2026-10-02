# Embedded SNS 체크포인트와 canonical DB 세대 보존

이 정책은 backend의 embedded runtime에 적용한다. 설정 화면이나 별도 정리 서버는 추가하지 않는다. 실제 실행 경계는 contributor/Docker backend와 Windows sidecar가 공유하는 coordinator·composition·lifespan이다.

## SNS 상세 기록

신규 V2 활동을 처음 생성할 때 `sns-completed-checkpoint-24h-v1` 표시를 canonical `ActivityGraphRun.result.checkpoint_retention`에 저장한다. 기존 활동에는 소급 표시하지 않는다. 정책 없는 기존 완료·실패·중단 기록은 이전 30일 정리 경로에서도 삭제하지 않는다.

정상 `completed`·`observed` 결과가 canonical DB에 확정되고 최종 graph 저장까지 확인된 활동의 상세만, `finished_at + 24시간 <= 현재 UTC`에서 정리한다. 실패·대기·실행 중·중단·미확정 결과, 실제 유효 lease, pending 효과/활동 claim, 이미지 수신·저장·첨부 복구 의존은 보호한다. 재개 lease의 ID가 원 활동 ID와 달라도 실제 캐릭터와 canonical lease 연결을 확인한다.

완료 결과는 graph·Provider·새 LLM 요청보다 먼저 읽는다. 읽기 권한·World·owner·engine/contract·lane/receipt 정합성은 계속 검사한다. autonomy OFF나 실행 lease 종료만으로 이미 완료된 결과의 읽기를 막지 않는다. 완료처럼 보이는 손상된 결과는 안정적인 오류로 끝내며 빈 graph나 새 ID로 재실행하지 않는다. 내부 정리 namespace는 업무 응답에서 제외한다.

maintenance는 startup에 한 cycle을 실행하고 이후 1시간마다 실행한다. SNS가 OFF이거나 새 활동이 없어도 동작한다. 기본 batch 50, 한 cycle 최대 후보 500 또는 새 작업 시작 예산 5초다. 보호 후보를 지나도록 `(finished_at, activity_id)` cursor를 전진시키며 다음 순회에서 다시 검사한다.

후보 하나마다 독립 Session의 짧은 조건부 claim을 commit한 뒤 canonical transaction을 종료한다. 공개 saver API `adelete_thread`로 해당 thread의 모든 namespace와 writes를 삭제하고 별도 조건부 완료 표시를 저장한다. mark 실패·중단은 다음 cycle의 같은 정리 대상으로 남는다. canonical 결과·사용량·효과·image intent를 다시 만들지 않는다. SQLite busy는 제한된 대기 후 연기하고 다른 캐릭터 scheduler를 정리 때문에 중지하지 않는다. backup helper와 maintenance는 같은 root의 OS maintenance lock으로 겹치지 않는다.

24시간은 즉시 삭제 타이머가 아니다. 주기 cycle까지 기다릴 수 있고 보호 조건이나 잠금 경합이 있으면 더 오래 남는다. 실제 데이터 정리는 backend가 실행 중이어야 한다.

## DB 자동 사본

실제 새 clean DB 또는 새 migration staging을 만들 때만 `generation-retention.json`을 기록한다. `canonical-generation-current-previous-v1`, creation ID, 정확한 relative path, schema, immutable migration manifest digest, 검증·승격 확인 상태를 기록한다. manifest digest는 변하는 사용자 DB 파일의 bytes hash가 아니다. 기존 generation·staging·수동 backup에는 표시를 추가하지 않는다.

기존 SQLite backup → forward migration → identity/manifest/FK/integrity 검사 → finalize → promote → 승격 후 검사를 유지한다. graph 처리가 끝나고 임시 engine이 닫히며 secret/media 불변 검사까지 통과한 뒤 신규 승격을 확정한다. 그 다음에만 정리를 실행한다.

기본 보호 집합은 current + previous다. 실제 사용 중인 generation pin, staging, 미확정 승격, 손상/불명확한 marker·pin, 알려지지 않은 파일을 포함한 세대도 추가 보호한다. 따라서 전체 디렉터리가 항상 두 개가 되는 정책은 아니다. 기존 자료와 보호 예외를 제외한 신규 자동 사본의 누적을 제한한다.

정리는 serving startup 소유권을 가진 contributor 또는 sidecar에서만 허용한다. 진단·installer/direct coordinator는 삭제 권한이 기본 OFF다. 실제 OS serving lock과 generation use pin은 raw PID나 lock 파일 존재와 구별한다. 소비자는 engine을 열기 전에 공유 migration lock 안에서 pin을 등록하고, worker·engine 종료 뒤 해제한다. 종료 성공을 확인할 수 없으면 pin을 보호하며 process 종료 후 OS lifetime lock 해제가 확인되어야 stale pin을 정리한다.

installer의 WAL checkpoint와 후속 preflight도 선택한 generation의 사용 pin을 작업 종료까지 유지한다. 그 사이 다른 serving startup이 새 세대를 승격하더라도 작업 중인 DB는 삭제 대상에서 제외한다. installer가 삭제 권한을 갖는 것은 아니며, 정상 완료·예외 모두 pin을 해제한 뒤 다음 serving startup이 다시 보호 집합을 판단한다.

DB 정리는 1시간마다 실행하지 않는다. 새 backend가 실제 시작하는 안전한 경계에서 실행한다. 같은 schema의 재시작은 새 DB 복제나 migration 없이 보존 정리만 시도한다. Docker는 backend 재생성·재시작, 개발자는 `up`으로 실제 backend를 다시 시작하는 때, Windows는 새 sidecar 시작이 해당 경계다. 이미 실행 중인 컨테이너에 로컬 소스 변경이 적용된다는 뜻은 아니다.

삭제는 canonical/generations 바로 아래의 확인된 한 세대 전체에 한정한다. root/current/previous, symlink·junction·reparse, 경로 탈출, 열린 pin, 미확인 파일은 거절한다. WAL/SHM을 열린 DB에서 따로 지우지 않는다. 세대 밖 runtime에 먼저 원자적인 removal intent를 기록하여 부분 제거를 재시도한다. 삭제 실패가 working current의 시작 실패·재복제·재승격으로 바뀌지 않는다. graph/search/media/수동 backup은 이 정책으로 제거하지 않는다.

## 비활성화와 적용 범위

`SNS_CHECKPOINT_POLICY_ENABLED=false`는 앞으로 생성되는 활동의 정책 표시를 중지한다. 이미 표시한 정책과 canonical reader를 지우지 않는다.

`SNS_CHECKPOINT_MAINTENANCE_ENABLED=false`는 상세 삭제 task를 중지한다. 완료 결과 reader와 기존 metadata는 유지한다.

`CANONICAL_GENERATION_RETENTION_ENABLED=false`는 startup의 generation 삭제를 중지한다. 소유권/사용 pin 및 신규 생성 기록은 계속 유지한다. 데이터 삭제를 되돌리는 코드 downgrade나 marker 강제 변경보다 이 설정으로 정리를 먼저 중지한다. 삭제된 상세/obsolete 사본은 자동 복원하지 않는다. 보존한 canonical 업무 결과와 current/previous, 별도로 확보한 backup을 복구 근거로 사용한다.

환경 설정 변경은 해당 backend를 실제 새 설정으로 시작할 때 반영한다. 이번 구현 검증은 임시 root만 사용하며 실제 Docker named volume이나 Windows 설치 데이터를 정리하는 작업을 포함하지 않는다.

Docker에서는 선택한 Compose 파일 또는 별도 override의 backend `environment`에 위 이름과 `"false"` 값을 명시적으로 전달한다. `.env`에 이름만 추가했지만 Compose가 container environment로 전달하지 않은 경우에는 설정 변경이 적용됐다고 보지 않는다. backend를 다시 시작한 뒤 실제 프로세스에 전달한 설정을 확인한다.

SQLite에서 상세 rows/BLOB를 삭제하면 빈 페이지가 재사용 가능해진다. 파일 bytes, WAL, Docker VHDX와 호스트 여유 공간이 같은 비율로 바로 줄어드는 것은 아니다. 이 정책은 VACUUM·VHDX 압축·Docker volume 제거·수동 legacy 삭제를 자동 실행하지 않는다.
