from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from color_rush.application.ports import SessionLockKey


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    return create_engine(url, echo=echo, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def acquire_session_lock(session: Session, session_id: object) -> None:
    key = SessionLockKey.for_session(session_id)  # type: ignore[arg-type]
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def database_clock(session: Session) -> datetime:
    value = session.execute(text("SELECT clock_timestamp()")).scalar_one()
    assert isinstance(value, datetime)
    return value


def hash_partition(session: Session, player_id: object, partition_count: int) -> int:
    value = session.execute(
        text("SELECT abs(hashtext(CAST(:pid AS text)))"),
        {"pid": str(player_id)},
    ).scalar_one()
    return int(value) % partition_count
