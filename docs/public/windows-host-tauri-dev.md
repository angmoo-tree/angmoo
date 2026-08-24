# Windows Host Tauri dev

Use this optional workflow only when changing Angmoo's actual Phone window,
native drag/resize, Creator Studio wide window, Relationship Graph wide window,
or Tauri window routing. Ordinary product development should use the Docker
contributor environment in a host browser.

## Supported reference environment

This PR verifies Windows 11 x64. You need:

- Docker Desktop with a running Linux container engine and Docker Compose
  2.22.0 or newer;
- Node.js 20.9.0 or newer;
- the repository-pinned Tauri CLI 2.11.4 (`npm ci --prefix desktop` installs it);
- Rust 1.97.1 with the MSVC target;
- Visual Studio C++ x64 build tools and Windows SDK 10.0.22000.0 or newer;
- Microsoft Edge WebView2 Evergreen Runtime;
- free loopback port `127.0.0.1:3000`.

The recorded reference host is Windows 11 Home build `26200.9168`. Other
Windows 11 builds may pass the same capability preflight; Windows 10, Windows
ARM64, Server, Wine, WSL GUI, and macOS are not claimed by this workflow.

## One-command bridge

From a clean checkout on the PR branch, close any installed Angmoo window and
run:

```powershell
.\scripts\dev\desktop-preflight.ps1
.\scripts\dev\desktop-dev.ps1
```

The first command reports every prerequisite and fails closed. The second
starts or reuses the two-service Docker contributor stack, checks runtime
readiness, starts Compose Watch, and opens the Windows Host Tauri Phone shell.
It does not build a sidecar or start a host FastAPI process.

Use `-NoWatch` only when the Docker stack is already healthy and source watch is
not needed:

```powershell
.\scripts\dev\desktop-dev.ps1 -NoWatch
```

## What to verify

1. The Phone window opens at Device Home and can move and resize.
2. Creator Studio opens in the one `studio` wide window.
3. Relationship Graph opens in the one `relationship-graph` wide window and
   preserves its route.
4. Closing and reopening each wide surface reuses its window label.
5. Docker shows only healthy `frontend` and `backend` services.
6. No host `angmoo-sidecar`, PostgreSQL, Neo4j, or Angmoo-owned JVM starts.
7. Closing Host Tauri leaves the Docker stack and contributor volume intact.

## Data safety

Contributor state stays in Docker named volume
`angmoo_contributor_embedded_data`. The bridge uses only
`.angmoo-dev/webview` for its repository-local WebView profile. It never mounts,
copies, migrates, or mutates installed-user data under
`%LOCALAPPDATA%\Angmoo`.

The launcher fingerprints installed canonical, graph, media, and secrets data
before and after the session and fails if they change. It also refuses to run
when an installed Angmoo or host sidecar process is active or when an Angmoo
data-root override is present.

Closing the Tauri window intentionally preserves Docker containers and data.
Stop them later without deleting the volume:

```powershell
docker compose -f compose.yml -f compose.dev.yml down
```

Do not add `--volumes` unless you intentionally want to delete the contributor
fixture.
