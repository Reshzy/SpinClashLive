from __future__ import annotations

import asyncio

import pytest
from fastapi import WebSocketDisconnect

from color_rush.api.ws import send_or_reset_buffer
from color_rush.application.ws_buffer import SnapshotClientBuffer


def test_buffer_rejects_stale_and_coalesces() -> None:
    buf = SnapshotClientBuffer(max_size=3)
    buf.push({"snapshot_sequence": 1, "data": {"state": "OPEN"}})
    buf.push({"snapshot_sequence": 2, "data": {"state": "OPEN"}})
    buf.push({"snapshot_sequence": 0, "data": {"state": "OPEN"}})
    buf.push({"snapshot_sequence": 3, "data": {"state": "OPEN"}})
    buf.push({"snapshot_sequence": 4, "data": {"state": "LOCKED"}})
    assert buf.coalesced >= 1
    outgoing = buf.pop_send()
    assert outgoing is not None
    assert outgoing["snapshot_sequence"] == 4


def test_buffer_bounded() -> None:
    buf = SnapshotClientBuffer(max_size=2)
    for seq in range(10):
        buf.push({"snapshot_sequence": seq})
    assert len(buf._q) <= 2


class _SlowWebSocket:
    async def send_text(self, _raw: str) -> None:
        await asyncio.sleep(2.0)


class _FastWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, raw: str) -> None:
        self.sent.append(raw)


class _DisconnectedWebSocket:
    async def send_text(self, _raw: str) -> None:
        raise WebSocketDisconnect()


@pytest.mark.asyncio
async def test_slow_client_send_resets_buffer() -> None:
    original = SnapshotClientBuffer()
    original.push({"snapshot_sequence": 1, "data": {"state": "OPEN"}})
    outgoing = original.pop_send()
    assert outgoing is not None
    reset = await send_or_reset_buffer(_SlowWebSocket(), outgoing, original, timeout_s=0.05)  # type: ignore[arg-type]
    assert reset is not original
    assert len(reset._q) == 0


@pytest.mark.asyncio
async def test_fast_client_keeps_buffer() -> None:
    original = SnapshotClientBuffer()
    ws = _FastWebSocket()
    kept = await send_or_reset_buffer(ws, {"snapshot_sequence": 2, "data": {}}, original)  # type: ignore[arg-type]
    assert kept is original
    assert ws.sent


@pytest.mark.asyncio
async def test_disconnected_ws_send_raises() -> None:
    with pytest.raises(WebSocketDisconnect):
        await send_or_reset_buffer(
            _DisconnectedWebSocket(),  # type: ignore[arg-type]
            {"snapshot_sequence": 1, "data": {}},
            SnapshotClientBuffer(),
        )
