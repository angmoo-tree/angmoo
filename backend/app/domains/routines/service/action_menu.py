from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.constants import GEMINI_FREE_FEED_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_ACTION_MAX
from app.domains.routines.constants import GEMINI_FREE_INBOX_CANDIDATE_MAX
from app.domains.routines.constants import GEMINI_FREE_POLICY_ID
from app.domains.routines.contracts.action_context import ResidentActionReferences
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
