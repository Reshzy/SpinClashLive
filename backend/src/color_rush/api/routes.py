from __future__ import annotations

from html import escape
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.api.deps import (
    check_revision,
    container_dep,
    current_user,
    db_session,
    require_permission,
)
from color_rush.api.errors import http_error, request_id_of
from color_rush.api.schemas import (
    AdminUserCreateRequest,
    AutoModeRequest,
    CancelRequest,
    GameCreateRequest,
    LoginRequest,
    ModerationRequest,
    NextBonusRequest,
    OverlayTicketCreated,
    OverlayTicketCreateRequest,
    RefreshRequest,
    RoundStartRequest,
    SeasonCreateRequest,
    SessionActionRequest,
    SessionCreateRequest,
    SettingsPutRequest,
    TokenResponse,
    YoutubeConnectRequest,
    YoutubeOAuthRevokeRequest,
    YoutubeOAuthStartRequest,
)
from color_rush.application.auth import create_admin_user, list_admin_users, login, logout, refresh_tokens, require_role
from color_rush.application.moderation import set_moderation
from color_rush.application.outbox import sweep_incomplete_jobs
from color_rush.application.overlay_tickets import create_overlay_ticket, list_overlay_tickets, revoke_overlay_ticket
from color_rush.application.periods import finalize_due_periods
from color_rush.application.players import (
    delete_player_data,
    list_archives,
    list_champions,
    list_leaderboard,
    list_periods,
    list_players,
    player_ranks,
)
from color_rush.application.seasons import create_season, list_seasons
from color_rush.application.settings import get_settings as get_game_settings
from color_rush.application.settings import put_settings
from color_rush.application.snapshots import cached_or_build
from color_rush.application.source_health import session_source_health
from color_rush.application.youtube_connect import connect_youtube, disconnect_youtube
from color_rush.application.youtube_oauth import complete_oauth_callback, oauth_status, revoke_oauth, start_oauth
from color_rush.composition import AppContainer
from color_rush.domain.clock import utc_now
from color_rush.domain.enums import AdminRole
from color_rush.domain.errors import InvalidCommandError
from color_rush.infrastructure.persistence.models import (
    AdminAction,
    AdminUser,
    Game,
    GameSession,
    Player,
    Round,
    SourceCheckpoint,
)
from color_rush.infrastructure.redis.projections import redis_available

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
game_router = APIRouter(prefix="/api/v1", tags=["game"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@auth_router.post("/login", response_model=TokenResponse)
def auth_login(
    body: LoginRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
) -> TokenResponse:
    access, refresh, user = login(
        session, container.settings, username=body.username, password=body.password, now=utc_now()
    )
    return TokenResponse(access_token=access, refresh_token=refresh, role=user.role, user_id=str(user.id))


@auth_router.post("/refresh", response_model=TokenResponse)
def auth_refresh(
    body: RefreshRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
) -> TokenResponse:
    access, refresh, user = refresh_tokens(session, container.settings, body.refresh_token, utc_now())
    return TokenResponse(access_token=access, refresh_token=refresh, role=user.role, user_id=str(user.id))


@auth_router.post("/logout")
def auth_logout(body: RefreshRequest, session: Annotated[Session, Depends(db_session)]) -> dict[str, str]:
    logout(session, body.refresh_token, utc_now())
    return {"status": "ok"}


@game_router.get("/game/snapshot")
def game_snapshot(
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(current_user)],
    session_id: UUID | None = None,
) -> dict[str, Any]:
    del user
    game_session = _active_session(session, session_id)
    return cached_or_build(session, container.redis, game_session, utc_now())


@game_router.get("/rounds/{round_id}")
def get_round(
    round_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    rnd = session.get(Round, round_id)
    if rnd is None:
        raise http_error(404, "not_found", "round not found", "round")
    return {
        "id": str(rnd.id),
        "session_id": str(rnd.session_id),
        "number": rnd.number,
        "state": rnd.state,
        "revision": rnd.revision,
        "result": rnd.result,
        "rules": rnd.rules_snapshot,
        "opened_at": rnd.opened_at.isoformat() if rnd.opened_at else None,
        "scheduled_closes_at": rnd.scheduled_closes_at.isoformat() if rnd.scheduled_closes_at else None,
        "presentation_plan": rnd.presentation_plan,
    }


@game_router.get("/leaderboards")
def get_leaderboards(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    scope: str = "weekly",
    period_id: UUID | None = None,
    game_id: UUID | None = None,
    cursor: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    del user
    page_size = min(max(limit, 1), 100)
    offset = max(cursor, 0)
    if period_id is None:
        if game_id is None:
            game_session = _active_session(session, None)
            game_id = game_session.game_id
        periods = list_periods(session, game_id, scope)
        if not periods:
            return {"scope": scope, "entries": [], "next_cursor": None}
        period_id = periods[0].id
    entries = list_leaderboard(session, period_id=period_id, limit=page_size, cursor=offset)
    next_cursor = offset + page_size if len(entries) == page_size else None
    return {"scope": scope, "period_id": str(period_id), "entries": entries, "next_cursor": next_cursor}


@game_router.get("/periods/{period_id}/champions")
def get_period_champions(
    period_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    rows = list_champions(session, period_id)
    items = []
    for row in rows:
        player = session.get(Player, row.player_id)
        items.append(
            {
                "award_type": row.award_type,
                "player_id": str(row.player_id),
                "display_name": player.display_name if player else "[unknown]",
                "display_title": row.display_title,
                "created_at": row.created_at.isoformat(),
            }
        )
    return {"period_id": str(period_id), "items": items}


@game_router.get("/periods/{period_id}/archives")
def get_period_archives(
    period_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    rows = list_archives(session, period_id)
    items = []
    for row in rows:
        player = session.get(Player, row.player_id)
        items.append(
            {
                "rank": row.final_rank,
                "player_id": str(row.player_id),
                "display_name": player.display_name if player else "[unknown]",
                "points": row.points,
                "correct_picks": row.correct_picks,
                "rounds_played": row.rounds_played,
                "gold_wins": row.gold_wins,
                "best_streak": row.best_streak,
            }
        )
    return {"period_id": str(period_id), "items": items}


@game_router.get("/players")
def get_players(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    search: str | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    del user
    rows, next_cursor = list_players(session, search=search, cursor=cursor)
    return {
        "items": [
            {
                "id": str(row.id),
                "display_name": row.display_name,
                "provider_channel_id": row.provider_channel_id if row.deleted_at is None else None,
                "deleted": row.deleted_at is not None,
            }
            for row in rows
        ],
        "next_cursor": next_cursor,
    }


@game_router.get("/players/{player_id}/ranks")
def get_player_ranks(
    player_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    game_id: UUID | None = None,
) -> dict[str, Any]:
    del user
    if game_id is None:
        game_id = _active_session(session, None).game_id
    return player_ranks(session, player_id, game_id)


@game_router.get("/periods")
def get_periods(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    scope: str | None = None,
    game_id: UUID | None = None,
) -> dict[str, Any]:
    del user
    if game_id is None:
        game_id = _active_session(session, None).game_id
    periods = list_periods(session, game_id, scope)
    return {
        "items": [
            {
                "id": str(item.id),
                "type": item.period_type,
                "status": item.status,
                "starts_at": item.starts_at.isoformat(),
                "ends_at": item.ends_at.isoformat() if item.ends_at else None,
            }
            for item in periods
        ]
    }


@admin_router.get("/health")
def admin_health(
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    redis_ok = redis_available(container.redis)
    game_session = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
    source = session_source_health(session, game_session).value if game_session else "healthy"
    return {
        "postgres": True,
        "redis": redis_ok,
        "source": source,
        "jobs": sweep_incomplete_jobs(session),
        "env": container.settings.color_rush_env,
    }


@admin_router.get("/audit")
def admin_audit(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    cursor: str | None = None,
) -> dict[str, Any]:
    require_role(AdminRole(user.role), "audit.read")
    stmt = select(AdminAction).order_by(AdminAction.created_at.desc())
    if cursor:
        stmt = stmt.where(AdminAction.id > UUID(cursor))
    rows = list(session.scalars(stmt.limit(51)))
    next_cursor = str(rows[49].id) if len(rows) > 50 else None
    return {
        "items": [
            {
                "id": str(row.id),
                "action": row.action,
                "reason": row.reason,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows[:50]
        ],
        "next_cursor": next_cursor,
    }


@admin_router.post("/games")
def admin_create_game(
    body: GameCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("sessions.write"))],
) -> dict[str, Any]:
    del user
    coordinator = container.coordinator(session)
    row = coordinator.create_game(body.name)
    return {"id": str(row.id), "name": row.name, "request_id": request_id_of(request)}


@admin_router.get("/games")
def admin_list_games(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    rows = list(session.scalars(select(Game).order_by(Game.created_at.desc())))
    return {"items": [{"id": str(row.id), "name": row.name} for row in rows]}


@admin_router.get("/sessions")
def admin_list_sessions(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    game_id: UUID | None = None,
) -> dict[str, Any]:
    del user
    stmt = select(GameSession).order_by(GameSession.created_at.desc())
    if game_id is not None:
        stmt = stmt.where(GameSession.game_id == game_id)
    rows = list(session.scalars(stmt.limit(100)))
    return {
        "items": [
            {
                "id": str(row.id),
                "game_id": str(row.game_id),
                "mode": row.mode,
                "paused": row.paused,
                "revision": row.revision,
                "source_mode": row.source_mode,
                "active_round_id": str(row.active_round_id) if row.active_round_id else None,
            }
            for row in rows
        ]
    }


@admin_router.get("/sessions/{session_id}")
def admin_get_session(
    session_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
) -> dict[str, Any]:
    del user
    row = _active_session(session, session_id)
    return {
        "id": str(row.id),
        "game_id": str(row.game_id),
        "mode": row.mode,
        "paused": row.paused,
        "revision": row.revision,
        "source_mode": row.source_mode,
        "broadcast_ref": row.broadcast_ref,
        "live_chat_ref": row.live_chat_ref,
        "active_round_id": str(row.active_round_id) if row.active_round_id else None,
        "config_version": row.config_version,
    }


@admin_router.get("/rounds")
def admin_list_rounds(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    session_id: UUID,
) -> dict[str, Any]:
    del user
    rows = list(
        session.scalars(select(Round).where(Round.session_id == session_id).order_by(Round.number.desc()).limit(50))
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "number": row.number,
                "state": row.state,
                "revision": row.revision,
                "result": row.result,
            }
            for row in rows
        ]
    }


@admin_router.post("/sessions")
def admin_create_session(
    body: SessionCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("sessions.write"))],
) -> dict[str, Any]:
    del user
    coordinator = container.coordinator(session)
    row = coordinator.create_session(body.game_id, mode=body.mode, source_mode=body.source_mode)
    return {"id": str(row.id), "revision": row.revision, "request_id": request_id_of(request)}


@admin_router.post("/rounds/start")
def admin_start_round(
    body: RoundStartRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, Any]:
    del user
    rid = request_id_of(request)
    game_session = session.get(GameSession, body.session_id)
    if game_session is None:
        raise http_error(404, "not_found", "session not found", rid)
    check_revision(game_session.revision, body.expected_revision, rid)
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    rnd = coordinator.start_round(body.session_id, token)
    return {"round_id": str(rnd.id), "state": rnd.state, "revision": rnd.revision}


@admin_router.post("/rounds/{round_id}/close")
def admin_close(
    round_id: UUID,
    body: SessionActionRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, Any]:
    return _round_action(session, container, body.session_id, body.expected_revision, request, "close", round_id, user)


@admin_router.post("/rounds/{round_id}/spin")
def admin_spin(
    round_id: UUID,
    body: SessionActionRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, Any]:
    return _round_action(session, container, body.session_id, body.expected_revision, request, "spin", round_id, user)


@admin_router.post("/rounds/{round_id}/cancel")
def admin_cancel(
    round_id: UUID,
    body: CancelRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, Any]:
    del user
    rid = request_id_of(request)
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    rnd = coordinator.cancel(body.session_id, token, body.reason)
    if rnd.id != round_id:
        raise http_error(409, "conflict", "round mismatch", rid)
    return {"round_id": str(rnd.id), "state": rnd.state}


@admin_router.post("/session/pause")
def admin_pause(
    body: SessionActionRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("pause"))],
) -> dict[str, str]:
    del user
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    coordinator.pause(body.session_id, token)
    return {"status": "paused"}


@admin_router.post("/session/resume")
def admin_resume(
    body: SessionActionRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("pause"))],
) -> dict[str, str]:
    del user
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    coordinator.resume(body.session_id, token)
    return {"status": "resumed"}


