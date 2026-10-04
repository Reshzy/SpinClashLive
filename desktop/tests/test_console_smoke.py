from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from color_rush_desktop.api_client.rest import RestClient
from color_rush_desktop.config import DesktopConfig
from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.views.dashboard import DashboardPage
from color_rush_desktop.views.overlay_setup import OverlaySetupPage
from color_rush_desktop.views.youtube import YouTubePage

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _vm() -> SessionViewModel:
    config = DesktopConfig(api_base="http://color-rush.test")
    return SessionViewModel(config, client=RestClient(config, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


@pytest.mark.qt
def test_grab_main_pages(qtbot) -> None:
    vm = _vm()
    vm.connected = True
    vm.stale = False
    vm.role = "owner"
    vm.env = "simulation"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pages = {
        "dashboard.png": DashboardPage(vm),
        "youtube.png": YouTubePage(vm),
        "overlay.png": OverlaySetupPage(vm),
    }
    for name, page in pages.items():
        qtbot.addWidget(page)
        page.resize(1200, 800)
        page.show()
        qtbot.wait(50)
        page.grab().save(str(ARTIFACTS / name))
    vm.shutdown()
    assert (ARTIFACTS / "dashboard.png").exists()


@pytest.mark.integration
def test_operator_smoke_against_running_api() -> None:
    base = os.environ.get("COLOR_RUSH_API_BASE", "http://127.0.0.1:8000")
    try:
        health = httpx.get(f"{base}/health/live", timeout=3.0)
        health.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"API not reachable at {base}: {exc}")
    login = httpx.post(
        f"{base}/api/v1/auth/login",
        json={"username": "owner", "password": "change-me-owner"},
        timeout=5.0,
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    game = httpx.post(
        f"{base}/api/v1/admin/games",
        json={"name": "Console smoke"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
        timeout=5.0,
    )
    game.raise_for_status()
    game_id = game.json()["id"]
    session = httpx.post(
        f"{base}/api/v1/admin/sessions",
        json={"game_id": game_id, "mode": "manual", "source_mode": "simulation"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
        timeout=5.0,
    )
    session.raise_for_status()
    session_id = session.json()["id"]
    started = httpx.post(
        f"{base}/api/v1/admin/rounds/start",
        json={"session_id": session_id},
        headers={**headers, "Idempotency-Key": str(uuid4())},
        timeout=5.0,
    )
    started.raise_for_status()
    paused = httpx.post(
        f"{base}/api/v1/admin/session/pause",
        json={"session_id": session_id},
        headers={**headers, "Idempotency-Key": str(uuid4())},
        timeout=5.0,
    )
    paused.raise_for_status()
    assert paused.json()["status"] == "paused"
    live = httpx.get(f"{base}/health/live", timeout=3.0)
    live.raise_for_status()
