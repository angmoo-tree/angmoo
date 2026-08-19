# Backend domain map and import contract

This document is the contributor-facing architecture contract for Angmoo's
incremental domain-first refactor. It describes the target direction; it does
not claim that every legacy module has already moved.

The T2.5 umbrella proposal is
[`#32`](https://github.com/angmoo-tree/angmoo/issues/32). The architecture
PR A recorded its baseline from `main` commit
`16fe1b58c34bfac7e0f94cf449d8078bba98d1b2` and merged as
`9141a266e922981fff9ee90abf3aeb0cfa3e42a4`. PR B used that exact base and
merged as `85a8eb7753130fcb2be9d75a2bc64ba3079c14c3`. PR C is based on that
PR B merge.

L2 starts with
[`#51`](https://github.com/angmoo-tree/angmoo/issues/51) from `main` commit
`45edb3fee5f229c0d44867d9461eaea5b3135551`. Its PR A adds only the
application-runtime state contract, probe port, versioned read schema, and
normalized diagnostic codes. Launcher, `/health`, scheduler, migration,
Compose, and provider behavior remain unchanged in this structural PR.

## Facts, policy, and enforcement

These files have deliberately separate responsibilities:

| File | Responsibility |
|---|---|
| `security/architecture_import_baseline.json` | Deterministic facts about every `backend/app` Python module and import edge |
| `security/architecture_import_policy.json` | Target direction, exact legacy exceptions, owners, removal conditions, and review dates |
| `scripts/ci/generate_architecture_inventory.py` | Reproduce the facts without network or provider calls |
| `scripts/ci/check_architecture_boundaries.py` | Enforce policy, cycles, and no-growth rules |

At the PR A baseline the precise inventory contained 246 modules, 595 internal
edges, and 1,030 unique per-module external import records. PR B added the
relationship read domain and adapter modules, producing 256 modules, 613
internal edges, and 1,036 unique per-module external import records. PR C
removes two usage-zero compatibility modules and their three edges, producing
254 modules, 610 internal edges, and 1,036 external import records. L1 PR A
moves the identity model, schema, and credential definitions behind a canonical
domain surface, producing 265 modules, 624 internal edges, and 1,036 external
import records without changing product behavior. The
previous T2 inventory reported 426 internal edges because
`from package import module` was recorded only as the package; inventory schema
v2 resolves the real module when it exists.

L2 PR A adds 11 runtime-domain modules and reaches 285 modules, 658 internal
edges, and 1,086 unique per-module external import records. It adds zero legacy
exceptions and leaves the exact legacy allowlist at 387 edges.

L3 PR A records its execution map at merge commit
`e989dca1bb103ad61fac3518fc39c9055ad424aa` with 316 modules, 705 internal
edges, and 387 exact legacy exceptions. L3 PR B makes the P1 World Creator
schemas, definition/hash logic, persistence models, generation context, banner
storage, and SQLAlchemy use-case adapter canonical under `app.domains.worlds`.
The resulting inventory contains 324 modules, 714 internal edges, 1,170
per-module external import records, and 377 exact legacy exceptions. The ten
removed exceptions were existing World Creator compatibility edges; PR B adds
no exception.

L3 PR C adds the `characters` identity persistence facade and the
`world_characters` domain/application/port/API/SQLAlchemy slices for the
owner-controlled identity foundation. The regenerated inventory contains 341
modules, 741 internal edges, and 1,191 per-module external import records while
the exact legacy exception count remains 377. The new route reaches concrete
SQLAlchemy only inside the domain infrastructure adapter; cross-domain World
and Local Owner checks use their stable public surfaces. No new legacy import
exception is introduced.

The policy now freezes 377 exact imports into the horizontal legacy prefixes
`app.cruds`, `app.models`, `app.schemas`, and `app.services`: 375 general
horizontal edges plus the 2-edge Neo4j write-runtime bridge. L1 PR A removes
three identity aggregate edges rather than replacing them with exceptions. PR B
added zero legacy exceptions and removed two stale exceptions. PR C also added
zero legacy exceptions and left the previous exact count at 390. L1 PR A lowers
that count to 387. L3 PR B removes ten World Creator exceptions and lowers it
to 377. Existing edges may only disappear. Updating the inventory cannot
silently authorize another legacy edge.

## Target tree

Only packages used by the current migration stage are created. Empty future
packages are not pre-created.

```text
backend/app/
├── core/                     # configuration, DB and common primitives
├── domains/
│   ├── identity/
│   ├── worlds/
│   ├── characters/
│   ├── activities/
│   ├── social/
│   ├── relationships/
│   ├── runtime/                  # application runtime state and public ports
│   ├── chat/
│   ├── world_packages/
│   └── media/
├── runtime/
│   ├── resident/
│   ├── scheduler/
│   └── graph_projection/
├── integrations/
│   ├── llm/
│   ├── image/
│   └── neo4j/
├── compatibility/           # temporary facade with an owner and removal gate
└── main.py
```

## Ownership and migration stages

| Area | Stable cross-area surface | Owner stage | T2.5 state |
|---|---|---:|---|
| `core` | small primitives only | L0 | existing core is audited, not moved in PR A |
| `identity` | `app.domains.identity.public` | L1 | PR A foundation active; runtime behavior unchanged |
| resident and scheduler runtime | `app.domains.runtime.public` | L2 | PR A state/schema foundation active; behavior unchanged |
| `worlds`, `world_characters`, `routines`, `routine_posts`, owner manual social | each domain's `public.py` | L3 | P1-P3 are active; PR F moves P4 continuation and atomic publication behind the routine-post public boundary; PR G moves owner manual writes and Inbox observation behind a stable public boundary |
| `world_packages` | `app.domains.world_packages.public` | L3.5 | new Local feature later |
| feed and `social` | `app.domains.social.public` | L4 | target only |
| `relationships` graph read | `app.domains.relationships.public` | T2.5 pilot | canonical read slice active; PR C removes usage-zero aliases; write path unchanged |
| relationships write and graph projection | domain/runtime public ports | L4 | unchanged by the read pilot |
| `chat` and chat memory | `app.domains.chat.public` | P8-L | blocked by Local transition gates |
| remaining active legacy or ownerless shim | none | L6 | final removal gate |

PR A added the contract and checker but moved **zero product source files**.
PR B moved only the P7 relationship graph read path. PR C removes only shims
proven unused, promotes the stable boundary contract in repository policy, and
closes the evidence loop.

The L3 execution baseline and exact migration ownership are recorded in
[`l3-p1-p4-execution-map.md`](l3-p1-p4-execution-map.md). L3 PR A adds only the
four public package anchors and parity guards. It adds no migration, provider
call, transaction change, HTTP response change, scheduler behavior, or product
write. L3 PR B moves only the P1 World Creator boundary and preserves its HTTP,
transaction, row-version, definition-hash, provider-free, and zero-post
contracts. L3 PR C adds an additive owner-controlled identity rather than
reusing the autonomous setup service. It validates Local Owner, World
ownership, membership and World role before persistence, and scheduler/run
preflight consumes only the stable WorldCharacter public policy. PR D-G move
the remaining behavior boundaries one at a time and remove the matching exact
legacy exceptions as their callers migrate.

L3 PR D makes `app.domains.world_characters.public` the only HTTP-facing entry
for autonomous World entry and setup. The domain-owned SQLAlchemy adapter uses
the identity `local-v2` resolver, a direct-LLM integration adapter, explicit
consent/attempt records, and the existing exact 40-candidate validator. The
legacy setup, schema, model, provider, contract, and direct-LLM modules are
compatibility aliases only; privacy cleanup remains in the legacy service
until its P3-P6 rows have migrated to their owning domains.

L3 PR E makes `app.domains.routines.public` the canonical P3 entry for daily
plan preparation, read, runtime-mode updates and elapsed lifecycle recovery.
Application use cases depend on explicit Clock, daily-plan repository and
lifecycle repository ports; SQLAlchemy is confined to infrastructure adapters.
Legacy `app.models`, `app.schemas`, `app.services.daily_activity_plans` and
activity-state paths remain thin compatibility facades. API and scheduler
consumers no longer import the legacy daily-plan service, and restart recovery
closes elapsed state without creating catch-up public actions.

L3 PR F makes `app.domains.routine_posts.public` the production entry for
autonomous routine selection, evidence-bounded continuation, two-call writing,
and atomic publication. Resident and scheduler consumers no longer import the
legacy runtime. The context, validated schemas, direct-LLM provider and
SQLAlchemy orchestration live under the domain; the old routine-post modules
are compatibility aliases. An exact L4-owned compatibility bridge isolates
agent-run, social-write, joint-activity and successful-event persistence that
has not yet moved to canonical social/runtime ports. The move preserves the
normal two-call and repair-inclusive three-call cap, successful-beat reuse with
zero provider calls, same-episode continuation, once-only event consumption,
and all-or-nothing post/beat/episode/state/outbox commit. The character
scheduler lifecycle and selected autonomous WorldCharacter are kept in sync:
activation, deactivation, character replacement and credential removal update
the WorldCharacter autonomy flag without enabling owner-controlled identities.

L3 PR G makes `app.domains.manual_social.public` the stable entry for Local
Owner-authored World posts, replies and once-only autonomous Inbox observation.
The HTTP body never selects an author: the Local Owner session, active
owner-controlled WorldCharacter and same-World target are revalidated on every
write. A committed reply and its Inbox candidate share one transaction; the
candidate is claimed at the target's next allowed P4 beat and consumed only in
the beat's atomic publication transaction. The manual request itself performs
zero provider calls and L3 writes no relationship delta, graph edge or
long-term memory. Four exact L4-owned compatibility edges isolate the existing
Post, reply, block and visibility persistence until the social domain moves in
L4. The resulting inventory contains 391 modules, 827 internal edges, 1,277
per-module external import records and 344 exact legacy exceptions.

## L3-ER1 storage and graph port extraction

ER1 PR B begins from Issue
[`#99`](https://github.com/angmoo-tree/angmoo/issues/99). It is a structural
compatibility step: PostgreSQL remains the canonical store, Neo4j remains the
graph projection, and the existing HTTP schemas, scheduler/projector process
model, transaction results, provider calls and user-visible behavior remain
unchanged.

The storage-neutral contracts are now explicit:

```text
domain application
├─ UnitOfWorkPort / domain repository protocols
├─ ClockPort / ClaimLeasePort
├─ OutboxPort
├─ RelationshipProjectionPort / RelationshipQueryPort
├─ SearchIndexPort
├─ MigrationSourcePort
└─ RuntimeDataPathPort
        ↓
current runtime adapters
├─ SQLAlchemy unit of work and projection outbox
├─ Alembic migration source
├─ Neo4j projection and relationship-query adapters
├─ callback-compatible current search adapter
└─ deterministic local data-path resolver
```

`GraphProjectionWorker` now claims, loads and finalizes work through
`OutboxPort`; it no longer imports SQLAlchemy, `app.models`, or graph CRUD.
The existing SQLAlchemy adapter temporarily owns three exact L4-reviewed
legacy edges until ER2/L4 move the outbox model and command builder. Projection
command value types live in the relationships domain and the legacy service is
only a compatibility facade. CI rejects a port importing runtime,
infrastructure, integrations, or any legacy horizontal layer.

No SQLite schema, LadybugDB database file, Tauri shell, data migration, runtime
switch or feature flag is introduced by this PR. Those remain independently
reviewed ER1 PR C and ER2+ gates.

## T2.5 relationship graph read pilot

The owner-only HTTP flow now has one canonical decision path:

```text
world_activity_runtime route
→ app.domains.relationships.public
→ graph_read/use_case.py
→ graph_read/repository.py ports and result types
→ app.integrations.relationship_graph_read Neo4j adapter
```

The L4-owned `app.services.relationship_graph_read` module composes the
existing SQLAlchemy models, PostgreSQL fallback queries, projection metrics,
and graph client factory into the domain gateway. It is not a second use-case
implementation. Current runtime consumers are the API route and social-memory
diagnostics; compatibility tests also cover its legacy facade. L4 removes this
adapter only after relationship persistence and graph runtime have canonical
ports.

PR C's `rg` and AST inventory found zero importers for
`app.schemas.relationship_graph` and `app.repositories.relationship_graph`.
Those aliases were therefore deleted instead of being retained until L4.
Schema consumers import the canonical domain schema, and Neo4j adapter tests
import `app.integrations.relationship_graph_read`. The active L4 service adapter
is intentionally retained because its runtime consumer count is not zero.

The pilot does not modify `SocialEvent`, `RelationshipState` writes,
`GraphProjectionOutbox`, projector leases or retries, replay commands, Neo4j
bootstrap, migrations, provider behavior, or transaction ownership.

## L0 core audit

The L0 Docker runtime proposal records the exact current `app.core` inventory
in `security/local_runtime_contract.json`. Shared configuration, database,
identifier, transaction, redaction, request-limit, browser-session, and
security primitives remain in core. Activity scheduling policy moves at L2/L3,
search normalization at L4, and media-specific policy at L6. Every deferred
module has an owner and removal condition.

`scripts/ci/check_local_runtime_contract.py` fails if a core module is added or
removed without updating that inventory, or if core imports `app.domains`,
`app.runtime`, or `app.integrations`. The audit changes no product behavior,
schema, transaction boundary, or provider call.

## L1 identity foundation

L1 starts with [`#40`](https://github.com/angmoo-tree/angmoo/issues/40). Its
first PR is structural only: `User`, `AuthSession`, identity support tables,
`LlmCredential`, auth schemas, and credential resolution now have canonical
definitions under `app.domains.identity`. Existing `app.models.auth`,
`app.models.credentials`, `app.schemas.auth`, and `app.credentials` imports are
compatibility facades that re-export the same Python objects.

This foundation changes no table, migration, OpenAPI field, provider call,
transaction boundary, authentication behavior, or secret format. Local owner,
persistent `APP_SECRET`, standard authenticated encryption, legacy credential
migration, and BYOK lifecycle remain later L1 PRs with their own gates.

## L2 runtime foundation

The canonical application-runtime read surface is
`app.domains.runtime.public`. Pure domain types own installation state,
component state, dependency state, and stable diagnostic codes. The
`ApplicationRuntimeProbe` port returns only application facts; it cannot expose
Docker socket data, container IDs, image digests, restart counts, or host
absolute paths. A read use case consumes that port and the API layer maps the
result to the strict `local-runtime-status-v1` Pydantic contract.

PR A provides only the boundary and a fake probe. The existing `/health`
response remains the minimal `{"status": "ok"}` liveness contract, and the
legacy scheduler keeps its current behavior. Host and Compose diagnostics are
owned by the later L2 launcher adapter, while PostgreSQL lease, fencing,
sleep/wake reconciliation, graceful drain, and projector degradation are
separate behavior PRs.

## Dependency direction

```text
FastAPI route/composition
        ↓
domain public API
        ↓
domain use case
        ↓
domain model, schema, or repository port
        ↓
core primitive or integration adapter

runtime orchestration
        ↓
multiple domain public APIs + integration public ports
```

Rules for new code:

- `core` does not import domains, runtime, or concrete integrations.
- A domain may import `core` and modules inside the same domain.
- Cross-domain use goes through `app.domains.<name>.public` only.
- A domain does not import runtime, a provider SDK, or a legacy horizontal
  layer.
- Domain `domain`, `application`, and `ports` modules do not import Docker,
  FastAPI, or SQLAlchemy; framework code stays in API, infrastructure, or
  integration adapters.
- Runtime composes domain public APIs and integration public ports; domains do
  not call upward into runtime.
- Integrations own transport and SDK details, not World or relationship policy.
- Routes translate HTTP input/output and errors; they do not own queries,
  provider calls, commits, or locks.
- Repositories and CRUD modules never import a use case or service above them.
- Wildcard imports and new `from app import models, schemas` dependencies are
  rejected.

Use this cross-domain form:

```python
from app.domains.relationships import public as relationships
```

Do not reach into another domain's implementation:

```python
from app.domains.relationships.graph_read.use_case import _internal_helper
```

`public.py` is a small stable surface, not a convenience re-export of every
internal name.

## Domain package vocabulary

Use names that reveal responsibility:

- `public.py`: stable names used outside the domain
- `router.py`: FastAPI router when the domain owns one
- `schemas.py`: HTTP/domain read contract owned by the domain
- `models.py`: ORM models only after their registry and migration boundary are
  ready to move
- `repository.py`: persistence/query port and result types, with no hidden
  commit
- `use_case.py` or `use_cases/`: authorization-following orchestration and
  transaction boundary
- `dependencies.py`: actual FastAPI request dependencies
- `errors.py`: stable domain errors and reason codes
- `planner.py`, `context.py`, `executor.py`, `apply.py`: explicit generation
  responsibilities

Avoid generic new `utils.py`, `helpers.py`, `common.py`, or `service.py` files
when a more precise responsibility exists.

## Transaction and provider boundary

Structural PRs do not move commit, rollback, lock, lease, idempotency, or retry
ownership. Event and Outbox writes remain in the same PostgreSQL transaction as
their canonical state. Repositories do not commit behind a caller's back.

The T2.5 pilot is read-only. It adds no migration, DB write, provider call,
prompt, model, token setting, or SocialEvent/Outbox/projector change. Tests use
synthetic PostgreSQL/Neo4j data and fake providers; real provider calls must
remain zero.

## Exact legacy disposition

The policy contains two reviewed edge groups and one exact module cycle:

| Entry | Count | Owner | Removal condition |
|---|---:|---:|---|
| pre-T2.5 horizontal imports | 385 edges | L6 fallback owner | remove each edge at its owning domain/runtime stage; none remain after L6 |
| Neo4j write-runtime command bridge | 2 edges | L4 | move projection commands and metrics behind runtime/integration public ports |
| routine/social interaction module cycle | 2 modules | L4 | split routine context and social interaction input behind public contracts |

Every exception records exact importer and imported module, a reason, owner
stage, removal condition, and review date. Wildcard prefixes are invalid. A
removed edge makes its policy entry stale and therefore fails CI until the
exception is deleted too.

## Contributor workflow

Before adding a backend feature:

1. Find the owning area in the table above.
2. Add behavior inside that area instead of creating another horizontal
   service.
3. Add the smallest stable name to the area's `public.py` only when another
   area needs it.
4. Keep persistence below the use case and provider SDKs inside integrations.
5. Run:

   ```powershell
   uv run --project backend python scripts/ci/generate_architecture_inventory.py --write
   uv run --project backend python scripts/ci/check_architecture_boundaries.py
   uv run --directory backend python -m pytest -q tests/test_t2_5_architecture_boundaries.py
   ```

6. Review the inventory diff. A new domain edge is expected only when it obeys
   the public API contract. Never add a legacy exception merely to turn CI
   green.

Checker failures include the importer, imported module, rule, expected fix,
whether an exact legacy exception exists, its owner stage, and this document.

Architecture changes use a focused Issue and PR. Do not mix product behavior,
migrations, dependency majors, provider configuration, bulk formatting,
Hosted/Private/Production settings, or unrelated frontend moves into a
structure-only PR.

## Embedded canonical persistence

ER2 introduces SQLite only as a runtime-owned infrastructure adapter. Domain
and application packages continue to depend on repository and UnitOfWork
ports; they do not import SQLite, filesystem paths, PRAGMAs, or connection
lifecycle code. Existing SQLAlchemy repositories can receive either the
current PostgreSQL session or the future SQLite session when their documented
contract is portable.

The initial schema and connection contract is documented in
`docs/architecture/l3-er2-sqlite-canonical-adapter.md`. Production remains on
PostgreSQL until the later ER2 concurrency, FTS, migration, and explicit
cutover gates pass.