@admin_router.patch("/session/auto-mode")
def admin_auto_mode(
    body: AutoModeRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, str]:
    del user
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    coordinator.set_mode(body.session_id, token, body.mode)
    return {"mode": body.mode.value}


@admin_router.put("/next-round-bonus")
def admin_next_bonus(
    body: NextBonusRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("rounds.write"))],
) -> dict[str, str]:
    del user
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(body.session_id).fencing_token
    coordinator.set_next_bonus(body.session_id, token, body.bonus, body.gold_reward)
    return {"bonus": body.bonus.value}


@admin_router.get("/settings")
def admin_get_settings(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    game_id: UUID,
) -> dict[str, Any]:
    del user
    row = get_game_settings(session, game_id)
    return {"version": row.version, "configuration": row.configuration, "activation_boundary": row.activation_boundary}


@admin_router.put("/settings")
def admin_put_settings(
    body: SettingsPutRequest,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("settings"))],
) -> dict[str, Any]:
    row = put_settings(
        session,
        game_id=body.game_id,
        configuration=body.configuration,
        actor_id=user.id,
        now=utc_now(),
        session_id=body.session_id,
        expected_revision=body.expected_revision,
    )
    return {"version": row.version}


@admin_router.get("/seasons")
def admin_list_seasons(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    game_id: UUID,
) -> dict[str, Any]:
    del user
    rows = list_seasons(session, game_id)
    return {
        "items": [
            {
                "id": str(row.id),
                "name": row.name,
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat(),
                "status": row.status,
            }
            for row in rows
        ]
    }


