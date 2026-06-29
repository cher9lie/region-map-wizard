"""ArcGIS Pro rendering engine — calls arcpy via a subprocess worker script.

All arcpy code lives in _arcgis_worker.py, which runs inside the ArcGIS Pro
conda environment.  This module never imports arcpy directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from src.core.exceptions import RenderFailedError, RendererNotAvailableError
from src.renderers.base import BaseRenderer, RenderConfig

_WORKER_SCRIPT = Path(__file__).parent / "_arcgis_worker.py"
_TEMPLATE_APRX = Path(__file__).parent.parent / "resources" / "templates" / "location_map_template.aprx"

# Candidate propy.bat paths (checked in order when registry lookup fails)
_PROPY_CANDIDATES: list[str] = [
    r"C:\Program Files\ArcGIS\Pro\bin\Python\scripts\propy.bat",
    r"C:\Program Files (x86)\ArcGIS\Pro\bin\Python\scripts\propy.bat",
    r"C:\ArcGIS\Pro\bin\Python\scripts\propy.bat",
]


class ArcGISRenderer(BaseRenderer):
    """Render location maps using ArcGIS Pro (arcpy) via a subprocess worker."""

    def __init__(self) -> None:
        self._propy_path: Optional[Path] = None
        self._arcgis_version: Optional[str] = None
        self._last_project_path: Optional[Path] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def check_available(self) -> tuple[bool, str]:
        """Detect ArcGIS Pro availability.

        Detection order (per SPEC §4.3.1):
          1. Cached self._propy_path
          2. ARCGIS_PRO_PATH env var
          3. Windows registry HKLM\\SOFTWARE\\ESRI\\ArcGISPro → InstallDir
          4. Common installation paths
          5. Verify by running: arcpy.GetInstallInfo()['Version']
        """
        propy = self._find_propy()
        if propy is None:
            return False, "未找到 ArcGIS Pro 安装（propy.bat 不存在）"
        try:
            result = subprocess.run(
                [str(propy), "-c",
                 "import arcpy; info=arcpy.GetInstallInfo(); print(info['Version'])"],
                capture_output=True,
                timeout=20,
            )
            # Decode with errors="replace" to tolerate GBK output from propy.bat
            stdout = result.stdout.decode("utf-8", errors="replace").strip()
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and stdout:
                self._propy_path = propy
                self._arcgis_version = stdout
                return True, f"ArcGIS Pro {stdout}"
            return False, f"arcpy 不可用: {stderr}"
        except FileNotFoundError:
            return False, f"未找到 ArcGIS Pro：{propy} 不存在"
        except subprocess.TimeoutExpired:
            return False, "ArcGIS Pro 检测超时"
        except Exception as exc:
            return False, str(exc)

    def get_project_path(self) -> Optional[Path]:
        """Return the .aprx saved during the last render(), or None."""
        return self._last_project_path

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """Render via subprocess.

        Serialises config to a temporary JSON file, launches _arcgis_worker.py
        through propy.bat, reads stdout JSON lines for progress, and returns
        the output image path when done.
        """
        available, reason = self.check_available()
        if not available:
            raise RendererNotAvailableError("ArcGIS Pro", reason)

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        # Build config dict: convert Path objects to strings
        config_data: dict = {}
        for k, v in vars(config).items():
            if k.startswith("_"):
                continue
            config_data[k] = str(v) if isinstance(v, Path) else v

        # Add worker-specific fields
        config_data["template_path"] = str(_TEMPLATE_APRX)
        config_data["temp_dir"] = tempfile.gettempdir()
        config_data["output_dir"] = str(Path(config.output_path).parent)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(config_data, tmp, ensure_ascii=False, indent=2)
            config_json = tmp.name

        self._last_project_path = None

        try:
            _p(0, "启动 ArcGIS Pro 渲染进程...")
            process = subprocess.Popen(
                [str(self._propy_path), str(_WORKER_SCRIPT), "--config", config_json],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Read as bytes; propy.bat may emit GBK-encoded banner/error lines
                # that would crash a utf-8 text reader.
            )

            # Drain stderr in a background thread to prevent pipe-buffer deadlock.
            # If stderr fills its OS pipe buffer (65 KB on Windows) while we are
            # reading stdout, the worker blocks on stderr and we block on stdout.
            stderr_chunks: list[bytes] = []
            def _drain_stderr() -> None:
                for chunk in process.stderr:  # type: ignore[union-attr]
                    stderr_chunks.append(chunk)
            _stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            _stderr_thread.start()

            output_path: Optional[str] = None
            for raw_bytes in process.stdout:  # type: ignore[union-attr]
                # Decode as UTF-8 (worker JSON lines) and tolerate GBK bytes
                # from cmd.exe wrappers by replacing undecodable bytes.
                raw = raw_bytes.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # non-JSON log line (e.g. propy.bat banner), ignore

                step = msg.get("step", "")
                pct = int(msg.get("progress", 0))
                text = msg.get("message", "")

                if step == "error":
                    raise RenderFailedError(text or "ArcGIS 渲染失败")
                if step == "done":
                    output_path = msg.get("output")
                    project_p = msg.get("project")
                    if project_p:
                        self._last_project_path = Path(project_p)
                    _p(100, text or "完成")
                    break
                _p(pct, text)

            _stderr_thread.join(timeout=5)
            process.wait(timeout=300)
            if process.returncode != 0:
                stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")[:300]
                raise RenderFailedError(
                    f"ArcGIS 渲染进程退出码 {process.returncode}: {stderr}"
                )

            if output_path:
                return Path(output_path)
            return Path(config.output_path)

        except (RenderFailedError, RendererNotAvailableError):
            raise
        except Exception as exc:
            raise RenderFailedError(str(exc)) from exc
        finally:
            Path(config_json).unlink(missing_ok=True)

    # ── Private ───────────────────────────────────────────────────────────────

    def _find_propy(self) -> Optional[Path]:
        """Locate propy.bat following SPEC §4.3.1 detection order."""
        # 1. Cached result
        if self._propy_path and self._propy_path.exists():
            return self._propy_path

        # 2. Environment variable
        env_path = os.environ.get("ARCGIS_PRO_PATH")
        if env_path:
            candidate = Path(env_path) / "bin" / "Python" / "scripts" / "propy.bat"
            if candidate.exists():
                return candidate

        # 3. Windows registry
        install_dir = _read_arcgis_registry()
        if install_dir:
            candidate = Path(install_dir) / "bin" / "Python" / "scripts" / "propy.bat"
            if candidate.exists():
                return candidate

        # 4. Common installation paths
        for path_str in _PROPY_CANDIDATES:
            p = Path(path_str)
            if p.exists():
                return p

        return None


def _read_arcgis_registry() -> Optional[str]:
    """Read ArcGIS Pro InstallDir from the Windows registry."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\ESRI\ArcGISPro",
        )
        install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
        winreg.CloseKey(key)
        return install_dir
    except Exception:
        return None
