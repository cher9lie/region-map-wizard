"""GEE authentication dialog."""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QTextEdit,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

if _QT_AVAILABLE:
    class _AuthWorker(QThread):
        done = pyqtSignal(bool, str)

        def __init__(self, fetcher):
            super().__init__()
            self._fetcher = fetcher

        def run(self):
            try:
                self._fetcher.authenticate()
                self.done.emit(True, "认证成功！")
            except Exception as exc:
                self.done.emit(False, str(exc))

    class GEEAuthDialog(QDialog):
        """Dialog that authenticates the user with Google Earth Engine."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Google Earth Engine 认证")
            self.setMinimumWidth(420)
            self._fetcher = None
            self._worker = None
            self._build_ui()

        def set_fetcher(self, fetcher) -> None:
            self._fetcher = fetcher

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)

            layout.addWidget(QLabel("Cloud Project ID:"))
            self._project_edit = QLineEdit()
            self._project_edit.setPlaceholderText("例如: my-gee-project-12345")
            layout.addWidget(self._project_edit)

            self._auth_btn = QPushButton("开始认证（会弹出浏览器）")
            self._auth_btn.clicked.connect(self._start_auth)
            layout.addWidget(self._auth_btn)

            layout.addWidget(QLabel("状态:"))
            self._status = QTextEdit()
            self._status.setReadOnly(True)
            self._status.setFixedHeight(80)
            layout.addWidget(self._status)

            btns = QHBoxLayout()
            self._close_btn = QPushButton("关闭")
            self._close_btn.clicked.connect(self.accept)
            btns.addStretch()
            btns.addWidget(self._close_btn)
            layout.addLayout(btns)

        def _start_auth(self) -> None:
            if self._fetcher is None:
                self._status.append("错误：未设置 GEE Fetcher")
                return
            project_id = self._project_edit.text().strip()
            if not project_id:
                self._status.append("请输入 Cloud Project ID")
                return
            self._fetcher._project_id = project_id
            self._auth_btn.setEnabled(False)
            self._status.append("正在认证，请在浏览器中完成授权…")
            self._worker = _AuthWorker(self._fetcher)
            self._worker.done.connect(self._on_auth_done)
            self._worker.start()

        def _on_auth_done(self, success: bool, msg: str) -> None:
            self._status.append(msg)
            self._auth_btn.setEnabled(True)
