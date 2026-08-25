# Contributor development

The official contributor profile is `CONTRIBUTOR_EMBEDDED`. It uses the same
SQLite canonical store, FTS5 search, LadybugDB projection, and in-process
scheduler/projector semantics as the installed product.

## Docker-first workflow

From the repository root:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

This starts:

- `frontend`: Next.js dev server, HMR, compile and route logs;
- `backend`: FastAPI reload, API/runtime logs, SQLite, LadybugDB, scheduler, and
  projector.

Open <http://127.0.0.1:3000>. Use the browser DevTools for frontend console and
network diagnostics. Use `docker compose ... logs -f backend` or `frontend` for
container logs.

Run deterministic checks inside the pinned containers:

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python -m pytest -q
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python ../scripts/check_ci_policy.py
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm lint
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm typecheck
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm build
```

The contributor named volume is separate from installed
`%LOCALAPPDATA%\Angmoo`. Parent `DATABASE_URL`, `NEO4J_URI`, graph-provider, or
external-worker settings do not change the typed Docker profile.

## Optional Docker + Host Tauri dev

General feature development uses the host browser. A contributor changing the
actual Phone window, native drag/resize, wide windows, or sidecar host lifecycle
may run a host Tauri dev process that loads the Docker frontend and connects to
the same Docker backend.

This is platform-shell development, not a second frontend, backend, or database
implementation. It must use the checkout's contributor endpoint and must never
read or write installed-user data. The host must provide the repository-pinned
Rust/Tauri prerequisites and the target OS WebView runtime.

Windows is the current reference shell environment and is also verified by
Windows Actions. macOS host development and app/DMG packaging require a future
target-OS contract; they are not claimed by this document.

## Native maintainer fallback

Maintainers may run Next.js and FastAPI natively for focused debugging, with an
explicit checkout-local data root. This is a convenience fallback, not the
cross-platform Quickstart or a different runtime profile.

## SQLite-only boundary

PostgreSQL and Neo4j are not contributor runtime services, and the repository
does not ship a PostgreSQL offline importer. Schema changes target the current
SQLite baseline and explicit SQLite generation lifecycle. Historical Alembic
revisions remain provenance evidence and are not an alternate runtime chain.

Neo4j has no development runtime. LadybugDB tests use frozen ER3 direct,
reverse, evidence, World-scope, and bounded-path parity fixtures.

Use synthetic data and fake providers. Never place credentials, APP_SECRET,
private content, personal runtime data, or raw logs in commits, Issues, or pull
requests.
