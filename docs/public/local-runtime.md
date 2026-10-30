# Local PostgreSQL runtime contract

The 0.1.4 local product uses PostgreSQL as its canonical store. The complete
platform, connection, search and maintenance contract is in
[PostgreSQL runtime](postgresql-runtime.md).

## Platforms

| Environment | Composition | Persistent state |
| --- | --- | --- |
| Docker amd64 / ARM64 | frontend, backend, PostgreSQL | PGDATA, application data, bootstrap credentials |
| Termux ARM64 | three image filesystems through PRoot | selected home, PGDATA, app data, protected credentials |
| Windows x64 | Tauri, sidecar, bundled native PostgreSQL | per-user Angmoo data root and private DB cluster |

The backend keeps scheduler/projector in process. LadybugDB is a replayable
projection; a graph outage does not roll back committed social/relationship
writes. Pending projection work remains available for recovery. UI and
diagnostics distinguish degraded/rebuilding/failed from a healthy empty graph.

## Lifecycle and data ownership

Start PostgreSQL and verify readiness before backend; start frontend after
backend readiness. Stop in reverse order, allowing commits and clean DB stop.
Only processes and clusters whose installation identity has been verified can
be controlled. Never remove PID/lock files merely because readiness failed.

Use separate data for contributors, tests and installed users. Windows data
does not become a Docker bind mount. Default uninstall keeps data; explicit
data removal is a separate user action. A DB server already running on a
developer's machine is not reused or stopped by the installed application.

Normal PG serving never falls back to SQLite. Existing 0.1.3 data requires
[explicit migration](postgresql-migration.md). Legacy embedded profiles and
SQLite generations remain only for supported input/recovery tests. Private
experimental PostgreSQL v3/v4/v5 data is outside the official input support.

## Security and recovery

DB credentials, the root application secret, media and retained-result journals
are protected persistent data. They are never baked into images or frontend
assets. Docker DB ports are private; Windows/Termux bind DB to loopback.
Origin, Host, browser-session and desktop launch-token checks remain enforced.

Use [backup and restore](postgresql-backup.md) to preserve the whole installation.
Returning to the preserved 0.1.3 environment does not backport PG changes.
Diagnostics are read-only and redact credentials and content. A final `ready`
sample does not prove absence of errors during prior activity.

## Platform-shell development

General development uses Docker and the browser. Native window work may use
the [Windows Host Tauri bridge](windows-host-tauri-dev.md), which points to
that same Docker backend and a repository-local WebView profile. It does not
start an installed sidecar or read installed data. macOS packaging requires
its own target-OS contract and is not claimed here.
