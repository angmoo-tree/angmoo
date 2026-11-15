# Run Angmoo with Docker

> **0.1.5 support policy:** Docker (Linux amd64/ARM64, including Windows Docker Desktop) and experimental Termux ARM64 remain supported. New Windows native installers and official native support end with 0.1.5. Existing EXEs, source and manual workflows are retained. No Windows-native-to-Docker data migration tool is provided: Docker starts a separate empty environment. Keep your old installation and backup if you need its data. Existing Docker/Termux 0.1.4 users update with their data preserved; do not run the SQLite migration again. 0.1.5 commands require the corresponding official release to be published.

English | [한국어](container-release.ko.md)

This is the 0.1.5 source configuration for Linux amd64 and ARM64. The versioned
assets become available after formal publication. Existing 0.1.3 users must
first migrate to 0.1.4 with the [historical migration tool](postgresql-migration.md), then follow the 0.1.4 update steps below.

## New installation

Use Git, Docker with a Linux engine, and Compose 2.23.0 or newer.

```sh
git clone --branch release-v0.1.5 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

Open http://127.0.0.1:3000. Frontend, backend and PostgreSQL use the same product
version/source. The database port is private. PGDATA, app media/secrets and DB
bootstrap credentials have separate persistent volumes. See the
[runtime contract](postgresql-runtime.md).

## Update from 0.1.4

0.1.4 already uses PostgreSQL. Back up its [database, media and secrets](postgresql-backup.md) before updating; no SQLite converter is needed.

Run `docker compose ls` and identify the project and Compose file you already use. A standard installation uses `compose.yml`; an installation migrated from 0.1.3 uses the printed `installation/compose.json`. Keep that file, project name, data volumes, ports and secret mounts. Starting a new project would show a separate empty installation.

Save this small override as `angmoo-0.1.5.yml` beside the existing Compose file:

```yaml
services:
  postgres:
    image: ghcr.io/angmoo-tree/angmoo-postgres:release-v0.1.5
  backend:
    image: ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.5
    environment:
      ANGMOO_VERSION: 0.1.5
  frontend:
    image: ghcr.io/angmoo-tree/angmoo-frontend:release-v0.1.5
```

Replace `EXISTING_PROJECT` and `EXISTING_COMPOSE` below with those existing values. Quote a path containing spaces. The first command downloads all three images before the current services stop.

```sh
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml pull
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE stop
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml up -d --wait
```

Use both `-f` files for later starts and restarts. Open the same address as before, then check your Worlds, characters and saved data. Keep the backup and old images until you have checked the update. For rollback, restore the complete 0.1.4 backup with its matching images; do not attach older images to changed data. Do not use `down --volumes` or delete credentials.

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
