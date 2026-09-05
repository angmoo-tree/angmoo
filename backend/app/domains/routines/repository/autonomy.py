"""Global transaction lock acquired before the selected-World lock."""
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.domains.routines.constants import SERVER_LLM_AUTONOMY_CAPACITY_LOCK_KEY

def _lock_server_llm_autonomy_capacity(db: Session) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.execute(
        text("select pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": SERVER_LLM_AUTONOMY_CAPACITY_LOCK_KEY},
    )
