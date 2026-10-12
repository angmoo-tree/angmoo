"""Lifetime and native derived-store checks for scoped erasure."""
import asyncio
from dataclasses import replace
from app.runtime.world_scope_streams import WorldScopeStreams
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from test_l3_er3_ladybug_projection import _event, _relationship


def test_scope_signal_closes_target_stream_and_keeps_other_world_running():
    async def exercise():
        registry = WorldScopeStreams()
        entered = {"a": asyncio.Event(), "b": asyncio.Event()}
        gate = asyncio.Event()
        async def events(world):
            entered[world].set()
            await gate.wait()
            yield world
        async def consume(world):
            return [event async for event in registry.track(world, events(world))]
        a = asyncio.create_task(consume("a"))
        b = asyncio.create_task(consume("b"))
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 1)
        registry.close_world("a")
        results = await asyncio.gather(a, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert not b.done()
        gate.set()
        assert await b == ["b"]
        assert registry._streams == {}
    asyncio.run(exercise())


def test_native_graph_erasure_is_bounded_durable_and_fences_late_commands(tmp_path):
    root = tmp_path / "graph"
    a = _relationship()
    b = _event(world_id="world-b", event_id="event-b", actor_id="actor-b", target_id=None)
    with LadybugRelationshipProjection(database_root=root) as graph:
        graph.apply(a)
        graph.apply(b)
        survivor = graph.world_digest("world-b")
        for _ in range(10):
            if graph.erase_world(a.event.world_id, batch_size=1):
                break
        else:
            raise AssertionError("bounded graph erase did not finish")
        assert all(not values for values in graph.world_digest(a.event.world_id).values())
        assert graph.world_digest("world-b") == survivor
        assert graph.apply(a) == "world_erased"
    with LadybugRelationshipProjection(database_root=root) as graph:
        assert graph.apply(a) == "world_erased"
        assert graph.world_digest("world-b") == survivor
