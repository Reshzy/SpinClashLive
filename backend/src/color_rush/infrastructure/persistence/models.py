from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, ExcludeConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


@event.listens_for(Base.metadata, "before_create")
def _create_required_extensions(metadata: object, connection: Connection, **_kwargs: object) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))


class Game(Base):
    __tablename__ = "games"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    broadcast_ref: Mapped[str | None] = mapped_column(String(128))
    live_chat_ref: Mapped[str | None] = mapped_column(String(128))
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timezone_version: Mapped[str] = mapped_column(String(64), nullable=False)
    active_round_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_inbox_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    next_round_bonus: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    next_round_gold_bonus_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=28)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="simulation")
    last_help_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rounds: Mapped[list[Round]] = relationship(back_populates="session")


class CoordinatorLease(Base):
    __tablename__ = "coordinator_leases"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("game_sessions.id"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceCheckpoint(Base):
    __tablename__ = "source_checkpoints"

    broadcast_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    next_page_token: Mapped[str | None] = mapped_column(String(512))
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ownership_token: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("game_sessions.id"))
    resync_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_class: Mapped[str | None] = mapped_column(String(32))
    lag_ms: Mapped[int | None] = mapped_column(Integer)


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("provider", "provider_channel_id", name="uq_players_provider_channel"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_ref: Mapped[str | None] = mapped_column(String(512))
    profile_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_lookup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerModeration(Base):
    __tablename__ = "player_moderation"
    __table_args__ = (
        UniqueConstraint("player_id", "scope_key", name="uq_moderation_player_scope"),
        Index("ix_moderation_scope_player", "scope_key", "player_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Round(Base):
    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("session_id", "number", name="uq_rounds_session_number"),
        Index(
            "uq_rounds_session_nonterminal",
            "session_id",
            unique=True,
            postgresql_where=text(
                "state IN ('open','draining','locked','spinning','result','settling','settled')"
            ),
        ),
        Index("ix_rounds_session_state", "session_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rules_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cutoff_sequence: Mapped[int | None] = mapped_column(BigInteger)
    result: Mapped[str | None] = mapped_column(String(16))
    result_draw: Mapped[int | None] = mapped_column(Integer)
    presentation_plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    drain_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[GameSession] = relationship(back_populates="rounds")


class CommandInbox(Base):
    __tablename__ = "command_inbox"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_inbox_session_sequence"),
        UniqueConstraint(
            "provider",
            "broadcast_id",
            "provider_message_id",
            name="uq_inbox_provider_message",
        ),
        Index("ix_inbox_eligible", "session_id", "processing_status", "sequence"),
        CheckConstraint("sequence > 0", name="ck_inbox_sequence_positive"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(160), nullable=False)
    broadcast_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_round_id: Mapped[UUID | None] = mapped_column(ForeignKey("rounds.id"))
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    command: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_reason: Mapped[str] = mapped_column(String(64), nullable=False)


class Pick(Base):
    __tablename__ = "picks"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", name="uq_picks_round_player"),
        Index("ix_picks_round_color", "round_id", "choice"),
        Index("ix_picks_round_player", "round_id", "player_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    choice: Mapped[str] = mapped_column(String(16), nullable=False)
    last_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScoreLedger(Base):
    __tablename__ = "score_ledger"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", name="uq_ledger_round_player"),
        Index("ix_ledger_round_player_effective", "round_id", "player_id", "effective_at"),
        CheckConstraint("points_delta >= 0", name="ck_ledger_points_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rules_version: Mapped[int] = mapped_column(Integer, nullable=False)


class PlayerStatistics(Base):
    __tablename__ = "player_statistics"
    __table_args__ = (UniqueConstraint("player_id", "game_id", name="uq_stats_player_game"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    lifetime_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        Index("ix_seasons_game_status", "game_id", "status"),
        CheckConstraint("ends_at > starts_at", name="ck_seasons_interval"),
        ExcludeConstraint(
            ("game_id", "="),
            ("during", "&&"),
            using="gist",
            name="ex_seasons_no_overlap",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    during: Mapped[Any] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True),
        nullable=False,
    )


class LeaderboardPeriod(Base):
    __tablename__ = "leaderboard_periods"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "period_type",
            "local_identity",
            "timezone_version",
            name="uq_period_logical_identity",
        ),
        Index("ix_periods_game_type_status", "game_id", "period_type", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone_version: Mapped[str] = mapped_column(String(64), nullable=False)
    season_id: Mapped[UUID | None] = mapped_column(ForeignKey("seasons.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    local_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoundPeriod(Base):
    __tablename__ = "round_periods"
    __table_args__ = (UniqueConstraint("round_id", "period_type", name="uq_round_period_type"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_periods.id"), nullable=False)


class LeaderboardScore(Base):
    __tablename__ = "leaderboard_scores"
    __table_args__ = (
        UniqueConstraint("period_id", "player_id", name="uq_lb_score_period_player"),
        Index("ix_lb_scores_period_points_player", "period_id", "points", "player_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_periods.id"), nullable=False)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    correct_picks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LeaderboardArchive(Base):
    __tablename__ = "leaderboard_archives"
    __table_args__ = (UniqueConstraint("period_id", "player_id", name="uq_archive_period_player"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_periods.id"), nullable=False)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(BigInteger, nullable=False)
    correct_picks: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False)
    gold_wins: Mapped[int] = mapped_column(Integer, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False)


class ChampionAward(Base):
    __tablename__ = "champion_awards"
    __table_args__ = (UniqueConstraint("period_id", "award_type", name="uq_champion_period_type"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("leaderboard_periods.id"), nullable=False)
    award_type: Mapped[str] = mapped_column(String(32), nullable=False)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    display_title: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettlementJob(Base):
    __tablename__ = "settlement_jobs"
    __table_args__ = (
        UniqueConstraint("round_id", "partition", name="uq_settlement_round_partition"),
        Index("ix_settlement_pending", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    partition: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[str | None] = mapped_column(Text)


class ProjectionJob(Base):
    __tablename__ = "projection_jobs"
    __table_args__ = (
        UniqueConstraint("job_key", name="uq_projection_job_key"),
        Index("ix_projection_pending", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    job_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_outbox_event_id"),
        Index(
            "ix_outbox_pending",
            "published_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    aggregate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAction(Base):
    __tablename__ = "admin_actions"
    __table_args__ = (UniqueConstraint("request_id", name="uq_admin_actions_request"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id"), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    __table_args__ = (UniqueConstraint("game_id", "version", name="uq_config_game_version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    activation_boundary: Mapped[str] = mapped_column(String(32), nullable=False, default="next_round")
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OverlayTicket(Base):
    __tablename__ = "overlay_tickets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("game_sessions.id"))
    secret_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="overlay")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoogleCredential(Base):
    __tablename__ = "google_credentials"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(
        String(256), nullable=False, default="https://www.googleapis.com/auth/youtube.readonly"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (Index("ix_idempotency_expires", "expires_at"),)

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id"), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
