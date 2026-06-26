"""QGIS PyQGIS rendering engine — generates three-panel location maps via QgsLayout."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from src.renderers.base import BaseRenderer, RenderConfig
from src.core.exceptions import RenderFailedError, RendererNotAvailableError

# ---------------------------------------------------------------------------
# QGIS availability probe — all PyQGIS imports are deferred
# ---------------------------------------------------------------------------

_QGIS_AVAILABLE: bool = False
_QGIS_VERSION: str = ""

# Windows search paths (checked in order)
_QGIS_WIN_PATHS = [
    r"C:\Program Files\QGIS 3.40",
    r"C:\Program Files\QGIS 3.38",
    r"C:\Program Files\QGIS 3.34",
    r"C:\OSGeo4W",
]


def _probe_qgis() -> tuple[bool, str]:
    """Try to import qgis.core; return (available, version_string)."""
    global _QGIS_AVAILABLE, _QGIS_VERSION
    try:
        from qgis.core import Qgis
        v = Qgis.version()
        _QGIS_AVAILABLE = True
        _QGIS_VERSION = v
        return True, v
    except Exception:
        return False, ""


# Run probe at import time (fast, no side-effects if QGIS absent)
_probe_qgis()


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class QGISRenderer(BaseRenderer):
    """Render three-panel location maps using PyQGIS QgsLayout."""

    def __init__(self) -> None:
        self._qgs = None  # QgsApplication instance

    # ── BaseRenderer interface ─────────────────────────────────────────────────

    def check_available(self) -> tuple[bool, str]:
        if _QGIS_AVAILABLE:
            return True, f"QGIS {_QGIS_VERSION}"
        return False, "未检测到 QGIS 安装 (qgis.core 不可导入)"

    def get_project_path(self) -> Optional[Path]:
        return None  # we build the layout in-memory; no persistent .qgz

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """Full render pipeline: QGIS init → layers → layout → export."""
        if not _QGIS_AVAILABLE:
            raise RendererNotAvailableError("QGIS")

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        try:
            _p(0, "初始化 QGIS...")
            self._init_qgis()

            from qgis.core import QgsProject
            project = QgsProject.instance()
            project.clear()

            _p(10, "加载矢量图层...")
            vector_layers = self._setup_vector_layers(project, config)

            raster_layer = None
            if config.raster_path and Path(config.raster_path).exists():
                _p(25, "加载栅格图层...")
                raster_layer = self._setup_raster_layer(project, config)

            _p(40, "创建布局...")
            layout = self._create_layout(project, config)

            _p(60, "添加地图注记...")
            self._add_map_decorations(layout, config)

            _p(75, "添加连接线...")
            self._add_connection_lines(layout, config)

            _p(85, "导出...")
            output = self._export(layout, config)

            _p(100, "完成")
            return output

        except (RendererNotAvailableError, RenderFailedError):
            raise
        except Exception as exc:
            raise RenderFailedError(str(exc)) from exc

    # ── QGIS initialisation ────────────────────────────────────────────────────

    def _init_qgis(self) -> None:
        if self._qgs is not None:
            return

        qgis_prefix = self._detect_qgis_prefix()
        if not qgis_prefix:
            raise RendererNotAvailableError("QGIS", "无法找到 QGIS 安装路径")

        # Inject QGIS libraries into PATH / PYTHONPATH on Windows
        if sys.platform == "win32":
            self._configure_win_env(qgis_prefix)

        from qgis.core import QgsApplication
        self._qgs = QgsApplication([], False)
        self._qgs.setPrefixPath(str(qgis_prefix), True)
        self._qgs.initQgis()

    def _detect_qgis_prefix(self) -> Optional[Path]:
        """Return the QGIS prefix path, or None if not found."""
        # 1. Respect explicit override
        env_path = os.environ.get("QGIS_PREFIX_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # 2. Windows registry
        if sys.platform == "win32":
            p = self._read_qgis_registry()
            if p:
                return p

        # 3. Well-known Windows installation paths
        for root in _QGIS_WIN_PATHS:
            candidate = Path(root) / "apps" / "qgis"
            if candidate.exists():
                return candidate

        # 4. Try the already-importable path
        try:
            import qgis
            return Path(qgis.__file__).parent.parent
        except Exception:
            return None

    @staticmethod
    def _read_qgis_registry() -> Optional[Path]:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\QGIS")
            install_dir, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            candidate = Path(install_dir) / "apps" / "qgis"
            return candidate if candidate.exists() else None
        except Exception:
            return None

    @staticmethod
    def _configure_win_env(qgis_prefix: Path) -> None:
        qgis_root = qgis_prefix.parent.parent  # e.g. C:\Program Files\QGIS 3.40
        bin_dirs = [
            str(qgis_prefix / "bin"),
            str(qgis_root / "bin"),
        ]
        py_dirs = [
            str(qgis_prefix / "python"),
            str(qgis_prefix / "python" / "plugins"),
        ]
        for d in bin_dirs:
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        for d in py_dirs:
            if d not in sys.path:
                sys.path.insert(0, d)

    # ── Layer setup ───────────────────────────────────────────────────────────

    def _setup_vector_layers(self, project, config: RenderConfig) -> dict:
        from qgis.core import (
            QgsVectorLayer, QgsFillSymbol, QgsLineSymbol,
            QgsSingleSymbolRenderer,
        )

        layers = {}
        specs = [
            ("country",  config.country_boundary,  "#E8E8E8", "#888888", 0.3),
            ("province", config.province_boundary,  "#D0D0D0", "#666666", 0.4),
            ("city",     config.city_boundary,       "#C0C0C0", "#444444", 0.5),
        ]

        for name, path, fill_color, line_color, line_width in specs:
            if not path or not Path(path).exists():
                continue
            layer = QgsVectorLayer(str(path), name, "ogr")
            if not layer.isValid():
                continue

            symbol = QgsFillSymbol.createSimple({
                "color": fill_color,
                "outline_color": line_color,
                "outline_width": str(line_width),
            })
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            project.addMapLayer(layer)
            layers[name] = layer

        # Highlighted layer (province on China map, city on province map)
        for name, path, fill_alpha in [
            ("province_highlight", config.province_boundary, "100,0,0,80"),
            ("city_highlight",     config.city_boundary,     "200,0,0,100"),
        ]:
            if not path or not Path(path).exists():
                continue
            layer = QgsVectorLayer(str(path), name, "ogr")
            if not layer.isValid():
                continue
            r, g, b = _hex_to_rgb(config.highlight_color)
            symbol = QgsFillSymbol.createSimple({
                "color": f"{r},{g},{b},80",
                "outline_color": config.highlight_color,
                "outline_width": str(config.highlight_width),
            })
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            project.addMapLayer(layer)
            layers[name] = layer

        return layers

    def _setup_raster_layer(self, project, config: RenderConfig):
        from qgis.core import (
            QgsRasterLayer, QgsColorRampShader, QgsRasterShader,
            QgsSingleBandPseudoColorRenderer,
        )

        layer = QgsRasterLayer(str(config.raster_path), "raster", "gdal")
        if not layer.isValid():
            return None

        if config.data_type == "dem":
            color_ramp_data = _load_color_ramp(config.color_ramp)
            if color_ramp_data:
                shader_function = QgsColorRampShader()
                shader_function.setColorRampType(QgsColorRampShader.Interpolated)
                items = []
                from qgis.core import QgsColorRampShader
                for stop in color_ramp_data.get("stops", []):
                    r, g, b = _hex_to_rgb(stop["color"])
                    from qgis.PyQt.QtGui import QColor
                    items.append(
                        QgsColorRampShader.ColorRampItem(
                            stop["value"],
                            QColor(r, g, b),
                            stop.get("label", str(stop["value"])),
                        )
                    )
                shader_function.setColorRampItemList(items)
                raster_shader = QgsRasterShader()
                raster_shader.setRasterShaderFunction(shader_function)
                renderer = QgsSingleBandPseudoColorRenderer(
                    layer.dataProvider(), 1, raster_shader
                )
                layer.setRenderer(renderer)

        project.addMapLayer(layer)
        return layer

    # ── Layout creation ───────────────────────────────────────────────────────

    def _create_layout(self, project, config: RenderConfig):
        """Build a QgsPrintLayout with three map panels per SPEC §4.2."""
        from qgis.core import (
            QgsPrintLayout, QgsLayoutItemMap, QgsLayoutSize,
            QgsUnitTypes, QgsRectangle, QgsCoordinateReferenceSystem,
            QgsLayoutPoint,
        )
        from qgis.PyQt.QtCore import QRectF

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()

        # A4 landscape
        page = layout.pageCollection().pages()[0]
        page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))

        # ── (a) China overview — 90×78mm, top-left at (5, 22) ────────────────
        map_china = QgsLayoutItemMap(layout)
        map_china.setFixedSize(QgsLayoutSize(90, 78, QgsUnitTypes.LayoutMillimeters))
        map_china.attemptMove(QgsLayoutPoint(5, 22, QgsUnitTypes.LayoutMillimeters))
        crs_lcc = QgsCoordinateReferenceSystem(
            '+proj=lcc +lat_1=25 +lat_2=47 +lat_0=35 +lon_0=105 '
            '+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs'
        )
        map_china.setCrs(crs_lcc)
        map_china.zoomToExtent(QgsRectangle(-2800000, -1500000, 2800000, 2500000))
        map_china.setId("map_china")
        layout.addLayoutItem(map_china)

        # ── (b) Province panel — 90×62mm, below (a) at (5, 105) ─────────────
        map_province = QgsLayoutItemMap(layout)
        map_province.setFixedSize(QgsLayoutSize(90, 62, QgsUnitTypes.LayoutMillimeters))
        map_province.attemptMove(QgsLayoutPoint(5, 105, QgsUnitTypes.LayoutMillimeters))
        map_province.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        map_province.setId("map_province")
        layout.addLayoutItem(map_province)

        # ── (c) Study-area detail — 182×155mm, right panel ───────────────────
        map_detail = QgsLayoutItemMap(layout)
        map_detail.setFixedSize(QgsLayoutSize(182, 155, QgsUnitTypes.LayoutMillimeters))
        map_detail.attemptMove(QgsLayoutPoint(100, 22, QgsUnitTypes.LayoutMillimeters))
        map_detail.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        map_detail.setId("map_detail")
        layout.addLayoutItem(map_detail)

        # ── Title label ────────────────────────────────────────────────────────
        self._add_title(layout, config)

        # ── Footer ─────────────────────────────────────────────────────────────
        self._add_footer(layout, config)

        # ── Panel labels (a) (b) (c) ──────────────────────────────────────────
        self._add_panel_labels(layout)

        return layout

    def _add_title(self, layout, config: RenderConfig) -> None:
        from qgis.core import QgsLayoutItemLabel, QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes
        from qgis.PyQt.QtGui import QFont
        from qgis.PyQt.QtCore import Qt

        title_text = config.title or (
            f"{config.city_name}研究区区位图"
            if config.language == "zh"
            else f"Location Map of {config.city_name} Study Area"
        )
        label = QgsLayoutItemLabel(layout)
        label.setText(title_text)
        font = QFont("SimHei" if config.language == "zh" else "Arial", 16, QFont.Bold)
        label.setFont(font)
        label.setHAlign(Qt.AlignHCenter)
        label.setFixedSize(QgsLayoutSize(182, 12, QgsUnitTypes.LayoutMillimeters))
        label.attemptMove(QgsLayoutPoint(100, 8, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)

    def _add_footer(self, layout, config: RenderConfig) -> None:
        from qgis.core import QgsLayoutItemLabel, QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes
        from qgis.PyQt.QtGui import QFont
        from qgis.PyQt.QtCore import Qt
        import datetime

        today = datetime.date.today().strftime("%Y-%m-%d")
        footer = (
            f"坐标系: WGS84 (EPSG:4326)  |  数据来源: Google Earth Engine / 天地图  |  制图日期: {today}"
        )
        label = QgsLayoutItemLabel(layout)
        label.setText(footer)
        label.setFont(QFont("SimSun" if config.language == "zh" else "Arial", 7))
        label.setHAlign(Qt.AlignHCenter)
        label.setFixedSize(QgsLayoutSize(287, 8, QgsUnitTypes.LayoutMillimeters))
        label.attemptMove(QgsLayoutPoint(5, 200, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(label)

    def _add_panel_labels(self, layout) -> None:
        from qgis.core import QgsLayoutItemLabel, QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes
        from qgis.PyQt.QtGui import QFont
        from qgis.PyQt.QtCore import Qt

        specs = [("(a)", 5, 17), ("(b)", 5, 100), ("(c)", 100, 17)]
        for text, x, y in specs:
            label = QgsLayoutItemLabel(layout)
            label.setText(text)
            label.setFont(QFont("SimHei", 12, QFont.Bold))
            label.setFixedSize(QgsLayoutSize(15, 7, QgsUnitTypes.LayoutMillimeters))
            label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
            layout.addLayoutItem(label)

    # ── Decorations ───────────────────────────────────────────────────────────

    def _add_map_decorations(self, layout, config: RenderConfig) -> None:
        """Add grid, scale bar, north arrow, and legend to the detail panel."""
        map_detail = layout.itemById("map_detail")
        if map_detail is None:
            return

        if config.show_grid:
            self._add_grid(layout, map_detail, config)

        if config.show_scalebar:
            self._add_scalebar(layout, map_detail, config)

        if config.show_north_arrow:
            self._add_north_arrow(layout, config)

        if config.show_legend:
            self._add_legend(layout, config)

    def _add_grid(self, layout, map_item, config: RenderConfig) -> None:
        from qgis.core import QgsLayoutItemMapGrid, QgsUnitTypes
        from qgis.PyQt.QtGui import QFont, QColor

        grid = QgsLayoutItemMapGrid("grid", map_item)
        # Auto-calculate interval from extent
        extent = map_item.extent()
        span = max(extent.width(), extent.height()) if extent else 5.0
        interval = _calc_grid_interval(span)
        grid.setIntervalX(interval)
        grid.setIntervalY(interval)
        grid.setAnnotationEnabled(True)
        grid.setAnnotationFont(QFont("SimSun", 8))
        grid.setAnnotationFontColor(QColor("#666666"))
        grid.setFrameStyle(QgsLayoutItemMapGrid.NoFrame)
        map_item.grids().addGrid(grid)
        map_item.updateBoundingRect()

    def _add_scalebar(self, layout, map_item, config: RenderConfig) -> None:
        from qgis.core import (
            QgsLayoutItemScaleBar, QgsUnitTypes,
            QgsLayoutSize, QgsLayoutPoint,
        )
        from qgis.PyQt.QtGui import QFont, QColor

        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setLinkedMap(map_item)
        scalebar.setUnits(QgsUnitTypes.DistanceKilometers)
        scalebar.setNumberOfSegments(4)
        scalebar.setNumberOfSegmentsLeft(0)
        scalebar.setFont(QFont("SimSun", 7))
        scalebar.setFontColor(QColor("#333333"))
        # Position: bottom-left of detail map
        scalebar.attemptMove(
            QgsLayoutPoint(102, 165, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(scalebar)

    def _add_north_arrow(self, layout, config: RenderConfig) -> None:
        from qgis.core import (
            QgsLayoutItemPicture, QgsLayoutSize,
            QgsLayoutPoint, QgsUnitTypes,
        )

        arrow_path = (
            Path(__file__).parent.parent
            / "resources" / "north_arrows" / "arrow_default.svg"
        )
        pic = QgsLayoutItemPicture(layout)
        if arrow_path.exists():
            pic.setPicturePath(str(arrow_path))
        pic.setFixedSize(QgsLayoutSize(12, 18, QgsUnitTypes.LayoutMillimeters))
        # Position: top-right of detail panel
        pic.attemptMove(
            QgsLayoutPoint(268, 26, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(pic)

    def _add_legend(self, layout, config: RenderConfig) -> None:
        from qgis.core import (
            QgsLayoutItemLegend, QgsLayoutSize,
            QgsLayoutPoint, QgsUnitTypes,
        )
        from qgis.PyQt.QtGui import QFont

        legend = QgsLayoutItemLegend(layout)
        legend.setAutoUpdateModel(True)
        legend.setTitle("图例" if config.language == "zh" else "Legend")
        legend.setStyleFont(
            QgsLayoutItemLegend.LegendTitle,
            QFont("SimHei" if config.language == "zh" else "Arial", 8),
        )
        legend.setStyleFont(
            QgsLayoutItemLegend.LegendItem,
            QFont("SimSun" if config.language == "zh" else "Arial", 7),
        )
        legend.attemptMove(
            QgsLayoutPoint(245, 145, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(legend)

    # ── Connection lines ──────────────────────────────────────────────────────

    def _add_connection_lines(self, layout, config: RenderConfig) -> None:
        """Draw dashed rectangles / arrows connecting the three panels."""
        try:
            from qgis.core import (
                QgsLayoutItemPolyline, QgsLayoutItemShape,
                QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
            )
            from qgis.PyQt.QtGui import QPolygonF, QPen, QColor
            from qgis.PyQt.QtCore import QPointF
        except Exception:
            return  # skip if types unavailable

        # Simple connector: a small red rectangle around the province region on (a)
        box = QgsLayoutItemShape(layout)
        box.setShapeType(QgsLayoutItemShape.Rectangle)
        pen = QPen(QColor(200, 0, 0), 0.5)
        box.setFrameEnabled(True)
        box.setBackgroundEnabled(False)
        box.setFixedSize(QgsLayoutSize(30, 20, QgsUnitTypes.LayoutMillimeters))
        box.attemptMove(QgsLayoutPoint(30, 45, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(box)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self, layout, config: RenderConfig) -> Path:
        from qgis.core import QgsLayoutExporter

        exporter = QgsLayoutExporter(layout)
        output = Path(config.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fmt = config.output_format.lower()

        if fmt in ("jpg", "jpeg"):
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = config.dpi
            res = exporter.exportToImage(str(output), settings)
        elif fmt == "png":
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = config.dpi
            res = exporter.exportToImage(str(output), settings)
        elif fmt == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = config.dpi
            res = exporter.exportToPdf(str(output), settings)
        elif fmt == "svg":
            settings = QgsLayoutExporter.SvgExportSettings()
            settings.dpi = config.dpi
            res = exporter.exportToSvg(str(output), settings)
        else:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = config.dpi
            res = exporter.exportToImage(str(output), settings)

        if res != QgsLayoutExporter.Success:
            raise RenderFailedError(f"QgsLayoutExporter 返回错误码 {res}")

        return output


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _calc_grid_interval(extent_degrees: float) -> float:
    """Auto-select graticule interval from SPEC §4.2."""
    if extent_degrees > 30:
        return 10.0
    if extent_degrees > 10:
        return 5.0
    if extent_degrees > 5:
        return 2.0
    if extent_degrees > 2:
        return 1.0
    if extent_degrees > 1:
        return 0.5
    if extent_degrees > 0.5:
        return 0.25
    return 0.1


def _load_color_ramp(name: str) -> Optional[dict]:
    """Load a colour ramp definition from color_ramps.json."""
    ramps_path = Path(__file__).parent.parent / "data" / "color_ramps.json"
    if not ramps_path.exists():
        return None
    with ramps_path.open(encoding="utf-8") as f:
        ramps = json.load(f)
    return ramps.get(name)
