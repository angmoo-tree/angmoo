# L3-ER6 Windows installer release-candidate contract

ER6 packages the production-off embedded-runtime preview as an installable
Windows release candidate. It does not publish a GitHub Release, switch the
contributor Docker default, or authorize the ER7 canonical cutover.

## Installed product shape

The NSIS Setup and MSI contain one Tauri host, the static frontend, and the
self-contained FastAPI sidecar. The sidecar owns SQLite, LadybugDB, scheduler,
and projector in process. A clean machine does not need Python, Node.js,
pnpm, Docker, PostgreSQL, Neo4j, or a JVM.

```text
angmoo-desktop.exe (product display name: Angmoo)
└─ angmoo-sidecar-x86_64-pc-windows-msvc.exe
   ├─ SQLite canonical generation
   ├─ LadybugDB replayable graph projection
   ├─ scheduler component
   └─ projector component
```

The per-user product root is `%LOCALAPPDATA%\Angmoo`. Installer-owned files
live under `app`, while user data has a separate lifetime:

```text
app/angmoo-desktop.exe
app/angmoo-sidecar.exe
canonical/generations/<generation>/angmoo.sqlite3
canonical/current-generation.json
canonical/previous-generation.json
graph/current-generation.json
graph/generations/
search/
media/
secrets/app-secret
runtime/
```

The packaged sidecar creates an APP_SECRET only for a truly empty first run.
If canonical data already exists but the secret is missing, startup fails
closed instead of silently creating an incompatible secret. Docker and browser
development defaults remain unchanged.

## Offline PostgreSQL to SQLite migration

> Historical ER6 evidence: the command and importer described in this section
> were removed before the first public SQLite-only release. They are retained
> here only to preserve the verified transition record and are no longer
> executable or supported.

The current Docker source is stopped before migration. The connection string,
including its password, is supplied only through `DATABASE_URL`; it is never a
command argument or report field.

```powershell
$env:DATABASE_URL = '<read from the existing local secret source>'
backend\.venv\Scripts\python.exe `
  backend\scripts\dry_run_postgres_to_sqlite.py `
  --output-root "$env:LOCALAPPDATA\com.angmoo.desktop" `
  --generation er6-migrated-v1 `
  --app-version 0.4.0-1 `
  --confirm-source-stopped
```

The command performs a disk-space preflight, opens a repeatable read-only
PostgreSQL snapshot, converts all canonical tables into a temporary SQLite
generation, verifies migration lineage, row counts, primary-key and row
digests, foreign keys, SQLite integrity, and media-manifest digests, then
publishes the completed generation without changing the selected runtime.
Output contains only counts, digests, owned paths, and status fields.

The graph is rebuilt from successful canonical events after migration:

```powershell
$env:DATABASE_URL = 'sqlite+pysqlite:///C:/.../angmoo.sqlite3'
$env:LADYBUG_DATABASE_ROOT = 'C:\...\graph\ladybug'
backend\.venv\Scripts\python.exe `
  backend\scripts\manage_ladybug_preview.py replay `
  --world-id '<synthetic-world-id>' `
  --database-root "$env:LADYBUG_DATABASE_ROOT"
```

Only after parity and product preview checks may a generation marker be
written. Promotion and rollback are separate explicit commands:

```powershell
backend\.venv\Scripts\python.exe `
  backend\scripts\manage_release_candidate.py promote `
  --runtime-root "$env:LOCALAPPDATA\com.angmoo.desktop" `
  --generation er6-migrated-v1 `
  --content-sha256 '<migration manifest content_sha256>'

backend\.venv\Scripts\python.exe `
  backend\scripts\manage_release_candidate.py rollback `
  --runtime-root "$env:LOCALAPPDATA\com.angmoo.desktop"
```

The marker digest attests the immutable migration result at promotion time.
The selected database remains writable, so normal application writes do not
invalidate the marker. Rollback refuses a missing generation database.

## Synthetic backup and restore policy

ER6 migration evidence uses only a marked synthetic fixture. Backup refuses a
fixture unless `synthetic_fixture=true` and
`contains_real_credentials=false`. It still carries a synthetic APP_SECRET and
synthetic `local-v2` credential so restore can prove real envelope decryption.

