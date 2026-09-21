from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from p7_graph_support import sqlite_engine, seed_projection_fixture
from app.domains.relationships.models.personalization import RelationshipPolicy, RelationshipMetricApplication
from app.domains.relationships.models.social import GraphProjectionOutbox
from app.domains.relationships.contracts.metric_interpretation import MetricInterpretation
from app.domains.relationships.service.personalized_metrics import ExperiencedSource, stage_experience, apply_staged_experience
from app.runtime.persistence.sqlite_schema import build_sqlite_v16_metadata, build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.v16_to_v17_relationship_personalization import upgrade, capture_delta, verify_delta


class References:
    def __init__(self, source):
        self.source = source

    def validate(self, source):
        assert (source.world_id, source.actor_id, source.target_id, source.key) == (
            self.source.world_id, self.source.actor_id, self.source.target_id, self.source.key)


def test_confirmed_experience_replay_preserves_single_delta_and_outbox():
    with Session(sqlite_engine()) as db:
        f = seed_projection_fixture(db, suffix="ri")
        now = datetime(2026, 9, 22, tzinfo=UTC)
        db.add(RelationshipPolicy(world_id=f.world.id, mode="interpreted", activated_at=now - timedelta(hours=1)))
        db.flush()
        source = ExperiencedSource(f.world.id, f.actor_world_character.id, f.target_world_character.id,
            "chat_turn", "message-1", "v1", now, now, "Asia/Seoul")
        refs = References(source)
        proposal = MetricInterpretation(source.target_id, "keep", "increase", "keep", (source.key,))
        before = f.relationship.trust
        app = stage_experience(db, references=refs, source=source, decision_key="generation-1", interpretation=proposal)
        assert app is not None
        db.commit()
        apply_staged_experience(db, application_id=app.id, references=refs, now=now)
        db.commit()
        replay = stage_experience(db, references=refs, source=source, decision_key="regeneration-2", interpretation=proposal)
        assert replay.id == app.id
        apply_staged_experience(db, application_id=app.id, references=refs, now=now)
        db.commit()
        assert f.relationship.trust == before + 1
        assert len(db.scalars(select(RelationshipMetricApplication)).all()) == 1
        assert len(db.scalars(select(GraphProjectionOutbox).where(GraphProjectionOutbox.projection_type == "relationship_snapshot")).all()) == 1


def test_pre_activation_source_never_gets_replayed_as_new_experience():
    with Session(sqlite_engine()) as db:
        f = seed_projection_fixture(db, suffix="old-ri")
        now = datetime(2026, 9, 22, tzinfo=UTC)
        db.add(RelationshipPolicy(world_id=f.world.id, mode="interpreted", activated_at=now))
        db.flush()
        source = ExperiencedSource(f.world.id, f.actor_world_character.id, f.target_world_character.id,
            "post", "post-1", "v1", now-timedelta(days=1), now, "Asia/Seoul")
        assert stage_experience(db, references=References(source), source=source, decision_key="new-read", interpretation=None) is None


def test_v16_upgrade_and_fresh_install_have_identical_schema():
    digests = []
    for fresh in (True, False):
        with create_engine("sqlite://").begin() as connection:
            (build_sqlite_baseline_metadata() if fresh else build_sqlite_v16_metadata()).create_all(connection)
            create_schema_version_table(connection)
            if not fresh:
                old_manifest = json.loads(Path("app/runtime/migrations/sqlite_versions/manifests/v16.json").read_text())
                assert sqlite_schema_contract_digest(connection) == old_manifest["schema_digest"]
                before = capture_delta(connection)
                upgrade(connection)
                verify_delta(connection, before)
            assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            digests.append(sqlite_schema_contract_digest(connection))
    manifest = json.loads(Path("app/runtime/migrations/sqlite_versions/manifests/v17.json").read_text())
    assert digests[0] == digests[1] == manifest["schema_digest"]
