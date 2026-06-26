"""ArcGIS Pro rendering engine — calls arcpy via a subprocess worker script."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from src.renderers.base import BaseRenderer, RenderConfig
from src.core.exceptions import RenderFailedError, RendererNotAvailableError

_WORKER_SCRIPT = Path(__file__).parent / "_arcgis_worker.py"

# Common ArcGIS Pro Python executable locations
_ARCGIS_PYTHON_CANDIDATES = [
    r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe",
    r"C:\Program Files (x86)\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe",
]


class ArcGISRenderer(BaseRenderer):
    """Render location maps using ArcGIS Pro (arcpy) via subprocess."""

    def __init__(self) -> None:
        self._python_exe: Optional[Path] = None

    def check_available(self) -> tuple[bool, str]:
        exe = self._find_arcgis_python()
        if exe is None:
            return False, "未检测到 ArcGIS Pro Python 环境"
        try:
            result = subprocess.run(
                [str(exe), "-c",
                 "import arcpy; info=arcpy.GetInstallInfo(); print(info['Version'])"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                version = result.stdout.strip()
                self._python_exe = exe
                return True, f"ArcGIS Pro {version}"
            return False, f"arcpy 不可用: {result.stderr.strip()}"
        except Exception as exc:
            return False, str(exc)

    def get_project_path(self) -> Optional[Path]:
        return None

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        available, reason = self.check_available()
        if not available:
            raise RendererNotAvailableError("ArcGIS Pro", reason)

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        # Serialise config to a temp JSON file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            config_data = {
                k: str(v) if isinstance(v, Path) else v
                for k, v in vars(config).items()
                if not k.startswith("_")
            }
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            config_path = f.name

        try:
            _p(0, "启动 ArcGIS Pro 渲染进程...")
            process = subprocess.Popen(
                [str(self._python_exe), str(_WORKER_SCRIPT), config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )

            last_output_path: Optional[str] = None
            for line in process.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    pct = msg.get("progress", 0)
                    text = msg.get("message", "")
                    output_p = msg.get("output_path")
                    _p(pct, text)
                    if output_p:
                        last_output_path = output_p
                except json.JSONDecodeError:
                    pass  # non-JSON log line

            process.wait(timeout=300)
            if process.returncode != 0:
                raise RenderFailedError(f"ArcGIS 渲染进程退出码 {process.returncode}")

            if last_output_path:
                return Path(last_output_path)
            return Path(config.output_path)

        except (RenderFailedError, RendererNotAvailableError):
            raise
        except Exception as exc:
            raise RenderFailedError(str(exc)) from exc
        finally:
            Path(config_path).unlink(missing_ok=True)

    # ── Private ───────────────────────────────────────────────────────────────

    def _find_arcgis_python(self) -> Optional[Path]:
        if self._python_exe and self._python_exe.exists():
            return self._python_exe

        # 1. User-configured path
        # (would be read from ConfigManager in the real pipeline)

        # 2. Well-known locations
        for candidate in _ARCGIS_PYTHON_CANDIDATES:
            p = Path(candidate)
            if p.exists():
                return p

        return None
