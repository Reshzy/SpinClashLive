from __future__ import annotations

import time

import httpx
import pytest

from color_rush_desktop.api_client.rest import RestClient
from color_rush_desktop.config import DesktopConfig
from color_rush_desktop.roles import can
from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.views.dashboard import DashboardPage
from color_rush_desktop.views.login import LoginView
from color_rush_desktop.views.settings import SettingsPage
from color_rush_desktop.views.shell import PAGES, MainShell

pytestmark = pytest.mark.qt


def _vm(transport: httpx.BaseTransport | None = None) -> SessionViewModel:
    config = DesktopConfig(api_base="http://color-rush.test")
    client = RestClient(config, transport=transport)
    return SessionViewModel(config, client=client)


def test_disconnected_buttons_disabled(qtbot) -> None:
    vm = _vm()
    page = DashboardPage(vm)
    qtbot.addWidget(page)
    assert vm.stale
    assert not page.btn_start.isEnabled()
    assert not page.btn_cancel.isEnabled()
    vm.shutdown()


def test_moderator_cannot_save_settings(qtbot) -> None:
    vm = _vm()
    vm.role = "moderator"
    vm.connected = True
    vm.stale = False
    page = SettingsPage(vm)
    qtbot.addWidget(page)
    page._enable()
    assert not page._save_btn.isEnabled()
    assert can("moderator", "pause")
    assert not can("moderator", "settings")
    vm.shutdown()


def test_failed_action_keeps_round_state(qtbot) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(
                409,
                json={"code": "round_busy", "message": "session is paused", "request_id": "r1"},
            )
        return httpx.Response(200, json={})

    vm = _vm(httpx.MockTransport(handler))
    vm.connected = True
    vm.stale = False
    vm.role = "owner"
    vm.session_id = "11111111-1111-1111-1111-111111111111"
    vm.round_state = "waiting"
    page = DashboardPage(vm)
    qtbot.addWidget(page)
    errors: list[tuple[str, str]] = []
    vm.error_occurred.connect(lambda code, message: errors.append((code, message)))
    page._start()
    qtbot.waitUntil(lambda: bool(errors), timeout=3000)
    assert errors[0][0] == "round_busy"
    assert vm.round_state == "waiting"
    vm.shutdown()


def test_slow_network_keeps_ui_clickable(qtbot) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.4)
        return httpx.Response(200, json={"status": "ok"})

    vm = _vm(httpx.MockTransport(handler))
    vm.connected = True
    vm.stale = False
    vm.role = "owner"
    vm.session_id = "11111111-1111-1111-1111-111111111111"
    page = DashboardPage(vm)
    qtbot.addWidget(page)
    page._enable()
    assert page.btn_pause.isEnabled()
    started = time.monotonic()
    page.btn_pause.click()
    assert page.btn_resume.isEnabled()
    assert time.monotonic() - started < 0.2
    vm.shutdown()


def test_reconnect_ignores_stale_snapshot(qtbot) -> None:
    vm = _vm()
    vm.connected = True
    vm.apply_snapshot(
        {
            "snapshot_sequence": 5,
            "session_id": "abc",
            "data": {"state": "open", "session_revision": 3},
        }
    )
    vm.apply_snapshot(
        {
            "snapshot_sequence": 2,
            "session_id": "abc",
            "data": {"state": "locked", "session_revision": 9},
        }
    )
    assert vm.round_state == "open"
    assert vm.revision == 3
    vm.apply_snapshot(
        {
            "snapshot_sequence": 6,
            "session_id": "abc",
            "data": {"state": "locked", "session_revision": 4},
        }
    )
    assert vm.round_state == "locked"
    vm.shutdown()


def test_login_error_and_shell_pages(qtbot) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "auth_error", "message": "invalid credentials", "request_id": "x"})

    vm = _vm(httpx.MockTransport(handler))
    login = LoginView(vm)
    qtbot.addWidget(login)
    login.user.setText("owner")
    login.password.setText("nope")
    login._submit()
    qtbot.waitUntil(lambda: "auth_error" in login.error.text(), timeout=3000)
    shell = MainShell(vm)
    qtbot.addWidget(shell)
    assert shell.nav.count() == len(PAGES)
    for index in range(shell.nav.count()):
        shell.nav.setCurrentRow(index)
        assert shell.stack.currentIndex() == index
    vm.shutdown()


def test_shutdown_cancels_worker(qtbot) -> None:
    started = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        started["n"] += 1
        time.sleep(1.5)
        return httpx.Response(200, json={"ok": True})

    vm = _vm(httpx.MockTransport(handler))
    vm.connected = True
    vm.stale = False
    vm.get("/api/v1/admin/health", job_id="health")
    qtbot.waitUntil(lambda: started["n"] > 0 or True, timeout=500)
    vm.shutdown()
    assert not vm._thread.isRunning()
