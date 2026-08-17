# Frontend product-shell boundaries

This document is the contributor-facing architecture contract for the L2.5
Angmoo product shell. It is incremental: existing SNS, chat, profile, and
creator routes remain in their legacy locations until a reviewed migration PR
moves one surface at a time.

## Product surfaces

| Public feature | Responsibility | Shell |
| --- | --- | --- |
| `features/device-home/public.ts` | Local device entry and app grid | phone-like `DeviceFrame` |
| `features/creator-studio/public.ts` | World creation and management workspace | wide desktop shell |
| `features/world-app/public.ts` | One explicit `world_id` runtime surface | phone-like `DeviceFrame` |
| `features/runtime-status/public.ts` | Secret-free aggregate status presentation | shared status badge |

`shared/ui` contains presentation primitives only. It must not decide World
visibility, owner authorization, runtime health, or feature availability.
`shared/navigation` contains stable route builders without fetching data or
choosing a World.

## Import rules

1. A route composition root imports a feature through
   `@/features/<feature>/public`.
2. A feature imports another feature only through that feature's `public.ts`.
3. A shared primitive never imports a product feature, legacy component, or
   data client.
4. New feature code does not import legacy `@/components` or `@/lib` paths
   unless an exact, owned, time-bounded exception is recorded in
   `security/frontend_architecture_policy.json`.
5. Legacy route files that have not migrated remain allowed. The policy does
   not pretend the whole frontend is already domain-first.

Run the boundary locally with:

```bash
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
```

## Incremental behavior boundary

- PR A established the public feature, shared UI, route-builder, and import
  boundaries without switching a live route.
- PR B made Device Home the canonical `/` route and added the owner-scoped,
  read-only World surface. The legacy global Feed remains available at
  `/posts`.
- PR C adds `/worlds/{world_id}` and the explicit
  `feed|chat|characters|relationships` World routes. Every entry performs an
  owner-session and active-membership read through
  `GET /api/v1/worlds/mine/{world_id}` before rendering World data. Missing,
  archived, private, draft, foreign, or permission-lost Worlds fail closed and
  never fall back to another World.

PR C does not claim that a World-scoped Feed, Chat, Character list, or
Relationship entry is already implemented. Those tabs retain the selected
`world_id` but render a truthful unavailable state. In particular, `/posts`
continues to mean the existing global community Feed and must never be labeled
or embedded as a World Feed.

Creator Studio wiring and optional PWA behavior remain later L2.5 PRs.

## Visual contract

Device Home and World App share a thin, uniform, flat frame. The initial tokens
are a 436 px maximum device width, 3 px bezel, and 34 px outer corner radius.
The values are a product contract snapshot, not a Samsung asset or runtime
dependency. App entries use a consistent squircle grid; Creator Studio leaves
the device frame and uses a wide workspace.
