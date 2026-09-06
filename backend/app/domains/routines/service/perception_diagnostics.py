from __future__ import annotations

from app.domains.routines.constants import FEED_PERCEPTION_DEBUG_ACTION_TYPE
from app.domains.routines.service import activity_logs as agent_crud
from app.domains.routines.service.decision_results import _safe_perception_text
from sqlalchemy.orm import Session
from typing import Any
import json


def _format_feed_perception_debug_result(
    *, run_id: str, feed_perception_result: dict[str, Any]
) -> str | None:
    if feed_perception_result.get("status") != "ok":
        return None
    perception = feed_perception_result.get("perception")
    if not isinstance(perception, dict):
        return None

    interesting_posts: list[dict[str, str]] = []
    raw_posts = perception.get("interesting_posts")
    if isinstance(raw_posts, list):
        for item in raw_posts[:5]:
            if not isinstance(item, dict):
                continue
            interesting_posts.append(
                {
                    "post_id": _safe_perception_text(item.get("post_id"), 80),
                    "character_thought": _safe_perception_text(
                        item.get("character_thought"), 180
                    ),
                }
            )

    payload = {
        "run_id": run_id,
        "interesting_posts": interesting_posts,
        "character_thoughts": _safe_perception_text(
            perception.get("character_thoughts"), 500
        ),
        "post_seed": _safe_perception_text(perception.get("post_seed"), 240),
        "no_relevant_signal": bool(perception.get("no_relevant_signal")),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _log_feed_perception_debug(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    run_id: str,
    feed_perception_result: dict[str, Any],
) -> None:
    result = _format_feed_perception_debug_result(
        run_id=run_id, feed_perception_result=feed_perception_result
    )
    if result is None:
        return
    agent_crud.log_activity(
        db,
        user_id=user_id,
        character_id=character_id,
        action_type=FEED_PERCEPTION_DEBUG_ACTION_TYPE,
        target_post_id=None,
        reason=f"{FEED_PERCEPTION_DEBUG_ACTION_TYPE} run_id={run_id}",
        result=result,
    )
