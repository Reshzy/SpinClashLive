from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QWidget

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.status import PageFrame


class ModerationPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Moderation", parent)
        self._vm = vm
        note = QLabel(
            "Use Players to game-block or unblock with a reason. That is not a YouTube chat ban. "
            "OPEN picks are removed; LOCKED picks stay frozen."
        )
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "Action", "Reason", "ID"])
        self.body.addWidget(self.table, 1)
        vm.connected_changed.connect(lambda ok: ok and self.reload())
        vm.action_ok.connect(self._on_ok)

    def reload(self) -> None:
        self._vm.get("/api/v1/admin/audit", job_id="mod-audit")

    def _on_ok(self, job_id: str, payload: object) -> None:
        if job_id != "mod-audit":
            return
        data = payload if isinstance(payload, dict) else {}
        rows = [item for item in (data.get("items") or []) if str(item.get("action") or "").startswith("player") or "moderation" in str(item.get("action"))]
        if not rows:
            rows = data.get("items") or []
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(str(row.get("created_at"))))
            self.table.setItem(index, 1, QTableWidgetItem(str(row.get("action"))))
            self.table.setItem(index, 2, QTableWidgetItem(str(row.get("reason") or "")))
            self.table.setItem(index, 3, QTableWidgetItem(str(row.get("id"))))
        self.set_empty("No audit entries." if not rows else None)
