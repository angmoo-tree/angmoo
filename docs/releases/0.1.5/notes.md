# Angmoo 0.1.5

This release updates dependencies, includes security and compatibility fixes, and focuses supported installation paths on Docker and experimental Termux.

## What's new

- **Security fixes:** Update PDF handling, the Next.js web runtime, cryptography and WebSocket dependencies, and affected container packages.
- **Compatibility:** Update Google GenAI 3, SQLAlchemy 2.1, Ladybug 0.22 and related dependencies. Preserve the existing Chat, SNS, memory and relationship workflows with the updated libraries.
- **PostgreSQL setup:** Create missing search structures during installation or update while preserving existing memories and the restricted serving role.
- **Documentation:** Clarify the English and Korean installation, update and support guidance, including when a Termux installation is ready to open.

## Download and update

- **Docker — Linux amd64 and ARM64:** Follow the [installation and update guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.5/docs/public/container-release.md). Windows users can use Docker Desktop.
- **Android ARM64 — Termux:** Follow the [Termux guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.5/docs/public/termux.md). Android support remains experimental.

**Existing Docker and Termux 0.1.4 users:** Back up your installation and follow the PostgreSQL update steps. Keep the existing data directory or Docker volumes. Do not repeat the SQLite migration.

**Native Windows installations:** New native Windows installers and official native support end with 0.1.5. Historical releases, source and manual development workflows remain available. No Windows-native-to-Docker migration tool is provided. Docker starts a separate empty environment; conversations, memories, relationships and settings do not transfer automatically. Preserve your original installation and backups if you need those records.

## Notes

- Existing SQLite 0.1.3 installations must first follow the [historical 0.1.4 migration guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.md).
- See [verification scope and known limits](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md) and [source and release integrity information](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md#source-and-artifact-integrity).

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.4...release-v0.1.5)
