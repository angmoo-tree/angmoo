"""Bounded query construction; scope is never supplied by a language model."""
import re

from app.runtime.autonomous_activity.contracts import (
    AI_QUERY_CHARS, NATURAL_QUERY_CHARS, Candidate, ResolvedQuery, Selection, SelectionOutput,
)


def compact(value: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= limit:
        return normalized
    sentences = re.split(r"(?<=[.!?。！？])\s+", normalized)
    kept = []
    for sentence in sentences:
        if len(" ".join([*kept, sentence])) > limit:
            break
        kept.append(sentence)
    return " ".join(kept)


def validate_selection(payload: dict, candidates: list[Candidate], limit: int) -> list[Selection]:
    parsed = SelectionOutput.model_validate(payload).selections
    ids = [item.target_id for item in parsed]
    if len(ids) > limit or len(ids) != len(set(ids)) or not set(ids) <= {c.target_id for c in candidates}:
        raise ValueError("selection_target_invalid")
    return parsed


def resolve_query(selection: Selection, candidate: Candidate, *, lane: str) -> ResolvedQuery:
    value = selection.memory_query
    if isinstance(value, str) and value.strip() and len(value.strip()) <= AI_QUERY_CHARS:
        return ResolvedQuery(target_id=candidate.target_id, query=compact(value, AI_QUERY_CHARS), origin="selector")
    if lane == "feed":
        material = (candidate.topic_signature or "").strip() or candidate.text
    else:
        # Current utterance first; a long parent must not displace it.
        material = compact(candidate.text, 600) + " " + compact(candidate.parent_text, 200)
    return ResolvedQuery(target_id=candidate.target_id, query=compact(material, NATURAL_QUERY_CHARS), origin="natural",
        fallback_reason="selector_bypassed" if value is None else "invalid_query")


def routine_query(*, title: str, activity_seed: str, previous: dict | None) -> ResolvedQuery:
    """previous is the backend-verified last successful post in this episode."""
    if previous is None:
        material = title + " " + activity_seed
    else:
        signature = previous.get("topic_signature")
        scene = signature.strip() if isinstance(signature, str) and signature.strip() else (
            str(previous.get("title") or "") + " " + str(previous.get("body") or "")
        )
        scene = compact(scene, max(0, NATURAL_QUERY_CHARS - len(title) - 1))
        material = scene + " " + title
    return ResolvedQuery(target_id="routine", query=compact(material, NATURAL_QUERY_CHARS), origin="routine")
