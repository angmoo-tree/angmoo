from dataclasses import dataclass

class LocalBotError(Exception):
    pass

class LocalBotAuthError(LocalBotError):
    pass

class LocalBotForbiddenError(LocalBotError):
    pass

class LocalBotModeError(LocalBotError):
    pass

class LocalBotRateLimitError(LocalBotError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

@dataclass(frozen=True)
class QuotaExceeded(Exception):
    label: str
    message: str
    retry_after_seconds: int

    def __str__(self) -> str:
        return self.message
