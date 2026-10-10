# L3-ER2 SQLite concurrency contract

Status: PR E candidate, OFF by default

## Scope

This contract proves the embedded canonical database can preserve Angmoo's
existing claim, lease, idempotency, and projection-outbox meanings without
PostgreSQL row locks, `SKIP LOCKED`, or advisory locks. It does not switch the
production runtime to SQLite, enable FTS5, migrate user data, or connect
LadybugDB.

## One-process writer boundary

The future installed runtime owns one FastAPI sidecar process. That process
accepts work through a bounded task queue and keeps canonical SQLite write
transactions short. Each read-modify-write operation starts with
`BEGIN IMMEDIATE`, performs a state-conditioned update, and commits or rolls
back before provider, network, image, or graph work begins.

`SqliteRetryPolicy` supplies a finite attempt count, finite delay, and finite
elapsed-time ceiling. Exhaustion raises the stable
`sqlite_busy_retry_exhausted` reason code. Queue saturation fails explicitly as
`sqlite_task_queue_full`; it does not create an unbounded in-memory backlog.

## PostgreSQL semantic translation

| Existing mechanism | Embedded-runtime equivalent |
|---|---|
| `FOR UPDATE` | `BEGIN IMMEDIATE` plus version/state-conditioned CAS |
| `SKIP LOCKED` | bounded candidate query, lease owner/expiry, then per-row CAS |
| advisory transaction lock | one sidecar process plus durable singleton lease row |
| multiple worker processes | bounded internal task queue |
| database clock | injected UTC clock at the adapter boundary |

## Scheduler lease

`SqliteSchedulerLeaseRepository` implements the existing scheduler lease
domain contract using `runtime_scheduler_leases`. Acquisition, heartbeat,
tick-start, tick-finish, and release are fenced by owner ID, fencing epoch,
active state, and lease expiry. A different owner can reclaim only after
expiry, increments the fencing epoch, and makes stale owners unable to commit
subsequent lease operations.

This PR keeps the production scheduler composition on its PostgreSQL adapter.
The SQLite adapter is executable evidence for the later canonical switch.

## Projection outbox

`SqliteProjectionOutbox` implements the existing relationship outbox port.
It selects at most the bounded batch size, atomically changes each still
claimable row to `processing`, assigns an owner and expiry, and increments the
attempt count. An expired row can be reclaimed; an old owner cannot finalize
it. Active World rebuild exclusion and the established retry/dead-letter
policy remain intact.

SocialEvent and Outbox rows remain canonical SQLite data. LadybugDB remains a
rebuildable projection and is not written in the SQLite transaction.

## Executable evidence

`backend/tests/test_l3_er2_sqlite_concurrency.py` covers:

- ten concurrent scheduler acquisitions with exactly one active owner;
- expired lease reclaim and stale fencing rejection;
- ten identical owner writes with one Post and one idempotency ledger row;
- ten concurrent projector claims with one owner and no duplicate event/outbox;
- scheduler versus owner-write and scheduler versus projector contention;
- rollback immediately before commit and reclaim after a committed claim;
- WAL checkpoint, close/reopen, and a worker killed during a blocked
  checkpoint while preserving its already committed row;
- bounded busy retry and stable failure reason code;
- bounded sidecar task-queue rejection.

All fixtures are synthetic and file-backed. Provider calls, public writes to a
running Angmoo installation, user-data migration, and production selection are
zero.

## Remaining ER2 gates

PR F still owns FTS5/search parity and PR G owns offline PostgreSQL-to-SQLite
migration, restore, rollback, disk-full handling, and full oracle parity. No
SQLite canonical cutover is authorized by this contract.

## 2026-10-10 current SQLite runtime and recovery extension

The preceding ER2 paragraphs describe that historical stage, not the current runtime.
The injected session engine now selects the existing SQLite scheduler adapter for
SQLite, retaining other-dialect composition. Owner/epoch/expiry CAS remains canonical;
expired same-owner acquisition also increments epoch. Lease operations use short
BEGIN IMMEDIATE, rollback and fresh reads, at most four BUSY attempts/250ms, per-call
50ms busy timeout and restoration. LOCKED and other errors are not BUSY retries.
Canonical connection-pool checkout is also bounded at 50ms; general busy_timeout stays
5000ms. The tradeoff is earlier failure under pool pressure rather than unbounded
lease-worker delay. Existing outbox/manual-write callers are separately regressed.

The one-worker/four-capacity lease executor creates connections inside its thread,
expires queued work after one second and tracks actual concurrent Future completion.
Cancellation alone is not drain completion. One scheduler runner owns recovery:
DEGRADED stops new ticks, drains work, heartbeats the same valid owner/epoch or obtains
an expired lease's new epoch, respecting another owner. Backoff 1/2/4/8/10 seconds is
stop-interruptible. A supervisor does not independently restart it. Live unsettled
children prevent finish/restart, and cleanup does not mask the primary error.
Committed tick windows prevent effect replay after finish failure. No missed-window
burst, schema/migration, activity limit or AI policy change is introduced.

Scheduler health requires READY plus a live heartbeat owner/epoch/expiry proof.
Recovery/fatal/expired proof yields503; verified recovery yields200; projector policy
is retained. Diagnostics exclude SQL, keys and conversation content. The incident's
actual lock-holder remains unidentified; Chat is not assumed to be its cause.
Temporary SQLite tests and isolated final-source Docker fake ticks establish local
mechanical recovery only. Original app containers/data, installed-app identity,
real-AI behavior and physical-device USER CHECK are separate. See the
[implementation/verification record](../verification/creator-studio-copy-media-scheduler-20261010.md).
