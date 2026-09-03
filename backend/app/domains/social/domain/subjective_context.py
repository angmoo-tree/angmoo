"""Versioned, public-safe subjective context for one successful SNS action.

This contract deliberately stores a Character's short declared explanation,
not chain-of-thought, provider payloads, or a later inference from post text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


ACTION_SUBJECTIVE_CONTEXT_VERSION = "social-action-subjective-context.v1"
MAX_SUBJECTIVE_TEXT_CHARS = 280


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


class SubjectiveContextProvenance(StrEnum):
    DECLARED_AT_ACTION_DECISION = "declared_at_action_decision"


class SubjectiveContextContractError(ValueError):
    """Stable fail-closed error for unsafe subjective payloads."""


@dataclass(frozen=True, slots=True)
class ActionSubjectiveContextV1:
    motivation_kind: ActionMotivationKind
    motivation_text: str
    emotion_label: ActionEmotionLabel = ActionEmotionLabel.UNSPECIFIED
    emotion_text: str | None = None
    emotion_intensity: int | None = None
    provenance_kind: SubjectiveContextProvenance = (
        SubjectiveContextProvenance.DECLARED_AT_ACTION_DECISION
    )
    version: str = ACTION_SUBJECTIVE_CONTEXT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.motivation_kind, ActionMotivationKind) or not isinstance(self.emotion_label, ActionEmotionLabel) or not isinstance(self.provenance_kind, SubjectiveContextProvenance):
            raise SubjectiveContextContractError("subjective_context_catalog_invalid")
        if self.version != ACTION_SUBJECTIVE_CONTEXT_VERSION:
            raise SubjectiveContextContractError(
                "subjective_context_version_mismatch"
            )
        motivation = " ".join(self.motivation_text.split())
        if not motivation or len(motivation) > MAX_SUBJECTIVE_TEXT_CHARS:
            raise SubjectiveContextContractError(
                "subjective_context_motivation_invalid"
            )
        if self.emotion_text is not None:
            emotion = " ".join(self.emotion_text.split())
            if not emotion or len(emotion) > MAX_SUBJECTIVE_TEXT_CHARS:
                raise SubjectiveContextContractError(
                    "subjective_context_emotion_invalid"
                )
        if self.emotion_intensity is not None and (
            type(self.emotion_intensity) is not int or not 0 <= self.emotion_intensity <= 100
        ):
            raise SubjectiveContextContractError(
                "subjective_context_emotion_intensity_invalid"
            )
        if self.emotion_label is ActionEmotionLabel.UNSPECIFIED and (
            self.emotion_text is not None or self.emotion_intensity is not None
        ):
            raise SubjectiveContextContractError(
                "subjective_context_unspecified_emotion_detail_forbidden"
            )

    @property
    def normalized_motivation_text(self) -> str:
        return " ".join(self.motivation_text.split())

    @property
    def normalized_emotion_text(self) -> str | None:
        if self.emotion_text is None:
            return None
        return " ".join(self.emotion_text.split())


__all__ = [
    "ACTION_SUBJECTIVE_CONTEXT_VERSION",
    "MAX_SUBJECTIVE_TEXT_CHARS",
    "ActionEmotionLabel",
    "ActionMotivationKind",
    "ActionSubjectiveContextV1",
    "SubjectiveContextContractError",
    "SubjectiveContextProvenance",
]
