"""Safe metadata for authored auxiliary text, never provider reasoning or raw tails."""
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Literal

from app.contracts.activity_thought import ActivityThought, MAX_THOUGHT_CHARACTERS, parse_activity_thought

AUX_OUTPUT_POLICY = "authored-aux-output.v1"


@dataclass(frozen=True, slots=True)
class AuxiliaryNormalizationReceipt:
    field: str
    input_chars: int | None
    rendered_chars: int | None
    normalized_chars: int
    limit: int
    truncated: bool
    state: Literal["recorded", "missing", "invalid"]
    inherited: bool = False
    policy_version: str = AUX_OUTPUT_POLICY

    def __post_init__(self):
        if self.field not in {"thought", "topic_signature", "novelty_basis"} or self.policy_version != AUX_OUTPUT_POLICY:
            raise ValueError("auxiliary_receipt_policy_invalid")
        if self.state not in {"recorded", "missing", "invalid"}:
            raise ValueError("auxiliary_receipt_state_invalid")
        if any(type(v) is not int or v < 0 for v in (self.normalized_chars, self.limit)):
            raise ValueError("auxiliary_receipt_length_invalid")
        if any(v is not None and (type(v) is not int or v < 0) for v in (self.input_chars, self.rendered_chars)):
            raise ValueError("auxiliary_receipt_length_invalid")
        if self.normalized_chars > self.limit or type(self.truncated) is not bool or type(self.inherited) is not bool:
            raise ValueError("auxiliary_receipt_length_invalid")

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_auxiliary_text(value: object, *, field: str, limit: int,
                             input_chars: int | None = None) -> tuple[str, AuxiliaryNormalizationReceipt]:
    """The owner validates/render names first, then supplies its field's bound."""
    if not isinstance(value, str):
        return "", AuxiliaryNormalizationReceipt(field, None, None, 0, limit, False,
                                                  "missing" if value is None else "invalid")
    stripped = value.strip()
    text = stripped[:limit]
    return text, AuxiliaryNormalizationReceipt(field, len(value) if input_chars is None else input_chars,
        len(value), len(text), limit, len(stripped) > limit, "recorded" if stripped else "missing")


def finalize_activity_thought(value: object, *, render: Callable[[str], str] | None = None,
                              inherited: ActivityThought | None = None) -> tuple[ActivityThought, AuxiliaryNormalizationReceipt]:
    """Validate the entire raw thought, including a tail that will be discarded."""
    original_length = len(value) if isinstance(value, str) else None
    rendered = render(value) if render is not None and isinstance(value, str) else value
    thought = parse_activity_thought(rendered)
    _, receipt = normalize_auxiliary_text(rendered, field="thought", limit=MAX_THOUGHT_CHARACTERS, input_chars=original_length)
    if inherited is not None and inherited.truncated and thought.status == "recorded":
        thought = replace(thought, truncated=True)
        receipt = replace(receipt, truncated=True, inherited=True)
    return thought, receipt


def restore_activity_thought(value: dict) -> tuple[ActivityThought, AuxiliaryNormalizationReceipt]:
    """Trust only the saved state/true flag; do not invent the lost raw length."""
    raw = value.get("text") if value.get("status") == "recorded" else None
    thought, receipt = finalize_activity_thought(raw)
    if value.get("status") == "invalid":
        thought = ActivityThought(status="invalid")
        receipt = replace(receipt, state="invalid")
    if thought.status == "recorded" and value.get("truncated") is True:
        thought = replace(thought, truncated=True)
        receipt = replace(receipt, truncated=True)
    return thought, replace(receipt, input_chars=None, rendered_chars=None, inherited=True)
