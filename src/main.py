"""Application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _setup_bundled_dlls() -> None:
    """Register *.libs DLL directories when running as a PyInstaller bundle.

    pyogrio / rasterio / pyproj / shapely pip wheels bundle GDAL, GEOS and PROJ
    DLLs inside sibling *.libs directories.  Their delvewheel startup patches
    find those dirs via __file__, which is a *virtual* path inside the PYZ
    archive and fails os.path.isdir().  We replicate the registration here
    using the real filesystem path before any GIS package is imported.
    """
    base = Path(getattr(sys, "_MEIPASS", ""))
    if not base.is_dir():
        exe = Path(sys.executable).resolve()
        for candidate in [exe.parent / "_internal", exe.parent]:
            if candidate.is_dir():
                base = candidate
                break
    if not base.is_dir():
        return

    libs_dirs = [d for d in base.iterdir() if d.is_dir() and d.name.endswith(".libs")]

    for d in libs_dirs:
        try:
            os.add_dll_directory(str(d))
        except Exception:
            pass

    # Prepend to PATH so that any legacy DLL loader (including the one inside
    # pyogrio's delvewheel patch) can also find the DLLs via PATH lookup.
    if libs_dirs:
        extra = os.pathsep.join(str(d) for d in libs_dirs)
        os.environ["PATH"] = extra + os.pathsep + os.environ.get("PATH", "")


# Must be called before any GIS package is imported.
_setup_bundled_dlls()


def main() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
    except ImportError:
        print("PyQt5 未安装，请先运行: pip install PyQt5", file=sys.stderr)
        sys.exit(1)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Region Map Wizard")

    qss_path = Path(__file__).parent / "resources" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    from src.gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
