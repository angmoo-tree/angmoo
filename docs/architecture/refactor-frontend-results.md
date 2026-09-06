# Frontend refactor execution results

Current: **AR-F2-0 COMPLETE; AR-F2-A PR #292 MERGED, post-merge checks pending;
AR-F2-B PR preparation and validation; AR-F2-C through AR-F5-B NOT STARTED**.
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
- PR #291 first Linux architecture check failed because Windows `git archive`
  honored `core.autocrlf=true`. Read the same pinned Git commit with explicit
  `core.autocrlf=false` and `core.eol=lf`; correct the initial unmerged checkpoint's
  308 text fingerprints from that commit, with all 324 paths and binary assets
  unchanged. This does not recapture current product code after migration.
  Both host configurations are now tested against `git show` bytes:
  **33 preparation tests passed**. Tauri static build also PASS locally.
- Corrected frontend preservation also PASS in a Linux container. Static browser
  regression: **68 passed in 41.7s**; fixture-based native bootstrap, shutdown,
  scoped Chat/Memory, media authentication and direct-open routes are preserved.

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

## AR-F2-0 integration

- PR #291 head `1daca62035f4d2eb7f938d30f073cd280b540dea`: **23/23 checks
  SUCCESS**, including all five installer gates. Latest-head backend CI:
  **2720 passed / 22 skipped**. Frontend CI: web 21, Settings 2, static 68 and
  fixed-environment visual 36 PASS; lint, typecheck, proxy and both builds PASS.
- Merged as `72b6573898ad4a720125aba2905327f49aa7fbd2`. Post-merge Actions are
  running and remain separate from the successful PR checks. AR-F2-A starts
  from that integrated commit; its PR will not close before predecessor checks.

## AR-F2-A common UI

- Move 15 existing files into `components/ui`, `styles`, `hooks` and `utils`.
  JSX, semantic values, focus/keyboard behavior, image failure fallback and
  scroll lifecycle stay unchanged. Existing shared public exports lead to the
  canonical implementation until their feature consumers migrate.
- ProfileAvatar uses the already-canonical safe media helper and runtime media
  hook directly; new common modules do not import old shared implementations.
- Move the real source-contract paths and design markers with their consumers.
  Do not rewrite historical source checkpoints or browser/visual assertions.
- Local boundary/stock PASS; design remains **1408 raw colors / 33 files /
  18 surfaces / 11 screenshots**. Related existing regressions: **94 passed**.
  TypeScript and ESLint PASS. Next production and static builds PASS; web
  **21 passed in 48.7s**, static **68 passed in 33.8s**. All 15 implementation/CSS
  bodies match pinned PR290 after excluding import declarations and normalizing
  checkout line endings. PR #292 at `51b2c1a1` passed frontend CI: web 21,
  Settings 2, static 68 and fixed-Linux visual 36. Native checks remain pending.
- The first full preservation run detected 15 stale K01/K24 current paths;
  update only the current/target path arrays and retain historical classifications.
  The full guard rerun passes: 2742 protected/current nodes and 37 contracts.
- The first full backend CI found three additional stale source-path consumers
  (Creator Studio presentation, media security and P8-L-E generated inventory).
  Correct their physical paths without changing assertions or baseline evidence;
  all 18 tests in those three files pass locally. The latest commit must pass
  the full CI suite again before merge; earlier frontend success is historical.

### AR-F2-A integration

- PR #292 final head `76d09e6f16f974c9168f5c57620c76993c042dc5`: 23/23
  checks SUCCESS, including all five Windows Installer jobs and Host Tauri.
- Local full backend: 2720 passed, 22 skipped, 28 warnings, 757.97 seconds.
- Merge `5c967a87cb4b72a51146d15f525a1eec3627a5a3`, 2026-09-07 03:08:15 KST.
  All seven post-merge workflows are SUCCESS. Windows Installer run 34050757126
  passed all five build/clean-install/supported-upgrade/failure-recovery/aggregate
  jobs. AR-F2-A is complete; next-stage integration remains sequential.

