# Changing the frontend

1. Read [ARCHITECTURE](../../frontend/ARCHITECTURE.md),
   [DESIGN](../../frontend/DESIGN.md) and applicable directory instructions.
2. Identify the feature owner, composed screen, route and runtime consumers.
   Describe a visible before/after behavior rather than an old migration stage.
3. Classify reused design as DIRECT, ADAPTED, LOCAL or REJECTED and record its
   source. Use existing primitives, tokens and local assets.
4. Keep requests behind the feature API and common transport. Preserve scope,
   cancellation, accepted-write identity and late-response guards.
5. Add English/Korean labels, placeholders, errors and accessible names together.
6. Check the affected states and supported Next/static/native consumers.

Use concrete files under `features/<feature>`. Composition connects different
features with values, callbacks or slots. Do not restore `public.ts`/`shared`
facades or move business DTOs into a common folder merely to evade an import rule.

For navigation, confirm the destination in the current route/capability owner.
Static/Tauri must not expose a link that only works in Next. Use the common
viewport and actual scroll owner; do not restore the decorative phone frame.

For Chat history, retain the reader's position at the time the response arrives and separate
contiguous catch-up from the largest displayed ID. For Feed, preserve mounted
rows and drafts through additional-page and refresh errors. Retry a read after
a refresh failure, not an already accepted write. Lazy images must retain
authenticated transport, reserved space and URL cleanup.

## Choose verification by impact

Ownership and design changes use these checks from the repository root:

```sh
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
```

For shared screens, route/build changes or affected fixtures, select the relevant
builds and scenarios in the existing root `browser-tests` project:

```sh
pnpm --dir frontend build
pnpm --dir frontend build:static
```

These are available checks, not a requirement to rebuild both apps for every
prose edit. Remote required scope follows [CI validation](../operations/ci-validation.md).

Use synthetic data, fixed clocks and fake providers. Check loading, empty,
forbidden, offline, retry, narrow layout, keyboard and long English/Korean copy
where affected. Native window and installed-runtime checks remain separate.

Only regenerate a design report or snapshot after reviewing an intentional
change. Do not increase raw-color allowances, pixel tolerances or skip coverage
to hide a failure. Do not add another Playwright installation under `frontend`.
