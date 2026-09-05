"""Document chunk values and embedding credential material used by lore."""

from dataclasses import dataclass
from app.domains.character_lore.constants import EMBEDDING_MODEL


@dataclass(frozen=True)
class LoreChunkDraft:
    section_hint: str | None
    text: str
    content_hash: str


@dataclass(frozen=True)
class RetrievedLoreChunk:
    id: str
    source_id: str
    source_filename: str
    section_hint: str | None
    text: str
    distance: float


@dataclass(frozen=True)
class LoreRetrievalResult:
    mode: str
    chunks: tuple[RetrievedLoreChunk, ...] = ()
    error_message: str | None = None

    @property
    def chunk_ids(self) -> list[str]:
        return [chunk.id for chunk in self.chunks]


@dataclass(frozen=True)
class _GoogleEmbeddingCredential:
    api_key: str
    credential_id: str
    key_fingerprint: str | None
    provider: str
    model: str = EMBEDDING_MODEL
