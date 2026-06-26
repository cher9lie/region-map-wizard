"""Abstract base class and shared data types for all render engines."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RenderConfig:
    """Full rendering configuration — matches SPEC §4.1 exactly."""

    # ── Boundary data ──────────────────────────────────────────────────────────
    country_boundary: Path
    province_boundary: Path
    city_boundary: Path
    province_name: str
    city_name: str

    # ── Raster data ───────────────────────────────────────────────────────────
    raster_path: Optional[Path]
    data_type: str          # 'dem' | 'hillshade' | 'sentinel2'
    color_ramp: str         # key in color_ramps.json

    # ── Output settings ───────────────────────────────────────────────────────
    output_path: Path
    output_format: str      # 'jpg' | 'png' | 'pdf' | 'tiff' | 'svg'
    dpi: int = 300
    page_size: str = "a4_landscape"   # 'a4_landscape' | 'a4_portrait' | 'a3_landscape'
    language: str = "zh"              # 'zh' | 'en'

    # ── Style ─────────────────────────────────────────────────────────────────
    title: Optional[str] = None
    show_grid: bool = True
    show_scalebar: bool = True
    show_north_arrow: bool = True
    show_legend: bool = True
    highlight_color: str = "#FF0000"
    highlight_width: float = 1.5

    # ── Adcodes (used by renderers to filter gpkg layers correctly) ───────────
    province_adcode: str = ""
    city_adcode: str = ""

    # ── Custom SHP mode ───────────────────────────────────────────────────────
    custom_shp: Optional[Path] = None
    custom_name: Optional[str] = None


class BaseRenderer(ABC):
    """Abstract base class every render engine must implement."""

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """Return (available, reason/version) for this engine."""

    @abstractmethod
    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """Execute rendering.

        Args:
            config: Rendering configuration.
            progress_callback: Optional fn(percent: int, message: str).

        Returns:
            Path to the output file.

        Raises:
            RenderFailedError
        """

    @abstractmethod
    def get_project_path(self) -> Optional[Path]:
        """Return path to the editable project file (.qgz / .aprx), or None."""
