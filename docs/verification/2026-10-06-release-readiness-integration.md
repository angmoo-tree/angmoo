# 0.1.0 release readiness integration

This integration publishes the existing `feat/0.1.0-release-readiness` branch for
normal merge into `main`. The starting implementation is
`a26488e219e4041642e9783963c525f1471481ab`; it contains 62 commits after the
initial base `8e6e89d69bd9e98938ef587adfc143bc3fc1ec40`. GitHub PR and main CI
are separate gates and remain pending when this report is first introduced.

## Resulting behavior and scope

- Device preferences retain Korean/English UI and accepted-job language/timezone
  inputs. The shared product viewport supports Phone and wide layouts; Windows
  uses the native window frame and operating-system resize behavior.
- World SNS preserves title/body/image composition, the left-aligned `게시글` /
  `Post` detail header, and replies before the user reply composer. Likes apply
  the server-confirmed count and viewer state to the affected post while
  preserving content, images, drafts, pagination and scroll.
- World Chat diagnostics use the centered shared dialog. Chat list and room
  delete actions use the owning soft-delete workflow and admission checks.
- The World character directory uses the shared management card display,
  current-World membership and user-first ordering. Management profile/status/
  settings and edits use the current World instance. The relationship action
  precedes the message action; graph nodes use profile images and common
  fallbacks. Profile activity statistics stay within the profile content.
- Character imports start from an immutable creation/restored/legacy-transition
  origin. World instances retain independent configuration and autonomy; new
  imports start OFF. Accepted work uses frozen inputs and existing resource,
  permission, revision and execution-lock checks.
- SQLite remains canonical. The formal v29 staged migration recognizes both
  attested early v28 and final v28 sources, validates the target before promotion
  and preserves the previous generation. See the separate
  [SQLite recovery report](2026-10-06-sqlite-v28-startup-recovery.md).

This is an integration of the recorded implementation. It does not claim that
all remaining UI decisions, real-provider quality, installed-app validation or
direct user review are complete. Older global management screens remain
available as references for later status/settings design work.

## Additional compatibility correction before publication

The legacy local character dashboard could return HTTP 500 after a saved profile
with `http://localhost:3000/icon.svg` or its old local-preview equivalent entered
the new typed import/World configuration reader. Synthetic data reproduces the
same `configuration_media_invalid` failure; it is independent of PostgreSQL.

The owning Characters import configuration validator now preserves exact
historical HTTP loopback references only for the shipped `/icon.svg` and the
existing public managed media paths. It does not fetch the URL or rewrite the
stored profile, origin payload or digest. External HTTP, nonpublic local routes,
credentials, query/fragment data, traversal and invalid ports remain rejected.
Profile writes still use the existing owned-media workflow. Existing HTTPS and
relative managed-media contracts remain in force.

The Device dashboard shows counts and the empty-state prompt only after a
successful read. Failed reads show the shared error/retry component and retain
previously loaded cards instead of presenting a confirmed zero-character state.
No additional UI copy, color, dependency, endpoint or database version is needed
for this correction. The implementation follows `frontend/ARCHITECTURE.md`,
`frontend/DESIGN.md` and `backend/ARCHITECTURE.md`.

## Executed local evidence

Evidence lives in the ignored `artifacts/release-readiness-20261006/` directory.
Only synthetic SQLite fixtures and fake/offline browser responses were used.
The existing offline Python guard blocks nonloopback provider connections and
implicit user dotenv/key loading. No operational or installed database was read
or changed during this integration verification.

| Check | Observed result |
| --- | --- |
| Before-fix compatibility regression | 7 failed / 16 passed; expected failures identify the compatibility defect |
| Final focused `test_legacy_configuration_media.py` | 24 passed / 0 failed, including actual agents list/detail and World dashboard/settings routes, immutable origin and stored profile preservation |
| Existing World configuration/import-copy/social-input suites | 36 existing cases passed in the combined run; that run also contained one subsequently corrected new test-fixture failure and is not reported as an overall pass |
| Korean/English browser error-to-success transition | 2 passed / 0 failed; failed read has neither summary nor empty state, retry then confirms a genuinely empty result |
| Frontend lint, typecheck and Next build | Completed successfully; hosted CI must validate the final committed candidate again |
| Backend/frontend ownership boundaries and derived inventories | Passed; the derived import inventory adds only the standard-library `ipaddress` dependency, and the design inventory refreshes the changed source digest without raising color budgets |
| Current-tree secret scan | Fatal findings 0; binary/source asset audit notices retained |
| Complete Git-history secret scan | Fatal findings 0; 49 audit notices, including historical model/screenshot assets, remain visible |
| DCO | Initial branch ancestry passed; final appended commits require signed-off verification before publication |

The new historical fixture seeds a persisted legacy row through SQLAlchemy Core
before exercising reads. The application's immutable snapshot update guard
remains unchanged. The first combined attempt correctly rejected an ORM update
to that immutable row; the fixture was corrected instead of weakening the guard.

Source/checkpoint/node preservation uses the repository's committed, append-only
introduction and exact product-delta records. Frozen checkpoints, test
assertions, original records, CI policies and validator checks are not replaced
to obtain a passing result. Collection/preservation is distinct from executed
tests. Hosted CI, Windows/platform-shell review, PR merge and the exact merged
commit's main CI must be recorded separately in the execution ledger.

## Preservation and publication boundaries

At integration start there are no running Docker containers and the user has
ended the observation session. An isolated frontend preview is task-owned and
stopped after validation. Docker images/containers/volumes, user data, backups
and the Windows installation are preserved. No PostgreSQL test resource is
created and no real LLM, image or embedding request is submitted.

The branch is published with a normal upstream push and a Draft PR. Source
provenance commits are preserved by a normal merge commit; no force push,
history rewrite, administrative protection bypass or direct main push is used.
For native/platform changes, `.github/CODEOWNERS` requires successful target-OS
CI and the user's explicit review for the final candidate before Ready/merge.
The final merged SHA must be reachable from remote main and its main push CI
must finish successfully. UI user checks, installed-app state and real AI
quality remain separate from this Git/CI integration outcome.
