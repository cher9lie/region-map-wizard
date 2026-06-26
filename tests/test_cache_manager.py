"""Tests for CacheManager."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.core.cache_manager import CacheManager


@pytest.fixture()
def cache(tmp_path):
    return CacheManager(tmp_path / "rmw_cache")


class TestCachePaths:
    def test_returns_path(self, cache):
        p = cache.get_cache_path("110100", "dem")
        assert isinstance(p, Path)

    def test_deterministic(self, cache):
        p1 = cache.get_cache_path("110100", "dem", scale=90)
        p2 = cache.get_cache_path("110100", "dem", scale=90)
        assert p1 == p2

    def test_different_scale_different_key(self, cache):
        p1 = cache.get_cache_path("110100", "dem", scale=90)
        p2 = cache.get_cache_path("110100", "dem", scale=30)
        assert p1 != p2

    def test_different_adcode_different_key(self, cache):
        p1 = cache.get_cache_path("110100", "dem")
        p2 = cache.get_cache_path("130100", "dem")
        assert p1 != p2

    def test_dem_is_static(self, cache):
        p1 = cache.get_cache_path("110100", "dem")
        p2 = cache.get_cache_path("110100", "dem", year="static")
        assert p1 == p2

    def test_sentinel2_year_scoped(self, cache):
        p1 = cache.get_cache_path("110100", "sentinel2", year=2023)
        p2 = cache.get_cache_path("110100", "sentinel2", year=2024)
        assert p1 != p2

    def test_subdir_created(self, cache):
        cache.get_cache_path("110100", "dem")
        assert (cache._root / "dem").is_dir()


class TestCacheIsHit:
    def test_miss_when_no_file(self, cache):
        assert cache.is_cached("110100", "dem") is False

    def test_hit_after_creating_file(self, cache):
        path = cache.get_cache_path("110100", "dem")
        path.write_bytes(b"fake tif data")
        assert cache.is_cached("110100", "dem") is True

    def test_get_cached_none_when_absent(self, cache):
        assert cache.get_cached("110100", "dem") is None

    def test_get_cached_returns_path_when_present(self, cache):
        path = cache.get_cache_path("110100", "dem")
        path.write_bytes(b"fake tif data")
        result = cache.get_cached("110100", "dem")
        assert result == path


class TestClearCache:
    def test_clear_all(self, cache):
        p = cache.get_cache_path("110100", "dem")
        p.write_bytes(b"data")
        cache.clear_cache()
        assert not p.exists()

    def test_clear_by_adcode(self, cache):
        p1 = cache.get_cache_path("110100", "dem")
        p2 = cache.get_cache_path("130100", "dem")
        p1.write_bytes(b"data")
        p2.write_bytes(b"data")
        cache.clear_cache("110100")
        assert not p1.exists()
        assert p2.exists()

    def test_cache_dir_still_exists_after_clear_all(self, cache):
        cache.clear_cache()
        assert cache._root.exists()


class TestCacheSize:
    def test_zero_when_empty(self, cache):
        assert cache.get_cache_size() == 0

    def test_returns_total_bytes(self, cache):
        p1 = cache.get_cache_path("110100", "dem")
        p2 = cache.get_cache_path("110100", "hillshade")
        p1.write_bytes(b"a" * 100)
        p2.write_bytes(b"b" * 200)
        assert cache.get_cache_size() == 300
