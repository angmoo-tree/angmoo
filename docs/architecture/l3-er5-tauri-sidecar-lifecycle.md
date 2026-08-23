# L3-ER5 Tauri sidecar lifecycle and loopback security

PR M connects the static product shell from PR K and the product-shaped Windows
host from PR L to one packaged FastAPI sidecar. It is a preview-only runtime
contract: Docker, browser development, and the public release remain unchanged.
ER6 still owns the installer, migration user experience, and clean-machine
closeout; ER7 still owns removal of the legacy PostgreSQL and Neo4j defaults.

## Runtime sequence

1. The Rust host verifies the packaged sidecar path and build-time SHA-256.
2. The first application instance creates a private launch token and a
   process-owned runtime directory.
3. The sidecar binds to `127.0.0.1:0`, writes token-free endpoint metadata, and
   reports readiness only after the FastAPI application has started.
4. The static frontend shows a loading surface until the Rust host reports a
   healthy endpoint, then installs the endpoint and token in memory.
5. Product requests use the dynamic endpoint. The token is attached only to
   sidecar requests and is never written to endpoint, PID, log, or diagnostic
   metadata.
6. On a sidecar crash the product switches to a bounded recovery surface. The
   explicit retry command starts a new launch with a new token.
7. On application exit the host requests graceful shutdown, waits for owned
   metadata to disappear, and uses a kill fallback only if the sidecar does not
   drain in time.

ER6 packages the Windows sidecar with PyInstaller's no-console subsystem. The
host therefore does not depend on stdout for readiness: every launch receives
a random generation identifier, polls an atomically replaced
`sidecar.endpoint.json`, validates schema/PID/loopback/dynamic-port/generation,
and only then performs the authenticated health request. Endpoint metadata
contains no launch token, APP_SECRET, credential, or API key. Docker, direct
backend execution, and `tauri dev` keep their normal developer diagnostics.

The ER6 Studio lifecycle surface remains read-only. A creator opens a World and
retrieves only that World's existing WorldCharacter summaries through the
`world_characters` domain. Autonomous entries link to the existing P2/P3/P4
setup route; owner-controlled entries link to the existing World profile area.
Creation, deletion, placement, archive, and recovery remain deferred to P10-L.

The packaged one-file Python executable appears as two Windows PIDs while it is
running: a PyInstaller bootloader and its child Python worker. They represent
one logical sidecar, one owner record, one listening port, and one FastAPI
application. Duplicate-runtime assertions therefore use the owner record,
endpoint, and listening socket rather than raw PID count.

## Security boundary

- The sidecar accepts only an HMAC-verified `X-Angmoo-Launcher-Token` generated
  for the current launch.
- After that token and the exact `http://tauri.localhost` origin pass the
  sidecar middleware, the packaged WebView resolves the already-claimed
  installation owner directly. It does not depend on a cross-site HttpOnly
  cookie surviving the `tauri.localhost` to dynamic `127.0.0.1` boundary.
  Token-authenticated host health probes omit `Origin` and never inherit an
  owner identity.
- The static shell may mount before Tauri has returned the sidecar's dynamic
  loopback port and launch token. Installing that runtime configuration emits
  an in-process configuration-change event; the shared auth provider retries
  `/auth/me` on that event instead of preserving an early fallback-port
  failure as an unauthenticated Device Home.
- Browser-originated product requests must use the exact
  `http://tauri.localhost` origin. CORS preflight is limited to that origin,
  the declared methods, and the launch-token/content-type headers.
- The trusted frontend-origin header is injected only after token validation;
  callers cannot promote themselves to a trusted local frontend.
- Tauri capabilities remain `core:default`. There is no JavaScript shell,
  raw-command, SQL, Cypher, or arbitrary sidecar execution capability.
- The Rust host supplies fixed executable arguments and environment keys. No
  frontend value is interpolated into a command line.
- A second desktop instance exits without starting another sidecar. Stale
  metadata is replaced only after its recorded owner PID is no longer alive.
- Cleanup removes only metadata owned by the current process and does not sweep
  unrelated processes or application data.

## Build and provenance

`desktop/scripts/build-sidecar.ps1` pins PyInstaller `6.16.0`, packages the
backend application and LadybugDB native wheel, emits the platform-specific
Tauri sidecar filename, and writes a SHA-256 file. `build.rs` embeds that digest
into the Rust binary; startup fails closed when the file and embedded digest do
not match.

Contributor commands:

```text
cd desktop
pnpm run build:sidecar
pnpm run build:shell
```

`pnpm run build:product` performs both steps. Hosted Windows CI repeats the
package, Rust format/test/clippy, and no-bundle product-link checks. Generated
binaries and digest files are ignored; source, package script, and workflow are
the reviewable provenance contract.

## Local executable evidence

The 2026-08-21 Windows probe produced:

- packaged sidecar: `56,398,511` bytes;
- sidecar SHA-256:
  `74d4912bd70e12654d8fc78d9e3924478fd889fce9ea5241fda8681116609967`;
- linked Tauri executable: `11,617,280` bytes;
- dynamic loopback health: HTTP 200;
- missing token: HTTP 401;
- wrong origin: HTTP 403;
- graceful shutdown: HTTP 200 followed by process exit;
- endpoint and owner metadata removed after shutdown;
- second product instance rejected;
- Node/Next descendants and `:3000` listeners: zero;
- orphan logical sidecars after product exit: zero.
- static Device Home media is fetched with the per-launch token and rendered
  from a revocable `blob:` URL; direct unauthenticated `/media` loading is not
  used by the packaged shell.

These are implementation and local executable results, not an ER5 merge or
user-screen verdict. The PR remains behind Hosted CI, user lifecycle scenario,
and user-owned Ready/merge gates.

## Required regressions

- backend focused security and full-suite tests;
- frontend lint, typecheck, static export, and static product-window tests;
- Rust format, unit tests, clippy, and Windows no-bundle link;
- browser development/HMR and the existing six-service Docker stack;
- delayed readiness, crash/retry, restart persistence, and Phone/Studio/Graph
  user scenarios before ER5 is marked complete.