@admin_router.post("/seasons")
def admin_create_season(
    body: SeasonCreateRequest,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("seasons"))],
) -> dict[str, str]:
    del user
    row = create_season(session, game_id=body.game_id, name=body.name, starts_at=body.starts_at, ends_at=body.ends_at)
    return {"id": str(row.id)}


@admin_router.post("/players/{player_id}/moderation")
def admin_moderation(
    player_id: UUID,
    body: ModerationRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("moderation"))],
) -> dict[str, Any]:
    row = set_moderation(
        session,
        player_id=player_id,
        scope_key=body.scope_key,
        blocked=body.blocked,
        reason=body.reason,
        actor_id=user.id,
        now=utc_now(),
        request_id=request.headers.get("idempotency-key"),
    )
    return {"player_id": str(player_id), "blocked": row.blocked, "scope_key": row.scope_key}


@admin_router.post("/players/{player_id}/delete-data")
def admin_delete_player(
    player_id: UUID,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("delete"))],
    game_id: UUID | None = None,
) -> dict[str, str]:
    row = delete_player_data(
        session, player_id=player_id, actor_id=user.id, now=utc_now(), request_id=request.headers.get("idempotency-key")
    )
    if container.redis is not None and game_id is not None:
        from color_rush.infrastructure.redis.projections import delete_player_keys

        periods = list_periods(session, game_id)
        delete_player_keys(container.redis, game_id, player_id, [item.id for item in periods])
    return {"status": "anonymized", "player_id": str(row.id)}


