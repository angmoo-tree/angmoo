# 관계 스냅샷과 Docker 준비 상태 복구 — 2026-10-13

- 저장소: `D:/project_code/angmoo-workspace/angmoo-tree-angmoo`
- 브랜치: `feat/0.1.0-release-readiness`
- 시작 HEAD: `3afd9966503aaa8f13cb346b6172e407f7959d04`; 시작 작업 트리 clean.
- 범위: 현재 Docker 홈의 `일부 기능 제한` 원인 수정과 실제 작업자 복구 확인.
- 로컬 변경·로컬 커밋만 수행한다. push/PR/원격 CI/main 병합은 수행하지 않는다.

## 확인한 원인

Docker 백엔드 자체와 `/health`는 정상이고 스케줄러·관계망 작업자도 살아 있었다.
하지만 canonical `graph_projection_outbox`에 `internal_error`로 재시도 대기 중인
`relationship_snapshot` 6건이 있어 Runtime status가 degraded로 판정됐다.
홈은 이 상태를 `일부 기능 제한`으로 표시한다.

스냅샷 명령은 정상 계약상 `event=None`과 명시적 `world_id`를 사용한다.
World 삭제 보호 검사가 `RelationshipStateProjectionCommand`의 `event.world_id`를
항상 읽어, 6건 모두 그래프 접근 전에 `AttributeError`로 실패했다.
canonical 명령 생성·출처 검사에는 통과했으며 이벤트를 만들 필요가 없는 작업이다.
기존 native snapshot 시험도 수정 전 같은 오류로 실패했다.

## 구현과 보존한 경계

`integrations/ladybug_projection.py`에서 관계 명령의 이벤트가 있으면 그 이벤트의
World ID를, 이벤트가 없으면 명령의 명시적 World ID를 사용한다.
World ID가 없으면 기존 구조화된 `world_missing` 오류로 거절하며,
검증한 동일 ID로 World 삭제 표식 검사와 스냅샷 저장을 수행한다.

삭제된 World에 늦게 도착한 이벤트·스냅샷이 다시 기록되는 것을 막는
`world-erasure` fence는 유지한다. canonical 출처·권한·World 연결 검사,
관계 버전과 동일 버전 충돌 검사, worker lease/CAS/반영 완료 조건,
health·Runtime status·UI 표시 조건과 DB 스키마도 변경하지 않는다.
가짜 SocialEvent를 만들거나 실패 행을 성공 처리하거나 제외하지 않는다.

제품 변경은 기존 integrations 소유 모듈 한 곳이다. 새 import나 domain 간 의존성,
API/UI 번역 변경은 없다. `backend/ARCHITECTURE.md`의 canonical/derived-store와
단일 Ladybug writer 경계를 유지한다. 프론트엔드 구조·디자인 변경은 없다.

## 관련 검증

격리 disposable Docker에서 pytest를 수행한다. 사용자 canonical/graph 볼륨은
연결하지 않고 source/tests만 read-only로 연결하며 `--network none`, UID/GID
10001:10001, `ANGMOO_DENY_EXTERNAL_NETWORK=1`을 사용한다. 신규 AI/이미지 모델
실행이나 유료 제공사 시험 호출은 없다. 전체 backend/frontend 시험은 실행하지 않는다.

대상은 native Ladybug 이벤트/스냅샷·재실행·버전·다른 World 보존·writer 잠금,
World 삭제 fence와 재개, canonical 명령 검증, worker lease/재시도/transaction,
Runtime schema/status read transaction의 관련 7개 시험 파일이다.

추가 회귀는 World ID가 없는 스냅샷이 쓰기 없이 거절되는 것과,
이벤트 없는 스냅샷도 World 삭제·재개 후 fence에 막히면서 다른 World를 보존하는 것을 확인한다.

첫 수정 후 묶음은 41 passed / 1 `ladybug_transient` 실패였다. 실패한 기존
이벤트 기반 clear-world 시험만 같은 제한·같은 소스로 다시 실행하면 1 passed였다.
제품 timeout이나 시험 기대값을 완화하지 않고 같은 관련 묶음을 다시 실행하여
**42 passed / failures=0 / errors=0 / skipped=0**, 94.35초를 확인했다.
첫 실행의 `ladybug_transient` 원인을 확정하지 않으며, 스냅샷의 재현 가능한
`AttributeError`와 구분한다. 위 재실행들은 실패 확인 후 필요한 범위에서만 수행했다.

