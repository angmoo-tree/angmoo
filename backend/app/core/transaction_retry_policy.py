"""Shared bounded transaction retry budget, independent of database adapters."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SqliteRetryPolicy:
    max_attempts: int = 4
    initial_delay_seconds: float = 0.01
    maximum_delay_seconds: float = 0.05
    maximum_elapsed_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must not be negative")
        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError("maximum_delay_seconds is smaller than the initial delay")
        if self.maximum_elapsed_seconds <= 0:
            raise ValueError("maximum_elapsed_seconds must be positive")
