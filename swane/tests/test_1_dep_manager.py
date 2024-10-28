import os
from swane import strings
from PySide6.QtCore import QThreadPool
from swane.config.ConfigManager import ConfigManager
import shutil
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
import pytest
from swane.tests import TEST_DIR
from nipype.interfaces import fsl, dcm2nii, freesurfer
from swane.workers.SlicerCheckWorker import SlicerCheckWorker
import distutils.dir_util


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

    def test_dep(self, monkeypatch):
        # check dcm2niix presence and absence
        assert shutil.which("dcm2niix") is not None, "dcm2niix not installed"
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.DETECTED, "dcm2niix present error"
        monkeypatch.setattr(dcm2nii.Info, "version_cmd", "nil")
        dcm2nii.Info._version = None
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.MISSING, "dcm2niix absent error"

        # check FSL presence and absence
        assert shutil.which("bet") is not None, "fsl not installed"
        assert DependencyManager.check_fsl().state == DependenceStatus.DETECTED, "fsl present error"
        fsl_dir_bk = os.environ["FSLDIR"]
        fsl_version_file_bk = fsl.Info.version_file
        os.environ["FSLDIR"] = ""
        fsl.Info.version_file = None
        fsl.Info._version = None
        assert DependencyManager.check_fsl().state == DependenceStatus.MISSING, "fsl absent error"
        os.environ["FSLDIR"] = fsl_dir_bk
        fsl.Info.version_file = fsl_version_file_bk
        fsl.Info._version = None
        # check FSL outdated version
        monkeypatch.setattr(DependencyManager, "MIN_FSL_VERSION", "1000")
        assert DependencyManager.check_fsl().state == DependenceStatus.WARNING, "fsl outdated error"

        # check freesurfer presence and absence
        assert shutil.which("recon-all") is not None, "freesurfer not installed"
        assert DependencyManager.check_freesurfer().state == DependenceStatus.DETECTED, "freesurfer present error"
        freesurfer_home_bk = os.environ["FREESURFER_HOME"]
        freesurfer_version_file_bk = freesurfer.Info.version_file
        freesurfer.Info.version_file = None
        os.environ["FREESURFER_HOME"] = ""
        assert DependencyManager.check_freesurfer().state == DependenceStatus.MISSING, "freesurfer absent error"
        os.environ["FREESURFER_HOME"] = freesurfer_home_bk
        freesurfer.Info.version_file = freesurfer_version_file_bk
        # check freesurfer outdated version
        monkeypatch.setattr(DependencyManager, "MIN_FREESURFER_VERSION", "1000")
        assert DependencyManager.check_fsl().state == DependenceStatus.WARNING, "freesurfer outdated error"
        monkeypatch.undo()
        # check freesurfer matlas absence presence and absence
        monkeypatch.setattr(DependencyManager, "FREESURFER_MATLAB_COMMAND", "nil")
        assert DependencyManager.check_freesurfer().state == DependenceStatus.WARNING, "freesurfer matlab absent error"
        monkeypatch.undo()

        # check graphviz presence
        assert DependencyManager.check_graphviz().state == DependenceStatus.DETECTED, "graphviz presence error"

    def test_slicer_dep(self, monkeypatch, qtbot):
        global_config = ConfigManager(global_base_folder=os.path.join(TEST_DIR, "dep"))

        # test need_slicer_check function
        assert global_config.get_slicer_path() == "", "Error initializing slicer path"
        assert DependencyManager.need_slicer_check(global_config) is True, "need slicer check on empty string error"
        global_config.set_slicer_path("nonexistingpath")
        assert DependencyManager.need_slicer_check(global_config) is True, "need slicer check on non existing path error"
        assert DependencyManager.need_slicer_check(None) is False, "need slicer check on invalid config error"

        # test check_slicer function
        slicer_check_worker = SlicerCheckWorker("")
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.DETECTED, "slicer presence error"

        # slicer absence
        real_slicer = blocker.args[0]
        assert os.access(real_slicer, os.W_OK) is True, "Slicer non writeable"
        slicer_dir = os.path.dirname(real_slicer)
        slicer_python = os.path.join(slicer_dir, "bin", "PythonSlicer")
        assert os.path.exists(slicer_python) is True, "PythonSlicer not found"
        slicer_python_bk = slicer_python+"_bk"
        shutil.move(slicer_python, slicer_python_bk)
        slicer_check_worker = SlicerCheckWorker("")
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
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
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert unfound in blocker.args[0], "Error in specifing custom Slicer executable"

        # uninstall and reinstall module from copied slicer
        found_list, rel_path = SlicerCheckWorker.find_slicer_python(slicer_dir_copy)
        cmd = os.path.abspath(os.path.join(
            os.path.dirname(found_list[0]), rel_path))
        os.system(cmd + " --no-main-window --python-code 'manager = slicer.app.extensionsManagerModel();manager.scheduleExtensionForUninstall(\"SlicerFreeSurfer\");import sys;sys.exit(0)'")
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.MISSING and blocker.args[2] == strings.check_dep_slicer_error2, "Missing SlicerFreeSurfer error"
        install_script = os.path.join(os.path.dirname(__file__), "..", "workers", "slicer_script_freesurfer_module_install.py")
        os.system(
            cmd + " --no-main-window --python-script " + install_script)
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.DETECTED, "Reinstall SlicerFreeSurfer error"

        # test for outdated slicer version
        monkeypatch.setattr(DependencyManager, "MIN_SLICER_VERSION", "1000")
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=2000000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.WARNING, "Slicer outdated version error"
        monkeypatch.undo()
