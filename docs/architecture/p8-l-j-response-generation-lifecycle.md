# P8-L-J response request and generation lifecycle

## Outcome

P8-L-J establishes the durable request, generation, fencing and route-aware
call-accounting foundation that later P8-L stages will use for live Local World
Chat. It does not turn on a Retrieval Router, either specialist Planner, the
Character Response Generator, streaming transport, retry UI or a new send
route. The existing one-provider-call Chat path therefore remains unchanged.

This stage closes four boundaries:

1. versioned semantic, resolved-scope and typed-plan contracts;
2. one canonical response-attempt row per accepted request attempt;
3. renewable lease, generation fence and monotonic stream sequence guards;
4. route-aware logical-call and provider-attempt accounting.

```text
stored user message
        |
        v
chat_response_requests
  -> lease + generation fence
  -> RetrievalIntentEnvelope
  -> code-owned ResolvedRetrievalEnvelope
  -> bounded CanonicalPlan / GraphPlan / workflow recipe
  -> route-aware call tracker
  -> evidence frozen
  -> Character Response Generator (later stage)
  -> assistant message + typed metadata + committed request (one transaction)
```

## Domain ownership

`app.domains.chat` owns the request lifecycle, semantic intent envelope,
code-resolved policy envelope, bounded cross-store workflow recipes,
request-wide call budget, generation fence and final response commit boundary.
It never owns Memory search semantics or relationship graph semantics.

`app.domains.memory` owns `canonical-plan.v1`. A plan may choose only the
closed P8-L-H primitive catalog and is limited to six steps. It contains no SQL,
table names or arbitrary predicates.

`app.domains.relationships` owns `graph-plan.v1`. A plan may choose only the
closed P8-L-I primitive catalog and is limited to three steps. It contains no
Cypher, labels, properties or arbitrary traversal.

`AnswerRequestContractValidator` binds both specialized plans to the same
resolved-envelope version, hash and request ID. It checks each operation against
the owning H/I registry and the code-injected allowlist. Entity mentions are not
usable until code resolves them to same-World canonical IDs.

## Versioned envelopes and recipes

The Router-facing semantic contract is `retrieval-intent.v1`. It may propose a
route, intent, entity mention and semantic role, relationship from/to meaning,
time/aggregation meaning and a clarification slot. It cannot provide owner,
World, WorldCharacter or evidence IDs, permissions, limits, SQL or Cypher.

Code converts it into `resolved-retrieval.v1`, which fixes the authenticated
owner, World, requester/responding WorldCharacter, mention-to-ID bindings,
absolute time bounds, membership/block/visibility scope, Memory setting,
operation allowlists and hard caps. A deterministic hash binds this envelope to
all downstream plans.

`retrieval-workflow.v1` accepts these route shapes:

| Route | Canonical plan | Graph plan | Recipe |
| --- | ---: | ---: | --- |
| `CURRENT_CONTEXT` | no | no | no |
| `CANONICAL` | yes | no | no |
| `GRAPH` | no | yes | no |
| `BOTH` | yes | yes | required |
| `CLARIFICATION` | no | no | no |

For `BOTH`, coordination remains code-owned and bounded to
`INDEPENDENT_PARALLEL`, `GRAPH_THEN_CANONICAL` or
`CANONICAL_THEN_GRAPH`. No extra coordinator LLM is introduced.

## Canonical response-attempt row

Embedded SQLite v6 and Alembic revision `20260831_0086` add only
`chat_response_requests`. The v5-to-v6 migration creates an empty table and
preserves all prior canonical rows. The table records:

- request, thread, source user-message and stable response-slot identity;
- request-scope hash, idempotency key, generation ID and attempt lineage;
- selected model, route and bounded workflow recipe;
- lease token, lease generation and expiry;
- lifecycle state, last accepted stream sequence and typed terminal reason;
- per-node state, logical/physical call snapshot and typed response metadata;
- deadline, cancellation and terminal timestamps;
- the one committed assistant-message reference.

There is no canonical column for raw token deltas, a partial answer, typing
presence, socket state, prompt text, provider body or hidden reasoning.
Pending, streaming, failed and cancelled output cannot become a Memory
candidate. Only the successfully finalized `ok` assistant message can later be
considered by the Memory lifecycle.

## Lease, fence and stream sequence

Acceptance is idempotent by thread and idempotency key. Each lease acquisition
or renewal increments `lease_generation`. Every state mutation and final commit
matches request ID, thread, scope hash, generation ID, attempt number, lease
generation and expected prior state. It also requires a live lease, an active
deadline and no cancellation request.

A stale worker therefore cannot finalize after another worker renews or takes
over the request. The stream contract `chat-generation-stream.v1` binds the same
request/generation/attempt identity and accepts only the exact next sequence.
An exact duplicate sequence is ignored idempotently; a gap, reversal or scope
mismatch fails closed.

The final transaction inserts one `ok` assistant message and changes the
request to `committed` with typed metadata and the assistant reference. A
transaction failure leaves neither side committed. Replaying the same valid
finalization returns the already committed row and does not insert a second
assistant message.

## Route-aware call tracker

Logical product-node calls and physical provider attempts are separate
counters. The normal full-path logical caps are:

| Route | Router | Canonical Planner | Graph Planner | CRG | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| `CURRENT_CONTEXT` | 1 | 0 | 0 | 1 | 2 |
| `CANONICAL` | 1 | 1 | 0 | 1 | 3 |
| `GRAPH` | 1 | 0 | 1 | 1 | 3 |
| `BOTH` | 1 | 1 | 1 | 1 | 4 |
| `CLARIFICATION` | 1 | 0 | 0 | 1 | 2 |

Foreground schema repair is request-wide and at most one additional logical
call. It can apply only to an already-used Router or Planner node. The Character
Response Generator cannot use schema repair and may be invoked exactly once.
Each logical call permits at most two physical provider attempts, so transport
retry does not masquerade as another product-node call. Cancellation and the
request deadline stop both logical and physical accounting.

P8-L-J exercises this topology with bounded fake nodes and reports exactly zero
provider calls. Live node adapters and provider configuration remain a later
stage.

## Executable evidence

`test_p8_l_j_response_generation_lifecycle.py` proves route budgets, the
request-wide repair limit, duplicate-CRG rejection, envelope/plan binding,
cross-catalog and raw-query rejection, renewable fencing, exact stream
sequencing, transactional rollback, one-assistant finalization, idempotent
finalize replay, no raw-delta canonical columns and no Memory candidate before
commit.

`test_p8_l_j_response_generation_migration.py` proves that v5-to-v6 creates only
the empty response-request table, is reversible in the migration harness and
that copy-on-write Embedded SQLite upgrade preserves the original v5 database
and its user data.

The real Windows installer matrix now freezes readable predecessors v1 through
v5. The v5 fixture retains the P8-L-F Memory schema, omits only the v6 response
table and proves the real installer path into v6. Earlier fixtures continue to
prove their complete migration chain.

`p8-l-j-response-generation-inventory.json` chains the frozen P8-L-I inventory,
records the new schema and contracts and makes live provider nodes, API route,
UI presence/stream/retry, Evidence Bundle content policy and Memory owner UI
explicit non-scope.
