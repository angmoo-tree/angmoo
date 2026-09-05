# Backend domain map and import contract

> **Architecture refactor, 2026-09-05:** The target is described in [ARCHITECTURE](../../backend/ARCHITECTURE.md). This document continues to describe the unmigrated code. The `refactor` section in the architecture policy activates new rules only for listed scopes; the current role modules are explicitly enumerated during the AR-G/AR-B transition. See [feature preservation](refactor-feature-preservation.md) for baseline, consumer mapping and validation. Existing public/layer rules below apply outside migrated scopes.

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
│   ├── memory/
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
| `world_packages` | `app.domains.world_packages.contracts` | L3.5 | Local export/import active; imported runtime remains inert until local setup and explicit autonomy enable |
| feed and `social` | `app.domains.social.public` | L4 | P5 search, canonical source writes, observation and causal apply are active; concrete SQLite adapters are under `app.runtime.social` |
| `relationships` graph read and P8 recall | `app.domains.relationships.public` | T2.5/L4/P8-L | canonical API read remains active; P8-L-I adds the closed six-primitive recall facade, canonical/observation revalidation and bounded degraded policy; P8-L-M adds the ID-free Graph Planner port, strict direction-aware plan validator and typed execution over that I boundary while runtime composition stays under `app.runtime.graph_projection` |
| relationships write and graph projection | domain/runtime public ports | L4 | PR E removes horizontal service/CRUD/model bridges; runtime SQLAlchemy composition is isolated under `app.runtime.relationships` and graph lifecycle under `app.runtime.graph_projection` |
| Chat entry, thread, model binding, message, response request/generation, retry and response commit | `app.domains.chat.public` | P8-L | P8-L-B/D establish the domain and World-scoped identity; P8-L-J~N add durable lifecycle, typed Router/Planners and bounded BOTH; P8-L-P connects live send/retry, immutable Evidence Bundle, exactly-once CRG, fenced commit and CRG-only NDJSON transport; its PR #245 Hotfix adds default/override thread model binding, immutable accepted-request model snapshots and family-safe provider thinking resolution |
| canonical Memory setting, candidate, item, evidence, lifecycle and recall | `app.domains.memory.public` | P8-L | P8-L-F owns the seven-table canonical schema and opt-in scope, P8-L-G/H own provider-free write and typed canonical/FTS read, P8-L-L/O add Canonical Planner and background maintenance, and P8-L-P invokes the existing candidate lifecycle only after a successful Chat commit |
| remaining active legacy or ownerless shim | none | L6 | final removal gate |

P8-L-A freezes the pre-migration Chat baseline in
`security/p8_l_a_inventory.json`: four horizontal
`models/schemas/services/routes/messages.py` modules, eleven owner-only
operations, four ORM tables and ten exact legacy import edges. That snapshot
remains immutable historical evidence after the source tree moves.

P8-L-B consumes that inventory as a parity migration. `app.domains.chat.public`
exports the supported Chat schemas, errors and `ChatService`; the application
service depends only on the framework-free `ChatRuntimePort`.
`app.runtime.chat.composition` binds that application boundary to the concrete
SQLAlchemy Chat runtime. ORM definitions are owned by
`app.domains.chat.infrastructure.sqlalchemy_models`, while SQLAlchemy session,
credential, prompt-safety and direct-provider execution remain below the
application boundary in `app.runtime.chat`.

The existing `app.api.v1.routes.messages` module remains a compatibility HTTP
transport with the same route family. `app.services.messages`,
`app.models.messages` and `app.schemas.messages` remain thin compatibility
facades or aliases for reviewed aggregate imports, tests and migration
registration. They do not retain Chat policy ownership, and their remaining
consumers and cleanup gate must stay visible in the architecture inventory
rather than being silently deferred to L6.

This structure-only move preserves the eleven route operations, request and
response payloads, authorization, four table identities, Alembic and Embedded
SQLite schema, one-provider-call cap, bounded transcript and output limits,
full-result response behavior, transaction boundaries, 150-second response
lease and retry-in-place behavior. It does not enable Local Character chat,
streaming, retrieval or Memory.

