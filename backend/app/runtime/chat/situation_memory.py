"""Capture final Chat delivery and participate before its existing checkpoint."""
from datetime import UTC, datetime
from hashlib import sha256
from app.domains.chat.models import MessageMessage
from app.core.calendar import utc_instant

from app.domains.chat.contracts.evidence_bundle import EvidenceLocatorKind
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, CommittedActivityResult, CommittedEffect, stable_digest
from app.domains.memory.service.situation_policy import restore
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.policies.situation_output import parse_description
from app.runtime.memory.situation_sources import SituationSources


class ChatSituationMemory:
    def __init__(self, session):
        self.session = session

    def freeze(self, command, bundle, payload):
        snapshot = restore(command.request.node_state.get("_situation_policy"))
        if snapshot is None:
            raise ValueError("situation_snapshot_required")
        sources = SituationSources(self.session)
        entries = []
        def add(kind, identifier, delivered, path, *, role="core"):
            entries.append(sources.describe(snapshot.scope, kind=kind, identifier=identifier,
                delivered=delivered, path=path, role=role, ordinal=len(entries),
                target=command.request.response_slot_id if role == "core" else None,
                private_thread=command.request.thread_id))
        add("CHAT_MESSAGE", str(command.request.user_message_id), payload["latest_user_message"], "/latest_user_message")
        for index, context in enumerate(command.response_context):
            if context.source_id is None:
                raise ValueError("situation_context_identity_missing")
            add("CHAT_MESSAGE", context.source_id, payload["recent_context"][index]["content"], f"/recent_context/{index}/content")
        for index, item in enumerate(bundle.items):
            locator = item.locator
            if locator is None:
                raise ValueError("situation_evidence_identity_missing")
            if locator.kind is EvidenceLocatorKind.MEMORY_ITEM:
                add("MEMORY_ITEM", locator.source_id, payload["frozen_evidence"]["items"][index]["text"],
                    f"/frozen_evidence/items/{index}/text", role="prior")
            elif locator.kind is EvidenceLocatorKind.CANONICAL_SOURCE:
                add(locator.source_type, locator.source_id, payload["frozen_evidence"]["items"][index]["text"],
                    f"/frozen_evidence/items/{index}/text", role="background")
            elif locator.kind in {EvidenceLocatorKind.GRAPH_RELATIONSHIP, EvidenceLocatorKind.IMAGE_ASSET}:
                add("RELATIONSHIP" if locator.kind is EvidenceLocatorKind.GRAPH_RELATIONSHIP else "IMAGE_ASSET",
                    locator.source_id, payload["frozen_evidence"]["items"][index]["text"], f"/frozen_evidence/items/{index}/text", role="background")
                if locator.kind is EvidenceLocatorKind.IMAGE_ASSET:
                    image = command.image_evidence
                    if image is None or image.asset_id != locator.source_id:
                        raise ValueError("situation_image_interpretation_missing")
                    add("IMAGE_INTERPRETATION", image.interpretation_id,
                        payload["frozen_evidence"]["items"][index]["text"],
                        f"/frozen_evidence/items/{index}/text", role="background")
            else:
                # Non-source evidence requires its owner-specific delivery adapter.
                raise ValueError("situation_evidence_kind_unsupported")
        if command.social_snapshot is not None:
            for item in command.social_snapshot.items:
                add("RELATIONSHIP", item.relationship.relationship_state_id,
                    payload["social_context"]["context"], "/social_context/context", role="background")
        return DeliveredInputManifest(f"chat:{command.request.request_scope_hash}", snapshot,
            stable_digest(payload), tuple(entries), private_thread_id=command.request.thread_id)

    def admit(self, command, committed, response):
        if command.request.node_state.get("_situation_policy") is None:
            return
        if restore(command.request.node_state["_situation_policy"]) is None:
            return
        if response.situation_manifest is None or committed.committed_assistant_message_id is None:
            raise ValueError("situation_chat_result_missing")
        identifier = str(committed.committed_assistant_message_id)
        self.session.flush()
        result_source = SituationSources(self.session).describe(response.situation_manifest.snapshot.scope,
            kind="CHAT_MESSAGE", identifier=identifier, delivered=response.text,
            path="/committed_result/text", role="committed_result", ordinal=len(response.situation_manifest.sources),
            target=command.request.response_slot_id, private_thread=command.request.thread_id)
        # The result is linked separately from sources that the model actually saw.
        result = CommittedActivityResult(command.request.response_slot_id, "chat", command.request.response_slot_id,
            ("reply",), (CommittedEffect("reply", "CHAT_MESSAGE", identifier, "succeeded"),),
            response.situation_output_digest or "", sha256(response.text.encode()).hexdigest(),
            utc_instant(self.session.get(MessageMessage, int(identifier)).created_at), counterpart_id=command.preflight.requester_world_character_id,
            thought_reference=f"chat:{identifier}" if response.activity_thought else None, result_sources=(result_source,))
        draft = response.situation_draft or parse_description(None, target_key=result.target_key)
        admit(self.session, manifest=response.situation_manifest, draft=draft, result=result, now=datetime.now(UTC))
