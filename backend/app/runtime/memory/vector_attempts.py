"""Import legacy budgets once, before issuing any new physical request."""
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from sqlalchemy import text
from contextlib import closing
import sqlite3
from app.domains.memory.repository import vector_attempts as store


def import_legacy(projection):
    if projection._attempts_ready:
        return
    for index in projection._retained_indexes():
        # Read ordinary budget tables even when Vec1's own derived schema is
        # damaged. Never create a missing old database or discard its failure.
        factory = (lambda: closing(sqlite3.connect(index.database_path.as_uri()+"?mode=rw", uri=True))) if hasattr(index, "database_path") else index._connect
        try:
            with factory() as connection:
                _import_one(projection, connection)
        except sqlite3.Error as exc:
            from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError
            error = MemoryVectorProjectionError("memory_vector_legacy_budget_unavailable")
            error.sqlite_errorcode = getattr(exc, "sqlite_errorcode", None)
            raise error from None
    projection._attempts_ready = True


def _import_one(projection, connection):
    connection.execute("PRAGMA busy_timeout=25")
    connection.execute("CREATE TABLE IF NOT EXISTS embedding_attempts_v2 (document_id TEXT NOT NULL, profile TEXT NOT NULL, content_hash TEXT NOT NULL, credential_revision TEXT NOT NULL, attempts INTEGER NOT NULL, code TEXT, retry_after REAL NOT NULL, PRIMARY KEY(document_id,profile,content_hash,credential_revision))")
    connection.commit()
    cursor = connection.execute("SELECT document_id,profile,content_hash,credential_revision,attempts,code,retry_after FROM embedding_attempts_v2")
    while rows := cursor.fetchmany(64):
        with projection._factory() as session:
            def copy():
                for identifier, profile, digest, revision, attempts, code, due in rows:
                    session.execute(text("""INSERT INTO memory_vector_attempts VALUES (:item,:profile,:digest,:revision,:attempts,:code,:due)
                        ON CONFLICT(item_id,profile,content_hash,credential_revision) DO UPDATE SET
                        attempts=max(attempts,excluded.attempts),retry_after=max(retry_after,excluded.retry_after),
                        code=CASE WHEN code='terminal' OR excluded.code='terminal' THEN 'terminal' ELSE code END"""),
                        dict(item=identifier.removeprefix("memory-item:"), profile=profile,digest=digest,
                            revision=revision,attempts=attempts,code=code,due=due))
            run_sqlite_session_immediate(session, copy, require_clean=True)
    # Replay after a crash uses max(), never lowers a budget.
    connection.execute("DELETE FROM embedding_attempts_v2")
    connection.commit()


def claim(projection, keys, now, *, prepared=()):
    import_legacy(projection)
    # Fail admission before paying when the local projection is already busy.
    with projection.index._connect() as connection:
        connection.execute("PRAGMA busy_timeout=25")
        connection.execute("BEGIN IMMEDIATE")
        connection.rollback()
    with projection._factory() as session:
        def admit():
            from app.domains.memory.repository.vector_queue import owns
            from app.domains.memory.models.vector_work import MemoryVectorWork
            from app.runtime.memory.vector_proof import current
            allowed = set()
            for value in prepared:
                if not owns(session, value.claim) or not current(session, value.proof):
                    continue
                if value.claim is not None:
                    work = session.get(MemoryVectorWork, (value.claim.generation, value.item_id))
                    work.lease_until = work.due_at = now + 120
                allowed.add(f"memory-item:{value.item_id}")
            admitted = tuple(key for key in keys if not prepared or key[0] in allowed)
            return store.claim(session, admitted, now)
        return run_sqlite_session_immediate(session, admit, require_clean=True)


def finish(projection, doc_id, profile, digest, revision, terminal):
    with projection._factory() as session:
        run_sqlite_session_immediate(session, lambda: store.finish(session, doc_id, profile, digest, revision, terminal), require_clean=True)
