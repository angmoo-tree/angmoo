from dataclasses import replace
import pytest
from sqlalchemy import select

from memory.test_activity_situation_contract import stack, values, NOW
from memory.test_activity_situation_application import apply, real_source
from app.domains.memory.policies.situation_output import language_only, parse_description, parse_situations, inspect_situations
from app.domains.memory.policies.situation_generation import instructions, with_chat_situation, with_social_situations
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_validation import restore_admission
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.activity_situation import stable_digest
from app.runtime.memory.situation_application_sources import PreparedSituationSources


@pytest.mark.parametrize("locale,raw", [("en-US", "en"), ("en-US", " ENGLISH "), ("en-GB", "en-GB"),
    ("ko-KR", "ko"), ("ko-KR", "Korean"), ("ja-JP", "ja"), ("ja-JP", "ja-JP")])
def test_only_exact_admitted_markers_are_blocked(locale, raw):
    assert language_only(raw, locale)
    assert parse_description(raw, target_key="one", locale=locale).error_code == "situation_description_language_only"
    payload = {"decision": {}, "draft": {}, "situations": [
        {"target_id": "one", "description": raw}, {"target_id": "two", "description": "Ian nodded."}]}
    parsed = parse_situations(payload, ("one", "two"), locale=locale)
    assert parsed["one"].status == "invalid" and parsed["two"].description == "Ian nodded."
    diagnostic = inspect_situations(payload, ("one", "two"), locale=locale)
    assert diagnostic["entries"][0]["reason"] == "description_language_only"


@pytest.mark.parametrize("raw", ["Ian nodded.", "Hi!", "no", "it", "Ian mentioned English lessons.", "English.", "🙂", "고마워했다."])
def test_no_language_dictionary_or_sentence_shape_heuristics(raw):
    assert not language_only(raw, "en-US")
    assert parse_description(raw, target_key="one", locale="en-US").description == raw


@pytest.mark.parametrize("locale,name", [("en-US", "English"), ("ko-KR", "Korean"), ("ja-JP", "ja-JP")])
def test_common_field_guidance_and_historical_schema(locale, name):
    base = {"properties": {"text": {"type": "string"}}, "required": ["text"]}
    chat = with_chat_situation(base, locale=locale)
    social = with_social_situations(base, ["one"], locale=locale)
    description = chat["properties"]["situation_description"]["description"]
    assert f"in {name};" in description
    assert social["properties"]["situations"]["items"]["properties"]["description"]["description"] == description
    legacy = with_social_situations(base, ["one"], locale=locale, revision="situation-target-output.v2")
    assert "description" not in legacy["properties"]["situations"]["items"]["properties"]["description"]
    for lane in ("chat", "routine", "feed", "inbox"):
        assert "relevant previous context actually supplied" in instructions(locale, lane)
        assert "Do not try to fill every category" in instructions(locale, lane)
        assert "relevant previous context actually supplied" not in instructions(locale, lane, revision="situation-target-output.v2")


@pytest.mark.parametrize("historical", [False, True])
def test_new_and_historical_marker_receipts_do_not_become_memories(stack, historical):
    session, scope, setting, memory = stack
    post = real_source(session, scope)
    manifest, _, result = values(session, scope, target=post.id)
    source = PreparedSituationSources(session).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/target/body", role="core", ordinal=0, target=post.id)
    manifest = replace(manifest, snapshot=replace(manifest.snapshot, memory_search_locale="en-US"), sources=(source,))
    draft = parse_description("en", target_key=post.id, locale=None if historical else "en-US")
    row = admit(session, manifest=manifest, draft=draft, result=result, now=NOW)
    original = row.content_digest, row.description, row.description_status, stable_digest(row.result)
    session.commit()
    if historical:
        assert restore_admission(session, row, revision="situation-validation.v4").receipt.description == "en"
        for revision in ("situation-validation.v5", "situation-validation.v6"):
            with pytest.raises(ValueError, match="situation_description_language_only"):
                restore_admission(session, row, revision=revision)
        apply(session, setting, memory)
    assert row.state == "blocked" and row.error_code == "situation_description_language_only"
    assert (row.content_digest, row.description, row.description_status, stable_digest(row.result)) == original
    assert session.scalar(select(MemoryItem.id)) is None
