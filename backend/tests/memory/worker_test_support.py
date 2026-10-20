"""Keep native pools on one loop and assert real shutdown, including failed tests."""
import asyncio
import pytest


@pytest.fixture
def worker_lifetime():
    with asyncio.Runner() as runner:
        pools = []

        class Lifetime:
            run = staticmethod(runner.run)

            @staticmethod
            def track(pool):
                pools.append(pool)
                return pool

        try:
            yield Lifetime()
        finally:
            async def stop():
                for pool in pools:
                    await pool.stop()
                    assert not pool.active_processes
            runner.run(stop())
