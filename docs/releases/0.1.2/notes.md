# Angmoo 0.1.2

This update improves photo attachment and profile previews, and fixes how
characters use your SNS interactions in activities and conversations.

## What's new

- **Photo uploads:** Improved reading of photos selected on Android across
  posts, Chat, profiles, Worlds and image references. Each feature keeps its
  existing size limits, and unreadable files have clearer error messages.
- **Profile previews:** Saved avatars and banners update immediately, including
  when replacing an existing image, without refreshing the page.
- **SNS and Chat:** Fixed failures when Routine activities use user comments
  and when memory-enabled Chat uses likes or unlikes from today's SNS activity.
- **Memory and Worlds:** Memory management lists AI characters rather than
  your user profile. New Worlds use `No role` and an English default description;
  existing roles and their stored text are preserved.
- **Termux guidance:** Added Samsung's memory-cleaning exclusion setting to
  the English and Korean README setup instructions.

## Download and update

- **Windows x64:** [Download the installer](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.2/Angmoo_0.1.2_x64-setup.exe).
- **Docker — amd64 and ARM64:** Follow the [installation guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.2/docs/public/container-release.md).
- **Android ARM64 — Termux:** Follow the [Termux guide](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.2/docs/public/termux.md). Android support is experimental.

Back up your Angmoo data before updating and keep the same data directory or
Docker volume. For a custom Termux data home, follow its update instructions;
the default installer does not automatically select that home.

## Notes

- World packages containing the new English default role may not import into
  0.1.1. Use 0.1.2 or later to read those packages.
- The Windows installer is not code-signed; Windows may show an unknown
  publisher warning. Download it from this official release.
- Android power and memory policies can interrupt background activity. This
  release does not certify uninterrupted screen-off operation on every phone.

[Full changelog](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.1...release-v0.1.2)
