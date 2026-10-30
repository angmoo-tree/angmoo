"""Reviewed checkpoint types for the frozen schema-41 Angmoo runtime."""
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# StrEnum declared in a data-only contracts module; no constructor I/O.
# The actual phone inventory contains this type and SDK built-in safe types.
ALLOWED=(('app.domains.memory.contracts.hybrid_recall','RecallAxisStatus'),)


def checkpoint_serde():
    return JsonPlusSerializer(pickle_fallback=False,allowed_json_modules=ALLOWED,allowed_msgpack_modules=ALLOWED)
