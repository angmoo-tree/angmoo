# Isolated Termux PostgreSQL trial and SQLite migration

For the 2026-10-28 candidate, also apply the [historical snapshot policy](memory-experience-snapshots.md):
schema 3, existing PG clone upgrade and one backend process. The 10-27 evidence below is historical,
not acceptance of the new candidate.

Date: 2026-10-27. This is the operating guide for the **prepared local trial `angmoo-pg-20261027-run01`**, not a released installer or an official update. [한국어](postgresql-termux-experiment.ko.md).

## Supported and tested combination

| Component | Scope |
|---|---|
| Source installation | Termux Angmoo 0.1.3, source `01ef3847c77a890071728b7f618f18fa88b775bf` |
| SQLite source | Schema 41, revision `20261022_0118`, migration count 117, 181 canonical tables |
| Target | PostgreSQL 17.11 and pgvector 0.8.7, ARM64 image filesystems executed by PRoot |
| Physical device | Galaxy A52s SM-A528N, Android 14, Google Play Termux 2026.10.09 |
| Search | GIN full-text search with CJK bigrams/normalized substring matching; 768-dimensional float32 cosine exact vector search |
| Migration | Canonical records, reusable vectors and budgets, checkpoints/pending writes, media and secrets; FTS/LadybugDB rebuilt from canonical data |
| Other schemas | Schema 40/42, unknown or corrupt files are rejected; no unverified upgrade chain |
| Deferred | G5 mixed workloads, long runs, screen-off/resource/battery comparison, real AI and user checks; Windows installer and Docker product support |

The stock PRoot failed at the Google Play Termux Android linker/shared-memory helper boundary. The successful run uses a pinned, locally patched PRoot and an APK loader **inside the trial setup**. It does not replace global PRoot, change Termux settings, or alter the installed `angmoo` wrapper. This is evidence for this device/combination, not all Android devices. See `scripts/postgresql_experiment/build_phone_proot.py` and the run's `versions.lock.json` / `g1-report.md`.

## Locations and identities

PC source: `D:/project_code/angmoo-workspace/experiments/angmoo-postgresql-termux`, local branch `experiment/postgresql-termux`, no remotes, pushes disabled. The original `angmoo-tree-angmoo` repository remains available on `main`/`work/0.1.4` without reverting the experiment.

The following commands run in **Termux**:

```sh
TRIAL="$HOME/angmoo-pg-experiments/20261027-run01"
python "$TRIAL/scripts/phone_app.py" status all
```

| Resource | Location |
|---|---|
| Tools | `$TRIAL/scripts/` |
| Image archives/identity | `$TRIAL/artifacts/`, `$TRIAL/records/app-images.json` |
| PostgreSQL filesystem/data | `$TRIAL/rootfs`, `$TRIAL/pgdata`, loopback port 15414 |
| Backend/frontend filesystems | `$TRIAL/images/`, loopback ports 18114 / 13114 |
| Immutable source snapshot | `$TRIAL/migration/D0`, `snapshot.json` |
| Offline conversion copy | `$TRIAL/migration/D1` |
| Migrated app | `$TRIAL/appdata`, database `angmoo_pg_run01` |
| Restored validation app | `$TRIAL/appdata-restore`, database `angmoo_pg_run01_restore` |
| Old-version recovery copy | `$TRIAL/migration/D2-recovery`, `$TRIAL/recovery-images/` |
| Selected target | `$TRIAL/records/selection.json` |
| Credentials | Private files under `$TRIAL/secrets/` and app `secrets/`; never print or commit their contents |

All three images are local and unpublished. PRoot executes their filesystems; there is no Docker daemon on the phone. The manifest records exact image/archive hashes and source commits. The frontend change is limited to preserving the PostgreSQL SQLSTATE field in the existing Chat diagnostic export (two files). Its provenance is **LOCAL**, with no hosted visual reference or new screen. Frontend and backend build commits differ. These are experimental assets, not a final release candidate built from a single commit.

## Restart the already validated target

Do **not** reconvert/reactivate an already used target. Initial `verify` compares its canonical records with the source snapshot; normal new session/activity records will make that comparison differ after use. Continue from the existing verified selection:

```sh
python "$TRIAL/scripts/phone_app.py" start all
python "$TRIAL/scripts/phone_app.py" status all
# Open http://127.0.0.1:13114 on the phone.
python "$TRIAL/scripts/phone_app.py" stop all
```

