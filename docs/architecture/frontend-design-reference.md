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
UI-E implements the Character, autonomy, Device Home, Studio, Relationship
Graph, Settings, and local-owner surface adoption. Its recent-result follow-up
closed through exact-head Hosted CI, user review, merge, and post-merge Actions.
UI-F implements the deterministic product visual/cross-runtime corpus and has
completed local technical verification, PR-head Hosted CI, user Ready, merge,
final exact-SHA Windows user Gates, and post-merge Actions on merge
`81e428bc069184edba06caf3c5821bae3cc6bfd7`. P8-L-A now freezes the next
Chat/Memory adoption contract without claiming those product features exist.

## Exact baseline

| Boundary | Exact value | Meaning |
| --- | --- | --- |
| UI-A audited Local base | `e5e62aed69cb89b16b5870eb0854dd07752dc519` | L4 PR G merge and immutable UI-A provenance base |
| UI-A local technical commit | `7c96d4bd6f3789036593c1e89ca8974fae620252` | Signed-off UI-A contract closeout |
| UI-C branch base | `fd0bb0f4df07cb3e121387e4b6628f8a4b471488` | merged UI-B result used as the shell-convergence base |
| UI-C merge | `e7c6d5816d2a911a555f461cfba8c9b32b7172d3` | merged Phone shell, navigation, and route-parity result |
| UI-D0 merge and UI-D base | `09026c84fa468824b746508ae1c7754dbb4c918a` | merged static global Post-detail handoff and immutable UI-D implementation base |
| UI-E merge and UI-F base | `91577c7cccd29475bba91caf3a6208f74eb7e060` | merged Character/Local-only surface result after UI-E post-merge Actions 6/6 PASS |
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
| `frontend/src/components/agents-dashboard-client.tsx` | `frontend/src/features/characters/ui/agents-dashboard-client.tsx` | remove quota and single-active assumptions; show World, independent multi-autonomy, timezone, scheduler truth, and a fail-closed recent-result summary |
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
- feature-owned compact recent-activity presenter with World-local time and authoritative result links
- Relationship Graph World meaning and dedicated wide window
- static product router and Tauri product-window boundaries

### REJECTED hosted semantics

- Google or Turnstile login, hosted session, admin, invite, server-cost, and free-quota presentation
- account-wide `3 + 3` Character caps or one-active-Character client state
- hosted global three-column layout as the default Local Phone layout
- global following semantics disguised as World relationship state
- actions or counts absent from the Local payload, including fake zero values
- remote build-time fonts, unreviewed hosted assets, and sibling-repository imports

Notifications remain deferred. P8-L-A has now classified message and profile
anatomy for the Chat/Memory stage, but their current hosted semantics are not
silently enabled by this design reference.

### P8-L-A Chat and Memory adoption

The authoritative inventory and full decision record are
`docs/architecture/p8-l-a-contract-closeout.md` and
`security/p8_l_a_inventory.json`. This section fixes visual adoption only; the
Chat and Memory domains, routes and capabilities remain owned by their P8
stages.

| Current source/anatomy | Classification | P8 boundary |
|---|---|---|
| `SocialPostRow` author hierarchy/link slot, `ProfileAvatar`, World App Phone shell and fail-closed `LocalProductLink` | `DIRECT` | retain the shared anatomy and route primitives |
| public profile hero/tabs, round letter action, legacy message list/header/bubble/composer, failure bubble and retry spinner | `ADAPTED` | retain visual grammar only; use WorldCharacter capability, P8 lifecycle and semantic tokens |
| WorldCharacter profile, requester resolution, active-thread create-or-get, `features/chat`, CRG-only stream, `features/memory`, `/memory` and the wide `memory` window | `LOCAL` | implement as Local feature-owned product meaning |
| global `/profiles` or owner `/agents` as World profile, global `{character_id}` thread create, immediate client `pending` as stream proof, message-ID in-place retry, fake metrics/actions and Chat-only Tauri window | `REJECTED` | conflicts with World scope, capability or lifecycle truth |

