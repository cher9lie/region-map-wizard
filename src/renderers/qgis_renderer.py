"""QGIS rendering engine — calls PyQGIS via a subprocess worker script.

QGIS ships its own isolated Python environment on Windows (OSGeo4W or
standalone installer).  All PyQGIS code therefore lives in _qgis_worker.py,
which is launched through python-qgis.bat — the QGIS equivalent of ArcGIS
Pro's propy.bat.  This module never imports qgis.core directly.
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

_WORKER_SCRIPT = Path(__file__).parent / "_qgis_worker.py"

# python-qgis.bat candidates — checked in order when registry lookup fails.
# Both the standalone installer ("QGIS X.Y") and OSGeo4W variants are covered.
_PYTHON_QGIS_CANDIDATES: list[str] = []
for _ver in ("3.40", "3.38", "3.36", "3.34", "3.32", "3.30", "3.28"):
    _PYTHON_QGIS_CANDIDATES += [
        rf"C:\Program Files\QGIS {_ver}\bin\python-qgis.bat",
        rf"C:\Program Files\QGIS {_ver}\bin\python-qgis-ltr.bat",
    ]
_PYTHON_QGIS_CANDIDATES += [
    r"C:\OSGeo4W\bin\python-qgis.bat",
    r"C:\OSGeo4W64\bin\python-qgis.bat",
]


class QGISRenderer(BaseRenderer):
    """Render location maps using QGIS (PyQGIS) via a subprocess worker."""

    def __init__(self) -> None:
        self._python_qgis_path: Optional[Path] = None
        self._qgis_version: Optional[str] = None
        self._last_project_path: Optional[Path] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def check_available(self) -> tuple[bool, str]:
        """Detect QGIS availability.

        Detection order:
          1. Cached self._python_qgis_path
          2. QGIS_INSTALL_PATH env var → {path}/bin/python-qgis.bat
          3. Windows registry HKLM\\SOFTWARE\\QGIS\\QGIS3 → InstallPath
          4. Common installation paths (standalone + OSGeo4W)
          5. Verify by running:
               python-qgis.bat -c "from qgis.core import Qgis; print(Qgis.version())"
        """
        bat = self._find_python_qgis()
        if bat is None:
            return False, "未找到 QGIS 安装（python-qgis.bat 不存在）"
        try:
            result = subprocess.run(
                [str(bat), "-c",
                 "from qgis.core import Qgis; print(Qgis.version())"],
                capture_output=True,
                timeout=25,
            )
            stdout = result.stdout.decode("utf-8", errors="replace").strip()
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and stdout:
                self._python_qgis_path = bat
                self._qgis_version = stdout
                return True, f"QGIS {stdout}"
            return False, f"PyQGIS 不可用: {stderr}"
        except FileNotFoundError:
            return False, f"未找到 QGIS：{bat} 不存在"
        except subprocess.TimeoutExpired:
            return False, "QGIS 检测超时"
        except Exception as exc:
            return False, str(exc)

    def get_project_path(self) -> Optional[Path]:
        """Return the .qgz saved during the last render(), or None."""
        return self._last_project_path

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """Render via subprocess.

        Serialises config to a temporary JSON file, launches _qgis_worker.py
        through python-qgis.bat, reads stdout JSON lines for progress, and
        returns the output image path when done.
        """
        available, reason = self.check_available()
        if not available:
            raise RendererNotAvailableError("QGIS", reason)

        def _p(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)

        # Serialise config — convert Path objects to strings
        config_data: dict = {}
        for k, v in vars(config).items():
            if k.startswith("_"):
                continue
            config_data[k] = str(v) if isinstance(v, Path) else v

        config_data["output_dir"] = str(Path(config.output_path).parent)
        config_data["temp_dir"] = tempfile.gettempdir()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(config_data, tmp, ensure_ascii=False, indent=2)
            config_json = tmp.name

        self._last_project_path = None

        try:
            _p(0, "启动 QGIS 渲染进程...")
            process = subprocess.Popen(
                [str(self._python_qgis_path), str(_WORKER_SCRIPT),
                 "--config", config_json],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Drain stderr in a background thread to prevent pipe-buffer deadlock.
            stderr_chunks: list[bytes] = []
            def _drain_stderr() -> None:
                for chunk in process.stderr:  # type: ignore[union-attr]
                    stderr_chunks.append(chunk)
            _stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            _stderr_thread.start()

            output_path: Optional[str] = None
            for raw_bytes in process.stdout:  # type: ignore[union-attr]
                raw = raw_bytes.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                step = msg.get("step", "")
                pct = int(msg.get("progress", 0))
                text = msg.get("message", "")

                if step == "error":
                    raise RenderFailedError(text or "QGIS 渲染失败")
                if step == "done":
                    output_path = msg.get("output")
                    project_p = msg.get("project")
                    if project_p:
                        self._last_project_path = Path(project_p)
                    _p(100, text or "完成")
                    break
                _p(pct, text)

            _stderr_thread.join(timeout=5)
            process.wait(timeout=600)
            if process.returncode != 0:
                stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")[:300]
                raise RenderFailedError(
                    f"QGIS 渲染进程退出码 {process.returncode}: {stderr}"
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

    def _find_python_qgis(self) -> Optional[Path]:
        """Locate python-qgis.bat following the detection order above."""
        if self._python_qgis_path and self._python_qgis_path.exists():
            return self._python_qgis_path

        # 1. Environment variable
        env_path = os.environ.get("QGIS_INSTALL_PATH")
        if env_path:
            for name in ("python-qgis.bat", "python-qgis-ltr.bat"):
                candidate = Path(env_path) / "bin" / name
                if candidate.exists():
                    return candidate

        # 2. Windows registry
        install_dir = _read_qgis_registry()
        if install_dir:
            for name in ("python-qgis.bat", "python-qgis-ltr.bat"):
                candidate = Path(install_dir) / "bin" / name
                if candidate.exists():
                    return candidate

        # 3. Common paths
        for path_str in _PYTHON_QGIS_CANDIDATES:
            p = Path(path_str)
            if p.exists():
                return p

        return None


def _read_qgis_registry() -> Optional[str]:
    """Read QGIS InstallPath from the Windows registry."""
    try:
        import winreg
        for sub_key in (r"SOFTWARE\QGIS\QGIS3",
                        r"SOFTWARE\QGIS\QGIS3-LTR",
                        r"SOFTWARE\QGIS"):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_key)
                install_dir, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if install_dir:
                    return install_dir
            except OSError:
                continue
    except Exception:
        pass
    return None
