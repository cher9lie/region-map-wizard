"""Local file cache for GEE-downloaded rasters."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Optional


class CacheManager:
    """Manage a directory of cached GeoTIFF files keyed by content hash."""

    def __init__(self, cache_dir: Path) -> None:
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_cache_path(self, adcode: str, data_type: str, **kwargs) -> Path:
        """Return the path where this dataset would be cached (may not exist)."""
        key = self._make_key(adcode, data_type, **kwargs)
        subdir = self._root / data_type
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / f"{adcode}_{key}.tif"

    def is_cached(self, adcode: str, data_type: str, **kwargs) -> bool:
        return self.get_cache_path(adcode, data_type, **kwargs).exists()

    def get_cached(self, adcode: str, data_type: str, **kwargs) -> Optional[Path]:
        path = self.get_cache_path(adcode, data_type, **kwargs)
        return path if path.exists() else None

    def clear_cache(self, adcode: str | None = None) -> None:
        """Delete cached files.  Pass adcode to delete only that area's files."""
        if adcode is None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root.mkdir(parents=True, exist_ok=True)
        else:
            for f in self._root.rglob(f"{adcode}_*.tif"):
                f.unlink(missing_ok=True)

    def get_cache_size(self) -> int:
        """Return total cache size in bytes."""
        return sum(f.stat().st_size for f in self._root.rglob("*.tif") if f.is_file())

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _make_key(adcode: str, data_type: str, **kwargs) -> str:
        """Deterministic 16-char hex key matching SPEC §3.5."""
        year = kwargs.get("year", "static")
        scale = kwargs.get("scale", "")
        raw = f"{adcode}_{data_type}_{scale}_{year}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
