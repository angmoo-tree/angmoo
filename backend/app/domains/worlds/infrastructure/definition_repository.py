"""Exact import compatibility for the immutable SQLite v2->v3 migration.

The definitions are owned by app.domains.worlds.service.definition; this module has no implementation.
"""

from app.domains.worlds.service.definition import (
    WORLD_CONTRACT_VERSION,
    DAYPARTS,
    canonical_text,
    canonical_tags,
    load_definition_parts,
    canonical_world_definition,
    world_contract_hash,
    evaluate_world_readiness,
    refresh_world_contract,
    place_read,
    role_read,
    daypart_read,
    rule_read,
    glossary_read,
    world_read,
)

__all__ = [
    "WORLD_CONTRACT_VERSION",
    "DAYPARTS",
    "canonical_text",
    "canonical_tags",
    "load_definition_parts",
    "canonical_world_definition",
    "world_contract_hash",
    "evaluate_world_readiness",
    "refresh_world_contract",
    "place_read",
    "role_read",
    "daypart_read",
    "rule_read",
    "glossary_read",
    "world_read",
]
