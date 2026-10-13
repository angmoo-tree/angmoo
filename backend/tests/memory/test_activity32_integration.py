"""New admission through one real SQLite transaction, with a network-free selector."""
import asyncio
import json
from sqlalchemy import select, func

from app.domains.identity.service import world_credentials
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.contracts.provenance import MemorySourceTypeV1, MemoryKindV1
from app.domains.memory.models.batch import MemoryActivationEpoch, MemorySourceDelivery
from app.domains.memory.models.items import MemoryCandidate, MemoryItem
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
from app.domains.memory.service.items import MemoryWriteLifecycleService
from app.domains.memory.policies.batch import MEMORY_CONSENT_VERSION
from app.domains.social.models.posts import Post
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.episode_batch import run_episode_batch
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from memory.test_episode_chat_pipeline import setup, response_session


class SkipAll:
    def __init__(self):
        self.calls, self.bundles = 0, []
    def validate_bundle(self, bundle):
        pass
    async def select(self, bundle, *, timeout):
        self.calls += 1; self.bundles.append(bundle)
        return EpisodeSelection((), tuple(f"S{i}" for i in range(1, len(bundle.new_units) + 1)))


def prepare(db, *, posts=31):
    scope, memory, _, done, now = setup(db)
    key_args = dict(owner_id=scope.owner_id, world_id=scope.world_id, world_character_id=scope.subject_world_character_id, purpose="consolidation")
    world_credentials.save(db, **key_args, data=WorldCredentialWrite(expected_revision=0, provider="google",
        model="gemini-3.1-flash-lite", thinking_level="high", api_key="synthetic-world-memory-key"))
    repo = memory_batch_repository(db)
    repo.save_settings(scope, expected_version=0, expected_profile_version=0, ai_enabled=True,
        shutdown_enabled=True, schedule_enabled=False, local_time="22:30", consent_version=MEMORY_CONSENT_VERSION,
        model_id="gemini-3.1-flash-lite", idempotency_key="modern-settings", now=now)
    setting = memory.get_scope_setting(scope)
    epoch = db.scalar(select(MemoryActivationEpoch).where(MemoryActivationEpoch.scope_setting_id == setting.id,
        MemoryActivationEpoch.scope_version == setting.version))
    pairs = [(MemorySourceTypeV1.CHAT_MESSAGE, str(done.committed_assistant_message_id))]
    for i in range(posts):
        db.add(Post(id=f"modern-post-{i}", world_id=scope.world_id, author_world_character_id=scope.subject_world_character_id,
            author_name="subject", title=f"Original post {i}", body=f"Original public activity {i}", created_at=now))
        pairs.append((MemorySourceTypeV1.POST, f"modern-post-{i}"))
    db.flush()
    writer = MemoryWriteLifecycleService(memory, source_evidence_reader(db))
    candidates, cutoff = [], 0
    for kind, source in pairs:
        candidate = writer.propose_candidate(scope=scope, source_type=kind, source_id=source,
            memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT).candidate
        candidates.append(candidate.id)
        row = MemorySourceDelivery(scope_setting_id=setting.id, epoch_id=epoch.id, source_type=kind.value,
            source_id=source, state="delivered", candidate_id=candidate.id, captured_at=now)
        db.add(row); db.flush(); cutoff = row.sequence
    job_id = repo.enqueue(scope_setting_id=setting.id, candidate_ids=tuple(candidates), cutoff=cutoff,
        trigger="shutdown", now=now, generation_policy="activity32")
    db.commit()
    batch = repo.claim(lease_token="modern-lease", now=now)
    db.commit()
    assert batch is not None and batch.job_id == job_id and batch.policy_version == ACTIVITY_POLICY_VERSION
    return repo, batch, now, key_args


