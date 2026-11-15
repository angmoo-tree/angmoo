# Angmoo 0.1.5

> Draft, not a published release. Final image identities and Docker/Termux update
> verification must be completed before publication. No 0.1.5 installation command
> is available from this draft.

This update refreshes dependencies and focuses new releases on Docker and experimental Termux.

## What's new

- **Dependencies:** Integrates the five dependency updates, including fixes in pypdf, Next.js, cryptography and websockets, plus Google SDK 3, SQLAlchemy and Ladybug updates. Runtime images also receive Debian security fixes.
- **Google compatibility:** Preserves the existing API behavior, embedding batches and retry policy while handling the SDK's new HTTP transport errors correctly.
- **Supported platforms:** Ends new native Windows installers and official native Windows support. Existing code, manual checks and historical releases remain available.
- **Documentation:** Updates English and Korean installation and contribution guidance to explain supported platforms and data continuity.

## Download and update

- **Docker — amd64 and ARM64:** Follow the [container guide](../../public/container-release.md).
- **Android ARM64 — Termux:** Follow the [Termux guide](../../public/termux.md). Android support remains experimental.
- **Windows:** Use Docker Desktop to start a fresh Docker installation. No Windows-native-to-Docker migration tool is provided; existing conversations, memories, relationships and settings do not transfer automatically. Keep your original installation and backups if you need those records.

Existing Docker/Termux 0.1.4 installations use a PostgreSQL-to-PostgreSQL update. Back up first and retain the data directory or volume; do not repeat the SQLite migration.

## Notes

CI and synthetic provider tests do not establish successful real-device updates. Final candidate validation and versioned download links remain pending. No guarantee is made for every Android device or unlimited workloads.
