import asyncio
import json
from dataclasses import replace
from hashlib import sha256
import pytest
from sqlalchemy import event, func, select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from app.contracts.environment import EnvironmentSnapshot
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.service.situation_policy import capture
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.runtime.memory.composition import memory_repository
from app.runtime.chat.situation_memory import ChatSituationMemory
from app.integrations.llm.character_response_generator import _user_payload


@pytest.mark.parametrize("invalid,fail_insert", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("with_image", [False, True])
def test_real_chat_finalize_receipt_is_atomic_and_auxiliary_errors_do_not_lose_reply(response_session, invalid, fail_insert, with_image):
    db = response_session
    route = f.RetrievalRoute.CURRENT_CONTEXT
    scope = MemoryScope("p-owner", "p-world", "p-responding")
    service = MemoryScopeService(memory_repository(db))
    setting = service.get_or_create(scope)
    service.update(scope, expected_version=setting.version, enabled=True, retention_days=180)
    record = f._request(db, route)
    snapshot = capture(db, owner_id=scope.owner_id, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
        environment=EnvironmentSnapshot(memory_search_locale="ko-KR"), policy="activity_situation")
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    row.node_state_json = json.dumps({**json.loads(row.node_state_json), "_situation_policy": snapshot})
    db.commit()
    record = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    command = f._command(record)
    if with_image:
        from app.domains.chat.contracts.image_evidence import ChatImageEvidence, visible_context
        from app.domains.media.models import MediaAsset, ImageInterpretation
        analysis = {"description": "A sign.", "visible_text": ["OPEN"], "uncertainties": []}
        asset = MediaAsset(id="chat-image", owner_id=scope.owner_id, scope_kind="thread", scope_id="p-thread",
            storage_key="synthetic-image", content_type="image/png", content_hash="a"*64,
            byte_size=1, width=1, height=1, revision=1)
        db.add(asset)
        db.flush()
        interpretation = ImageInterpretation(id="chat-analysis", cache_key="b"*64, asset_id=asset.id,
            owner_id=scope.owner_id, scope_key="thread:p-thread", asset_revision=1, model="fixture",
            thinking_level="medium", credential_revision=1, status="ready", description=analysis["description"],
            result_json=json.dumps(analysis))
        db.add(interpretation)
        db.commit()
        command = replace(command, image_evidence=ChatImageEvidence(scope.owner_id, "p-thread", asset.id,
            1, asset.content_hash, interpretation.id, visible_context(analysis)))
    class Generator(f._Generator):
        async def generate(self, request):
            response = await super().generate(request)
            return replace(response, situation_manifest=request.situation_manifest_factory(_user_payload(request)),
                situation_draft=parse_description(None if invalid else "평범한 하루의 안부를 나누었다.", target_key=request.situation_target),
                situation_output_digest=sha256(response.text.encode()).hexdigest())
    workflow = f._workflow(db, route, Generator())
    workflow._situation_memory = ChatSituationMemory(db)
    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO memory_situation_receipts"):
            raise RuntimeError("injected_receipt_failure")
    if fail_insert:
        event.listen(db.bind, "before_cursor_execute", fail)
    try:
        events = asyncio.run(f._collect(workflow.run(command)))
    finally:
        if fail_insert:
            event.remove(db.bind, "before_cursor_execute", fail)
    assistants = db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant"))
    receipts = list(db.scalars(select(MemorySituationReceipt)))
    assert len(receipts) == assistants == (0 if fail_insert else 1)
    if not fail_insert:
        assert receipts[0].state == ("blocked" if invalid else "pending")
        assert receipts[0].description_status == ("missing" if invalid else "valid")
        if with_image:
            from app.domains.memory.models.activity_situation import MemorySituationManifest
            from app.domains.memory.contracts.activity_situation import DeliveredInputManifest
            from app.runtime.memory.situation_sources import SituationSources
            from datetime import UTC, datetime
            row = db.get(MemorySituationManifest, receipts[0].manifest_id)
            manifest = DeliveredInputManifest.from_dict(row.payload)
            source = next(s for s in manifest.sources if s.source_type == "IMAGE_INTERPRETATION")
            assert source.role == "background" and source.source_id == interpretation.id
            reader = SituationSources(db)
            assert reader.validate(manifest, source, now=datetime.now(UTC)).state == "available"
            interpretation.result_json = json.dumps({**analysis, "visible_text": ["CLOSED"]})
            db.commit()
            assert reader.validate(manifest, source, now=datetime.now(UTC)).state == "changed"