@admin_router.post("/youtube/connect")
def admin_yt_connect(
    body: YoutubeConnectRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("youtube"))],
) -> dict[str, Any]:
    row = connect_youtube(
        session,
        container.settings,
        session_id=body.session_id,
        video_ref=body.video_ref,
        actor_id=user.id,
        now=utc_now(),
        request_id=request.headers.get("idempotency-key"),
    )
    return {"broadcast_ref": row.broadcast_ref, "live_chat_ref": row.live_chat_ref, "source_mode": row.source_mode}


@admin_router.post("/youtube/disconnect")
def admin_yt_disconnect(
    body: SessionActionRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("youtube"))],
) -> dict[str, str]:
    disconnect_youtube(
        session,
        session_id=body.session_id,
        actor_id=user.id,
        now=utc_now(),
        request_id=request.headers.get("idempotency-key"),
    )
    return {"status": "disconnected"}


@admin_router.post("/youtube/oauth/start")
def admin_yt_oauth_start(
    body: YoutubeOAuthStartRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("youtube"))],
) -> dict[str, str]:
    del session
    return start_oauth(container.settings, game_id=body.game_id, user_id=user.id, now=utc_now())


@admin_router.get("/youtube/oauth/callback")
def admin_yt_oauth_callback(
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = Query(default=None),
) -> HTMLResponse:
    if error or not code or not state:
        message = error or "missing authorization code"
        return HTMLResponse(
            f"<!doctype html><html><body><p>YouTube authorization failed: {escape(message)}</p>"
            "<p>You can close this window and return to Color Rush Live.</p></body></html>",
            status_code=400,
        )
    try:
        complete_oauth_callback(session, container.settings, code=code, state=state, now=utc_now())
    except Exception as exc:
        return HTMLResponse(
            f"<!doctype html><html><body><p>YouTube authorization failed: {escape(str(exc))}</p>"
            "<p>You can close this window and return to Color Rush Live.</p></body></html>",
            status_code=400,
        )
    return HTMLResponse(
        "<!doctype html><html><body><p>YouTube authorization complete.</p>"
        "<p>Return to Color Rush Live. You can close this window.</p></body></html>"
    )


