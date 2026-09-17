"""Rank-preserving packet budget with atomic units and explicit partial coverage."""

from dataclasses import asdict
import json

from app.domains.memory.contracts.episode_packet import (
    EpisodePacket, EpisodePacketDelivery, EPISODE_PACKET_VERSION,
    CHAT_PACKET_LIMIT, CHAT_PACKET_CHARACTERS, SNS_PACKET_LIMIT, SNS_PACKET_CHARACTERS,
)


def bounded_episode_packets(packets: tuple[EpisodePacket, ...], *, purpose: str = "chat") -> EpisodePacketDelivery:
    if purpose not in {"chat", "sns"}:
        raise ValueError("episode_packet_purpose_invalid")
    maximum, budget = (CHAT_PACKET_LIMIT, CHAT_PACKET_CHARACTERS) if purpose == "chat" else (SNS_PACKET_LIMIT, SNS_PACKET_CHARACTERS)
    # Dedup a fused episode by canonical identity while preserving RRF order.
    by_reference = {}
    for packet in packets:
        by_reference.setdefault(packet.reference, packet)
    unique = tuple(by_reference.values())
    selected = []
    seen_sources = set()
    seen_thoughts = set()
    omitted_units = 0

    def encoded(values, omitted):
        return json.dumps({"version": EPISODE_PACKET_VERSION, "packets": values,
                           "omitted_packets": len(unique) - len(values),
                           "omitted_units": omitted}, ensure_ascii=False, separators=(",", ":"))

    for packet in unique[:maximum]:
        # Validate/retain coverage counts for the entire manifest, not just the
        # units that fit. No missing source is described as verified evidence.
        statuses = {status: sum(s.status == status for u in packet.units for s in u.sources)
                    for status in ("verified", "missing", "changed", "unavailable")}
        has_unverified_sources = not statuses["verified"] or any(
            statuses[s] for s in ("missing", "changed", "unavailable"))
        payload = {"ref": packet.reference, "situation": packet.summary,
                   "representation": packet.representation, "source_statuses": statuses,
                   "followup_truncated": packet.followup_truncated,
                   "follows": list(packet.follows_references), "units": [],
                   "omitted_units": len(packet.units), "partial": bool(packet.units) or has_unverified_sources}
        # A situation is never cut into a misleading sentence prefix. Stop at
        # the first situation that cannot fit instead of preferring shorter,
        # lower-ranked memories merely because they are cheap.
        if len(encoded([*selected, payload], omitted_units + len(packet.units))) > budget:
            break
        pending_sources, pending_thoughts = set(), set()
        for unit in packet.units:
            sources = []
            unit_sources = set()
            for source in unit.sources:
                key = (source.reference, source.start_offset, source.end_offset)
                if source.status == "verified" and (key in seen_sources or key in pending_sources or key in unit_sources):
                    sources.append({"ref": source.reference, "start_offset": source.start_offset,
                                    "end_offset": source.end_offset, "already_in_context": True})
                else:
                    sources.append(asdict(source))
                    # Invalid/missing material is not an original-text cache hit.
                    if source.status == "verified":
                        unit_sources.add(key)
            duplicate_thought = unit.thought_reference is not None and unit.thought_reference in (seen_thoughts | pending_thoughts)
            value = {"ref": unit.reference, "sources": sources, "coverage": unit.coverage,
                     "thought_ref": unit.thought_reference,
                     "thought": {"already_in_context": True} if duplicate_thought else asdict(unit.thought),
                     "legacy_action_declaration": unit.legacy_subjective_context}
            trial = dict(payload, units=[*payload["units"], value], omitted_units=payload["omitted_units"] - 1)
            trial["partial"] = bool(trial["omitted_units"]) or has_unverified_sources or any(u.coverage != "complete" for u in packet.units)
            if len(encoded([*selected, trial], omitted_units + trial["omitted_units"])) > budget:
                continue
            payload = trial
            pending_sources.update(unit_sources)
            if unit.thought_reference and unit.thought.status == "recorded":
                pending_thoughts.add(unit.thought_reference)
        selected.append(payload)
        seen_sources.update(pending_sources)
        seen_thoughts.update(pending_thoughts)
        omitted_units += payload["omitted_units"]
    text = encoded(selected, omitted_units)
    if len(text) > budget:
        raise ValueError("episode_packet_budget_exceeded")
    return EpisodePacketDelivery(tuple(selected), len(unique) - len(selected), omitted_units, text)