## AR-F2-C product composition preparation

- Move the common World/Studio screens out of Next's `app` directory. Next and
  the static product router use the same composition; CSS bodies, state effects,
  native window commands and PWA lifecycle behavior are retained.
- Place product shells/navigation and bootstrap providers above features. The
  Device frame and capability-aware link presentation remain reusable common UI.
- Extract the single auth context/useAuth hook, Runtime status types and Worlds'
  shell DTO ownership. Worlds no longer obtains its API DTO from Device Home.
- Retire only the unused World App named-export facade. Record all 13 original
  exports and their live destinations; check destination declarations, absence of
  consumers and rejection of implementation-file retirement. Ten new regression
  cases cover missing type exports, fake destinations and remaining consumers.
- Preserve the historical L4 public-entry count against its pinned checkpoint;
  compare today's public-entry list with source instead of retaining a dead file
  to satisfy an old topology count. Frozen assertions and behavior remain intact.
- Preparation validation: TypeScript/ESLint, Node proxy, 324-file source/browser
  preservation and partial architecture checks pass. CI/merge and full runtime
  verification remain pending; this section is not an AR-F2-C completion claim.
- Next and static production builds PASS; web 21 PASS (47.5s), Settings 2 PASS
  (8.6s), static direct-open/product behavior 68 PASS (36.0s). Full backend 2730
  PASS, 22 existing SKIP, 28 warnings (982.82s). The later structure-assertion
  adjustment preserves pinned historical import topology and independently
  requires actual current screen/navigation/frame imports. It does not freeze
  current product behavior tests or replace their fixtures.
- Source introduction `322130952465bbe350e0a6b63dbb21d0c57eed2f` adds four source
  files and ten retirement regression nodes; its append-only record is retained.
  Full preservation gate PASS: 2752 protected/current nodes and 37 contracts.
  CI and sequential integration remain required before stage completion.
- PR #294 security scanning identified two generic-key matches in the append-only
  source ledger. Both are exact Git blob IDs for `use-auth.ts` and `auth-context.ts`,
  independently matched to source commit `322130952465bbe350e0a6b63dbb21d0c57eed2f`.
  Allow only those exact lines in that ledger path; retain all other scanning.

## Temporary-file cleanup

User authorized cleanup of obsolete backend-refactor temporary files. Check
actual worktree/process consumers and document/evidence links first. Preserve
supported migration/extension code, user data, backups and referenced evidence.
Removed workspace `.task-output/ar-b8b-pr-preparation` using `git worktree remove`
without force. Its HEAD `b20c09c986f1b4eaf0b3db558f7353735405e878` is an ancestor
of origin/main; tracked/untracked source is clean, ignored files are exclusively
Python/pytest caches, no process or exact plan/architecture-document path consumer
was found. Its Git history remains available. The cleanup receipt is in workspace
`.task-output/angmoo-refactor-8-3/backend-temp-cleanup.json`. Other worktrees and
referenced installer/runtime evidence remain until individually assessed.

The subsequent read-only audit assessed 72 remaining backend worktrees and removed
31 more under the same conditions (32 removed total). The 41 that did not meet all
conditions remain. Exact paths, commits and results are recorded in workspace
`.task-output/angmoo-refactor-8-3/backend-worktree-audit.json`; no branches or
committed history were deleted.

## AR-F2-B runtime and server/client transport

- Prepare in an isolated worktree while PR #292's fixed HEAD finishes Windows
  checks. Integrate in sequence only after AR-F2-A merge and post-merge gates.
- Move server proxy to `lib/server/backend.ts`, native window commands to
  `lib/desktop/product-window.ts`, runtime navigation hooks to
  `hooks/use-runtime-navigation.ts`. Next routes use the actual server entry.
