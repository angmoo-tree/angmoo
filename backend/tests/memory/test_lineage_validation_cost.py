"""Migrated flat dependencies retain deletion rights without ancestor reads."""
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
    from app.runtime.persistence.experience_migration import migrate
    migrate(db,now=NOW)
    db.commit()
    db.add_all([post,*nodes])
    return db, scope, post, nodes, reader


def test_migrated_prior_dag_checks_only_owned_memory_without_source_reads(stack, monkeypatch):
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
    assert len(validation.completed) == 1
    assert validation.memo_hits == 0
    assert calls[post.id] == 0


def test_hotbrief_roots_share_one_read_but_recheck_after_source_change(stack, monkeypatch):
    from app.runtime.memory.composition import memory_consolidation_repository
    db, scope, post, nodes, reader = lineage(stack)
    repository = memory_consolidation_repository(db)
    repository._source_reader = reader
    calls = Counter()
    original = reader.read_evidence
    def read(**values):
        calls[values['source_id']] += 1
        return original(**values)
    monkeypatch.setattr(reader, 'read_evidence', read)
    setting = stack[2]
    items = repository.hot_brief_source_items(setting=setting, now=NOW, limit=24)
    assert len(items) == 24
    assert calls[post.id] == 0
    post.body += ' source revised'
    db.commit()
    assert len(repository.hot_brief_source_items(setting=setting, now=NOW, limit=24)) == 24


def test_correction_source_extraction_keeps_the_same_fresh_validation(stack, monkeypatch):
    from app.domains.memory.repository.situation_reads import correction_evidence
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    item = db.get(MemoryItem, admitted.applied_item_id)
    reader = source_evidence_reader(db)
    contexts = []
    original = reader.validate_situation_source
    def validate(*args, **kwargs):
        contexts.append(kwargs.get('validation'))
        return original(*args, **kwargs)
    monkeypatch.setattr(reader, 'validate_situation_source', validate)
    assert correction_evidence(db, reader, scope, item, NOW)
    assert contexts == []
    post.report_hidden_at = NOW
    db.commit()
    assert correction_evidence(db, reader, scope, item, NOW)
    assert contexts == []
    from app.domains.memory.repository.experience import tombstone
    tombstone(db,item,setting.id,now=NOW);db.commit()
    from app.domains.memory.exceptions import MemoryConflictError
    with pytest.raises(MemoryConflictError, match='source_unavailable'):
        correction_evidence(db, reader, scope, item, NOW)
    assert contexts == []


def test_projection_batch_bounds_sql_and_rechecks_hidden_source(stack):
    from sqlalchemy import event
    from app.domains.memory.repository.recall import SqlAlchemyMemoryRecallDocumentSource
    db, scope, post, nodes, reader = lineage(stack)
    source = SqlAlchemyMemoryRecallDocumentSource(lambda: db, source_reader_factory=source_evidence_reader,
        now_factory=lambda: NOW, episode_only=True)
    statements = []
    def count(*args):
        statements.append(1)
    event.listen(db.bind, 'before_cursor_execute', count)
    try:
        docs = source.documents_for_item_ids([item.id for item in nodes], session=db)
    finally:
        event.remove(db.bind, 'before_cursor_execute', count)
    assert len(docs) == len(nodes) and all(docs.values())
    assert len(statements) < 250, 'projection expanded shared sources into individual SQL reads'
    post.report_hidden_at = NOW
    db.commit()
    assert all(source.documents_for_item_ids([item.id for item in nodes], session=db).values())


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
        from app.domains.memory.repository.experience import tombstone
        tombstone(db,nodes[0],stack[2].id,now=NOW)
    elif change == "prior-source-digest":
        restriction = db.get(MemoryEpisodeRestriction, nodes[0].id)
        sources = json.loads(restriction.sources_json)
        sources[0]["digest"] = "0" * 64
        restriction.sources_json = json.dumps(sources)
    else:
        db.get(MemoryEpisodeRestriction, nodes[0].id).priors_json = json.dumps([
            {"id": nodes[-1].id, "version": nodes[-1].version}])
    db.commit()
    assert currently_accessible(db, reader, scope, nodes[-1], NOW) == (change not in {"subject-inactive","prior-deleted"})
