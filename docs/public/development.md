# Contributor development

The supported contributor profile is `CONTRIBUTOR_EMBEDDED`. It uses the same
SQLite canonical store, LadybugDB graph projection, and in-process scheduler
and projector as the installed Angmoo product. Only the frontend delivery mode
changes between Next.js dev, Tauri dev, and a static release build.

Start the backend from one terminal:

```powershell
cd backend
uv sync --frozen
uv run python -m app.runtime.contributor_backend --data-root ..\.angmoo-dev
```

Start the frontend from a second terminal:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

The explicit `.angmoo-dev` root keeps contributor data separate from the
installed `%LOCALAPPDATA%\Angmoo` product data. Runtime profile, database,
graph provider, and component ownership are assembled by typed Python config;
parent `DATABASE_URL`, `NEO4J_URI`, and external-worker variables do not change
the embedded result.

For Phone, Creator Studio, Relationship Graph, native window, or sidecar work:

```powershell
cd desktop
npm install
npm run dev
```

The debug Tauri host uses `CONTRIBUTOR_EMBEDDED` and the checkout-local data
root. Release builds use `LOCAL_EMBEDDED` and `%LOCALAPPDATA%\Angmoo`.

Use synthetic data and fake providers for tests. Do not place real provider
credentials, APP_SECRET values, private content, or personal runtime data in
logs, Issues, or pull requests. The old PostgreSQL/Neo4j six-service Compose
path is a temporary ER7 rollback surface only; it is not a second supported
runtime for new features.
