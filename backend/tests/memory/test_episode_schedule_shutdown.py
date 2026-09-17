import asyncio
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.items import MemoryItem
from app.runtime.memory.batch_runtime import MemoryBatchRuntime
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory.source_delivery import install_memory_delivery, uninstall_memory_delivery
from memory.test_p8_l_r_memory_batch_safety import memory_session, _stack, _save, _post
from memory.test_episode_selection_service import Provider


def test_scheduled_then_new_activity_shutdown_uses_episode_lane_once(memory_session):
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope, schedule_enabled=True)
    db.commit()
    factory = sessionmaker(bind=db.bind)
    provider = Provider()
    runtime = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1",
        episode_provider_factory=lambda *args: provider)
    install_memory_delivery(factory)
    try:
        with factory() as current:
            _post(current, scope, "scheduled-episode-source")
            config = current.get(MemoryBatchSetting, setting.id)
            config.next_due_at = datetime.now(UTC) - timedelta(seconds=1)
            current.commit()
        assert asyncio.run(runtime.tick()) == "memory_selection_completed"
        assert provider.calls == 1
        with factory() as current:
            _post(current, scope, "shutdown-after-schedule-source")
        assert asyncio.run(runtime.tick()) == "memory_batch_queue_empty"
        assert provider.calls == 1
        assert asyncio.run(runtime.tick(shutdown=True)) == "memory_selection_completed"
        assert provider.calls == 2
        # Repeated shutdown and a freshly constructed worker do not summarize again.
        restarted = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1",
            episode_provider_factory=lambda *args: provider)
        assert asyncio.run(restarted.tick(shutdown=True)) == "memory_batch_queue_empty"
        assert provider.calls == 2
        with factory() as current:
            assert current.scalar(select(func.count(MemoryItem.id))) == 2
    finally:
        uninstall_memory_delivery(factory)