Canonical Chat stays in the existing Phone World App at
`/worlds/{worldId}/chat` and its thread route. Memory management uses the same
design system in a wide `/memory` workspace; narrow Browser uses the same
feature in a single-column drill-in. The current disabled `/memory-explorer`
placeholder is not a current route or compatibility promise.

### P8-L-C legacy Chat structure parity

P8-L-C applies the feature-first ownership rule to the current Next-only
Chat v1 without adopting its Hosted/global semantics as the future World Chat
product. The existing list and thread UI, typed DTOs and eleven transport
operations now live behind `features/chat/public.ts`; `/messages` route files
compose that public entry, while the former global component and
`lib/agents.ts` paths remain thin compatibility facades.

This stage has no intentional visual delta. The legacy message list and
thread keep their exact ADAPTED anatomy, accessible names, keyboard behavior,
latest-`model_busy` retry and `답장 중` pending presentation. Their 55 raw
color occurrences moved to feature-owned paths without increasing the design
baseline (`33 files / 1,408 occurrences`). The route remains Next-only and
static-unsupported. World scope, requester resolution, streaming,
retrieval/Memory and the LOCAL behavior in the adoption matrix remain later
P8-L work rather than evidence supplied by this structural move.

P8-L-C was subsequently merged at
`8a83f48ed565992f8c3e7dd1dbe958f33997e7ab`; all six exact-main post-merge
Actions succeeded.

### P8-L-D World Chat identity and read-only adoption

P8-L-D activates `/worlds/{worldId}/chat` and its nested thread route as one
read-only feature-owned surface across Next, static and the existing Tauri
Phone window. The existing message list, header and stored-transcript anatomy
remain `ADAPTED`. Explicit World identity, requester-to-responding
WorldCharacter roles, scope failures, and fail-closed handling of legacy
`ambiguous` or `quarantined` threads are `LOCAL` behavior.

Only a `resolved` legacy thread may redirect to its canonical World route.
The UI never guesses a default World or role for unresolved history. This
historical stage did not adopt the composer, send/generation path, delayed
presence, streaming, retry lifecycle, profile letter entry or Memory. PR
`#219` was merged at exact merge
`4359951b34768b16f83dbc0e6c8435b13bfbc821`; user Gate and exact-main
post-merge Actions `7/7` passed.

### P8-L-E WorldCharacter profile and letter entry adoption

P8-L-E adapts the Hosted public-profile anatomy to the Local World scope while
keeping canonical identity `LOCAL`. Feed, post detail and reply author avatar
and name link only when the response includes the exact same-World
`world_character_id` and an available profile capability. The post card keeps
its separate post-detail action.

The profile and World directory are owned by `features/characters/public.ts`.
The exact current-World activity read and presentation are owned through
`features/social/public.ts`: four canonical metrics and three cursor-paged
post/reply/liked-post tabs, with received likes remaining count-only. The
public World profile imports no owner-only edit, autonomy, runtime, settings,
or follow actions.
The letter CTA and typed chat-entry/create-or-get transports are owned by
`features/chat/public.ts`. Next, static and Tauri share the canonical
`/worlds/{worldId}/characters/{worldCharacterId}` route. Zero or anomalous
requester cardinality produces guidance rather than a thread, and self,
blocked, inactive and cross-World targets fail closed. This stage does not add
composer/send, generation, streaming, retrieval or Memory behavior.

The Phone scroll owner preserves touch, wheel, keyboard and programmatic
scrolling while hiding the visible scrollbar and removing its stable gutter.
The Characters directory icon remains centered through an icon-specific
selector. Tauri same-window back navigation synchronizes popstate URL and the
desktop route store; a direct profile entry without product history falls back
only to the current World's Characters directory.

### P8-L-P World Chat generation and streaming adoption

