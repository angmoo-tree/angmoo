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

## PR C reviewed behavior delta

PR C moves owner manual post/reply writes and validated autonomous-result
apply behind `app.domains.social.public`. A real file-backed SQLite regression
uses two sessions, two threads and a barrier: under normal short contention the
owner and autonomous writes both commit exactly once. A forced long
`BEGIN IMMEDIATE` lock instead returns `sqlite_busy_retry_exhausted`, commits no
partial source/event/evidence/Inbox/ledger rows, and the same request succeeds
once after the lock is released.

Failure injection after the source post, event, evidence and Inbox candidate
also proves rollback of the whole caller-owned UoW. The source event is
`audit_only`; `RelationshipState` and graph outbox counts remain zero until the
separate PR D observation transaction. The autonomous fixture calls the
production apply use case with a deterministic validated result and performs
zero provider calls, so this PR does not claim scheduler, observation or
follow-up user-scenario completion.

On the frontend the World Feed composer and thread move from `world-app` to
`features/social`, and the PR-C-owned `lib/community` DTO/client exceptions are
removed. The generated inventory and exact consumer-edge count are regenerated
with this reviewed ownership reduction.

## PR D reviewed behavior delta

PR D separates the immutable source write from the later fact that a specific
WorldCharacter actually observed that source. Routine, Inbox and Feed enter one
`app.domains.social.public` observation contract. The observation adapter
revalidates the source event, evidence, live public Post, World membership and
block state before changing any relationship row. One directional
`RelationshipStateChange` is the idempotent receipt for one observer and one
source event; retries and lane overlap reuse it instead of applying a second
delta.

The observation transaction changes only deterministic counters: familiarity
and interaction count increase by one, while affinity, trust and tension remain
unchanged. This records exposure, not a private emotion. It enqueues the
separate `relationship-observation-v1` graph command in the observer-to-source
direction while retaining the source event's original actor-to-target evidence
direction. Source success alone still produces no observer-side relationship
delta.

Observation commits before provider planning. `NO_ACTION`, planner failure,
writer failure and a later follow-up rollback therefore preserve the source
evidence and observation receipt while creating no partial follow-up event.
The frontend social model maps pending, observation failure, observed
`NO_ACTION`, follow-up failure and follow-up success into explicit product copy
without inferring a character's private feelings.

The reviewed PR D inventory delta is 522 Python modules, 1,220 internal edges,
1,768 per-module external imports, 20 selected legacy-horizontal modules, 40
selected canonical-boundary modules, 33 frontend consumer edges, seven feature
public surfaces, five shared public surfaces and 92 focused parity nodes. There
are no architecture-policy legacy exceptions and no package cycles.

## PR E reviewed ownership delta

PR E completes the active relationship/projection ownership move without
changing the frozen P7 deltas or query result contract. Relationship-owned ORM
definitions live under `app.domains.relationships.infrastructure`; concrete
aggregate SQLAlchemy social-event writes and social-memory reads are composed
under `app.runtime.relationships`. Projection command building, worker, replay,
metrics, process client, graph-read composition and diagnostics live under
`app.runtime.graph_projection`. The former horizontal graph and social-memory
service/CRUD/model modules are absent, and an architecture test keeps them
absent. Domain infrastructure imports no legacy horizontal registry.

LadybugDB remains the only graph adapter and SQLite remains canonical. The six
typed query digest, World replay, stale-version rejection, outage write,
backlog recovery and limited canonical-fallback regressions remain the behavior
oracle. A focused bootstrap-schema regression keeps `WorldCharacter` as the
actor identity and forbids a `Human` node table without changing the immutable
LadybugDB v2 manifest.

The frontend relationship API, typed model and client UI live behind
`features/relationships/public.ts`. Next and static/Tauri composition both use
that public component and distinguish loading, empty, rebuilding, degraded,
failed and ready states.

## Runtime and upgrade baseline

The supported SQLite chain is consecutive and copy-on-write:

| Source | Target | Meaning | Canonical tables |
|---|---|---|---:|
| v1 | v2 | World Package registry | 83 -> 87 |
| v2 | v3 | explicit `no_specific_role` semantic normalization | 87 -> 87 |

The v2-to-v3 step must preserve custom roles and create at most one canonical
reserved no-role row for each affected World. A missing non-null custom role
reference is not silently rewritten. LadybugDB remains derived data. PR D
freezes projection schema v2 because the relationship command now carries the
observer-to-source direction independently from the immutable source event
direction. The immutable v1 manifest remains a supported predecessor and is
replayed from SQLite canonical evidence into a staging v2 generation before
atomic promotion.

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
- SQLite v1-to-v2-to-v3 and LadybugDB v1-to-v2 generation/replay lifecycle
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
