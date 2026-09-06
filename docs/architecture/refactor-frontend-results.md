# Frontend refactor execution results

Current: **AR-F2-0 IN PROGRESS; AR-F2-A through AR-F5-B NOT STARTED**.
The user delegated implementation, validation, PRs and merges. AR-X, P8-L-S,
real-provider product verification, Release and Production remain separate.

## Starting point — 2026-09-07

- Local and fetched origin/main: `33e9df8593272f6c81236c477ae73ef057d0d3dd`.
- Clean product worktree before creating `refactor/ar-f2-0-frontend-foundation`.
- Preserve PR258, PR263 and the append-only backend evidence; PR290 is the
  additive frontend checkpoint, not a replacement baseline.
- Frontend stock: 324 tracked source/support/test/asset files. The checkpoint
  is independently reproduced from pinned Git source; browser assertions,
  fixture payloads, visual snapshots, locks and public assets remain protected.
- Existing frontend boundary: PASS, 13 features, zero legacy exception edges.
  This is partial migration coverage (Device Home), not full feature independence.
- Existing design gate: PASS, raw colors 1408, 33 tracked color files, 18 surfaces,
  zero route gaps, 11 screenshots. No visual baseline changed.

## AR-F2-0 implementation

- Add a final whole-tree boundary mode, initially inactive. It discovers new
  features/common files and static-shell entries, rejects reverse/sibling/test
  imports, unreferenced old roles, calculated imports and transitive server
  dependencies in common screens. Existing partial-scope rules remain active.
- Add the PR290 frontend stock/consumer preservation gate to Security CI.
- Connect frontend, browser tests and boundary policy inputs to both automatic
  Windows Host events; regressions check each event independently.
- Correct frontend stage ownership in K01–K24 and existing exact bridges.
  Backend per-item status and its completion evidence are not reset.
- The first focused run found a Windows root-relative path issue: `/absolute.ts`
  was not classified as absolute by Path.is_absolute. Explicitly reject root and
  drive prefixes; retain the original failing test. Rerun: **81 passed in 0.98s**.
- Capture/check: **324 files PASS**. Partial frontend and Windows Host contract
  checks: **PASS**. These are local checks, not PR/merge/post-merge completion.
- Existing stock: **2709 protected lineages / 2740 collected / 37 items PASS**;
  the additional 31 nodes are this preparation's boundary/preservation tests.
- Browser collection only: web 21, static 68, Local Settings 2, visual 36.
  These counts are configuration-specific, not browser execution results.
- Node 24.19.0 with installed dependencies: frontend-directory ESLint and
  TypeScript checks PASS; Node World Package proxy check PASS. The first ESLint
  invocation from repository root emitted a Next pages-root warning; the correct
  frontend working directory completed without it. The local pnpm shim and
  existing node_modules use 11.19.0; canonical CI remains pinned to 11.22.0.
- CI policy, secret-allowlist metadata, backend import inventory, deferred
  inventory, L4 current inventory and Memory batch current inventory PASS.
- Actual Next browser regression: **21 passed in 54.6s**, including World Chat,
  Memory owner controls, Social/profile/letter, legacy Messages and Relationship
  Graph. These use synthetic API fixtures; no real provider calls were made.
- Next production build PASS. Introduction commit
  `74ce61a2269bf48b9d084af587597199574345e3` is recorded in the append-only
  ledger: **5 new source files / 31 test nodes**.

## How to run the added guard

From the repository root, with the locked backend environment:

```powershell
uv run --project backend python scripts/ci/check_refactor_frontend_preservation.py
uv run --directory backend python -m pytest -q tests/test_refactor_frontend_foundation.py
```

`--capture` is one-time initialization and refuses to overwrite the checkpoint.
The checkpoint uses pinned PR290 source; it must not be refreshed after a move.
Current path changes belong in `security/refactor_path_map.json`. The stock gate
protects files/consumer oracles; actual browser/native runs prove behavior.

## Pending before AR-F2-0 closeout

- Exact-head CI, PR, merge and post-merge verification.
- Continue AR-F2-A only after this preparation unit is integrated.

## Temporary-file cleanup

User authorized cleanup of obsolete backend-refactor temporary files. Check
actual worktree/process consumers and document/evidence links first. Preserve
supported migration/extension code, user data, backups and referenced evidence.
Record exact removed paths and reasons when cleanup is performed; no deletions
have been performed in this preparation change.
