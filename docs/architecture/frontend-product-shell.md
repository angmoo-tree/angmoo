# Frontend product-shell boundaries

> **Architecture refactor, 2026-09-05:** The target is described in [ARCHITECTURE](../../frontend/ARCHITECTURE.md). This document continues to describe the unmigrated code. The `refactor` section in the architecture policy activates new rules only for listed scopes; it is empty during AR-1 preparation. See [feature preservation](refactor-feature-preservation.md) for baseline, consumer mapping and validation. Existing public/layer rules below apply outside migrated scopes.

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
| `features/characters/public.ts` | Local owner Character list, autonomy presentation, mutation state and time/result summary | shared Phone route for Next and static/Tauri |
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
and accessibility closeout. UI-F's deterministic product corpus is now
implemented and locally verified; its external lifecycle and final exact-SHA
Windows user checks remain pending.

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

## L4.5 UI-E Character and Local-only boundary

UI-E moves the Local owner Character dashboard behind
`features/characters/public.ts`. Both the Next `/agents` wrapper and the
static/Tauri product router consume that one public entry. The feature owns its
typed read/mutation client, autonomy presentation state, per-Character pending
mutation state, and the flat Character-row UI. The former
`components/agents-dashboard-client.tsx` path is only a compatibility export;
new route composition must not import it.

The dashboard deliberately keeps three concepts separate:

- a Character's saved ON/OFF setting;
- scheduler state such as running, scheduled, resting, or failed;
- external-control mode, which is not presented as a Local runtime-health
  category.

Turning one Character off changes only that Character's endpoint and local
pending state. It never disables another active Character or reintroduces an
account-wide single-active rule. Active hours are shown with their explicit
timezone, while stored API instants are normalized as UTC and formatted in the
World timezone for next-activity and recent-result presentation.

The compact recent-result presentation is owned by
`features/characters/model/character-recent-activity-presentation.ts`. It is a
pure allowlist over action type, timestamp, and authoritative
`target_post_id`; it never parses or returns `AgentActivityLog.result`.
Unknown or malformed action types fail closed to generic Korean copy. A
malformed or long raw result is ignored, so a known action still uses its safe
allowlisted summary; absent recent activity is distinguished from a historical timestamp. The dashboard
renders the result as one full-span bounded row with a World-local `<time>` and
an optional `LocalProductLink`. The same component and route source are used in
Next and static/Tauri, so JSON metadata, internal IDs, and unsupported
destinations cannot leak through an adapter-specific fallback.

UI-E does not turn a public or World Feed author into an owner-management
destination. `/agents/{characterId}` remains a Local owner surface with
management capability; a public profile remains a separate, capability-gated
route. The World Feed therefore must not link every author to `/agents` merely
for visual parity.

The other UI-E Local surfaces retain their existing feature ownership:

- `features/device-home` distinguishes World launchability from runtime state
  and never exposes an unavailable World as a link;
- `features/runtime-status` preserves starting, ready, degraded, failed,
  recovery-required, stopping, and stopped meanings instead of flattening
  them into one badge;
- `features/creator-studio` keeps the versioned World-local leave sequence and
  exact confirmation copy, without deleting the global Character or preserved
  activity/relationship evidence;
- `features/relationships` distinguishes ready, empty, degraded, rebuilding,
  unavailable, and failed, and never presents canonical fallback data as a
  healthy LadybugDB projection.

This boundary closes behavior and state vocabulary. UI-F now implements the
fixed-viewport product corpus, cross-runtime screenshot parity, zoom, focus,
and reduced-motion checks. Exact-SHA Windows display-scale, Host Tauri,
installer, user Ready, merge, and post-merge closeout remain separate Gates.

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

## L4.5 UI-D social presentation boundary

`features/social/public.ts` exports the product-neutral
`SocialPostPresentation`, `SocialPostActionPresentation`, and shared
`SocialPostRow`. Global Feed, global Post detail, World Feed, World-scoped
detail, and World reply presentation consume that public boundary instead of
maintaining route-specific card anatomy.

Presentation never grants capability. Adapters provide handle, avatar, media,
action, and count only when the canonical payload and route capability own the
value; omitted data stays omitted instead of becoming a fake zero or disabled
hosted action. Global Feed and Post detail retain the global `/feed` and
`/posts/{postId}/thread` endpoints. World Feed, detail, and reply use only
`/worlds/{worldId}/manual-social/**` and verify the exact World, owner actor,
root Post, reply parent, and provider-free write result before rendering a
success. The shared row cannot authorize endpoint fallback or scope mixing.

