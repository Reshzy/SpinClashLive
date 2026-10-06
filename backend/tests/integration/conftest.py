from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from color_rush.application.coordinator import Coordinator
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.domain.enums import SessionMode

ROOT = Path(__file__).resolve().parents[3]


def _database_url() -> str | None:
    return os.environ.get("COLOR_RUSH_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _run_upgrade(url: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(_alembic_config(url), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    url = _database_url()
    if not url:
        pytest.skip("COLOR_RUSH_TEST_DATABASE_URL is not set")
    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    _run_upgrade(url)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def db_session(pg_engine: Engine) -> Iterator[Session]:
    connection = pg_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 10, 4, 8, 0, tzinfo=UTC))


@pytest.fixture
def coordinator(db_session: Session, clock: FrozenClock) -> Coordinator:
    return Coordinator(
        db_session,
        clock=clock,
        rng=SequenceRng([960]),
        owner_id="test-worker",
        lease_ttl_seconds=30,
        partition_count=4,
    )


@pytest.fixture
def redis_client() -> Iterator[object]:
    url = os.environ.get("COLOR_RUSH_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    from redis import Redis
    from redis.exceptions import RedisError

    client = Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except RedisError as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def started_session(coordinator: Coordinator, db_session: Session) -> tuple[object, int]:
    game = coordinator.create_game()
    db_session.flush()
    game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL)
    token = coordinator.claim_lease(game_session.id).fencing_token
    return game_session, token
