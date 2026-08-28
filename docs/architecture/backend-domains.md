# Backend domain map and import contract

This document is the contributor-facing architecture contract for Angmoo's
incremental domain-first refactor. It describes the target direction; it does
not claim that every legacy module has already moved.

> **ER7 runtime note (2026-08-24):** the official installed and contributor
> runtimes are SQLite/FTS5 + LadybugDB with scheduler and projector owned by one
> FastAPI process. PostgreSQL is neither a supported runtime nor a migration
> input, and no PostgreSQL importer ships in the product. Neo4j is static parity
> evidence only. Historical trees and counts below are explicitly labelled;
> they are not a supported server-runtime topology.

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
│   ├── graph_projection/
│   └── relationships/          # SQLAlchemy composition over the aggregate ORM registry
├── integrations/
│   ├── llm/
│   ├── image/
│   └── graph/                # LadybugDB adapter; static Neo4j parity fixtures live in docs/tests
├── compatibility/           # temporary facade with an owner and removal gate
└── main.py
```

## Ownership and migration stages

| Area | Stable cross-area surface | Owner stage | T2.5 state |
|---|---|---:|---|
| `core` | small primitives only | L0 | existing core is audited, not moved in PR A |
| `identity` | `app.domains.identity.public` | L1 | PR A foundation active; runtime behavior unchanged |
| resident and scheduler runtime | `app.domains.runtime.public` | L2 | PR A state/schema foundation active; behavior unchanged |
| `worlds`, `world_characters`, `routines`, `routine_posts`, owner manual social | domain `public.py` contracts plus runtime composition | L3/L4 | P1-P4 are active; routine SQLAlchemy orchestration is under `app.runtime.routine_posts`, and owner writes/Inbox adapters are under `app.runtime.social` |
| `world_packages` | `app.domains.world_packages.public` | L3.5 | Local export/import active; imported runtime remains inert until local setup and explicit autonomy enable |
| feed and `social` | `app.domains.social.public` | L4 | P5 search, canonical source writes, observation and causal apply are active; concrete SQLite adapters are under `app.runtime.social` |
| `relationships` graph read | `app.domains.relationships.public` | T2.5/L4 | canonical read slice active; PR E owns its runtime composition under `app.runtime.graph_projection` |
| relationships write and graph projection | domain/runtime public ports | L4 | PR E removes horizontal service/CRUD/model bridges; runtime SQLAlchemy composition is isolated under `app.runtime.relationships` and graph lifecycle under `app.runtime.graph_projection` |
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

ER4 adds `app.runtime.single_backend_components` as the lifecycle composition
root and keeps runtime status observations behind `app.domains.runtime.public`.
Because ER4 changes ownership rather than scheduler/projector behavior, one
explicit compatibility module retains three exact imports to the reviewed L2
workers. The exception is owned by L6 and must disappear when those worker
implementations move behind canonical runtime ports; no API route or FastAPI
entrypoint imports a legacy worker directly.

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

L3 PR F introduced `app.domains.routine_posts.public` for autonomous routine
selection, evidence-bounded continuation, two-call writing, and atomic
publication. L4 PR F keeps the validated context and provider contracts under
that domain while moving SQLAlchemy execution composition to
`app.runtime.routine_posts`; resident and scheduler consumers no longer import
a domain-internal persistence module. The bounded routine compatibility bridge
still isolates agent-run and joint-activity persistence scheduled for L6. The
move preserves the
normal two-call and repair-inclusive three-call cap, successful-beat reuse with
zero provider calls, same-episode continuation, once-only event consumption,
and all-or-nothing post/beat/episode/state/outbox commit. The character
scheduler lifecycle and selected autonomous WorldCharacter are kept in sync:
activation, deactivation, character replacement and credential removal update
the WorldCharacter autonomy flag without enabling owner-controlled identities.

L3 PR G originally made `app.domains.manual_social.public` the stable entry for Local
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
per-module external import records and 344 exact legacy exceptions. L4 PR F
removes that temporary namespace: commands, ports and use cases now belong to
`app.domains.social`, while SQLAlchemy read/write/Inbox adapters are composed
under `app.runtime.social`.

## Historical L3-ER1 storage and graph port extraction

ER1 PR B begins from Issue
[`#99`](https://github.com/angmoo-tree/angmoo/issues/99). It is a structural
compatibility step: PostgreSQL remains the canonical store, Neo4j remains the
graph projection, and the existing HTTP schemas, scheduler/projector process
model, transaction results, provider calls and user-visible behavior remain
unchanged.