P8-L-D now implements `world_id`, requester/responding WorldCharacter
identity, active World-thread uniqueness, deterministic backfill, collision
quarantine and lossless rollback refusal. Alembic `20260831_0084` and Embedded
SQLite v4 preserve legacy IDs/messages, bind only a unique eligible
owner-controlled requester/responding pair, leave unresolved history
`ambiguous`, and mark active collisions `quarantined`. The canonical transport
is owned by `app.api.v1.routes.world_chat`; it composes the Chat domain public
DTO/error boundary and runtime service without importing runtime composition
back into the domain. P8-L-D is implemented on Issue `#218` branch
`feat/p8-l-d-world-chat-identity-role-binding`; local technical verification
passed with the full backend suite at `1543 passed, 22 skipped`. Implementation
commit `9351b38d70496ff60d97a1484808cbe7c3be58c5` is pushed and Draft PR `#219`
is open; Hosted CI is running while user, Ready, merge and post-merge Gates
remain pending, so this is not merged-main evidence. PostgreSQL-specific
concurrency also remains unverified.

The final target split remains deliberate. `domains/chat` owns Chat entry,
active-thread create-or-get, message/request/generation lifecycle, retry,
request-wide call budget, Evidence Bundle boundary and fenced response commit.
`domains/memory` owns Memory scope, provenance, lifecycle, retention,
correction, deletion and canonical recall. Neither package owns WorldCharacter
eligibility or graph semantics; they use the existing worlds/characters and
relationships public facades. Provider adapters and CRG delta transport remain
integrations, while SQLite, the separate private P8 FTS5 projection and
LadybugDB execution remain runtime concerns. The full frozen decisions are in
`docs/architecture/p8-l-a-contract-closeout.md`.

P8-L-I keeps graph semantics in `domains/relationships`. The versioned
`graph-recall.v1` contract exposes only direct relation, relationship evidence,
shared neighbors, a one-to-three-hop shortest path, related-character ranking
and a depth-one-or-two neighborhood. The domain validator owns direction and
hard caps; the runtime adapter supplies the existing typed
`RelationshipGraphQueryPort` and canonical SQLAlchemy facts. Every projected
edge is revalidated against canonical relationship version, active membership,
block state and subject observation before it can leave the facade. Direct,
evidence, shared-neighbor and ranking operations have bounded canonical
fallbacks; path and neighborhood degrade to no evidence rather than performing
an unbounded relational scan. The detailed contract and executable evidence
are recorded in `docs/architecture/p8-l-i-graph-recall.md`.

P8-L-J keeps response-request orchestration in `domains/chat` while typed
Canonical plan semantics stay in `domains/memory` and typed Graph plan semantics
stay in `domains/relationships`. `retrieval-intent.v1` carries only semantic
meaning; code produces the immutable `resolved-retrieval.v1` identity, scope,
policy and hard-cap envelope. Both specialist plans bind to its hash and the
code-owned `retrieval-workflow.v1` recipe. Embedded SQLite v6 and Alembic
`20260831_0086` add the sole `chat_response_requests` table. Renewable lease
generation, request/generation/attempt fencing, strict stream sequence and an
atomic assistant-message/request commit prevent stale or duplicate writers.
The call tracker distinguishes logical node calls from physical attempts,
enforces route caps of 2/3/3/4/2 plus one request-wide Router/Planner schema
repair, and permits exactly one Character Response Generator call. P8-L-J uses
provider-free fake nodes; live adapters, send/stream/retry transport and UI
remain later scope. The full boundary is recorded in
`docs/architecture/p8-l-j-response-generation-lifecycle.md`.

P8-L-K adds the provider-neutral Retrieval Router port, strict untrusted JSON
parser, deterministic same-World identity/time/policy resolver and safe
`CLARIFICATION` conversion under `app.domains.chat`. The provider SDK adapter
is isolated in `app.integrations.llm`; canonical SQLAlchemy scope resolution is
composed in `app.runtime.chat`. The Router never owns actual IDs, operation
primitives or hard caps. See
`docs/architecture/p8-l-k-retrieval-router.md`.

P8-L-L adds the provider-neutral Canonical Retrieval Planner port and strict
`canonical-plan.v1` wire contract under `domains/memory`. Chat application
orchestration binds the K intent and resolved-envelope hashes, while the Memory
validator and executor accept only H's nine typed canonical operations. Actual
owner/World/WorldCharacter/thread/time values and hard caps are injected by
code; the provider receives only semantic intent and opaque refs. Provider SDK
composition remains under `app.integrations.llm`, and SQLite/FTS5 execution and
canonical revalidation remain under the existing H Memory boundary. See
`docs/architecture/p8-l-l-canonical-retrieval-planner.md`.

P8-L-M adds the provider-neutral Graph Retrieval Planner port and strict
`graph-plan.v1` wire contract under `domains/relationships`. Chat application
orchestration binds the K intent and resolved-envelope hashes, while the
Relationships validator and executor accept only I's six typed graph
operations. Actual owner/World/WorldCharacter values, relationship from/to
direction and row/hop/fan-out hard caps are injected by code; the provider
receives only semantic intent and opaque refs and never emits Cypher. Provider
SDK composition remains under `app.integrations.llm`, and LadybugDB execution
plus SQLite canonical/observation revalidation remain under the existing I
boundary. See `docs/architecture/p8-l-m-graph-retrieval-planner.md`.