제품 모듈의 전후 AST import 비교도 일치하며 새 의존성 0건이다.
저장소 전체 구조 정책과 전체 시험을 이번 결과의 PASS로 주장하지 않는다.

## 실제 Docker 확인

Compose Watch가 source 변경을 동기화하고 StatReload가 앱을 재시작했다.
로컬/컨테이너 제품 파일 SHA256은
`7a16654f2aae0c2e56197e5f408972e3973716d658db0948f1504088b6579eb4`로 일치한다.
수동 restart/rebuild나 설치 앱 변경은 없다.

active generation manifest와 실제 server process의 열린 FD로 canonical DB를 확인했다.
`schema_version=37`, `source_revision=20261012_0114`다. DB 진단은 `mode=ro`와
`PRAGMA query_only=ON`으로만 수행한다. World/대화/기억 본문이나 인증 키를 출력하지 않는다.

기존 6건의 원본·출처·dedupe 연결을 묶은 SHA256을 전후 비교하고, 기존 작업자의
예정된 재시도가 실제로 반영·완료됐는지 확인한다. 재시도 시각과 행 상태를 직접 수정하지 않는다.
서비스의 기존 자연 활동은 유지하므로 전체 DB 바이트가 동일하다고 주장하지 않는다.

ignored evidence 경로: `artifacts/diagnostics/graph-snapshot-recovery-20261013/`.
`before.json`, 최종 runtime snapshot, pytest XML과 홈 화면 캡처를 저장한다.

## 최종 결과

2026-10-13 03:52:25 KST canonical/health 확인 뒤 실제 Edge 홈을 새로고침했다.
한국어 상태 배지와 접근성 설명이 모두 **준비됨**이며, 기존 World 5개의 실행 가능 표시도 확인했다.
화면 언어나 배지 문자열을 변경하지 않고 정상 서버 상태의 기존 표시 계약을 사용한다.

| 확인 | 수정 후 결과 |
| --- | --- |
| 관련 pytest 최종 묶음 | **42 passed**, 94.35초; failures/errors/skipped 각각 0 |
| 원래 실패 대기 6건 | **6건 모두 succeeded**, 각 attempt_count 5 → 6 |
| 완료 시각, KST | 03:40:07 / 03:40:58 / 03:43:11 / 03:43:29 / 03:46:28 / 03:52:01 |
| pending / failed / dead-letter | **0 / 0 / 0** |
| succeeded 총계 | 5833 → **5839** |
| 기존 6건의 원본·출처·dedupe SHA256 | 전후 **6건 모두 일치** |
| `last_error_class` / lease / next_attempt_at | 실제 worker 완료로 모두 해제 |
| `/health` | HTTP 200, `status=ok`, scheduler/projector 모두 ready |
| Docker backend/frontend | 둘 다 running / healthy; 기존 컨테이너와 data volume 유지 |
| Edge `http://127.0.0.1:3000/` | 실제 홈 상태 배지 **준비됨**, 화면 캡처 저장 |
| dependency/AST 범위 | 새 import 0, dependency/policy 변경 0, `git diff --check` 통과 |

기존에 살아 있는 worker가 수정된 어댑터를 사용하여 각 예약 시각에 claim·검증·반영·
완료 CAS를 수행했다. 수동 DB 쓰기, 실패 삭제, 상태 강제 변경, 예약 앞당기기,
가짜 이벤트, World 전체 재구성은 수행하지 않았다. 문제를 일으킨 제품 코드는 수정했고,
수정된 소스에서 정상 자동 재시도가 복구를 완료했다.

스크린샷: `artifacts/diagnostics/graph-snapshot-recovery-20261013/home-ready.jpg`.
최종 읽기 증거는 같은 경로의 `after.json`, 시험은 `scoped-regression.xml`이다.
이번 확인은 현재 Docker runtime이며 Windows 설치본 상태나 실제 AI 응답 품질의 PASS를
의미하지 않는다. 정상 자율활동과 사용자의 기존 설정은 유지했다.

이 기록과 제품 수정·회귀를 같은 로컬 커밋에 저장한다. 정확한 최종 SHA는 Git과
최종 응답에서 확인한다.
