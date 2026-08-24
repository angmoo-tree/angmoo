from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings
from app.domains.relationships.projection.commands import (
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)
from app.integrations.ladybug_projection import (
    LadybugProjectionError,
    LadybugRelationshipProjection,
)
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.services.graph_projection_replay import (
    GraphProjectionReplayService,
    create_replay_run,
    projection_digest,
)
from app.services.graph_projection_worker import GraphProjectionWorker
from app.services.relationship_graph_read import get_owner_relationship_graph
from p7_graph_support import seed_projection_fixture, sqlite_engine


NOW = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def _relationship(
    *,
    world_id: str,
    actor: str,
    target: str,
    index: int,
    familiarity: int,
    affinity: int,
    trust: int,
    tension: int,
    suffix: str = "fixture",
) -> RelationshipStateProjectionCommand:
    occurred_at = NOW + timedelta(minutes=index)
    event = SocialEventProjectionCommand(
        world_id=world_id,
        event_id=f"event-{actor}-{target}-{suffix}",
        event_type="reply_created",
        occurred_at=occurred_at,
        schema_version="social-event-v1",
        actor_world_character_id=f"wc-{actor}-{suffix}",
        actor_character_id=f"char-{actor}-{suffix}",
        target_world_character_id=f"wc-{target}-{suffix}",
        target_character_id=f"char-{target}-{suffix}",
    )
    return RelationshipStateProjectionCommand(
        event=event,
        relationship_state_id=f"relationship-{actor}-{target}-{suffix}",
        familiarity=familiarity,
        affinity=affinity,
        trust=trust,
        tension=tension,
        interaction_count=index + 1,
        last_event_id=event.event_id,
        last_event_at=occurred_at,
        updated_at=occurred_at,
        relationship_version=index + 1,
    )


def _commands(*, world_id: str, suffix: str) -> list[RelationshipStateProjectionCommand]:
    specs = (
        ("a", "b", 0, 30, 20, 20, 1),
        ("b", "a", 1, 7, -3, 2, 9),
        ("a", "c", 2, 10, 5, 5, 8),
        ("b", "c", 3, 8, 3, 4, 2),
        ("d", "a", 4, 6, 1, 3, 4),
        ("d", "b", 5, 6, 2, 3, 3),
        ("c", "d", 6, 12, 6, 7, 2),
        ("d", "e", 7, 15, 8, 8, 1),
        ("a", "f", 8, 20, 10, 10, 3),
    )
    return [
        _relationship(
            world_id=world_id,
            actor=actor,
            target=target,
            index=index,
            familiarity=familiarity,
            affinity=affinity,
            trust=trust,
            tension=tension,
            suffix=suffix,
        )
        for (
            actor,
            target,
            index,
            familiarity,
            affinity,
            trust,
            tension,
        ) in specs
    ]


def _ids(suffix: str) -> dict[str, str]:
    return {letter: f"wc-{letter}-{suffix}" for letter in "abcdef"}


def _time(value: object) -> str | None:
    if value is None:
        return None
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        value = to_native()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _hit(value: object) -> dict[str, Any]:
    result = asdict(value)
    result["last_event_at"] = _time(result["last_event_at"])
    result["updated_at"] = _time(result["updated_at"])
    result["event_ids"] = list(result["event_ids"])
    return result


