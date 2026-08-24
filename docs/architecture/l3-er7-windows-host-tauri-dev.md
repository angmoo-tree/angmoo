# L3-ER7 Windows Host Tauri dev architecture

PR Q adds one Windows-only product-shell development bridge. It does not add a
second backend, database, graph provider, or contributor data store.

```text
Windows host Tauri shell
├─ Phone window: main -> /
├─ Creator Studio window: studio -> /studio...
└─ Relationship Graph window: relationship-graph -> relationship graph route
                         │
                         ▼
Docker contributor stack
├─ frontend: Next.js dev, HMR, browser/Tauri WebView source
└─ backend: CONTRIBUTOR_EMBEDDED
   ├─ SQLite + FTS5
   ├─ LadybugDB
   ├─ scheduler in process
   └─ projector in process
```

## Ownership boundary

The Docker contributor stack owns API execution and all contributor data. The
Host Tauri process owns only native windows and a repository-local WebView
profile at `.angmoo-dev/webview`. It does not start `angmoo-sidecar`, create a
host SQLite or LadybugDB store, or read and write installed-user
`%LOCALAPPDATA%\Angmoo` data.

The compile-time `contributor-docker-bridge` feature selects the typed desktop
launch mode. It is rejected in release builds. The additive Tauri config:

- disables `beforeDevCommand`, so no second host Next.js process starts;
- loads only `http://127.0.0.1:3000` from Docker;
- disables bundling and external sidecar binaries;
- allows core window commands only for `main`, `studio`, and
  `relationship-graph` on that one loopback origin.

The installed product path remains unchanged: normal debug/release modes retain
the bundled-sidecar implementation, and release builds continue to use the
installer and `%LOCALAPPDATA%\Angmoo` lifecycle contract.

## Preflight and lifecycle

`scripts/dev/desktop-preflight.ps1` fails closed unless the reviewed Windows
11 x64 host, Docker Engine, Compose, Node, Rust, Tauri CLI, MSVC tools, Windows
SDK, WebView2, ports, processes, repository files, and data-root boundaries are
valid. The reference environment is Windows 11 Home build `26200.9168`; it is
evidence, not an exact-build-only promise. Windows 10, ARM64, Server, Wine, WSL
GUI, and macOS are unverified by this PR.

`scripts/dev/desktop-dev.ps1` then:

1. records the exact Git commit and fingerprints protected installed data;
2. starts or reuses the same two-service Docker dev stack;
3. proves `CONTRIBUTOR_EMBEDDED`, SQLite, LadybugDB, scheduler, and projector
   readiness;
4. optionally starts Compose Watch;
5. starts only the Host Tauri shell;
6. stops the host shell/watch client on exit while preserving the Docker stack
   and `angmoo_contributor_embedded_data` volume;
7. proves no host sidecar appeared and installed-data fingerprints did not
   change.

The script never runs `docker compose down`, `--volumes`, prune, or any
installed-data removal command.

## Review and evidence Gate

The protected surface is `desktop/src-tauri`, `desktop/platform`, the two
Windows scripts, their CI contract, and product-shell documentation. CODEOWNERS
records `@jingujeon` as the current platform-shell maintainer. During the
single-maintainer period this is an explicit maintainer review record, not an
impossible self-approval rule.

Required closeout evidence is:

- local contract checker, synthetic PowerShell preflight matrix, and both Rust
  launch-mode test suites;
- Hosted Windows workflow PASS;
- platform-shell maintainer review;
- user confirmation that Phone drag/resize and Phone-to-Studio/Graph wide
  windows work while the Docker backend remains healthy;
- no host sidecar, no installed-data mutation, and no Docker volume deletion.

Implementation and technical evidence do not replace the final user screen or
merge approval Gate.
