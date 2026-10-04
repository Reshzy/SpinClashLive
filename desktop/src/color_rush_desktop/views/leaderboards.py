from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.status import PageFrame


class LeaderboardsPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Leaderboards", parent)
        self._vm = vm
        self._cursor = 0
        self.scope = QComboBox()
        self.scope.addItems(["weekly", "daily", "season", "all_time"])
        self.period = QComboBox()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Rank", "Player", "Points", "Rounds"])
        self.champion = QLabel("Champion: —")
        self.archive = QLabel("Archive: —")
        row = QHBoxLayout()
        load = QPushButton("Load")
        more = QPushButton("Next page")
        row.addWidget(self.scope)
        row.addWidget(self.period)
        row.addWidget(load)
        row.addWidget(more)
        self.body.addLayout(row)
        self.body.addWidget(self.table, 1)
        self.body.addWidget(self.champion)
        self.body.addWidget(self.archive)
        note = QLabel("Tie order is points descending, then canonical player id. Empty periods have no champion.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.body.addWidget(note)
        load.clicked.connect(self.reload)
        more.clicked.connect(lambda: self.reload(next_page=True))
        self.scope.currentTextChanged.connect(lambda _: self._load_periods())
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self._load_periods())

    def _load_periods(self) -> None:
        params = {"scope": self.scope.currentText()}
        if self._vm.game_id:
            params["game_id"] = self._vm.game_id
        self._vm.get("/api/v1/periods", job_id="periods", params=params)

    def reload(self, next_page: bool = False) -> None:
        if next_page:
            self._cursor += 50
        else:
            self._cursor = 0
        period_id = self.period.currentData()
        params: dict[str, object] = {"scope": self.scope.currentText(), "cursor": self._cursor, "limit": 50}
        if period_id:
            params["period_id"] = period_id
        if self._vm.game_id:
            params["game_id"] = self._vm.game_id
        self._vm.get("/api/v1/leaderboards", job_id="leaderboard", params=params)
        if period_id:
            self._vm.get(f"/api/v1/periods/{period_id}/champions", job_id="champions")
            self._vm.get(f"/api/v1/periods/{period_id}/archives", job_id="archives")

    def _on_ok(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id == "periods":
            self.period.clear()
            for item in data.get("items") or []:
                label = f"{item.get('status')} {item.get('starts_at')}"
                self.period.addItem(label, item.get("id"))
            if self.period.count():
                self.reload()
            else:
                self.set_empty("No periods for this scope yet.")
        if job_id == "leaderboard":
            rows = data.get("entries") or []
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.table.setItem(index, 0, QTableWidgetItem(str(row.get("rank"))))
                self.table.setItem(index, 1, QTableWidgetItem(str(row.get("display_name"))))
                self.table.setItem(index, 2, QTableWidgetItem(str(row.get("points"))))
                self.table.setItem(index, 3, QTableWidgetItem(str(row.get("rounds_played"))))
            self.set_empty("No scores in this period." if not rows else None)
        if job_id == "champions":
            items = data.get("items") or []
            if items:
                first = items[0]
                self.champion.setText(f"Champion: {first.get('display_name')} ({first.get('display_title')})")
            else:
                self.champion.setText("Champion: none (period not finalized or empty)")
        if job_id == "archives":
            count = len(data.get("items") or [])
            status = "archived Top 100" if count else "not archived"
            self.archive.setText(f"Archive: {status} ({count} rows)")