def _query_snapshot(
    repository: RelationshipGraphRepository,
    *,
    world_id: str,
    suffix: str,
) -> dict[str, Any]:
    ids = _ids(suffix)
    path_1 = repository.find_shortest_path(
        world_id=world_id,
        source_world_character_id=ids["a"],
        target_world_character_id=ids["b"],
        direction_mode="outgoing",
        max_hops=1,
    )
    path_2 = repository.find_shortest_path(
        world_id=world_id,
        source_world_character_id=ids["a"],
        target_world_character_id=ids["d"],
        direction_mode="outgoing",
        max_hops=2,
    )
    path_3 = repository.find_shortest_path(
        world_id=world_id,
        source_world_character_id=ids["a"],
        target_world_character_id=ids["e"],
        direction_mode="outgoing",
        max_hops=3,
    )

    def path(value: object) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            "world_character_ids": list(value.world_character_ids),
            "oriented_edges": [_hit(edge) for edge in value.oriented_edges],
            "hop_count": value.hop_count,
        }

    def rank(mode: str) -> list[dict[str, Any]]:
        return [
            _hit(hit)
            for hit in repository.rank_related_characters(
                world_id=world_id,
                source_world_character_id=ids["a"],
                mode=mode,
                limit=20,
            )
        ]

    def visualization(depth: int) -> dict[str, Any]:
        value = repository.get_visualization_neighborhood(
            world_id=world_id,
            source_world_character_id=ids["a"],
            depth=depth,
            node_limit=20,
            edge_limit=40,
        )
        return {
            "center": value.center_world_character_id,
            "nodes": list(value.nodes),
            "edges": [_hit(edge) for edge in value.edges],
            "truncated": value.truncated,
        }

    evidence = repository.list_relationship_evidence(
        world_id=world_id,
        source_world_character_id=ids["a"],
        target_world_character_id=ids["b"],
        limit=5,
    )
    return {
        "direct": [
            _hit(hit)
            for hit in repository.get_direct_relationship(
                world_id=world_id,
                source_world_character_id=ids["a"],
                target_world_character_id=ids["b"],
            )
        ],
        "reverse": [
            _hit(hit)
            for hit in repository.get_direct_relationship(
                world_id=world_id,
                source_world_character_id=ids["b"],
                target_world_character_id=ids["a"],
            )
        ],
        "both": [
            _hit(hit)
            for hit in repository.get_direct_relationship(
                world_id=world_id,
                source_world_character_id=ids["a"],
                target_world_character_id=ids["b"],
                include_reverse=True,
            )
        ],
        "shared_outgoing": repository.list_shared_neighbors(
            world_id=world_id,
            source_world_character_id=ids["a"],
            target_world_character_id=ids["b"],
            direction_mode="outgoing",
        ),
        "shared_incoming": repository.list_shared_neighbors(
            world_id=world_id,
            source_world_character_id=ids["a"],
            target_world_character_id=ids["b"],
            direction_mode="incoming",
        ),
        "shared_either": repository.list_shared_neighbors(
            world_id=world_id,
            source_world_character_id=ids["a"],
            target_world_character_id=ids["b"],
            direction_mode="either",
        ),
        "path_1": path(path_1),
        "path_2": path(path_2),
        "path_3": path(path_3),
        "rank_positive": rank("positive"),
        "rank_tense": rank("tense"),
        "rank_recent": rank("recent"),
        "evidence": [
            {
                **asdict(hit),
                "occurred_at": _time(hit.occurred_at),
            }
            for hit in evidence
        ],
        "visualization_1": visualization(1),
        "visualization_2": visualization(2),
    }


def _assert_expected_snapshot(
    snapshot: dict[str, Any], *, suffix: str
) -> None:
    ids = _ids(suffix)
    assert [row["actor_world_character_id"] for row in snapshot["direct"]] == [
        ids["a"]
    ]
    assert [row["actor_world_character_id"] for row in snapshot["reverse"]] == [
        ids["b"]
    ]
    assert [row["actor_world_character_id"] for row in snapshot["both"]] == [
        ids["a"],
        ids["b"],
    ]
    assert snapshot["shared_outgoing"] == [ids["c"]]
    assert snapshot["shared_incoming"] == [ids["d"]]
    assert snapshot["shared_either"] == [ids["c"], ids["d"]]
    assert snapshot["path_1"]["world_character_ids"] == [ids["a"], ids["b"]]
    assert snapshot["path_2"]["world_character_ids"] == [
        ids["a"],
        ids["c"],
        ids["d"],
    ]
    assert snapshot["path_3"]["world_character_ids"] == [
        ids["a"],
        ids["c"],
        ids["d"],
        ids["e"],
    ]
    assert [row["target_world_character_id"] for row in snapshot["rank_positive"]] == [
        ids["b"],
        ids["f"],
        ids["c"],
    ]
    assert [row["target_world_character_id"] for row in snapshot["rank_tense"]] == [
        ids["c"],
        ids["f"],
        ids["b"],
    ]
    assert [row["target_world_character_id"] for row in snapshot["rank_recent"]] == [
        ids["f"],
        ids["c"],
        ids["b"],
    ]
    assert [row["event_id"] for row in snapshot["evidence"]] == [
        f"event-a-b-{suffix}"
    ]
    assert len(snapshot["visualization_1"]["edges"]) == 5
    assert len(snapshot["visualization_2"]["edges"]) == 9


