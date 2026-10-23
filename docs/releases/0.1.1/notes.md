# Angmoo 0.1.1

This update makes Termux startup simpler and refreshes the installation and
everyday-use guides.

## What's new

- **Termux startup:** After setup, use `angmoo start`, `angmoo status` and
  `angmoo stop` directly in the current or a new Termux shell. No shell profile
  edit is needed, and the existing full-path commands continue to work.
- **Existing installations:** New tools can check an existing 0.1.0 installation
  against its own version information. Update instructions explain how to keep
  the same data directory, including a custom installation home.
- **Documentation:** Updated the English and Korean READMEs and installation
  guides to make setup and everyday use easier to follow.

## Download and update

- **Windows x64:** [Download the installer](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.1/Angmoo_0.1.1_x64-setup.exe).
- **Docker — amd64 and ARM64:** Follow the [installation guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.1/docs/public/container-release.md).
- **Android ARM64 — Termux:** Follow the [Termux guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.1/docs/public/termux.md). Android support is experimental.

Before updating, back up your Angmoo data and follow the instructions for your
installation. Keep your existing data directory or Docker volume. The default
Termux installer does not automatically select a previous custom data home.

## Notes

- Android power and memory policies can interrupt background activity. This
  release does not certify uninterrupted screen-off operation on every phone.

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.0...release-v0.1.1)
