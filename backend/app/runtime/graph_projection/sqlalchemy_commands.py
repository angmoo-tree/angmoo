"""Compose graph command reads with the existing caller Session."""
from sqlalchemy.orm import Session
from app.domains.relationships.contracts.projection_commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    ProjectionCommandError,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)
from app.domains.relationships.service import projection_commands
from app.runtime.graph_projection.command_references import SqlAlchemyProjectionCommandReferences


def build_projection_command(
    db: Session,
    *,
    outbox_id: str,
    replay_relationship_snapshot: bool = False,
) -> ProjectionCommand:
    return projection_commands.build_projection_command(
        db,
        outbox_id=outbox_id,
        replay_relationship_snapshot=replay_relationship_snapshot,
        references=SqlAlchemyProjectionCommandReferences(db),
    )
