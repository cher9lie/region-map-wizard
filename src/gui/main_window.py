"""Main application window for Region Map Wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QComboBox, QPushButton, QProgressBar,
        QTextEdit, QFileDialog,
        QLineEdit, QMessageBox, QApplication, QStatusBar,
        QScrollArea, QSizePolicy, QFrame, QCheckBox,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QPixmap, QColor
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

from src.core.config_manager import ConfigManager
from src.core.boundary_manager import BoundaryManager
from src.core.pipeline import MapWizardPipeline
from src.renderers.base import RenderConfig
from src.constants import APP_NAME, VERSION

_DATA_DIR = Path(__file__).parent.parent / "data"

# ── Stylesheet ─────────────────────────────────────────────────────────────────
_STYLE = """
/* ── Base ─────────────────────────────────────────────────────────────────── */
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
    font-size: 12px;
    color: #18181B;
    outline: none;
}
QMainWindow { background: #F4F4F5; }

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
QWidget#sidebar {
    background: #FAFAFA;
    border-right: 1px solid #E4E4E7;
}

/* App branding */
QLabel#appTitle {
    font-size: 13px;
    font-weight: 700;
    color: #09090B;
    letter-spacing: -0.3px;
}
QLabel#appSubtitle {
    font-size: 11px;
    color: #A1A1AA;
}

/* Section header — pure typography, no box */
QLabel#sectionLabel {
    font-size: 10px;
    font-weight: 600;
    color: #A1A1AA;
    letter-spacing: 1px;
    padding-top: 20px;
    padding-bottom: 6px;
}

/* Label above a field — small, muted */
QLabel#fieldLabel {
    font-size: 11px;
    color: #71717A;
    padding-bottom: 2px;
}

/* SHP filename display — mimics a disabled input */
QLabel#shpLabel {
    color: #A1A1AA;
    font-size: 11px;
    padding: 5px 10px;
    background: #F4F4F5;
    border-radius: 6px;
    min-height: 28px;
}

/* ── Inputs — filled, no visible border ───────────────────────────────────── */
QComboBox, QLineEdit {
    border: 1.5px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
    background: #F4F4F5;
    color: #09090B;
    font-size: 12px;
    min-height: 28px;
    selection-background-color: #DBEAFE;
}
QComboBox:hover {
    background: #E4E4E7;
}
QLineEdit:hover {
    background: #E4E4E7;
}
QComboBox:focus, QLineEdit:focus {
    background: #FFFFFF;
    border-color: #A5B4FC;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QComboBox QAbstractItemView {
    border: 1px solid #E4E4E7;
    border-radius: 6px;
    background: #FFFFFF;
    selection-background-color: #EEF2FF;
    selection-color: #3730A3;
    padding: 2px 0;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 0 10px;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
QPushButton {
    border: 1.5px solid #E4E4E7;
    border-radius: 6px;
    padding: 4px 12px;
    background: #FFFFFF;
    color: #3F3F46;
    font-size: 12px;
    min-height: 28px;
}
QPushButton:hover {
    background: #FAFAFA;
    border-color: #A1A1AA;
    color: #18181B;
}
QPushButton:pressed {
    background: #F4F4F5;
    border-color: #71717A;
}
QPushButton:disabled {
    color: #D4D4D8;
    background: #FAFAFA;
    border-color: #F4F4F5;
}

/* Primary action button */
QPushButton#runButton {
    background: #09090B;
    color: #FAFAFA;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    min-height: 44px;
    letter-spacing: 0.1px;
}
QPushButton#runButton:hover {
    background: #27272A;
    color: #FAFAFA;
    border: none;
}
QPushButton#runButton:pressed {
    background: #3F3F46;
    color: #FAFAFA;
    border: none;
}
QPushButton#runButton:disabled {
    background: #D4D4D8;
    color: #FAFAFA;
    border: none;
}

/* Small compact buttons */
QPushButton#smallBtn {
    font-size: 11px;
    min-height: 28px;
    padding: 3px 10px;
    border-radius: 5px;
    color: #52525B;
}
QPushButton#smallBtn:hover {
    color: #18181B;
}

