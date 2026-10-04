from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.confirm import confirm_action
from color_rush_desktop.widgets.status import PageFrame


class PlayersPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Players", parent)
        self._vm = vm
        self._cursor: str | None = None
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search display name")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Channel", "Deleted"])
        self.ranks = QLabel("Select a player to load four ranks.")
        self.ranks.setWordWrap(True)
        row = QHBoxLayout()
        self.block = QPushButton("Game-block")
        self.unblock = QPushButton("Unblock")
        self.delete = QPushButton("Delete data")
        self.delete.setProperty("cssClass", "danger")
        self.more = QPushButton("Next page")
        row.addWidget(self.block)
        row.addWidget(self.unblock)
        row.addWidget(self.delete)
        row.addWidget(self.more)
        self.body.addWidget(self.search)
        self.body.addWidget(self.table, 1)
        self.body.addWidget(self.ranks)
        note = QLabel("Game blocking removes an OPEN pick and rejects future picks. It does not ban the person from YouTube chat.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.body.addWidget(note)
        self.body.addLayout(row)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self._debounce.timeout.connect(self.reload)
        self.table.itemSelectionChanged.connect(self._load_ranks)
        self.block.clicked.connect(lambda: self._mod(True))
        self.unblock.clicked.connect(lambda: self._mod(False))
        self.delete.clicked.connect(self._delete)
        self.more.clicked.connect(lambda: self.reload(next_page=True))
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self.reload())
        vm.stale_changed.connect(lambda _: self._enable())
        self._enable()

    def reload(self, next_page: bool = False) -> None:
        params: dict[str, str] = {}
        if self.search.text().strip():
            params["search"] = self.search.text().strip()
        if next_page and self._cursor:
            params["cursor"] = self._cursor
        else:
            self._cursor = None
        self._vm.get("/api/v1/players", job_id="players", params=params or None)

    def _selected_id(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), 0).text()

    def _load_ranks(self) -> None:
        player_id = self._selected_id()
        if not player_id:
            return
        params = {"game_id": self._vm.game_id} if self._vm.game_id else None
        self._vm.get(f"/api/v1/players/{player_id}/ranks", job_id="player-ranks", params=params)

    def _mod(self, blocked: bool) -> None:
        player_id = self._selected_id()
        if not player_id:
            return
        scope = f"game:{self._vm.game_id}" if self._vm.game_id else "game"
        self._vm.write(
            "POST",
            f"/api/v1/admin/players/{player_id}/moderation",
            {"scope_key": scope, "blocked": blocked, "reason": "operator console"},
            job_id="moderation",
        )

    def _delete(self) -> None:
        player_id = self._selected_id()
        if not player_id:
            return
        if not confirm_action(
            self,
            "Delete player data",
            f"Anonymize player {player_id} in SQL/Redis projections? This cannot restore the original profile.",
        ):
            return
        params = f"?game_id={self._vm.game_id}" if self._vm.game_id else ""
        self._vm.write("POST", f"/api/v1/admin/players/{player_id}/delete-data{params}", {}, job_id="delete-player")

    def _on_ok(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id == "players":
            rows = data.get("items") or []
            self._cursor = data.get("next_cursor")
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.table.setItem(index, 0, QTableWidgetItem(str(row.get("id"))))
                self.table.setItem(index, 1, QTableWidgetItem(str(row.get("display_name"))))
                self.table.setItem(index, 2, QTableWidgetItem(str(row.get("provider_channel_id") or "")))
                self.table.setItem(index, 3, QTableWidgetItem("yes" if row.get("deleted") else "no"))
            self.set_empty("No players yet." if not rows else None)
        if job_id == "player-ranks":
            stats = data.get("stats") or {}
            ranks = data.get("ranks") or {}
            parts = [f"{scope}: rank {info.get('rank')} ({info.get('points')} pts)" for scope, info in ranks.items() if isinstance(info, dict)]
            self.ranks.setText(
                f"{data.get('display_name')} · streak {stats.get('current_streak')} best {stats.get('best_streak')} · "
                + " · ".join(parts)
            )

    def _enable(self) -> None:
        self.block.setEnabled(self._vm.can("moderation"))
        self.unblock.setEnabled(self._vm.can("moderation"))
        self.delete.setEnabled(self._vm.can("delete"))
