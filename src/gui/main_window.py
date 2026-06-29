"""Main application window for Region Map Wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QComboBox, QPushButton, QProgressBar,
        QTextEdit, QFileDialog, QFormLayout,
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

# ── Stylesheet ─────────────────────────────────────────────────────────────────
_STYLE = """
/* ── Reset & Base ─────────────────────────────────────────────────────────── */
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
    font-size: 12px;
    color: #0F172A;
    outline: none;
}
QMainWindow, QDialog {
    background: #F8FAFC;
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
QWidget#sidebar {
    background: #FFFFFF;
    border-right: 1px solid #F1F5F9;
}
QLabel#appTitle {
    font-size: 14px;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.5px;
}
QLabel#appSubtitle {
    font-size: 11px;
    color: #94A3B8;
}

/* Section header — uppercase label, no box */
QLabel#sectionLabel {
    font-size: 10px;
    font-weight: 600;
    color: #94A3B8;
    letter-spacing: 0.8px;
    padding-top: 16px;
    padding-bottom: 2px;
}

/* ── Form row labels ──────────────────────────────────────────────────────── */
QLabel#formLabel {
    color: #64748B;
    font-size: 12px;
    min-width: 56px;
    max-width: 56px;
}

/* ── Inputs ───────────────────────────────────────────────────────────────── */
QComboBox, QLineEdit {
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 3px 8px;
    background: #FFFFFF;
    color: #0F172A;
    font-size: 12px;
    min-height: 26px;
    selection-background-color: #DBEAFE;
}
QComboBox:hover, QLineEdit:hover {
    border-color: #CBD5E1;
}
QComboBox:focus, QLineEdit:focus {
    border: 1px solid #3B82F6;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QComboBox QAbstractItemView {
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    background: #FFFFFF;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    padding: 2px 0;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 0 8px;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
QPushButton {
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 4px 12px;
    background: #FFFFFF;
    color: #374151;
    font-size: 12px;
    min-height: 26px;
}
QPushButton:hover {
    background: #F8FAFC;
    border-color: #CBD5E1;
    color: #111827;
}
QPushButton:pressed {
    background: #F1F5F9;
    border-color: #94A3B8;
}
QPushButton:disabled {
    color: #CBD5E1;
    background: #F8FAFC;
    border-color: #F1F5F9;
}

QPushButton#runButton {
    background: #18181B;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    min-height: 42px;
    letter-spacing: 0.2px;
}
QPushButton#runButton:hover {
    background: #27272A;
    color: #FFFFFF;
    border: none;
}
QPushButton#runButton:pressed {
    background: #3F3F46;
    color: #FFFFFF;
    border: none;
}
QPushButton#runButton:disabled {
    background: #D4D4D8;
    color: #FFFFFF;
    border: none;
}

QPushButton#smallBtn {
    font-size: 11px;
    min-height: 24px;
    padding: 2px 8px;
    border-radius: 5px;
}

QPushButton#geeBtn {
    background: transparent;
    border: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 11px;
    min-height: 30px;
    border-radius: 6px;
}
QPushButton#geeBtn:hover {
    background: #F8FAFC;
    border-color: #CBD5E1;
    color: #374151;
}

/* ── Checkbox ─────────────────────────────────────────────────────────────── */
QCheckBox {
    color: #64748B;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1.5px solid #D1D5DB;
    border-radius: 4px;
    background: #FFFFFF;
}
QCheckBox::indicator:hover { border-color: #94A3B8; }
QCheckBox::indicator:checked {
    background: #18181B;
    border-color: #18181B;
}

/* ── Progress bar ─────────────────────────────────────────────────────────── */
QProgressBar {
    border: none;
    border-radius: 2px;
    background: #F1F5F9;
    max-height: 3px;
    font-size: 0px;
}
QProgressBar::chunk {
    background: #18181B;
    border-radius: 2px;
}

/* ── Log panel ────────────────────────────────────────────────────────────── */
QTextEdit#logPanel {
    border: 1px solid #F1F5F9;
    border-radius: 6px;
    background: #FAFAFA;
    color: #64748B;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 4px 8px;
    selection-background-color: #DBEAFE;
}

