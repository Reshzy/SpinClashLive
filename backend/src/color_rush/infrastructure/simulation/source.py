from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from random import Random
from uuid import UUID

from color_rush.application.dto import NormalizedCommand, SourceBatch, SourceCheckpointData
from color_rush.application.ports import Clock
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import Color, SourceHealth


class SimulationChatSource:
    """Deterministic ChatSource. Forced outcomes exist only on this class."""

    def __init__(
        self,
        *,
        clock: Clock,
        broadcast_id: str,
        session_id: UUID | None = None,
        seed: int = 1,
        ownership_token: str = "simulation-owner",
        players: list[tuple[str, str]] | None = None,
    ) -> None:
        self.clock = clock
        self.broadcast_id = broadcast_id
        self.session_id = session_id
        self.seed = seed
        self.ownership_token = ownership_token
        self.players = players or [
            (f"sim-ch-{index:03d}", name)
            for index, name in enumerate(
                ["Alice", "Bob", "Cara", "Drew", "Eve", "Finn", "Gia", "Hank"], start=1
            )
        ]
        self._rng = Random(seed)
        self._connected = False
        self._page = 0
        self._forced: Color | None = None
        self._gap_until_page: int | None = None

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> SourceHealth:
        if not self._connected:
            return SourceHealth.DISABLED
        if self._gap_until_page is not None and self._page < self._gap_until_page:
            return SourceHealth.TRANSIENT
        return SourceHealth.HEALTHY

    def force_outcome(self, color: Color | None) -> None:
        """Simulation-only. Production composition must never call this."""
        self._forced = color

    def forced_outcome(self) -> Color | None:
        return self._forced

    def insert_gap(self, pages: int = 1) -> None:
        self._gap_until_page = self._page + max(pages, 1)

    def iter_batches(self) -> Iterator[SourceBatch]:
        if not self._connected:
            self.connect()
        yield self._history_batch()
        yield self._normal_batch()
        yield self._burst_batch()
        yield self._duplicate_and_invalid_batch()
        yield self._repeat_and_change_batch()
        if self._gap_until_page is not None:
            self._page += 1
            yield self._empty_gap_batch()
            self._gap_until_page = None
        yield self._delayed_batch()

    def _token(self) -> str:
        self._page += 1
        return f"sim-page-{self._page}"

    def _checkpoint(self, token: str, health: SourceHealth = SourceHealth.HEALTHY) -> SourceCheckpointData:
        return SourceCheckpointData(
            broadcast_id=self.broadcast_id,
            next_page_token=token,
            source_mode="simulation",
            ownership_token=self.ownership_token,
            session_id=self.session_id,
            resync_required=health is SourceHealth.RESYNC,
            error_class=None if health is SourceHealth.HEALTHY else health.value,
            lag_ms=0,
        )

    def _command(
        self,
        *,
        message_id: str,
        channel_id: str,
        display_name: str,
        text: str,
        published_offset_s: float = 0,
    ) -> NormalizedCommand:
        published = self.clock.now() + timedelta(seconds=published_offset_s)
        return NormalizedCommand(
            provider="simulation",
            provider_message_id=message_id,
            broadcast_id=self.broadcast_id,
            provider_channel_id=channel_id,
            display_name=display_name,
            command_text=text,
            command=parse_command(text),
            published_at=published,
        )

    def _history_batch(self) -> SourceBatch:
        channel_id, name = self.players[0]
        command = self._command(
            message_id="hist-old-1",
            channel_id=channel_id,
            display_name=name,
            text="!red",
            published_offset_s=-3600,
        )
        return SourceBatch((command,), self._checkpoint(self._token()), SourceHealth.HEALTHY)

    def _normal_batch(self) -> SourceBatch:
        colors = ["!red", "!gold", "!green", "!score", "!help"]
        commands: list[NormalizedCommand] = []
        for index, (channel_id, name) in enumerate(self.players[:4]):
            commands.append(
                self._command(
                    message_id=f"n-{self.seed}-{index}",
                    channel_id=channel_id,
                    display_name=name,
                    text=colors[index % len(colors)],
                )
            )
        return SourceBatch(tuple(commands), self._checkpoint(self._token()), SourceHealth.HEALTHY)

    def _burst_batch(self) -> SourceBatch:
        commands: list[NormalizedCommand] = []
        for index in range(12):
            channel_id, name = self.players[index % len(self.players)]
            commands.append(
                self._command(
                    message_id=f"burst-{self.seed}-{index}",
                    channel_id=channel_id,
                    display_name=name,
                    text=self._rng.choice(["!red", "!green", "!gold"]),
                )
            )
        return SourceBatch(tuple(commands), self._checkpoint(self._token()), SourceHealth.HEALTHY)

    def _duplicate_and_invalid_batch(self) -> SourceBatch:
        channel_id, name = self.players[1]
        first = self._command(
            message_id="dup-same",
            channel_id=channel_id,
            display_name=name,
            text="!green",
        )
        duplicate = self._command(
            message_id="dup-same",
            channel_id=channel_id,
            display_name=name,
            text="!green",
        )
        invalid = self._command(
            message_id="invalid-1",
            channel_id=channel_id,
            display_name=name,
            text="go red please",
        )
        return SourceBatch((first, duplicate, invalid), self._checkpoint(self._token()), SourceHealth.HEALTHY)

    def _repeat_and_change_batch(self) -> SourceBatch:
        channel_id, name = self.players[2]
        commands = [
            self._command(message_id="chg-1", channel_id=channel_id, display_name=name, text="!red"),
            self._command(message_id="chg-2", channel_id=channel_id, display_name=name, text="!red"),
            self._command(message_id="chg-3", channel_id=channel_id, display_name=name, text="!green"),
        ]
        return SourceBatch(tuple(commands), self._checkpoint(self._token()), SourceHealth.HEALTHY)

    def _empty_gap_batch(self) -> SourceBatch:
        return SourceBatch((), self._checkpoint(self._token(), SourceHealth.TRANSIENT), SourceHealth.TRANSIENT)

    def _delayed_batch(self) -> SourceBatch:
        channel_id, name = self.players[3]
        delayed = self._command(
            message_id="delayed-1",
            channel_id=channel_id,
            display_name=name,
            text="!gold",
            published_offset_s=-0.5,
        )
        return SourceBatch((delayed,), self._checkpoint(self._token()), SourceHealth.HEALTHY)


def inject_chat(
    container: object,
    session_id: UUID,
    *,
    broadcast_id: str,
    player_channel_id: str,
    display_name: str,
    text: str,
    published_at: object,
    message_id: str,
    page_token: str | None = None,
) -> object:
    from datetime import datetime

    from color_rush.application.ingest import append_and_process
    from color_rush.composition import AppContainer
    from color_rush.infrastructure.persistence.db import session_scope

    assert isinstance(container, AppContainer)
    assert isinstance(published_at, datetime)
    command = NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id=broadcast_id,
        provider_channel_id=player_channel_id,
        display_name=display_name,
        command_text=text,
        command=parse_command(text),
        published_at=published_at,
    )
    checkpoint = SourceCheckpointData(
        broadcast_id=broadcast_id,
        next_page_token=page_token,
        source_mode="simulation",
        ownership_token="simulation-owner",
        session_id=session_id,
    )
    with session_scope(container.session_factory) as session:
        return append_and_process(
            session,
            session_id=session_id,
            commands=[command],
            checkpoint=checkpoint,
        )
