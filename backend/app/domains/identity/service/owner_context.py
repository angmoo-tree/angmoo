"""Installation ownership queries that participate in the caller session."""
from sqlalchemy.orm import Session
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import InstallationIdentity


def is_claimed_local_owner(db: Session, user_id: str) -> bool:
    installation = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
    return bool(
        installation is not None
        and installation.bootstrap_state == "claimed"
        and installation.owner_user_id == user_id
    )
