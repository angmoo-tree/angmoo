"""Immutable source snapshots and scoped episode proposals; no model authority."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import re

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.provenance import MemorySourceTypeV1

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")

EPISODE_VERSION = "episode-selection.v1"
MAX_NEW_CHAT_TURNS = 50
MAX_CONTEXT_CHAT_TURNS = 5
MAX_NEW_SOCIAL_UNITS = 20
MAX_EPISODE_CHARACTERS = 2_000
MAX_EPISODES_PER_BUNDLE = 50
MAX_PRIOR_EPISODES = 8
MAX_EPISODE_INPUT_CHARACTERS = 24_000
MAX_EPISODE_INPUT_BYTES = 72_000
MAX_EPISODE_OUTPUT_TOKENS = 8_192


@dataclass(frozen=True, slots=True)
class EpisodeSourceMember:
    source_type: str
    source_id: str
    source_digest: str
    role: str
    text: str
    start_offset: int = 0
    total_characters: int | None = None
    actor_label: str | None = None
    occurred_at: str | None = None

    def __post_init__(self) -> None:
        if (self.source_type not in MemorySourceTypeV1.values() or not self.source_id
            or not _DIGEST.fullmatch(self.source_digest) or not self.role or not isinstance(self.text, str)):
            raise ValueError("episode_source_identity_invalid")
        if self.start_offset < 0 or (self.total_characters is not None and self.start_offset + len(self.text) > self.total_characters):
            raise ValueError("episode_source_range_invalid")
        if self.actor_label is not None and (not self.actor_label.strip() or len(self.actor_label) > 80):
            raise ValueError("episode_source_actor_label_invalid")
        if self.occurred_at is not None and datetime.fromisoformat(self.occurred_at).tzinfo is None:
            raise ValueError("episode_source_time_invalid")


@dataclass(frozen=True, slots=True)
class EpisodeSourceUnit:
    unit_key: str
    unit_revision: str
    scope: MemoryScope
    kind: Literal["chat_turn", "sns_interaction", "observed_post", "event"]
    occurred_at: datetime
    members: tuple[EpisodeSourceMember, ...]
    thread_id: str | None = None
    thought: ActivityThought = ActivityThought()
    thought_reference: str | None = None
    coverage: Literal["complete", "partial_source"] = "complete"
    legacy_subjective_context: str | None = None

    def __post_init__(self) -> None:
        if (not self.unit_key or len(self.unit_key) > 160 or not _DIGEST.fullmatch(self.unit_revision)
            or not self.members or self.occurred_at.tzinfo is None):
            raise ValueError("episode_unit_invalid")
        if self.kind not in {"chat_turn", "sns_interaction", "observed_post", "event"}:
            raise ValueError("episode_unit_kind_invalid")
        if self.kind == "chat_turn" and not self.thread_id:
            raise ValueError("episode_chat_thread_required")
        if self.coverage not in {"complete", "partial_source"}:
            raise ValueError("episode_unit_coverage_invalid")
        if self.thought.status == "recorded" and not self.thought_reference:
            raise ValueError("episode_thought_reference_required")
        if self.legacy_subjective_context is not None and self.thought_reference is not None:
            raise ValueError("episode_duplicate_perspective")


@dataclass(frozen=True, slots=True)
class EpisodePriorCandidate:
    item_id: str
    item_version: int
    summary: str

    def __post_init__(self):
        if (not self.item_id or isinstance(self.item_version, bool) or self.item_version < 1
            or not self.summary.strip() or len(self.summary) > MAX_EPISODE_CHARACTERS):
            raise ValueError("episode_prior_invalid")


@dataclass(frozen=True, slots=True)
class EpisodeBundle:
    bundle_ref: str
    scope: MemoryScope
    new_units: tuple[EpisodeSourceUnit, ...]
    context_units: tuple[EpisodeSourceUnit, ...] = ()
    prior_episodes: tuple[EpisodePriorCandidate, ...] = ()
    activation_epoch: str = ""
    cutoff_sequence: int = 0

    def __post_init__(self) -> None:
        if not self.bundle_ref or not self.new_units or len(self.prior_episodes) > MAX_PRIOR_EPISODES:
            raise ValueError("episode_bundle_invalid")
        units = (*self.new_units, *self.context_units)
        if any(unit.scope != self.scope for unit in units):
            raise ValueError("episode_bundle_scope_mismatch")
        if len({unit.unit_key for unit in units}) != len(units):
            raise ValueError("episode_bundle_duplicate_unit")
        is_chat = self.new_units[0].kind == "chat_turn"
        if any((unit.kind == "chat_turn") != is_chat for unit in units):
            raise ValueError("episode_bundle_kind_mismatch")
        if is_chat and len({unit.thread_id for unit in units}) != 1:
            raise ValueError("episode_bundle_thread_mismatch")
        if len(self.new_units) > (MAX_NEW_CHAT_TURNS if is_chat else MAX_NEW_SOCIAL_UNITS):
            raise ValueError("episode_bundle_new_limit")
        if is_chat and len(self.context_units) > MAX_CONTEXT_CHAT_TURNS:
            raise ValueError("episode_bundle_context_limit")
        if len({prior.item_id for prior in self.prior_episodes}) != len(self.prior_episodes):
            raise ValueError("episode_bundle_duplicate_prior")

    def source_refs(self) -> dict[str, EpisodeSourceUnit]:
        return {
            **{f"S{i}": unit for i, unit in enumerate(self.new_units, 1)},
            **{f"C{i}": unit for i, unit in enumerate(self.context_units, 1)},
        }


@dataclass(frozen=True, slots=True)
class EpisodeProposal:
    summary: str
    source_refs: tuple[str, ...]
    follows_episode_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodeSelection:
    episodes: tuple[EpisodeProposal, ...]
    skipped_new_refs: tuple[str, ...]
    needs_split: bool = False
