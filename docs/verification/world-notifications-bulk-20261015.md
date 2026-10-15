# World notification bulk read — 2026-10-15 LOCAL

Status: **I00–I31 implementation and focused LOCAL verification complete**. This document
does not certify hosted CI, main merge, installed-app deployment or USER CHECK.

Baseline: `feat/world-user-notifications`,
`1dbfbeff9b707d10ffac7fb78fa98cf0af8925a6`; main remains
`3e5d268d085627f691ee814616f6a1c757dd2c62`.
Scope: local implementation, relevant checks and signed-off local commit only.

The header reuses the exact existing Check size20 and 44px circular control before
Refresh. World rows display localized Unread markers instead of individual checks.
Home/feed count backgrounds reuse brand-soft; server-confirmed zero hides them.
The explicit read-all POST validates current scope, updates all eligible unread
pages in one immediate UoW/set update, preserves first read_at and handled state,
and leaves later arrivals unread. Entry/source navigation never marks read.
Global notifications retain individual reads. No schema, migration, native URL,
installer, provider, activity, relationship or memory behavior changed.

The scoped controller has one pending bulk command and a 15-second client wait
bound. A lost response/timeout is uncertain, reconciles by GET and is never
automatically replayed. Permission/profile/session changes fence old responses.
The version-2 journal stores only user/session/scope and an unconfirmed flag.

Provenance: ADAPTED existing Check/control/list/tokens; LOCAL scoped bulk command
and state. No assets, fonts, dependencies, raw-color allowance or visual threshold
changes. Original notification implementation evidence remains historical.

Evidence directory: `artifacts/world-notifications-bulk-20261015/` (ignored).
Measurements, commands, actual results and remaining boundaries are recorded below.
Previous-pass counts are not reused for this change. The final signed-off commit
is recorded in the workspace plan and Git history; this file is part of that commit.

## Confirmed behavior and diagnosis boundary

- Existing individual PATCH requests remain available for compatibility, but the
  World controller no longer sends them, including on admitted source navigation.
- One header click sends one POST, not an array of per-item requests. Duplicate
  UI clicks and twenty direct controller calls share one pending command.
- The request carries only the expected recipient profile; authentication,
  current profile, deletion, visibility and block predicates are checked on the
  server. Different World/principal/profile requests do not clear unrelated rows.
- Every eligible unread page is covered. Read timestamps are first-write-only;
  delivery identities, handled state, activity and relationship data are unchanged.
- Future arrivals remain unread. Lost responses and a late commit after the
  15-second client bound reconcile through GET, never automatic POST replay.
- Provider leases cover development setup/cleanup/setup and reject stale scope
  responses. No real development HMR session or installed-app USER CHECK is claimed.
- Global notifications retain the original individual-read API/presentation mode.

Synthetic file SQLite reproduces writer contention on the existing individual
route: six concurrent PATCH requests yielded two 200 and four bounded 503 results,
leaving four unread. The bulk route completed all six with one request/update/commit.
This establishes a failing concurrent-write path, not proof that the user's
installed/runtime freeze has precisely the same cause. No installed identity,
user DB/log or Docker runtime was inspected for that claim.

## Query cost and measured results

The initial bulk route reused the old recursive visibility lookup. At 10,000
synthetic replies the write transaction took about 108.7 seconds. Statement-level
timings isolated the visibility query. Merely changing membership lookup did not
resolve its recursive rescan. The final query materializes only scoped visible
post ID/World/parent columns once, then follows visible ancestors. Parent/block,
cross-World and live-reaction checks remain intact. No persisted index, schema or
historical migration was added or changed. Verification SQLite: **3.50.4**.

The final interpreter-work regression scales visible posts from 100 to 1,000 and
rejects quadratic VM work; it does not assert a machine-specific millisecond limit.
The manual 10,000-row sample additionally records HTTP time, writer span and query
plan. These are single local samples, not cross-device performance guarantees.

| Final sample | HTTP change requests | Notification UPDATEs | Successful commits | HTTP elapsed |
| --- | ---: | ---: | ---: | ---: |
| 6 individual, serial | 6 | 6 | 6 | 152.495 ms |
| 6 individual, concurrent | 6 | 2 | 2 | 447.529 ms; four 503 |
| 6 bulk | 1 | 1 | 1 | 38.261 ms |
| 100 bulk | 1 | 1 | 1 | 36.214 ms |
| 1,000 bulk | 1 | 1 | 1 | 52.879 ms |
| 10,000 bulk | 1 | 1 | 1 | 266.965 ms |

