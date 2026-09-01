"""SQLAlchemy persistence models for Chat v1 compatibility and World Chat v2."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domains.chat.domain.generation_lifecycle import (
    ResponseRequestState,
    ResponseTerminalReason,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.domain.workflow_recipe import WorkflowRecipe


def _sql_values(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


RESPONSE_REQUEST_SCHEMA_TABLES = ("chat_response_requests",)


class CharacterMessageSetting(Base):
    __tablename__ = "character_message_settings"

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship()


class UserMessagePreference(Base):
    __tablename__ = "user_message_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    credential_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="message_key"
    )
    source_character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    default_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gemini-2.5-flash-lite"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()
    source_character: Mapped[Optional["Character"]] = relationship()


class MessageThread(Base):
    __tablename__ = "message_threads"
    __table_args__ = (
        CheckConstraint(
            "(response_lease_token IS NULL) = "
            "(response_lease_expires_at IS NULL)",
            name="ck_message_threads_response_lease_pair",
        ),
        CheckConstraint(
            "(world_scope_status = 'resolved' AND world_id IS NOT NULL "
            "AND requester_world_character_id IS NOT NULL "
            "AND responding_world_character_id IS NOT NULL "
            "AND requester_world_character_id <> responding_world_character_id) OR "
            "(world_scope_status IN ('ambiguous', 'quarantined') "
            "AND world_id IS NULL "
            "AND requester_world_character_id IS NULL "
            "AND responding_world_character_id IS NULL)",
            name="ck_message_threads_world_scope_binding",
        ),
        ForeignKeyConstraint(
            ["requester_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_requester_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_responding_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_message_threads_responding_character",
        ),
        Index(
            "uq_message_threads_active_world_roles",
            "requester_id",
            "world_id",
            "requester_world_character_id",
            "responding_world_character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
        ),
        Index(
            "uq_message_threads_active_legacy_ambiguous",
            "requester_id",
            "character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
        ),
        Index(
            "ix_message_threads_owner_world_status",
            "requester_id",
            "world_id",
            "world_scope_status",
        ),
        Index(
            "ix_message_threads_requester_last",
            "requester_id",
            "last_message_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    world_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("worlds.id", name="fk_message_threads_world"), nullable=True
    )
    requester_world_character_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    responding_world_character_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    world_scope_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ambiguous", server_default="ambiguous"
    )
    selected_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gemini-2.5-flash-lite"
    )
    response_lease_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    response_lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requester: Mapped["User"] = relationship()
    character: Mapped["Character"] = relationship()
    messages: Mapped[list["MessageMessage"]] = relationship(
        back_populates="thread", order_by="MessageMessage.created_at"
    )


class MessageMessage(Base):
    __tablename__ = "message_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("message_threads.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    error_code: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    thread: Mapped[MessageThread] = relationship(back_populates="messages")


class ChatResponseRequest(Base):
    """One durable attempt for one stored user message response slot."""

    __tablename__ = "chat_response_requests"
    __table_args__ = (
        CheckConstraint(
            f"state IN ({_sql_values(tuple(state.value for state in ResponseRequestState))})",
            name="ck_chat_response_requests_state",
        ),
        CheckConstraint(
            "route IS NULL OR route IN "
            f"({_sql_values(tuple(route.value for route in RetrievalRoute))})",
            name="ck_chat_response_requests_route",
        ),
        CheckConstraint(
            "workflow_recipe IS NULL OR workflow_recipe IN "
            f"({_sql_values(tuple(recipe.value for recipe in WorkflowRecipe))})",
            name="ck_chat_response_requests_workflow_recipe",
        ),
        CheckConstraint(
            "terminal_reason IS NULL OR terminal_reason IN "
            f"({_sql_values(tuple(reason.value for reason in ResponseTerminalReason))})",
            name="ck_chat_response_requests_terminal_reason",
        ),
        CheckConstraint(
            "length(request_scope_hash) = 64",
            name="ck_chat_response_requests_scope_hash",
        ),
        CheckConstraint(
            "attempt_number >= 1 AND lease_generation >= 0 "
            "AND last_emitted_sequence >= -1",
            name="ck_chat_response_requests_counters",
        ),
        CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)",
            name="ck_chat_response_requests_lease_pair",
        ),
        CheckConstraint(
            "(state = 'committed' AND terminal_reason = 'committed' "
            "AND terminal_at IS NOT NULL "
            "AND committed_assistant_message_id IS NOT NULL "
            "AND lease_token IS NULL) OR "
            "(state IN ('rejected','cancelled','timed_out','failed','orphaned') "
            "AND terminal_reason IS NOT NULL AND terminal_at IS NOT NULL "
            "AND committed_assistant_message_id IS NULL AND lease_token IS NULL) OR "
            "(state NOT IN ('committed','rejected','cancelled','timed_out','failed','orphaned') "
            "AND terminal_reason IS NULL AND terminal_at IS NULL "
            "AND committed_assistant_message_id IS NULL)",
            name="ck_chat_response_requests_terminal_shape",
        ),
        UniqueConstraint(
            "thread_id",
            "idempotency_key",
            name="uq_chat_response_requests_thread_idempotency",
        ),
        UniqueConstraint(
            "response_slot_id",
            "attempt_number",
            name="uq_chat_response_requests_slot_attempt",
        ),
        Index(
            "ix_chat_response_requests_thread_created",
            "thread_id",
            "created_at",
        ),
        Index(
            "ix_chat_response_requests_active_lease",
            "state",
            "lease_expires_at",
        ),
        Index(
            "ix_chat_response_requests_user_message_attempt",
            "user_message_id",
            "attempt_number",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("message_threads.id"), nullable=False
    )
    user_message_id: Mapped[int] = mapped_column(
        ForeignKey("message_messages.id"), nullable=False
    )
    response_slot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    generation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_of_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_response_requests.request_id")
    )
    selected_model: Mapped[str] = mapped_column(String(120), nullable=False)
    route: Mapped[str | None] = mapped_column(String(32))
    workflow_recipe: Mapped[str | None] = mapped_column(String(40))
    lease_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResponseRequestState.ACCEPTED.value,
        server_default=ResponseRequestState.ACCEPTED.value,
    )
    last_emitted_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=-1, server_default="-1"
    )
    terminal_reason: Mapped[str | None] = mapped_column(String(48))
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    committed_assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("message_messages.id")
    )
    node_state_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    call_tracker_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    response_metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def create_response_request_schema(connection: Connection) -> None:
    Base.metadata.create_all(
        connection,
        tables=[Base.metadata.tables[name] for name in RESPONSE_REQUEST_SCHEMA_TABLES],
        checkfirst=False,
    )


def drop_response_request_schema(connection: Connection) -> None:
    Base.metadata.drop_all(
        connection,
        tables=[
            Base.metadata.tables[name]
            for name in reversed(RESPONSE_REQUEST_SCHEMA_TABLES)
        ],
        checkfirst=False,
    )


__all__ = [
    "RESPONSE_REQUEST_SCHEMA_TABLES",
    "CharacterMessageSetting",
    "ChatResponseRequest",
    "MessageMessage",
    "MessageThread",
    "UserMessagePreference",
    "create_response_request_schema",
    "drop_response_request_schema",
]
