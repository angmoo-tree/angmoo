"""Independent Memory embedding profile; credentials never affect vector identity."""
from dataclasses import dataclass
import hashlib

EMBEDDING_PROVIDER = "google"
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_REVISION = "memory-summary.v1"
EMBEDDING_PROFILE = hashlib.sha256(
    b"google/gemini-embedding-2/768/float32/cosine/task-search-result/title-memory/identity.v1"
).hexdigest()


def embedding_text(text: str, *, query: bool) -> str:
    # Keep the complete accepted summary; dimension is not an input length cap.
    if not text.strip():
        raise ValueError("memory_embedding_input_empty")
    return f"task: search result | query: {text}" if query else f"title: Memory | text: {text}"


@dataclass(frozen=True, slots=True)
class MemoryEmbeddingConfiguration:
    enabled: bool = False
    provider: str = EMBEDDING_PROVIDER
    model: str = EMBEDDING_MODEL
    credential_id: str | None = None
    profile: str = EMBEDDING_PROFILE
    version: int = 0

