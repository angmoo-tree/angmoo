from dataclasses import replace
import json

from app.contracts.activity_thought import parse_activity_thought
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketUnit, EpisodePacketSource
from app.domains.memory.policies.episode_packets import bounded_episode_packets


def packet(index, body="9월 13일 공연은 취소됐어."):
    return EpisodePacket(f"episode-{index}", "9월 10일 연습했고 13일 공연은 취소됐다.", "episode_v1", (
        EpisodePacketUnit(f"unit-{index}", (
            EpisodePacketSource("source-cancel", "user", body, "verified", end_offset=len(body)),
        ), parse_activity_thought("다음 준비를 돕고 싶다."), "thought-1"),
    ))


def test_rank_order_dedup_and_shared_source_thought_preserve_links():
    result = bounded_episode_packets((packet(1), packet(2), packet(1)))
    assert [p["ref"] for p in result.packets] == ["episode-1", "episode-2"]
    assert result.packets[1]["units"][0]["sources"][0]["already_in_context"]
    assert result.packets[1]["units"][0]["thought"]["already_in_context"]
    assert result.text.count("9월 13일 공연은 취소됐어.") == 1
    assert result.text.count("다음 준비를 돕고 싶다.") == 1


def test_missing_cancellation_is_partial_not_verified_or_deleted_episode():
    original = packet(1)
    unit = original.units[0]
    value = replace(original, units=(replace(unit, sources=(replace(unit.sources[0], text=None, status="missing"),)),))
    result = bounded_episode_packets((value,))
    assert result.packets[0]["partial"]
    assert result.packets[0]["source_statuses"] == {"verified": 0, "missing": 1, "changed": 0, "unavailable": 0}
    assert "13일 공연은 취소됐다" in result.text
    assert "취소됐어" not in result.text


def test_no_remaining_original_links_is_explicitly_partial():
    for units in ((), (EpisodePacketUnit("empty", ()),)):
        value = replace(packet(1), units=units)
        result = bounded_episode_packets((value,))
        assert result.packets[0]["partial"]
        assert result.packets[0]["source_statuses"]["verified"] == 0
        assert result.packets[0]["situation"] == value.summary


def test_large_unit_is_omitted_whole_without_truncating_cancellation():
    result = bounded_episode_packets((packet(1, "연습" * 5000 + "공연은 취소됐어."),))
    assert len(result.text) <= 8000
    assert result.omitted_units == 1
    assert result.packets[0]["units"] == []
    assert result.packets[0]["partial"]
    assert "13일 공연은 취소됐다" in result.text


def test_chat_and_sns_have_independent_packet_and_actual_json_budgets():
    values = tuple(packet(i) for i in range(20))
    for purpose, maximum, budget in (("chat", 12, 8000), ("sns", 3, 3000)):
        result = bounded_episode_packets(values, purpose=purpose)
        assert len(result.packets) <= maximum
        assert result.omitted_packets == 20 - len(result.packets)
        assert len(result.text) <= budget
        assert json.loads(result.text)["omitted_units"] == result.omitted_units
