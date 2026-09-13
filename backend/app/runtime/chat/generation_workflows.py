"""Construct the existing Chat provider, Memory and graph workflow in order."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts.retrieval_observation import current
from app.domains.characters.models import Character
from app.domains.chat.contracts.execution import GenerationExecution
from app.domains.chat.contracts.response_lifecycle import (
    ResponseLifecycleRepositoryPort,
)
from app.domains.chat.repository import retrieval_diagnostics
from app.domains.chat.service import (
    BothRetrievalWorkflowCoordinator,
    CanonicalRetrievalPlanningService,
    CharacterResponseGenerationService,
    EvidenceBundleAssembler,
    GraphRetrievalPlanningService,
    ResponseGenerationWorkflowService,
    RetrievalRoutingService,
)
from app.domains.identity.contracts import CredentialMaterial
from app.domains.memory.service.recall import CanonicalRecallService
from app.domains.memory.service.retrieval_plan import CanonicalRetrievalPlanExecutor
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanExecutor
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.domains.world_characters.models import WorldCharacter
from app.integrations.llm import (
    DirectLlmCanonicalRetrievalPlannerProvider,
    DirectLlmCharacterResponseGenerator,
    DirectLlmGraphRetrievalPlannerProvider,
)
from app.runtime.chat.evidence_reads import today_reader as today_reader
from app.runtime.chat.memory_producer import SqlAlchemySuccessfulChatMemoryProducer
from app.runtime.chat.response_graph import LangGraphResponseExecutor
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
from app.runtime.chat.retrieval_tools import ToolPlanningService, ToolBothCoordinator, parallel_tools, RetryingRead
from app.runtime.chat.retrieval_policy import (
    build_retrieval_policy as SqlAlchemyRetrievalPolicyResolver,
)
from app.runtime.chat.today_sns_activity import (
    build_today_snapshot_validator as SqlAlchemyTodaySnsSnapshotValidator,
)
from app.runtime.graph_projection.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway,
)


class SqlAlchemyResponseWorkflowUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._diagnostic_snapshot = None

    def checkpoint(self) -> None:
        observation = current.get()
        snapshot = None if observation is None else observation.payload()
        if observation is not None and snapshot != self._diagnostic_snapshot:
            try:
                with self._session.begin_nested():
                    retrieval_diagnostics.save(self._session, observation)
                self._diagnostic_snapshot = snapshot
            except Exception:
                # SAVEPOINT rolled back. Do not log exception/query parameters.
                pass
        self._session.commit()

    def rollback(self) -> None:
        self._diagnostic_snapshot = None
        self._session.rollback()


class SupervisorResponseWorkflowUnitOfWork(SqlAlchemyResponseWorkflowUnitOfWork):
    """Batch graph decisions while retaining the existing transaction owner."""

    def checkpoint(self) -> None:
        observation = current.get()
        snapshot = None if observation is None else observation.payload()
        if observation is not None and _diagnostic_trigger(
            snapshot
        ) == _diagnostic_trigger(self._diagnostic_snapshot):
            self._diagnostic_snapshot = snapshot
        super().checkpoint()


def _diagnostic_trigger(snapshot: dict | None) -> dict | None:
    """Include Supervisor decisions in the next existing diagnostic write.

    A decision alone must not add a SAVEPOINT/upsert at every workflow boundary.
    Router, retrieval, CRG and terminal observations still flush the full payload.
    """
    if snapshot is None:
        return None
    return {
        **snapshot,
        "events": [row for row in snapshot["events"] if row["event"] != "supervisor"],
    }


def build(
    db: Session,
    material: CredentialMaterial,
    *,
    memory_recall_service: CanonicalRecallService,
    runtime_settings: Settings,
    lifecycle: ResponseLifecycleRepositoryPort,
    world_id: str,
) -> GenerationExecution:
    canonical = CanonicalRetrievalPlanningService(
        planner=DirectLlmCanonicalRetrievalPlannerProvider(material),
        executor=CanonicalRetrievalPlanExecutor(RetryingRead(memory_recall_service)),
    )
    graph_recall = GraphRecallService(
        SqlAlchemyRelationshipGraphReadGateway(
            db, config=runtime_settings, graph_provider="ladybug"
        )
    )
    graph = GraphRetrievalPlanningService(
        planner=DirectLlmGraphRetrievalPlannerProvider(material),
        executor=GraphRetrievalPlanExecutor(RetryingRead(graph_recall)),
    )
    canonical = ToolPlanningService("CANONICAL", canonical)
    graph = ToolPlanningService("GRAPH", graph)
    character_labels = _character_labels(db, world_id)
    workflow = ResponseGenerationWorkflowService(
        graph_executor=LangGraphResponseExecutor(),
        lifecycle=lifecycle,
        router=RetrievalRoutingService(
            router=DirectLlmSupervisorSelectionProvider(
                material,
                native_controls=True,
                code_coordination=True,
                positional_entity_refs=False,
            ),
            policy=SqlAlchemyRetrievalPolicyResolver(db),
        ),
        canonical=canonical,
        graph=graph,
        both=ToolBothCoordinator(BothRetrievalWorkflowCoordinator(canonical=canonical, graph=graph, parallel_runner=parallel_tools)),
        evidence=EvidenceBundleAssembler(),
        character_response=CharacterResponseGenerationService(
            DirectLlmCharacterResponseGenerator(material)
        ),
        unit_of_work=SupervisorResponseWorkflowUnitOfWork(db),
        memory_producer=SqlAlchemySuccessfulChatMemoryProducer(db),
        today_snapshot_validator=SqlAlchemyTodaySnsSnapshotValidator(
            db, character_labels
        ),
    )
    return GenerationExecution(workflow, character_labels)


def _character_labels(db: Session, world_id: str) -> dict[str, str]:
    rows = db.execute(
        select(WorldCharacter.id, Character.name)
        .join(Character, Character.id == WorldCharacter.character_id)
        .where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.status == "active",
            Character.deleted_at.is_(None),
            Character.moderation_status == "active",
        )
    ).all()
    return {identifier: name for identifier, name in rows}
