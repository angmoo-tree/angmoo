"""Small disposable records, never query text or canonical response state."""
from datetime import UTC, datetime, timedelta
import json
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.domains.chat.models import ChatRetrievalDiagnostic
from app.contracts.retrieval_observation import MAX_BYTES, Observation


def save_postgresql(engine, observation: Observation) -> bool:
    """Capture after the authoritative commit, using its pool but no business locks.

    READ COMMITTED is limited to this disposable table. A transaction advisory
    lock serializes its bounded retention scan; a busy writer skips this capture
    instead of delaying chat. The next changed observation can try again.
    """
    from time import monotonic
    from sqlalchemy import text
    from app.core.postgresql_deadline import read_deadline
    deadline = monotonic() + .25
    with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
        with connection.begin(), read_deadline(connection, deadline):
            connection.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
            connection.exec_driver_sql("SET LOCAL statement_timeout='250ms'")
            # App-owned namespace, shared only by retrieval diagnostic writers.
            if not connection.scalar(text('SELECT pg_try_advisory_xact_lock(1886221416, 1)')):
                return False
            with Session(connection) as db:
                save(db, observation)
                db.commit()
    return True


def save(db: Session, observation: Observation) -> None:
    payload = json.dumps(observation.payload(), ensure_ascii=True, separators=(",", ":"))
    size = len(payload.encode())
    if size > MAX_BYTES or not observation.request_id:
        return
    now = datetime.now(UTC)
    # The table has <=1000 rows by construction; expired deletion is indexed.
    db.execute(delete(ChatRetrievalDiagnostic).where(ChatRetrievalDiagnostic.expires_at <= now))
    existing = db.get(ChatRetrievalDiagnostic, observation.request_id)
    if existing is None:
        ids = list(db.scalars(select(ChatRetrievalDiagnostic.request_id).order_by(ChatRetrievalDiagnostic.expires_at.desc(), ChatRetrievalDiagnostic.request_id).offset(999)))
        if ids:
            db.execute(delete(ChatRetrievalDiagnostic).where(ChatRetrievalDiagnostic.request_id.in_(ids)))
        db.add(ChatRetrievalDiagnostic(request_id=observation.request_id, expires_at=now+timedelta(days=7), payload_bytes=size, payload_json=payload))
    else:
        existing.payload_json, existing.payload_bytes = payload, size
    db.flush()


def read(db: Session, request_id: str) -> dict:
    row = db.get(ChatRetrievalDiagnostic, request_id)
    if row is None:
        return {"status": "not_recorded", "record": None}
    expires = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
    if expires <= datetime.now(UTC):
        return {"status": "expired", "record": None}
    try:
        from app.domains.chat.schemas import DiagnosticRecord
        record = DiagnosticRecord.model_validate_json(row.payload_json).model_dump()
    except ValueError:
        return {"status": "unavailable", "record": None}
    return {"status": "available", "record": record}
