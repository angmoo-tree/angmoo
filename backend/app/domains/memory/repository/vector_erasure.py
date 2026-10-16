"""Erase only the selected items' projection state in the caller transaction."""
from sqlalchemy import delete
from app.domains.memory.models.vector_work import MemoryVectorWork, MemoryVectorDependency, MemoryVectorAttempt


def erase(session, identifiers):
    ids = tuple(identifiers)
    if len(ids) > 100:
        raise ValueError("memory_vector_erasure_page_limit")
    erase_selected(session, ids)


def erase_selected(session, item_selection):
    """Apply the caller's scoped item subquery in its existing scrub transaction."""
    for model in (MemoryVectorWork, MemoryVectorDependency, MemoryVectorAttempt):
        session.execute(delete(model).where(model.item_id.in_(item_selection)))
