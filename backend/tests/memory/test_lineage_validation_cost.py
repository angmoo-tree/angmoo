"""Shared lineage stays bounded without retaining an authorization decision."""
import json
from collections import Counter

import pytest

from memory.test_activity_situation_contract import stack, NOW
from memory.test_activity_situation_application import real_source, receipt, apply
from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.episode_privacy import currently_accessible
from app.runtime.memory.source_composition import source_evidence_reader

pytestmark = pytest.mark.usefixtures("deny_external_network")


def lineage(stack, levels=12):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    original = db.get(MemoryItem, admitted.applied_item_id)
    values = {column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns}
    bundle = MemoryEpisodeBundle(id="lineage-bundle", scope_setting_id=setting.id,
        policy_version=ACTIVITY_POLICY_VERSION, activation_epoch="lineage-epoch",
        cutoff_sequence=1, manifest_hash="a" * 64, manifest_json="{}", result_hash="b" * 64,
        created_at=NOW)
    db.add(bundle)
    reader = source_evidence_reader(db)
    evidence = reader.read_evidence(scope=scope, source_type=MemorySourceTypeV1.POST, source_id=post.id)
    sources = json.dumps([{"type": "POST", "id": post.id, "digest": evidence.source_digest}])
    nodes, previous = [], []
    for level in range(levels):
        current = []
        for side in range(2):
            item = MemoryItem(**{**values, "id": f"lineage-{level:02d}-{side}"})
            db.add(item)
            db.flush()
            db.add(MemoryEpisodeInfo(memory_item_id=item.id, bundle_id=bundle.id, policy_version=ACTIVITY_POLICY_VERSION))
            db.add(MemoryEpisodeRestriction(memory_item_id=item.id, mode="public", thread_id=None,
                sources_json=sources, priors_json=json.dumps([{"id": value.id, "version": value.version} for value in previous])))
            current.append(item)
        nodes.extend(current)
        previous = current
    db.commit()
    return db, scope, post, nodes, reader


def test_shared_prior_dag_validates_each_item_once_and_keeps_every_source_check(stack, monkeypatch):
    db, scope, post, nodes, reader = lineage(stack)
    calls = Counter()
    original = reader.read_evidence
    def read(**values):
        calls[values["source_id"]] += 1
        assert sum(calls.values()) <= len(nodes), "shared lineage was repeatedly expanded"
        return original(**values)
    monkeypatch.setattr(reader, "read_evidence", read)
    from app.domains.memory.contracts.access_validation import MemoryAccessValidation
    validation = MemoryAccessValidation(db, NOW)
    assert currently_accessible(db, reader, scope, nodes[-1], NOW, validation=validation)
    # Every reachable node applies its own restriction to the same fresh fact.
    # Source rows are read once in this operation, not once per path or node.
    assert len(validation.completed) == len(nodes) - 1
    assert validation.memo_hits > 0
    assert calls[post.id] == 1


@pytest.mark.parametrize("change", ["source-body", "source-hidden", "subject-inactive", "prior-version", "prior-deleted", "prior-source-digest", "cycle"])
def test_same_session_and_reader_recheck_changes_after_success(stack, change):
    db, scope, post, nodes, reader = lineage(stack, levels=4)
    assert currently_accessible(db, reader, scope, nodes[-1], NOW)
    if change == "source-body":
        post.body += " changed"
    elif change == "source-hidden":
        post.report_hidden_at = NOW
    elif change == "subject-inactive":
        from app.domains.world_characters.models import WorldCharacter
        db.get(WorldCharacter, scope.subject_world_character_id).status = "left"
    elif change == "prior-version":
        nodes[0].version += 1
    elif change == "prior-deleted":
        nodes[0].status, nodes[0].deleted_at = "deleted", NOW
    elif change == "prior-source-digest":
        restriction = db.get(MemoryEpisodeRestriction, nodes[0].id)
        sources = json.loads(restriction.sources_json)
        sources[0]["digest"] = "0" * 64
        restriction.sources_json = json.dumps(sources)
    else:
        db.get(MemoryEpisodeRestriction, nodes[0].id).priors_json = json.dumps([
            {"id": nodes[-1].id, "version": nodes[-1].version}])
    db.commit()
    assert not currently_accessible(db, reader, scope, nodes[-1], NOW)
