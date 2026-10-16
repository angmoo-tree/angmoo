"""Immutable source proof built in an explicit read snapshot, never a writer.

Epochs are authorization fences; dependencies only select work. Neither is a
replacement for canonical revalidation at search time.
"""
from app.core import work_observation as observation
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from time import time
from sqlalchemy import event, inspect, text
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.vector_work import read_work, retained_registration
from app.runtime.memory.vector_mutations import catalog

SOURCE_TABLES = {
    "POST": "posts", "REPLY": "posts", "REACTION": "post_likes",
    "CHAT_MESSAGE": "message_messages", "SOCIAL_EVENT": "social_events",
    "ACTIVITY_BEAT": "activity_beats", "RELATIONSHIP_CHANGE": "relationship_state_changes",
    "JOINT_ACTIVITY": "joint_activities", "ROUTINE_ACTIVITY": "daily_activity_plan_items",
    "ACTIVITY_PROPOSAL": "activity_proposals", "IMAGE_INTERPRETATION": "image_interpretations",
    "IMAGE_ASSET": "media_assets", "RELATIONSHIP": "relationship_states", "MEMORY_ITEM": "memory",
    "OWNER_MEMORY_REQUEST": "message_messages", "ACTIVITY_EVENT": "activity_beats",
    "RELATIONSHIP_EVENT": "relationship_state_changes", "JOINT_COMMITMENT": "joint_activities",
}


@dataclass(frozen=True)
class VectorProof:
    epochs: tuple[tuple[str, int], ...]
    dependencies: frozenset[tuple[str, str]]
    next_boundary: float | None
    observed_at: float
    related_dependencies: tuple = ()
    world_closed: bool = False


def revisions(session, keys):
    return tuple((key, session.execute(text(
        "SELECT revision FROM memory_vector_validation_revisions WHERE scope_key=:key"),
        {"key": key}).scalar_one_or_none() or 0) for key in keys)


def current(session, proof):
    return (not proof.world_closed and revisions(session, (key for key, _ in proof.epochs)) == proof.epochs
        and (proof.next_boundary is None or time() < proof.next_boundary))


def _references(value, dependencies):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return
    if isinstance(value, dict):
        kind, identifier = value.get("source_type") or value.get("type"), value.get("source_id") or value.get("id")
        if kind in SOURCE_TABLES and identifier is not None:
            dependencies.add((SOURCE_TABLES[kind], str(identifier)))
        for child in value.values():
            _references(child, dependencies)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _references(child, dependencies)


class SourceReadSet:
    """Normalize the observed source graph, keeping prior edges direct.

    Foreign source facts may be shared by many memories. A prior's source
    graph is stored at that prior, not copied into every descendant's row.
    Partial ancestor observations are merged; only the root's full observed
    dependency set replaces its prior set.
    """
    def __init__(self, item_id):
        self.item_id = item_id
        self.graph = {("memory", item_id): set()}
        self.boundaries = []
        self.entries = {entry["table"]: entry for entry in catalog()}

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
        for name in ("source", "payload", "result", "resolved_source", "sources_json", "priors_json"):
            if name in table.c:
                _references(getattr(row, name), references)
        if "source_type" in table.c and "source_id" in table.c:
            _references({"type": row.source_type, "id": row.source_id}, references)
        if "priors_json" in table.c:
            try:
                references.update(("memory", str(ref["id"])) for ref in json.loads(row.priors_json))
            except (ValueError, TypeError, KeyError):
                pass  # Policy validation rejects malformed provenance.
        if table.name == "memory_items" and row.superseded_by_id:
            self.graph.setdefault(("memory", row.superseded_by_id), set()).add(("memory", row.id))
        if table.name == "social_event_evidence":
            if row.source_post_id:
                self.graph.setdefault(("posts", row.source_post_id), set()).add(own)
            if row.source_object_type == "post_like":
                self.graph.setdefault(("post_likes", row.source_object_id), set()).add(own)
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
        # sqlite3 legacy transaction control does not BEGIN for SELECT. An
        # explicit BEGIN makes all source reads and captured epochs one view.
        session.connection().exec_driver_sql("BEGIN")
        observed = time()
        event.listen(session, "loaded_as_persistent", readset.loaded)
        item = session.get(MemoryItem, item_id)
        if item is None:
            return None, (), None, None, False, VectorProof((), frozenset(readset.dependencies), None, observed)
        with observation.span("vector_source_proof", world_id=item.world_id,
                actor_id=item.subject_world_character_id, item_id=item_id, version=item.version):
            keys = (f"world:{item.world_id}", f"owner:{item.owner_id}")
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
            boundary = min((value for value in readset.boundaries if value > observed), default=None)
            proof = VectorProof(epochs, readset.dependencies, boundary, observed, readset.related())
            return work, documents, material, revision, retained, proof
