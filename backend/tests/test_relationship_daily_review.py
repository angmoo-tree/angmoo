import asyncio
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from p7_graph_support import sqlite_engine, seed_projection_fixture
from app.domains.memory.models.items import MemoryItem
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.service.daily_review import plan_review, run_review_step, apply_review


class References:
    def revalidate(self, work):
        assert work.actor_world_character_id != work.target_world_character_id


class Provider:
    def __init__(self):
        self.calls = []
        self.fail_next = False

    async def review(self, payload, *, partial, timeout):
        self.calls.append(payload)
        if self.fail_next:
            self.fail_next = False
            raise TimeoutError()
        refs = [m['memory_id'] for m in payload.get('memories', [])]
        if not refs:
            refs = list(dict.fromkeys(r for p in payload['partial_results'] for r in p['memory_refs']))
        if partial:
            return dict(findings=['도움과 의견 충돌을 함께 고려한다.'], uncertainty='', memory_refs=refs[:64])
        return dict(decision='update', relationship_label='함께 성장하는 동료',
                    perception='의견은 다르지만 어려울 때 도와주는 상대다.', memory_refs=refs[:64])


def seed(count):
    engine = sqlite_engine()
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        f = seed_projection_fixture(db, suffix='daily')
        memories = []
        for i in range(count):
            item = MemoryItem(id=f'm-{i:04}', owner_id=f.owner.id, world_id=f.world.id,
                subject_world_character_id=f.actor_world_character.id, memory_kind='AUTOBIOGRAPHICAL_EVENT',
                summary='서로 도왔지만 의견 충돌도 있었다. ' * 80, confidence=1, salience=1)
            db.add(item)
            memories.append(dict(memory_id=item.id, summary=item.summary, digest='a'*64,
                source_refs=[f'post:{i//2}'], occurred_at='2026-09-22T00:00:00Z'))
        db.flush()
        root = plan_review(db, world_id=f.world.id, actor_id=f.actor_world_character.id,
            target_id=f.target_world_character.id, period_key='2026-09-22', base={}, memories=memories)
        db.commit()
        return factory, root.id, f.relationship.id


def run(factory, work_id, provider):
    return asyncio.run(run_review_step(factory, work_id=work_id,
        references_factory=lambda db: References(), provider_factory=lambda base: provider))


def test_direct_result_is_durable_and_applied_once_without_metric_change():
    from app.domains.relationships.models.social import RelationshipState
    factory, root_id, state_id = seed(2)
    provider = Provider()
    assert run(factory, root_id, provider) == 'ready'
    assert run(factory, root_id, provider) == 'ready'
    assert len(provider.calls) == 1
    with factory() as db:
        state = db.get(RelationshipState, state_id)
        before = (state.familiarity, state.affinity, state.trust, state.tension)
        assert state.relationship_label is None
        assert apply_review(db, work_id=root_id, references=References(), now=datetime.now(UTC)) == 'applied'
        db.commit()
        version = state.version
        assert apply_review(db, work_id=root_id, references=References(), now=datetime.now(UTC)) == 'applied'
        assert state.version == version
        assert before == (state.familiarity, state.affinity, state.trust, state.tension)
        assert state.relationship_label == '함께 성장하는 동료'
        assert set(db.scalars(select(RelationshipReviewMemoryReceipt.status))) == {'applied'}


def test_split_retry_reuses_finished_parts_and_only_final_updates():
    from app.domains.relationships.models.social import RelationshipState
    factory, root_id, state_id = seed(36)
    provider = Provider()
    with factory() as db:
        parts = list(db.scalars(select(RelationshipReviewWork.id).where(RelationshipReviewWork.parent_id == root_id)))
        assert len(parts) > 1
    assert run(factory, root_id, provider) == 'waiting_for_parts'
    assert not provider.calls
    assert run(factory, parts[0], provider) == 'ready'
    provider.fail_next = True
    assert run(factory, parts[1], provider) == 'retry_pending'
    # Expired retry time is a scheduler gate; service resumes the failed unit.
    for part in parts[1:]:
        assert run(factory, part, provider) == 'ready'
    assert run(factory, parts[0], provider) == 'ready'
    with factory() as db:
        assert db.get(RelationshipState, state_id).perception is None
        assert set(db.scalars(select(RelationshipReviewMemoryReceipt.status))) == {'pending'}
    assert run(factory, root_id, provider) == 'ready'
    with factory() as db:
        assert apply_review(db, work_id=root_id, references=References(), now=datetime.now(UTC)) == 'applied'
        db.commit()
    assert len(provider.calls) == len(parts) + 2
