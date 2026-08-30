# L4.5 frontend design reference and provenance

This document is the public, clean-clone companion to
[`frontend/DESIGN.md`](../../frontend/DESIGN.md). It records the evidence used
by **L4.5 UI-A — Design contract, reference, and provenance closeout** and the
machine-readable foundation introduced by **L4.5 UI-B — Semantic token and
primitive foundation** without making a sibling checkout, a private source
tree, or the hosted service a runtime or build dependency.

UI-A establishes the contract and inventory. It does not restyle pages, change
an API, or claim that the current UI already conforms to the design contract.
UI-B adds a Local-owned semantic source, shared primitives, limited real
consumer adoption, and one deterministic test fixture. UI-C adds the
feature-owned Phone shell, capability-driven navigation, and route/window
parity contract. UI-D0 closes static global Post-detail handoff, and UI-D adds
one feature-owned social presentation across global and World-scoped adapters.
UI-E and UI-F still own Local-only surface adoption and the final
visual/cross-runtime closeout.

## Exact baseline

| Boundary | Exact value | Meaning |
| --- | --- | --- |
| UI-A audited Local base | `e5e62aed69cb89b16b5870eb0854dd07752dc519` | L4 PR G merge and immutable UI-A provenance base |
| UI-A local technical commit | `7c96d4bd6f3789036593c1e89ca8974fae620252` | Signed-off UI-A contract closeout |
| UI-C branch base | `fd0bb0f4df07cb3e121387e4b6628f8a4b471488` | merged UI-B result used as the shell-convergence base |
| UI-C merge | `e7c6d5816d2a911a555f461cfba8c9b32b7172d3` | merged Phone shell, navigation, and route-parity result |
| UI-D0 merge and UI-D base | `09026c84fa468824b746508ae1c7754dbb4c918a` | merged static global Post-detail handoff and immutable UI-D implementation base |
| Hosted visual reference | `jingujeon/angmoo@7f967abd6117381be5c081ed284addb889b06fec` | Immutable social-UI audit snapshot |
| Latest shared first-party history | `637426d8f2245311d6c5cb4ca52bcfc8103cca25` | Hosted and Local already share the audited frontend ancestry through this commit |
| Local GPL transition | `b95ffe2c59e02d97f2047791c4959c1494b9ee35` | Current application license boundary |
| Legacy design reference | revision `887ea5ff673f827851e8623a186541f10d0126e6`, blob `a31db8b2f83755cc0c71a5318ff2df1adb09e0ef` | Opaque historical, audit-only input; not distributed |

The hosted reference is Apache-2.0 at the recorded snapshot, while the current
Local repository is GPL-3.0-only. The visual files audited for UI-A are not a
new import: they descend from first-party history already shared by the two
repositories before the Local GPL transition. UI-A copies no post-common
hosted source, asset, icon, or font, so it introduces no new bundled Apache
component and does not add an Apache notice.

Any future attempt to copy source that exists only after the shared-history
commit is a new provenance decision. That PR must stop before copying, record
the exact source blob, and close the license-policy and notice question. A
`DIRECT` or `ADAPTED` label is a design-adoption classification, not permission
to copy code without that review.

The historical design reference has no asserted distribution license and is
not shipped. It contributed only audit questions such as palette, typography,
shape, and spacing. The Local design contract is a newly written repository
artifact and the clean clone needs only this repository to understand it.

## DIRECT / ADAPTED / LOCAL / REJECTED

The machine-readable source and target records, including hosted Git blob OIDs,
are in [`security/frontend_design_policy.json`](../../security/frontend_design_policy.json).
The classification applies to the stated visual scope, not automatically to an
entire mixed-purpose source file.

### DIRECT visual anatomy

