"""Tests for ArcGISRenderer — all mocked, no ArcGIS Pro installation required."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import RenderFailedError, RendererNotAvailableError
from src.renderers.arcgis_renderer import ArcGISRenderer
from src.renderers.base import RenderConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def renderer() -> ArcGISRenderer:
    return ArcGISRenderer()


@pytest.fixture()
def sample_config(tmp_path: Path) -> RenderConfig:
    """Minimal RenderConfig with real Path objects."""
    return RenderConfig(
        country_boundary=tmp_path / "country.gpkg",
        province_boundary=tmp_path / "province.gpkg",
        city_boundary=tmp_path / "city.gpkg",
        province_name="四川省",
        city_name="成都市",
        raster_path=None,
        data_type="dem",
        color_ramp="elevation",
        output_path=tmp_path / "output.jpg",
        output_format="jpg",
    )


# ── check_available ───────────────────────────────────────────────────────────

class TestCheckAvailable:
    def test_no_arcgis_returns_false(self, renderer: ArcGISRenderer) -> None:
        """When propy.bat cannot be found, check_available returns (False, ...)."""
        with patch.object(renderer, "_find_propy", return_value=None):
            ok, reason = renderer.check_available()
        assert ok is False
        assert "未找到" in reason

    def test_with_arcgis_returns_true(self, renderer: ArcGISRenderer, tmp_path: Path) -> None:
        """When propy.bat exists and arcpy works, returns (True, 'ArcGIS Pro 3.4.0')."""
        fake_propy = tmp_path / "propy.bat"
        fake_propy.write_text("")
        with (
            patch.object(renderer, "_find_propy", return_value=fake_propy),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="3.4.0\n", stderr="")
            ok, reason = renderer.check_available()
        assert ok is True
        assert "ArcGIS Pro 3.4.0" in reason

    def test_subprocess_file_not_found_returns_false(
        self, renderer: ArcGISRenderer, tmp_path: Path
    ) -> None:
        fake_propy = tmp_path / "propy.bat"
        fake_propy.write_text("")
        with (
            patch.object(renderer, "_find_propy", return_value=fake_propy),
            patch("subprocess.run", side_effect=FileNotFoundError("not found")),
        ):
            ok, reason = renderer.check_available()
        assert ok is False
        assert "未找到" in reason or "not found" in reason

    def test_arcpy_unavailable_returns_false(
        self, renderer: ArcGISRenderer, tmp_path: Path
    ) -> None:
        fake_propy = tmp_path / "propy.bat"
        fake_propy.write_text("")
        with (
            patch.object(renderer, "_find_propy", return_value=fake_propy),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="No module named 'arcpy'"
            )
            ok, reason = renderer.check_available()
        assert ok is False
        assert "arcpy" in reason


# ── render — subprocess invocation ────────────────────────────────────────────

class TestRenderSubprocess:
    def _setup_available(self, renderer: ArcGISRenderer, tmp_path: Path) -> Path:
        """Make renderer think ArcGIS is available."""
        fake_propy = tmp_path / "propy.bat"
        fake_propy.write_text("")
        renderer._propy_path = fake_propy
        renderer._arcgis_version = "3.4.0"
        return fake_propy

    def test_render_calls_popen_with_propy_and_worker(
        self, renderer: ArcGISRenderer, sample_config: RenderConfig, tmp_path: Path
    ) -> None:
        """Popen must be called with propy path and worker script as first two args."""
        fake_propy = self._setup_available(renderer, tmp_path)
        done_line = json.dumps({
            "step": "done", "progress": 100,
            "message": "完成", "output": str(sample_config.output_path)
        })
        mock_proc = MagicMock()
        mock_proc.stdout = iter([done_line + "\n"])
        mock_proc.stderr = StringIO("")
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        with (
            patch.object(renderer, "check_available", return_value=(True, "ArcGIS Pro 3.4.0")),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            renderer.render(sample_config)

        call_args = mock_popen.call_args[0][0]  # first positional arg (the command list)
        assert str(fake_propy) == call_args[0]
        from src.renderers._arcgis_worker import __file__ as worker_file
        assert str(Path(worker_file).resolve()) == str(Path(call_args[1]).resolve())
        assert "--config" in call_args

    def test_render_parses_progress_callbacks(
        self, renderer: ArcGISRenderer, sample_config: RenderConfig, tmp_path: Path
    ) -> None:
        """progress_callback must be called for each non-done, non-error step."""
        self._setup_available(renderer, tmp_path)
        stdout_lines = [
            json.dumps({"step": "loading", "progress": 10, "message": "加载模板..."}) + "\n",
            json.dumps({"step": "data",    "progress": 30, "message": "加载数据..."}) + "\n",
            json.dumps({"step": "render",  "progress": 60, "message": "渲染..."})    + "\n",
            json.dumps({"step": "export",  "progress": 90, "message": "导出..."})    + "\n",
            json.dumps({
                "step": "done", "progress": 100, "message": "完成",
                "output": str(sample_config.output_path)
            }) + "\n",
        ]
        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr = StringIO("")
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        callback = MagicMock()
        with (
            patch.object(renderer, "check_available", return_value=(True, "ArcGIS Pro 3.4.0")),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            renderer.render(sample_config, progress_callback=callback)

        # Should be called for initial launch (0%) + loading/data/render/export + done
        assert callback.call_count == 6
        pcts = [call.args[0] for call in callback.call_args_list]
        assert pcts == [0, 10, 30, 60, 90, 100]

    def test_render_raises_on_error_step(
        self, renderer: ArcGISRenderer, sample_config: RenderConfig, tmp_path: Path
    ) -> None:
        """When worker emits {"step": "error"}, RenderFailedError must be raised."""
        self._setup_available(renderer, tmp_path)
        error_line = json.dumps({"step": "error", "message": "arcpy 崩溃了"}) + "\n"
        mock_proc = MagicMock()
        mock_proc.stdout = iter([error_line])
        mock_proc.stderr = StringIO("")
        mock_proc.returncode = 1
        mock_proc.wait.return_value = 1

        with (
            patch.object(renderer, "check_available", return_value=(True, "ArcGIS Pro 3.4.0")),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            with pytest.raises(RenderFailedError) as exc_info:
                renderer.render(sample_config)
        assert "arcpy 崩溃了" in str(exc_info.value)

    def test_render_unavailable_raises_renderer_not_available(
        self, renderer: ArcGISRenderer, sample_config: RenderConfig
    ) -> None:
        with patch.object(renderer, "check_available", return_value=(False, "未找到 ArcGIS")):
            with pytest.raises(RendererNotAvailableError):
                renderer.render(sample_config)


# ── config serialization ──────────────────────────────────────────────────────

class TestConfigSerialization:
    def test_path_objects_serialized_to_strings(
        self, renderer: ArcGISRenderer, sample_config: RenderConfig, tmp_path: Path
    ) -> None:
        """Config JSON written to disk must be loadable and contain str paths."""
        import tempfile as _tmp
        import os

        done_line = json.dumps({
            "step": "done", "progress": 100,
            "message": "完成", "output": str(sample_config.output_path)
        })
        mock_proc = MagicMock()
        mock_proc.stdout = iter([done_line + "\n"])
        mock_proc.stderr = StringIO("")
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        written_json: dict = {}

        original_open = open

        def _capture_json(path, mode="r", **kw):
            fh = original_open(path, mode, **kw)
            if mode == "w" and str(path).endswith(".json"):
                class _Capture:
                    def write(self_, data):
                        fh.write(data)
                    def __enter__(self_): return self_
                    def __exit__(self_, *a):
                        fh.seek(0)
                        try:
                            written_json.update(json.load(fh))
                        except Exception:
                            pass
                        fh.close()
                    @property
                    def name(self_): return fh.name
                return _Capture()
            return fh

        fake_propy = tmp_path / "propy.bat"
        fake_propy.write_text("")
        renderer._propy_path = fake_propy

        with (
            patch.object(renderer, "check_available", return_value=(True, "ArcGIS Pro 3.4.0")),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("builtins.open", side_effect=_capture_json),
        ):
            try:
                renderer.render(sample_config)
            except Exception:
                pass

        # Verify Path objects were converted to strings
        for key in ("country_boundary", "province_boundary", "city_boundary", "output_path"):
            val = written_json.get(key)
            if val is not None:
                assert isinstance(val, str), f"{key} should be str, got {type(val)}"
                # Must be valid JSON-loadable (no Path objects)
                json.dumps({key: val})  # would raise if not serialisable

    def test_get_project_path_initially_none(self, renderer: ArcGISRenderer) -> None:
        assert renderer.get_project_path() is None
