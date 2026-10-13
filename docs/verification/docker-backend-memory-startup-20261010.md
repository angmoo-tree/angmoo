# Docker 백엔드 시작 지연과 기억 검증 실행 경계 수정 검증

작성일: 2026-10-10 · 범위: 현재 로컬 브랜치 `feat/0.1.0-release-readiness`

기준 HEAD: `9998b6eb2c4155b0ab55ceaae96410532394c46c`

## 문제와 원인

개발 Compose 실행에서 백엔드가 `Waiting for application startup`에 오래 머물러
Docker 헬스체크에 실패했다. 프론트엔드는 `service_healthy` 의존성을 기다리므로
`created` 상태에 남았다. 이전 실행에서 앱 시작 대기는
2026-10-10 12:32:05.247 UTC부터 12:34:44.620 UTC까지 약 **159.37초**였다.

이번 문제의 직접 원인은 기억의 출처·권한 검증을 서버 이벤트 루프와 커밋 경로에서
동기적으로 반복 실행하는 구조였다.

- FTS 시작 코드가 백그라운드 스레드를 시작하기 전에 최대 900개 기억을 검증했다.
- FTS `after_commit`이 색인 작업의 잠금을 기다린 뒤 별도 Session으로 역사적 출처를
  검증했다. HTTP 요청이나 스케줄러의 커밋까지 색인 처리에 묶였다.
- 공유된 이전 기억을 여러 경로에서 다시 방문하고, 같은 범위·참여자·차단·출처를
  한 번의 읽기 안에서 반복 조회했다.
- 상황기억 저장·요약과 벡터 색인의 출처 읽기도 비동기 함수 안에서 동기 SQL을 실행했다.

이벤트 루프가 멈추면 정상적인 헬스 응답과 스케줄러 heartbeat도 지연된다.
이전 실행의 lease 상실과 fence 거절은 그 결과였다. 만료된 실행 권한을 거절하는
검증 자체를 제거할 문제가 아니었다.

## 구현한 실행 경계

| 소유자 | 변경 | 유지한 계약 |
| --- | --- | --- |
| Memory domain | `MemoryAccessValidation`으로 한 번의 동기 읽기 안에서 완료된 공통 계보와 동일한 canonical 사실을 재사용 | Session·시각이 다른 문맥은 거절. 쓰기, 다음 요청, provider 대기 이후에는 새로운 검증 문맥 사용 |
| FTS runtime | 시작 시 전체 자료를 동기 검사하지 않고, 한 소유 스레드가 32개씩 처리. 커밋 리스너는 식별자만 전달 | canonical SQL을 다시 읽은 결과로만 색인. 기존 build → validate → orphan 정리 → 원자적 승격 유지 |
| FTS queue | 100개까지 식별자를 모으고, 초과하면 전체 재검사를 예약 | 롤백한 변경은 전달하지 않음. 메모리 큐가 중단돼도 다음 시작에서 SQL과 재동기화 |
| Situation runtime | 전용 단일 작업자에서 Session을 열고 닫으며, 16개 접수 기록씩 저장 | cutoff, 접수·출처 검증, lease/fence, 바깥 트랜잭션의 원자성 유지 |
| Brief runtime | 한 트랜잭션에 한 캐릭터 범위를 처리하고 커서로 순회 | 잘못된 범위를 지나가도 다른 캐릭터의 처리를 막지 않음 |
| Vector runtime | provider 호출 전의 무거운 출처 읽기를 소유 작업자로 이동 | provider 응답 이후의 현재 권한·버전·쓰기 fence는 기존 Session에서 새로 확인 |
| 종료 처리 | 취소된 실행 중 SQL도 추적하고, Session·색인·엔진 종료 전에 실제 작업 완료를 기다림 | 저장 준비·마지막 fence를 같은 작업자에 순서대로 전달. FTS 완료 판정에는 미처리 커밋도 포함 |

모든 source scope, 현재 참여자와 차단, 비공개 채팅 thread, 실제 전달 증명,
원문 digest, 이전 기억의 버전·삭제 상태, 순환 계보 검사를 유지했다.
캐시는 reader, Session, runtime, index에 남기지 않는다. 후보를 실제 기억으로
읽어 주는 canonical hydration과 provider 응답 뒤의 적용 검증도 유지했다.

Docker 헬스체크의 timeout·retries·start period, 스케줄러의 45초 lease와 10초
heartbeat, DB 스키마 **v36**은 변경하지 않았다. 프론트엔드 기능·문구 변경도 없다.

## 트레이드오프

서버 응답 경로에서 비싼 파생 색인 처리를 제거했으므로, 저장된 기억이 검색 후보에
반영될 때까지 짧은 지연이 생길 수 있다. 자료가 많아 전체 재검사를 할 때는
백그라운드 준비가 더 오래 진행될 수 있다. 전체 재검사 중에는 기존 계약대로 FTS가
`MemoryRecallPreparing`을 반환한다. 검색 준비 완료 판정을 앞당기지 않았다.
준비된 색인에서 얻은 후보도 현재 canonical 권한·출처 검사에 통과해야만 반환된다.

