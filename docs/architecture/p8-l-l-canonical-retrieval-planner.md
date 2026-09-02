# P8-L-L Canonical Retrieval Planner and typed canonical execution

## Outcome

P8-L-L enables the `CANONICAL` specialist node after the P8-L-K Retrieval
Router. The Planner converts the Router's immutable semantic intent into a
bounded `canonical-plan.v1`; code validates its binding, injects the actual
owner/World/responding-WorldCharacter/thread/time scope and executes only the
nine P8-L-H SQLite repository/FTS5 primitives. FTS5 remains a candidate
projection and every returned row still passes H's canonical revalidation.

This stage does not enable a new World Chat send endpoint or generate a
Character answer. The Graph Planner, BOTH coordinator, Evidence Bundle merge,
Character Response Generator and streaming UI remain later stages.

The implementation is tracked by [Issue #235](https://github.com/angmoo-tree/angmoo/issues/235)
on branch `feat/p8-l-l-canonical-retrieval-planner`, based exactly on merged
P8-L-K main `0de2f741f5737ca88622bf7863cbe4c77c43517d`.

```text
retrieval-intent.v1 route = CANONICAL
        |
        v
resolved-retrieval.v1 hash/version/request binding
        |
        v
Canonical Retrieval Planner provider
  - semantic intent and opaque entity refs only
  - canonical-only nine-operation catalog
        |
        v
strict canonical-plan.v1 parser
        |
        v
CanonicalRetrievalPlanValidator
  - exact binding and allowlist
  - prior-step dependency only
  - request-wide repair at most once
        |
        v
CanonicalRetrievalPlanExecutor
  - code injects actual IDs, scope, UTC time and hard cap
  - P8-L-H CanonicalRecallService
  - private FTS5 candidates -> SQLite canonical revalidation
```

## Domain-first ownership

`app.domains.memory` owns the provider-neutral Canonical Planner port, strict
plan parser, operation-specific parameter contract, validator and typed plan
executor. It reuses `CANONICAL_PRIMITIVE_REGISTRY` and
`CanonicalRecallService`; it does not import Chat, provider SDKs, SQLAlchemy or
LadybugDB.

`app.domains.chat.application.canonical_retrieval` owns foreground request
orchestration. It proves the Router intent hash matches the resolved envelope,
restores the route-aware call tracker, builds an ID-free Planner request,
applies the request-wide repair token and derives a code-only Memory execution
context. The Memory subject is always the responding WorldCharacter.

`app.integrations.llm.canonical_retrieval_planner` is the sole provider SDK
adapter. It uses the existing direct-LLM transport with one physical call per
logical invocation and disables implicit JSON repair. It receives no owner,
World, thread, WorldCharacter, source or event identifier.

Runtime SQLite and FTS5 ownership does not move. The typed executor calls the
existing P8-L-H public application service, whose concrete SQLAlchemy and
private FTS5 adapters remain under `app.runtime.memory`.

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
Supported operations are the nine P8-L-H canonical primitives:

- `search_thread_messages`
- `search_posts`
- `search_memory_items`
- `list_social_events`
- `canonical_event_details`
- `get_post_thread`
- `list_activity_episodes`
- `list_relationship_changes`
- `get_character_summaries`

The only provider parameters are plain `search_text`, opaque
`counterpart_ref`/`entity_ref`, `current_thread` and a bounded limit hint.
Detail operations may read only `prior_step.source_refs`. Step references are
forward-only, step IDs are unique and the plan contains at most six steps.

The parser rejects unknown fields and operations, actual identifier fields,
raw SQL/query markers, schema/table/column/property material, Graph operations,
`graph.*`/`workflow.*` handoffs and unresolved or cyclic dependencies. The
provider schema contains no Graph catalog. Search text is a plain-language FTS
concept; it is not an FTS expression or Text-to-SQL.

## Code-owned binding and execution

`CanonicalPlanExecutionContext` is created only after K has resolved policy.
It contains the actual owner+World+responding subject Memory scope, current
thread ID, opaque-ref to actual same-World WorldCharacter bindings, absolute
UTC bounds, operation allowlist and row hard cap. None of those canonical IDs
enters the provider request.

The validator requires an exact request/version/hash match with the immutable
resolved envelope. It rejects any operation not present in both H's registry
and the resolved route allowlist, and it resolves only opaque refs already
bound by K. A provider limit above the resolved row cap is normalized downward
and recorded; it never expands the code cap.

The executor translates each accepted step to `CanonicalRecallQuery`. Search
steps use the private P8 FTS5 projection and then H's SQLite revalidation.
Direct steps use the typed repository. A detail step receives only canonical
`CanonicalRecallRecord.reference` values from a prior executed step; if the
dependency yields zero records, it short-circuits without issuing an invalid or
wider query.

Memory OFF or an empty canonical operation allowlist short-circuits before the
Planner and database. Zero results, projection degradation and policy outcomes
are not schema-repair triggers.

## Calls, repair and metrics

The K tracker snapshot is restored with exact route, per-node logical counts,
physical attempts and any already-consumed repair token. A normal CANONICAL
path therefore has:

```text
Retrieval Router                 1
Canonical Retrieval Planner     1
Character Response Generator    1 (later stage)
normal full-path cap             3
```

P8-L-L executes only the first two nodes. If provider JSON or resolved-plan
validation fails, the request may spend its one shared repair token on one
additional Canonical Planner logical call. If the Router already spent that
token, no Planner repair is allowed. The direct adapter performs no hidden JSON
retry. Character Response Generator repair remains forbidden.

Metrics record first-pass validity, repair use, policy short-circuit, logical
and physical Planner calls, executable steps, clamped limits, accepted result
records, provider and model.

## Executable evidence

`test_p8_l_l_canonical_retrieval_planner.py` proves:

- canonical-only schema and exact-key parsing;
- cross-catalog, fabricated-ID, raw-query and invalid dependency rejection;
- exact resolved request/version/hash binding;
- code-only actual scope, entity, thread, UTC time and row-cap injection;
- prior-step source-reference execution and zero-dependency short-circuit;
- one normal Canonical Planner call and CANONICAL full-path cap three;
- one request-wide repair shared with the Router;
- Memory OFF short-circuit before provider or retrieval;
- direct adapter hidden retry disabled and no credential/canonical-ID leakage;
- all 36 frozen Korean cases, four per canonical operation, parse, validate and
  execute through the typed boundary.

The frozen corpus is provider-free executable contract evidence, not a claim
that a live production model has passed final quality or latency evaluation.
That comparison remains P8-L-S.

## Non-scope

- Graph Retrieval Planner or LadybugDB execution;
- BOTH recipes, cross-store dependency coordination or Evidence Bundle merge;
- deterministic cross-store intersection/comparison/ranking;
- Character Response Generator and answer commit;
- message send/retry route integration, token streaming or `입력 중` UI;
- live held-out model quality PASS;
- schema migration, installer format or Ladybug generation change.
