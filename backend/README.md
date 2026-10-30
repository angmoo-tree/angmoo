# Angmoo backend

The FastAPI backend owns local identity, Worlds, characters, SNS, Chat, memories
and relationships. PostgreSQL is canonical; full-text search, pgvector exact search and LadybugDB are
derived search/projection facilities. The scheduler and projector run within the same supported embedded application.

## Develop

From the repository root:

```sh
docker compose -f compose.yml -f compose.dev.yml up --watch
```

Open http://127.0.0.1:3000. See [contributor development](../docs/public/development.md)
for the isolated data volume, host tools and optional native window testing.
For released application installation, use [README](../README.md).

## Find the implementation

- [ARCHITECTURE](ARCHITECTURE.md): domain roles, dependencies and transaction ownership.
- `app/main.py`: the single app factory and public profile.
- `app/domains/`: HTTP and business behavior by owner.
- `app/runtime/`: resource lifetime and cross-owner composition.
- `app/runtime/persistence/postgresql_schema.py`: current schema and upgrades.
- `app/runtime/postgresql_installation.py`: supported 0.1.3 SQLite input migration.
- `app/runtime/migrations/`: frozen legacy SQLite input compatibility.
- `tests/`: business, runtime, adapter and migration regressions.

The contributor launcher and installed sidecar call `create_public_app` with
explicit runtime configuration. Do not recreate bootstrap by pointing a generic
server at personal data. Historical Alembic files are not used to initialize a Local installation.

## Verify a change

Select tests for the affected service, its consumers and relevant failure cases.
For example, when changing Chat behavior, run the matching files under
`tests/chat` using the repository's pinned uv environment. Changes to shared DB
or runtime behavior need their wider contract tests. The remote selection policy
is described in [CI validation](../docs/operations/ci-validation.md).

Use fake providers and disposable roots. Do not use installed user data or real
API credentials as test fixtures. Stop development with the documented Compose
`down` command and preserve the named volume unless deletion is intended.
