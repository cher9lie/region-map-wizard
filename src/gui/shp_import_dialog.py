"""SHP import dialog — lets users load a custom boundary shapefile."""

from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QFileDialog,
    )
    from PyQt5.QtCore import Qt
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

if _QT_AVAILABLE:
    class SHPImportDialog(QDialog):
        """Dialog to import a custom SHP study-area boundary."""

        def __init__(self, boundary_manager, parent=None):
            super().__init__(parent)
            self.setWindowTitle("导入自定义研究区 SHP")
            self.setMinimumWidth(460)
            self._boundary_mgr = boundary_manager
            self._shp_path: Path | None = None
            self._custom_name: str = ""
            self._build_ui()

        @property
        def shp_path(self) -> Path | None:
            return self._shp_path

        @property
        def custom_name(self) -> str:
            return self._custom_name

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)

            # File picker
            row = QHBoxLayout()
            self._path_edit = QLineEdit()
            self._path_edit.setPlaceholderText("选择 .shp 文件…")
            self._path_edit.setReadOnly(True)
            browse_btn = QPushButton("浏览…")
            browse_btn.clicked.connect(self._browse)
            row.addWidget(self._path_edit)
            row.addWidget(browse_btn)
            layout.addLayout(row)

            layout.addWidget(QLabel("区域名称:"))
            self._name_edit = QLineEdit()
            self._name_edit.setPlaceholderText("例如: 洞庭湖流域")
            layout.addWidget(self._name_edit)

            self._info_label = QLabel("")
            self._info_label.setWordWrap(True)
            layout.addWidget(self._info_label)

            btns = QHBoxLayout()
            self._ok_btn = QPushButton("确定")
            self._ok_btn.setEnabled(False)
            self._ok_btn.clicked.connect(self._on_ok)
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self.reject)
            btns.addStretch()
            btns.addWidget(cancel_btn)
            btns.addWidget(self._ok_btn)
            layout.addLayout(btns)

        def _browse(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 SHP 文件", "", "Shapefiles (*.shp)"
            )
            if not path:
                return
            self._path_edit.setText(path)
            self._validate(Path(path))

        def _validate(self, path: Path) -> None:
            try:
                valid, msg, _ = self._boundary_mgr.validate_custom_shp(path)
            except Exception as exc:
                valid, msg = False, str(exc)
            self._info_label.setText(msg)
            self._ok_btn.setEnabled(valid)
            if valid:
                self._shp_path = path

        def _on_ok(self) -> None:
            self._custom_name = self._name_edit.text().strip() or "自定义区域"
            self.accept()