Startup is PostgreSQL → backend → frontend; shutdown is the reverse. The launcher checks PID/start ticks/boot ID, executable mappings, source and launch identities. It reuses an already ready owned process and never kills another process to reclaim a port. A partial startup failure retains processes and records; inspect the cause, stop the trial with `stop all`, and retry.

Serving uses `angmoo_pg_run01_runtime`, with application DML privileges but no superuser, database creation, schema creation or schema-ledger modification. Preparation/migration/backup/restore uses the separate `angmoo_pg_run01_admin` credentials. Credentials stay in separate private files.

The launcher supports `validation` and `real-use`. Without a mode record it defaults to `validation`, which suspends automatic SNS/AI workers and blocks external provider sockets. It validates decryption, HTTP, storage/search and synthetic checkpoint resumption. Real-use enables chat, autonomous SNS, memory processing and embeddings with the copied credentials and existing settings. Due work may run immediately and incur API usage. Character switches, models and budgets are not changed by the mode selection.

After the user requests G5 real use, preserve a PostgreSQL/app backup before switching:

```sh
python "$TRIAL/scripts/phone_app.py" stop frontend
python "$TRIAL/scripts/phone_app.py" stop backend
python "$TRIAL/scripts/phone_app.py" start postgres
python "$TRIAL/scripts/phone_migrate.py" pg-backup
python "$TRIAL/scripts/phone_app.py" mode real-use
python "$TRIAL/scripts/phone_app.py" start all
python "$TRIAL/scripts/phone_app.py" status all
```

`records/execution-mode.json` binds the mode to the selected data paths and persists across restarts. Changing mode requires the app to be stopped. To return, use the same shutdown sequence followed by `mode validation` and `start all`. This does not undo trial activity or copy it back to the original SQLite installation.

Both modes retain SQLite denial, trial path/database identity checks and the limited runtime role. Real-use readiness requires backend `/health` to report `validation_mode=false`, `automatic_activity=enabled` and a ready real scheduler. It is not evidence of full G5 acceptance, AI quality or USER CHECK.

Exported Docker filesystems have an empty `/etc/resolv.conf`. The launcher copies the installed Termux resolver to `$TRIAL/records/resolv.conf` and binds that private copy inside PRoot. It does not modify global DNS or image files and retains the copy across starts. DNS/TLS reachability is distinct from credential authentication and an actual AI response.

Service logs remain in `$TRIAL/logs/` while processes are alive, including after USB disconnection. Selecting a mode does not start a full SNS observation session or a long-running CPU/PSS recorder. G5 workload comparison, request/cost accounting, 60-minute/8-hour and screen-off results require separate measurement records.

FTS can revalidate/rebuild canonical records on startup. Several minutes were observed on this phone. Search reports `preparing` during this interval instead of silently returning an empty result or using SQLite. HTTP `/health` means that the service started; it does not mean that every search projection is ready. Check projection progress and PostgreSQL diagnostics too.

## First migration into a new empty trial

The following sequence applies only to a **fresh owned target**. It must not be rerun over this populated `run01`; existing D0/targets are refused. A new run needs a new explicitly reviewed root/DB/port ownership configuration and image manifest. Do not delete old data to reuse a run name.

1. Identify the installed source and data root with `angmoo status`. Stop the source normally and verify no original-data file descriptors remain open.
2. Prepare the pinned PostgreSQL 17 cluster, extensions, private roles and empty database with the G1 ownership records. Keep data and credentials outside images.
3. Run the migration commands below. `activate` changes only the experimental launcher selection.

```sh
python "$TRIAL/scripts/phone_migrate.py" inspect
python "$TRIAL/scripts/phone_migrate.py" dry-run
python "$TRIAL/scripts/phone_migrate.py" backup
python "$TRIAL/scripts/prepare_phone_database.py"
python "$TRIAL/scripts/phone_migrate.py" convert
python "$TRIAL/scripts/phone_migrate.py" verify
python "$TRIAL/scripts/phone_migrate.py" activate
python "$TRIAL/scripts/phone_app.py" start backend
python "$TRIAL/scripts/phone_app.py" start frontend
```

`inspect` checks quiescence, total files/bytes and disk budget, and inspects schema/integrity when a consistent D1 already exists. `backup` verifies free space and copies the complete stopped installation to D0 and D1. Open writers, changes during copying and existing destinations are refused. Schema inspection happens on consistent D1 before canonical target writes.

