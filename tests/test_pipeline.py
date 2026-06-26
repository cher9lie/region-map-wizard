"""Tests for MapWizardPipeline and ConfigManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config_manager import ConfigManager
from src.core.pipeline import MapWizardPipeline
from src.renderers.base import RenderConfig


# ---------------------------------------------------------------------------
# ConfigManager tests
# ---------------------------------------------------------------------------

class TestConfigManager:
    def test_defaults_loaded(self, tmp_path):
        cfg = ConfigManager(config_path=tmp_path / "config.json")
        assert cfg.get("dpi") == 300
        assert cfg.get("language") == "zh"

    def test_save_and_reload(self, tmp_path):
        cfg = ConfigManager(config_path=tmp_path / "config.json")
        cfg.set("dpi", 150)
        cfg2 = ConfigManager(config_path=tmp_path / "config.json")
        assert cfg2.get("dpi") == 150

    def test_get_missing_key_returns_default(self, tmp_path):
        cfg = ConfigManager(config_path=tmp_path / "config.json")
        assert cfg.get("nonexistent_key", "fallback") == "fallback"

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("not valid json", encoding="utf-8")
        cfg = ConfigManager(config_path=p)
        assert cfg.get("dpi") == 300

    def test_as_dict_returns_all_keys(self, tmp_path):
        cfg = ConfigManager(config_path=tmp_path / "config.json")
        d = cfg.as_dict()
        assert "gee_project_id" in d
        assert "dpi" in d

    def test_save_with_data_dict(self, tmp_path):
        cfg = ConfigManager(config_path=tmp_path / "config.json")
        cfg.save({"dpi": 600, "language": "en"})
        cfg2 = ConfigManager(config_path=tmp_path / "config.json")
        assert cfg2.get("dpi") == 600
        assert cfg2.get("language") == "en"


# ---------------------------------------------------------------------------
# Pipeline.validate_config tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def cfg(tmp_path):
    return ConfigManager(config_path=tmp_path / "config.json")


@pytest.fixture()
def pipeline(cfg):
    return MapWizardPipeline(cfg)


def _make_config(tmp_path, **overrides) -> RenderConfig:
    defaults = dict(
        country_boundary=tmp_path / "country.geojson",
        province_boundary=tmp_path / "province.geojson",
        city_boundary=tmp_path / "city.geojson",
        province_name="北京市",
        city_name="北京市",
        raster_path=None,
        data_type="dem",
        color_ramp="dem_hypsometric",
        output_path=tmp_path / "out.jpg",
        output_format="jpg",
        dpi=300,
    )
    defaults.update(overrides)
    return RenderConfig(**defaults)


class TestValidateConfig:
    def test_valid_config_no_errors(self, pipeline, tmp_path):
        config = _make_config(tmp_path)
        assert pipeline.validate_config(config) == []

    def test_missing_output_path(self, pipeline, tmp_path):
        config = _make_config(tmp_path, output_path="")
        errors = pipeline.validate_config(config)
        assert any("输出路径" in e for e in errors)

    def test_bad_format(self, pipeline, tmp_path):
        config = _make_config(tmp_path, output_format="bmp")
        errors = pipeline.validate_config(config)
        assert any("格式" in e for e in errors)

    def test_bad_dpi(self, pipeline, tmp_path):
        config = _make_config(tmp_path, dpi=5000)
        errors = pipeline.validate_config(config)
        assert any("DPI" in e for e in errors)

    def test_bad_data_type(self, pipeline, tmp_path):
        config = _make_config(tmp_path, data_type="lidar")
        errors = pipeline.validate_config(config)
        assert any("数据类型" in e for e in errors)

    def test_missing_custom_shp(self, pipeline, tmp_path):
        config = _make_config(tmp_path, custom_shp=tmp_path / "nonexistent.shp")
        errors = pipeline.validate_config(config)
        assert any("SHP" in e for e in errors)


class TestSelectRenderer:
    def test_qgis_renderer(self, pipeline):
        from src.renderers.qgis_renderer import QGISRenderer
        r = pipeline._select_renderer("qgis")
        assert isinstance(r, QGISRenderer)

    def test_cartopy_renderer(self, pipeline):
        from src.renderers.cartopy_renderer import CartopyRenderer
        r = pipeline._select_renderer("cartopy")
        assert isinstance(r, CartopyRenderer)

    def test_arcgis_renderer(self, pipeline):
        from src.renderers.arcgis_renderer import ArcGISRenderer
        r = pipeline._select_renderer("arcgis")
        assert isinstance(r, ArcGISRenderer)

    def test_unknown_falls_back_to_cartopy(self, pipeline):
        from src.renderers.cartopy_renderer import CartopyRenderer
        r = pipeline._select_renderer("unknown_engine")
        assert isinstance(r, CartopyRenderer)
