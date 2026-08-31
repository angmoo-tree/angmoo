# P8-L-A contract and inventory closeout

This document is the repository-owned closeout for **P8-L-A —
contract·inventory closeout**. It freezes the exact pre-P8 implementation
baseline and the contracts that later P8-L PRs must implement. It does not add
a Chat or Memory runtime, change a database schema, call a provider, or claim a
user-visible feature is complete.

The machine-readable sources are:

- `security/p8_l_a_contract_registry.json` — frozen API, lifecycle, stream,
  retrieval, call-budget, evidence and safety contracts;
- `security/p8_l_a_inventory_policy.json` — frozen decisions and inventory
  policy;
- `security/p8_l_a_inventory.json` — generated exact-tree inventory;
- `backend/tests/fixtures/p8_l/retrieval_topology_v1/held_out_ko.jsonl` —
  frozen 315-case Korean evaluation corpus;
- `scripts/ci/generate_p8_l_a_inventory.py` — deterministic writer/checker.

## Exact baseline and allowed status

| Boundary | Frozen value |
|---|---|
| repository commit | `81e428bc069184edba06caf3c5821bae3cc6bfd7` |
| repository tree | `c932080bdd55b03de30123076ac48eb8b17f6cb4` |
| Alembic revisions | 82, one head `20260825_0083` |
| Embedded SQLite | schema v3, source revision `20260825_0083`, 87 canonical tables |
| P8-L-A result | local contract and inventory PASS |
| product runtime | Chat v2 and canonical Memory not implemented |
| external lifecycle | tracked by Issue #212 and its Draft PR; Ready and merge require explicit user approval |

The user request to execute P8-L-A closes the P8-L start approval for this
stage and includes Issue, push, Draft PR and Hosted CI verification under the
canonical stage lifecycle. It does not authorize Ready, merge, release,
Production, P8-L-B or later work.
The only valid completion claim for this change is `P8-L-A LOCAL CONTRACT AND
INVENTORY PASS` after the generated inventory, focused tests, architecture
checks and documentation checks pass.

## Local verification evidence

The 2026-08-31 local closeout passed the following exact checks from the
repository baseline recorded above:

| Gate | Result |
|---|---|
| frozen snapshot self-check and exact-current audit | PASS — 82 revisions, 11 legacy route operations, 4 legacy tables, 315 corpus cases |
| P8-L-A contract, registry, corpus, snapshot and migration test | PASS — 8 tests |
| focused Chat, model-selection, security, fixture and Embedded migration regression | PASS — 83 tests |
| backend architecture inventory and boundaries | PASS — 530 modules, 1,250 internal edges, 322 exact legacy edges |
| public route inventory | PASS — 172 operations |
| frontend architecture boundary | PASS — 11 features, 0 exact legacy edges |
| frontend design contract | PASS — 17 surfaces, 0 route gaps |
| public documentation | PASS |
| Embedded migration contract | PASS — current-only baseline |
| whitespace check | PASS |

The PostgreSQL-only message lease and quota concurrency nodes remain an
external-environment Gate: seven adjacent deletion/security nodes passed and
two concurrency nodes skipped because `SECURITY_CONCURRENCY_DATABASE_URL` was
not configured. That skip does not claim PostgreSQL concurrency PASS and must
be rerun in Hosted/PostgreSQL verification before the external lifecycle is
closed.

## Current legacy Chat inventory

The current implementation is a Hosted-style, global-identity private message
v1, not World Chat v2.

### Source and imports

There are four horizontal runtime modules:

```text
backend/app/api/v1/routes/messages.py
backend/app/models/messages.py
backend/app/schemas/messages.py
backend/app/services/messages.py
```

Five message-named Alembic revisions and those four modules form nine exact
message modules in the architecture inventory. Ten exact legacy import edges
remain under the historical horizontal-layer exception. P8-L-B owns their
parity migration; compatibility exports may remain until their documented
consumers are moved, but the edges must not silently be deferred to L6.

`backend/app/domains/chat`, `backend/app/domains/memory`,
`frontend/src/features/chat` and `frontend/src/features/memory` are absent at
this baseline. Their absence is a generated assertion, not an implementation
failure in P8-L-A.

