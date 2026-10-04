from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from color_rush.domain.enums import Color, CommandType, DecisionReason


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


@dataclass(frozen=True, slots=True)
class PlayerPickView:
    player_id: UUID
    choice: Color
    last_sequence: int
    change_count: int
