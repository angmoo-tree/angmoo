"""After-commit queue hints; durable queue reads and bounded polling own truth."""
import asyncio
from sqlalchemy import event
from sqlalchemy.orm import Session


class CommittedQueueWakeup:
    def __init__(self, sessions, tables):
        with sessions() as db:
            self.engine = db.get_bind()
        self.enabled = self.engine.dialect.name == 'postgresql'
        self.wake = asyncio.Event()
        self.loop = asyncio.get_running_loop()
        self.closed = False
        self.tables = frozenset(tables)
        self.marker = f'committed_queue_wakeup_{id(self)}'
        self.listeners = (("after_flush", self._flushed), ("do_orm_execute", self._executed),
            ("after_commit", self._committed), ("after_rollback", self._rolled_back))
        if self.enabled:
            for name, callback in self.listeners:
                event.listen(Session, name, callback)

    def _owns(self, session):
        bind = session.get_bind()
        return getattr(bind, 'engine', bind) is self.engine

    def _flushed(self, session, context):
        if self._owns(session) and any(getattr(getattr(row, '__table__', None), 'name', None) in self.tables
                for row in (*session.new, *session.dirty, *session.deleted)):
            session.info[self.marker] = True

    def _executed(self, state):
        if (state.is_insert or state.is_update or state.is_delete) and self._owns(state.session):
            if getattr(getattr(state.statement, 'table', None), 'name', None) in self.tables:
                state.session.info[self.marker] = True

    def _committed(self, session):
        if session.in_nested_transaction():
            return
        if session.info.pop(self.marker, False):
            self.notify()

    def _rolled_back(self, session):
        # Retain a conservative hint for earlier writes in an outer transaction.
        # A rolled-back savepoint may cause a harmless empty scan after commit.
        if not session.in_nested_transaction():
            session.info.pop(self.marker, None)

    def notify(self):
        if not self.closed and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.wake.set)
            except RuntimeError:
                if not self.loop.is_closed():
                    raise

    def begin_poll(self):
        # Clear before reading the queue, never after it: a commit concurrent
        # with that read must still wake the following wait.
        self.wake.clear()

    async def wait(self, timeout):
        try:
            await asyncio.wait_for(self.wake.wait(), timeout)
        except TimeoutError:
            pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.enabled:
            for name, callback in self.listeners:
                event.remove(Session, name, callback)
        self.wake.set()
