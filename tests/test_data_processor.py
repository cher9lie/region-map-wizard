"""Tests for DataProcessor."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
import geopandas as gpd
from shapely.geometry import Polygon

from src.core.data_processor import DataProcessor, _hex_to_rgba

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_DEM = FIXTURES / "sample_dem.tif"
SAMPLE_BOUNDARY = FIXTURES / "sample_boundary.geojson"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_tif(path: Path, bands: int = 1, width: int = 20, height: int = 20,
              dtype: str = "float32", xmin=116.0, ymin=39.5,
              xmax=116.2, ymax=39.7, nodata=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    data = np.arange(bands * height * width, dtype=dtype).reshape(bands, height, width)
    kwargs = dict(
        driver="GTiff", height=height, width=width,
        count=bands, dtype=dtype, crs="EPSG:4326", transform=transform,
    )
    if nodata is not None:
        kwargs["nodata"] = nodata
    with rasterio.open(path, "w", **kwargs) as dst:
        dst.write(data)
    return path


# ---------------------------------------------------------------------------
# merge_tiles
# ---------------------------------------------------------------------------

class TestMergeTiles:
    def test_single_tile_passthrough(self, tmp_path):
        t1 = _make_tif(tmp_path / "t1.tif", xmin=116.0, xmax=116.2)
        out = tmp_path / "merged.tif"
        result = DataProcessor.merge_tiles([t1], out)
        assert result == out
        with rasterio.open(result) as src:
            assert src.width == 20

    def test_two_tiles_merged(self, tmp_path):
        t1 = _make_tif(tmp_path / "t1.tif", xmin=116.0, xmax=116.2, width=20)
        t2 = _make_tif(tmp_path / "t2.tif", xmin=116.2, xmax=116.4, width=20)
        out = tmp_path / "merged.tif"
        result = DataProcessor.merge_tiles([t1, t2], out)
        with rasterio.open(result) as src:
            assert src.width >= 20

    def test_output_created(self, tmp_path):
        t1 = _make_tif(tmp_path / "t1.tif")
        out = tmp_path / "sub" / "merged.tif"
        DataProcessor.merge_tiles([t1], out)
        assert out.exists()


# ---------------------------------------------------------------------------
# clip_to_boundary
# ---------------------------------------------------------------------------

class TestClipToBoundary:
    def test_clip_reduces_extent(self, tmp_path):
        src_tif = _make_tif(tmp_path / "big.tif",
                            xmin=116.0, ymin=39.5, xmax=117.0, ymax=40.5,
                            width=100, height=100)
        clip_poly = Polygon([(116.2, 39.7), (116.8, 39.7),
                              (116.8, 40.3), (116.2, 40.3)])
        gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[clip_poly], crs="EPSG:4326")
        out = tmp_path / "clipped.tif"
        DataProcessor.clip_to_boundary(src_tif, gdf, out)
        with rasterio.open(out) as dst:
            b = dst.bounds
            assert b.left >= 116.2 - 0.01
            assert b.right <= 116.8 + 0.01

    def test_clip_uses_sample_boundary(self, tmp_path):
        """Integration test against the real fixture files."""
        gdf = gpd.read_file(SAMPLE_BOUNDARY)
        out = tmp_path / "clipped.tif"
        DataProcessor.clip_to_boundary(SAMPLE_DEM, gdf, out)
        assert out.exists()
        with rasterio.open(out) as src:
            assert src.height > 0


# ---------------------------------------------------------------------------
# apply_color_ramp
# ---------------------------------------------------------------------------

COLOR_RAMP = {
    "stops": [
        {"value": 0,   "color": "#000000"},
        {"value": 500, "color": "#ffffff"},
    ]
}


class TestApplyColorRamp:
    def test_returns_rgba_array(self):
        rgba = DataProcessor.apply_color_ramp(SAMPLE_DEM, COLOR_RAMP)
        with rasterio.open(SAMPLE_DEM) as src:
            h, w = src.height, src.width
        assert rgba.shape == (h, w, 4)
        assert rgba.dtype == np.uint8

    def test_min_value_maps_to_black(self, tmp_path):
        tif = _make_tif(tmp_path / "zero.tif")
        # data is arange → all values >= 0; zero val → black
        rgba = DataProcessor.apply_color_ramp(tif, COLOR_RAMP)
        # First pixel should be close to black
        assert int(rgba[0, 0, 0]) < 10

    def test_max_value_maps_to_white(self, tmp_path):
        data = np.full((1, 10, 10), 500, dtype=np.float32)
        tif = tmp_path / "high.tif"
        transform = from_bounds(116.0, 39.5, 116.5, 40.0, 10, 10)
        with rasterio.open(tif, "w", driver="GTiff", height=10, width=10,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=transform) as dst:
            dst.write(data)
        rgba = DataProcessor.apply_color_ramp(tif, COLOR_RAMP)
        assert int(rgba[0, 0, 0]) == 255


# ---------------------------------------------------------------------------
# normalize_sentinel2
# ---------------------------------------------------------------------------

class TestNormalizeSentinel2:
    def test_output_is_uint8(self, tmp_path):
        src = _make_tif(tmp_path / "s2.tif", bands=3, dtype="float32")
        out = tmp_path / "s2_norm.tif"
        DataProcessor.normalize_sentinel2(src, out, min_val=0, max_val=400)
        with rasterio.open(out) as dst:
            assert dst.dtypes[0] == "uint8"

    def test_values_clipped_to_0_255(self, tmp_path):
        src = _make_tif(tmp_path / "s2.tif", bands=3, dtype="float32")
        out = tmp_path / "s2_norm.tif"
        DataProcessor.normalize_sentinel2(src, out, min_val=0, max_val=400)
        with rasterio.open(out) as dst:
            data = dst.read()
        assert data.min() >= 0
        assert data.max() <= 255


# ---------------------------------------------------------------------------
# get_raster_extent
# ---------------------------------------------------------------------------

class TestGetRasterExtent:
    def test_extent_matches_sample_dem(self):
        xmin, ymin, xmax, ymax = DataProcessor.get_raster_extent(SAMPLE_DEM)
        assert xmin == pytest.approx(116.0, abs=0.01)
        assert ymin == pytest.approx(39.5, abs=0.01)
        assert xmax == pytest.approx(116.5, abs=0.01)
        assert ymax == pytest.approx(40.0, abs=0.01)

    def test_returns_four_floats(self):
        result = DataProcessor.get_raster_extent(SAMPLE_DEM)
        assert len(result) == 4
        assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# get_raster_stats
# ---------------------------------------------------------------------------

class TestGetRasterStats:
    def test_stats_keys(self):
        stats = DataProcessor.get_raster_stats(SAMPLE_DEM)
        for key in ("min", "max", "mean", "nodata", "crs", "shape", "resolution"):
            assert key in stats

    def test_shape_is_tuple(self):
        stats = DataProcessor.get_raster_stats(SAMPLE_DEM)
        assert isinstance(stats["shape"], tuple)
        assert len(stats["shape"]) == 2

    def test_min_lt_max(self):
        stats = DataProcessor.get_raster_stats(SAMPLE_DEM)
        assert stats["min"] < stats["max"]


# ---------------------------------------------------------------------------
# _hex_to_rgba
# ---------------------------------------------------------------------------

class TestHexToRgba:
    def test_black(self):
        assert _hex_to_rgba("#000000") == (0, 0, 0, 255)

    def test_white(self):
        assert _hex_to_rgba("#ffffff") == (255, 255, 255, 255)

    def test_red(self):
        assert _hex_to_rgba("#ff0000") == (255, 0, 0, 255)

    def test_no_hash(self):
        assert _hex_to_rgba("00ff00") == (0, 255, 0, 255)
