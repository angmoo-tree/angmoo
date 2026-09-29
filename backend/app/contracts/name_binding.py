"""Shared durable, scoped names for one generation request; no template engine."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

NAME_BINDING_POLICY = "persona-name-binding-v1"


class NameBindingError(ValueError):
    """Safe reason code, with no names or source text in the exception."""


@dataclass(frozen=True)
class NameBindingSnapshot:
    owner_id: str
    world_id: str
    actor_world_character_id: str
    actor_display_name: str
    user_world_character_id: str | None = None
    user_display_name: str | None = None
    user_profile_version: int | None = None
    policy_version: str = NAME_BINDING_POLICY

    def __post_init__(self):
        if self.policy_version != NAME_BINDING_POLICY or any(
            not isinstance(value, str) or not value for value in
            (self.owner_id, self.world_id, self.actor_world_character_id, self.actor_display_name)
        ):
            raise NameBindingError("name_binding_invalid")
        user = (self.user_world_character_id, self.user_display_name, self.user_profile_version)
        if any(value is not None for value in user) and not (
            isinstance(user[0], str) and bool(user[0]) and isinstance(user[1], str) and bool(user[1])
            and type(user[2]) is int and user[2] >= 0
        ):
            raise NameBindingError("name_binding_invalid")

    @property
    def digest(self) -> str:
        return sha256(json.dumps(asdict(self), ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {**asdict(self), "binding_digest": self.digest}


def read_name_binding(metadata: dict | None) -> NameBindingSnapshot | None:
    """Absent namespace is legacy. An explicit but damaged namespace is an error."""
    if not metadata:
        return None
    if "name_binding" not in metadata:
        if "name_binding_policy" in metadata:
            raise NameBindingError("name_binding_missing")
        return None
    if metadata.get("name_binding_policy", NAME_BINDING_POLICY) != NAME_BINDING_POLICY:
        raise NameBindingError("name_binding_invalid")
    raw = metadata["name_binding"]
    if not isinstance(raw, dict):
        raise NameBindingError("name_binding_invalid")
    try:
        snapshot = NameBindingSnapshot(**{k: v for k, v in raw.items() if k != "binding_digest"})
    except (TypeError, ValueError) as exc:
        raise NameBindingError("name_binding_invalid") from exc
    if raw.get("binding_digest") != snapshot.digest:
        raise NameBindingError("name_binding_invalid")
    return snapshot
