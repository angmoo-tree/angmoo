# P8-L-K Retrieval Router, semantic/policy envelope and clarification

## Outcome

P8-L-K turns on the first live provider-facing node in the split P8-L
retrieval topology: the Retrieval Router. It classifies a bounded chat turn as
`CURRENT_CONTEXT`, `CANONICAL`, `GRAPH`, `BOTH`, or `CLARIFICATION`, but it can
produce only semantic meaning. Canonical identity, owner/World/thread scope,
time, permissions, Memory state, query-operation capabilities and hard caps
remain code-owned.

This stage does not connect a new message-send endpoint and does not call a
Canonical Planner, Graph Planner or Character Response Generator. The existing
Chat v1 response path remains unchanged until the later orchestration and
streaming stages.

The implementation is tracked by [Issue #232](https://github.com/angmoo-tree/angmoo/issues/232)
on branch `feat/p8-l-k-retrieval-router-envelope`, based exactly on
`628369ed786eb0acb8d36f25be2a389b9f38646e`.

```text
stored user message + bounded recent context
        |
        v
deterministic preflight
        |
        v
Retrieval Router provider
        |
        v
strict RetrievalIntentEnvelope parser
        |
        v
same-World Entity + World-time Resolver
        |
        v
immutable ResolvedRetrievalEnvelope
        |
        +-- CURRENT_CONTEXT / CANONICAL / GRAPH / BOTH
        |
        `-- ambiguous identity, direction, World or time
              -> CLARIFICATION (never broadened to BOTH)
```

## Ownership and ports

`app.domains.chat` owns the strict Router wire parser, semantic envelope,
deterministic routing use case, safe clarification result and immutable policy
binding. `RetrievalRouterProviderPort` contains bounded conversation text and
display identity only. It deliberately has no owner, World, thread,
WorldCharacter, source or event identifier field.

`app.integrations.llm.retrieval_router` is the only provider-SDK adapter. It
uses the existing direct-LLM transport, requests one closed JSON response and
disables the helper's implicit JSON retry. A validation repair is therefore an
explicit second logical Router call counted against the J request-wide repair
token, not a hidden provider action.

`app.runtime.chat.retrieval_policy` implements the canonical SQLAlchemy scope
port. Before the Router runs it proves the claimed local owner, active owned
World, exact resolved thread, owner-controlled requester, active responder and
unblocked role pair. After semantic routing it resolves names/handles only
inside that same World, removes inactive, blocked, hidden or unobservable
candidates, reads the responding Character's Memory setting and converts
relative time with the World's IANA timezone.

The application use case imports the already-public H and I primitive
registries only to inject route-appropriate allowlists. The Router never sees
or chooses those primitives. `CURRENT_CONTEXT` and `CLARIFICATION` receive no
retrieval operations; `CANONICAL` receives only the H registry; `GRAPH`
receives only the I registry; and `BOTH` receives both.

## Strict semantic wire contract

The supported provider JSON has exact top-level fields. Unknown or missing
fields fail closed. Closed catalogs cover route, intent, entity role,
relationship dimension/polarity, time kind, aggregation, coordination hint and
clarification slot. At most four entity mentions are accepted.

The parser rejects any output containing canonical identifier fields, SQL,
Cypher, schema/table/column/label/property names, query operations or
row/hop/timeout/token limits. It also enforces these cross-field rules:

- `decision` must match the selected route;
- `BOTH` requires one bounded coordination hint and no other route may have it;
- `CLARIFICATION` requires one unresolved semantic slot;
- non-clarification routes cannot carry a clarification slot;
- `CURRENT_CONTEXT` cannot smuggle relationship, time or aggregation work;
- relationship from/to may use only requester/responding semantic aliases or
  an entity ref declared in the same envelope.

The direct provider prompt contains no canonical IDs. Character and
conversation text are explicitly untrusted data and cannot alter the schema or
policy.

## Code-owned resolution and clarification

`RetrievalRoutingService` creates `resolved-retrieval.v1` only after canonical
preflight. Its values are bound to the Router intent hash and request ID and
include:

- authenticated owner, current World and exact thread role tuple;
- entity-ref to same-World WorldCharacter-ID bindings;
- actual relationship from/to IDs derived from semantic refs;
- absolute UTC bounds derived from World-local time;
- Memory enabled state and visibility/observation policy;
- closed canonical/graph operation allowlists;
- row, hop, fan-out, timeout and token hard caps.

Ambiguous or unavailable identity, material direction, World or time produces
a new hash-bound `CLARIFICATION` intent. Only safe display name/handle
candidates may enter the clarification result. Blocked, inactive, hidden and
unobservable candidates are excluded and their IDs are never exposed. The
result has no retrieval operation allowlist, so ambiguity cannot become a
wider `BOTH` search.

## Calls, repair and metrics

The normal Router logical count is one. A schema/semantic output failure may
use the foreground request's single repair token, producing at most one second
Router logical call. A second invalid result fails closed. The direct adapter
allows no hidden JSON repair and reports physical attempts separately.

The K result records route, first-pass validity, repair use, clarification,
entity/direction/time resolution outcomes, Router logical calls, physical
attempts, provider and model. It retains the J route-aware tracker contract:
the `CURRENT_CONTEXT` and `CLARIFICATION` full-path cap is two because the later
Character Response Generator owns the one remaining user-visible call.

## P8-L-P Router stability correction

The P8-L-P integration correction keeps K's semantic and policy ownership but
closes the provider-schema gap exposed by an installed World Chat run. The
provider-facing schema now marks every nested object field as required when the
nullable object is present. Gemini's supported `responseJsonSchema` contract does
not receive `additionalProperties`; the domain parser remains the final fail-closed
authority for exact keys, cross-field rules and forbidden material.

The Router prompt fixes the decision/route matrix and includes a minimal
`CURRENT_CONTEXT` example for greetings and present-mood questions. In
particular, `안녕 지금 기분이 어때?` keeps entities empty and relationship,
time, aggregation, coordination and clarification fields null. A repair prompt
receives only an allowlisted validation code, never the rejected payload.

If the one request-wide repair is exhausted, the Chat domain creates a typed
`router-diagnostic.v1` value containing only the node, normalized validation
code, repair-used/exhausted flags and bounded physical-attempt count. The
lifecycle stores it under `chat_response_requests.node_state_json` without a
new migration. Raw Router output, prompt, conversation, persona, credential,
provider body and stack trace are never persisted or sent on the public stream.

Safe output-variability mismatches such as invalid JSON shape, decision/route
conflict or non-minimal `CURRENT_CONTEXT` terminate as
`router_schema_rejected` with `retryable=true`. This enables only the existing
user-selected retry flow: the same user message and response slot are reused,
while request, generation and attempt are new and the whole workflow starts at
the Router. Forbidden fields and raw SQL/Cypher markers remain nonretryable;
preflight identity, scope and policy rejection is unchanged. There is no
automatic retry or automatic Character Response Generator call after a Router
failure.

## Executable evidence

`test_p8_l_k_retrieval_router.py` proves:

- exact-key and closed-catalog parsing plus raw-query/canonical-ID rejection;
- one Router call and zero retrieval operations for `CURRENT_CONTEXT`;
- code-only same-World identity, direction, World-time and hard-cap injection;
- ambiguity becoming `CLARIFICATION`, never `BOTH`;
- blocked identity exclusion from clarification candidates;
- request-wide Router repair at most once;
- request deadline expiry cancelling the in-flight provider call;
- all 315 frozen Korean topology cases normalize into the strict K contract;
- the direct provider adapter disables hidden JSON repair and leaks no secret;
- the real SQLAlchemy policy adapter binds only the active, unblocked,
  same-World Character even when a same-name blocked Character exists.

No live provider call is made by the test suite. The 315 cases are executable
contract fixtures, not a claim that a production model has passed the final
held-out quality comparison. Model accuracy, warm/cold latency and the
one-shot-versus-split topology decision remain the P8-L-S evaluation Gate.

The exact working tree passed the full backend suite with `1,634 passed`,
`22 skipped` and `25 warnings`. Architecture inventory is current at 617
modules, 1,494 internal edges and 2,029 external imports; the P8-L-J frozen
predecessor inventory and the P8-L-K chained inventory are both current.

## Non-scope

- Canonical Retrieval Planner and its typed execution;
- Graph Retrieval Planner and its typed execution;
- BOTH dependency coordinator and Evidence Bundle;
- Character Response Generator and user-visible streaming;
- new message-send/retry API integration and `입력 중` UI;
- live held-out model-quality PASS;
- schema migration, installer format or Ladybug generation change.