FTS 큐는 영속 저장소를 추가하지 않고, canonical SQL 및 기존 재시작 재검사로
복구한다. 큐 상한을 넘으면 증분 반영 대신 전체 재검사를 선택한다. 일부 중복
작업을 감수하면서 메모리 증가와 커밋 지연을 제한하는 선택이다.

종료 시 실행 중인 SQL을 버리고 엔진을 먼저 닫지 않는다. 따라서 실제 페이지가
끝날 때까지 기다릴 수 있지만, 소유권이 없는 작업과 Session을 남기는 위험을
줄인다. 강제 프로세스 종료 후에는 기존 영속 접수·lease·색인 재검사 경로로 복구한다.

## 검증 환경과 데이터 보존

일반 로컬 pytest와 개발 Docker 이미지 빌드를 수행했다. PR, 원격 또는 로컬 CI
워크플로, main 반영, 설치된 Windows 앱 검사·변경은 수행하지 않았다.
외부 AI를 호출하는 추가 검증도 수행하지 않았다.

원래 named volume `angmoo_angmoo_contributor_embedded_data`는 보존했다.
정지 상태의 현재 canonical generation을 작업공간의 진단 artifact에 백업했다.
실제 데이터 부하 검사는 원본 볼륨을 읽기 전용으로 연결하고, 별도 익명 볼륨에
복사한 격리 컨테이너에서 실행했다. 네트워크는 `none`이고 사본에서만 자율활동을
끄고 5개 기억 요약 범위를 다시 준비하도록 했다. 원본 설정은 변경하지 않았다.

재시작 전후 비교 결과:

- DB 선택 마커와 암호화 키 파일의 digest가 동일했다.
- 5개 credential 관련 테이블의 레코드 수와 전체 레코드 digest가 동일했다.
- 캐릭터 자율활동 설정의 digest가 동일했다.
- 비교 시점의 기억 수는 양쪽 모두 **1,550개**였다.
- 원본 SQLite `quick_check=ok`, `foreign_key_check` 위반 **0개**였다.

진단용 원본·사본, 암호문, 키 원문, 대화 본문은 Git에 추가하지 않았다.
이 문서에는 집계된 결과만 기록한다.

## 회귀 검사

변경을 검증한 집중 검사에는 다음 경계가 포함된다.

- 공유된 이전 기억 DAG의 중복 방문 억제와 각 원문 검증 유지.
- 같은 Session·reader에서도 다음 검사는 변경된 원문, 숨김, 참여자 이탈,
  이전 기억의 버전·삭제 및 순환 계보를 다시 거절.
- FTS 작업이 멈춰 있는 동안 서버 시작과 다른 canonical 커밋이 완료됨.
- 커밋·롤백·큐 초과·중단·재시작·오프라인 변경 및 1,001개 기억의 단계적 색인 복구.
- SQL 실행 중 비동기 타이머 진행, 대기자 취소 후 작업 소유권 유지,
  다음 작업 직렬화와 실제 종료 drain.
- 상황기억 수동·예약·종료 저장, 부모 출처 복구, 현재 권한 재검사,
  모의 embedding 및 벡터 적용 fence.
- backend architecture, runtime 소유권 및 기존 전환 계약.

집중 pytest 결과: **74 passed**, 최종 작업자·보안·벡터·종료 관련 검사
**56 passed**, architecture·소유권·전환 검사 **52 passed**.
같은 테스트가 일부 겹치므로 이를 합산한 고유 테스트 수로 표현하지 않는다.

Docker에서도 이번 실행 경계에 직접 관련된 14개 테스트 파일을 명시적으로 실행했고,
**132 passed, 2 warnings, 489.07초**, 실패·제외 항목 없이 완료했다.
모든 검사는 `--network none` 및 `ANGMOO_DENY_EXTERNAL_NETWORK=1`에서 수행했다.

Docker 집중 검사 파일은 다음과 같다.

```text
tests/memory/test_canonical_worker_lifecycle.py
tests/memory/test_recall_projection_responsiveness.py
tests/memory/test_lineage_validation_cost.py
tests/memory/test_activity_situation_schedule.py
tests/memory/test_activity_situation_recall.py
tests/memory/test_multilingual_projection_lifecycle.py
tests/memory/test_p8_l_h_canonical_recall.py
tests/memory/test_world_embedding_preparation.py
tests/memory/test_situation_parent_binding_recovery.py
tests/memory/test_vector_projection_lifecycle.py
tests/memory/test_activity_situation_transition.py
tests/routines/test_scheduler_singleton.py
tests/test_creator_scheduler_recovery.py
tests/test_refactor_architecture_boundaries.py
```

### 광범위 검사에서 발견한 기존 실패

