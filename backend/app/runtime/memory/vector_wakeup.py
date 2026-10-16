"""Optional after-commit wake hint. Persisted changes and due polling own truth."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app.runtime.memory.vector_mutations import catalog


class VectorWakeup:
    def __init__(self, projection, loop):
        watched = {entry["table"]: entry["columns"] for entry in catalog()}
        engine = projection._factory.kw.get("bind")
        marker = f"vector_wake_{id(self)}"

        def flushed(session, context):
            bind = session.get_bind()
            if getattr(bind, "engine", bind) is engine and any(row.__table__.name in watched and
                (row in session.new or row in session.deleted or any(inspect(row).attrs[column].history.has_changes()
                    for column in watched[row.__table__.name]))
                for row in (*session.new, *session.dirty, *session.deleted)):
                session.info[marker] = True

        def committed(session):
            if session.info.pop(marker, False) and not projection._closing:
                loop.call_soon_threadsafe(projection._wake.set)

        def rolled_back(session):
            session.info.pop(marker, None)

        self.listeners = (("after_flush", flushed), ("after_commit", committed), ("after_rollback", rolled_back))
        for name, callback in self.listeners:
            event.listen(Session, name, callback)

    def close(self):
        for name, callback in self.listeners:
            event.remove(Session, name, callback)