| Hosted source at the reference commit | Local-owned target | Adopted scope |
| --- | --- | --- |
| `frontend/src/components/post-list-client.tsx` | `frontend/src/features/social/ui/post-list-client.tsx` | flat post row, type hierarchy, media, action rhythm |
| `frontend/src/components/post-list-client.tsx` | `frontend/src/features/social/ui/social-post-row.tsx` and `social-presentation.module.css` | shared flat row, author hierarchy, explicit action rhythm, and accessible row navigation |
| `frontend/src/components/post-detail-client.tsx` | `frontend/src/components/post-detail-client.tsx` | original post, reply hierarchy, back header |
| `frontend/src/components/profile-avatar.tsx` | `frontend/src/shared/ui/profile-avatar.tsx` | round avatar and deterministic fallback |
| `frontend/src/components/expandable-post-text.tsx` | `frontend/src/features/social/ui/expandable-post-text.tsx` | clamp and explicit expansion |
| `frontend/src/components/mentioned-text.tsx` | `frontend/src/features/social/ui/mentioned-text.tsx` | mention presentation |
| `frontend/src/lib/post-card-navigation.ts` | `frontend/src/features/social/model/post-card-navigation.ts` | accessible row navigation |
| `frontend/src/lib/use-mobile-pull-to-refresh.ts` | `frontend/src/shared/interaction/use-mobile-pull-to-refresh.ts` | touch refresh interaction |

### ADAPTED visual grammar

| Hosted source | Local-owned target | Required adaptation |
| --- | --- | --- |
| `frontend/src/components/app-shell.tsx` | current shell, then shared Device shell | keep visual chrome; remove hosted global/account routing assumptions |
| `frontend/src/components/agents-dashboard-client.tsx` | Local Character dashboard | remove quota and single-active assumptions; show World and scheduler truth |
| `frontend/src/components/character-profile-client.tsx` | Local profile | expose only real Local chat, World, activity, graph, or management capabilities |
| `frontend/src/components/post-list-client.tsx` composer and tabs | `frontend/src/features/social/ui/world-social-feed.tsx` | preserve owner-controlled World write and real World scopes |
| `frontend/src/components/post-media-grid.tsx` | `frontend/src/features/social/ui/post-media-grid.tsx` | preserve hosted frame anatomy while using authenticated Local media URLs and payload-backed 0/1/2/3/4+ layout without remote fallback |

### LOCAL product surfaces

- Device Home and its runtime entry state
- World App and World-scoped navigation
- owner-controlled World social write adapters
- payload-backed optional social presentation and capability contracts
- Creator Studio, Character create/link/leave, and World Package surfaces
- autonomy schedule, next-run, provider, and scheduler state
- Relationship Graph World meaning and dedicated wide window
- static product router and Tauri product-window boundaries

### REJECTED hosted semantics

- Google or Turnstile login, hosted session, admin, invite, server-cost, and free-quota presentation
- account-wide `3 + 3` Character caps or one-active-Character client state
- hosted global three-column layout as the default Local Phone layout
- global following semantics disguised as World relationship state
- actions or counts absent from the Local payload, including fake zero values
- remote build-time fonts, unreviewed hosted assets, and sibling-repository imports

Notifications, messages, and profile anatomy may be reconsidered in their
own product stages. Their current hosted semantics are not silently enabled by
this design reference.

## Feature-first ownership contract

The existing feature-first boundary remains authoritative:

```text
app route wrapper
  -> features/<feature>/public
  -> feature-owned api/model/ui

shared/ui
  -> product-neutral presentation only
  -> never imports a feature, app route, legacy component, or data client
```

The current ten public feature boundaries and zero exact legacy exceptions are
enforced by `scripts/ci/check_frontend_architecture_boundaries.py`. The ninth
boundary is the UI-B-only `features/ui-foundation/public.ts` test fixture. It
is not a product surface. The tenth is the UI-C product boundary
`features/device-shell/public.ts`; it owns Phone chrome and product route
capabilities without moving those decisions into neutral `shared/ui`.

## UI-B semantic foundation

The machine-readable contract is the `semantic_foundation` object in
[`security/frontend_design_policy.json`](../../security/frontend_design_policy.json).
Its canonical implementation paths are:

| Role | Repository-owned path |
| --- | --- |
| semantic token source | `frontend/src/shared/ui/semantic-tokens.css` |
| global Tailwind/CSS entry | `frontend/src/app/globals.css` |
| shared public export | `frontend/src/shared/ui/public.ts` |
| deterministic fixture | `frontend/src/features/ui-foundation/ui/semantic-foundation-fixture.tsx` |
| fixture feature boundary | `frontend/src/features/ui-foundation/public.ts` |
| noindex Next wrapper | `frontend/src/app/ui-foundation/page.tsx` |
| static fixture composition | `frontend/src/composition/static-product-router.tsx` |

