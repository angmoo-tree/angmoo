import pytest
from pydantic import ValidationError
from app.domains.media.generation_contracts import (
    MODEL_CATALOG, ApiImageOptions, NovelOptions, ImagePreparationError,
    compose_positive, initial_reference,
)


@pytest.mark.parametrize("style,appearance,expected", [
    ("", "", "walking in a park"), ("ink", "", "ink, walking in a park"),
    ("", "green hair", "green hair, walking in a park"),
    ("ink", "green hair", "ink, green hair, walking in a park"),
])
def test_optional_identity(style, appearance, expected):
    assert compose_positive(style=style, appearance=appearance, scene="walking in a park") == expected


def test_scene_required_and_no_provider_option_leak():
    with pytest.raises(ImagePreparationError):
        compose_positive(style="ink", appearance="hair", scene=" ")
    with pytest.raises(ValidationError):
        ApiImageOptions.model_validate({"steps": 28})


def test_reference_initialization_does_not_enable_generation():
    assert len(MODEL_CATALOG) == 7
    assert sum(initial_reference(p, m, mode="allow_anlas") for p, m, _ in MODEL_CATALOG.values()) == 6
    assert not initial_reference("novelai", "nai-diffusion-4-5-full", mode="opus_free")
    assert not initial_reference("comfyui", "custom")
    assert initial_reference("comfyui", "custom", reference_validated=True)


@pytest.mark.parametrize("values", [{"steps":29}, {"width":1088}, {"n":2}, {"scale":"5"}])
def test_free_request_bounds_and_strict_types(values):
    with pytest.raises(ValidationError):
        NovelOptions.model_validate(values)


@pytest.mark.parametrize("enabled,scene,body,error", [
    (False, None, "책상 위의 책을 읽었다.", None),
    (True, "reading a book at a blue desk", "책상 위의 책을 읽었다.", None),
    (True, "", "책상 위의 책을 읽었다.", None),
    (True, 123, "책상 위의 책을 읽었다.", "scene_invalid"),
    (True, {"provider": "unexpected"}, "책상 위의 책을 읽었다.", "scene_invalid"),
    (True, "x" * 1801, "책상 위의 책을 읽었다.", "scene_invalid"),
    (True, "reading a book at a blue desk", "", "post_invalid"),
], ids=["disabled", "scene", "empty-scene", "invalid-number", "invalid-object", "overlong-scene", "invalid-post"])
def test_final_combined_sns_call_emits_scene_without_extra_llm_or_losing_post(monkeypatch, enabled, scene, body, error):
    import asyncio
    from types import SimpleNamespace
    from app.runtime.autonomous_activity import provider as transport
    from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
    from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft

    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        if kwargs["context"].node == "CombinedTargetSelector":
            return kwargs["validator"]({})
        draft = {"replies": []}
        if kwargs["context"].node == "RoutineDecisionDraft":
            draft = {"title": "책을 읽은 하루", "body": body, "novelty_basis": "오늘의 독서", "thought": "읽기를 즐겼다."}
            if enabled:
                draft["image_prompt"] = scene
        return kwargs["validator"]({"decision": {"state_update": None}, "draft": draft})
    monkeypatch.setattr(transport, "generate_json", generate)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic-only")
    monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: SimpleNamespace(node=k["node"], lane=k["lane"]))
    provider = CombinedActivityProvider(SimpleNamespace(generation_thinking_level=None, on_rate_limit_wait=None),
        None, ledger=SimpleNamespace(reserve=lambda _: pytest.fail("normal output should not request recovery")))
    provider.image_enabled = enabled
    async def run():
        final = None
        for node in ("CombinedTargetSelector", "InboxActionPlanner", "FeedActionPlanner", "RoutineActionPlanner"):
            final = await provider.call(node=node, lane="synthetic_sns", system="Use supplied facts.", payload={},
                schema={"type": "object", "properties": {"decisions": {"type": "array", "items": {
                    "type": "object", "properties": {"target_id": {"type": "string", "enum": ["synthetic-post"]}}}}}},
                validator=lambda value: value, max_tokens=8192)
        return final
    final = asyncio.run(run())
    assert [call["context"].node for call in calls] == ["CombinedTargetSelector", "InboxDecisionDraft", "FeedDecisionDraft", "RoutineDecisionDraft"]
    assert len(calls) == 4 and all(call["sdk_attempts"] == 1 for call in calls)
    for call in calls[1:3]:
        assert "image_prompt" not in call["response_schema"]["properties"]["draft"]["properties"]
    schema = calls[-1]["response_schema"]["properties"]["draft"]
    assert ("image_prompt" in schema["properties"]) is enabled
    assert ("image_prompt" in schema["required"]) is enabled
    assert not {"model", "steps", "negative_prompt", "appearance", "style"}.intersection(schema["properties"])
    if error == "post_invalid":
        with pytest.raises(ValidationError):
            parse_routine_draft(final["provisional_draft"], image_enabled=enabled)
    else:
        draft = parse_routine_draft(final["provisional_draft"], image_enabled=enabled)
        assert draft["title"] == "책을 읽은 하루" and draft["body"] == body
        if enabled:
            assert draft["_image_error"] == error
            assert draft["_image_prompt"] == (scene if isinstance(scene, str) and error is None else "")
        else:
            assert "_image_prompt" not in draft and "_image_error" not in draft
