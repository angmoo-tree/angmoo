"""Shared action vocabulary used by planning and successful social observations.

Storage, provenance, and subjective text policy belong to Social.
"""

from enum import StrEnum


class ActionMotivationKind(StrEnum):
    SELF_EXPRESSION = "self_expression"
    SHARE_INFORMATION = "share_information"
    CONTINUE_TOPIC = "continue_topic"
    ANSWER_QUESTION = "answer_question"
    ENCOURAGE_COUNTERPART = "encourage_counterpart"
    EMPATHIZE = "empathize"
    DISAGREE_OR_CORRECT = "disagree_or_correct"
    RELATIONSHIP_MAINTENANCE = "relationship_maintenance"
    CURIOSITY = "curiosity"
    RECIPROCATE = "reciprocate"
    OTHER_DECLARED = "other_declared"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)


class ActionEmotionLabel(StrEnum):
    NEUTRAL = "neutral"
    INTERESTED = "interested"
    JOYFUL = "joyful"
    AFFECTIONATE = "affectionate"
    CONCERNED = "concerned"
    SURPRISED = "surprised"
    SAD = "sad"
    ANGRY = "angry"
    TENSE = "tense"
    EMBARRASSED = "embarrassed"
    PROUD = "proud"
    RELIEVED = "relieved"
    MIXED = "mixed"
    UNSPECIFIED = "unspecified"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)
