# Angmoo 0.1.3

This update fixes a Termux startup problem that could prevent Angmoo from starting again after an interrupted run.

## What's new

- **Termux startup:** Unfinished log sessions are now recovered after confirming that their previous processes have ended. Old log records no longer block startup simply because an interruption left no closing timestamp.
- **Clearer installation messages:** If installation finishes but the server cannot start, the installer now explains which step failed and where to check the saved logs.
- **Documentation:** Updated the English and Korean installation guides with recovery and data-preservation guidance.

## Download and update

- **Windows x64:** [Download the installer](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.3/Angmoo_0.1.3_x64-setup.exe).
- **Docker — amd64 and ARM64:** Follow the [installation guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.3/docs/public/container-release.md).
- **Android ARM64 — Termux:** Follow the [Termux guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.3/docs/public/termux.md). Android support is experimental.

Before updating, back up your Angmoo data and follow the instructions for your installation. Keep your existing data directory or Docker volume.

## Notes

- The Windows installer is not code-signed, so Windows may show an unrecognized-publisher warning. Download it from this official release.
- If a previous process is still running or its state cannot be confirmed, Angmoo keeps the logs and prevents a second server from starting. Interrupted logs may be incomplete and remain subject to the existing retention limits.
- Android power and memory policies can still interrupt background operation. This update does not prevent Android from terminating Termux.

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.2...release-v0.1.3)
