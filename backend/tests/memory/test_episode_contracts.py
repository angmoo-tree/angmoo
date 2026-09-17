from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.contracts.activity_thought import parse_activity_thought
from app.domains.memory.contracts.episode import EpisodeBundle, EpisodeSourceMember, EpisodeSourceUnit
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.policies.episode_bundles import partition_episode_units, bundle_manifest_hash
from app.domains.memory.policies.episode_prompt import episode_prompt_payload
from app.domains.memory.policies.episode_selection import parse_episode_selection


def unit(index, text="연습을 돕겠다고 제안했다."):
    return EpisodeSourceUnit(
        unit_key=f"turn-{index}", unit_revision="a" * 64,
        scope=MemoryScope("owner", "world", "character"), kind="chat_turn",
        occurred_at=datetime(2026, 9, 16, tzinfo=UTC), thread_id="thread",
        members=(EpisodeSourceMember("CHAT_MESSAGE", f"message-{index}", "b" * 64, "user", text),),
    )


def test_oversized_source_ranges_preserve_every_character_and_original_identity():
    from app.domains.memory.policies.episode_ranges import split_source_unit
    source = unit(1, "가나다🙂" * 7000)
    parts = split_source_unit(source)
    assert len(parts) > 1
    members = [m for part in parts for m in part.members]
    assert "".join(m.text for m in members) == source.members[0].text
    assert {m.source_id for m in members} == {source.members[0].source_id}
    assert all(part.coverage == "partial_source" for part in parts)
    assert all(len(m.text) <= 6000 for m in members)
    assert members[-1].start_offset + len(members[-1].text) == len(source.members[0].text)
    for bundle in partition_episode_units(parts, activation_epoch="range-test", cutoff_sequence=1):
        episode_prompt_payload(bundle)


@pytest.mark.parametrize("length", [279, 280, 281, 2000])
def test_thought_is_bounded_without_rejecting_valid_body(length):
    thought = parse_activity_thought("생" * length)
    assert thought.status == "recorded"
    assert len(thought.text) == min(length, 280)
    assert thought.truncated == (length > 280)


@pytest.mark.parametrize("value,status", [(None, "missing"), ("  ", "missing"), ({}, "invalid"), (123, "invalid")])
def test_bad_thought_is_data_not_a_generation_exception(value, status):
    assert parse_activity_thought(value).status == status


@pytest.mark.parametrize("size", [0, 1, 49, 50, 51, 100, 300])
def test_partition_preserves_new_units_and_overlap(size):
    sources = tuple(unit(i) for i in range(size))
    bundles = partition_episode_units(sources, activation_epoch="epoch", cutoff_sequence=size)
    assert tuple(u for b in bundles for u in b.new_units) == sources
    for index, bundle in enumerate(bundles):
        assert len(bundle.new_units) <= 50
        assert len(bundle.context_units) <= 5
        if index:
            assert bundle.context_units == bundles[index - 1].new_units[-5:]
        episode_prompt_payload(bundle)


def test_long_input_reduces_turn_count_not_source_content():
    sources = tuple(unit(i, "내용" * 600) for i in range(51))
    bundles = partition_episode_units(sources, activation_epoch="epoch", cutoff_sequence=51)
    assert len(bundles) > 2
    assert tuple(u for b in bundles for u in b.new_units) == sources


def test_single_oversized_source_requires_explicit_range_path():
    with pytest.raises(MemoryValidationError, match="source_range_split_required"):
        partition_episode_units((unit(1, "가" * 25000),), activation_epoch="epoch", cutoff_sequence=1)


def test_private_threads_cannot_share_bundle():
    with pytest.raises(MemoryValidationError, match="scope_mismatch"):
        partition_episode_units((unit(1), replace(unit(2), thread_id="other")), activation_epoch="epoch", cutoff_sequence=2)


def payload():
    return {"bundle_ref": "B1", "episodes": [{"summary": "연습은 취소됐다.", "source_refs": ["S1", "S2"], "follows_episode_refs": []}], "skipped_new_refs": [], "needs_split": False}


def test_selected_sources_resolve_to_prebound_units():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)))
    parsed = parse_episode_selection(payload(), bundle)
    assert parsed.episodes[0].source_refs == ("S1", "S2")


@pytest.mark.parametrize("refs", [["S1"], ["S1", "S999"], ["S1", "S1"], ["S1", {}]])
def test_missing_duplicate_or_invented_source_is_not_accepted(refs):
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)))
    data = payload()
    data["episodes"][0]["source_refs"] = refs
    with pytest.raises(MemoryValidationError):
        parse_episode_selection(data, bundle)


def test_reference_only_episode_and_used_skip_conflict_are_rejected():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)), (unit(0),))
    data = payload()
    data["episodes"][0]["source_refs"] = ["C1"]
    with pytest.raises(MemoryValidationError, match="new_source_required"):
        parse_episode_selection(data, bundle)
    data = payload()
    data["skipped_new_refs"] = ["S1"]
    with pytest.raises(MemoryValidationError, match="coverage_incomplete"):
        parse_episode_selection(data, bundle)


def test_zero_memories_requires_explicit_skip_of_every_new_source():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)))
    data = {"bundle_ref": "B1", "episodes": [], "skipped_new_refs": ["S1", "S2"], "needs_split": False}
    assert not parse_episode_selection(data, bundle).episodes


def test_split_result_does_not_mark_any_source_processed():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1),))
    data = {"bundle_ref": "B1", "episodes": [], "skipped_new_refs": [], "needs_split": True}
    assert parse_episode_selection(data, bundle).needs_split
    data["skipped_new_refs"] = ["S1"]
    with pytest.raises(MemoryValidationError, match="split_has_results"):
        parse_episode_selection(data, bundle)


def test_summary_is_not_silently_truncated():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1), unit(2)))
    data = payload()
    data["episodes"][0]["summary"] = "가" * 2001
    with pytest.raises(MemoryValidationError, match="summary_invalid"):
        parse_episode_selection(data, bundle)


def test_manifest_changes_when_context_revision_or_cutoff_changes():
    bundle = EpisodeBundle("B1", unit(1).scope, (unit(1),), (unit(0),), cutoff_sequence=1)
    changed = replace(bundle, context_units=(replace(unit(0), unit_revision="c" * 64),))
    assert bundle_manifest_hash(bundle) != bundle_manifest_hash(changed)
    assert bundle_manifest_hash(bundle) != bundle_manifest_hash(replace(bundle, cutoff_sequence=2))
