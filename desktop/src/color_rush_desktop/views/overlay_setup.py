from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.confirm import confirm_action
from color_rush_desktop.widgets.status import PageFrame


class OverlaySetupPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Overlay Setup", parent)
        self._vm = vm
        self.label = QLineEdit("overlay")
        self.url = QLineEdit()
        self.url.setReadOnly(True)
        self.url.setPlaceholderText("OBS URL appears once after create — copy it now")
        create = QPushButton("Create credential")
        create.setProperty("cssClass", "accent")
        copy = QPushButton("Copy OBS URL")
        preview = QPushButton("Open preview")
        revoke = QPushButton("Revoke selected")
        row = QHBoxLayout()
        row.addWidget(self.label)
        row.addWidget(create)
        row.addWidget(copy)
        row.addWidget(preview)
        row.addWidget(revoke)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Label", "Revoked", "Created"])
        self.body.addLayout(row)
        self.body.addWidget(self.url)
        howto = QLabel(
            "OBS Browser Source: 1920×1080 (tested 1280×720). Paste the URL including the fragment. "
            "Keep audio off. This console never embeds owner controls in the overlay."
        )
        howto.setWordWrap(True)
        self.body.addWidget(howto)
        self.body.addWidget(self.table, 1)
        create.clicked.connect(self._create)
        copy.clicked.connect(self._copy)
        preview.clicked.connect(self._preview)
        revoke.clicked.connect(self._revoke)
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self.reload())
        vm.role_changed.connect(lambda _: self._enable())
        vm.stale_changed.connect(lambda _: self._enable())
        self._create_btn = create
        self._revoke_btn = revoke
        self._enable()

    def reload(self) -> None:
        if not self._vm.game_id:
            self.set_empty("Create a game first.")
            return
        self._vm.get("/api/v1/admin/overlay-tickets", job_id="overlay-list", params={"game_id": self._vm.game_id})

    def _create(self) -> None:
        if not self._vm.game_id:
            return
        self._vm.write(
            "POST",
            "/api/v1/admin/overlay-tickets",
            {"game_id": self._vm.game_id, "session_id": self._vm.session_id, "label": self.label.text().strip() or "overlay"},
            job_id="overlay-create",
        )

    def _copy(self) -> None:
        if self.url.text():
            QGuiApplication.clipboard().setText(self.url.text())
            self.status.setText("OBS URL copied. The secret is not written to logs.")

    def _preview(self) -> None:
        target = self.url.text() or f"{self._vm.config.api_base}/overlay"
        QDesktopServices.openUrl(QUrl(target))

    def _revoke(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        ticket_id = self.table.item(items[0].row(), 0).text()
        if not confirm_action(self, "Revoke overlay ticket", f"Revoke overlay credential {ticket_id}?"):
            return
        self._vm.write("POST", f"/api/v1/admin/overlay-tickets/{ticket_id}/revoke", {}, job_id="overlay-revoke")

    def _on_ok(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id == "overlay-create":
            obs_url = str(data.get("obs_url") or "")
            self.url.setText(obs_url)
            self.reload()
        if job_id in {"overlay-list", "overlay-revoke"}:
            if job_id == "overlay-revoke":
                self.reload()
                return
            rows = data.get("items") or []
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.table.setItem(index, 0, QTableWidgetItem(str(row.get("id"))))
                self.table.setItem(index, 1, QTableWidgetItem(str(row.get("label"))))
                self.table.setItem(index, 2, QTableWidgetItem("yes" if row.get("revoked") else "no"))
                self.table.setItem(index, 3, QTableWidgetItem(str(row.get("created_at"))))
            self.set_empty("No overlay credentials yet." if not rows else None)

    def _enable(self) -> None:
        ok = self._vm.can("overlay")
        self._create_btn.setEnabled(ok)
        self._revoke_btn.setEnabled(ok)
