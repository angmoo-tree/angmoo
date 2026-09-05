"""Change the attached credential only; the caller keeps its original transaction."""
from datetime import datetime
from app.domains.identity.models import LlmCredential


def set_cooldown_until(credential: LlmCredential, *, cooldown_until: datetime | None) -> None:
    credential.cooldown_until = cooldown_until
