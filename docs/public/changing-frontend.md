# Changing the frontend

Keep API access in `src/lib`, preserve loading and error states, and test at
mobile and desktop widths. Run lint and both public-image-disabled and
private-image-enabled builds.

Do not add remote build-time fonts, unapproved assets, or default external
image requests. A public page must load without production data or provider
credentials and must not expose admin, maintenance, or agent-tools controls.
