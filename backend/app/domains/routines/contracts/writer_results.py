"""Existing values and pure result converters used by resident writers."""

from collections.abc import Callable
from typing import Any, Protocol

from app.domains.routines.contracts.prompt_context import StatePromptView


class WriterTaskContext(Protocol):
    run_id: str


class SavedStateContext(Protocol):
    state: StatePromptView | None


JsonContextBuilder = Callable[[Any], dict[str, Any] | None]
ValidationSummaryReader = Callable[[BaseException], list[dict[str, str]] | None]
