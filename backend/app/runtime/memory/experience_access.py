"""Compose current ownership/deletion reads in the caller's existing Session."""
from dataclasses import dataclass
from app.domains.chat.models import MessageThread
from app.runtime.subject_scope import read_scope_presence


@dataclass(frozen=True)
class SqlAlchemyMemoryExperienceAccess:
    session: object

    def scope_present(self, scope):
        return all(value is not None for value in read_scope_presence(self.session, scope))

    def thread_accessible(self, scope, thread_id, *, validation):
        if validation.session is not self.session:
            raise ValueError("memory_access_validation_context_mismatch")
        thread = validation.get(MessageThread, thread_id)
        return (thread is not None and thread.deleted_at is None
            and (thread.requester_id, thread.world_id) == (scope.owner_id, scope.world_id)
            and scope.subject_world_character_id in {
                thread.requester_world_character_id, thread.responding_world_character_id})
