"""Tests for QGISRenderer — no QGIS installation required.

All subprocess calls and registry reads are mocked so the test suite works
in any CI environment.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import RenderFailedError, RendererNotAvailableError
from src.renderers.qgis_renderer import QGISRenderer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.output_path = str(tmp_path / "out.jpg")
    cfg.output_format = "jpg"
    cfg.dpi = 300
    cfg.province_name = "湖南省"
    cfg.city_name = "长沙市"
    cfg.data_type = "dem"
    cfg.raster_path = ""
    cfg.country_boundary = ""
    cfg.province_boundary = ""
    cfg.city_boundary = ""
    # Make vars() work on the mock
    cfg.__dict__.update({k: getattr(cfg, k) for k in [
        "output_path", "output_format", "dpi",
        "province_name", "city_name", "data_type",
        "raster_path", "country_boundary", "province_boundary", "city_boundary",
    ]})
    return cfg


def _json_line(*args, **kwargs) -> bytes:
    return (json.dumps({"step": args[0], "progress": args[1],
                         "message": args[2], **kwargs},
                        ensure_ascii=False) + "\n").encode()


# ── Tests: check_available ────────────────────────────────────────────────────

class TestCheckAvailable:
    def _make_renderer(self, bat_path: Path) -> QGISRenderer:
        r = QGISRenderer()
        r._python_qgis_path = bat_path
        return r

    def test_returns_true_when_qgis_responds(self, tmp_path):
        bat = tmp_path / "python-qgis.bat"
        bat.touch()
        renderer = self._make_renderer(bat)

        mock_result = MagicMock(returncode=0,
                                stdout=b"3.34.3\n",
                                stderr=b"")
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = renderer.check_available()

        assert ok is True
        assert "3.34.3" in msg

    def test_returns_false_when_bat_missing(self):
        renderer = QGISRenderer()
        with patch.object(renderer, "_find_python_qgis", return_value=None):
            ok, msg = renderer.check_available()
        assert ok is False
        assert "未找到" in msg

    def test_returns_false_when_returncode_nonzero(self, tmp_path):
        bat = tmp_path / "python-qgis.bat"
        bat.touch()
        renderer = self._make_renderer(bat)

        mock_result = MagicMock(returncode=1,
                                stdout=b"",
                                stderr=b"Import error\n")
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = renderer.check_available()

        assert ok is False
        assert "不可用" in msg or "Import" in msg


# ── Tests: render ─────────────────────────────────────────────────────────────

class TestRender:
    def _make_available_renderer(self, tmp_path: Path) -> QGISRenderer:
        bat = tmp_path / "python-qgis.bat"
        bat.touch()
        r = QGISRenderer()
        r._python_qgis_path = bat
        r._qgis_version = "3.34.3"
        return r

    def _mock_render(self, renderer: QGISRenderer, stdout_lines: list[bytes],
                     returncode: int = 0):
        """Return a context manager that patches both check_available and Popen."""
        from unittest.mock import patch, MagicMock
        from io import BytesIO

        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr = BytesIO(b"")
        mock_proc.returncode = returncode
        mock_proc.wait.return_value = returncode

        class _CM:
            def __enter__(self_):
                self_._p1 = patch.object(
                    renderer, "check_available",
                    return_value=(True, "QGIS 3.34.3"),
                )
                self_._p2 = patch("subprocess.Popen", return_value=mock_proc)
                self_._p1.start()
                self_._p2.start()
                return mock_proc

            def __exit__(self_, *_):
                self_._p1.stop()
                self_._p2.stop()

        return _CM()

    def test_raises_when_not_available(self):
        renderer = QGISRenderer()
        with patch.object(renderer, "check_available", return_value=(False, "未安装")):
            with pytest.raises(RendererNotAvailableError):
                renderer.render(MagicMock())

    def test_render_success_returns_output_path(self, tmp_path):
        renderer = self._make_available_renderer(tmp_path)
        cfg = _make_config(tmp_path)
        output = str(tmp_path / "out.jpg")

        stdout_lines = [
            _json_line("loading",  5,  "初始化 QGIS 项目..."),
            _json_line("data",    15,  "加载行政区边界..."),
            _json_line("data",    30,  "加载栅格数据..."),
            _json_line("render",  60,  "创建地图框..."),
            _json_line("export",  88,  "导出 JPG..."),
            _json_line("done",   100,  "完成",
                       output=output, project=str(tmp_path / "out.qgz")),
        ]
        with self._mock_render(renderer, stdout_lines):
            result = renderer.render(cfg)

        assert result == Path(output)

    def test_render_parses_progress_callbacks(self, tmp_path):
        renderer = self._make_available_renderer(tmp_path)
        cfg = _make_config(tmp_path)
        output = str(tmp_path / "out.jpg")

        stdout_lines = [
            _json_line("loading",  5,  "初始化..."),
            _json_line("data",    30,  "加载数据..."),
            _json_line("render",  60,  "渲染..."),
            _json_line("export",  88,  "导出..."),
            _json_line("done",   100,  "完成",
                       output=output, project=str(tmp_path / "out.qgz")),
        ]
        calls: list[tuple[int, str]] = []
        with self._mock_render(renderer, stdout_lines):
            renderer.render(cfg, progress_callback=lambda p, m: calls.append((p, m)))

        pcts = [c[0] for c in calls]
        # First call is the initial _p(0, "启动..."), then 4 steps + done
        assert calls[0][0] == 0
        assert 5  in pcts
        assert 30 in pcts
        assert 60 in pcts
        assert 88 in pcts
        assert 100 in pcts

    def test_render_raises_on_error_step(self, tmp_path):
        renderer = self._make_available_renderer(tmp_path)
        cfg = _make_config(tmp_path)

        stdout_lines = [
            _json_line("loading", 5, "初始化..."),
            _json_line("error",   5, "找不到边界文件"),
        ]
        with self._mock_render(renderer, stdout_lines, returncode=1):
            with pytest.raises(RenderFailedError, match="找不到边界文件"):
                renderer.render(cfg)

    def test_render_stores_project_path(self, tmp_path):
        renderer = self._make_available_renderer(tmp_path)
        cfg = _make_config(tmp_path)
        output = str(tmp_path / "out.jpg")
        qgz = str(tmp_path / "out.qgz")

        stdout_lines = [
            _json_line("done", 100, "完成", output=output, project=qgz),
        ]
        with self._mock_render(renderer, stdout_lines):
            renderer.render(cfg)

        assert renderer.get_project_path() == Path(qgz)

    def test_non_json_stdout_lines_ignored(self, tmp_path):
        renderer = self._make_available_renderer(tmp_path)
        cfg = _make_config(tmp_path)
        output = str(tmp_path / "out.jpg")

        stdout_lines = [
            b"QGIS startup banner...\n",
            b"\xb3\xa4\xc9\xd0\r\n",   # GBK garbage
            _json_line("loading", 5, "初始化..."),
            _json_line("done", 100, "完成",
                       output=output, project=str(tmp_path / "out.qgz")),
        ]
        with self._mock_render(renderer, stdout_lines):
            result = renderer.render(cfg)

        assert result == Path(output)
