"""First-greeting request, response and generated writer payload."""
from pydantic import BaseModel, Field

class AgentFirstGreetingCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)


class _FirstGreetingWriterPayload(BaseModel):
    post_title: str = Field(min_length=1, max_length=160)
    post_body: str = Field(min_length=1, max_length=4000)
    topic_signature: str = Field(min_length=1, max_length=300)
    persona_basis: str = Field(min_length=1, max_length=500)
    tendency_basis: str = Field(min_length=1, max_length=500)