`prepare_phone_database.py` starts the G1-owned cluster and creates the empty target database, extensions, ownership identity and private admin DSN. No manual SQL is required. This run is already prepared, so a repeated invocation is refused before changes.

Conversion preserves IDs, types, FKs/unique constraints, UTC timestamps, JSON, settings and budgets, and verifies normalized row digests in primary-key order. Vec1 payloads are extracted and checked against canonical registrations, profiles, versions and scopes, then reused as exact float32 vectors. No embedding calls occur. Checkpoints are decoded using a reviewed strict serializer and converted to the pinned SDK format with parent/channel/pending-write checks. Unknown types stop migration.

D0 must match the whole byte manifest. D1 may recreate transient SHM and an **empty WAL belonging to a known database** during read-only SQLite access. Nonempty WAL, DB, vector/checkpoint payload, media or secret changes remain fatal. Original WAL content is preserved unchanged in D0.

Before activation the tool rechecks source freshness, D0, conversion and app files. It never replaces the original wrapper or SQLite installation. If the original app has been used since the snapshot, make a new snapshot in a new trial instead of treating an old conversion as current.

## Interruptions, resume and refusal

```sh
python "$TRIAL/scripts/phone_migrate.py" convert --stop-after canonical
python "$TRIAL/scripts/phone_migrate.py" resume
python "$TRIAL/scripts/phone_migrate.py" abort
```

`vectors` and `checkpoints` are also explicit stage boundaries. A completed stage resumes only with the same migration ID and snapshot digest. `abort` records a stopped migration and retains staging; it does not delete data or roll back the original. Wrong targets, different migration identities, schemas 40/42, corruption or undecodable checkpoints fail closed rather than producing a blank usable app. Detailed failures remain in private `records/operation-failure-*.json`; do not share raw contents that could include SQL/user text.

## PostgreSQL backup and restore

Stop app writers but keep PostgreSQL running. `pg-backup` combines a `pg_dump -Fc` snapshot with media/secrets/runtime files, image/version/role requirements and table/sequence/constraint/index/trigger fingerprints. Do not copy live PGDATA as an application backup.

```sh
python "$TRIAL/scripts/phone_app.py" stop frontend
python "$TRIAL/scripts/phone_app.py" stop backend
python "$TRIAL/scripts/phone_migrate.py" pg-backup
# Use the returned backup path. This is the actual validated backup:
# Run restore only while its destination database does not exist.
python "$TRIAL/scripts/phone_migrate.py" pg-restore --backup backups/20261027-055021-278a2bf5
python "$TRIAL/scripts/phone_migrate.py" activate-restored
```

That backup was restored into empty `angmoo_pg_run01_restore` and passed app/API, search and interrupted-checkpoint resumption checks. **The restore destination now exists; do not rerun pg-restore.** Restart the verified selection with `start all` instead. `pg-resume-restore --backup ...` can resume a fingerprint-comparison interruption. A partially copied `appdata-restore` is not overwritten automatically; retain its evidence and retry in a fresh isolated destination after diagnosis.

Preserve PostgreSQL major 17 and the required roles/extensions. Do not attach a new major image to old PGDATA. Restore acceptance compares row digests, sequences, ACLs and DDL semantics, not only the exit code. Only PostgreSQL's equivalent constant-array cast spellings are normalized; different constraints remain failures.

## Return to the original SQLite application

Resume coding in the original repository. On the phone, stop the trial, then use the existing `angmoo start` to use the untouched original installation and data. Deleting experiment files is unnecessary.

The recovery exercise copied D0 to writable D2 and copied the old 0.1.3 image filesystems into the trial directory. It did not restore over the installed data. Preparation is provided by `phone_migrate.py rollback-to-snapshot` / `phone_recovery.py prepare`; it has already happened in this run, so do not repeat it.

```sh
python "$TRIAL/scripts/phone_app.py" stop all
python "$TRIAL/scripts/phone_recovery.py" start backend
python "$TRIAL/scripts/phone_recovery.py" start frontend
python "$TRIAL/scripts/phone_recovery.py" stop frontend
python "$TRIAL/scripts/phone_recovery.py" stop backend
```

The old-version harness is a read/recovery check with external APIs and automatic workers suspended. **D0 restores the pre-migration point in time. Changes created later in PostgreSQL are not backported to SQLite.** Preserve them in a PostgreSQL backup. A lossless reverse converter is not provided.

## Diagnostics and interpreting results

Run `pg_diagnostics.py` inside the backend filesystem with the selected private DSN and data root. The old direct-SQLite SNS reporter refuses a PostgreSQL-marked root. For example:

