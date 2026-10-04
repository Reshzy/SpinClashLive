from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.status import PageFrame


class SeasonsPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Seasons", parent)
        self._vm = vm
        self.name = QLineEdit()
        self.name.setPlaceholderText("Season name")
        self.starts = QDateTimeEdit(QDateTime.currentDateTimeUtc())
        self.ends = QDateTimeEdit(QDateTime.currentDateTimeUtc().addMonths(1))
        self.starts.setCalendarPopup(True)
        self.ends.setCalendarPopup(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Start", "End", "Status"])
        create = QPushButton("Create season")
        create.setProperty("cssClass", "accent")
        finalize = QPushButton("Finalize due periods")
        row = QHBoxLayout()
        row.addWidget(self.name)
        row.addWidget(self.starts)
        row.addWidget(self.ends)
        row.addWidget(create)
        row.addWidget(finalize)
        self.body.addLayout(row)
        self.body.addWidget(self.table, 1)
        note = QLabel("No live destructive leaderboard reset. Seasons cannot overlap. Timezone is Asia/Manila unless migrated.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.body.addWidget(note)
        create.clicked.connect(self._create)
        finalize.clicked.connect(self._finalize)
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self.reload())
        vm.role_changed.connect(lambda _: self._enable())
        vm.stale_changed.connect(lambda _: self._enable())
        self._create_btn = create
        self._finalize_btn = finalize
        self._enable()

    def reload(self) -> None:
        if not self._vm.game_id:
            self.set_empty("Create a game first.")
            return
        self._vm.get("/api/v1/admin/seasons", job_id="seasons", params={"game_id": self._vm.game_id})

    def _create(self) -> None:
        if not self._vm.game_id:
            return
        self._vm.write(
            "POST",
            "/api/v1/admin/seasons",
            {
                "game_id": self._vm.game_id,
                "name": self.name.text().strip() or "Season",
                "starts_at": _iso(self.starts),
                "ends_at": _iso(self.ends),
            },
            job_id="create-season",
        )

    def _finalize(self) -> None:
        if not self._vm.game_id:
            return
        self._vm.write("POST", f"/api/v1/admin/periods/finalize?game_id={self._vm.game_id}", {}, job_id="finalize")

    def _on_ok(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id in {"create-season", "finalize"}:
            self.reload()
        if job_id == "seasons":
            rows = data.get("items") or []
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.table.setItem(index, 0, QTableWidgetItem(str(row.get("name"))))
                self.table.setItem(index, 1, QTableWidgetItem(str(row.get("starts_at"))))
                self.table.setItem(index, 2, QTableWidgetItem(str(row.get("ends_at"))))
                self.table.setItem(index, 3, QTableWidgetItem(str(row.get("status"))))
            self.set_empty("No seasons." if not rows else None)

    def _enable(self) -> None:
        ok = self._vm.can("seasons")
        self._create_btn.setEnabled(ok)
        self._finalize_btn.setEnabled(ok)


def _iso(edit: QDateTimeEdit) -> str:
    stamp = edit.dateTime().toUTC().toSecsSinceEpoch()
    return datetime.fromtimestamp(stamp, tz=UTC).isoformat()
