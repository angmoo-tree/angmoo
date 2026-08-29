# Frontend product-shell boundaries

This document is the contributor-facing architecture contract for the L2.5
Angmoo product shell. It is incremental: existing SNS, chat, profile, and
creator routes remain in their legacy locations until a reviewed migration PR
moves one surface at a time.

## Product surfaces

The canonical visual and interaction vocabulary is
[`frontend/DESIGN.md`](../../frontend/DESIGN.md). Its portable UI-A evidence,
adoption matrix, provenance, raw-color baseline, route gaps, and visual-harness
plan are recorded in
[`frontend-design-reference.md`](frontend-design-reference.md). This document
continues to own dependency direction and product-shell boundaries; the design
contract cannot override World, authorization, capability, or Tauri window
meaning.

| Public feature | Responsibility | Shell |
| --- | --- | --- |
| `features/device-home/public.ts` | Local device entry and app grid | phone-like `DeviceFrame` |
| `features/device-shell/public.ts` | Local Phone chrome, capability-driven bottom navigation, safe-area and scroll ownership | one product-owned `DeviceShell` composed from neutral `DeviceFrame` |
| `features/creator-studio/public.ts` | World creation and management workspace | wide desktop shell |
| `features/world-app/public.ts` | One explicit `world_id` runtime surface | phone-like `DeviceFrame` |
| `features/runtime-status/public.ts` | Secret-free aggregate status presentation | shared status badge |
| `features/social/public.ts` | Feed read composition, social DTO entry and shared post-list UI | Next route and static/Tauri router |
| `features/relationships/public.ts` | Relationship graph API, typed projection state and shared graph UI | Next route and Tauri wide window |
| `features/ui-foundation/public.ts` | UI-B deterministic semantic-token and primitive fixture only | unlinked noindex Next wrapper and static test composition; not product navigation |

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
6. A visual reference is classified per adopted scope as `DIRECT`, `ADAPTED`,
   `LOCAL`, or `REJECTED`; that classification never creates a sibling
   repository dependency or bypasses source, asset, font, and license review.
7. Next and static/Tauri route wrappers render the same feature component.
   UI-C's explicit Local route matrix is the only source for Phone bottom
   navigation; a Next-only route stays hidden instead of becoming a broken
   installed-product link.

Run the boundary locally with:

