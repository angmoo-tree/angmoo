"""Swappable setup provider inputs and observable request accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.domains.identity.contracts import CredentialMaterial
from app.domains.world_characters.schemas import setup as schemas


@dataclass(frozen=True)
class WorldCharacterProviderResult:
    payload: Any
    physical_request_count: int
    prompt_token_count: int | None
    output_token_count: int | None
    total_token_count: int | None
    latency_ms: int | None

class WorldCharacterSetupProvider(Protocol):
    async def generate_community_profile(
        self,
        *,
        material: CredentialMaterial,
        character_id: str,
        generation_input: dict[str, Any],
    ) -> WorldCharacterProviderResult: ...

    async def generate_repertoire(
        self,
        *,
        material: CredentialMaterial,
        character_id: str,
        generation_input: dict[str, Any],
        community_profile: schemas.WorldCommunityProfilePayload,
        validator,
    ) -> WorldCharacterProviderResult: ...
