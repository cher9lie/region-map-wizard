"""Cartopy + matplotlib rendering engine (pure-Python, no QGIS/ArcGIS needed)."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from src.renderers.base import BaseRenderer, RenderConfig
from src.core.exceptions import RenderFailedError

# When bundled by PyInstaller, native DLLs (GDAL, GEOS, PROJ) live in *.libs
# sibling directories inside _MEIPASS.  Register them before any GIS import so
# the Windows DLL loader can find them regardless of runtime-hook ordering.
if hasattr(sys, "_MEIPASS"):
    _meipass = Path(sys._MEIPASS)
    for _d in _meipass.iterdir():
        if _d.is_dir() and _d.name.endswith(".libs"):
            try:
                os.add_dll_directory(str(_d))
            except Exception:
                pass
    try:
        os.add_dll_directory(str(_meipass))
    except Exception:
        pass

_CARTOPY_ERROR: str = ""
try:
    import cartopy.crs as ccrs
    import cartopy.io.img_tiles as cimgt
    import matplotlib
    matplotlib.use("Agg")

    # Academic font stack: Times New Roman (Latin) + SimSun (CJK serif) + fallbacks.
    # matplotlib ≥ 3.6 does per-character font fallback automatically.
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "Times New Roman", "SimSun", "SimHei",
        "Microsoft YaHei", "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    import matplotlib.pyplot as plt
    _CARTOPY_AVAILABLE = True
except Exception:
    import traceback
    _CARTOPY_ERROR = traceback.format_exc()
    ccrs = None           # type: ignore[assignment]
    cimgt = None          # type: ignore[assignment]
    plt = None            # type: ignore[assignment]
    _CARTOPY_AVAILABLE = False
    # Write error to temp file so it's visible without a console
    try:
        import tempfile as _tf
        _log = Path(_tf.gettempdir()) / "rmw_cartopy_error.txt"
        _log.write_text(_CARTOPY_ERROR, encoding="utf-8")
    except Exception:
        pass

_DATA_DIR = Path(__file__).parent.parent / "data"

# ── Panel layout (A4 landscape 297 × 210 mm → figure fractions) ──────────────
# (a) and (b) are the same height (78 mm).  (c) spans their full combined height
# so all three share the same top edge (188 mm from bottom) and (b)/(c) share
# the same bottom edge (27 mm from bottom).
# Origin = figure bottom-left.
_W, _H = 297.0, 210.0
_AX_CHINA    = [5/_W, 110/_H,  90/_W,  78/_H]   # top=188 mm, bot=110 mm
_AX_PROVINCE = [5/_W,  27/_H,  90/_W,  78/_H]   # top=105 mm, bot= 27 mm
_AX_DETAIL   = [100/_W, 27/_H, 182/_W, 161/_H]  # top=188 mm, bot= 27 mm
_AX_CHINA_FULL = [5/_W, 27/_H, 90/_W, 161/_H]  # 2-panel mode: full left column height
_LARGE_SHP_THRESHOLD = 5.0  # degrees; custom SHP wider/taller than this → skip province panel

# ── Basemap registry ──────────────────────────────────────────────────────────
# Each entry: url_template (str or None for cimgt.OSM), fallback hex colour.
# URL vars: {x} {y} {z} — x/y are tile coords, z is zoom level.
BASEMAP_REGISTRY: dict[str, dict] = {
    "esri_gray": {
        "label_zh": "ESRI 浅灰（学术）",
        "label_en": "ESRI Light Gray",
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"),
        "fallback": "#D8E4EE",
    },
    "esri_topo": {
        "label_zh": "ESRI 地形图",
        "label_en": "ESRI World Topo",
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"),
        "fallback": "#F0EDE0",
    },
    "esri_natgeo": {
        "label_zh": "ESRI 国家地理",
        "label_en": "ESRI NatGeo",
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}"),
        "fallback": "#F5F0E8",
    },
    "esri_relief": {
        "label_zh": "ESRI 晕渲地形",
        "label_en": "ESRI Shaded Relief",
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}"),
        "fallback": "#E8E8E8",
    },
    "osm": {
        "label_zh": "OpenStreetMap",
        "label_en": "OpenStreetMap",
        "url": None,   # special: use cimgt.OSM()
        "fallback": "#F2EFE9",
    },
    "carto_light": {
        "label_zh": "CartoDB 极简白",
        "label_en": "CartoDB Positron",
        "url": "https://a.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png",
        "fallback": "#FFFFFF",
    },
}


def _zoom_for_span(span_deg: float) -> int:
    """Tile zoom level for a geographic span in degrees."""
    if span_deg > 50: return 4
    if span_deg > 20: return 5
    if span_deg > 10: return 6
    if span_deg > 5:  return 7
    if span_deg > 2:  return 8
    if span_deg > 1:  return 9
    return 10


def _grid_interval(span_deg: float) -> float:
    """Choose a round gridline interval for the given span."""
    if span_deg < 0.5:  return 0.1
    if span_deg < 1.5:  return 0.2
    if span_deg < 3.0:  return 0.5
    if span_deg < 6.0:  return 1.0
    return 2.0


def _add_basemap_tiles(ax, basemap_key: str, zoom: int) -> bool:
    """Load tiles for the chosen basemap; return True on success."""
    if not _CARTOPY_AVAILABLE:
        return False
    meta = BASEMAP_REGISTRY.get(basemap_key, BASEMAP_REGISTRY["esri_gray"])
    url = meta["url"]
    try:
        if url is None:
            tiler = cimgt.OSM()
        else:
            url_tmpl = url   # capture for closure

            class _Tiler(cimgt.GoogleWTS):
                def _image_url(self, tile):
                    x, y, z = tile
                    return url_tmpl.format(x=x, y=y, z=z)

            tiler = _Tiler()
        ax.add_image(tiler, zoom)
        return True
    except Exception:
        return False


class CartopyRenderer(BaseRenderer):
    """Render three-panel location maps with cartopy + matplotlib."""

    def check_available(self) -> tuple[bool, str]:
        if _CARTOPY_AVAILABLE:
            import matplotlib, cartopy
            return True, f"cartopy {cartopy.__version__} / matplotlib {matplotlib.__version__}"
        reason = _CARTOPY_ERROR.strip().splitlines()[-1] if _CARTOPY_ERROR else "cartopy 或 matplotlib 未安装"
        return False, reason

    def get_project_path(self) -> Optional[Path]:
        return None

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        if not _CARTOPY_AVAILABLE:
            raise RenderFailedError("cartopy 未安装，无法使用 Cartopy 渲染引擎")

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        # Detect large custom SHP → 2-panel mode (skip province panel)
        self._use_two_panel = False
        if config.custom_shp:
            shp_path = Path(config.custom_shp)
            if not shp_path.exists():
                raise RenderFailedError(f"自定义 SHP 文件不存在: {shp_path}")
            try:
                from src.core.boundary_manager import read_shp_safe
                _shp = read_shp_safe(shp_path)
                if _shp.crs and _shp.crs.to_epsg() != 4326:
                    _shp = _shp.to_crs(epsg=4326)
                _b = _shp.total_bounds
                if max(_b[2] - _b[0], _b[3] - _b[1]) > _LARGE_SHP_THRESHOLD:
                    self._use_two_panel = True
            except RenderFailedError:
                raise
            except Exception as exc:
                raise RenderFailedError(f"无法读取自定义 SHP: {exc}") from exc

        try:
            _p(0, "创建画布...")
            fig = plt.figure(figsize=(_W / 25.4, _H / 25.4), dpi=config.dpi)
            fig.patch.set_facecolor("white")

            _p(10, "绘制中国全图 (a)...")
            ax_china = self._add_china_panel(fig, config)

            ax_province = None
            if not self._use_two_panel:
                _p(35, "绘制省级图 (b)...")
                ax_province = self._add_province_panel(fig, config)

            _p(55, "绘制研究区详图 (c)...")
            ax_detail = self._add_detail_panel(fig, config)

            _p(75, "添加标题和注记...")
            self._add_title(fig, config)
            self._add_panel_labels(fig, config)
            self._add_footer(fig, config)
            if config.show_north_arrow and not config.show_grid:
                self._add_north_arrow(ax_detail)
            if config.show_scalebar:
                self._add_scalebar(ax_detail, config)
            if config.show_zoom_lines:
                # Force matplotlib to finalise axis positions before reading them.
                # Cartopy GeoAxes shrink themselves to maintain aspect ratio, so
                # ax.get_position() only returns the real on-canvas bbox after draw.
                # Use 72 DPI for this intermediate render — ax.get_position() returns
                # figure-fraction coords that are DPI-independent, so the result is
                # identical to a full-DPI draw but uses ~17x less memory.
                _orig_dpi = fig.get_dpi()
                fig.set_dpi(72)
                fig.canvas.draw()
                fig.set_dpi(_orig_dpi)
                self._add_zoom_connections(fig, ax_china, ax_province, ax_detail, config)

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

    def _read_layer(self, gpkg_path, layer: str,
                    filter_col: str | None = None, filter_val: str | None = None):
        import geopandas as gpd
        p = Path(gpkg_path)
        if not p.exists():
            return None
        gdf = gpd.read_file(p, layer=layer)
        if filter_col and filter_val:
            gdf = gdf[gdf[filter_col] == filter_val]
        return gdf if not gdf.empty else None

    # ── Panels ────────────────────────────────────────────────────────────────

    def _add_china_panel(self, fig, config: RenderConfig):
        """(a) China overview with ESRI basemap + province/custom-SHP highlight."""
        lcc = ccrs.LambertConformal(
            central_longitude=105, central_latitude=35,
            standard_parallels=(25, 47),
        )
        rect = _AX_CHINA_FULL if getattr(self, "_use_two_panel", False) else _AX_CHINA
        ax = fig.add_axes(rect, projection=lcc)
        # Pin to top-left so the top border aligns with the detail map top border.
        ax.set_anchor("NW")
        ax.set_extent([73, 135, 15, 54], crs=ccrs.PlateCarree())

        # Basemap tiles (fills the full panel, no clip needed)
        bm = config.basemap or "esri_gray"
        tile_ok = _add_basemap_tiles(ax, bm, zoom=4)
        if not tile_ok:
            ax.set_facecolor(BASEMAP_REGISTRY.get(bm, {}).get("fallback", "#D8E4EE"))

        # Province polygons — low-opacity fill so basemap shows through
        prov = self._read_layer(config.province_boundary, "province")
        if prov is not None:
            prov.plot(ax=ax, facecolor="#DDEEDD40", edgecolor="#777777",
                      linewidth=0.3, transform=ccrs.PlateCarree(), zorder=3)
            if config.province_adcode and not config.custom_shp:
                sel = prov[prov["adcode"] == config.province_adcode]
                if not sel.empty:
                    sel.plot(ax=ax, facecolor=f"{config.highlight_color}44",
                             edgecolor=config.highlight_color, linewidth=1.2,
                             transform=ccrs.PlateCarree(), zorder=4)

        # Country outline
        country = self._read_layer(config.country_boundary, "country")
        if country is not None:
            country.plot(ax=ax, facecolor="none", edgecolor="#222222",
                         linewidth=0.7, transform=ccrs.PlateCarree(), zorder=5)

        # Always draw study-area red box on the China map, regardless of
        # whether zoom connection lines are enabled.
        if config.custom_shp:
            try:
                import numpy as _np
                from src.core.boundary_manager import read_shp_safe as _rss
                _shp = _rss(Path(config.custom_shp))
                if _shp.crs and _shp.crs.to_epsg() != 4326:
                    _shp = _shp.to_crs(epsg=4326)
                _b = _shp.total_bounds  # [minx, miny, maxx, maxy]
                _lons = [_b[0], _b[2], _b[2], _b[0], _b[0]]
                _lats = [_b[1], _b[1], _b[3], _b[3], _b[1]]
                ax.plot(_lons, _lats, "-", color=config.highlight_color,
                        linewidth=1.2, transform=ccrs.PlateCarree(), zorder=6)
            except Exception:
                pass
        elif config.city_adcode:
            try:
                _city = self._read_layer(config.city_boundary, "city",
                                         filter_col="adcode",
                                         filter_val=config.city_adcode)
                if _city is not None:
                    _city.plot(ax=ax, facecolor="none",
                               edgecolor=config.highlight_color, linewidth=1.0,
                               transform=ccrs.PlateCarree(), zorder=6)
            except Exception:
                pass

        ax.spines["geo"].set_linewidth(0.6)
        return ax

    def _add_province_panel(self, fig, config: RenderConfig):
        """(b) Province zoom with ESRI basemap + city highlight."""
        ax = fig.add_axes(_AX_PROVINCE, projection=ccrs.PlateCarree())

        prov_code = config.province_adcode or ""
        prov = self._read_layer(config.province_boundary, "province",
                                filter_col="adcode", filter_val=prov_code)

        # Set extent first so tiles cover the right area
        if prov is not None:
            b = prov.total_bounds
            pad = max(b[2]-b[0], b[3]-b[1]) * 0.08
            ax.set_extent([b[0]-pad, b[2]+pad, b[1]-pad, b[3]+pad],
                          crs=ccrs.PlateCarree())
            span = max(b[2]-b[0], b[3]-b[1])
        else:
            span = 10.0

        # Basemap tiles
        bm = config.basemap or "esri_gray"
        tile_ok = _add_basemap_tiles(ax, bm, zoom=_zoom_for_span(span))
        if not tile_ok:
            ax.set_facecolor(BASEMAP_REGISTRY.get(bm, {}).get("fallback", "#EAF4FB"))

        # Province fill (low-opacity so basemap shows through)
        if prov is not None:
            prov.plot(ax=ax, facecolor="#E8F0E040", edgecolor="#555555",
                      linewidth=0.6, transform=ccrs.PlateCarree(), zorder=3)

        # Cities in province
        cities = self._read_layer(config.city_boundary, "city",
                                  filter_col="province_adcode", filter_val=prov_code)
        if cities is not None:
            cities.plot(ax=ax, facecolor="#D0DDC840", edgecolor="#444444",
                        linewidth=0.4, transform=ccrs.PlateCarree(), zorder=4)
            if config.city_adcode:
                sel = cities[cities["adcode"] == config.city_adcode]
                if not sel.empty:
                    sel.plot(ax=ax, facecolor=f"{config.highlight_color}55",
                             edgecolor=config.highlight_color, linewidth=1.0,
                             transform=ccrs.PlateCarree(), zorder=5)

        ax.spines["geo"].set_linewidth(0.6)
        return ax

    def _add_detail_panel(self, fig, config: RenderConfig):
        """(c) Study-area detail with basemap + raster + academic zebra frame."""
        import matplotlib.ticker as mticker

        ax = fig.add_axes(_AX_DETAIL, projection=ccrs.PlateCarree())

        # Prefer custom SHP if provided; fall back to admin city boundary
        if config.custom_shp:
            shp_path = Path(config.custom_shp)
            if not shp_path.exists():
                raise RenderFailedError(f"自定义 SHP 文件不存在: {shp_path}")
            try:
                from src.core.boundary_manager import read_shp_safe
                city = read_shp_safe(shp_path)
                if city.crs is None:
                    raise RenderFailedError("自定义 SHP 缺少坐标参考系（.prj 文件），无法制图")
                if city.crs.to_epsg() != 4326:
                    city = city.to_crs(epsg=4326)
                if city.empty or city.geometry.is_empty.all():
                    raise RenderFailedError("自定义 SHP 文件中没有有效几何要素")
            except RenderFailedError:
                raise
            except Exception as exc:
                raise RenderFailedError(f"读取自定义 SHP 失败: {exc}") from exc
        else:
            city = self._read_layer(config.city_boundary, "city",
                                    filter_col="adcode", filter_val=config.city_adcode)

        bounds = None
        if city is not None:
            bounds = city.total_bounds
            pad = max(bounds[2]-bounds[0], bounds[3]-bounds[1]) * 0.15
            ax.set_extent([bounds[0]-pad, bounds[2]+pad,
                           bounds[1]-pad, bounds[3]+pad],
                          crs=ccrs.PlateCarree())
            span = max(bounds[2]-bounds[0], bounds[3]-bounds[1])
        else:
            ax.set_global()
            span = 10.0

        # Basemap tiles (fill full panel before vector layers)
        bm = config.basemap or "esri_gray"
        zoom = _zoom_for_span(span)
        tile_ok = _add_basemap_tiles(ax, bm, zoom=zoom)
        fallback_color = BASEMAP_REGISTRY.get(bm, {}).get("fallback", "#F4F4F0")
        if not tile_ok:
            ax.set_facecolor(fallback_color)

        # Surrounding province cities as context (subtle fill, low opacity)
        if config.province_adcode:
            ctx = self._read_layer(config.city_boundary, "city",
                                   filter_col="province_adcode",
                                   filter_val=config.province_adcode)
            if ctx is not None:
                ctx.plot(ax=ax, facecolor="#E0E5DC55", edgecolor="#888888",
                         linewidth=0.4, transform=ccrs.PlateCarree(), zorder=2)

        # Optional raster overlay
        if config.raster_path and Path(config.raster_path).exists():
            self._draw_raster(ax, config)

        # Target city: semi-transparent fill + bold outline
        if city is not None:
            city.plot(ax=ax, facecolor=f"{config.highlight_color}2A",
                      edgecolor=config.highlight_color, linewidth=1.8,
                      transform=ccrs.PlateCarree(), zorder=5)

        # Gridlines: explicit interval so zebra frame aligns exactly
        interval = _grid_interval(span)
        gl = None
        if config.show_grid:
            gl = ax.gridlines(
                draw_labels=True, linewidth=0.35,
                color="#555555", alpha=0.4, linestyle="--",
                x_inline=False, y_inline=False,
            )
            gl.top_labels = False
            gl.left_labels = False
            gl.right_labels = True
            gl.xlocator = mticker.MultipleLocator(interval)
            gl.ylocator = mticker.MultipleLocator(interval)
            gl.xlabel_style = {"size": 7, "fontname": "Times New Roman"}
            gl.ylabel_style = {"size": 7, "fontname": "Times New Roman"}

            # Academic zebra frame (replaces plain geo spine)
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            xticks = [t for t in mticker.MultipleLocator(interval).tick_values(xlim[0], xlim[1])]
            yticks = [t for t in mticker.MultipleLocator(interval).tick_values(ylim[0], ylim[1])]
            self._add_zebra_frame(ax, xticks, yticks)
        else:
            ax.spines["geo"].set_linewidth(0.8)

        self._detail_lat = ((bounds[1]+bounds[3])/2) if bounds is not None else 35.0
        return ax

    # ── Academic zebra frame ──────────────────────────────────────────────────

    @staticmethod
    def _add_zebra_frame(ax, xticks: list, yticks: list, s: float = 0.008) -> None:
        """Alternating black/white border strips aligned with gridline intervals.

        `s` is the frame thickness as a fraction of the axes size.
        """
        from matplotlib.patches import Rectangle

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()

        def fracs(ticks, lim):
            """Clamp tick values to [lim0, lim1] and return as axis fractions."""
            pts = sorted({lim[0]} | {t for t in ticks if lim[0] < t < lim[1]} | {lim[1]})
            span = lim[1] - lim[0]
            return [(p - lim[0]) / span for p in pts]

        xf = fracs(xticks, xlim)
        yf = fracs(yticks, ylim)

        def seg(x, y, w, h, color):
            ax.add_patch(Rectangle(
                (x, y), w, h,
                transform=ax.transAxes,
                facecolor=color, edgecolor="none",
                clip_on=False, linewidth=0, zorder=15,
            ))

        # Four edges: alternating black / white per gridline interval
        for i, (x0, x1) in enumerate(zip(xf[:-1], xf[1:])):
            c = "black" if i % 2 == 0 else "white"
            seg(x0, -s, x1 - x0, s, c)   # bottom
            seg(x0, 1.0, x1 - x0, s, c)  # top

        for i, (y0, y1) in enumerate(zip(yf[:-1], yf[1:])):
            c = "black" if i % 2 == 0 else "white"
            seg(-s, y0, s, y1 - y0, c)   # left
            seg(1.0, y0, s, y1 - y0, c)  # right

        # Solid black corners
        for cx, cy in [(-s, -s), (1.0, -s), (-s, 1.0), (1.0, 1.0)]:
            seg(cx, cy, s, s, "black")

        # Inner map border (replaces invisible geo spine)
        ax.spines["geo"].set_linewidth(0)
        for lw, rect in [
            (0.5, Rectangle((0, 0), 1, 1)),
            (0.8, Rectangle((-s, -s), 1 + 2 * s, 1 + 2 * s)),
        ]:
            rect.set_transform(ax.transAxes)
            rect.set_fill(False)
            rect.set_edgecolor("black")
            rect.set_linewidth(lw)
            rect.set_clip_on(False)
            rect.set_zorder(16)
            ax.add_patch(rect)

    # ── Zoom connection lines ─────────────────────────────────────────────────

    def _add_zoom_connections(self, fig, ax_china, ax_province, ax_detail, config: RenderConfig) -> None:
        """Leader lines linking panels to show the zoom relationship.

        3-panel mode: (a) zoom box → (b) top corners; (b) city zoom box → (c) left corners.
        2-panel mode (large custom SHP): (a) right edge corners → (c) left corners.

        Call AFTER fig.canvas.draw() so that ax.get_position() returns the real
        on-canvas bounding box (cartopy shrinks GeoAxes to maintain aspect ratio).
        """
        from matplotlib.lines import Line2D
        from matplotlib.patches import Rectangle

        lc = "#555555"
        lw = 0.75
        two_panel = getattr(self, "_use_two_panel", False)

        def _pos(ax):
            """Return [x0, y0, width, height] in figure fraction after layout."""
            p = ax.get_position()
            return [p.x0, p.y0, p.width, p.height]

        def _line(p1, p2, color=lc):
            fig.add_artist(Line2D(
                [p1[0], p2[0]], [p1[1], p2[1]],
                transform=fig.transFigure, color=color,
                linewidth=lw, linestyle="--", clip_on=False, zorder=20,
            ))

        def _box(x0, y0, x1, y1, color, lw_box=0.9):
            fig.add_artist(Rectangle(
                (x0, y0), x1 - x0, y1 - y0,
                transform=fig.transFigure, fill=False,
                edgecolor=color, linewidth=lw_box,
                linestyle="--", clip_on=False, zorder=20,
            ))

        def _geo_to_fig(ax, lons_arr, lats_arr, crs_src=None):
            """Convert geographic points to figure fraction coords."""
            import numpy as _np
            if crs_src is not None:
                lcc = ccrs.LambertConformal(
                    central_longitude=105, central_latitude=35,
                    standard_parallels=(25, 47),
                )
                pts3d = lcc.transform_points(crs_src, lons_arr, lats_arr)
                pts = pts3d[:, :2]
            else:
                pts = _np.column_stack([lons_arr, lats_arr])
            disp = ax.transData.transform(pts)
            return fig.transFigure.inverted().transform(disp)

        def _clamp_to_panel(fp, rect):
            x0, y0, w, h = rect
            x1, y1 = x0 + w, y0 + h
            return (
                max(x0, min(x1, fp[:, 0].min())),
                max(y0, min(y1, fp[:, 1].min())),
                max(x0, min(x1, fp[:, 0].max())),
                max(y0, min(y1, fp[:, 1].max())),
            )

        # Actual rendered positions of the detail panel (c)
        dp = _pos(ax_detail)
        c_tl = (dp[0], dp[1] + dp[3])   # top-left corner of (c)
        c_bl = (dp[0], dp[1])            # bottom-left corner of (c)

        # ── 2-PANEL MODE (large custom SHP): SHP bbox right corners → (c) left ──
        if two_panel:
            import numpy as _np2
            cp = _pos(ax_china)
            box_drawn = False
            if config.custom_shp:
                try:
                    from src.core.boundary_manager import read_shp_safe
                    shp = read_shp_safe(Path(config.custom_shp))
                    if shp.crs and shp.crs.to_epsg() != 4326:
                        shp = shp.to_crs(epsg=4326)
                    b = shp.total_bounds
                    lons = _np2.array([b[0], b[2], b[2], b[0]])
                    lats = _np2.array([b[1], b[1], b[3], b[3]])
                    fp = _geo_to_fig(ax_china, lons, lats, ccrs.PlateCarree())
                    bx0, by0, bx1, by1 = _clamp_to_panel(fp, cp)
                    _box(bx0, by0, bx1, by1, config.highlight_color)
                    # Connect from SHP bbox right corners to (c) left corners
                    _line((bx1, by1), c_tl)
                    _line((bx1, by0), c_bl)
                    box_drawn = True
                except Exception:
                    pass
            if not box_drawn:
                # Fallback: connect from China panel right edge
                _line((cp[0] + cp[2], cp[1] + cp[3]), c_tl)
                _line((cp[0] + cp[2], cp[1]),          c_bl)
            return

        # ── 3-PANEL MODE ──────────────────────────────────────────────────────

        import numpy as np

        def _shp_bounds_in_panel(ax_panel, panel_rect):
            """Return clamped figure-fraction bbox of the custom SHP in ax_panel."""
            from src.core.boundary_manager import read_shp_safe
            shp = read_shp_safe(Path(config.custom_shp))
            if shp.crs and shp.crs.to_epsg() != 4326:
                shp = shp.to_crs(epsg=4326)
            b = shp.total_bounds
            lons = np.array([b[0], b[2], b[2], b[0]])
            lats = np.array([b[1], b[1], b[3], b[3]])
            fp = _geo_to_fig(ax_panel, lons, lats)
            return _clamp_to_panel(fp, panel_rect)

        # Step 1: (b) study-area zoom box → right side connects to (c) left corners
        city_connected = False
        if ax_province is not None:
            try:
                pp = _pos(ax_province)
                if config.custom_shp:
                    # Use custom SHP bounding box in province panel
                    cx0, cy0, cx1, cy1 = _shp_bounds_in_panel(ax_province, pp)
                    _box(cx0, cy0, cx1, cy1, config.highlight_color, lw_box=0.8)
                    _line((cx1, cy1), c_tl)
                    _line((cx1, cy0), c_bl)
                    city_connected = True
                elif config.city_adcode:
                    city = self._read_layer(config.city_boundary, "city",
                                            filter_col="adcode", filter_val=config.city_adcode)
                    if city is not None:
                        cb = city.total_bounds
                        lons = np.array([cb[0], cb[2], cb[2], cb[0]])
                        lats = np.array([cb[1], cb[1], cb[3], cb[3]])
                        fp_c = _geo_to_fig(ax_province, lons, lats)
                        cx0, cy0, cx1, cy1 = _clamp_to_panel(fp_c, pp)
                        _box(cx0, cy0, cx1, cy1, config.highlight_color, lw_box=0.8)
                        _line((cx1, cy1), c_tl)
                        _line((cx1, cy0), c_bl)
                        city_connected = True
            except Exception:
                pass

        # Fallback: connect (b) right edge directly to (c) left corners
        if not city_connected and ax_province is not None:
            pp = _pos(ax_province)
            _line((pp[0] + pp[2], pp[1] + pp[3]), c_tl)
            _line((pp[0] + pp[2], pp[1]),          c_bl)

        # Step 2: (a) study-area zoom box → (b) top corners
        if ax_china is None:
            return
        try:
            cp = _pos(ax_china)
            pp = _pos(ax_province) if ax_province is not None else None

            if config.custom_shp:
                # Draw custom SHP bbox on China panel and connect to (b) top
                bx0, by0, bx1, by1 = _shp_bounds_in_panel(ax_china, cp)
                _box(bx0, by0, bx1, by1, config.highlight_color, lw_box=1.0)
                if pp is not None:
                    b_tl = (pp[0],         pp[1] + pp[3])
                    b_tr = (pp[0] + pp[2], pp[1] + pp[3])
                    _line((bx0, by0), b_tl, color=config.highlight_color)
                    _line((bx1, by0), b_tr, color=config.highlight_color)
            elif config.province_adcode:
                prov = self._read_layer(config.province_boundary, "province",
                                        filter_col="adcode", filter_val=config.province_adcode)
                if prov is None:
                    return
                b = prov.total_bounds
                lons = np.array([b[0], b[2], b[2], b[0]])
                lats = np.array([b[1], b[1], b[3], b[3]])
                fp = _geo_to_fig(ax_china, lons, lats, ccrs.PlateCarree())
                bx0, by0, bx1, by1 = _clamp_to_panel(fp, cp)
                _box(bx0, by0, bx1, by1, config.highlight_color, lw_box=1.0)
                if pp is not None:
                    b_tl = (pp[0],         pp[1] + pp[3])
                    b_tr = (pp[0] + pp[2], pp[1] + pp[3])
                    _line((bx0, by0), b_tl, color=config.highlight_color)
                    _line((bx1, by0), b_tr, color=config.highlight_color)
        except Exception:
            pass

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
                      origin="upper", aspect="auto", zorder=3)
        elif config.data_type == "hillshade":
            with rasterio.open(raster_path) as src:
                data = src.read(1)
            ax.imshow(data, extent=extent, transform=ccrs.PlateCarree(),
                      cmap="gray", vmin=0, vmax=255, origin="upper",
                      aspect="auto", zorder=3)
        elif config.data_type == "sentinel2":
            with rasterio.open(raster_path) as src:
                rgb = src.read([1, 2, 3])
            rgb = np.clip(rgb / 255.0, 0, 1).transpose(1, 2, 0)
            ax.imshow(rgb, extent=extent, transform=ccrs.PlateCarree(),
                      origin="upper", aspect="auto", zorder=3)

    # ── Annotations ───────────────────────────────────────────────────────────

    @staticmethod
    def _load_en_names() -> dict[str, str]:
        """Return adcode → English name dict built from cities.json."""
        cities_json = _DATA_DIR / "cities.json"
        if not cities_json.exists():
            return {}
        try:
            import json
            data = json.loads(cities_json.read_text(encoding="utf-8"))
            names: dict[str, str] = {}
            for prov in data.get("provinces", []):
                if "adcode" in prov and "name_en" in prov:
                    names[prov["adcode"]] = prov["name_en"]
                for city in prov.get("cities", []):
                    if "adcode" in city and "name_en" in city:
                        names[city["adcode"]] = city["name_en"]
            return names
        except Exception:
            return {}

    def _to_english(self, name_zh: str, adcode: str) -> str:
        """Return English name: cities.json lookup → pypinyin → bare name."""
        if not hasattr(self, "_en_names"):
            self._en_names = self._load_en_names()
        en = self._en_names.get(adcode, "")
        if en:
            return en
        # Strip common suffixes and try again by stripping them from name_zh
        stripped = name_zh.rstrip("市省区县自治区特别行政区")
        for code, ename in self._en_names.items():
            pass  # already tried adcode above
        # Fallback: pypinyin if available, else raw Chinese
        try:
            from pypinyin import lazy_pinyin, Style
            parts = lazy_pinyin(stripped, style=Style.FIRST_LETTER)
            # Capitalize each syllable via normal pinyin
            from pypinyin import pinyin
            syllables = [s[0] for s in pinyin(stripped, style=Style.NORMAL)]
            return " ".join(s.capitalize() for s in syllables)
        except ImportError:
            return stripped

    def _add_title(self, fig, config: RenderConfig) -> None:
        is_en = config.language == "en"
        if config.title:
            title = config.title
        else:
            # Priority: explicit custom_name → SHP filename → city name
            if config.custom_name:
                area_name = config.custom_name
            elif config.custom_shp:
                area_name = Path(config.custom_shp).stem
            else:
                area_name = config.city_name
            if is_en:
                area_en = self._to_english(area_name, config.city_adcode)
                title = f"Location Map of {area_en} Study Area"
            else:
                title = f"{area_name}研究区区位图"

        # Centre title across the full figure width
        fig.text(0.5, 0.982, title,
                 ha="center", va="top",
                 fontsize=13, fontweight="bold",
                 fontname="SimHei" if not is_en else "Times New Roman")

    def _add_panel_labels(self, fig, config: RenderConfig) -> None:
        """(a)(b) in 2-panel mode; (a)(b)(c) in 3-panel mode."""
        two_panel = getattr(self, "_use_two_panel", False)
        china_rect = _AX_CHINA_FULL if two_panel else _AX_CHINA
        if two_panel:
            panels = [("(a)", china_rect), ("(b)", _AX_DETAIL)]
        else:
            panels = [("(a)", china_rect), ("(b)", _AX_PROVINCE), ("(c)", _AX_DETAIL)]
        for label, ax_rect in panels:
            x = ax_rect[0]                   # left edge of panel
            y = ax_rect[1] + ax_rect[3]      # top edge of panel
            fig.text(
                x, y + 0.004, label,
                ha="left", va="bottom",      # text sits just above top border
                fontsize=10, fontweight="bold", fontstyle="italic",
                fontname="Times New Roman",
            )

    def _add_footer(self, fig, config: RenderConfig) -> None:
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        is_en = config.language == "en"
        if is_en:
            footer = (
                f"Coordinate System: WGS84 (EPSG:4326)  |  "
                f"Data: Google Earth Engine / Tianditu  |  Date: {today}"
            )
        else:
            footer = (
                f"坐标系: WGS84 (EPSG:4326)  |  "
                f"数据来源: Google Earth Engine / 天地图  |  制图日期: {today}"
            )
        # Place below the lowest panel bottom
        # SimHei confirmed present in font cache; Times New Roman for English-only mode
        footer_font = "Times New Roman" if is_en else "SimHei"
        # Both (b) and (c) share the same bottom edge; footer sits 4 mm below
        min_bottom = _AX_DETAIL[1]   # == _AX_PROVINCE[1] == 27/210
        fig.text(0.5, min_bottom - 0.019, footer,
                 ha="center", va="top",
                 fontsize=6, color="#777777",
                 fontname=footer_font)

    def _add_north_arrow(self, ax) -> None:
        """North arrow — only drawn when gridlines are disabled."""
        ax.annotate("", xy=(0.955, 0.935), xytext=(0.955, 0.855),
                    xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color="black",
                                   lw=1.5, mutation_scale=12))
        ax.text(0.955, 0.96, "N", transform=ax.transAxes,
                ha="center", va="center", fontsize=9, fontweight="bold",
                fontname="Times New Roman")

    def _add_scalebar(self, ax, config: RenderConfig) -> None:
        lat = getattr(self, "_detail_lat", 35.0)
        meters_per_deg = math.cos(math.radians(lat)) * 111_320
        try:
            from matplotlib_scalebar.scalebar import ScaleBar
            ax.add_artist(ScaleBar(
                meters_per_deg, units="m", location="lower left",
                font_properties={"size": 7, "family": "Times New Roman"},
                sep=3, pad=0.4, border_pad=0.5,
                box_color="white", box_alpha=0.7,
            ))
        except ImportError:
            ax.text(0.04, 0.04, "50 km", transform=ax.transAxes,
                    fontsize=7, ha="left", va="bottom", color="#444444",
                    fontname="Times New Roman")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_color_ramp(name: str) -> dict | None:
        p = _DATA_DIR / "color_ramps.json"
        if not p.exists():
            return None
        with p.open(encoding="utf-8") as f:
            ramps = json.load(f)
        return ramps.get(name)
