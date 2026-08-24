from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from app.domains.relationships.graph_read.repository import (
    RelationshipGraphQueryPort,
)
from app.domains.relationships.ports.outbox import OutboxPort, ProjectionWorkItem
from app.domains.relationships.ports.projection import RelationshipProjectionPort
from app.domains.relationships.projection.commands import NoGraphMutationCommand
from app.domains.routines.infrastructure.system_clock import SystemClock
from app.domains.routines.ports.clock import ClockPort
from app.domains.runtime.infrastructure.sqlalchemy_scheduler_lease import (
    SqlAlchemySchedulerLeaseRepository,
)
from app.domains.runtime.ports.migration_source import MigrationSourcePort
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.domains.runtime.ports.scheduler_lease_repository import ClaimLeasePort
from app.domains.runtime.ports.search_index import (
    SearchIndexDocument,
    SearchIndexHit,
    SearchIndexPort,
)
from app.domains.runtime.ports.unit_of_work import UnitOfWorkPort
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.runtime.graph_projection.sqlalchemy_outbox import SqlAlchemyProjectionOutbox
from app.runtime.migrations.alembic_source import AlembicMigrationSource
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.runtime.search.callback_index import CallbackSearchIndexAdapter
from app.services.graph_projection_commands import (
    NoGraphMutationCommand as LegacyNoGraphMutationCommand,
)
from app.services.graph_projection_worker import GraphProjectionWorker


def test_current_adapters_satisfy_er1_runtime_ports() -> None:
    assert isinstance(SystemClock(), ClockPort)
    assert isinstance(
        object.__new__(SqlAlchemySchedulerLeaseRepository), ClaimLeasePort
    )
    assert isinstance(object.__new__(SqlAlchemyProjectionOutbox), OutboxPort)
    assert isinstance(
        object.__new__(LadybugRelationshipProjection), RelationshipProjectionPort
    )
    assert isinstance(
        object.__new__(RelationshipGraphRepository), RelationshipGraphQueryPort
    )
    assert isinstance(object.__new__(SqlAlchemyUnitOfWork), UnitOfWorkPort)


def test_projection_command_compatibility_facade_keeps_type_identity() -> None:
    assert LegacyNoGraphMutationCommand is NoGraphMutationCommand


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def flush(self) -> None:
        self.calls.append(("flush", None))

    def commit(self) -> None:
        self.calls.append(("commit", None))

    def rollback(self) -> None:
        self.calls.append(("rollback", None))

    def refresh(self, entity: object) -> None:
        self.calls.append(("refresh", entity))


def test_sqlalchemy_unit_of_work_delegates_without_owning_domain_logic() -> None:
    session = _RecordingSession()
    entity = object()
    adapter = SqlAlchemyUnitOfWork(session)  # type: ignore[arg-type]
    adapter.flush()
    adapter.commit()
    adapter.rollback()
    adapter.refresh(entity)
    assert session.calls == [
        ("flush", None),
        ("commit", None),
        ("rollback", None),
        ("refresh", entity),
    ]


def test_runtime_data_path_is_deterministic_and_side_effect_free(tmp_path: Path) -> None:
    adapter = StaticRuntimeDataPath(tmp_path / "Angmoo")
    assert isinstance(adapter, RuntimeDataPathPort)
    paths = adapter.resolve()
    assert paths.canonical == paths.root / "canonical"
    assert paths.graph == paths.root / "graph"
    assert paths.search == paths.root / "search"
    assert paths.media == paths.root / "media"
    assert paths.secrets == paths.root / "secrets"
    assert not paths.root.exists()


def test_alembic_migration_source_is_stable_and_read_only(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    first = versions / "001_first.py"
    first.write_text(
        'revision = "001"\ndown_revision = None\n', encoding="utf-8"
    )
    second = versions / "002_second.py"
    second.write_text(
        'revision: str = "002"\ndown_revision: str | None = "001"\n',
        encoding="utf-8",
    )
    adapter = AlembicMigrationSource(versions)
    assert isinstance(adapter, MigrationSourcePort)
    revisions = adapter.revisions()
    assert [(item.revision, item.down_revision, item.path) for item in revisions] == [
        ("001", None, "001_first.py"),
        ("002", "001", "002_second.py"),
    ]
    assert revisions == adapter.revisions()
    assert all(len(item.sha256) == 64 for item in revisions)


def test_callback_search_adapter_keeps_current_search_behind_port() -> None:
    writes: list[str] = []
    removes: list[str] = []
    queries: list[tuple[str, str, int]] = []
    hit = SearchIndexHit(document_id="post-1", score=1.0, snippet="hello")
    adapter = CallbackSearchIndexAdapter(
        upsert=lambda document: writes.append(document.document_id),
        remove=removes.append,
        search=lambda world_id, query, limit: (
            queries.append((world_id, query, limit)) or (hit,)
        ),
    )
    assert isinstance(adapter, SearchIndexPort)
    adapter.upsert(
        SearchIndexDocument(
            document_id="post-1",
            world_id="world-1",
            kind="post",
            text="hello",
            metadata={"source": "canonical"},
        )
    )
    adapter.remove(document_id="post-2")
    assert adapter.search(world_id="world-1", query="hello", limit=3) == (hit,)
    assert writes == ["post-1"]
    assert removes == ["post-2"]
    assert queries == [("world-1", "hello", 3)]


class _PortOutbox:
    def __init__(self) -> None:
        self.finalized: list[str] = []

    def claim(self, **_kwargs) -> tuple[ProjectionWorkItem, ...]:
        return (ProjectionWorkItem(id="outbox-1", projection_type="social_event"),)

    def load_command(self, *, outbox_id: str) -> NoGraphMutationCommand:
        assert outbox_id == "outbox-1"
        return NoGraphMutationCommand(
            world_id="world-1", event_id="event-1", reason="no-op"
        )

    def finalize_success(self, *, outbox_id: str, **_kwargs) -> str:
        self.finalized.append(outbox_id)
        return "succeeded"

    def finalize_failure(self, **_kwargs) -> str:
        raise AssertionError("failure path was not expected")


class _PortStore:
    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        assert isinstance(command, NoGraphMutationCommand)
        assert timeout_seconds == 5.0
        return "no_graph_mutation"


def test_projection_worker_can_run_with_ports_only() -> None:
    outbox = _PortOutbox()
    result = GraphProjectionWorker(
        outbox=outbox,
        store=_PortStore(),
        worker_id="er1-port-worker",
        concurrency=1,
    ).process_batch()
    assert result.claimed == 1
    assert result.succeeded == 1
    assert outbox.finalized == ["outbox-1"]


def test_port_modules_and_projection_worker_preserve_dependency_direction() -> None:
    app_root = Path(__file__).parents[1] / "app"
    port_roots = [
        app_root / "domains" / "relationships" / "ports",
        app_root / "domains" / "runtime" / "ports",
    ]
    forbidden = ("app.runtime", "app.integrations", "app.models", "app.cruds")
    for root in port_roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            ]
            assert not any(
                imported.startswith(forbidden) for imported in imports
            ), path

    worker_source = (
        app_root / "services" / "graph_projection_worker.py"
    ).read_text(encoding="utf-8")
    assert "from sqlalchemy" not in worker_source
    assert "from app import models" not in worker_source
    assert "from app.cruds" not in worker_source


def test_test_clock_values_are_timezone_aware() -> None:
    assert SystemClock().now_utc().tzinfo is not None
    assert datetime.now(UTC).tzinfo is not None
