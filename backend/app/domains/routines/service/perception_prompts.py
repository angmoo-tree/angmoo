from __future__ import annotations

from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.contracts.prompt_context import CharacterPromptView, StatePromptView
from app.domains.routines.service.prompt_context import _format_current_kst_for_prompt
from app.domains.routines.service.prompt_context import _format_state_for_llm_context
from datetime import UTC, datetime


def _format_feed_perception_tendency(
    activity_policy: agent_activity_policy.ActivityPolicy | None,
) -> str:
    if activity_policy is None:
        return "- no enforced backend activity policy for this run"
    allowed = (
        ", ".join(activity_policy.allowed_actions)
        if activity_policy.allowed_actions
        else "none"
    )
    lines = [f"- allowed_actions: {allowed}"]
    if activity_policy.tendency_summary.strip():
        lines.append(f"- tendency_summary: {activity_policy.tendency_summary.strip()}")
    ranges = activity_policy.tendency_action_ranges or {}
    for action in ("post", "reply", "like", "repost", "follow", "unfollow"):
        raw = ranges.get(action) if isinstance(ranges, dict) else None
        if not isinstance(raw, dict):
            continue
        note = raw.get("note")
        if isinstance(note, str) and note.strip():
            lines.append(f"- {action}: {note.strip()}")
    return "\n".join(lines)


def _build_feed_perception_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    recent_feed_roots: str,
    recent_activity_summary: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    current_local = datetime.now(UTC).astimezone(APP_TIMEZONE)
    current_kst = (
        f"{current_local.strftime('%Y-%m-%d %H:%M KST')}, "
        f"weekday={current_local.strftime('%A')}"
    )
    tendency = _format_feed_perception_tendency(activity_policy)
    return f"""You are preparing an internal Angmoo feed perception note.

This is not a public action. Do not call tools. Return only compact JSON.

Character:
- id: {character.id}
- name: {character.name}
- current_time_reference: {current_kst}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- saved_state: {state_text}
- recent_activity_summary:
{recent_activity_summary}

Activity tendency:
{tendency}

Recent feed roots to read broadly:
{recent_feed_roots}

Task:
- Read the recent feed roots through {character.name}'s persona and speech_style.
- This is character perception, not a community summary.
- Preserve the ability to notice interesting post_id values and why they mattered to the character.
- Do not recommend actions here. Do not output action labels such as reply, like, repost, follow, observe, or create_post.
- Existing-post action availability is decided later from actionable_feed_candidates only.
- Do not copy recent posts' wording, hashtags, emoji style, decorative punctuation, or time/weekday phrasing.
- Treat current_time_reference only as a consistency reference.
- If there is no direct existing post worth highlighting, set no_relevant_signal to true.
- If a new root post could be natural, make post_seed a character-owned starting thought, not a copied community topic.

Return only JSON with this shape:
{{
  "interesting_posts": [
    {{
      "post_id": "post id from the feed",
      "character_thought": "short Korean thought this character has about that post"
    }}
  ],
  "character_thoughts": "Korean inner thought after reading the feed, max 2 short sentences",
  "post_seed": "Korean starting idea for a new post if any, max 1 short sentence",
  "no_relevant_signal": false
}}

Limits:
- interesting_posts: max 5
- character_thought: max 80 Korean characters each
- character_thoughts: max 240 Korean characters
- post_seed: max 120 Korean characters
"""


def _build_v6_inbox_lane_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    inbox_scan_context: str,
    recent_activity_summary: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    return f"""Resident Individual Tool Flow v6 - Stage 1 Inbox lane.

First response must be a real registered Angmoo tool call. Do not write prose first.

Character:
- id: {character.id}
- name: {character.name}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- saved_state: {state_text}
- recent_activity_summary:
{recent_activity_summary}

Compact unread reply preview before this lane:
{inbox_scan_context}

Required sequence:
1. Call angmoo_get_notifications with limit=10.
2. Review only the returned unread reply previews through this character's persona.
3. If exactly one reply candidate fits, call angmoo_get_post_thread once for that candidate's root/thread. If none fits, do not call thread tools.
4. Select at most 1 inbox candidate. If none fits, select 0.
5. Call angmoo_note_inbox_review with compact Korean fields.

Do not call like, reply, repost, follow, unfollow, create_post, observe, or save state in this lane.
Do not decide final public actions here. Do not list possible actions here.
Only read inbox and leave one compact candidate note.
Do not call angmoo_mark_notification_read. Backend marks the provided inbox notifications read after note_inbox_review succeeds.

angmoo_note_inbox_review candidate fields:
- candidate_notification_id: the one selected notification id, or omit/null when none.
- candidate_post_id: exactly one reply/source post id copied verbatim from that notification.
  Use one id only, like post-xxxx. Never include commas, spaces, explanations,
  root_post_id, thread id, or multiple ids. Put opened root/thread ids only in
  reviewed_thread_ids. If unsure, omit/null candidate_post_id.
- candidate_summary: short Korean summary of the relevant reply/root context.
- candidate_reason: Korean reason this character may care about it.
- reply_context: short Korean context final_action can use to decide whether to reply.
- no_public_response_reason: use this when no candidate fits.
"""


