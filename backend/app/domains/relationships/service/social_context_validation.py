"""Revalidate frozen SNS facts using a bounded canonical read, never ranking."""
from time import monotonic

from app.contracts.read_deadline import bounded_read
from app.domains.relationships.contracts.social_context import (
    CURRENTNESS_REVISION, LEGACY_CURRENTNESS, CanonicalSocialContextReference,
    RelationshipValidationReceipt, SocialContextItem, SocialContextValidationError,
    SocialContextValidationResult,
)
from app.domains.relationships.contracts.graph_recall_gateway import GraphRecallGateway
from app.domains.relationships.policies.graph_recall import (
    _node_valid, _relationship_facts_valid, _relationship_record,
)
from app.domains.relationships.policies.social_context_validation import (
    assert_prompt_receipt, display_name, facts_digest, input_content_hash,
    original_rows, social_context_row,
)


class SocialContextValidationService:
    def __init__(self, gateway: GraphRecallGateway, *, deadline_seconds=2.0, clock=monotonic):
        if not 0 < deadline_seconds <= 10:
            raise ValueError("social_context_limits_invalid")
        self.gateway, self.deadline_seconds, self.clock = gateway, deadline_seconds, clock

    def _canonical(self, scope, references):
        deadline = self.clock() + self.deadline_seconds
        try:
            with bounded_read(self.deadline_seconds):
                facts = self.gateway.canonical_social_context_facts(scope=scope, references=references)
            if self.clock() >= deadline:
                raise SocialContextValidationError("canonical_unavailable")
        except SocialContextValidationError:
            raise
        except Exception as exc:
            # Do not expose SQL/provider messages or treat an outage as empty.
            raise SocialContextValidationError("canonical_unavailable") from exc
        access = facts.scope_access
        if (not access.subject_exists or access.character_deleted
                or access.character_owner_id != scope.owner_id
                or access.subject_world_id != scope.world_id
                or access.membership_world_id != scope.world_id
                or access.world_character_status != "active" or access.membership_status != "active"):
            raise SocialContextValidationError("visibility_lost")
        return facts

    @staticmethod
    def _item(scope, facts, reference):
        candidate = next((value for value in facts.relationships.values()
            if value.canonical_hit is not None and value.canonical_hit.target_world_character_id == reference.target_world_character_id), None)
        hit = candidate.canonical_hit if candidate is not None else None
        if (hit is None or hit.actor_world_character_id != scope.subject_world_character_id
                or (reference.relationship_state_id is not None and hit.relationship_state_id != reference.relationship_state_id)
                or not _relationship_facts_valid(scope, hit, candidate, hit)
                or not _node_valid(scope, facts.nodes.get(scope.subject_world_character_id))
                or not _node_valid(scope, facts.nodes.get(reference.target_world_character_id))):
            raise SocialContextValidationError("visibility_lost")
        return SocialContextItem(_relationship_record(hit), display_name(facts.nodes[reference.target_world_character_id].display_name), (), "canonical")

    def validate(self, *, scope, binding, prompt, receipt, policy):
        if policy == LEGACY_CURRENTNESS and receipt is None:
            return self._legacy(scope=scope, prompt=prompt)
        if policy not in {CURRENTNESS_REVISION, LEGACY_CURRENTNESS} or receipt is None:
            raise SocialContextValidationError("receipt_invalid")
        parsed = RelationshipValidationReceipt.from_dict(receipt)
        if parsed.scope != scope or parsed.binding != binding:
            raise SocialContextValidationError("receipt_invalid")
        assert_prompt_receipt(prompt, parsed)
        references = tuple(CanonicalSocialContextReference(ref.target_world_character_id,
            ref.relationship_state_id) for ref in parsed.references)
        facts = self._canonical(scope, references)
        for reference, expected in zip(references, parsed.references, strict=True):
            item = self._item(scope, facts, reference)
            if item.relationship.relationship_version != expected.relationship_version:
                raise SocialContextValidationError("version_changed")
            if item.relationship.view_version != expected.view_version:
                raise SocialContextValidationError("view_changed")
            if facts_digest(item) != expected.facts_digest:
                raise SocialContextValidationError("facts_changed")
        return SocialContextValidationResult(parsed.revision,
            "valid" if parsed.basis == "facts" else parsed.basis, len(references))

    def _legacy(self, *, scope, prompt):
        if prompt == {}:
            self._canonical(scope, ())
            return SocialContextValidationResult(LEGACY_CURRENTNESS, "disabled", 0)
        rows = original_rows(prompt)
        if any(row["target_id"] == scope.subject_world_character_id for row in rows):
            raise SocialContextValidationError("legacy_unprovable")
        references = tuple(CanonicalSocialContextReference(row["target_id"]) for row in rows)
        facts = self._canonical(scope, references)
        versions = []
        for reference, row in zip(references, rows, strict=True):
            item = self._item(scope, facts, reference)
            if social_context_row(item) != row:
                raise SocialContextValidationError("legacy_unprovable")
            versions.append((item.relationship.relationship_state_id, item.relationship.relationship_version))
        if input_content_hash(scope, versions, prompt["context"], prompt["status"]) != prompt.get("content_hash"):
            raise SocialContextValidationError("legacy_unprovable")
        # This proves historical rows and relation versions, NOT an absent view version.
        basis = "valid_legacy_facts" if rows else "unavailable" if prompt["status"] == "unavailable" else "no_facts"
        return SocialContextValidationResult(LEGACY_CURRENTNESS, basis, len(references))
