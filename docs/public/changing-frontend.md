# Changing the frontend

Read [`frontend/DESIGN.md`](../../frontend/DESIGN.md) before changing a
user-visible surface. Record the surface (`Phone`, `studio`, or
`relationship-graph`), feature owner, hosted adoption classification, shared
component decision, and capability/route impact in the pull request. The
supporting evidence and current debt inventory live in
[`frontend-design-reference.md`](../architecture/frontend-design-reference.md).

Keep API access behind the owning feature or canonical shared API adapter,
preserve distinct loading, empty, forbidden, not-found, degraded, retry, and
error states, and test at the fixed viewports required by the current L4.5
stage. Do not create separate Browser and Tauri feature implementations.

Run the deterministic contract checks before lint and builds:

```bash
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend build:static
```

The raw-color report is intentionally tracked. When an approved UI change
removes raw colors, lower the policy baseline and regenerate the report with:

```bash
uv run --project backend python scripts/ci/check_frontend_design_contract.py --write
```

Do not update the report merely to hide an increase. New raw colors remain
zero; touched repeated values move toward semantic roles.

Do not add remote build-time fonts, unapproved assets, or default external
image requests. A public page must load without production data or provider
credentials and must not expose admin, maintenance, or agent-tools controls.

Use the existing root `browser-tests` Playwright package. Do not add a second
Playwright installation or lockfile under `frontend`. Screenshot baselines
start only when the applicable L4.5 visual stage defines a deterministic
fixture and an intentional review process.
