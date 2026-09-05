from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any, Mapping
import unicodedata

from pydantic import ValidationError

from app.domains.world_characters.contracts.setup import (
    CharacterGenerationRecord as Character,
    ValidatedActivityCandidate,
    ValidatedActivityRepertoire,
)
from app.domains.world_characters.exceptions import WorldCharacterContractError
from app.domains.world_characters.schemas import setup as schemas
from app.domains.world_characters import models
from app.domains.world_characters.models import WorldCharacter


CHARACTER_CONTRACT_VERSION = "p2-character-contract-v1"
WORLD_CHARACTER_GENERATOR_VERSION = "p2-world-character-generator-v1"
REPERTOIRE_SCHEMA_VERSION = 1
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.88
DAYPARTS = ("dawn", "morning", "afternoon", "evening")

_NON_WORD = re.compile(r"[^\w\s-]+", flags=re.UNICODE)


def _canonical_text(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").strip().split())


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_character_contract(character: Character) -> dict[str, Any]:
    """Return the stable, owner-safe Character identity used by P2 generation."""

    return {
        "contract_version": CHARACTER_CONTRACT_VERSION,
        "character_id": character.id,
        "name": _canonical_text(character.name),
        "one_liner": _canonical_text(character.one_liner),
        "personality": _canonical_text(character.personality),
        "speech_style": _canonical_text(character.speech_style),
        "worldview": _canonical_text(character.worldview),
        "topic_preferences": _canonical_text(character.topic_preferences),
        "safety_rules": _canonical_text(character.safety_rules),
        "persona_summary": _canonical_text(character.persona_summary),
    }


def character_contract_hash(character: Character) -> str:
    return canonical_sha256(build_character_contract(character))


def build_world_character_generation_input(
    *,
    character: Character,
    world_character: WorldCharacter,
    world_context: schemas.WorldGenerationContextRead,
    previous_candidate_signatures: list[str] | None = None,
    recent_execution_signatures: list[str] | None = None,
) -> dict[str, Any]:
    """Build the sanitized input shared by the two logical provider calls."""

    role = next(
        (item for item in world_context.roles if item.key == world_character.role_key),
        None,
    )
    return {
        "character": build_character_contract(character),
        "world": world_context.model_dump(mode="json"),
        "world_character": {
            "world_character_id": world_character.id,
            "role_key": world_character.role_key,
            "local_profile": _canonicalize_local_profile(
                world_character.local_profile or {}
            ),
            "role": role.model_dump(mode="json") if role is not None else None,
        },
        "recent_history": {
            "previous_candidate_signatures": sorted(
                set(previous_candidate_signatures or [])
            )[:80],
            "recent_execution_signatures": sorted(
                set(recent_execution_signatures or [])
            )[:40],
        },
    }


def _canonicalize_local_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = ("role_description", "background", "access_scope")
    result: dict[str, Any] = {}
    for key in allowed_keys:
        item = value.get(key)
        if isinstance(item, str):
            result[key] = _canonical_text(item)[:500]
        elif key == "access_scope" and isinstance(item, list):
            result[key] = sorted(
                {
                    _canonical_text(entry)[:120]
                    for entry in item
                    if isinstance(entry, str) and _canonical_text(entry)
                }
            )[:20]
    return result


def validate_community_profile(
    payload: Mapping[str, Any],
) -> schemas.WorldCommunityProfilePayload:
    try:
        return schemas.WorldCommunityProfilePayload.model_validate(payload)
    except ValidationError as exc:
        error_types = {item["type"] for item in exc.errors()}
        keyword_error = any(
            item["loc"] and item["loc"][0] == "search_keywords"
            for item in exc.errors()
        )
        reason_code = (
            "profile_keyword_count_invalid"
            if keyword_error
            else "profile_schema_invalid"
        )
        raise WorldCharacterContractError(
            reason_code,
            details={"validation_error_count": len(exc.errors()), "error_type_count": len(error_types)},
        ) from None


def canonical_candidate_signature(
    candidate: schemas.WorldActivityCandidatePayload,
) -> str:
    return canonical_sha256(
        {
            "activity_kind": candidate.activity_kind,
            "title": _comparison_text(candidate.title),
            "activity_seed": _comparison_text(candidate.activity_seed),
            "place_key": (candidate.place_key or "").casefold(),
            "social_mode": candidate.social_mode,
        }
    )


def validate_activity_repertoire(
    payload: Mapping[str, Any],
    *,
    world_context: schemas.WorldGenerationContextRead,
    world_character: models.WorldCharacter,
) -> ValidatedActivityRepertoire:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != 40:
        raise WorldCharacterContractError(
            "repertoire_count_invalid",
            details={
                "candidate_count": len(raw_candidates)
                if isinstance(raw_candidates, list)
                else 0
            },
        )
    try:
        parsed = schemas.WorldActivityRepertoirePayload.model_validate(payload)
    except ValidationError as exc:
        raise WorldCharacterContractError(
            "provider_response_invalid",
            details={"validation_error_count": len(exc.errors())},
        ) from None

    counts = Counter(item.daypart for item in parsed.candidates)
    if counts != Counter({daypart: 10 for daypart in DAYPARTS}):
        raise WorldCharacterContractError(
            "repertoire_daypart_invalid",
            details={daypart: counts.get(daypart, 0) for daypart in DAYPARTS},
        )

    places = {item.key: item for item in world_context.places}
    dayparts = {item.daypart: item for item in world_context.daypart_profiles}
    signatures: set[str] = set()
    comparison_documents: list[tuple[str, str]] = []
    clusters: Counter[tuple[str, str, str]] = Counter()
    kinds_by_daypart: dict[str, Counter[str]] = {
        daypart: Counter() for daypart in DAYPARTS
    }
    ordinals: Counter[str] = Counter()
    result: list[ValidatedActivityCandidate] = []

    for candidate in parsed.candidates:
        _validate_world_references(
            candidate,
            world_character=world_character,
            places=places,
            dayparts=dayparts,
            world_context=world_context,
        )
        signature = canonical_candidate_signature(candidate)
        if signature in signatures:
            raise WorldCharacterContractError("repertoire_duplicate")
        signatures.add(signature)
        comparison_documents.append(
            (candidate.daypart, _candidate_comparison_document(candidate))
        )
        clusters[_candidate_cluster(candidate)] += 1
        kinds_by_daypart[candidate.daypart][candidate.activity_kind] += 1
        ordinals[candidate.daypart] += 1
        result.append(
            ValidatedActivityCandidate(
                payload=candidate,
                ordinal=ordinals[candidate.daypart],
                canonical_signature=signature,
            )
        )

    oversized_clusters = sum(1 for count in clusters.values() if count > 2)
    if oversized_clusters:
        raise WorldCharacterContractError(
            "repertoire_duplicate",
            details={"oversized_cluster_count": oversized_clusters},
        )

    for daypart, kind_counts in kinds_by_daypart.items():
        if len(kind_counts) < 5 or max(kind_counts.values(), default=0) > 3:
            raise WorldCharacterContractError(
                "repertoire_diversity_invalid",
                details={
                    "daypart": daypart,
                    "distinct_kind_count": len(kind_counts),
                    "max_kind_count": max(kind_counts.values(), default=0),
                },
            )

    near_duplicate_pairs = 0
    for index, (left_daypart, left) in enumerate(comparison_documents):
        for right_daypart, right in comparison_documents[index + 1 :]:
            if left_daypart != right_daypart:
                continue
            if _character_ngram_jaccard(left, right) >= NEAR_DUPLICATE_JACCARD_THRESHOLD:
                near_duplicate_pairs += 1
    if near_duplicate_pairs:
        raise WorldCharacterContractError(
            "repertoire_duplicate",
            details={"near_duplicate_pair_count": near_duplicate_pairs},
        )

    return ValidatedActivityRepertoire(
        candidates=tuple(result),
        daypart_counts={daypart: counts[daypart] for daypart in DAYPARTS},
        near_duplicate_pair_count=0,
    )


def _validate_world_references(
    candidate: schemas.WorldActivityCandidatePayload,
    *,
    world_character: models.WorldCharacter,
    places: Mapping[str, schemas.WorldPlaceInput],
    dayparts: Mapping[str, schemas.WorldDaypartProfileInput],
    world_context: schemas.WorldGenerationContextRead,
) -> None:
    if candidate.place_key is not None:
        place = places.get(candidate.place_key)
        if place is None:
            raise WorldCharacterContractError("world_reference_invalid")
        if place.available_dayparts and candidate.daypart not in place.available_dayparts:
            raise WorldCharacterContractError("world_reference_invalid")
        if (
            place.access_role_keys
            and world_character.role_key not in place.access_role_keys
        ):
            raise WorldCharacterContractError("world_reference_invalid")

    daypart = dayparts.get(candidate.daypart)
    if daypart is not None:
        candidate_text = _candidate_comparison_document(candidate)
        restricted = {
            _comparison_text(item)
            for item in daypart.restricted_features
            if _comparison_text(item)
        }
        if any(item in candidate_text for item in restricted):
            raise WorldCharacterContractError("world_rule_conflict")

    candidate_text = _candidate_comparison_document(candidate)
    for rule in world_context.rules:
        if rule.rule_kind != "forbid":
            continue
        forbidden = _comparison_text(rule.description)
        if forbidden and len(forbidden) >= 4 and forbidden in candidate_text:
            raise WorldCharacterContractError("world_rule_conflict")


def _comparison_text(value: str) -> str:
    normalized = _canonical_text(value).casefold()
    return " ".join(_NON_WORD.sub(" ", normalized).split())


def _candidate_comparison_document(
    candidate: schemas.WorldActivityCandidatePayload,
) -> str:
    return " ".join(
        filter(
            None,
            (
                _comparison_text(candidate.title),
                _comparison_text(candidate.activity_seed),
                candidate.activity_kind,
                (candidate.place_key or "").casefold(),
                candidate.social_mode,
            ),
        )
    )


def _candidate_cluster(
    candidate: schemas.WorldActivityCandidatePayload,
) -> tuple[str, str, str]:
    title_tokens = _comparison_text(candidate.title).split()
    seed_tokens = _comparison_text(candidate.activity_seed).split()
    return (
        candidate.activity_kind,
        " ".join(title_tokens[:2]),
        " ".join(seed_tokens[:3]),
    )


def _character_ngrams(value: str, size: int = 3) -> set[str]:
    compact = value.replace(" ", "")
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _character_ngram_jaccard(left: str, right: str) -> float:
    left_grams = _character_ngrams(left)
    right_grams = _character_ngrams(right)
    union = left_grams | right_grams
    if not union:
        return 1.0
    return len(left_grams & right_grams) / len(union)
