"""Attached activity tendency state and original commit/readiness rules."""
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.exceptions import TendencyAnalysisRequiredError


def _mark_tendency_error(
    db: Session, setting: models.AgentActivitySetting, message: str
) -> None:
    setting.tendency_error = message[:1000]
    db.commit()


def _has_tendency_analysis(setting: models.AgentActivitySetting) -> bool:
    profile = (
        setting.planner_tendency_profile
        if isinstance(setting.planner_tendency_profile, dict)
        else {}
    )
    criteria = profile.get("feed_seed_interest_criteria")
    return bool(
        setting.tendency_updated_at
        and setting.tendency_summary.strip()
        and setting.tendency_action_ranges
        and isinstance(criteria, str)
        and criteria.strip()
    )


def _ensure_tendency_analysis_ready(setting: models.AgentActivitySetting) -> None:
    if _has_tendency_analysis(setting):
        return
    raise TendencyAnalysisRequiredError(
        "커뮤니티 성향 분석을 먼저 실행해주세요."
    )


def _clear_tendency_analysis(setting: models.AgentActivitySetting) -> None:
    setting.tendency_summary = ""
    setting.tendency_action_ranges = {}
    setting.planner_tendency_profile = {}
    setting.tendency_updated_at = None
    setting.tendency_error = None
