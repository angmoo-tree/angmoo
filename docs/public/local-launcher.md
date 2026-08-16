# Local launcher contract

Angmoo keeps Docker Compose as its canonical runtime. The Windows launcher is a
thin convenience wrapper: it validates the host, calls the same Compose files,
and reports stable results. It does not run a second supervisor, read database
rows, reveal APP_SECRET, or mount the Docker socket into an application service.

## Commands

Run these commands from any working directory by using the checkout's script
path. The script always resolves the installation root that contains it.

```powershell
.\angmoo.ps1 start
.\angmoo.ps1 status
.\angmoo.ps1 doctor
.\angmoo.ps1 doctor --json
.\angmoo.ps1 logs
.\angmoo.ps1 restart
.\angmoo.ps1 stop
```

`start`, `restart`, and `stop` are serialized by an installation-scoped host
lock. Repeated `start` and `stop` calls are idempotent. Normal lifecycle commands
preserve PostgreSQL, Neo4j, media, and APP_SECRET named volumes. Options such as
`--volumes`, `-v`, and `--purge` are rejected.

The original Quickstart remains official and starts the same six services:

```powershell
docker compose up -d
```

## Contributor mode

Use the contributor overlay when the checkout should build backend and frontend
development images:

```powershell
.\angmoo.ps1 start --contributor
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The launcher starts the development stack in the background and prints the
canonical Watch command. Compose Watch remains attached to the contributor's
terminal rather than becoming a hidden launcher daemon.

## Preflight and disk policy

Preflight verifies Docker Engine, Docker Compose, the supported CPU architecture,
canonical Compose configuration, the configured loopback port, disk space, and
the relationship between persistent database and secret volumes. It reports only
secret metadata such as `present` or `missing`.

- Fresh release-image pull: warn below 15 GB, fail below 10 GB, recommend 20 GB.
- Existing release stack restart: fail only at critical filesystem pressure.
- Contributor local build: warn below 30 GB, fail below 10 GB, recommend 40 GB.

Neither `start` nor `doctor` prunes images, build cache, containers, or volumes.
`doctor` reports low disk as a degraded result so cleanup remains an explicit
owner action.

## JSON and exit codes

`--json` emits `angmoo-launcher-result-v1`. Human and JSON output use the same
state, error code, and exit code. Important exit codes are `0` for success or an
idempotent no-op, `10` for Docker/Compose unavailable, `11` for host preflight
failure, `20` for startup failure, `21` for recovery or lifecycle-lock ownership,
`30` for a degraded doctor result, and `40` for a blocked destructive option.