```sh
python - <<'PY'
import pathlib,sys,time
r=pathlib.Path.home()/'angmoo-pg-experiments/20261027-run01'
sys.path.insert(0,str(r/'scripts'))
import phone_app
s=phone_app.selection()
x=phone_app.run_backend('/experiment/scripts/pg_diagnostics.py',
    '--dsn-file','/experiment/'+s['dsn_file'],
    '--data-root','/experiment/'+s['data_root'],
    '--output','/experiment/records/diagnostics-'+str(time.time_ns())+'.json')
print(x['stdout'])
raise SystemExit(x['returncode'])
PY
```

These are scoped scheduler/memory state and count diagnostics, not a judgment of AI responses. Do not output credential values or conversation bodies. Some existing public error codes remain for API compatibility; internal errors distinguish PostgreSQL SQLSTATE, pool, queue, timeout and currentness causes.

G4 migrated 181 canonical tables / 27,506 rows, 255 vectors, 1,754 checkpoints and 4,093 pending writes. The application, with SQLite connections denied, passed decryption of 57 encrypted credentials, 28 authenticated API checks, search, backup restore and synthetic interrupted-activity resumption. This does not establish real-AI quality, long-run suitability or compatibility with every phone.

No automatic cleanup is provided. Keep original data, D0, trial code/images/databases and evidence. Present exact owned resources and preservation choices, then delete only items the user explicitly authorizes in a separate cleanup task.

## SNS PostgreSQL transaction retries

Keep SERIALIZABLE and retry the complete short database unit, including fresh reads and ownership/currentness validation. `activity_write` uses the existing PostgreSQL transaction owner with at most four attempts, a five-second total budget and 20–100 ms exponential delays. Expire ORM values on every attempt, including retries after an outer COMMIT abort. This scoped budget accommodates PRoot overhead without changing the global isolation level or pool size.

Boundaries cover activity binding/leases/state initialization, Feed preparation/delivery/observation/finalization, Inbox settlement, Routine leases/state, provider allowance/profile bookkeeping, daily preparation, final results and checkpoint confirmation. Provider calls, image generation and filesystem effects remain outside replayable callbacks. Preserve existing publication idempotency and authorization checks; never replay an entire SNS run to hide a database failure.

Only confirmed aborts (`40001`, `40P01`, `55P03`) use the bounded retry path. An uncertain COMMIT requires durable receipt reconciliation, not blind replay. Constraint/ownership/currentness failures remain visible. Storage exhaustion/deadlines/pool failures are not provider backoff. Persist safe SQLSTATE metadata on failure and remove stale failure metadata on completion. Real PostgreSQL conflict tests verify fresh lease checks, concurrent metadata preservation and single provider/publication effects; real-phone acceptance and the full G5 assessment remain separate evidence.

Reference: [PostgreSQL 17 serialization failure handling](https://www.postgresql.org/docs/17/mvcc-serialization-failure-handling.html).

## Predicate capacity and interrupted selection recovery

The phone experiment launcher sets `max_pred_locks_per_transaction=256` and explicitly retains the previous relation promotion threshold with `max_pred_locks_per_relation=32`. Keep 20 connections, `shared_buffers=64MB`, application SERIALIZABLE isolation and currentness validation. Do not hide capacity error `53200` with retries. Measure additional shared allocation separately from total phone memory and stability under load. These settings apply only to the experiment launcher.

An interrupted v2 Feed/Combined TargetSelector may make one selection recovery after rechecking ownership, current inputs, the activity stage and absence of public effects. Preserve the original delivery history and normal-call reservation. Atomically reserve the existing recovery allowance and advance the delivery attempt, accepting the in-memory attempt only after commit. Only an actual response marks delivery complete. Stale callbacks cannot overwrite the new attempt; another interruption cannot replenish its allowance. Retention preserves the cycle being resumed while keeping the existing policy for other cycles.

Recovery is restricted to selection before public effects. It does not replay completed replies, likes or posts. The original provider request may already have incurred cost; a new request can add cost, bounded by the attempt and activity budgets. Ownership changes, stale inputs and exhausted budgets remain explicit failures. Real PostgreSQL tests cover parent-graph cancellation/resumption, a single public effect and atomic admission after COMMIT abort. Real-phone validation and long-running G5 acceptance are separate evidence.

Reference: [PostgreSQL 17 lock settings](https://www.postgresql.org/docs/17/runtime-config-locks.html).
