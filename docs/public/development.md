# Contributor development

The official `CONTRIBUTOR_POSTGRESQL` profile runs one backend process with
PostgreSQL canonical persistence, full-text search, exact pgvector retrieval,
LadybugDB projection and in-process scheduler/projector.

## Docker-first workflow

Use Git, Docker with a Linux engine, and Compose 2.23.0 or newer. From the root:

```sh
docker compose -f compose.yml -f compose.dev.yml up --watch
docker compose -f compose.yml -f compose.dev.yml logs --tail 100 postgres backend frontend
docker compose -f compose.yml -f compose.dev.yml down
```

Open <http://127.0.0.1:3000>. Frontend HMR and backend sync/restart use these
same services. The private PostgreSQL container is not exposed on the host.
The DB, application media/secrets and DB bootstrap credentials use separate
volumes. `down` preserves them; do not add `--volumes` when data is needed.
The legacy SQLite volume is mounted read-only to refuse an accidental update
without the [migration tool](postgresql-migration.md).

## Focused verification

Use synthetic fixtures and fake providers. Run related tests for the actual
change rather than every backend/frontend test. PostgreSQL integration tests
require an explicitly owned disposable DB. `scripts/ci/prepare_postgresql_tests.py`
refuses a nonempty fixture. CI uses a private synthetic credential, never a
personal connection string. Do not point its explicit test DSN at a user DB.

```sh
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm typecheck
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm lint
```

Run the relevant domain/runtime tests, schema upgrade, cancellation, authorization,
conflict or migration cases as needed. Wider hosted checks follow
[CI validation](../operations/ci-validation.md). Local checks do not waive them.

## Storage and architecture changes

New schema changes belong to the versioned PostgreSQL schema owner. Preserve
SQLite 41 as an explicit 0.1.3 input, and keep original snapshots/secrets intact.
No historical hosted Alembic chain or Neo4j service is used by this runtime.
Read [runtime](postgresql-runtime.md), [migration](postgresql-migration.md),
[backend architecture](../../backend/ARCHITECTURE.md) and the frontend
[architecture](../../frontend/ARCHITECTURE.md)/[design](../../frontend/DESIGN.md).

## Native window development

Use [Windows Host Tauri dev](windows-host-tauri-dev.md) for window/drag/resize or
host lifecycle changes. It loads the Docker frontend and same DB/API, with a
separate repository-local WebView profile. It must never touch installed data.
Native installer validation separately builds the pinned Windows PostgreSQL
resources. macOS packaging is not covered. Keep credentials, raw logs, private
content and World Packages out of Git, public CI and Issues.