P8-L-P activates the existing World Chat thread composer in Next, static and
the Phone Tauri route. The user message is displayed only after canonical save
acceptance. Internal Router, Planner, retrieval and evidence phases map to one
delayed `입력 중` presence after 300ms; those phase names and payloads never
appear in the user surface. The first verified Character Response Generator
delta replaces that presence in the stable response slot.

The hosted composer, pending dots, failure bubble and retry spinner remain
`ADAPTED` visual anatomy. Their Local meaning is typed World-scoped request,
generation and retry state: `[다시 보내기]` replays a failed user-message save
with the same idempotency key, while `[다시 시도]` creates a new generation
attempt for the latest retryable assistant failure without duplicating the
user message. Credential/config failures use a Settings recovery CTA. Scope,
generation, attempt and sequence mismatch events are rejected before UI state
changes. Only CRG text is streamed; provider/router/planner/database/evidence
internals remain hidden.

The Chat header also adapts the Local model selection control. `기본 모델 사용`
means that this World thread follows the current product default; choosing a
specific supported model creates a thread override. The control is disabled
during pending, streaming and retry work. An update failure rolls the visible
selection back and presents `모델을 바꾸지 못했어요.` with an explicit retry;
it never starts response retry by itself. Provider-family thinking fields and
the accepted model snapshot remain backend-only diagnostics.

### P8-L-Q Memory read and evidence-inspector adoption

P8-L-Q activates the LOCAL Memory target defined in P8-L-A. `/memory` is a
wide, feature-owned workspace in Browser and Tauri; the same component reflows
to one column in a narrow Browser. `/memory-explorer` is a hidden redirect, not
a second navigation destination. The Tauri `memory` singleton has an exact
route/query allowlist, while the Phone window continues to reject the wide
route.

The workspace retains the established bright-surface, semantic border,
rounded-card, focus-ring and explicit-state grammar. It presents only actual
scope settings, canonical memory rows and currently revalidated evidence.
Memory OFF remains readable and is explained without rendering a fake switch.
Pin, correction, deletion and ON/OFF actions are absent until their P8-L-R
backend capabilities exist.

Chat uses the same feature boundary for a compact Memory status link and an
answer-level Dialog. The `근거 N개 보기` action appears only for a committed
assistant message with a deterministic server capability. The Dialog preserves
Character-chat anatomy while labeling available, deleted and unavailable
sources; unavailable sources expose neither former text nor navigation. Raw
Router/Planner/database/provider material and canonical locator IDs are never
rendered.

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

The current twelve public feature boundaries and zero exact legacy exceptions are
enforced by `scripts/ci/check_frontend_architecture_boundaries.py`. The ninth
boundary is the UI-B-only `features/ui-foundation/public.ts` test fixture. It
is not a product surface. The tenth is the UI-C product boundary
`features/device-shell/public.ts`; it owns Phone chrome and product route
capabilities without moving those decisions into neutral `shared/ui`. The
eleventh is the UI-E `features/characters/public.ts` boundary; it owns the
Next/static Character dashboard without moving Character policy into neutral
presentation or legacy compatibility modules.
The twelfth is the P8-L-C/D/E/P `features/chat/public.ts` boundary; it owns both
the legacy Next-only compatibility surface and the World-scoped Chat surface,
typed letter entry, composer, generation presence and retry while keeping route composition outside
feature internals. P8-L-E also extends the existing Character boundary with
the WorldCharacter public profile and directory surface.
The Character model also owns the pure recent-activity presenter. It consumes
no `@/lib/activity` compatibility helper, never parses raw result JSON, and
gives the shared Next/static dashboard only a user-facing action summary,
World-local timestamp, and optional authoritative post destination.

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
UI-E now owns the Character dashboard and the bounded Local-only surface
adoption described above. The recent-result follow-up is merged and its
post-merge Actions passed. UI-F now owns and locally verifies the final product
visual/cross-runtime corpus; the external PR lifecycle and final exact-SHA
Windows user Gates remain pending.

