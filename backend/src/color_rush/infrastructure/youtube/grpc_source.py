from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from color_rush.application.dto import SourceBatch, SourceCheckpointData
from color_rush.domain.enums import SourceHealth
from color_rush.infrastructure.youtube.normalize import classify_youtube_error, normalize_live_chat_items

GRPC_HOST = "dns:///youtube.googleapis.com:443"


def _message_to_dict(message: Any) -> dict[str, Any]:
    snippet = getattr(message, "snippet", None)
    author = getattr(message, "author_details", None)
    text = None
    if snippet is not None:
        details = getattr(snippet, "text_message_details", None)
        if details is not None:
            text = getattr(details, "message_text", None)
    type_name = None
    if snippet is not None:
        raw_type = getattr(snippet, "type", None)
        type_name = getattr(raw_type, "name", raw_type)
    return {
        "id": getattr(message, "id", None),
        "snippet": {
            "type": type_name,
            "publishedAt": getattr(snippet, "published_at", None) if snippet is not None else None,
            "displayMessage": getattr(snippet, "display_message", None) if snippet is not None else None,
            "authorChannelId": getattr(snippet, "author_channel_id", None) if snippet is not None else None,
            "textMessageDetails": {"messageText": text},
        },
        "authorDetails": {
            "channelId": getattr(author, "channel_id", None) if author is not None else None,
            "displayName": getattr(author, "display_name", None) if author is not None else None,
            "profileImageUrl": getattr(author, "profile_image_url", None) if author is not None else None,
        },
    }


class YouTubeStreamSource:
    """Official liveChatMessages.streamList over gRPC."""

    def __init__(
        self,
        *,
        live_chat_id: str,
        broadcast_id: str,
        ownership_token: str,
        api_key: str | None = None,
        access_token: str | None = None,
        session_id: object | None = None,
        page_token: str | None = None,
        stub: object | None = None,
    ) -> None:
        self.live_chat_id = live_chat_id
        self.broadcast_id = broadcast_id
        self.ownership_token = ownership_token
        self.api_key = api_key
        self.access_token = access_token
        self.session_id = session_id
        self.page_token = page_token
        self._stub = stub
        self._connected = False
        self._health = SourceHealth.HEALTHY
        self._channel: object | None = None

    def connect(self) -> None:
        if self._stub is not None:
            self._connected = True
            return
        try:
            import grpc

            from color_rush.infrastructure.youtube.generated import stream_list_pb2, stream_list_pb2_grpc
        except ImportError as exc:
            raise RuntimeError("gRPC YouTube stubs are not generated; use polling transport") from exc
        creds = grpc.ssl_channel_credentials()
        self._channel = grpc.secure_channel(GRPC_HOST, creds)
        self._stub = stream_list_pb2_grpc.V3DataLiveChatMessageServiceStub(self._channel)  # type: ignore[no-untyped-call]
        self._pb2 = stream_list_pb2
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        channel = self._channel
        if channel is not None:
            close = getattr(channel, "close", None)
            if callable(close):
                close()

    def health(self) -> SourceHealth:
        return self._health

    def _metadata(self) -> tuple[tuple[str, str], ...]:
        if self.access_token:
            return (("authorization", f"Bearer {self.access_token}"),)
        if self.api_key:
            return (("x-goog-api-key", self.api_key),)
        return ()

    def iter_batches(self) -> Iterator[SourceBatch]:
        self.connect()
        pb2 = getattr(self, "_pb2", None)
        while self._connected:
            if pb2 is None:
                request = _FakeRequest(
                    live_chat_id=self.live_chat_id,
                    page_token=self.page_token,
                    part=["id", "snippet", "authorDetails"],
                )
            else:
                request = pb2.LiveChatMessageListRequest(
                    part=["id", "snippet", "authorDetails"],
                    live_chat_id=self.live_chat_id,
                    page_token=self.page_token,
                )
            try:
                stream = self._stub.StreamList(request, metadata=self._metadata())  # type: ignore[union-attr]
                for response in stream:
                    items = [_message_to_dict(item) for item in getattr(response, "items", [])]
                    commands = normalize_live_chat_items(items, broadcast_id=self.broadcast_id)
                    token = getattr(response, "next_page_token", None) or self.page_token
                    self.page_token = token
                    offline = bool(getattr(response, "offline_at", None))
                    health = SourceHealth.ENDED if offline else SourceHealth.HEALTHY
                    self._health = health
                    checkpoint = SourceCheckpointData(
                        broadcast_id=self.broadcast_id,
                        next_page_token=token,
                        source_mode="youtube",
                        ownership_token=self.ownership_token,
                        session_id=self.session_id,  # type: ignore[arg-type]
                        resync_required=False,
                        error_class=None if health is SourceHealth.HEALTHY else health.value,
                    )
                    yield SourceBatch(tuple(commands), checkpoint, health)
                    if not token:
                        return
            except Exception as exc:
                grpc_code = getattr(getattr(exc, "code", lambda: None)(), "value", None)
                health = classify_youtube_error(None, str(exc), grpc_code=grpc_code)
                self._health = health
                checkpoint = SourceCheckpointData(
                    broadcast_id=self.broadcast_id,
                    next_page_token=self.page_token,
                    source_mode="youtube",
                    ownership_token=self.ownership_token,
                    session_id=self.session_id,  # type: ignore[arg-type]
                    resync_required=health is SourceHealth.RESYNC,
                    error_class=health.value,
                )
                yield SourceBatch((), checkpoint, health)
                return


class _FakeRequest:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)
