# Adding a LangGraph node

Keep state keys and node results compatible with
`app/services/resident_contracts.py`. A node should receive only the context it
needs, return an explicit partial state update, and classify provider and
policy failures without embedding prompt or key material.

Add tests for success, invalid output, timeout, retry, and retry termination as
applicable. Prompt, trace, provider, or resident-orchestration changes require
hosted validation.