The UI-D0 async boundary remains composition-owned. Static
`/posts/{postId}` waits until the final thread or error is known, rejects stale
responses, and remounts detail state by Post identity. UI-D changes the child
presentation without weakening that ready Gate.

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
24.04, Chromium revision 1234 (`151.0.7922.34`), projects `next-production`
and `static-export`, threshold `0.1`, and `maxDiffPixels=25`. UI-F preserves the
UI-B `436x880` semantic fixture and expands the same manifest to five reviewed
viewport sizes and 10 product PNGs, for exactly 11 screenshot calls and 11
committed expected images. Core CI runs the pixel Gate in that container rather
than inheriting mutable host-runner font packages.

UI-C kept that screenshot count at one. Its shell Gate is behavior-driven:
Next and static suites check one Phone frame and one scroll owner, current-route
bottom navigation, no hosted desktop rails, zero horizontal overflow at the
reviewed Phone widths, centered Phone behavior on a wide Browser, wide
Relationship Graph separation, static direct-open coverage, and legacy Studio
alias canonicalization. Static behavior also proves inner-owner Feed
pagination and that hosted-only profile links are not clickable. UI-F now
adds the expanded product screenshot and state corpus without creating a
second Playwright dependency graph.

UI-D's paired Next and static/Tauri World scenarios cover compact composition,
flat rows, keyboard and text-selection-safe post navigation, exact World detail
routes, provider-free scoped replies, long text, forbidden, missing, service,
scope-mismatch, and retry states. The static suite additionally covers
authenticated media 0/1/2/3/4+, top-level and nested global replies, and hidden
unsupported actions. UI-D0 separately retains the global delayed-response,
offline, keyboard-open, and post-identity regressions. The implementation owns
explicit loading and empty states, while the expanded cross-runtime state and
visual corpus remains UI-F scope. The suites also assert zero fallback from
World social adapters to global endpoints. UI-F adds nested global reply
link/keyboard assertions and keeps unsupported like/repost/follow/share actions
hidden; these behavior tests and product screenshots still do not replace the
final Windows display-scale and installed exact-SHA user Gates.

The `next-production` visual project launches the already-built standalone
output through `frontend/scripts/serve-production.mjs`. On canonical Ubuntu the
helper assembles the traced runtime by copying `.next/static`, the first-party
`public` directory, and `frontend/src/app/icon.svg` as `/icon.svg` before
starting `.next/standalone/server.js`. The static-export project serves the
existing static build. The fixture requires `/icon.svg` to load successfully in
both projects, so the visual Gate covers the same first-party asset contract
without a remote image or a second frontend implementation.

UI-F's `ui-f-product-visuals-v1` fixture is stored in
`browser-tests/fixtures/visual-corpus.json` and served by the read-only
`browser-tests/visual-fixture-server.mjs`. It fixes time, locale, timezone,
light mode, DPR, reduced motion, owner, Worlds, long Korean Feed data,
Character autonomy states, Studio groups, graph projection states, and runtime
health. Any write, provider-shaped call, or external network request fails the
test. The corpus covers `360x800`, `390x844`, `436x880`, `1440x1000`, and
`1440x900`; Next production and static export share each expected image rather
than maintaining runtime-specific baselines.

The pinned-Noble local canonical run passed `36/36`. UI-F also reduced a static
composition fork by routing Feed reads through `features/social/public.ts`, and
its source inventory now records 27 legacy candidate-consumer edges instead of
28. UI-F subsequently completed Issue, PR-head Hosted CI, user Ready, merge,
exact-SHA Windows/installer Gates, and post-merge Actions on exact merge
`81e428bc069184edba06caf3c5821bae3cc6bfd7`.

## P8-L-A Chat and Memory product boundary

P8-L-A freezes an inventory and target contract; it does not make Chat or
Memory available. The current `/worlds/{worldId}/chat` path already reaches the
same Next/static `WorldApp` Phone shell and is accepted by the Rust Phone
allowlist, but its section is deliberately `unavailable`. Legacy `/messages`
and `/messages/{threadId}` remain Next-only wrappers over legacy components.
There is no `features/chat`, `features/memory`, WorldCharacter profile route,
generation stream, or Memory window at the audited baseline.

The P8 target stays feature-first:

