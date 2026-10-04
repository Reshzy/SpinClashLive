from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from color_rush.domain.enums import Color, CommandType, DecisionReason, SourceHealth


@dataclass(frozen=True, slots=True)
class NormalizedCommand:
    provider: str
    provider_message_id: str
    broadcast_id: str
    provider_channel_id: str
    display_name: str
    command_text: str
    command: CommandType | None
    published_at: datetime
    avatar_ref: str | None = None


@dataclass(frozen=True, slots=True)
class IngestResult:
    sequences: tuple[int, ...]
    decisions: tuple[DecisionReason, ...]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class SourceCheckpointData:
    broadcast_id: str
    next_page_token: str | None
    source_mode: str
    ownership_token: str
    session_id: UUID | None = None
    resync_required: bool = False
    error_class: str | None = None
    lag_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SourceBatch:
    commands: tuple[NormalizedCommand, ...]
    checkpoint: SourceCheckpointData
    health: SourceHealth
    lag_ms: int = 0


@dataclass(frozen=True, slots=True)
class PlayerPickView:
    player_id: UUID
    choice: Color
    last_sequence: int
    change_count: int


@dataclass(frozen=True, slots=True)
class LookupSpotlight:
    player_id: UUID
    display_name: str
    ranks: dict[str, int]
    scores: dict[str, int]
    expires_at: datetime


@dataclass
class SnapshotData:
    state: str
    closes_at: datetime | None
    rules: dict[str, object]
    counts: dict[str, int]
    recent_players: dict[str, list[dict[str, str]]]
    leaderboard: dict[str, object]
    recent_results: list[str]
    source_status: str
    animation_plan: dict[str, object] | None = None
    projection_fresh_at: datetime | None = None
    lookup: dict[str, object] | None = None
    ceremony: dict[str, object] | None = None
    paused: bool = False
    round_number: int | None = None
    session_revision: int = 1


@dataclass
class SnapshotEnvelope:
    schema_version: int
    type: str
    session_id: str
    round_id: str | None
    snapshot_sequence: int
    server_time: str
    data: dict[str, object] = field(default_factory=dict)
