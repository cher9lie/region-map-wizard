"""Main application window for Region Map Wizard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QComboBox, QPushButton, QProgressBar,
        QTextEdit, QFileDialog, QGroupBox, QFormLayout,
        QLineEdit, QMessageBox, QSizePolicy, QApplication,
        QStatusBar,
    )
    from PyQt5.QtCore import Qt, QThread
    from PyQt5.QtGui import QFont, QIcon
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

from src.core.config_manager import ConfigManager
from src.core.boundary_manager import BoundaryManager
from src.core.gee_fetcher import GEEFetcher
from src.core.pipeline import MapWizardPipeline
from src.renderers.base import RenderConfig
from src.constants import APP_NAME, VERSION, DEFAULT_CACHE_DIR_NAME
from src.core.cache_manager import CacheManager

_DATA_DIR = Path(__file__).parent.parent / "data"

if _QT_AVAILABLE:
    class MainWindow(QMainWindow):
        """Primary UI: province/city selector, engine selector, run button, log panel."""

        def __init__(self) -> None:
            super().__init__()
            self._cfg = ConfigManager()
            self._boundary_mgr = BoundaryManager()
            self._worker: Optional[object] = None
            self._custom_shp: Optional[Path] = None
            self._custom_name: str = ""

            self._pipeline = MapWizardPipeline(self._cfg)

            self.setWindowTitle(f"{APP_NAME} v{VERSION}")
            self.setMinimumSize(720, 580)
            self.resize(860, 680)

            self._build_ui()
            self._populate_provinces()
            self._load_saved_state()

        # ── UI construction ────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)
            root = QHBoxLayout(central)
            root.setContentsMargins(8, 8, 8, 8)

            # ── Left panel ────────────────────────────────────────────────────
            left = QVBoxLayout()
            left.setSpacing(6)
            root.addLayout(left, stretch=0)

            # Study area group
            area_group = QGroupBox("研究区选择")
            area_form = QFormLayout(area_group)

            self._province_combo = QComboBox()
            self._province_combo.currentIndexChanged.connect(self._on_province_changed)
            area_form.addRow("省份:", self._province_combo)

            self._city_combo = QComboBox()
            area_form.addRow("城市:", self._city_combo)

            shp_row = QHBoxLayout()
            self._shp_label = QLabel("（未选择）")
            self._shp_label.setWordWrap(True)
            shp_btn = QPushButton("导入 SHP…")
            shp_btn.setFixedWidth(90)
            shp_btn.clicked.connect(self._import_shp)
            shp_row.addWidget(self._shp_label)
            shp_row.addWidget(shp_btn)
            area_form.addRow("自定义:", shp_row)

            left.addWidget(area_group)

            # Data options
            data_group = QGroupBox("数据选项")
            data_form = QFormLayout(data_group)

            self._data_type_combo = QComboBox()
            self._data_type_combo.addItems(["DEM 高程", "山体阴影", "Sentinel-2 真彩色", "仅矢量"])
            data_form.addRow("数据类型:", self._data_type_combo)

            self._color_ramp_combo = QComboBox()
            self._color_ramp_combo.addItems(["dem_hypsometric", "dem_green_brown"])
            data_form.addRow("色带:", self._color_ramp_combo)

            left.addWidget(data_group)

            # Engine & output
            out_group = QGroupBox("渲染与输出")
            out_form = QFormLayout(out_group)

            self._engine_combo = QComboBox()
            self._populate_engines()
            out_form.addRow("渲染引擎:", self._engine_combo)

            fmt_combo = QComboBox()
            fmt_combo.addItems(["JPG", "PNG", "PDF"])
            self._fmt_combo = fmt_combo
            out_form.addRow("输出格式:", fmt_combo)

            dpi_combo = QComboBox()
            dpi_combo.addItems(["150", "300", "600"])
            dpi_combo.setCurrentText("300")
            self._dpi_combo = dpi_combo
            out_form.addRow("DPI:", dpi_combo)

            dir_row = QHBoxLayout()
            self._out_dir_edit = QLineEdit()
            self._out_dir_edit.setPlaceholderText("输出目录…")
            dir_btn = QPushButton("…")
            dir_btn.setFixedWidth(30)
            dir_btn.clicked.connect(self._pick_output_dir)
            dir_row.addWidget(self._out_dir_edit)
            dir_row.addWidget(dir_btn)
            out_form.addRow("输出目录:", dir_row)

            left.addWidget(out_group)

            # GEE auth button
            gee_btn = QPushButton("GEE 认证设置…")
            gee_btn.clicked.connect(self._open_gee_dialog)
            left.addWidget(gee_btn)

            left.addStretch()

            # Run / Cancel
            self._run_btn = QPushButton("一键制作")
            self._run_btn.setObjectName("runButton")
            self._run_btn.setFixedHeight(36)
            self._run_btn.clicked.connect(self._on_run_cancel)
            left.addWidget(self._run_btn)

            # ── Right panel ───────────────────────────────────────────────────
            right = QVBoxLayout()
            root.addLayout(right, stretch=1)

            # Progress bar
            self._progress = QProgressBar()
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            right.addWidget(self._progress)

            self._progress_label = QLabel("就绪")
            right.addWidget(self._progress_label)

            # Log panel
            self._log = QTextEdit()
            self._log.setReadOnly(True)
            self._log.setFont(QFont("Consolas", 9))
            right.addWidget(self._log)

            # Status bar
            self.setStatusBar(QStatusBar())

        # ── Populate helpers ───────────────────────────────────────────────────

        def _populate_provinces(self) -> None:
            self._province_combo.clear()
            for p in self._boundary_mgr.list_provinces():
                self._province_combo.addItem(p["name"], userData=p["adcode"])

        def _populate_engines(self) -> None:
            engines = [
                ("QGIS", "qgis"),
                ("Cartopy (纯Python)", "cartopy"),
                ("ArcGIS Pro", "arcgis"),
            ]
            from src.renderers.qgis_renderer import QGISRenderer
            from src.renderers.cartopy_renderer import CartopyRenderer
            from src.renderers.arcgis_renderer import ArcGISRenderer
            renderers = {
                "qgis": QGISRenderer(),
                "cartopy": CartopyRenderer(),
                "arcgis": ArcGISRenderer(),
            }
            for label, key in engines:
                avail, reason = renderers[key].check_available()
                display = label if avail else f"{label} (不可用)"
                self._engine_combo.addItem(display, userData=key)
                idx = self._engine_combo.count() - 1
                if not avail:
                    # Grey out but keep selectable so user sees the reason
                    item = self._engine_combo.model().item(idx)
                    from PyQt5.QtGui import QColor
                    item.setForeground(QColor("#999999"))

        def _load_saved_state(self) -> None:
            last_prov = self._cfg.get("last_province", "110000")
            for i in range(self._province_combo.count()):
                if self._province_combo.itemData(i) == last_prov:
                    self._province_combo.setCurrentIndex(i)
                    break
            saved_dir = self._cfg.get("last_output_dir", "")
            if saved_dir:
                self._out_dir_edit.setText(saved_dir)

        # ── Slots ─────────────────────────────────────────────────────────────

        def _on_province_changed(self, _: int) -> None:
            adcode = self._province_combo.currentData()
            self._city_combo.clear()
            if adcode:
                try:
                    for city in self._boundary_mgr.list_cities(adcode):
                        self._city_combo.addItem(city["name"], userData=city["adcode"])
                except Exception:
                    pass

        def _pick_output_dir(self) -> None:
            d = QFileDialog.getExistingDirectory(self, "选择输出目录")
            if d:
                self._out_dir_edit.setText(d)

        def _import_shp(self) -> None:
            from src.gui.shp_import_dialog import SHPImportDialog
            dlg = SHPImportDialog(self._boundary_mgr, self)
            if dlg.exec_():
                self._custom_shp = dlg.shp_path
                self._custom_name = dlg.custom_name
                self._shp_label.setText(str(dlg.shp_path.name) if dlg.shp_path else "（未选择）")

        def _open_gee_dialog(self) -> None:
            from src.gui.gee_auth_dialog import GEEAuthDialog
            dlg = GEEAuthDialog(self)
            dlg.set_fetcher(self._pipeline.gee_fetcher)
            dlg.exec_()

        def _on_run_cancel(self) -> None:
            if self._worker and getattr(self._worker, "isRunning", lambda: False)():
                self._worker.cancel()
                self._run_btn.setText("一键制作")
                self.append_log("已取消")
                return
            self._start_render()

        def _start_render(self) -> None:
            out_dir = self._out_dir_edit.text().strip()
            if not out_dir:
                QMessageBox.warning(self, "提示", "请先选择输出目录")
                return

            city_name = self._city_combo.currentText()
            province_name = self._province_combo.currentText()
            fmt = self._fmt_combo.currentText().lower()
            dpi = int(self._dpi_combo.currentText())
            engine_key = self._engine_combo.currentData() or "cartopy"

            data_map = {
                "DEM 高程": "dem",
                "山体阴影": "hillshade",
                "Sentinel-2 真彩色": "sentinel2",
                "仅矢量": "none",
            }
            data_type = data_map.get(self._data_type_combo.currentText(), "dem")

            output_path = Path(out_dir) / f"{city_name}_区位图.{fmt}"

            config = RenderConfig(
                country_boundary=_DATA_DIR / "china_admin.gpkg",
                province_boundary=_DATA_DIR / "china_admin.gpkg",
                city_boundary=_DATA_DIR / "china_admin.gpkg",
                province_name=province_name,
                city_name=city_name,
                raster_path=None,
                data_type=data_type,
                color_ramp=self._color_ramp_combo.currentText(),
                output_path=output_path,
                output_format=fmt,
                dpi=dpi,
                custom_shp=self._custom_shp,
                custom_name=self._custom_name or None,
            )

            self._cfg.set("last_renderer", engine_key)
            self._cfg.set("last_output_dir", out_dir)

            from src.gui.worker import MapWorker
            self._worker = MapWorker(self._pipeline, config)
            self._worker.progress.connect(self.update_progress)
            self._worker.log.connect(self.append_log)
            self._worker.finished.connect(self.on_finished)
            self._worker.error.connect(self.on_error)

            self._run_btn.setText("取消")
            self._progress.setValue(0)
            self.append_log(f"开始制作: {city_name} ({engine_key})")
            self._worker.start()

        # ── Worker callbacks ──────────────────────────────────────────────────

        def update_progress(self, pct: int, msg: str) -> None:
            self._progress.setValue(pct)
            self._progress_label.setText(msg)

        def append_log(self, msg: str) -> None:
            self._log.append(msg)
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())

        def on_finished(self, output_path: str) -> None:
            self._run_btn.setText("一键制作")
            self._progress.setValue(100)
            self.append_log(f"✓ 输出完成: {output_path}")
            self.statusBar().showMessage(f"完成: {output_path}", 5000)

        def on_error(self, error_msg: str) -> None:
            self._run_btn.setText("一键制作")
            self.append_log(f"✗ 错误: {error_msg}")
            QMessageBox.critical(self, "制图失败", error_msg)
