# Contributing to Angmoo

Thank you for helping improve Angmoo. The canonical repository is
`angmoo-tree/angmoo`. Issues and pull requests may be written in English or
Korean; the English guide is canonical if translations differ.

## Before opening a change

- Read `docs/public/architecture.md` and `docs/public/contribution-map.md`.
- Start from the latest `main` in a branch or fork.
- Use synthetic data and fake providers. Never submit credentials, personal
  data, raw logs, backups, or a local user's World Package.
- Add or update the smallest relevant deterministic test.
- Keep unrelated refactoring out of a behavior change.

An Issue before implementation is recommended for features, bugs, and
structural changes so scope can be agreed first. Small documentation and typo
fixes may open a pull request without an Issue. Issue linkage is not enforced
mechanically. When an Issue exists, use `Closes #number` or an explicit
reference in the pull request.

## Local development and checks

The contributor baseline requires Git, Python 3.13 with `uv`, and the
repository-pinned Node/pnpm toolchain. The official contributor runtime is
`CONTRIBUTOR_EMBEDDED`: SQLite canonical persistence, LadybugDB projection, and
scheduler/projector in the FastAPI process. Start the backend with an explicit
checkout-local data root:

```powershell
cd backend
uv sync --frozen
uv run python -m app.runtime.contributor_backend --data-root ..\.angmoo-dev
```

In another terminal, start the normal Next.js development frontend:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

The backend logs remain in its terminal and frontend compile, route, console,
and network diagnostics remain in the Next.js terminal and browser DevTools.
`.angmoo-dev` is ignored and is never shared with the installed product's
`%LOCALAPPDATA%\Angmoo` data. Tauri window work may use `cd desktop; npm run
dev`; debug builds use the same contributor embedded profile and checkout-local
data root.

Run checks with the locked local toolchains:

```powershell
cd backend
uv run python -m pytest -q

cd ..\frontend
pnpm lint
pnpm typecheck
pnpm build
```

The previous six-service Compose environment is a temporary ER7 rollback
surface, not the canonical contributor architecture. Do not add new
PostgreSQL/Neo4j runtime behavior or a second implementation for that path.
During PR O only, the exact rollback command remains:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

Product-shell changes also run a required Chromium smoke in Core CI. A
contributor with the repository-pinned Node/pnpm toolchain on the host can run
the same deterministic, fake-backend suite without a provider or database
write:

```powershell
cd browser-tests
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test
```

The suite uses port `3100` by default and can use an already running frontend
through `ANGMOO_E2E_BASE_URL`. It must not point at a profile containing real
user data.

The required `local-core-smoke` check additionally builds the release targets,
scans image vulnerabilities and secrets, validates SPDX SBOM output, and runs
the isolated Linux clean-clone lifecycle fixtures. PostgreSQL and Neo4j test
legacy database state is disposable. Provider-dependent tests use fake providers and must not
make external model calls.
## Pull requests and merge ownership

Every change reaches `main` through a pull request. The ten required checks
are:

- `backend`
- `frontend`
- `migration-postgres`
- `local-core-smoke`
- `local-autonomy-smoke`
- `local-full-graph`
- `oss-boundary`
- `dependency-license`
- `dco`
- `architecture-boundary`

`windows-local-smoke` and `codeql` remain advisory checks. Advisory does not
mean ignored: failures and promotion conditions must be documented and
security findings must be resolved or explicitly triaged.

External contributors submit pull requests and cannot push to or merge
`main`. The repository owner performs the final review and merge after required
checks pass and conversations are resolved. During the single-maintainer
period, `required approvals: 0` avoids requiring an impossible self-approval;
it does not remove owner review or give contributors merge authority.

## License and DCO

Accepted contributions are provided under `GPL-3.0-only` unless explicitly
stated otherwise. Every human commit must certify the Developer Certificate of Origin 1.1 with a `Signed-off-by: Name <email>` trailer. Use:

```powershell
git commit -s
```

The DCO 1.1 confirms that you have the right to submit the contribution; it
does not replace the project license. Dependabot receives only the narrow bot
exception enforced by the repository checker.

## Contract and architecture changes

REST/OpenAPI, Alembic, routine/social/graph contracts, authorization,
credentials, lease/retry, and user-data boundaries are compatibility surfaces.
Intentional breaking changes require an Issue, migration or compatibility plan
when applicable, focused tests, and a clear rollback path.

T2.5 adds the incremental domain-first contract in
`docs/architecture/backend-domains.md`. Before adding backend behavior, choose
the owning domain or runtime area there. Cross-domain imports must use
`app.domains.<name>.public`; do not reach into another domain's internal module
or add a dependency on the horizontal `services`, `models`, `schemas`, or
`cruds` paths.

The L2.5 frontend product-shell contract is documented in
`docs/architecture/frontend-product-shell.md`. Route files import migrated
features only through `@/features/<feature>/public`; features do not deep-import
one another, and product-neutral `shared` primitives do not import features or
legacy data clients.

The import inventory records facts, while `security/architecture_import_policy.json`
records target rules and exact reviewed legacy exceptions. Existing exceptions
may shrink but must not grow merely to make CI pass. Run:

```powershell
uv run --project backend python scripts/ci/generate_architecture_inventory.py --write
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py tests/test_l2_5_frontend_architecture_boundaries.py
```

Keep structure-only PRs focused. Do not mix behavior changes, migrations,
provider configuration, dependency majors, transaction semantics, bulk
formatting, or Hosted/Private/Production settings into a package-move PR.

Report vulnerabilities through the private process in `SECURITY.md`, never a
public Issue.
