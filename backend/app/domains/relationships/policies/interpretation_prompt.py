"""Small shared output contract, never an extra relationship model call."""

from copy import deepcopy

METRIC_INSTRUCTIONS = """
Assess how the character receives the counterpart's actually observed words and
actions using the persona, existing relationship, supplied memories and context.
Express affinity, trust and tension as increase/keep/decrease. Greetings,
acknowledgements, repetition and insufficient evidence mean keep. A trust change
requires specific new evidence of reliability. Your intended reply, unexecuted
actions and a counterpart's hidden intent are not evidence of relationship change.
Previously judged events shown again as context do not create another change.
Do not assign numeric scores, familiarity, relationship labels or perception here.
Return only counterparts with meaningful changes in relationship_metrics; otherwise [].
Use only supplied target and new_evidence_refs. Do not expose this side result to users.
"""


def with_metric_schema(schema: dict) -> dict:
    result = deepcopy(schema)
    result.setdefault("properties", {})["relationship_metrics"] = {
        "type": "array", "items": {"type": "object", "properties": {
            "target_ref": {"type": "string"},
            **{axis: {"type": "string", "enum": ["increase", "keep", "decrease"]}
               for axis in ("affinity", "trust", "tension")},
            "new_evidence_refs": {"type": "array", "items": {"type": "string"}},
        }, "required": ["target_ref", "affinity", "trust", "tension", "new_evidence_refs"]}}
    result["required"] = [*result.get("required", []), "relationship_metrics"]
    return result
