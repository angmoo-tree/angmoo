"""Bind provided Daypart observations to the caller's existing Session."""

from collections.abc import Callable
from datetime import date
from functools import partial
from typing import Any

from sqlalchemy.orm import Session

from app.domains.characters.models import Character as _model_Character
from app.domains.memory.contracts.daypart import DaypartObservationReferences
from app.domains.memory.service import daypart_observations
from app.domains.routines.contracts.action_context import ResidentActionReferences
from app.domains.routines.service.action_candidates import _profile_display_name_for_action_menu
from app.domains.routines.utils.context_text import _clip_text
from app.domains.social.repository import posts as community_crud


def _build_daypart_memory_note(
    *,
    db: Session,
    activity_daypart: str,
    daypart_start_date: date,
    character: _model_Character,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    profile_references: Callable[[Session], ResidentActionReferences],
) -> str:
    return daypart_observations.build_daypart_memory_note(
        db=db,
        activity_daypart=activity_daypart,
        daypart_start_date=daypart_start_date,
        character=character,
        run_id=run_id,
        inbox_candidates=inbox_candidates,
        feed_interest_payload=feed_interest_payload,
        references=DaypartObservationReferences(
            post_author=partial(_daypart_observation_author, profile_references=profile_references), clip_text=_clip_text
        ),
    )

def _record_provided_daypart_observations(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    profile_references: Callable[[Session], ResidentActionReferences],
) -> None:
    return daypart_observations.record_provided_daypart_observations(
        db=db,
        activity_daypart=activity_daypart,
        memory_session_key=memory_session_key,
        daypart_start_date=daypart_start_date,
        character_id=character_id,
        run_id=run_id,
        inbox_candidates=inbox_candidates,
        feed_interest_payload=feed_interest_payload,
        references=DaypartObservationReferences(
            post_author=partial(_daypart_observation_author, profile_references=profile_references), clip_text=_clip_text
        ),
    )

def _daypart_observation_author(db: Session, source_post_id: str | None, missing: str | None, *, profile_references: Callable[[Session], ResidentActionReferences]) -> str | None:
    post = community_crud.get_post(db, source_post_id) if source_post_id else None
    return (
        _profile_display_name_for_action_menu(
            profile_references(db), user_id=post.author_user_id, character_id=post.author_character_id
        )
        if post is not None
        else missing
    )
