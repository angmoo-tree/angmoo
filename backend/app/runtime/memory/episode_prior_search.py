"""Optional bounded lexical prior candidates; no embeddings or model calls."""

from time import monotonic
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind, MemoryRecallLexicalPolicy
from app.domains.memory.contracts.hybrid_recall import RecallAxisStatus


def episode_prior_search(index):
    def search(bundle):
        texts = [member.text for unit in bundle.new_units for member in unit.members]
        # Every input can contribute a short fragment; this is only candidate
        # discovery. The full originals remain in the consolidation prompt.
        allowance = max(1, 950 // max(1, len(texts)))
        query = " ".join(text[:allowance] for text in texts)[:1000]
        try:
            result = index.search_grouped(MemoryRecallSearchQuery(bundle.scope, query,
                (RecallDocumentKind.MEMORY_ITEM,), 50, lexical_policy=MemoryRecallLexicalPolicy.GROUP_OR_V1),
                deadline=monotonic() + 0.5)
            if result.status not in {RecallAxisStatus.READY, RecallAxisStatus.PARTIAL}:
                return ()
            return tuple(dict.fromkeys(candidate.memory_item_id for candidate in result.candidates))
        except (RuntimeError, OSError):
            # A missing optional projection does not authorize new facts.
            # Exact links/recent canonical candidates remain available.
            return ()
    return search
