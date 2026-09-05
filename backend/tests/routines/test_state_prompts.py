from types import SimpleNamespace

from app.domains.routines.service import state_prompts as agent_runs


def test_state_lane_prompt_has_input_voice_boundary():
    prompt = agent_runs._build_v6_state_lane_prompt(
        character=SimpleNamespace(
            id="char-1",
            name="state tester",
            handle="state_tester",
            persona_summary="quiet observer",
            speech_style="calm",
        ),
        state=None,
        activity_policy=None,
        public_action_ledger="- none",
        tick_activity="- none",
        observation_context="- none",
    )

    assert "입력 말투 경계 규칙" in prompt
    assert "Current tick successful public action ledger, Previous saved state" in prompt
    assert "mood, summary, memory_note를 저장할 때는 위 입력에 남아 있던 웃음소리" in prompt
    assert "새 state의 말투는 현재 Character의 persona와 speech_style에 명시된 말투만 기준" in prompt


def test_memory_note_refine_prompt_has_input_voice_boundary():
    prompt = agent_runs._build_memory_note_refine_prompt(
        character=SimpleNamespace(
            id="char-1",
            name="refine tester",
            handle="refine_tester",
            persona_summary="quiet observer",
            speech_style="calm",
        ),
        state=None,
        activity_policy=None,
        tick_activity="- none",
    )

    assert "입력 말투 경계 규칙" in prompt
    assert "Actual activity from this tick, First-pass saved state에 적힌 말투" in prompt
    assert "mood, summary, memory_note를 다듬을 때는 위 입력에 남아 있던 웃음소리" in prompt
    assert "다듬은 state의 말투는 현재 Character의 persona와 speech_style에 명시된 말투만 기준" in prompt


def test_v6_state_recovery_prompt_is_tool_only_and_compact() -> None:
    character = SimpleNamespace(
        id="char-test",
        name="테스트",
        handle="test",
        persona_summary="quiet observer",
        speech_style="short Korean notes",
    )
    activity_policy = SimpleNamespace(tendency_summary="prefers compact observations")

    prompt = agent_runs._build_v6_state_recovery_prompt(
        character=character,
        state=None,
        activity_policy=activity_policy,
        public_action_ledger="- observed only",
        tick_activity="- feed_viewed; feed_interests_noted",
        observation_context="- semantic_event: someone discussed resting",
    )

    assert "angmoo_save_character_state" in prompt
    assert "Do not call public action, feed, inbox, writing, read, or scan tools." in prompt
    assert "Public action ledger from this tick" in prompt
    assert "Compact observation context from this tick" in prompt
    assert "raw feed" not in prompt.lower()
    assert "thread body" not in prompt.lower()
