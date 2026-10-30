# Windows Host Tauri dev

Use this optional workflow only when changing Angmoo's native window behavior,
resizing, Creator Studio or Memory workspaces, or Tauri window routing.
For ordinary product development, use the Docker contributor environment in a
host browser.

## Supported reference environment

This workflow targets Windows 11 x64. You need:

- Docker Desktop with a running Linux container engine and Docker Compose
  2.22.0 or newer;
- Node.js 20.9.0 or newer;
- the repository-pinned Tauri CLI 2.11.4 (`npm ci --prefix desktop` installs it);
- Rust 1.97.1 with the MSVC target;
- Visual Studio C++ x64 build tools and Windows SDK 10.0.22000.0 or newer;
- Microsoft Edge WebView2 Evergreen Runtime;
- free loopback port `127.0.0.1:3000`.

Run the capability preflight on the actual host; an old reference build does
not establish current compatibility. Windows 10, Windows
ARM64, Server, Wine, WSL GUI, and macOS are not claimed by this workflow.

## One-command bridge

From the development checkout, close any installed Angmoo window and
run:

```powershell
.\scripts\dev\desktop-preflight.ps1
.\scripts\dev\desktop-dev.ps1
```

The first command reports every prerequisite and fails closed. The second
starts or reuses the three-service PostgreSQL Docker contributor stack, checks runtime
readiness, starts Compose Watch, and opens the Windows Host Tauri main shell.
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

1. The main window opens at Device Home and can move, resize and maximize.
2. Creator Studio opens in a single wide `studio` window.
3. Memory opens in its `memory` workspace; current World relationships remain
   inside the World route and retain scope.
4. Closing and reopening each wide surface reuses its window label.
5. Docker shows healthy `postgres`, `backend` and `frontend` services.
6. No native host `angmoo-sidecar`, PostgreSQL, Neo4j, or Angmoo-owned JVM starts; PostgreSQL runs inside the contributor Docker project.
7. Closing Host Tauri leaves the Docker stack and contributor volume intact.

## Data safety

Contributor state stays in Docker named volume
`angmoo_contributor_embedded_data` (application files), the project's PostgreSQL
and bootstrap-secret volumes. The old SQLite application volume is a protected
migration source, not a new empty 0.1.4 database. The bridge uses only
`.angmoo-dev/webview` for its repository-local WebView profile. It never mounts,
copies, migrates, or mutates installed-user data under
`%LOCALAPPDATA%\Angmoo`.

The launcher fingerprints installed canonical, graph, media, secrets and any native PostgreSQL data
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
