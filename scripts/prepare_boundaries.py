"""
Prepare china_admin.gpkg from raw boundary sources.

Usage
-----
    python scripts/prepare_boundaries.py --input <raw_dir> --output src/data/china_admin.gpkg

Expected raw data layout
------------------------
    <raw_dir>/
        country.geojson          # China national boundary + nine-dash line
        province/
            *.geojson            # One file per province (or a single merged file)
        city/
            *.geojson            # One file per city (or a single merged file)

Data sources
------------
1. 天地图行政区划数据 GS(2024)0650
   https://www.tianditu.gov.cn/
2. 或使用 GADM data (https://gadm.org/) as a starting point, then overlay
   China's official nine-dash line from authoritative sources.

Output schema
-------------
Layer "country":
    name TEXT, name_en TEXT
    geometry MultiPolygon  EPSG:4326

Layer "province":
    adcode CHAR(6), name TEXT, name_en TEXT,
    center_lon REAL, center_lat REAL
    geometry MultiPolygon  EPSG:4326

Layer "city":
    adcode CHAR(6), province_adcode CHAR(6),
    name TEXT, name_en TEXT,
    center_lon REAL, center_lat REAL
    geometry MultiPolygon  EPSG:4326

Layer "nine_dash_line":
    name TEXT
    geometry MultiLineString  EPSG:4326
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import geopandas as gpd
    from shapely.ops import unary_union
except ImportError:
    print("请先安装依赖: pip install geopandas shapely", file=sys.stderr)
    sys.exit(1)


def _read_geojsons(directory: Path) -> gpd.GeoDataFrame:
    frames = [gpd.read_file(f) for f in sorted(directory.glob("*.geojson"))]
    if not frames:
        raise FileNotFoundError(f"未在 {directory} 找到任何 .geojson 文件")
    return gpd.pd.concat(frames, ignore_index=True)


def build_gpkg(raw_dir: Path, output: Path) -> None:
    raw_dir = Path(raw_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print("加载国界数据...")
    country_file = raw_dir / "country.geojson"
    if not country_file.exists():
        raise FileNotFoundError(f"找不到国界文件: {country_file}")
    country = gpd.read_file(country_file).to_crs(epsg=4326)
    country.to_file(output, layer="country", driver="GPKG")
    print(f"  → country 图层写入完毕 ({len(country)} 个要素)")

    print("加载省级数据...")
    province_dir = raw_dir / "province"
    if province_dir.is_dir():
        province = _read_geojsons(province_dir).to_crs(epsg=4326)
    else:
        province_file = raw_dir / "province.geojson"
        province = gpd.read_file(province_file).to_crs(epsg=4326)
    # Ensure adcode is string
    if "adcode" in province.columns:
        province["adcode"] = province["adcode"].astype(str).str.zfill(6)
    province.to_file(output, layer="province", driver="GPKG")
    print(f"  → province 图层写入完毕 ({len(province)} 个要素)")

    print("加载市级数据...")
    city_dir = raw_dir / "city"
    if city_dir.is_dir():
        city = _read_geojsons(city_dir).to_crs(epsg=4326)
    else:
        city_file = raw_dir / "city.geojson"
        city = gpd.read_file(city_file).to_crs(epsg=4326)
    if "adcode" in city.columns:
        city["adcode"] = city["adcode"].astype(str).str.zfill(6)
    if "province_adcode" not in city.columns and "adcode" in city.columns:
        city["province_adcode"] = city["adcode"].str[:2].str.ljust(6, "0")
    city.to_file(output, layer="city", driver="GPKG")
    print(f"  → city 图层写入完毕 ({len(city)} 个要素)")

    nine_dash_file = raw_dir / "nine_dash_line.geojson"
    if nine_dash_file.exists():
        print("加载九段线数据...")
        ndl = gpd.read_file(nine_dash_file).to_crs(epsg=4326)
        ndl.to_file(output, layer="nine_dash_line", driver="GPKG")
        print(f"  → nine_dash_line 图层写入完毕 ({len(ndl)} 个要素)")

    print(f"\n完成！GeoPackage 已保存到: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 china_admin.gpkg")
    parser.add_argument("--input", required=True, help="原始数据目录")
    parser.add_argument(
        "--output",
        default="src/data/china_admin.gpkg",
        help="输出路径 (默认 src/data/china_admin.gpkg)",
    )
    args = parser.parse_args()
    build_gpkg(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
