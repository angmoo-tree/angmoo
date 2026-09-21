"""One subject, one counterpart, full saved memories and bounded results."""

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True, slots=True)
class ReviewMemory:
    memory_id: str
    summary: str
    source_refs: tuple[str, ...]
    digest: str
    occurred_at: str

    def __post_init__(self):
        if not self.memory_id or not self.summary.strip() or len(self.summary) > 2000 or len(self.digest) != 64:
            raise ValueError("relationship_review_memory_invalid")

    def payload(self) -> dict:
        return {"memory_id": self.memory_id, "summary": self.summary,
                "source_refs": list(self.source_refs), "digest": self.digest,
                "occurred_at": self.occurred_at}


def manifest_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def validate_review_result(value: object, *, partial: bool, allowed_refs: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError("relationship_review_result_invalid")
    refs = value.get("memory_refs")
    if not isinstance(refs, list) or len(refs) > 64 or any(not isinstance(ref, str) or ref not in allowed_refs for ref in refs):
        raise ValueError("relationship_review_result_refs_invalid")
    if partial:
        findings = value.get("findings")
        if not isinstance(findings, list) or len(findings) > 12 or any(not isinstance(v, str) or not v.strip() or len(v) > 300 for v in findings):
            raise ValueError("relationship_review_findings_invalid")
        uncertainty = value.get("uncertainty", "")
        if not isinstance(uncertainty, str) or len(uncertainty) > 300:
            raise ValueError("relationship_review_uncertainty_invalid")
        return {"findings": findings, "uncertainty": uncertainty, "memory_refs": list(dict.fromkeys(refs))}
    decision = value.get("decision")
    if decision not in {"keep", "update"}:
        raise ValueError("relationship_review_decision_invalid")
    if decision == "keep":
        return {"decision": "keep", "memory_refs": list(dict.fromkeys(refs))}
    label, perception = value.get("relationship_label"), value.get("perception")
    if (not isinstance(label, str) or not 1 <= len(label.strip()) <= 32
        or not isinstance(perception, str) or not 1 <= len(perception.strip()) <= 300
        or not refs):
        raise ValueError("relationship_review_view_invalid")
    return {"decision": "update", "relationship_label": label.strip(),
            "perception": perception.strip(), "memory_refs": list(dict.fromkeys(refs))}


class ReviewNeedsSplit(ValueError):
    """Provider could not complete a bounded result; divide the same target."""
