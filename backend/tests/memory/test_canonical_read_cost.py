"""Repeatable synthetic shared-source cost probe, with no provider or user data."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

from sqlalchemy import event, select
from memory.test_activity_situation_contract import stack, values, NOW
from memory.test_activity_situation_application import real_source, apply
from memory.test_activity_situation_recall import readers
from app.domains.memory.repository.situation_admission import admit
from app.runtime.memory.situation_sources import SituationSources
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.contracts.recall import MemoryRecallCandidate, RecallDocumentKind


def test_shared_source_cost(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    prior = MemoryItem(id="shared-canonical-prior", owner_id=scope.owner_id, world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id, memory_kind="AUTOBIOGRAPHICAL_EVENT",
        summary="공유된 이전 경험", status="active", confidence=1.0, salience=.5, version=1,
        valid_from=NOW, created_at=NOW, updated_at=NOW)
    db.add(prior); db.commit()
    prior_source = SituationSources(db).describe(scope, kind="MEMORY_ITEM", identifier=prior.id,
        delivered=prior.summary, path="/prior", role="prior", ordinal=1, target=post.id)
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id,
        delivered=post.body, path="/target/body", role="core", ordinal=0, target=post.id)
    for number in range(50):
        manifest, draft, result = values(db, scope, target=post.id,
            logical=f"cost-{number}", call=f"cost-call-{number}")
        admit(db, manifest=replace(manifest, sources=(source, prior_source)), draft=draft, result=result, now=NOW)
    db.commit()
    apply(db, setting, memory)
    items = list(db.scalars(select(MemoryItem).where(MemoryItem.id != prior.id).order_by(MemoryItem.id)))
    assert len(items) == 50
    reader, request, _, _ = readers(db, scope, items[0])
    observed = []
    if hasattr(reader, "access_observer"):
        reader.access_observer = observed.append
    candidates = tuple(RankedMemoryCandidate(MemoryRecallCandidate(
        f"memory-item:{item.id}", item.id, RecallDocumentKind.MEMORY_ITEM,
        item.id, 1.0, item.summary, metadata={"item_version": str(item.version)}),
        item.version, sha256(item.summary.encode()).hexdigest()) for item in items)
    counts = []
    def sql(*_):
        counts.append(1)
    event.listen(db.bind, "before_cursor_execute", sql)
    measured = {}
    try:
        for size in (1, 10, 50):
            reader.revalidate(request, candidates[:size])  # warm-up, excluded
            samples, queries = [], []
            for _ in range(5):
                counts.clear()
                observed.clear()
                start = perf_counter()
                records = reader.revalidate(request, candidates[:size])
                samples.append((perf_counter() - start) * 1000)
                queries.append(len(counts))
                assert len(records) == size
            measured[str(size)] = {"sql": median(queries), "ms": round(median(samples), 3)}
            if observed:
                measured[str(size)].update(unique_nodes=observed[-1].unique_nodes, memo_hits=observed[-1].memo_hits)
        from app.runtime.memory_http import _service
        counts.clear()
        _service(db).detail(scope, item_id=items[0].id, now=NOW)
        detail_samples, detail_queries = [], []
        for _ in range(5):
            counts.clear(); start = perf_counter()
            detail = _service(db).detail(scope, item_id=items[0].id, now=NOW)
            detail_samples.append((perf_counter()-start)*1000); detail_queries.append(len(counts))
            assert detail.item.id == items[0].id
        measured["detail"] = {"sql": median(detail_queries), "ms": round(median(detail_samples), 3)}
    finally:
        event.remove(db.bind, "before_cursor_execute", sql)
    print("CANONICAL_COST " + json.dumps(measured, sort_keys=True))
    output = os.environ.get("ANGMOO_COST_OUTPUT")
    if output:
        Path(output).write_text(json.dumps(measured, indent=2), encoding="utf-8")
    baseline = os.environ.get("ANGMOO_COST_BASELINE")
    if baseline:
        before = json.loads(Path(baseline).read_text(encoding="utf-8"))
        assert measured["50"]["sql"] <= before["50"]["sql"] * .25
        assert measured["50"]["ms"] <= before["50"]["ms"] * .6
        if "detail" in before: assert measured["detail"]["sql"] <= before["detail"]["sql"]
