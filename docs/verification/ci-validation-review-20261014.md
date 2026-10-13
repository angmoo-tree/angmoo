# CI validation transition review — 2026-10-14

This record distinguishes selection comparison from a successful full test run. It is not a release approval or an immutable census of test names.

## Hosted observer comparison (R02)

- Source: `bfd1c29f15ce4adbe381d0920362cc1be179789f`; Core checkout: `0fdd9b45667dce5f8cbcec0436952fcaee816508`; tree: `70b53b21a3bc59d4b007c2f8b6afb5d868f4ac57`.
- [Core observer run](https://github.com/angmoo-tree/angmoo/actions/runs/38460303777), [Local Smoke](https://github.com/angmoo-tree/angmoo/actions/runs/38460303501), [Windows Installer](https://github.com/angmoo-tree/angmoo/actions/runs/38460303900).
- The recommended and executed job maps were identical: full backend, frontend, migration, three local smoke paths, Windows build, native, host development and full installer. CI/helper changes conservatively required every scope. The four backend partitions, frontend, migration and native/installer preparation actually started. Existing required names remain result gates; governance remains unconditional.
- This comparison established that activation does not omit a scope for this change. It did **not** establish a full PASS: an old test required exactly four installer artifact references and failed after the representative consumer was added. It now validates source/attempt identity for each actual consumer and its hosted sentinel. Artifact-policy tests now use the frontend worker and the backend aggregate's actual upload condition. No failing product assertion was removed.
- The initial malformed Actions event key was repaired separately. The policy parser now recognizes YAML 1.2 booleans and rejects `true:` as an event key.
- Active mode is enabled after this comparison. This PR still selects full because it changes shared CI/build policy. Scoped selection has separate positive/negative tests, including real collection, empty individual partitions, missing nodes, wrong attempts and failure/cancellation propagation. The final full result is required independently.

## Test decisions and measured cost

The current-risk decisions and replacement tests are in [the CI guide](../operations/ci-validation.md). Three completed migration replay/count modules were retired; current Chat/runtime owners, authorization, data, cancellation and installation protection remain. The search timeout test covers acknowledged NN progress and deliberately missing progress without changing the production deadline or nonblocking protocol.

[The setup-uv baseline Core run](https://github.com/angmoo-tree/angmoo/actions/runs/38456529930) completed successfully. Its first backend partition took 1,425.78 seconds for 1,581 passed and 14 skipped tests. The removed historical Chat/public-factory replays included individual cases of approximately 50–96 seconds. The existing immutable Git evidence cache remains; current candidate/source analysis is not cached across edits. Four partitions are retained pending evidence that rebalance is worthwhile.

Frontend Next/static/shell checks, synthetic providers and installation fixtures are retained because they cover real delivery paths. Supported predecessors remain the entire schema-derived range (currently 1–36); shared PE bytes are verified once while each database fixture remains independently writable. An old schema or synthetic test input is not itself grounds for deletion.

## Completion boundary

During hosted execution of `8c68292d`, Local Smoke's ten-request SQLite test encountered the existing 250 ms bounded busy response at `BEGIN IMMEDIATE`. A local run reproduced the same admission-contract issue in its outbox companion. The fixture now verifies permitted busy responses separately from successful claims, preserves the single-write/owner invariant, and checks explicit duplicate redelivery after contention. A held-writer case proves no partial write on refusal. Production concurrency policy is unchanged. Full success still requires rerunning the affected final source.

The baseline event journals quantify 117 retired replay/count nodes across the four partitions: 598.42, 724.26, 672.87 and 837.70 worker-seconds respectively (2,833.25 summed worker-seconds). These run in parallel; the sum is not elapsed-time savings. This supports removing completed historical obligations instead of increasing the partition count.

At this commit, final hosted full execution, human platform review of the narrow setup-uv PR, normal merges, post-merge checks and fixed-main candidate verification remain pending. Local focused tests and observer selection are not substitutes. The live run ledger and raw local evidence are under `artifacts/ci-modernization-20261014/`; final measured timings and remote results will be appended after completion. No release is published and no developer installation or user data is modified.
