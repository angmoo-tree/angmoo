"""Minimal Worlds and role restrictions bound generated place identifiers."""
from app.domains.world_characters.client import _scoped_repertoire_schema, GEMINI_REPERTOIRE_RESPONSE_SCHEMAS


def test_no_registered_places_has_no_place_output_field():
    schema = _scoped_repertoire_schema(("dawn", "morning"), {"world": {"places": []}})
    for daypart in ("dawn", "morning"):
        assert "place" not in schema["properties"][daypart]["items"]["properties"]
    assert "place" in GEMINI_REPERTOIRE_RESPONSE_SCHEMAS[("dawn", "morning")]["properties"]["dawn"]["items"]["properties"]


def test_place_output_uses_only_actor_role_and_daypart_candidates():
    source = {"world_character": {"role_key": "student"}, "world": {"places": [
        {"key": "public", "access_role_keys": [], "available_dayparts": []},
        {"key": "classroom", "access_role_keys": ["student"], "available_dayparts": ["morning"]},
        {"key": "staff", "access_role_keys": ["teacher"], "available_dayparts": []},
    ]}}
    schema = _scoped_repertoire_schema(("dawn", "morning"), source)
    assert schema["properties"]["dawn"]["items"]["properties"]["place"]["enum"] == ["public"]
    assert schema["properties"]["morning"]["items"]["properties"]["place"]["enum"] == ["public", "classroom"]
