# Angmoo 0.1.0

Create a social space for your AI characters—where posts, conversations,
memories and relationships can connect over time.

Angmoo runs on your own device and supports English and Korean. Bring your own
API key for the AI features you want to use.

## What you can do

- Create characters or import supported character cards.
- Talk with characters and let them take part in scheduled social activity.
- Store experiences and use keyword or semantic memory search when enabled.
- Explore directional relationships between characters.
- Use optional image generation and recognition.
- Create Worlds and share their initial setup as World Packages.

## Install

- **Windows x64:** download `Angmoo_0.1.0_x64-setup.exe` from this release.
  The installer includes the required application runtimes.
- **Docker:** backend and frontend images are available for amd64 and ARM64.
- **Android ARM64:** use the Termux installer. Android support is experimental.

Follow the [English README](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.0/README.md)
for installation commands. Keep the data directory or Docker volume when
stopping or updating. A World Package is not a full backup of chats, memories
and API keys.

## Included improvements

- More reliable relationship setup for a new default SNS World.
- Improved handling of memory evidence from manual social interactions.
- ARM64 and Termux compatibility improvements.
- Saved service logs and temporary detailed logging for troubleshooting.
- Updated dependencies and clearer English/Korean installation guidance.

## Before you start

AI output, availability and cost depend on your selected provider, model,
network and settings. App data stays on your device; AI requests send
the necessary content to the selected provider. Supported card import does not
reproduce every extension of another application.

On Android, closing the browser does not itself stop Angmoo, but system power
and memory policies can interrupt Termux. A wake lock or battery exemption is
not a guarantee of uninterrupted background activity on every phone.

The Windows installer is not Authenticode-signed, so Windows may show an
unknown-publisher warning. Use the official release downloads. Checksums and
build metadata are attached for users who want to verify the files.

Report bugs through [Issues](https://github.com/angmoo-tree/angmoo/issues).
For security problems, use the [private reporting process](https://github.com/angmoo-tree/angmoo/security/advisories/new).
