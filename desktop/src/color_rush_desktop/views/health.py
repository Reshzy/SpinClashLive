from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.status import PageFrame, StatusChip


class HealthPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Health / Audit", parent)
        self._vm = vm
        self.pg = StatusChip("postgres")
        self.redis = StatusChip("redis")
        self.source = StatusChip("source")
        self.jobs = QLabel("Jobs: —")
        refresh = QPushButton("Refresh")
        self.body.addWidget(self.pg)
        self.body.addWidget(self.redis)
        self.body.addWidget(self.source)
        self.body.addWidget(self.jobs)
        self.body.addWidget(refresh)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["When", "Action", "Reason"])
        self.body.addWidget(self.table, 1)
        refresh.clicked.connect(self.reload)
        vm.health_changed.connect(self._health)
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self.reload())

    def reload(self) -> None:
        self._vm.get("/api/v1/admin/health", job_id="health")
        self._vm.get("/api/v1/admin/audit", job_id="audit")

    def _health(self, payload: dict) -> None:
        self.pg.set_state("ok" if payload.get("postgres") else "error", "PostgreSQL")
        self.redis.set_state("ok" if payload.get("redis") else "warn", "Redis")
        source = str(payload.get("source") or "unknown")
        self.source.set_state("ok" if source == "healthy" else "warn", f"Source {source}")
        self.jobs.setText(f"Jobs: {payload.get('jobs')}")

    def _on_ok(self, job_id: str, payload: object) -> None:
        if job_id != "audit":
            return
        data = payload if isinstance(payload, dict) else {}
        rows = data.get("items") or []
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(str(row.get("created_at"))))
            self.table.setItem(index, 1, QTableWidgetItem(str(row.get("action"))))
            self.table.setItem(index, 2, QTableWidgetItem(str(row.get("reason") or "")))
        self.set_empty("No audit history." if not rows else None)
