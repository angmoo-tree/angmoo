"""Connect resident note policy to current Social authorization and source reads."""

from typing import Any
from sqlalchemy.orm import Session
from app.domains.routines.service import feed_history_notes as service
from app.domains.routines.schemas import feed_history as schemas
from app.domains.routines.models import AgentRun
from app.domains.social.models.posts import Post
from app.domains.social.exceptions import AgentRunAuthorizationError
from app.domains.social.repository import posts as post_repository
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.runtime.social.agent_tool_authorization import _get_agent_tool_run
from app.runtime.social.feed_history import RuntimeFeedHistoryReferences
from app.domains.routines.service import action_briefs as agent_briefs


class RuntimeFeedHistoryNoteReferences:
    authorization_error = AgentRunAuthorizationError

    @property
    def history(self) -> RuntimeFeedHistoryReferences:
        return RuntimeFeedHistoryReferences()

    def authorize(self, db: Session, *, session_key: str, action: str) -> AgentRun:
        return _get_agent_tool_run(db, session_key=session_key, action=action)

    def get_post(self, db: Session, post_id: str) -> Post | None:
        return post_repository.get_post(db, post_id)

    def is_public_context_visible(self, db: Session, post: Post) -> bool:
        return _is_post_public_context_visible(db, post)

    def normalize_post_seed_intent(self, value: Any, *, post_seed: Any = None) -> str:
        return agent_briefs.normalize_post_seed_intent(value, post_seed=post_seed)


def note_agent_tool_feed_interests(
    db: Session, session_key: str, data: schemas.AgentFeedInterestsCreate
) -> schemas.AgentToolNoteRead:
    return service.note_agent_tool_feed_interests(
        db, session_key, data, references=RuntimeFeedHistoryNoteReferences()
    )


def note_agent_tool_feed_history_sanitize(
    db: Session, session_key: str, data: schemas.AgentFeedHistorySanitizeCreate
) -> schemas.AgentToolNoteRead:
    return service.note_agent_tool_feed_history_sanitize(
        db, session_key, data, references=RuntimeFeedHistoryNoteReferences()
    )
