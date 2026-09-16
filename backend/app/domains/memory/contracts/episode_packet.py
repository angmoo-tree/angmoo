"""Scoped, revalidated episode detail passed to one response or SNS writer."""

from dataclasses import dataclass
from typing import Literal
from collections.abc import Mapping
from typing import Protocol

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence


@dataclass(frozen=True, slots=True)
class EpisodeSourceDetail:
    evidence: CanonicalMemoryEvidence
    text: str


class EpisodeDetailReader(Protocol):
    def read_sources(self, *, scope: MemoryScope, identities: tuple[tuple[str, str], ...]) -> Mapping[tuple[str, str], EpisodeSourceDetail]: ...
    def read_thoughts(self, *, scope: MemoryScope, references: tuple[str, ...]) -> Mapping[str, ActivityThought]: ...

EPISODE_PACKET_VERSION = "episode-packet.v1"
CHAT_PACKET_LIMIT = 12
CHAT_PACKET_CHARACTERS = 8_000
SNS_PACKET_LIMIT = 3
SNS_PACKET_CHARACTERS = 3_000


@dataclass(frozen=True, slots=True)
class EpisodePacketSource:
    reference: str
    role: str
    text: str | None
    status: Literal["verified", "missing", "changed", "unavailable"]
    start_offset: int = 0
    end_offset: int | None = None

    def __post_init__(self):
        if not self.reference or self.status not in {"verified", "missing", "changed", "unavailable"}:
            raise ValueError("episode_packet_source_invalid")
        if (self.text is not None) != (self.status == "verified"):
            raise ValueError("episode_packet_source_content_invalid")


@dataclass(frozen=True, slots=True)
class EpisodePacketUnit:
    reference: str
    sources: tuple[EpisodePacketSource, ...]
    thought: ActivityThought = ActivityThought()
    thought_reference: str | None = None
    coverage: str = "complete"
    legacy_subjective_context: str | None = None


@dataclass(frozen=True, slots=True)
class EpisodePacket:
    reference: str
    summary: str
    representation: Literal["legacy_summary", "episode_v1"]
    units: tuple[EpisodePacketUnit, ...]
    follows_references: tuple[str, ...] = ()
    followup_truncated: bool = False


@dataclass(frozen=True, slots=True)
class EpisodePacketDelivery:
    packets: tuple[dict, ...]
    omitted_packets: int
    omitted_units: int
    text: str