@admin_router.get("/youtube/oauth/status")
def admin_yt_oauth_status(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("youtube"))],
    game_id: UUID,
) -> dict[str, Any]:
    del user
    return oauth_status(session, game_id)


@admin_router.post("/youtube/oauth/revoke")
def admin_yt_oauth_revoke(
    body: YoutubeOAuthRevokeRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("youtube"))],
) -> dict[str, Any]:
    count = revoke_oauth(
        session,
        game_id=body.game_id,
        actor_id=user.id,
        now=utc_now(),
        request_id=request.headers.get("idempotency-key"),
    )
    return {"status": "revoked", "count": count}


@admin_router.get("/users")
def admin_list_users(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("users"))],
) -> dict[str, Any]:
    del user
    rows = list_admin_users(session)
    return {
        "items": [
            {
                "id": str(row.id),
                "username": row.username,
                "role": row.role,
                "created_at": row.created_at.isoformat(),
                "revoked": row.revoked_at is not None,
            }
            for row in rows
        ]
    }


@admin_router.post("/users")
def admin_create_user(
    body: AdminUserCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("users"))],
) -> dict[str, str]:
    try:
        role = AdminRole(body.role)
    except ValueError as exc:
        raise InvalidCommandError("unknown role") from exc
    row = create_admin_user(
        session,
        username=body.username,
        password=body.password,
        role=role,
        actor_id=user.id,
        now=utc_now(),
        request_id=request.headers.get("idempotency-key"),
    )
    return {"id": str(row.id), "username": row.username, "role": row.role}