/* GEE settings button — ghost */
QPushButton#geeBtn {
    background: transparent;
    border: 1.5px solid #E4E4E7;
    color: #71717A;
    font-size: 11px;
    min-height: 32px;
    border-radius: 6px;
}
QPushButton#geeBtn:hover {
    background: #F4F4F5;
    border-color: #A1A1AA;
    color: #3F3F46;
}

/* ── Checkbox ─────────────────────────────────────────────────────────────── */
QCheckBox {
    color: #52525B;
    font-size: 12px;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1.5px solid #D4D4D8;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:hover { border-color: #71717A; }
QCheckBox::indicator:checked {
    background: #09090B;
    border-color: #09090B;
}

/* ── Progress bar ─────────────────────────────────────────────────────────── */
QProgressBar {
    border: none;
    border-radius: 2px;
    background: #E4E4E7;
    max-height: 3px;
    font-size: 0px;
}
QProgressBar::chunk {
    background: #09090B;
    border-radius: 2px;
}

/* ── Log panel ────────────────────────────────────────────────────────────── */
QTextEdit#logPanel {
    border: none;
    border-radius: 6px;
    background: #F4F4F5;
    color: #71717A;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 6px 10px;
    selection-background-color: #DBEAFE;
}

/* ── Preview card ─────────────────────────────────────────────────────────── */
QFrame#previewCard {
    background: #FFFFFF;
    border: 1px solid #E4E4E7;
    border-radius: 8px;
}

/* ── Content area ─────────────────────────────────────────────────────────── */
QWidget#content { background: #F4F4F5; }

/* ── Scrollbars ───────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    border: none; background: transparent; width: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #D4D4D8; border-radius: 2px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #A1A1AA; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal {
    border: none; background: transparent; height: 4px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #D4D4D8; border-radius: 2px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #A1A1AA; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ── Status bar ───────────────────────────────────────────────────────────── */
QStatusBar {
    background: #F4F4F5;
    border-top: 1px solid #E4E4E7;
    font-size: 11px;
    color: #A1A1AA;
    padding: 0 8px;
}
QStatusBar::item { border: none; }

