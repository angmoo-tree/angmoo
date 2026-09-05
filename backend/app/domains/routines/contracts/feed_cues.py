"""Identity-only inputs; callers keep their original attached objects."""
from typing import Protocol


class FeedCueIdentity(Protocol):
    @property
    def id(self) -> str: ...
