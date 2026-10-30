# PostgreSQL backup and recovery

English | [한국어](postgresql-backup.ko.md)

A full Angmoo backup includes **the database, media, installation secret, runtime credentials and installation/version records**. World Package export is not a full backup. Keep the matching installer or three image references with it, and keep all private files out of public support reports.

## Back up a stopped installation

Stop through the normal launcher and wait for completion. Do not copy a live PGDATA directory or only one file from it. A cold backup is restored with the same PostgreSQL major version, platform and matching Angmoo resources. Moving between Windows, Linux and Termux is not a directory-copy migration.

| Environment | What to preserve after stopping |
| --- | --- |
| Windows | The full Angmoo data root, including `postgresql`, `postgresql-appdata`, media/secrets and the migration directory; the matching installer |
| Docker, fresh install | PostgreSQL data, application data and bootstrap-secret volumes, Compose configuration and exact image references |
| Docker, migrated install | Both external data volumes and the private migration folder containing credentials, `migration.json` and `installation/compose.json` |
| Termux | The selected PostgreSQL home, its credentials, PGDATA, application data and installation records; source-home selection and matching release/image manifests |

For Docker, use the actual volume names from `docker inspect` or the saved Compose configuration. This example archives one stopped volume into a **new private backup directory**:

```sh
docker compose -f "<installation>/compose.json" stop
docker run --rm --user 0:0 --entrypoint tar \
  --mount type=volume,src=<actual-volume-name>,dst=/source,readonly \
  --mount type=bind,src=<absolute-private-backup-directory>,dst=/backup \
  ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.4 \
  -czf /backup/<unique-archive-name>.tar.gz -C /source .
```

Repeat for every required volume. Do not start a database while it is being archived. Record each archive's SHA-256. `docker compose stop` preserves volumes; adding `--volumes` to cleanup is unrelated and destructive. Normal operation of a migrated installation uses the generated Compose file, not the old 0.1.3 project directory.

For Termux, run `angmoo stop`, identify the selected sibling home from `selection.json`, and archive that stopped home to a separate private location. Keep the original 0.1.3 home separately. Reinstallation of the same release can recreate image filesystems; it must not replace the restored data with an empty installation. Host-tool compatibility also depends on the Termux distribution/version.

## Restore and verify

Restore into new empty directories or volumes. Check hashes, use the same PostgreSQL major/platform and preserve credentials and permissions. Keep the current installation until the restored copy has passed startup, expected identity/schema, representative record and media reads, a new write, search and clean restart. Select only the verified copy for normal operation.

On Windows, Angmoo's native controller verifies its cluster path and PostgreSQL system ID before stopping or starting it. Its internal dump/restore path refuses a mismatched backup or active application sessions, keeps a pre-restore dump and restores into an empty database of the same owned cluster. A standalone `pg_dump` is an additional DB backup, not a replacement for the full file set above.

Do not edit installation IDs, disable integrity checks, delete pending work, or attach an old image to a newer schema to force startup. A failed restore stays a failed restore; retain the dump and private error record and retry only with the correct resources.

## Return to 0.1.3 after migration

Use the platform's [migration rollback](postgresql-migration.md) and the preserved old SQLite installation. PostgreSQL writes after migration do not flow back into SQLite. Keep both until you decide which data to retain. Removing images, old environments or backups requires a separate deliberate cleanup action.

## Safe diagnosis

Record product commit/version, PostgreSQL major, schema version, stable error code and which phase failed. Do not publish DSNs, passwords, raw SQL parameters, credentials or conversation text. For installed Windows diagnosis, verify the physical installation and opened data paths before treating a path as the active database. [Legacy SQLite recovery](../operations/sqlite-recovery.md) applies to the retained migration source, not the running PostgreSQL database.
