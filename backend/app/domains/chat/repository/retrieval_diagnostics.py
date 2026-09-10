"""Small disposable records, never query text or canonical response state."""
from datetime import UTC, datetime, timedelta
import json
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.domains.chat.models import ChatRetrievalDiagnostic
from app.contracts.retrieval_observation import MAX_BYTES, Observation


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