This section records the historical ER1 boundary. The PostgreSQL migration
source port and adapter were removed before the first public SQLite-only
release. PostgreSQL is not a legacy runtime or an accepted offline input.
Current runtime ports begin at `RuntimeDataPathPort`, the SQLite generation
lifecycle and replayable LadybugDB projection contracts.

The storage-neutral contracts are now explicit:

```text
domain application
├─ UnitOfWorkPort / domain repository protocols
├─ ClockPort / ClaimLeasePort
├─ OutboxPort
├─ RelationshipProjectionPort / RelationshipQueryPort
├─ SearchIndexPort
└─ RuntimeDataPathPort
        ↓
current runtime adapters
├─ SQLAlchemy unit of work over SQLite canonical generations
├─ SQLite projection outbox and FTS5 search
├─ LadybugDB projection and relationship-query adapter
└─ deterministic local data-path resolver
```

`GraphProjectionWorker` now claims, loads and finalizes work through
`OutboxPort`; it no longer imports SQLAlchemy, `app.models`, or graph CRUD.
The existing SQLAlchemy adapter temporarily owns three exact L4-reviewed
legacy edges until ER2/L4 move the outbox model and command builder. Projection
command value types live in the relationships domain and the legacy service is
only a compatibility facade. CI rejects a port importing runtime,
infrastructure, integrations, or any legacy horizontal layer.

At the time, ER1 introduced no SQLite schema, LadybugDB database file, Tauri
shell, data migration, runtime switch or feature flag. Those later gates are
now complete; this paragraph is retained only to explain the original PR
boundary.

## T2.5 relationship graph read pilot

The owner-only HTTP flow now has one canonical decision path:

```text
world_activity_runtime route
→ app.domains.relationships.public
→ graph_read/use_case.py
→ graph_read/repository.py ports and result types
→ app.runtime.graph_projection.relationship_graph_read composition
→ app.integrations.ladybug_projection
   with bounded SQLite canonical fallback when projection is unavailable
```

The L4-owned `app.runtime.graph_projection.relationship_graph_read` module
composes the registered SQLAlchemy models over SQLite, canonical fallback
queries, projection metrics and the shared in-process LadybugDB runtime into
the domain gateway. It is not a second use-case implementation. Current
runtime consumers are the API route and social-memory diagnostics. PR E moves
relationship-owned ORM definitions under
`app.domains.relationships.infrastructure`, isolates concrete aggregate
SQLAlchemy writes and reads under `app.runtime.relationships`, moves
worker/replay/metrics and diagnostics under `app.runtime.graph_projection`,
and deletes the former horizontal service/CRUD/model modules rather than
retaining compatibility facades. Domain infrastructure does not import the
aggregate `app.models` registry; only the runtime composition edge is reviewed.

PR C's `rg` and AST inventory found zero importers for
`app.schemas.relationship_graph` and `app.repositories.relationship_graph`.
Those aliases were therefore deleted instead of being retained until L4.
Schema consumers import the canonical domain schema. Neo4j query documents
remain immutable parity fixtures; no Neo4j driver or server is composed.

The historical pilot did not modify `SocialEvent`, `RelationshipState` writes,
`GraphProjectionOutbox`, projector leases or retries, replay commands,
migrations, provider behavior, or transaction ownership.

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

Structural PRs do not move commit, rollback, lock, lease, idempotency or retry
ownership. Event and Outbox writes remain in the same caller-owned SQLite
transaction as their canonical state. Repositories do not commit behind a
caller's back.

The T2.5 pilot was read-only. It added no migration, DB write, provider call,
prompt, model, token setting or SocialEvent/Outbox/projector change. Current
tests use isolated SQLite/LadybugDB generations, static parity fixtures and fake
providers; real provider calls remain zero unless a test explicitly owns one.

