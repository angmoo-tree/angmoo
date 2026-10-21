# SQLite, bounded reads and Termux integration verification

## Scope and source

Implementation started from `5884441cc8687a8f57f3614e8bfbf5295ef9bb56` on
`feat/termux-release-common`. The earlier nine common Termux/scheduler commits,
test discovery change and integration inventory are preserved. Emulator-only
commits `9da6b012`, `80db718c`, `639eaf80` are excluded.

This change implements the approved U000–U114 contracts. PR/CI/main, five
same-source candidates and the PC Android handoff are later evidence stages;
this report does not claim they already passed. No physical-device install,
provider request, live-data migration, power experiment or public release was
performed for these local checks.

## Implemented contracts

- Names: remove semantic slang/reserved-name restrictions and name-derived
  operator presentation. Preserve blank/length/format/duplicate/cooldown,
  owner ID, World authorization and actual deleted-author state. No rename of
  existing records and no privileged behavior from choosing a name.
- SQLite: lease operations share one deadline from submission through queue and
  BUSY retry. Keep worker 1/capacity 4/queue age 1 second, ordinary writer policy,
  owner/epoch/expiry checks and actual-work drain. Retry only BUSY after rollback.
  Finish retries only the frozen logical tick and result; no activity replay.
  Buffer bounded transaction observations and emit after transaction cleanup.
- Initial reads: daily-preparation owns the plan ID/date/version admission;
  distinguish absent, lost, forbidden and missing targets. Selected/unselected
  owner reads do not create identities. Initial ensure remains an explicit write.
- Chat: latest/before/after keyset pages, default 50/max 100, scope-bound bounded
  cursors, select-in attachments and page-local evidence. Confirmed committed
  messages/evidence are upserted without a full conversation reload. Contiguous
  catch-up state is independent of newly committed messages and is limited to
  two pages per event, with explicit continuation. Preserve response-time reading
  anchors, draft, model, stream/inspector and late-response scope fences.
- World Feed: default 30 roots/max 100, keyset pagination, batched summaries,
  summary-only refresh after a write/image completion. Keep failed append/refresh
  separate from successful writes, preserve draft/anchor and revision-aware likes.
  Pause offscreen image-status reads; server image jobs continue.
- Authenticated media: start downloads near the real scroll viewport, reserve
  space, cancel stale auth/runtime/source work and revoke object URLs. Existing
  avatar/composer consumers keep their eager wrapper.
- Termux: basic logs by default; `start/restart --log-mode detailed
  --log-duration 15m`, bounded 1–60 minutes, expiry back to basic. Immutable
  launch-bound policy, service ACK/unconfirmed distinction, one-way UTC/local
  monotonic expiry. Status labels its UTC estimate; it cannot observe a remote
  service's monotonic clock. Missing policy keeps other launch modes compatible.
  Basic retains lifecycle/warnings/errors; detailed source records omit content,
  query strings, keys and tokens. Owned selector self-pipe and writer condition
  replace idle periodic wakeups, retaining bounded queues/rotation/close semantics.
- Fixed terminal messages are English. Web text and public documents remain KO/EN.
  Reproducible tools/bootstrap/setup allowlists include the new policy module.

## Data and time compatibility

SQLite schema 41 / Alembic `20261022_0118` adds only two read indexes:
`message_messages(thread_id, created_at, id)` and the World root-feed keyset
index. Historical manifests stay frozen. Upgrade rollback, populated-row
preservation, foreign keys and actual EXPLAIN index use are checked. No new
diagnostic database writes or persistent read connections are introduced.

Normal contracts remain: search worker process/round 30/60 seconds; Chat search
20 seconds; SNS search 30 seconds; Chat request/lease 180 seconds; Termux
backend/frontend/start readiness 180/180/370 seconds. Worker counts are unchanged.

## Local verification

Local evidence directory (not a repository artifact):
`D:/project_code/angmoo-workspace/.task-output/runtime-pages-termux-integration-20261021/run-01`.
Counts below are individual runs, not a sum of unique tests.

