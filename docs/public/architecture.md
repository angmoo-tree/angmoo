# Angmoo public architecture

This document describes the public-source local product architecture. It does
not describe a private hosted deployment or promise production-grade
self-hosting.

## Supported topology

Angmoo uses one embedded backend composition for installed users and
contributors:

```text
Next.js dev, Tauri WebView, or bundled static frontend
                         ↓
                    FastAPI
                    ├─ SQLite canonical persistence
                    ├─ FTS5 search projection
                    ├─ LadybugDB graph projection
                    ├─ scheduler component
                    └─ projector component
```

The installed product runs Tauri plus a bundled FastAPI sidecar. The official
contributor Quickstart runs a Next.js development frontend and the same typed
`CONTRIBUTOR_EMBEDDED` backend in two Linux Docker containers.

PostgreSQL is not a supported application runtime. The frozen
`LEGACY_MIGRATION` tool may read one approved PostgreSQL schema revision in an
offline, read-only process and atomically promote a verified SQLite generation.
Neo4j is not a runtime dependency; ER3 relationship meaning remains as static
parity fixtures used by LadybugDB tests.

## Request and autonomous-runtime flow

```text
HTTP route
   ↓
domain/application use case
   ↓
RepositoryPort / GraphProjectionPort / GraphQueryPort
   ├─ SQLite adapter
   └─ LadybugDB adapter

FastAPI lifespan
   ├─ scheduler component -> SQLite lease and canonical writes
   └─ projector component -> SQLite outbox -> LadybugDB
```

- Routes own HTTP parsing, authentication dependencies, and response/error
  conversion.
- Domain/application code owns authorization, policy, deterministic choices,
  and transaction boundaries.
- Repository and graph ports preserve domain-first boundaries and testability;
  they do not promise permanent multi-database support.
- SQLite is the source of truth. LadybugDB graph state can be cleared and
  replayed from successful canonical events.
- Code validates World scope, source-event success, deletion/hide/cancel state,
  and bounded context before an LLM may generate creative output.

## Runtime profiles

- `LOCAL_EMBEDDED`: installed product, Tauri static frontend, bundled sidecar.
- `CONTRIBUTOR_EMBEDDED`: Docker-first development, optional host Tauri bridge.
- `TEST`: explicit isolated stores or fakes.
- `LEGACY_MIGRATION`: offline PostgreSQL read-only source only.

Profiles are converted to typed runtime configuration and passed to the FastAPI
composition root. Parent environment variables cannot silently select a server
database, Neo4j, or external workers. Missing or invalid profiles fail closed.

## Provider and credential boundaries

Provider-neutral contracts live under `app/providers/`. Provider adapters are
the only modules that import an external provider SDK. Fake providers cover
network-free success and failure scenarios.

`app/credentials/resolver.py` is the application boundary allowed to decrypt a
stored credential envelope. Raw credential material is revealed only at the
provider request boundary. Logs, trackers, traces, run results, and read
responses use identifiers, fingerprints, booleans, or redacted errors.

## Preserved contracts

- Generated FastAPI `/openapi.json` is the canonical REST contract.
- The frozen SQLite baseline and explicit SQLite migration chain are the
  canonical schema contract; historical PostgreSQL Alembic files are evidence,
  not a new-feature runtime chain.
- World scope, owner control mode, deterministic P2/P3/P4 behavior,
  credential redaction, lease/fencing, retry, and restart behavior remain
  compatibility surfaces.
- Intentional breaking changes require an Issue, deterministic tests, a data
  migration when applicable, and a rollback plan.

## Public/private boundary

The public source includes FastAPI, Next.js, Tauri, SQLite/LadybugDB adapters,
scheduler/projector components, providers and fakes, local owner, World and
social surfaces, migrations, public-safe tests, Docker contributor tooling,
and target-OS packaging workflows.

It excludes hosted infrastructure, production credentials and configuration,
private runbooks, dumps, backups, logs, traces, uploads, runtime outputs, and
private admin or maintenance operations.
