from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from color_rush.application.coordinator import Coordinator
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.domain.enums import SessionMode
from color_rush.infrastructure.persistence.models import Base


def _database_url() -> str | None:
    return os.environ.get("COLOR_RUSH_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


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
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
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
def started_session(coordinator: Coordinator, db_session: Session) -> tuple[object, int]:
    game = coordinator.create_game()
    db_session.flush()
    game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL)
    token = coordinator.claim_lease(game_session.id).fencing_token
    return game_session, token
