"""Request names preserve originals, exact scopes, literals and existing output bounds."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot, read_name_binding
from app.domains.characters.policies.name_macros import render_names, name_macro_review
from app.domains.characters.policies.authored_names import authored_routine_draft
from app.domains.characters.service.prompt_persona import request_persona, model_persona
from app.runtime.autonomous_activity.name_binding import social_draft_names


def binding(**changes):
    return replace(NameBindingSnapshot("owner", "world-a", "actor", "Sakana", "my-profile", "민식", 3), **changes)


@pytest.mark.parametrize("source, expected", [
    ("{{user}}는 {{char}}를 안다.", "민식는 Sakana를 안다."),
    ("{{ USER }} / {{ Char }} / <user> / <BOT> / <char>", "민식 / Sakana / 민식 / Sakana / Sakana"),
    ("'{{user}}'", "'민식'"),
    (r"\{{user}} + {{char}}", r"\{{user}} + Sakana"),
    ("`{{user}}` + {{user}}", "`{{user}}` + 민식"),
    ("```text\n{{user}}\n``` {{char}}", "```text\n{{user}}\n``` Sakana"),
    ("{{random::{{user}}}} {{user}}", "{{random::{{user}}}} 민식"),
    ("{{getvar::x}} {{user", "{{getvar::x}} {{user"),
    ("<username> <script> {{char}}", "<username> <script> Sakana"),
])
def test_one_pass_names_without_grammar_or_template_execution(source, expected):
    assert render_names(source, binding()).text == expected


def test_inserted_names_are_literal_even_with_macro_syntax_and_backslashes():
    names = binding(user_display_name="민수{{char}}$\\", actor_display_name="고양이{{user}}")
    assert render_names("{{user}} {{char}}", names, output=True).text == "민수{{char}}$\\ 고양이{{user}}"
    assert render_names("민수{{char}}$\\ 고양이{{user}}", names, output=True).text == "민수{{char}}$\\ 고양이{{user}}"


def test_policy_is_persisted_and_explicit_damage_does_not_downgrade():
    names = binding()
    assert read_name_binding({}) is None
    assert read_name_binding({"name_binding": names.to_dict()}) == names
    with pytest.raises(NameBindingError, match="missing"):
        read_name_binding({"name_binding_policy": names.policy_version})
    for corrupt in ({"actor_display_name": "Changed"}, {"binding_digest": "0" * 64}, {"user_display_name": None}):
        with pytest.raises(NameBindingError):
            read_name_binding({"name_binding": {**names.to_dict(), **corrupt}})


def test_absent_user_is_distinct_from_saved_default_user_and_char_still_works():
    absent = binding(user_display_name=None, user_world_character_id=None, user_profile_version=None)
    assert render_names("{{char}}", absent).text == "Sakana"
    with pytest.raises(NameBindingError, match="missing"):
        render_names("{{user}}", absent)
    assert render_names("{{user}}", binding(user_display_name="사용자")).text == "사용자"


def test_persona_allowlist_keeps_raw_settings_and_past_records_untouched():
    source = {"name": "Sakana", "worldview": "{{user}}의 친구 {{char}}", "speech_style": "대화 상대: 반가워",
              "personality": "{{char}}는 쾌활하다", "topic_preferences": "{{user}}와 게임", "id": "{{user}}"}
    original = dict(source)
    persona = request_persona(source, binding())
    assert persona["description"] == "민식의 친구 Sakana"
    assert persona["speech_style"] == "대화 상대: 반가워"
    assert persona["topic_preferences"] == "민식와 게임"
    assert source == original
    assert model_persona(source)["description"] == original["worldview"]


def test_rendered_limits_are_checked_without_truncating_or_changing_source():
    with pytest.raises(NameBindingError, match="rendered_limit"):
        render_names("{{user}}", binding(user_display_name="이름" * 40), limit=10)
    with pytest.raises(NameBindingError, match="rendered_limit"):
        request_persona({"worldview": "{{user}}" * 1000}, binding(user_display_name="긴이름" * 20))


def test_other_reply_recipient_uses_id_even_if_names_match():
    names = binding(user_display_name="Seraphina")
    assignments = [{"task_id": "task", "source": {"target_id": "post", "counterpart_id": "other-character"}}]
    with pytest.raises(NameBindingError, match="addressee_ambiguous"):
        social_draft_names({"replies": [{"target_id": "post", "body": "{{user}}, 고마워"}]}, names,
            assignments=assignments, combined=True, lane="feed")
    assignments[0]["source"]["counterpart_id"] = names.user_world_character_id
    final = social_draft_names({"replies": [{"target_id": "post", "body": "{{user}}, 고마워"}]}, names,
        assignments=assignments, combined=True, lane="feed")
    assert final["replies"][0] == {"target_id": "post", "body": "Seraphina, 고마워"}


def test_new_output_fields_keep_ids_and_literals_and_validate_final_lengths():
    value = {"title": "{{char}}", "body": "{{user}}, 좋아! `{{user}}`", "thought": "{{char}}는 즐거웠다",
             "source_id": "{{user}}", "quoted_record": "{{user}} 원문"}
    final = authored_routine_draft(value, binding())
    assert final["body"] == "민식, 좋아! `{{user}}`"
    assert final["thought"] == "Sakana는 즐거웠다"
    assert final["source_id"] == final["quoted_record"].split()[0] == "{{user}}"
    assert value["body"].startswith("{{user}}")
    with pytest.raises(NameBindingError, match="unsupported"):
        authored_routine_draft({"body": "{{getvar::x}}"}, binding())
    with pytest.raises(NameBindingError, match="rendered_limit"):
        authored_routine_draft({"title": "{{user}}" * 100}, binding())


def test_review_distinguishes_supported_names_and_unsupported_nested_syntax():
    assert name_macro_review("{{user}} {{ CHAR }} `{{user}}` {{random::{{user}}}}") == {
        "supported": 2, "unsupported": 1, "protected": 1}
