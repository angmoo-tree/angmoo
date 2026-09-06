"""Bind Social authorization to the existing same-Session owner queries."""

from sqlalchemy.orm import Session
from app.domains.identity.models import User
from app.domains.routines.models import AgentRun
from app.domains.social.service import agent_tool_authorization as service
from app.domains.routines.repository import runs as agent_run_crud
from app.runtime.resident import activity_policy as agent_activity_policy


class RuntimeAgentToolReferences:
    @property
    def activity_policy_denied(self) -> type[Exception]:
        return agent_activity_policy.ActivityPolicyDeniedError

    def get_active_run_for_tool_auth_key(
        self, db: Session, key: str
    ) -> AgentRun | None:
        return agent_run_crud.get_active_run_for_tool_auth_key(db, key)

    def get_active_run_for_session(self, db: Session, key: str) -> AgentRun | None:
        return agent_run_crud.get_active_run_for_session(db, key)

    def get_latest_run_for_tool_auth_key(
        self, db: Session, key: str
    ) -> AgentRun | None:
        return agent_run_crud.get_latest_run_for_tool_auth_key(db, key)

    def get_latest_run_for_session(self, db: Session, key: str) -> AgentRun | None:
        return agent_run_crud.get_latest_run_for_session(db, key)

    def get_user(self, db: Session, user_id: str) -> User | None:
        return db.get(User, user_id)

    def assert_action_allowed(self, db: Session, *, run: AgentRun, action: str) -> None:
        return agent_activity_policy.assert_action_allowed(db, run=run, action=action)


def _get_agent_tool_run(
    db: Session,
    *,
    session_key: str,
    action: str,
    requested_post_id: str | None = None,
    requested_character_id: str | None = None,
) -> AgentRun:
    return service._get_agent_tool_run(
        db,
        references=RuntimeAgentToolReferences(),
        session_key=session_key,
        action=action,
        requested_post_id=requested_post_id,
        requested_character_id=requested_character_id,
    )


def _agent_tool_user(
    db: Session, run: AgentRun, *, action: str, session_key: str
) -> User:
    return service._agent_tool_user(
        db,
        run,
        references=RuntimeAgentToolReferences(),
        action=action,
        session_key=session_key,
    )


def _ensure_tick_action_allowed(
    db: Session, *, session_key: str, run: AgentRun, action: str
) -> None:
    return service._ensure_tick_action_allowed(
        db,
        references=RuntimeAgentToolReferences(),
        session_key=session_key,
        run=run,
        action=action,
    )
