# Move Angmoo 0.1.3 data to 0.1.4

English | [한국어](postgresql-migration.ko.md)

Angmoo 0.1.4 uses PostgreSQL for application data, activity checkpoints and search. **Existing 0.1.3 SQLite data needs migration.** Selecting a new image alone does not convert it.

Direct migration supports the official **0.1.3** data format (SQLite schema 41). Other SQLite releases and private PostgreSQL experiments are outside this support contract. The migration retains IDs, conversations, posts, memories, relationships, media and installation secrets. It initializes the additional fields required by the 0.1.4 features, including maintenance recovery and stored experience snapshots.

## Before starting

Use assets from the same published [0.1.4 Release](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.4). Verify the downloaded files against `RELEASE-SHA256SUMS`. Release assets are available only after publication; a missing download is not a reason to use a script from `main`.

The tool shows the source, backup location and free space before confirmation. It stops the selected old environment, preserves an immutable backup and converts a separate working copy into a new PostgreSQL installation. It does not delete the old installation, images or data. Conversion and index rebuilding do not call an AI provider.

A backup contains private conversations and keys. Keep it in private storage and do not attach it to an Issue. Allow space for the source copies, new database and extracted images; the displayed check is a minimum, not an estimate of future media growth.

## Docker on amd64 or ARM64

Keep Docker running. Load or pull all three 0.1.4 images before migration. Download `angmoo-migrate.exe` on Windows, or `angmoo-migrate.py` on a Linux host with Python 3.10 or newer.

Docker images are supplied for Linux amd64 and ARM64. Migration on a macOS host has not been verified; official macOS-host migration support is deferred. ARM64 image availability alone does not establish Mac installation discovery, permissions or rollback behavior.

```powershell
.\angmoo-migrate.exe --language en
```

```sh
python3 angmoo-migrate.py --language en
```

The tool reads Compose labels and actual backend mounts. If it finds one environment, review and confirm it. If it finds several, select one, then confirm. It never picks the first environment silently. Docker connection or permission errors are reported as errors, not as an empty search result.

Only if no environment is found, specify the existing source explicitly:

```powershell
.\angmoo-migrate.exe --language en --source-volume "angmoo_angmoo_contributor_embedded_data" --backup-directory "D:\AngmooBackups"
```

Use the real volume name, not the example blindly. `--list` lists candidates without migrating. The Windows installer's AppData is not a Docker migration source.

After verification, the tool prints the browser address and the path to the new installation's `compose.json`. Use that file for normal operation:

```sh
docker compose -f "<backup-directory>/<migration>/installation/compose.json" ps
docker compose -f "<backup-directory>/<migration>/installation/compose.json" stop
docker compose -f "<backup-directory>/<migration>/installation/compose.json" up -d --wait
```

The generated Compose file uses the verified images and new external data volumes. It does not reuse the old SQLite volume as a PostgreSQL directory. Keep the migration folder: it contains the operating configuration, private credentials and backup.

To resume an interrupted conversion using the same images and source:

```powershell
.\angmoo-migrate.exe --language en --resume "D:\AngmooBackups\<migration>\migration.json"
```

To stop the new installation and return to the preserved source:

```powershell
.\angmoo-migrate.exe --language en --rollback "D:\AngmooBackups\<migration>\migration.json"
```

Rollback restarts only source containers that were running before migration. PostgreSQL changes made after migration stay in the new environment; they are not merged back into SQLite.

## Termux / PRoot on ARM64

Update the official launcher using the versioned installer in [Termux instructions](termux.md). Existing 0.1.3 installations are offered migration before startup. You can also start it explicitly:

```sh
angmoo migrate --release 0.1.4 --language en
angmoo start
```

For a custom installation, keep its home explicit:

```sh
angmoo --home "$HOME/.local/share/angmoo-custom" migrate --release 0.1.4 --language en
```

