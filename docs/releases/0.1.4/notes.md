# Angmoo 0.1.4

Angmoo now uses PostgreSQL for local data and search, with an explicit migration path for official 0.1.3 installations.

## What's new

- **Local storage and search:** App data, activity checkpoints and keyword search use PostgreSQL. Semantic memory search uses exact pgvector similarity search. Docker and Termux run frontend, backend and PostgreSQL; the Windows installer includes and manages a private PostgreSQL server.
- **Memory and relationship processing:** Background memory saving and relationship review share one execution queue. Completed results remain saved, and failed work can be retried manually or ended without retrying. SNS and Chat retain the input captured when an activity starts.
- **Installation and recovery:** Added 0.1.3 migration tools for Docker and Termux and a first-launch migration prompt for Windows. Improved Windows initial preparation, interrupted-migration recovery and PostgreSQL read transactions.
- **Documentation:** Updated the English and Korean READMEs, memory/search diagrams and installation, migration and recovery guides.

## Download and update

- **Windows x64:** [Download the installer](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.4/Angmoo_0.1.4_x64-setup.exe). Install the program, then launch Angmoo and confirm data migration. Program installation and data migration are separate steps. Follow the [Windows migration instructions](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.md#windows-x64-installer).
- **Docker — amd64 and ARM64:** Follow the [installation guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/container-release.md). Existing 0.1.3 users should run the [migration tool](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.md), which detects existing projects and asks you to confirm or select one.
- **Android ARM64 — Termux:** Follow the [Termux guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/termux.md) and its migration instructions. Android support remains experimental.

Back up your complete Angmoo data before updating. Direct migration supports official 0.1.3 only. Keep the original SQLite data and backups until you have checked the new environment; changes made in PostgreSQL are not copied back to 0.1.3.

## Notes

- Existing memories whose original text cannot be verified during migration keep their summaries and an explicit unavailable-original state. New memories follow the snapshot policy described in the README.
- macOS-host migration has not been qualified for official support. ARM64 image availability does not establish that host-specific migration result.
- The previously reported chat-image sizing and new-World language-default issues are outside this release's fixes.
- The Windows installer is not Authenticode-signed. Checksums and GitHub build-provenance attestation are included; these are separate from Windows publisher signing. See the [validation record](https://github.com/angmoo-tree/angmoo/blob/main/docs/releases/0.1.4/verification.md) for the tested platforms and remaining limits.

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.3...release-v0.1.4)
