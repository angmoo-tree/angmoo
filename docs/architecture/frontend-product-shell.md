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
| `features/social/public.ts` | Feed read composition, social DTO entry and shared post-list UI | Next route and static/Tauri router |

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
- PR C added `/worlds/{world_id}` and the explicit
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

PR D makes `/studio` the canonical, local-owner Creator Studio surface. Its
dashboard reads `surface=creator_studio`, groups owner-managed Worlds without
provider calls or public writes, and connects existing deterministic World
create, edit, validate, and publish operations behind the wide shell.
`/studio/worlds/new` and `/studio/worlds/{world_id}` are canonical; the legacy
`/worlds/new` and `/worlds/{world_id}/creator` routes only redirect to them.
Draft, private, and archived Worlds remain Studio-only while a published,
publish-ready public or unlisted World becomes eligible for Device Home and the
World App. Import remains a truthful unavailable capability until L3.5.

L4 PR B establishes `features/social/public.ts` as the frontend Feed entry.
`feed-page.tsx` is now a thin composition adapter and both the Next route and
the static/Tauri product router render the same `PostListClient` exported by
that public boundary. The large existing Feed UI was moved intact rather than
forked, so this ownership change does not alter route, write, or visual
behavior.

The moved client still consumes exact legacy component and `lib/community`
edges. Each edge is recorded in `security/frontend_architecture_policy.json`
with its L4 PR C or PR F removal condition. This is a reviewed progressive
migration, not a blanket exception: unlisted `features/social -> components`
or `features/social -> lib` imports fail CI, stale exceptions fail CI, route
and composition imports must use `features/social/public.ts`, and no Tauri-only
social UI fork is permitted.

L4 PR C moves the World Feed composer/thread UI, its owner-write DTOs and its
typed write client under `features/social`. `features/world-app` now composes
that feature only through `features/social/public.ts`; it no longer owns a
second social client or the post/reply UI. The general Feed DTO and the list,
following, delete and report calls also moved out of `lib/community`, removing
the three PR-C-owned legacy import exceptions while leaving the unrelated
presentation edges for PR F.

The World Feed keeps a pending idempotency key across a retryable SQLite busy
response. An unchanged post or reply is retried with the same key and cannot
be duplicated; editing the payload creates a new logical request. The typed
`sqlite_busy_retry_exhausted` state tells the user that another activity is
being saved and that the same request can be retried. Browser, static/Tauri and
Windows Host Tauri dev all use this one feature implementation.

The optional PWA shell is implemented as a standards-based manifest plus a
cache-free service worker lifecycle. It only changes the browser chrome:

- ordinary browser use remains the complete default experience;
- standalone launch starts at the canonical Device Home and keeps the same
  local owner session, SQLite data, and routes;
- Creator Studio still leaves the phone frame for its wide workspace;
- the service worker has no fetch handler, Cache API use, offline response
  store, background write queue, or API/auth/credential persistence;
- service-worker script responses are not cached, and registration explicitly
  checks for updates while unregister remains available for recovery.

PWA installation never creates a second owner, database, or runtime.
The three bundled PWA PNG files are deterministic raster derivatives of the
project-owned `frontend/src/app/icon.svg`: 192px and 512px general icons plus a
512px maskable icon with an expanded Angmoo color safe area. No third-party
icon or remote build asset is introduced.

## L3 owner-controlled World actor

Creator Studio now contains the Local Owner's minimum World identity editor.
It requires a display name, an HTTP(S) avatar URL, and a one-line introduction;
World role, preferred address, interests, and World-local background remain
optional. The feature calls the owner-scoped WorldCharacter API only and does
not start BYOK setup, enable autonomy, or create a social write.

The World App reads the same identity and presents it as the current manual
actor with `automatic activity OFF`. A missing identity is an explicit Studio
setup state, not a fallback to another World or autonomous Character. Manual
Post and Comment controls remain unavailable until the separately reviewed L3
PR G author-guard contract is implemented.

## Visual contract

Device Home and World App share a thin, uniform, flat frame. The initial tokens
are a 436 px maximum device width, 3 px bezel, and 34 px outer corner radius.
The values are a product contract snapshot, not a Samsung asset or runtime
dependency. App entries use a consistent squircle grid; Creator Studio leaves
the device frame and uses a wide workspace.

## Browser regression Gate

Core CI runs the isolated Playwright Chromium suite in `browser-tests`. It protects the
canonical Home route, 390 px and wide-browser device layouts, keyboard-visible
app links, zero and multiple World states, Creator Studio grouping, explicit
World routing with no fallback, degraded runtime presentation, and the
standalone cache-free PWA contract. Backend requests are fulfilled with
synthetic owner-scoped fixtures; any browser write or provider-shaped request
fails the audit. These tests complement the backend authorization contract and
do not replace the Windows clean-clone or final user visual Gate.