The token source owns the canonical color, type, spacing, radius, elevation,
focus, and motion values. Shared consumers import `Avatar`, `Button`, form,
surface, status, navigation, dialog, and feedback primitives through
`@/shared/ui/public`; they do not deep-import implementation files. Required
token and export markers are checked from the policy so deleting or bypassing
the source of truth fails the deterministic contract.

UI-B directly adopts the new component API in two existing product consumers:

- `frontend/src/features/world-packages/world-package-export-panel.tsx`;
- `frontend/src/features/world-packages/world-package-import-client.tsx`.

Two compatibility bridges also compose new primitives behind existing public
exports and therefore affect a broader, pre-existing consumer graph:

| Compatibility adapter | New primitive | Existing public contract | Impact |
| --- | --- | --- | --- |
| `frontend/src/shared/ui/profile-avatar.tsx` | `Avatar` | `ProfileAvatar` | Existing profile/avatar call sites receive the new primitive transitively |
| `frontend/src/shared/ui/status-badge.tsx` | `StatusChip` | `StatusBadge` | Existing runtime/status call sites receive the new primitive transitively |

These adapters are tracked and hashed separately from the two direct World
Package consumers. They preserve their existing public names and product
semantics; they do not make every downstream surface a direct UI-B adoption.

The fixture is evidence, not a third direct product consumer. Its schema is
`ui-b-semantic-primitives-v1`. `/ui-foundation` is an unlinked, noindex test
harness rendered by the same feature component in Next production and the
static export. It is excluded from the product route/surface inventory and
must not appear in Device navigation. This route does not close any UI-C route
gap by itself or authorize another product route.

The fixture's `BottomNavigation` items are button-only state controls. They
exercise selection, horizontal visibility, touch, and `aria-current` without
claiming that any `href` is a supported product destination. Actual route href
wiring and capability-driven navigation are implemented by UI-C's
`features/device-shell` boundary.

`globals.css` imports the semantic source globally. Transitional aliases remap
existing legacy utilities, and the two compatibility bridges propagate
`Avatar` and `StatusChip` into existing call sites, even though only the two
World Package consumers directly adopt the new component API in UI-B. The
existing Next/static product-shell behavior smoke therefore covers both global
alias and compatibility-bridge impact in addition to the fixture tests. This
transitional reach is not evidence that untouched pages conform to the design
contract. UI-D now owns the shared social row and endpoint-isolated adapters;
UI-E and UI-F remain pending after that bounded adoption.

The machine-readable required smoke set is:

```bash
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests test
pnpm --dir browser-tests exec playwright test --config=playwright.static.config.ts
pnpm --dir browser-tests test:visual
```

## Route and surface inventory

The complete deterministic Next route and route-handler inventory remains
[`docs/architecture/next-static-compatibility.json`](next-static-compatibility.json).
UI-A adds a reviewed product-surface matrix in
`security/frontend_design_policy.json` so route existence is not confused with
Phone, wide-window, or static-host support.

Current canonical surface families:

| Surface | Current product shell | Expected window | Adoption |
| --- | --- | --- | --- |
| Device Home | `DeviceShell` composed from `DeviceFrame` | `phone` | `LOCAL` |
| World Home, Feed, Chat, Characters, Relationships | `DeviceShell` composed from `DeviceFrame` | `phone` | `LOCAL` adapter plus shared UI-D social presentation |
| Feed and Post detail compatibility routes | `AppShell` compatibility facade delegating to `DeviceShell` | `phone` | `DIRECT`/`ADAPTED`; UI-D social presentation adopted |
| Agent list, create, detail, autonomy, settings, owner gate | `AppShell` compatibility facade delegating to `DeviceShell` | `phone` | `ADAPTED`/`LOCAL`; screen adoption remains UI-E |
| Creator Studio | dedicated wide shell | `studio` | `LOCAL` |
| Relationship Graph | dedicated `RelationshipGraphFrame` | `relationship-graph` | `LOCAL` |

### UI-C route-gap closeout

UI-A recorded five route gaps. UI-C closes them in code and functional
contract coverage:

1. The Rust Phone allowlist accepts `/agents`.
2. It also accepts `/worlds/{worldId}/posts/{postId}`, while `safe_world_id`
   prevents the reserved `new` segment from becoming a dynamic World ID.
