"""Committed request pairing for episode input, independent of Memory storage."""

from dataclasses import dataclass
from datetime import datetime

from app.contracts.activity_thought import ActivityThought


@dataclass(frozen=True, slots=True)
class CommittedMemoryTurn:
    request_id: str
    thread_id: str
    user_message_id: int
    user_text: str
    assistant_message_id: int
    assistant_text: str
    occurred_at: datetime
    thought: ActivityThought
    thought_recorded: bool
