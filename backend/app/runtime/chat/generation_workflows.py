"""Construct the existing Chat provider, Memory and graph workflow in order."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domains.characters.models import Character
from app.domains.chat.contracts.execution import GenerationExecution
from app.domains.chat.contracts.response_lifecycle import (
    ResponseLifecycleRepositoryPort,
)
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
from app.domains.memory.public import (
    CanonicalRecallService,
    CanonicalRetrievalPlanExecutor,
)
from app.domains.relationships.public import (
    GraphRecallService,
    GraphRetrievalPlanExecutor,
)
from app.domains.world_characters.models import WorldCharacter
from app.integrations.llm import (
    DirectLlmCanonicalRetrievalPlannerProvider,
    DirectLlmCharacterResponseGenerator,
    DirectLlmGraphRetrievalPlannerProvider,
    DirectLlmRetrievalRouterProvider,
)
from app.runtime.chat.evidence_reads import today_reader as today_reader
from app.runtime.chat.memory_producer import SqlAlchemySuccessfulChatMemoryProducer
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

    def checkpoint(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


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
        executor=CanonicalRetrievalPlanExecutor(memory_recall_service),
    )
    graph_recall = GraphRecallService(
        SqlAlchemyRelationshipGraphReadGateway(
            db, config=runtime_settings, graph_provider="ladybug"
        )
    )
    graph = GraphRetrievalPlanningService(
        planner=DirectLlmGraphRetrievalPlannerProvider(material),
        executor=GraphRetrievalPlanExecutor(graph_recall),
    )
    character_labels = _character_labels(db, world_id)
    workflow = ResponseGenerationWorkflowService(
        lifecycle=lifecycle,
        router=RetrievalRoutingService(
            router=DirectLlmRetrievalRouterProvider(material),
            policy=SqlAlchemyRetrievalPolicyResolver(db),
        ),
        canonical=canonical,
        graph=graph,
        both=BothRetrievalWorkflowCoordinator(canonical=canonical, graph=graph),
        evidence=EvidenceBundleAssembler(),
        character_response=CharacterResponseGenerationService(
            DirectLlmCharacterResponseGenerator(material)
        ),
        unit_of_work=SqlAlchemyResponseWorkflowUnitOfWork(db),
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
