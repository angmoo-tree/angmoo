"""Bind actual same-Session projections and the original Routines log writer."""

from app.domains.local_bot.contracts.rate_limits import RateLimitWorkflows
from app.domains.routines.service import activity_logs
from app.runtime.local_bot import queries


def build_rate_limit_workflows() -> RateLimitWorkflows:
    return RateLimitWorkflows(reads=queries, log_activity=activity_logs.log_activity)
