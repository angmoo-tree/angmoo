# L4.5 frontend design reference and provenance

This document is the public, clean-clone companion to
[`frontend/DESIGN.md`](../../frontend/DESIGN.md). It records the evidence used
by **L4.5 UI-A — Design contract, reference, and provenance closeout** without
making a sibling checkout, a private source tree, or the hosted service a
runtime or build dependency.

UI-A establishes the contract and inventory. It does not restyle pages, change
an API, or claim that the current UI already conforms to the design contract.

## Exact baseline

| Boundary | Exact value | Meaning |
| --- | --- | --- |
| Local `main` base | `e5e62aed69cb89b16b5870eb0854dd07752dc519` | L4 PR G merge and UI-A branch base |
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
| `frontend/src/components/post-detail-client.tsx` | `frontend/src/components/post-detail-client.tsx` | original post, reply hierarchy, back header |
| `frontend/src/components/profile-avatar.tsx` | `frontend/src/shared/ui/profile-avatar.tsx` | round avatar and deterministic fallback |
| `frontend/src/components/expandable-post-text.tsx` | `frontend/src/features/social/ui/expandable-post-text.tsx` | clamp and explicit expansion |
| `frontend/src/components/mentioned-text.tsx` | `frontend/src/features/social/ui/mentioned-text.tsx` | mention presentation |
| `frontend/src/components/post-media-grid.tsx` | `frontend/src/features/social/ui/post-media-grid.tsx` | media frame and grid |
| `frontend/src/lib/post-card-navigation.ts` | `frontend/src/features/social/model/post-card-navigation.ts` | accessible row navigation |
| `frontend/src/lib/use-mobile-pull-to-refresh.ts` | `frontend/src/shared/interaction/use-mobile-pull-to-refresh.ts` | touch refresh interaction |

### ADAPTED visual grammar

| Hosted source | Local-owned target | Required adaptation |
| --- | --- | --- |
| `frontend/src/components/app-shell.tsx` | current shell, then shared Device shell | keep visual chrome; remove hosted global/account routing assumptions |
| `frontend/src/components/agents-dashboard-client.tsx` | Local Character dashboard | remove quota and single-active assumptions; show World and scheduler truth |
| `frontend/src/components/character-profile-client.tsx` | Local profile | expose only real Local chat, World, activity, graph, or management capabilities |
| `frontend/src/components/post-list-client.tsx` composer and tabs | `frontend/src/features/social/ui/world-social-feed.tsx` | preserve owner-controlled World write and real World scopes |

### LOCAL product surfaces

- Device Home and its runtime entry state
- World App and World-scoped navigation
- owner-controlled World social write adapters
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

The current eight public feature boundaries and zero exact legacy exceptions
are enforced by `scripts/ci/check_frontend_architecture_boundaries.py`. UI-A
does not refactor page components or the static composition adapter. The
remaining top-level `components`, `lib`, and manual static-router debt is
inventoried for incremental migration; UI-C owns shell and route convergence.

## Route and surface inventory

The complete deterministic Next route and route-handler inventory remains
[`docs/architecture/next-static-compatibility.json`](next-static-compatibility.json).
UI-A adds a reviewed product-surface matrix in
`security/frontend_design_policy.json` so route existence is not confused with
Phone, wide-window, or static-host support.

Current canonical surface families:

| Surface | Current product shell | Expected window | Adoption |
| --- | --- | --- | --- |
| Device Home | `DeviceFrame` Phone | `phone` | `LOCAL` |
| World Home, Feed, Chat, Characters, Relationships | `DeviceFrame` Phone | `phone` | `LOCAL` plus adapted social presentation |
| Feed and Post detail compatibility routes | current `AppShell` | `phone` | `DIRECT`/`ADAPTED`; shell debt remains |
| Agent list, create, detail, autonomy, settings, owner gate | current `AppShell` | `phone` | `ADAPTED`/`LOCAL`; shell debt remains |
| Creator Studio | dedicated wide shell | `studio` | `LOCAL` |
| Relationship Graph | wide product surface | `relationship-graph` | `LOCAL`; dedicated shell convergence remains |

### Reviewed route gaps assigned to UI-C

UI-A records these gaps instead of claiming route parity:

1. The React static router handles `/agents`, but the Rust Phone path allowlist
   does not.
2. The React static router handles
   `/worlds/{worldId}/posts/{postId}`, but the Rust Phone path allowlist does
   not.
3. The static direct-open route list omits `/studio/import` and `/agents` even
   though the React static router handles both.
4. The shared `AppShell` exposes clickable Next-only search, notifications,
   messages, profile, tree, licenses, and API-guide destinations in the static
   profile.
5. `/worlds/new` and `/worlds/{worldId}/creator` are Browser redirect aliases;
   canonical navigation must use their Studio destinations instead of letting
   the static router reinterpret them.

These are current debts, not UI-A regressions. UI-C must choose one explicit
capability for every destination:

```text
A. Next and static both implemented
B. hidden from Phone navigation
C. explicit disabled or unavailable entry
D. validated external Browser destination
```

Until UI-C closes them, the repository may claim that the route inventory was
reviewed, but not `ROUTE PARITY PASS` or `clickable broken static route = 0`.

## Raw-color baseline

UI-A freezes one exact scan definition rather than treating similar regex
results as interchangeable:

```regex
#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{5}|[0-9A-Fa-f]{3}|[0-9A-Fa-f])?\b
```

Scope: sorted `frontend/src` files with the `.css`, `.ts`, or `.tsx`
extension. The word boundary intentionally excludes SVG fragment references
such as `url(#beak)`.

UI-A baseline:

```text
raw color occurrences = 1,938
files with raw color  = 59
```

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

At UI-A closeout the repository intentionally has:

```text
toHaveScreenshot/page.screenshot calls = 0
committed visual snapshot images        = 0
```

UI-B creates the first reviewed screenshot only when a real semantic primitive
consumer exists. At that time the same `browser-tests/package.json` adds the
reserved `test:visual` command, a visual config, deterministic fixtures, and a
baseline manifest. It must not add Playwright under `frontend`.

The visual configuration must freeze locale, timezone, light color scheme,
reduced motion, device scale, caret and animation behavior, browser revision,
fixture schema, viewport, and diff policy. Remote requests fail closed; real
credentials, user data, provider calls, remote fonts, and network images are
forbidden. Ubuntu with the locked CI Chromium owns the pixel baseline. Windows
100%, 125%, and 150% display scale remains a separate Tauri user-smoke Gate.

Planned viewport families are `360x800`, `390x844`, `436x880`, centered Phone
at `1440x1000`, and the two wide workspaces at `1440x900`.

## Asset and font provenance

UI-A adds no asset, font, dependency, or copied icon.

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

UI-A permits this exact status only:

```text
UI-A DESIGN CONTRACT / REFERENCE / PROVENANCE CLOSEOUT = PASS
UI-B through UI-F                                      = NOT STARTED
ANGMOO LOCAL DESIGN FOUNDATION PASS                    = NOT YET
```
