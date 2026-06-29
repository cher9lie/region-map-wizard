"""Google Earth Engine data fetcher with tile-download and caching support."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable, Optional

from src.constants import (
    DEM_DOWNLOAD_SCALE,
    DOWNLOAD_MAX_RETRIES,
    DOWNLOAD_TIMEOUT,
    GEE_S2_ASSET,
    GEE_SRTM_ASSET,
    HILLSHADE_DOWNLOAD_SCALE,
    MAX_TILE_PIXELS,
    SENTINEL2_DOWNLOAD_SCALE,
)
from src.core.exceptions import GEEAuthFailedError, GEEDownloadFailedError, GEEQuotaExceededError

ProgressCallback = Optional[Callable[[int, str], None]]

# Lazy imports — ee / geemap may not be installed in every environment
try:
    import ee
    import geemap
    _EE_AVAILABLE = True
except ImportError:
    ee = None       # type: ignore[assignment]
    geemap = None   # type: ignore[assignment]
    _EE_AVAILABLE = False


def _report(cb: ProgressCallback, pct: int, msg: str) -> None:
    if cb is not None:
        cb(pct, msg)


class GEEFetcher:
    """Fetch DEM, Hillshade, and Sentinel-2 imagery from Google Earth Engine."""

    def __init__(self, project_id: str, cache_dir: Path) -> None:
        self._project_id = project_id
        self._cache_dir = Path(cache_dir)
        self._authenticated = False

    # ── Auth ───────────────────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Step 1: OAuth browser flow — always forces a fresh browser login."""
        if not _EE_AVAILABLE:
            raise GEEAuthFailedError("earthengine-api 未安装")
        try:
            # force=True: skip "valid credentials" cache so the browser always opens.
            # auth_mode='localhost': use Python's local redirect server, avoids gcloud
            # dependency and works reliably in a desktop GUI.
            ee.Authenticate(auth_mode="localhost", force=True)
            return True
        except Exception as exc:
            raise GEEAuthFailedError(str(exc)) from exc

    def initialize(self, project_id: str) -> bool:
        """Step 2: Initialize EE with the chosen Cloud project."""
        if not _EE_AVAILABLE:
            raise GEEAuthFailedError("earthengine-api 未安装")
        try:
            ee.Initialize(project=project_id)
            self._project_id = project_id
            self._authenticated = True
            return True
        except Exception as exc:
            raise GEEAuthFailedError(str(exc)) from exc

    def is_authenticated(self) -> bool:
        if self._authenticated:
            return True
        if not _EE_AVAILABLE or not self._project_id:
            return False
        try:
            ee.Initialize(project=self._project_id)
            self._authenticated = True
            return True
        except Exception:
            return False

    def has_credentials(self) -> bool:
        """True if the OAuth credentials file exists (user has logged in before)."""
        return (Path.home() / ".config" / "earthengine" / "credentials").exists()

    # ── Public fetch methods ───────────────────────────────────────────────────

    def fetch_dem(
        self,
        geometry: "ee.Geometry",
        output_path: Path,
        progress_callback: ProgressCallback = None,
    ) -> Path:
        """Download SRTM DEM clipped to geometry."""
        self._ensure_auth()
        _report(progress_callback, 0, "准备 DEM 下载...")
        image = ee.Image(GEE_SRTM_ASSET).select("elevation")
        return self._download_with_tiles(
            image, geometry, output_path,
            scale=DEM_DOWNLOAD_SCALE,
            progress_callback=progress_callback,
        )

    def fetch_hillshade(
        self,
        geometry: "ee.Geometry",
        output_path: Path,
        progress_callback: ProgressCallback = None,
    ) -> Path:
        """Download hillshade derived from SRTM."""
        self._ensure_auth()
        _report(progress_callback, 0, "准备山体阴影下载...")
        dem = ee.Image(GEE_SRTM_ASSET)
        image = ee.Terrain.hillshade(dem)
        return self._download_with_tiles(
            image, geometry, output_path,
            scale=HILLSHADE_DOWNLOAD_SCALE,
            progress_callback=progress_callback,
        )

    def fetch_sentinel2(
        self,
        geometry: "ee.Geometry",
        output_path: Path,
        year_range: int = 1,
        cloud_max: int = 20,
        progress_callback: ProgressCallback = None,
    ) -> Path:
        """Download Sentinel-2 true-colour median composite."""
        self._ensure_auth()
        _report(progress_callback, 0, "准备 Sentinel-2 下载...")
        import datetime

        end = datetime.date.today()
        start = end.replace(year=end.year - year_range)

        collection = (
            ee.ImageCollection(GEE_S2_ASSET)
            .filterBounds(geometry)
            .filterDate(str(start), str(end))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
            .select(["B4", "B3", "B2"])
        )
        image = collection.median().divide(10000).clamp(0, 0.3).multiply(255 / 0.3).toUint8()
        return self._download_with_tiles(
            image, geometry, output_path,
            scale=SENTINEL2_DOWNLOAD_SCALE,
            progress_callback=progress_callback,
        )

    # ── Tile download logic ────────────────────────────────────────────────────

    def _download_with_tiles(
        self,
        image: "ee.Image",
        geometry: "ee.Geometry",
        output_path: Path,
        scale: int,
        progress_callback: ProgressCallback = None,
    ) -> Path:
        """Tile-based download: split large areas, merge, then clip."""
        import rasterio
        from rasterio.merge import merge as rio_merge
        from rasterio.mask import mask as rio_mask
        import geopandas as gpd
        from shapely.geometry import box, mapping

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        bounds = geometry.bounds().getInfo()["coordinates"][0]
        xs = [p[0] for p in bounds]
        ys = [p[1] for p in bounds]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)

        # Estimate pixel count
        width_px = (xmax - xmin) * 111_320 / scale
        height_px = (ymax - ymin) * 110_574 / scale
        total_px = width_px * height_px

        tiles = self._make_tiles(xmin, ymin, xmax, ymax, total_px, scale)
        _report(progress_callback, 5, f"分片下载 ({len(tiles)} 个 tile)...")

        tile_paths: list[Path] = []
        tmp_dir = output_path.parent / "_tiles"
        tmp_dir.mkdir(exist_ok=True)

        for idx, (tx0, ty0, tx1, ty1) in enumerate(tiles):
            pct = 5 + int(80 * idx / len(tiles))
            _report(progress_callback, pct, f"下载 tile {idx + 1}/{len(tiles)}...")
            tile_geom = ee.Geometry.BBox(tx0, ty0, tx1, ty1)
            tile_path = tmp_dir / f"tile_{idx:04d}.tif"
            self._download_single(image, tile_geom, tile_path, scale)
            tile_paths.append(tile_path)

        _report(progress_callback, 88, "合并 tiles...")
        if len(tile_paths) == 1:
            tile_paths[0].rename(output_path)
        else:
            datasets = [rasterio.open(p) for p in tile_paths]
            merged, transform = rio_merge(datasets)
            meta = datasets[0].meta.copy()
            meta.update(
                width=merged.shape[2],
                height=merged.shape[1],
                transform=transform,
            )
            for ds in datasets:
                ds.close()
            with rasterio.open(output_path, "w", **meta) as dst:
                dst.write(merged)
            for p in tile_paths:
                p.unlink(missing_ok=True)

        _report(progress_callback, 95, "裁剪到研究区...")
        geo_shape = geometry.getInfo()
        with rasterio.open(output_path) as src:
            clipped, clipped_transform = rio_mask(
                src, [geo_shape], crop=True, nodata=src.nodata
            )
            meta = src.meta.copy()
        meta.update(
            width=clipped.shape[2],
            height=clipped.shape[1],
            transform=clipped_transform,
        )
        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(clipped)

        try:
            tmp_dir.rmdir()
        except OSError:
            pass

        _report(progress_callback, 100, "下载完成")
        return output_path

    def _make_tiles(
        self,
        xmin: float, ymin: float, xmax: float, ymax: float,
        total_px: float, scale: int,
    ) -> list[tuple[float, float, float, float]]:
        """Split bounding box into tiles each below MAX_TILE_PIXELS."""
        if total_px <= MAX_TILE_PIXELS:
            return [(xmin, ymin, xmax, ymax)]

        n_tiles = math.ceil(total_px / MAX_TILE_PIXELS)
        cols = max(1, math.ceil(math.sqrt(n_tiles)))
        rows = max(1, math.ceil(n_tiles / cols))
        dx = (xmax - xmin) / cols
        dy = (ymax - ymin) / rows

        tiles = []
        for r in range(rows):
            for c in range(cols):
                tiles.append((
                    xmin + c * dx,
                    ymin + r * dy,
                    xmin + (c + 1) * dx,
                    ymin + (r + 1) * dy,
                ))
        return tiles

    def _download_single(
        self,
        image: "ee.Image",
        geometry: "ee.Geometry",
        output_path: Path,
        scale: int,
    ) -> None:
        """Download one tile with retry/back-off."""
        last_exc: Exception | None = None
        for attempt in range(DOWNLOAD_MAX_RETRIES):
            try:
                geemap.download_ee_image(
                    image,
                    filename=str(output_path),
                    region=geometry,
                    scale=scale,
                    crs="EPSG:4326",
                    overwrite=True,
                )
                return
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                if "quota" in err_str or "resource exhausted" in err_str:
                    raise GEEQuotaExceededError(str(exc)) from exc
                # Don't retry if it's a clear auth/project error
                if any(k in err_str for k in ("not enabled", "permission denied", "unauthenticated", "forbidden")):
                    break
                if attempt < DOWNLOAD_MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)

        raise GEEDownloadFailedError(str(last_exc)) from last_exc

    # ── Private helpers ────────────────────────────────────────────────────────

    def _ensure_auth(self) -> None:
        if not self.is_authenticated():
            raise GEEAuthFailedError()
