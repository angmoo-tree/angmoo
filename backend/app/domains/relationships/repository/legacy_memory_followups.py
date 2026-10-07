"""Retire only the request attachment owned by obsolete memory queue work."""
from sqlalchemy import select, update
from app.domains.relationships.models.manual_review import RelationshipReviewRequest


def detach_discarded_memory_requests(session, request_ids):
    # ReviewWork and its memory receipts are independent canonical relationship
    # work over already saved memories. Keep those even when an obsolete memory
    # request had attached to them. Only the cascading request attachment goes.
    aliases = list(session.scalars(select(RelationshipReviewRequest).where(
        RelationshipReviewRequest.canonical_request_id.in_(request_ids),
        RelationshipReviewRequest.memory_request_id.not_in(request_ids))))
    for alias in aliases:
        root = session.get(RelationshipReviewRequest, alias.canonical_request_id)
        if root is not None:
            alias.state, alias.snapshot, alias.work_ids = root.state, root.snapshot, list(root.work_ids)
        alias.canonical_request_id = None
    session.execute(update(RelationshipReviewRequest).where(
        RelationshipReviewRequest.memory_request_id.in_(request_ids)).values(canonical_request_id=None))
    session.flush()
