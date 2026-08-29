# Contributing to Angmoo

Thank you for helping improve Angmoo. The canonical repository is
`angmoo-tree/angmoo`. Issues and pull requests may be written in English or Korean;
the English guide is canonical if translations differ.

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

The official contributor baseline requires Git and Docker Compose 2.22.0 or
newer. It is a reproducible Linux Docker environment with exactly two services:
Next.js development frontend and FastAPI `CONTRIBUTOR_EMBEDDED` backend. Start
it from the repository root:

```powershell
docker compose -f compose.yml -f compose.dev.yml up --watch
```

The backend process owns SQLite canonical persistence, FTS5, LadybugDB,
scheduler, and projector. Frontend HMR and logs are available from the frontend
container and browser DevTools; FastAPI reload and runtime logs are available
from the backend container. The named volume is contributor-only and never
mounts or copies `%LOCALAPPDATA%\Angmoo`.

Run checks in the pinned containers:

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python -m pytest -q
docker compose -f compose.yml -f compose.dev.yml exec -T backend uv run python ../scripts/check_ci_policy.py
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm lint
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm typecheck
docker compose -f compose.yml -f compose.dev.yml exec -T frontend pnpm build
```

Stop without deleting the contributor data volume:

```powershell
docker compose -f compose.yml -f compose.dev.yml down
```

Native Next.js/FastAPI commands remain an optional maintainer convenience, not
the cross-platform baseline. Contributors who change the actual Phone or wide
native windows may use the documented `Docker + Host Tauri dev` bridge against
the same Docker stack. They must not point it at installed-user data. Windows
packaging and installed-runtime behavior are verified on Windows Actions;
macOS packaging is not yet claimed as implemented.

On a supported Windows 11 x64 host, install the locked desktop dependencies,
run the fail-closed preflight, and start the bridge:

```powershell
npm ci --ignore-scripts --prefix desktop
.\scripts\dev\desktop-preflight.ps1
.\scripts\dev\desktop-dev.ps1
```

The wrapper starts or reuses the Docker dev stack and opens only the host Tauri
Phone/Studio/Graph shell. It must not start `angmoo-sidecar`, use
`%LOCALAPPDATA%\Angmoo`, stop the Docker stack, or delete its named volume. See
`docs/public/windows-host-tauri-dev.md` for support limits and the user check.

Changes under the CODEOWNERS platform-shell boundary require an explicit
**platform-shell maintainer review** record after Hosted Windows checks pass.
During the single-maintainer period this is a documented owner review Gate, not
an impossible self-approval requirement. The final user Phone and wide-window
screen Gate remains separate from technical CI.

Do not add PostgreSQL/Neo4j server runtime behavior, an offline PostgreSQL
importer, or a second implementation. SQLite is the only canonical store;
Neo4j parity survives only as static fixtures.

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
the isolated two-service Linux clean-clone lifecycle fixtures. Provider-dependent
tests use fake providers and must not make external model calls.

World Package changes must use synthetic fixtures only. The representative
closeout suite verifies a source-to-target round trip, final-artifact exclusion,
bounded staging, atomic commit/recovery, and independent target evolution:

```powershell
docker compose -f compose.yml -f compose.dev.yml exec -T backend `
  uv run python -m pytest -q `
  tests/test_l3_5_world_package_v1_contract.py `
  tests/test_l3_5_world_package_export.py `
  tests/test_l3_5_world_package_preview.py `
  tests/test_l3_5_world_package_import_commit.py `
  tests/test_l3_5_world_package_closeout.py `
  tests/test_l3_5_world_package_closeout_contract.py
```

Never upload a real `.angmoo-world` to a public Issue, pull request, Action
artifact, or log. Create a minimal synthetic package for ordinary bugs. Follow
`SECURITY.md` and agree on a private transfer before sharing a real artifact for
a vulnerability investigation. See `docs/public/world-package-v1.md` for the
portable-data and local-runtime exclusion boundary.

## Pull requests and merge ownership

Every change reaches `main` through a pull request. The required check meanings
include:

- `backend`
- `frontend`
- `embedded-data-migration`
- `local-core-smoke`
- `local-autonomy-smoke`
- `local-full-graph` (LadybugDB plus frozen static parity fixtures)
- `oss-boundary`
- `dependency-license`
- `dco`
- `architecture-boundary`
- `tauri-windows`
- `tauri-windows-host-dev`
- `windows-installer-build` for the exact-SHA NSIS/MSI candidate
- `windows-installer-clean-install` for an empty LocalAppData install/start
- `windows-installer-supported-upgrade` for every supported predecessor
- `windows-installer-failure-recovery` for fail-closed app/data rollback
- final `windows-installer` only when the complete installer matrix passes

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

User-visible frontend work must also read `frontend/DESIGN.md` and
`docs/architecture/frontend-design-reference.md`. Record whether hosted visual
anatomy is `DIRECT`, `ADAPTED`, `LOCAL`, or `REJECTED`, keep Next and
static/Tauri wrappers on the same feature component, and do not invent actions,
counts, routes, or state absent from the Local capability contract. Run the
design inventory alongside the architecture boundary:

```powershell
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

An intentional raw-color reduction updates
`security/frontend_design_policy.json` and regenerates
`docs/architecture/frontend-design-baseline.json` with `--write`. Increasing
the baseline or adding an asset, font, hosted-only source file, or screenshot
requires explicit rationale and provenance; regenerating a report alone is not
approval.

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
