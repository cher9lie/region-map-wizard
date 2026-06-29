"""SHP import dialog — lets users load a custom boundary shapefile."""

from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QFileDialog, QWidget,
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
            self.setWindowTitle("导入自定义研究区")
            self.setMinimumWidth(480)
            self.setModal(True)
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
            layout.setContentsMargins(20, 20, 20, 16)
            layout.setSpacing(14)

            # Dialog title
            dlg_title = QLabel("导入自定义研究区")
            dlg_title.setStyleSheet(
                "font-size: 15px; font-weight: 700; color: #1e1e1e; margin-bottom: 2px;"
            )
            layout.addWidget(dlg_title)

            hint = QLabel("选择一个多边形 Shapefile（.shp）作为研究区边界。文件将自动验证并转换到 WGS-84 坐标系。")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888888; font-size: 11px;")
            layout.addWidget(hint)

            # File picker row
            file_lbl = QLabel("SHP 文件")
            file_lbl.setStyleSheet("color: #555555; font-size: 12px; font-weight: 600;")
            layout.addWidget(file_lbl)

            pick_row = QHBoxLayout()
            pick_row.setSpacing(8)
            self._path_edit = QLineEdit()
            self._path_edit.setPlaceholderText("点击「浏览」选择 .shp 文件…")
            self._path_edit.setReadOnly(True)
            pick_row.addWidget(self._path_edit, 1)
            browse_btn = QPushButton("浏览…")
            browse_btn.setFixedWidth(72)
            browse_btn.clicked.connect(self._browse)
            pick_row.addWidget(browse_btn)
            layout.addLayout(pick_row)

            # Validation info
            self._info_label = QLabel("")
            self._info_label.setWordWrap(True)
            self._info_label.setStyleSheet(
                "font-size: 11px; color: #555555; min-height: 18px;"
            )
            layout.addWidget(self._info_label)

            # Name field
            name_lbl = QLabel("区域名称")
            name_lbl.setStyleSheet("color: #555555; font-size: 12px; font-weight: 600;")
            layout.addWidget(name_lbl)

            self._name_edit = QLineEdit()
            self._name_edit.setPlaceholderText("例如: 洞庭湖流域、塔里木盆地")
            layout.addWidget(self._name_edit)

            # Separator
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: #eeeeee;")
            layout.addWidget(sep)

            # Buttons
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedWidth(80)
            cancel_btn.clicked.connect(self.reject)
            btn_row.addWidget(cancel_btn)

            self._ok_btn = QPushButton("确定")
            self._ok_btn.setEnabled(False)
            self._ok_btn.setFixedWidth(80)
            self._ok_btn.setStyleSheet(
                "QPushButton { background: #0067c0; color: white; border: none;"
                " border-radius: 5px; font-weight: 600; min-height: 30px; }"
                "QPushButton:hover { background: #005aa8; }"
                "QPushButton:disabled { background: #cccccc; color: #ffffff; }"
            )
            self._ok_btn.clicked.connect(self._on_ok)
            btn_row.addWidget(self._ok_btn)
            layout.addLayout(btn_row)

        def _browse(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 SHP 文件", "", "Shapefiles (*.shp)"
            )
            if not path:
                return
            self._path_edit.setText(path)
            self._validate(Path(path))

        def _validate(self, path: Path) -> None:
            self._info_label.setText("验证中…")
            self._info_label.setStyleSheet("font-size: 11px; color: #888888;")
            self._ok_btn.setEnabled(False)
            try:
                valid, msg, _ = self._boundary_mgr.validate_custom_shp(path)
            except Exception as exc:
                valid, msg = False, str(exc)

            if valid:
                self._info_label.setText(f"验证通过 — {msg}")
                self._info_label.setStyleSheet("font-size: 11px; color: #107c10;")
                self._shp_path = path
                self._ok_btn.setEnabled(True)
            else:
                self._info_label.setText(f"验证失败 — {msg}")
                self._info_label.setStyleSheet("font-size: 11px; color: #c42b1c;")

        def _on_ok(self) -> None:
            self._custom_name = self._name_edit.text().strip() or "自定义区域"
            self.accept()
