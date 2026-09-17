"""Register accepted content atomically with canonical Memory persistence."""
import hashlib
from app.domains.memory.models.embedding import MemoryVectorEligibility


def register_content(session, item, *, now):
    row = session.get(MemoryVectorEligibility, item.id)
    digest = hashlib.sha256(item.summary.encode("utf-8")).hexdigest()
    if row is None:
        row = MemoryVectorEligibility(memory_item_id=item.id, item_version=item.version,
            content_hash=digest, registration_revision="memory-vector.v1", registered_at=now)
        session.add(row)
    else:
        row.item_version, row.content_hash = item.version, digest
    return row