### Routes and tables

The current owner-only API has eleven operations under `/api/v1/messages` and
`/api/v1/characters/{character_id}/message-settings`. The generated inventory
freezes their methods and paths. There is no P8 World Chat or canonical Memory
API. The existing `/characters/{character_id}/worlds/{world_id}/social-memory`
endpoint remains an L4 relationship/social diagnostic and must not be renamed
or presented as P8 canonical Memory.

The four legacy Chat tables are:

```text
character_message_settings
user_message_preferences
message_threads
message_messages
```

`message_threads` binds an authenticated `User requester_id` to a global
`Character character_id`. It has no `world_id`, requester/responding
WorldCharacter IDs, response request, generation, attempt, response slot or
evidence identity. `message_messages` supports only `ok/error` rows. A failed
assistant row is retried in place by message ID.

The current service uses the most recent 20 successful messages, a 12,000
character context cap, a 2,000 character user-message cap, 1,024 output tokens,
a 150-second thread lease and `RunLlmTracker(max_calls=1)`. It waits for a full
provider result and has no token stream, request-level renewal/fence,
generation sequence, reconnect, orphan recovery or durable attempt lineage.
The Local execution mode is explicitly rejected by this v1 service.

### PostgreSQL and Embedded SQLite drift

Alembic `0046` defines the legacy preference-source check, active
requester/Character unique index, thread/message indexes and message role/status
checks. The aggregate ORM metadata used to build Embedded SQLite does not
define all of those constraints and indexes. In particular, Embedded v3 has no
database-enforced active requester/Character uniqueness; the service performs
query-then-insert without an idempotency key or unique-conflict recovery.

P8-L-B must preserve this as an explicit pre-existing parity fact and must not
quietly fix it during the structure-only move. P8-L-D must implement the new
World-scoped uniqueness and related checks in Alembic and Embedded SQLite
together, with migration collision, quarantine and rollback evidence.

## Backend domain-first ownership

The target split is final:

| Meaning | Canonical owner |
|---|---|
| Chat entry, thread, message, request/generation lifecycle, retry, route budget, Evidence Bundle boundary and response commit | `app.domains.chat.public` |
| Memory setting, candidate, item, provenance, lifecycle, retention, correction, deletion and canonical recall | `app.domains.memory.public` |
| WorldCharacter eligibility and identity | existing worlds/characters public facade |
| graph primitive and direction meaning | `app.domains.relationships.public` |
| provider/LLM adapters and CRG stream transport | `app.integrations` |
| SQLite, FTS5 and LadybugDB concrete execution | `app.runtime` |

Domain/application code must not import FastAPI, SQLAlchemy, a provider SDK or
LadybugDB. Chat and Memory use public facades/ports and do not duplicate World,
relationship or source-success policy.

## Frontend feature-first ownership and route contract

The canonical Chat surface remains inside the existing World App Phone:

```text
/worlds/{worldId}/chat
/worlds/{worldId}/chat/{threadId}
logical Tauri window kind: phone
```

The list/empty state uses the first route; a stable selected thread uses the
nested route. P8-L-D must extend Next, static and Rust route grammar together
for the nested route. The existing `/messages` family becomes
compatibility-only after its P8-L-C feature-boundary migration and must not be
promoted as new Local navigation.

The WorldCharacter public profile route is:

```text
/worlds/{worldId}/characters/{worldCharacterId}
```

The source DTO must retain `world_id + author_world_character_id` and expose a
typed profile capability. The profile exposes the letter CTA only when the
backend provides same-World responding and requester-resolution capability.
Owner `/agents` and global `/profiles` are never fallback targets.

The Memory owner workspace is frozen as:

```text
Browser/static route: /memory
logical Tauri window kind: memory
layout: wide MemoryWorkspace; narrow Browser uses single-column drill-in
```

Optional `worldId` and `worldCharacterId` scope parameters must be present as a
pair and be resolved by code. A same-origin allowlisted `returnTo` may return to
the exact World Chat. Unknown, repeated, partial, cross-World or unsafe scope
parameters fail closed. The current disabled `/memory-explorer` Device Home
placeholder is not a shipped route and conveys no compatibility right. When
Memory is implemented it may become a hidden redirect to `/memory`, but it is
not the canonical route.

