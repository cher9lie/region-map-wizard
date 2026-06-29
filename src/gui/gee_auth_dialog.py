"""GEE authentication dialog — two-step: login then pick project."""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
        QLabel, QComboBox, QPushButton, QFrame,
        QSizePolicy, QWidget,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

if _QT_AVAILABLE:

    # ── Background workers ────────────────────────────────────────────────────

    class _LoginWorker(QThread):
        done = pyqtSignal(bool, str)

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
        done = pyqtSignal(bool, list, str)

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
            self.setMinimumWidth(480)
            self.setModal(True)
            self._fetcher = None
            self._worker = None
            self._build_ui()

        def set_fetcher(self, fetcher) -> None:
            self._fetcher = fetcher
            self._check_existing_login()

        # ── UI ────────────────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 16)
            layout.setSpacing(12)

            # Dialog title
            dlg_title = QLabel("Google Earth Engine 认证")
            dlg_title.setStyleSheet(
                "font-size: 15px; font-weight: 700; color: #1e1e1e; margin-bottom: 4px;"
            )
            layout.addWidget(dlg_title)

            # ── Step 1 card ────────────────────────────────────────────────────
            step1_card = QFrame()
            step1_card.setStyleSheet(
                "QFrame { border: 1px solid #e8e8e8; border-radius: 8px;"
                " background: #fafafa; padding: 0; }"
            )
            s1 = QVBoxLayout(step1_card)
            s1.setContentsMargins(14, 12, 14, 12)
            s1.setSpacing(8)

            s1_header = QHBoxLayout()
            step1_badge = QLabel("01")
            step1_badge.setStyleSheet(
                "background: #0067c0; color: white; font-size: 10px; font-weight: 700;"
                " border-radius: 10px; padding: 2px 7px; min-width: 0;"
            )
            step1_badge.setFixedSize(28, 20)
            step1_badge.setAlignment(Qt.AlignCenter)
            step1_title = QLabel("登录 Google 账号")
            step1_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e1e1e; border: none; background: transparent;")
            s1_header.addWidget(step1_badge)
            s1_header.addSpacing(8)
            s1_header.addWidget(step1_title)
            s1_header.addStretch()
            self._login_status = QLabel("")
            self._login_status.setStyleSheet(
                "color: #107c10; font-size: 11px; font-weight: 600; border: none; background: transparent;"
            )
            s1_header.addWidget(self._login_status)
            s1.addLayout(s1_header)

            tip = QLabel("点击按钮将在浏览器中打开 Google 授权页面，完成授权后返回此窗口。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color: #888888; font-size: 11px; border: none; background: transparent;")
            s1.addWidget(tip)

            self._login_btn = QPushButton("在浏览器中登录")
            self._login_btn.setStyleSheet(
                "QPushButton { min-height: 32px; font-size: 12px; }"
            )
            self._login_btn.clicked.connect(self._start_login)
            s1.addWidget(self._login_btn)

            layout.addWidget(step1_card)

            # ── Step 2 card ────────────────────────────────────────────────────
            self._step2_card = QFrame()
            self._step2_card.setStyleSheet(
                "QFrame { border: 1px solid #e8e8e8; border-radius: 8px;"
                " background: #fafafa; padding: 0; }"
            )
            s2 = QVBoxLayout(self._step2_card)
            s2.setContentsMargins(14, 12, 14, 12)
            s2.setSpacing(8)

            s2_header = QHBoxLayout()
            step2_badge = QLabel("02")
            step2_badge.setStyleSheet(
                "background: #0067c0; color: white; font-size: 10px; font-weight: 700;"
                " border-radius: 10px; padding: 2px 7px; min-width: 0;"
            )
            step2_badge.setFixedSize(28, 20)
            step2_badge.setAlignment(Qt.AlignCenter)
            step2_title = QLabel("选择 Cloud 项目")
            step2_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e1e1e; border: none; background: transparent;")
            s2_header.addWidget(step2_badge)
            s2_header.addSpacing(8)
            s2_header.addWidget(step2_title)
            s2_header.addStretch()
            s2.addLayout(s2_header)

            proj_row = QHBoxLayout()
            self._project_combo = QComboBox()
            self._project_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._project_combo.setPlaceholderText("加载中…")
            proj_row.addWidget(self._project_combo, stretch=1)
            self._refresh_btn = QPushButton("刷新")
            self._refresh_btn.setFixedWidth(58)
            self._refresh_btn.clicked.connect(self._load_projects)
            proj_row.addWidget(self._refresh_btn)
            s2.addLayout(proj_row)

            self._proj_hint = QLabel("")
            self._proj_hint.setWordWrap(True)
            self._proj_hint.setStyleSheet(
                "color: #aaaaaa; font-size: 10px; border: none; background: transparent;"
            )
            s2.addWidget(self._proj_hint)

            layout.addWidget(self._step2_card)
            self._step2_card.setVisible(False)

            # ── Status ─────────────────────────────────────────────────────────
            self._status_label = QLabel("")
            self._status_label.setWordWrap(True)
            self._status_label.setStyleSheet("color: #666666; font-size: 11px;")
            layout.addWidget(self._status_label)

            # ── Buttons ────────────────────────────────────────────────────────
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: #eeeeee;")
            layout.addWidget(sep)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._confirm_btn = QPushButton("完成")
            self._confirm_btn.setEnabled(False)
            self._confirm_btn.setFixedWidth(80)
            self._confirm_btn.setStyleSheet(
                "QPushButton { background: #0067c0; color: white; border: none;"
                " border-radius: 5px; font-weight: 600; min-height: 30px; }"
                "QPushButton:hover { background: #005aa8; }"
                "QPushButton:disabled { background: #cccccc; color: #ffffff; }"
            )
            self._confirm_btn.clicked.connect(self._confirm)
            btn_row.addWidget(self._confirm_btn)
            close_btn = QPushButton("关闭")
            close_btn.setFixedWidth(80)
            close_btn.clicked.connect(self.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

        # ── Logic ─────────────────────────────────────────────────────────────

        def _check_existing_login(self) -> None:
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
            self._login_btn.setText("在浏览器中登录")
            if success:
                self._mark_logged_in()
                self._load_projects()
            else:
                self._set_status(f"登录失败: {error}")

        def _mark_logged_in(self) -> None:
            self._login_status.setText("已登录")
            self._step2_card.setVisible(True)
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
                    cur = getattr(self._fetcher, "_project_id", "")
                    if cur:
                        idx = self._project_combo.findText(cur)
                        if idx >= 0:
                            self._project_combo.setCurrentIndex(idx)
                    self._confirm_btn.setEnabled(True)
                    self._set_status(f"找到 {len(projects)} 个项目，请选择后点击完成。")
                    self._proj_hint.setText(
                        "如未找到项目，请先在 console.cloud.google.com 创建并启用 Earth Engine API。"
                    )
                else:
                    self._project_combo.setPlaceholderText("（未找到项目）")
                    self._set_status("未找到可用项目，请检查 GEE 权限。")
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
                self._login_status.setText("已登录并初始化")
            else:
                self._set_status(f"初始化失败: {error}")

        def _set_status(self, msg: str) -> None:
            self._status_label.setText(msg)
