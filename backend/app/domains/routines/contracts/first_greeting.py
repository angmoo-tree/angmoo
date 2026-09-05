"""Same-session owners, credential transport and provider IO for first greeting."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Protocol, TypeVar, Generic
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.schemas.first_greeting import _FirstGreetingWriterPayload
from app.domains.routines.contracts.activity_management import ActivityOwner, TendencyPersona
from app.domains.routines.contracts.autonomy_management import AutonomyCredential
from app.domains.routines.contracts.manual_activity import ImportedWorldGuard
from app.domains.routines.contracts.feed_cues import FeedCuePolicy

ResultT = TypeVar("ResultT")
ResultT_co = TypeVar("ResultT_co", covariant=True)

class GreetingPostValue(Protocol):
    id: str
    title: str
    body: str

class GreetingPostInput(Protocol):
    title: str
    body: str
    author_character_id: str | None

class GreetingPostInputFactory(Protocol):
    def __call__(self, *, title: str, body: str, author_character_id: str) -> GreetingPostInput: ...

class GreetingResponse(Protocol[ResultT_co]):
    def __call__(self, *, run_id: str, status: str, summary: str | None, character_id: str, post_id: str, post: GreetingPostValue, image_attempt: dict[str, Any] | None, first_greeting_available_at: datetime | None, gateway_result: dict[str, Any]) -> ResultT_co: ...

class GreetingTracker(Protocol):
    def summary(self) -> dict[str, Any]: ...

class GreetingKey(Protocol):
    def __call__(self, credential: AutonomyCredential | None, *, user: ActivityOwner, character: TendencyPersona) -> str: ...

class GreetingWriter(Protocol):
    def __call__(self, *, api_key: str, character: TendencyPersona, setting: models.AgentActivitySetting, credential: AutonomyCredential | None, run_id: str, tracker: GreetingTracker, topic: str) -> Awaitable[_FirstGreetingWriterPayload]: ...

class GreetingPost(Protocol):
    def __call__(self, db: Session, user: ActivityOwner, data: GreetingPostInput, *, log_manual_activity: bool) -> GreetingPostValue: ...

class GreetingResult(Protocol):
    def __call__(self, *, post_id: str, title: str, body: str, topic_signature: str, novelty_basis: str, message: str) -> str: ...

class GreetingImage(Protocol):
    def __call__(self, *, db: Session, character: TendencyPersona, credential: AutonomyCredential | None, run_id: str, tracker: GreetingTracker, topic: str, post: GreetingPostValue) -> Awaitable[dict[str, Any] | None]: ...

@dataclass(frozen=True)
class FirstGreetingWorkflows(Generic[ResultT]):
    get_owned_character: Callable[[Session, ActivityOwner, str], TendencyPersona]
    ensure_not_suspended: Callable[[TendencyPersona], None]
    ensure_llm_mode: Callable[[TendencyPersona], None]
    ensure_imported_world_runtime_enabled: ImportedWorldGuard
    ensure_run_now_available: Callable[[Session], None]
    build_activity_policy: FeedCuePolicy
    has_authored_post: Callable[[Session, str], bool]
    get_credential: Callable[[Session, str], AutonomyCredential | None]
    resolve_key: GreetingKey
    new_tracker: Callable[[], GreetingTracker]
    _run_first_greeting_writer: GreetingWriter
    post_input: GreetingPostInputFactory
    build_response: GreetingResponse[ResultT]
    create_post: GreetingPost
    build_post_created_activity_result: GreetingResult
    attach_image: GreetingImage
    get_post: Callable[[Session, str], GreetingPostValue]
    deferred_error: type[Exception]
