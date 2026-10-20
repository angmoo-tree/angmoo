import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.contracts.routine_output import COMPACT_EFFECT_WIRE, LEGACY_WIRE, saved_policy
from app.providers.contracts import ProviderRequest
from app.providers.gemini import _generate_content_sync, prepare_generate_request
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft
from routine_posts.google_wire_fixture import routine_request, valid_output


@pytest.mark.parametrize("count", [0, 1, 3, 5, 7, 8])
def test_actual_full_envelope_only_changes_effect_bound(count, monkeypatch):
    with routine_request(count) as new, routine_request(count, profile=LEGACY_WIRE) as old:
        original = deepcopy(old["schema"])
        expected = deepcopy(original)
        effects = expected["properties"]["decision"]["properties"]["source_event_effects"]
        assert effects.pop("maxItems") == count
        assert new["schema"] == expected
        assert old["schema"] == original
        assert "situations" in expected["properties"] and "draft" in expected["properties"]
        output = valid_output(count)
        result = new["validator"](output)
        assert len(result["plan"]["source_event_effects"]) == count
        assert len(result["_situations"]) == 1
        parse_routine_draft(output["draft"], image_enabled=True)
        seen = []
        class Client:
            def __init__(self, **_kwargs):
                self.models = self
            def generate_content(self, **kwargs):
                seen.append(kwargs["config"].model_dump(by_alias=True, exclude_none=True))
                return SimpleNamespace(text=json.dumps(output), parsed=None,
                    candidates=[], usage_metadata=None)
        monkeypatch.setattr("app.providers.gemini.genai.Client", Client)
        request = ProviderRequest(api_key="synthetic", model="gemini-3.5-flash-lite",
            system_prompt=new["system"], user_prompt="Synthetic verification.",
            response_mime_type="application/json", response_schema=new["schema"],
            max_output_tokens=new["max_tokens"], thinking_level="medium", sdk_attempts=1,
            timeout_seconds=60)
        prepared = prepare_generate_request(request)
        assert prepared.config.response_json_schema == expected
        _generate_content_sync(request)
        assert seen[0]["responseJsonSchema"] == expected
        assert "responseSchema" not in seen[0]


@pytest.mark.parametrize("invalid", ["nine", "duplicate", "external", "unused", "range"])
def test_server_rejects_invalid_effects_without_truncation(invalid):
    with routine_request(8) as request:
        value = valid_output(8)
        effects = value["decision"]["source_event_effects"]
        if invalid == "nine":
            effects.append(deepcopy(effects[0]))
        elif invalid == "duplicate":
            effects[1] = deepcopy(effects[0])
        elif invalid == "external":
            effects[0]["source_event_id"] = "unprovided-event"
            value["decision"]["used_source_event_ids"][0] = "unprovided-event"
        elif invalid == "unused":
            value["decision"]["used_source_event_ids"].pop()
        else:
            effects[0]["state_change"]["mood_intensity_delta"] = 21
        with pytest.raises(ValueError):
            request["validator"](value)


def test_old_admission_keeps_legacy_wire_and_frozen_profile():
    old = {"routine_policy": {"output_contract": "routine-output.enum-preserved.v1",
        "state_schema_version": 2, "thought_policy": "thought_v1"}}
    frozen = deepcopy(old)
    assert saved_policy(old).provider_schema_profile == LEGACY_WIRE
    assert old == frozen
    assert saved_policy(None).provider_schema_profile == LEGACY_WIRE
    new = deepcopy(old)
    new["routine_policy"]["provider_schema_profile"] = COMPACT_EFFECT_WIRE
    assert saved_policy(new).provider_schema_profile == COMPACT_EFFECT_WIRE