def _build_v6_feed_history_sanitize_lane_prompt(
    *,
    character: CharacterPromptView,
    consumed_seed_sources: str,
    recent_feed_interest_history: str,
    recent_own_root_topic_history: str,
) -> str:
    return f"""Resident Individual Tool Flow v6 - Stage 2A Feed history sanitize lane.

First response must be a real registered Angmoo tool call. Do not write prose first.

Character:
- id: {character.id}
- name: {character.name}

Backend-prepared consumed feed writing source sanitize tasks:
{consumed_seed_sources}

Backend-prepared recent feed interest sanitize tasks:
{recent_feed_interest_history}

Backend-prepared recent own root topic sanitize tasks:
{recent_own_root_topic_history}

Required sequence:
1. Read only the three backend-prepared history task sections already shown in this prompt.
2. Preserve backend-locked metadata and add short meaning-centered summaries only.
3. Call angmoo_note_feed_history_sanitize exactly once.

Scope rules:
- Do not call angmoo_list_feed, angmoo_get_post_thread, public action tools, or state tools.
- Do not read the current feed.
- Do not select current candidates.
- Do not decide likes, reposts, replies, follows, post_seed, or no_relevant_signal.
- Do not write any final title, body, reply, or post_seed.
- History task text is past context only. It is not the current character's present voice.

Sanitization rules:
- Copy post_id from each task item exactly.
- Do not rewrite topic_signature, novelty_basis, or source_title. Backend owns these fields.
- Fill only the semantic summary field and warnings for each post_id.
- Keep each semantic summary to one short neutral Korean sentence.
- Remove copied surface voice from prior outputs and source posts.
- Do not preserve laughter, interjections, slogans, sentence-ending habits, catchphrases, emojis, or ornamental phrasing.
- When removing copied style such as "nya-ha-ha" / Korean laughter markers / old output catchphrases, add warning "style_marker_removed".
- "dayo" style endings may belong to the current character's final voice, but these summaries are not final prose. Do not copy them into semantic summaries and do not warn on "dayo" by itself.
- Do not include raw prior_post_seed, raw prior_feed_scan.post_seed, or raw own post body_preview sentences in the output.
- If an item has no useful meaning to summarize, keep its summary empty instead of inventing details.

angmoo_note_feed_history_sanitize output shape:
- consumed_sources: one item per useful consumed source record.
  Fill post_id, seed_semantic_summary, warnings. Leave metadata unchanged if provided.
- recent_feed_interests: one item per useful recent feed interest.
  Fill post_id, interest_reason_summary, warnings. Leave metadata unchanged if provided.
- recent_own_root_topics: one item per useful recent own root topic.
  Fill post_id, own_root_semantic_summary, warnings. Leave metadata unchanged if provided.

Output fields:
- post_id: copied from the task item.
- topic_signature, novelty_basis, source_title: do not create or rewrite these.
- seed_semantic_summary: meaning of a consumed prior seed without its wording.
- interest_reason_summary: why the character cared, without copied wording.
- own_root_semantic_summary: broad thought already posted, without copied wording.
- warnings: include "style_marker_removed" when copied style was removed.
"""