The final 10,000-row writer observation was **261.687 ms**, with zero remaining
unread. The prior 108,663.077 ms figure is the initial single-update implementation
using the inherited query, not an assertion that the former UI exposed a bulk API.
Evidence: `measurement.json`, `measurement-before-query-optimization.json`,
`sql-duration.json`, query plans and the isolated `measure.py` in the evidence folder.
All generated data is synthetic; provider calls are zero.

## Final relevant checks

| Check | Actual result |
| --- | --- |
| Backend World notification and bulk module | **33 PASS**, 0 failure/skip; includes true writer lock, rollback, scope, multiple pages, first timestamp, live reactions, cross-World references and SQL scaling |
| Controller lifecycle/single-flight/scope Node tests | **3 PASS** |
| Next production notification browser suite | **36 PASS** |
| Static notification browser suite | **35 PASS / 1 intentional SKIP**: global `/notifications` remains unsupported in static |
| Actual HTTP/file SQLite browser flow | **2 PASS**, one Next and one static, actual canonical source replies, two Worlds, principal rejection, one bulk POST/no individual PATCH |
| Backend/frontend architecture | PASS; no new reverse boundary edges |
| Frontend design contract | PASS; raw colors **1129 / 34 files**, 18 surfaces, 0 route gaps, 63 screenshot calls; existing canonical PNGs and thresholds preserved |
| Frontend lint, typecheck, KO/EN catalog | PASS; catalog 16 namespaces / 2603 source keys with parity |
| Next production build and static build | Both PASS, built sequentially from final feature source |

The browser total is **73 PASS / 1 intentional SKIP**; repeated intermediate runs
are not added to that total. Initial test-fixture ID/legacy-row selection mistakes
were corrected before the final 33-pass backend report. Existing Starlette
deprecation warnings are separate from product failures.

Visual review includes KO/EN and 320/360/390/436/1280px. Direct PNG inspection found
the added toolbar could clip Refresh at 320px English despite no document overflow.
Narrow header spacing/title size now adapt, and the regression checks both button
bounds, not only document scroll width. The final 320px English image shows both
44px controls fully visible. Unread text and count contrast are >=4.5:1, focus and
tab order remain visible, badge backgrounds equal the active Feed tab token.

## Reproduction commands

Run from the stated working directory with the existing local dependencies.

```powershell
# Repository root
backend/.venv/Scripts/python.exe scripts/ci/check_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_architecture_boundaries.py
backend/.venv/Scripts/python.exe scripts/ci/check_frontend_design_contract.py --check

# backend: offline pytest; PYTHONPATH also includes scripts/testing/offline-python
./.venv/Scripts/python.exe -m pytest tests/social/test_world_user_notifications.py tests/social/test_world_notifications_bulk.py -q --tb=short --junitxml=../artifacts/world-notifications-bulk-20261015/backend-notifications.xml

# frontend
pnpm run lint
pnpm run typecheck
pnpm run test:ui-catalog
node --test scripts/tests/world-notification-controller.test.mjs
pnpm run build
pnpm run build:static

# browser-tests, after both builds finish
pnpm exec playwright test -c playwright.world-notifications.config.ts
pnpm exec playwright test -c playwright.world-notifications-static.config.ts
pnpm exec playwright test -c playwright.world-notifications-backend.config.ts
```

The backend fixture uses an isolated file DB and actual routers/services/repository;
auth/environment are synthetic and external network/provider calls are rejected.
Screenshots, JSON browser reports, HTTP attachments and JUnit live in the evidence
directory. No unconditional whole-backend/whole-frontend test run, installer
matrix, paid AI, deployment, push, PR, hosted CI or main merge was performed.

## I00–I31 completion map

| Steps | Evidence/outcome |
| --- | --- |
| I00–I03 | Clean baseline, scoped instructions, inherited concurrent PATCH diagnosis and explicit bulk contract |
| I04–I09 | DTO/service/router/set UPDATE, first read/visibility/CSRF/rollback/real contention and later delivery tests |
| I10–I13 | Strict response scope, one pending command, no source-click writes, outcome journal, timeout and GET reconciliation |
| I14–I18 | Exact existing Check/control before Refresh, Unread markers, soft badge, KO/EN and home/feed reconciliation |
| I19–I23 | Next/static/actual HTTP, late/failed commands, lifecycle and narrow layout, 100/1,000/10,000-row evidence |
| I24–I28 | Current architecture/design docs, 33 backend + 3 controller + 73 browser pass, relevant structure/build/visual review |
| I29–I31 | Signed-off local commit, plan/verification closeout and user handoff; main and remote scope preserved |

Installed Angmoo, user Docker/watch state, real-AI activity quality and actual user
freeze resolution remain unmeasured. The request's local implementation and
verification can be complete without claiming those separate deployment/user gates.
