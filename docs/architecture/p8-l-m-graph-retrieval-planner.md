# P8-L-M Graph Retrieval Planner and typed graph execution

## Outcome

P8-L-M enables the `GRAPH` specialist node after the P8-L-K Retrieval Router.
The Planner converts the Router's immutable semantic intent into a bounded
`graph-plan.v1`; code validates its binding, injects the actual
owner/World/responding-WorldCharacter scope, direction and hard caps, then
executes only the six P8-L-I `GraphRecallService` primitives. LadybugDB remains
a projection: every edge, node and event candidate still passes P8-L-I's
SQLite canonical and observation revalidation before it can be returned.

This stage does not enable a new World Chat send endpoint or generate a
Character answer. The BOTH coordinator, Evidence Bundle merge, Character
Response Generator and streaming UI remain later stages.

The implementation is tracked by [Issue #238](https://github.com/angmoo-tree/angmoo/issues/238)
on branch `feat/p8-l-m-graph-retrieval-planner`, based exactly on merged P8-L-L
main `ad33e453d0f4197c329bd3ee4569667bbec41e38`.

```text
retrieval-intent.v1 route = GRAPH
        |
        v
resolved-retrieval.v1 hash/version/request binding
        |
        v
Graph Retrieval Planner provider
  - semantic intent and opaque entity refs only
  - graph-only six-operation catalog
        |
        v
strict graph-plan.v1 parser
        |
        v
GraphRetrievalPlanValidator
  - exact binding, direction and allowlist
  - hop, fan-out and row hard caps
  - request-wide repair at most once
        |
        v
GraphRetrievalPlanExecutor
  - code injects actual IDs and scope
  - P8-L-I GraphRecallService / GraphQueryPort
  - SQLite canonical and observation revalidation
```

## Domain-first ownership

`app.domains.relationships` owns the provider-neutral Graph Planner port,
strict plan parser, operation-specific parameter contract, validator and typed
plan executor. It reuses `GRAPH_RECALL_PRIMITIVE_REGISTRY` and
`GraphRecallService`; it does not import Chat, provider SDKs, SQLAlchemy or a
LadybugDB client.

`app.domains.chat.application.graph_retrieval` owns foreground request
orchestration. It proves the Router intent hash matches the resolved envelope,
restores the route-aware call tracker, builds an ID-free Planner request,
applies the request-wide repair token and derives a code-only graph execution
context. The graph subject is always the responding WorldCharacter.

`app.integrations.llm.graph_retrieval_planner` is the sole provider SDK
adapter. It uses the existing direct-LLM transport with one physical call per
logical invocation and disables implicit JSON repair. It receives no owner,
World, thread, WorldCharacter, relationship-state or event identifier.

Runtime graph ownership does not move. The typed executor calls the existing
P8-L-I public application service, whose concrete LadybugDB query adapter and
canonical SQLAlchemy facts remain under `app.runtime.graph_projection`.

## Strict provider contract

The provider schema has exactly these root fields:

```text
version
request_id
envelope_version
envelope_hash
steps
```

Each step has exactly `id`, `operation`, `input_ref` and `parameters`.
Supported operations are the six P8-L-I primitives:

- `direct_relationship`
- `relationship_evidence`
- `shared_neighbors`
- `shortest_path`
- `rank_related_characters`
- `relationship_neighborhood`

The only provider parameters are opaque `counterpart_ref`, semantic
`direction`, the closed `ranking` enum and bounded limit/depth/hop hints. A
counterpart-dependent step may read only `prior_step.world_character_refs`.
Step references are forward-only, step IDs are unique and a plan contains at
most three steps.

The parser rejects unknown fields and operations, actual identifier fields,
raw SQL/Cypher/query markers, table/schema/label/property/relationship-type
material, Canonical operations, `canonical.*`/`workflow.*` handoffs and
unresolved or cyclic dependencies. The provider schema contains no Canonical
catalog and the Planner never produces executable Cypher.

## Code-owned direction, binding and execution

`GraphPlanExecutionContext` is created only after K has resolved policy. It
contains the actual owner+World+responding subject scope, opaque-ref to actual
same-World WorldCharacter bindings, from/to relationship direction, operation
allowlist, row/hop/fan-out hard caps and projection lifecycle flag. None of
those canonical IDs enters the provider request.

The validator requires an exact request/version/hash match with the immutable
resolved envelope. It rejects any operation not present in both I's registry
and the resolved route allowlist. It resolves only opaque refs already bound by
K, checks that the selected counterpart matches the resolved from/to pair and
rejects a reversed relationship direction. Provider limits and hop hints above
the code caps are normalized downward and recorded; they never expand policy.

The executor translates each accepted step to `GraphRecallQuery`. It does not
build query strings. P8-L-I dispatches the closed primitive through the typed
`RelationshipGraphQueryPort`, checks the code-supplied projection lifecycle
flag and projection lag, and applies bounded
fallback policy. Every candidate then passes current SQLite relationship
version, active membership, block, deletion and observation checks.

A dependent step receives only same-World WorldCharacter references produced
by a prior accepted result. Code deduplicates them, excludes the responding
subject and applies the fan-out cap. If the prior result is empty, the step
short-circuits without widening the query. An unobservable scope or empty Graph
allowlist short-circuits before the Planner. Memory OFF does not disable
current relationship recall; the graph privacy/observation scope remains the
authoritative gate.

## Calls, repair and metrics

The K tracker snapshot is restored with exact route, per-node logical counts,
physical attempts and any already-consumed repair token. A normal GRAPH path
therefore has:

```text
Retrieval Router                 1
Graph Retrieval Planner         1
Character Response Generator    1 (later stage)
normal full-path cap             3
```

P8-L-M executes only the first two nodes. If provider JSON or resolved-plan
validation fails, the request may spend its one shared repair token on one
additional Graph Planner logical call. If the Router already spent that token,
no Planner repair is allowed. Zero candidates, projection degradation, policy
denial and dependency short-circuit are not repair triggers. The direct adapter
performs no hidden JSON retry.

Metrics record first-pass validity, repair use, policy short-circuit, logical
and physical Planner calls, executable steps, clamped limits and hops, result
count, provider and model.

## Executable evidence

`test_p8_l_m_graph_retrieval_planner.py` proves:

- graph-only schema and exact-key parsing;
- Canonical-catalog, fabricated-ID, raw-query and invalid dependency rejection;
- exact resolved request/version/hash and semantic direction binding;
- code-only actual scope, entity, hop, fan-out and row-cap injection;
- prior-step WorldCharacter-reference execution and zero-result short-circuit;
- one normal Graph Planner call and GRAPH full-path cap three;
- one request-wide repair shared with the Router;
- unobservable pre-provider short-circuit and Memory-OFF graph independence;
- direct adapter hidden retry disabled and no credential/canonical-ID leakage;
- all 36 frozen Korean cases, six per graph operation, parse, validate and
  execute through the typed boundary.

The frozen corpus is provider-free executable contract evidence, not a claim
that a live production model has passed final quality or latency evaluation.
That comparison remains P8-L-S.

## Non-scope

- Canonical Retrieval Planner changes;
- BOTH recipes, cross-store dependency coordination or Evidence Bundle merge;
- deterministic cross-store intersection/comparison/ranking;
- Character Response Generator and answer commit;
- message send/retry route integration, token streaming or `입력 중` UI;
- live held-out model quality PASS;
- schema migration, installer format or Ladybug generation change.
