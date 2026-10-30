"""Current owned-memory rights captured in one read snapshot, never a writer.

Epochs are authorization fences; dependencies only select work. Neither is a
replacement for current memory authorization at search time.
"""
from app.core import work_observation as observation
from dataclasses import dataclass
from datetime import UTC, datetime
from time import time
from sqlalchemy import event, inspect, text
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.vector_work import read_work, retained_registration
from app.runtime.memory.vector_mutations import catalog, EXPERIENCE_RIGHT_TABLES

@dataclass(frozen=True)
class VectorProof:
    epochs: tuple[tuple[str, int], ...]
    dependencies: frozenset[tuple[str, str]]
    next_boundary: float | None
    observed_at: float
    related_dependencies: tuple = ()
    world_closed: bool = False


def revisions(session, keys):
    if session.get_bind().dialect.name == "postgresql":
        from app.runtime.memory.postgresql_epochs import read_keys
        return tuple((key, int(session.execute(text(
            "SELECT COALESCE(sum(revision),0) FROM memory_vector_validation_revisions WHERE scope_key=ANY(:keys)"),
            {"keys": read_keys(key)}).scalar_one())) for key in keys)
    return tuple((key, session.execute(text(
        "SELECT revision FROM memory_vector_validation_revisions WHERE scope_key=:key"),
        {"key": key}).scalar_one_or_none() or 0) for key in keys)


def current(session, proof):
    return (not proof.world_closed and revisions(session, (key for key, _ in proof.epochs)) == proof.epochs
        and (proof.next_boundary is None or time() < proof.next_boundary))


class SourceReadSet:
    """Record owned-memory authorization dependencies, never original sources."""
    def __init__(self, item_id):
        self.item_id = item_id
        self.graph = {("memory", item_id): set()}
        self.boundaries = []
        self.entries = {entry["table"]: entry for entry in catalog() if entry["table"] in EXPERIENCE_RIGHT_TABLES}

    def loaded(self, session, row):
        table = inspect(row).mapper.local_table
        entry = self.entries.get(table.name)
        if entry is None:
            return
        expression = entry["key"]
        if not expression.startswith("{row}."):
            return
        value = getattr(row, expression[6:])
        if value is None:
            return
        own = entry["kind"], str(value)
        references = self.graph.setdefault(own, set())
        for column in table.columns:
            value = getattr(row, column.name)
            if value is None:
                continue
            for foreign in column.foreign_keys:
                target = self.entries.get(foreign.column.table.name)
                if target is not None and target["kind"] != "world":
                    references.add((target["kind"], str(value)))
        for name in ("valid_from", "valid_until", "expires_at"):
            value = getattr(row, name, None)
            if isinstance(value, datetime):
                self.boundaries.append((value.replace(tzinfo=UTC) if value.tzinfo is None else value).timestamp())

    def dependencies_for(self, identifier):
        root = ("memory", identifier)
        visited, frontier = {root}, list(self.graph.get(root, ()))
        while frontier:
            key = frontier.pop()
            if key in visited:
                continue
            visited.add(key)
            if key[0] != "memory":
                frontier.extend(self.graph.get(key, ()))
        return frozenset(visited)

    @property
    def dependencies(self):
        return self.dependencies_for(self.item_id)

    def related(self):
        return tuple((key, self.dependencies_for(key)) for kind, key in self.graph
            if kind == "memory" and key != self.item_id)


def snapshot(projection, item_id, credential_revision):
    from app.runtime.memory_embedding_provider import embedding_material, validate_embedding_credential
    readset = SourceReadSet(item_id)
    with projection._factory() as session:
        if session.get_bind().dialect.name == "postgresql":
            from app.core.postgresql_reads import begin_owned_read
            begin_owned_read(session.connection())
        else:
            # sqlite3 legacy transaction control does not BEGIN for SELECT.
            session.connection().exec_driver_sql("BEGIN")
        observed = time()
        event.listen(session, "loaded_as_persistent", readset.loaded)
        item = session.get(MemoryItem, item_id)
        if item is None:
            return None, (), None, None, False, VectorProof((), frozenset(readset.dependencies), None, observed)
        with observation.span("vector_source_proof", world_id=item.world_id,
                actor_id=item.subject_world_character_id, item_id=item_id, version=item.version):
            keys = (f"experience:world:{item.world_id}", f"experience:owner:{item.owner_id}")
            epochs = revisions(session, keys)
            if session.execute(text("SELECT 1 FROM world_deletion_requests WHERE world_id=:world"), {"world": item.world_id}).first():
                return None, (), None, None, False, VectorProof(epochs, frozenset(), None, observed, world_closed=True)
            readset.graph[("memory", item_id)].update({("world", item.world_id), ("users", item.owner_id)})
            work = read_work(session, item_id)
            retained = retained_registration(session, item_id)
            from app.domains.memory.exceptions import MemoryScopeError
            try:
                # OFF retains valid vectors, but is not permission to retain a
                # revoked source or skip a future expiry boundary.
                documents = projection._source.documents_for_item_ids((item_id,), session=session).get(item_id, ()) if retained else ()
            except MemoryScopeError:
                documents = ()
            from app.domains.memory.exceptions import MemoryValidationError
            revision, material = None, None
            try:
                if documents and work:
                    revision = validate_embedding_credential(session, work[0], revision=credential_revision)
                    material = embedding_material(session, work[0], revision=revision)
            except MemoryValidationError as exc:
                # Persist observed dependencies before blocking, so a credential
                # correction can wake this item without a full rescan.
                material = exc
            from app.domains.memory.models.experience import MemoryExperienceDependency
            from sqlalchemy import select
            readset.graph[("memory",item_id)].update(("memory",identifier) for identifier in session.scalars(
                select(MemoryExperienceDependency.origin_memory_id).where(MemoryExperienceDependency.memory_item_id==item_id)))
            boundary = min((value for value in readset.boundaries if value > observed), default=None)
            proof = VectorProof(epochs, readset.dependencies, boundary, observed, readset.related())
            return work, documents, material, revision, retained, proof
