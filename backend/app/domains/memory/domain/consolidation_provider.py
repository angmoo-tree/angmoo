"""Strict output contract for the optional Memory consolidation provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domains.memory.domain.consolidation import (
    MAX_MAINTENANCE_BATCH_CANDIDATES,
    validate_consolidation_summary,
)
from app.domains.memory.domain.errors import MemoryValidationError


MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION = "memory-consolidation-output.v1"


@dataclass(frozen=True, slots=True)
class MemorySummaryProposal:
    candidate_ref: str
    summary: str


def memory_consolidation_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "proposals"],
        "properties": {
            "version": {
                "type": "string",
                "enum": [MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION],
            },
            "proposals": {
                "type": "array",
                "maxItems": MAX_MAINTENANCE_BATCH_CANDIDATES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_ref", "summary"],
                    "properties": {
                        "candidate_ref": {"type": "string", "maxLength": 40},
                        "summary": {"type": "string", "maxLength": 2_000},
                    },
                },
            },
        },
    }


def parse_memory_consolidation_payload(
    payload: dict[str, Any],
) -> tuple[MemorySummaryProposal, ...]:
    if set(payload) != {"version", "proposals"}:
        raise MemoryValidationError("memory_consolidation_output_shape_invalid")
    if payload.get("version") != MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION:
        raise MemoryValidationError("memory_consolidation_output_version_invalid")
    raw_proposals = payload.get("proposals")
    if not isinstance(raw_proposals, list) or len(raw_proposals) > MAX_MAINTENANCE_BATCH_CANDIDATES:
        raise MemoryValidationError("memory_consolidation_proposals_invalid")
    proposals: list[MemorySummaryProposal] = []
    seen: set[str] = set()
    for raw in raw_proposals:
        if not isinstance(raw, dict) or set(raw) != {"candidate_ref", "summary"}:
            raise MemoryValidationError("memory_consolidation_proposal_shape_invalid")
        candidate_ref = raw.get("candidate_ref")
        summary = raw.get("summary")
        if (
            not isinstance(candidate_ref, str)
            or not candidate_ref.startswith("candidate-")
            or len(candidate_ref) > 40
            or candidate_ref in seen
            or not isinstance(summary, str)
        ):
            raise MemoryValidationError("memory_consolidation_proposal_invalid")
        seen.add(candidate_ref)
        proposals.append(
            MemorySummaryProposal(
                candidate_ref=candidate_ref,
                summary=validate_consolidation_summary(summary),
            )
        )
    return tuple(proposals)


__all__ = [
    "MEMORY_CONSOLIDATION_PROVIDER_OUTPUT_VERSION",
    "MemorySummaryProposal",
    "memory_consolidation_response_schema",
    "parse_memory_consolidation_payload",
]
