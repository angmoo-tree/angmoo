# PostgreSQL dependencies and replacement

The native PostgreSQL 17.11 server and pgvector 0.8.7 extension retain the
PostgreSQL License. The Python `pgvector` package is a different component.
Windows resource sources and hashes are in `scripts/windows-postgresql.lock.json`;
the Linux image digest is in `Dockerfile.postgres`. Windows preserves the
upstream server/command-line notices and pgvector license beside the resources.

The Windows recipe adds a UTF-8 `activeCodePage` process manifest to the bundled
native executables, preserving any existing manifest settings. This supports
Korean and other Unicode installation/data paths without changing the system
locale. It requires Windows 10 version 1903 (build 18362) or later. The generated
resource manifest records the recipe code hash, executable hashes and this
modification; the original downloaded archive hash remains separately pinned.
Rebuild these resources with `scripts/build_windows_postgresql.py` and the
Windows SDK manifest tool before packaging the sidecar/installer. See Microsoft's
[process UTF-8 documentation](https://learn.microsoft.com/en-us/windows/apps/design/globalizing/use-utf8-code-page).

Psycopg 3.3.6, psycopg-binary 3.3.6 and psycopg-pool 3.3.3 report LGPL-3.0-only.
They are unmodified locked libraries. Keep their package license files and the
accompanying GPL text. The release includes `angmoo-postgresql-sources.zip`
with the pinned Psycopg repository, exact locked pool source and notices. The
Psycopg source pin is recorded in `security/psycopg-source-lock.json`.
See the [upstream source](https://github.com/psycopg/psycopg/tree/a67654d1e7afbf9b3a619557838f62de1c790e7c)
and its license files. Do not describe the native pgvector extension as MIT or
assume the binary wheel's libpq version equals the server version.

## Rebuild with a modified library

Use the released product tag and its matching source, never a newer `main`.
Install the locked backend environment with `uv sync --frozen --project backend`.
For a local modification, build/install the modified Psycopg library into that
explicit backend environment. Preserve upstream notices and make modifications
to covered library files available under their applicable license.

On Windows, run `desktop/scripts/build-sidecar.ps1 -Python <environment-python>`
and rebuild the Tauri host/installer using the documented desktop commands. The
sidecar hash is generated from the rebuilt binary and compiled into the rebuilt
host; no publisher signing key or authorization token is needed to run that
local build. Keep user data separate while testing. Docker users can rebuild
the backend image with the modified locked library and the published Dockerfile.
The distribution must not forbid debugging those modifications.

The native server, app source, libraries, World Packages and user data have
separate license/data boundaries. Exact dependency review and packaged-file
checks remain required; this guide does not replace the upstream license text.
