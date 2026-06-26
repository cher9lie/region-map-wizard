"""Main application window for Region Map Wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QComboBox, QPushButton, QProgressBar,
        QTextEdit, QFileDialog, QGroupBox, QFormLayout,
        QLineEdit, QMessageBox, QApplication, QStatusBar,
        QScrollArea, QSizePolicy, QFrame, QCheckBox,
    )
    from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
    from PyQt5.QtGui import QFont, QPixmap, QColor
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

from src.core.config_manager import ConfigManager
from src.core.boundary_manager import BoundaryManager
from src.core.pipeline import MapWizardPipeline
from src.renderers.base import RenderConfig
from src.constants import APP_NAME, VERSION

_DATA_DIR = Path(__file__).parent.parent / "data"

if _QT_AVAILABLE:
    class MainWindow(QMainWindow):
        """Primary UI: province/city selector, engine selector, run button,
        log panel (left), image preview (right)."""

        def __init__(self) -> None:
            super().__init__()
            self._cfg = ConfigManager()
            self._boundary_mgr = BoundaryManager()
            self._worker: Optional[object] = None
            self._custom_shp: Optional[Path] = None
            self._custom_name: str = ""
            self._last_output: Optional[str] = None
            self._pipeline = MapWizardPipeline(self._cfg)

            self.setWindowTitle(f"{APP_NAME} v{VERSION}")
            self.setMinimumSize(900, 620)
            self.resize(1100, 720)

            self._build_ui()
            self._populate_provinces()
            self._load_saved_state()

        # ── UI construction ────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)
            root = QHBoxLayout(central)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            # ── Left panel (controls) ──────────────────────────────────────────
            left = QVBoxLayout()
            left.setSpacing(6)
            root.addLayout(left, stretch=0)

            # Study area
            area_group = QGroupBox("研究区选择")
            area_form = QFormLayout(area_group)
            area_form.setSpacing(4)

            self._province_combo = QComboBox()
            self._province_combo.currentIndexChanged.connect(self._on_province_changed)
            area_form.addRow("省份:", self._province_combo)

            self._city_combo = QComboBox()
            area_form.addRow("城市/区:", self._city_combo)

            shp_row = QHBoxLayout()
            self._shp_label = QLabel("（未选择）")
            self._shp_label.setWordWrap(True)
            shp_btn = QPushButton("导入 SHP…")
            shp_btn.setFixedWidth(86)
            shp_btn.clicked.connect(self._import_shp)
            shp_row.addWidget(self._shp_label)
            shp_row.addWidget(shp_btn)
            area_form.addRow("自定义:", shp_row)
            left.addWidget(area_group)

            # Data options
            data_group = QGroupBox("数据选项")
            data_form = QFormLayout(data_group)
            data_form.setSpacing(4)

            self._data_type_combo = QComboBox()
            self._data_type_combo.addItems(["仅矢量", "DEM 高程", "山体阴影", "Sentinel-2 真彩色"])
            data_form.addRow("数据类型:", self._data_type_combo)

            self._color_ramp_combo = QComboBox()
            self._color_ramp_combo.addItems(["dem_hypsometric", "dem_green_brown"])
            data_form.addRow("色带:", self._color_ramp_combo)

            self._basemap_combo = QComboBox()
            from src.renderers.cartopy_renderer import BASEMAP_REGISTRY
            for key, meta in BASEMAP_REGISTRY.items():
                self._basemap_combo.addItem(meta["label_zh"], userData=key)
            data_form.addRow("底图:", self._basemap_combo)

            self._lang_combo = QComboBox()
            self._lang_combo.addItem("中文", userData="zh")
            self._lang_combo.addItem("English", userData="en")
            data_form.addRow("语言:", self._lang_combo)

            self._zoom_lines_chk = QCheckBox("显示区位连接线")
            self._zoom_lines_chk.setChecked(False)
            data_form.addRow("", self._zoom_lines_chk)
            left.addWidget(data_group)

            # Engine & output
            out_group = QGroupBox("渲染与输出")
            out_form = QFormLayout(out_group)
            out_form.setSpacing(4)

            self._engine_combo = QComboBox()
            self._populate_engines()
            out_form.addRow("渲染引擎:", self._engine_combo)

            self._fmt_combo = QComboBox()
            self._fmt_combo.addItems(["JPG", "PNG", "PDF"])
            out_form.addRow("格式:", self._fmt_combo)

            self._dpi_combo = QComboBox()
            self._dpi_combo.addItems(["150", "300", "600"])
            self._dpi_combo.setCurrentText("300")
            out_form.addRow("DPI:", self._dpi_combo)

            dir_row = QHBoxLayout()
            self._out_dir_edit = QLineEdit()
            self._out_dir_edit.setPlaceholderText("输出目录…")
            dir_btn = QPushButton("…")
            dir_btn.setFixedWidth(28)
            dir_btn.clicked.connect(self._pick_output_dir)
            dir_row.addWidget(self._out_dir_edit)
            dir_row.addWidget(dir_btn)
            out_form.addRow("输出目录:", dir_row)
            left.addWidget(out_group)

            # GEE auth button
            gee_btn = QPushButton("GEE 认证设置…")
            gee_btn.clicked.connect(self._open_gee_dialog)
            left.addWidget(gee_btn)

            # Log panel — below GEE auth
            log_label = QLabel("运行日志:")
            log_label.setStyleSheet("color: #555; font-size: 11px;")
            left.addWidget(log_label)

            self._log = QTextEdit()
            self._log.setReadOnly(True)
            self._log.setFont(QFont("Consolas", 8))
            self._log.setFixedHeight(110)
            self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            left.addWidget(self._log)

            left.addStretch()

            # Run / Cancel
            self._run_btn = QPushButton("一键制作")
            self._run_btn.setObjectName("runButton")
            self._run_btn.setFixedHeight(36)
            self._run_btn.clicked.connect(self._on_run_cancel)
            left.addWidget(self._run_btn)

            # ── Right panel (preview) ──────────────────────────────────────────
            right = QVBoxLayout()
            right.setSpacing(4)
            root.addLayout(right, stretch=1)

            # Progress row
            prog_row = QHBoxLayout()
            self._progress = QProgressBar()
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._progress.setFixedHeight(16)
            prog_row.addWidget(self._progress)
            self._progress_label = QLabel("就绪")
            self._progress_label.setFixedWidth(160)
            self._progress_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            prog_row.addWidget(self._progress_label)
            right.addLayout(prog_row)

            # Image preview area
            preview_frame = QFrame()
            preview_frame.setFrameShape(QFrame.StyledPanel)
            preview_frame.setStyleSheet("border:1px solid #CCCCCC; border-radius:4px;")
            preview_layout = QVBoxLayout(preview_frame)
            preview_layout.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setAlignment(Qt.AlignCenter)
            scroll.setStyleSheet("border:none; background:transparent;")

            self._preview_label = QLabel("制作完成后，地图将在此处显示")
            self._preview_label.setAlignment(Qt.AlignCenter)
            self._preview_label.setStyleSheet("color:#AAAAAA; font-size:13px;")
            self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            scroll.setWidget(self._preview_label)
            preview_layout.addWidget(scroll)
            right.addWidget(preview_frame, stretch=1)

            self.setStatusBar(QStatusBar())

        # ── Populate helpers ───────────────────────────────────────────────────

        def _populate_provinces(self) -> None:
            self._province_combo.clear()
            for p in self._boundary_mgr.list_provinces():
                self._province_combo.addItem(p["name"], userData=p["adcode"])

        def _populate_engines(self) -> None:
            """Add placeholder items immediately, then probe availability in background."""
            _ENGINES = [
                ("QGIS",           "qgis",    "src.renderers.qgis_renderer",    "QGISRenderer"),
                ("Cartopy (纯Python)", "cartopy", "src.renderers.cartopy_renderer", "CartopyRenderer"),
                ("ArcGIS Pro",     "arcgis",  "src.renderers.arcgis_renderer",  "ArcGISRenderer"),
            ]
            for label, key, _mod, _cls in _ENGINES:
                self._engine_combo.addItem(f"{label} (检测中…)", userData=key)

            # Default to Cartopy (index 1) while probing
            self._engine_combo.setCurrentIndex(1)

            # Probe each engine in a daemon thread; update the combo on completion
            def _probe():
                results = []
                for label, key, mod_name, cls_name in _ENGINES:
                    try:
                        import importlib
                        mod = importlib.import_module(mod_name)
                        cls = getattr(mod, cls_name)
                        avail, ver = cls().check_available()
                    except Exception as exc:
                        avail, ver = False, str(exc)
                    results.append((label, key, avail, ver))
                return results

            class _ProbeThread(QThread):
                done = pyqtSignal(list)
                def run(self):
                    self.done.emit(_probe())

            self._probe_thread = _ProbeThread()

            def _on_done(results):
                self._engine_combo.clear()
                preferred_idx = 1  # default to Cartopy
                for i, (label, key, avail, ver) in enumerate(results):
                    display = label if avail else f"{label} (不可用)"
                    self._engine_combo.addItem(display, userData=key)
                    if not avail:
                        self._engine_combo.model().item(i).setForeground(QColor("#999999"))
                        self.append_log(f"[引擎检测] {label} 不可用: {ver}")
                    else:
                        self.append_log(f"[引擎检测] {label} 可用: {ver}")
                    if key == "cartopy" and avail:
                        preferred_idx = i
                self._engine_combo.setCurrentIndex(preferred_idx)

            self._probe_thread.done.connect(_on_done)
            self._probe_thread.start()

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

            city_adcode = self._city_combo.currentData() or ""
            city_name = self._city_combo.currentText()
            province_adcode = self._province_combo.currentData() or ""
            province_name = self._province_combo.currentText()
            fmt = self._fmt_combo.currentText().lower()
            dpi = int(self._dpi_combo.currentText())
            engine_key = self._engine_combo.currentData() or "cartopy"
            language = self._lang_combo.currentData() or "zh"
            basemap = self._basemap_combo.currentData() or "esri_gray"

            data_map = {
                "DEM 高程": "dem", "山体阴影": "hillshade",
                "Sentinel-2 真彩色": "sentinel2", "仅矢量": "none",
            }
            data_type = data_map.get(self._data_type_combo.currentText(), "none")

            safe_name = city_name.replace("/", "_").replace("\\", "_")
            output_path = Path(out_dir) / f"{safe_name}_区位图.{fmt}"

            gpkg = _DATA_DIR / "china_admin.gpkg"
            config = RenderConfig(
                country_boundary=gpkg,
                province_boundary=gpkg,
                city_boundary=gpkg,
                province_name=province_name,
                city_name=city_name,
                province_adcode=province_adcode,
                city_adcode=city_adcode,
                raster_path=None,
                data_type=data_type,
                color_ramp=self._color_ramp_combo.currentText(),
                output_path=output_path,
                output_format=fmt,
                dpi=dpi,
                language=language,
                basemap=basemap,
                show_zoom_lines=self._zoom_lines_chk.isChecked(),
                custom_shp=self._custom_shp,
                custom_name=self._custom_name or None,
            )

            self._cfg.set("last_renderer", engine_key)
            self._cfg.set("last_output_dir", out_dir)
            self._cfg.set("last_province", province_adcode)

            from src.gui.worker import MapWorker
            self._worker = MapWorker(self._pipeline, config)
            self._worker.progress.connect(self.update_progress)
            self._worker.log.connect(self.append_log)
            self._worker.finished.connect(self.on_finished)
            self._worker.error.connect(self.on_error)

            self._run_btn.setText("取消")
            self._progress.setValue(0)
            self._preview_label.setText("正在制作，请稍候…")
            self._preview_label.setPixmap(QPixmap())
            self.append_log(f"开始制作: {city_name} ({engine_key})")
            self._worker.start()

        # ── Worker callbacks ──────────────────────────────────────────────────

        def update_progress(self, pct: int, msg: str) -> None:
            self._progress.setValue(pct)
            self._progress_label.setText(msg)

        def append_log(self, msg: str) -> None:
            self._log.append(msg)
            self._log.verticalScrollBar().setValue(
                self._log.verticalScrollBar().maximum()
            )

        def on_finished(self, output_path: str) -> None:
            self._run_btn.setText("一键制作")
            self._progress.setValue(100)
            self.append_log(f"完成: {output_path}")
            self.statusBar().showMessage(f"完成: {output_path}", 8000)
            self._show_preview(output_path)

        def on_error(self, error_msg: str) -> None:
            self._run_btn.setText("一键制作")
            self._preview_label.setText("制作失败")
            self.append_log(f"错误: {error_msg}")
            QMessageBox.critical(self, "制图失败", error_msg)

        def _show_preview(self, path: str) -> None:
            """Load and display the output image in the preview label."""
            pix = QPixmap(path)
            if pix.isNull():
                self._preview_label.setText(f"无法预览: {path}")
                return
            # Scale to fit the label while keeping aspect ratio
            avail = self._preview_label.parent().size()
            pix_scaled = pix.scaled(
                avail.width() - 10, avail.height() - 10,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._preview_label.setPixmap(pix_scaled)
            self._preview_label.setToolTip(path)
            self._last_output = path
