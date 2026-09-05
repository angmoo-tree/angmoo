"""Stable routine context admission errors."""

class RoutineContextUnavailable(Exception):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)
