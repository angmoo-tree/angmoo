# P8-L-N BOTH code-owned Workflow Coordinator

## Outcome

P8-L-N closes the bounded orchestration foundation for Router route `BOTH`.
It adds no coordinator model and accepts no generated workflow expression.
`app.domains.chat` validates the Router's `coordination_hint` against one
versioned registry, selects the recipe fixed for the semantic intent, runs the
existing P8-L-L Canonical and P8-L-M Graph specialist services, and produces a
deterministically ordered set of cross-axis references for P8-L-P.

The implementation is tracked by
[Issue #240](https://github.com/angmoo-tree/angmoo/issues/240) on branch
`feat/p8-l-n-both-workflow-coordinator`, based exactly on merged P8-L-M main
`b3688a19a42e4f98fe7f0710f97b42464b7b8595`.

This stage does not create an Evidence Bundle, call the Character Response
Generator, commit an Assistant message, expose a live send/retry route, or
change the frontend. Those integrations remain P8-L-P.

## Closed recipe registry

`WORKFLOW_RECIPE_REGISTRY` contains exactly three recipes:

| Recipe | Code-selected intents | Planning/execution order | Merge |
| --- | --- | --- | --- |
| `INDEPENDENT_PARALLEL` | `relationship_comparison`, `mixed_evidence` | Canonical and Graph Planners concurrently | deterministic union, exact event/WorldCharacter join and dedupe |
| `GRAPH_THEN_CANONICAL` | `relationship_state`, `relationship_cause`, `relationship_path` | Graph typed result, then Canonical only when bounded event refs exist | exact event-reference intersection |
| `CANONICAL_THEN_GRAPH` | `historical_recall`, `event_aggregation` | Canonical typed result, then Graph only when bounded WorldCharacter refs exist | exact WorldCharacter-reference intersection |

The Router hint is a suggestion. A hint incompatible with the registered
intent is recorded as not accepted and replaced by the code-selected recipe.
Neither the Router nor a specialist Planner can add a recipe, reorder axes,
change union to intersection, raise the two-Planner normal call cap, or submit
a condition/expression to execute.

## Opaque dependency and actual binding

Dependent recipes use only these two slots:

```text
graph-result.event_refs
canonical-result.world_character_refs
```

`WorkflowDependencyBinding` binds one slot to values extracted from an already
typed and revalidated result. The binding is created only by Chat application
code, is deduplicated and fan-out capped, and carries an explicit source axis,
target axis and value kind. The actual values do not enter either specialist
provider request. The downstream Planner continues to see semantic intent and
opaque entity references only; the coordinator uses the code-only binding to
filter the final intersection.

If the first axis is policy-short-circuited or produces zero dependency
values, the downstream specialist service is not called. Memory opt-out and an
empty Canonical allowlist prevent the dependent Canonical call. Unobservable
Graph scope and an empty Graph allowlist prevent the dependent Graph call.
There is no result-based re-planning loop.

## Concurrency and request-wide accounting

For `INDEPENDENT_PARALLEL`, both specialist services share the same
`RouteAwareCallTracker` instance and are awaited together. This preserves real
parallel Planner latency while making the request-wide repair token singular:
if one Planner spends the repair, the other cannot spend a second one.

For dependent recipes, the first Planner and typed executor finish before the
dependency binding is evaluated. The second Planner starts at most once and
only when the dependency and its policy axis are usable. The normal full-path
budget remains:

```text
Retrieval Router                 1
Canonical Retrieval Planner     1
Graph Retrieval Planner         1
Character Response Generator    1 (P8-L-P)
normal BOTH full-path cap        4
request-wide schema repair       +1 maximum
Workflow Coordinator LLM        0
```

P8-L-N itself finishes after the Router and the required Planner calls, so it
does not consume the Character Response Generator slot.

## Deterministic merge boundary

The coordinator normalizes only references from accepted typed results:

- Canonical source/evidence event refs and counterpart WorldCharacter refs;
- Graph evidence/last-event refs and revalidated relationship/path/character
  refs;
- stable axis-local references and accepted occurrence timestamps.

Independent results use exact event or WorldCharacter equality to join and
otherwise remain a bounded union. Dependent results must match the recipe's
exact dependency type. Code then deduplicates, ranks cross-axis matches before
single-axis results, applies stable timestamp/reference tie-breaking, truncates
to the resolved row cap, and derives a non-authoritative opaque
`workflow-ref-*` identifier.

This output is not yet an Evidence Bundle and contains no provider-visible
text. P8-L-P still owns canonical evidence snapshotting, content budgeting,
Character Response Generator streaming and the fenced response commit.

## Domain-first ownership

- `app.domains.chat.domain.workflow_recipe` owns the provider-neutral recipe,
  axis, dependency and selection contracts.
- `app.domains.chat.application.both_retrieval` owns request orchestration,
  parallel/sequential scheduling, downstream short-circuit and deterministic
  reference merge.
- `app.domains.memory.public` remains the only cross-domain Canonical typed
  retrieval boundary.
- `app.domains.relationships.public` remains the only cross-domain Graph typed
  retrieval boundary.
- Provider adapters remain under `app.integrations.llm`; the coordinator has
  no provider SDK or runtime/persistence import.
- SQLite, FTS5, LadybugDB, canonical revalidation and observation policy stay
  under their existing L/M typed services.

The standalone Canonical and Graph service methods continue to reject route
`BOTH`. Only the coordinator passes the shared internal tracker capability that
opens their already validated specialist execution for a BOTH request.

## Executable evidence

`test_p8_l_n_both_workflow_coordinator.py` proves:

- the three-entry registry and code override of an incompatible Router hint;
- Graph-then-Canonical ordering and event-reference intersection;
- Canonical-then-Graph ordering and WorldCharacter-reference intersection;
- actual simultaneous start of independent specialist Planners;
- dependency-zero and policy-denied downstream Planner short-circuit;
- one shared request-wide repair token across parallel Planners;
- deterministic exact join, dedupe, rank and resolved-row truncation;
- no coordinator LLM call and no Character Response Generator consumption;
- exact request/intent/tracker binding and coordinator-only BOTH entry.

The generated inventory freezes the updated J→K→L→M predecessor chain and the
N boundary. Tests use fake providers and typed recall adapters; live provider
calls remain zero.

### 2026-09-02 local technical Gate

The exact P8-L-N branch tree passed the following local checks before its
signed commit and Draft PR handoff:

- P8-L-N behavior and inventory: `12 passed`;
- P8-L-H through P8-L-N plus the adjacent OSS/L4 inventory selection:
  `104 passed`;
- complete backend suite: `1682 passed, 22 skipped` in `363.43s`;
- Python compilation: `compileall` passed;
- architecture boundary and inventory: `629` modules, `1546` internal edges,
  `2076` external imports and `312` legacy exact edges;
- current-tree L4 inventory: passed with `95` parity nodes;
- public route inventory: `179` operations;
- test-node baseline: `604` approved, `1704` current, `1100` new;
- local OSS CI policy: `10` required, `1` advisory and `8` workflows;
- secret allowlist metadata: `24` exact tuples;
- dependency licenses: `74` Python and `56` Node packages, with `4`
  conditional reviews accepted by policy;
- vulnerability audit: no known vulnerability in `74` Python packages and no
  known production Node vulnerability;
- J, K, L, M and N generated inventory checks: passed.

These checks prove the deterministic coordinator boundary and repository
regression state. They do not replace Hosted CI, installer/user validation,
held-out model evaluation or the user-owned merge Gate.

## Non-scope

- new SQL/Alembic/Embedded schema or LadybugDB generation;
- raw SQL, raw Cypher, Text-to-SQL or Text-to-Cypher;
- arbitrary DAG/expression, cycle, unbounded fan-out or iterative re-planning;
- Evidence Bundle text/snapshot and token budget integration;
- Character Response Generator, streaming and Assistant commit;
- World Chat send/retry API and generation lifecycle composition;
- `입력 중`, retry or other frontend behavior;
- live held-out model quality/latency PASS;
- installer, upgrade, backup or release changes.