class Selector:
    def __init__(self, *, during=None):
        self.calls, self.bundles, self.during = 0, [], during
    def validate_bundle(self, bundle):
        pass
    async def select(self, bundle, *, timeout):
        self.calls += 1; self.bundles.append(bundle)
        if self.during:
            self.during()
        selected = next(f"S{i}" for i, value in enumerate(bundle.new_units, 1) if value.kind != "chat_turn")
        return EpisodeSelection((EpisodeProposal("Original public experience", (selected,)),),
            tuple(f"S{i}" for i in range(1, len(bundle.new_units) + 1) if f"S{i}" != selected))


def test_mixed_32_one_call_skipped_private_inputs_still_limit_every_saved_episode(response_session, deny_external_network):
    db = response_session
    repo, batch, now, _ = prepare(db)
    selector = Selector()
    assert asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda frozen: selector, timeout=10, clock=lambda: now)) == "memory_selection_completed"
    assert selector.calls == 1 and len(selector.bundles[0].activities) == 32
    item = db.scalar(select(MemoryItem))
    restriction = db.get(MemoryEpisodeRestriction, item.id)
    assert restriction.mode == "private_thread" and item.thread_id == restriction.thread_id
    assert len(json.loads(restriction.sources_json)) == 33
    assert db.scalar(select(func.count(MemoryCandidate.id)).where(MemoryCandidate.status == "pending")) == 0
    work, = SqlAlchemyEpisodeWork(db).list(job_id=batch.job_id, setting=batch.setting)
    assert work.calls == 1 and work.state == "completed"
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db))
    assert len(packets.read(scope=batch.setting.scope, item_ids=(item.id,), now=now)) == 1
    # Even an unused public input belongs to the immutable access intersection.
    db.get(Post, "modern-post-30").deleted_at = now
    db.commit()
    assert packets.read(scope=batch.setting.scope, item_ids=(item.id,), now=now) == ()
    assert db.get(MemoryItem, item.id).summary == "Original public experience"


def test_key_rotation_while_selector_waits_keeps_admitted_revision(response_session, deny_external_network):
    db = response_session
    repo, batch, now, key_args = prepare(db)
    def rotate():
        world_credentials.save(db, **key_args, data=WorldCredentialWrite(expected_revision=1, provider="google",
            model="gemini-3.1-flash-lite", thinking_level="high", api_key="rotated-world-memory-key"))
        db.commit()
    selector = Selector(during=rotate)
    code = asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda frozen: selector, timeout=10, clock=lambda: now))
    assert code == "memory_selection_completed" and selector.calls == 1
    assert db.scalar(select(func.count(MemoryItem.id))) == 1
    assert world_credentials.resolve(db, **key_args, revision=1).reveal() == "synthetic-world-memory-key"


def test_split_public_leaf_retains_private_root_and_every_root_source(response_session, deny_external_network):
    db = response_session
    repo, batch, now, _ = prepare(db)
    class SplitThenSave:
        calls = 0
        def validate_bundle(self, bundle):
            pass
        async def select(self, bundle, *, timeout):
            self.calls += 1
            if self.calls == 1:
                return EpisodeSelection((), (), needs_split=True)
            return EpisodeSelection((EpisodeProposal(f"Split experience {self.calls}", ("S1",)),),
                tuple(f"S{i}" for i in range(2, len(bundle.new_units) + 1)))
    selector = SplitThenSave()
    assert asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda b: selector,
        timeout=10, clock=lambda: now)) == "memory_selection_completed"
    assert selector.calls == 3
    items = list(db.scalars(select(MemoryItem)))
    assert len(items) == 2
    restrictions = [db.get(MemoryEpisodeRestriction, item.id) for item in items]
    assert all(row.mode == "private_thread" and len(json.loads(row.sources_json)) == 33 for row in restrictions)
    assert len({item.thread_id for item in items}) == 1 and items[0].thread_id is not None
    db.get(Post, "modern-post-30").deleted_at = now; db.commit()
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db))
    assert packets.read(scope=batch.setting.scope, item_ids=tuple(item.id for item in items), now=now) == ()


