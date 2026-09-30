"""Connect Chat's attachment lifecycle to the common pixel-analysis service."""
import json
from app.domains.chat.models import MessageAttachment
from app.domains.chat.exceptions import MessageValidationError
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.chat.contracts.image_evidence import ChatImageEvidence, visible_context


def configure_chat_image_services(app):
    """Bind app-owned image collaborators after the base Chat services exist."""
    from app.domains.chat.service.generation import GenerationService
    from app.domains.chat.service.evidence import EvidenceService
    from app.runtime.chat import generation_workflows, evidence_reads

    images = ChatImageAttachments(app.state.media_runtime)
    threads = app.state.chat_thread_service
    settings = app.state.chat_settings_service
    app.state.chat_generation_service = GenerationService(
        threads, settings, generation_workflows, images=images)
    app.state.chat_evidence_service = EvidenceService(
        threads, evidence_reads, image_reader=images.asset_current)


class ChatImageAttachments:
    def __init__(self, media):
        self.media = media

    def existing_asset(self, db, message_id):
        row = db.get(MessageAttachment, message_id)
        return row.asset_id if row else None

    def assert_current(self, db, owner_id, thread_id, message_id, evidence):
        if evidence is None:
            return
        row = db.get(MessageAttachment, message_id, populate_existing=True)
        if row is None or row.asset_id != evidence.asset_id or row.interpretation_id != evidence.interpretation_id:
            raise ImagePreparationError("chat_attachment_changed")
        asset, _ = self.media.assets.read(db, owner_id=owner_id, asset_id=row.asset_id, digest=evidence.asset_hash)
        if asset.scope_kind != "thread" or asset.scope_id != thread_id or asset.revision != evidence.asset_revision:
            raise ImagePreparationError("chat_attachment_changed")

    def previous_context(self, db, owner_id, thread_id, message):
        row = db.get(MessageAttachment, message.id)
        if row is None or not row.snapshot_json:
            return message.content
        try:
            value = json.loads(row.snapshot_json)
            evidence = self.evidence(owner_id, thread_id, value)
            self.assert_current(db, owner_id, thread_id, message.id, evidence)
        except (ImagePreparationError, InvalidProfileMediaError, ValueError):
            return message.content
        text = message.content + "\n<untrusted_image_observation>" + evidence.context + "</untrusted_image_observation>"
        return text if len(text) <= 4000 else message.content

    def asset_current(self, db, owner_id, thread_id, locator):
        try:
            asset, _ = self.media.assets.read(db, owner_id=owner_id, asset_id=locator.get("source_id"))
            return asset.scope_kind == "thread" and asset.scope_id == thread_id and locator.get("source_revision") == f"{asset.revision}:{asset.content_hash}"
        except Exception:
            return False

    def accept(self, db, owner_id, thread_id, message_id, asset_id):
        asset = self.media.assets.owned(db, owner_id=owner_id, asset_id=asset_id,
            scope_kind="thread", scope_id=thread_id)
        state = self.media.interpretation.preflight(db, owner_id, asset_id)
        if not state["allowed"]:
            raise MessageValidationError(state["reason"])
        self.media.assets.attach(db, owner_id=owner_id, asset_id=asset.id, scope_kind="thread", scope_id=thread_id)
        db.add(MessageAttachment(message_id=message_id, asset_id=asset.id))
        db.flush()

    async def observation(self, db, owner_id, thread_id, message_id):
        row = db.get(MessageAttachment, message_id)
        if row is None:
            return None
        asset = self.media.assets.owned(db, owner_id=owner_id, asset_id=row.asset_id,
            scope_kind="thread", scope_id=thread_id)
        if row.snapshot_json:
            value = json.loads(row.snapshot_json)
            if value.get("asset_revision") != asset.revision or value.get("asset_hash") != asset.content_hash:
                raise ImagePreparationError("chat_image_changed")
            return value
        asset_id = asset.id
        db.rollback()
        analysis = await self.media.interpretation.interpret(db, owner_id, asset_id, retry_failed=True)
        asset = self.media.assets.owned(db, owner_id=owner_id, asset_id=asset_id,
            scope_kind="thread", scope_id=thread_id)
        value = {"source": "actual_image_analysis", "asset_id": asset.id, "asset_revision": asset.revision,
            "asset_hash": asset.content_hash, "interpretation_id": analysis.id,
            "analysis": json.loads(analysis.result_json)}
        row = db.get(MessageAttachment, message_id, populate_existing=True)
        row.interpretation_id, row.snapshot_json = analysis.id, json.dumps(value, ensure_ascii=False)
        db.commit()
        return value

    @staticmethod
    def message_context(content, observation):
        if observation is None:
            return content
        return content if content.strip() else visible_context(observation["analysis"])

    @staticmethod
    def evidence(owner_id, thread_id, observation):
        if observation is None:
            return None
        return ChatImageEvidence(owner_id, thread_id, observation["asset_id"], observation["asset_revision"],
            observation["asset_hash"], observation["interpretation_id"], visible_context(observation["analysis"]))
