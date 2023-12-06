import os
from PySide6.QtCore import QThreadPool
from swane.config.ConfigManager import ConfigManager
import shutil
from swane.utils.DependencyManager import DependencyManager, DependenceStatus
import pytest
from swane.tests import TEST_DIR
from nipype.interfaces import fsl, dcm2nii, freesurfer
from swane.workers.SlicerCheckWorker import SlicerCheckWorker


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "dep")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.chdir(test_dir)


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
        print(fsl.Info.version())
        fsl_dir_bk = os.environ["FSLDIR"]
        fsl_version_file_bk = fsl.Info.version_file
        os.environ["FSLDIR"] = ""
        fsl.Info.version_file = None
        fsl.Info._version = None
        assert DependencyManager.check_fsl().state == DependenceStatus.MISSING, "fsl absent error"
        print(fsl.Info.version())
        os.environ["FSLDIR"] = fsl_dir_bk
        fsl.Info.version_file = fsl_version_file_bk
        fsl.Info._version = None
        print(fsl.Info.version())
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

        #check graphviz presence
        assert DependencyManager.check_graphviz().state == DependenceStatus.DETECTED, "graphviz presence error"

    def test_slicer_dep(self, monkeypatch, qtbot):
        global_config = ConfigManager(global_base_folder=TEST_DIR)

        # test need_slicer_check function
        assert global_config.get_slicer_path() == "", "Error initializing slicer path"
        assert DependencyManager.need_slicer_check(global_config) == True, "need slicer check on empty string error"
        global_config.set_slicer_path("nonexistingpath")
        assert DependencyManager.need_slicer_check(global_config) == True, "need slicer check on non existing path error"
        assert DependencyManager.need_slicer_check(None) == False, "need slicer check on invalid config error"

        # test check_slicer function
        slicer_check_worker = SlicerCheckWorker("")
        with qtbot.waitSignal(slicer_check_worker.signal.slicer, timeout=20000) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.DETECTED, "slicer presence error"
