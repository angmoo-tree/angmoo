"""Bounded pending-only batches. Single-item providers remain valid."""
import asyncio
from collections import defaultdict
from app.core.result_journal import ResultJournalError
from app.core.sqlite_concurrency import is_sqlite_contention
from app.domains.memory.contracts.embedding import EMBEDDING_DIMENSIONS, embedding_text
from app.providers.contracts import EmbeddingRequest, EmbeddingBatchRequest
from app.providers.registry import get_embedding_adapter, get_model_spec
from app.runtime.memory.vector_delivery import prepare, persist
from app.runtime.memory.sqlite_vec1 import vector_blob


async def sync_items(projection, item_ids, *, credential_revision=None):
    identifiers = tuple(dict.fromkeys(item_ids))
    if len(identifiers) > 64:
        raise ValueError("memory_embedding_page_limit")
    if not identifiers:
        return {}
    if projection._closing:
        return dict.fromkeys(identifiers, "deferred")
    documents = await projection._canonical.call(projection._source.documents_for_item_ids, identifiers)
    outcomes, groups = {}, defaultdict(list)
    for item_id in identifiers:
        value = await projection._canonical.call(prepare, projection, item_id, documents.get(item_id, ()), credential_revision)
        if isinstance(value, str):
            projection._received.pop(item_id, None)
            outcomes[item_id] = value
            continue
        scope, config, digest, version = value.work
        try:
            received = projection._received.get(item_id) or projection.journal.read(scope.world_id, item_id)
        except ResultJournalError:
            projection.last_code = "memory_embedding_result_invalid"
            outcomes[item_id] = "local_result_invalid"
            continue  # Keep the invalid receipt, but don't starve unrelated items.
        if received is not None:
            outcomes[item_id] = await projection._canonical.call(persist, projection, value, received)
            continue
        identity = projection.index.identity(f"memory-item:{item_id}")
        if identity and identity[1:] == (digest, config.profile):
            # Use the same final canonical fence as a newly returned vector;
            # refresh metadata only after the fresh source/credential read.
            from app.runtime.memory.vector_delivery import refresh_current
            outcomes[item_id] = await projection._canonical.call(refresh_current, projection, value)
            continue
        groups[value.group].append(value)
    for group in groups.values():
        scope, config, _, _ = group[0].work
        provider = projection._provider or get_embedding_adapter(config.provider, config.model)
        spec = get_model_spec(config.provider, config.model)
        limits = spec.embedding_batch_limits
        batch = (spec.capabilities.embedding_batch and limits is not None
            and callable(getattr(provider, "embed_batch_measured", None)))
        chunk = []
        for prepared in group:
            if chunk and (not batch or not limits.fits(tuple(embedding_text(p.document.text, query=False)
                    for p in (*chunk, prepared)))):
                await _submit(projection, provider, chunk, outcomes)
                chunk = []
            chunk.append(prepared)
        if chunk:
            await _submit(projection, provider, chunk, outcomes)
    return outcomes


async def _submit(projection, provider, candidates, outcomes):
    if projection._closing:
        outcomes.update((p.item_id, "deferred") for p in candidates)
        return
    eligible = []
    for p in candidates:
        _, config, digest, _ = p.work
        limits = get_model_spec(config.provider, config.model).embedding_batch_limits
        if limits is not None and not limits.fits((embedding_text(p.document.text, query=False),)):
            projection.last_code = "memory_embedding_input_limit"
            outcomes[p.item_id] = "failed"
        elif len(projection._received) + len(eligible) >= 64:
            outcomes[p.item_id] = "local_result_pending"
        else:
            eligible.append(p)
    try:
        claimed = await projection._canonical.call(projection._claim_attempts,
            tuple((f"memory-item:{p.item_id}", p.work[1].profile, p.work[2], p.attempt_revision) for p in eligible)) if eligible else set()
    except Exception as exc:
        if not is_sqlite_contention(exc):
            raise
        outcomes.update((p.item_id, "deferred") for p in eligible)
        return
    admitted = [p for p in eligible if f"memory-item:{p.item_id}" in claimed]
    outcomes.update((p.item_id, "attempts_exhausted") for p in eligible if p not in admitted)
    if not admitted:
        return
    first = admitted[0]
    texts = tuple(embedding_text(p.document.text, query=False) for p in admitted)
    projection.logical_calls += 1
    counted = False
    try:
        if len(admitted) == 1:
            response = await provider.embed_measured(EmbeddingRequest(first.material.reveal(), first.work[1].model,
                texts[0], EMBEDDING_DIMENSIONS), timeout_seconds=30)
            vectors = (response.vector,)
        else:
            response = await provider.embed_batch_measured(EmbeddingBatchRequest(first.material.reveal(), first.work[1].model,
                texts, EMBEDDING_DIMENSIONS), timeout_seconds=30)
            vectors = response.vectors
        if projection.physical_attempts is not None:
            projection.physical_attempts += response.physical_attempts
        counted = True
        if len(vectors) != len(admitted):
            raise ValueError("embedding_cardinality_mismatch")
        for vector in vectors:
            vector_blob(vector)
        projection.last_usage = response.usage
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        attempts = getattr(exc, "physical_attempts", None)
        if not counted:
            projection.physical_attempts = (None if attempts is None or projection.physical_attempts is None
                else projection.physical_attempts + attempts)
        for p in admitted:
            if not getattr(exc, "retryable", False):
                projection._finish_attempt(f"memory-item:{p.item_id}", p.work[1].profile,
                    p.work[2], p.attempt_revision, terminal=True)
            outcomes[p.item_id] = "failed"
        projection.last_code = "memory_embedding_failed"
        return
    # Own all received values before any individual write can fail or cancel.
    if projection._closing:
        outcomes.update((p.item_id, "deferred") for p in admitted)
        return
    for p, vector in zip(admitted, vectors, strict=True):
        projection._received[p.item_id] = {"binding": p.binding, "vector": list(vector)}
    await projection._canonical.call(_preserve, projection, admitted)
    for p in admitted:
        outcomes[p.item_id] = await projection._canonical.call(persist, projection, p, projection._received[p.item_id])
        await asyncio.sleep(0)  # A short per-item UoW gives other writers a turn.


def _preserve(projection, admitted):
    from app.core.result_journal import ResultJournalError
    for p in admitted:
        try:
            projection.journal.write(p.work[0].world_id, p.item_id, projection._received[p.item_id])
        except (ResultJournalError, OSError):
            # Keep the bounded in-process owner. persist performs classification
            # and fresh authority checks; this is not another provider attempt.
            continue
