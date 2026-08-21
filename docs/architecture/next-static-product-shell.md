# Next static product shell contract

ER5 PR K keeps one React/Next frontend source while separating two delivery
profiles:

- `pnpm build` keeps the existing Next server/standalone profile for browser,
  Docker, and contributor HMR workflows.
- `pnpm build:static` builds `frontend/static-shell` with `output: "export"`;
  its route resolver lives in the product composition layer rather than a
  domain feature, so incremental legacy surfaces remain behind the existing
  architecture-boundary contract. The build copies generated release assets
  to the untracked `frontend/out`.

The static entry imports the same Device Home, Creator Studio, World App,
settings, agent, activity setup, relationship graph, feed, and post components
from `frontend/src`. It is not a second product implementation.

## Runtime injection

Before product requests begin, the future Tauri launcher supplies:

```ts
window.__ANGMOO_RUNTIME_CONFIG__ = {
  profile: "tauri-static",
  apiBaseUrl: "http://127.0.0.1:<dynamic-port>",
  launchToken: "<per-launch-random-token>",
};
```

Only HTTP loopback hosts are accepted. In the browser/server profile,
`/api/backend/*` and `/media/*` keep their current same-origin Next behavior.
In the static profile, the shared request adapter maps them to the sidecar's
`/api/v1/*` and `/media/*` endpoints and carries the optional launch token. The
token is never attached to a non-sidecar URL. Backend token, CORS, and origin
enforcement are owned by ER5 PR M.

## Dynamic route fallback

The static build intentionally has one physical product entry. `index.html` is
also emitted as `404.html`; the Tauri asset protocol or preview static server
must use it as the fallback for dynamic URLs. The client router then resolves
World, Character, and Post identifiers from `location.pathname`. Internal links
perform full-document navigation in this profile so direct-open and refresh use
the same fallback contract.

The supported ER5 matrix includes:

- `/`
- `/studio`
- `/studio/worlds/new`
- `/studio/worlds/{world_id}`
- `/worlds/{world_id}` and `/worlds/{world_id}/feed`
- `/characters/{character_id}/worlds/{world_id}/autonomy-setup`
- `/characters/{character_id}/worlds/{world_id}/relationship-graph`
- `/agents/{character_id}`
- `/posts` and `/posts/{post_id}`
- `/settings`
- `/login` as the local-owner recovery entry

## Browser-only responsibilities

Next `headers()`, `redirects()`, and `rewrites()` remain in the browser/server
profile. Tauri owns CSP and the static asset protocol; the shared runtime
adapter owns API/media routing. The optional PWA service worker is not copied to
`frontend/out` and is explicitly unregistered in the static profile.

`frontend/out`, `frontend/static-shell/out`, `.next`, and generated
`next-env.d.ts` files are build artifacts and are never committed.
