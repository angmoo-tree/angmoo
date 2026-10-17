# Checkpoint maintenance contention regression — 2026-10-18

## Incident and scope

Main `6735cd86c68c4c8f382d6978927df4ccfac58fdc` failed
[Core CI partition 1](https://github.com/angmoo-tree/angmoo/actions/runs/39075656176/job/117522420473)
in `test_three_characters_progress_with_normal_and_large_cleanup`.
The other three backend partitions passed. This partition reported 1 failure,
1,686 passes and 20 existing skips. Its synthetic activity's `BEGIN IMMEDIATE`
exhausted four bounded attempts with `SQLITE_BUSY`.

The log does not identify the competing lock owner or its exact hold time.
It does identify an unsupported test assumption: all concurrent synthetic
activities had to obtain admission on their first invocation. The canonical
writer deliberately permits a typed busy result after at most four attempts
within its 250 ms budget. Maintenance already defers unsuccessful work, while
the activity side of this test had no redelivery phase.

한국어 요약: 동시에 실행하는 시험이 첫 시도에서 모두 성공한다고 가정한 것이
문제였다. 잠금 제한을 늘리거나 실패를 무시하지 않고, 명시적인 경합 응답과
잠금 해제 후 동일 체크포인트 재개를 함께 검증한다. 실제 CI 당시 잠금 소유자와
유지 시간은 확인되지 않았으며, 이 변경을 제품 전체의 경합 해소로 해석하지 않는다.

## Correction and preserved guarantees

Only the test workload and this evidence document change. Product runtime,
SQLite retry limits, checkpoint cleanup, AI adapters, locks and production image payload inputs
remain unchanged.

- The synthetic provider call has its own durable graph node. The existing
  production graph resume contract is modeled with the same thread ID and
  `ainvoke(None, config)` when a saved checkpoint exists.
- The first concurrent round drains all activities and maintenance. Only an
  exact `SqliteBusyRetryExhausted` carrying SQLite's BUSY primary code receives
  one explicit redelivery after the initial owners finish. Other failures and
  failed redelivery still fail the test. No repeat-until-green loop is added.
- Failed write attempts remain in timing samples. Progress gaps span recovery;
  existing relative latency assertions are unchanged.
- Every activity must still complete steps 1–8 exactly once, retain a terminal
  checkpoint, invoke its fake provider once and persist one public effect.
  All 20 normal and one large expired checkpoint must eventually be pruned.
- A new deterministic test holds a real writer lock. All three activities
  must defer, write no effect before release, and finish after release without
  repeating the provider. All 21 cleanup targets must defer and then complete.

This retains meaningful progress, exact-effect and performance checks while
allowing the already documented bounded-admission outcome. Serializing all
test writers or raising product timeouts would conceal the contention contract
and was not used. This synthetic resume proof is separate from scheduler-driven
recovery and live AI quality; the existing actual graph resume regressions are
included in focused validation.

## Verification

- Original overlap test, unchanged product: 1 PASS locally. It is sensitive to
  scheduling and does not reproduce on every invocation.
- New held-writer scenario before adding explicit recovery: FAILED at the same
  `BEGIN IMMEDIATE` with `SqliteBusyRetryExhausted`. The local elapsed bound was
  reached after three attempts; the CI incident reached four. Both conform to
  the unchanged attempt/time budgets.
- Initial targeted checks after the correction: 3 PASS in 35.15 seconds
  (normal overlap, forced canonical busy and checkpoint SDK busy).
- Related local validation: **55 PASS in 266.86 seconds** across checkpoint
  maintenance, retention, the production autonomous graph resume tests and
  SQLite concurrency. The three initial checks are a subset, not added again.
- Architecture boundaries: PASS (1,569 modules, 6,804 edges, zero legacy edges).
- Local reports are under `artifacts/checkpoint-maintenance-20261018/`; the
  original CI log and controlled pre-fix failure are preserved in the workspace
  task output. Hosted PR and post-merge results are separate verification.

No user database, installed application, existing Docker container, official
tag, package or Release was modified. ARM64 user testing follows CI repair;
official publication remains P6.
