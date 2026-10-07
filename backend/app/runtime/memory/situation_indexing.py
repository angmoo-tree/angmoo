"""Observe admitted quit search work within the host's existing deadline."""
import asyncio
from sqlalchemy import select

from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationRequest
from app.domains.memory.repository.vector_work import read_work


class SituationSearchDrain:
    def __init__(self, hybrid, fts):
        self.hybrid, self.fts = hybrid, fts

    async def wait(self, situations):
        # The normal projector owns embedding calls. This observer neither
        # triggers a whole-library preparation nor invokes a provider itself.
        while True:
            cursor, pending = 0, False
            while True:
                with situations.session_factory() as db:
                    rows = db.execute(select(MemorySituationReceipt.sequence, MemorySituationReceipt.applied_item_id).where(
                        MemorySituationReceipt.run_id.in_(select(MemorySituationRequest.run_id).where(
                            MemorySituationRequest.request_key == situations.quit_identity)),
                        MemorySituationReceipt.state == "applied", MemorySituationReceipt.sequence > cursor,
                    ).order_by(MemorySituationReceipt.sequence).limit(100)).all()
                    expected = [(identifier, work[3], work[2], work[1].profile)
                        for _, identifier in rows if identifier is not None
                        if (work := read_work(db, identifier)) is not None]
                # Canonical read transactions are closed before projection I/O
                # or waiting for a slow provider owned by the background worker.
                projection = self.hybrid.projection
                if expected and projection is None:
                    return False
                for identifier, version, digest, profile in expected:
                    identity = projection.index.identity(f"memory-item:{identifier}")
                    pending |= identity is None or tuple(identity) != (version, digest, profile)
                if not rows or len(rows) < 100:
                    break
                cursor = rows[-1][0]
                await asyncio.sleep(0)
            fts_state = self.fts.state.value
            if fts_state in {"degraded", "stopped"}:
                return False
            if not pending and fts_state == "ready":
                return True
            if self.hybrid.read_status() in {"degraded", "vector_unavailable"}:
                return False
            await asyncio.sleep(0.1)

    def fence(self):
        projection = self.hybrid.projection
        if projection is not None:
            projection.fence()
