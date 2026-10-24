"""Capture final Chat delivery and participate before its existing checkpoint."""
from datetime import UTC, datetime
from hashlib import sha256
from app.domains.chat.models import MessageMessage
from app.core.calendar import utc_instant

from app.domains.chat.contracts.evidence_bundle import EvidenceLocatorKind
from app.domains.chat.contracts.today_sns_activity import TodaySnsSnapshotChangedError
from app.domains.chat.exceptions import ChatSituationEvidenceError
from app.domains.chat.service.today_situation_delivery import selected_event_entries
from app.domains.relationships.contracts.source_event_evidence import SourceEventBasis
from app.domains.memory.exceptions import SituationSourceAdmissionError, SituationDeliveryBindingError
from app.domains.memory.contracts.activity_situation import (
    DeliveredInputManifest, CommittedActivityResult, CommittedEffect, stable_digest,
    FinalDeliveredFragment, RelationshipDeliveryBasis,
)
from app.domains.relationships.policies.social_context_validation import facts_digest
from app.domains.memory.service.situation_policy import restore
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.policies.situation_output import parse_description
from app.runtime.memory.situation_sources import SituationSources


class ChatSituationMemory:
    def __init__(self, session):
        self.session = session

    def freeze(self, command, bundle, payload):
        # Capturing delivery is read-only and never flushes a caller's pending
        # writes. Each invocation owns fresh, bounded canonical facts.
        with self.session.no_autoflush:
            return self._freeze(command, bundle, payload)

    def _freeze(self, command, bundle, payload):
        snapshot = restore(command.request.node_state.get("_situation_policy"))
        if snapshot is None:
            raise ValueError("situation_snapshot_required")
        sources = SituationSources(self.session)
        selected = selected_event_entries(command, bundle, payload, snapshot.scope)
        references = {index: SourceEventBasis(entry.source_id, entry.event_type, entry.actor_id,
            entry.counterpart_id, entry.source_post_id, entry.target_post_id,
            entry.root_post_id, entry.parent_post_id, entry.source_revision) for index, entry in selected.items()}
        if references:
            # Fresh populate_existing reads must not overwrite uncommitted
            # caller edits. The response UoW checkpoints before this boundary;
            # an unfinished edit must be resolved by its owner, never here.
            if self.session.dirty or self.session.deleted:
                raise ChatSituationEvidenceError("situation_today_pending_changes")
            message = self.session.get(MessageMessage, command.request.user_message_id, populate_existing=True)
            if message is None or message.thread_id != command.request.thread_id:
                raise ChatSituationEvidenceError("situation_today_thread_invalid")
        facts = sources.prepare_manual_events(ref.event_id for ref in references.values()) if references else None
        entries = []
        payload_digest = stable_digest(payload)
        def add(kind, identifier, delivered, path, *, role="core", basis=None, event_reference=None):
            try:
                entry = sources.describe(snapshot.scope, kind=kind, identifier=identifier,
                    delivered=delivered, path=path, role=role, ordinal=len(entries),
                    target=command.request.response_slot_id if role == "core" else None,
                    private_thread=command.request.thread_id, relationship_basis=basis,
                    manual_event_reference=event_reference, capture_validation=facts,
                    delivery=FinalDeliveredFragment.capture(payload, path=path, text=delivered, payload_digest=payload_digest))
            except SituationDeliveryBindingError as exc:
                raise ChatSituationEvidenceError("situation_today_binding_invalid") from exc
            except SituationSourceAdmissionError as exc:
                raise TodaySnsSnapshotChangedError("situation_today_source_changed") from exc
            entries.append(entry)
        latest = payload["latest_user_message"]
        if isinstance(latest, dict) and latest["content"] != f"{latest['name']}: {command.preflight.user_message}":
            raise ValueError("situation_chat_presentation_changed")
        add("CHAT_MESSAGE", str(command.request.user_message_id), command.preflight.user_message,
            "/latest_user_message/content" if isinstance(latest, dict) else "/latest_user_message")
        for index, context in enumerate(command.response_context):
            if context.source_id is None:
                raise ValueError("situation_context_identity_missing")
            presented = payload["recent_context"][index]
            expected = f"{presented['name']}: {context.content}" if "name" in presented else context.content
            if presented["content"] != expected:
                raise ValueError("situation_chat_presentation_changed")
            add("CHAT_MESSAGE", context.source_id, context.content, f"/recent_context/{index}/content")
        for index, item in enumerate(bundle.items):
            locator = item.locator
            if locator is None:
                raise ValueError("situation_evidence_identity_missing")
            if locator.kind is EvidenceLocatorKind.MEMORY_ITEM:
                add("MEMORY_ITEM", locator.source_id, payload["frozen_evidence"]["items"][index]["text"],
                    f"/frozen_evidence/items/{index}/text", role="prior")
            elif locator.kind is EvidenceLocatorKind.CANONICAL_SOURCE:
                add(locator.source_type, locator.source_id, payload["frozen_evidence"]["items"][index]["text"],
                    f"/frozen_evidence/items/{index}/text", role="background", event_reference=references.get(index))
            elif locator.kind in {EvidenceLocatorKind.GRAPH_RELATIONSHIP, EvidenceLocatorKind.IMAGE_ASSET}:
                basis = None
                if locator.kind is EvidenceLocatorKind.GRAPH_RELATIONSHIP:
                    if locator.relationship_facts_digest is None or locator.relationship_view_version is None:
                        raise ValueError("situation_relationship_prepared_basis_missing")
                    basis = RelationshipDeliveryBasis(locator.source_id, locator.actor_world_character_id,
                        locator.target_world_character_id, int(locator.source_revision),
                        locator.relationship_view_version, locator.relationship_facts_digest)
                add("RELATIONSHIP" if locator.kind is EvidenceLocatorKind.GRAPH_RELATIONSHIP else "IMAGE_ASSET",
                    locator.source_id, payload["frozen_evidence"]["items"][index]["text"], f"/frozen_evidence/items/{index}/text", role="background", basis=basis)
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
                relationship = item.relationship
                basis = RelationshipDeliveryBasis(relationship.relationship_state_id,
                    relationship.actor_world_character_id, relationship.target_world_character_id,
                    relationship.relationship_version, relationship.view_version, facts_digest(item))
                add("RELATIONSHIP", item.relationship.relationship_state_id,
                    payload["social_context"]["context"], "/social_context/context", role="background", basis=basis)
        return DeliveredInputManifest(f"chat:{command.request.request_scope_hash}", snapshot,
            payload_digest, tuple(entries), private_thread_id=command.request.thread_id, version=2)

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
