# Local embedded runtime contract

Angmoo has one official persistence, graph, and lifecycle meaning. Installed
users and contributors differ only in how the frontend and backend are
packaged; they do not use different databases or worker topologies.

## Canonical components

```text
frontend
   ↓
FastAPI backend
├─ SQLite canonical store
├─ FTS5 search projection
├─ LadybugDB graph projection
├─ scheduler component
└─ projector component
```

SQLite is the only canonical relational source. LadybugDB is rebuilt from
successful canonical events and is never an independent source of truth. The
scheduler and projector are supervised in the FastAPI process; there are no
external scheduler or projector services.

The four typed profiles are:

- `LOCAL_EMBEDDED`: Tauri static frontend and bundled FastAPI sidecar.
- `CONTRIBUTOR_EMBEDDED`: Docker or optional host development frontend with
  the same SQLite/LadybugDB/in-process backend meaning.
- `TEST`: isolated SQLite/LadybugDB or explicitly supplied fakes.
- `LEGACY_MIGRATION`: frozen PostgreSQL read-only input to an offline SQLite
  generation. Public API, scheduler, projector, SNS writes, and provider calls
  are prohibited.

There is no supported PostgreSQL/Neo4j server runtime or
`DOCKER_COMPATIBILITY` profile. Neo4j parity is retained as static ER3 fixtures,
not as a server, driver, JVM, or second query implementation.

## Contributor Docker topology

The official cross-platform contributor command is:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

It starts exactly two Linux containers:

```text
host browser -> frontend: Next.js dev, HMR, frontend logs
                         ↓
                backend: CONTRIBUTOR_EMBEDDED
                         ├─ FastAPI reload and logs
                         ├─ SQLite + FTS5
                         ├─ LadybugDB
                         ├─ scheduler
                         └─ projector
```

Only the frontend is published to the host, at `127.0.0.1:3000` by default.
Changing `ANGMOO_PORT` may move that loopback port. Angmoo never kills another
listener or silently chooses a new port.

Contributor state is stored in the Docker named volume
`angmoo_contributor_embedded_data`, under these logical directories:

```text
canonical/
graph/
media/
secrets/
runtime/
logs/
```

Compose never mounts or copies installed-user `%LOCALAPPDATA%\Angmoo` data.
Parent `DATABASE_URL`, `NEO4J_URI`, graph-provider, or external-worker variables
cannot change the typed contributor profile.

Normal shutdown preserves the named volume:

```powershell
docker compose -f compose.yml -f compose.dev.yml down
```

`--volumes` is a separate destructive reset and must be intentional. Removing
PostgreSQL or Neo4j services from Compose never prunes an old
`angmoo_postgresql_data`, `angmoo_neo4j_data`, or `angmoo_neo4j_logs` volume.

## Installed product topology

The Windows installed product runs the Tauri host and bundled FastAPI sidecar.
It does not require Docker, Node, Python, PostgreSQL, Neo4j, or a JVM on the
user's system. Its data remains under `%LOCALAPPDATA%\Angmoo`, with the `app`
payload lifetime separated from canonical user data.

The contributor named volume and installed product root must never be shared.
Default uninstall preserves user data; explicit remove-data remains a separate
interactive action.

## Optional platform-shell development

General feature work uses Docker and the host browser. Contributors changing
the actual Phone window, drag/resize, wide windows, or sidecar host lifecycle
may connect a host Tauri dev process to the same Docker stack. This is not a
second runtime architecture and must not use installed-user data.

The implemented Windows path is:

```powershell
.\scripts\dev\desktop-preflight.ps1
.\scripts\dev\desktop-dev.ps1
```

It loads the Docker frontend at `127.0.0.1:3000`, never starts a host sidecar,
and writes only the repository-local `.angmoo-dev/webview` profile. The complete
support, safety, and screen-check contract is in
[`windows-host-tauri-dev.md`](windows-host-tauri-dev.md).

Windows packaging is built and tested by Windows Actions. macOS packaging is
not claimed as implemented until a separate target-OS plan and validation pass.

## State, privacy, and recovery

Runtime state uses `stopped`, `starting`, `healthy`, `degraded`, `blocked`,
`stale_state`, and `stopping`. Human and JSON diagnostics use stable reason
codes without secrets or stack traces.

`APP_SECRET`, provider credentials, local content, and media never enter image
build arguments, image layers, tracked environment files, frontend containers,
or logs. Status and doctor may report only safe metadata.

Rollback uses Git commits/tags, prior installer artifacts, SQLite generations,
atomic migration markers, and preserved secrets/media. Angmoo does not keep a
second PostgreSQL/Neo4j runtime merely as a rollback path.
