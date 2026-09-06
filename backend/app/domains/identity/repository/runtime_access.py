"""Canonical installation row used by owner-only runtime diagnostics."""
from sqlalchemy.orm import Session
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY

def read_installation(db: Session) -> InstallationIdentity | None:
    return db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
