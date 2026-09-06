from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.constants import GEMINI_FREE_FEED_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_POLICY_ID
from app.domains.routines.contracts.action_context import ResidentActionReferences
from app.domains.routines.service.action_admission import _profile_following_status
from app.domains.routines.service.action_admission import _v6_allowed_tool_calls
from app.domains.routines.service.action_admission import _v6_unavailable_post_actions
from app.domains.routines.service.action_briefs import PREPARED_CREATE_POST_BRIEF_SENTINEL
from app.domains.routines.service.action_briefs import is_feed_scan_community_theme_brief
from app.domains.routines.service.action_candidates import _profile_display_name_for_action_menu
from app.domains.routines.service.action_candidates import _profile_target_parts
from app.domains.routines.utils.context_text import _clip_text
from typing import Any


def _format_v6_action_menu_table(
    references: ResidentActionReferences,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    relationship_review_candidate: str = "- none",
    feed_cue: models.AgentFeedCue | None = None,
    prepared_create_post_brief: str | None = None,
) -> str:
    allowed = set(allowed_actions)
    sections: list[str] = [
        "Common rules:",
        "- Use only tool + exact params pairs listed under allowed tool calls.",
        "- tools_allow is run-wide; target-specific availability is this backend action menu.",
        "- Do not infer a missing action only because the tool exists.",
        "- Execute selected tool calls sequentially.",
        f"- effective_tier: {GEMINI_FREE_POLICY_ID}",
        f"- inbox public target max: {GEMINI_FREE_INBOX_CANDIDATE_MAX} thread",
        f"- feed public target max: {GEMINI_FREE_FEED_CANDIDATE_MAX} post",
        f"- inbox selected target action max: {GEMINI_FREE_INBOX_ACTION_MAX}",
        f"- feed selected target action max: {GEMINI_FREE_FEED_ACTION_MAX}",
    ]

    inbox_sections: list[str] = []
    inbox_allowed = allowed - {"post", "repost", "unfollow", "observe"}
    for index, item in enumerate(
        inbox_candidates[:GEMINI_FREE_INBOX_CANDIDATE_MAX], start=1
    ):
        post_id = str(item["source_post_id"])
        root_post_id = str(item["root_post_id"])
        tool_calls = _v6_allowed_tool_calls(
            references,
            character_id=character_id,
            allowed=inbox_allowed,
            post_id=post_id,
            author_target_type=item.get("actor_target_type"),
            author_target_id=item.get("actor_target_id"),
            reply_root_post_id=root_post_id,
            reply_label="reply",
        )
        if not tool_calls:
            continue
        unavailable = _v6_unavailable_post_actions(
            references,
            character_id=character_id,
            allowed=inbox_allowed,
            post_id=post_id,
            author_target_type=item.get("actor_target_type"),
            author_target_id=item.get("actor_target_id"),
            reply_root_post_id=root_post_id,
        )
        inbox_sections.append(
            "\n".join(
                [
                    f"Inbox candidate {index}",
                    f"notification_id: {item['notification_id']}",
                    f"root_post_id: {root_post_id}",
                    f"source_post_id: {post_id}",
                    f"actor: {item['actor_name']} ({item['actor_ref']})",
                    f"reply_summary: {item['source_body']}",
                    f"candidate_reason: {item.get('candidate_reason') or '-'}",
                    f"reply_context: {item.get('reply_context') or '-'}",
                    "allowed tool calls:",
                    *tool_calls,
                    "not available:",
                    *(unavailable or ["- none"]),
                ]
            )
        )
    sections.append("\nInbox actions:")
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
            post = references.get_post(post_id)
            if post is None or not references.is_post_public_context_visible(post):
                continue
            has_feed_interest_context = True
            author_target_type, author_target_id = _profile_target_parts(
                user_id=post.author_user_id,
                character_id=post.author_character_id,
            )
            tool_calls = _v6_allowed_tool_calls(
                references,
                character_id=character_id,
                allowed=allowed,
                post_id=post.id,
                author_target_type=author_target_type,
                author_target_id=author_target_id,
                reply_root_post_id=post.id,
                reply_label="reply",
            )
            if not tool_calls:
                continue
            unavailable = _v6_unavailable_post_actions(
                references,
                character_id=character_id,
                allowed=allowed,
                post_id=post.id,
                author_target_type=author_target_type,
                author_target_id=author_target_id,
                reply_root_post_id=post.id,
            )
            feed_sections.append(
                "\n".join(
                    [
                        f"Feed candidate {index}",
                        f"post_id: {post.id}",
                        f"author: {_profile_display_name_for_action_menu(references, user_id=post.author_user_id, character_id=post.author_character_id)}",
                        f"summary: {_clip_text(neutralize_context_text(str(item.get('summary') or post.title)), 240)}",
                        f"interest_reason: {_clip_text(neutralize_context_text(str(item.get('reason') or '')), 240)}",
                        f"short_reply_context: {_clip_text(neutralize_context_text(post.body), 500)}",
                        "allowed tool calls:",
                        *tool_calls,
                        "not available:",
                        *(unavailable or ["- none"]),
                    ]
                )
            )
    sections.append("\nFeed actions:")
    sections.append("\n\n".join(feed_sections) if feed_sections else "- none")

    writing_lines: list[str] = []
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
        cue_text = (
            _clip_text(neutralize_context_text(feed_cue.topic), 300)
            if feed_cue
            else "-"
        )
        writing_lines.extend(
            [
                "Writing candidate 1",
                "context:",
                "  motivation: community-reactive or self-expression",
                f"  owner_feed_cue: {cue_text}",
                f"  post_seed: {post_seed or '-'}",
                f"  topic_signature: {topic_signature or '-'}",
                f"  novelty_basis: {novelty_basis or '-'}",
                *(
                    [
                        "  prepared_create_post_brief:",
                        *[
                            f"    {line}"
                            for line in prepared_create_post_brief.splitlines()
                        ],
                    ]
                    if prepared_create_post_brief
                    else []
                ),
                "allowed tool calls:",
                "- tool: angmoo_create_post_from_brief",
                f"  author_character_id: {character_id}",
                f"  brief: {PREPARED_CREATE_POST_BRIEF_SENTINEL}",
                "not available:",
                "- none",
            ]
        )
    sections.append("\nWriting actions:")
    sections.append("\n".join(writing_lines) if writing_lines else "- none")

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
                    "Relationship candidate 1",
                    "allowed tool calls:",
                    "- tool: angmoo_unfollow_profile",
                    f"  target_type: {target_type}",
                    f"  target_id: {target_id}",
                    f"  follower_character_id: {character_id}",
                    "not available:",
                    "- none",
                    "candidate_context:",
                    "  limit: only choose when the relationship review target is explicit.",
                    *[
                        f"  {line}"
                        for line in relationship_review_candidate.splitlines()
                    ],
                ]
            )
    sections.append("\nRelationship actions:")
    sections.append("\n".join(relationship_lines) if relationship_lines else "- none")
    return "\n".join(sections)