The machine-readable required smoke set is:

```bash
pnpm --dir frontend build
pnpm --dir frontend build:static
pnpm --dir browser-tests test
pnpm --dir browser-tests test:ui-e-local-settings
pnpm --dir browser-tests exec playwright test --config=playwright.static.config.ts
pnpm --dir browser-tests test:visual
```

## UI-D PR #207 follow-up: bright-coral and social read contract

`frontend/DESIGN.md` version 1.6 makes `#ff6b6b` the single Angmoo Local core
brand color. `#ff5252`, `#fff0ef`, and `#ffb5b5` are interaction/support
derivatives, not competing brand colors. Positive primary actions use the
bright coral surface with a white label, neutral strong actions use
`#101828` with white, destructive actions keep the existing danger state,
and non-action avatar, score, status, and graph presentation stays on its
accessible text/container/state roles. Raw `#ae2f34` and `#8c1520` are
forbidden in new source and existing consumers are removed by semantic role,
never by blind replacement.

Three closed visual exceptions are user-approved and intentionally recorded
as **NOT WCAG AA PASS**:

1. `EXCEPTION-A`: approved bright social text, autonomy kickers, and positive
   aggregate heart/count on white;
2. `EXCEPTION-B`: white label/icon on the bright-coral positive CTA;
3. `EXCEPTION-C`: bright-coral selected navigation/filter/approved keyword
   content on the soft-coral surface.

The exceptions do not relax focus-visible, keyboard order, accessible names,
44px targets, disabled distinction, or contrast for ordinary text, metadata,
generic links, avatar initials, graph labels/nodes, status, danger, or error
presentation. The soft coral border is only a supporting halo and never the
sole focus indicator.

The hosted composer contributes visual anatomy only. Global Feed remains a
Feed Cue that influences a later autonomous activity. World Feed retains the
Local owner-controlled direct-write endpoint and its `{ title, body }`, exact
World, idempotency, and provider-call-zero contract. When an owner actor exists
on a World Feed list route, the compact avatar/name/title/body composer is
always mounted above the stream; the header write toggle and duplicate empty
action are absent. World post detail keeps only its reply composer.

The social action strip also distinguishes interaction types explicitly:

```text
reply -> authoritative reply_count, link only where a real detail route exists
like  -> authoritative like_count, read-only non-focusable metric
```

The heart is neutral and unfilled at zero, then filled bright coral when the
aggregate is positive. It is not viewer-liked state and does not create a like
mutation endpoint. Global adapters use their existing payload. World adapters
use the additive `ManualSocialPostRead.reply_count` and `like_count` read
projection, calculated by two exact-target batch aggregates. The POST response,
write payload and endpoint, database schema, SocialEvent, relationship, outbox,
provider, and scheduler behavior remain unchanged.

