# Adding a LangGraph node

Start with the graph that actually invokes the behavior. SNS orchestration is
assembled by [autonomous_activity/graph.py](../../backend/app/runtime/autonomous_activity/graph.py)
using `ParentState`, `LaneState` and typed `LanePorts` from the same runtime area.
Inbox, Feed and Routine lanes have different inputs and effects; a new node must
not silently share another lane's private state.

1. Put business authorization, allowed actions and state transitions in the
   owning domain service or policy. Runtime connects the concrete collaborators.
2. Keep checkpoint state serializable. Do not put Session objects, SDK clients,
   provider keys or live resources in graph state.
3. Return an explicit partial state update. Preserve guards, cancellation,
   owner/epoch checks and canonical effect receipts before applying output.
4. Read already committed results before considering another provider call.
   A checkpoint alone is not proof that an action committed; an unknown outcome
   is not permission to repeat a paid request or public action.
5. Preserve existing call, retry and deadline budgets. Account for SDK retries.
6. Record only bounded safe diagnostic facts, never prompt/key material.

Inspect [resident execution context](../../backend/app/runtime/resident/context.py)
when working on that runtime's caller. Do not treat an older graph name as the
entry point for every current SNS flow.

Add targeted success, invalid-output, cancellation, timeout and replay tests for
the affected node and its actual graph consumers. Use fake providers. Broader
remote validation follows [CI policy](../operations/ci-validation.md).
