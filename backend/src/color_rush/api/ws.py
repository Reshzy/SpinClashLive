from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.auth import get_user
from color_rush.application.overlay_tickets import resolve_overlay_ticket
from color_rush.application.snapshots import cached_or_build
from color_rush.composition import AppContainer, get_runtime_container
from color_rush.domain.clock import utc_now
from color_rush.domain.errors import AuthError, NotFoundError
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import GameSession
from color_rush.infrastructure.security import decode_access_token, decode_overlay_ws_token

ws_router = APIRouter()
MAX_BUFFER = 8
AUTH_DEADLINE_S = 5.0
MAX_PAYLOAD = 32 * 1024


@ws_router.websocket("/ws/v1/overlay")
async def overlay_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    container = get_runtime_container()
    if not _origin_allowed(websocket, container):
        await websocket.close(code=4403)
        return
    try:
        token = await _read_auth(websocket)
        with session_scope(container.session_factory) as session:
            game_session = _game_session_for_overlay(session, container, token)
            if game_session is None:
                await websocket.close(code=4404)
                return
            snapshot = cached_or_build(session, container.redis, game_session, utc_now())
            game_id = game_session.game_id
        await _send_bounded(websocket, snapshot)
        await _pump(websocket, str(game_id), operator=False)
    except (AuthError, NotFoundError, TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
        await websocket.close(code=4401)


@ws_router.websocket("/ws/v1/admin")
async def admin_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    container = get_runtime_container()
    if not _origin_allowed(websocket, container):
        await websocket.close(code=4403)
        return
    try:
        token = await _read_auth(websocket)
        payload = decode_access_token(container.settings.secret_key, token)
        with session_scope(container.session_factory) as session:
            get_user(session, UUID(str(payload["sub"])))
            game_session = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
            if game_session is None:
                await websocket.close(code=4404)
                return
            snapshot = cached_or_build(session, container.redis, game_session, utc_now())
            game_id = game_session.game_id
        await _send_bounded(websocket, snapshot)
        await _pump(websocket, str(game_id), operator=True)
    except (AuthError, TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
        await websocket.close(code=4401)


def _game_session_for_overlay(session: Session, container: AppContainer, token: str) -> GameSession | None:
    try:
        payload = decode_overlay_ws_token(container.settings.secret_key, token)
        session_id = payload.get("session_id")
        if session_id:
            found = session.get(GameSession, UUID(str(session_id)))
            if found is not None:
                return found
    except AuthError:
        ticket = resolve_overlay_ticket(session, token, utc_now())
        if ticket.session_id is not None:
            found = session.get(GameSession, ticket.session_id)
            if found is not None:
                return found
    return session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))


def _origin_allowed(websocket: WebSocket, container: object) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    allowed = getattr(getattr(container, "settings", None), "origin_list", [])
    return origin in allowed


async def _read_auth(websocket: WebSocket) -> str:
    header = websocket.headers.get("authorization") or websocket.query_params.get("ticket") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1]
    if header:
        return header
    message = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_DEADLINE_S)
    data = json.loads(message)
    token = data.get("token") or data.get("ticket")
    if not token:
        raise AuthError("missing token")
    return str(token)


async def _send_bounded(websocket: WebSocket, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload)
    if len(raw.encode()) > MAX_PAYLOAD:
        payload = {
            **payload,
            "data": {
                **(payload.get("data") or {}),
                "truncated": True,
                "recent_players": {"red": [], "gold": [], "green": []},
            },
        }
        raw = json.dumps(payload)
    await websocket.send_text(raw)


async def _pump(websocket: WebSocket, game_id: str, *, operator: bool) -> None:
    del operator
    container = get_runtime_container()
    redis = container.redis
    last_seq = -1
    if redis is None:
        while True:
            await asyncio.sleep(0.25)
            with session_scope(container.session_factory) as session:
                game_session = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
                if game_session is None:
                    continue
                snapshot = cached_or_build(session, None, game_session, utc_now())
            seq = int(snapshot.get("snapshot_sequence") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            await _send_bounded(websocket, snapshot)
    pubsub = redis.pubsub()  # type: ignore[no-untyped-call]
    pubsub.subscribe(f"game:{game_id}:snapshot")
    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.25)
            if message and message.get("type") == "message":
                data = json.loads(message["data"])
                seq = int(data.get("snapshot_sequence") or 0)
                if seq < last_seq:
                    continue
                last_seq = seq
                await _send_bounded(websocket, data)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except TimeoutError:
                continue
    finally:
        pubsub.close()
