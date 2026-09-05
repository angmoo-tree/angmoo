from types import SimpleNamespace

from app.domains.routines.service import perception_prompts as agent_runs


def test_feed_scan_prompt_uses_own_thought_only_for_post_seed():
    prompt = agent_runs._build_v6_feed_scan_lane_prompt(
        character=SimpleNamespace(
            id="char-1",
            name="seed tester",
            persona_summary="notices small warm signals",
            speech_style="quiet",
        ),
        state=None,
        activity_policy=None,
        recent_activity_summary="- none",
        consumed_seed_sources="- none",
        recent_feed_interest_history="- none",
        recent_own_root_topic_history="- none",
    )

    assert 'post_seed_intent="own_thought"' in prompt
    assert 'set post_seed_intent="public_reaction"' not in prompt
    assert "A nickname mention, gratitude, encouragement, or impression may appear only as supporting context" in prompt
    assert "speaking to, thanking, encouraging, or praising a specific author" in prompt
    assert 'Do not output post_seed_intent="public_reaction" or "direct_address"' in prompt
    assert "Source-owned concrete scenes in feed cards" in prompt
    assert "Do not write post_seed as if the current character personally saw, did, or felt" in prompt
    assert "Convert source-owned scenes into this character's reaction, question, value judgment, or worldview extension" in prompt
    assert "Context boundary rules" in prompt
    assert "neutral inputs for facts, relationships, emotions, topics, repetition checks, and source tracking only" in prompt
    assert "Do not copy their surface style" in prompt
    assert "created_at, title, and body_preview show the source author's past context" in prompt
    assert "Judge current time only from the Current time value" in prompt
    assert "post_seed is a meaning-centered memo for writing_composition, not a final title/body draft" in prompt
    assert "과거 출력이나 다른 캐릭터의 고유 추임새" in prompt
    assert "post_seed에는 캐릭터의 표면 말투를 넣지 마세요." in prompt
    assert "laughter, interjections, sentence-ending habits, unique catchphrases" in prompt
    assert "Reflect character through interests, judgment criteria, viewpoint, and value judgment only" in prompt
    assert "Final title/body voice is applied only in writing_composition" in prompt
    assert "Call angmoo_list_feed with limit=30" in prompt
    assert "Call angmoo_note_feed_interests with interests, post_seed, post_seed_intent, topic_signature, novelty_basis, no_relevant_signal, and review_reason" in prompt
    assert "Do not run public actions in this lane" in prompt
    assert "Input duplicate gate" in prompt
    assert "Output duplicate gate" in prompt


def test_feed_history_sanitize_prompt_is_scoped_to_history_only():
    prompt = agent_runs._build_v6_feed_history_sanitize_lane_prompt(
        character=SimpleNamespace(id="char-1", name="frog"),
        consumed_seed_sources=(
            "- post_id: post-old\n"
            "  prior_post_seed: nya-ha-ha copied catchphrase"
        ),
        recent_feed_interest_history=(
            "- post_id: post-interest\n"
            "  prior_feed_scan:\n"
            "    post_seed: copied old seed"
        ),
        recent_own_root_topic_history=(
            "- post_id: post-own\n"
            "  body_preview: copied old own post body"
        ),
    )

    assert "angmoo_note_feed_history_sanitize" in prompt
    assert "Do not call angmoo_list_feed" in prompt
    assert "Do not read the current feed" in prompt
    assert "Do not select current candidates" in prompt
    assert "Do not write any final title, body, reply, or post_seed" in prompt
    assert "Do not rewrite topic_signature, novelty_basis, or source_title" in prompt
    assert "Fill only the semantic summary field and warnings" in prompt
    assert "post_id" in prompt
    assert "style_marker_removed" in prompt
    assert "consumed_sources" in prompt
    assert "recent_feed_interests" in prompt
    assert "recent_own_root_topics" in prompt


def test_feed_scan_prompt_uses_sanitized_history_without_raw_seed_text():
    prompt = agent_runs._build_v6_feed_scan_lane_prompt(
        character=SimpleNamespace(
            id="char-1",
            name="seed tester",
            persona_summary="notices small warm signals",
            speech_style="quiet",
        ),
        state=None,
        activity_policy=None,
        recent_activity_summary="- none",
        consumed_seed_sources=(
            "- post_id: post-old\n"
            "  topic_signature: weekend lunch strategy\n"
            "  semantic_summary: the source topic was lunch planning, not a voice sample\n"
            "  warnings: style_marker_removed"
        ),
        recent_feed_interest_history=(
            "- topic_signature: frog lunch loop\n"
            "  source_title: lunch note\n"
            "  semantic_summary: cared about lunch planning\n"
            "  warnings: style_marker_removed"
        ),
        recent_own_root_topic_history=(
            "- topic_signature: already posted lunch thought\n"
            "  semantic_summary: already wrote about lunch strategy\n"
            "  warnings: -"
        ),
    )

    assert "Sanitized consumed feed writing source records" in prompt
    assert "Sanitized recent feed interests by this character" in prompt
    assert "Sanitized recent own root post topics by this character" in prompt
    assert "semantic_summary" in prompt
    assert "style_marker_removed" in prompt
    assert "prior_post_seed" not in prompt
    assert "prior_feed_scan" not in prompt
    assert "nya-ha-ha" not in prompt
    assert "copied old own post body" not in prompt
    assert "Input duplicate gate" in prompt
    assert "topic_signature, source_title, semantic_summary, and novelty_basis" in prompt


def test_feed_scan_prompt_suppresses_similar_recent_interests():
    prompt = agent_runs._build_v6_feed_scan_lane_prompt(
        character=SimpleNamespace(
            id="char-1",
            name="seed tester",
            persona_summary="notices small warm signals",
            speech_style="quiet",
        ),
        state=None,
        activity_policy=None,
        recent_activity_summary="- none",
        consumed_seed_sources="- none",
        recent_feed_interest_history=(
            "- source_title: old note\n"
            "  topic_signature: same loop\n"
            "  semantic_summary: same loop"
        ),
        recent_own_root_topic_history=(
            "- topic_signature: same loop\n"
            "  semantic_summary: same own thought"
        ),
    )

    assert "Sanitized recent feed interests by this character" in prompt
    assert "Sanitized recent own root post topics by this character" in prompt
    assert "Input duplicate gate" in prompt
    assert "Output duplicate gate" in prompt
    assert "topic_signature" in prompt
    assert "keep interests[0] only when a low-cost existing-post reaction may still fit" in prompt
    assert "Do not block a post just because it has the same author" in prompt
    assert "new event, new progress, new viewpoint" in prompt
    assert 'interests=[], post_seed="", no_relevant_signal=true' in prompt
