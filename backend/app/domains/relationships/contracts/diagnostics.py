"""Read-only values and same-Session owner collaborators for diagnostics."""
from __future__ import annotations
from datetime import date, datetime
from typing import Protocol
from app.domains.relationships.contracts.graph_read import GraphProvider, RelationshipGraphReadGateway
from app.domains.relationships.contracts.projection_commands import ProjectionPost


class DiagnosticsOwner(Protocol):
    @property
    def id(self) -> str: ...


class DiagnosticsCharacter(Protocol):
    @property
    def owner_id(self) -> str: ...
    @property
    def deleted_at(self) -> datetime | None: ...


class DiagnosticsWorldCharacter(Protocol):
    @property
    def id(self) -> str: ...


class DiagnosticsJoint(Protocol):
    id: str
    proposal_id: str | None
    activity_seed: str
    place_key: str | None
    scheduled_local_date: date | None
    target_daypart: str | None
    timezone_snapshot: str | None
    status: str
    opening_post_id: str | None
    opened_by_world_character_id: str | None
    started_at: datetime | None
    completed_at: datetime | None


class DiagnosticsReferences(Protocol):
    def get_character(self, character_id: str) -> DiagnosticsCharacter | None: ...
    def find_world_character(self, *, world_id: str, character_id: str) -> DiagnosticsWorldCharacter | None: ...
    def world_character_status(self, *, world_id: str, world_character_id: str) -> str | None: ...
    def pair_blocked(self, *, world_id: str, actor_id: str, target_id: str) -> bool: ...
    def get_post(self, post_id: str) -> ProjectionPost | None: ...
    def list_active_joint_activities(self, *, world_id: str, world_character_id: str) -> list[tuple[DiagnosticsJoint, list[object]]]: ...
    def graph_gateway(self, *, graph_provider: GraphProvider) -> RelationshipGraphReadGateway: ...
