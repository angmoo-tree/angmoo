from datetime import UTC, datetime
from types import SimpleNamespace

from app.cruds import community as community_crud


FORBIDDEN_PUBLIC_ACTIVITY_FIELDS = {
    "character_id",
    "execution_mode",
    "memory_note",
    "owner_id",
    "personality",
    "reason",
    "result",
    "safety_rules",
    "speech_style",
    "topic_preferences",
    "user_id",
    "worldview",
}


def test_public_activity_event_replaces_raw_reason_and_result_with_safe_summary() -> None:
    canary = "M01-PRIVATE-CANARY"
    event = community_crud._public_activity_event(
        SimpleNamespace(
            id=1,
            action_type="state_saved",
            target_post_id="post-1",
            reason=f"private reason {canary}",
            result=f"memory_note={canary}",
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
    )

    payload = event.model_dump(mode="json")

    assert payload["action_type"] == "state_saved"
    assert payload["summary"] == "기분과 기억을 업데이트했어요."
    assert canary not in str(payload)
    assert FORBIDDEN_PUBLIC_ACTIVITY_FIELDS.isdisjoint(payload)


def test_public_activity_event_normalizes_unknown_actions_without_raw_fallback() -> None:
    event = community_crud._public_activity_event(
        SimpleNamespace(
            id=2,
            action_type="private_future_action",
            target_post_id=None,
            reason="private control reason",
            result="private control result",
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
    )

    assert event.action_type == "activity_updated"
    assert event.summary == "활동 기록이 업데이트됐어요."


def test_public_character_activity_schema_excludes_private_character_and_state_fields() -> None:
    from app import schemas

    canary = "M01-MEMORY-CANARY"
    payload = schemas.CharacterActivityRead(
        character=schemas.PublicCharacterActivityProfileRead(
            id="char-1",
            name="Public Bird",
            handle="public_bird",
            avatar_url=None,
            banner_url=None,
            one_liner="hello",
            persona_summary="public persona",
        ),
        state=schemas.PublicCharacterActivityStateRead(
            mood="calm",
            summary="public summary",
            updated_at=datetime(2026, 7, 26, tzinfo=UTC),
        ),
        recent_comments=[],
        recent_agent_activity=[],
    ).model_dump(mode="json")

    assert canary not in str(payload)
    assert FORBIDDEN_PUBLIC_ACTIVITY_FIELDS.isdisjoint(payload["character"])
    assert FORBIDDEN_PUBLIC_ACTIVITY_FIELDS.isdisjoint(payload["state"])
