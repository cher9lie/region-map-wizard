"""Main pipeline: validates config, fetches data, calls renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from src.core.boundary_manager import BoundaryManager
from src.core.cache_manager import CacheManager
from src.core.config_manager import ConfigManager
from src.core.data_processor import DataProcessor
from src.core.gee_fetcher import GEEFetcher
from src.core.exceptions import BoundaryNotFoundError, RenderFailedError
from src.renderers.base import BaseRenderer, RenderConfig
from src.constants import DEFAULT_CACHE_DIR_NAME

ProgressCallback = Optional[Callable[[int, str], None]]
LogCallback = Optional[Callable[[str], None]]

_DATA_DIR = Path(__file__).parent.parent / "data"


class MapWizardPipeline:
    """Orchestrate the full workflow: boundary → GEE download → render."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self._cfg = config_manager

        cache_dir_str = self._cfg.get("cache_dir", "")
        cache_dir = (
            Path(cache_dir_str)
            if cache_dir_str
            else Path.home() / DEFAULT_CACHE_DIR_NAME
        )

        self.boundary_mgr = BoundaryManager(
            gpkg_path=_DATA_DIR / "china_admin.gpkg",
            cities_json_path=_DATA_DIR / "cities.json",
        )
        self.gee_fetcher = GEEFetcher(
            project_id=self._cfg.get("gee_project_id", ""),
            cache_dir=cache_dir,
        )
        self.cache_mgr = CacheManager(cache_dir)
        self.data_proc = DataProcessor()

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(
        self,
        config: RenderConfig,
        progress_callback: ProgressCallback = None,
        log_callback: LogCallback = None,
    ) -> Path:
        """Run the full pipeline.

        Progress milestones (percent):
            0-5   Validate
            5-10  Fetch boundaries
            10-60 GEE download / cache
            60-95 Render
            95-100 Write output
        """

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        def _log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        # Step 1 — Validate
        _p(0, "验证输入参数...")
        errors = self.validate_config(config)
        if errors:
            raise ValueError("配置无效: " + "; ".join(errors))
        _log("参数验证通过")

        # Step 2 — Boundaries
        _p(5, "获取行政区边界...")
        adcode = self._resolve_adcode(config)
        _log(f"行政区 adcode: {adcode}")
        # Renderer reads directly from the GPKG; no GeoJSON export needed.
        # province_adcode / city_adcode on the config drive per-layer filtering.
        _log("边界数据准备完成")

        # Step 3 — Raster data
        if config.data_type and config.data_type != "none":
            _p(10, "检查缓存...")
            year = None
            if config.data_type == "sentinel2":
                import datetime
                year = datetime.date.today().year

            cached = self.cache_mgr.get_cached(adcode, config.data_type, year=year)
            if cached:
                _log(f"命中缓存: {cached}")
                config = _replace(config, raster_path=cached)
                _p(60, "使用缓存数据")
            else:
                _p(10, "从 GEE 下载数据...")
                cache_path = self.cache_mgr.get_cache_path(
                    adcode, config.data_type, year=year
                )
                from shapely.geometry import mapping
                geom = None
                geom_error = ""
                try:
                    import ee
                    if not self.gee_fetcher.is_authenticated():
                        raise RuntimeError("GEE 未登录，请先完成 GEE 认证设置")
                    if config.custom_shp:
                        from src.core.boundary_manager import read_shp_safe
                        shp = read_shp_safe(Path(config.custom_shp))
                        if shp.crs and shp.crs.to_epsg() != 4326:
                            shp = shp.to_crs(epsg=4326)
                        geom = ee.Geometry(mapping(shp.unary_union))
                    else:
                        city_gdf = self.boundary_mgr.get_boundary(adcode, "city")
                        geom = ee.Geometry(mapping(city_gdf.unary_union))
                except Exception as e:
                    geom_error = str(e)

                if geom is not None:
                    raster_path = self._download_raster(
                        config, geom, cache_path,
                        lambda pct, msg: _p(10 + int(pct * 0.5), msg),
                    )
                    config = _replace(config, raster_path=raster_path)
                    _log("GEE 数据下载完成")
                else:
                    raise RuntimeError(geom_error or "无法获取研究区几何范围，跳过栅格下载")

        # Step 4 — Render
        _p(60, "调用渲染引擎...")
        renderer = self._select_renderer(self._cfg.get("last_renderer", "qgis"))
        available, reason = renderer.check_available()
        if not available:
            raise RenderFailedError(f"渲染引擎不可用: {reason}")

        def render_progress(pct: int, msg: str) -> None:
            _p(60 + int(pct * 0.35), msg)

        output = renderer.render(config, progress_callback=render_progress)
        _log(f"渲染完成: {output}")

        # Step 5 — Done
        _p(100, "输出完成")
        return output

    def validate_config(self, config: RenderConfig) -> list[str]:
        """Return a list of validation error strings (empty = OK)."""
        errors: list[str] = []

        if not config.output_path:
            errors.append("未指定输出路径")

        if config.output_format.lower() not in ("jpg", "jpeg", "png", "pdf", "tiff", "svg"):
            errors.append(f"不支持的输出格式: {config.output_format}")

        if config.dpi < 72 or config.dpi > 1200:
            errors.append(f"DPI 超出范围 [72, 1200]: {config.dpi}")

        if config.data_type not in ("dem", "hillshade", "sentinel2", "none", ""):
            errors.append(f"未知数据类型: {config.data_type}")

        if config.custom_shp and not Path(config.custom_shp).exists():
            errors.append(f"自定义 SHP 文件不存在: {config.custom_shp}")

        return errors

    def _select_renderer(self, engine_name: str) -> BaseRenderer:
        name = engine_name.lower()
        if name == "qgis":
            from src.renderers.qgis_renderer import QGISRenderer
            return QGISRenderer()
        if name in ("arcgis", "arcgis_pro"):
            from src.renderers.arcgis_renderer import ArcGISRenderer
            return ArcGISRenderer()
        if name == "cartopy":
            from src.renderers.cartopy_renderer import CartopyRenderer
            return CartopyRenderer()
        # Default fallback
        from src.renderers.cartopy_renderer import CartopyRenderer
        return CartopyRenderer()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _resolve_adcode(self, config: RenderConfig) -> str:
        """Derive the city adcode from config (city_boundary filename or name)."""
        if config.custom_shp:
            return "custom"
        # Infer from city_name via cities.json
        for prov in self.boundary_mgr._cities_data["provinces"]:
            for city in prov["cities"]:
                if city["name"] == config.city_name or city["name_en"] == config.city_name:
                    return city["adcode"]
        return "000000"

    def _export_boundaries(
        self, adcode: str, config: RenderConfig
    ) -> tuple[Path, Path, Path]:
        """Export boundary GeoDataFrames as GeoJSON for the renderer to load."""
        out_dir = Path(config.output_path).parent / ".rmw_boundaries"
        out_dir.mkdir(parents=True, exist_ok=True)

        country_path = out_dir / "country.geojson"
        province_path = out_dir / "province.geojson"
        city_path = out_dir / "city.geojson"

        try:
            country, province, city, _ = self.boundary_mgr.get_context_boundaries(adcode)
            country.to_file(country_path, driver="GeoJSON")
            province.to_file(province_path, driver="GeoJSON")
            city.to_file(city_path, driver="GeoJSON")
        except Exception:
            # If gpkg not available write empty files so renderer can handle gracefully
            _write_empty_geojson(country_path)
            _write_empty_geojson(province_path)
            _write_empty_geojson(city_path)

        return country_path, province_path, city_path

    def _download_raster(
        self,
        config: RenderConfig,
        geom,
        cache_path: Path,
        progress_cb: ProgressCallback,
    ) -> Path:
        if config.data_type == "dem":
            return self.gee_fetcher.fetch_dem(geom, cache_path, progress_cb)
        if config.data_type == "hillshade":
            return self.gee_fetcher.fetch_hillshade(geom, cache_path, progress_cb)
        if config.data_type == "sentinel2":
            yr = self._cfg.get("sentinel2_year_range", 1)
            cloud = self._cfg.get("sentinel2_cloud_max", 20)
            return self.gee_fetcher.fetch_sentinel2(
                geom, cache_path, year_range=yr, cloud_max=cloud,
                progress_callback=progress_cb,
            )
        return cache_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _replace(config: RenderConfig, **kwargs) -> RenderConfig:
    """Return a new RenderConfig with some fields replaced (poor-man's replace)."""
    import dataclasses
    return dataclasses.replace(config, **kwargs)


def _write_empty_geojson(path: Path) -> None:
    path.write_text(
        '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
    )
