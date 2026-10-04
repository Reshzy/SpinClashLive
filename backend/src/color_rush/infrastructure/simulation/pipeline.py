from datetime import datetime
from uuid import UUID

from color_rush.application.dto import NormalizedCommand, SourceCheckpointData
from color_rush.application.ingest import append_and_process
from color_rush.composition import AppContainer
from color_rush.domain.commands import parse_command
from color_rush.infrastructure.persistence.db import session_scope


def inject_chat(
    container: AppContainer,
    session_id: UUID,
    *,
    broadcast_id: str,
    player_channel_id: str,
    display_name: str,
    text: str,
    published_at: datetime,
    message_id: str,
    page_token: str | None = None,
) -> object:
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
    )
    with session_scope(container.session_factory) as session:
        return append_and_process(
            session,
            session_id=session_id,
            commands=[command],
            checkpoint=checkpoint,
        )