def test_ladybug_typed_query_workload_and_world_isolation(tmp_path: Path) -> None:
    suffix = "ladybug-parity"
    world_id = "world-arcana-parity"
    commands = _commands(world_id=world_id, suffix=suffix)
    other = _relationship(
        world_id="world-other-parity",
        actor="a",
        target="b",
        index=0,
        familiarity=99,
        affinity=99,
        trust=99,
        tension=0,
        suffix="other-world",
    )
    with LadybugRelationshipProjection(
        database_root=tmp_path / "ladybug-query-parity"
    ) as projection:
        for command in [*commands, other]:
            assert projection.apply(command) == "applied"
        repository = RelationshipGraphRepository(projection)
        snapshot = _query_snapshot(
            repository, world_id=world_id, suffix=suffix
        )
        _assert_expected_snapshot(snapshot, suffix=suffix)
        assert projection.world_digest(world_id) == projection_digest(commands)
        assert repository.get_direct_relationship(
            world_id="world-other-parity",
            source_world_character_id=_ids(suffix)["a"],
            target_world_character_id=_ids(suffix)["b"],
        ) == []

        exclusion = SourceExclusionProjectionCommand(
            world_id=world_id,
            event_id=commands[0].event.event_id,
            reason="source_hidden",
        )
        assert projection.apply(exclusion) == "removed"
        assert repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=_ids(suffix)["a"],
            target_world_character_id=_ids(suffix)["b"],
        ) == []
        assert projection.world_digest(world_id) == projection_digest(
            [*commands, exclusion]
        )


def test_ladybug_world_replay_restores_digest_and_sqlite_source(
    tmp_path: Path,
) -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="ladybug-replay")
        first_run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="er3-pr-i",
            reason_code="provider_parity",
        )
        first_run_id = first_run.id
        world_id = fixture.world.id
        actor_id = fixture.actor_world_character.id
        target_id = fixture.target_world_character.id
        source_event_id = fixture.event.id
        db.commit()

    session_factory = lambda: Session(engine, expire_on_commit=False)
    with LadybugRelationshipProjection(
        database_root=tmp_path / "ladybug-replay"
    ) as projection:
        replay = GraphProjectionReplayService(
            session_factory=session_factory,
            store=projection,
            worker_id="ladybug-replay-worker",
        )
        assert replay.execute(first_run_id).status == "succeeded"
        first_digest = projection.world_digest(world_id)
        assert first_digest["relationships"]

        evidence = RelationshipGraphRepository(
            projection
        ).list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        assert [row.event_id for row in evidence] == [source_event_id]
        with Session(engine) as db:
            source = db.get(models.SocialEvent, source_event_id)
            assert source is not None
            assert source.result == "succeeded"
            assert source.world_id == world_id
            response = get_owner_relationship_graph(
                db,
                character_id=fixture.actor.id,
                world_id=world_id,
                user=fixture.owner,
                view="evidence",
                target_world_character_id=target_id,
                repository=RelationshipGraphRepository(projection),
                graph_provider="ladybug",
            )
            assert response.meta.source == "ladybug"
            assert response.meta.graph_status == "lagging"
            assert [edge.last_event_id for edge in response.edges] == [
                source_event_id
            ]
            assert [row.event_id for row in response.evidence] == [
                source_event_id
            ]

        projection.clear_world(world_id)
        assert projection.world_digest(world_id) == {
            "world_characters": [],
            "events": [],
            "relationships": [],
            "evidence": [],
        }
        with Session(engine, expire_on_commit=False) as db:
            second_run = create_replay_run(
                db,
                world_id=world_id,
                mode="world_rebuild",
                source_event_id=None,
                requested_by="er3-pr-i",
                reason_code="clear_replay",
            )
            second_run_id = second_run.id
            db.commit()
        assert replay.execute(second_run_id).status == "succeeded"
        assert projection.world_digest(world_id) == first_digest


class _UnavailableLadybug:
    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        raise LadybugProjectionError("ladybug_unavailable")


def test_ladybug_outage_backlog_recovers_to_zero_lag(tmp_path: Path) -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="ladybug-recovery")
        outbox_id = fixture.outbox.id
        world_id = fixture.world.id

    session_factory = lambda: Session(engine, expire_on_commit=False)
    unavailable = GraphProjectionWorker(
        session_factory=session_factory,
        store=_UnavailableLadybug(),
        worker_id="ladybug-unavailable",
    ).process_batch()
    assert unavailable.retried == 1
    assert unavailable.graph_degraded is True
    with Session(engine) as db:
        pending = db.get(models.GraphProjectionOutbox, outbox_id)
        assert pending is not None
        pending.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    with LadybugRelationshipProjection(
        database_root=tmp_path / "ladybug-recovery"
    ) as projection:
        recovered = GraphProjectionWorker(
            session_factory=session_factory,
            store=projection,
            worker_id="ladybug-recovered",
        ).process_batch()
        assert recovered.succeeded == 1
        assert projection.world_digest(world_id)["relationships"]

    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, outbox_id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.last_error_class is None
        assert db.query(models.GraphProjectionOutbox).filter(
            models.GraphProjectionOutbox.status.in_(("pending", "processing"))
        ).count() == 0
