from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CharacterLoreSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    character_id: str
    filename: str
    extension: str
    content_type: str | None = None
    file_size_bytes: int
    raw_text_hash: str
    extracted_char_count: int
    chunk_count: int
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class CharacterLoreStatusRead(BaseModel):
    character_id: str
    source_count: int
    ready_source_count: int
    chunk_count: int
    ready_chunk_count: int
    max_sources: int
    max_text_chars: int
    max_chunks: int
    max_file_bytes: int
