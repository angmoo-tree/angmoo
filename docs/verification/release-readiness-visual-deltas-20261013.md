# Versioned product visual evidence — 2026-10-13

This records intended product changes already implemented on the release-readiness
branch. It does not replace the immutable UI-B/UI-F checkpoint, change screenshot
tolerance, or certify a new human USER CHECK. The original 11 PNGs remain byte-for-byte
unchanged. Eight additional images live under `snapshots/ui-f/release-readiness-20261013`.
The same expected images are compared by production Next and static export.

## Reason for the new version

The original UI-F captures predate the user's requested Device Home navigation,
World Feed composition, embedded Relationships, and World usage/deletion changes.
Reverting those implementations solely to match the old PNGs would undo the product
contract in `frontend/DESIGN.md`. Updating the old PNGs would lose the original oracle.
The new namespace retains both versions and makes each intentional change reviewable.

| New capture | Existing implementation and expected difference |
| --- | --- |
| Device Home, 360×800 and centered 1440×1000 | `00c7facf` and `66fe9812`: current Angmoo wordmark and no global bottom navigation on Home. World launchability remains separate from runtime health. |
| Runtime unavailable, 390×844 | The same Home layout; the real degraded state remains visible while launchable World entries remain available. |
| World Feed, 436×880 | `66fe9812` and `c7f540cd`: content header with current World profile, post body guidance, and no fixed original-image preparation explanation. The title, compact composer, feed rows and five World destinations remain. |
| Creator Studio populated and empty, 1440×900 | `7e3f3625`: groups use local usage state, deletion is payload-backed, and current empty-state copy is retained. The wide Studio shell remains. |
| Relationships ready and degraded, 1440×900 | `6e66c25b` and `66fe9812`: relationships are embedded in the World shell with five destinations. Direction, current graph status, canonical fallback and relationship-review controls remain. |

All listed commits are actual ancestors of the branch; full source/blob references
and the later test alignment are verified by append-only committed provenance.
No actual user's media, data, database or provider output is part of these images.

## Fixture and execution boundaries

- The deterministic visual server now supplies an empty active-deletion receipt list
  and the server-backed deletion capabilities in its synthetic Studio rows. Previously
  the missing read produced a spurious deletion error. That error is asserted absent;
  an enabled delete action is asserted before capture. No deletion is executed.
- The embedded graph tests assert the actual content owner, five World destinations,
  ready/degraded states and absence of the retired independent graph shell.
- Chromium and the canonical Ubuntu Playwright container are pinned by the existing
  policy. Viewports, reduced-motion behavior, fixed time, local fonts, authentication,
  provider blocking, read-only audit and 25-pixel/0.1 comparison limits are unchanged.
- Only the five changed Next test cases created the eight previously absent versioned
  images. Creation is not a parity PASS. The subsequent 36-test run performs ordinary
  comparisons without snapshot updates across both runtimes, including unchanged
  semantic primitives, global Feed and autonomy images.
- The inventory contains the historical 11 plus the new eight images (19 total).
  The 61 screenshot call mappings and raw-color limits remain unchanged. The exact
  new asset introduction and browser source changes follow their implementation
  commit in the append-only evidence ledger.

The corrected-head hosted CI, final platform review, main merge/CI and installed
USER CHECK are recorded separately in the PR and execution ledger.