P8-L-N adds the code-owned `BOTH` Workflow Coordinator under `domains/chat`.
The Router may suggest a recipe, but code selects one of exactly
`INDEPENDENT_PARALLEL`, `GRAPH_THEN_CANONICAL` and
`CANONICAL_THEN_GRAPH` from an intent-typed registry. Independent specialist
Planners share one request tracker and run concurrently; dependent recipes
bind only capped typed event or WorldCharacter references and short-circuit
the second Planner on zero dependency or policy denial. Deterministic exact
join, intersection, ranking and dedupe produce bounded references for P8-L-P.
There is no coordinator LLM, provider adapter, arbitrary workflow expression,
schema change or Character response call. See
`docs/architecture/p8-l-n-both-workflow-coordinator.md`.

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

L3 PR E originally introduced the `app.domains.routines.public` entry for daily
planning and lifecycle. AR-B4-A now places actual planning decisions and commit
boundaries in `service/plans.py`, historical selection SQL in `repository/plans.py`,
and HTTP handling in `router.py`. The same request Session reaches the multi-owner
reference queries through `runtime/routines/plan_references.py`; WorldCharacter
owns the mode/version mutation, while routines retains the original transaction.
Clock/FrozenClock remains useful without the former forwarding daily-plan usecases.
Legacy model/schema/state and daily-plan aliases retain identical objects until
their consumers move. Guarded elapsed/restart lifecycle now lives in
`service/lifecycle.py`; `runtime/routines/lifecycle_references.py` supplies the
original owner records and autonomous elapsed-plan join on the caller's Session.
The service preserves per-character commits and owner-controlled rejection.
The differently admitted runner claim/lifecycle functions now live under
`service/execution/claims.py` and `service/execution/lifecycle.py`, preserving
episode-before-beat locks and the original flush/commit decisions. Publication
evidence reads use the caller's Session through `runtime/routines/activity_references.py`.
Joint scheduling and resident execution remain following B4 slices, with no
catch-up public actions added.

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

### L4 PR G verification-fixture lifecycle

The bounded L4 follow-up keeps Character identity creation on the existing
agent surface and adds only current-World fixture lifecycle policy to
`app.domains.world_characters`. Creator Studio reads an owner-scoped candidate
contract, reuses the existing idempotent World entry command, and performs a
versioned `leave` command. A left WorldCharacter is not hard-deleted, cannot be
silently recreated behind the `(world_id, character_id)` unique key, and
returns the typed `world_character_left_restore_unsupported` state until a
later explicit restore contract exists.

The leave application boundary verifies creator access, Character ownership,
autonomous control mode, exact confirmation name, row version and idempotency.
It clears the selected `CharacterActiveWorld`, marks the WorldCharacter
`left`, forces World-local autonomy off and preserves Character, setup,
content, SocialEvent, relationship and graph evidence rows. No SQLite or
LadybugDB schema change is introduced.

Scheduler slot and legacy AgentRun persistence remain pre-L6. The already
allowlisted `app.api.v1.routes.worlds -> app.models` composition boundary owns
a narrow runtime-idle guard so the WorldCharacter domain does not gain a new
legacy dependency. For the selected active World, the UI first calls the
existing deactivation command; the leave transaction then rejects an enabled
activity setting, assigned slot, running AgentRun or running P2 setup attempt.
An inactive participation in a different World can therefore be removed
without stopping the Character selected in another World.

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

### P8-L-E current-World public social profile read

`app.domains.social` owns the storage-neutral WorldCharacter social-profile
query, four activity counts, three typed tab pages and public result snapshots.
The API composition first resolves the exact active `world_id +
world_character_id` through the WorldCharacter public boundary, then injects
authenticated owner and resolved identity into the social application port.
The domain never guesses membership from a Character name or handle.

`app.runtime.social.sqlalchemy_profile_repository` owns canonical SQLAlchemy
translation, encrypted WorldCharacter/tab-scoped cursors and presentation snapshot
assembly. It consumes the L6-removable ORM aliases exposed by the already
allowlisted `sqlalchemy_read_repository` persistence bridge rather than adding
a second `app.models` architecture exception. Every count and row is limited to the requested World and excludes
blocked counterparts plus deleted, hidden or inaccessible sources. The read
does not write canonical state, alter LadybugDB projection, invoke a provider or
fall back to a global Character profile. Received likes are a count-only
aggregate; `posts`, `replies` and `likes` are the only page operations.

