from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str):
    sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if sqlite else {},
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA busy_timeout = 5000")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = FULL")
                cursor.execute("PRAGMA wal_autocheckpoint = 1000")
            finally:
                cursor.close()
    return engine


def create_session_factory(database_engine):
    return sessionmaker(
        bind=database_engine,
        autoflush=False,
        autocommit=False,
    )


_default_engine: Engine | None = None
_default_session_factory: sessionmaker[Session] | None = None


def get_default_engine() -> Engine:
    """Create the transitional default engine only for a legacy caller.

    Official embedded composition passes an explicit SQLite engine and session
    factory. Importing the public application must therefore not load the
    PostgreSQL DBAPI, which is deliberately absent from the packaged sidecar,
    merely because compatibility callers remain before PR P.
    """

    global _default_engine, _default_session_factory
    if _default_engine is None:
        _default_engine = create_database_engine(settings.database_url)
        _default_session_factory = create_session_factory(_default_engine)
    return _default_engine


def get_default_session_factory() -> sessionmaker[Session]:
    global _default_session_factory
    if _default_session_factory is None:
        get_default_engine()
    assert _default_session_factory is not None
    return _default_session_factory


def SessionLocal() -> Session:
    """Compatibility callable retained until PR P removes legacy globals."""

    return get_default_session_factory()()


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