## Exact L4 disposition

At exact L4 baseline `0917bfa6bbb14c4b15a4a26d1f221817bd4e52e1`, the
repository-wide architecture inventory contains 504 modules, 1,171 internal
edges and zero module cycles. The active architecture policy has zero legacy
import exceptions and zero allowed cycles. L4 PR A additionally records 18
selected social/relationship legacy-horizontal modules and 26 existing
canonical domain/runtime modules in `security/l4_pr_a_inventory.json`.

These counts are an exact baseline, not a permanent architecture target. Later
L4 PRs must preserve the frozen behavior oracle while moving ownership toward
the canonical surfaces. Any intentional inventory change regenerates the
machine-readable artifact and explains the delta in review; unexplained drift
fails CI.

### L4 PR B social search ownership

`app.domains.social.public` is the canonical public boundary for the P5
interest-discovery search lane. Its application use case accepts a narrow
`SocialSearchIndexPort`, performs two bounded keyword queries, deduplicates the
ranked document IDs, and never opens a filesystem path or SQLAlchemy session.
The embedded runtime owns the concrete SQLite FTS5 index and rebuilds it
deterministically from canonical posts before registering the search as ready.

FTS5 is a candidate projection, not an authorization source. The existing P5
service receives only candidate IDs and performs one canonical SQLite query
that revalidates World scope, public visibility, delete/report state, active
WorldCharacter membership, self exclusion, repost/root-post rules, and blocks
in both directions. Observation and action eligibility checks remain
canonical. The production P5 path has no SQL `contains`/`LIKE` or silent full
scan fallback.

Committed post changes update or remove the FTS5 document after the caller's
transaction succeeds. A projection failure does not roll back the social
write: the runtime publishes one of `search_rebuilding`,
`search_schema_mismatch`, `search_digest_stale`, or `search_unavailable`, and
the P5 interest lane records an explicit degraded no-action cycle with zero
provider calls. The next embedded-runtime startup rebuilds from SQLite. Inbox
and routine lanes keep their independent scheduling and are not replaced by
FTS5.

Until the later L4 social-write ownership PR moves the canonical `Post` model,
one exact `app.runtime.search.social_projection -> app.models` adapter edge is
recorded in the architecture policy. It is runtime-owned, has a dated removal
condition, and must not expand into another service/model/CRUD dependency.

### L4 PR C canonical social source writes

`app.domains.social.public` now owns the owner manual post/reply application
boundary and the apply boundary for an already validated autonomous post or
reply result. The domain exposes storage-neutral commands, application use
cases, and a caller-owned UoW port only. `app.api.v1.routes.manual_social`
composes those contracts with the runtime-owned
`app.runtime.social.sqlalchemy_unit_of_work` SQLite adapter; the domain does
not import that adapter, legacy ORM/services, or runtime modules. Both
owner and validated-autonomous paths acquire the single writer with
`BEGIN IMMEDIATE`; no provider or LLM call is allowed inside that transaction.

One caller-owned transaction contains the source `Post`, its audit-only
`SocialEvent`, one `SocialEventEvidence` row, the idempotency ledger and, for an
owner reply to an autonomous actor, the pending Inbox candidate. A failure at
any stage rolls all of them back. A bounded lock exhaustion is exposed as the
typed retryable reason `sqlite_busy_retry_exhausted`; retrying the same request
identifier can therefore complete exactly once after the lock is released.

This is source transaction T1 only. A successful post/reply does not update
`RelationshipState` and does not enqueue a graph projection. PR D owns the
later observation transaction that may create a directional relationship
delta and outbox evidence after the target actor actually observes the source.

L4 PR F removes the former `app.compatibility.manual_social` and
`app.domains.manual_social` facades completely. Feed/thread reads, source-write
UoW, observation UoW and Inbox persistence are runtime-owned adapters under
`app.runtime.social`. Their bounded exact-edge exception remains only while the
canonical `Post` ORM and community persistence service are pre-L6 modules.

### L4 PR D source observation and follow-up causality

