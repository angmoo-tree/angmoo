# Angmoo 0.1.5

This release updates dependencies, includes security and compatibility fixes, and focuses supported installation paths on Docker and experimental Termux.

## What's new

- **Security fixes:** Update PDF handling, the Next.js web runtime, cryptography and WebSocket dependencies, and affected container packages.
- **Compatibility:** Update Google GenAI 3, SQLAlchemy 2.1, Ladybug 0.22 and related dependencies. Preserve the existing Chat, SNS, memory and relationship workflows with the updated libraries.
- **PostgreSQL setup:** Create missing search structures during installation or update while preserving existing memories and the restricted serving role.
- **Documentation:** Clarify the English and Korean installation, update and support guidance, including when a Termux installation is ready to open.

## Download and update

- **New installation:** Follow the [Docker setup](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/container-release.md#new-installation) or [Termux setup](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/termux.md#first-installation). Docker supports Linux amd64/ARM64 and Windows Docker Desktop; Android ARM64 support remains experimental.
- **Update Docker 0.1.4 → 0.1.5:** Back up first, then follow the [update steps](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/container-release.md#update-from-014) in the **existing installation folder**. Keep the same project, volumes and settings; do not repeat `git clone`. The guide separates standard Git installations from migration-generated Compose configurations.
- **Update Termux 0.1.4 → 0.1.5:** Back up, run `angmoo stop`, then use the [same official installer as a new installation](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/termux.md#update-while-keeping-the-same-data-home). It keeps the selected data home and starts automatically. Follow the separate instructions if you explicitly use `--home`. Preparation continues after `Installed; run angmoo start.`; wait for `Ready` and the address.

These PostgreSQL updates do not require SQLite migration. Open the existing address and check your Worlds, characters, memories and conversations.

**Native Windows installations:** New native Windows installers and official native support end with 0.1.5. Historical releases, source and manual development workflows remain available. No Windows-native-to-Docker migration tool is provided. Docker starts a separate empty environment; conversations, memories, relationships and settings do not transfer automatically. Preserve your original installation and backups if you need those records.

## Notes

- Installation and update instructions were clarified after publication. The links above point to the corrected documentation; the 0.1.5 product tag, images and downloads are unchanged. Attached notes retain their original publication text.
- Existing SQLite 0.1.3 installations must first follow the [historical 0.1.4 migration guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.md).
- See [verification scope and known limits](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md) and [source and release integrity information](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md#source-and-artifact-integrity).

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.4...release-v0.1.5)
