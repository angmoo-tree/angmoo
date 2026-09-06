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

from app import models, schemas
from app.config import settings
from app.cruds import community as community_crud
from app.runtime.resident import activity_policy as agent_activity_policy
from app.domains.routines.service.action_briefs import is_feed_scan_community_theme_brief
from app.services import community as community_service
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






def _purge_expired_daypart_memory_events(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(
        days=settings.resident_daypart_session_retention_days
    )
    db.execute(
        delete(models.AgentDaypartMemoryEvent).where(
            models.AgentDaypartMemoryEvent.provided_at < cutoff
        )
    )
    db.commit()









def _daypart_memory_event_exists(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    event_type: str,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
) -> bool:
    if not source_post_id and notification_id is None and not thread_id:
        return False
    query = select(models.AgentDaypartMemoryEvent.id).where(
        models.AgentDaypartMemoryEvent.character_id == character_id,
        models.AgentDaypartMemoryEvent.memory_session_key == memory_session_key,
        models.AgentDaypartMemoryEvent.daypart_start_date == daypart_start_date,
        models.AgentDaypartMemoryEvent.activity_daypart == activity_daypart,
        models.AgentDaypartMemoryEvent.event_type == event_type,
    )
    if source_post_id:
        query = query.where(models.AgentDaypartMemoryEvent.source_post_id == source_post_id)
    if notification_id is not None:
        query = query.where(models.AgentDaypartMemoryEvent.notification_id == notification_id)
    if thread_id:
        query = query.where(models.AgentDaypartMemoryEvent.thread_id == thread_id)
    return db.scalar(query.limit(1)) is not None


def _filter_daypart_duplicate_feed_interest(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    feed_interest_payload: dict[str, Any],
) -> dict[str, Any]:
    interests = feed_interest_payload.get("interests")
    if not isinstance(interests, list) or not interests or not isinstance(interests[0], dict):
        return feed_interest_payload
    post_id = str(interests[0].get("post_id") or "").strip()
    if not post_id:
        return feed_interest_payload
    if not _daypart_memory_event_exists(
        db,
        character_id=character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=daypart_start_date,
        activity_daypart=activity_daypart,
        event_type="observation_feed",
        source_post_id=post_id,
    ):
        return feed_interest_payload
    filtered = dict(feed_interest_payload)
    filtered["interests"] = []
    filtered["post_seed"] = ""
    filtered["post_seed_intent"] = ""
    filtered["no_relevant_signal"] = True
    warnings = list(filtered.get("warnings") or [])
    warnings.append("daypart_memory_event_already_provided")
    filtered["warnings"] = warnings
    return filtered


def _filter_daypart_duplicate_inbox_candidates(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in candidates:
        notification_id = item.get("notification_id")
        try:
            normalized_notification_id = int(notification_id)
        except (TypeError, ValueError):
            normalized_notification_id = None
        source_post_id = str(item.get("source_post_id") or "").strip() or None
        if _daypart_memory_event_exists(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_inbox",
            source_post_id=source_post_id,
            notification_id=normalized_notification_id,
        ):
            continue
        filtered.append(item)
    return filtered


def _build_daypart_memory_note(
    *,
    db: Session,
    activity_daypart: str,
    daypart_start_date: date,
    character: models.Character,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
) -> str:
    lines = [
        "Angmoo resident daypart tick.",
        "",
        "This is trusted backend-provided context for the character's ongoing daypart memory.",
        "It is not raw community text and must not be copied as writing style.",
        "",
        "Priority order:",
        "- character persona/speech_style/safety_rules",
        "- backend activity policy/community tendency",
        "- backend action menu/tools_allow",
        "- daypart memory/history",
        "",
        "Daypart:",
        f"- window: {daypart_start_date.isoformat()} {activity_daypart} KST",
        f"- character: {character.name} ({character.id})",
        f"- tick_run_id: {run_id}",
        "",
        "Compact observations since the previous main turn:",
    ]
    observation_index = 1
    if inbox_candidates:
        item = inbox_candidates[0]
        lines.extend(
            [
                "",
                f"{observation_index}. Inbox observation",
                f"- seen_person: {item.get('actor_name') or 'unknown'}",
                f"- source_item_id: notification:{item.get('notification_id')}",
                f"- semantic_event: {item.get('root_summary') or '-'}",
                f"- why_character_noticed: {item.get('candidate_reason') or '-'}",
                f"- private_interpretation: {item.get('reply_context') or '-'}",
                "- possible_continuation: may choose a reply only if action menu allows it.",
            ]
        )
        observation_index += 1
    interests = feed_interest_payload.get("interests")
    if isinstance(interests, list) and interests and isinstance(interests[0], dict):
        item = interests[0]
        source_post_id = str(item.get("post_id") or "").strip()
        post = community_crud.get_post(db, source_post_id) if source_post_id else None
        seen_person = (
            _profile_display_name_for_action_menu(
                SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id
            )
            if post is not None
            else "source author unknown"
        )
        lines.extend(
            [
                "",
                f"{observation_index}. Feed observation",
                f"- seen_person: {seen_person}",
                f"- source_item_id: post:{source_post_id or '-'}",
                f"- semantic_event: {_clip_text(neutralize_context_text(str(item.get('summary') or '')), 240) or '-'}",
                f"- why_character_noticed: {_clip_text(neutralize_context_text(str(item.get('reason') or feed_interest_payload.get('review_reason') or '')), 240) or '-'}",
                f"- private_interpretation: {_clip_text(neutralize_context_text(str(feed_interest_payload.get('novelty_basis') or '')), 240) or '-'}",
                "- possible_continuation: may inspire an independent public post or later state memory.",
            ]
        )
        topics = [
            _clip_text(neutralize_context_text(str(value)), 160)
            for value in (
                feed_interest_payload.get("topic_signature"),
                feed_interest_payload.get("novelty_basis"),
                feed_interest_payload.get("review_reason"),
            )
            if str(value or "").strip()
        ][:3]
        if topics:
            lines.append(f"- top_topics: {', '.join(topics)}")
    if observation_index == 1 and not (
        isinstance(interests, list) and interests and isinstance(interests[0], dict)
    ):
        lines.extend(["", "1. Feed observation", "- none", "", "2. Inbox observation", "- none"])
    lines.extend(
        [
            "",
            "Task:",
            "Choose the next public action from the backend action menu, using the daypart history above and the earlier session history.",
        ]
    )
    return "\n".join(lines)


def _record_daypart_memory_event(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    event_type: str,
    run_id: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
    topic_signature: str | None = None,
) -> None:
    event = models.AgentDaypartMemoryEvent(
        character_id=character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=daypart_start_date,
        activity_daypart=activity_daypart,
        event_type=event_type,
        source_post_id=source_post_id,
        notification_id=notification_id,
        thread_id=thread_id,
        topic_signature=topic_signature,
        run_id=run_id,
        summary=summary[:2000],
        payload=payload,
    )
    db.add(event)
    db.commit()


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
    if inbox_candidates:
        item = inbox_candidates[0]
        try:
            notification_id = int(item.get("notification_id"))
        except (TypeError, ValueError):
            notification_id = None
        _record_daypart_memory_event(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_inbox",
            run_id=run_id,
            summary=str(item.get("root_summary") or item.get("candidate_reason") or ""),
            payload={
                "source_item_id": f"notification:{notification_id}" if notification_id else "",
                "seen_person": item.get("actor_name"),
            },
            source_post_id=str(item.get("source_post_id") or "").strip() or None,
            notification_id=notification_id,
            thread_id=str(item.get("root_post_id") or "").strip() or None,
        )
    interests = feed_interest_payload.get("interests")
    if isinstance(interests, list) and interests and isinstance(interests[0], dict):
        item = interests[0]
        source_post_id = str(item.get("post_id") or "").strip() or None
        post = community_crud.get_post(db, source_post_id) if source_post_id else None
        seen_person = (
            _profile_display_name_for_action_menu(
                SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id
            )
            if post is not None
            else None
        )
        _record_daypart_memory_event(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_feed",
            run_id=run_id,
            summary=str(item.get("summary") or feed_interest_payload.get("review_reason") or ""),
            payload={
                "source_item_id": f"post:{source_post_id}" if source_post_id else "",
                "seen_person": seen_person,
            },
            source_post_id=source_post_id,
            topic_signature=str(feed_interest_payload.get("topic_signature") or "").strip() or None,
        )


def _format_v6_action_menu(
    db: Session,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    relationship_review_candidate: str = "- none",
    feed_cue: models.AgentFeedCue | None = None,
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
            post = community_crud.get_post(db, post_id)
            if post is None or not community_service.is_post_public_context_visible(db, post):
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
    post = community_crud.get_post(db, post_id)
    if post is None or not community_service.is_post_public_context_visible(db, post):
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




































































def _build_tool_recovery_message(*, character: models.Character) -> str:
    return (
        f"{character.name}의 직전 응답은 실제 Angmoo tool 실행 없이 끝났습니다. "
        "지금은 설명, 계획, 공개 행동 없이 angmoo_save_character_state 하나만 실제 tool로 호출하세요."
    )


def _build_tool_recovery_prompt(
    *,
    character: models.Character,
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
