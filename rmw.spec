# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Region Map Wizard."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
VENV_SP = ROOT / ".venv" / "Lib" / "site-packages"

# ── Native DLLs from pip wheel *.libs dirs ─────────────────────────────────
binaries = []
for libs_dir in VENV_SP.glob("*.libs"):
    for dll in libs_dir.glob("*.dll"):
        binaries.append((str(dll), libs_dir.name))

# pyogrio C extension .pyd files — not auto-discovered when the importing
# module (pyogrio.geopandas) is not in the dependency graph visible to PyInstaller
for pyd in (VENV_SP / "pyogrio").glob("*.pyd"):
    binaries.append((str(pyd), "pyogrio"))

# ── Data files ─────────────────────────────────────────────────────────────
datas = [
    (str(ROOT / "src" / "data"),      "src/data"),
    (str(ROOT / "src" / "resources"), "src/resources"),
]

# PROJ datum data
proj_data = VENV_SP / "pyproj" / "proj_dir" / "share" / "proj"
if proj_data.exists():
    datas.append((str(proj_data), "pyproj/proj_dir/share/proj"))

# matplotlib fonts/styles
datas += collect_data_files("matplotlib", includes=["mpl-data/**/*"])

# cartopy offline data
datas += collect_data_files("cartopy", includes=["data/**/*"])

# ── Analysis ───────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "src" / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # App modules — list explicitly to avoid recursion
        "src.constants",
        "src.core.config_manager",
        "src.core.boundary_manager",
        "src.core.pipeline",
        "src.core.exceptions",
        "src.core.gee_fetcher",
        "src.core.data_processor",
        "src.core.cache_manager",
        "src.renderers.base",
        "src.renderers.cartopy_renderer",
        "src.renderers.qgis_renderer",
        "src.renderers.arcgis_renderer",
        "src.gui.main_window",
        "src.gui.worker",
        "src.gui.gee_auth_dialog",
        "src.gui.shp_import_dialog",
        # PyQt5
        "PyQt5.sip",
        "PyQt5.QtPrintSupport",
        "PyQt5.QtXml",
        # GIS — pyogrio: collect all submodules so geopandas.py (which imports
        # _geometry) is included, triggering collection of _geometry.pyd
        *collect_submodules("pyogrio"),
        "shapely",
        "shapely.geometry",
        "shapely.ops",
        "shapely.vectorized",
        "cartopy",
        "cartopy.crs",
        "cartopy.io.img_tiles",
        "cartopy.feature",
        "cartopy.mpl.geoaxes",
        "cartopy.mpl.ticker",
        "cartopy.mpl.patch",
        "pyproj",
        "pyproj.transformer",
        "pyproj.crs",
        "rasterio",
        "rasterio.crs",
        "rasterio.transform",
        "rasterio.features",
        # matplotlib
        "matplotlib.backends.backend_agg",
        "matplotlib.backends.backend_pdf",
        "matplotlib_scalebar.scalebar",
        # others
        "PIL",
        "PIL.Image",
        "pandas",
        "numpy",
    ],
    hookspath=[],
    runtime_hooks=["hooks/rthook_gdal_dlls.py"],
    excludes=[
        "PyQt5.QtWebEngine",
        "PyQt5.QtWebEngineWidgets",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RegionMapWizard",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RegionMapWizard",
)
