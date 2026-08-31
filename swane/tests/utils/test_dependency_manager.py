"""Light unit tests for :mod:`swane.utils.DependencyManager`.

Everything here is mocked: no real FSL/FreeSurfer/dcm2niix/Slicer is needed.
The real Slicer detection/install dance lives in
``workers/test_slicer_check_worker.py`` (marked ``heavy``), since that one
cannot be faked without a real bundled Slicer.
"""

import os
import types

import swane.utils.DependencyManager as dm
from swane.utils.DependencyManager import (
    DependencyManager,
    Dependence,
    DependenceStatus,
)
from swane.config.ConfigManager import ConfigManager


def _manager_with(**states):
    """Build a DependencyManager and override its probed dependencies."""
    manager = DependencyManager()
    for attr, state in states.items():
        setattr(manager, attr, Dependence(state, "label"))
    return manager


class TestDependenceObject:

    def test_fields(self):
        dep = Dependence(DependenceStatus.DETECTED, "ok", DependenceStatus.WARNING)
        assert dep.state == DependenceStatus.DETECTED
        assert dep.label == "ok"
        assert dep.state2 == DependenceStatus.WARNING


class TestStatusFlags:

    def test_is_flags_reflect_states(self):
        manager = _manager_with(
            fsl=DependenceStatus.WARNING,  # detected even if outdated
            dcm2niix=DependenceStatus.DETECTED,
            graphviz=DependenceStatus.MISSING,
        )
        assert manager.is_fsl() is True
        assert manager.is_dcm2niix() is True
        assert manager.is_graphviz() is False

        manager.fsl = Dependence(DependenceStatus.MISSING, "x")
        assert manager.is_fsl() is False

    def test_freesurfer_matlab_flag(self):
        manager = DependencyManager()
        manager.freesurfer = Dependence(
            DependenceStatus.DETECTED, "fs", DependenceStatus.DETECTED
        )
        assert manager.is_freesurfer() is True
        assert manager.is_freesurfer_matlab() is True
        manager.freesurfer = Dependence(
            DependenceStatus.DETECTED, "fs", DependenceStatus.MISSING
        )
        assert manager.is_freesurfer_matlab() is False


class TestSlicerHelpers:

    def test_check_slicer_version(self):
        assert DependencyManager.check_slicer_version("5.2.1") is True
        assert DependencyManager.check_slicer_version("6.0.0") is True
        assert DependencyManager.check_slicer_version("5.0.0") is False
        assert DependencyManager.check_slicer_version("") is False
        assert DependencyManager.check_slicer_version(None) is False
        assert DependencyManager.check_slicer_version("not-a-version") is False

    def test_is_slicer(self, tmp_path):
        assert DependencyManager.is_slicer(None) is False

        config = ConfigManager(global_base_folder=str(tmp_path))
        assert DependencyManager.is_slicer(config) is False  # empty path

        slicer = tmp_path / "Slicer"
        slicer.write_text("x")
        config.set_slicer_path(str(slicer))
        assert DependencyManager.is_slicer(config) is True

    def test_need_slicer_check(self, tmp_path, monkeypatch):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.set_slicer_path("does-not-exist")
        assert DependencyManager.need_slicer_check(config) is True
        assert DependencyManager.need_slicer_check(None) is False


class TestToolChecksMocked:

    def test_check_graphviz(self, monkeypatch):
        monkeypatch.setattr(dm, "which", lambda cmd: None)
        assert DependencyManager.check_graphviz().state == DependenceStatus.WARNING
        monkeypatch.setattr(dm, "which", lambda cmd: "/usr/bin/dot")
        assert DependencyManager.check_graphviz().state == DependenceStatus.DETECTED

    def test_check_dcm2niix(self, monkeypatch):
        monkeypatch.setattr(dm.dcm2nii.Info, "version", lambda: None)
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.MISSING
        monkeypatch.setattr(dm.dcm2nii.Info, "version", lambda: "1.0.20220720")
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.DETECTED

    def test_check_fsl(self, monkeypatch):
        monkeypatch.setattr(dm, "is_linux", lambda: False)

        monkeypatch.setattr(dm.fsl.base.Info, "version", lambda: None)
        assert DependencyManager.check_fsl().state == DependenceStatus.MISSING

        monkeypatch.setattr(dm.fsl.base.Info, "version", lambda: "6.0.7")
        assert DependencyManager.check_fsl().state == DependenceStatus.DETECTED

        monkeypatch.setattr(dm.fsl.base.Info, "version", lambda: "5.0.0")
        assert DependencyManager.check_fsl().state == DependenceStatus.WARNING

    def test_check_freesurfer_missing(self, monkeypatch):
        monkeypatch.setattr(dm.freesurfer.base.Info, "version", lambda: None)
        assert DependencyManager.check_freesurfer().state == DependenceStatus.MISSING

    def test_check_freesurfer_without_home(self, monkeypatch):
        monkeypatch.setattr(dm.freesurfer.base.Info, "version", lambda: "7.4.0")
        monkeypatch.setattr(dm.freesurfer.base.Info, "looseversion", lambda: "7.4.0")
        monkeypatch.delenv("FREESURFER_HOME", raising=False)
        assert DependencyManager.check_freesurfer().state == DependenceStatus.MISSING

    def test_check_freesurfer_detected(self, monkeypatch, tmp_path):
        """The full "everything present" branch: version, license, tcsh and the
        Matlab runtime all found, with enough RAM for the Synth recon-all path.
        """
        # check_freesurfer() falls back to a license.txt in the home directory;
        # isolate it so a real license file in the developer's actual $HOME
        # doesn't leak into this scenario.
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.delenv("FS_LICENSE", raising=False)

        monkeypatch.setattr(dm.freesurfer.base.Info, "version", lambda: "8.2.0")
        monkeypatch.setattr(dm.freesurfer.base.Info, "looseversion", lambda: "8.2.0")
        fake_fs = tmp_path / "freesurfer"
        fake_fs.mkdir()
        monkeypatch.setenv("FREESURFER_HOME", str(fake_fs))
        (fake_fs / "license.txt").write_text("license")
        monkeypatch.setattr(dm, "which", lambda cmd: "/usr/bin/tcsh")
        monkeypatch.setattr(
            dm.subprocess,
            "run",
            lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        monkeypatch.setattr(
            dm.ResourceManager, "total_memory_gb", staticmethod(lambda: 9999)
        )
        monkeypatch.setattr(
            dm.ResourceManager,
            "synth_reconall_ram_requirements",
            staticmethod(lambda: 1),
        )

        dep = DependencyManager.check_freesurfer()
        assert dep.state == DependenceStatus.DETECTED
        assert dep.state2 == DependenceStatus.DETECTED

    def test_check_antspyx(self, monkeypatch):
        import ants

        monkeypatch.setattr(ants, "__version__", "0.6.3")
        assert DependencyManager.check_antspyx().state == DependenceStatus.DETECTED

        monkeypatch.setattr(ants, "__version__", "0.6.2")
        assert DependencyManager.check_antspyx().state == DependenceStatus.WARNING

        monkeypatch.delattr(ants, "__version__", raising=False)
        assert DependencyManager.check_antspyx().state == DependenceStatus.MISSING

    def test_is_freesurfer_synth(self, monkeypatch):
        monkeypatch.setattr(dm.freesurfer.base.Info, "looseversion", lambda: "8.2.0")
        assert DependencyManager.is_freesurfer_synth() is True
        monkeypatch.setattr(dm.freesurfer.base.Info, "looseversion", lambda: "7.0.0")
        assert DependencyManager.is_freesurfer_synth() is False
