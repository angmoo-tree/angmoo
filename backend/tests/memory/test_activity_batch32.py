from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.domains.memory.contracts.activity_batch import chat_excerpt, private_thread_intersection
from app.domains.memory.contracts.episode import EpisodeBundle, EpisodeSourceMember, EpisodeSourceUnit
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.policies.activity_bundles import partition_activity_units
from app.domains.memory.policies.episode_bundles import bundle_manifest_hash
from app.domains.memory.policies.episode_selection import parse_episode_selection
from app.domains.memory.service.episode_manifest import episode_input_manifest, restore_episode_input


def source(index, *, chat=True, text="hello", thread="thread"):
    return EpisodeSourceUnit(f"unit-{index:04}", "a" * 64, MemoryScope("owner", "world", "subject"),
        "chat_turn" if chat else "sns_interaction", datetime(2026, 10, 6, tzinfo=UTC) + timedelta(seconds=index),
        (EpisodeSourceMember("CHAT_MESSAGE" if chat else "POST", str(index), sha256(text.encode()).hexdigest(),
            "user" if chat else "post", text, total_characters=len(text)),), thread_id=thread if chat else None)


@pytest.mark.parametrize("length", [0, 499, 500, 501, 100_000])
def test_excerpt_preserves_exact_unicode_ranges_and_whole_identity(length):
    raw = ("가🙂\r\n " * (length // 5 + 1))[:length]
    value = chat_excerpt(raw)
    assert value.text == "".join(raw[left:right] for left, right in value.segments)
    assert len(value.text) == min(500, length)
    assert value.omitted_characters + len(value.text) == length
    assert value.whole_hash == sha256(raw.encode()).hexdigest()
    if length > 500:
        assert value.segments == ((0, 350), (length - 150, length))


def test_32_chat_activities_are_one_request_not_32_turns():
    units = tuple(source(index, text="short complete utterance") for index in range(960))
    bundles = partition_activity_units(units, activation_epoch="epoch", cutoff_sequence=960)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert len(bundle.activities) == 32 and len(bundle.new_units) == 960
    assert all(len(a.unit_keys) == 30 and len(a.context_keys) <= 5 for a in bundle.activities)
    assert {u.unit_key for u in bundle.new_units} == {u.unit_key for u in units}


def test_sns_and_chat_share_a_request_and_activity_is_not_an_output_reference():
    bundles = partition_activity_units((source(1), source(2, chat=False)), activation_epoch="epoch", cutoff_sequence=2)
    assert len(bundles) == 1 and len(bundles[0].activities) == 2
    with pytest.raises(MemoryValidationError, match="reference_invalid"):
        parse_episode_selection({"bundle_ref": "B1", "episodes": [{"summary": "test", "source_refs": ["A1"],
            "follows_episode_refs": []}], "skipped_new_refs": ["S2"], "needs_split": False}, bundles[0])


def test_private_intersection_does_not_union_or_ignore_skipped_inputs():
    assert private_thread_intersection((None, "thread", None)) == "thread"
    with pytest.raises(MemoryValidationError, match="intersection_empty"):
        partition_activity_units((source(1), source(2, thread="other")), activation_epoch="epoch", cutoff_sequence=2)


def test_new_output_limits_do_not_change_legacy_contract():
    unit = source(1)
    legacy = EpisodeBundle("B1", unit.scope, (unit,))
    modern = partition_activity_units((unit,), activation_epoch="epoch", cutoff_sequence=1)[0]
    payload = {"bundle_ref": "B1", "episodes": [{"summary": "x" * 1500, "source_refs": ["S1"],
        "follows_episode_refs": []}], "skipped_new_refs": [], "needs_split": False}
    assert parse_episode_selection(payload, legacy).episodes
    with pytest.raises(MemoryValidationError, match="summary_invalid"):
        parse_episode_selection(payload, modern)
    assert episode_input_manifest(legacy)["version"] == "episode-input.v1"
    assert "segments" not in episode_input_manifest(legacy)["new"][0]["members"][0]


def test_omitted_middle_change_invalidates_manifest_even_when_excerpt_matches():
    raw = "x" * 350 + "middle" + "z" * 150
    bundle = partition_activity_units((source(1, text=raw),), activation_epoch="epoch", cutoff_sequence=1)[0]
    changed = partition_activity_units((source(1, text=raw.replace("middle", "MIDDLE")),), activation_epoch="epoch", cutoff_sequence=1)[0]
    assert bundle.new_units[0].members[0].text == changed.new_units[0].members[0].text
    assert bundle_manifest_hash(bundle) != bundle_manifest_hash(changed)
    assert "middle" not in str(episode_input_manifest(bundle))
