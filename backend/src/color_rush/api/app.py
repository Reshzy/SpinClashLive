from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text

from color_rush.api.errors import domain_error_handler, error_body, request_id_of
from color_rush.api.routes import admin_router, auth_router, game_router
from color_rush.api.ws import ws_router
from color_rush.application.dto import NormalizedCommand
from color_rush.application.ingest import append_and_process
from color_rush.application.settlement import settle_round
from color_rush.composition import AppContainer, get_runtime_container, set_runtime_container
from color_rush.config import get_settings
from color_rush.domain.clock import utc_now
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import Color
from color_rush.domain.errors import AuthError, DomainError, SettlementError
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import IdempotencyKey
from color_rush.infrastructure.redis.projections import redis_available
from color_rush.infrastructure.security import decode_access_token
from color_rush.observability import configure_logging
from color_rush.observability.metrics import record_http

_rate_buckets: dict[str, list[float]] = defaultdict(list)

OVERLAY_PLACEHOLDER = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Color Rush Live overlay</title>
<style>
body {
  margin: 0;
  background: #16181d;
  color: #f4f6fb;
  font: 20px/1.4 Segoe UI, sans-serif;
  display: grid;
  place-items: center;
  min-height: 100vh;
}
main { text-align: center; max-width: 720px; padding: 32px; }
.kicker {
  color: #ff8a3d;
  letter-spacing: .12em;
  text-transform: uppercase;
  font-size: 14px;
}
</style>
</head>
<body>
<main>
<p class="kicker">OBS Browser Source</p>
<h1>Color Rush Live</h1>
<p>Build the overlay with <code>npm run build</code> in <code>overlay/</code>, then reload this URL.</p>
<p>Recommended sizes: 1920x1080 and 1280x720.</p>
</main>
</body>
</html>
"""


def overlay_dist_dir() -> Path | None:
    here = Path(__file__).resolve()
    candidates: list[Path] = [Path.cwd() / "overlay" / "dist", Path("/app/overlay/dist")]
    if len(here.parents) >= 4:
        candidates.insert(0, here.parents[4] / "overlay" / "dist")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return None


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


class SimCommandBatch(BaseModel):
    session_id: str
    broadcast_id: str = "sim-broadcast"
    page_token: str | None = None
    commands: list[SimCommand]


@asynccontextmanager
async def api_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def create_app(container: AppContainer | None = None) -> FastAPI:
    configure_logging()
    settings = (container or get_runtime_container()).settings if container else get_settings()
    if container is not None:
        set_runtime_container(container)
    app = FastAPI(title="Color Rush Live", version="0.2.0", lifespan=api_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, Any]:
        runtime = get_runtime_container()
        with runtime.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        redis_ok = redis_available(runtime.redis)
        status = "ready" if redis_ok else "degraded"
        return {"status": status, "env": runtime.settings.color_rush_env, "redis": redis_ok}

    @app.get("/metrics")
    def metrics(request: Request) -> PlainTextResponse:
        runtime = get_runtime_container()
        if not runtime.settings.trusted_metrics:
            host = request.client.host if request.client else ""
            if host not in {"127.0.0.1", "::1"}:
                raise HTTPException(status_code=403, detail="metrics restricted")
        try:
            from color_rush.application.health import collect_operator_health

            with session_scope(runtime.session_factory) as session:
                collect_operator_health(
                    session, runtime.redis, now=utc_now(), env=runtime.settings.color_rush_env
                )
        except Exception:
            pass
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth_router)
    app.include_router(game_router)
    app.include_router(admin_router)
    app.include_router(ws_router)
    if settings.is_simulation:
        _mount_simulation(app)

    @app.get("/overlay", response_model=None)
    @app.get("/overlay/", response_model=None)
    def overlay_page() -> HTMLResponse | FileResponse:
        dist = overlay_dist_dir()
        if dist is not None:
            return FileResponse(
                dist / "index.html",
                media_type="text/html",
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(OVERLAY_PLACEHOLDER)

    dist = overlay_dist_dir()
    if dist is not None:
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/overlay/assets", StaticFiles(directory=str(assets)), name="overlay-assets")

    @app.get("/overlay/{asset_path:path}")
    def overlay_public_asset(asset_path: str) -> FileResponse:
        dist_dir = overlay_dist_dir()
        if dist_dir is None or not asset_path or asset_path.endswith("/"):
            raise HTTPException(status_code=404)
        target = (dist_dir / asset_path).resolve()
        if dist_dir.resolve() not in target.parents or not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    @app.middleware("http")
    async def _limits(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("content-length") and int(request.headers["content-length"]) > 64_000:
            record_http("oversized", request.method, 413)
            return JSONResponse(
                error_body("payload_too_large", "payload too large", request_id_of(request)),
                413,
            )
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _rate_buckets[ip]
        _rate_buckets[ip] = [stamp for stamp in bucket if now - stamp < 1.0]
        if len(_rate_buckets[ip]) > 40:
            record_http("rate_limited", request.method, 429)
            return JSONResponse(
                error_body("rate_limited", "slow down", request_id_of(request)),
                429,
            )
        _rate_buckets[ip].append(now)
        admin_write = request.method in {"POST", "PUT", "PATCH"} and request.url.path.startswith("/api/v1/admin")
        body = await request.body()
        if admin_write:
            key = request.headers.get("idempotency-key")
            if not key:
                return JSONResponse(
                    error_body("missing_idempotency_key", "Idempotency-Key required", request_id_of(request)),
                    400,
                )
            request_hash = hashlib.sha256(f"{request.method}:{request.url.path}:".encode() + body).hexdigest()
            cached = _load_idempotency(key)
            if cached is not None:
                if cached[2] != request_hash:
                    return JSONResponse(
                        error_body(
                            "conflict",
                            "idempotency key reused with a different body",
                            request_id_of(request),
                            retry=False,
                        ),
                        409,
                    )
                return JSONResponse(cached[1], status_code=cached[0])
        response = await call_next(request)
        route = request.scope.get("route")
        template = getattr(route, "path", request.url.path.split("?")[0] or "unmatched")
        if "{" in str(template) or str(template).startswith("/"):
            record_http(str(template)[:80], request.method, response.status_code)
        else:
            record_http("unmatched", request.method, response.status_code)
        if admin_write:
            chunks = [chunk async for chunk in response.body_iterator]
            payload = b"".join(chunks)
            actor = _actor_from_request(request)
            if actor is not None and 200 <= response.status_code < 300:
                try:
                    parsed: dict[str, Any] = json.loads(payload.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    parsed = {"ok": True}
                _store_idempotency(
                    key=request.headers.get("idempotency-key") or "",
                    actor_id=actor,
                    request_hash=hashlib.sha256(f"{request.method}:{request.url.path}:".encode() + body).hexdigest(),
                    status_code=response.status_code,
                    response_json=parsed if isinstance(parsed, dict) else {"ok": True},
                )
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                content=payload,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
        return response

    return app


def _load_idempotency(key: str) -> tuple[int, dict[str, Any], str] | None:
    runtime = get_runtime_container()
    with session_scope(runtime.session_factory) as session:
        row = session.get(IdempotencyKey, key)
        if row is None:
            return None
        return row.status_code, row.response_json, row.request_hash


def _store_idempotency(
    *,
    key: str,
    actor_id: UUID,
    request_hash: str,
    status_code: int,
    response_json: dict[str, Any],
) -> None:
    if not key:
        return
    runtime = get_runtime_container()
    now = utc_now()
    with session_scope(runtime.session_factory) as session:
        if session.get(IdempotencyKey, key) is not None:
            return
        session.add(
            IdempotencyKey(
                key=key,
                actor_id=actor_id,
                request_hash=request_hash,
                status_code=status_code,
                response_json=response_json,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )


def _actor_from_request(request: Request) -> UUID | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1]
    try:
        payload = decode_access_token(get_runtime_container().settings.secret_key, token)
        return UUID(str(payload["sub"]))
    except (AuthError, ValueError, KeyError):
        return None


def _mount_simulation(app: FastAPI) -> None:
    @app.post("/simulation/commands")
    def simulation_commands(body: SimCommand) -> dict[str, Any]:
        from datetime import datetime

        container = get_runtime_container()
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
        return {"sequences": list(result.sequences), "decisions": [item.value for item in result.decisions]}

    @app.post("/simulation/commands/batch")
    def simulation_commands_batch(body: SimCommandBatch) -> dict[str, Any]:
        from datetime import datetime

        from color_rush.application.dto import SourceCheckpointData

        container = get_runtime_container()
        commands = [
            NormalizedCommand(
                provider="simulation",
                provider_message_id=item.message_id,
                broadcast_id=item.broadcast_id,
                provider_channel_id=item.provider_channel_id,
                display_name=item.display_name,
                command_text=item.text,
                command=parse_command(item.text),
                published_at=datetime.fromisoformat(item.published_at),
            )
            for item in body.commands
        ]
        checkpoint = SourceCheckpointData(
            broadcast_id=body.broadcast_id,
            next_page_token=body.page_token,
            source_mode="simulation",
            ownership_token="simulation-load",
            session_id=UUID(body.session_id),
        )
        with session_scope(container.session_factory) as session:
            result = append_and_process(
                session,
                session_id=UUID(body.session_id),
                commands=commands,
                checkpoint=checkpoint,
            )
        return {
            "sequences": list(result.sequences),
            "decisions": [item.value for item in result.decisions],
            "count": len(result.sequences),
        }

    @app.post("/simulation/rounds/start")
    def simulation_start(body: SimStartRound) -> dict[str, Any]:
        container = get_runtime_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.start_round(UUID(body.session_id), body.fence_token, RoundRules())
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/close")
    def simulation_close(body: SimStartRound) -> dict[str, Any]:
        container = get_runtime_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.close_ingress(UUID(body.session_id), body.fence_token, early=True)
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/drain")
    def simulation_drain(body: SimStartRound) -> dict[str, Any]:
        container = get_runtime_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.complete_drain(UUID(body.session_id), body.fence_token)
        return {"round_id": str(rnd.id), "state": rnd.state}

    @app.post("/simulation/rounds/spin")
    def simulation_spin(body: SimSpin) -> dict[str, Any]:
        container = get_runtime_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.spin(UUID(body.session_id), body.fence_token, forced=body.forced)
        return {"round_id": str(rnd.id), "state": rnd.state, "result": rnd.result}

    @app.post("/simulation/rounds/settle")
    def simulation_settle(body: SimStartRound) -> dict[str, Any]:
        container = get_runtime_container()
        with session_scope(container.session_factory) as session:
            coordinator = container.coordinator(session)
            rnd = coordinator.advance_after_spin(UUID(body.session_id), body.fence_token)
            if rnd.state != "settling":
                rnd = coordinator.advance_after_spin(UUID(body.session_id), body.fence_token)
            settle_round(session, rnd.id, container.clock.now())
            try:
                rnd = coordinator.mark_settled(UUID(body.session_id), body.fence_token)
            except SettlementError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"round_id": str(rnd.id), "state": rnd.state}


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("color_rush.api.app:app", host=settings.color_rush_host, port=settings.color_rush_port)
