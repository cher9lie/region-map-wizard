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
    import matplotlib
    matplotlib.use("Agg")
    # Chinese font support — must be set before any figure is created
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "STHeiti",
        "Arial Unicode MS", "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe
    _CARTOPY_AVAILABLE = True
except ImportError:
    ccrs = None           # type: ignore[assignment]
    plt = None            # type: ignore[assignment]
    _CARTOPY_AVAILABLE = False

_DATA_DIR = Path(__file__).parent.parent / "data"

# Panel layout on A4 landscape (297 × 210 mm), all in figure fractions.
# Origin is bottom-left. Coords derived from SPEC §4.2:
#   (a) China:    90×78 mm at ( 5 mm,  22 mm from top)
#   (b) Province: 90×62 mm at ( 5 mm, 105 mm from top)
#   (c) Detail:  182×155 mm at (100 mm,  22 mm from top)
W, H = 297.0, 210.0
_AX_CHINA    = [5/W, (H-22-78)/H,   90/W,  78/H]   # [0.017, 0.524, 0.303, 0.371]
_AX_PROVINCE = [5/W, (H-105-62)/H,  90/W,  62/H]   # [0.017, 0.205, 0.303, 0.295]
_AX_DETAIL   = [100/W, (H-22-155)/H, 182/W, 155/H]  # [0.337, 0.157, 0.613, 0.738]


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
            _p(0, "创建画布...")
            fig = plt.figure(figsize=(W / 25.4, H / 25.4), dpi=config.dpi)
            fig.patch.set_facecolor("white")

            _p(10, "绘制中国全图 (a)...")
            self._add_china_panel(fig, config)

            _p(35, "绘制省级图 (b)...")
            self._add_province_panel(fig, config)

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

            _p(90, "导出...")
            output = Path(config.output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output, dpi=config.dpi, bbox_inches=None, facecolor="white")
            plt.close(fig)

            _p(100, "完成")
            return output

        except RenderFailedError:
            raise
        except Exception as exc:
            raise RenderFailedError(str(exc)) from exc

    # ── Layer reading ─────────────────────────────────────────────────────────

    def _read_layer(
        self, gpkg_path, layer: str,
        filter_col: str | None = None, filter_val: str | None = None,
    ):
        """Read a GeoPackage layer, optionally filtering by a column value."""
        import geopandas as gpd
        p = Path(gpkg_path)
        if not p.exists():
            return None
        gdf = gpd.read_file(p, layer=layer)
        if filter_col and filter_val:
            gdf = gdf[gdf[filter_col] == filter_val]
        if gdf.empty:
            return None
        return gdf

    # ── Panels ────────────────────────────────────────────────────────────────

    def _add_china_panel(self, fig, config: RenderConfig):
        """(a) China overview in Lambert Conformal Conic, province highlighted."""
        lcc = ccrs.LambertConformal(
            central_longitude=105, central_latitude=35,
            standard_parallels=(25, 47),
        )
        ax = fig.add_axes(_AX_CHINA, projection=lcc)
        ax.set_extent([73, 135, 15, 54], crs=ccrs.PlateCarree())

        # Draw all provinces (base fill)
        prov = self._read_layer(config.province_boundary, "province")
        if prov is not None:
            prov.plot(ax=ax, facecolor="#D8E8D0", edgecolor="#888888",
                      linewidth=0.3, transform=ccrs.PlateCarree(), zorder=2)
            # Highlight selected province
            if config.province_adcode:
                sel = prov[prov["adcode"] == config.province_adcode]
                if not sel.empty:
                    sel.plot(ax=ax, facecolor=f"{config.highlight_color}77",
                             edgecolor=config.highlight_color, linewidth=1.2,
                             transform=ccrs.PlateCarree(), zorder=3)

        # Country outline on top
        country = self._read_layer(config.country_boundary, "country")
        if country is not None:
            country.plot(ax=ax, facecolor="none", edgecolor="#333333",
                         linewidth=0.6, transform=ccrs.PlateCarree(), zorder=4)

        ax.set_facecolor("#C8DFF0")  # sea colour
        ax.spines["geo"].set_linewidth(0.5)
        return ax

    def _add_province_panel(self, fig, config: RenderConfig):
        """(b) Province zoom with city highlighted."""
        ax = fig.add_axes(_AX_PROVINCE, projection=ccrs.PlateCarree())

        prov_code = config.province_adcode or ""

        # Province boundary fill
        prov = self._read_layer(config.province_boundary, "province",
                                filter_col="adcode", filter_val=prov_code)
        if prov is not None:
            prov.plot(ax=ax, facecolor="#E8F0E0", edgecolor="#555555",
                      linewidth=0.6, transform=ccrs.PlateCarree(), zorder=2)
            bounds = prov.total_bounds  # (minx, miny, maxx, maxy)
            pad = max((bounds[2]-bounds[0]), (bounds[3]-bounds[1])) * 0.08
            ax.set_extent([bounds[0]-pad, bounds[2]+pad, bounds[1]-pad, bounds[3]+pad],
                          crs=ccrs.PlateCarree())

        # All cities in province
        cities = self._read_layer(config.city_boundary, "city",
                                  filter_col="province_adcode", filter_val=prov_code)
        if cities is not None:
            cities.plot(ax=ax, facecolor="#D0DDCA", edgecolor="#444444",
                        linewidth=0.4, transform=ccrs.PlateCarree(), zorder=3)
            # Highlight target city
            if config.city_adcode:
                sel = cities[cities["adcode"] == config.city_adcode]
                if not sel.empty:
                    sel.plot(ax=ax, facecolor=f"{config.highlight_color}66",
                             edgecolor=config.highlight_color, linewidth=1.0,
                             transform=ccrs.PlateCarree(), zorder=4)

        ax.set_facecolor("#EAF4FB")
        ax.spines["geo"].set_linewidth(0.5)
        return ax

    def _add_detail_panel(self, fig, config: RenderConfig):
        """(c) Study-area detail with optional raster overlay."""
        import math
        ax = fig.add_axes(_AX_DETAIL, projection=ccrs.PlateCarree())

        # Get target city boundary for extent
        city = self._read_layer(config.city_boundary, "city",
                                filter_col="adcode", filter_val=config.city_adcode)
        bounds = None
        if city is not None:
            bounds = city.total_bounds  # (minx, miny, maxx, maxy)
            pad = max((bounds[2]-bounds[0]), (bounds[3]-bounds[1])) * 0.15
            ax.set_extent([bounds[0]-pad, bounds[2]+pad, bounds[1]-pad, bounds[3]+pad],
                          crs=ccrs.PlateCarree())
        else:
            ax.set_global()

        # Surrounding province cities as light context
        prov_code = config.province_adcode or ""
        if prov_code:
            ctx = self._read_layer(config.city_boundary, "city",
                                   filter_col="province_adcode", filter_val=prov_code)
            if ctx is not None:
                ctx.plot(ax=ax, facecolor="#E8EDE4", edgecolor="#AAAAAA",
                         linewidth=0.4, transform=ccrs.PlateCarree(), zorder=2)

        # Optional raster overlay
        if config.raster_path and Path(config.raster_path).exists():
            self._draw_raster(ax, config)

        # City boundary — filled highlight
        if city is not None:
            city.plot(ax=ax, facecolor=f"{config.highlight_color}33",
                      edgecolor=config.highlight_color, linewidth=1.5,
                      transform=ccrs.PlateCarree(), zorder=5)

        # Grid with labels
        if config.show_grid:
            gl = ax.gridlines(draw_labels=True, linewidth=0.35,
                              color="#777777", alpha=0.5, linestyle="--")
            gl.top_labels = False
            gl.right_labels = False
            gl.xlabel_style = {"size": 7}
            gl.ylabel_style = {"size": 7}

        ax.set_facecolor("#EAF4FB")
        ax.spines["geo"].set_linewidth(0.8)
        # Store lat center for scalebar
        self._detail_lat = ((bounds[1]+bounds[3])/2) if bounds is not None else 35.0
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

    # ── Annotations ───────────────────────────────────────────────────────────

    def _add_title(self, fig, config: RenderConfig) -> None:
        is_en = config.language == "en"
        if config.title:
            title = config.title
        elif is_en:
            title = f"Location Map of {config.city_name} Study Area"
        else:
            title = f"{config.city_name}研究区区位图"

        # Centre title above detail panel (x = mid of detail panel)
        detail_cx = _AX_DETAIL[0] + _AX_DETAIL[2] / 2
        fig.text(detail_cx, 0.97, title,
                 ha="center", va="top",
                 fontsize=14, fontweight="bold")

    def _add_panel_labels(self, fig) -> None:
        labels = [
            ("(a)", _AX_CHINA[0] + 0.005,    _AX_CHINA[1] + _AX_CHINA[3] - 0.005),
            ("(b)", _AX_PROVINCE[0] + 0.005, _AX_PROVINCE[1] + _AX_PROVINCE[3] - 0.005),
            ("(c)", _AX_DETAIL[0] + 0.005,   _AX_DETAIL[1] + _AX_DETAIL[3] - 0.005),
        ]
        for text, x, y in labels:
            fig.text(x, y, text, fontsize=11, fontweight="bold", va="top",
                     color="#222222")

    def _add_footer(self, fig, config: RenderConfig) -> None:
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        is_en = config.language == "en"
        if is_en:
            footer = (f"CRS: WGS84 (EPSG:4326)  |  "
                      f"Data: Google Earth Engine / Tianditu  |  Date: {today}")
        else:
            footer = (f"坐标系: WGS84 (EPSG:4326)  |  "
                      f"数据来源: Google Earth Engine / 天地图  |  制图日期: {today}")
        fig.text(0.5, 0.003, footer,
                 ha="center", va="bottom", fontsize=6.5, color="#999999")

    def _add_north_arrow(self, ax) -> None:
        """Draw a north arrow (↑N) in the top-right corner of the detail axes."""
        # Arrow shaft pointing up: from (0.94, 0.84) to (0.94, 0.92)
        ax.annotate("", xy=(0.94, 0.93), xytext=(0.94, 0.84),
                    xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color="black",
                                   lw=1.5, mutation_scale=12))
        # "N" label above the arrowhead
        ax.text(0.94, 0.96, "N", transform=ax.transAxes,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color="black")

    def _add_scalebar(self, ax, config: RenderConfig) -> None:
        import math
        # Compute meters per degree at the centre latitude of the detail panel
        lat = getattr(self, "_detail_lat", 35.0)
        meters_per_deg = math.cos(math.radians(lat)) * 111_320  # m per degree longitude
        try:
            from matplotlib_scalebar.scalebar import ScaleBar
            ax.add_artist(ScaleBar(
                meters_per_deg, units="m", location="lower left",
                font_properties={"size": 7},
                sep=3, pad=0.3,
            ))
        except ImportError:
            ax.text(0.04, 0.04, "50 km", transform=ax.transAxes,
                    fontsize=7, ha="left", va="bottom", color="#444444")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_color_ramp(name: str) -> dict | None:
        p = _DATA_DIR / "color_ramps.json"
        if not p.exists():
            return None
        with p.open(encoding="utf-8") as f:
            ramps = json.load(f)
        return ramps.get(name)
