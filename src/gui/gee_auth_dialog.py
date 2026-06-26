"""GEE authentication dialog — two-step: login then pick project."""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
        QLabel, QComboBox, QPushButton, QFrame,
        QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

if _QT_AVAILABLE:

    # ── Background workers ────────────────────────────────────────────────────

    class _LoginWorker(QThread):
        done = pyqtSignal(bool, str)  # success, message

        def __init__(self, fetcher):
            super().__init__()
            self._fetcher = fetcher

        def run(self):
            try:
                self._fetcher.authenticate()
                self.done.emit(True, "")
            except Exception as exc:
                self.done.emit(False, str(exc))

    class _ListProjectsWorker(QThread):
        done = pyqtSignal(bool, list, str)  # success, projects, message

        def __init__(self, fetcher):
            super().__init__()
            self._fetcher = fetcher

        def run(self):
            try:
                projects = self._fetcher.list_projects()
                self.done.emit(True, projects, "")
            except Exception as exc:
                self.done.emit(False, [], str(exc))

    class _InitWorker(QThread):
        done = pyqtSignal(bool, str)

        def __init__(self, fetcher, project_id):
            super().__init__()
            self._fetcher = fetcher
            self._project_id = project_id

        def run(self):
            try:
                self._fetcher.initialize(self._project_id)
                self.done.emit(True, "")
            except Exception as exc:
                self.done.emit(False, str(exc))

    # ── Dialog ────────────────────────────────────────────────────────────────

    class GEEAuthDialog(QDialog):
        """Two-step GEE auth: ① OAuth login → ② pick project from dropdown."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Google Earth Engine 认证")
            self.setMinimumWidth(460)
            self._fetcher = None
            self._worker = None
            self._build_ui()

        def set_fetcher(self, fetcher) -> None:
            self._fetcher = fetcher
            self._check_existing_login()

        # ── UI ────────────────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setSpacing(10)

            # ── Step 1 ────────────────────────────────────────────────────────
            step1_box = QFrame()
            step1_box.setFrameShape(QFrame.StyledPanel)
            step1_box.setStyleSheet(
                "QFrame { border: 1px solid #CCCCCC; border-radius: 5px; "
                "background: #FAFAFA; padding: 4px; }"
            )
            s1 = QVBoxLayout(step1_box)

            s1_header = QHBoxLayout()
            step1_title = QLabel("第一步：登录 Google 账号")
            step1_title.setFont(QFont("", -1, QFont.Bold))
            s1_header.addWidget(step1_title)
            s1_header.addStretch()
            self._login_status = QLabel("")
            self._login_status.setStyleSheet("color: #2E7D32; font-weight: bold;")
            s1_header.addWidget(self._login_status)
            s1.addLayout(s1_header)

            tip = QLabel("点击按钮会弹出浏览器，用 Google 账号授权即可，无需填写任何信息。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color: #666; font-size: 11px;")
            s1.addWidget(tip)

            self._login_btn = QPushButton("打开浏览器登录")
            self._login_btn.setFixedHeight(32)
            self._login_btn.clicked.connect(self._start_login)
            s1.addWidget(self._login_btn)

            layout.addWidget(step1_box)

            # ── Step 2 ────────────────────────────────────────────────────────
            self._step2_box = QFrame()
            self._step2_box.setFrameShape(QFrame.StyledPanel)
            self._step2_box.setStyleSheet(
                "QFrame { border: 1px solid #CCCCCC; border-radius: 5px; "
                "background: #FAFAFA; padding: 4px; }"
            )
            s2 = QVBoxLayout(self._step2_box)

            step2_title = QLabel("第二步：选择 Cloud 项目")
            step2_title.setFont(QFont("", -1, QFont.Bold))
            s2.addWidget(step2_title)

            proj_row = QHBoxLayout()
            self._project_combo = QComboBox()
            self._project_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._project_combo.setPlaceholderText("（加载中…）")
            proj_row.addWidget(self._project_combo, stretch=1)

            self._refresh_btn = QPushButton("刷新")
            self._refresh_btn.setFixedWidth(54)
            self._refresh_btn.clicked.connect(self._load_projects)
            proj_row.addWidget(self._refresh_btn)
            s2.addLayout(proj_row)

            self._proj_hint = QLabel("")
            self._proj_hint.setStyleSheet("color: #666; font-size: 11px;")
            s2.addWidget(self._proj_hint)

            layout.addWidget(self._step2_box)
            self._step2_box.setVisible(False)

            # ── Status bar ────────────────────────────────────────────────────
            self._status_label = QLabel("")
            self._status_label.setWordWrap(True)
            self._status_label.setStyleSheet("color: #555; font-size: 11px;")
            layout.addWidget(self._status_label)

            # ── Buttons ───────────────────────────────────────────────────────
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._confirm_btn = QPushButton("完成")
            self._confirm_btn.setEnabled(False)
            self._confirm_btn.setFixedWidth(70)
            self._confirm_btn.clicked.connect(self._confirm)
            btn_row.addWidget(self._confirm_btn)
            close_btn = QPushButton("关闭")
            close_btn.setFixedWidth(70)
            close_btn.clicked.connect(self.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

        # ── Logic ─────────────────────────────────────────────────────────────

        def _check_existing_login(self) -> None:
            """If credentials already exist, skip login and go to step 2."""
            if self._fetcher and self._fetcher.has_credentials():
                self._mark_logged_in()
                self._load_projects()

        def _start_login(self) -> None:
            if self._fetcher is None:
                self._set_status("错误：GEE Fetcher 未初始化")
                return
            self._login_btn.setEnabled(False)
            self._login_btn.setText("等待浏览器授权…")
            self._set_status("请在弹出的浏览器窗口中完成 Google 账号授权…")
            self._worker = _LoginWorker(self._fetcher)
            self._worker.done.connect(self._on_login_done)
            self._worker.start()

        def _on_login_done(self, success: bool, error: str) -> None:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("打开浏览器登录")
            if success:
                self._mark_logged_in()
                self._load_projects()
            else:
                self._set_status(f"登录失败: {error}")

        def _mark_logged_in(self) -> None:
            self._login_status.setText("✓ 已登录")
            self._step2_box.setVisible(True)
            self.adjustSize()

        def _load_projects(self) -> None:
            if self._fetcher is None:
                return
            self._project_combo.clear()
            self._project_combo.setPlaceholderText("加载中…")
            self._refresh_btn.setEnabled(False)
            self._proj_hint.setText("")
            self._confirm_btn.setEnabled(False)
            self._set_status("正在获取项目列表…")

            self._worker = _ListProjectsWorker(self._fetcher)
            self._worker.done.connect(self._on_projects_loaded)
            self._worker.start()

        def _on_projects_loaded(self, success: bool, projects: list, error: str) -> None:
            self._refresh_btn.setEnabled(True)
            if success:
                if projects:
                    self._project_combo.clear()
                    for pid in projects:
                        self._project_combo.addItem(pid)
                    # Pre-select current project if known
                    cur = getattr(self._fetcher, "_project_id", "")
                    if cur:
                        idx = self._project_combo.findText(cur)
                        if idx >= 0:
                            self._project_combo.setCurrentIndex(idx)
                    self._confirm_btn.setEnabled(True)
                    self._set_status(f"找到 {len(projects)} 个项目，请选择后点击完成。")
                    self._proj_hint.setText(
                        "提示：如果没有项目，请先在 console.cloud.google.com 创建，并启用 Earth Engine API。"
                    )
                else:
                    self._project_combo.setPlaceholderText("（未找到项目）")
                    self._set_status("未找到可用项目，请检查 GEE 权限或先在 Cloud Console 创建项目。")
            else:
                self._project_combo.setPlaceholderText("（加载失败）")
                self._set_status(f"获取项目列表失败: {error}")

        def _confirm(self) -> None:
            project_id = self._project_combo.currentText().strip()
            if not project_id:
                self._set_status("请先选择一个项目")
                return
            self._confirm_btn.setEnabled(False)
            self._set_status(f"正在初始化项目 {project_id}…")
            self._worker = _InitWorker(self._fetcher, project_id)
            self._worker.done.connect(self._on_init_done)
            self._worker.start()

        def _on_init_done(self, success: bool, error: str) -> None:
            self._confirm_btn.setEnabled(True)
            if success:
                self._set_status(f"认证成功！当前项目: {self._project_combo.currentText()}")
                self._login_status.setText("✓ 已登录并初始化")
            else:
                self._set_status(f"初始化失败: {error}")

        def _set_status(self, msg: str) -> None:
            self._status_label.setText(msg)
