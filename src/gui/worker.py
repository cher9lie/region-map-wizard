"""QThread worker that runs MapWizardPipeline.run() off the main thread."""

from __future__ import annotations

from pathlib import Path

try:
    from PyQt5.QtCore import QThread, pyqtSignal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    # Stub so the module can be imported without PyQt5
    class QThread:  # type: ignore[no-redef]
        pass
    class pyqtSignal:  # type: ignore[no-redef]
        def __init__(self, *a, **kw): pass

from src.core.pipeline import MapWizardPipeline
from src.renderers.base import RenderConfig


if _QT_AVAILABLE:
    class MapWorker(QThread):
        """Execute the full render pipeline in a background thread."""

        progress = pyqtSignal(int, str)    # percent, message
        log = pyqtSignal(str)              # log line
        finished = pyqtSignal(str)         # output path
        error = pyqtSignal(str)            # error message

        def __init__(self, pipeline: MapWizardPipeline, config: RenderConfig) -> None:
            super().__init__()
            self._pipeline = pipeline
            self._config = config
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            try:
                output = self._pipeline.run(
                    self._config,
                    progress_callback=self._on_progress,
                    log_callback=self._on_log,
                )
                if not self._cancelled:
                    self.finished.emit(str(output))
            except Exception as exc:
                self.error.emit(str(exc))

        def _on_progress(self, pct: int, msg: str) -> None:
            if not self._cancelled:
                self.progress.emit(pct, msg)

        def _on_log(self, msg: str) -> None:
            if not self._cancelled:
                self.log.emit(msg)

else:
    class MapWorker:  # type: ignore[no-redef]
        """Stub used when PyQt5 is unavailable."""
        def __init__(self, *a, **kw): pass
