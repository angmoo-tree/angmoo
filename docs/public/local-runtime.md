# Local Docker runtime contract

Angmoo is transitioning from a host-native contributor setup to one canonical
Docker Compose topology. This document records the L0 contract and its
Dockerfiles and Compose implementation. The proposal and acceptance matrix are
tracked in
[`#36`](https://github.com/angmoo-tree/angmoo/issues/36).

## Canonical topology

The default user and contributor environments both contain the complete local
application:

```text
frontend -> backend -> PostgreSQL
                 \-> Neo4j
scheduler -> PostgreSQL
projector -> PostgreSQL + Neo4j
```

Only the frontend is published to the host, at `127.0.0.1:3000` by default.
The backend, PostgreSQL, and Neo4j use service names on the internal Compose
network. Changing `ANGMOO_PORT` may move the frontend port; Angmoo never kills
another listener or silently chooses a different port.

The user command is:

```powershell
docker compose up -d
```

The contributor command is:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The contributor overlay builds the same Dockerfiles locally and enables
Compose Watch. Release Compose uses the official GHCR image names; publishing
those images and the final clean-clone gate are owned by PR C.

Reduced diagnostic starts are explicit service selections and are not the
general Quickstart:

```powershell
# core
docker compose up -d postgresql backend frontend

# autonomy
docker compose up -d postgresql backend scheduler frontend
```

## Support tiers

- Tier 1: Windows 11 with PowerShell 5.1 or 7 and Docker Desktop.
- Tier 2: current Ubuntu LTS with Docker Engine and Compose v2.
- Best effort: macOS. It is not an L0 release blocker until it has a clean
  clone smoke.

Compose 2.22.0 or newer is required because the contributor contract uses
Compose Watch. Engine support is capability-based: digest-pinned pulls,
healthchecks, named volumes, loopback publication, project isolation, and
dependency readiness must work. The first Windows baseline was recorded with
Docker 29.6.1 and Compose 5.3.0 on `linux/amd64` containers.

Application images use Python 3.13 with uv 0.11.9 and Node.js 22 with pnpm
10.33.2. PostgreSQL 16.14 with pgvector is the source of truth. Neo4j
2026.06.0 is a disposable, replayable relationship projection. Database
images are pinned by digest in `security/local_runtime_contract.json`.

## Modes

The default is always the full six-service Angmoo stack. Reduced modes exist
only for CI, diagnosis, and low-resource development:

- `core`: frontend, backend, PostgreSQL
- `autonomy`: core plus scheduler

A reduced mode must be reported as intentional, not as a healthy full stack.
BYOK absence produces `provider_not_configured` and no external provider call.

## State and error vocabulary

Runtime state uses `stopped`, `starting`, `healthy`, `degraded`, `blocked`,
`stale_state`, and `stopping`. Stable error codes are defined in the machine
contract. Human output and JSON output use the same code and must not expose a
secret or an internal stack trace.

Normal shutdown is:

```powershell
docker compose down
```

It does not delete PostgreSQL, Neo4j, media, or secret state. Volume removal
and data reset remain separate destructive actions and require an explicit
user decision.

## Secret boundary

`APP_SECRET`, provider credentials, database credentials, certificates, local
data, and media never enter a Docker build argument, image layer, tracked
environment file, frontend container, or log. L0 fixes the process and path
boundary; L1 owns persistent owner bootstrap, OS-vault/DPAPI storage, rotation,
and credential recovery.

## Core audit

`security/local_runtime_contract.json` assigns every current `app.core` module
an owner stage and disposition. Configuration, DB, IDs, transaction primitives,
redaction, request limits, and security primitives remain in core. Activity,
search, and media policy migrate to their owning domain/runtime stages. Core
must not import domains, runtime orchestration, or concrete integrations.

Device Home is owned by L2.5, local owner and persistent secrets by L1, and
World Package staging/import by L3.5. L0 only fixes the runtime route and data
boundaries; it does not implement those product surfaces.