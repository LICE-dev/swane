"""Shared fixtures for the ``nipype_pipeline`` unit tests.

These build tiny synthetic NIfTI volumes and plain text files on the fly, so
node interfaces can be exercised without any real neuroimaging data.
"""

import numpy as np
import nibabel as nib
import pytest

from swane.config.ConfigManager import ConfigManager


# --------------------------------------------------------------------------- #
# Workflow-construction fixtures (shared by ``workflows/`` and ``matrix/``)
#
# These build real :class:`ConfigManager` sections and empty "DICOM" input
# directories so each ``*_workflow`` builder can be assembled and its node graph
# inspected — without DICOM data, FSL/FreeSurfer execution, or network access.
# --------------------------------------------------------------------------- #
@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect the home directory so config writes never touch the real one.

    A subject :class:`ConfigManager` transiently instantiates a *global* config
    in the user's home directory; this keeps that side effect in a throwaway
    folder.
    """
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


@pytest.fixture
def make_nifti(tmp_path):
    """Return a factory that writes a small NIfTI and returns its path.

    Parameters accepted by the factory:

    * ``name`` - file name inside the test's ``tmp_path``.
    * ``shape`` - image shape (defaults to a tiny 4x4x4 volume).
    * ``zooms`` - voxel sizes in mm; when given they are stored in the header.
    * ``data`` - explicit voxel data (overrides ``shape``).
    * ``affine`` - image affine (defaults to the identity).
    """

    def _make(name="img.nii.gz", shape=(4, 4, 4), zooms=None, data=None, affine=None):
        if data is None:
            data = np.zeros(shape, dtype=np.float32)
        else:
            data = np.asarray(data, dtype=np.float32)
        if affine is None:
            affine = np.eye(4)
        img = nib.Nifti1Image(data, affine)
        if zooms is not None:
            img.header.set_zooms(zooms)
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(img, str(path))
        return str(path)

    return _make


@pytest.fixture
def make_file(tmp_path):
    """Return a factory that writes a plain text/binary file and returns its path."""

    def _make(name, content=""):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return str(path)

    return _make


class FakeRuntime:
    """Minimal stand-in for a nipype ``runtime`` object.

    Command interfaces read the captured command output from ``runtime.stdout``;
    tests build one of these to drive ``aggregate_outputs`` without running the
    external executable.
    """

    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fake_runtime():
    """Return the :class:`FakeRuntime` factory class."""
    return FakeRuntime
