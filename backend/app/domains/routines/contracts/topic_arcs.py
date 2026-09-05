"""The role value needed to validate an ordered TopicArc."""

from typing import Protocol


class TopicArcStepRole(Protocol):
    role: str
