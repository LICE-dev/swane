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

# FSL's own default output type, used only as a fallback below and by every
# FSLCommand's __init__ (nipype.interfaces.fsl.base.FSLCommand) each time a
# node is instantiated: without a real FSL install nipype leaves
# FSLOUTPUTTYPE unset and silently falls back to the legacy "NIFTI" (not
# "NIFTI_GZ", FSL's actual default since 5.x) — see nipype's
# fsl.base.Info.output_type(). Pin it explicitly so construction-only tests
# match what a real FSL install produces, but never override a value the
# environment (e.g. a real FSL's fsl.sh) already set.
os.environ.setdefault("FSLOUTPUTTYPE", "NIFTI_GZ")

# Mirror image of the above, for FreeSurfer. As soon as FreeSurfer is detected,
# nipype's FSCommand.__init__ reads os.environ["SUBJECTS_DIR"] with no default
# (nipype.interfaces.freesurfer.base.Info.subjectsdir) and raises a bare
# KeyError when it is unset — normally FreeSurferEnv.sh provides it. That makes
# the construction tests pass only on machines *without* FreeSurfer, which is
# backwards: a fully equipped box is the reference, not the exception. Point it
# at a real empty directory (the trait is Directory(exists=True), so a
# non-existent path would fail validation too) and never override a value the
# environment already set.
if not os.environ.get("SUBJECTS_DIR"):
    import tempfile

    os.environ["SUBJECTS_DIR"] = tempfile.mkdtemp(prefix="swane_tests_subjects_")

# Some nipype FSL interfaces pick their *input spec class* once, at import
# time, based on nipype.interfaces.fsl.base.Info.version() (e.g. FILMGLS:
# FSL <=5.0.6 lacks the tcon_file/fcon_file inputs swane wires — see
# fMRI_task_workflow). On a box without a real FSL install (e.g. the
# Windows dev machine these tests must also run on) that version is None
# and nipype silently falls back to the old/reduced interface, breaking
# workflow construction for reasons that have nothing to do with swane's
# code. Patch nipype's common PackageInfo.version() so *only* FSL interface
# classes (nipype.interfaces.fsl.*), and only when the real detection comes
# up empty, report a modern FSL version (>= 6.0, matching FSLOUTPUTTYPE
# above) instead of None. Where a real FSL install is present (e.g. the
# heavy/integration tests), real detection wins and this fallback never
# triggers. Must run before anything below imports nipype.interfaces.fsl
# (swane.utils.DependencyManager does, transitively).
#
# The same reasoning applies to FreeSurfer, for a different trait: nipype's
# FSCommand fills ``subjects_dir`` from SUBJECTS_DIR *only when FreeSurfer is
# detected* (freesurfer.base.Info.subjectsdir), so the assembled graph — and
# therefore the golden snapshots — would otherwise depend on whether the tool
# happens to be installed. Faking the version here makes construction identical
# on both, and the snapshot renderer rewrites the directory to a token.
_FALLBACK_VERSIONS = {
    "nipype.interfaces.fsl": "6.0.7.22",
    "nipype.interfaces.freesurfer": "8.0.0",
}
from nipype.interfaces.base import core as _nipype_core

_real_package_version = _nipype_core.PackageInfo.version.__func__


def _package_version_with_fallback(klass):
    version = _real_package_version(klass)
    if version is None:
        for prefix, fallback in _FALLBACK_VERSIONS.items():
            if klass.__module__.startswith(prefix):
                return fallback
    return version


_nipype_core.PackageInfo.version = classmethod(_package_version_with_fallback)

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
# GUI fixture fallback
# --------------------------------------------------------------------------- #
# pytest-qt only registers its ``qtbot`` fixture when a real Qt binding loads.
# On an environment without a working PySide6 (e.g. the Store-packaged Python
# where shiboken6 crashes on import), ``qtbot`` would be "fixture not found" and
# every GUI test would ERROR. Provide a fallback that SKIPS with a clear reason
# instead — defined only when Qt is unavailable, so it never shadows the real
# pytest-qt fixture where Qt works.
from swane.utils.qt_compat import QT_AVAILABLE

if not QT_AVAILABLE:

    @pytest.fixture
    def qtbot(*args, **kwargs):
        pytest.skip(
            "no working Qt binding (PySide6) in this environment — GUI test skipped"
        )


# --------------------------------------------------------------------------- #
# DICOM fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def phantom_dicom_tree(tmp_path_factory):
    """Build every synthetic DICOM scenario once and share it read-only."""
    root = tmp_path_factory.mktemp("phantom_dicom")
    return build_dicom_tree(str(root))
