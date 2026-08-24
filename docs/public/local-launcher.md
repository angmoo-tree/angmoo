# Local launcher contract

The Windows PowerShell launcher is an optional thin wrapper around the official
two-service contributor Compose files. It validates the host, runs Compose,
and reports stable results. It does not supervise a second backend, read raw
database rows, reveal secrets, or mount the Docker socket into an application
service.

## Contributor commands

```powershell
.\angmoo.ps1 start --contributor
.\angmoo.ps1 status --contributor
.\angmoo.ps1 doctor --contributor
.\angmoo.ps1 doctor --contributor --json
.\angmoo.ps1 logs --contributor
.\angmoo.ps1 restart --contributor
.\angmoo.ps1 stop --contributor
```

The equivalent canonical command is:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The launcher starts the development containers in the background and prints
the Watch command. Compose Watch remains attached to the contributor terminal;
the launcher does not become a hidden daemon.

`start`, `restart`, and `stop` are serialized by a checkout-scoped host lock.
Repeated starts and stops are idempotent. Normal lifecycle commands preserve
`angmoo_contributor_embedded_data`. Destructive options such as `--volumes`,
`-v`, and `--purge` are rejected.

The plain non-contributor image mode is retained only for explicit container
artifact validation. It is not the installed-user product path and does not
restore PostgreSQL/Neo4j server compatibility. The canonical user product is
the Tauri installer.

## Aggregate status and doctor

`status` combines two separate safe sources in an
`angmoo-launcher-result-v1` result:

- the backend snapshot reports SQLite migration/integrity, local owner, World
  and WorldCharacter counts, scheduler lease, recent safe provider metadata,
  last successful activity identifiers, outbox/projector state, and LadybugDB
  health;
- the host launcher reports the two Compose services, restart counts, short
  image digests, loopback ports, disk pressure, Docker storage categories, the
  contributor named volume, and point-in-time container resource samples.

The backend never receives the Docker socket or host filesystem paths. If the
backend is unavailable, application checks become `unknown` while host Docker
diagnostics remain available.

## Diagnostic privacy

Human output, JSON, and tests share one recursive sanitizer. They may contain
opaque IDs, aggregate counts, normalized reason codes, timestamps, restart
counts, resource measurements, and shortened image digests. They never contain
APP_SECRET, provider keys, credential envelopes, cookies, authorization
headers, prompts, private content, full container IDs, or host absolute paths.

Status and doctor are read-only. They do not decrypt credentials, prune Docker
objects, mutate scheduler leases, replay outbox rows, or call a provider.

## Preflight and disk policy

Preflight verifies Docker Engine, Compose capability, CPU architecture,
canonical Compose configuration, the loopback port, disk space, and the
contributor volume. It never mounts `%LOCALAPPDATA%\Angmoo`.

- Contributor local build: warn below 30 GB, fail below 10 GB, recommend 40 GB.
- Existing stack restart: fail only at critical filesystem pressure.

Neither `start` nor `doctor` prunes images, build cache, containers, or volumes.
Cleanup remains an explicit owner action.

## JSON and exit codes

`--json` emits `angmoo-launcher-result-v1`. Human and JSON output use the same
state, error code, and exit code. Important exit codes are `0` success or an
idempotent no-op, `10` Docker/Compose unavailable, `11` preflight failure,
`20` startup failure, `21` recovery or lifecycle-lock ownership, `30` degraded
doctor, and `40` blocked destructive option.
