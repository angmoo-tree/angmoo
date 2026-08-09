from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import schemas
from app.providers.gemini import build_generate_content_config
from app.services import world_character_contracts as contracts
from app.services import world_character_provider


def _character(**overrides):
    values = {
        "id": "character-a",
        "name": " 마린  ",
        "one_liner": "마법약을 공부하는 학생",
        "personality": "차분하고 호기심이 많다.",
        "speech_style": "짧고 다정하게 말한다.",
        "worldview": "배움은 나눌수록 깊어진다.",
        "topic_preferences": "마법약, 도서관, 친구",
        "safety_rules": "위험한 주문을 혼자 사용하지 않는다.",
        "persona_summary": "아르카나 학교에서 연금술을 배우는 학생",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _world_character(**overrides):
    values = {
        "id": "world-character-a",
        "role_key": "student",
        "local_profile": {"background": "연금술과 2학년"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _world_context() -> schemas.WorldGenerationContextRead:
    return schemas.WorldGenerationContextRead(
        world_id="world-a",
        name="아르카나 마법학교",
        tagline="마법을 배우는 기숙학교",
        setting_description="마법 학생들이 수업과 동아리 활동을 한다.",
        daily_life_description="수업, 식사, 자습과 교류가 이어진다.",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
        timezone="Asia/Seoul",
        language="ko",
        definition_version=1,
        contract_version="world-v1",
        contract_hash="a" * 64,
        additional_generation_guidance="",
        places=[
            schemas.WorldPlaceInput(
                key="alchemy-lab",
                name="연금술 실습실",
                available_dayparts=["morning", "afternoon", "evening", "dawn"],
                access_role_keys=["student"],
            )
        ],
        roles=[
            schemas.WorldRoleInput(
                key="student",
                name="학생",
                autonomous_allowed=True,
            )
        ],
        daypart_profiles=[],
        rules=[
            schemas.WorldRuleInput(
                key="no-dangerous-spells",
                rule_kind="forbid",
                description="감독 없이 위험한 주문 사용",
            )
        ],
        glossary=[],
    )


def _profile_payload() -> dict:
    return {
        "visible_summary": "연금술과 친구들의 학업 이야기에 관심을 보인다.",
        "core_interests": ["연금술", "마법약", "친구"],
        "adjacent_interests": ["도서관", "기숙사 생활"],
        "avoid_topics": ["위험한 주문"],
        "discovery_openness": 72,
        "search_keywords": [
            "연금술",
            "마법약",
            "도서관",
            "실습",
            "기숙사",
            "친구",
            "수업",
            "학교 행사",
        ],
        "action_profile": {
            key: {"weight": 50, "note": f"{key} 행동 기준"}
            for key in schemas.WORLD_COMMUNITY_ACTION_KEYS
        },
    }


def _repertoire_payload() -> dict:
    activity_names = [
        "재료 정리",
        "향기 기록",
        "온도 관찰",
        "도구 세척",
        "약초 분류",
        "공식 복습",
        "실험 일지",
        "안전 표식",
        "친구 피드백",
        "보관함 점검",
    ]
    activity_kinds = [
        "duty",
        "rest",
        "self_care",
        "hobby",
        "exploration",
        "social",
        "maintenance",
        "challenge",
        "duty",
        "rest",
    ]
    candidates = []
    for daypart in contracts.DAYPARTS:
        for index in range(10):
            activity_name = activity_names[index]
            candidates.append(
                {
                    "daypart": daypart,
                    "activity_kind": activity_kinds[index],
                    "title": f"{daypart} {activity_name}",
                    "activity_seed": (
                        f"{daypart} 시간에 {activity_name} 활동을 진행하고 "
                        f"그 결과를 개인 노트의 {index + 1}번 항목에 정리한다."
                    ),
                    "place_key": "alchemy-lab",
                    "social_mode": "open_to_interaction",
                }
            )
    return {"candidates": candidates}


def test_character_contract_hash_is_stable_and_excludes_unrelated_fields() -> None:
    baseline = contracts.character_contract_hash(_character())
    whitespace_variant = contracts.character_contract_hash(
        _character(name="마린", avatar_url="https://example.test/private.png")
    )
    changed = contracts.character_contract_hash(
        _character(personality="활발하고 호기심이 많다.")
    )

    assert baseline == whitespace_variant
    assert baseline != changed


def test_community_profile_contract_normalizes_and_requires_exact_keys() -> None:
    profile = contracts.validate_community_profile(_profile_payload())
    assert len(profile.search_keywords) == 8
    assert set(profile.action_profile.model_dump()) == schemas.WORLD_COMMUNITY_ACTION_KEYS

    duplicate = _profile_payload()
    duplicate["search_keywords"][-1] = " 연금술 "
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_community_profile(duplicate)
    assert exc_info.value.reason_code == "profile_keyword_count_invalid"

    unexpected_action = _profile_payload()
    unexpected_action["action_profile"]["share"] = {
        "weight": 50,
        "note": "unsupported action",
    }
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_community_profile(unexpected_action)
    assert exc_info.value.reason_code == "profile_schema_invalid"


def test_gemini_transport_schemas_use_only_fixed_properties() -> None:
    profile_schema = world_character_provider.GEMINI_PROFILE_RESPONSE_SCHEMA
    repertoire_schemas = tuple(
        world_character_provider.GEMINI_REPERTOIRE_RESPONSE_SCHEMAS.values()
    )

    def assert_supported(value) -> None:
        if isinstance(value, dict):
            assert "additionalProperties" not in value
            assert "$defs" not in value
            assert "$ref" not in value
            for item in value.values():
                assert_supported(item)
        elif isinstance(value, list):
            for item in value:
                assert_supported(item)

    assert_supported(profile_schema)
    for repertoire_schema in repertoire_schemas:
        assert_supported(repertoire_schema)
    action_schema = profile_schema["properties"]["action_profile"]
    assert set(action_schema["properties"]) == schemas.WORLD_COMMUNITY_ACTION_KEYS
    assert set(action_schema["required"]) == schemas.WORLD_COMMUNITY_ACTION_KEYS
    for repertoire_schema in repertoire_schemas:
        assert len(repertoire_schema["properties"]) == 2
        for candidates_schema in repertoire_schema["properties"].values():
            assert candidates_schema["minItems"] == 10
            assert candidates_schema["maxItems"] == 10
            candidate_schema = candidates_schema["items"]
            assert set(candidate_schema["properties"]) == {
                "kind",
                "title",
                "seed",
                "place",
                "social",
            }
            assert set(candidate_schema["required"]) == {
                "kind",
                "title",
                "seed",
                "social",
            }
            assert candidate_schema["properties"]["title"]["minLength"] == 1
            assert candidate_schema["properties"]["title"]["maxLength"] == 120
            assert candidate_schema["properties"]["seed"]["maxLength"] == 500

    for response_schema in (profile_schema, *repertoire_schemas):
        config = build_generate_content_config(
            system_prompt="system",
            max_output_tokens=128,
            response_mime_type="application/json",
            response_schema=response_schema,
            thinking_level=None,
        )
        serialized = config.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert "responseSchema" not in serialized
        assert_supported(serialized["responseJsonSchema"])


def test_repertoire_transport_uses_domain_keys_and_server_enforces_text_bounds() -> None:
    domain_payload = _repertoire_payload()
    domain_to_transport = {
        value: key
        for key, value in world_character_provider._REPERTOIRE_TRANSPORT_FIELDS.items()
    }
    transport_payload = {
        daypart: [
            {
                domain_to_transport[key]: value
                for key, value in candidate.items()
                if key != "daypart"
            }
            for candidate in domain_payload["candidates"]
            if candidate["daypart"] == daypart
        ]
        for daypart in ("dawn", "morning")
    }
    expanded_candidates = world_character_provider._expand_repertoire_transport(
        transport_payload,
        dayparts=("dawn", "morning"),
    )
    assert expanded_candidates == domain_payload["candidates"][:20]
    validated = contracts.validate_activity_repertoire(
        domain_payload,
        world_context=_world_context(),
        world_character=_world_character(),
    )
    assert len(validated.candidates) == 40

    invalid = _repertoire_payload()
    invalid["candidates"][0]["title"] = "x" * 121
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            invalid,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "provider_response_invalid"

    prompt = world_character_provider._REPERTOIRE_SYSTEM_PROMPT
    assert "title=short owner-visible activity title" in prompt
    assert "seed=concrete activity_seed" in prompt
    assert "1..500 characters" in prompt


def test_repertoire_contract_accepts_exact_4_by_10() -> None:
    result = contracts.validate_activity_repertoire(
        _repertoire_payload(),
        world_context=_world_context(),
        world_character=_world_character(),
    )

    assert len(result.candidates) == 40
    assert result.daypart_counts == {daypart: 10 for daypart in contracts.DAYPARTS}
    assert all(1 <= candidate.ordinal <= 10 for candidate in result.candidates)
    assert len({candidate.canonical_signature for candidate in result.candidates}) == 40


@pytest.mark.parametrize("candidate_count", [39, 41])
def test_repertoire_contract_rejects_wrong_total(candidate_count: int) -> None:
    payload = _repertoire_payload()
    if candidate_count == 39:
        payload["candidates"].pop()
    else:
        payload["candidates"].append(dict(payload["candidates"][-1]))
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            payload,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "repertoire_count_invalid"


def test_repertoire_contract_rejects_daypart_and_cross_world_references() -> None:
    wrong_daypart = _repertoire_payload()
    wrong_daypart["candidates"][0]["daypart"] = "morning"
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            wrong_daypart,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "repertoire_daypart_invalid"

    cross_world = _repertoire_payload()
    cross_world["candidates"][0]["place_key"] = "other-world-place"
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            cross_world,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "world_reference_invalid"


def test_repertoire_contract_rejects_exact_and_near_duplicates() -> None:
    duplicate = _repertoire_payload()
    duplicate["candidates"][1] = dict(duplicate["candidates"][0])
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            duplicate,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "repertoire_duplicate"

    near_duplicate = _repertoire_payload()
    near_duplicate["candidates"][1] = dict(near_duplicate["candidates"][0])
    near_duplicate["candidates"][1]["title"] += "!"
    near_duplicate["candidates"][1]["activity_seed"] += " 조금"
    with pytest.raises(contracts.WorldCharacterContractError) as exc_info:
        contracts.validate_activity_repertoire(
            near_duplicate,
            world_context=_world_context(),
            world_character=_world_character(),
        )
    assert exc_info.value.reason_code == "repertoire_duplicate"


def test_generation_input_contains_only_same_world_safe_context() -> None:
    character = _character()
    character.owner_email = "owner@example.test"
    context = contracts.build_world_character_generation_input(
        character=character,
        world_character=_world_character(
            local_profile={
                "background": "연금술과 2학년",
                "private_note": "must not leak",
            }
        ),
        world_context=_world_context(),
    )
    serialized = str(context)
    assert "owner@example.test" not in serialized
    assert "private_note" not in serialized
    assert context["world"]["world_id"] == "world-a"
