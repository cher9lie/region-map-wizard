"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path


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

    # Load stylesheet
    qss_path = Path(__file__).parent / "resources" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    from src.gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
