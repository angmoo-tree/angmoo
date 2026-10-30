# Backend guide

The FastAPI application is composed in `app/main.py`. Domain routes own HTTP,
domain services own policy and state transitions, same-owner persistence files
own storage, and runtime owns composition. Read
[Backend Architecture](../../backend/ARCHITECTURE.md) before changing code.

PostgreSQL is the canonical 0.1.4 store, including activity checkpoints, keyword
search and exact pgvector retrieval. LadybugDB is rebuildable. The official
entrypoint is `python -m app.runtime.postgresql_server`; deployment prepares a
protected marker/DSN and current schema before serving. Never supply a personal
DB to tests or use the runtime role for schema migration.

See [development](development.md), [runtime](postgresql-runtime.md),
[SQLite 0.1.3 migration](postgresql-migration.md), and
[backup and restore](postgresql-backup.md). Frozen SQLite and historical hosted
Alembic files are compatibility/provenance evidence, not the current PG chain.
Select tests for affected behavior and report local, CI and user checks separately.
