"""Tests for GEEFetcher — all GEE calls are mocked."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from src.core.gee_fetcher import GEEFetcher
from src.core.exceptions import GEEAuthFailedError, GEEDownloadFailedError, GEEQuotaExceededError
from src.constants import DEM_DOWNLOAD_SCALE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tiny_tif(path: Path, bands: int = 1) -> None:
    """Write a 10×10 float32 GeoTIFF covering a small Beijing area."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.random.rand(bands, 10, 10).astype("float32")
    transform = from_bounds(116.0, 39.5, 116.5, 40.0, 10, 10)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=10, width=10,
        count=bands,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fetcher(tmp_path):
    return GEEFetcher(project_id="test-project", cache_dir=tmp_path / "cache")


@pytest.fixture()
def mock_ee_geometry():
    """Minimal ee.Geometry mock covering a small Beijing region."""
    geom = MagicMock()
    geom.bounds.return_value.getInfo.return_value = {
        "coordinates": [[[116.0, 39.5], [116.5, 39.5], [116.5, 40.0], [116.0, 40.0]]]
    }
    geom.getInfo.return_value = {
        "type": "Polygon",
        "coordinates": [[[116.0, 39.5], [116.5, 39.5], [116.5, 40.0], [116.0, 40.0]]],
    }
    return geom


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuthentication:
    def test_is_authenticated_false_when_ee_unavailable(self, fetcher):
        with patch("src.core.gee_fetcher._EE_AVAILABLE", False):
            assert fetcher.is_authenticated() is False

    def test_authenticate_raises_when_ee_unavailable(self, fetcher):
        with patch("src.core.gee_fetcher._EE_AVAILABLE", False):
            with pytest.raises(GEEAuthFailedError):
                fetcher.authenticate()

    def test_authenticate_calls_ee_initialize(self, fetcher):
        mock_ee = MagicMock()
        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", mock_ee):
            fetcher.authenticate()
            mock_ee.Authenticate.assert_called_once()
            mock_ee.Initialize.assert_called_once_with(project="test-project")

    def test_authenticate_raises_on_ee_error(self, fetcher):
        mock_ee = MagicMock()
        mock_ee.Authenticate.side_effect = RuntimeError("network error")
        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", mock_ee):
            with pytest.raises(GEEAuthFailedError):
                fetcher.authenticate()


# ---------------------------------------------------------------------------
# Download tests
# ---------------------------------------------------------------------------

class TestFetchDEM:
    def test_fetch_dem_calls_download(self, fetcher, mock_ee_geometry, tmp_path):
        output = tmp_path / "dem.tif"

        def fake_download(image, filename, **kwargs):
            _write_tiny_tif(Path(filename))

        fetcher._authenticated = True
        mock_ee = MagicMock()
        mock_geemap = MagicMock(side_effect=fake_download)

        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", mock_ee), \
             patch("src.core.gee_fetcher.geemap") as mock_gm:
            mock_gm.download_ee_image.side_effect = fake_download
            result = fetcher.fetch_dem(mock_ee_geometry, output)

        assert result == output
        assert output.exists()

    def test_fetch_dem_raises_when_not_authenticated(self, fetcher, mock_ee_geometry, tmp_path):
        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee") as mock_ee:
            mock_ee.Initialize.side_effect = Exception("not authenticated")
            with pytest.raises(GEEAuthFailedError):
                fetcher.fetch_dem(mock_ee_geometry, tmp_path / "out.tif")


class TestFetchSentinel2:
    def test_fetch_sentinel2_calls_download(self, fetcher, mock_ee_geometry, tmp_path):
        output = tmp_path / "s2.tif"

        def fake_download(image, filename, **kwargs):
            _write_tiny_tif(Path(filename), bands=3)

        fetcher._authenticated = True
        mock_ee = MagicMock()
        # Make the ee.ImageCollection chain return a mock image
        mock_ee.ImageCollection.return_value.filterBounds.return_value \
            .filterDate.return_value.filter.return_value \
            .select.return_value.median.return_value \
            .divide.return_value.clamp.return_value \
            .multiply.return_value.toUint8.return_value = MagicMock()

        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", mock_ee), \
             patch("src.core.gee_fetcher.geemap") as mock_gm:
            mock_gm.download_ee_image.side_effect = fake_download
            result = fetcher.fetch_sentinel2(mock_ee_geometry, output)

        assert result == output
        assert output.exists()


class TestRetryLogic:
    def test_retries_on_failure_then_succeeds(self, fetcher, mock_ee_geometry, tmp_path):
        output = tmp_path / "dem.tif"
        call_count = [0]

        def flaky_download(image, filename, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("transient error")
            _write_tiny_tif(Path(filename))

        fetcher._authenticated = True
        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", MagicMock()), \
             patch("src.core.gee_fetcher.geemap") as mock_gm, \
             patch("src.core.gee_fetcher.time.sleep"):
            mock_gm.download_ee_image.side_effect = flaky_download
            fetcher.fetch_dem(mock_ee_geometry, output)

        assert call_count[0] == 2

    def test_raises_after_max_retries(self, fetcher, mock_ee_geometry, tmp_path):
        output = tmp_path / "dem.tif"
        fetcher._authenticated = True

        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", MagicMock()), \
             patch("src.core.gee_fetcher.geemap") as mock_gm, \
             patch("src.core.gee_fetcher.time.sleep"):
            mock_gm.download_ee_image.side_effect = RuntimeError("always fails")
            with pytest.raises(GEEDownloadFailedError):
                fetcher.fetch_dem(mock_ee_geometry, output)

    def test_quota_error_raises_immediately(self, fetcher, mock_ee_geometry, tmp_path):
        output = tmp_path / "dem.tif"
        fetcher._authenticated = True

        with patch("src.core.gee_fetcher._EE_AVAILABLE", True), \
             patch("src.core.gee_fetcher.ee", MagicMock()), \
             patch("src.core.gee_fetcher.geemap") as mock_gm, \
             patch("src.core.gee_fetcher.time.sleep"):
            mock_gm.download_ee_image.side_effect = Exception("resource exhausted quota")
            with pytest.raises(GEEQuotaExceededError):
                fetcher.fetch_dem(mock_ee_geometry, output)


class TestTiling:
    def test_small_area_single_tile(self, fetcher):
        tiles = fetcher._make_tiles(116.0, 39.5, 116.5, 40.0, 1_000_000, 90)
        assert len(tiles) == 1

    def test_large_area_multiple_tiles(self, fetcher):
        # Force > MAX_TILE_PIXELS
        from src.constants import MAX_TILE_PIXELS
        tiles = fetcher._make_tiles(100.0, 20.0, 125.0, 55.0, MAX_TILE_PIXELS * 10, 90)
        assert len(tiles) > 1

    def test_tiles_cover_full_bbox(self, fetcher):
        from src.constants import MAX_TILE_PIXELS
        xmin, ymin, xmax, ymax = 116.0, 39.0, 120.0, 42.0
        tiles = fetcher._make_tiles(xmin, ymin, xmax, ymax, MAX_TILE_PIXELS * 5, 90)
        xs = [t[0] for t in tiles] + [t[2] for t in tiles]
        ys = [t[1] for t in tiles] + [t[3] for t in tiles]
        assert min(xs) == pytest.approx(xmin, abs=1e-6)
        assert max(xs) == pytest.approx(xmax, abs=1e-6)
        assert min(ys) == pytest.approx(ymin, abs=1e-6)
        assert max(ys) == pytest.approx(ymax, abs=1e-6)
