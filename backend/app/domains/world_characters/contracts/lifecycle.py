from typing import Protocol


class WorldCharacterLeaveRuntimeGuard(Protocol):
    def require_idle(
        self,
        *,
        owner_user_id: str,
        character_id: str,
        world_character_id: str,
        selected_active_world: bool,
    ) -> None: ...
