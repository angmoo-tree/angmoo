# L3-ER4 single backend runtime contract

## Scope

ER4 changes lifecycle ownership only. It does not change scheduler decisions,
provider calls, canonical rows, projection commands, or public HTTP contracts.
At the time of ER4, the in-process path was enabled by an explicit
`compose.in-process.yml` proof override. ER7 later promoted that ownership to
the canonical installed and contributor runtimes and removed the override and
external worker services.

## Ownership

```text
FastAPI lifespan
├─ scheduler component
│  └─ existing L2 resident scheduler
└─ projector component
   └─ existing relationship outbox worker
```

`app.runtime.single_backend_components` owns task creation, startup readiness,
bounded shutdown, and privacy-safe observations. API status reads consume only
`app.domains.runtime.public`. The three exact imports from
`app.runtime.component_workers` to the existing worker logic are
reviewed compatibility edges. They preserve the L2 behavior while ER4 changes
only the owner process; the policy requires their later removal behind
canonical runtime ports.

## Startup and shutdown

Startup succeeds only after both components report either `ready` or an
allowed graph `degraded` state. A duplicate scheduler lease fails startup and
the already-started projector is stopped. Shutdown first signals both workers,
allows the configured bounded drain, cancels non-cooperative asyncio tasks,
and records only bounded reason codes.

The graph component may start degraded because the canonical database remains
authoritative and its outbox is replayable. A scheduler duplicate is not an
allowed degraded startup state. A lease lost after startup, including a Windows
sleep gap longer than the lease TTL, is reported with the bounded
`scheduler_lease_lost` reason and retried inside the lifespan owner. Recovery
acquires a new fencing epoch and preserves the current-window-only no-catch-up
contract.

Contributor frontend startup removes only `.next/dev` before `next dev` starts.
This disposable Turbopack cache can retain a route manifest from an earlier
Compose Watch source snapshot and otherwise make existing App Router pages such
as `/login` resolve to the framework 404 page. Release images and user data are
unaffected.

## Opt-in Compose profile

Contributor validation uses:

The historical ER4 override command is no longer executable. The canonical ER7
contributor command is:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The Windows thin launcher exposes the same explicit profile and reports four
required containers while reading scheduler/projector state from the backend:

```powershell
.\angmoo.ps1 start --contributor --in-process
.\angmoo.ps1 status --contributor --in-process
.\angmoo.ps1 doctor --contributor --in-process
```

Before an in-process start, the launcher parks any existing external scheduler
and projector without deleting volumes. It only treats a repeated start as an
idempotent no-op when the backend diagnostic payload confirms both components
are already ready.

The typed ER7 profile now starts both components in process and has no
`external-workers` profile. A stale pre-ER7 worker, if manually left running,
still cannot become a second writer because the scheduler lease and projector
claim fencing fail closed.

## Preserved behavior and evidence

- scheduler singleton lease and process lock
- five-way bounded resident execution (`RESIDENT_TICK_MAX_RUNS=5`)
- deterministic scheduling and current-window-only no-catch-up behavior
- scheduler heartbeat and bounded shutdown drain
- projector bounded concurrency, claim fencing, retry, dead-letter, and replay
- graph degraded state without loss of canonical writes
- aggregate status uses content-free diagnostic codes only
- legacy external worker mode remains the default regression path

No prompt, provider response, API key, `APP_SECRET`, private content, host path,
or raw worker exception is stored in the component observation registry or
returned by the runtime status API.
