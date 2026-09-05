"""Claimed-owner access decision for local runtime diagnostics."""
from sqlalchemy.orm import Session
from app.domains.identity.repository.runtime_access import read_installation

def is_runtime_owner(db: Session, owner_id: str) -> bool:
    installation = read_installation(db)
    return not (
        installation is None
        or installation.bootstrap_state != "claimed"
        or installation.owner_user_id != owner_id
    )
