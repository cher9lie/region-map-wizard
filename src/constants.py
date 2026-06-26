"""Global constants for Region Map Wizard."""

VERSION = "1.0.0a1"
APP_NAME = "研究区区位图自动制图工具"
APP_NAME_EN = "Region Map Wizard"

# Default page size (mm)
PAGE_WIDTH_MM = 297
PAGE_HEIGHT_MM = 210

# Default DPI
DEFAULT_DPI = 300

# GEE download scale (meters per pixel)
DEM_DOWNLOAD_SCALE = 90       # 30m is overkill for location maps
HILLSHADE_DOWNLOAD_SCALE = 90
SENTINEL2_DOWNLOAD_SCALE = 100

# GEE datasets
GEE_SRTM_ASSET = "USGS/SRTMGL1_003"
GEE_S2_ASSET = "COPERNICUS/S2_SR_HARMONIZED"

# Cache
DEFAULT_CACHE_DIR_NAME = ".rmw_cache"
DEFAULT_CONFIG_DIR_NAME = ".rmw"

# Tile download
MAX_TILE_PIXELS = 10_000_000  # 10M pixels per tile
DOWNLOAD_TIMEOUT = 120        # seconds
DOWNLOAD_MAX_RETRIES = 3