```text
World App route wrapper
  -> features/chat/public
  -> feature-owned API/model/UI

World social author or features/characters profile
  -> features/chat/public entry capability only

Memory route/window composition
  -> features/memory/public
```

No route, profile or social feature may deep-import Chat internals. Chat may
use the Memory public facade for owner-management entry and evidence
presentation, but it does not own Memory lifecycle policy. Shared UI retains
only product-neutral avatar, button, dialog, live-region, status and feedback
primitives.

The canonical routes and windows are:

| Surface | Browser/static route | Tauri window |
|---|---|---|
| World Chat list | `/worlds/{worldId}/chat` | existing `phone`/`main` |
| World Chat thread | `/worlds/{worldId}/chat/{threadId}` | existing `phone`/`main` |
| WorldCharacter profile | `/worlds/{worldId}/characters/{worldCharacterId}` | existing `phone`/`main` |
| owner Memory workspace | `/memory` | new wide `memory` singleton |

The current disabled Device Home `/memory-explorer` placeholder is not a
shipped route and is not implementation evidence. P8 may retain it only as a
hidden compatibility redirect to `/memory` after the real feature exists.
Phone Chat uses a Dialog for quick evidence inspection; list, filter, pin,
correction and deletion belong to the wide Memory workspace.

World social DTOs must retain `world_id + author_world_character_id` through
presentation. A profile link or letter CTA is rendered only when the backend
returns the corresponding capability; unsupported runtimes keep the identity
inert. Global `/profiles`, owner-management `/agents`, and global
`{character_id}` message creation are not fallbacks. The requester candidate
contract is 0 = setup guidance, 1 = automatic resolve, N = anomaly and no
thread. Active-thread create-or-get must remain idempotent under double click,
replay and concurrency.

Legacy message/profile visual anatomy is adoption evidence, not behavior
parity. Avatar/row/World shell primitives are DIRECT; profile, letter,
transcript, composer, failure bubble and retry spinner are ADAPTED; World
identity, requester resolution, generation lifecycle, CRG-only stream and
Memory workspace are LOCAL. Immediate client `pending` as stream proof,
message-ID in-place retry, fake counts/actions, a Chat-only Tauri window, and
automatic use of the clicked post as evidence are REJECTED.

P8 later adds exact Next/static/Rust route tests, unauthenticated Chat return,
profile-to-Chat/back restoration, delayed single presence, stream/reconnect,
typed retry and Memory window parity. Until those tests and backend
capabilities exist, the current unavailable/disabled states remain truthful.
The full machine-verifiable baseline and decisions live in
`docs/architecture/p8-l-a-contract-closeout.md` and
`security/p8_l_a_inventory.json`.

## P8-L-C legacy Chat feature boundary

P8-L-C moves the existing Next-only Chat v1 frontend behind a feature-first
public boundary without changing its product behavior. The canonical owner is
now:

```text
frontend/src/features/chat/
  api/chat-client.ts
  model/chat-contract.ts
  ui/messages-client.tsx
  ui/message-thread-client.tsx
  public.ts
```

Both `app/messages/page.tsx` and `app/messages/[threadId]/page.tsx` remain
thin Next route wrappers and import Chat only through
`@/features/chat/public`. The former global component paths are one-line
compatibility facades, and the message exports in `lib/agents.ts` are
compatibility re-exports. New consumers use the feature public boundary;
Chat internals do not import `@/components` or `@/lib` and no Chat-specific
policy moved into `shared`.

This stage deliberately preserves the eleven existing Chat v1 transport
operations, request bodies, 401 behavior, thread/model state, optimistic send,
latest-`model_busy` retry, deletion navigation, keyboard handling, accessible
names, `답장 중` pending anatomy, and exact visual classes. The design baseline
therefore moves 39 and 16 raw-color occurrences to the two feature-owned UI
paths while the repository total remains 1,408 occurrences across 33 files.
There is no intentional screenshot or visual result change.

Legacy `/messages` stays `next: supported` and `static: unsupported` in the
reviewed route matrix. This structural parity is not evidence for
World-scoped thread identity, `/worlds/{worldId}/chat` activation, requester
resolution, generation streaming, typed retry, retrieval, Memory, a new
schema/provider flow, or static/Tauri Chat support. Those capabilities remain
owned by the later P8-L stages.

P8-L-C was merged at
`8a83f48ed565992f8c3e7dd1dbe958f33997e7ab` and its six exact-main
post-merge Actions succeeded.