| Area | Evidence/result |
|---|---|
| Semantic-name real write paths | `k1-retest.log`: 42 passed; earlier unaffected cases also passed |
| Lease/recovery/finish contracts | `k2-retest.log`: 28 passed; `k2-k7-exact-retest.log`: 10 passed including scheduler deadline regression and package reproducibility |
| Preparation/selection reads | `k3-tests.log`: 32 passed |
| Chat pages, response/evidence/ownership | `k4-backend.log`: 46 passed |
| Feed pages, nested visibility, ownership/reactions | `final-social-queries.log`: 32 passed |
| Migration/populated data | `k6-migrations.log`: 125 passed, 3 platform skips, 4 old expected-head failures; all four corrected cases plus frozen versions in `k6-migration-expectation-retest.log`: 11 passed |
| New v40→v41 rollback/row/index proof | `k6-index-migration.log`: 1 passed |
| Backend log policy | `k7-backend.log`: 22 passed |
| Owned Linux Termux processes/CLI/retention | `k7-posix.log`: 40 passed, isolated Linux/Python 3.13, network disabled |
| Release/bootstrap | `k7-release-final.log`: 85 passed plus one outdated module-list failure; exact corrected reproducibility test passed (`k7-release-retest.log`) |
| Page/anchor/gap/draft/media behavior | `k6-pages-final-next.log` and `k6-pages-final-static.log`: 5 passed each |
| Existing image integration | `final-image-browser.log`: 58 passed; six old full-feed-refresh fixtures corrected to single-summary contract, `final-image-summary-retest2.log`: 6 passed |
| Daily preparation Next/static | `final-daily-next.log`, `final-daily-static.log`: 2 passed each |
| Existing static Chat/World social/owner | `final-static-preservation.log`: 10 passed |
| Existing author→Chat/evidence/like tab races | targeted final reruns passed; a confirmed reaction now reaches the current same-auth/runtime view while World/actor scope is still checked |
| Static checks | Backend/frontend architecture, inventories, design, route security, migration contract, eslint and tsc passed |
| Build/transport | Production Next/static builds passed; media/proxy lifecycle and service-policy Node checks passed |

New Chat/Feed screenshots were inspected in Next/static on Windows. They show
the latest Chat position/composer and root Feed without a global loading takeover.
Two diagnostic capture sites are added; the eleven canonical snapshots and their
Linux thresholds are unchanged. This is LOCAL evidence, not installed USER CHECK.
Required CI retains its full impact selection; tests are not skipped to avoid it.

## Measured cost and limitations

`benchmark_pages.py` compares the same synthetic fixtures against the starting
commit and implementation using Windows Python 3.13, TestClient and in-memory
SQLite. Five reads per condition; no AI calls or writes. These are not Android
latency guarantees and not a controlled isolated CPU benchmark.

| Fixture | Before | After |
|---|---|---|
| 5,000 Chat messages | 5,000 returned, 3,888,085 bytes, 5,018 SELECTs | 50 returned, 80,260 bytes including compatibility projection, 19 SELECTs |
| 501 roots + 3,000 replies on one root | Latest 100 were replies, zero roots, 59,922 bytes, 17 SELECTs | 30 roots, 18,304 bytes, 18 SELECTs |
| Endpoint writes | 0 | 0 |

The large Feed fixture exposed a recursive rescan in the existing descendant
count query. The repository now materializes visible ID/parent edges once using
the same pattern as World notifications, then traverses them with UNION cycle
protection. Hidden/blocked/cross-World ancestors remain ineligible. Final five
reads took 33–83 ms on this fixture instead of the intermediate 5.1–6.6 seconds;
the earlier endpoint returned a different set, so its latency is not an equal
workload speedup claim. Exact counts still cost work proportional to the visible
graph; unbounded accumulated DOM and very large worlds remain future concerns.

Capture benchmark: isolated Linux amd64/Python 3.13, 30 seconds, three repeats
each for idle/low/burst. Idle CPU time fell from 0.164–0.199 to 0.020–0.025 seconds;
low-rate from 0.171–0.180 to 0.028–0.034. Burst (100,000 records, 5.8 MB) remained
4.108–5.046 seconds with unchanged write bytes and no reported losses/errors.
FD/thread close observations and RSS/PSS are in `capture-benchmark.json`.

Source-only logging (10,000 synthetic accesses, 1% errors) emitted 100 records /
5,400 bytes in basic instead of 10,000 / 780,000 legacy bytes. Detailed emitted
10,000 sanitized records / 540,000 bytes. This StringIO experiment excludes disk
and Capture cost; neither experiment measures physical-phone battery usage.

Actual original SQLite lock holders, real-AI answer quality, phone installation,
native ARM64 timing, screen-off activity and OEM power behavior remain unobserved
by this implementation verification. They are not prerequisites for the approved
PC handoff, but must not be labelled device PASS.
