import os
import types
from swane import strings
# Use the test-friendly qt_compat layer instead of importing PySide6 directly.
from swane.utils.qt_compat import QThreadPool
from swane.config.ConfigManager import ConfigManager
import shutil
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
import pytest
from swane.tests import TEST_DIR
from nipype.interfaces import fsl, dcm2nii, freesurfer
from swane.workers.SlicerCheckWorker import SlicerCheckWorker
import distutils.dir_util

# These tests probe the real external tools. Skipped unless --run-heavy and the
# tools are installed (see conftest marker auto-skip).
pytestmark = [
    pytest.mark.heavy,
    pytest.mark.requires_fsl,
    pytest.mark.requires_freesurfer,
    pytest.mark.requires_dcm2niix,
    pytest.mark.requires_slicer,
]

# INSTALL REQUIRED LIB: pip3 install pytest pytest-qt pytest-xdist
# START TEST: pytest swane/ --color=yes --verbose -n 3


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "dep")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)


# @pytest.mark.skip
class TestDependencyManager:

    def test_dep(self, monkeypatch, tmp_path):
        # check dcm2niix presence and absence via monkeypatched version detection
        monkeypatch.setattr(dcm2nii.Info, 'version', staticmethod(lambda: '1.0'))
        assert (
            DependencyManager.check_dcm2niix().state == DependenceStatus.DETECTED
        ), 'dcm2niix present error'
        monkeypatch.setattr(dcm2nii.Info, 'version', staticmethod(lambda: None))
        assert (
            DependencyManager.check_dcm2niix().state == DependenceStatus.MISSING
        ), 'dcm2niix absent error'

        # check FSL presence and absence via monkeypatched version and environment
        monkeypatch.setattr(fsl.base.Info, 'version', staticmethod(lambda: '6.1.0'))
        monkeypatch.setenv('FSLDIR', str(tmp_path / 'fsl'))
        (tmp_path / 'fsl').mkdir()
        monkeypatch.setattr(DependencyManager, 'MIN_FSL_VERSION', '1000')
        assert (
            DependencyManager.check_fsl().state == DependenceStatus.WARNING
        ), 'fsl outdated error'
        monkeypatch.setattr(DependencyManager, 'MIN_FSL_VERSION', '6.0.6')
        assert (
            DependencyManager.check_fsl().state == DependenceStatus.DETECTED
        ), 'fsl present error'
        monkeypatch.setattr(fsl.base.Info, 'version', staticmethod(lambda: None))
        assert (
            DependencyManager.check_fsl().state == DependenceStatus.MISSING
        ), 'fsl absent error'

        # check freesurfer presence and absence via monkeypatched version and runtime
        monkeypatch.setattr(freesurfer.base.Info, 'version', staticmethod(lambda: '8.1.0'))
        monkeypatch.setattr(freesurfer.base.Info, 'looseversion', staticmethod(lambda: '8.1.0'))
        fake_fs = tmp_path / 'freesurfer'
        fake_fs.mkdir()
        monkeypatch.setenv('FREESURFER_HOME', str(fake_fs))
        license_file = fake_fs / 'license.txt'
        license_file.write_text('license')
        monkeypatch.setattr(DependencyManager, 'FREESURFER_MATLAB_COMMAND', 'echo ok')
        monkeypatch.setattr(DependencyManager, 'MIN_FREESURFER_VERSION', '7.3.2')
        monkeypatch.setattr('swane.utils.DependencyManager.which', lambda cmd: '/usr/bin/tcsh' if cmd == 'tcsh' else None)
        monkeypatch.setattr('swane.utils.DependencyManager.ResourceManager', types.SimpleNamespace(
            total_memory_gb=staticmethod(lambda: 9999),
            synth_reconall_ram_requirements=staticmethod(lambda: 1),
            synth_seg_ram_requirements=staticmethod(lambda: 1),
        ))
        fake_result = types.SimpleNamespace(returncode=0, stdout='', stderr='')
        monkeypatch.setattr('swane.utils.DependencyManager.subprocess.run', lambda *args, **kwargs: fake_result)
        assert (
            DependencyManager.check_freesurfer().state == DependenceStatus.DETECTED
        ), 'freesurfer present error'
        monkeypatch.setenv('FREESURFER_HOME', '')
        assert (
            DependencyManager.check_freesurfer().state == DependenceStatus.MISSING
        ), 'freesurfer absent error'

        # check graphviz presence via monkeypatched which
        monkeypatch.setattr('swane.utils.DependencyManager.which', lambda cmd: '/usr/bin/dot')
        assert (
            DependencyManager.check_graphviz().state == DependenceStatus.DETECTED
        ), 'graphviz presence error'
        monkeypatch.setattr('swane.utils.DependencyManager.which', lambda cmd: None)
        assert (
            DependencyManager.check_graphviz().state == DependenceStatus.WARNING
        ), 'graphviz warning error'

    def test_slicer_dep(self, monkeypatch, qtbot):
        global_config = ConfigManager(global_base_folder=os.path.join(TEST_DIR, "dep"))

        # test need_slicer_check function
        assert global_config.get_slicer_path() == "", "Error initializing slicer path"
        assert (
            DependencyManager.need_slicer_check(global_config) is True
        ), "need slicer check on empty string error"
        global_config.set_slicer_path("nonexistingpath")
        assert (
            DependencyManager.need_slicer_check(global_config) is True
        ), "need slicer check on non existing path error"
        assert (
            DependencyManager.need_slicer_check(None) is False
        ), "need slicer check on invalid config error"

        # test check_slicer function

        # slicer absence
        real_slicer = blocker.args[0]
        assert os.access(real_slicer, os.W_OK) is True, "Slicer non writeable"
        slicer_dir = os.path.dirname(real_slicer)
        slicer_python = os.path.join(slicer_dir, "bin", "PythonSlicer")
        assert os.path.exists(slicer_python) is True, "PythonSlicer not found"
        slicer_python_bk = slicer_python + "_bk"
        shutil.move(slicer_python, slicer_python_bk)
        slicer_check_worker = SlicerCheckWorker("")
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        shutil.move(slicer_python_bk, slicer_python)
        assert blocker.args[3] == DependenceStatus.MISSING, "slicer absence error"

        # double_slicer
        slicer_dir_copy = os.path.join(TEST_DIR, "dep")
        # use cp to force all files are copied before going on
        os.system("cp -r %s %s" % (slicer_dir, slicer_dir_copy))
        found_list, _ = SlicerCheckWorker.find_slicer_python("")
        if slicer_dir_copy in found_list[0]:
            unfound = slicer_dir
        else:
            unfound = os.path.join(slicer_dir_copy, os.path.basename(slicer_dir))

        unfound_slicer = os.path.join(unfound, "Slicer")
        assert os.path.exists(unfound_slicer) is True, "Error on duplicating Slicer"
        slicer_check_worker = SlicerCheckWorker(unfound_slicer)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert unfound in blocker.args[0], "Error in specifing custom Slicer executable"

        # uninstall and reinstall module from copied slicer
        found_list, rel_path = SlicerCheckWorker.find_slicer_python(slicer_dir_copy)
        cmd = os.path.abspath(os.path.join(os.path.dirname(found_list[0]), rel_path))
        os.system(
            cmd
            + " --no-main-window --python-code 'manager = slicer.app.extensionsManagerModel();manager.scheduleExtensionForUninstall(\"SlicerFreeSurfer\");import sys;sys.exit(0)'"
        )
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.DETECTED
        ), "Cannot reinstall SlicerFreeSurfer error"
        # try to install non-existing module
        monkeypatch.setattr(DependencyManager, "SLICER_MODULES", ["blabla"])
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Missing module not raising error"

        # test for outdated slicer version
        monkeypatch.setattr(DependencyManager, "MIN_SLICER_VERSION", "1000")
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Slicer outdated version error"
        monkeypatch.undo()
