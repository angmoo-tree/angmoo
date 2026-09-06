from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy.orm import Session

from app.domains.routines import models, schemas
from app.core import prompt_safety
from app.domains.routines.contracts.feed_cues import FeedCueWorkflows
from app.domains.routines.contracts.activity_management import ActivityOwner
from app.domains.routines.exceptions import AgentFeedCueUnavailableError, AgentFeedCueConflictError
from app.domains.routines.service import activity_settings
from app.domains.routines.service.tendency_settings import _has_tendency_analysis
from app.domains.routines.contracts.feed_cues import FeedCueIdentity
from app.domains.routines.repository.feed_cues import get_pending_feed_cue


def create_feed_cue(
    db: Session, *, user: FeedCueIdentity, character: FeedCueIdentity, topic: str
) -> models.AgentFeedCue:
    cue = models.AgentFeedCue(
        user_id=user.id,
        character_id=character.id,
        topic=topic.strip(),
        status="pending",
    )
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return cue


def mark_pending_feed_cue_used(
    db: Session, *, character_id: str, run_id: str | None, post_id: str
) -> models.AgentFeedCue | None:
    cue = get_pending_feed_cue(db, character_id)
    if cue is None:
        return None
    cue.status = "used"
    cue.consumed_run_id = run_id
    cue.consumed_post_id = post_id
    cue.consumed_at = datetime.now(UTC)
    db.commit()
    db.refresh(cue)
    return cue


def get_feed_cue(
    db: Session, user: ActivityOwner, character_id: str,
    *, workflows: FeedCueWorkflows,
) -> schemas.AgentFeedCueRead | None:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_llm_mode(character)
    cue = get_pending_feed_cue(db, character.id)
    return schemas.AgentFeedCueRead.model_validate(cue) if cue else None


def give_feed_cue(
    db: Session, user: ActivityOwner, character_id: str, data: schemas.AgentFeedCueCreate,
    *, workflows: FeedCueWorkflows,
) -> schemas.AgentFeedCueRead:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_not_suspended(character)
    workflows.ensure_llm_mode(character)
    workflows.ensure_imported_world_runtime_enabled(db, character=character)
    workflows.ensure_feed_cues_available(db)
    setting = activity_settings.ensure_setting(db, character.id)
    if not _has_tendency_analysis(setting):
        raise AgentFeedCueUnavailableError("커뮤니티 성향 분석을 먼저 실행해주세요.")
    if not setting.auto_enabled:
        if not data.manual_run:
            raise AgentFeedCueUnavailableError("자율 활동 중인 앵무에게만 모이를 줄 수 있습니다.")
    if not setting.allow_post or setting.max_posts_per_day <= 0:
        raise AgentFeedCueUnavailableError("게시글 작성이 허용된 앵무에게만 모이를 줄 수 있습니다.")
    policy = workflows.build_activity_policy(
        db, character_id=character.id, ignore_active_hours=True
    )
    if "post" not in policy.allowed_actions:
        reason = policy.blocked_reasons.get("post", "post writing is blocked")
        raise AgentFeedCueUnavailableError(
            f"지금은 글쓰기 제한 때문에 모이를 받을 수 없습니다: {reason}"
        )
    if get_pending_feed_cue(db, character.id) is not None:
        raise AgentFeedCueConflictError("이미 다음 활동을 기다리는 모이가 있습니다.")
    _ensure_feed_cue_prompt_safety(data.topic, invalid_prompt=workflows.prompt_injection_error)
    cue = create_feed_cue(
        db, user=user, character=character, topic=data.topic
    )
    return schemas.AgentFeedCueRead.model_validate(cue)


def _ensure_feed_cue_prompt_safety(topic: str, *, invalid_prompt: type[Exception]) -> None:
    try:
        prompt_safety.ensure_no_prompt_injection_text(
            topic,
            field_name="topic",
            field_kind="feed_cue",
        )
    except prompt_safety.PromptSafetyError as exc:
        raise invalid_prompt(
            "feed_cue_prompt_injection_detected"
        ) from exc
