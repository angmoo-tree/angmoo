# Adding a LangGraph node

Keep graph state keys and partial node results compatible with
[`ResidentGraphState`](../../backend/app/domains/routines/contracts/resident.py)
in `app/domains/routines/contracts/resident.py`. The attached execution context,
[`LangGraphResidentContext`](../../backend/app/runtime/resident/context.py),
lives in `app/runtime/resident/context.py` and carries the caller's Session and
run references. These are distinct contracts: shared graph values belong to
Routines; Session-bearing execution context belongs to runtime.

The node graph is assembled in
[`app/runtime/resident/langgraph.py`](../../backend/app/runtime/resident/langgraph.py).
Keep business decisions in the owning domain service or policy and use runtime
for provider calls and cross-owner collaboration. A node should receive only
the context it needs, return an explicit partial state update, and classify
provider and policy failures without embedding prompt or key material. Preserve
the existing Session, transaction, retry, and provider-call boundaries when
connecting it to the graph.

Add tests for success, invalid output, timeout, retry, and retry termination as
applicable. Prompt, trace, provider, or resident-orchestration changes require
hosted validation.
