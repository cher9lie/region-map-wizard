"""
Convert tianditu-format GeoJSON files to china_admin.gpkg.

Input files (place in region-map-tool/ root or specify via --input-dir):
    中国_省.geojson   — province boundaries, gb field = "156" + 6-digit adcode
    中国_市.geojson   — city boundaries, same gb format
    中国_县.geojson   — county boundaries (optional, not used)

Output: src/data/china_admin.gpkg with layers country / province / city
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import geopandas as gpd
    import pandas as pd
    from shapely.ops import unary_union
except ImportError:
    print("请先安装: pip install geopandas shapely", file=sys.stderr)
    sys.exit(1)

TARGET_CRS = "EPSG:4326"

# adcodes that are NOT standard mainland provinces but appear in 省 file
# (台湾 710000, 香港 810000, 澳门 820000 are kept; 境界线 has empty gb → filtered)
_MAINLAND_ONLY = False  # set True to exclude TW/HK/MO from country dissolve


def _strip_gb(gb_series: pd.Series) -> pd.Series:
    """Strip leading '156' country prefix from gb codes."""
    s = gb_series.astype(str).str.strip()
    # gb looks like '156110000' → '110000'
    return s.where(~s.str.startswith("156"), s.str[3:])


def build_gpkg(input_dir: Path, output: Path) -> None:
    input_dir = Path(input_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # ── Province layer ────────────────────────────────────────────────────────
    print("读取省级数据…")
    prov_raw = gpd.read_file(input_dir / "中国_省.geojson")
    # Filter out non-boundary features (境界线, empty gb)
    prov = prov_raw[
        prov_raw["gb"].notna() & (prov_raw["gb"] != "") & (prov_raw["name"] != "境界线")
    ].copy()
    prov["adcode"] = _strip_gb(prov["gb"])
    prov = prov.rename(columns={"name": "name"})
    prov = prov[["adcode", "name", "geometry"]].to_crs(TARGET_CRS)
    # Fix any invalid geometries
    prov["geometry"] = prov["geometry"].buffer(0)
    print(f"  省级要素: {len(prov)} 个")

    # ── Country layer — dissolve all provinces ────────────────────────────────
    print("生成国界图层（dissolve 省级边界）…")
    country_geom = unary_union(prov.geometry)
    country = gpd.GeoDataFrame(
        {"name": ["中华人民共和国"], "name_en": ["China"]},
        geometry=[country_geom],
        crs=TARGET_CRS,
    )

    # ── City layer ────────────────────────────────────────────────────────────
    print("读取市级数据…")
    city_raw = gpd.read_file(input_dir / "中国_市.geojson")
    city = city_raw[
        city_raw["gb"].notna() & (city_raw["gb"] != "") & (city_raw["name"] != "境界线")
    ].copy()
    city["adcode"] = _strip_gb(city["gb"])
    city["province_adcode"] = city["adcode"].str[:2] + "0000"
    city = city[["adcode", "province_adcode", "name", "geometry"]].to_crs(TARGET_CRS)
    city["geometry"] = city["geometry"].buffer(0)

    # ── District layer for direct-controlled municipalities ───────────────────
    # 北京110/天津120/上海310/重庆500: replace single-city entry with actual districts
    ZHIXIA = {"110000", "120000", "310000", "500000"}
    city = city[~city["province_adcode"].isin(ZHIXIA)].copy()

    county_path = input_dir / "中国_县.geojson"
    if county_path.exists():
        print("读取县/区级数据（直辖市用）…")
        county_raw = gpd.read_file(county_path)
        county = county_raw[
            county_raw["gb"].notna() & (county_raw["gb"] != "") & (county_raw["name"] != "境界线")
        ].copy()
        county["adcode"] = _strip_gb(county["gb"])
        county["province_adcode"] = county["adcode"].str[:2] + "0000"
        zhixia_districts = county[county["province_adcode"].isin(ZHIXIA)].copy()
        zhixia_districts = zhixia_districts[["adcode", "province_adcode", "name", "geometry"]].to_crs(TARGET_CRS)
        zhixia_districts["geometry"] = zhixia_districts["geometry"].buffer(0)
        city = pd.concat([city, zhixia_districts], ignore_index=True)
        print(f"  直辖市区级要素: {len(zhixia_districts)} 个")

    print(f"  市级要素合计: {len(city)} 个")

    # ── Write GPKG ────────────────────────────────────────────────────────────
    if output.exists():
        output.unlink()

    print(f"\n写入 {output} …")
    country.to_file(output, layer="country", driver="GPKG")
    print(f"  [OK] country   ({len(country)} 要素)")
    prov.to_file(output, layer="province", driver="GPKG")
    print(f"  [OK] province  ({len(prov)} 要素)")
    city.to_file(output, layer="city", driver="GPKG")
    print(f"  [OK] city      ({len(city)} 要素)")

    # nine_dash_line: create empty placeholder so gpkg is schema-complete
    ndl = gpd.GeoDataFrame({"name": pd.Series([], dtype=str)}, geometry=[], crs=TARGET_CRS)
    ndl.to_file(output, layer="nine_dash_line", driver="GPKG")
    print("  [OK] nine_dash_line (空占位层)")

    print(f"\n完成！→ {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="天地图 GeoJSON → china_admin.gpkg")
    parser.add_argument(
        "--input-dir",
        default=".",
        help="含有 中国_省/市/县.geojson 的目录（默认当前目录）",
    )
    parser.add_argument(
        "--output",
        default="src/data/china_admin.gpkg",
        help="输出路径（默认 src/data/china_admin.gpkg）",
    )
    args = parser.parse_args()
    build_gpkg(Path(args.input_dir), Path(args.output))


if __name__ == "__main__":
    main()
