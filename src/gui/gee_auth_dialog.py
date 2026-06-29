"""GEE authentication dialog — two-step: login then enter project ID."""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton,
        QWidget,
    )
    from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
    from PyQt5.QtGui import QDesktopServices
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
        """Two-step GEE auth: ① OAuth browser login → ② enter Cloud project ID."""

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

            # ── Step 1 ─────────────────────────────────────────────────────────
            step1_card = QWidget()
            s1 = QVBoxLayout(step1_card)
            s1.setContentsMargins(0, 0, 0, 0)
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
            step1_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e1e1e;")
            s1_header.addWidget(step1_badge)
            s1_header.addSpacing(8)
            s1_header.addWidget(step1_title)
            s1_header.addStretch()
            self._login_status = QLabel("")
            self._login_status.setStyleSheet(
                "color: #107c10; font-size: 11px; font-weight: 600;"
            )
            s1_header.addWidget(self._login_status)
            s1.addLayout(s1_header)

            tip = QLabel("点击按钮将在浏览器中打开 Google 授权页面，完成授权后返回此窗口。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color: #888888; font-size: 11px;")
            s1.addWidget(tip)

            self._login_btn = QPushButton("在浏览器中登录")
            self._login_btn.setStyleSheet(
                "QPushButton { min-height: 32px; font-size: 12px; }"
            )
            self._login_btn.clicked.connect(self._start_login)
            s1.addWidget(self._login_btn)

            layout.addWidget(step1_card)

            # ── Separator ──────────────────────────────────────────────────────
            sep1 = QWidget()
            sep1.setFixedHeight(1)
            sep1.setStyleSheet("background: #eeeeee;")
            layout.addWidget(sep1)

            # ── Step 2 ─────────────────────────────────────────────────────────
            self._step2_card = QWidget()
            s2 = QVBoxLayout(self._step2_card)
            s2.setContentsMargins(0, 0, 0, 0)
            s2.setSpacing(8)

            s2_header = QHBoxLayout()
            step2_badge = QLabel("02")
            step2_badge.setStyleSheet(
                "background: #0067c0; color: white; font-size: 10px; font-weight: 700;"
                " border-radius: 10px; padding: 2px 7px; min-width: 0;"
            )
            step2_badge.setFixedSize(28, 20)
            step2_badge.setAlignment(Qt.AlignCenter)
            step2_title = QLabel("输入 Cloud 项目 ID")
            step2_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e1e1e;")
            s2_header.addWidget(step2_badge)
            s2_header.addSpacing(8)
            s2_header.addWidget(step2_title)
            s2_header.addStretch()
            s2.addLayout(s2_header)

            hint = QLabel(
                "在 Google Cloud Console 顶部点击项目选择器，即可看到项目 ID（非项目名称）。"
                "格式示例：<b>my-project-123456</b>"
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888888; font-size: 11px;")
            s2.addWidget(hint)

            proj_row = QHBoxLayout()
            self._project_input = QLineEdit()
            self._project_input.setPlaceholderText("输入项目 ID，例如 my-project-123456")
            self._project_input.setStyleSheet(
                "QLineEdit { border: 1px solid #cccccc; border-radius: 4px;"
                " padding: 4px 8px; font-size: 12px; min-height: 32px; }"
                "QLineEdit:focus { border-color: #0067c0; }"
            )
            self._project_input.textChanged.connect(self._on_project_input_changed)
            proj_row.addWidget(self._project_input, stretch=1)

            console_btn = QPushButton("打开控制台")
            console_btn.setFixedWidth(88)
            console_btn.setStyleSheet("QPushButton { min-height: 32px; }")
            console_btn.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl("https://console.cloud.google.com"))
            )
            proj_row.addWidget(console_btn)
            s2.addLayout(proj_row)

            layout.addWidget(self._step2_card)
            self._step2_card.setVisible(False)

            # ── Status ─────────────────────────────────────────────────────────
            self._status_label = QLabel("")
            self._status_label.setWordWrap(True)
            self._status_label.setStyleSheet("color: #666666; font-size: 11px;")
            layout.addWidget(self._status_label)

            # ── Buttons ────────────────────────────────────────────────────────
            sep2 = QWidget()
            sep2.setFixedHeight(1)
            sep2.setStyleSheet("background: #eeeeee;")
            layout.addWidget(sep2)

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
                # Pre-fill with previously used project if any
                cur = getattr(self._fetcher, "_project_id", "")
                if cur:
                    self._project_input.setText(cur)
            self._login_btn.setEnabled(True)
            self._login_btn.setText("在浏览器中登录")

        def _on_project_input_changed(self, text: str) -> None:
            self._confirm_btn.setEnabled(bool(text.strip()))

        def _start_login(self) -> None:
            if self._fetcher is None:
                self._set_status("错误：GEE Fetcher 未初始化")
                return
            self._login_btn.setEnabled(False)
            self._login_btn.setText("等待浏览器授权…")
            self._set_status(
                "浏览器授权页面已在后台打开，请切换到浏览器完成登录后返回此窗口。"
                "（若未弹出请检查任务栏）"
            )
            self._worker = _LoginWorker(self._fetcher)
            self._worker.done.connect(self._on_login_done)
            self._worker.start()

        def _on_login_done(self, success: bool, error: str) -> None:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("在浏览器中登录")
            if success:
                self._mark_logged_in()
            else:
                self._set_status(f"登录失败: {error}")

        def _mark_logged_in(self) -> None:
            self._login_status.setText("已登录")
            self._step2_card.setVisible(True)
            self._set_status("登录成功，请在下方输入您的 Cloud 项目 ID 后点击完成。")
            self.adjustSize()

        def _confirm(self) -> None:
            project_id = self._project_input.text().strip()
            if not project_id:
                self._set_status("请先输入项目 ID")
                return
            self._confirm_btn.setEnabled(False)
            self._set_status(f"正在连接项目 {project_id}…")
            self._worker = _InitWorker(self._fetcher, project_id)
            self._worker.done.connect(self._on_init_done)
            self._worker.start()

        def _on_init_done(self, success: bool, error: str) -> None:
            self._confirm_btn.setEnabled(True)
            if success:
                project_id = self._project_input.text().strip()
                self._set_status(f"认证成功！当前项目: {project_id}")
                self._login_status.setText("已登录并初始化")
            else:
                self._set_status(f"初始化失败: {error}\n请检查项目 ID 是否正确，以及该项目是否已启用 Earth Engine API。")

        def _set_status(self, msg: str) -> None:
            self._status_label.setText(msg)
