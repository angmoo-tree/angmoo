"""Real plan writes run off-loop; AI remains async with no checked-out DB."""
import asyncio
from datetime import datetime,UTC
from threading import get_ident
from types import SimpleNamespace
from time import sleep
from sqlalchemy import event,select
from postgresql.test_activity_transactions import store
from routines import test_daily_preparation as fixture_source
from app.domains.routines.client import PreparationTracker
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.schemas.daily_generation import InitialPreparationOutput


def test_daily_preparation_db_stages_and_physical_reservation_release_session(store,monkeypatch,deny_external_network):
    engine,_,_=store
    monkeypatch.setattr(fixture_source,'_engine',lambda:engine)
    fixture=fixture_source.preparation_scope.__wrapped__(monkeypatch,deny_external_network)
    db,world,ready,runtime=next(fixture)
    character_id,world_id,owner_id=ready.character.id,world.id,ready.user.id
    db.rollback()
    main=get_ident();sql_threads=[];provider_calls=[];ticks=[]
    original_source=runtime._source
    def slow_source(*args,**kwargs):
        sleep(.08)
        return original_source(*args,**kwargs)
    monkeypatch.setattr(runtime,'_source',slow_source)
    def before(*_):sql_threads.append(get_ident())
    event.listen(engine,'before_cursor_execute',before)
    async def generate(**kwargs):
        tracker=PreparationTracker(kwargs['reserve'])
        assert await tracker.reserve_provider_call_order()==1
        assert engine.pool.checkedout()==0
        assert get_ident()==main
        provider_calls.append(1)
        await asyncio.sleep(.03)
        return InitialPreparationOutput(daily_plan=fixture_source.output(),
            recommendation_topics=[{'name':'독서','scope':'common'}]),tracker
    async def scenario():
        async def heartbeat():
            while True:
                ticks.append(1)
                await asyncio.sleep(.005)
        pulse=asyncio.create_task(heartbeat())
        try:
            return await runtime.ensure_preparation(db,character_id=character_id,world_id=world_id,
                user=SimpleNamespace(id=owner_id),request_id='async-preparation',
                # Reservation checks the live lease clock. This test measures
                # execution ownership, not a historical calendar boundary.
                generator=generate,now=datetime.now(UTC))
        finally:
            pulse.cancel()
            await asyncio.gather(pulse,return_exceptions=True)
    try:
        result=asyncio.run(scenario())
        assert result.plan_state=='ready',result
        assert provider_calls==[1] and len(ticks)>=20
        assert sql_threads and main not in sql_threads
        assert engine.pool.checkedout()==0
        event.remove(engine,'before_cursor_execute',before)
        job=db.scalar(select(ActivityPreparationJob).where(ActivityPreparationJob.request_id=='async-preparation'))
        assert job.state=='ready' and job.attempt_count==1
    finally:
        if event.contains(engine,'before_cursor_execute',before):event.remove(engine,'before_cursor_execute',before)
        fixture.close()