/* ── Dialogs ──────────────────────────────────────────────────────────────── */
QDialog { background: #FFFFFF; }
QDialog QFrame { border: none; background: transparent; }
QDialog QLabel { font-size: 12px; color: #3F3F46; }
QMessageBox { background: #FFFFFF; }
QMessageBox QPushButton { min-width: 72px; }
"""


if _QT_AVAILABLE:
    class MainWindow(QMainWindow):
        """Primary UI — province/city selector, engine, run button, preview."""

        def __init__(self) -> None:
            super().__init__()
            self._cfg = ConfigManager()
            self._boundary_mgr = BoundaryManager()
            self._worker: Optional[object] = None
            self._custom_shp: Optional[Path] = None
            self._custom_name: str = ""
            self._last_output: Optional[str] = None
            self._pipeline = MapWizardPipeline(self._cfg)

            self.setWindowTitle(f"{APP_NAME}  v{VERSION}")
            self.setMinimumSize(960, 620)
            self.resize(1180, 760)

            app = QApplication.instance()
            if app:
                app.setStyleSheet(_STYLE)

            self._build_ui()
            self._populate_provinces()
            self._load_saved_state()

        # ── Layout helpers ─────────────────────────────────────────────────────

        @staticmethod
        def _sec(text: str) -> "QLabel":
            """Uppercase section header — no box, pure typography."""
            lbl = QLabel(text.upper())
            lbl.setObjectName("sectionLabel")
            return lbl

        @staticmethod
        def _lbl(text: str) -> "QLabel":
            """Small field label that sits above an input."""
            lbl = QLabel(text)
            lbl.setObjectName("fieldLabel")
            return lbl

        @staticmethod
        def _hbox(*widgets, spacing: int = 8) -> "QWidget":
            """Return a QWidget containing widgets in a horizontal row."""
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(spacing)
            for item in widgets:
                if isinstance(item, int):
                    lay.addSpacing(item)
                elif item == "stretch":
                    lay.addStretch()
                else:
                    lay.addWidget(item)
            return w

        # ── UI construction ────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            central = QWidget()
            central.setObjectName("central")
            self.setCentralWidget(central)

            root = QHBoxLayout(central)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            # ── SIDEBAR ────────────────────────────────────────────────────────
            sidebar_content = QWidget()
            sidebar_content.setObjectName("sidebar")
            sb = QVBoxLayout(sidebar_content)
            sb.setContentsMargins(18, 22, 18, 16)
            sb.setSpacing(0)

            # Branding
            title_lbl = QLabel("Region Map Wizard")
            title_lbl.setObjectName("appTitle")
            sub_lbl = QLabel("研究区区位图自动制图工具")
            sub_lbl.setObjectName("appSubtitle")
            sb.addWidget(title_lbl)
            sb.addSpacing(3)
            sb.addWidget(sub_lbl)

            # ── STUDY AREA ─────────────────────────────────────────────────────
            sb.addWidget(self._sec("研究区"))

            sb.addWidget(self._lbl("省份"))
            self._province_combo = QComboBox()
            self._province_combo.currentIndexChanged.connect(self._on_province_changed)
            sb.addWidget(self._province_combo)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("城市"))
            self._city_combo = QComboBox()
            sb.addWidget(self._city_combo)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("自定义 SHP"))
            self._shp_label = QLabel("未选择")
            self._shp_label.setObjectName("shpLabel")
            shp_import_btn = QPushButton("导入")
            shp_import_btn.setObjectName("smallBtn")
            shp_import_btn.setFixedWidth(48)
            shp_import_btn.clicked.connect(self._import_shp)
            self._shp_clear_btn = QPushButton("×")
            self._shp_clear_btn.setObjectName("smallBtn")
            self._shp_clear_btn.setFixedWidth(28)
            self._shp_clear_btn.setVisible(False)
            self._shp_clear_btn.clicked.connect(self._clear_shp)
            sb.addWidget(self._hbox(
                self._shp_label, shp_import_btn, self._shp_clear_btn,
                spacing=6,
            ))

            # ── DATA OPTIONS ───────────────────────────────────────────────────
            sb.addWidget(self._sec("数据选项"))

            sb.addWidget(self._lbl("数据类型"))
            self._data_type_combo = QComboBox()
            self._data_type_combo.addItems(["仅矢量", "DEM 高程", "山体阴影", "Sentinel-2 真彩色"])
            sb.addWidget(self._data_type_combo)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("色带"))
            self._color_ramp_combo = QComboBox()
            self._color_ramp_combo.addItems(["dem_hypsometric", "dem_green_brown"])
            sb.addWidget(self._color_ramp_combo)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("底图"))
            self._basemap_combo = QComboBox()
            from src.renderers.cartopy_renderer import BASEMAP_REGISTRY
            for key, meta in BASEMAP_REGISTRY.items():
                self._basemap_combo.addItem(meta["label_zh"], userData=key)
            sb.addWidget(self._basemap_combo)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("语言"))
            self._lang_combo = QComboBox()
            self._lang_combo.addItem("中文", userData="zh")
            self._lang_combo.addItem("English", userData="en")
            sb.addWidget(self._lang_combo)

            sb.addSpacing(10)
            self._zoom_lines_chk = QCheckBox("显示区位连接线")
            self._zoom_lines_chk.setChecked(False)
            sb.addWidget(self._zoom_lines_chk)

            # ── RENDER & OUTPUT ────────────────────────────────────────────────
            sb.addWidget(self._sec("渲染与输出"))

            sb.addWidget(self._lbl("引擎"))
            self._engine_combo = QComboBox()
            self._populate_engines()
            sb.addWidget(self._engine_combo)

            # Format + DPI — two equal columns
            sb.addSpacing(10)
            fmt_col = QVBoxLayout()
            fmt_col.setSpacing(3)
            fmt_col.setContentsMargins(0, 0, 0, 0)
            fmt_col.addWidget(self._lbl("格式"))
            self._fmt_combo = QComboBox()
            self._fmt_combo.addItems(["JPG", "PNG", "PDF"])
            fmt_col.addWidget(self._fmt_combo)

            dpi_col = QVBoxLayout()
            dpi_col.setSpacing(3)
            dpi_col.setContentsMargins(0, 0, 0, 0)
            dpi_col.addWidget(self._lbl("DPI"))
            self._dpi_combo = QComboBox()
            self._dpi_combo.addItems(["150", "300", "600"])
            self._dpi_combo.setCurrentText("300")
            dpi_col.addWidget(self._dpi_combo)

            fmt_dpi_w = QWidget()
            fmt_dpi_lay = QHBoxLayout(fmt_dpi_w)
            fmt_dpi_lay.setContentsMargins(0, 0, 0, 0)
            fmt_dpi_lay.setSpacing(10)
            fmt_dpi_lay.addLayout(fmt_col)
            fmt_dpi_lay.addLayout(dpi_col)
            sb.addWidget(fmt_dpi_w)

            sb.addSpacing(10)
            sb.addWidget(self._lbl("输出目录"))
            self._out_dir_edit = QLineEdit()
            self._out_dir_edit.setPlaceholderText("选择目录…")
            dir_btn = QPushButton("…")
            dir_btn.setObjectName("smallBtn")
            dir_btn.setFixedWidth(36)
            dir_btn.clicked.connect(self._pick_output_dir)
            sb.addWidget(self._hbox(self._out_dir_edit, dir_btn, spacing=6))

            # ── CACHE ──────────────────────────────────────────────────────────
            sb.addWidget(self._sec("缓存"))

            sb.addWidget(self._lbl("缓存目录"))
            saved_cache = self._cfg.get("cache_dir", "")
            self._cache_dir_edit = QLineEdit(saved_cache or str(Path.home() / ".rmw_cache"))
            self._cache_dir_edit.setReadOnly(True)
            cache_dir_btn = QPushButton("…")
            cache_dir_btn.setObjectName("smallBtn")
            cache_dir_btn.setFixedWidth(36)
            cache_dir_btn.clicked.connect(self._pick_cache_dir)
            sb.addWidget(self._hbox(self._cache_dir_edit, cache_dir_btn, spacing=6))

            sb.addSpacing(6)
            self._cache_size_label = QLabel(self._get_cache_size_str())
            self._cache_size_label.setStyleSheet("color: #A1A1AA; font-size: 11px;")
            clear_cache_btn = QPushButton("立即清除缓存")
            clear_cache_btn.setObjectName("smallBtn")
            clear_cache_btn.clicked.connect(self._clear_cache_now)
            sb.addWidget(self._hbox(self._cache_size_label, "stretch", clear_cache_btn, spacing=6))

            sb.addStretch(1)

            # GEE auth
            gee_btn = QPushButton("GEE 认证设置…")
            gee_btn.setObjectName("geeBtn")
            gee_btn.clicked.connect(self._open_gee_dialog)
            sb.addWidget(gee_btn)
            sb.addSpacing(8)

            # Primary run button
            self._run_btn = QPushButton("开始制图")
            self._run_btn.setObjectName("runButton")
            self._run_btn.clicked.connect(self._on_run_cancel)
            sb.addWidget(self._run_btn)

            sidebar_scroll = QScrollArea()
            sidebar_scroll.setFixedWidth(296)
            sidebar_scroll.setWidget(sidebar_content)
            sidebar_scroll.setWidgetResizable(True)
            sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            sidebar_scroll.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }"
            )
            root.addWidget(sidebar_scroll)

            # ── CONTENT AREA ────────────────────────────────────────────────────
            content = QWidget()
            content.setObjectName("content")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(16, 14, 16, 14)
            cv.setSpacing(10)

            # Progress row
            prog_row = QHBoxLayout()
            prog_row.setSpacing(10)
            self._progress = QProgressBar()
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._progress.setMaximumHeight(3)
            prog_row.addWidget(self._progress, 1)
            self._progress_label = QLabel("就绪")
            self._progress_label.setStyleSheet("color: #A1A1AA; font-size: 11px; min-width: 0;")
            self._progress_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            prog_row.addWidget(self._progress_label)
            cv.addLayout(prog_row)

            # Preview card
            preview_card = QFrame()
            preview_card.setObjectName("previewCard")
            pc_layout = QVBoxLayout(preview_card)
            pc_layout.setContentsMargins(1, 1, 1, 1)
            pc_layout.setSpacing(0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setAlignment(Qt.AlignCenter)
            scroll.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }"
                "QScrollArea > QWidget > QWidget { background: transparent; }"
            )
            self._preview_label = QLabel("制作完成后，地图将在此处显示")
            self._preview_label.setAlignment(Qt.AlignCenter)
            self._preview_label.setStyleSheet("color: #D4D4D8; font-size: 14px; background: transparent;")
            self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            scroll.setWidget(self._preview_label)
            pc_layout.addWidget(scroll)
            cv.addWidget(preview_card, 1)

            # Log
            log_hdr = QLabel("运行日志")
            log_hdr.setStyleSheet("color: #A1A1AA; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
            cv.addWidget(log_hdr)

            self._log = QTextEdit()
            self._log.setObjectName("logPanel")
            self._log.setReadOnly(True)
            self._log.setFixedHeight(90)
            cv.addWidget(self._log)

            root.addWidget(content, 1)
            self.setStatusBar(QStatusBar())

        # ── Populate ───────────────────────────────────────────────────────────

        def _populate_provinces(self) -> None:
            self._province_combo.clear()
            for p in self._boundary_mgr.list_provinces():
                self._province_combo.addItem(p["name"], userData=p["adcode"])

        def _populate_engines(self) -> None:
            _ENGINES = [
                ("QGIS",               "qgis",    "src.renderers.qgis_renderer",    "QGISRenderer"),
                ("Cartopy (纯Python)", "cartopy",  "src.renderers.cartopy_renderer", "CartopyRenderer"),
                ("ArcGIS Pro",         "arcgis",  "src.renderers.arcgis_renderer",  "ArcGISRenderer"),
            ]
            for label, key, _m, _c in _ENGINES:
                self._engine_combo.addItem(f"{label} (检测中…)", userData=key)
            self._engine_combo.setCurrentIndex(1)

            def _probe():
                results = []
                for label, key, mod_name, cls_name in _ENGINES:
                    try:
                        import importlib
                        mod = importlib.import_module(mod_name)
                        avail, ver = getattr(mod, cls_name)().check_available()
                    except Exception as exc:
                        avail, ver = False, str(exc)
                    results.append((label, key, avail, ver))
                return results

            class _ProbeThread(QThread):
                done = pyqtSignal(list)
                def run(self): self.done.emit(_probe())

            self._probe_thread = _ProbeThread()

            def _on_done(results):
                self._engine_combo.clear()
                preferred_idx = 1
                for i, (label, key, avail, ver) in enumerate(results):
                    self._engine_combo.addItem(
                        label if avail else f"{label} (不可用)", userData=key
                    )
                    if not avail:
                        self._engine_combo.model().item(i).setForeground(QColor("#D4D4D8"))
                        self.append_log(f"[引擎] {label} 不可用: {ver}")
                    else:
                        self.append_log(f"[引擎] {label} 可用: {ver}")
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

        # ── Slots ──────────────────────────────────────────────────────────────

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
                name = str(dlg.shp_path.name) if dlg.shp_path else "未选择"
                self._shp_label.setText(name)
                self._shp_label.setStyleSheet(
                    "color: #18181B; font-size: 11px; padding: 5px 10px;"
                    " background: #F4F4F5; border-radius: 6px; min-height: 28px;"
                )
                self._shp_clear_btn.setVisible(True)
                self._province_combo.setEnabled(False)
                self._city_combo.setEnabled(False)

        def _clear_shp(self) -> None:
            self._custom_shp = None
            self._custom_name = ""
            self._shp_label.setText("未选择")
            self._shp_label.setStyleSheet("")  # revert to objectName CSS
            self._shp_clear_btn.setVisible(False)
            self._province_combo.setEnabled(True)
            self._city_combo.setEnabled(True)

        def _open_gee_dialog(self) -> None:
            from src.gui.gee_auth_dialog import GEEAuthDialog
            dlg = GEEAuthDialog(self)
            dlg.set_fetcher(self._pipeline.gee_fetcher)
            dlg.exec_()
            pid = self._pipeline.gee_fetcher._project_id
            if pid:
                self._cfg.set("gee_project_id", pid)

        def _on_run_cancel(self) -> None:
            if self._worker and getattr(self._worker, "isRunning", lambda: False)():
                self._worker.cancel()
                self._run_btn.setText("开始制图")
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

            area_name = self._custom_name or city_name
            safe_name = area_name.replace("/", "_").replace("\\", "_")
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
            label = f"{area_name} (SHP)" if self._custom_shp else city_name
            self.append_log(f"开始制作: {label} ({engine_key})")
            if self._custom_shp:
                self.append_log(
                    f"自定义 SHP: {self._custom_shp.name}  "
                    f"标题名称: {self._custom_name or '(SHP文件名)'}"
                )
            self._worker.start()

        # ── Worker callbacks ───────────────────────────────────────────────────

        def update_progress(self, pct: int, msg: str) -> None:
            self._progress.setValue(pct)
            self._progress_label.setText(msg)

        def append_log(self, msg: str) -> None:
            self._log.append(msg)
            self._log.verticalScrollBar().setValue(
                self._log.verticalScrollBar().maximum()
            )

        def on_finished(self, output_path: str) -> None:
            self._run_btn.setText("开始制图")
            self._progress.setValue(100)
            self.append_log(f"完成: {output_path}")
            self.statusBar().showMessage(f"输出: {output_path}", 10000)
            self._show_preview(output_path)

        def on_error(self, error_msg: str) -> None:
            self._run_btn.setText("开始制图")
            self._preview_label.setText("制作失败")
            self.append_log(f"错误: {error_msg}")
            QMessageBox.critical(self, "制图失败", error_msg)

        def _show_preview(self, path: str) -> None:
            pix = QPixmap(path)
            if pix.isNull():
                self._preview_label.setText(f"无法预览: {path}")
                return
            avail = self._preview_label.parent().size()
            pix_scaled = pix.scaled(
                avail.width() - 10, avail.height() - 10,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._preview_label.setPixmap(pix_scaled)
            self._preview_label.setToolTip(path)
            self._last_output = path

        # ── Cache helpers ──────────────────────────────────────────────────────

        def _get_cache_size_str(self) -> str:
            try:
                size = self._pipeline.cache_mgr.get_cache_size()
                if size < 1024 ** 2:
                    return f"{size / 1024:.1f} KB"
                return f"{size / 1024 ** 2:.1f} MB"
            except Exception:
                return "—"

        def _pick_cache_dir(self) -> None:
            d = QFileDialog.getExistingDirectory(self, "选择缓存目录", self._cache_dir_edit.text())
            if d:
                self._cache_dir_edit.setText(d)
                self._cfg.set("cache_dir", d)
                self._pipeline.cache_mgr._root = Path(d)
                self._pipeline.cache_mgr._root.mkdir(parents=True, exist_ok=True)
                self._cache_size_label.setText(self._get_cache_size_str())

        def _clear_cache_now(self) -> None:
            self._pipeline.cache_mgr.clear_cache()
            self._cache_size_label.setText(self._get_cache_size_str())
            self.append_log("缓存已清除")

        def closeEvent(self, event) -> None:
            self._pipeline.cache_mgr.clear_cache()
            event.accept()

else:
    class MainWindow:  # type: ignore[no-redef]
        """Stub used when PyQt5 is unavailable."""
        def __init__(self, *a, **kw): pass
