# P8-L-I graph recall facade

## Outcome

P8-L-I turns the existing P7 relationship graph query boundary into a bounded,
evidence-safe retrieval facade. It does not add a graph store, a migration, a
provider call, a Retrieval Router, or a Graph Planner. SQLite remains canonical
and LadybugDB remains a replayable projection.

The stable consumer boundary is `app.domains.relationships.public`. A future
Chat retrieval coordinator supplies already-resolved owner, World, subject and
counterpart identifiers through `GraphRecallQuery`; it cannot supply SQL,
Cypher, labels, properties, table names, arbitrary predicates, or an unbounded
traversal.

```text
resolved retrieval scope
        |
        v
relationships.public GraphRecallService
  -> closed primitive registry and validator
  -> RelationshipGraphQueryPort
  -> LadybugDB bounded templates
  -> SQLite canonical relationship, membership, block and observation facts
  -> GraphRecallResult
```

## Closed v1 contract

The version is `graph-recall.v1`. The six allowlisted operations are:

| Operation | Required input | Hard boundary |
| --- | --- | --- |
| `direct_relationship` | counterpart, direction | exact pair, at most 20 results |
| `relationship_evidence` | counterpart, direction | at most 5 evidence events |
| `shared_neighbors` | counterpart, direction | at most 20 accepted nodes |
| `shortest_path` | counterpart, direction | one path, 1-3 hops |
| `rank_related_characters` | ranking mode | positive, tense or recent; at most 20 |
| `relationship_neighborhood` | depth | depth 1-2, at most 20 nodes and 40 edges |

The validator rejects missing or malformed scope identifiers, self-targeting,
counterparts on operations that do not accept one, unknown enum values, result
limits above the operation cap, paths above three hops, and neighborhoods above
depth two. `GraphRecallQuery` contains no free-form query language.

## Domain and runtime ownership

`app.domains.relationships.graph_recall` owns the framework-free request,
result, primitive registry, validation, orchestration, fallback policy and
candidate acceptance rules. It depends only on relationship-domain graph-read
types and ports.

`app.runtime.graph_projection.relationship_graph_read` implements the narrow
canonical gateway with SQLAlchemy and composes the service with the existing
LadybugDB-backed `RelationshipGraphQueryPort`. Provider transport errors are
normalized before they enter the domain. A caller outside the relationships
domain does not import the LadybugDB integration repository.

The current P7 API graph read remains compatible. Its existing public response
schema and route are not replaced by the recall contract.

## Canonical and epistemic revalidation

Every accepted relationship edge must still exist in the same World in
canonical SQLite. Actor and target WorldCharacter memberships must be active,
neither endpoint may be blocked, and the actor/target direction must match the
projected edge. A projection version mismatch records a stale-edge metric and
uses the current canonical relationship snapshot; stale projected values are
never returned.

The responding subject must also be able to know the source event. An event is
observed when the subject is its actor or target, or when an `observed` feed
receipt connects that subject to a canonical evidence Post. Invalidated,
ineligible, failed, deleted, report-hidden, non-public, cross-World or
unobserved evidence is excluded. This rule also applies to indirect path and
shared-neighbor edges, so graph connectivity is not treated as omniscient
Character knowledge.

Returned node identifiers are independently checked for same-World active
membership, non-deleted Character state and no block with the subject. A path
is accepted only when every node, every oriented edge, endpoint order and
direction survive; otherwise the whole path becomes no evidence. Neighborhood
edges must remain reachable from the subject within the requested depth.

Provider-returned evidence cannot introduce an unrelated event. Its
relationship-state reference must belong to the already revalidated direct
pair, its projected version cannot exceed the canonical version, and the
canonical event actor/target must match the requested direction before source
visibility and observation are checked.

## Degraded behavior

Projection disabled, rebuild, failed rebuild, query timeout, provider outage
and malformed provider results are normal degraded outcomes rather than Chat
request exceptions.

| Primitive | Bounded canonical behavior during graph failure |
| --- | --- |
| direct relationship | exact directional `RelationshipState` fallback |
| relationship evidence | exact directional state plus revalidated last-event evidence |
| shared neighbors | intersection of two bounded canonical direct-edge sets |
| ranking | bounded subject-direct set with deterministic canonical ranking |
| shortest path | degraded/no evidence; no relational full scan |
| neighborhood | degraded/no evidence; no relational full scan |

When projection lag is present, graph candidates still undergo canonical
revalidation. A zero-result fallback-capable primitive uses the same bounded
canonical path and reports `lagging`; path and neighborhood never expand into
an unbounded SQLite traversal. Graph failure therefore leaves basic Chat and
canonical Memory recall available to their later coordinator.

## Executable evidence

`backend/tests/test_p8_l_i_graph_recall.py` proves the closed six-operation
registry, limits, stale replacement, direction, observation filtering,
same-World owner scope, blocked fail-closed behavior, shared/path/rank and
neighborhood revalidation, graph-disabled fallback, and the real SQLAlchemy
runtime composition. Existing P7 graph API and repository tests remain in the
focused regression set.

`p8-l-i-graph-recall-inventory.json` is generated and checked in tests. It
chains the frozen P8-L-H inventory, records zero canonical schema changes,
freezes the primitive/fallback matrix, and keeps live Router/Planner calls,
multi-step plan schemas, Evidence Bundle merge, Character response generation,
Chat send/stream/retry and Memory owner UI outside this stage.
