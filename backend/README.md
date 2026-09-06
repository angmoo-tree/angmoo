# Angmoo backend

The supported contributor environment runs the Next.js frontend and the
`CONTRIBUTOR_EMBEDDED` backend in two Docker containers. From this backend
directory, return to the repository root and start the stack:

```bash
cd ..
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The contributor launcher prepares the embedded SQLite generation, constructs
the runtime configuration, and calls `app.main.create_public_app`. That export
selects the public profile of the single application factory in `app/main.py`.
The contributor volume is separate from installed-user data.

Run backend checks from the repository root in the same development container:

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python -m pytest -q
```

Stop the stack while retaining the contributor volume:

```bash
docker compose -f compose.yml -f compose.dev.yml down
```

Local schema upgrades use the explicit embedded SQLite migration chain in
`app/runtime/migrations`. The existing `alembic/versions` files preserve
historical PostgreSQL revisions and their graph; `alembic upgrade head` is not
the Local database bootstrap procedure. Preserve existing revision and embedded
migration bodies when adding a supported data upgrade.

Read [Backend Architecture](ARCHITECTURE.md) for ownership and Session rules,
[Contributing](../CONTRIBUTING.md) for prerequisites and checks, and
[Contributor development](../docs/public/development.md) for supported execution
paths. Use synthetic data and fake providers for local tests.
