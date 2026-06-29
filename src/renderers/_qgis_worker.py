"""Subprocess worker — runs inside the QGIS Python environment.

Launched by QGISRenderer as:
    python-qgis.bat _qgis_worker.py --config <config_json_path>

python-qgis.bat sets up all necessary environment variables
(QGIS_PREFIX_PATH, PYTHONPATH, GDAL_DATA, PROJ_DATA …) before this script
runs, so no manual path manipulation is needed here.

Progress is reported to stdout as UTF-8 JSON lines:
    {"step": "loading",  "progress": 10,  "message": "..."}
    {"step": "data",     "progress": 30,  "message": "..."}
    {"step": "render",   "progress": 60,  "message": "..."}
    {"step": "export",   "progress": 90,  "message": "..."}
    {"step": "done",     "progress": 100, "message": "完成",
     "output": "/path/to/map.jpg", "project": "/path/to/map.qgz"}
    {"step": "error",    "message": "<detail>"}

IMPORTANT: This script must NOT import any rmw project modules.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path


# ── Protocol helpers ──────────────────────────────────────────────────────────

def _report(step: str, progress: int, message: str, **extra) -> None:
    payload = {"step": step, "progress": progress, "message": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _error(message: str) -> None:
    print(json.dumps({"step": "error", "message": message}, ensure_ascii=False),
          flush=True)


# ── Grid interval helper ──────────────────────────────────────────────────────

def _grid_interval(span_deg: float) -> float:
    if span_deg > 30:   return 10.0
    if span_deg > 10:   return 5.0
    if span_deg > 5:    return 2.0
    if span_deg > 2:    return 1.0
    if span_deg > 1:    return 0.5
    if span_deg > 0.5:  return 0.25
    return 0.1


# ── Main flow ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Force UTF-8 stdout so Chinese JSON messages aren't GBK-encoded by cmd.exe
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", line_buffering=True
        )

    parser = argparse.ArgumentParser(description="QGIS map worker")
    parser.add_argument("--config", required=True, help="Path to config JSON file")
    args = parser.parse_args()

    config_path = Path(args.config)
    with config_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    try:
        from qgis.core import QgsApplication
    except ImportError:
        _error("qgis.core 不可导入 — 请确保在 QGIS Python 环境中运行此脚本")
        sys.exit(1)

    # Standalone QGIS initialisation (python-qgis.bat has already set the env)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        _render(cfg)
    except Exception as exc:
        _error(str(exc))
        sys.exit(1)
    finally:
        qgs.exitQgis()


def _render(cfg: dict) -> None:
    from qgis.core import (
        QgsProject, QgsPrintLayout,
        QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemScaleBar,
        QgsLayoutItemPicture, QgsLayoutItemMapGrid,
        QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes,
        QgsRectangle, QgsCoordinateReferenceSystem,
        QgsVectorLayer, QgsRasterLayer,
        QgsFillSymbol, QgsSingleSymbolRenderer,
        QgsColorRampShader, QgsRasterShader,
        QgsSingleBandPseudoColorRenderer, QgsSingleBandGrayRenderer,
        QgsMultiBandColorRenderer,
        QgsLayoutExporter,
    )
    from qgis.PyQt.QtGui import QFont, QColor
    from qgis.PyQt.QtCore import Qt
    import datetime

    output_dir = cfg.get("output_dir", tempfile.gettempdir())
    output_path_str = cfg.get("output_path", "")
    output_fmt = cfg.get("output_format", "jpg").lower()
    dpi = int(cfg.get("dpi", 300))
    province_name = cfg.get("province_name", "")
    city_name = cfg.get("city_name", "")
    data_type = cfg.get("data_type", "dem").lower()

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if not output_path_str:
        stem = f"{province_name}_{city_name}_区位图" if province_name else "区位图"
        output_path_str = str(Path(output_dir) / f"{stem}.{output_fmt}")
    stem = Path(output_path_str).stem

    # ── Step 1: Project + Layout ──────────────────────────────────────────────
    _report("loading", 5, "初始化 QGIS 项目...")
    project = QgsProject.instance()
    project.clear()

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    page = layout.pageCollection().pages()[0]
    page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))

    # ── Step 2: Load boundary layers ─────────────────────────────────────────
    _report("data", 15, "加载行政区边界...")

    country_path  = cfg.get("country_boundary", "")
    province_path = cfg.get("province_boundary", "")
    city_path     = cfg.get("city_boundary", "")

    country_layer  = _load_vector(country_path,  "country",  project)
    province_layer = _load_vector(province_path, "province", project)
    city_layer     = _load_vector(city_path,     "city",     project)

    # Highlight copies (separate layer refs for per-panel layer assignment)
    highlight_color = cfg.get("highlight_color", "#FF0000")
    highlight_width = float(cfg.get("highlight_width", 1.5))
    prov_hi = _load_vector_highlight(province_path, "province_hi", project,
                                     highlight_color, highlight_width)
    city_hi  = _load_vector_highlight(city_path,     "city_hi",    project,
                                     highlight_color, highlight_width)

    # ── Step 3: Load raster ───────────────────────────────────────────────────
    raster_layer = None
    raster_path = cfg.get("raster_path", "")
    if raster_path and Path(raster_path).exists():
        _report("data", 30, "加载栅格数据...")
        raster_layer = _load_raster(raster_path, data_type, project, cfg)

    # ── Step 4: Three map frames ──────────────────────────────────────────────
    _report("render", 40, "创建地图框...")

    MM = QgsUnitTypes.LayoutMillimeters

    # (a) China overview — 90×78mm, top-left at (5, 5)
    map_china = QgsLayoutItemMap(layout)
    map_china.setFixedSize(QgsLayoutSize(90, 78, MM))
    map_china.attemptMove(QgsLayoutPoint(5, 5, MM))
    lcc_crs = QgsCoordinateReferenceSystem(
        "+proj=lcc +lat_1=25 +lat_2=47 +lat_0=35 +lon_0=105 "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    map_china.setCrs(lcc_crs)
    map_china.zoomToExtent(QgsRectangle(-2_800_000, -1_500_000, 2_800_000, 2_500_000))
    china_layers = [l for l in (country_layer, prov_hi) if l]
    map_china.setLayers(china_layers)
    map_china.setKeepLayerSet(True)
    map_china.setId("map_china")
    layout.addLayoutItem(map_china)

    # (b) Province panel — 90×62mm, below (a) at (5, 88)
    map_province = QgsLayoutItemMap(layout)
    map_province.setFixedSize(QgsLayoutSize(90, 62, MM))
    map_province.attemptMove(QgsLayoutPoint(5, 88, MM))
    map_province.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    prov_layers = [l for l in (province_layer, city_hi) if l]
    map_province.setLayers(prov_layers)
    map_province.setKeepLayerSet(True)
    if province_layer and province_layer.isValid():
        ext = province_layer.extent()
        ext.grow(ext.width() * 0.1)
        map_province.zoomToExtent(ext)
    map_province.setId("map_province")
    layout.addLayoutItem(map_province)

    # (c) Detail — 182×155mm, right side at (100, 22)
    map_detail = QgsLayoutItemMap(layout)
    map_detail.setFixedSize(QgsLayoutSize(182, 155, MM))
    map_detail.attemptMove(QgsLayoutPoint(100, 22, MM))
    map_detail.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    detail_layers = [l for l in (raster_layer, city_layer) if l]
    map_detail.setLayers(detail_layers)
    map_detail.setKeepLayerSet(True)
    if city_layer and city_layer.isValid():
        ext = city_layer.extent()
        ext.grow(ext.width() * 0.15)
        map_detail.zoomToExtent(ext)
    map_detail.setId("map_detail")
    layout.addLayoutItem(map_detail)

    # ── Step 5: Decorations ────────────────────────────────────────────────────
    _report("render", 60, "添加图面装饰...")

    # Title
    title_text = (cfg.get("title") or
                  f"{province_name}{city_name}研究区区位图")
    _add_label(layout, title_text, 100, 8, 182, 12,
               QFont("SimHei", 16, QFont.Bold), Qt.AlignHCenter)

    # Panel labels
    for txt, x, y in [("(a)", 5, 0), ("(b)", 5, 83), ("(c)", 100, 17)]:
        _add_label(layout, txt, x, y, 15, 6,
                   QFont("SimHei", 10, QFont.Bold), Qt.AlignLeft)

    # Footer
    today = datetime.date.today().strftime("%Y-%m-%d")
    footer = (f"坐标系: WGS84 (EPSG:4326)  |  "
              f"数据来源: Google Earth Engine / 天地图  |  制图日期: {today}")
    _add_label(layout, footer, 5, 201, 287, 7,
               QFont("SimSun", 7), Qt.AlignHCenter)

    # Graticule on detail panel
    detail_ext = map_detail.extent()
    span = max(detail_ext.width(), detail_ext.height()) if detail_ext else 2.0
    interval = _grid_interval(span)
    grid = QgsLayoutItemMapGrid("graticule", map_detail)
    grid.setIntervalX(interval)
    grid.setIntervalY(interval)
    grid.setAnnotationEnabled(True)
    grid.setAnnotationFont(QFont("SimSun", 7))
    grid.setAnnotationFontColor(QColor("#666666"))
    grid.setFrameStyle(QgsLayoutItemMapGrid.NoFrame)
    map_detail.grids().addGrid(grid)

    # Scale bar
    scalebar = QgsLayoutItemScaleBar(layout)
    scalebar.setLinkedMap(map_detail)
    scalebar.setUnits(QgsUnitTypes.DistanceKilometers)
    scalebar.setNumberOfSegments(4)
    scalebar.setNumberOfSegmentsLeft(0)
    scalebar.setStyle("Single Box")
    scalebar.setFont(QFont("SimSun", 7))
    scalebar.attemptMove(QgsLayoutPoint(102, 165, MM))
    layout.addLayoutItem(scalebar)

    # North arrow
    pic = QgsLayoutItemPicture(layout)
    pic.setNorthMode(QgsLayoutItemPicture.GridNorth)
    pic.setLinkedMap(map_detail)
    pic.setFixedSize(QgsLayoutSize(10, 15, MM))
    pic.attemptMove(QgsLayoutPoint(269, 25, MM))
    layout.addLayoutItem(pic)

    # ── Step 6: Save .qgz ─────────────────────────────────────────────────────
    _report("render", 82, "保存 QGIS 工程...")
    project_path = str(Path(output_dir) / f"{stem}.qgz")
    project.setFileName(project_path)
    project.write()

    # ── Step 7: Export ────────────────────────────────────────────────────────
    _report("export", 88, f"导出 {output_fmt.upper()}...")
    exporter = QgsLayoutExporter(layout)

    if output_fmt in ("jpg", "jpeg"):
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        res = exporter.exportToImage(output_path_str, settings)
    elif output_fmt == "png":
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        res = exporter.exportToImage(output_path_str, settings)
    elif output_fmt == "pdf":
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = dpi
        res = exporter.exportToPdf(output_path_str, settings)
    elif output_fmt == "svg":
        settings = QgsLayoutExporter.SvgExportSettings()
        settings.dpi = dpi
        res = exporter.exportToSvg(output_path_str, settings)
    else:
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        res = exporter.exportToImage(output_path_str, settings)

    if res != QgsLayoutExporter.Success:
        raise RuntimeError(f"QgsLayoutExporter 返回错误码 {res}")

    _report("done", 100, "完成",
            output=output_path_str,
            project=project_path)


# ── Layer helpers ─────────────────────────────────────────────────────────────

def _load_vector(path: str, name: str, project) -> object | None:
    if not path or not Path(path).exists():
        return None
    from qgis.core import QgsVectorLayer
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        return None
    project.addMapLayer(layer, False)
    return layer


def _load_vector_highlight(path: str, name: str, project,
                            color_hex: str, width: float) -> object | None:
    if not path or not Path(path).exists():
        return None
    from qgis.core import (QgsVectorLayer, QgsFillSymbol,
                            QgsSingleSymbolRenderer)
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        return None
    r, g, b = _hex_to_rgb(color_hex)
    symbol = QgsFillSymbol.createSimple({
        "color": f"{r},{g},{b},60",
        "outline_color": color_hex,
        "outline_width": str(width),
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    project.addMapLayer(layer, False)
    return layer


def _load_raster(path: str, data_type: str, project, cfg: dict) -> object | None:
    from qgis.core import (QgsRasterLayer, QgsColorRampShader, QgsRasterShader,
                            QgsSingleBandPseudoColorRenderer,
                            QgsSingleBandGrayRenderer, QgsMultiBandColorRenderer)
    from qgis.PyQt.QtGui import QColor
    import json as _json

    layer = QgsRasterLayer(path, "raster", "gdal")
    if not layer.isValid():
        return None

    if data_type == "dem":
        color_ramp_name = cfg.get("color_ramp", "elevation")
        ramp_data = _load_color_ramp_data(color_ramp_name)
        if ramp_data:
            shader_fn = QgsColorRampShader()
            shader_fn.setColorRampType(QgsColorRampShader.Interpolated)
            items = []
            for stop in ramp_data.get("stops", []):
                r, g, b = _hex_to_rgb(stop["color"])
                items.append(
                    QgsColorRampShader.ColorRampItem(
                        float(stop["value"]),
                        QColor(r, g, b),
                        stop.get("label", str(stop["value"])),
                    )
                )
            shader_fn.setColorRampItemList(items)
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(shader_fn)
            renderer = QgsSingleBandPseudoColorRenderer(
                layer.dataProvider(), 1, shader
            )
            layer.setRenderer(renderer)

    elif data_type == "hillshade":
        renderer = QgsSingleBandGrayRenderer(layer.dataProvider(), 1)
        renderer.setContrastEnhancement(None)
        layer.setRenderer(renderer)

    elif data_type == "sentinel2":
        renderer = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
        layer.setRenderer(renderer)

    project.addMapLayer(layer, False)
    return layer


def _load_color_ramp_data(name: str) -> dict | None:
    """Load color ramp from a sibling color_ramps.json if it exists."""
    candidates = [
        Path(__file__).parent.parent / "data" / "color_ramps.json",
    ]
    for p in candidates:
        if p.exists():
            import json as _json
            with p.open(encoding="utf-8") as f:
                ramps = _json.load(f)
            return ramps.get(name)
    return None


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _add_label(layout, text: str, x: float, y: float,
               w: float, h: float, font, align) -> None:
    from qgis.core import (QgsLayoutItemLabel, QgsLayoutSize,
                            QgsLayoutPoint, QgsUnitTypes)
    MM = QgsUnitTypes.LayoutMillimeters
    label = QgsLayoutItemLabel(layout)
    label.setText(text)
    label.setFont(font)
    label.setHAlign(align)
    label.setFixedSize(QgsLayoutSize(w, h, MM))
    label.attemptMove(QgsLayoutPoint(x, y, MM))
    layout.addLayoutItem(label)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
