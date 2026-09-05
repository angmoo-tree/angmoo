"""Typed provider/runtime construction used by the Chat generation service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.orm import Session

from app.config import Settings
from app.domains.chat.contracts.response_lifecycle import (
    ResponseLifecycleRepositoryPort,
)
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityReaderPort
from app.domains.identity.contracts import CredentialMaterial

if TYPE_CHECKING:
    from app.domains.chat.service.response_workflow import (
        ResponseGenerationWorkflowService,
    )
    from app.domains.memory.public import CanonicalRecallService


@dataclass(frozen=True, slots=True)
class GenerationExecution:
    workflow: ResponseGenerationWorkflowService
    character_labels: Mapping[str, str]


class GenerationWorkflows(Protocol):
    def build(
        self,
        db: Session,
        material: CredentialMaterial,
        *,
        memory_recall_service: CanonicalRecallService,
        runtime_settings: Settings,
        lifecycle: ResponseLifecycleRepositoryPort,
        world_id: str,
    ) -> GenerationExecution: ...
    def today_reader(self, db: Session) -> TodaySnsActivityReaderPort: ...