### P8-L-O bounded Memory consolidation and hot brief

`app.domains.memory` owns the automatic/immediate maintenance threshold, leased
queue orchestration, canonical source revalidation, candidate acceptance,
source-version-fenced hot brief and bounded retry/drain contract. The
SQLAlchemy adapter reuses the P8-L-F SQLite v6 tables; P8-L-O adds no migration
or persistence generation. `memory_hot_briefs` remains a disposable cache over
exact accepted item ID+version rows and is invalidated by lifecycle changes or
Memory OFF.

`app.integrations.llm.memory_consolidation` is an optional, background-only
summary-proposal adapter. It receives opaque candidate refs and validated,
bounded deterministic summaries, performs at most one physical provider call
per claimed batch, and disables hidden overload/JSON-repair retries. It never
owns canonical IDs, scope, TTL, evidence, acceptance, hot-brief source
selection, foreground Chat budget or final Character text. Provider absence or
failure falls back to deterministic summaries without blocking canonical
source writes or basic Chat.

The exact thresholds, call/input/lease/retry/drain ceilings and executable
failure contract are frozen in
`docs/architecture/p8-l-o-memory-consolidation-hot-brief.md` and its generated
inventory. P8-L-P now consumes this capability through a successful-Chat
after-commit candidate producer; Memory read/control UI remains later scope.

### P8-L-P Evidence Bundle and Character response streaming

`app.domains.chat` now owns the immutable `evidence-bundle.v1` snapshot,
deterministic dedupe/sort/caps, five-route response workflow and public
`chat-generation-stream.v1` event boundary. The existing Router, Canonical
Planner, Graph Planner and code-owned BOTH coordinator produce only typed,
canonically revalidated evidence. The Character Response Generator sees the
frozen provider-safe bundle and may write one response; it cannot reroute,
replan, query a database or commit a message.

`app.runtime.chat.world_generation` composes the provider adapters and exposes
idempotent message acceptance, explicit latest-failure retry, request status
and NDJSON events. Only verified CRG text is emitted as `delta` payload. The
current direct adapter validates the complete provider answer before splitting
it into bounded transport deltas, so this stage does not claim provider-native
token streaming. Assistant message, response metadata and committed request
are fenced and atomic. A separate provider-free producer then proposes the
committed assistant message to canonical Memory when that exact responding
WorldCharacter scope is ON; producer failure cannot roll back Chat.

The P8-L-P PR #245 Hotfix keeps model policy in `domains/chat`: a thread is
either `default`, which follows the current Local product preference, or
`thread_override`, which preserves the World-scoped selection. Runtime code
resolves the effective model before accepting a request and persists that
immutable snapshot on `chat_response_requests`; explicit retry creates a new
request and snapshots the binding again. Active generation rejects model
changes. Provider adapters use a closed family resolver: Gemini 3 receives
`thinkingLevel`, Gemini 2.5 Flash/Flash-Lite low thinking receives
`thinkingBudget: 0`, Gemma receives no Gemini thinking field, and unknown
families fail before provider I/O. Durable failure diagnostics use a bounded
allowlist and never persist credentials, prompts or raw provider bodies.

Alembic `20260903_0087` and Embedded SQLite v7 add only
`message_threads.model_binding_mode`; deterministic backfill uses the current
product preference, preserves unambiguous thread overrides and fails closed on
unknown models without rewriting historical accepted request snapshots. The
copy-on-write manifest/digest/rollback and installer supported-upgrade fixture
contracts remain enforced. There is no new canonical table or LadybugDB
generation. The exact bounds, public event allowlist, after-commit contract and
executable gates are in
`docs/architecture/p8-l-p-evidence-response-streaming.md` and its generated
inventory. Memory read/control UI, held-out quality/latency and cross-runtime
user closeout remain P8-L-Q~S scope.

### P8-L-Q Memory read and evidence-inspector boundary

`app.domains.memory.domain.read_surface` owns framework-free lifecycle,
evidence-availability and bounded page/detail contracts.
`app.domains.memory.application.read_surface` owns side-effect-free setting
reads, exact owner+World+subject list/detail orchestration and current canonical
source revalidation through ports. It imports neither FastAPI nor SQLAlchemy.
The concrete Memory repository and source reader remain below that boundary;
`app.api.v1.routes.memory` performs HTTP composition instead of making the
Memory domain depend on runtime adapters.

