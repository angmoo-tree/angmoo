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

## Windows PowerShell encoding safety

Both commands support Windows PowerShell 5.1 and PowerShell 7 when the host
console starts in CP949 or UTF-8. They temporarily decode native Docker Compose
JSON as UTF-8 without BOM, retry a failed decode at most once, and restore the
previous console input, console output, and pipeline output encodings in a
`finally` block.

If Docker exits unsuccessfully, returns an unexpected empty response, or still
cannot produce valid JSON after the bounded retry, the command fails closed
with `compose_json_decode_failed`. Diagnostics include only the command type,
exit code, character and byte length, retry attempt, PowerShell version, active
code page, and a redacted reason. Raw Docker JSON, secrets, labels, mounts, and
local paths are never printed as part of that failure.

Do not work around an encoding failure by changing the machine-wide system
locale or permanently running `chcp 65001`. A supported Host Tauri checkout
must handle the active Windows console encoding itself.

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
