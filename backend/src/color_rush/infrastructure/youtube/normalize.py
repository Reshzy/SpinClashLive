from __future__ import annotations

from datetime import datetime
from typing import Any

from color_rush.application.dto import NormalizedCommand
from color_rush.domain.clock import utc_now
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import SourceHealth

TEXT_TYPES = {"textMessageEvent", "TEXT_MESSAGE_EVENT", 1}


def _parse_published(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return utc_now()
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def normalize_live_chat_items(
    items: list[dict[str, Any]],
    *,
    broadcast_id: str,
) -> list[NormalizedCommand]:
    commands: list[NormalizedCommand] = []
    for item in items:
        snippet = item.get("snippet") or {}
        author = item.get("authorDetails") or {}
        message_type = snippet.get("type")
        if message_type not in TEXT_TYPES and message_type != "textMessageEvent":
            continue
        text_details = snippet.get("textMessageDetails") or snippet.get("text_message_details") or {}
        text = str(
            text_details.get("messageText")
            or text_details.get("message_text")
            or snippet.get("displayMessage")
            or ""
        )
        message_id = str(item.get("id") or "")
        channel_id = str(
            author.get("channelId") or author.get("channel_id") or snippet.get("authorChannelId") or ""
        )
        if not message_id or not channel_id:
            continue
        display_name = str(author.get("displayName") or author.get("display_name") or "player")[:128]
        avatar = author.get("profileImageUrl") or author.get("profile_image_url")
        commands.append(
            NormalizedCommand(
                provider="youtube",
                provider_message_id=message_id,
                broadcast_id=broadcast_id,
                provider_channel_id=channel_id,
                display_name=display_name,
                command_text=text,
                command=parse_command(text),
                published_at=_parse_published(snippet.get("publishedAt") or snippet.get("published_at")),
                avatar_ref=str(avatar) if avatar else None,
            )
        )
    return commands


def classify_youtube_error(status_code: int | None, reason: str | None, grpc_code: int | None = None) -> SourceHealth:
    if grpc_code == 7 or status_code == 403:
        if reason in {"liveChatDisabled"}:
            return SourceHealth.DISABLED
        if reason in {"liveChatEnded"}:
            return SourceHealth.ENDED
        if reason in {"rateLimitExceeded"}:
            return SourceHealth.QUOTA
        return SourceHealth.PERMISSION
    if grpc_code == 9:
        return SourceHealth.DISABLED
    if grpc_code == 5 or status_code == 404:
        return SourceHealth.ENDED
    if grpc_code == 8 or status_code == 429:
        return SourceHealth.QUOTA
    if grpc_code == 3 or status_code == 400:
        if reason in {"pageTokenInvalid"}:
            return SourceHealth.RESYNC
        return SourceHealth.TRANSIENT
    if status_code == 401:
        return SourceHealth.RESYNC
    return SourceHealth.TRANSIENT