`app.domains.social.public` also owns the storage-neutral observation command,
result and UnitOfWork port. Runtime lanes enter that one application contract
through the runtime-owned `app.runtime.social.observations` adapter;
Routine, Inbox and Feed do not write `RelationshipState`, change rows or graph
outbox rows themselves.

The adapter revalidates the canonical source event, evidence, live public Post,
World scope, active WorldCharacter identities and block state. The
`RelationshipStateChange` unique key over relationship direction and source
event is the observation receipt: retry, restart and overlap between lanes can
reuse the receipt but cannot apply another delta. The relationship direction is
observer to source actor. Observation adds one familiarity and one interaction
count only; affinity, trust and tension remain unchanged because source
exposure cannot establish a user's or character's private emotion.

The source event remains immutable and keeps its original actor-to-target
direction. A separate `relationship-observation-v1` outbox payload projects the
observer-to-source relationship snapshot into LadybugDB. Projection command
construction validates both directions explicitly: event nodes preserve source
evidence while `RELATES_TO` uses the observed relationship direction.

Each lane commits observation before provider work. Planner `NO_ACTION`,
planner failure, writer failure and a rolled-back follow-up cannot erase the
receipt. A public follow-up remains a new canonical social write with its own
idempotency key, event, evidence and outbox transaction; it is never folded
into the observation transaction. This is the T1 source, T2 observation and T3
optional follow-up causal boundary.

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

SQLite is the sole canonical relational persistence for installed, Docker and
contributor runtimes. Domain and application packages continue to depend on
repository and UnitOfWork ports; they do not import SQLite filesystem paths,
PRAGMAs or connection lifecycle code. SQLAlchemy repositories receive the
caller-owned SQLite session selected by the typed runtime composition.

The schema and connection contract is documented in
`docs/architecture/l3-er2-sqlite-canonical-adapter.md`. The cutover, migration,
FTS5, direct-update and supported-predecessor gates are complete. SQLite v3 is
the L4 baseline and v1-to-v2-to-v3 remains a consecutive copy-on-write upgrade
chain.

## Embedded canonical concurrency

ER2 PR E keeps claim and lease mechanics below domain ports. Runtime-owned
SQLite infrastructure may use `BEGIN IMMEDIATE`, bounded busy retry, and
state-conditioned CAS, while scheduler and relationship domain code continues
to depend on the existing lease and outbox contracts. SQLite adapters do not
import API routes or product use cases, and domain packages do not import
SQLite connection details.

The executable translation and failure boundaries are documented in
`docs/architecture/l3-er2-sqlite-concurrency.md`. SQLite adapters are selected
for `LOCAL_EMBEDDED` and `CONTRIBUTOR_EMBEDDED`; `TEST` must select an isolated
SQLite generation or an explicit fake.

## Embedded relationship projection

ER3 PR H introduced `app.integrations.ladybug_projection`; it is now the sole
official implementation of the relationships domain
`RelationshipProjectionPort`. It consumes validated, database-neutral
projection commands. The projector worker handles the domain-owned
`RelationshipProjectionBackendError`; it does not import either graph
provider's exception type.

The LadybugDB adapter owns exactly one database and connection behind an
in-process serialized access lock plus a cross-process writer lock. API routes
cannot construct the adapter or open LadybugDB connections. Its schema contains
World, WorldCharacter and SocialEvent nodes and directional RELATES_TO and
RELATIONSHIP_GROUNDED_IN evidence edges, with World scope and source-event
metadata on every relevant projection record. Event/state upsert,
stale-version rejection, source delete/hide, clear-and-replay, and close/reopen
are deterministic and idempotent.

LadybugDB is derived data only. SQLite outbox state remains canonical when the
graph is unavailable, so a graph failure leaves a retryable row instead of
rolling back an already committed social write. LadybugDB projection schema
v2 is selected by the installed and contributor embedded profiles. It adds the
explicit observer-to-source relationship direction to the projection command
without changing the immutable source-event direction. The v1 manifest remains
a supported predecessor and is rebuilt from SQLite canonical evidence into a
staging v2 generation before promotion. Typed six-query parity, World replay
and outage recovery are required regression contracts. Neo4j is retained only
as static fixture evidence.
