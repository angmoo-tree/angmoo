"""Validate bound reference inputs and current rights independently of freshness."""
from time import monotonic
import sqlite3
from app.core.sqlite_concurrency import sqlite_error_identity

from app.contracts.read_deadline import bounded_read, current_read_deadline
from app.domains.relationships.contracts.social_context import (
    CURRENTNESS_REVISION, PREVIOUS_CURRENTNESS, LEGACY_CURRENTNESS, CanonicalSocialContextReference,
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
                raise SocialContextValidationError("canonical_read_deadline")
        except SocialContextValidationError:
            raise
        except Exception as exc:
            # Do not expose SQL/provider messages or treat an outage as empty.
            code, _ = sqlite_error_identity(exc)
            primary = code & 0xFF if code is not None else None
            reason = ("canonical_database_busy" if primary == sqlite3.SQLITE_BUSY else
                "canonical_read_deadline" if primary == sqlite3.SQLITE_INTERRUPT or isinstance(exc, TimeoutError) else
                "canonical_database_error" if primary is not None else "canonical_read_error")
            raise SocialContextValidationError(reason, error_type=type(exc).__name__, sqlite_code=code) from exc
        access = facts.scope_access
        if (not access.subject_exists or access.character_deleted
                or access.character_owner_id != scope.owner_id
                or access.subject_world_id != scope.world_id
                or access.membership_world_id != scope.world_id
                or access.world_character_status != "active" or access.membership_status != "active"):
            raise SocialContextValidationError("visibility_lost", failure_scope="shared")
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

    def validate_many(self, *, scope, requests):
        """One guard, one canonical read; no cache survives this invocation."""
        if requests and all(request['policy'] == CURRENTNESS_REVISION for request in requests):
            parsed = tuple(self._frozen_receipt(scope=scope, **request) for request in requests)
            self.assert_access(scope, tuple(dict.fromkeys(
                ref.target_world_character_id for receipt in parsed for ref in receipt.references)))
            return tuple(SocialContextValidationResult(receipt.revision,
                'valid' if receipt.basis == 'facts' else receipt.basis,
                len(receipt.references), 'initial_input') for receipt in parsed)
        references = []
        for request in requests:
            if request["receipt"] is None and request["policy"] == LEGACY_CURRENTNESS:
                if request["prompt"]:
                    references.extend(CanonicalSocialContextReference(row["target_id"]) for row in original_rows(request["prompt"]))
            else:
                parsed = RelationshipValidationReceipt.from_dict(request["receipt"])
                if parsed.scope != scope or parsed.binding != request["binding"]:
                    raise SocialContextValidationError("receipt_invalid")
                assert_prompt_receipt(request["prompt"], parsed)
                references.extend(CanonicalSocialContextReference(ref.target_world_character_id, ref.relationship_state_id) for ref in parsed.references)
        with bounded_read(self.deadline_seconds):
            facts = self._canonical(scope, tuple(dict.fromkeys(references)))
            return tuple(self.validate(scope=scope, _facts=facts, **request) for request in requests)

    def validate(self, *, scope, binding, prompt, receipt, policy, _facts=None, effects=()):
        deadline = current_read_deadline.get()
        if deadline is not None and monotonic() >= deadline:
            raise SocialContextValidationError("canonical_read_deadline")
        if policy == CURRENTNESS_REVISION:
            parsed = self._frozen_receipt(scope=scope, binding=binding, prompt=prompt,
                receipt=receipt, policy=policy, effects=effects)
            self.assert_access(scope, tuple(ref.target_world_character_id for ref in parsed.references))
            return SocialContextValidationResult(parsed.revision,
                'valid' if parsed.basis == 'facts' else parsed.basis,
                len(parsed.references), 'initial_input')
        if policy == LEGACY_CURRENTNESS and receipt is None:
            return self._legacy(scope=scope, prompt=prompt, facts=_facts)
        if policy not in {PREVIOUS_CURRENTNESS, LEGACY_CURRENTNESS} or receipt is None:
            raise SocialContextValidationError("receipt_invalid")
        parsed = RelationshipValidationReceipt.from_dict(receipt)
        if parsed.scope != scope or parsed.binding != binding:
            raise SocialContextValidationError("receipt_invalid")
        assert_prompt_receipt(prompt, parsed)
        references = tuple(CanonicalSocialContextReference(ref.target_world_character_id,
            ref.relationship_state_id) for ref in parsed.references)
        facts = self._canonical(scope, references) if _facts is None else _facts
        proven_count = 0
        for reference, expected in zip(references, parsed.references, strict=True):
            item = self._item(scope, facts, reference)
            from app.domains.relationships.contracts.social_context import RelationshipValidationReference
            from app.domains.relationships.policies.effect_progress import proves
            actual = RelationshipValidationReference(item.relationship.relationship_state_id,
                item.relationship.target_world_character_id, item.relationship.relationship_version,
                item.relationship.view_version, facts_digest(item))
            if actual != expected and effects and proves(expected, actual, effects):
                proven_count += 1
                continue
            if item.relationship.relationship_version != expected.relationship_version:
                raise SocialContextValidationError("version_changed")
            if item.relationship.view_version != expected.view_version:
                raise SocialContextValidationError("view_changed")
            if facts_digest(item) != expected.facts_digest:
                raise SocialContextValidationError("facts_changed")
        return SocialContextValidationResult(parsed.revision,
            "valid" if parsed.basis == "facts" else parsed.basis, len(references),
            "same_decision_effects" if proven_count else None)

    @staticmethod
    def _frozen_receipt(*, scope, binding, prompt, receipt, policy, effects=()):
        parsed = RelationshipValidationReceipt.from_dict(receipt)
        if parsed.revision != policy or parsed.scope != scope or parsed.binding != binding:
            raise SocialContextValidationError('receipt_invalid')
        assert_prompt_receipt(prompt, parsed)
        return parsed

    def assert_access(self, scope, target_ids):
        """Read only current scope/participant/block facts, not relationship values."""
        deadline = self.clock() + self.deadline_seconds
        try:
            self._assert_access(scope, target_ids)
            active_deadline = current_read_deadline.get()
            if self.clock() >= deadline or (active_deadline is not None and monotonic() >= active_deadline):
                raise SocialContextValidationError("canonical_read_deadline")
        except SocialContextValidationError:
            raise
        except Exception as exc:
            code, _ = sqlite_error_identity(exc)
            primary = code & 0xFF if code is not None else None
            reason = ("canonical_database_busy" if primary == sqlite3.SQLITE_BUSY else
                "canonical_read_deadline" if primary == sqlite3.SQLITE_INTERRUPT or isinstance(exc, TimeoutError) else
                "canonical_database_error" if primary is not None else "canonical_read_error")
            raise SocialContextValidationError(reason, error_type=type(exc).__name__, sqlite_code=code) from exc

    def assert_snapshot_usable(self, snapshot):
        versions = [(item.relationship.relationship_state_id, item.relationship.relationship_version)
                    for item in snapshot.items]
        if input_content_hash(snapshot.scope, versions, snapshot.context_text, snapshot.status) != snapshot.content_hash:
            raise SocialContextValidationError("receipt_invalid")
        self.assert_access(snapshot.scope,
            tuple(item.relationship.target_world_character_id for item in snapshot.items))

    def _assert_access(self, scope, target_ids):
        targets = tuple(dict.fromkeys(target_ids))
        if len(targets) > 36 or scope.subject_world_character_id in targets:
            raise SocialContextValidationError('receipt_invalid')
        with bounded_read(self.deadline_seconds):
            access = self.gateway.graph_recall_scope_access(scope=scope)
            if (not access.subject_exists or access.character_deleted
                    or access.character_owner_id != scope.owner_id
                    or access.subject_world_id != scope.world_id
                    or access.membership_world_id != scope.world_id
                    or access.world_character_status != 'active' or access.membership_status != 'active'):
                raise SocialContextValidationError('visibility_lost', failure_scope='shared')
            nodes = self.gateway.node_candidates(world_id=scope.world_id,
                world_character_ids={scope.subject_world_character_id, *targets},
                subject_world_character_id=scope.subject_world_character_id)
            by_id = {node.world_character_id: node for node in nodes}
            if any(not _node_valid(scope, by_id.get(identifier))
                    for identifier in (scope.subject_world_character_id, *targets)):
                raise SocialContextValidationError('visibility_lost')

    def capture(self, *, scope, references):
        """Exact full canonical values under the caller's existing writer UoW."""
        from app.domains.relationships.contracts.social_context import RelationshipValidationReference
        facts = self._canonical(scope, references)
        result = []
        for reference in references:
            item = self._item(scope, facts, reference)
            result.append(RelationshipValidationReference(item.relationship.relationship_state_id,
                item.relationship.target_world_character_id, item.relationship.relationship_version,
                item.relationship.view_version, facts_digest(item)))
        return tuple(result)

    def _legacy(self, *, scope, prompt, facts=None):
        if prompt == {}:
            if facts is None:
                self._canonical(scope, ())
            return SocialContextValidationResult(LEGACY_CURRENTNESS, "disabled", 0)
        rows = original_rows(prompt)
        if any(row["target_id"] == scope.subject_world_character_id for row in rows):
            raise SocialContextValidationError("legacy_unprovable")
        references = tuple(CanonicalSocialContextReference(row["target_id"]) for row in rows)
        facts = self._canonical(scope, references) if facts is None else facts
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
