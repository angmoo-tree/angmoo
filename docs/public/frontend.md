# Frontend guide

Angmoo uses Next.js for browser execution and a static frontend inside Tauri.
Both render the same feature components. Start development through the
[Docker contributor environment](development.md).

Read [Frontend Architecture](../../frontend/ARCHITECTURE.md) for code ownership,
[DESIGN](../../frontend/DESIGN.md) for appearance and interaction, and
[product shell](../architecture/frontend-product-shell.md) for viewport and
navigation. [Design reference](../architecture/frontend-design-reference.md)
explains reviewed visual adoption and asset provenance.

## Where code belongs

- `src/app`: thin Next routes, layouts and server-specific work.
- `src/composition`: screens, shells and providers that connect features.
- `src/features/<feature>`: API, components, hooks, DTOs and feature utilities.
- `src/components`, `hooks`, `lib`, `types`, `utils`, `styles`: appropriate common
  presentation, transport and tools.

Import concrete owner files. Different features communicate through composition,
not direct sibling imports. Retired `public.ts` and `shared` paths are not new
extension points. Do not put business authorization in a common primitive.

## Runtime and UI behavior

`ProductViewport` provides the responsive body and native toolbar. The neutral
`components/ui/device-frame.tsx` and `components/layout/device-shell.tsx` receive
presentation inputs; they do not determine World permissions. Use the actual
scroll owner for pagination, anchoring and lazy media.

Preserve distinct loading, empty, forbidden, missing, offline, degraded and error
states. Accepted writes and subsequent refreshes have separate outcomes. Scope
changes must cancel observation and reject late results without repeating a write.

Keep API and credential transport in the existing adapters. A frontend flag
does not supply credentials, enable backend work or establish authorization.
User-visible text and accessible names require English and Korean. Use local,
rights-cleared assets and the existing font/token policy.

Follow [changing the frontend](changing-frontend.md) for a focused workflow and
the applicable browser/build checks.