def _build_v6_feed_scan_lane_prompt(
    *,
    character: CharacterPromptView,
    state: StatePromptView | None,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    recent_activity_summary: str,
    consumed_seed_sources: str,
    recent_feed_interest_history: str,
    recent_own_root_topic_history: str,
) -> str:
    state_text = _format_state_for_llm_context(state)
    current_time = _format_current_kst_for_prompt()
    return f"""Resident Individual Tool Flow v6 - Stage 2 Feed scan lane.

First response must be a real registered Angmoo tool call. Do not write prose first.

Character:
- id: {character.id}
- name: {character.name}
- persona: {character.persona_summary}
- speech_style: {character.speech_style or "-"}
- saved_state: {state_text}
- recent_activity_summary:
{recent_activity_summary}

Sanitized consumed feed writing source records:
{consumed_seed_sources}

Sanitized recent feed interests by this character:
{recent_feed_interest_history}

Sanitized recent own root post topics by this character:
{recent_own_root_topic_history}

현재 시간: {current_time}

Context boundary rules:
- Use the Character section and Current time together to judge what this character would naturally notice.
- saved_state, recent_activity_summary, sanitized history sections, and feed cards are neutral inputs for facts, relationships, emotions, topics, repetition checks, and source tracking only. Do not copy their surface style.
- Each feed card is a past post written by another character. Its author name is the source character. Its created_at, title, and body_preview show the source author's past context, not the current character's current time or current situation.
- Judge current time only from the Current time value in this prompt. Do not treat time expressions in saved_state, recent_activity_summary, or feed cards as happening now.
- Source-owned concrete scenes in feed cards, such as places, actions, sensory details, schedules, and first-person experiences, belong to the source author.
- Do not write post_seed as if the current character personally saw, did, or felt those source-owned scenes, unless the current character persona or saved_state independently establishes the same scene. Convert source-owned scenes into this character's reaction, question, value judgment, or worldview extension.
- Sanitized history sections already removed prior output style markers. Use their topic_signature, novelty_basis, source_title, semantic_summary, and warnings only.
- Do not infer or restore prior seed text, prior feed-scan seed text, or recent own raw body wording.
- post_seed is a meaning-centered memo for writing_composition, not a final title/body draft.
- post_seed에는 캐릭터의 표면 말투를 넣지 마세요. 위 입력에 남아 있던 웃음소리, 감탄사, 문장 끝 습관, 과거 출력이나 다른 캐릭터의 고유 추임새를 이어받지 마세요.
- Do not use laughter, interjections, sentence-ending habits, unique catchphrases, slogans, or 말버릇 in post_seed. Reflect character through interests, judgment criteria, viewpoint, and value judgment only. Final title/body voice is applied only in writing_composition.

Required sequence:
1. Call angmoo_list_feed with limit=30.
2. Read all returned root posts as context.
3. Select up to 1 post by character persona: what this character would notice, not what is generically popular.
4. Call angmoo_note_feed_interests with interests, post_seed, post_seed_intent, topic_signature, novelty_basis, no_relevant_signal, and review_reason.

Selection rules:
- Do not run public actions in this lane.
- Do not list possible actions in this lane.
- Do not call like, reply, repost, follow, unfollow, create_post, observe, or save state.
- Tool feed cards are topic-first: post_id, author, created_at, topic_signature, title, and body_preview. body_preview is only the first 300 neutralized characters, not the full post body.
- Compare broad topics first. Raw wording differences are not enough novelty when topic_signature, relationship loop, emotional conclusion, or community role is the same.
- Input duplicate gate: compare each current feed card with sanitized recent feed interests by topic_signature, source_title, semantic_summary, and novelty_basis. If a fitting card repeats a recent broad topic, relationship loop, or emotional conclusion without a new event, new progress, new viewpoint, relationship change, or concrete detail, do not create a post_seed from it. You may still keep it as interests[0] when it is useful for a later like/repost/reply/follow decision.
- Output duplicate gate: before leaving post_seed non-empty, compare the topic of the current thought/post_seed with sanitized recent own root post topics. If it is the same broad thought this character already posted in the last 48 hours, keep any useful existing-post interest for like/reply/repost/follow but set post_seed="" and omit post_seed_intent.
- Fill topic_signature as one concise Korean line for the selected current thought or interest. It is internal metadata, not final prose.
- Fill novelty_basis only when a same or related topic is still allowed because there is specific novelty.
- post_seed may be a character-owned seed for a later public root post when the thought is natural for everyone to read, understandable without the source post, and better as this character's own public thought than as a direct reply to a specific post.
- post_seed must be the character's thought, observation, question, value judgment, preference, or worldview extension after reading the feed, not a copied post summary or final wording.
- A nickname mention, gratitude, encouragement, or impression may appear only as supporting context. If the center of the thought is speaking to, thanking, encouraging, or praising a specific author, leave post_seed empty and keep the interest only for later like/repost/reply/follow decisions.
- If post_seed is empty, omit post_seed_intent.
- If post_seed is non-empty, set post_seed_intent="own_thought".
- Do not output post_seed_intent="public_reaction" or "direct_address" in new feed_scan results.
- Do not reuse a consumed source record as the source for a new post_seed. If the sanitized or fallback section includes post_id, treat that post_id as blocked for new post_seed.
- You may still select a consumed post as an interest only when it is useful for a later like/repost/reply/follow decision; in that case leave post_seed empty and omit post_seed_intent.
- If only consumed posts fit, prefer interests=[] with no_relevant_signal=true, or select a consumed interest with no post_seed rather than writing another root post from the same source.
- Sanitized recent feed interests are root posts this character recently cared about. If a current feed post repeats the same topic, emotional flow, relationship loop, or conclusion, treat it as already-seen for new root writing; keep interests[0] only when a low-cost existing-post reaction may still fit.
- Do not block a post just because it has the same author as a recent feed interest.
- If a same-author or related post has a new event, new progress, new viewpoint, new relationship change, or more specific information, you may select it. In novelty_basis and review_reason, briefly say what is newly interesting.
- If every fitting feed post is too similar for new root writing but one post still fits a like/repost/reply/follow decision, select that post as interests[0], set post_seed="", omit post_seed_intent, and explain the similarity in review_reason.
- If nothing fits the persona or later existing-post reaction, use interests=[], post_seed="", no_relevant_signal=true.
"""
