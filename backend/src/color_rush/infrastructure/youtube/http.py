from __future__ import annotations

from collections.abc import Iterator

import httpx

from color_rush.application.dto import SourceBatch, SourceCheckpointData
from color_rush.domain.enums import SourceHealth
from color_rush.infrastructure.youtube.normalize import classify_youtube_error, normalize_live_chat_items
from color_rush.infrastructure.youtube.video import parse_video_ref

VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MESSAGES_URL = "https://www.googleapis.com/youtube/v3/liveChat/messages"


class YouTubeHttpClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: LiteralHttp | None = None,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout) if transport is None else None
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    def _params(self, extra: dict[str, str]) -> dict[str, str]:
        params = dict(extra)
        if self.api_key and not self.access_token:
            params["key"] = self.api_key
        return params

    def _get(self, url: str, params: dict[str, str]) -> httpx.Response:
        if self._transport is not None:
            return self._transport.get(url, params=params, headers=self._headers())
        assert self._client is not None
        return self._client.get(url, params=self._params(params), headers=self._headers())

    def resolve_live_chat_id(self, video_ref: str) -> str:
        video_id = parse_video_ref(video_ref)
        response = self._get(VIDEOS_URL, {"part": "liveStreamingDetails", "id": video_id})
        if response.status_code >= 400:
            raise LookupError(f"videos.list failed: {response.status_code}")
        payload = response.json()
        items = payload.get("items") or []
        if not items:
            raise LookupError("video not found")
        details = items[0].get("liveStreamingDetails") or {}
        chat_id = details.get("activeLiveChatId")
        if not chat_id:
            raise LookupError("live chat is not available for this video")
        return str(chat_id)

    def list_messages(
        self,
        live_chat_id: str,
        *,
        page_token: str | None = None,
        broadcast_id: str,
        ownership_token: str,
        session_id: object | None = None,
    ) -> SourceBatch:
        params = {
            "liveChatId": live_chat_id,
            "part": "id,snippet,authorDetails",
        }
        if page_token:
            params["pageToken"] = page_token
        response = self._get(MESSAGES_URL, params)
        if response.status_code >= 400:
            reason = None
            try:
                error = response.json().get("error", {})
                errors = error.get("errors") or [{}]
                reason = errors[0].get("reason")
            except Exception:
                reason = None
            health = classify_youtube_error(response.status_code, reason)
            checkpoint = SourceCheckpointData(
                broadcast_id=broadcast_id,
                next_page_token=page_token,
                source_mode="youtube",
                ownership_token=ownership_token,
                session_id=session_id,  # type: ignore[arg-type]
                resync_required=health is SourceHealth.RESYNC,
                error_class=health.value,
            )
            return SourceBatch((), checkpoint, health)
        payload = response.json()
        items = list(payload.get("items") or [])
        commands = normalize_live_chat_items(items, broadcast_id=broadcast_id)
        interval = int(payload.get("pollingIntervalMillis") or 5000)
        health = SourceHealth.HEALTHY
        if payload.get("offlineAt"):
            health = SourceHealth.ENDED
        checkpoint = SourceCheckpointData(
            broadcast_id=broadcast_id,
            next_page_token=payload.get("nextPageToken"),
            source_mode="youtube",
            ownership_token=ownership_token,
            session_id=session_id,  # type: ignore[arg-type]
            resync_required=False,
            error_class=None if health is SourceHealth.HEALTHY else health.value,
            lag_ms=interval,
        )
        return SourceBatch(tuple(commands), checkpoint, health, lag_ms=interval)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


class LiteralHttp:
    """Test double for httpx.Client.get."""

    def get(self, url: str, params: dict[str, str], headers: dict[str, str]) -> httpx.Response:
        raise NotImplementedError


class YouTubePollingSource:
    def __init__(
        self,
        client: YouTubeHttpClient,
        *,
        live_chat_id: str,
        broadcast_id: str,
        ownership_token: str,
        session_id: object | None = None,
        page_token: str | None = None,
    ) -> None:
        self.client = client
        self.live_chat_id = live_chat_id
        self.broadcast_id = broadcast_id
        self.ownership_token = ownership_token
        self.session_id = session_id
        self.page_token = page_token
        self._connected = False
        self._health = SourceHealth.HEALTHY

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self.client.close()

    def health(self) -> SourceHealth:
        return self._health

    def iter_batches(self) -> Iterator[SourceBatch]:
        self.connect()
        while self._connected:
            batch = self.client.list_messages(
                self.live_chat_id,
                page_token=self.page_token,
                broadcast_id=self.broadcast_id,
                ownership_token=self.ownership_token,
                session_id=self.session_id,
            )
            self._health = batch.health
            self.page_token = batch.checkpoint.next_page_token
            yield batch
            terminal = {SourceHealth.ENDED, SourceHealth.DISABLED, SourceHealth.PERMISSION, SourceHealth.RESYNC}
            if batch.health in terminal:
                break
