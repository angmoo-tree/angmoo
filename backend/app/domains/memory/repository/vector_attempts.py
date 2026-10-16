"""Generation-independent call budget in the caller's bounded transaction."""
from sqlalchemy import text


def claim(session, keys, now):
    admitted = set()
    for doc_id, profile, digest, revision in keys:
        values = dict(item=doc_id.removeprefix("memory-item:"), profile=profile, digest=digest, revision=revision)
        old = session.execute(text("SELECT attempts,code,retry_after FROM memory_vector_attempts WHERE item_id=:item AND profile=:profile AND content_hash=:digest AND credential_revision=:revision"), values).first()
        if old and (old[0] >= 3 or old[1] == "terminal" or old[2] > now):
            continue
        count = old[0] + 1 if old else 1
        session.execute(text("""INSERT INTO memory_vector_attempts VALUES(:item,:profile,:digest,:revision,:count,NULL,:due)
            ON CONFLICT(item_id,profile,content_hash,credential_revision) DO UPDATE SET
            attempts=excluded.attempts,code=NULL,retry_after=excluded.retry_after"""),
            {**values, "count": count, "due": now + 30 * 2 ** (count - 1)})
        admitted.add(doc_id)
    return admitted


def finish(session, doc_id, profile, digest, revision, terminal):
    values = dict(item=doc_id.removeprefix("memory-item:"), profile=profile, digest=digest, revision=revision)
    if terminal:
        session.execute(text("UPDATE memory_vector_attempts SET code='terminal' WHERE item_id=:item AND profile=:profile AND content_hash=:digest AND credential_revision=:revision"), values)
    else:
        session.execute(text("DELETE FROM memory_vector_attempts WHERE item_id=:item AND profile=:profile AND content_hash=:digest"), values)
