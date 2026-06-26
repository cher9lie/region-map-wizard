"""
Subprocess worker script — runs inside the ArcGIS Pro Python environment.

Called by ArcGISRenderer as:
    <arcgis_python.exe> _arcgis_worker.py <config_json_path>

Progress is reported to stdout as JSON lines:
    {"progress": 50, "message": "渲染中..."}
    {"progress": 100, "message": "完成", "output_path": "/path/to/output.jpg"}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _report(progress: int, message: str, output_path: str | None = None) -> None:
    payload: dict = {"progress": progress, "message": message}
    if output_path:
        payload["output_path"] = output_path
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: _arcgis_worker.py <config_json>", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    with config_path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    try:
        import arcpy
    except ImportError:
        _report(0, "arcpy 不可用")
        sys.exit(1)

    output_path = cfg.get("output_path", "output.jpg")
    output_fmt = cfg.get("output_format", "jpg").lower()

    _report(5, "创建 ArcGIS 项目...")
    aprx = arcpy.mp.ArcGISProject("CURRENT")

    _report(15, "创建布局...")
    layout = aprx.listLayouts()[0] if aprx.listLayouts() else aprx.createLayout(297, 210, "MILLIMETER")

    _report(30, "加载图层...")
    map_obj = aprx.listMaps()[0] if aprx.listMaps() else aprx.createMap("Map")

    country_path = cfg.get("country_boundary", "")
    province_path = cfg.get("province_boundary", "")
    city_path = cfg.get("city_boundary", "")
    raster_path = cfg.get("raster_path", "")

    for lyr_path in [country_path, province_path, city_path]:
        if lyr_path and Path(lyr_path).exists():
            map_obj.addDataFromPath(lyr_path)

    if raster_path and Path(raster_path).exists():
        map_obj.addDataFromPath(raster_path)

    _report(60, "设置地图框...")
    map_frames = layout.listElements("MAPFRAME_ELEMENT")
    if map_frames:
        map_frames[0].map = map_obj

    _report(80, "导出...")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if output_fmt == "pdf":
        layout.exportToPDF(output_path, resolution=int(cfg.get("dpi", 300)))
    elif output_fmt == "png":
        layout.exportToPNG(output_path, resolution=int(cfg.get("dpi", 300)))
    else:
        layout.exportToJPEG(output_path, resolution=int(cfg.get("dpi", 300)))

    _report(100, "完成", output_path=output_path)


if __name__ == "__main__":
    main()
