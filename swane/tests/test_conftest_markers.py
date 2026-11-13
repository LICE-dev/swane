"""The ``requires_slicer`` marker honours ``SWANE_SLICER_PATH``.

CI installs Slicer outside PATH and without a ``~/.SWANe`` configuration, and
exports its executable as ``SWANE_SLICER_PATH`` (the variable the prerelease
sweep already reads): the marker must then enable the Slicer tests.
"""

import pytest

from swane.tests import conftest


@pytest.fixture
def no_other_slicer(monkeypatch):
    """Neither ``Slicer`` on PATH nor a Slicer in the user's configuration."""
    monkeypatch.setattr(conftest.shutil, "which", lambda name: None)
    monkeypatch.setattr(conftest, "_configured_slicer_path", lambda: None)
    monkeypatch.delenv("SWANE_SLICER_PATH", raising=False)


def test_env_path_enables_the_marker(no_other_slicer, monkeypatch, tmp_path):
    slicer = tmp_path / "Slicer"
    slicer.write_text("")
    monkeypatch.setenv("SWANE_SLICER_PATH", str(slicer))
    assert conftest._TOOL_MARKERS["requires_slicer"]()


def test_env_path_to_a_missing_file_does_not(no_other_slicer, monkeypatch, tmp_path):
    monkeypatch.setenv("SWANE_SLICER_PATH", str(tmp_path / "missing"))
    assert not conftest._TOOL_MARKERS["requires_slicer"]()


def test_no_slicer_anywhere_disables_the_marker(no_other_slicer):
    assert not conftest._TOOL_MARKERS["requires_slicer"]()