def test_explicit_key_revoke_during_selector_rejects_late_result(response_session, deny_external_network):
    db = response_session
    repo, batch, now, key_args = prepare(db)
    def revoke():
        world_credentials.delete(db, **key_args, expected_revision=1)
        db.commit()
    selector = Selector(during=revoke)
    code = asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda frozen: selector, timeout=10, clock=lambda: now))
    assert code != "memory_selection_completed" and selector.calls == 1
    assert db.scalar(select(func.count(MemoryItem.id))) == 0
    assert db.scalar(select(func.count(MemoryCandidate.id)).where(MemoryCandidate.status == "pending")) == 32


def test_sqlite_960_turns_cross_every_page_bound_with_160_context_refs(response_session, deny_external_network):
    from hashlib import sha256
    from app.domains.chat.models import ChatResponseRequest, MessageMessage, ChatMessageThought
    from app.domains.chat.contracts import build_request_scope_hash
    from app.runtime.memory.episode_job_inputs import build_episode_job_inputs
    db = response_session
    repo, initial, now, _ = prepare(db, posts=0)
    first = SkipAll()
    assert asyncio.run(run_episode_batch(repo, initial, provider_factory=lambda b: first,
        timeout=10, clock=lambda: now)) == "memory_selection_completed"
    original = db.scalar(select(ChatResponseRequest))
    question = db.get(MessageMessage, original.user_message_id)
    answer = db.get(MessageMessage, original.committed_assistant_message_id)
    thought = db.get(ChatMessageThought, answer.id)
    values = lambda row: {column.name: getattr(row, column.name) for column in row.__table__.columns}
    request_values, question_values, answer_values, thought_values = map(values, (original, question, answer, thought))
    assistants = [answer.id]
    for n in range(1, 965):
        q = MessageMessage(**{**question_values, "id": None, "content": f"User raw {n} 🦜", "created_at": now})
        a = MessageMessage(**{**answer_values, "id": None, "content": f"Assistant raw {n} 日本語", "created_at": now})
        db.add_all([q, a]); db.flush()
        request_id = f"scale-request-{n}"
        db.add(ChatResponseRequest(**{**request_values, "request_id": request_id,
            "user_message_id": q.id, "committed_assistant_message_id": a.id,
            "response_slot_id": f"scale-slot-{n}", "idempotency_key": f"scale-idempotency-{n}",
            "generation_id": f"scale-generation-{n}", "request_scope_hash": build_request_scope_hash(
                owner_id=initial.setting.scope.owner_id, world_id=initial.setting.scope.world_id,
                thread_id=original.thread_id, user_message_id=q.id, requester_world_character_id="response-requester",
                responding_world_character_id=initial.setting.scope.subject_world_character_id)}))
        db.flush()
        db.add(ChatMessageThought(**{**thought_values, "message_id": a.id, "request_id": request_id,
            "source_digest": sha256(a.content.encode()).hexdigest(), "thought_text": f"Own thought {n} 한국어"}))
        assistants.append(a.id)
    db.flush()
    epoch = db.scalar(select(MemoryActivationEpoch).where(MemoryActivationEpoch.scope_setting_id == initial.setting.id,
        MemoryActivationEpoch.scope_version == initial.setting.version))
    writer = MemoryWriteLifecycleService(repo.memory, source_evidence_reader(db))
    candidate_ids = []
    for identity in assistants[5:]:
        candidate = writer.propose_candidate(scope=initial.setting.scope, source_type=MemorySourceTypeV1.CHAT_MESSAGE,
            source_id=str(identity), memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT).candidate
        candidate_ids.append(candidate.id)
        db.add(MemorySourceDelivery(scope_setting_id=initial.setting.id, epoch_id=epoch.id,
            source_type="CHAT_MESSAGE", source_id=str(identity), state="delivered", candidate_id=candidate.id, captured_at=now))
    db.flush()
    cutoff = db.scalar(select(func.max(MemorySourceDelivery.sequence)))
    from app.domains.memory.service.batch_preparation import enqueue_scope
    from app.runtime.memory.batch_preparation import build_preparation_dependencies
    assert enqueue_scope(db, dependencies=build_preparation_dependencies(generation_policy="activity32"),
        scope_setting_id=initial.setting.id, trigger="shutdown", now=now, cutoff=cutoff) == 1
    db.commit()
    batch = repo.claim(lease_token="scale-lease", now=now); db.commit()
    assert len(batch.candidates) == 960
    selector = SkipAll()
    assert asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda b: selector,
        timeout=10, clock=lambda: now)) == "memory_selection_completed"
    bundle, = selector.bundles
    assert selector.calls == 1 and len(bundle.activities) == 32 and len(bundle.new_units) == 960
    assert sum(len(a.context_keys) for a in bundle.activities) == 160
    assert all(len(a.unit_keys) == 30 and len(a.context_keys) == 5 for a in bundle.activities)
    assert len({m.source_id for u in bundle.new_units for m in u.members}) == 1920
    assert all(u.thought.text.startswith("Own thought") for u in bundle.new_units)
    assert {m.source_id for u in bundle.new_units for m in u.members if m.role == "assistant"} == set(map(str, assistants[5:]))
    assert len(bundle.prior_episodes) <= 8
    assert repo.claim(lease_token="scale-resume", now=now) is None
    assert db.scalar(select(func.count(MemoryCandidate.id)).where(MemoryCandidate.status == "pending")) == 0


