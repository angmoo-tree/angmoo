"""Connect LocalBot key changes to the existing activity log."""
from app.domains.local_bot.contracts.key_management import LocalKeyWorkflows
from app.domains.routines.service.activity_logs import log_activity


def build_local_key_workflows() -> LocalKeyWorkflows:
    return LocalKeyWorkflows(log_activity=log_activity)
