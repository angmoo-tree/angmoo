"""The existing run retry decision, independent of a provider response object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RuntimeBackoff:
    kind: str
    message: str
    retry_at: datetime
    repeated_overload: bool = False
