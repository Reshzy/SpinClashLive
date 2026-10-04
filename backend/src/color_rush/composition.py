from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from color_rush.application.coordinator import Coordinator
from color_rush.application.ports import Clock, Rng, SecureRng, SystemClock
from color_rush.config import Settings, get_settings
from color_rush.infrastructure.persistence.db import create_db_engine, create_session_factory


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    clock: Clock
    rng: Rng
    worker_id: str

    def coordinator(self, session: Session) -> Coordinator:
        return Coordinator(
            session,
            clock=self.clock,
            rng=self.rng,
            owner_id=self.worker_id,
            lease_ttl_seconds=self.settings.coordinator_lease_ttl_seconds,
            partition_count=self.settings.settlement_partition_count,
        )


def build_container(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    rng: Rng | None = None,
) -> AppContainer:
    resolved = settings or get_settings()
    engine = create_db_engine(resolved.database_url)
    return AppContainer(
        settings=resolved,
        engine=engine,
        session_factory=create_session_factory(engine),
        clock=clock or SystemClock(),
        rng=rng or SecureRng(),
        worker_id=resolved.color_rush_worker_id,
    )
