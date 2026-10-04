from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from color_rush.application.dto import NormalizedCommand
from color_rush.application.ingest import append_and_process
from color_rush.application.settlement import settle_round
from color_rush.composition import AppContainer, build_container
from color_rush.config import get_settings
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import Color
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import session_scope

_container: AppContainer | None = None


def get_container() -> AppContainer:
    global _container
    if _container is None:
        _container = build_container()
    return _container


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Color Rush Live", version="0.1.0")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        container = get_container()
        with container.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "env": settings.color_rush_env}

    if settings.is_simulation:
        _mount_simulation(app)

    return app


class SimCommand(BaseModel):
    session_id: str
    broadcast_id: str = "sim-broadcast"
    provider_channel_id: str
    display_name: str
    text: str
    published_at: str
    message_id: str


class SimStartRound(BaseModel):
    session_id: str
    fence_token: int = Field(ge=1)


class SimSpin(BaseModel):
    session_id: str
    fence_token: int
    forced: Color | None = None


def _mount_simulation(app: FastAPI) -> None:
    @app.post("/simulation/commands")
    def simulation_commands(body: SimCommand) -> dict[str, Any]:
        from datetime import datetime
        from uuid import UUID

        container = get_container()
        command = NormalizedCommand(
            provider="simulation",
            provider_message_id=body.message_id,
            broadcast_id=body.broadcast_id,
            provider_channel_id=body.provider_channel_id,
            display_name=body.display_name,
            command_text=body.text,
            command=parse_command(body.text),
            published_at=datetime.fromisoformat(body.published_at),
        )
        with session_scope(container.session_factory) as session:
            result = append_and_process(
                session,
                session_id=UUID(body.session_id),
                commands=[command],
                checkpoint=None,
            )
        return {
            "sequences": list(result.sequences),
            "decisions": [item.value for item in result.decisions],
        }

    @app.post("/simulation/rounds/start")
    def simulation_start(body: SimStartRound) -> dict[str, Any]:
        from uuid import UUID

        container = get_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.start_round(UUID(body.session_id), body.fence_token, RoundRules())
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/close")
    def simulation_close(body: SimStartRound) -> dict[str, Any]:
        from uuid import UUID

        container = get_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.close_ingress(UUID(body.session_id), body.fence_token, early=True)
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/drain")
    def simulation_drain(body: SimStartRound) -> dict[str, Any]:
        from uuid import UUID

        container = get_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.complete_drain(UUID(body.session_id), body.fence_token)
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/spin")
    def simulation_spin(body: SimSpin) -> dict[str, Any]:
        from uuid import UUID

        container = get_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.spin(UUID(body.session_id), body.fence_token, forced=body.forced)
        return {"round_id": str(rnd.id), "state": rnd.state, "result": rnd.result}

    @app.post("/simulation/rounds/settle")
    def simulation_settle(body: SimStartRound) -> dict[str, Any]:
        from uuid import UUID

        container = get_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.advance_after_spin(UUID(body.session_id), body.fence_token)
            if rnd.state != "settling":
                rnd = coordinator.advance_after_spin(UUID(body.session_id), body.fence_token)
            settle_round(session, rnd.id, container.clock.now())
            if not _jobs_complete(session, rnd.id):
                raise HTTPException(status_code=409, detail="settlement incomplete")
            rnd = coordinator.mark_settled(UUID(body.session_id), body.fence_token)
        return {"round_id": str(rnd.id), "state": rnd.state}


def _jobs_complete(session: object, round_id: object) -> bool:
    from color_rush.application.settlement import all_partitions_complete

    return all_partitions_complete(session, round_id)  # type: ignore[arg-type]


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("color_rush.api.app:app", host=settings.color_rush_host, port=settings.color_rush_port)
