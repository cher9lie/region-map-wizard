"""Raster processing utilities: merge, clip, colour-ramp, normalise, stats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import geopandas as gpd


class DataProcessor:
    """Static helpers for raster manipulation used by the pipeline and renderers."""

    @staticmethod
    def merge_tiles(tile_paths: list[Path], output_path: Path) -> Path:
        """Merge multiple GeoTIFF tiles into a single file using rasterio."""
        import rasterio
        from rasterio.merge import merge as rio_merge

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        datasets = [rasterio.open(p) for p in tile_paths]
        try:
            merged, transform = rio_merge(datasets)
            meta = datasets[0].meta.copy()
            meta.update(
                width=merged.shape[2],
                height=merged.shape[1],
                transform=transform,
            )
        finally:
            for ds in datasets:
                ds.close()

        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(merged)
        return output_path

    @staticmethod
    def clip_to_boundary(
        raster_path: Path,
        boundary_gdf: "gpd.GeoDataFrame",
        output_path: Path,
    ) -> Path:
        """Clip a raster to the union of geometries in a GeoDataFrame."""
        import rasterio
        from rasterio.mask import mask as rio_mask

        raster_path = Path(raster_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(raster_path) as src:
            raster_crs = src.crs
            if boundary_gdf.crs and boundary_gdf.crs != raster_crs:
                boundary_gdf = boundary_gdf.to_crs(raster_crs)
            shapes = [geom.__geo_interface__ for geom in boundary_gdf.geometry if geom is not None]
            clipped, clipped_transform = rio_mask(src, shapes, crop=True, nodata=src.nodata)
            meta = src.meta.copy()

        meta.update(
            width=clipped.shape[2],
            height=clipped.shape[1],
            transform=clipped_transform,
        )
        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(clipped)
        return output_path

    @staticmethod
    def apply_color_ramp(raster_path: Path, color_ramp: dict) -> np.ndarray:
        """Map a single-band DEM raster to an RGBA array using a colour ramp."""
        import rasterio

        stops = sorted(color_ramp["stops"], key=lambda s: s["value"])
        stop_values = np.array([s["value"] for s in stops], dtype=float)
        stop_colors = np.array(
            [_hex_to_rgba(s["color"]) for s in stops], dtype=np.uint8
        )

        with rasterio.open(raster_path) as src:
            data = src.read(1).astype(float)
            nodata = src.nodata

        if nodata is not None:
            mask = data == nodata
        else:
            mask = np.zeros(data.shape, dtype=bool)

        height, width = data.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)

        for channel in range(4):
            interp = np.interp(data, stop_values, stop_colors[:, channel].astype(float))
            rgba[:, :, channel] = interp.astype(np.uint8)

        rgba[mask, 3] = 0
        return rgba

    @staticmethod
    def normalize_sentinel2(
        raster_path: Path,
        output_path: Path,
        min_val: float = 0,
        max_val: float = 3000,
    ) -> Path:
        """Stretch Sentinel-2 reflectance values to 0-255 uint8."""
        import rasterio

        raster_path = Path(raster_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(raster_path) as src:
            data = src.read().astype(float)
            meta = src.meta.copy()

        data = np.clip((data - min_val) / (max_val - min_val) * 255, 0, 255)
        meta.update(dtype="uint8")

        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(data.astype(np.uint8))
        return output_path

    @staticmethod
    def get_raster_extent(raster_path: Path) -> tuple[float, float, float, float]:
        """Return (xmin, ymin, xmax, ymax) in EPSG:4326."""
        import rasterio
        from rasterio.warp import transform_bounds

        with rasterio.open(raster_path) as src:
            if src.crs and src.crs.to_epsg() != 4326:
                bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            else:
                b = src.bounds
                bounds = (b.left, b.bottom, b.right, b.top)
        return bounds

    @staticmethod
    def get_raster_stats(raster_path: Path) -> dict[str, Any]:
        """Return basic stats for a raster file."""
        import rasterio

        with rasterio.open(raster_path) as src:
            data = src.read(1)
            nodata = src.nodata
            valid = data[data != nodata] if nodata is not None else data.ravel()
            return {
                "min": float(valid.min()) if valid.size else None,
                "max": float(valid.max()) if valid.size else None,
                "mean": float(valid.mean()) if valid.size else None,
                "nodata": nodata,
                "crs": str(src.crs),
                "shape": (src.height, src.width),
                "resolution": (abs(src.transform.a), abs(src.transform.e)),
            }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    """Convert '#RRGGBB' to (R, G, B, 255)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, 255
