"""Cartopy + matplotlib rendering engine (pure-Python, no QGIS/ArcGIS needed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from src.renderers.base import BaseRenderer, RenderConfig
from src.core.exceptions import RenderFailedError

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyArrowPatch
    _CARTOPY_AVAILABLE = True
except ImportError:
    ccrs = None           # type: ignore[assignment]
    plt = None            # type: ignore[assignment]
    _CARTOPY_AVAILABLE = False

_DATA_DIR = Path(__file__).parent.parent / "data"


class CartopyRenderer(BaseRenderer):
    """Render three-panel location maps with cartopy + matplotlib."""

    def check_available(self) -> tuple[bool, str]:
        if _CARTOPY_AVAILABLE:
            import matplotlib
            import cartopy
            return True, f"cartopy {cartopy.__version__} / matplotlib {matplotlib.__version__}"
        return False, "cartopy 或 matplotlib 未安装"

    def get_project_path(self) -> Optional[Path]:
        return None

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        if not _CARTOPY_AVAILABLE:
            raise RenderFailedError("cartopy 未安装，无法使用 Cartopy 渲染引擎")

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        try:
            import geopandas as gpd

            _p(0, "创建画布...")
            # A4 landscape in inches
            fig = plt.figure(figsize=(297 / 25.4, 210 / 25.4), dpi=config.dpi)

            _p(10, "绘制中国全图 (a)...")
            ax_china = self._add_china_panel(fig, config)

            _p(35, "绘制省级图 (b)...")
            ax_province = self._add_province_panel(fig, config)

            _p(55, "绘制研究区详图 (c)...")
            ax_detail = self._add_detail_panel(fig, config)

            _p(75, "添加标题和注记...")
            self._add_title(fig, config)
            self._add_panel_labels(fig)
            self._add_footer(fig, config)
            if config.show_north_arrow:
                self._add_north_arrow(ax_detail)
            if config.show_scalebar:
                self._add_scalebar(ax_detail, config)
            self._add_connection_lines(fig)

            _p(90, "导出...")
            output = Path(config.output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(
                output,
                dpi=config.dpi,
                bbox_inches="tight",
                facecolor="white",
            )
            plt.close(fig)

            _p(100, "完成")
            return output

        except (RenderFailedError,):
            raise
        except Exception as exc:
            raise RenderFailedError(str(exc)) from exc

    # ── Panels ────────────────────────────────────────────────────────────────

    def _add_china_panel(self, fig, config: RenderConfig):
        """(a) China overview in Lambert Conformal Conic."""
        import geopandas as gpd
        from matplotlib.colors import to_rgba

        lcc = ccrs.LambertConformal(
            central_longitude=105, central_latitude=35,
            standard_parallels=(25, 47),
        )
        # [left, bottom, width, height] in figure fraction
        ax = fig.add_axes([0.017, 0.115, 0.303, 0.72], projection=lcc)
        ax.set_extent([72, 136, 15, 55], crs=ccrs.PlateCarree())

        self._draw_vector_layer(ax, config.country_boundary, "#E0E0E0", "#888888", 0.4)
        self._draw_vector_layer(ax, config.province_boundary, "#D8D8D8", "#666666", 0.3,
                                highlight_name=config.province_name,
                                highlight_color=config.highlight_color)
        return ax

    def _add_province_panel(self, fig, config: RenderConfig):
        """(b) Province overview in PlateCarree."""
        ax = fig.add_axes([0.017, 0.04, 0.303, 0.355], projection=ccrs.PlateCarree())

        self._draw_vector_layer(ax, config.province_boundary, "#D8D8D8", "#666666", 0.5)
        self._draw_vector_layer(ax, config.city_boundary, "#C8C8C8", "#444444", 0.4,
                                highlight_name=config.city_name,
                                highlight_color=config.highlight_color)
        ax.gridlines(draw_labels=False, linewidth=0.3, color="#BBBBBB", alpha=0.6)
        return ax

    def _add_detail_panel(self, fig, config: RenderConfig):
        """(c) Study-area detail with optional raster overlay."""
        ax = fig.add_axes([0.337, 0.04, 0.655, 0.88], projection=ccrs.PlateCarree())

        # Raster overlay
        if config.raster_path and Path(config.raster_path).exists():
            self._draw_raster(ax, config)

        # Vector overlays
        self._draw_vector_layer(ax, config.city_boundary, "none", config.highlight_color, 1.2)

        if config.show_grid:
            gl = ax.gridlines(
                draw_labels=True, linewidth=0.4,
                color="#777777", alpha=0.5, linestyle="--",
            )
            gl.top_labels = False
            gl.right_labels = False

        return ax

    # ── Raster drawing ────────────────────────────────────────────────────────

    def _draw_raster(self, ax, config: RenderConfig) -> None:
        import rasterio
        from src.core.data_processor import DataProcessor

        raster_path = Path(config.raster_path)
        color_ramp = self._load_color_ramp(config.color_ramp)

        with rasterio.open(raster_path) as src:
            b = src.bounds
            extent = [b.left, b.right, b.bottom, b.top]

        if config.data_type == "dem" and color_ramp:
            rgba = DataProcessor.apply_color_ramp(raster_path, color_ramp)
            ax.imshow(rgba, extent=extent, transform=ccrs.PlateCarree(),
                      origin="upper", aspect="auto", zorder=1)
        elif config.data_type == "hillshade":
            with rasterio.open(raster_path) as src:
                data = src.read(1)
            ax.imshow(data, extent=extent, transform=ccrs.PlateCarree(),
                      cmap="gray", vmin=0, vmax=255, origin="upper",
                      aspect="auto", zorder=1)
        elif config.data_type == "sentinel2":
            with rasterio.open(raster_path) as src:
                rgb = src.read([1, 2, 3])
            rgb = np.clip(rgb / 255.0, 0, 1).transpose(1, 2, 0)
            ax.imshow(rgb, extent=extent, transform=ccrs.PlateCarree(),
                      origin="upper", aspect="auto", zorder=1)

    # ── Vector drawing ────────────────────────────────────────────────────────

    def _draw_vector_layer(
        self, ax, path, face_color: str, edge_color: str,
        line_width: float,
        highlight_name: str | None = None,
        highlight_color: str = "#FF0000",
    ) -> None:
        if not path or not Path(path).exists():
            return
        import geopandas as gpd

        gdf = gpd.read_file(path)
        if gdf.empty:
            return

        gdf.plot(
            ax=ax, facecolor=face_color, edgecolor=edge_color,
            linewidth=line_width, transform=ccrs.PlateCarree(), zorder=2,
        )
        if highlight_name:
            name_cols = [c for c in gdf.columns if "name" in c.lower()]
            for col in name_cols:
                match = gdf[gdf[col] == highlight_name]
                if not match.empty:
                    match.plot(
                        ax=ax,
                        facecolor=f"{highlight_color}44",
                        edgecolor=highlight_color,
                        linewidth=1.5,
                        transform=ccrs.PlateCarree(),
                        zorder=3,
                    )
                    break

    # ── Annotations ───────────────────────────────────────────────────────────

    def _add_title(self, fig, config: RenderConfig) -> None:
        title = config.title or (
            f"{config.city_name}研究区区位图"
            if config.language == "zh"
            else f"Location Map of {config.city_name} Study Area"
        )
        fig.text(
            0.66, 0.97, title,
            ha="center", va="top",
            fontsize=16, fontweight="bold",
            fontfamily="SimHei" if config.language == "zh" else "Arial",
        )

    def _add_panel_labels(self, fig) -> None:
        for text, x, y in [("(a)", 0.018, 0.96), ("(b)", 0.018, 0.44), ("(c)", 0.337, 0.96)]:
            fig.text(x, y, text, fontsize=12, fontweight="bold", va="top")

    def _add_footer(self, fig, config: RenderConfig) -> None:
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        footer = (
            f"坐标系: WGS84 (EPSG:4326)  |  数据来源: Google Earth Engine / 天地图  |  制图日期: {today}"
        )
        fig.text(0.5, 0.005, footer, ha="center", va="bottom", fontsize=7, color="#999999")

    def _add_north_arrow(self, ax) -> None:
        """Draw a simple N arrow in the top-right of the detail axes."""
        ax.annotate(
            "N", xy=(0.96, 0.92), xytext=(0.96, 0.82),
            xycoords="axes fraction",
            arrowprops=dict(arrowstyle="-|>", color="black", lw=1.5),
            ha="center", va="center", fontsize=11, fontweight="bold",
        )

    def _add_scalebar(self, ax, config: RenderConfig) -> None:
        """Draw a simple scale bar (rough approximation for lat/lon coords)."""
        try:
            from matplotlib_scalebar.scalebar import ScaleBar
            ax.add_artist(ScaleBar(1, location="lower left", font_properties={"size": 7}))
        except ImportError:
            # Fallback: hand-drawn bar
            ax.annotate(
                "50 km", xy=(0.05, 0.05), xycoords="axes fraction",
                fontsize=7, ha="left", va="bottom",
            )

    def _add_connection_lines(self, fig) -> None:
        """Draw connector arrows between the three panels."""
        from matplotlib.patches import FancyArrowPatch
        ax_dummy = fig.add_axes([0, 0, 1, 1], facecolor="none")
        ax_dummy.set_axis_off()
        for xy_start, xy_end in [
            ((0.32, 0.67), (0.337, 0.85)),
            ((0.32, 0.25), (0.337, 0.55)),
        ]:
            ax_dummy.annotate(
                "", xy=xy_end, xytext=xy_start,
                arrowprops=dict(
                    arrowstyle="-|>", color="#CC0000", lw=0.8,
                    connectionstyle="arc3,rad=0",
                ),
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_color_ramp(name: str) -> dict | None:
        p = _DATA_DIR / "color_ramps.json"
        if not p.exists():
            return None
        with p.open(encoding="utf-8") as f:
            ramps = json.load(f)
        return ramps.get(name)
