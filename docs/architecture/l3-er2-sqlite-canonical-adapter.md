# L3-ER2 SQLite canonical adapter contract

Status: PR D implementation, production OFF

## Purpose and boundary

This adapter proves that the frozen Angmoo canonical schema and existing
SQLAlchemy repositories can run on one file-backed SQLite database without
changing the current PostgreSQL product path. It is an infrastructure adapter
below the domain and application layers; domains do not import SQLite.

PR D does not switch production, migrate user data, add FTS5, enable vector
recall, change scheduler or projector concurrency, or remove PostgreSQL. Those
changes remain in ER2 PR E-G and later embedded-runtime stages.

## File ownership and lineage

The installed-runtime path contract is:

```text
%LOCALAPPDATA%\Angmoo\canonical\generations\<generation>\angmoo.sqlite3
```

Resolving the path has no filesystem side effect. Opening the adapter creates
the generation directory and database. A generation identifier is restricted
to an ASCII filename-safe token and cannot traverse directories.

The initial embedded baseline is derived from the frozen PostgreSQL model
inventory at Alembic revision `20260819_0082`:

- source migrations: 81
- canonical tables: 83
- embedded schema version: 1
- schema lineage table: `angmoo_schema_version`
- schema digest: deterministic SHA-256 over normalized `sqlite_master` DDL

The adapter fails closed when the version row is missing, the Alembic lineage
does not match, an unversioned schema is present, the DDL digest changes, or an
existing file cannot satisfy the configured connection/page contract.
Later schema changes must advance the embedded version and supply an explicit
SQLite migration; PostgreSQL Alembic files are not replayed against SQLite.

## SQLite connection contract

Every connection applies:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;
PRAGMA wal_autocheckpoint = 1000;
PRAGMA page_size = 4096;
```

`FULL`, a 4 KiB page, and a 1,000-page automatic checkpoint are conservative
PR D defaults. ER2 PR E owns concurrency, crash, disk-full, retry, and
checkpoint benchmarks and may change them only with recorded evidence.

One `SqliteCanonicalDatabase` owns the engine, session factory, checkpoint,
doctor, and close lifecycle. `SqliteUnitOfWork` implements the same
`UnitOfWorkPort` used by the current persistence path. It never commits behind
a repository caller except where a pre-existing repository contract already
owns that transaction.

## Canonical representation

- UUID: lower-case, hyphenated text
- ULID: upper-case Crockford text
- timestamp: timezone-aware UTC ISO-8601 with microseconds and `Z`
- JSON: UTF-8, sorted keys, compact separators, no NaN or Infinity
- enum: explicit allowlist plus database CHECK constraints
- vector legacy payload: finite-number JSON text while vector recall is OFF

The PostgreSQL `Vector(768)` model column compiles to SQLite `TEXT`; this is a
storage-compatibility fallback, not an enabled vector search path.

Foreign keys and CHECK/UNIQUE constraints are preserved. The 13 PostgreSQL
partial-index predicates are copied to SQLite partial indexes, including the
nullable scheduler-slot uniqueness contract.

## Repository and domain boundary

Existing SQLAlchemy repositories receive a normal SQLAlchemy `Session` from
this adapter. There is no separate SQLite fork of identity or product policy.
The contract test executes the existing `SqlAlchemyIdentityRepository` against
the file-backed database, closes the engine, reopens it, and verifies the same
owner/session state.

Application composition imports the canonical model registry before opening
the adapter. The persistence adapter only reads the registered SQLAlchemy
metadata and fails closed unless all 83 tables are present; it does not create a
new runtime-to-legacy-model dependency.

The current PostgreSQL adapter remains the runtime default and continues to run
the full test and migration suites. SQLite selection is not wired into settings,
FastAPI startup, Docker Compose, scheduler, projector, or release packaging in
PR D.

## Doctor and rollback

The doctor reports the resolved file, generation, embedded version, source
revision and migration count, schema digest match, canonical table count, and
all connection PRAGMAs. It contains no row data, credential, token, prompt, or
user path beyond the database location already owned by the local runtime.

Rollback for PR D is code-only: stop selecting or remove the OFF-by-default
adapter. PostgreSQL data and product behavior are untouched.
