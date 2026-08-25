# L3-ER7 typed embedded runtime composition

ER7 promotes the embedded runtime proven by the Windows installer work to the
single official local architecture. Runtime selection is explicit and
fail-closed:

| Profile | Canonical store | Graph | Components | Public API |
|---|---|---|---|---|
| `LOCAL_EMBEDDED` | SQLite | LadybugDB | in process | yes |
| `CONTRIBUTOR_EMBEDDED` | isolated SQLite | isolated LadybugDB | in process | yes |
| `TEST` | isolated SQLite or explicit fake | isolated LadybugDB or explicit fake | test-owned | test-owned |

`RuntimeConfig` owns the resolved data paths, SQLite generation, graph root,
component mode, origin policy, and product flags. `create_app(runtime_config=)`
constructs a dedicated SQLAlchemy engine/session factory and passes the same
resolved settings to graph reads, scheduler/projector ownership, status, and
media mounting. Provider and persistence values are not written back to
`os.environ`.

The installed product uses `%LOCALAPPDATA%\Angmoo`. Browser contributor runs
and Tauri debug runs use the checkout-local `.angmoo-dev` root. Neither may
silently fall back to PostgreSQL, Neo4j, an external worker, a relative SQLite
file, or a newly generated secret when profile resolution fails.

## ER7 PR P canonical contributor runtime

The official contributor path now runs the same persistence, graph, and
component meanings as the installed product:

```text
Linux Docker
├─ frontend — Next.js dev, HMR, browser logs
└─ backend — CONTRIBUTOR_EMBEDDED
   ├─ SQLite + FTS5
   ├─ LadybugDB
   ├─ scheduler in process
   └─ projector in process
```

The Compose project contains only `frontend` and `backend`. Its named volume is
development-only and is never shared with `%LOCALAPPDATA%\Angmoo`. PostgreSQL,
Neo4j, JVM, and external scheduler/projector processes are not supported public
or contributor runtimes.

PostgreSQL runtime and offline import support ended before the first public
SQLite-only release. Historical Alembic revisions remain provenance evidence,
not an executable import chain. Neo4j remains only in static ER3 parity
fixtures; no live server, driver, or JVM is required.

The module-level `app.public_main:app` and old environment-shaped settings are
test and rollback compatibility surfaces. Product and contributor entrypoints
must pass a typed `RuntimeConfig` directly and must not use those surfaces to
select a provider or persistence backend.
