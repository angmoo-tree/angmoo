"""HTTP collaboration above Chat and Memory's mutually consumed runtime packages.

The application composes concrete readers and credential readiness here.
Memory services own the actual consent, mutation and transaction decisions.
"""
from sqlalchemy.orm import Session
from app.runtime.memory.composition import memory_repository, memory_batch_repository


from contextlib import nullcontext
from app.domains.memory.contracts.management import MemoryWorkflows
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.service.inspector import MemoryReadService
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.service.items import MemoryWriteLifecycleService
from app.runtime.memory.sqlalchemy_source_reader import SqlAlchemyMemorySourceEvidenceReader
from app.runtime.world_characters.composition import public_profile_service
from app.runtime.memory_selection_provider import memory_provider


def _service(db: Session) -> MemoryReadService:
    return MemoryReadService(
        memory_repository(db),
        SqlAlchemyMemorySourceEvidenceReader(db),
    )



def _scope_service(db: Session) -> MemoryScopeService:
    return MemoryScopeService(memory_repository(db))



def _write_service(db: Session) -> MemoryWriteLifecycleService:
    return MemoryWriteLifecycleService(
        memory_repository(db),
        SqlAlchemyMemorySourceEvidenceReader(db),
    )



def _character_names(db: Session, scope: MemoryScope) -> dict[str, str]:
    profiles = public_profile_service(db).list_for_world(
        world_id=scope.world_id,
        current_user_id=scope.owner_id,
    )
    return {profile.world_character_id: profile.display_name for profile in profiles}



def _validate_provider(db: Session, owner_id: str, model_id: str) -> None:
    # Original Save-time credential readiness; no generation or replacement Session.
    memory_provider(lambda: nullcontext(db), owner_id, model_id)


def build_memory_workflows() -> MemoryWorkflows:
    return MemoryWorkflows(
        read_service=_service,
        scope_service=_scope_service,
        write_service=_write_service,
        batch_repository=memory_batch_repository,
        character_names=_character_names,
        validate_provider=_validate_provider,
    )
