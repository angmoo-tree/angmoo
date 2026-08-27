# L4 P5-P7 parity and ownership baseline

This document is the review map for L4 PR A. The machine-readable source is
`security/l4_pr_a_inventory.json`; regenerate it with:

```powershell
backend\.venv\Scripts\python.exe scripts\ci\generate_l4_pr_a_inventory.py --write
```

CI uses `--check`. A mismatch means that a reviewed P5-P7 behavior oracle,
runtime manifest, installer Gate, or ownership edge changed without updating
the L4 inventory.

## Exact baseline and scope

- exact L3.5/main baseline:
  `0917bfa6bbb14c4b15a4a26d1f221817bd4e52e1`
- SQLite canonical schema: v3
- LadybugDB projection schema: v1
- official runtime: SQLite/FTS5 + LadybugDB + in-process scheduler/projector
- PR A is inventory and documentation only

PR A does not change a schema, endpoint, relationship delta, provider-call
count, or production composition. Later L4 PRs may change ownership only after
the corresponding frozen behavior nodes continue to pass.

## PR B reviewed delta

PR B intentionally adds `app.domains.social` as the canonical P5 search
boundary and moves the existing post-list UI behind
`frontend/src/features/social/public.ts`. The runtime-owned SQLite FTS5
projection is now the only production keyword candidate source. Candidate IDs
are revalidated against canonical SQLite before they can enter the existing
observation/planner path; the former SQL substring scan is not retained as a
fallback.

The frozen eight-keyword, two-keyword-per-cycle, bounded-candidate and provider
call contracts remain unchanged. FTS5 rebuilding, schema mismatch, digest
staleness, or unavailability produces an explicit degraded P5 result and zero
provider calls. The generated inventory includes the new domain and focused
projection regression. Exact frontend legacy edges created by moving the
unchanged Feed client are separately owned in the frontend architecture policy
and must decrease through PR C/F.

The reviewed PR B inventory delta is 514 Python modules, 1,194 internal edges,
1,746 per-module external imports, 35 selected canonical-boundary modules, 36
frontend candidate consumer edges, seven feature public surfaces, and 89
focused parity nodes. The PR A SHA remains the historical entry baseline; these
current counts are intentionally regenerated with the ownership move.

## Runtime and upgrade baseline

The supported SQLite chain is consecutive and copy-on-write:

| Source | Target | Meaning | Canonical tables |
|---|---|---|---:|
| v1 | v2 | World Package registry | 83 -> 87 |
| v2 | v3 | explicit `no_specific_role` semantic normalization | 87 -> 87 |

The v2-to-v3 step must preserve custom roles and create at most one canonical
reserved no-role row for each affected World. A missing non-null custom role
reference is not silently rewritten. LadybugDB v1 remains derived data and is
replayed from SQLite canonical evidence when its manifest changes or recovery
is required.

The Windows installer context remains a required five-part Gate:

1. `release-candidate`
2. `windows-installer-supported-upgrade`
3. `windows-installer-failure-recovery`
4. `installed-runtime-smoke`
5. `windows-installer` final aggregator

This records the upgrade context only; PR A does not modify installer behavior.

## Backend ownership baseline

The deterministic backend inventory at the exact baseline contains:

| Metric | Count |
|---|---:|
| Python modules | 504 |
| Internal import edges | 1,171 |
| Per-module external imports | 1,732 |
| Architecture-policy legacy exceptions | 0 |
| Module cycles | 0 |
| Selected L4 legacy-horizontal modules | 18 |
| Existing canonical social/relationship/runtime modules | 26 |

The current L4 move candidates remain primarily under `app.services`,
`app.models`, `app.cruds`, and `app.compatibility.manual_social`. Existing
canonical surfaces under `app.domains.manual_social`,
`app.domains.relationships`, `app.runtime.graph_projection`, and the LadybugDB
integration are preserved. The exact module paths and imports are recorded in
the generated JSON rather than duplicated here.

## Frontend feature-first baseline

The current inventory contains 12 L4 route/component/API/type candidates and
37 exact consumer edges. It records:

- Feed composition and post-list/post-thread clients
- owner-controlled World post/reply UI
- community transport and DTO surface
- Relationship Graph route, UI, typed API and degraded/rebuilding states
- four current community route adapters
- six existing feature public surfaces and five shared public surfaces

`features/social` and `features/relationships` are the only new L4 feature
names in the allowlist. PR A does not create them or move source. Subsequent
PRs must make the recorded legacy consumer count decrease or stay equal; it
must never increase. Route roots compose feature `public.ts` surfaces, shared
code remains product-neutral, and social/relationships cannot deep-import one
another.

## Frozen behavior oracle

The generated baseline records 85 focused test nodes across the following
contracts:

- P5 deterministic keyword normalization, eight-keyword profile, World-scoped
  FTS candidate filtering, cursor rotation and exactly-once observation
- P6 SocialEvent, Evidence, directional RelationshipState, World isolation,
  Inbox apply, delete/hide exclusion and transaction rollback
- owner-controlled post/reply idempotency, zero provider calls and World-scoped
  thread reads
- P7 typed LadybugDB queries, direct/reverse/evidence behavior, bounded query
  caps, World replay digest and outage recovery
- SQLite v1-to-v2-to-v3 and LadybugDB v1 generation/replay lifecycle
- direct-created World and imported World registration/replay
- frontend boundary, route and static product-shell evidence

The counter contracts are explicit: no P5 candidate uses zero provider calls,
a reused minute cycle does not perform a second provider call, manual
post/reply uses zero provider calls, one successful interaction creates one
outbox result, a rolled-back interaction commits zero canonical rows, and a
concurrent package commit wins exactly once.

## Updating the baseline

Run the generator only when an intentional L4 ownership or reviewed oracle
change occurs. Update the policy and generated artifact in the same PR, explain
the delta in review, and keep all frozen behavior tests green. Never refresh
the JSON merely to silence CI after an unexplained behavior or runtime drift.
