from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    database_url = settings.database_url
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


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
