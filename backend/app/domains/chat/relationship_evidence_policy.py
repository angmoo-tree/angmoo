"""Exact final-input capture and historical/current read separation; no I/O."""
from hashlib import sha256
import json
import re

from app.domains.chat.contracts.relationship_evidence import (
    RelationshipEvidenceDelivery, RelationshipDeliveredItem, RelationshipEvidenceRead, digest, validate_projection,
)
from app.domains.relationships.contracts.social_context import SocialContextItem
from app.domains.relationships.service.social_context_evidence import project_social_context_evidence


def capture_delivery(binding, bundle, snapshot, payload, prompt, identity=None, current_inspector=None):
    items = []
    inspector = bundle.inspector_snapshot()
    for index, (item, raw) in enumerate(zip(bundle.items, inspector["items"], strict=True)):
        locator = item.locator
        if item.kind.value != "graph_relationship":
            continue
        if locator is None or locator.relationship_facts_digest is None or locator.relationship_view_version is None:
            raise ValueError("relationship_evidence_basis_missing")
        fragment = payload["frozen_evidence"]["items"][index]["text"]
        if fragment != item.text:
            raise ValueError("relationship_evidence_payload_changed")
        items.append(RelationshipDeliveredItem("items", item.opaque_reference, locator.source_id,
            locator.actor_world_character_id, locator.target_world_character_id, int(locator.source_revision),
            locator.relationship_view_version, locator.relationship_facts_digest, "graph",
            identity.names.get(locator.target_world_character_id) if identity else None,
            f"/frozen_evidence/items/{index}/text", fragment, digest(fragment), digest(raw), item.relationship_projection))
    if snapshot is not None:
        if payload["social_context"] != snapshot.prompt_view():
            raise ValueError("relationship_evidence_payload_changed")
        raw_items = current_inspector["items"]
        for index, (item, raw) in enumerate(zip(snapshot.items, raw_items, strict=True)):
            relation = item.relationship
            row, fact_digest = project_social_context_evidence(item)
            fragment = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            if fragment + "\n" not in snapshot.context_text:
                raise ValueError("relationship_evidence_row_missing")
            items.append(RelationshipDeliveredItem("current_context", raw["ref"], relation.relationship_state_id,
                relation.actor_world_character_id, relation.target_world_character_id, relation.relationship_version,
                relation.view_version, fact_digest, "social", item.display_name,
                f"/social_context/context/row/{index}", fragment, digest(fragment), digest(raw),
                {key: row[key] for key in ("familiarity", "affinity", "trust", "tension", "interactions", "relationship_label", "perception")}))
    return RelationshipEvidenceDelivery(binding, digest(payload), sha256(prompt.encode()).hexdigest(), tuple(items)).to_dict()


def validate_delivery(raw, *, binding, capture, inspector, current_inspector):
    proof = RelationshipEvidenceDelivery.from_dict(raw)
    if proof.binding != binding or capture != {"digest": raw["digest"], "payload_digest": proof.payload_digest,
            "prompt_digest": proof.prompt_digest}:
        raise ValueError("relationship_evidence_binding_invalid")
    sections = {"items": (inspector or {}).get("items", []),
        "current_context": (current_inspector or {}).get("items", [])}
    expected = {(section, item["ref"]): item for section, values in sections.items()
        for item in values if item.get("kind") == "graph_relationship"}
    if set(expected) != {(item.section, item.reference) for item in proof.items}:
        raise ValueError("relationship_evidence_inspector_mismatch")
    for item in proof.items:
        raw_item = expected[item.section, item.reference]
        locator = raw_item.get("locator") or {}
        if digest(raw_item) != item.inspector_digest or (locator.get("source_id"), locator.get("actor_world_character_id"),
                locator.get("target_world_character_id"), locator.get("source_revision")) != (
                item.state_id, item.actor_id, item.target_id, str(item.version)):
            raise ValueError("relationship_evidence_inspector_mismatch")
        if item.section == "items" and " ".join(item.fragment.split()) != raw_item["text"]:
            raise ValueError("relationship_evidence_fragment_invalid")
        index = sections[item.section].index(raw_item)
        expected_path = f"/frozen_evidence/items/{index}/text" if item.section == "items" else f"/social_context/context/row/{index}"
        if item.path != expected_path:
            raise ValueError("relationship_evidence_path_invalid")
        if item.section == "items" and item.projection is not None and item.projection != graph_projection(item.fragment):
            raise ValueError("relationship_evidence_projection_invalid")
        if item.section == "current_context":
            row = json.loads(item.fragment)
            if row.get("target_id") != item.target_id or row.get("target") != item.name:
                raise ValueError("relationship_evidence_fragment_invalid")
            if item.projection != {key: row[key] for key in item.projection or ()}:
                raise ValueError("relationship_evidence_projection_invalid")
    return proof


def historical_read(item, current):
    if not current.access_allowed:
        return RelationshipEvidenceRead(reason="current_unavailable" if current.reason != "read_unavailable" else "read_unavailable")
    relation = current.relationship
    if relation is None:
        return RelationshipEvidenceRead(item.fragment, item.name, "not_checked")
    if relation.relationship_version < item.version or relation.view_version < item.view_version:
        return RelationshipEvidenceRead(reason="historical_unverified")
    if relation.relationship_version == item.version and relation.view_version == item.view_version:
        actual = project_social_context_evidence(SocialContextItem(relation, item.name, (), "canonical"))[1] if item.basis == "social" else relation.delivery_facts_digest()
        if actual != item.facts_digest:
            return RelationshipEvidenceRead(reason="historical_unverified")
        change = "same"
    else:
        change = "changed"
    return RelationshipEvidenceRead(item.fragment, item.name, change)


def graph_projection(fragment):
    """Decode only the exact code-owned bounded graph template, never arbitrary prose."""
    match = re.fullmatch(r".+에서 .+ 방향의 현재 관계: 친숙도 (\d+), 호감 (-?\d+), 신뢰 (-?\d+), 긴장 (\d+), 상호작용 (\d+)회\.", fragment)
    if match is None:
        return None
    value = dict(zip(("familiarity", "affinity", "trust", "tension", "interactions"), map(int, match.groups()), strict=True))
    return validate_projection({**value, "relationship_label": None, "perception": None})


def restore_legacy_relationships(manifest, inspector, binding):
    """Only exact retained v2 fragments/bases, no inferred perception or latest facts."""
    restored = {}
    if manifest is None or manifest.version not in {2, 3} or manifest.call_identity != f"chat:{binding.request_scope_hash}":
        return restored
    for index, raw in enumerate(inspector.get("items", [])[:12]):
        locator = raw.get("locator") or {}
        if raw.get("kind") != "graph_relationship" or locator.get("actor_world_character_id") != binding.actor_id:
            continue
        text = raw.get("text")
        path = f"/frozen_evidence/items/{index}/text"
        for source in manifest.sources:
            basis = source.relationship_basis
            if basis is None or source.delivery_payload_digest != manifest.payload_digest or source.payload_path != path:
                continue
            if (source.source_id, basis.actor_id, basis.target_id, str(basis.version), source.delivered_digest) != (
                    locator.get("source_id"), binding.actor_id, locator.get("target_world_character_id"),
                    locator.get("source_revision"), sha256(text.encode()).hexdigest()):
                continue
            projection = graph_projection(text)
            restored[("items", raw["ref"])] = RelationshipDeliveredItem("items", raw["ref"], basis.state_id,
                basis.actor_id, basis.target_id, basis.version, basis.view_version, basis.facts_digest, "graph", None,
                path, text, digest(text), digest(raw), projection)
    return restored