Chat remains in the Phone window; a separate Chat Tauri window is rejected.
Memory list/filter/pin/correction/delete is wide; Phone Chat may use a shared
Dialog for a quick evidence view.

### Adoption matrix

| Existing anatomy or behavior | Decision | P8 use |
|---|---|---|
| `SocialPostRow` author hierarchy/link slot, `ProfileAvatar`, World App section parser/shell, static World parser, Rust Phone Chat allowlist, fail-closed `LocalProductLink` | DIRECT | preserve visual and routing primitives without adopting Hosted identity semantics |
| Hosted profile anatomy and round letter button; legacy message list/header/bubble/composer/failure/retry-spinner anatomy; Chat unavailable slot; World social presentation adapter; safe login return; Chat route smoke | ADAPTED | replace global identity, pending boolean, message-ID retry and Next-only routes with World capability and P8 lifecycle |
| `features/chat`, `features/memory`, WorldCharacter profile/DTO, requester resolution, create-or-get, generation stream, evidence UI, `/memory` and `memory` window | LOCAL | new Local product meaning and implementation |
| global `/profiles` or owner `/agents` as World profile; `{character_id}` thread create; Local-message rejection as P8 availability; immediate `pending` as stream proof; same assistant-row retry; `/messages` as canonical Local route; Chat-only Tauri window; fake counts/actions; clicked social origin as automatic evidence | REJECTED | conflicts with World identity, capability, lifecycle, evidence or route truth |

The current unauthenticated World Chat route also has a known return gap:
`safeLoginReturnTo` does not allow the World Chat family and falls back to `/`.
The later route PR must add a fail-closed exact World return test rather than
reusing an arbitrary query path.

## Chat entry and create-or-get contract

World social author, World Character list and existing Chat identity DTOs must
all resolve to the same `world_id + world_character_id` profile target.

Requester candidates are active, owner-controlled WorldCharacters in the same
World:

| Count | v1 behavior |
|---:|---|
| 0 | do not create a thread; return typed setup guidance |
| 1 | resolve automatically and create-or-get the active thread |
| N | treat as uniqueness/migration anomaly; do not choose arbitrarily or create a thread |

Self-target, inactive, left, deleted, blocked, hidden, cross-owner and
cross-World targets fail closed. The active tuple is:

```text
owner_id
+ world_id
+ requester_world_character_id
+ responding_world_character_id
+ active state
```

The database owns its unique active result. Double click, network replay and
concurrent requests use an idempotency key and unique-conflict re-read; they
must create at most one active thread.

The target API families are:

```text
GET/POST /api/v1/worlds/{world_id}/chat/threads
GET      /api/v1/worlds/{world_id}/world-characters/{responding_id}/chat-entry
GET      /api/v1/worlds/{world_id}/chat/threads/{thread_id}
POST     /api/v1/worlds/{world_id}/chat/threads/{thread_id}/messages
POST     /api/v1/worlds/{world_id}/chat/threads/{thread_id}/retry
GET      /api/v1/worlds/{world_id}/chat/threads/{thread_id}/requests/{request_id}
GET      /api/v1/worlds/{world_id}/chat/threads/{thread_id}/requests/{request_id}/events

GET/PATCH /api/v1/worlds/{world_id}/world-characters/{subject_id}/memory/settings
GET       /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories
GET       /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}
POST      /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}/pin
POST      /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}/corrections
DELETE    /api/v1/worlds/{world_id}/world-characters/{subject_id}/memories/{memory_id}
```

The exact DTO shape is implemented in its owning PR, but these route families,
scope bindings and typed outcomes are contract-frozen. The machine registry
freezes the plan's stable typed outcomes and HTTP classes without inventing a
per-operation error cross-product or OpenAPI operation IDs. Raw exceptions,
provider bodies, SQL or graph details never cross the user API.

## Response request, transport and visible state

