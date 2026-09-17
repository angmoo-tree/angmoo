"""Opaque references for provider packets, preserving source/turn associations."""

from dataclasses import replace
from hashlib import sha256


def episode_provider_reference(kind, identifier):
    return kind + "-" + sha256(f"{kind}:{identifier}".encode()).hexdigest()[:24]


def episode_provider_view(packets):
    """Convert identifiers before budget calculation, never rewrite prose.

    This is not anonymization of story content. It keeps storage identities
    out of model control metadata while retaining character names in prose.
    """
    return tuple(replace(packet,
        reference=episode_provider_reference("episode", packet.reference),
        follows_references=tuple(episode_provider_reference("episode", ref) for ref in packet.follows_references),
        units=tuple(replace(unit,
            reference=episode_provider_reference("unit", unit.reference),
            thought_reference=episode_provider_reference("thought", unit.thought_reference) if unit.thought_reference else None,
            sources=tuple(replace(source, reference=episode_provider_reference("source", source.reference))
                          for source in unit.sources)) for unit in packet.units),
    ) for packet in packets)
