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

# NOTE: the Windows ``pwd`` stub and the FSL/FreeSurfer version fallback for
# nipype live in the repository-root ``conftest.py``: pytest imports the
# ``swane`` package (and so ``swane.patches`` -> nipype.interfaces.fsl) before
# this file runs, which is too late for either of them.

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
if not os.environ.get("SUBJECTS_DIR") or not os.path.exists(os.environ["SUBJECTS_DIR"]):
    import tempfile

    os.environ["SUBJECTS_DIR"] = tempfile.mkdtemp(prefix="swane_tests_subjects_")

from swane.config.ConfigManager import ConfigManager
from swane.utils.DependencyManager import DependencyManager
from swane.tests.helpers.fsl_policy_override import (
    ENV_VAR as _FSL_POLICY_ENV_VAR,
    apply_fsl_policy_override,
)

# TEMPORARY (see swane/tests/helpers/fsl_policy_override.py): the Windows CI
# runner sets SWANE_TEST_FSL_MANDATORY=0 to test as if FSL were only
# recommended. Applied before any test module is imported.
_FSL_POLICY_OVERRIDDEN = apply_fsl_policy_override()


def pytest_report_header(config):
    if _FSL_POLICY_OVERRIDDEN:
        return "%s=0: FSL_MANDATORY overridden to False" % _FSL_POLICY_ENV_VAR


# DependencyManager reads the FSL/FreeSurfer versions from their install files
# without importing nipype (to keep it off GUI startup), so the nipype version
# fallback of the repository-root conftest does not reach it. When a tool is not
# installed, fall back to nipype's (faked) version, so FSL/FreeSurfer detection
# (e.g. the fMRI engine resolution) matches nipype's view of the tools. The real
# readers stay reachable as ``__wrapped__`` for their own tests.
import functools

import swane.utils.DependencyManager as _dependency_manager

_real_read_fsl_version = _dependency_manager._read_fsl_version
_real_read_freesurfer_version = _dependency_manager._read_freesurfer_version


@functools.wraps(_real_read_fsl_version)
def _read_fsl_version_with_fallback():
    version = _real_read_fsl_version()
    if version is None:
        from nipype.interfaces.fsl.base import Info

        return Info.version()
    return version


@functools.wraps(_real_read_freesurfer_version)
def _read_freesurfer_version_with_fallback():
    raw_version, version = _real_read_freesurfer_version()
    if raw_version is None:
        from nipype.interfaces.freesurfer.base import Info

        return Info.version(), str(Info.looseversion())
    return raw_version, version


_dependency_manager._read_fsl_version = _read_fsl_version_with_fallback
_dependency_manager._read_freesurfer_version = _read_freesurfer_version_with_fallback
from swane.tests.helpers.dicom_scenarios import build_dicom_tree


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #
def _configured_slicer_path():
    """The ``slicer_path`` swane itself would use, read read-only from the
    real ``~/.SWANe`` config file (never written here — this must not mutate
    the user's actual application config as a side effect of collection).
    3D Slicer is normally an extracted tarball/AppImage, not something on
    PATH, so swane's own configured path is the only reliable signal.
    """
    import configparser

    from swane.resources import strings

    config_file = os.path.join(os.path.expanduser("~"), "." + strings.APPNAME)
    if not os.path.exists(config_file):
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(config_file)
        return parser["main"]["slicer_path"]
    except Exception:
        return None


_TOOL_MARKERS = {
    "requires_dcm2niix": lambda: shutil.which("dcm2niix") is not None,
    "requires_fsl": lambda: shutil.which("bet") is not None
    or bool(os.environ.get("FSLDIR")),
    "requires_freesurfer": lambda: shutil.which("recon-all") is not None
    or bool(os.environ.get("FREESURFER_HOME")),
    "requires_slicer": lambda: shutil.which("Slicer") is not None
    or any(
        path and os.path.exists(path)
        for path in (os.environ.get("SWANE_SLICER_PATH"), _configured_slicer_path())
    ),
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


@pytest.fixture
def slicer_executable():
    """The 3D Slicer executable a ``requires_slicer`` test should launch, found
    the same way that marker looks for one."""
    for path in (
        os.environ.get("SWANE_SLICER_PATH"),
        _configured_slicer_path(),
        shutil.which("Slicer"),
    ):
        if path and os.path.exists(path):
            return path
    pytest.skip("no 3D Slicer executable found")


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


@pytest.fixture(autouse=True)
def _restore_c_numeric_locale():
    """Ensure LC_NUMERIC is 'C' so C/C++ scientific libraries (ITK/ANTs) work
    reliably even after Qt's QApplication initializes and alters the C locale.
    """
    import locale

    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass
    yield
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass
