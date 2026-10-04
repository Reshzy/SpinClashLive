from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from color_rush.domain.enums import BonusType, Color, SessionMode


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retry: bool | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class GameCreateRequest(BaseModel):
    name: str = Field(default="Color Rush Live", min_length=1, max_length=120)


class SessionCreateRequest(BaseModel):
    game_id: UUID
    mode: SessionMode = SessionMode.MANUAL
    source_mode: str = "simulation"
    expected_revision: int | None = None


class RoundStartRequest(BaseModel):
    session_id: UUID
    expected_revision: int | None = None


class SessionActionRequest(BaseModel):
    session_id: UUID
    expected_revision: int | None = None


class AutoModeRequest(BaseModel):
    session_id: UUID
    mode: SessionMode
    expected_revision: int | None = None


class NextBonusRequest(BaseModel):
    session_id: UUID
    bonus: BonusType
    gold_reward: int = Field(default=28, ge=0)
    expected_revision: int | None = None


class CancelRequest(BaseModel):
    session_id: UUID
    reason: str = Field(min_length=1, max_length=160)
    expected_revision: int | None = None


class SettingsPutRequest(BaseModel):
    game_id: UUID
    session_id: UUID | None = None
    configuration: dict[str, Any]
    expected_revision: int | None = None


class SeasonCreateRequest(BaseModel):
    game_id: UUID
    name: str = Field(min_length=1, max_length=120)
    starts_at: datetime
    ends_at: datetime


class ModerationRequest(BaseModel):
    scope_key: str = Field(min_length=3, max_length=160)
    blocked: bool
    reason: str | None = Field(default=None, max_length=500)


class YoutubeConnectRequest(BaseModel):
    session_id: UUID
    video_ref: str = Field(min_length=6, max_length=256)
    expected_revision: int | None = None


class OverlayTicketCreateRequest(BaseModel):
    game_id: UUID
    session_id: UUID | None = None
    label: str = Field(default="overlay", max_length=80)


class OverlayTicketCreated(BaseModel):
    ticket_id: str
    secret: str
    obs_url: str


class YoutubeOAuthStartRequest(BaseModel):
    game_id: UUID


class YoutubeOAuthRevokeRequest(BaseModel):
    game_id: UUID


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(min_length=4, max_length=32)


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
