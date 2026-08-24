# L3-ER7 typed embedded runtime composition

ER7 promotes the embedded runtime proven by the Windows installer work to the
single official local architecture. Runtime selection is explicit and
fail-closed:

| Profile | Canonical store | Graph | Components | Public API |
|---|---|---|---|---|
| `LOCAL_EMBEDDED` | SQLite | LadybugDB | in process | yes |
| `CONTRIBUTOR_EMBEDDED` | isolated SQLite | isolated LadybugDB | in process | yes |
| `TEST` | isolated SQLite or explicit fake | isolated LadybugDB or explicit fake | test-owned | test-owned |
| `LEGACY_MIGRATION` | PostgreSQL read-only input to SQLite generation | none during import | disabled | no |

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

## Transitional compatibility allowlist

Until the separately approved ER7 legacy-removal PR lands, the following old
surfaces remain present but are not canonical defaults:

- module-level `app.public_main:app` for existing CI and rollback tests;
- `LADYBUG_GRAPH_PREVIEW_ENABLED` as a read-compatible alias in old fixtures;
- PostgreSQL/Neo4j adapters and the six-service Compose files;
- explicit `provider=ladybug` query support used by ER3 regression fixtures.

New product and contributor code must use `GRAPH_PROVIDER=ladybug` through the
typed composition. The allowlist may shrink but must not grow. PR P removes the
legacy runtime only after PR O merge, rollback evidence, and separate user
approval.