```bash
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

## L4.5 UI-A design boundary

UI-A tracks `frontend/DESIGN.md`, the file-level hosted/Local adoption matrix,
shared-history and license evidence, the current route/surface and screenshot
inventory, and one deterministic raw-color report. It intentionally changes no
page visuals or backend contract. The static composition adapter still has
legacy component imports; UI-A froze the then-current Phone route gaps in
`security/frontend_design_policy.json` rather than hiding them behind a new
exception. UI-C later closes those five recorded gaps explicitly.

The existing `browser-tests` package remains the sole Playwright graph. UI-B
adds the first reviewed screenshot consumer there; UI-A records a truthful
zero-screenshot baseline and does not create a second harness.

## L4.5 UI-B semantic foundation boundary

UI-B establishes `frontend/src/shared/ui/semantic-tokens.css` as the Local-owned
semantic source and `frontend/src/shared/ui/public.ts` as the only public
primitive export. The primitives remain product-neutral: they render actions,
fields, surfaces, identity presentation, state, navigation chrome, dialogs,
and feedback, but they do not choose a World, authorize an owner, infer runtime
health, or decide whether a product capability exists.

Direct UI-B product adoption is intentionally limited to the existing World
Package export and import panels. Separately, the existing `ProfileAvatar`
adapter now composes `Avatar`, and the existing `StatusBadge` adapter composes
`StatusChip`. Those compatibility bridges retain their old public contracts
while propagating the new primitive into a broader existing consumer graph;
they are tracked separately and do not turn every downstream call site into a
direct UI-B consumer. The deterministic fixture does not count as a product
consumer.

`globals.css` imports the token source globally and remaps legacy Tailwind
aliases. Untouched surfaces may therefore receive either a global alias change
or a transitive compatibility-bridge change without directly adopting the new
component API. Existing product-shell Browser and static smoke covers both
transitional effects, but neither is whole-frontend design conformance.

The `/ui-foundation` wrapper exists only to render the same
`SemanticFoundationFixture` in Next production and static export. The Next
wrapper declares `robots.index=false` and `robots.follow=false`; no product
navigation links to it. The path is deliberately absent from the product
route/surface inventory. Its static composition entry is test infrastructure,
not an added Device capability, a UI-C route-parity fix, or permission to add
the route to a Rust Phone allowlist.

The fixture's `BottomNavigation` is deliberately button-only. It proves local
selected state, overflow visibility, touch behavior, and `aria-current` without
attaching product-route `href` values. UI-C still owns actual destination
capability, static/Next route parity, and route href wiring.

UI-C owns Device shell, navigation, route capability, and direct-open parity.
UI-D owns social presentation adoption, UI-E owns Character/autonomy and
Local-only surface adoption, and UI-F owns the full viewport, cross-runtime,
and accessibility closeout.

## L4.5 UI-C Phone shell boundary

UI-C establishes three deliberately different layers:

1. `shared/ui/device-frame.tsx` is a product-neutral frame primitive. It owns
   the bounded canvas and the single `data-device-scroll-owner="true"` content
   region, but it does not choose routes or product capabilities. In a Tauri
   Phone window it also reserves the `data-device-titlebar-inset="true"`
   region above page-owned content so native drag, minimize, and close controls
   cannot cover a header action.
2. `features/device-shell/ui/device-shell.tsx` is the Local product shell. It
   decides Browser centering versus full-viewport Phone rendering and composes
   the page-owned optional header with safe-area bottom navigation. It does
   not inject a second generic title above an existing page header.
3. `components/app-shell.tsx` is a compatibility facade for route wrappers that
   have not yet migrated. It delegates chrome to `DeviceShell`; it is no
   longer a second three-column or Tauri-specific shell.

The product navigation matrix is owned by
`features/device-shell/model/device-navigation.ts`. Home, Feed, 내 앵무, and
Settings are the only current bottom destinations because both Next and the
static composition support them. Search, notifications, messages, profiles,
tree, licenses, and the API guide remain explicit Next-only capabilities and
are hidden from the Local Phone instead of being rendered as dead links.
`LocalProductLink` enforces the same fail-closed rule inside shared social and
Character presentation: Next keeps the hosted destination, while static/Tauri
renders an inert label with `role="link"`, `aria-disabled="true"`, unavailable
copy, and non-interactive presentation when its router has no matching product
route.

The `DeviceFrame` content region is the only Phone scroll owner. Feed and
Character-profile pagination plus pull-to-refresh resolve that element first
and retain `window` only as a compatibility fallback for routes without the
Phone shell. Static Feed waits for its initial sidecar read before mounting the
stateful Feed client, so the first successful page and cursor are not lost.

UI-C also closes the reviewed route gaps without changing backend contracts:

- Rust accepts `/agents` and `/worlds/{worldId}/posts/{postId}` only in the
  Phone window, with `new` rejected as a dynamic World ID;
- the static direct-open matrix covers `/studio/import` and `/agents`;
- `/worlds/new` and `/worlds/{worldId}/creator` canonicalize to their Studio
  routes before window classification, preserving single, repeated, and empty
  query values in both Next and static/Tauri;
- Creator Studio and Relationship Graph keep their dedicated wide shells.
- Phone, Creator Studio, and Relationship Graph shells each own exactly one
  `main` landmark; their nested clients render content containers rather than
  a second `main`.
- the native Relationship Graph allowlist accepts the Local canonical
  `ladybug` provider only; legacy `neo4j` query input fails closed.

The Tauri Phone geometry regression measures the native controls and the
`/agents` page-owned `만들기` action at 360, 390, 433, and 436 CSS-pixel widths.
It also clicks the bottom navigation and verifies URL, in-memory product route,
and `aria-current` move together inside the same Phone window.

These are shell and navigation guarantees, not a claim that UI-D social rows,
UI-E Character/Local-only screens, or UI-F's complete visual and accessibility
corpus is finished. UI-C adds functional fixed-viewport assertions and retains
UI-B's single reviewed screenshot rather than creating an early second corpus.

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
World App. L3.5 later added the canonical World Package import surface without
forking the Device Home, browser, static/Tauri, or installed product source.

L4 PR B establishes `features/social/public.ts` as the frontend Feed entry.
`feed-page.tsx` is now a thin composition adapter and both the Next route and
the static/Tauri product router render the same `PostListClient` exported by
that public boundary. The large existing Feed UI was moved intact rather than
forked, so this ownership change does not alter route, write, or visual
behavior.

L4 PR F closes the remaining Social-owned presentation and transport edges.
`features/social` now consumes only its own public surface and canonical
`shared` API, auth, interaction, and UI boundaries; its exact legacy exception
list is empty. The old component and `lib` paths used by unrelated screens are
thin compatibility facades or retain their pre-L4 client contract, while route
and composition imports use `features/social/public.ts`. CI rejects any new
`features/social -> components` or `features/social -> lib` edge and any
Tauri-only social UI fork.

L4 PR G turns Creator Studio's WorldCharacter card from a read-only checkpoint
into a bounded verification-fixture surface. `features/creator-studio` owns the
typed candidate, entry and leave clients plus the UI orchestration; it does not
import legacy `components` or `lib` modules. The same feature renders in Next
browser, static/Tauri, Host Tauri dev and installer paths.

`새 캐릭터 만들기` reuses `/agents/new` with a validated current-World return
context. In that context Character creation uses the existing direct create
contract and deliberately skips credential probe, tendency analysis, public
write and onboarding provider calls. Creator Studio then selects an enabled
autonomous World role (including canonical `no_specific_role`) and invokes the
existing idempotent World entry command. Removal is separately labelled
`이 World에서 제거`, requires the canonical Character confirmation name, stops
the selected autonomy first, and calls the versioned leave command. The copy
states that historical activity and relationship evidence remains and sends
global Character deletion to the existing `내 앵무 관리` surface instead.

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

L4 PR D adds one pure `features/social/model` presentation contract for the
causal state returned by autonomous activity. It distinguishes observation
pending, observation failure, observed `NO_ACTION`, observed follow-up failure
and observed follow-up success. The existing autonomy setup surface consumes
that public contract and does not guess private feelings from a source post or
relationship delta. A failed follow-up is presented as a preserved observation
plus an absent public action, not as a failed or rolled-back observation.

L4 PR E moves the relationship graph transport contract, typed presentation model and client UI
under `features/relationships`. The Next relationship route and static/Tauri
router import only `features/relationships/public.ts`, so Phone navigation and
the Graph wide window render the same component. The model distinguishes
loading, empty, rebuilding, degraded canonical fallback, failed and ready
states; the UI does not collapse a projector replay into an empty graph or a
query failure into a healthy fallback. The old component and `lib` client paths
are deleted rather than re-exported.

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
setup state, not a fallback to another World or autonomous Character. Its
manual Post and Reply controls use `features/social/public.ts` and the canonical
owner-scoped social write API. They neither invoke a provider nor enable
autonomy; the route still revalidates actor ownership and World scope.

## Visual contract

All ordinary Local user routes share the feature-owned `DeviceShell`, which
composes a thin, uniform, flat `DeviceFrame`. The initial tokens
are a 436 px maximum device width, 3 px bezel, and 34 px outer corner radius.
The values are a product contract snapshot, not a Samsung asset or runtime
dependency. App entries use a consistent squircle grid; Creator Studio leaves
the device frame and uses a wide workspace.

UI-B's `436x880` fixture is not a replacement Device shell. It verifies the
shared semantic vocabulary in a bounded Phone canvas. UI-C's real product
shell separately owns the optional page-header slot, safe area, actual route
links, and one scroll model.

## Browser regression Gate

Core CI runs the isolated Playwright Chromium suite in `browser-tests`. It protects the
canonical Home route, 390 px and wide-browser device layouts, keyboard-visible
app links, zero and multiple World states, Creator Studio grouping, explicit
World routing with no fallback, degraded runtime presentation, and the
standalone cache-free PWA contract. Backend requests are fulfilled with
synthetic owner-scoped fixtures; any browser write or provider-shaped request
fails the audit. These tests complement the backend authorization contract and
do not replace the Windows clean-clone or final user visual Gate.

UI-B adds `test:visual` to the same dependency graph. Its canonical pixel
manifest is the digest-pinned Playwright 1.62.1 Noble container on Ubuntu
24.04, Chromium revision 1234 (`151.0.7922.34`), a `436x880` viewport, and
projects `next-production` and `static-export`. Core CI runs the pixel Gate in
that container rather than inheriting mutable host-runner font packages. The
one expected baseline is
`browser-tests/snapshots/ui-b/semantic-foundation-phone.png` with threshold
`0.1` and `maxDiffPixels=25`. This bounded fixture baseline does not close the
UI-F route, viewport, Windows display-scale, Tauri, installer, or exact-SHA
user Gates.

UI-C keeps that screenshot count at one. Its shell Gate is behavior-driven:
Next and static suites check one Phone frame and one scroll owner, current-route
bottom navigation, no hosted desktop rails, zero horizontal overflow at the
reviewed Phone widths, centered Phone behavior on a wide Browser, wide
Relationship Graph separation, static direct-open coverage, and legacy Studio
alias canonicalization. Static behavior also proves inner-owner Feed
pagination and that hosted-only profile links are not clickable. UI-F still
owns the expanded product screenshot and state corpus.

The `next-production` visual project launches the already-built standalone
output through `frontend/scripts/serve-production.mjs`. On canonical Ubuntu the
helper assembles the traced runtime by copying `.next/static`, the first-party
`public` directory, and `frontend/src/app/icon.svg` as `/icon.svg` before
starting `.next/standalone/server.js`. The static-export project serves the
existing static build. The fixture requires `/icon.svg` to load successfully in
both projects, so the visual Gate covers the same first-party asset contract
without a remote image or a second frontend implementation.
