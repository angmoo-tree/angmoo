"""Immutable server-owned identity/evidence used by a single generation request."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RoutineRequestContext:
    world_id: str
    actor_id: str
    episode_id: str
    beat_id: str
    sequence_no: int
    considered_source_event_ids: tuple[str, ...]
    continuity_facts: tuple[str, ...]
    detail_keys: tuple[str, ...]
    plan_version: int
    episode_version: int
    state_schema_version: int
    output_contract: str
    claim_run_id: str
    source_context_digest: str

    def metadata(self) -> dict:
        return {"episode_id": self.episode_id, "beat_id": self.beat_id,
            "sequence_no": self.sequence_no, "considered_source_event_ids": list(self.considered_source_event_ids)}
