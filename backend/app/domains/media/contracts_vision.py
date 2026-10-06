"""Purpose-specific policy supplied by the runtime, never a foreign key picker."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VisionPolicy:
    model: str
    thinking_level: str
    enabled: bool
    daily_limit: int | None
    credential_revision: int
    scope_key: str
    cache_scope: str
    settings_path: str


class VisionPolicyPort(Protocol):
    def read(self, db, owner_id, asset, actor_id=None) -> VisionPolicy: ...
    def resolve(self, db, row, asset): ...
    def available(self, db, policy) -> bool: ...
    def lock(self, db, policy) -> None: ...
    def reserve(self, db, policy, request_key) -> None: ...
    def transition(self, db, request_key, state) -> None: ...
