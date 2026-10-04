from __future__ import annotations

from collections.abc import Iterator

from color_rush.application.dto import SourceBatch
from color_rush.domain.enums import SourceHealth
from color_rush.infrastructure.youtube.grpc_source import YouTubeStreamSource
from color_rush.infrastructure.youtube.http import YouTubeHttpClient, YouTubePollingSource


class YouTubeChatSource:
    """One owned live-chat reader. streamList primary, list polling fallback."""

    def __init__(
        self,
        *,
        live_chat_id: str,
        broadcast_id: str,
        ownership_token: str,
        transport: str = "stream",
        api_key: str | None = None,
        access_token: str | None = None,
        session_id: object | None = None,
        page_token: str | None = None,
        http_client: YouTubeHttpClient | None = None,
        stream_source: YouTubeStreamSource | None = None,
    ) -> None:
        self.transport = transport
        self._http = YouTubePollingSource(
            http_client
            or YouTubeHttpClient(api_key=api_key, access_token=access_token),
            live_chat_id=live_chat_id,
            broadcast_id=broadcast_id,
            ownership_token=ownership_token,
            session_id=session_id,
            page_token=page_token,
        )
        self._stream = stream_source or YouTubeStreamSource(
            live_chat_id=live_chat_id,
            broadcast_id=broadcast_id,
            ownership_token=ownership_token,
            api_key=api_key,
            access_token=access_token,
            session_id=session_id,
            page_token=page_token,
        )
        self._active = self._stream if transport == "stream" else self._http

    def connect(self) -> None:
        try:
            self._active.connect()
        except RuntimeError:
            self.transport = "poll"
            self._active = self._http
            self._active.connect()

    def disconnect(self) -> None:
        self._active.disconnect()

    def health(self) -> SourceHealth:
        return self._active.health()

    def iter_batches(self) -> Iterator[SourceBatch]:
        self.connect()
        yield from self._active.iter_batches()