The Chat domain extends its immutable Evidence Bundle with typed private
locators and persists an `evidence-inspector.v1` snapshot only at the same
fenced assistant commit. Normal response DTOs strip its underscore-prefixed
metadata key. `app.runtime.chat.world_generation` may resolve those locators
only for the authenticated request's committed thread, then revalidates
canonical source digest/scope/visibility/observation/membership/block state,
Memory item lifecycle/version/evidence, or exact directional relationship
state before presenting a bounded excerpt. Stale, deleted or locator-less
evidence exposes no former text or canonical link.

The four Q routes are GET-only; setting GET does not create a row, Memory OFF
does not hide existing owner data, and no read starts a provider, projection,
candidate or maintenance write. The stage adds no migration, SQLite schema
version or LadybugDB generation. Full contracts and frozen file evidence are
in `docs/architecture/p8-l-q-memory-read-inspector.md` and its generated
inventory. ON/OFF, pin, correction and delete mutations remain P8-L-R.

### P8-L-R Memory owner-control boundary

`app.domains.memory.application.scope_control` owns exact-scope ON/OFF target
state and optimistic setting-version checks. `write_lifecycle` owns pin,
correction-supersession and delete lifecycle rules. A correction is not an
in-place text edit: it revalidates every canonical source, creates a stable
replacement item with the same typed shape and evidence set, and supersedes
the prior item. Target-state replays and stable correction keys make repeated
owner requests idempotent without adding a second mutation model.

`app.api.v1.routes.memory` derives the authenticated owner and exact
World+subject scope, enforces Local mutation origin, maps typed domain failures
to bounded HTTP errors and commits the canonical transaction. It does not
construct SQL, query FTS directly or invoke a model. The concrete repository
remains below the Memory port; after-commit projection synchronizes FTS5 and a
projection failure never rolls back a successful canonical mutation. OFF
blocks new candidates, writes and retrieval while leaving existing owner data
available for pin/unpin and delete; correction requires the scope to be ON.

The stage adds no migration, SQLite schema-version change, graph mutation or
provider call. Full contracts, limits and frozen file evidence are in
`docs/architecture/p8-l-r-memory-owner-control.md` and its generated inventory.
Installed-runtime causal proof, held-out quality/latency and final user
closeout remain P8-L-S.

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

## P8-L-R Today SNS working context

Social owns the closed ActionSubjectiveContextV1 and factual Today activity
contracts, exported through its public surface. Chat owns the L2.5 snapshot,
sufficiency guard, evidence selection and immutable generation fence.
Concrete batched reads and successful-action persistence stay in runtime/social;
provider composition and snapshot revalidation stay in runtime/chat. No
domain/application module gains SQLAlchemy, runtime or provider imports.
Existing Router/Planner roles and route call caps remain.

The normalized subjective table is embedded SQLite v8 / Alembic
20260904_0088, with no inferred legacy backfill or Ladybug schema change.
Memory OFF does not disable same-day canonical SNS awareness. Details and
separate Gates are in p8-l-r-today-sns-activity.md.

## Embedded canonical persistence

SQLite is the sole canonical relational persistence for installed, Docker and
contributor runtimes. Domain and application packages continue to depend on
repository and UnitOfWork ports; they do not import SQLite filesystem paths,
PRAGMAs or connection lifecycle code. SQLAlchemy repositories receive the
caller-owned SQLite session selected by the typed runtime composition.

The schema and connection contract is documented in
`docs/architecture/l3-er2-sqlite-canonical-adapter.md`. The cutover, migration,
FTS5, direct-update and supported-predecessor gates are complete. SQLite v3
remains the supported pre-World-Chat predecessor; P8-L-D introduces SQLite v4
and extends the consecutive copy-on-write chain to v1-to-v2-to-v3-to-v4. The
candidate installer must prove all three predecessor upgrades and same-version
idempotency before merge.

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


## Current AR-B2 WorldCharacter role ownership

WorldCharacter model/schema/contract/validation/provider, owner identity, profile,
Studio, entry/setup approval, lifecycle and runtime-mode/readiness policies now
live in the flat role modules documented in backend/ARCHITECTURE.md. These current
paths supersede the older L3/P2 infrastructure/application descriptions above.
The remaining public model exports and immutable SQLite alias paths are exact
transition consumers, not an endorsement of new cross-owner ORM imports.

The same-Session runtime adapters own joined reads, scheduler busy checks and
cross-domain cleanup. WC service does not import runtime or expose another
owner's ORM class as a service contract. Entry/setup HTTP owns no runtime state
mutation policy. app/api/world_errors.py translates the same World error objects
for both World and WC routers. The Character detail response owns the single
readiness Pydantic class in characters/schemas.py; WC policy and the old schema
aggregate consume that identical object. The unused Runtime alias and WC schema
fragment are removed, so Character response assembly does not depend back on WC.