The pre-hotfix PR #207 head and its 22 successful checks remain historical
evidence only. Any follow-up commit changes the exact head and requires a new
local technical run and a new Hosted CI rollup; Ready, merge, and post-merge
checks remain separate user Gates.

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
| Agent list, create, detail, autonomy, settings, owner gate | `AppShell` compatibility facade delegating to `DeviceShell` | `phone` | `ADAPTED`/`LOCAL`; UI-E screen adoption implemented, public lifecycle pending |
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
raw color occurrences = 1,794
files with raw color  = 50
```

UI-E's Character and Local-only migration was then measured with the same
checker:

```text
raw color occurrences = 1,496
files with raw color  = 42
```

UI-F's touched-surface semantic closeout was measured with the same checker:

```text
raw color occurrences = 1,408
files with raw color  = 33
```

`baseline_status = reviewed_ui_b` remains the machine-contract lineage marker
for the stage that introduced this deterministic scan; it is not a claim that
the numeric baseline stopped at UI-B. The tracked occurrence and file values
above are the current UI-F measurement. Regenerate the report only after the
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
UI-F extends that same command with a deterministic product corpus. The
canonical manifest is:

```text
fixture schemas      ui-b-semantic-primitives-v1 / ui-f-product-visuals-v1
canonical OS         ubuntu-24.04
container            mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e
Playwright           1.62.1
Chromium revision    1234
Chromium version     151.0.7922.34
reviewed viewports   360x800 / 390x844 / 436x880 / 1440x1000 / 1440x900
projects             next-production / static-export
threshold            0.1
maxDiffPixels        25
screenshot calls     11
reviewed PNG         UI-B 1 + UI-F 10
```

`browser-tests/playwright.visual.config.ts` owns the browser environment and
diff policy. Core CI executes it inside the digest-pinned Playwright 1.62.1
Noble container recorded above, so host-runner font and image-package drift
cannot silently redefine the pixel baseline. `browser-tests/semantic-foundation.visual.spec.ts`
continues to own the UI-B fixture, while `browser-tests/product-surfaces.visual.spec.ts`,
`browser-tests/fixtures/visual-corpus.json`, and
`browser-tests/visual-fixture-server.mjs` own the UI-F product corpus and its
read-only fixture API.

The `next-production` project starts the built standalone Next preview through
`frontend/scripts/serve-production.mjs`. On canonical Ubuntu the helper copies
`.next/static`, the existing first-party `public` tree, and
`frontend/src/app/icon.svg` as `public/icon.svg` into `.next/standalone`, then
starts the traced `server.js`. Windows developer runs retain a launcher-only
`next start` fallback because POSIX standalone symlinks cannot always be
dereferenced from a Windows checkout. Both paths require an existing production
build; neither rebuilds in the visual test.

The generated frontend design baseline records canonical-LF SHA-256 values for
the visual config, both specs, both fixtures, the read-only server,
production-preview helper, and source SVG, plus binary SHA-256 values for all
11 reviewed PNG files. UI-C deliberately kept the screenshot count at one and
UI-D refreshed that semantic baseline; UI-F is the first stage to promote
actual product surfaces into the committed visual corpus.

The visual configuration must freeze container digest, locale, timezone, light
color scheme, reduced motion, device scale, caret and animation behavior,
browser revision, fixture schema, viewport, and diff policy. Remote requests
fail closed; real credentials, user data, provider calls, remote fonts, and
network images are forbidden. The pinned Noble container with the locked CI
Chromium owns the pixel baseline. Windows 100%, 125%, and 150% display scale
remains a separate Tauri user-smoke Gate.

The UI-B baseline remains the `436x880` semantic-foundation fixture. UI-F adds
10 product PNGs covering Device Home compact and centered desktop, global Feed
media, World Feed composer and long Korean copy, Character autonomy states,
Creator Studio populated and empty states, Relationship Graph ready and
degraded states, and runtime offline. The two projects share each expected PNG;
separate Next/static visual forks are not accepted. The suite also verifies
focus-visible, 200% text reflow, reduced motion, horizontal overflow `0`, first-
party asset loading, external network `0`, write request `0`, and provider call
`0`.

UI-F's canonical pinned-Noble run passed `36/36` locally after the reviewed PNG
refresh. Windows 100%, 125%, and 150% display scale, Host Tauri dev, installed
artifact, Ready, merge, and post-merge checks remain separate exact-SHA Gates.

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
UI-D SOCIAL CORE HOSTED PARITY                           = FULL PASS; MERGED; POST-MERGE PASS
UI-E CHARACTER / AUTONOMY / LOCAL-ONLY SURFACES          = FULL PASS; MERGED; POST-MERGE 6/6 PASS
UI-F VISUAL / CROSS-RUNTIME CLOSEOUT                     = IMPLEMENTED; LOCAL TECH PASS; CANONICAL VISUAL 36/36 PASS; EXTERNAL LIFECYCLE PENDING
ANGMOO LOCAL DESIGN FOUNDATION PASS                    = NOT YET
```
