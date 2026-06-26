"""Persistent JSON config for Region Map Wizard (~/.rmw/config.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG: dict[str, Any] = {
    "gee_project_id": "",
    "last_province": "110000",
    "last_city": "110100",
    "last_data_type": "dem",
    "last_renderer": "qgis",
    "last_output_dir": "",
    "output_format": "jpg",
    "dpi": 300,
    "language": "zh",
    "cache_dir": "",
    "qgis_prefix_path": "",
    "arcgis_python_path": "",
    "sentinel2_year_range": 1,
    "sentinel2_cloud_max": 20,
}


class ConfigManager:
    """Read/write ~/.rmw/config.json."""

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path.home() / ".rmw" / "config.json"
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}
        self.load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        """Load from disk, falling back to defaults for missing keys."""
        self._data = dict(_DEFAULT_CONFIG)
        if self._path.exists():
            try:
                with self._path.open(encoding="utf-8") as f:
                    on_disk = json.load(f)
                self._data.update(on_disk)
            except (json.JSONDecodeError, OSError):
                pass  # corrupt file → use defaults
        return self._data

    def save(self, data: dict[str, Any] | None = None) -> None:
        """Persist current config (or provided dict) to disk."""
        if data is not None:
            self._data.update(data)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
