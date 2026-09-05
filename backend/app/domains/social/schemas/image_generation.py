"""Structured output validation for Social image identity and scene prompts."""
from pydantic import BaseModel, Field


class _VisualIdentityPayload(BaseModel):
    usable_identity: bool = True
    identity_prompt: str = Field(default="", max_length=1200)
    reason: str | None = Field(default=None, max_length=300)



class _ImagePromptPayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=1800)
    alt_text: str = Field(min_length=1, max_length=240)