@admin_router.post("/overlay-tickets", response_model=OverlayTicketCreated)
def admin_overlay_create(
    body: OverlayTicketCreateRequest,
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
    user: Annotated[AdminUser, Depends(require_permission("overlay"))],
) -> OverlayTicketCreated:
    del user
    row, secret = create_overlay_ticket(
        session,
        game_id=body.game_id,
        session_id=body.session_id,
        label=body.label,
        now=utc_now(),
        ttl_seconds=container.settings.overlay_ticket_ttl_seconds,
    )
    host = container.settings.color_rush_host
    port = container.settings.color_rush_port
    obs_url = f"http://{host}:{port}/overlay#{secret}"
    return OverlayTicketCreated(ticket_id=str(row.id), secret=secret, obs_url=obs_url)


@admin_router.get("/overlay-tickets")
def admin_overlay_list(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("overlay"))],
    game_id: UUID,
) -> dict[str, Any]:
    del user
    rows = list_overlay_tickets(session, game_id)
    return {
        "items": [
            {
                "id": str(row.id),
                "label": row.label,
                "revoked": row.revoked_at is not None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@admin_router.post("/overlay-tickets/{ticket_id}/revoke")
def admin_overlay_revoke(
    ticket_id: UUID,
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("overlay"))],
) -> dict[str, str]:
    del user
    revoke_overlay_ticket(session, ticket_id, utc_now())
    return {"status": "revoked"}


@admin_router.post("/periods/finalize")
def admin_finalize_periods(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(require_permission("seasons"))],
    game_id: UUID,
) -> dict[str, int]:
    del user
    count = finalize_due_periods(session, game_id, utc_now())
    return {"finalized": count}


@admin_router.get("/source")
def admin_source(
    session: Annotated[Session, Depends(db_session)],
    user: Annotated[AdminUser, Depends(current_user)],
    session_id: UUID | None = None,
) -> dict[str, Any]:
    del user
    game_session = _active_session(session, session_id)
    checkpoint = None
    if game_session.broadcast_ref:
        checkpoint = session.get(SourceCheckpoint, game_session.broadcast_ref)
    return {
        "source_mode": game_session.source_mode,
        "broadcast_ref": game_session.broadcast_ref,
        "live_chat_ref": game_session.live_chat_ref,
        "health": session_source_health(session, game_session).value,
        "lag_ms": checkpoint.lag_ms if checkpoint else None,
        "resync_required": checkpoint.resync_required if checkpoint else False,
    }


def _active_session(session: Session, session_id: UUID | None) -> GameSession:
    if session_id is not None:
        row = session.get(GameSession, session_id)
        if row is None:
            raise http_error(404, "not_found", "session not found", "session")
        return row
    row = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
    if row is None:
        raise http_error(404, "not_found", "no session", "session")
    return row


def _round_action(
    session: Session,
    container: AppContainer,
    session_id: UUID,
    expected: int | None,
    request: Request,
    action: str,
    round_id: UUID,
    user: AdminUser,
) -> dict[str, Any]:
    del user
    rid = request_id_of(request)
    game_session = session.get(GameSession, session_id)
    if game_session is None:
        raise http_error(404, "not_found", "session not found", rid)
    check_revision(game_session.revision, expected, rid)
    coordinator = container.coordinator(session)
    token = coordinator.claim_lease(session_id).fencing_token
    if action == "close":
        rnd = coordinator.close_ingress(session_id, token, early=True)
    else:
        rnd = coordinator.spin(session_id, token)
    if rnd.id != round_id:
        raise http_error(409, "conflict", "round mismatch", rid)
    return {"round_id": str(rnd.id), "state": rnd.state, "result": rnd.result}
