"""The HTTP first-greeting result combines the run and its Social post."""
from datetime import datetime
from app.domains.routines.schemas.runs import UtcInstantResponseModel
from app.domains.social.schemas.community import PostDetail


class AgentFirstGreetingRead(UtcInstantResponseModel):
    run_id: str
    status: str
    summary: str | None = None
    character_id: str
    post_id: str | None = None
    post: PostDetail | None = None
    image_attempt: dict | None = None
    first_greeting_available_at: datetime | None = None
    gateway_result: dict
