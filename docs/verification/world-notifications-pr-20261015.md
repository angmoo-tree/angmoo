# World notifications PR validation follow-up — 2026-10-15

Scope: publish `feat/world-user-notifications`, open
[PR #375](https://github.com/angmoo-tree/angmoo/pull/375), correct CI failures and
complete required checks. The owner retains main review/merge authority. This
record does not claim a main merge, installed-app deployment or direct USER CHECK.

## Initial CI failures and corrections

The initial PR head was `4cbf710e0090678735ab12b4a53cd239c03166a5`, based on
`3e5d268d085627f691ee814616f6a1c757dd2c62`.

1. Security/architecture and backend preflight stopped at stale current-source
   inventories. Regenerated the import and L4 inventories from the actual eight
   new modules and existing changed imports. The current hybrid-memory successor
   records schema v38 and current source hashes; its functional contract and
   frozen predecessor remain unchanged. No import policy or boundary is relaxed.
2. Embedded migration, Host Windows and installer preflight found the same
   historical schema mismatch. Some older metadata builders copy current ORM
   tables directly instead of following `build_sqlite_v37_metadata`. They were
   copying the new notification delivery column/indexes into released schemas.
   Both construction paths now use the same removal helper. All historical
   manifests and migration steps remain unchanged. Eight regression cases verify
   exact released manifest digests for v1, v3–v8 and v37.
3. Registered the five new notification operations in the explicit owner-only
   route security inventories. Existing route entries are unchanged. Public-route
   and authenticated-mutation counts grow by exactly five and two, respectively;
   tests also require those exact added routes and retain authentication checks.
4. The existing production/static World feed screenshot detects the added bell.
   The pinned Linux Chromium static run reproduces the same 57-pixel difference
   as both hosted projects. Direct actual/diff image review confines the change
   to the intended bell; the composer, logo, stream and tabs are unchanged. A
   new dated PNG is the shared current Next/static expectation. All earlier 19
   PNGs and the 25-pixel/0.1 comparison thresholds remain unchanged.

Initial evidence: [Core CI](https://github.com/angmoo-tree/angmoo/actions/runs/38704920980),
[Security and Governance](https://github.com/angmoo-tree/angmoo/actions/runs/38704921086),
[Host Windows](https://github.com/angmoo-tree/angmoo/actions/runs/38704921306),
[Windows Installer](https://github.com/angmoo-tree/angmoo/actions/runs/38704921068).
Those initial failures are not counted as passing final-head CI.

## Focused local verification

- Migration regression and existing embedded migration modules: **30 PASS**.
  This includes historical manifest matching, forward data preservation,
  rejection/rollback and graph rebuild behavior.
- Security harness, public runtime and hybrid-memory inventory: **28 PASS**.
  Existing private-route exclusions, authentication and demo mutation boundaries
  remain covered alongside the new owner-only routes.
- Architecture boundary: **PASS**, 1,527 modules / 6,599 edges / zero legacy exact
  edges. L4 inventory and frozen Memory batch/current successor checks: **PASS**.
- Pinned Linux image: `mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`.
  The current static comparison is **1 PASS**. Pixel differences from the prior
  image are confined to `(336, 28)–(357, 49)`; current PNG SHA-256 is
  `80a346cff3279c3b46a910fac876ce25c3fb8baf7a87420d732b62e824793883`.
  The local check runs the actual static visual test with an isolated override
  excluding only the Next server. It uses the canonical fixture, viewport,
  browser, locale, timezone and screenshot thresholds. Hosted CI still verifies
  the complete canonical Next/static config; a Windows-built standalone output
  is not claimed as a locally verified Linux Next production server.

Reproduction from `backend`, with the existing offline test environment:

```powershell
./.venv/Scripts/python.exe -m pytest tests/migrations/test_world_notifications_v38.py tests/test_embedded_data_migration_contract.py tests/test_embedded_data_migration.py -q --tb=short
./.venv/Scripts/python.exe -m pytest tests/test_m3_security_harness.py tests/test_m4_public_runtime.py tests/memory/test_hybrid_episode_inventory.py -q --tb=short
```

Source ownership continues to follow `backend/ARCHITECTURE.md`,
`frontend/ARCHITECTURE.md` and `frontend/DESIGN.md`. Tests use synthetic isolated
data with no external model calls. Original feature and bulk-read local checks
remain in their separate verification records; overlapping tests are not added
to a purported combined unique total. Remote final-head results and Windows
platform review remain separate from these local results.

## Complete-corpus follow-up

The complete backend run for `abae86ab` finished with six failures across two
partitions; the other two partitions passed. All reported cases are corrected
without changing production behavior:

- Two global-mention fixtures now explicitly identify their Post as global with
  `world_id=None`, matching the real Post contract and retaining the exact
  recipient/self/duplicate expectations. Production does not use a missing-field
  fallback to hide an invalid World scope.
- The Character state HTTP regression ignores non-APIRoute router inclusions
  when locating the existing route. It still requires the identical route object,
  successful owner HTTP write and foreign-owner 404 without changing saved state.
- The home-shell contract now expects the approved World Feed destination while
  retaining the launchability gate and legacy global feed checks.
- Current SQL-marker and Next/static inventories are regenerated. The SQL marker
  inventory retains the same 111 paths; only two current-source hashes/line
  references change. Historical migration/Neo4j corpora and negative guards are
  preserved. The new notification page accounts for the 44→45 route count, and
  the test explicitly requires that page with no static blockers. The frontend
  design report records this same current route inventory.

The four relevant modules pass **22 tests** locally with external networking
denied. The existing Starlette/httpx deprecation warnings are not hidden. Command
from `backend`:

```powershell
./.venv/Scripts/python.exe -m pytest tests/social/test_community_posts_route.py tests/characters/test_character_state_http.py tests/test_l2_5_world_app_shell_contract.py tests/test_l3_er0_embedded_runtime_inventory.py -q --tb=short
```

That local result does not stand in for the new commit's hosted CI. PR checks
must finish on the actual final head; prior-head successful frontend/Windows
jobs are not copied or treated as final-head approvals.
