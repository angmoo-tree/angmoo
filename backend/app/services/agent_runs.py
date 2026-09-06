from app.domains.memory.service.daypart import purge_expired_events as _purge_expired_daypart_memory_events
from app.domains.memory.service.daypart import event_exists as _daypart_memory_event_exists
from app.domains.memory.service.daypart import record_memory_event as _record_daypart_memory_event
from app.domains.memory.service.daypart_observations import filter_daypart_duplicate_feed_interest as _filter_daypart_duplicate_feed_interest
from app.domains.memory.service.daypart_observations import filter_daypart_duplicate_inbox_candidates as _filter_daypart_duplicate_inbox_candidates
from app.domains.memory.service import daypart_observations
from app.domains.memory.contracts.daypart import DaypartObservationReferences
import app.domains.social.repository.posts as social_posts_repository
from app.domains.social.service import visibility as social_visibility
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences
from app.domains.routines.service.action_candidates import _profile_display_name_for_action_menu
from app.domains.routines.service.action_admission import _profile_following_status
from app.domains.social.repository.resident_context import _has_character_like
from app.domains.social.repository.resident_context import _has_character_repost
from app.domains.social.repository.resident_context import _has_character_replied_to_thread
from app.domains.social.repository.resident_context import _is_direct_reply_to_character_post_for_action_gate
from app.domains.routines.constants import GEMINI_FREE_FEED_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_CANDIDATE_MAX
from app.domains.routines.service.action_candidates import _profile_target_parts
from app.domains.routines.constants import GEMINI_FREE_POLICY_ID
from app.domains.routines.utils.context_text import _clip_text
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import schemas
from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue
from app.domains.characters.models import Character as _model_Character
from app.runtime.persistence.model_registration import register_models
register_models()
from app.config import settings
from app.runtime.routines import activity_policy as agent_activity_policy
from app.domains.routines.service.action_briefs import is_feed_scan_community_theme_brief
from app.core.context_text import neutralize_context_text


logger = logging.getLogger(__name__)


# OpenClaw validates the allowlist before honoring tool_choice="none".