3. The static direct-open list covers `/studio/import` and `/agents`.
4. `AppShell` exposes only the capability-driven Local bottom destinations;
   Next-only search, notifications, messages, profiles, tree, licenses, and
   API-guide routes remain explicitly hidden. `LocalProductLink` also turns
   any such destination inside shared Feed or Character presentation into an
   inert static/Tauri label instead of a clickable not-found route.
5. `/worlds/new` and `/worlds/{worldId}/creator` canonicalize to their Studio
   destinations before product-window classification, preserving single,
   repeated, and empty query values in both Next and static runtimes.

The Phone content region is the sole scroll owner. Feed and Character-profile
pagination plus pull-to-refresh resolve it first, while shell-less compatibility
routes retain the previous `window` fallback. Static Feed waits for its initial
sidecar read before mounting the stateful Feed client so the first page and its
cursor cannot be discarded during hydration.

`features/device-shell/model/device-navigation.ts` chooses one explicit
capability for every reviewed destination:

```text
A. Next and static both implemented
B. hidden from Phone navigation
C. explicit disabled or unavailable entry
D. validated external Browser destination
```

The machine-readable `known_route_gaps` list is therefore empty and the three
previously under-tested route families now read
`declared_and_direct_open_tested`. This shell-level closeout does not replace
UI-F's full route/state/runtime visual matrix or Windows installer user Gate.

## Raw-color baseline

UI-A freezes one exact scan definition rather than treating similar regex
results as interchangeable:

```regex
#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{5}|[0-9A-Fa-f]{3}|[0-9A-Fa-f])?\b
```

Scope: sorted `frontend/src` files with the `.css`, `.ts`, or `.tsx`
extension. The word boundary intentionally excludes SVG fragment references
such as `url(#beak)`.

UI-A audit baseline:

```text
raw color occurrences = 1,938
files with raw color  = 59
```

UI-B reviewed baseline:

```text
raw color occurrences = 1,894
files with raw color  = 56
baseline status       = reviewed_ui_b
```

UI-C's shell migration was then measured with the same checker:

```text
raw color occurrences = 1,860
files with raw color  = 53
```

UI-D's bounded Social-core migration was measured with that same checker:

```text
raw color occurrences = 1,796
files with raw color  = 50
```

`baseline_status = reviewed_ui_b` remains the machine-contract lineage marker
for the stage that introduced this deterministic scan; it is not a claim that
the numeric baseline stopped at UI-B. The tracked occurrence and file values
above are the current UI-D measurement. Regenerate the report only after the
source settles, and change the values only to the checker-measured result.
Never guess the count or update it merely to hide growth.

The per-extension, per-file, and per-value result is tracked in
[`frontend-design-baseline.json`](frontend-design-baseline.json). Regenerate or
check it from a clean clone with:

