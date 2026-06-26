"""Boundary manager — loads china_admin.gpkg and answers spatial queries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import geopandas as gpd
from shapely.geometry import box

from src.core.exceptions import BoundaryNotFoundError, InvalidSHPError

_DATA_DIR = Path(__file__).parent.parent / "data"
_DEFAULT_GPKG = _DATA_DIR / "china_admin.gpkg"
_DEFAULT_CITIES_JSON = _DATA_DIR / "cities.json"


class BoundaryManager:
    """Loads china_admin.gpkg and answers boundary / city-list queries."""

    def __init__(
        self,
        gpkg_path: Path = _DEFAULT_GPKG,
        cities_json_path: Path = _DEFAULT_CITIES_JSON,
    ) -> None:
        self._gpkg = Path(gpkg_path)
        self._cities_json = Path(cities_json_path)

        with self._cities_json.open(encoding="utf-8") as f:
            self._cities_data: dict = json.load(f)

        # Lazy-loaded layer cache
        self._layers: dict[str, gpd.GeoDataFrame] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_provinces(self) -> list[dict]:
        """Return [{adcode, name, name_en}, …] for all provinces."""
        return [
            {
                "adcode": p["adcode"],
                "name": p["name"],
                "name_en": p["name_en"],
                "center": p["center"],
            }
            for p in self._cities_data["provinces"]
        ]

    def list_cities(self, province_adcode: str) -> list[dict]:
        """Return city list for a given province adcode."""
        for prov in self._cities_data["provinces"]:
            if prov["adcode"] == province_adcode:
                return [
                    {
                        "adcode": c["adcode"],
                        "name": c["name"],
                        "name_en": c["name_en"],
                        "center": c["center"],
                    }
                    for c in prov["cities"]
                ]
        raise BoundaryNotFoundError(province_adcode)

    def get_boundary(self, adcode: str, level: str) -> gpd.GeoDataFrame:
        """Return the GeoDataFrame for a given adcode and level.

        level: 'country' | 'province' | 'city'
        """
        gdf = self._load_layer(level)
        if level == "country":
            return gdf

        field = "adcode" if level in ("province", "city") else "name"
        result = gdf[gdf[field] == adcode]
        if result.empty:
            raise BoundaryNotFoundError(adcode)
        return result

    def get_country_boundary(self) -> gpd.GeoDataFrame:
        """Return the full China country boundary layer."""
        return self._load_layer("country")

    def get_context_boundaries(
        self, city_adcode: str
    ) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
        """Return (country, province, city, all_provinces) GeoDataFrames.

        all_provinces is the full province layer (used for the China overview panel).
        """
        province_adcode = city_adcode[:2] + "0000"
        country = self.get_country_boundary()
        all_provinces = self._load_layer("province")
        province = self.get_boundary(province_adcode, "province")
        city = self.get_boundary(city_adcode, "city")
        return country, province, city, all_provinces

    def validate_custom_shp(
        self, shp_path: Path
    ) -> tuple[bool, str, Optional[gpd.GeoDataFrame]]:
        """Validate a user-supplied SHP file.

        Returns (valid, message, GeoDataFrame or None).
        Automatically reprojects to EPSG:4326 if needed.
        """
        shp_path = Path(shp_path)
        try:
            gdf = gpd.read_file(shp_path)
        except Exception as exc:
            raise InvalidSHPError(str(exc)) from exc

        if gdf.empty or gdf.geometry.is_empty.all():
            return False, "文件中没有有效几何要素", None

        if gdf.crs is None:
            return False, "SHP 文件缺少坐标参考系信息", None

        if gdf.crs.to_epsg() != 4326:
            try:
                gdf = gdf.to_crs(epsg=4326)
            except Exception as exc:
                return False, f"坐标系转换失败: {exc}", None

        return True, "有效", gdf

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_layer(self, layer: str) -> gpd.GeoDataFrame:
        if layer in self._layers:
            return self._layers[layer]

        if not self._gpkg.exists():
            raise FileNotFoundError(
                f"行政边界文件不存在: {self._gpkg}\n"
                "请运行 scripts/prepare_boundaries.py 生成该文件。"
            )

        gdf = gpd.read_file(self._gpkg, layer=layer)
        self._layers[layer] = gdf
        return gdf
