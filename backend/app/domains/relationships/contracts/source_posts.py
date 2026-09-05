"""Already-persisted source fields used by the audit-only event writer."""
from typing import Protocol
from app.domains.relationships.contracts.events import EventPost


class SourceEventPost(EventPost, Protocol):
    @property
    def id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def body(self) -> str: ...
