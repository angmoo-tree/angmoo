"""Selected-target recall through the already composed FTS5/Vec1/RRF service."""
import asyncio
from dataclasses import asdict
import json
from datetime import UTC, datetime
from time import monotonic

from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.runtime.autonomous_activity.contracts import MEMORY_CHARS, MEMORY_LIMIT, RECALL_CONCURRENCY, identity_key


def bounded_records(records):
    """Retain whole summary/units and disclose omissions, never clip JSON/text."""
    packets = []
    omitted_units = 0
    for record in records:
        if len(packets) >= MEMORY_LIMIT:
            break
        packet = json.loads(record.text) if record.metadata.get("episode_packet") == "v1" else {"ref": record.reference, "situation": record.text, "units": [], "partial": True}
        units = list(packet.get("units", []))
        packet = {**packet, "units": []}
        packet["omitted_units"] = packet.get("omitted_units", 0) + len(units)
        if len(json.dumps([*packets, packet], ensure_ascii=False)) > MEMORY_CHARS:
            break
        for unit in units:
            trial = {**packet, "units": [*packet["units"], unit], "omitted_units": packet["omitted_units"] - 1}
            if len(json.dumps([*packets, trial], ensure_ascii=False)) <= MEMORY_CHARS:
                packet = trial
        packet["partial"] = packet.get("partial", False) or bool(packet["omitted_units"])
        omitted_units += packet["omitted_units"]
        packets.append(packet)
    # If a linked correction fell outside this smaller SNS budget, do not
    # present its earlier version as an unqualified current recollection.
    all_packets = [json.loads(r.text) for r in records if r.metadata.get("episode_packet") == "v1"]
    delivered = {p.get("ref") for p in packets}
    missing_followups = {ref for p in all_packets if p.get("ref") not in delivered for ref in p.get("follows", [])}
    for packet in packets:
        if packet.get("ref") in missing_followups:
            packet["followup_truncated"] = True
            packet["partial"] = True
    return {"packets": packets, "omitted_packets": len(records) - len(packets), "omitted_units": omitted_units}


def context_memories(memories):
    """One packet body per call, retaining every target-to-memory association."""
    seen = set()
    result = {}
    for target, value in memories.items():
        packets = []
        for packet in value.get("packets", []):
            ref = packet.get("ref")
            packets.append({"ref": ref, "already_in_context": True} if ref in seen else packet)
            if ref:
                seen.add(ref)
        result[target] = {**value, "packets": packets}
    return result


class SelectedRecall:
    def __init__(self, service, *, owner_id, world_id, actor_id):
        self.service = service
        self.scope = MemoryScope(owner_id, world_id, actor_id)
        self._limit = asyncio.Semaphore(RECALL_CONCURRENCY)

    async def one(self, *, activity_id: str, target: dict, query: dict):
        text = query["query"]
        if not text:
            return {"status": "no_query_material", "packets": []}
        if self.service is None:
            return {"status": "unavailable", "reason": "hybrid_service_unavailable", "packets": []}
        key = identity_key(activity_id, target["target_id"], text)
        request = HybridRecallRequest(request_id=activity_id, call_id=key, envelope_hash=key,
            scope=self.scope, search_text=text, profile=EMBEDDING_PROFILE,
            kinds=(RecallDocumentKind.MEMORY_ITEM,), result_limit=MEMORY_LIMIT,
            counterpart_world_character_id=target.get("counterpart_id"), thread_id=None)
        try:
            async with self._limit:
                retrieved_after = datetime.now(UTC).isoformat()
                result = await self.service.execute(request, deadline=monotonic() + 15)
        except (TimeoutError, OSError):
            return {"status": "unavailable", "reason": "recall_transport_unavailable", "packets": []}
        except RuntimeError as exc:
            if str(exc) != "hybrid_all_axes_unavailable":
                raise
            return {"status": "unavailable", "reason": str(exc), "packets": []}
        # Scope errors and cancellation propagate; they are never "no memory".
        if result.scope != self.scope:
            raise ValueError("recall_scope_mismatch")
        packet = bounded_records(result.records)
        return {**packet, "status": "empty" if not result.records else "partial" if result.status.value == "partial" or packet["omitted_units"] or packet["omitted_packets"] else "ready",
            "ranked_memory_ids": [r.memory_item_id for r in result.records],
            "retrieved_after": retrieved_after,
            "duration_ms": result.duration_ms, "axes": [json.loads(json.dumps(asdict(a), default=lambda v: v.value)) for a in result.axes],
            "embedding_usage": asdict(result.embedding_usage)}

    async def selected(self, *, activity_id, targets, queries):
        by_id = {t["target_id"]: t for t in targets}
        # An invalid target cannot broaden the search to an entire World.
        if any(q["target_id"] not in by_id for q in queries):
            raise ValueError("recall_target_invalid")
        results = await asyncio.gather(*(self.one(activity_id=activity_id, target=by_id[q["target_id"]], query=q) for q in queries))
        return dict(zip((q["target_id"] for q in queries), results, strict=True))
