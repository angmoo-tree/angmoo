# Frontend product shell

The shell connects runtime navigation, viewport size and feature composition.
It does not own a second implementation of Feed, Chat, Memory or authorization.
Read [Frontend Architecture](../../frontend/ARCHITECTURE.md) for imports and
[DESIGN](../../frontend/DESIGN.md) for presentation.

## Owners

| Owner | Responsibility |
| --- | --- |
| `composition/shells/product-viewport.tsx` | Shared viewport and native toolbar placement |
| `components/ui/device-frame.tsx` | Neutral frame/scroll presentation |
| `components/layout/device-shell.tsx` | Presentation of the supplied navigation and layout |
| `composition/screens` | Product screen composition and cross-feature slots |
| `composition/shells/world-app-navigation.ts` | World section identity and routes |
| `composition/static-product-router.tsx` | Supported static route dispatch |
| `lib/navigation` | Internal route validation and capability checks |
| `lib/desktop/product-window.ts` | Native kind, current route and approved commands |
| `lib/dom/scroll-viewport.ts` | Discovery of the actual scroll owner |

Paths are relative to `frontend/src`. Common primitives do not import features,
own credentials, resolve a World or decide whether a mutation is authorized.
Composition supplies the relevant state and callbacks.

## Viewport and native windows

Next and static roots use the same `ProductViewport`. It owns `100dvh` and leaves
the remaining height to the body after a native toolbar. Ordinary content uses
a responsive maximum width of 960 CSS px; wide workspaces use the applicable 1440 CSS px
maximum. Do not restore a fixed decorative phone silhouette or use CSS maxima
as native window limits.

Native windows use opaque OS chrome, independent resize, maximize and Snap.
Initial and minimum main dimensions are constrained by the monitor work area,
DPI and real frame insets. `phone` is a logical kind, not a mandatory phone
shape. `main` is a host window label and must not be confused with a route.

`desktopWindowKindForRoute` currently chooses `memory` for `/memory`, `studio`
for Studio routes and `phone` for other supported routes. The retained
`relationship-graph` enum reads older launch metadata; current World relationship
navigation stays in the World screen. Do not create a new wide window merely
because the enum exists.

## Navigation

The native toolbar uses actual URL/history state, not a second route stack.
Consume initial bootstrap metadata once; the real deep URL wins on reload.
Normalize supported aliases before interpreting dynamic IDs. Reject malformed,
unsupported, cross-origin and private-token-bearing routes.

Device Home presents real launchable Worlds and supported tools without its
retired global bottom menu. World navigation retains World, Feed, Chat,
Characters and Relationships. The active route provides one meaningful current
state and stays within the authenticated World.

A link needs a real supported destination in its current runtime. Explicitly
hide an unavailable route or present its supported unavailable state. Do not
make static navigation point to a Next-only dead end. External HTTP(S) links
use the narrow validated command; do not expand native shell or remote access.

Native back, reload and cross-window actions pass through the existing unsaved
input guard. A blocked or failed navigation does not silently erase draft state.
Cross-window transitions preserve the allowed return route and window kind.

## Scroll and screen lifetime

One scroll owner controls a page's history anchoring, pagination, visibility and
pull-to-refresh. The document/window fallback is only for routes without that
owner. Delayed content and callback refs must be observed when they mount.

Chat retains the reader's current anchor on prepend and preserves explicit
bottom intent on resize/IME/media changes. Feed keeps mounted rows and drafts
through partial reads. Neither behavior requires a new shell or provider.

Scope changes remove subscriptions, polling and observers and reject late
responses. UI observation does not own an already accepted server job. Closing
a child window, disconnecting a client and stopping the application have
different lifecycle contracts.

## Local preparation and shutdown

Composition connects one Identity-owned session controller to the app.
Environment reporting and native status observation also have shared owners;
route changes must not spawn parallel controllers or retry loops.

The installed app coordinates backend quiesce, pending work and shutdown through
its existing native commands. Host Tauri development reuses contributor Docker
and leaves that stack intact when its window closes. Closing a browser
does not implicitly shut down the server.

## Verify the affected shell behavior

Use the existing Next/static browser projects for route entry, reload, history,
scope changes, unsupported routes, viewport, focus and cleanup. Verify actual
native resize/DPI/window behavior when those boundaries change. Synthetic
native/browser tests do not replace an installed user check.

Do not require obsolete migration snapshots for routine shell edits. Keep
current route validation, import boundaries, build and lifecycle tests. Use the
actual selection in [CI validation](../operations/ci-validation.md).