```powershell
backend\.venv\Scripts\python.exe `
  backend\scripts\manage_release_candidate.py backup `
  --runtime-root '<synthetic runtime root>' `
  --backup-root '<private temporary backup root>'

backend\.venv\Scripts\python.exe `
  backend\scripts\manage_release_candidate.py restore `
  --runtime-root '<synthetic runtime root>' `
  --backup-root '<private temporary backup root>' `
  --target-root '<empty restore root>'
```

Every file is path-confined and SHA-256 verified before and after restore.
Symlinks, tampered contents, non-empty restore targets, personal data, and real
credentials fail closed. Backup directories, APP_SECRET files, and synthetic
fixture markers are explicitly rejected from public CI artifacts.

## Installer, update, and uninstall

- NSIS is per-user and MSI has a stable upgrade code.
- Downgrades are blocked; an explicit rollback uses the generation marker.
- The offline WebView2 installer is bundled for a disconnected first start.
- Interactive NSIS uninstall offers `keep data` and a second confirmation for
  `remove data`.
- Silent NSIS uninstall and MSI uninstall always preserve local data.
- Program removal never treats the data root as an installer-owned directory.

## Supported direct-update contract

An installer build is not considered safe merely because it can be produced or
clean-installed. Every SQLite predecessor version that the candidate declares
readable must have a deterministic synthetic fixture and must pass a real NSIS
direct update on `windows-latest`.

The current matrix covers SQLite v1 and v2 as supported predecessors and v3 as
the target/current no-op state. Each migration step owns a semantic delta
contract. The v2 to v3 contract permits only the exact reserved
`no_specific_role` rows, affected autonomous `WorldCharacter` role/version
changes, and their derived World/profile/repertoire/plan hashes. All unrelated
table content and identities remain immutable. A conflicting reserved role
fails closed with a stable code.

The installer transaction stages and verifies the new host and sidecar before
promotion. If data migration then fails, it restores the verified previous app
only when the previous payload can still read the active data version. If data
has already advanced or the backup cannot be trusted, the installer refuses to
run either payload. Failed updates never expose the success finish page or
`Run Angmoo now` action.

The Windows Installer workflow reports these separate meanings:

- `windows-installer-build`: exact-SHA NSIS/MSI artifact and payload manifest;
- `windows-installer-clean-install`: empty LocalAppData install/start/stop;
- `windows-installer-supported-upgrade`: real NSIS v1/v2 direct-update matrix;
- `windows-installer-failure-recovery`: conflict injection, data immutability,
  and verified previous-app restoration;
- `embedded-data-migration`: version chain, semantic delta, copy-on-write, and
  idempotency;
- `windows-installer`: fail-closed aggregator for the complete installer
  matrix.

Adding SQLite v4 or a later version without adding the new supported
predecessor fixture causes the matrix contract to fail instead of silently
skipping the missing upgrade path. No fixture contains personal data or real
credentials.

## Supply-chain evidence

The Windows Installer workflow builds NSIS and MSI from locked Python, Node,
pnpm, Rust, and Tauri inputs. It produces:

- `SHA256SUMS`;
- SPDX 2.3 SBOM for Python, Node, Rust, and installer files;
- in-toto/SLSA-shaped provenance metadata;
- `LICENSE` and `THIRD_PARTY_NOTICES.md`;
- GitHub build provenance attestation on non-PR builds.

The workflow audits locked Python and production frontend dependencies, scans
the NSIS installer with Microsoft Defender, silently installs it, starts the
product, waits for the endpoint and SQLite generation, and rejects Python,
Node, Java, PostgreSQL, Neo4j, or Docker child processes.

## Verification boundary

Automated evidence covers migration, Ladybug replay, backup/restore,
credential decryption, installer metadata, and an installed-runtime smoke. The
following remain explicit user gates before ER6 can be marked complete:

- install on the intended clean Windows 11 machine and check 125%/150% DPI;
- full P1-P4 product scenario and relationship graph;
- offline first start, port collision, existing-instance, update, and rollback;
- interactive NSIS `keep data` and `remove data` outcomes;
- user final screen judgment and PR merge;
- separate approval to enter ER7 canonical switch.
