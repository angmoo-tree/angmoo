"""Real owner writes, Today reader and final Chat adapter; only transport is fake."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from chat import test_p8_l_p_evidence_response_streaming as f
from app.contracts.environment import EnvironmentSnapshot
from app.domains.chat.service.today_sns_activity import TodaySnsActivityAssembler
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.service.situation_policy import capture
from app.domains.social.contracts.writes import OwnerLikeCommand, OwnerPostCommand, OwnerReplyCommand
from app.integrations import direct_llm
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
from app.runtime.chat.situation_memory import ChatSituationMemory
from app.runtime.chat.today_sns_activity import SqlAlchemyTodaySnsSnapshotValidator
from app.runtime.memory.composition import memory_repository
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from app.runtime.social.today_activity import today_social_activity_reader


def prepare(db, *, transitions=(True,), enabled=True, route=f.RetrievalRoute.CURRENT_CONTEXT,
            include_today=True, nested=False, count=1, event_kind="like"):
    db.get(f.models.WorldCharacter, "p-responding").activity_runtime_mode = "routine_resident_v1"
    db.add(f.models.CharacterActiveWorld(character_id="p-requester-character", world_character_id="p-requester",
        selected_at=datetime.now(UTC), idempotency_key="today-like-active", version=1))
    posts = []
    for index in range(count):
        post = f.models.Post(id=f"today-root-{index}", world_id="p-world", author_name="Same name",
            author_character_id="p-responding-character", author_world_character_id="p-responding",
            title="Same title", body="같은 내용 🙂 é.", visibility="public",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        db.add(post)
        posts.append(post)
    db.commit()
    root = posts[0]
    if nested:
        for index in range(2):
            parent = posts[-1]
            reply = f.models.Post(id=f"today-reply-{index}", world_id="p-world", author_name="Same name",
                author_character_id="p-responding-character", author_world_character_id="p-responding",
                title="", body="Nested context.", visibility="public", reply_to_post_id=parent.id,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
            db.add(reply)
            db.commit()
            posts.append(reply)
    writer = SqlAlchemySocialWriteUnitOfWork(db)
    targets = posts[-1:] if nested else posts
    for post in targets:
        for liked in transitions:
            writer.set_owner_like(OwnerLikeCommand("p-world", "p-owner", post.id, liked))
            writer.set_owner_like(OwnerLikeCommand("p-world", "p-owner", post.id, liked))
    if event_kind == "reply":
        writer.create_owner_reply(OwnerReplyCommand("p-world", "p-owner", "today-owner-reply", root.id,
                                                    "A real owner comment."))
    elif event_kind == "post":
        writer.create_owner_post(OwnerPostCommand("p-world", "p-owner", "today-owner-post", "Owner note", "A public owner note."))
    social_events = list(db.scalars(select(f.models.SocialEvent)))
    scope = MemoryScope("p-owner", "p-world", "p-responding")
    settings = MemoryScopeService(memory_repository(db))
    setting = settings.get_or_create(scope)
    settings.update(scope, expected_version=setting.version, enabled=enabled, retention_days=180)
    record = f._request(db, route)
    policy = capture(db, owner_id=scope.owner_id, world_id=scope.world_id,
        actor_id=scope.subject_world_character_id,
        environment=EnvironmentSnapshot(memory_search_locale="en-US"), policy="activity_situation")
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    row.node_state_json = json.dumps({**json.loads(row.node_state_json), "_situation_policy": policy})
    db.commit()
    labels = {"p-responding": "Same name", "p-requester": "Same name"}
    snapshot = TodaySnsActivityAssembler(today_social_activity_reader(db)).assemble(
        owner_id=scope.owner_id, world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
        timezone="Asia/Seoul", character_labels=labels, now=datetime.now(UTC))
    record = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    command = replace(f._command(record), today_sns_snapshot=snapshot if include_today else None,
                      character_labels=labels)
    assembler = EvidenceBundleAssembler()
    bundle = assembler.with_today_sns(assembler.current_context(request_id=record.request_id,
        request_scope_hash=record.request_scope_hash), snapshot if include_today else None,
        user_message=command.preflight.user_message)
    payload = {"latest_user_message": command.preflight.user_message, "recent_context": [],
               "frozen_evidence": bundle.provider_payload()}
    return SimpleNamespace(db=db, scope=scope, setting=setting, command=command, record=record,
        snapshot=snapshot, bundle=bundle, payload=payload, events=social_events, posts=posts,
        root=root, post=posts[-1], labels=labels, route=route)


def execute(case, monkeypatch, *, transport_error=None, invalid_description=False, mutate_payload=None):
    calls, requests, manifests, errors = [], [], [], []
    async def transport(**kwargs):
        # SQLAlchemy may retain a logical read transaction; SQLite has no write
        # transaction across the provider await. Do not commit from the reader.
        assert not case.db.connection().connection.driver_connection.in_transaction
        calls.append(kwargs)
        if transport_error is not None:
            raise transport_error
        return direct_llm.DirectLlmResponse(text="A synthetic offline response.",
            parsed={"text": "A synthetic offline response.",
                    "situation_description": None if invalid_description else "We discussed today's public activity."},
            usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", transport)
    material = CredentialMaterial("synthetic", "google", "gemini-3.1-flash-lite", "synthetic",
                                  CredentialPurpose.MESSAGE_LLM, "synthetic-not-a-key")
    class Generator(DirectLlmCharacterResponseGenerator):
        async def generate(self, request):
            requests.append(request)
            if mutate_payload is not None:
                original = request.situation_manifest_factory
                def freeze(payload):
                    mutate_payload(payload)
                    return original(payload)
                request = replace(request, situation_manifest_factory=freeze)
            try:
                response = await super().generate(request)
                manifests.append(response.situation_manifest)
                return response
            except Exception as exc:
                errors.append(exc)
                raise
    workflow = f._workflow(case.db, case.route, Generator(material),
        today_snapshot_validator=SqlAlchemyTodaySnsSnapshotValidator(case.db, case.labels))
    workflow._situation_memory = ChatSituationMemory(case.db)
    events = asyncio.run(f._collect(workflow.run(case.command)))
    final = f.SqlAlchemyResponseLifecycleRepository(case.db).get_request(case.record.request_id)
    assistants = list(case.db.scalars(select(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")))
    receipts = list(case.db.scalars(select(MemorySituationReceipt)))
    return SimpleNamespace(events=events, final=final, assistants=assistants, receipts=receipts,
        calls=calls, requests=requests, manifests=manifests, errors=errors, workflow=workflow)
