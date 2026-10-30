"""Optional bounded, content-free observer for the isolated A/B/C experiment.

Run instead of the existing entrypoint with the same arguments. The installed
product functions, transaction policies, pools and validation remain unchanged.
No SQL text, parameters, request bodies, URLs or credentials are persisted.
"""
from contextlib import asynccontextmanager
from collections import deque
import asyncio
import hashlib
import json
import pathlib
import sys
from threading import Lock, current_thread
from time import monotonic

BOUNDS = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000, 30000)


class Metrics:
    def __init__(self):
        self.lock = Lock()
        self.values = {}
        self.slow = deque(maxlen=64)
        self.started = monotonic()

    def record(self, key, milliseconds, *, code=None, site=None):
        with self.lock:
            # Keep fixed counters addressable after bounded SQL cardinality
            # fills up; provider attempts must never disappear into "other".
            if key not in self.values and len(self.values) >= 250 and key.startswith('sql:'):
                key = 'other'
            row = self.values.setdefault(key, {'count':0,'total_ms':0,'max_ms':0,
                'failures':0,'histogram':[0]*(len(BOUNDS)+1)})
            row['count'] += 1
            row['total_ms'] += milliseconds
            row['max_ms'] = max(row['max_ms'], milliseconds)
            row['failures'] += int(code is not None)
            if site is not None and 'site' not in row:
                row['site'] = site
            row['histogram'][next((i for i,b in enumerate(BOUNDS) if milliseconds <= b),len(BOUNDS))] += 1
            if milliseconds >= 250 or code:
                self.slow.append({'elapsed_seconds':round(monotonic()-self.started,3),
                    'kind':key,'milliseconds':round(milliseconds,3),'code':code,'site':site,
                    'thread':current_thread().name[:48]})

    def snapshot(self):
        with self.lock:
            return {'elapsed_seconds':round(monotonic()-self.started,3),'bounds_ms':BOUNDS,
                    'metrics':{k:{**v,'histogram':list(v['histogram'])} for k,v in self.values.items()},
                    'recent_slow':list(self.slow)}


METRICS = Metrics()
ENGINES = []


def observe(engine):
    from sqlalchemy import event
    if engine.dialect.name != 'postgresql':
        return engine
    ENGINES.append(engine)
    original = engine.pool.connect

    def connect():
        started = monotonic()
        try:
            result = original()
        except BaseException as exc:
            METRICS.record('acquire', (monotonic()-started)*1000, code=type(exc).__name__)
            raise
        METRICS.record('acquire', (monotonic()-started)*1000)
        return result

    engine.pool.connect = connect

    @event.listens_for(engine, 'checkout')
    def checkout(dbapi, record, proxy):
        record.info['load_checkout_at'] = monotonic()

    @event.listens_for(engine, 'checkin')
    def checkin(dbapi, record):
        start = record.info.pop('load_checkout_at', None)
        if start is not None:METRICS.record('hold', (monotonic()-start)*1000)

    @event.listens_for(engine, 'begin')
    def begin(connection):connection.info['load_transaction_at'] = monotonic()

    def end_transaction(connection):
        start=connection.info.pop('load_transaction_at',None)
        if start is not None:METRICS.record('transaction', (monotonic()-start)*1000)
    event.listen(engine,'commit',end_transaction)
    event.listen(engine,'rollback',end_transaction)

    @event.listens_for(engine, 'before_cursor_execute')
    def before(connection,cursor,statement,parameters,context,many):
        context._load_started = monotonic()
        context._load_digest = hashlib.sha256(statement.encode()).hexdigest()[:16]
        context._load_site = None
        frame=sys._getframe(1)
        for _ in range(64):
            if frame is None:break
            name=frame.f_code.co_filename.replace('\\','/')
            if '/app/' in name and '/site-packages/' not in name:
                context._load_site=name.rsplit('/app/',1)[-1]+':'+str(frame.f_lineno)
                break
            frame=frame.f_back

    @event.listens_for(engine, 'after_cursor_execute')
    def after(connection,cursor,statement,parameters,context,many):
        METRICS.record('sql:'+context._load_digest,(monotonic()-context._load_started)*1000,site=context._load_site)

    @event.listens_for(engine, 'handle_error')
    def error(context):
        execution=context.execution_context
        if execution is not None and hasattr(execution,'_load_started'):
            code=getattr(context.original_exception,'sqlstate',None) or type(context.original_exception).__name__
            METRICS.record('sql:'+execution._load_digest,(monotonic()-execution._load_started)*1000,code=code,site=execution._load_site)
    return engine


def attach(app, destination):
    original_lifespan=app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as state:
            stop=asyncio.Event()

            async def sample():
                previous=monotonic();next_write=previous
                while not stop.is_set():
                    await asyncio.sleep(.25)
                    now=monotonic()
                    METRICS.record('event_loop_lag',max(0,now-previous-.25)*1000)
                    previous=now
                    if now>=next_write:
                        value=METRICS.snapshot()
                        value['pools']=[{'size':e.pool.size(),'checked_out':e.pool.checkedout(),'overflow':e.pool.overflow()} for e in ENGINES]
                        destination.write_text(json.dumps(value))
                        next_write=now+5
            task=asyncio.create_task(sample(),name='postgresql-observation')
            try:yield state
            finally:
                stop.set();task.cancel()
                try:await task
                except asyncio.CancelledError:pass
                destination.write_text(json.dumps(METRICS.snapshot()))
    app.router.lifespan_context=lifespan


def main():
    from app.integrations.direct_llm import RunLlmTracker
    original_provider_order = RunLlmTracker.next_provider_call_order
    def provider_order(self):
        value = original_provider_order(self)
        METRICS.record('provider_physical_attempt', 0)
        return value
    RunLlmTracker.next_provider_call_order = provider_order
    import app.database as database
    original_engine=database.create_database_engine
    database.create_database_engine=lambda *a,**kw:observe(original_engine(*a,**kw))
    import app.runtime.postgresql_backend as backend
    original_app=backend.create_app
    def create(root,*args,**kwargs):
        app=original_app(root,*args,**kwargs)
        attach(app,pathlib.Path(root)/'runtime/postgresql-observation.json')
        return app
    backend.create_app=create
    backend.main()


if __name__=='__main__':main()
