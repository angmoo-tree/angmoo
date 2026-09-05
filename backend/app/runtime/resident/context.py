"""Attached execution records shared by a resident run on its caller Session."""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.domains.characters.models import Character, CharacterState
from app.domains.identity.models import LlmCredential
from app.domains.routines.models import AgentFeedCue
from app.domains.social.public import SocialSearchIndexPort, SocialSearchState
from app.domains.routines.contracts import activity_policy as agent_activity_policy


@dataclass(frozen=True)
class LangGraphResidentContext:
    db: Session
    run_id: str
    user_id: str
    agent_id: str
    session_key: str
    character: Character
    credential: LlmCredential
    state: CharacterState | None
    activity_policy: agent_activity_policy.ActivityPolicy
    selected_post_id: str | None
    run_started_at: datetime
    feed_cue: AgentFeedCue | None = None
    memory_session_key: str | None = None
    daypart_start_date: date | None = None
    activity_daypart: str | None = None
    require_public_action: bool = False
    run_mode: str = "scheduled"
    relationship_point_id: int | None = None
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None
    social_search_index: SocialSearchIndexPort | None = None
    social_search_state: SocialSearchState = SocialSearchState.UNAVAILABLE

