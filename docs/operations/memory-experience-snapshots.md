# Historical memory snapshots — isolated PostgreSQL experiment

> **0.1.4 scope:** This document retains the named implementation phase and its original schema, SQLite/FTS5/Vec1 measurements and validation outcomes. Current serving uses PostgreSQL schema 5, PostgreSQL keyword search and pgvector exact search; LadybugDB remains derived. Follow the [current runtime contract](../public/postgresql-runtime.md) and [migration guide](../public/postgresql-migration.md). Historical PASS or NOT VERIFIED results are not relabelled as current PostgreSQL evidence.

Implementation policy, 2026-10-28. Device acceptance is recorded in the individual
run report; this document does not claim that device/load tests passed.

New SNS/Chat input journals retain exactly the final delivered text, speaker,
time and fragment ranges. Memory storage and SNS/Chat recall use these copies. Relationship review
uses only the owner character's situation-memory bodies grouped by counterpart
and the existing directional relationship label/perception. Editing/deleting a source post does not change the saved experience.
Current memory ownership, consent, version and explicit deletion, World/character/
thread boundaries, actual action permissions, leases and relationship view versions
remain enforced. Flat tombstone dependencies revoke deleted memories and derived
copies. Unknown provider delivery remains unknown. A known pre-publication
rejection records read-but-not-executed, never successful action.

PostgreSQL schema 3 has 185 canonical tables. SQLite 41 stays the immutable
181-table input; `convert/resume/verify` reports the four extra snapshot tables
separately. Old manifest/receipt hashes are preserved. Legacy originals are copied
only if original digests and ranges prove them; otherwise summaries remain with
`snapshot_unavailable`. Audit output includes counts, snapshot JSON bytes, flat
links, summary-state hashes, scope/orphan checks and pending-work classification.
Legacy episode inputs lacking durable original text fail before a provider call
with `episode_manifest_snapshot_unavailable`. Legacy SNS memory checkpoints cannot
resume the removed live-source policy. Existing response journals, committed
effect receipts remain authoritative. Frozen relationship inputs/results remain
audit records; obsolete review inputs are not submitted or applied as the new
`relationship-situation-summary.v1` policy. Unsubmitted reviews can be replanned
with the same receipts after current memory rights checks. Previously submitted,
received or delivery-unknown work is retired with an explicit policy-change reason,
preserving its inputs/results/journal and avoiding an automatic paid replay.

Stop the experiment app, verify a full backup restore, and select a separate DB
clone before upgrading. Inside the new candidate backend image:

```sh
python -m app.runtime.postgresql_experience_upgrade \
  --dsn-file /experiment/secrets/restore-dsn \
  --expected-database angmoo_pg_run01_restore
```

The tool refuses preserved database names and active runtime connections. Schema,
backfill and version marker commit atomically. Reapply `pg_runtime_role.py` for
the existing runtime role's privileges on new tables. A failed upgrade rolls back;
a downgrade needs the verified pre-upgrade backup and matching old image.

Startup refreshes derived vector authorization metadata and reuses unchanged
vector payloads. Exact search, model and dimensions remain unchanged. Two C31
canonical reader child processes are replaced by bounded backend threads. The
connection budget is primary 10+5, checkpoint 2, direct maximum 2: app maximum 19,
role 20, server 28, including three reserved administrator slots. These are
ceilings, not preallocated sessions. Android global settings are unchanged.

The Memory detail UI uses the existing shared Next/static component (LOCAL
reference). It distinguishes historical copies, unavailable originals and failed
actions. Snapshot storage and prompt overhead must be measured on the phone.
Official release, Windows installer and Docker product migration remain separate.

---

# 기억 원문 스냅샷 — PostgreSQL 격리 실험

새 SNS/Chat은 최종 AI 입력의 실제 텍스트·작성자·시각·범위를 보존한다. 기억 정리·검색·
원문 전달은 저장된 복사본을 사용하며 원래 글의 수정·삭제 때문에 기억을 폐기하지 않는다.
관계 검토만 별도로 상대별 상황기억 본문과 기존 방향성 관계 label/perception을 사용한다.
관계 검토에서 원문·원문 스냅샷은 조회·재검증·전달하지 않는다. 기억 ID·시각은 연결·순서용이다.
수치 점수·persona·자격 증명과 권한 검증 자료도 관계 AI 입력에 넣지 않는다.
수집 동의, 기억 자체의 권한·버전·명시적 삭제, World/캐릭터/대화 범위, 실제 게시 대상과
실행권·관계 버전 검사는 유지한다. 평탄한 삭제 의존성은 삭제된 기억의 파생 재사용도 막는다.
전송 불확실은 불확실로, 게시 전 거절은 “읽었지만 반응을 실행하지 못함”으로 보존한다.

새 PG 대상은 schema 3 / canonical 185개다. SQLite 41 원본 181개 테이블과 해시는 유지한다.
이전 도구는 추가 4개 테이블과 검증 결과를 별도 보고한다. 과거 원문은 저장된 digest·범위로
입증되는 경우만 복원하며, 나머지는 요약을 유지하고 `snapshot_unavailable`로 표시한다.
옛 manifest·receipt 해시는 고쳐 쓰지 않는다. 미완료 episode 입력에 원문이 없으면 AI를
다시 부르기 전에 재처리 필요 오류를 낸다. 옛 SNS checkpoint도 과거 원문 검증 경로로
우회하지 않는다. 이미 받은 결과와 공개 효과의 receipt, 관계의 고정 입력·결과는 보존한다.
관계 입력 정책은 `relationship-situation-summary.v1`이다. 옛 미호출 작업은 현재 기억 권한을
검사해 새 작업과 기존 receipt를 연결한다. 이미 호출했거나 응답·전송 불확실 이력이 있으면
자동 재호출·새 정책으로의 결과 적용을 막고 정책 변경 사유로 종료하며 원래 기록을 보존한다.

서비스 정상 종료·전체 백업·복원 검증 후 별도 복제 DB에서 위 명령을 실행한다.
도구는 보존 DB 이름과 runtime 연결이 남은 DB를 거절한다. 새 테이블 runtime 권한을
반영한 뒤 기동한다. 전환 실패 시 같은 트랜잭션으로 롤백하며, 구버전 복귀에는 검증한
이전 백업과 해당 이미지가 필요하다. 이전 검증은 건수·바이트·연결·요약 상태 해시·권한·
고아 연결·미완료 작업 분류를 포함한다.

전용 canonical reader 자식 프로세스 둘을 제거하고 backend 내부의 제한된 thread를 쓴다.
주 풀 10+5 / checkpoint 2 / 별도 최대 2, 앱 최대 19 / 계정 20 / 서버 28 / 관리자 예약 3이다.
항상 그 수의 세션을 생성한다는 뜻은 아니다. Android 전역 설정은 바꾸지 않는다.
기존 벡터·모델·차원·정확 검색을 유지하며 내용 해시가 같은 벡터를 재사용한다.
화면은 당시 원문·원문 없음·실패한 반응을 구분한다. 실제 원문 저장 비용·AI 입력 비용·
메모리/CPU·전체 부하 통과 여부는 실행 보고서에서 확인한다. 정식 배포와 Windows/Docker는 후속이다.