```bash
uv run --project backend python scripts/ci/check_frontend_design_contract.py --write
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

UI-A does not bulk-recolor the tree. UI-B and later PRs must keep new raw-color
growth at zero, migrate touched consumers to semantic roles, and intentionally
lower the tracked baseline when debt is removed.

## Visual harness extension

`browser-tests` is the only browser-test dependency graph. It pins
`@playwright/test` 1.62.1 in both its package and lockfile and currently owns:

- `playwright.config.ts` plus `product-shell.spec.ts` for Next behavior;
- `playwright.static.config.ts` plus `static-product-shell.spec.ts` for static
  direct-open, Tauri-like route, window, and interaction behavior.

UI-B activates the reserved `test:visual` command in the existing
`browser-tests/package.json`; it does not add Playwright under `frontend`.
The canonical manifest is:

```text
fixture schema       ui-b-semantic-primitives-v1
canonical OS         ubuntu-24.04
container            mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e
Playwright           1.62.1
Chromium revision    1234
Chromium version     151.0.7922.34
reviewed viewport    436x880
projects             next-production / static-export
threshold            0.1
maxDiffPixels        25
screenshot calls     1
reviewed PNG         browser-tests/snapshots/ui-b/semantic-foundation-phone.png
```

`browser-tests/playwright.visual.config.ts` owns the browser environment and
diff policy. Core CI executes it inside the digest-pinned Playwright 1.62.1
Noble container recorded above, so host-runner font and image-package drift
cannot silently redefine the pixel baseline. `browser-tests/semantic-foundation.visual.spec.ts`
owns the fixture schema, interaction/accessibility checks, `/icon.svg` load
assertion in both projects, and the single screenshot call.

The `next-production` project starts the built standalone Next preview through
`frontend/scripts/serve-production.mjs`. On canonical Ubuntu the helper copies
`.next/static`, the existing first-party `public` tree, and
`frontend/src/app/icon.svg` as `public/icon.svg` into `.next/standalone`, then
starts the traced `server.js`. Windows developer runs retain a launcher-only
`next start` fallback because POSIX standalone symlinks cannot always be
dereferenced from a Windows checkout. Both paths require an existing production
build; neither rebuilds in the visual test.

The generated frontend design baseline records canonical-LF SHA-256 values for
the visual config, spec, fixture, production-preview helper, and source SVG,
plus a binary SHA-256 for the reviewed, committed UI-B PNG. UI-C deliberately
keeps the screenshot call and PNG count at one; its additional shell evidence
is functional route, viewport, overflow, navigation, and window-kind coverage.

The visual configuration must freeze container digest, locale, timezone, light
color scheme, reduced motion, device scale, caret and animation behavior,
browser revision, fixture schema, viewport, and diff policy. Remote requests
fail closed; real credentials, user data, provider calls, remote fonts, and
network images are forbidden. The pinned Noble container with the locked CI
Chromium owns the pixel baseline. Windows 100%, 125%, and 150% display scale
remains a separate Tauri user-smoke Gate.

UI-B reviews only the `436x880` semantic-foundation fixture. UI-C adds
functional shell assertions at `360`, `390`, `436`, and desktop Browser widths
plus static inner-scroll pagination and unsupported-route assertions without
promoting them into an early screenshot corpus. Completing the full
route/state/runtime matrix, including the two wide workspaces at `1440x900`,
belongs to UI-F.

## Asset and font provenance

UI-A adds no asset, font, dependency, or copied icon. UI-B likewise adds no
remote or bundled font and no copied hosted asset. Its fixture uses existing
Local PWA artwork and the already-licensed Lucide dependency.

- The application icon and favicon already descend from first-party shared
  history and remain covered by the current application and brand policy.
- The three PWA PNG files remain registered deterministic first-party
  derivatives.
- Lucide is consumed as the existing ISC-licensed dependency; Feather's MIT
  notice is already present where used.
- There is no `next/font`, `@font-face`, bundled font file, Google Fonts import,
  or remote font dependency.
- The historical Quicksand suggestion is rejected unless a future PR
  separately self-hosts a rights-cleared font and proves Korean fallback and
  offline behavior.

Hosted screenshots and user-generated feed media are evidence, not repository
assets. Future visual fixtures must be synthetic or independently
rights-cleared.

## Contributor workflow

Before changing user-visible frontend code:

1. read `frontend/DESIGN.md` and this inventory;
2. identify the feature owner and Phone or wide product surface;
3. record `DIRECT`, `ADAPTED`, `LOCAL`, or `REJECTED` for hosted reference use;
4. reuse a shared primitive only when it is product-neutral and has a real
   consumer;
5. preserve the same feature component across Next and static wrappers;
6. record raw-color, route, accessibility, fixed-viewport, and provenance
   evidence in the pull request;
7. run both frontend architecture and design-contract checkers.

Until the final raw-color values, reviewed PNG, generated manifest, and local
commands are all closed, this branch permits this status only:

```text
UI-A DESIGN CONTRACT / REFERENCE / PROVENANCE CLOSEOUT = PASS
UI-B SEMANTIC TOKEN / PRIMITIVE FOUNDATION             = PASS
UI-C PHONE SHELL / NAVIGATION / ROUTE PARITY            = PASS; MERGED; POST-MERGE PASS
UI-D0 STATIC POST DETAIL ASYNC HANDOFF                   = FULL PASS; MERGED; POST-MERGE PASS
UI-D SOCIAL CORE HOSTED PARITY                           = LOCAL TECH PASS; PUBLIC LIFECYCLE PENDING
UI-E through UI-F                                      = NOT STARTED
ANGMOO LOCAL DESIGN FOUNDATION PASS                    = NOT YET
```
