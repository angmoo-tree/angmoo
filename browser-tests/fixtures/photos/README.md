# First-party synthetic photo fixtures

These test files were created from solid colors/rectangles and synthetic metadata
for the 2026-10-10 local photo contract. They contain no real users, photographs,
credentials or provider output and are Angmoo first-party test data.

- `normal.jpg`: 320 × 240 colored rectangles.
- `orientation6.jpg`: 320 × 240 with EXIF orientation 6, displayed 240 × 320.
- `large.jpg`: 6,000 × 4,000 synthetic pixels for proportional scaling.
- `alpha.png`: 320 × 240 RGBA, corner alpha 64.
- `primary.heic`: 320 × 240 primary HEVC still of synthetic rectangles, generated
  locally from synthetic pixels with libheif; no external AI.

Exact SHA-256 values are checked in `security/frontend_design_policy.json`. These
are diagnostic pixels, not canonical product screenshots. Prepared copies and
screenshots are written only to ignored `artifacts/`, not user storage.