## P8-L-D World-scoped read-only Chat boundary

P8-L-D adds a canonical read-only list and thread detail to the existing
Phone World App without creating a Chat-only window:

| Surface | Next/static route | Tauri Phone route result |
|---|---|---|
| World Chat list | `/worlds/{worldId}/chat` | same list and World scope |
| World Chat thread | `/worlds/{worldId}/chat/{threadId}` | same nested detail and role binding |

Both route families compose `features/chat/public.ts`. The static parser
recognizes the nested thread before the generic World section, and the Rust
Phone allowlist accepts the same canonical paths. A thread is rendered only
when its response matches the requested `world_id`, requester is
`owner_controlled`, requester and responding WorldCharacter IDs differ, and
every returned message belongs to that thread.

The list/header/stored-transcript anatomy is adapted from legacy Chat. World
scope, explicit requester-to-responding direction, and fail-closed errors are
Local semantics. A resolved legacy `/messages/{threadId}` may redirect to the
canonical World thread; `ambiguous` and `quarantined` history stays on the
legacy surface with a no-guess warning.

This historical stage deliberately had no profile/letter entry, requester picker,
composer/send, generation, streaming, delayed typing presence, typed retry or
Memory behavior. It was merged as PR `#219` at exact merge
`4359951b34768b16f83dbc0e6c8435b13bfbc821`; user Gate and all seven
post-merge Actions passed.

## P8-L-E World social author profile and letter entry boundary

P8-L-E activates `/worlds/{worldId}/characters/{worldCharacterId}` across Next,
static and the existing Tauri Phone window. `features/characters/public.ts`
owns the identity profile contract, transport and shell. `features/social/public.ts`
owns the exact current-World activity client and presentation: four metrics
and three cursor-paged tabs, with received likes remaining count-only. It does
not mix another World or invent Hosted follower/activity data, and it does not
expose owner-only profile, autonomy, runtime, settings or follow actions.

World social rows keep three separate interaction targets: the card opens post
detail, while the author avatar and name open the exact WorldCharacter profile.
An absent or unavailable `author_profile_capability` leaves author identity
inert. The letter CTA calls `features/chat/public.ts`, resolves the local owner
requester as zero/one/anomaly, and exposes P8-L-D's idempotent active-thread
create-or-get only for the valid one-requester case. Self, blocked, inactive and
cross-World targets fail closed. This E slice still has no message send,
generation, streaming, retrieval or Memory behavior.

The shared Phone scroll owner keeps real scrolling but hides the scrollbar and
removes reserved gutter space. The Characters directory header keeps its icon
centered by separating icon and metadata selectors. Same-window Tauri history
stores a product-route index and synchronizes popstate URL back into the desktop
route store before static routing. The WorldCharacter profile back button thus
returns to the actual Feed or Characters origin; direct entry without prior
product history uses the current World's Characters directory as its bounded
fallback.

## P8-L-P World Chat response surface

P8-L-P builds on the P8-L-D/E World identity and entry routes without adding a
Chat-only Tauri window. `/worlds/{worldId}/chat/{threadId}` now owns a
feature-first composer, canonical-send acceptance, one stable assistant
response slot, 300ms delayed `입력 중` presence, verified CRG text deltas,
typed failure and explicit retry. Next, static and Tauri use the same
`features/chat` model, API and UI implementation.

The frontend accepts only `chat-generation-stream.v1` NDJSON events whose
request scope, generation, attempt and monotonic sequence match the active
request. `delta` has exactly one `text` field. Internal retrieval states do not
create separate indicators. A committed terminal is hydrated from the server
without automatic regeneration; late old-generation output is ignored.

Message-save recovery and assistant-response recovery are deliberately
separate. The former keeps draft content and its idempotency key for `다시
보내기`; the latter reuses the canonical user message and response slot while
requesting a new generation for `다시 시도`. Non-retryable credential or
configuration failures expose an allowed Settings CTA instead of a misleading
retry. Memory owner/read surfaces remain P8-L-Q/R scope.

The same `features/chat` boundary owns the World-scoped thread model selector.
Its two durable meanings are `기본 모델 사용`, which follows the current Local
product setting, and a fixed thread override. The selected and default model
come from the thread read contract rather than browser storage. The selector is
disabled while a message, generation, stream or retry is active; a failed model
PATCH restores the previous value and exposes a bounded retry surface. Changing
the model after a failed answer does not implicitly regenerate that answer.
Next, static and Tauri therefore share one binding, rollback and busy-state
contract.

