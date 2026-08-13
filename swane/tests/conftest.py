"""Shared pytest fixtures and marker handling for the SWANe test suite.

Highlights
----------
* Qt runs head-less (``QT_QPA_PLATFORM=offscreen``) so UI tests need no display.
* ``phantom_dicom_tree`` builds every synthetic DICOM scenario once per session.
* ``global_config`` / ``dependency_manager`` / ``workspace`` remove the
  copy-pasted setup that used to live in every ``test_*`` file.
* Tests marked ``requires_*`` / ``heavy`` are skipped automatically when the
  external tool (FSL, FreeSurfer, dcm2niix, 3D Slicer) or opt-in flag is absent,
  so the "light" suite runs green on a plain Windows/CI box.
"""

import os
import shutil

import pytest

# Qt must be head-less *before* any QApplication is created by pytest-qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from swane.config.ConfigManager import ConfigManager
from swane.utils.DependencyManager import DependencyManager
from swane.tests.helpers.dicom_scenarios import build_dicom_tree


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #
_TOOL_MARKERS = {
    "requires_dcm2niix": lambda: shutil.which("dcm2niix") is not None,
    "requires_fsl": lambda: shutil.which("bet") is not None
    or bool(os.environ.get("FSLDIR")),
    "requires_freesurfer": lambda: shutil.which("recon-all") is not None
    or bool(os.environ.get("FREESURFER_HOME")),
    "requires_slicer": lambda: shutil.which("Slicer") is not None
    or bool(os.environ.get("SWANE_SLICER_PATH")),
}

_MARKER_HELP = {
    "requires_dcm2niix": "needs the dcm2niix executable",
    "requires_fsl": "needs an FSL installation",
    "requires_freesurfer": "needs a FreeSurfer installation",
    "requires_slicer": "needs a 3D Slicer installation",
    "requires_display": "needs a real graphical display",
    "heavy": "slow end-to-end test (run with --run-heavy)",
}


def pytest_addoption(parser):
    parser.addoption(
        "--run-heavy",
        action="store_true",
        default=False,
        help="Run tests marked as 'heavy' (full workflow / real tools).",
    )


def pytest_configure(config):
    for name, help_text in _MARKER_HELP.items():
        config.addinivalue_line("markers", f"{name}: {help_text}")


def pytest_collection_modifyitems(config, items):
    run_heavy = config.getoption("--run-heavy")
    for item in items:
        for name, available in _TOOL_MARKERS.items():
            if name in item.keywords and not available():
                item.add_marker(
                    pytest.mark.skip(reason=f"skipped: {_MARKER_HELP[name]}")
                )
        if "requires_display" in item.keywords and not _has_display():
            item.add_marker(
                pytest.mark.skip(reason=f"skipped: {_MARKER_HELP['requires_display']}")
            )
        if "heavy" in item.keywords and not run_heavy:
            item.add_marker(
                pytest.mark.skip(reason="skipped: heavy test (use --run-heavy)")
            )


def _has_display():
    if os.name == "nt" or os.sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


# --------------------------------------------------------------------------- #
# Filesystem / config fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def workspace(tmp_path):
    """A disposable working directory; cwd is restored on teardown."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old_cwd)


@pytest.fixture
def main_working_directory(workspace):
    """A ready 'subjects' main working directory inside the workspace."""
    subjects = workspace / "subjects"
    subjects.mkdir(exist_ok=True)
    return subjects


@pytest.fixture
def global_config(workspace, main_working_directory):
    """A global ConfigManager pointing at a disposable main working dir."""
    config = ConfigManager(global_base_folder=str(workspace))
    config.set_main_working_directory(str(main_working_directory))
    return config


@pytest.fixture
def dependency_manager():
    return DependencyManager()


# --------------------------------------------------------------------------- #
# DICOM fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def phantom_dicom_tree(tmp_path_factory):
    """Build every synthetic DICOM scenario once and share it read-only."""
    root = tmp_path_factory.mktemp("phantom_dicom")
    return build_dicom_tree(str(root))
