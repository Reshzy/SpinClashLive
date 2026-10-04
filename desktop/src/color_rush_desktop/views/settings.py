from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.confirm import confirm_action
from color_rush_desktop.widgets.status import PageFrame


class SettingsPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Settings", parent)
        self._vm = vm
        self.version = QLabel("Version: —")
        self.pred_window = QSpinBox()
        self.pred_window.setRange(5, 300)
        self.drain = QSpinBox()
        self.drain.setRange(1, 30)
        self.animation = QSpinBox()
        self.animation.setRange(1, 30)
        self.result = QSpinBox()
        self.result.setRange(1, 30)
        self.cooldown = QSpinBox()
        self.cooldown.setRange(1, 30)
        self.timezone = QLineEdit("Asia/Manila")
        self.timezone.setReadOnly(True)
        form = QFormLayout()
        form.addRow("Prediction window (s)", self.pred_window)
        form.addRow("Drain bound (s)", self.drain)
        form.addRow("Animation (s)", self.animation)
        form.addRow("Result display (s)", self.result)
        form.addRow("Cooldown (s)", self.cooldown)
        form.addRow("Timezone (fixed in V1)", self.timezone)
        save = QPushButton("Save for next round")
        save.setProperty("cssClass", "accent")
        self.body.addWidget(self.version)
        self.body.addLayout(form)
        self.body.addWidget(save)
        info = QLabel(
            "Changes activate on the next round. The current OPEN round keeps its frozen rules snapshot. "
            "Timezone cannot be edited after the first production round."
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        self.body.addWidget(info)
        self.user_name = QLineEdit()
        self.user_name.setPlaceholderText("New operator username")
        self.user_pass = QLineEdit()
        self.user_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.user_pass.setPlaceholderText("Password (min 8)")
        self.user_role = QComboBox()
        self.user_role.addItems(["admin", "moderator", "observer", "owner"])
        create_user = QPushButton("Create operator")
        users_row = QHBoxLayout()
        users_row.addWidget(self.user_name)
        users_row.addWidget(self.user_pass)
        users_row.addWidget(self.user_role)
        users_row.addWidget(create_user)
        self.users = QTableWidget(0, 3)
        self.users.setHorizontalHeaderLabels(["Username", "Role", "Created"])
        self.body.addWidget(QLabel("Operators (owner)"))
        self.body.addLayout(users_row)
        self.body.addWidget(self.users)
        save.clicked.connect(self._save)
        create_user.clicked.connect(self._create_user)
        vm.action_ok.connect(self._on_ok)
        vm.connected_changed.connect(lambda ok: ok and self.reload())
        vm.role_changed.connect(lambda _: self._enable())
        vm.stale_changed.connect(lambda _: self._enable())
        self._save_btn = save
        self._create_btn = create_user
        self._config: dict[str, Any] = {}
        self._enable()

    def reload(self) -> None:
        if self._vm.game_id:
            self._vm.get("/api/v1/admin/settings", job_id="settings", params={"game_id": self._vm.game_id})
        if self._vm.can_role("users"):
            self._vm.get("/api/v1/admin/users", job_id="users")

    def _save(self) -> None:
        if not self._vm.game_id:
            return
        if not confirm_action(self, "Save settings", "Save these timings for the next round? The current round stays immutable."):
            return
        config = dict(self._config)
        config.update(
            {
                "prediction_window_s": self.pred_window.value(),
                "drain_bound_s": self.drain.value(),
                "animation_s": self.animation.value(),
                "result_display_s": self.result.value(),
                "cooldown_s": self.cooldown.value(),
                "timezone": self.timezone.text().strip() or "Asia/Manila",
            }
        )
        body = {"game_id": self._vm.game_id, "configuration": config, "session_id": self._vm.session_id}
        self._vm.write("PUT", "/api/v1/admin/settings", body, job_id="save-settings")

    def _create_user(self) -> None:
        self._vm.write(
            "POST",
            "/api/v1/admin/users",
            {
                "username": self.user_name.text().strip(),
                "password": self.user_pass.text(),
                "role": self.user_role.currentText(),
            },
            job_id="create-user",
        )

    def _on_ok(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id == "settings":
            self._config = dict(data.get("configuration") or {})
            self.version.setText(f"Version {data.get('version')} · activates on {data.get('activation_boundary')}")
            self.pred_window.setValue(int(self._config.get("prediction_window_s") or 30))
            self.drain.setValue(int(self._config.get("drain_bound_s") or 5))
            self.animation.setValue(int(self._config.get("animation_s") or 6))
            self.result.setValue(int(self._config.get("result_display_s") or 5))
            self.cooldown.setValue(int(self._config.get("cooldown_s") or 3))
            self.timezone.setText(str(self._config.get("timezone") or "Asia/Manila"))
        if job_id == "save-settings":
            self.reload()
        if job_id in {"users", "create-user"}:
            if job_id == "create-user":
                self.reload()
                return
            rows = data.get("items") or []
            self.users.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.users.setItem(index, 0, QTableWidgetItem(str(row.get("username"))))
                self.users.setItem(index, 1, QTableWidgetItem(str(row.get("role"))))
                self.users.setItem(index, 2, QTableWidgetItem(str(row.get("created_at"))))

    def _enable(self) -> None:
        self._save_btn.setEnabled(self._vm.can("settings"))
        owner = self._vm.can("users")
        self._create_btn.setEnabled(owner)
        self.users.setVisible(self._vm.can_role("users"))
