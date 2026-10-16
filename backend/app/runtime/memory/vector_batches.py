"""Bounded pending-only batches. Single-item providers remain valid."""
from app.core import work_observation as observation
import asyncio
from uuid import uuid4
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
    outcomes, groups = {}, defaultdict(list)
    for item_id in identifiers:
        try:
            value = await projection._canonical.call(prepare, projection, item_id, (), credential_revision)
        except Exception as exc:
            from app.domains.memory.exceptions import MemoryValidationError
            if isinstance(exc, MemoryValidationError):
                outcomes[item_id] = "configuration_invalid"
            elif is_sqlite_contention(exc):
                outcomes[item_id] = "deferred"
            else:
                raise
            continue
        if isinstance(value, str):
            projection._received.pop(item_id, None)
            outcomes[item_id] = value
            observation.emit("vector_candidate", item_id=item_id, outcome=value, reason="prepare_excluded")
            continue
        scope, config, digest, version = value.work
        try:
            received = projection._received.get(item_id) or projection.journal.read(scope.world_id, item_id)
        except ResultJournalError:
            projection.last_code = "memory_embedding_result_invalid"
            outcomes[item_id] = "local_result_invalid"
            continue  # Keep the invalid receipt, but don't starve unrelated items.
        if received is not None:
            with _scope(projection, value), observation.scope(purpose="document_recovery"):
                observation.emit("result", boundary="reuse", receipt_id=received.get("receipt_id"), reused=True)
                outcomes[item_id] = await projection._canonical.call(persist, projection, value, received)
            continue
        identity = projection.index.identity(f"memory-item:{item_id}")
        if identity and identity[1:] == (digest, config.profile):
            # Use the same final canonical fence as a newly returned vector;
            # refresh metadata only after the fresh source/credential read.
            from app.runtime.memory.vector_delivery import refresh_current
            with _scope(projection, value):
                outcomes[item_id] = await projection._canonical.call(refresh_current, projection, value)
                observation.emit("result", boundary="current", outcome=outcomes[item_id], current=outcomes[item_id] == "current")
            continue
        with _scope(projection, value):
            claim = projection._claims.get(item_id)
            observation.emit("vector_candidate", outcome="pending", desired_revision=claim.revision if claim else None)
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
                reason = "single_only_provider" if not batch else "item_limit" if len(chunk) >= limits.max_items else "byte_limit"
                await _submit(projection, provider, chunk, outcomes, reason=reason, group_size=len(group))
                chunk = []
            chunk.append(prepared)
        if chunk:
            await _submit(projection, provider, chunk, outcomes, reason="ready_group_end", group_size=len(group))
    return outcomes


def _scope(projection, prepared):
    scope, config, digest, version = prepared.work
    return observation.scope(world_id=scope.world_id, actor_id=scope.subject_world_character_id,
        item_id=prepared.item_id, content_hash=digest, version=version, profile=config.profile,
        credential_id=prepared.material.credential_id, credential_revision=prepared.revision, generation=projection.generation)


async def _submit(projection, provider, candidates, outcomes, *, reason, group_size):
    with _scope(projection, candidates[0]), observation.span("embedding_batch", batch_id=uuid4().hex, purpose=observation.facts().get("purpose", "document_incremental")):
        observation.emit("embedding_batch", boundary="candidates", count=len(candidates), reason=reason, group_size=group_size,
            members=[{"item_id": p.item_id, "content_hash": p.work[2], "version": p.work[3],
                "byte_size": len(embedding_text(p.document.text, query=False).encode())} for p in candidates])
        return await _submit_batch(projection, provider, candidates, outcomes)


async def _submit_batch(projection, provider, candidates, outcomes):
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
            tuple((f"memory-item:{p.item_id}", p.work[1].profile, p.work[2], p.attempt_revision) for p in eligible),
            prepared=tuple(eligible)) if eligible else set()
    except Exception as exc:
        if not is_sqlite_contention(exc):
            raise
        outcomes.update((p.item_id, "deferred") for p in eligible)
        return
    admitted = [p for p in eligible if f"memory-item:{p.item_id}" in claimed]
    outcomes.update((p.item_id, "attempts_exhausted") for p in eligible if p not in admitted)
    observation.emit("embedding_batch", boundary="excluded", outcomes=[{"item_id":p.item_id, "outcome":outcomes[p.item_id]} for p in candidates if p.item_id in outcomes])
    if not admitted:
        return
    observation.emit("embedding_batch", boundary="admitted", input_count=len(admitted), item_ids=[p.item_id for p in admitted], reason="same_scope_config_revision_ready_chunk")
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
        observation.emit("embedding_batch", boundary="failed", outcome="provider_failed")
        projection.last_code = "memory_embedding_failed"
        return
    # Own all received values before any individual write can fail or cancel.
    for p, vector in zip(admitted, vectors, strict=True):
        projection._received[p.item_id] = {"binding": p.binding, "vector": list(vector), "receipt_id": uuid4().hex}
    observation.emit("embedding_batch", boundary="received", response_count=len(vectors))
    await projection._canonical.call(_preserve, projection, admitted)
    if projection._closing:
        outcomes.update((p.item_id, "deferred") for p in admitted)
        return
    for p in admitted:
        with _scope(projection, p):
            outcomes[p.item_id] = await projection._canonical.call(persist, projection, p, projection._received[p.item_id])
            observation.emit("result", boundary="persisted", outcome=outcomes[p.item_id])
        observation.emit("wait", boundary="yield", reason="per_item_fairness")
        await asyncio.sleep(0)  # A short per-item UoW gives other writers a turn.


@observation.observed("received_result_preserve")
def _preserve(projection, admitted):
    from app.core.result_journal import ResultJournalError
    for p in admitted:
        try:
            projection.journal.write(p.work[0].world_id, p.item_id, projection._received[p.item_id])
            with _scope(projection, p):
                observation.emit("result", boundary="journal_preserved", receipt_id=projection._received[p.item_id]["receipt_id"])
        except (ResultJournalError, OSError):
            # Keep the bounded in-process owner. persist performs classification
            # and fresh authority checks; this is not another provider attempt.
            continue
