"""Fixtures for workflow-construction tests.

These build real :class:`ConfigManager` sections and empty input directories so
each ``*_workflow`` builder can be assembled and its node graph inspected —
without any DICOM data, FSL/FreeSurfer execution, or network access.

A subject :class:`ConfigManager` transiently instantiates a *global* config in
the user's home directory, so ``isolated_home`` redirects ``HOME``/
``USERPROFILE`` to a throwaway folder to keep the real user config untouched.
"""

import pytest

from swane.config.ConfigManager import ConfigManager


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect the home directory so config writes never touch the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def subject_config(tmp_path, isolated_home):
    """A subject :class:`ConfigManager` preloaded with workflow-preference defaults."""
    subject_dir = tmp_path / "subject"
    subject_dir.mkdir()
    return ConfigManager(subject_folder=str(subject_dir))


@pytest.fixture
def global_config(tmp_path, isolated_home):
    """A global :class:`ConfigManager` (holds the ``synth`` tool section)."""
    base = tmp_path / "global"
    base.mkdir()
    return ConfigManager(global_base_folder=str(base))


@pytest.fixture
def make_input_dir(tmp_path):
    """Return a factory creating empty 'DICOM' input directories on demand.

    The workflow builders only store these paths on a ``CustomDcm2niix`` node
    (whose ``source_dir`` trait requires an existing directory); the folders can
    be empty because nothing is ever read from them at construction time.
    """

    def _make(name="dicom"):
        path = tmp_path / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    return _make