def test_pause_settle_previous_admission_policy_and_restore_without_schema_downgrade(response_session, deny_external_network):
    db = response_session
    repo, batch, now, _ = prepare(db)
    current = Selector()
    assert asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda b: current,
        timeout=10, clock=lambda: now)) == "memory_selection_completed"
    item = db.scalar(select(MemoryItem)); original_restriction = db.get(MemoryEpisodeRestriction, item.id).sources_json
    assert repo.claim(lease_token="paused-with-no-new-admission", now=now) is None
    epoch = db.scalar(select(MemoryActivationEpoch).where(MemoryActivationEpoch.scope_setting_id == batch.setting.id,
        MemoryActivationEpoch.scope_version == batch.setting.version))
    writer = MemoryWriteLifecycleService(repo.memory, source_evidence_reader(db))
    for n, policy in enumerate(("episode_v1", "activity32")):
        post_id = f"policy-restored-{n}"
        db.add(Post(id=post_id, world_id=batch.setting.scope.world_id,
            author_world_character_id=batch.setting.scope.subject_world_character_id, author_name="subject",
            title="Policy transition fixture", body="Preserved public original", created_at=now)); db.flush()
        candidate = writer.propose_candidate(scope=batch.setting.scope, source_type=MemorySourceTypeV1.POST,
            source_id=post_id, memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT).candidate
        delivery = MemorySourceDelivery(scope_setting_id=batch.setting.id, epoch_id=epoch.id,
            source_type="POST", source_id=post_id, state="delivered", candidate_id=candidate.id, captured_at=now)
        db.add(delivery); db.flush()
        repo.enqueue(scope_setting_id=batch.setting.id, candidate_ids=(candidate.id,), cutoff=delivery.sequence,
            trigger="shutdown", now=now, generation_policy=policy); db.commit()
        restored = repo.claim(lease_token=f"restored-{n}", now=now); db.commit()
        assert restored.credential_id == batch.credential_id and restored.credential_revision == 1
        assert restored.policy_version == ("episode-selection.v1" if n == 0 else ACTIVITY_POLICY_VERSION)
        skip = SkipAll()
        assert asyncio.run(run_episode_batch(repo, restored, provider_factory=lambda b: skip,
            timeout=10, clock=lambda: now)) == "memory_selection_completed"
        assert skip.calls == 1 and repo.claim(lease_token=f"after-settle-{n}", now=now) is None
    assert current.calls == 1 and db.get(MemoryEpisodeRestriction, item.id).sources_json == original_restriction
    assert db.get(MemoryItem, item.id).summary == "Original public experience"
    assert db.scalar(select(func.count(MemoryItem.id))) == 1
