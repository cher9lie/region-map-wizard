"""Tests for BoundaryManager (cities.json path only; gpkg tests are skipped when file absent)."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.boundary_manager import BoundaryManager
from src.core.exceptions import BoundaryNotFoundError, InvalidSHPError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def manager(tmp_path):
    """BoundaryManager backed by the real cities.json but a fake gpkg path."""
    real_cities = Path(__file__).parent.parent / "src" / "data" / "cities.json"
    return BoundaryManager(
        gpkg_path=tmp_path / "china_admin.gpkg",   # does not exist
        cities_json_path=real_cities,
    )


# ---------------------------------------------------------------------------
# cities.json tests (no gpkg required)
# ---------------------------------------------------------------------------

class TestListProvinces:
    def test_returns_list(self, manager):
        provinces = manager.list_provinces()
        assert isinstance(provinces, list)
        assert len(provinces) >= 34

    def test_required_fields(self, manager):
        for p in manager.list_provinces():
            assert "adcode" in p
            assert "name" in p
            assert "name_en" in p
            assert "center" in p

    def test_beijing_present(self, manager):
        codes = {p["adcode"] for p in manager.list_provinces()}
        assert "110000" in codes

    def test_guangdong_present(self, manager):
        codes = {p["adcode"] for p in manager.list_provinces()}
        assert "440000" in codes


class TestListCities:
    def test_beijing_has_one_city(self, manager):
        cities = manager.list_cities("110000")
        assert len(cities) == 1
        assert cities[0]["adcode"] == "110100"

    def test_shandong_has_many_cities(self, manager):
        cities = manager.list_cities("370000")
        assert len(cities) >= 16

    def test_guangdong_cities_count(self, manager):
        cities = manager.list_cities("440000")
        assert len(cities) >= 19

    def test_invalid_province_raises(self, manager):
        with pytest.raises(BoundaryNotFoundError):
            manager.list_cities("999999")

    def test_city_fields(self, manager):
        for city in manager.list_cities("130000"):
            assert "adcode" in city
            assert "name" in city
            assert "name_en" in city
            assert "center" in city


# ---------------------------------------------------------------------------
# GeoPackage tests (skipped when gpkg absent)
# ---------------------------------------------------------------------------

def _gpkg_available() -> bool:
    real = Path(__file__).parent.parent / "src" / "data" / "china_admin.gpkg"
    return real.exists()


@pytest.mark.skipif(not _gpkg_available(), reason="china_admin.gpkg not present")
class TestGpkgBoundaries:
    @pytest.fixture()
    def real_manager(self):
        return BoundaryManager()

    def test_get_country_boundary(self, real_manager):
        gdf = real_manager.get_country_boundary()
        assert not gdf.empty
        assert gdf.crs.to_epsg() == 4326

    def test_get_province_boundary(self, real_manager):
        gdf = real_manager.get_boundary("110000", "province")
        assert not gdf.empty

    def test_get_city_boundary(self, real_manager):
        gdf = real_manager.get_boundary("110100", "city")
        assert not gdf.empty

    def test_boundary_not_found_raises(self, real_manager):
        with pytest.raises(BoundaryNotFoundError):
            real_manager.get_boundary("999999", "city")

    def test_get_context_boundaries(self, real_manager):
        country, province, city, all_prov = real_manager.get_context_boundaries("110100")
        assert not country.empty
        assert not province.empty
        assert not city.empty
        assert len(all_prov) >= 30


# ---------------------------------------------------------------------------
# validate_custom_shp tests
# ---------------------------------------------------------------------------

class TestValidateCustomSHP:
    def test_invalid_path_raises(self, manager):
        with pytest.raises(InvalidSHPError):
            manager.validate_custom_shp(Path("/nonexistent/file.shp"))

    def test_valid_shp_returns_true(self, manager, tmp_path):
        import geopandas as gpd
        from shapely.geometry import Polygon

        shp = tmp_path / "test.shp"
        gdf = gpd.GeoDataFrame(
            {"name": ["test"]},
            geometry=[Polygon([(116, 39), (117, 39), (117, 40), (116, 40)])],
            crs="EPSG:4326",
        )
        gdf.to_file(shp)
        valid, msg, result = manager.validate_custom_shp(shp)
        assert valid is True
        assert result is not None
        assert result.crs.to_epsg() == 4326

    def test_shp_with_wrong_crs_is_reprojected(self, manager, tmp_path):
        import geopandas as gpd
        from shapely.geometry import Polygon

        shp = tmp_path / "utm.shp"
        # Approximate Beijing in UTM Zone 50N (EPSG:32650)
        gdf = gpd.GeoDataFrame(
            {"name": ["test"]},
            geometry=[Polygon([(400000, 4400000), (410000, 4400000),
                               (410000, 4410000), (400000, 4410000)])],
            crs="EPSG:32650",
        )
        gdf.to_file(shp)
        valid, msg, result = manager.validate_custom_shp(shp)
        assert valid is True
        assert result.crs.to_epsg() == 4326

    def test_no_geometry_returns_false(self, manager, tmp_path):
        import geopandas as gpd
        from shapely.geometry import Polygon
        import numpy as np

        shp = tmp_path / "empty.shp"
        # Build an empty GeoDataFrame the safe way
        gdf = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
        gdf.to_file(shp)
        valid, msg, result = manager.validate_custom_shp(shp)
        assert valid is False