처음 넓은 Docker 검사는 **288 passed, 7 skipped, 2 failed**까지 확인한 뒤 중단했다.
완료된 전체 검사로 취급하지 않는다. 실패한 두 항목을 정지 전 컨테이너의 수정 전
`app` 소스로 다시 실행했고, **두 항목 모두 동일하게 실패**했다.

1. `test_daypart_runtime_bindings.py::test_cold_resident_imports_use_actual_owners_and_explicit_registration`:
   현재 등록 테이블에 예전의 고정 개수 **169**를 기대한다.
2. `test_hybrid_episode_inventory.py::test_current_inventory_preserves_predecessor_and_runtime_contract`:
   실제 스키마 **36**에 예전 값 **32**를 기대한다.

이 두 항목을 제외하고 넓은 검사를 다시 실행한 결과는
**316 passed, 7 skipped, 2 deselected, 3 failed**였고, `--maxfail=3`으로 중단됐다.
추가 실패는 `test_p8_l_f_memory_migration.py`의 세 항목이다.
모두 v4 시험 자료를 만드는 `build_sqlite_v4_metadata()`에서 고정 테이블 수
**87**과 실제 **88**의 차이로 실패했다. 동일한 파일을 수정 전 `app` 소스로
다시 실행해 **세 항목의 동일 실패**를 확인했다.

이번 수정에서는 ORM 테이블과 스키마를 추가하지 않았다. 발견된 5개 기존 실패는
별도 정리 대상으로 남겼다. 넓은 검사 전체가 통과했다고 표현하지 않고,
현재 변경에 직접 관련된 파일들을 명시한 Docker 집중 검사와 구분한다.

## 실제 Docker 확인

격리 사본은 기억 **1,550개**, 상황 접수 **215개**, 벡터 대상 **1,500개**를 가진
원본의 현재 generation에서 시작했다.

| 확인 | 결과 |
| --- | --- |
| 이전 원본 앱 시작 대기 | 약 159.37초 |
| 수정한 격리 사본 앱 시작 대기 | 약 6.48초 |
| 수정한 실제 원본 앱 시작 대기 | 약 9.81초 |
| 사본의 초기 `/health` 20회 | 전부 200, 최대 약 0.071초 |
| 원본 재시작 뒤 부하 중 `/health` 20회 | 전부 200, 최대 약 0.379초, 같은 scheduler epoch 유지 |
| frontend `http://127.0.0.1:3000/` | 200 |
| 원래 Compose 재시작 | `up -d --no-build` 완료, backend와 frontend 모두 healthy |

측정한 앱 시작 대기는 Uvicorn의 `Waiting for application startup`부터
`Application startup complete`까지이다. 이미지 빌드·컨테이너 생성·Python import
시간을 포함하는 전체 Compose 명령 시간과 구분한다.

동일한 정지 DB 사본과 고정 시각으로 첫 8개 기억을 수정 전·후 소스로 읽은 결과:
출력 8개 및 출력 전체 digest가 동일했고, SQL 실행은 **3,412 → 1,139회**로 감소했다.
이 비교는 검증 결과의 동일성과 반복 SQL 감소 증거다. Windows bind mount와
동시 부하가 있었으므로 그 읽기의 벽시계 시간을 성능 개선율로 사용하지 않는다.

격리 사본은 13:08:39 UTC에 앱 시작을 완료했고, 13:29:08 UTC 확인에서
FTS의 build·validate·orphan 처리와 승격을 끝냈다. 새로 검증된 FTS 문서는
**1,550개**, 색인 `quick_check=ok`, 미처리 요약 범위는 **0개**였다.
그 동안 scheduler epoch **959**가 유지됐고, 마지막 `/health`도 `ok`였다.
이번 사본은 같은 기기의 원본 FTS 작업 및 pytest와 부하가 겹쳤다.
약 20분의 백그라운드 준비 관찰을 일반적인 완료 시간이나 시작 대기로 해석하지 않는다.

실행 중인 원래 백엔드의 변경 소스 **17개**가 로컬 작업 파일과 SHA-256으로
모두 일치했다. 격리 사본은 검증을 마친 뒤 정상 정지했다.
`--rm`으로 생성한 시험 컨테이너와 시험용 익명 볼륨만 수명을 종료했고,
원래 Compose 컨테이너와 named volume은 유지했다.

**최종 원본 확인: 2026-10-10 13:37:24 UTC / 22:37:24 Asia/Seoul.**
원본 FTS도 준비를 끝냈고, 문서 **1,550개**, `quick_check=ok`였다.
원본 `/health=ok`, scheduler epoch **959** 및 유효한 heartbeat/lease가 유지됐으며,
백엔드와 프론트엔드가 모두 **running / healthy**였다.

## 변경 취소 범위

이번 변경은 DB migration을 추가하지 않았다. 코드 변경을 되돌리는 경우에도 원본
named volume, 암호화 키, 현재 generation은 그대로 보존한다. 구버전의 동기 검증
실행 경계로 돌아가면 이번 시작 지연이 재발할 수 있다. 실제 원본 데이터를
삭제하거나 초기화하는 방식으로 해결하지 않는다.