## P8-L-Q Memory read surface and answer evidence

P8-L-Q activates `features/memory/public.ts` as the sole feature-first Memory
presentation boundary. The Next `/memory` page and static product router both
compose the same `MemoryWorkspace`; `/memory-explorer` is only a hidden
compatibility redirect. The wide Tauri singleton uses window kind `memory` and
accepts exactly `/memory` with ordered scope dependencies (`subject` requires
`world`; `memory` requires `subject`). The Phone allowlist rejects the wide
route, while a narrow Browser reflows the same workspace to one column.

The workspace selects only launchable owner Worlds and active WorldCharacters,
then reads setting, bounded list, item lifecycle and currently revalidated
provenance. A requested scope that is absent never falls back to a different
World or Character. OFF means no new memory accumulation; it does not hide
stored items. Loading, no-scope, empty, forbidden/not-found, transport failure,
expired/superseded/deleted and unavailable evidence have explicit surfaces.
There are no ON/OFF, pin, correction or delete controls before P8-L-R.

World Chat composes `MemoryScopeSummary` and `WorldChatEvidenceInspector`
through the Memory public boundary. A committed assistant message gets a
`근거 N개 보기` action only from the server's deterministic capability/count
summary. The Phone Dialog then loads the current safe evidence view. Stale,
deleted or unvalidated evidence never displays its frozen excerpt or link;
source IDs, revisions, locators, raw query/prompt and provider details do not
enter the frontend contract. Viewing Memory or evidence performs GET requests
only and does not invoke a model or change Memory state.

## P8-L-R Memory owner control

P8-L-R keeps `features/memory/public.ts` as the sole feature-first Memory
boundary and adds explicit owner actions to the same `MemoryWorkspace` used by
Next, static and the wide Tauri Memory window. The setting control shows saved
ON/OFF state; item detail exposes pin/unpin, correction and delete. Existing
items remain visible and manageable while OFF, but correction is disabled
until Memory is ON because it creates a new canonical replacement.

Only one owner mutation may be pending in a workspace. Each request carries
the selected owner+World+subject scope, expected version and an idempotency key.
Transient failures preserve the same request for explicit retry; version
conflicts discard the stale request and reload current canonical state.
Correction and delete use shared accessible confirmation Dialogs, and success
opens the replacement or removes the deleted item without cross-scope
fallback. Projection cleanup is automatic after commit and is not presented as
a second owner action.

The wide Tauri surface stays multi-column while Browser widths at 799px and
below reflow the same controls and Dialogs into one column. Provider calls,
raw query/prompt text, canonical IDs and projection internals remain outside
the UI contract. Installed-runtime user proof and final causal closeout remain
P8-L-S.

## P8-L-R additional Today SNS activity context

L2.5 Today SNS context is backend-owned working context, not another product
destination. The existing features/memory inspector accepts today_sns_activity
and labels it “오늘 SNS 활동”, distinct from “저장된 기억”. Memory OFF copy
permits current-thread and today's World SNS facts while learned memory
read/write behavior remains unchanged. The same workspace and inspector run
in Next, static and Tauri; normal generation still shows only “입력 중”.
Stale source/ancestor revisions hide old evidence excerpts and links. Raw
snapshot, query, source ID, provider state and private counterpart motive are
not presented. See p8-l-r-today-sns-activity.md for the source and generation
contract; installed causal proof remains a separate user Gate.

## P8-L-R Memory batch settings and whole-app closing

The same Memory workspace adds saved opt-in AI selection, installation-level
model choice and per-WorldCharacter daily `HH:mm`/exit flags. World timezone,
next due, pending count, completion and attention/retry are server-owned.
Memory ON is distinct from paid source-excerpt consent. One mutation lock,
scope/version/idempotency and stale-response guards cover the new controls.
No new navigation destination or Hosted-specific credential surface is added.

Only the native whole-app exit workflow shows the shared `끄는 중…` Dialog.
Its `지금 종료` action abandons bounded Memory preparation; backdrop/Escape do
not undo native shutdown. Child-window close and browser navigation do not
trigger it. Keyboard focus, status announcement and reachable actions use the
existing Dialog primitives. Source/projection/provider details remain hidden.
See [the runtime contract](p8-l-r-memory-batch.md) for recovery and separate Gates.
