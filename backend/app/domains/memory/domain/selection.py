"""Strict retain/skip proposals; no authority or canonical IDs in model output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domains.memory.domain.batch_policy import (
    MAX_SELECTION_CANDIDATES,
    MAX_SELECTION_SUMMARY_CHARACTERS,
    MEMORY_SELECTION_VERSION,
)
from app.domains.memory.domain.errors import MemoryValidationError


RETAIN_REASONS = (
    "meaningful_experience",
    "commitment",
    "preference",
    "relationship_change",
)
SKIP_REASONS = ("routine_low_salience", "redundant_experience")


@dataclass(frozen=True, slots=True)
class MemorySelectionSource:
    candidate_ref: str
    evidence_ref: str
    memory_kind: str
    text: str
    subjective_context: str | None = None
    text_scope: str = "bounded_canonical_excerpt"


@dataclass(frozen=True, slots=True)
class MemorySelectionDecision:
    candidate_ref: str
    decision: str
    reason_code: str
    summary: str | None


def selection_response_schema() -> dict[str, Any]:
    memory = {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": ["summary", "evidence_refs", "subjective_context_refs"],
        "properties": {
            "summary": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_SELECTION_SUMMARY_CHARACTERS,
            },
            "evidence_refs": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {"type": "string"},
            },
            "subjective_context_refs": {
                "type": "array",
                "maxItems": 1,
                "items": {"type": "string"},
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "batch_ref", "decisions"],
        "properties": {
            "version": {"type": "string", "enum": [MEMORY_SELECTION_VERSION]},
            "batch_ref": {"type": "string", "enum": ["batch-1"]},
            "decisions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_SELECTION_CANDIDATES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_ref", "decision", "reason_code", "memory"],
                    "properties": {
                        "candidate_ref": {"type": "string", "maxLength": 40},
                        "decision": {"type": "string", "enum": ["retain", "skip"]},
                        "reason_code": {
                            "type": "string",
                            "enum": [*RETAIN_REASONS, *SKIP_REASONS],
                        },
                        "memory": memory,
                    },
                },
            },
        },
    }


def parse_selection(
    payload: Any,
    *,
    sources: tuple[MemorySelectionSource, ...],
) -> tuple[MemorySelectionDecision, ...]:
    def reject() -> None:
        raise MemoryValidationError("memory_selection_output_invalid")

    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "batch_ref",
        "decisions",
    }:
        reject()
    if (
        payload["version"] != MEMORY_SELECTION_VERSION
        or payload["batch_ref"] != "batch-1"
    ):
        reject()
    rows = payload["decisions"]
    allowed = {source.candidate_ref: source for source in sources}
    if not 1 <= len(allowed) <= MAX_SELECTION_CANDIDATES or len(allowed) != len(
        sources
    ):
        reject()
    if not isinstance(rows, list) or len(rows) != len(sources):
        reject()
    result: list[MemorySelectionDecision] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "candidate_ref",
            "decision",
            "reason_code",
            "memory",
        }:
            reject()
        ref = row["candidate_ref"]
        if not isinstance(ref, str) or ref not in allowed or ref in seen:
            reject()
        seen.add(ref)
        summary = None
        memory = row["memory"]
        if row["decision"] == "retain":
            if row["reason_code"] not in RETAIN_REASONS:
                reject()
            if not isinstance(memory, dict) or set(memory) != {
                "summary",
                "evidence_refs",
                "subjective_context_refs",
            }:
                reject()
            summary = memory["summary"]
            if (
                not isinstance(summary, str)
                or not 1 <= len(summary.strip()) <= MAX_SELECTION_SUMMARY_CHARACTERS
            ):
                reject()
            if memory["evidence_refs"] != [allowed[ref].evidence_ref]:
                reject()
            expected_subjective = (
                [f"{allowed[ref].evidence_ref}.subjective"]
                if allowed[ref].subjective_context
                else []
            )
            if memory["subjective_context_refs"] not in ([], expected_subjective):
                reject()
            summary = summary.strip()
        elif row["decision"] == "skip":
            if row["reason_code"] not in SKIP_REASONS or memory is not None:
                reject()
        else:
            reject()
        result.append(
            MemorySelectionDecision(ref, row["decision"], row["reason_code"], summary)
        )
    return tuple(result)
