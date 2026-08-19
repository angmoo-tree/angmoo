# L3-ER1 native runtime compatibility spike

This directory is an executable compatibility proof for Issue #101. It does
not change Angmoo's production runtime, database, public API, or release
defaults.

The spike freezes these candidate versions:

- CPython `3.13.12` (uv-managed Windows x86-64)
- LadybugDB Python package `ladybug==0.19.1`
- Rust `1.97.1` (`x86_64-pc-windows-msvc`)
- Tauri CLI `2.11.4` and Rust crate `tauri==2.11.5`
- PyInstaller `6.16.0`

- the current Docker backend and the native spike both use Python 3.13; the
  spike pins patch release 3.13.12 because that exact uv-managed interpreter
  is part of the native compatibility evidence;
- LadybugDB publishes an attested CPython 3.13 Windows x86-64 wheel for
  `0.19.1`; its default PyBind native module imports and creates databases
  without a machine-wide LadybugDB, OpenSSL, or JVM installation;
- `0.19.1` rejects a database path containing characters outside the active
  Windows ANSI code page; the dedicated sidecar temporarily exposes the real
  Unicode data directory through an unused ASCII drive alias, opens the graph
  there, and removes the alias on shutdown while the physical files remain in
  the intended user-data directory;
- this spike proves that a Python 3.13 packaged FastAPI sidecar can embed the
  native graph library;
- changing the production storage adapter is a later, separately reviewed ER
  step.

## What is proved

`python/ladybug_probe.py` creates a graph under a path containing both Korean
characters and spaces. It proves close/reopen, an Angmoo-owned exclusive writer
lock, serialized reads, idempotent `MERGE`, World-scoped direct/evidence reads,
and bounded one-to-three-hop traversal. The temporary drive alias is safe only
because the packaged Ladybug adapter owns an isolated process and removes it
on graceful or parent-death shutdown; it must not be copied into a shared
multi-purpose process.

`python/sidecar.py` is packaged as a single executable. It binds only to a
dynamic `127.0.0.1` port, requires an ephemeral token for every endpoint,
rejects duplicate ownership through the same exclusive lock, watches the Tauri
parent PID, and supports authenticated health and shutdown.

`python/sidecar_lifecycle_probe.py` executes those claims against the packaged
executable: it verifies a second writer exits with code 17, unauthenticated
health is rejected, authenticated shutdown exits cleanly, and terminating a
sentinel parent removes its orphaned sidecar within five seconds.

`tauri/` is a minimal Tauri v2 shell. It starts the packaged sidecar, reads the
dynamic-port handshake, verifies unauthenticated rejection and authenticated
health/graph access, requests graceful shutdown, and writes a token-free JSON
evidence file before exiting in automated mode.

## Windows run

From the repository root:

```powershell
pwsh -File .\spikes\l3-er1-native-runtime\scripts\run-spike.ps1
```

The generated artifacts and evidence stay outside Git under
`.codex-temp/l3-er1-native-runtime-spike`. A clean run may download the pinned
Python wheels, Rust crates, and Tauri tooling.

## Safety boundaries

- synthetic graph data only;
- external provider calls: zero;
- no application credential or local user content is read;
- the auth token is generated per launch and never written to evidence;
- no PostgreSQL, Neo4j, Docker volume, schema, or production setting changes;
- ER2 must not start until this spike is reviewed and the user explicitly
  approves the Go decision.
