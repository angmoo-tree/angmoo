"""Device Home errors; router.py owns their HTTP representation."""


class LocalOwnerRequiredError(PermissionError):
    reason_code = "local_owner_required"


class InvalidWorldSurfaceCursorError(ValueError):
    reason_code = "invalid_world_surface_cursor"


class WorldAppUnavailableError(LookupError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
