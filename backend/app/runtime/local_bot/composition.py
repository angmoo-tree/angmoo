"""Connect actual LocalBot actions to the original Social and activity owners."""

from app.domains.local_bot.contracts.actions import LocalBotWorkflows
from app.domains.routines.service import activity_logs
from app.runtime.local_bot import queries
from app.runtime.local_bot.rate_limits import build_rate_limit_workflows
from app.services import community, post_image_generation


def build_bot_workflows() -> LocalBotWorkflows:
    return LocalBotWorkflows(
        social=community,
        reads=queries,
        limits=build_rate_limit_workflows(),
        log_activity=activity_logs.log_activity,
        request_image=post_image_generation.create_local_api_post_image_request,
    )
