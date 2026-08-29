<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

<!-- BEGIN:angmoo-frontend-design-contract -->
# Angmoo frontend design and ownership contract

This block is maintained by Angmoo and must stay outside the generated Next.js
rules above.

Before changing user-visible frontend code, read:

1. `frontend/DESIGN.md`
2. `docs/architecture/frontend-design-reference.md`
3. `docs/architecture/frontend-product-shell.md`

Apply these repository rules:

- Record hosted-reference use as `DIRECT`, `ADAPTED`, `LOCAL`, or `REJECTED`.
- Keep route wrappers thin and import migrated features through
  `@/features/<feature>/public`.
- Put only product-neutral presentation in `shared`; do not move World,
  authorization, runtime, or capability decisions into a shared primitive.
- Reuse one feature component across Next and the static/Tauri router. Do not
  create a Tauri-only visual implementation.
- Expose only payload-backed actions, counts, routes, and states. Never render
  a fake zero or a clickable unsupported static route for visual parity.
- Prefer semantic tokens and existing shared primitives. A changed surface
  must not increase the tracked raw-color baseline.
- Do not add remote build-time fonts, unreviewed assets, sibling-checkout
  imports, hosted auth/quota/admin semantics, or account-wide single-active
  assumptions.
- Keep backend, API, schema, scheduler, provider, World scope, and ownership
  semantics outside a visual PR unless separately planned and approved.

Run at least:

```bash
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
```

Add build, static build, browser behavior, visual, Tauri, and user evidence in
proportion to the changed surface and the current L4.5 stage.
<!-- END:angmoo-frontend-design-contract -->
