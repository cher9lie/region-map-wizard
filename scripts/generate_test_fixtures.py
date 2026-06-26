"""Generate test fixture GeoTIFFs for use in pytest without real GEE data."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds


OUTPUT_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def make_sample_dem(output: Path = OUTPUT_DIR / "sample_dem.tif") -> None:
    """100×100 float32 DEM covering 116.0-116.5°E, 39.5-40.0°N (Beijing area)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    # Simulate some terrain: base elevation ~50m with variation
    data = (rng.integers(0, 800, (100, 100)) + 50).astype(np.float32)

    transform = from_bounds(116.0, 39.5, 116.5, 40.0, 100, 100)
    with rasterio.open(
        output, "w",
        driver="GTiff",
        height=100, width=100,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data[np.newaxis, :, :])

    print(f"Written: {output}")


def make_sample_boundary(output: Path = OUTPUT_DIR / "sample_boundary.geojson") -> None:
    """Minimal GeoJSON covering the same area as sample_dem.tif."""
    geojson = """{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {"name": "test_area"},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[116.0, 39.5],[116.5, 39.5],[116.5, 40.0],[116.0, 40.0],[116.0, 39.5]]]
      }
    }
  ]
}"""
    output.write_text(geojson, encoding="utf-8")
    print(f"Written: {output}")


if __name__ == "__main__":
    make_sample_dem()
    make_sample_boundary()
    print("Done.")
