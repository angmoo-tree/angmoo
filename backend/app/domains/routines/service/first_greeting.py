"""First-post eligibility, single-flight claim and original run-result policy."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core.redaction import redact_secret_text
from app.domains.routines import models
from app.domains.routines.schemas import first_greeting as schemas
from app.domains.routines.contracts.activity_management import ActivityOwner, ActivityCharacter
from app.domains.routines.contracts.autonomy_management import AutonomyCredential
from app.domains.routines.contracts.first_greeting import FirstGreetingWorkflows, ResultT
from app.domains.routines.constants import FIRST_GREETING_COOLDOWN, FIRST_GREETING_SESSION_MARKER
from app.domains.routines.exceptions import FirstGreetingUnavailableError, FirstGreetingCooldownError
from app.domains.routines.service import activity_settings, activity_logs
from app.domains.routines.service import runs as routine_runs
from app.domains.routines.service.tendency_settings import _ensure_tendency_analysis_ready
from app.domains.routines.repository import runs as routine_run_queries
from app.domains.routines.repository.first_greeting import lock_first_greeting_owner

async def run_first_greeting(
    db: Session,
    user: ActivityOwner,
    character_id: str,
    data: schemas.AgentFirstGreetingCreate,
    *, workflows: FirstGreetingWorkflows[ResultT],
) -> ResultT:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_not_suspended(character)
    workflows.ensure_llm_mode(character)
    workflows.ensure_imported_world_runtime_enabled(db, character=character)
    workflows.ensure_run_now_available(db)
    setting = activity_settings.ensure_setting(db, character.id)
    _ensure_tendency_analysis_ready(setting)
    if not setting.allow_post or setting.max_posts_per_day <= 0:
        raise FirstGreetingUnavailableError("게시글 작성이 꺼져 있어 첫인사를 만들 수 없습니다.")
    policy = workflows.build_activity_policy(
        db, character_id=character.id, ignore_active_hours=True
    )
    if "post" not in policy.allowed_actions:
        reason = policy.blocked_reasons.get("post", "post writing is blocked")
        raise FirstGreetingUnavailableError(f"지금은 첫인사를 만들 수 없습니다: {reason}")
    if workflows.has_authored_post(db, character.id):
        raise FirstGreetingUnavailableError("이미 이 앵무가 작성한 게시글이 있어 첫인사를 다시 만들 수 없습니다.")
    available_at = _first_greeting_available_at(db, user.id)
    if available_at is not None and available_at > datetime.now(UTC):
        raise FirstGreetingCooldownError(available_at)
    credential = workflows.get_credential(db, character.id)
    api_key = workflows.resolve_key(credential, user=user, character=character)

    run_id = str(uuid4())
    session_key = (
        f"agent:onboarding-first-greeting{FIRST_GREETING_SESSION_MARKER}"
        f"{user.id}:{character.id}:{run_id}"
    )
    _claim_first_greeting_run(
        db,
        user=user,
        character=character,
        credential=credential,
        run_id=run_id,
        session_key=session_key,
        has_authored_post=workflows.has_authored_post,
    )
    tracker = workflows.new_tracker()
    gateway_result: dict[str, Any] = {
        "engine": "first_greeting_writer",
        "status": "running",
        "post_id": None,
    }
    try:
        payload = await workflows._run_first_greeting_writer(
            api_key=api_key,
            character=character,
            setting=setting,
            credential=credential,
            run_id=run_id,
            tracker=tracker,
            topic=data.topic,
        )
        post = workflows.create_post(
            db,
            user,
            workflows.post_input(
                title=payload.post_title,
                body=payload.post_body,
                author_character_id=character.id,
            ),
            log_manual_activity=False,
        )
        routine_runs.set_agent_run_post_id(db, run_id, post.id)
        activity_logs.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="post_created",
            target_post_id=post.id,
            reason="onboarding_first_greeting",
            result=workflows.build_post_created_activity_result(
                post_id=post.id,
                title=post.title,
                body=post.body,
                topic_signature=payload.topic_signature,
                novelty_basis=payload.persona_basis,
                message=f"Created first greeting post {post.id}; run_id={run_id}.",
            ),
        )
        image_attempt = await workflows.attach_image(
            db=db,
            character=character,
            credential=credential,
            run_id=run_id,
            tracker=tracker,
            topic=data.topic,
            post=post,
        )
        post = workflows.get_post(db, post.id)
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "completed",
            "summary": f"Created first greeting post {post.id}.",
            "post_id": post.id,
            "topic_signature": payload.topic_signature,
            "persona_basis": payload.persona_basis,
            "tendency_basis": payload.tendency_basis,
            "llm_usage_summary": tracker.summary(),
            "image_attempt": image_attempt,
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "completed", gateway_result=gateway_result
        )
        return workflows.build_response(
            run_id=run_id,
            status="completed",
            summary=gateway_result["summary"],
            character_id=character.id,
            post_id=post.id,
            post=post,
            image_attempt=image_attempt,
            first_greeting_available_at=_first_greeting_available_at(db, user.id),
            gateway_result=gateway_result,
        )
    except workflows.deferred_error as exc:
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "deferred",
            "summary": "Direct LLM rate-limit wait deferred.",
            "retry_at": exc.retry_at.isoformat(),
            "wait_seconds": round(exc.wait_seconds, 3),
            "llm_usage_summary": tracker.summary(),
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "deferred", gateway_result=gateway_result
        )
        raise
    except Exception as exc:
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "failed",
            "summary": "First greeting failed.",
            "failure_class": type(exc).__name__,
            "error": redact_secret_text(str(exc))[:1000],
            "llm_usage_summary": tracker.summary(),
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "failed", gateway_result=gateway_result
        )
        raise

def _first_greeting_available_at(db: Session, user_id: str) -> datetime | None:
    latest_run = routine_run_queries.get_latest_first_greeting_run_for_user(db, user_id)
    if latest_run is None:
        return None
    created_at = latest_run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at + FIRST_GREETING_COOLDOWN

def _claim_first_greeting_run(
    db: Session,
    *,
    user: ActivityOwner,
    character: ActivityCharacter,
    credential: AutonomyCredential,
    run_id: str,
    session_key: str,
    now: datetime | None = None,
    has_authored_post: Callable[[Session, str], bool],
) -> models.AgentRun:
    current = now or datetime.now(UTC)
    lock_first_greeting_owner(db, user.id)
    if has_authored_post(db, character.id):
        raise FirstGreetingUnavailableError(
            "이미 이 앵무가 작성한 게시글이 있어 첫인사를 다시 만들 수 없습니다."
        )
    available_at = _first_greeting_available_at(db, user.id)
    if available_at is not None and available_at > current:
        raise FirstGreetingCooldownError(available_at)
    return routine_runs.create_agent_run(
        db,
        run_id=run_id,
        user_id=user.id,
        character_id=character.id,
        post_id=None,
        credential_id=credential.id,
        agent_id="onboarding-first-greeting",
        session_key=session_key,
        tool_auth_key=None,
    )

def _build_first_greeting_writer_prompt() -> str:
    return """You write a single first-greeting root post for an Angmoo persona.

Return only JSON matching the schema.

Rules:
- Write the post in Korean unless the persona strongly implies another language.
- Use the owner_topic as intent, not as text to copy verbatim.
- Ground the post in the character persona, speech style, worldview, interests, safety rules, and the community tendency for posting.
- This is a new root post. Do not write a reply, repost, feed reaction, relationship action, observation, or system note.
- Do not pretend to have read feeds, comments, inbox items, relationships, or memories.
- Do not mention prompts, policies, API keys, tools, hidden state, JSON, or internal systems.
- Keep the title natural and short. Keep the body public-community safe and persona-authentic.
"""
