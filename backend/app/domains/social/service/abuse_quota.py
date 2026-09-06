"""Reply/report limits and their public Social error contract."""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.identity.service import mutation_quota
from app.domains.social.exceptions import CommunityQuotaExceeded


_ACTION_POLICIES = {
    "reply": (
        ("reply_minute", timedelta(minutes=1), 10),
        ("reply_day", timedelta(days=1), 100),
    ),
    "report": (
        ("report_10m", timedelta(minutes=10), 5),
        ("report_day", timedelta(days=1), 30),
    ),
}


def consume(
    db: Session,
    *,
    user_id: str,
    action: str,
    now: datetime | None = None,
) -> None:
    policies = _ACTION_POLICIES.get(action)
    if policies is None:
        raise ValueError("Unsupported community quota action")
    retry_after = mutation_quota.consume(db, user_id=user_id, policies=policies, now=now)
    if retry_after is not None:
        raise CommunityQuotaExceeded(retry_after)
