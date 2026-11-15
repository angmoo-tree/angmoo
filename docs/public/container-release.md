# Run Angmoo with Docker

> **0.1.5 support policy:** Docker (Linux amd64/ARM64, including Windows Docker Desktop) and experimental Termux ARM64 remain supported. New Windows native installers and official native support end with 0.1.5. Existing EXEs, source and manual workflows are retained. No Windows-native-to-Docker data migration tool is provided: Docker starts a separate empty environment. Keep your old installation and backup if you need its data. Existing Docker/Termux 0.1.4 users update with their data preserved; do not run the SQLite migration again.

English | [한국어](container-release.ko.md)

This guide uses the published 0.1.5 configuration for Linux amd64 and ARM64. Existing 0.1.3 users must
first migrate to 0.1.4 with the [historical migration tool](postgresql-migration.md), then follow the 0.1.4 update steps below.

## New installation

Use Git, Docker with a Linux engine, and Compose 2.23.0 or newer.
Run this in an environment without an existing Angmoo installation. Existing 0.1.4 users should follow **Update** below.

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

0.1.4 already uses PostgreSQL. Back up its [database, media and secrets](postgresql-backup.md) first. Do not run the SQLite migration again. Follow **one** of the two paths below. Run commands one at a time and stop if a command fails.

### A. A standard 0.1.4 installation cloned with Git

1. Open a terminal in the **existing `angmoo` checkout used for installation**. Do not clone into a new folder.
2. Run `docker compose ls --all` to confirm the existing project and configuration. The default project is `angmoo`. If you previously used another name with `-p`, use that same `-p NAME` in every `docker compose` command below. Keep your `.env` and existing volumes.
3. If `.env` or your shell explicitly sets the version, update it to `ANGMOO_IMAGE_TAG=release-v0.1.5` and `ANGMOO_VERSION=0.1.5`. There is no need to add these if you use the defaults.
4. Run the following commands in order. If Git reports conflicting local changes, stop and preserve them; do not force a reset. Use B below if you edited Compose or use multiple configuration files.

```sh
git fetch origin tag release-v0.1.5
git switch --detach release-v0.1.5
docker compose pull
docker compose up -d --wait
docker compose ps
```

Open the same address (default http://127.0.0.1:3000) and check your Worlds, characters, memories and conversations. `up` replaces the services in the same project and reconnects their existing data volumes. Repeating `git clone` fails when the folder already exists; update the Compose version with the steps above instead.

### B. An installation migrated from 0.1.3 or using custom Compose configuration

Run `docker compose ls --all` to identify the existing project and actual configuration files. A migrated installation uses the `installation/compose.json` printed by the migration tool. Keep the existing files, project name, data volumes, ports and secret mounts. A new project would show a separate empty installation.

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

Replace `EXISTING_PROJECT` and `EXISTING_COMPOSE` below with those existing values. Quote paths containing spaces. If you already use multiple `-f` files, retain them in the same order and append the new override last. The first command downloads all three images before the current services stop.

```sh
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml pull
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE stop
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml up -d --wait
```

Use the same `-p` and all `-f` files for status, stop and start too. For example:

```sh
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml ps
```

Open the same address as before, then check your Worlds, characters and saved data. Keep the backup and old images until you have checked the update. For rollback, restore the complete 0.1.4 backup with its matching images; do not attach older images to changed data. Do not use `down --volumes` or delete credentials.

## Status and stop

These commands assume the default project and a single `compose.yml`. Keep the same `-p` if you use a custom project name. If you used B above, include the same `-p` and all `-f` files in each command.

```sh
docker compose ps
docker compose logs --tail 100 postgres backend frontend
docker compose stop
docker compose up -d --wait
```

`stop` and `down` retain data. Do not use `down --volumes` when it is needed.
Deleting an image is different from deleting a database volume.

## Historical 0.1.3 SQLite migration and recovery

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