- Extract shared session DTO/cache/notification/authenticated JSON transport to
  `lib/auth/browser-session.ts`. Keep Identity endpoints in the old auth-session
  module until F3-A; preserve existing error, 401, cookie and storage semantics.
- Split Social's `getInitialSocialFeed` server request from the browser client.
  The web feed page imports the server entry directly; the Social public export
  no longer introduces a server dependency into client consumers.
- Keep runtimeFetch's dynamic loopback address, launch token, CSRF, streams and
  the existing authenticated-media hook unchanged. Native event names, route
  normalization, history, window commands and shutdown meaning are unchanged.
- Local: 114 related regression tests, TypeScript/ESLint, architecture and design
  PASS; stock 324 PASS; all-client/static transitive server-dependency audit PASS.
  Existing real-Next World Package proxy PASS; web 21 PASS (56.4s), Settings 2
  PASS (9.3s), Next/static production builds PASS, static 68 PASS (32.9s).
- Initial worktree-only Next start failed because Turbopack rejects an external
  node_modules junction. Preserve that junction outside the worktree and install
  the same frozen dependencies locally (350 cached packages, no version/lock
  change). The proxy and web tests then pass; no product configuration workaround.
- Regenerate only current L4/design/Memory batch inventories after reviewed path
  moves. Preserve frozen Today/P8-L-Q predecessors, source and visual oracles.
- Source commit `f9fe45d338e86d88bf54e373f438fcd67b0168ad` introduces two new
  files and no new backend test nodes. Append its first-introduction record;
  the full preservation guard passes: 2742 protected/current nodes, 37 contracts.
  The AR-F2-A merge is an ancestor of this branch; no introduction commit or
  frozen checkpoint was rewritten while preparing the sequential integration.
- PR #293 first backend CI found the current Next/static compatibility inventory
  still contained 13 pre-move route hashes. Regenerate with the existing embedded
  inventory tool: only those current hashes change, with 44 routes and all
  capability classifications retained. This is not a frozen-oracle refresh.


## AR-F3-A isolated Identity and Settings preparation

- Identity owns login, Local owner bootstrap/claim, profile setup, user-profile
  editing, Turnstile and their session/API/type/pending-signup modules.
- Extract Identity endpoints from the mixed agents client, retaining all request
  bodies, cookies, status handling and storage/event ordering. Existing callers
  use forwarding exports until their own feature migration.
- Settings is an upper composition of installation/session and Chat key APIs.
  Feed preference saving and successful profile onboarding use callbacks wired
  by common screens, avoiding new Identity-to-Character or Social-to-Identity
  feature imports. The same screens remain in Next/static entry paths.
- A new Node differential test executes the pinned pre-extraction implementation
  and the current modules with identical fixture transport/storage: 14 request
  contracts, 5 failure cases and 4 storage/event transitions match. CI runs it
  with full Git history so the immutable comparison source is available.
- Local Identity/source contracts: 48 passed, 14 existing warnings. Web 21 PASS
  (1.3m), Settings 2 PASS (11.9s), static 68 PASS (47.7s), Next/static builds,
  TypeScript/ESLint and both Node contract scripts PASS. The wider frontend-related
  backend suite passed 485 cases and found one duplicated test-path segment in
  migration preparation; correct that exact path and all six tests in its file
  pass. Product calls and runtime behavior were unaffected.
- Seven source files were introduced at `d5fda64809532eaf2a211ee4c97c4375abf56ffa`,
  with zero new backend nodes. Preserve the source record and all earlier
  introduction commits. Full preservation/CI/sequential integration are pending.
- Predecessor AR-F2-B #293 passed 23/23 checks at
  `812128d3888a3e56139904505331139acfd4479e` and merged as
  `e67e0385fd77f1d3a62f3e877ca41f71a0102920` at 2026-09-07 04:05:46 KST.
  Its post-merge workflows and AR-F2-C #294 remain separate integration gates.