P8 uses a canonical `chat_response_requests` row per attempt, not a longer
thread lease alone. It owns request scope hash, idempotency, generation ID,
attempt/retry lineage, stable `response_slot_id`, renewable lease generation,
route/recipe, monotonic event sequence, typed terminal and committed assistant
reference. Finalize uses a fenced compare-and-swap and one transaction for the
complete assistant message, typed metadata and committed terminal state.

Raw deltas, the 300 ms timer, typing presence, connection and partial text have
zero canonical columns. Failed/cancelled/timed-out/orphaned attempt metadata is
durable, while partial text is not a transcript or memory source.

The stream protocol is versioned `chat-generation-stream.v1` over a
`fetch`-read NDJSON response. Fetch is required so static/Tauri can attach the
launcher token header; EventSource is not the canonical client. Events are
scoped by request, generation, attempt and monotonic sequence. Only Character
Response Generator text appears in delta events. Accepted, completed, failed
and cancelled events contain typed state, not Router/Planner/DB output.

Reconnect first reads the canonical request status and resumes only the active
attempt within a bounded sequence window. A committed terminal response is
hydrated without calling the Character Response Generator again. Missing gaps,
scope mismatch, stale generation, reversed/duplicate-invalid sequence and
orphaned active attempts fail closed to typed recovery.

All normal internal phases map to one user presence:

```text
request starts       -> canonical pending; no immediate visual placeholder
about 300 ms elapsed -> 입력 중 …
first CRG delta      -> replace presence with streaming assistant bubble
completed + commit   -> ok transcript
typed failure        -> failure bubble with retry or recovery CTA
```

The backend adds no artificial 300 ms delay. User-message save failure uses
`다시 보내기`; assistant generation failure uses explicit `다시 시도`.
Retry targets the latest retryable failed response request, creates a new
generation/attempt for the same source user message and re-runs the full
workflow. It does not duplicate the user message or rewrite the previous
attempt in place.

## Split retrieval contracts and call accounting

The versions are frozen:

```text
retrieval-intent.v1
resolved-retrieval.v1
canonical-plan.v1
graph-plan.v1
retrieval-workflow.v1
```

Routes are `CURRENT_CONTEXT`, `CANONICAL`, `GRAPH`, `BOTH` and
`CLARIFICATION`. Code-owned BOTH recipes are `INDEPENDENT_PARALLEL`,
`GRAPH_THEN_CANONICAL` and `CANONICAL_THEN_GRAPH`.

The Router owns a semantic envelope, not actual IDs or query operations. Code
resolves owner, World, requester/responding identity, entity references,
from/to direction, absolute time, membership, block/visibility/observation,
Memory state and hard caps. Each specialized Planner sees only its own typed
catalog and cannot alter the resolved envelope. Raw SQL and Cypher are always
rejected.

Normal full-path logical node-call caps are:

| Route | Router | Canonical Planner | Graph Planner | CRG | cap |
|---|---:|---:|---:|---:|---:|
| CURRENT_CONTEXT | 1 | 0 | 0 | 1 | 2 |
| CANONICAL | 1 | 1 | 0 | 1 | 3 |
| GRAPH | 1 | 0 | 1 | 1 | 3 |
| BOTH | 1 | 1 | 1 | 1 | 4 |
| CLARIFICATION | 1 | 0 | 0 | 1 | 2 |

A foreground request has one additional schema-repair token total, not one per
node. A policy denial, empty dependency or typed short circuit may skip a later
Planner. A logical node call and a physical provider attempt are recorded
separately; SDK retries count as physical attempts. The CRG is called at most
once per accepted attempt and exactly once for a successful visible response
or clarification response. Automatic response regeneration is forbidden.

## FTS ownership and migrations

P8 selects a separate private recall projection:

```text
existing P5 public search
  search/generations/v1/angmoo-search.sqlite3

P8 private recall
  search/memory-recall/generations/v1/angmoo-memory-recall.sqlite3
```

The P5 projection currently performs a full rebuild from public root Posts.
Adding private Chat/Memory documents to that file would let the P5 owner delete
them during rebuild and would mix public and private scope. P8 therefore has a
separate file, schema, generation, lifecycle owner, rebuild and doctor. Both
remain rebuildable projections over SQLite canonical rows.