The launcher verifies the source installation manifest. It creates a sibling home named `<old-home>-postgresql`, imports the three ARM64 images and uses the common converter. It keeps the original home and selects the new home only after verification. A confirmed migration does not itself send AI requests; ordinary `start` resumes normal application behavior.

Rerun the same migration command to resume before activation. The source, image commit and conversion rules must still match. Return to the preserved installation with:

```sh
angmoo migrate --rollback --language en
angmoo start
```

Use the same `--home` for rollback when the source was custom. Keep the Termux app open during migration. Android can interrupt processes even when a wake lock is held; a successful Linux/ARM64 test does not guarantee background survival.

Termux resume keeps the original target source and image identities. If a newly
supplied manifest differs, it stops with `migration_resume_target_changed`
before stopping the old installation. Use the original candidate to resume;
do not replace receipts or point old work at a different candidate.

## Windows x64 installer

The original SQLite data stays in place. Conversion staging excludes the new
process's owner/endpoint records and serving lock; it retains checkpoints,
result journals, media and installation secrets. The lifetime lock stays held
through copying so another sidecar cannot start over the same source.

Close Angmoo and run the 0.1.4 installer. On first launch, review the data migration prompt and backup location. Declining does not convert or erase the old SQLite data. Accepting prepares a separate native PostgreSQL cluster and application-data directory under the user's Angmoo root.

**Program installation and data migration are separate steps.** If the installer detects an older version and offers removal before installation, choose **Do not uninstall** to retain the installation for the upgrade. When reinstalling the same 0.1.4 version, use its add/reinstall option. The data-migration confirmation appears when you launch the installed app, not on the installer's existing-version page. Keep the default data-preservation options.

First initialization or migration can take longer than an ordinary restart. The launcher allows up to four minutes for first preparation and one minute for normal restart; this is a readiness limit, not a promise that every migration takes the same time. If it reports an error, preserve the source and backup and follow the recovery instructions.

The installer supplies PostgreSQL 17 and pgvector. You do not need Docker, WSL or an existing PostgreSQL installation. Angmoo uses its own cluster, credentials and loopback port; it does not register a machine-wide database service or stop a developer's PostgreSQL server.

If conversion fails, keep the source and `postgresql-migration` directory. A subsequent launch can resume compatible work. Do not delete database files or reinstall over the only backup to clear an error. Use [backup and recovery](postgresql-backup.md) and the stable error code when requesting help.

## What the migration can and cannot recover

Existing embeddings are converted and keyword/graph indexes are rebuilt. Historical original content that was never stored cannot be invented: those memories retain an explicit unavailable-snapshot state. New memories use the current snapshot policy.

Completed work and failure history remain. An old in-flight maintenance lease is not transferred to a new process; it becomes an explicit recovery state. Failed parts require manual recovery. Closing a failure preserves its history and prevents it from joining the next automatic round. A conversion pass does not certify AI-provider availability or retrieval relevance for every personal query.

Do not downgrade a PostgreSQL database by attaching a 0.1.3 image. The old image can use the preserved old SQLite data. See [runtime contracts](postgresql-runtime.md) for storage ownership and [backup and recovery](postgresql-backup.md) for a full backup.

## Review the tools and their verification

The tools are open source. Review the [Docker host adapter](../../launcher/migrate/docker_migrate.py), [Termux migration orchestration](../../launcher/termux/migrate.py), and [common converter](../../backend/app/runtime/postgresql_migration.py). Windows uses the same converter through the [native runtime](../../backend/app/runtime/windows_postgresql.py). When reviewing a downloaded release, select that release's tag rather than the changing `main` branch.

The Release supplies `angmoo-migration-tools.json`, `release-manifest.json` and `RELEASE-SHA256SUMS` to connect source identities and file hashes. Its verification record and linked Actions runs describe the tested platforms and remaining limitations. A checksum establishes file identity; the platform migration, preservation and recovery tests establish the tested behavior. Keep private data and credentials out of public reports.
