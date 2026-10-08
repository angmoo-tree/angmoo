"""Current canonical source checks for delivered situations, including deletion."""
from hashlib import sha256

from app.domains.chat.models import MessageMessage, MessageThread
from app.domains.social.models.posts import Post
from app.domains.relationships.models.social import RelationshipState, ActivityProposal, SocialEvent
from app.domains.media.models import MediaAsset, ImageInterpretation
from app.domains.routines.models.plans import DailyActivityPlan, DailyActivityPlanItem
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry, stable_digest
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.contracts.situation_validation import SituationSourceAccess
from app.domains.memory.policies.situation_validation import delivered_evidence, historical_relationship
from app.domains.memory.policies.retrievability import item_retrievable
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.service.source_evidence import SqlAlchemyMemorySourceEvidenceReader
from app.runtime.memory import source_queries
from app.runtime.memory.scope_queries import read_scope_presence
from app.domains.memory.exceptions import MemoryScopeError
from app.runtime.memory.source_queries import block_id, active_participant_ids


class SituationSources:
    def __init__(self, session, *, reader=None):
        self.session = session
        self.reader = reader if reader is not None else SqlAlchemyMemorySourceEvidenceReader(session, queries=source_queries)

    def read_evidence(self, **values):
        return self.reader.read_evidence(**values)

    def validate_situation_source(self, manifest, source, **values):
        return self.validate(manifest, source, **values)

    def describe(self, scope, *, kind, identifier, delivered, path, role, ordinal, target=None,
                 private_thread=None, delivery=None, relationship_basis=None):
        if delivery is not None and (delivery.path != path or delivery.text != delivered):
            raise ValueError("situation_delivery_fragment_mismatch")
        if kind == "ROUTINE_ACTIVITY":
            row = self.session.get(DailyActivityPlanItem, identifier)
            plan = self.session.get(DailyActivityPlan, row.plan_id) if row else None
            if plan is None or plan.world_id != scope.world_id or plan.world_character_id != scope.subject_world_character_id:
                raise ValueError("situation_routine_scope_invalid")
            raw, digest, version, thread = delivered, routine_digest(row), "1", None
            actor, counterpart = scope.subject_world_character_id, None
        elif kind == "ACTIVITY_PROPOSAL":
            row = self.session.get(ActivityProposal, identifier)
            if row is None or row.world_id != scope.world_id:
                raise ValueError("situation_proposal_scope_invalid")
            raw, digest, version, thread = delivered, proposal_digest(row), str(row.version), None
            actor, counterpart = row.proposer_world_character_id, row.target_world_character_id
        elif kind == "IMAGE_INTERPRETATION":
            row = self.session.get(ImageInterpretation, identifier)
            asset = self.session.get(MediaAsset, row.asset_id) if row else None
            if row is None or row.owner_id != scope.owner_id or asset is None or not asset_owned(asset, scope, private_thread):
                raise ValueError("situation_interpretation_scope_invalid")
            raw, digest, version, thread = row.result_json or row.description or "", interpretation_digest(row), str(row.asset_revision), private_thread
            actor, counterpart = scope.subject_world_character_id, None
        elif kind == "RELATIONSHIP":
            row = self.session.get(RelationshipState, identifier)
            if row is None or row.world_id != scope.world_id or row.actor_world_character_id != scope.subject_world_character_id:
                raise ValueError("situation_relationship_scope_invalid")
            raw, digest, version, thread = delivered, relationship_digest(row), str(row.version), None
            actor, counterpart = row.actor_world_character_id, row.target_world_character_id
            if relationship_basis is not None:
                if (relationship_basis.state_id != identifier or relationship_basis.actor_id != actor
                        or relationship_basis.target_id != counterpart):
                    raise ValueError("situation_relationship_scope_invalid")
                digest, version = relationship_basis.facts_digest, str(relationship_basis.version)
        elif kind == "IMAGE_ASSET":
            row = self.session.get(MediaAsset, identifier)
            if row is None or not asset_owned(row, scope, private_thread):
                raise ValueError("situation_image_scope_invalid")
            raw, digest, version, thread = delivered, row.content_hash, str(row.revision), private_thread
            actor, counterpart = scope.subject_world_character_id, None
        elif kind == "MEMORY_ITEM":
            item = self.session.get(MemoryItem, identifier)
            if item is None or (item.owner_id, item.world_id, item.subject_world_character_id) != (scope.owner_id, scope.world_id, scope.subject_world_character_id):
                raise ValueError("situation_prior_not_found")
            raw, digest, version, thread = item.summary, sha256(item.summary.encode()).hexdigest(), str(item.version), item.thread_id
            actor, counterpart = item.subject_world_character_id, item.counterpart_world_character_id
        else:
            source_type = MemorySourceTypeV1(kind)
            evidence = self.reader.read_evidence(scope=scope, source_type=source_type, source_id=identifier)
            code = memory_evidence_blocked_code(scope=scope, source_type=source_type, source_id=identifier, evidence=evidence)
            if evidence is None or (code is not None and not (
                    delivery is not None and code == "memory_unobserved" and kind in {"POST", "REPLY"})):
                raise ValueError("situation_source_not_admitted")
            raw, digest, version, thread = evidence.deterministic_summary, evidence.source_digest, evidence.source_digest, evidence.thread_id
            actor, counterpart = evidence.actor_world_character_id, evidence.counterpart_world_character_id
            if kind == "CHAT_MESSAGE":
                raw = self.session.get(MessageMessage, int(identifier)).content
            elif kind in {"POST", "REPLY"}:
                raw = self.session.get(Post, identifier).body
        from app.domains.memory.policies.situation_ranges import delivered_ranges
        ranges, transmitted_ranges = delivered_ranges(raw, delivered)
        return DeliveredSourceEntry(kind, identifier, version, digest, sha256(delivered.encode()).hexdigest(),
            path, role, ordinal, scope.world_id, target_key=target, thread_id=thread or private_thread,
            actor_id=actor, counterpart_id=counterpart, ranges=ranges, partial=raw != delivered,
            transformation=None if raw == delivered else "bounded-context.v1", delivered_ranges=transmitted_ranges,
            relationship_basis=relationship_basis,
            delivery_payload_digest=delivery.payload_digest if delivery is not None else None)

    def validate(self, manifest, source, *, now, ancestors=frozenset()):
        scope = manifest.snapshot.scope
        if any(value is None for value in read_scope_presence(self.session, scope)):
            raise MemoryScopeError("memory_scope_invalid")
        if source.world_id != scope.world_id:
            return SituationSourceAccess("forbidden", reason="situation_source_scope_forbidden")
        if source.thread_id:
            thread = self.session.get(MessageThread, source.thread_id, populate_existing=True)
            if (thread is None or thread.requester_id != scope.owner_id or thread.world_id != scope.world_id
                or thread.responding_world_character_id != scope.subject_world_character_id):
                return SituationSourceAccess("forbidden", reason="situation_thread_forbidden")
        participants = {scope.subject_world_character_id, source.actor_id, source.counterpart_id} - {None}
        if set(active_participant_ids(self.session, participants, scope.world_id)) != participants or any(
            block_id(self.session, scope.world_id, scope.subject_world_character_id, identifier)
            for identifier in participants - {scope.subject_world_character_id}):
            return SituationSourceAccess("forbidden", reason="situation_participant_forbidden")
        if source.source_type == "ROUTINE_ACTIVITY":
            row = self.session.get(DailyActivityPlanItem, source.source_id, populate_existing=True)
            plan = self.session.get(DailyActivityPlan, row.plan_id, populate_existing=True) if row else None
            if plan is None:
                return SituationSourceAccess("deleted")
            if plan.world_id != scope.world_id or plan.world_character_id != scope.subject_world_character_id:
                return SituationSourceAccess("forbidden", reason="situation_routine_scope_forbidden")
            return SituationSourceAccess("available") if routine_digest(row) == source.source_digest else SituationSourceAccess(
                "changed", reason="situation_routine_changed")
        if source.source_type == "ACTIVITY_PROPOSAL":
            row = self.session.get(ActivityProposal, source.source_id, populate_existing=True)
            if row is None:
                return SituationSourceAccess("deleted")
            if row.world_id != scope.world_id:
                return SituationSourceAccess("forbidden", reason="situation_proposal_scope_forbidden")
            return SituationSourceAccess("available") if proposal_digest(row) == source.source_digest else SituationSourceAccess(
                "changed", reason="situation_proposal_changed")
        if source.source_type == "IMAGE_INTERPRETATION":
            row = self.session.get(ImageInterpretation, source.source_id, populate_existing=True)
            asset = self.session.get(MediaAsset, row.asset_id, populate_existing=True) if row else None
            if row is None or asset is None:
                return SituationSourceAccess("deleted")
            if row.owner_id != scope.owner_id or not asset_owned(asset, scope, source.thread_id):
                return SituationSourceAccess("forbidden", reason="situation_interpretation_scope_forbidden")
            return SituationSourceAccess("available") if interpretation_digest(row) == source.source_digest and asset.revision == row.asset_revision else SituationSourceAccess(
                "changed", reason="situation_interpretation_changed")
        if source.source_type == "RELATIONSHIP":
            row = self.session.get(RelationshipState, source.source_id, populate_existing=True)
            if (row is None or row.world_id != scope.world_id
                    or row.actor_world_character_id != scope.subject_world_character_id
                    or row.actor_world_character_id != source.actor_id or row.target_world_character_id != source.counterpart_id):
                return SituationSourceAccess("forbidden", reason="situation_relationship_forbidden")
            basis = historical_relationship(manifest, source)
            if basis and row.version >= source.relationship_basis.version:
                return SituationSourceAccess("available", proof_origin="situation_delivered")
            if source.relationship_basis is not None:
                return SituationSourceAccess("changed", reason="situation_relationship_basis_invalid")
            return SituationSourceAccess("available") if relationship_digest(row) == source.source_digest else SituationSourceAccess(
                "changed", reason="situation_legacy_relationship_basis_missing")
        if source.source_type == "IMAGE_ASSET":
            row = self.session.get(MediaAsset, source.source_id, populate_existing=True)
            if row is None:
                return SituationSourceAccess("deleted")
            if not asset_owned(row, scope, source.thread_id):
                return SituationSourceAccess("forbidden", reason="situation_image_scope_forbidden")
            return SituationSourceAccess("available") if row.content_hash == source.source_digest and str(row.revision) == source.source_version else SituationSourceAccess(
                "changed", reason="situation_image_changed")
        if source.source_type == "MEMORY_ITEM":
            item = self.session.get(MemoryItem, source.source_id, populate_existing=True)
            if (item is None or str(item.version) != source.source_version
                or sha256(item.summary.encode()).hexdigest() != source.source_digest
                or (item.owner_id, item.world_id, item.subject_world_character_id) != (scope.owner_id, scope.world_id, scope.subject_world_character_id)
                or not item_retrievable(item, now)):
                return SituationSourceAccess("changed", reason="situation_prior_changed")
            from app.domains.memory.repository.episode_privacy import currently_accessible
            if not currently_accessible(self.session, self, scope, item, now, ancestors=ancestors):
                return SituationSourceAccess("forbidden", reason="situation_prior_forbidden")
            return SituationSourceAccess("available")
        try:
            kind = MemorySourceTypeV1(source.source_type)
        except ValueError:
            return SituationSourceAccess("forbidden", reason="situation_source_type_forbidden")
        current = self.reader.read_evidence(scope=scope, source_type=kind, source_id=source.source_id)
        if source.source_type in {"POST", "REPLY"}:
            post = self.session.get(Post, source.source_id, populate_existing=True)
            if post is not None and (post.world_id != scope.world_id or post.report_hidden_at is not None or post.visibility != "public"):
                return SituationSourceAccess("forbidden", reason="situation_post_forbidden")
            if post is None or post.deleted_at is not None:
                return SituationSourceAccess("deleted")
        elif source.source_type == "CHAT_MESSAGE":
            message = self.session.get(MessageMessage, int(source.source_id), populate_existing=True)
            thread = self.session.get(MessageThread, source.thread_id, populate_existing=True)
            if message is None or (thread is not None and thread.deleted_at is not None):
                return SituationSourceAccess("deleted")
        elif source.source_type == "SOCIAL_EVENT":
            event = self.session.get(SocialEvent, source.source_id, populate_existing=True)
            if event is None:
                return SituationSourceAccess("deleted")
            if event.world_id != scope.world_id:
                return SituationSourceAccess("forbidden", reason="situation_event_scope_forbidden")
            if event.invalidation_reason == "source_deleted":
                return SituationSourceAccess("deleted")
        if current is None:
            return SituationSourceAccess("forbidden", reason="situation_source_forbidden")
        code = memory_evidence_blocked_code(scope=scope, source_type=kind, source_id=source.source_id, evidence=current)
        current, origin = delivered_evidence(manifest, source, current, blocked_code=code)
        if memory_evidence_blocked_code(scope=scope, source_type=kind, source_id=source.source_id, evidence=current):
            return SituationSourceAccess("forbidden", reason="situation_delivery_proof_missing" if code == "memory_unobserved" else "situation_source_forbidden")
        if current.source_digest != source.source_digest or (current.thread_id and current.thread_id != manifest.private_thread_id):
            return SituationSourceAccess("changed", reason="situation_source_changed")
        return SituationSourceAccess("available", current, proof_origin=origin)


def relationship_digest(row):
    return stable_digest({"id": row.id, "version": row.version, "view_version": row.view_version,
        "label": row.relationship_label, "perception": row.perception, "familiarity": row.familiarity,
        "affinity": row.affinity, "trust": row.trust, "tension": row.tension, "interactions": row.interaction_count})


def asset_owned(asset, scope, thread):
    return asset.owner_id == scope.owner_id and (
        (asset.scope_kind == "world" and asset.scope_id == scope.world_id)
        or (thread is not None and asset.scope_kind == "thread" and asset.scope_id == thread))


def interpretation_digest(row):
    return stable_digest({"asset": row.asset_id, "revision": row.asset_revision, "status": row.status,
        "description": row.description, "hint": row.recall_hint, "scope": row.scope_key,
        "result": row.result_json, "model": row.model, "thinking_level": row.thinking_level})


def proposal_digest(row):
    return stable_digest({name: getattr(row, name) for name in (
        "id", "activity_seed", "place_key", "target_daypart", "date_policy", "target_date")})


def routine_digest(row):
    return stable_digest({name: getattr(row, name) for name in (
        "id", "plan_id", "daypart", "activity_kind", "title", "activity_seed", "social_mode", "place_key")})
