"""A real user reply locator survives Chat generation and atomic finalization."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from app.contracts.environment import EnvironmentSnapshot
from app.domains.chat.contracts.evidence_bundle import EvidenceItem, EvidenceKind, EvidenceLocator, EvidenceLocatorKind
from app.domains.chat.contracts.response_request import RetrievalAxis, RetrievalOutcome
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.service.situation_policy import capture
from app.domains.social.contracts.writes import OwnerReplyCommand
from app.integrations.llm.character_response_generator import _user_payload
from app.runtime.chat.situation_memory import ChatSituationMemory
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork


def test_chat_commits_real_manual_reply_evidence_and_rechecks_access(response_session, deny_external_network):
    db = response_session
    db.get(f.models.WorldCharacter, "p-responding").activity_runtime_mode = "routine_resident_v1"
    db.add(f.models.CharacterActiveWorld(character_id="p-requester-character", world_character_id="p-requester",
        selected_at=datetime.now(UTC), idempotency_key="chat-reply-active-world", version=1))
    root = f.models.Post(id="chat-reply-root", world_id="p-world", author_name="Character",
        author_character_id="p-responding-character", author_world_character_id="p-responding",
        title="Experiment", body="I am trying a new experiment.")
    db.add(root); db.commit()
    write = SqlAlchemySocialWriteUnitOfWork(db).create_owner_reply(OwnerReplyCommand(
        world_id="p-world", current_user_id="p-owner", target_post_id=root.id,
        idempotency_key="chat-manual-reply", body="Try a cooler temperature."))
    reply = db.scalars(select(f.models.Post).where(f.models.Post.reply_to_post_id == root.id)).one()
    scope, route = MemoryScope("p-owner", "p-world", "p-responding"), f.RetrievalRoute.CANONICAL
    settings = MemoryScopeService(memory_repository(db))
    setting = settings.get_or_create(scope)
    settings.update(scope, expected_version=setting.version, enabled=True, retention_days=180)
    record = f._request(db, route)
    snapshot = capture(db, owner_id=scope.owner_id, world_id=scope.world_id,
        actor_id=scope.subject_world_character_id, environment=EnvironmentSnapshot(memory_search_locale="en-US"),
        policy="activity_situation")
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    row.node_state_json = json.dumps({**json.loads(row.node_state_json), "_situation_policy": snapshot})
    db.commit()
    command = f._command(f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id))

    class ReplyEvidence(EvidenceBundleAssembler):
        def canonical(self, *, request_scope_hash, result):
            # Synthetic retrieval result; all delivery, canonical validation and
            # response finalization below use the actual product implementations.
            return self._bundle(request_id=result.request_id, request_scope_hash=request_scope_hash,
                route=route, outcome=RetrievalOutcome.MEMORY_USED, candidates=(EvidenceItem(
                    "reply-evidence", EvidenceKind.CANONICAL_SOURCE, reply.body, None, (RetrievalAxis.CANONICAL,),
                    locator=EvidenceLocator(EvidenceLocatorKind.CANONICAL_SOURCE, reply.id, source_type="REPLY")),))

    class Generator(f._Generator):
        async def generate(self, request):
            result = await super().generate(request)
            return replace(result, situation_manifest=request.situation_manifest_factory(_user_payload(request)),
                situation_draft=parse_description("We discussed the suggestion in the earlier comment.",
                    target_key=request.situation_target), situation_output_digest=sha256(result.text.encode()).hexdigest())

    generator = Generator()
    workflow = f._workflow(db, route, generator)
    workflow._evidence, workflow._situation_memory = ReplyEvidence(), ChatSituationMemory(db)
    events = asyncio.run(f._collect(workflow.run(command)))
    receipt = db.scalars(select(MemorySituationReceipt)).one()
    assert receipt.state == "pending", (receipt.error_code, events)
    assert len(generator.requests) == 1
    manifest = restore_context(db, receipt)
    source = next(entry for entry in manifest.sources if entry.source_type == "REPLY")
    assert source.source_id == reply.id
    assert source.source_id != write.delivery.inbox_candidate_id
    assert any(entry.source_type == "CHAT_MESSAGE" for entry in manifest.sources)
    assert db.scalars(select(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")).one()
    assert SituationSources(db).validate(manifest, source, now=datetime.now(UTC)).state == "available"
    reply.visibility = "private"
    db.commit(); db.expire_all()
    assert SituationSources(db).validate(manifest, source, now=datetime.now(UTC)).state != "available"
