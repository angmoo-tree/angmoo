# Run Angmoo with Docker

Angmoo 0.1.0 provides backend and frontend images for Linux amd64 and ARM64:

- `ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.0`
- `ghcr.io/angmoo-tree/angmoo-frontend:release-v0.1.0`

Use both services from the same release. The multi-platform tag selects the
matching execution image; its architecture manifests and layers are part of the
image, not extra application versions.

## Install and start

Install Git and Docker with Compose 2.22.0 or newer, then run:

```sh
git clone --branch release-v0.1.0 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

Open http://127.0.0.1:3000. The frontend is exposed on loopback; the backend and
its embedded SQLite/search/graph components run through the supported Compose
configuration. A Docker installation does not need separate PostgreSQL or Neo4j.

## Status, logs and stop

```sh
docker compose ps
docker compose logs --tail 100 backend frontend
docker compose down
```

The normal stop command preserves the named data volume. Do not add `--volumes`
when you need the data. Image cleanup, container cleanup and volume deletion are
different operations. Never remove a volume merely to fix a failed image pull.

## Updates and data

Record the release checkout, Compose project name and data-volume binding. Before switching versions, stop through Compose and back up the complete
data set, including the installation secret and media. Use the next release's
actual upgrade instructions and a matching backend/frontend pair.

Application images and user data have separate lifetimes. Supported embedded
migrations validate and promote data generations at startup; this is not a
promise that every arbitrary downgrade or future version is compatible. Do not
create a new empty project/volume and mistake it for a data-preserving upgrade.

`ANGMOO_IMAGE_TAG` selects the versioned image tag. Product version and data
schema version are separate; do not use old development values or override a
version check to force startup. World Package export is not a full backup.

## Development and release maintenance

For source development use [the contributor environment](development.md), with
its separate data volume. For candidate generation, identity and publication
use [release publishing](../operations/release-publishing.md) and
[candidate import](../operations/release-candidate-import.md).

Android uses [Termux and PRoot](termux.md), not Docker on the phone. Linux
ARM64 compatibility does not certify Android background or Doze behavior.
