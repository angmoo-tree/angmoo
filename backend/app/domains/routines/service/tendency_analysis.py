"""Tendency eligibility and attached result persistence with original commit order."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Callable
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.contracts.activity_management import ActivityOwner, TendencyPersona
from app.domains.routines.contracts.autonomy_management import AutonomyCredential
from app.domains.routines.contracts.tendency_analysis import TendencyAnalysisWorkflows, DetailT
from app.domains.routines.service import activity_settings, activity_logs
from app.domains.routines.service.tendency_settings import _mark_tendency_error


def prepare_tendency_analysis(db: Session, user: ActivityOwner, character_id: str, *, workflows: TendencyAnalysisWorkflows[DetailT]) -> tuple[TendencyPersona, models.AgentActivitySetting, AutonomyCredential]:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_mutable(user)
    workflows.ensure_llm_mode(character)
    workflows.ensure_imported_world_runtime_enabled(db, character=character)
    setting = activity_settings.ensure_setting(db, character.id)
    credential = workflows.get_credential(db, character.id)
    if credential is None or not credential.enabled:
        _mark_tendency_error(
            db, setting, "Agent credential is required before tendency analysis"
        )
        raise workflows.credential_required_error(
            "Agent credential is required before tendency analysis"
        )

    return character, setting, credential


def store_tendency_analysis(
    db: Session,
    setting: models.AgentActivitySetting,
    *,
    user: ActivityOwner,
    character: TendencyPersona,
    summary: str,
    action_ranges: dict[str, object],
    planner_profile: dict[str, object],
    reason: str,
    result_factory: Callable[[], str],
) -> None:
    setting.tendency_summary = summary
    setting.tendency_action_ranges = action_ranges
    setting.planner_tendency_profile = planner_profile
    setting.tendency_updated_at = datetime.now(UTC)
    setting.tendency_error = None
    db.commit()
    db.refresh(setting)
    activity_logs.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="tendency_analyzed",
        target_post_id=None,
        reason=reason,
        result=(
            result_factory()
        ),
    )
