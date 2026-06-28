"""Subprocess worker — runs inside the ArcGIS Pro Python environment.

Launched by ArcGISRenderer as:
    propy.bat _arcgis_worker.py --config <config_json_path>

Progress is reported to stdout as UTF-8 JSON lines (per SPEC §4.3.2):
    {"step": "loading",  "progress": 10,  "message": "..."}
    {"step": "data",     "progress": 30,  "message": "..."}
    {"step": "render",   "progress": 60,  "message": "..."}
    {"step": "export",   "progress": 90,  "message": "..."}
    {"step": "done",     "progress": 100, "message": "完成",
     "output": "/path/to/map.jpg", "project": "/path/to/map.aprx"}
    {"step": "error",    "message": "<error details>"}

IMPORTANT: This script must NOT import any rmw project modules.
           It communicates only through the JSON line protocol above.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


# ── Protocol helpers ──────────────────────────────────────────────────────────

def _report(step: str, progress: int, message: str, **extra) -> None:
    payload = {"step": step, "progress": progress, "message": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _error(message: str) -> None:
    print(json.dumps({"step": "error", "message": message}, ensure_ascii=False), flush=True)


# ── Layout geometry helpers ───────────────────────────────────────────────────

def _rect_polygon(x: float, y: float, w: float, h: float):
    """Return arcpy.Polygon for a rectangle given bottom-left origin (mm)."""
    import arcpy
    sr = arcpy.SpatialReference(0)  # 0 = "Unknown" / unitless page coords
    pts = arcpy.Array([
        arcpy.Point(x,     y),
        arcpy.Point(x + w, y),
        arcpy.Point(x + w, y + h),
        arcpy.Point(x,     y + h),
        arcpy.Point(x,     y),
    ])
    return arcpy.Polygon(pts, sr)


# ── Main flow ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Force stdout to UTF-8 so JSON with Chinese text isn't GBK-encoded by the
    # Windows console (propy.bat runs in a cmd environment that defaults to CP936).
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

    parser = argparse.ArgumentParser(description="ArcGIS Pro map worker")
    parser.add_argument("--config", required=True, help="Path to config JSON file")
    args = parser.parse_args()

    config_path = Path(args.config)
    with config_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    try:
        import arcpy
    except ImportError:
        _error("arcpy 不可用 — 请确保在 ArcGIS Pro Python 环境中运行此脚本")
        sys.exit(1)

    try:
        _render(cfg, arcpy)
    except Exception as exc:
        _error(str(exc))
        sys.exit(1)


def _render(cfg: dict, arcpy) -> None:
    template_path = cfg.get("template_path", "")
    temp_dir = cfg.get("temp_dir") or tempfile.gettempdir()
    output_dir = cfg.get("output_dir", temp_dir)
    output_path_str = cfg.get("output_path", "")
    output_fmt = cfg.get("output_format", "jpg").lower()
    dpi = int(cfg.get("dpi", 300))
    province_name = cfg.get("province_name", "")
    city_name = cfg.get("city_name", "")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    work_aprx = str(Path(temp_dir) / "rmw_work.aprx")

    # ── Step 1: Open project ──────────────────────────────────────────────────
    _report("loading", 5, "准备 ArcGIS Pro 项目...")

    use_template = template_path and Path(template_path).exists()
    if use_template:
        shutil.copy2(template_path, work_aprx)
        _report("loading", 10, "使用预制模板...")
        aprx = arcpy.mp.ArcGISProject(work_aprx)
        china_map    = aprx.listMaps("China_Map")[0]
        province_map = aprx.listMaps("Province_Map")[0]
        city_map     = aprx.listMaps("City_Map")[0]
        layout       = aprx.listLayouts("LocationMap")[0]
    else:
        _report("loading", 10, "从代码创建布局（未找到模板）...")
        aprx, china_map, province_map, city_map, layout = _create_layout_from_code(
            arcpy, work_aprx, cfg
        )

    # ── Step 2: Load boundary layers ─────────────────────────────────────────
    _report("data", 20, "加载行政区边界...")

    country_path  = cfg.get("country_boundary", "")
    province_path = cfg.get("province_boundary", "")
    city_path     = cfg.get("city_boundary", "")

    _add_layer_safe(china_map,    country_path,  arcpy)
    _add_layer_safe(province_map, province_path, arcpy)
    _add_layer_safe(city_map,     city_path,     arcpy)

    # ── Step 3: Load raster ───────────────────────────────────────────────────
    raster_path = cfg.get("raster_path", "")
    if raster_path and Path(raster_path).exists():
        _report("data", 35, "加载栅格数据...")
        city_map.addDataFromPath(raster_path)

    # ── Step 4: Symbolize ─────────────────────────────────────────────────────
    _report("render", 45, "设置符号化...")
    data_type = cfg.get("data_type", "dem").lower()
    _symbolize_layers(city_map, data_type, arcpy)
    _highlight_boundary(province_map, province_name, arcpy)
    _highlight_boundary(city_map, city_name, arcpy)

    # ── Step 5: Set map extents ───────────────────────────────────────────────
    _report("render", 60, "设置地图范围...")
    _set_map_extents(layout, cfg, arcpy)

    # ── Step 6: Update text elements ─────────────────────────────────────────
    _report("render", 70, "更新标注文字...")
    _update_text(layout, cfg, arcpy)

    # ── Step 7: Grid spacing via CIM ─────────────────────────────────────────
    _report("render", 78, "设置经纬网...")
    _set_grid_spacing(layout, arcpy)

    # ── Step 8: Save a copy for the user ─────────────────────────────────────
    _report("render", 85, "保存 ArcGIS Pro 工程副本...")
    stem = f"{province_name}_{city_name}_区位图" if province_name else "区位图"
    output_aprx = str(Path(output_dir) / f"{stem}.aprx")
    aprx.saveACopy(output_aprx)

    # ── Step 9: Export ────────────────────────────────────────────────────────
    _report("export", 90, f"导出 {output_fmt.upper()}...")
    if not output_path_str:
        output_path_str = str(Path(output_dir) / f"{stem}.{output_fmt}")

    fmt_map = {
        "pdf": "PDF", "jpg": "JPEG", "jpeg": "JPEG",
        "png": "PNG", "tif": "TIFF", "tiff": "TIFF",
        "svg": "SVG", "bmp": "BMP",
    }
    fmt_key = fmt_map.get(output_fmt, "JPEG")
    fmt = arcpy.mp.CreateExportFormat(fmt_key, output_path_str)
    fmt.resolution = dpi
    layout.export(fmt)

    del aprx  # release file lock

    _report("done", 100, "完成",
            output=output_path_str,
            project=output_aprx)


# ── Layout creation (full-code fallback) ─────────────────────────────────────

def _create_layout_from_code(arcpy, work_aprx: str, cfg: dict):
    """Create a three-panel layout entirely in code (no template).

    Requires a blank seed .aprx bundled at src/resources/templates/blank_seed.aprx.
    If that file is absent, raises a clear error pointing to the guide.
    """
    seed_aprx = Path(__file__).parent.parent / "resources" / "templates" / "blank_seed.aprx"
    if not seed_aprx.exists():
        raise FileNotFoundError(
            "缺少 ArcGIS Pro 模板文件。\n"
            "请按照 docs/arcgis_template_guide.md 的说明创建模板，\n"
            "将 location_map_template.aprx 放到 src/resources/templates/ 目录后重试。"
        )
    shutil.copy2(str(seed_aprx), work_aprx)
    aprx = arcpy.mp.ArcGISProject(work_aprx)

    china_map    = aprx.createMap("China_Map",    "MAP")
    province_map = aprx.createMap("Province_Map", "MAP")
    city_map     = aprx.createMap("City_Map",     "MAP")

    # Page: 297×210mm A4 landscape
    layout = aprx.createLayout(297, 210, "MILLIMETER", "LocationMap")

    # Panel geometry (bottom-left origin, per SPEC §4.2)
    # Bottom bar: y=5..13, left col x=5..95, right col x=100..287
    china_geom    = _rect_polygon(5,   127, 90, 78)   # (a) China
    province_geom = _rect_polygon(5,   22,  90, 62)   # (b) Province
    city_geom     = _rect_polygon(100, 22,  182, 155)  # (c) Detail

    china_mf    = layout.createMapFrame(china_geom,    china_map,    "China_MapFrame")
    province_mf = layout.createMapFrame(province_geom, province_map, "Province_MapFrame")  # noqa: F841
    city_mf     = layout.createMapFrame(city_geom,     city_map,     "City_MapFrame")     # noqa: F841

    # Title text element
    title_geom = _rect_polygon(100, 181, 182, 22)
    aprx.createTextElement(
        layout, title_geom,
        "RECTANGLE",
        cfg.get("title") or
        f"{cfg.get('province_name','')}{cfg.get('city_name','')}研究区区位图",
        "Title",
    )

    # North arrow (top-right of detail panel)
    _add_north_arrow_safe(layout, city_mf, arcpy)

    # Scale bar (bottom-left of detail panel)
    _add_scalebar_safe(layout, city_mf, arcpy)

    # Bottom info bar text
    bottom_geom = _rect_polygon(5, 5, 287, 8)
    aprx.createTextElement(
        layout, bottom_geom,
        "RECTANGLE",
        f"坐标系: WGS 1984 | 数据来源: GEE / 天地图 | 制图: Region Map Wizard",
        "DataSource",
    )

    return aprx, china_map, province_map, city_map, layout


# ── Symbolization helpers ─────────────────────────────────────────────────────

def _symbolize_layers(city_map, data_type: str, arcpy) -> None:
    """Apply colorizer to raster layers in the city map."""
    for lyr in city_map.listLayers():
        if not lyr.isRasterLayer:
            continue
        try:
            sym = lyr.symbology
            if data_type == "dem":
                sym.updateColorizer("RasterClassifyColorizer")
                sym.colorizer.classificationMethod = "EqualInterval"
                sym.colorizer.breakCount = 8
                # Apply a green-brown-white terrain palette if available
                try:
                    sym.colorizer.colorRamp = arcpy.mp.ListColorRamps(
                        "ArcGIS Colors", "Elevation #1"
                    )[0]
                except Exception:
                    pass
            elif data_type == "hillshade":
                sym.updateColorizer("RasterStretchColorizer")
                sym.colorizer.stretchType = "PercentClip"
                try:
                    sym.colorizer.colorRamp = arcpy.mp.ListColorRamps(
                        "ArcGIS Colors", "Black to White"
                    )[0]
                except Exception:
                    pass
            elif data_type == "sentinel2":
                sym.updateColorizer("RasterRGBColorizer")
                sym.colorizer.redBandIndex   = 1  # B4 Red
                sym.colorizer.greenBandIndex = 2  # B3 Green
                sym.colorizer.blueBandIndex  = 3  # B2 Blue
                sym.colorizer.stretchType    = "PercentClip"
            lyr.symbology = sym
        except Exception:
            pass  # symbology errors are non-fatal


def _highlight_boundary(map_obj, target_name: str, arcpy) -> None:
    """Highlight a named administrative boundary layer with red outline."""
    if not target_name:
        return
    for lyr in map_obj.listLayers():
        if lyr.isRasterLayer or not lyr.supports("SYMBOLOGY"):
            continue
        try:
            sym = lyr.symbology
            if hasattr(sym, "renderer") and hasattr(sym.renderer, "symbol"):
                sym.renderer.symbol.color = {"RGB": [255, 0, 0, 30]}
                sym.renderer.symbol.outlineColor = {"RGB": [255, 0, 0, 255]}
                sym.renderer.symbol.outlineWidth = 1.5
                lyr.symbology = sym
        except Exception:
            pass


# ── Map extent helpers ────────────────────────────────────────────────────────

def _set_map_extents(layout, cfg: dict, arcpy) -> None:
    """Zoom each map frame to its data extent."""
    for mf_name, lyr_key in [
        ("China_MapFrame",    "country_boundary"),
        ("Province_MapFrame", "province_boundary"),
        ("City_MapFrame",     "city_boundary"),
    ]:
        try:
            mf_list = layout.listElements("MAPFRAME_ELEMENT", mf_name)
            if not mf_list:
                continue
            mf = mf_list[0]
            lyr_path = cfg.get(lyr_key, "")
            if not lyr_path or not Path(lyr_path).exists():
                continue
            lyrs = mf.map.listLayers()
            if lyrs:
                ext = mf.getLayerExtent(lyrs[-1], False, True)
                mf.camera.setExtent(ext)
                mf.camera.scale *= 1.15  # add small border
        except Exception:
            pass


# ── Text / grid helpers ───────────────────────────────────────────────────────

def _update_text(layout, cfg: dict, arcpy) -> None:
    """Update Title and DataSource text elements if they exist."""
    province_name = cfg.get("province_name", "")
    city_name = cfg.get("city_name", "")
    title_text = cfg.get("title") or f"{province_name}{city_name}研究区区位图"

    for elm in layout.listElements("TEXT_ELEMENT"):
        if elm.name == "Title":
            elm.text = title_text
        elif elm.name == "DataSource":
            elm.text = (
                "坐标系: WGS 1984 | 数据来源: GEE / 天地图 | 制图: Region Map Wizard"
            )


def _set_grid_spacing(layout, arcpy) -> None:
    """Set graticule spacing on City_MapFrame via CIM Access (SPEC §4.3.5)."""
    try:
        lyt_cim = layout.getDefinition("V3")
        for elm in lyt_cim.elements:
            if getattr(elm, "name", "") == "City_MapFrame":
                grids = getattr(elm, "grids", [])
                for grid in grids:
                    try:
                        grid.gridLineOrigin.x = 0.5  # longitude interval °
                        grid.gridLineOrigin.y = 0.5  # latitude interval °
                    except Exception:
                        pass
        layout.setDefinition(lyt_cim)
    except Exception:
        pass  # CIM modifications are best-effort


# ── Map surround element helpers ──────────────────────────────────────────────

def _add_north_arrow_safe(layout, map_frame, arcpy) -> None:
    try:
        style_items = arcpy.mp.ListStyleItems("ArcGIS 2D", "North_Arrow", "Compass North 1")
        if style_items:
            na_geom = _rect_polygon(253, 155, 15, 20)
            layout.createMapSurroundElement(
                na_geom, "NORTH_ARROW", map_frame, style_items[0], "NorthArrow"
            )
    except Exception:
        pass


def _add_scalebar_safe(layout, map_frame, arcpy) -> None:
    try:
        style_items = arcpy.mp.ListStyleItems("ArcGIS 2D", "Scale_bar", "Alternating Scale Bar 1")
        if style_items:
            sb_geom = _rect_polygon(102, 24, 60, 8)
            layout.createMapSurroundElement(
                sb_geom, "SCALE_BAR", map_frame, style_items[0], "ScaleBar"
            )
    except Exception:
        pass


# ── Layer loading helpers ─────────────────────────────────────────────────────

def _add_layer_safe(map_obj, lyr_path: str, arcpy) -> None:
    if lyr_path and Path(lyr_path).exists():
        try:
            map_obj.addDataFromPath(lyr_path)
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
