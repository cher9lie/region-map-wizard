# PyInstaller runtime hook — runs before any user module is imported.
# Registers all *.libs DLL directories so GDAL/GEOS/PROJ native extensions
# (pyogrio, rasterio, pyproj, shapely, cartopy) can be loaded.
import os
import sys
from pathlib import Path


def _setup_dll_dirs():
    base = Path(getattr(sys, "_MEIPASS", ""))
    if not base.is_dir():
        # Fallback: look next to the executable (_internal sibling)
        exe = Path(sys.executable).resolve()
        for candidate in [exe.parent / "_internal", exe.parent]:
            if candidate.is_dir():
                base = candidate
                break

    if not base.is_dir():
        return

    libs_dirs = [str(d) for d in base.iterdir()
                 if d.is_dir() and d.name.endswith(".libs")]

    for d in libs_dirs:
        # os.add_dll_directory is the preferred Win10+ mechanism
        try:
            os.add_dll_directory(d)
        except Exception:
            pass

    # Also prepend to PATH — fallback for delvewheel patches and any
    # DLL loader that resolves via PATH rather than the directory list.
    if libs_dirs:
        os.environ["PATH"] = (
            os.pathsep.join(libs_dirs)
            + os.pathsep
            + os.environ.get("PATH", "")
        )

    # Add _MEIPASS itself (some DLLs land at the root level)
    try:
        os.add_dll_directory(str(base))
    except Exception:
        pass


_setup_dll_dirs()