def _format_v6_action_menu(
    references: ResidentActionReferences,
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
            references,
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
            post = references.get_post(post_id)
            if post is None or not references.is_post_public_context_visible(post):
                continue
            has_feed_interest_context = True
            author_target_type, author_target_id = _profile_target_parts(
                user_id=post.author_user_id,
                character_id=post.author_character_id,
            )
            actions = _v6_possible_post_actions(
                references,
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
                        f"작성자: {_profile_display_name_for_action_menu(references, user_id=post.author_user_id, character_id=post.author_character_id)}",
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
    references: ResidentActionReferences,
    *,
    character_id: str,
    allowed: set[str],
    post_id: str,
    author_target_type: str | None,
    author_target_id: str | None,
    reply_root_post_id: str,
    reply_label: str,
) -> list[str]:
    post = references.get_post(post_id)
    if post is None or not references.is_post_public_context_visible(post):
        return []
    actions: list[str] = []
    self_authored = post.author_character_id == character_id
    already_replied_to_thread = references.has_character_replied_to_thread(
        root_post_id=reply_root_post_id, character_id=character_id
    )
    direct_reply_to_character = references.is_direct_reply_to_character_post(
        post_id=post_id, character_id=character_id
    )
    if "like" in allowed and not references.has_character_like(
        post_id=post_id, character_id=character_id
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
    if "repost" in allowed and not references.has_character_repost(
        post_id=post_id, character_id=character_id
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
            references,
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
