# Embedded SNS checkpoints and canonical database generation retention

This policy applies to the backend's embedded runtime. It does not add a settings screen or a separate cleanup server. Its execution boundary is the coordinator, composition, and lifespan shared by the contributor/Docker backend and Windows sidecar.

## Detailed SNS records

When a new V2 activity is first created, store the `sns-completed-checkpoint-24h-v1` marker in canonical `ActivityGraphRun.result.checkpoint_retention`. Do not mark existing activities retroactively. Existing completed, failed, or interrupted records without a policy are not deleted through the former 30-day cleanup path either.

Clean up details only for activities whose normal `completed` or `observed` result is committed in the canonical DB and whose final graph write is confirmed, when `finished_at + 24 hours <= current UTC`.

Protect failed, waiting, running, interrupted, and unconfirmed results; valid leases; pending effects/activity claims; and dependencies needed to recover image receipt, storage, or attachment. Even when a resumed lease ID differs from the original activity ID, verify the actual character and canonical lease association.

Read completed results before accessing the graph, Provider, or a new LLM request. Continue checking read permissions, World, owner, engine/contract, and lane/receipt consistency. Autonomy OFF or an ended execution lease alone must not block reading an already completed result. A corrupt result that appears complete ends with a stable error; do not rerun it with an empty graph or new ID. Exclude internal cleanup namespaces from business responses.

Maintenance runs one cycle at startup and then at 1-hour intervals, even when SNS is OFF or no new activity occurs.

The default batch is 50. Each cycle allows at most 500 candidates or a 5-second budget for starting new work. Advance the `(finished_at, activity_id)` cursor past protected candidates and reconsider them on the next sweep.

For each candidate, commit a short conditional claim in an independent Session and close the canonical transaction. Delete all namespaces and writes for that thread through the public saver API `adelete_thread`, then persist a separate conditional completion marker. A failed or interrupted mark leaves the same cleanup target eligible for the next cycle.

Do not recreate canonical results, usage, effects, or image intent. Defer SQLite busy failures after a bounded wait; cleanup must not stop other characters' schedulers. Backup helpers and maintenance use the same root's OS maintenance lock to prevent overlap.

The 24-hour threshold is not an immediate deletion timer. Records may wait for a periodic cycle or remain longer because of protection or contention. Actual cleanup requires a running backend.

## Automatic database copies

Write `generation-retention.json` only when creating a genuinely new clean DB or migration staging generation. Record `canonical-generation-current-previous-v1`, creation ID, exact relative path, schema, immutable migration-manifest digest, and validation/promotion confirmation state.

The manifest digest is not a byte hash of the changing user database. Do not add markers to existing generations, staging directories, or manual backups.

Preserve the sequence: SQLite backup → forward migration → identity/manifest/FK/integrity checks → finalize → promote → post-promotion checks. Confirm a new promotion only after graph handling finishes, temporary engines close, and secret/media invariants pass. Cleanup follows that confirmation.

The default protected set is current + previous. Also protect generations in actual use, staging, unconfirmed promotions, corrupt/ambiguous markers or pins, and generations containing unknown files. This does not guarantee exactly two directories in total. It limits accumulation of new automatic copies while preserving legacy material and protection exceptions.

Only contributor or sidecar execution that owns serving startup may clean up generations. Diagnostics and installer/direct coordinator paths default to deletion authority OFF.

Actual OS serving locks and generation-use pins are distinct from raw PIDs or the mere existence of lock files. Consumers register pins under the shared migration lock before opening an engine, and release them after workers and engines stop. If shutdown cannot be confirmed, protect the pin. A stale pin can be cleaned up only after process exit and confirmed release of its OS lifetime lock.

Installer WAL checkpoints and subsequent preflight also retain a use pin on the selected generation until completion. Another serving startup may promote a new generation meanwhile, but the DB in use remains protected. This does not grant the installer deletion authority. Both success and exception paths release the pin; the next serving startup reassesses the protected set.

Database cleanup does not run at 1-hour intervals. It runs at the safe boundary where a new backend actually starts. A same-schema restart attempts retention cleanup without cloning a new DB or migrating. Relevant boundaries are backend recreation/restart in Docker, a developer's `up` that actually starts the backend again, or a new Windows sidecar start. This does not mean local source edits apply to an already running container.

Deletion is limited to one verified generation directly under canonical/generations. Reject root/current/previous, symlinks/junctions/reparse points, path escape, open pins, and unknown files. Do not delete WAL/SHM separately from an open database. Atomically record removal intent in runtime outside the generation before deletion so partial removal can be retried. Cleanup failure must not turn a working current generation into startup failure, recloning, or repromotion. This policy does not remove graph/search/media data or manual backups.

## Disabling cleanup and scope of application

`SNS_CHECKPOINT_POLICY_ENABLED=false` stops marking newly created activities. It does not remove existing policy markers or the canonical reader.

`SNS_CHECKPOINT_MAINTENANCE_ENABLED=false` stops the detail-deletion task. Completed-result readers and existing metadata remain.

`CANONICAL_GENERATION_RETENTION_ENABLED=false` stops generation deletion at startup. Ownership/use pins and records of newly created generations remain in force.

Stop cleanup through these settings before attempting a code downgrade or forced marker changes intended to undo deletion. Deleted details and obsolete copies are not restored automatically.

Use preserved canonical business results, current/previous generations, and separately secured backups as recovery evidence.

Environment changes apply when the relevant backend actually starts with the new configuration. Validate using temporary roots; do not clean personal Docker volumes or installed data as test fixtures.

For Docker, explicitly pass these names with `"false"` values through the backend `environment` in the chosen Compose file or an override. Adding a name to `.env` without having Compose pass it into the container is not an applied change. After restarting the backend, verify the configuration delivered to the actual process.

Deleting SQLite rows/BLOBs makes pages available for reuse. Database bytes, WAL, Docker VHDX size, and host free space do not necessarily shrink immediately or proportionally. This policy does not automatically run VACUUM, compact VHDX files, remove Docker volumes, or delete legacy material manually.

## Retired execution and recovery records

For unfinished old current/V1 SNS runs, use the supported transition in the same canonical Session. Do not resume the old run. After checking claims and uncertain effects, terminate it as abandoned/aborted. Do not retroactively add the new 24-hour tag to historical successes, usage, ledgers, or SDK details. Abandoned runs are not normal completed-cleanup candidates.

Durable normal/recovery reservations and input/output/output-policy data for the new split Routine recovery coexist with existing checkpoint_retention/name_binding/business results in the same CAS metadata.

Even if the final SDK write or graph confirmation fails after Finalize, reuse the canonical completed result rather than regenerating it. Startup handles old runs through that runtime's actual session factory before starting workers. Preserve serving/use pins, upgrade/maintenance locks, paired backups, and default protection for 2 generations. An SNS data transition does not create a new schema copy.
