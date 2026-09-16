"""Owner-visible bounded episode material without internal source identifiers."""

from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def episode_detail_view(db, scope, item_id, now):
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(
        scope=scope, item_ids=(item_id,), now=now, require_enabled=False)
    if not packets:
        return None
    delivery = bounded_episode_packets(episode_provider_view(packets))
    if not delivery.packets:
        return None
    packet = delivery.packets[0]
    return public_episode_packet(packet)


def public_episode_packet(packet):
    return {"representation": packet["representation"], "partial": packet["partial"],
        "omitted_units": packet["omitted_units"], "followup_count": len(packet["follows"]),
        "units": [{"sources": [{"role": source["role"], "text": source["text"],
                     "status": source["status"]} for source in unit["sources"] if not source.get("already_in_context")],
                   "thought": None if unit["thought"].get("already_in_context") else unit["thought"],
                   "legacy_declaration": unit.get("legacy_action_declaration")}
                  for unit in packet["units"]]}


def episode_receipt_view(db, scope, item_id, now, text):
    """Revalidate only material actually delivered to the completed response."""
    import json
    from dataclasses import asdict
    from copy import deepcopy
    if len(text) > 8000:
        return None
    try:
        frozen = json.loads(text)
        packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(
            scope=scope, item_ids=(item_id,), now=now, require_enabled=False)
        if not packets:
            return None
        current = episode_provider_view(packets)[0]
        if frozen["ref"] != current.reference or frozen["situation"] != current.summary:
            return None
        units = {u.reference: u for u in current.units}
        value = deepcopy(frozen)
        for unit in value["units"]:
            actual = units.get(unit["ref"])
            sources = {} if actual is None else {(s.reference, s.start_offset, s.end_offset): s for s in actual.sources}
            for source in unit["sources"]:
                if source.get("already_in_context"):
                    continue
                fresh = sources.get((source["reference"], source["start_offset"], source["end_offset"]))
                if fresh is None or asdict(fresh) != source:
                    source["text"] = None
                    source["status"] = "unavailable" if fresh is None else fresh.status if fresh.status != "verified" else "changed"
                    value["partial"] = True
            if not unit["thought"].get("already_in_context") and (
                    actual is None or asdict(actual.thought) != unit["thought"]):
                unit["thought"] = {"status": "invalid", "text": None, "truncated": False}
                value["partial"] = True
            if actual is None or actual.legacy_subjective_context != unit.get("legacy_action_declaration"):
                unit["legacy_action_declaration"] = None
        return frozen["situation"], public_episode_packet(value)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
