# Local stability PR CI follow-up (2026-10-20)

This report supplements the local implementation report for PR #393. Remote
checks, main integration, immutable candidates, and user first-launch checks are
separate gates. No existing Docker stack or installed Angmoo was started or changed.

## Causes and corrections

- The temporary manual-slot cleanup accidentally received an automatic recovery
  reader that its service does not accept. Remove that argument at runtime
  composition; retain the reader on automatic expired-lease recovery. Successful
  and failed run-once requests return temporary slots without enabling autonomy.
- Current metadata assertions now cover schema v40 / 181 canonical tables and
  Alembic `20261019_0117`. Historical revision hashes and v1-v39 manifests are
  unchanged. The v39 schema test explicitly constructs v39, with v40 tested too.
- Native supported-upgrade fixtures include v39. Only synthetic predecessor
  construction removes v40's connection table and rebuilds the historical session
  table (including its constraints/indexes), preserving any session rows. The
  existing exact schema digest, foreign keys, credential bytes, message survival,
  drift rejection, and real forward migration assertions remain enforced.
- Registration/profile fixtures explicitly confirm their synthetic environment
  before default World/profile creation. Timezone tests edit the fixture's existing
  environment instead of inserting a duplicate owner row. No product admission
  check was relaxed.
- Cancellation fixtures include the canonical graph-run table and supply explicit
  shutdown intent. Unknown cancellation is not mislabeled as shutdown.
- Source wiring tests follow the common local-entry API/controller while still
  requiring `/auth/me`, loopback restrictions, native launcher header checks,
  runtime-change invalidation, and event unsubscription.
- The new local connection table is installation-scoped, like installation
  identity; deletion inventory records retention of connection intent and no
  character ownership. Account-session deletion and deleted-owner rejection remain
  unchanged.
- The static Phone geometry test waits for the app list to be usable after local
  preparation. Pixel/geometry thresholds and native invocation assertions are
  unchanged; the previous failure measured a hidden loading subtree.
- Current generated inventories were regenerated from reviewed source. Frozen
  predecessor inventories were not rewritten.

## Focused validation

- Manual temporary-slot success/failure, autonomy OFF, and shutdown cleanup: 5 passed.
- New v39 predecessor generation/credential-preserving migration to v40, v40 schema,
  scheduler fixture, local-entry protocol/security, and account deletion: 23 passed.
- Current inventory, native matrix completeness, browser-session/static wiring,
  and privacy table classification: 51 passed.
- Static Tauri Phone geometry/delegation regression: 1 passed against the current
  production static build.
- Architecture inventory/boundaries, current L4 ownership, frozen Memory batch and
  current hybrid successor, embedded runtime inventory, and diff whitespace: passed.

Counts are overlapping test groups, not a combined coverage score. A targeted
replay of prior remote failures is recorded separately. The latest PR SHA must
still pass its required remote checks before merge. Actual ARM64 first launch,
native installed-app user checks, and real AI behavior are not claimed here.
