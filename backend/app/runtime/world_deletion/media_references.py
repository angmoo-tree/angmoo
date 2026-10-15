"""Reviewed managed-image references used by scoped World erasure.

Embedding `profile` strings are not image documents. New image-bearing fields
must be added here with their owning contract, never discovered by column name.
"""
import json

from sqlalchemy import JSON, String, case, cast, func, or_, select


DIRECT_REFERENCES = {
    "characters": ("avatar_url", "banner_url"),
    "agent_creation_drafts": ("avatar_temp_url", "banner_temp_url"),
    "profile_image_candidates": ("url",),
    "post_media": ("url",),
    "post_image_generation_jobs": ("media_url",),
    "worlds": ("icon_media_id", "banner_media_id"),
}
PROFILE_REFERENCES = {
    "world_characters": "local_profile",
    "world_character_configurations": "profile",
}
IMAGE_FIELDS = ("avatar_url", "banner_url")


class MediaReferenceContractError(ValueError):
    """Content-free, nonretryable preservation failure; no files may be removed."""


def validate_reference_contract(tables):
    for name, columns in DIRECT_REFERENCES.items():
        if name not in tables or any(
            key not in tables[name].c or not isinstance(tables[name].c[key].type, String)
            for key in columns
        ):
            raise MediaReferenceContractError("world_erasure_media_schema_invalid")
    for name, key in PROFILE_REFERENCES.items():
        if name not in tables or key not in tables[name].c or not isinstance(tables[name].c[key].type, JSON):
            raise MediaReferenceContractError("world_erasure_media_schema_invalid")


def candidate_match(column, candidates):
    return or_(*(column.like(
        "%/media/" + path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
        escape="\\",
    ) for path in candidates))


def profile_image_urls(db, tables, candidates):
    """SQL narrows the candidates; strict parsing and exact paths decide retention.

    CASE (not WHERE evaluation order) guards JSON functions. Invalid documents
    and invalid image field types are included so they fail closed, even when a
    malformed string cannot be searched for a candidate URL.
    """
    for name, key in PROFILE_REFERENCES.items():
        raw = cast(tables[name].c[key], String)
        valid = func.json_valid(raw) == 1
        kind = case((valid, func.json_type(raw)), else_="invalid")
        guards = [kind.not_in(("object", "null"))]
        for field in IMAGE_FIELDS:
            path = "$." + field
            field_kind = case((kind == "object", func.json_type(raw, path)))
            value = case((kind == "object", func.json_extract(raw, path)))
            guards.extend((field_kind.not_in(("text", "null")), candidate_match(value, candidates)))
        for value in db.scalars(select(raw).where(raw.is_not(None), or_(*guards))).yield_per(64):
            try:
                profile = json.loads(value)
            except (ValueError, TypeError) as exc:
                raise MediaReferenceContractError("world_erasure_media_profile_invalid") from exc
            if profile is None:
                continue
            if not isinstance(profile, dict) or any(
                profile.get(field) is not None and not isinstance(profile[field], str) for field in IMAGE_FIELDS
            ):
                raise MediaReferenceContractError("world_erasure_media_profile_invalid")
            yield from (profile[field] for field in IMAGE_FIELDS if profile.get(field))
