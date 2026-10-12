"""
Tests for ``_read_ic_mix`` file discovery (Review Focus 5) and the DataSink
``regexp_substitutions`` for the FSL-engine result rename
``melodic_mix`` → ``ica_mix``.

``_read_ic_mix`` is a private function inside ``slicer_script_result.py``;
it is imported via the test's ``slicer_mod`` fixture which loads the module
with recording stand-ins for the ``slicer``/``vtk``/``qt`` modules.

The DataSink substitution is verified by running the same ``re.sub`` that
Nipype's DataSink applies, proving that the regex renames the FSL result.
"""

import importlib.util
import os
import re
import sys
import types

import numpy as np
import pytest

# slicer_script_result imports SimpleITK at module level (it normally runs inside
# 3D Slicer); SimpleITK is not a SWANe dependency, so skip when it is absent.
pytest.importorskip("SimpleITK", reason="SimpleITK is not installed")

import swane

MODULE_PATH = os.path.join(
    os.path.dirname(swane.__file__), "workers", "slicer_script_result.py"
)


def _fake_module(name):
    """Return a module whose every attribute returns a silent no-op stub."""
    module = types.ModuleType(name)

    class _Stub:
        def __getattr__(self, attr):
            if attr.startswith("__") and attr.endswith("__"):
                raise AttributeError(attr)
            return _Stub()

        def __call__(self, *a, **kw):
            return _Stub()

        def __repr__(self):
            return f"<stub>"

    module.__dict__["_root"] = _Stub()
    module.__getattr__ = lambda attr, _r=module.__dict__["_root"]: getattr(_r, attr)
    return module


@pytest.fixture
def slicer_mod(monkeypatch):
    """Load ``slicer_script_result`` with fake slicer/vtk/qt."""
    for name in ("slicer", "vtk", "qt"):
        monkeypatch.setitem(sys.modules, name, _fake_module(name))
    spec = importlib.util.spec_from_file_location(
        "swane_slicer_result_ic_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReadIcMix:
    """``_read_ic_mix`` discovers the IC mixing-matrix file."""

    def test_ica_mix_is_preferred(self, slicer_mod, tmp_path):
        """When both ``ica_mix`` and ``melodic_mix`` exist, ``ica_mix`` wins."""
        mix = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        np.savetxt(tmp_path / "ica_mix", mix)
        np.savetxt(tmp_path / "melodic_mix", mix * 100)  # different data

        result = slicer_mod._read_ic_mix(str(tmp_path))
        assert result is not None
        assert len(result) == 2  # 2 components
        assert result[0] == pytest.approx([1.0, 3.0, 5.0])

    def test_melodic_mix_fallback(self, slicer_mod, tmp_path):
        """Pre-change results that only have ``melodic_mix`` still load
        (Review Focus 5: old results in Slicer)."""
        mix = np.array([[10.0, 20.0], [30.0, 40.0]])
        np.savetxt(tmp_path / "melodic_mix", mix)

        result = slicer_mod._read_ic_mix(str(tmp_path))
        assert result is not None
        assert len(result) == 2
        assert result[0] == pytest.approx([10.0, 30.0])

    def test_missing_both_returns_none(self, slicer_mod, tmp_path):
        """Neither ``ica_mix`` nor ``melodic_mix`` → None."""
        assert slicer_mod._read_ic_mix(str(tmp_path)) is None


class TestDataSinkSubstitution:
    """The FSL-engine DataSink ``regexp_substitutions`` renames ``melodic_mix``
    to ``ica_mix``."""

    @pytest.fixture
    def substitution_pattern(self):
        """The pattern used in MainWorkflow for the FSL ic_mix sink."""
        return (r"melodic_mix$", "ica_mix")

    def test_full_path_renamed(self, substitution_pattern):
        """``regexp_substitutions`` matches the full destination path."""
        pattern, replacement = substitution_pattern
        src = "/some/base/fMRI_resting_state/melodic_mix"
        result = re.sub(pattern, replacement, src)
        assert result == "/some/base/fMRI_resting_state/ica_mix"

    def test_prefix_is_preserved(self, substitution_pattern):
        """Only the trailing ``melodic_mix`` is replaced, the rest stays."""
        pattern, replacement = substitution_pattern
        src = "/path/to/work/dir/results/fMRI_resting_state/melodic_mix"
        result = re.sub(pattern, replacement, src)
        assert result.endswith("/ica_mix")
        assert "/fMRI_resting_state/" in result

    def test_other_files_not_affected(self, substitution_pattern):
        """Files that do not end with ``melodic_mix`` are untouched."""
        pattern, replacement = substitution_pattern
        for path in (
            "/path/melodic_IC.nii.gz",
            "/path/melodic_FTmix",
            "/path/ica_mix",
            "/path/thresh_zstat01.nii.gz",
        ):
            assert re.sub(pattern, replacement, path) == path


class TestTimecourseViewerRetry:
    """A failed ``_show`` (mix table not loaded yet) must not be cached."""

    def test_ic_not_cached_until_plotted(self, slicer_mod, monkeypatch):
        viewer = slicer_mod.TimecourseViewer()
        volume = types.SimpleNamespace(GetName=lambda: "r-thresh_zstat01")
        monkeypatch.setattr(slicer_mod, "_get_active_zstat", lambda node: (volume, 1))
        results = iter([False, True])
        shown = []

        def fake_show(ic, name):
            shown.append(ic)
            return next(results)

        monkeypatch.setattr(viewer, "_show", fake_show)

        viewer._on_composite_modified(object(), None)  # table not ready
        assert viewer._last_ic is None
        viewer._on_composite_modified(object(), None)  # same IC retried
        assert viewer._last_ic == 1
        viewer._on_composite_modified(object(), None)  # now cached
        assert shown == [1, 1]


class TestTimecourseViewerLayout:
    """The layout restored on hide must never be a plot layout."""

    @staticmethod
    def _setup(slicer_mod, monkeypatch, start_layout):
        plot_layout = 36
        layout_node = types.SimpleNamespace(
            SlicerLayoutConventionalView=2,
            SlicerLayoutConventionalPlotView=plot_layout,
            SlicerLayoutFourUpPlotView=37,
            SlicerLayoutFourUpPlotTableView=38,
            SlicerLayoutOneUpPlotView=39,
            SlicerLayoutThreeOverThreePlotView=40,
        )
        manager = types.SimpleNamespace(layout=start_layout)
        manager.setLayout = lambda value: setattr(manager, "layout", value)
        fake_slicer = types.SimpleNamespace(
            vtkMRMLLayoutNode=layout_node,
            app=types.SimpleNamespace(layoutManager=lambda: manager),
        )
        monkeypatch.setattr(slicer_mod, "slicer", fake_slicer)
        viewer = slicer_mod.TimecourseViewer()
        viewer._previous_layout = None
        return viewer, manager

    def test_plot_layout_not_remembered(self, slicer_mod, monkeypatch):
        viewer, manager = self._setup(slicer_mod, monkeypatch, 36)
        viewer._hide()
        assert manager.layout == 2

    def test_user_layout_restored(self, slicer_mod, monkeypatch):
        viewer, manager = self._setup(slicer_mod, monkeypatch, 3)
        viewer._previous_layout = 3
        manager.layout = 36
        viewer._hide()
        assert manager.layout == 3