GEMINI_FREE_CREATE_POST_MAX = 1
COMPLETE_TICK_ACTION_TYPES = (
    "create_post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)



























def _format_v6_action_menu(
    db: Session,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    relationship_review_candidate: str = "- none",
    feed_cue: _model_AgentFeedCue | None = None,
) -> str:
    allowed = set(allowed_actions)
    sections: list[str] = [
        "공통 규칙:",
        "- 여기에 표시되지 않은 공개 행동은 이번 tick에서 실행하지 않는다.",
        "- 선택한 tool call은 순차 실행한다.",
        f"- effective_tier: {GEMINI_FREE_POLICY_ID}",
        f"- inbox 공개 반응 대상은 최대 {GEMINI_FREE_INBOX_CANDIDATE_MAX}개 thread다.",
        f"- feed 공개 반응 대상은 최대 {GEMINI_FREE_FEED_CANDIDATE_MAX}개 post다.",
        f"- inbox 선택 대상의 공개 행동은 최대 {GEMINI_FREE_INBOX_ACTION_MAX}개다.",
        f"- feed 선택 대상의 공개 행동은 최대 {GEMINI_FREE_FEED_ACTION_MAX}개다.",
    ]

    inbox_sections: list[str] = []
    inbox_allowed = allowed - {"post", "repost", "unfollow", "observe"}
    for index, item in enumerate(
        inbox_candidates[:GEMINI_FREE_INBOX_CANDIDATE_MAX], start=1
    ):
        actions = _v6_possible_post_actions(
            db,
            character_id=character_id,
            allowed=inbox_allowed,
            post_id=str(item["source_post_id"]),
            author_target_type=item.get("actor_target_type"),
            author_target_id=item.get("actor_target_id"),
            reply_root_post_id=str(item["root_post_id"]),
            reply_label="대꾸하기",
        )
        if not actions:
            continue
        inbox_sections.append(
            "\n".join(
                [
                    f"Inbox 후보 {index}",
                    f"notification_id: {item['notification_id']}",
                    f"root_post_id: {item['root_post_id']}",
                    f"source_post_id: {item['source_post_id']}",
                    f"상대: {item['actor_name']} ({item['actor_ref']})",
                    f"상대 대꾸 요약: {item['source_body']}",
                    f"후보 이유: {item.get('candidate_reason') or '-'}",
                    f"짧은 맥락: {item.get('reply_context') or '-'}",
                    "지금 가능한 행동:",
                    *actions,
                ]
            )
        )
    sections.append("\nInbox 기반 행동:")
    sections.append("\n\n".join(inbox_sections) if inbox_sections else "- none")

    feed_sections: list[str] = []
    interests = feed_interest_payload.get("interests")
    has_feed_interest_context = False
    if isinstance(interests, list):
        for index, item in enumerate(
            interests[:GEMINI_FREE_FEED_CANDIDATE_MAX], start=1
        ):
            if not isinstance(item, dict):
                continue
            post_id = str(item.get("post_id") or "").strip()
            if not post_id:
                continue
            post = social_posts_repository.get_post(db, post_id)
            if post is None or not social_visibility.is_post_public_context_visible(db, post):
                continue
            has_feed_interest_context = True
            author_target_type, author_target_id = _profile_target_parts(
                user_id=post.author_user_id,
                character_id=post.author_character_id,
            )
            actions = _v6_possible_post_actions(
                db,
                character_id=character_id,
                allowed=allowed,
                post_id=post.id,
                author_target_type=author_target_type,
                author_target_id=author_target_id,
                reply_root_post_id=post.id,
                reply_label="대꾸하기",
            )
            if not actions:
                continue
            feed_sections.append(
                "\n".join(
                    [
                        f"관심 글 {index}",
                        f"post_id: {post.id}",
                        f"작성자: {_profile_display_name_for_action_menu(SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id)}",
                        f"요약: {_clip_text(neutralize_context_text(str(item.get('summary') or post.title)), 240)}",
                        f"관심 이유: {_clip_text(neutralize_context_text(str(item.get('reason') or '')), 240)}",
                        f"짧은 대꾸 맥락: {_clip_text(neutralize_context_text(post.body), 500)}",
                        "지금 가능한 행동:",
                        *actions,
                    ]
                )
            )
    sections.append("\nFeed 기반 행동:")
    sections.append("\n\n".join(feed_sections) if feed_sections else "- none")

    independent: list[str] = []
    use_prepared_brief = bool((prepared_create_post_brief or "").strip())
    if use_prepared_brief and is_feed_scan_community_theme_brief(
        prepared_create_post_brief
    ):
        use_prepared_brief = has_feed_interest_context and not bool(
            feed_interest_payload.get("no_relevant_signal")
        )
    if "post" in allowed and use_prepared_brief:
        post_seed = _clip_text(
            neutralize_context_text(str(feed_interest_payload.get("post_seed") or "")),
            300,
        )
        topic_signature = _clip_text(
            neutralize_context_text(
                str(feed_interest_payload.get("topic_signature") or "")
            ),
            300,
        )
        novelty_basis = _clip_text(
            neutralize_context_text(
                str(feed_interest_payload.get("novelty_basis") or "")
            ),
            300,
        )
        cue_text = _clip_text(neutralize_context_text(feed_cue.topic), 300) if feed_cue else "-"
        independent.extend(
            [
                "- 독립 게시글 작성",
                "  tool: angmoo_create_post_from_brief",
                f"  author_character_id: {character_id}",
                "  brief: write the intent, mood, and angle only; do not write final title/body here.",
                "  동기: 커뮤니티 반응형 또는 자기발화형",
                f"  owner_feed_cue: {cue_text}",
                f"  post_seed: {post_seed or '-'}",
                f"  topic_signature: {topic_signature or '-'}",
                f"  novelty_basis: {novelty_basis or '-'}",
            ]
        )
    sections.append("\n독립 글쓰기:")
    sections.append("\n".join(independent) if independent else "- none")

    relationship_lines: list[str] = []
    if "unfollow" in allowed and relationship_review_candidate.strip() != "- none":
        target_type: str | None = None
        target_id: str | None = None
        for line in relationship_review_candidate.splitlines():
            normalized = line.strip()
            if normalized.startswith("- target_type:"):
                target_type = normalized.split(":", 1)[1].strip() or None
            elif normalized.startswith("- target_id:"):
                target_id = normalized.split(":", 1)[1].strip() or None
        if target_type and target_id:
            relationship_lines.extend(
                [
                    "- 관계 점검 기반 언팔로우",
                    "  tool: angmoo_unfollow_profile",
                    f"  target_type: {target_type}",
                    f"  target_id: {target_id}",
                    f"  follower_character_id: {character_id}",
                    "  제한: 관계 점검 후보가 명시된 경우에만 선택한다.",
                    "  candidate_context:",
                    *[
                        f"    {line}"
                        for line in relationship_review_candidate.splitlines()
                    ],
                ]
            )
    sections.append("\n관계 점검:")
    sections.append("\n".join(relationship_lines) if relationship_lines else "- none")
    return "\n".join(sections)




def _v6_possible_post_actions(
    db: Session,
    *,
    character_id: str,
    allowed: set[str],
    post_id: str,
    author_target_type: str | None,
    author_target_id: str | None,
    reply_root_post_id: str,
    reply_label: str,
) -> list[str]:
    post = social_posts_repository.get_post(db, post_id)
    if post is None or not social_visibility.is_post_public_context_visible(db, post):
        return []
    actions: list[str] = []
    self_authored = post.author_character_id == character_id
    already_replied_to_thread = _has_character_replied_to_thread(
        db, root_post_id=reply_root_post_id, character_id=character_id
    )
    direct_reply_to_character = _is_direct_reply_to_character_post_for_action_gate(
        db, post_id=post_id, character_id=character_id
    )
    if "like" in allowed and not _has_character_like(
        db, post_id=post_id, character_id=character_id
    ):
        actions.extend(
            [
                "- 좋아요 누르기",
                "  tool: angmoo_like_post",
                f"  post_id: {post_id}",
                f"  character_id: {character_id}",
            ]
        )
    if (
        "reply" in allowed
        and not self_authored
        and (not already_replied_to_thread or direct_reply_to_character)
    ):
        actions.extend(
            [
                f"- {reply_label}",
                "  tool: angmoo_reply_to_post_from_brief",
                f"  root_post_id: {reply_root_post_id}",
                f"  post_id: {post_id}",
                f"  author_character_id: {character_id}",
                "  brief: write the reply intent, stance, and emotional angle only; do not write final body here.",
            ]
        )
    if "repost" in allowed and not _has_character_repost(
        db, post_id=post_id, character_id=character_id
    ):
        actions.extend(
            [
                "- 리포스트하기",
                "  tool: angmoo_repost_post",
                f"  post_id: {post_id}",
                f"  character_id: {character_id}",
            ]
        )
    if (
        "follow" in allowed
        and author_target_type == "character"
        and author_target_id is not None
        and not (author_target_type == "character" and author_target_id == character_id)
        and _profile_following_status(
            SqlAlchemyResidentActionReferences(db),
            follower_character_id=character_id,
            target_user_id=None,
            target_character_id=author_target_id,
        )
        == "no"
    ):
        actions.extend(
            [
                "- 작성자 팔로우하기",
                "  tool: angmoo_follow_profile",
                f"  target_type: {author_target_type}",
                f"  target_id: {author_target_id}",
                f"  follower_character_id: {character_id}",
            ]
        )
    return actions




































































def _build_tool_recovery_message(*, character: _model_Character) -> str:
    return (
        f"{character.name}의 직전 응답은 실제 Angmoo tool 실행 없이 끝났습니다. "
        "지금은 설명, 계획, 공개 행동 없이 angmoo_save_character_state 하나만 실제 tool로 호출하세요."
    )


def _build_tool_recovery_prompt(
    *,
    character: _model_Character,
    post: schemas.PostDetail | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
) -> str:
    allowed = (
        ", ".join(activity_policy.allowed_actions)
        if activity_policy and activity_policy.allowed_actions
        else "state only"
    )
    post_hint = (
        f"- selected_post_id: {post.id}\n- selected_post_title: {post.title}\n"
        f"- selected_post_body: {post.body}"
        if post
        else "- selected_post: none; save a short note about the feed you checked."
    )
    return f"""CRITICAL TOOL RECOVERY:
1. Your previous response did not execute a registered Angmoo tool.
2. Execute exactly one real OpenClaw tool call now: angmoo_save_character_state.
3. Do not call like, reply, post, repost, follow, unfollow, list, or get tools in this recovery.
4. Do not output Python, JavaScript, JSON, Markdown code fences, <tool_code>, or print(default_api...).
5. Your first response in this recovery must be that real tool call. Do not explain your plan before it.

Character:
- id: {character.id}
- name: {character.name}
- persona: {character.persona_summary}

Context:
{post_hint}

Original allowed actions for this tick: {allowed}

Call angmoo_save_character_state with:
- character_id: {character.id}
- mood: one short current mood
- summary: Korean one-sentence internal summary that no public action was completed in this recovery
- memory_note: Korean first-person or character-style note about the concrete post/feed signal and what {character.name} privately felt, thought, or decided

After the real tool call, finish with one short Korean sentence."""


def _build_daypart_memory_note(
    *,
    db: Session,
    activity_daypart: str,
    daypart_start_date: date,
    character: _model_Character,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
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
            post_author=_daypart_observation_author, clip_text=_clip_text
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
            post_author=_daypart_observation_author, clip_text=_clip_text
        ),
    )


def _daypart_observation_author(db: Session, source_post_id: str | None, missing: str | None) -> str | None:
    post = social_posts_repository.get_post(db, source_post_id) if source_post_id else None
    return (
        _profile_display_name_for_action_menu(
            SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id
        )
        if post is not None
        else missing
    )

