# L3-ER2 PostgreSQL to SQLite offline migration dry-run

Status: **production OFF / dry-run only**

This document freezes the PR G boundary for converting Angmoo's current
PostgreSQL canonical store into the SQLite schema introduced by ER2 PR D. The
tool proves that a complete, immutable source snapshot can be copied and
verified. It does not change the configured canonical database, start a new
runtime, or authorize ER3 cutover.

## Domain boundary

The runtime domain exposes only storage-neutral manifest and report contracts
through `OfflineCanonicalMigrationPort`. PostgreSQL snapshot mechanics,
SQLAlchemy reflection, SQLite generation management, and filesystem atomicity
remain infrastructure concerns under `app.runtime.migrations`.

No API route, UI action, scheduler job, projector worker, or startup hook calls
this adapter in PR G. A later approved transition stage must compose it
explicitly.

## Dry-run sequence

1. Validate all 81 Alembic revisions against the committed conversion
   inventory, including canonical LF source hashes and the expected head.
2. Verify the PostgreSQL source doctor: all 83 canonical tables, columns,
   primary keys, and the Alembic head must match the frozen source metadata.
3. Begin one `REPEATABLE READ, READ ONLY` PostgreSQL transaction.
4. Stream every canonical table in deterministic primary-key order into an
   owned temporary SQLite generation. Foreign keys are deferred only during
   the ordered bulk copy.
5. Recompute table row counts, primary-key digests, and complete row digests
   from SQLite and require exact parity with the source snapshot.
6. Require SQLite `foreign_key_check` to return zero rows and
   `integrity_check` to return `ok`. Contract-specific post-import verifiers
   may additionally exercise P1-P7 invariants.
7. Write a versioned manifest atomically, checkpoint the database, and rename
   the owned temporary generation into its final dry-run directory.
8. Return a report with `source_read_only=true` and
   `production_switched=false`.

The published dry-run generation is evidence only. The current PostgreSQL
runtime remains authoritative.

## Manifest and parity evidence

The manifest records:

- application and manifest versions;
- source dialect, Alembic head, migration count, lineage digest, and schema
  digest;
- target SQLite schema version and schema digest;
- conversion-inventory digest;
- per-table primary-key columns, row count, primary-key digest, and row digest;
- optional media-manifest audit result;
- a deterministic content digest over the migration evidence.

Secrets and plaintext credentials are never written to logs or the manifest.
Encrypted credential payloads are copied as opaque canonical rows and are
covered only by table digests.

## Failure and recovery contract

The migration fails closed before publication when it sees schema or lineage
drift, a non-PostgreSQL production source, missing or corrupt media, digest
mismatch, foreign-key violations, cancellation, disk-full errors, or a
contract-verifier failure.

On failure it removes only the owned `migration-tmp-*` generation. It does not
delete the source, another SQLite generation, canonical media, or runtime
secrets. A retry starts from a clean temporary generation. An existing final
generation is never overwritten.

## Synthetic proof matrix

Automated tests cover:

- an empty 83-table canonical store;
- an L3 fixture with two Worlds and the same character pair in both Worlds;
- pending and dead projection-outbox rows;
- visible, hidden, and deleted source events;
- present and removed credential records without exposing key material;
- valid, missing, and corrupt media manifests;
- cancellation, simulated disk-full failure, cleanup, and successful rerun;
- stale Alembic revision and accidental non-PostgreSQL source rejection.

At least one real PostgreSQL empty-schema dry-run is required before PR G is
reported ready. Synthetic SQLite sources are permitted only through the
explicit test-only flag and cannot be used by production composition.

## Explicit non-goals

- No production PostgreSQL to SQLite switch.
- No PostgreSQL or Neo4j removal.
- No vector index activation.
- No provider, LLM, image-generation, or public SNS write.
- No private user fixture export in CI.
- No ER3 LadybugDB projection cutover.
