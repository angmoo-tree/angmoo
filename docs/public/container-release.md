# Run Angmoo with Docker

English | [한국어](container-release.ko.md)

This is the 0.1.4 source configuration for Linux amd64 and ARM64. The versioned
assets become available after formal publication. Existing 0.1.3 users must
run the [migration tool](postgresql-migration.md) before replacing their stack.

## New installation

Use Git, Docker with a Linux engine, and Compose 2.23.0 or newer.

```sh
git clone --branch release-v0.1.4 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

Open http://127.0.0.1:3000. Frontend, backend and PostgreSQL use the same product
version/source. The database port is private. PGDATA, app media/secrets and DB
bootstrap credentials have separate persistent volumes. See the
[runtime contract](postgresql-runtime.md).

## Status and stop

```sh
docker compose ps
docker compose logs --tail 100 postgres backend frontend
docker compose stop
docker compose up -d --wait
```

`stop` and `down` retain data. Do not use `down --volumes` when it is needed.
Deleting an image is different from deleting a database volume.

## Existing data and recovery

The migration tool discovers actual Compose projects and volume mounts. Review
one candidate, or select among several; manual source entry is used only when
discovery finds none. It stops the selected source, backs it up, converts a
copy, verifies it, then selects the new configuration. Follow the
[migration guide](postgresql-migration.md) for commands and interrupted work.

After migration, operate the printed `installation/compose.json`. Running `up`
in a 0.1.3 checkout does not migrate it. New PostgreSQL changes are not merged
back to SQLite during rollback. Keep a [complete DB/media/secret backup](postgresql-backup.md)
before updates. A World Package is not a full installation backup.

Use separate [contributor data](development.md) for source work and
[Termux/PRoot](termux.md) on Android without Docker. ARM64 checks are separate
from Android power-management certification. Maintainers follow the
[same-source release process](../operations/release-publishing.md).