/* ── Preview card ─────────────────────────────────────────────────────────── */
QFrame#previewCard {
    background: #FFFFFF;
    border: 1px solid #F1F5F9;
    border-radius: 8px;
}

/* ── Scrollbars ───────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    border: none; background: transparent;
    width: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #E2E8F0; border-radius: 2px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #CBD5E1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal {
    border: none; background: transparent;
    height: 4px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #E2E8F0; border-radius: 2px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #CBD5E1; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ── Status bar ───────────────────────────────────────────────────────────── */
QStatusBar {
    background: #F8FAFC;
    border-top: 1px solid #F1F5F9;
    font-size: 11px;
    color: #94A3B8;
    padding: 0 8px;
}
QStatusBar::item { border: none; }

/* ── Dialogs ──────────────────────────────────────────────────────────────── */
QDialog { background: #FFFFFF; }
QDialog QFrame { border: none; background: transparent; }
QDialog QLabel { font-size: 12px; color: #374151; }
QMessageBox { background: #FFFFFF; }
QMessageBox QPushButton { min-width: 72px; }
"""


if _QT_AVAILABLE:
    class MainWindow(QMainWindow):
        """Primary UI: province/city selector, engine selector, run button,
        log panel (left sidebar), image preview (right)."""

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

        # ── UI helpers ─────────────────────────────────────────────────────────

        @staticmethod
        def _fl(text: str) -> "QLabel":
            """Form-row label with consistent fixed width."""
            lbl = QLabel(text)
            lbl.setObjectName("formLabel")
            return lbl

        @staticmethod
        def _sec(text: str) -> "QLabel":
            """Uppercase section header — typography only, no decorative box."""
            lbl = QLabel(text.upper())
            lbl.setObjectName("sectionLabel")
            return lbl

        @staticmethod
        def _wrap_form(form: "QFormLayout") -> "QWidget":
            """Wrap a QFormLayout in a plain QWidget for adding to a VBox."""
            w = QWidget()
            w.setLayout(form)
            return w

        def _make_form(self) -> "QFormLayout":
            f = QFormLayout()
            f.setSpacing(6)
            f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            f.setContentsMargins(0, 4, 0, 0)
            return f

        # ── UI construction ────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            central = QWidget()
            central.setObjectName("central")
            self.setCentralWidget(central)

            root = QHBoxLayout(central)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            # ── LEFT SIDEBAR ───────────────────────────────────────────────────
            sidebar_content = QWidget()
            sidebar_content.setObjectName("sidebar")
            sb = QVBoxLayout(sidebar_content)
            sb.setContentsMargins(16, 22, 16, 16)
            sb.setSpacing(0)

            # Branding
            title_lbl = QLabel("Region Map Wizard")
            title_lbl.setObjectName("appTitle")
            sub_lbl = QLabel("研究区区位图自动制图工具")
            sub_lbl.setObjectName("appSubtitle")
            sb.addWidget(title_lbl)
            sb.addSpacing(3)
            sb.addWidget(sub_lbl)

            # ── 研究区 ─────────────────────────────────────────────────────────
            sb.addWidget(self._sec("研究区"))
            area_form = self._make_form()

            self._province_combo = QComboBox()
            self._province_combo.currentIndexChanged.connect(self._on_province_changed)
            area_form.addRow(self._fl("省份"), self._province_combo)

            self._city_combo = QComboBox()
            area_form.addRow(self._fl("城市"), self._city_combo)

            shp_row = QHBoxLayout()
            shp_row.setSpacing(6)
            shp_row.setContentsMargins(0, 0, 0, 0)
            self._shp_label = QLabel("未选择")
            self._shp_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
            self._shp_label.setWordWrap(True)
            shp_btn = QPushButton("导入…")
            shp_btn.setObjectName("smallBtn")
            shp_btn.setFixedWidth(52)
            shp_btn.clicked.connect(self._import_shp)
            self._shp_clear_btn = QPushButton("清除")
            self._shp_clear_btn.setObjectName("smallBtn")
            self._shp_clear_btn.setFixedWidth(44)
            self._shp_clear_btn.setVisible(False)
            self._shp_clear_btn.clicked.connect(self._clear_shp)
            shp_row.addWidget(self._shp_label, 1)
            shp_row.addWidget(shp_btn)
            shp_row.addWidget(self._shp_clear_btn)
            area_form.addRow(self._fl("自定义"), shp_row)
            sb.addWidget(self._wrap_form(area_form))

            # ── 数据选项 ───────────────────────────────────────────────────────
            sb.addWidget(self._sec("数据选项"))
            data_form = self._make_form()

            self._data_type_combo = QComboBox()
            self._data_type_combo.addItems(["仅矢量", "DEM 高程", "山体阴影", "Sentinel-2 真彩色"])
            data_form.addRow(self._fl("数据类型"), self._data_type_combo)

            self._color_ramp_combo = QComboBox()
            self._color_ramp_combo.addItems(["dem_hypsometric", "dem_green_brown"])
            data_form.addRow(self._fl("色带"), self._color_ramp_combo)

            self._basemap_combo = QComboBox()
            from src.renderers.cartopy_renderer import BASEMAP_REGISTRY
            for key, meta in BASEMAP_REGISTRY.items():
                self._basemap_combo.addItem(meta["label_zh"], userData=key)
            data_form.addRow(self._fl("底图"), self._basemap_combo)

            self._lang_combo = QComboBox()
            self._lang_combo.addItem("中文", userData="zh")
            self._lang_combo.addItem("English", userData="en")
            data_form.addRow(self._fl("语言"), self._lang_combo)

            self._zoom_lines_chk = QCheckBox("显示区位连接线")
            self._zoom_lines_chk.setChecked(False)
            data_form.addRow(self._fl(""), self._zoom_lines_chk)
            sb.addWidget(self._wrap_form(data_form))

            # ── 渲染与输出 ──────────────────────────────────────────────────────
            sb.addWidget(self._sec("渲染与输出"))
            out_form = self._make_form()

            self._engine_combo = QComboBox()
            self._populate_engines()
            out_form.addRow(self._fl("引擎"), self._engine_combo)

            fmt_dpi_row = QHBoxLayout()
            fmt_dpi_row.setSpacing(6)
            fmt_dpi_row.setContentsMargins(0, 0, 0, 0)
            self._fmt_combo = QComboBox()
            self._fmt_combo.addItems(["JPG", "PNG", "PDF"])
            self._fmt_combo.setFixedWidth(72)
            dpi_lbl = QLabel("DPI")
            dpi_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; min-width: 0;")
            self._dpi_combo = QComboBox()
            self._dpi_combo.addItems(["150", "300", "600"])
            self._dpi_combo.setCurrentText("300")
            self._dpi_combo.setFixedWidth(72)
            fmt_dpi_row.addWidget(self._fmt_combo)
            fmt_dpi_row.addWidget(dpi_lbl)
            fmt_dpi_row.addWidget(self._dpi_combo)
            fmt_dpi_row.addStretch()
            out_form.addRow(self._fl("格式/DPI"), fmt_dpi_row)

            dir_row = QHBoxLayout()
            dir_row.setSpacing(6)
            dir_row.setContentsMargins(0, 0, 0, 0)
            self._out_dir_edit = QLineEdit()
            self._out_dir_edit.setPlaceholderText("选择输出目录…")
            dir_btn = QPushButton("…")
            dir_btn.setObjectName("smallBtn")
            dir_btn.setFixedWidth(28)
            dir_btn.clicked.connect(self._pick_output_dir)
            dir_row.addWidget(self._out_dir_edit, 1)
            dir_row.addWidget(dir_btn)
            out_form.addRow(self._fl("输出目录"), dir_row)
            sb.addWidget(self._wrap_form(out_form))

            # ── 缓存 ───────────────────────────────────────────────────────────
            sb.addWidget(self._sec("缓存"))
            cache_form = self._make_form()

            cache_dir_row = QHBoxLayout()
            saved_cache = self._cfg.get("cache_dir", "")
            self._cache_dir_edit = QLineEdit(saved_cache or str(Path.home() / ".rmw_cache"))
            self._cache_dir_edit.setReadOnly(True)
            self._cache_dir_edit.setStyleSheet(
                "QLineEdit { color: #64748B; font-size: 11px; }"
            )
            cache_dir_btn = QPushButton("…")
            cache_dir_btn.setObjectName("smallBtn")
            cache_dir_btn.setFixedWidth(28)
            cache_dir_btn.clicked.connect(self._pick_cache_dir)
            cache_dir_row.addWidget(self._cache_dir_edit, 1)
            cache_dir_row.addWidget(cache_dir_btn)
            cache_form.addRow(self._fl("目录"), cache_dir_row)

            self._cache_size_label = QLabel(self._get_cache_size_str())
            self._cache_size_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
            cache_form.addRow(self._fl("大小"), self._cache_size_label)

            clear_cache_btn = QPushButton("立即清除缓存")
            clear_cache_btn.setObjectName("smallBtn")
            clear_cache_btn.clicked.connect(self._clear_cache_now)
            cache_form.addRow("", clear_cache_btn)
            sb.addWidget(self._wrap_form(cache_form))

            sb.addStretch(1)

            # GEE auth button — ghost style, subtle
            gee_btn = QPushButton("GEE 认证设置…")
            gee_btn.setObjectName("geeBtn")
            gee_btn.clicked.connect(self._open_gee_dialog)
            sb.addWidget(gee_btn)
            sb.addSpacing(8)

            # Primary action
            self._run_btn = QPushButton("开始制图")
            self._run_btn.setObjectName("runButton")
            self._run_btn.clicked.connect(self._on_run_cancel)
            sb.addWidget(self._run_btn)

            sidebar_scroll = QScrollArea()
            sidebar_scroll.setFixedWidth(292)
            sidebar_scroll.setWidget(sidebar_content)
            sidebar_scroll.setWidgetResizable(True)
            sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            sidebar_scroll.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }"
            )
            root.addWidget(sidebar_scroll)

            # ── RIGHT CONTENT AREA ──────────────────────────────────────────────
            content = QWidget()
            content.setObjectName("content")
            content.setStyleSheet("QWidget#content { background: #F8FAFC; }")
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
            self._progress_label.setStyleSheet(
                "color: #94A3B8; font-size: 11px; min-width: 0;"
            )
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
            self._preview_label.setStyleSheet(
                "color: #CBD5E1; font-size: 14px; background: transparent;"
            )
            self._preview_label.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            scroll.setWidget(self._preview_label)
            pc_layout.addWidget(scroll)
            cv.addWidget(preview_card, 1)

            # Log section
            log_header_row = QHBoxLayout()
            log_header_row.setContentsMargins(2, 0, 0, 0)
            log_hdr = QLabel("运行日志")
            log_hdr.setStyleSheet(
                "color: #94A3B8; font-size: 10px; font-weight: 600; letter-spacing: 0.8px;"
            )
            log_header_row.addWidget(log_hdr)
            log_header_row.addStretch()
            cv.addLayout(log_header_row)

            self._log = QTextEdit()
            self._log.setObjectName("logPanel")
            self._log.setReadOnly(True)
            self._log.setFixedHeight(90)
            cv.addWidget(self._log)

            root.addWidget(content, 1)

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

            self._engine_combo.setCurrentIndex(1)

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
                preferred_idx = 1
                for i, (label, key, avail, ver) in enumerate(results):
                    display = label if avail else f"{label} (不可用)"
                    self._engine_combo.addItem(display, userData=key)
                    if not avail:
                        self._engine_combo.model().item(i).setForeground(QColor("#CBD5E1"))
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
                name = str(dlg.shp_path.name) if dlg.shp_path else "未选择"
                self._shp_label.setText(name)
                self._shp_label.setStyleSheet("color: #0F172A; font-size: 11px;")
                self._shp_clear_btn.setVisible(True)
                self._province_combo.setEnabled(False)
                self._city_combo.setEnabled(False)

        def _clear_shp(self) -> None:
            self._custom_shp = None
            self._custom_name = ""
            self._shp_label.setText("未选择")
            self._shp_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
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
                self.append_log(f"自定义 SHP: {self._custom_shp.name}  标题名称: {self._custom_name or '(SHP文件名)'}")
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
