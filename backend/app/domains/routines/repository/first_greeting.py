"""The original PostgreSQL per-owner first-greeting transaction lock."""
import hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_first_greeting_owner(db: Session, user_id: str) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        lock_key = int.from_bytes(
            hashlib.sha256(
                f"angmoo:first-greeting:{user_id}:v1".encode("utf-8")
            ).digest()[:8],
            byteorder="big",
            signed=True,
        )
        db.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
