from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from p7_graph_support import sqlite_engine, seed_projection_fixture
from app.domains.relationships.service.policy_activation import activate_policy
from app.domains.relationships.models.personalization import RelationshipMetricApplication
from app.runtime.relationships.social_metrics import prepare_sources, stage_sources
from app.runtime.relationships.experience_metrics import apply_pending_metrics


def test_read_without_comment_and_cross_lane_replay_only_apply_once():
    with Session(sqlite_engine()) as db:
        f = seed_projection_fixture(db, suffix='read')
        now = datetime.now(UTC)
        activate_policy(db, world_id=f.world.id, now=now-timedelta(days=1))
        db.commit()
        sources = prepare_sources(db, actor=f.actor_world_character, post_ids=[f.root_post.id])
        raw = [dict(target_ref=f.target_world_character.id, affinity='increase', trust='keep', tension='decrease', new_evidence_refs=[f.root_post.id])]
        before = f.relationship.affinity
        stage_sources(db, actor=f.actor_world_character, manifest=sources, raw=raw, decision_key='feed-read', now=now)
        apply_pending_metrics(db, world_id=f.world.id)
        db.refresh(f.relationship)
        assert f.relationship.affinity == before+1
        version = f.relationship.version
        stage_sources(db, actor=f.actor_world_character, manifest=sources, raw=raw, decision_key='inbox-replay', now=now)
        apply_pending_metrics(db, world_id=f.world.id)
        db.refresh(f.relationship)
        assert f.relationship.version == version
        assert len(list(db.scalars(select(RelationshipMetricApplication)))) == 1