No migration is created in P8-L-A. The following append-only reservations are
frozen from current head `20260825_0083`/Embedded v3:

| Stage | Alembic | Embedded | Purpose |
|---|---|---:|---|
| P8-L-D | `20260831_0084` | v4 | World-scoped Chat identity and active uniqueness |
| P8-L-F | `20260831_0085` | v5 | canonical Memory schema and scope control |
| P8-L-J | `20260831_0086` | v6 | response request/generation lifecycle |

Each actual schema PR must first confirm that the expected head still exists.
Head drift reopens the reservation; it never authorizes rewriting or forking an
already published revision/manifest. Every version requires an immutable
manifest, copy-on-write migration, pre/post count and digest, failure rollback
and Alembic/Embedded parity evidence.

## Frozen Korean comparison corpus and adoption Gate

The evaluation corpus contains 315 unique Korean questions in twelve
categories. It is evaluation-only and must not be copied into Planner prompts
or few-shot examples. Every case fixes the expected route, intent, optional
BOTH recipe, logical evidence reference and zero-policy-violation outcome.

The initial one-shot baseline and split topology use the same evaluation-only
configuration:

```text
provider: google
model: gemini-2.5-flash-lite
seed: 8312026
temperature: 0
top_p: 1
```

This choice matches the exact pre-P8 message default and is only a comparison
fixture; it does not freeze the production response model. If this exact model
is unavailable before the first evaluation, the contract must be explicitly
reopened and both baselines rerun with the same replacement. Silent model
substitution invalidates comparison evidence.

Absolute quality gates include Router macro-F1 0.90, entity/role/from-to/time
accuracy 0.95, executable Canonical and Graph plan rate 0.98, BOTH recipe
success 0.95, evidence precision 0.95, evidence recall 0.85, clarification F1
0.90, grounded response 0.90, unnecessary retrieval at most 0.10 and schema
repair at most 0.05. Every listed safety violation must be exactly zero.

The split topology is adopted only after the absolute and zero-safety gates and
at least one comparison criterion pass: evidence F1 improves by at least 0.03;
critical semantic errors fall by at least 30% with evidence F1 no worse than
0.01; a smaller model meets every absolute and zero-safety gate; or a measured
node-specific model arrangement reduces resource or cost with non-inferior
end-to-end quality while still meeting every gate. Failure reopens the contract
instead of silently falling back to a different topology.

Initially Router and both Planners use the same model with separate narrow
prompts/schemas. Warm/cold node latency, total tokens, logical/physical calls,
model load/swap time and peak CPU/RAM/VRAM are recorded. A warm same-model run
must not swap/reload between roles. A node-specific model is considered only
after its quality is non-inferior and its load/swap/residency cost is measured;
role-name separation alone is not a resource improvement.

## P8-L-A verification and next Gate

Required local checks:

```powershell
backend\.venv\Scripts\python.exe scripts/ci/generate_p8_l_a_inventory.py --audit-current
backend\.venv\Scripts\python.exe scripts/ci/generate_p8_l_a_inventory.py --check
backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_p8_l_a_inventory.py
backend\.venv\Scripts\python.exe scripts/ci/generate_architecture_inventory.py --check
backend\.venv\Scripts\python.exe scripts/ci/check_architecture_boundaries.py
backend\.venv\Scripts\python.exe scripts/ci/check_frontend_architecture_boundaries.py
backend\.venv\Scripts\python.exe scripts/ci/check_frontend_design_contract.py
```

`--audit-current` is the one-time A-closeout comparison against the exact
pre-P8 source tree. `--check` validates the immutable policy, registry,
inventory and corpus without requiring current product source. Later P8-L
stages add their own append-only inventories and must not rewrite A merely
because the expected Chat/Memory domain packages now exist.

P8-L-B may start only after P8-L-A merge and post-merge exact-main verification
are closed and the user separately approves P8-L-B execution. That stage
approval includes its Issue, branch, implementation, push, Draft PR and Hosted
CI verification; Ready and merge remain an explicit user Gate.
P8-L-A does not make P8-L technically complete, user-verified, merged or ready
for P9-L.
