"""Boundary manager — loads china_admin.gpkg and answers spatial queries."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
from shapely.geometry import box

from src.core.exceptions import (
    BoundaryNotFoundError,
    InvalidSHPError,
    SHPCRSError,
    SHPGeometryTypeError,
    SHPMissingFilesError,
)

_DATA_DIR = Path(__file__).parent.parent / "data"
_DEFAULT_GPKG = _DATA_DIR / "china_admin.gpkg"
_DEFAULT_CITIES_JSON = _DATA_DIR / "cities.json"

# Companion files required by GDAL/Fiona to read a Shapefile correctly.
_SHP_REQUIRED = (".shx", ".dbf")
_SHP_OPTIONAL = (".prj", ".cpg", ".sbn", ".sbx", ".qix")


def read_shp_safe(path: Path) -> gpd.GeoDataFrame:
    """Read a Shapefile, transparently handling non-ASCII (e.g. Chinese) paths.

    On Windows, GDAL/Fiona may fail to open paths that contain characters
    outside the system ANSI code page.  When a non-ASCII path is detected all
    companion files (*.shx, *.dbf, *.prj, *.cpg …) are copied to a temporary
    ASCII directory, read from there, and the temp directory is cleaned up
    before returning.

    Raises:
        InvalidSHPError: if the file cannot be opened for any reason.
    """
    path = Path(path)

    # Fast path: pure-ASCII paths — try directly first.
    try:
        path.as_posix().encode("ascii")
        _needs_copy = False
    except UnicodeEncodeError:
        _needs_copy = True

    if not _needs_copy:
        try:
            return gpd.read_file(path)
        except Exception as exc:
            raise InvalidSHPError(str(exc)) from exc

    # Non-ASCII path: copy all files that share the same stem to a temp dir.
    tmpdir = Path(tempfile.mkdtemp(prefix="rmw_shp_"))
    try:
        stem_lower = path.stem.lower()
        copied_shp: Optional[Path] = None
        for f in path.parent.iterdir():
            if f.stem.lower() == stem_lower:
                dest = tmpdir / ("shp" + f.suffix.lower())
                shutil.copy2(f, dest)
                if f.suffix.lower() == ".shp":
                    copied_shp = dest

        if copied_shp is None or not copied_shp.exists():
            raise InvalidSHPError("将 SHP 文件复制到临时目录时失败，请检查文件权限")

        try:
            return gpd.read_file(copied_shp)
        except Exception as exc:
            raise InvalidSHPError(str(exc)) from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

        Returns (valid, human-readable message, GeoDataFrame or None).
        Raises InvalidSHPError (or a subclass) for hard failures that the
        caller cannot recover from.  Returns (False, msg, None) for soft
        failures the user can fix by choosing a different file.
        """
        shp_path = Path(shp_path)

        # ── 1. Extension ──────────────────────────────────────────────────────
        if shp_path.suffix.lower() != ".shp":
            raise InvalidSHPError(
                f"请选择 .shp 文件，当前选择的是 {shp_path.suffix!r} 文件"
            )

        # ── 2. File exists ────────────────────────────────────────────────────
        if not shp_path.exists():
            raise InvalidSHPError(f"文件不存在: {shp_path.name}")

        # ── 3. Required companion files (.shx, .dbf) ──────────────────────────
        missing: list[str] = []
        for ext in _SHP_REQUIRED:
            # Use with_suffix so Windows case-insensitivity handles .SHX etc.
            companion = shp_path.with_suffix(ext)
            if not companion.exists():
                missing.append(ext)
        if missing:
            raise SHPMissingFilesError(missing)

        # ── 4. Optional .prj warning (not a hard error — CRS may still parse) ─
        has_prj = shp_path.with_suffix(".prj").exists()

        # ── 5. Read file (handles non-ASCII / Chinese paths automatically) ────
        # InvalidSHPError is raised internally by read_shp_safe on failure.
        gdf = read_shp_safe(shp_path)

        # ── 6. Non-empty geometry ─────────────────────────────────────────────
        if gdf.empty:
            return False, "SHP 文件中没有任何要素（空文件）", None
        if gdf.geometry.is_empty.all() or gdf.geometry.isna().all():
            return False, "SHP 文件中所有几何要素均为空", None

        # ── 7. Geometry type must be polygon ──────────────────────────────────
        geom_types = set(gdf.geometry.geom_type.dropna().unique())
        polygon_types = {"Polygon", "MultiPolygon"}
        if not geom_types & polygon_types:
            raise SHPGeometryTypeError("、".join(sorted(geom_types)) or "Unknown")

        # ── 8. CRS present ────────────────────────────────────────────────────
        if gdf.crs is None:
            if not has_prj:
                raise SHPCRSError("缺少 .prj 投影文件，无法确定坐标系，请添加后重试")
            raise SHPCRSError(".prj 文件存在但坐标系无法识别")

        # ── 9. Reproject to WGS-84 if needed ─────────────────────────────────
        if gdf.crs.to_epsg() != 4326:
            try:
                gdf = gdf.to_crs(epsg=4326)
            except Exception as exc:
                raise SHPCRSError(f"投影转换失败 ({gdf.crs.to_string()} → EPSG:4326): {exc}") from exc

        # ── 10. Sanity-check reprojected bounds ───────────────────────────────
        b = gdf.total_bounds  # [minx, miny, maxx, maxy]
        if not (-180 <= b[0] < b[2] <= 180 and -90 <= b[1] < b[3] <= 90):
            return False, (
                f"坐标超出合理范围 (minx={b[0]:.2f}, miny={b[1]:.2f}, "
                f"maxx={b[2]:.2f}, maxy={b[3]:.2f})，请确认坐标系是否正确"
            ), None

        # ── 11. Summary info ──────────────────────────────────────────────────
        span = max(b[2] - b[0], b[3] - b[1])
        try:
            area_km2 = gdf.to_crs("EPSG:3857").area.sum() / 1e6
            area_str = f"面积约 {area_km2:,.0f} km²"
        except Exception:
            area_str = f"跨度 {span:.2f}°"

        msg = f"有效 ({len(gdf)} 个面要素，{area_str})"
        return True, msg, gdf

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
