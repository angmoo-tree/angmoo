# L3-ER5 Tauri product-window contract

PR L turns the static frontend proven by PR K into product-shaped Tauri
windows. It does not start, authenticate, recover, or package the FastAPI
sidecar; those lifecycle and security responsibilities remain in PR M.

## Window ownership

| Window | Label | Route boundary | Sizing |
| --- | --- | --- | --- |
| Phone | `main` | Device Home, World App, Feed, settings and owner flows | fixed aspect, monitor-fit at 100%, 125%, and 150% scaling |
| Creator Studio | `studio` | `/studio` and its World editor routes | resizable wide window, minimum `980x680` |
| Relationship Graph | `relationship-graph` | one scoped Character/World graph route | resizable wide window, minimum `900x620` |

Each label is a singleton. Opening an existing surface updates its allowlisted
route, restores the window, and focuses it instead of creating another window.
The Tauri webviews use one application origin and the same frontend runtime
adapter, so they observe the same owner session and canonical World state.

`Memory Explorer` is shown as a disabled, planned application icon. It has no
route, command, or backend capability in PR L and therefore cannot be mistaken
for a shipped product feature.

## Navigation boundary

The browser and Docker development modes keep ordinary Next navigation. In a
Tauri host, the shared desktop bridge maps only Creator Studio and Relationship
Graph routes to wide windows. Phone routes remain in the Phone window. The Rust
host validates the window kind, path shape, identifier segments, and graph
provider query before creating or reusing a window.

The static release profile injects the requested route before React starts and
dispatches a local route event when an existing window is reused. This avoids a
Node/Next server in the eventual general-user process tree while preserving the
same React feature source used by browser contributors.

## Capability and PR boundary

PR L grants only `core:default` to the three product windows. It does not include
`tauri-plugin-shell`, raw shell permission, sidecar execution, database commands,
installer behavior, or per-launch credentials. PR M implements and verifies the
separate lifecycle contract documented in
`docs/architecture/l3-er5-tauri-sidecar-lifecycle.md`:

- packaged sidecar path and hash validation;
- dynamic loopback port and per-launch token;
- strict origin/CORS and injected runtime configuration;
- single instance, readiness, crash recovery, graceful shutdown, and orphan cleanup.

## Verification

- Rust unit tests prove route rejection and monitor-fit sizing.
- frontend lint and TypeScript check prove the bridge is shared safely.
- static Playwright tests prove Phone-to-wide delegation, disabled Memory
  Explorer, and direct wide-window static routing.
- a Windows Tauri no-bundle build proves the real WebView2 product shell links.
- browser Next and Docker/self-host checks remain mandatory regressions.
