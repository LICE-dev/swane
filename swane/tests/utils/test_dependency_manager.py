"""Light unit tests for :mod:`swane.utils.DependencyManager`.

Everything here is mocked: no real FSL/FreeSurfer/dcm2niix/Slicer is needed.
The real Slicer detection/install dance lives in
``workers/test_slicer_check_worker.py`` (marked ``heavy``), since that one
cannot be faked without a real bundled Slicer.
"""

import os
import subprocess
import sys
import types

import pytest

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

    def _valid_slicer_config(self, tmp_path):
        """A config whose cached Slicer data would skip the full check."""
        import json

        exe = tmp_path / "Slicer"
        exe.write_text("x")
        exe.chmod(0o755)
        paths = {}
        for name in DependencyManager.SLICER_MODULES:
            (tmp_path / name).mkdir()
            paths[name] = str(tmp_path / name)
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.set_slicer_path(str(exe))
        config.set_slicer_version("5.6.2")
        config.set_slicer_validator(False)
        config.set_slicer_extensions_state(
            json.dumps({"revision": "1", "paths": paths})
        )
        return config

    def test_need_slicer_check_trusts_intact_cache(self, tmp_path, monkeypatch):
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        patched = []
        monkeypatch.setattr(
            SlicerCheckWorker,
            "add_slicer_startup_patch",
            staticmethod(lambda: patched.append(True)),
        )
        config = self._valid_slicer_config(tmp_path)
        assert DependencyManager.need_slicer_check(config) is False
        assert patched == [True]

    def test_need_slicer_check_detects_removed_extension(self, tmp_path, monkeypatch):
        import shutil
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        monkeypatch.setattr(
            SlicerCheckWorker, "add_slicer_startup_patch", staticmethod(lambda: None)
        )
        config = self._valid_slicer_config(tmp_path)
        shutil.rmtree(tmp_path / DependencyManager.SLICER_MODULES[0])
        assert DependencyManager.need_slicer_check(config) is True

    def test_need_slicer_check_without_recorded_extensions(self, tmp_path, monkeypatch):
        """Preferences written by an older SWANe have no extension state."""
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        monkeypatch.setattr(
            SlicerCheckWorker, "add_slicer_startup_patch", staticmethod(lambda: None)
        )
        config = self._valid_slicer_config(tmp_path)
        config.set_slicer_extensions_state("")
        assert DependencyManager.need_slicer_check(config) is True

    def test_need_slicer_check_executable_replaced_by_folder(
        self, tmp_path, monkeypatch
    ):
        from swane.workers.SlicerCheckWorker import SlicerCheckWorker

        monkeypatch.setattr(
            SlicerCheckWorker, "add_slicer_startup_patch", staticmethod(lambda: None)
        )
        config = self._valid_slicer_config(tmp_path)
        config.set_slicer_path(str(tmp_path))
        assert DependencyManager.need_slicer_check(config) is True

    def test_extensions_state_survives_percent_in_path(self, tmp_path):
        config = ConfigManager(global_base_folder=str(tmp_path))
        config.set_slicer_extensions_state('{"paths": {"A": "/100%/x"}}')
        assert config.get_slicer_extensions_state() == '{"paths": {"A": "/100%/x"}}'


class TestToolChecksMocked:

    def test_check_graphviz(self, monkeypatch):
        monkeypatch.setattr(dm, "which", lambda cmd: None)
        assert DependencyManager.check_graphviz().state == DependenceStatus.WARNING
        monkeypatch.setattr(dm, "which", lambda cmd: "/usr/bin/dot")
        assert DependencyManager.check_graphviz().state == DependenceStatus.DETECTED

    def test_check_dcm2niix(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: None if name == "dcm2niix" else object(),
        )
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.MISSING

        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: object() if name == "dcm2niix" else None,
        )
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.metadata.version",
            lambda name: "1.0.20220720",
        )
        assert DependencyManager.check_dcm2niix().state == DependenceStatus.DETECTED

    def test_check_fsl(self, monkeypatch):
        monkeypatch.setattr(dm, "is_linux", lambda: False)

        monkeypatch.setattr(dm, "_read_fsl_version", lambda: None)
        assert DependencyManager.check_fsl().state == DependenceStatus.MISSING

        monkeypatch.setattr(dm, "_read_fsl_version", lambda: "6.0.7.8")
        assert DependencyManager.check_fsl().state == DependenceStatus.DETECTED

        # eddy gained --nthr (which SWANe passes) in FSL 6.0.7.8
        monkeypatch.setattr(dm, "_read_fsl_version", lambda: "6.0.7.7")
        assert DependencyManager.check_fsl().state == DependenceStatus.WARNING

        monkeypatch.setattr(dm, "_read_fsl_version", lambda: "5.0.0")
        assert DependencyManager.check_fsl().state == DependenceStatus.WARNING

    def test_check_freesurfer_missing(self, monkeypatch):
        monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: (None, None))
        assert DependencyManager.check_freesurfer().state == DependenceStatus.MISSING

    def test_check_freesurfer_without_home(self, monkeypatch):
        monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("7.4.0", "7.4.0"))
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

        monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("8.2.0", "8.2.0"))
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
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: object() if name == "ants" else None,
        )
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.metadata.version",
            lambda name: "0.6.3",
        )
        assert DependencyManager.check_antspyx().state == DependenceStatus.DETECTED

        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.metadata.version",
            lambda name: "0.6.0",
        )
        assert DependencyManager.check_antspyx().state == DependenceStatus.WARNING

        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: None,
        )
        assert DependencyManager.check_antspyx().state == DependenceStatus.MISSING

    def test_is_freesurfer_synth(self, monkeypatch):
        monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("8.2.0", "8.2.0"))
        assert DependencyManager.is_freesurfer_synth() is True
        monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("7.0.0", "7.0.0"))
        assert DependencyManager.is_freesurfer_synth() is False

    def test_is_antspynet_true_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: object() if name == "antspynet" else None,
        )
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.metadata.version",
            lambda name: DependencyManager.MIN_ANTSPYNET_VERSION,
        )
        assert DependencyManager.is_antspynet() is True
        assert DependencyManager.check_antspynet().state == DependenceStatus.DETECTED

    def test_is_antspynet_false_when_absent(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: None,
        )
        assert DependencyManager.is_antspynet() is False
        assert DependencyManager.check_antspynet().state == DependenceStatus.MISSING

    def test_check_antspynet_label_includes_license_link(self, monkeypatch):
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.util.find_spec",
            lambda name: object() if name == "antspynet" else None,
        )
        monkeypatch.setattr(
            "swane.utils.DependencyManager.importlib.metadata.version",
            lambda name: DependencyManager.MIN_ANTSPYNET_VERSION,
        )
        dep = DependencyManager.check_antspynet()
        assert dep.state == DependenceStatus.DETECTED
        assert "href=" in dep.label


def test_is_dipy_uses_instance_attribute():
    manager = DependencyManager()
    manager.dipy = Dependence(DependenceStatus.MISSING, "mock missing")
    assert manager.is_dipy() is False

    manager.dipy = Dependence(DependenceStatus.DETECTED, "mock detected")
    assert manager.is_dipy() is True


def test_is_antspynet_uses_instance_attribute():
    manager = DependencyManager()
    manager.antspynet = Dependence(DependenceStatus.MISSING, "mock missing")
    assert manager.is_antspynet() is False

    manager.antspynet = Dependence(DependenceStatus.DETECTED, "mock detected")
    assert manager.is_antspynet() is True


def test_is_freesurfer_synth_uses_instance_attribute():
    manager = DependencyManager()
    manager.freesurfer = Dependence(
        DependenceStatus.DETECTED, "mock detected", detected_version="7.0.0"
    )
    assert manager.is_freesurfer_synth() is False

    manager.freesurfer = Dependence(
        DependenceStatus.DETECTED, "mock detected", detected_version="8.2.0"
    )
    assert manager.is_freesurfer_synth() is True


def test_has_en_us_locale_memoized(monkeypatch):
    import swane.utils.DependencyManager as dm

    calls = 0

    def mock_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout="en_US.utf8\n", stderr="")

    monkeypatch.setattr(dm.subprocess, "run", mock_run)
    monkeypatch.setattr(dm, "is_linux", lambda: True)
    dm._has_en_us_locale.cache_clear()

    assert dm._has_en_us_locale() is True
    assert dm._has_en_us_locale() is True
    assert calls == 1


def test_has_en_us_locale_non_linux(monkeypatch):
    import swane.utils.DependencyManager as dm

    calls = 0

    def mock_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout="en_US.utf8\n", stderr="")

    monkeypatch.setattr(dm.subprocess, "run", mock_run)
    monkeypatch.setattr(dm, "is_linux", lambda: False)
    dm._has_en_us_locale.cache_clear()

    assert dm._has_en_us_locale() is True
    assert calls == 0


def test_has_en_us_locale_missing(monkeypatch):
    import swane.utils.DependencyManager as dm

    monkeypatch.setattr(
        dm.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="C\nPOSIX\n", stderr=""
        ),
    )
    monkeypatch.setattr(dm, "is_linux", lambda: True)
    dm._has_en_us_locale.cache_clear()

    assert dm._has_en_us_locale() is False


def test_has_en_us_locale_exception(monkeypatch):
    import swane.utils.DependencyManager as dm

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="locale -a", timeout=1.0)

    monkeypatch.setattr(dm.subprocess, "run", mock_run)
    monkeypatch.setattr(dm, "is_linux", lambda: True)
    dm._has_en_us_locale.cache_clear()

    assert dm._has_en_us_locale() is False


def test_check_freesurfer_matlab_absent_does_not_spawn(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("FS_LICENSE", raising=False)

    monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("8.2.0", "8.2.0"))
    fake_fs = tmp_path / "freesurfer"
    fake_fs.mkdir()
    monkeypatch.setenv("FREESURFER_HOME", str(fake_fs))
    (fake_fs / "license.txt").write_text("license")

    # which("tcsh") -> found, which("checkMCR.sh") -> not found
    def mock_which(cmd):
        if cmd == dm.DependencyManager.FSL_TCSH_COMMAND:
            return "/usr/bin/tcsh"
        return None

    monkeypatch.setattr(dm, "which", mock_which)
    monkeypatch.setattr(dm.shutil, "which", lambda cmd: None)

    calls = 0

    def mock_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(dm.subprocess, "run", mock_run)
    monkeypatch.setattr(
        dm.ResourceManager, "total_memory_gb", staticmethod(lambda: 9999)
    )
    monkeypatch.setattr(
        dm.ResourceManager,
        "synth_reconall_ram_requirements",
        staticmethod(lambda: 1),
    )

    dep = DependencyManager.check_freesurfer()
    assert dep.state == DependenceStatus.WARNING
    assert dep.state2 == DependenceStatus.MISSING
    assert calls == 0


def test_check_freesurfer_matlab_candidate_in_freesurfer_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("FS_LICENSE", raising=False)

    monkeypatch.setattr(dm, "_read_freesurfer_version", lambda: ("8.2.0", "8.2.0"))
    fake_fs = tmp_path / "freesurfer"
    bin_dir = fake_fs / "bin"
    bin_dir.mkdir(parents=True)
    mcr_script = bin_dir / "checkMCR.sh"
    mcr_script.write_text("#!/bin/sh\nexit 0\n")
    mcr_script.chmod(0o755)

    monkeypatch.setenv("FREESURFER_HOME", str(fake_fs))
    (fake_fs / "license.txt").write_text("license")

    def mock_which(cmd):
        if cmd == dm.DependencyManager.FSL_TCSH_COMMAND:
            return "/usr/bin/tcsh"
        return None

    monkeypatch.setattr(dm, "which", mock_which)
    monkeypatch.setattr(dm.shutil, "which", lambda cmd: None)

    captured_args = []

    def mock_run(args, **kwargs):
        captured_args.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="MCR OK", stderr="")

    monkeypatch.setattr(dm.subprocess, "run", mock_run)
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
    assert len(captured_args) == 1
    args, kwargs = captured_args[0]
    assert args == [str(mcr_script)]
    assert kwargs.get("shell") is False
    assert kwargs.get("timeout") == 3.0


# swane/tests/conftest.py wraps the version readers with a fake installed
# version: these tests exercise the real readers.
_real_read_fsl_version = getattr(
    dm._read_fsl_version, "__wrapped__", dm._read_fsl_version
)
_real_read_freesurfer_version = getattr(
    dm._read_freesurfer_version, "__wrapped__", dm._read_freesurfer_version
)


def test_read_fsl_version(monkeypatch, tmp_path):
    monkeypatch.delenv("FSLDIR", raising=False)
    assert _real_read_fsl_version() is None

    fsldir = tmp_path / "fsl"
    monkeypatch.setenv("FSLDIR", str(fsldir))
    assert _real_read_fsl_version() is None

    etc = fsldir / "etc"
    etc.mkdir(parents=True)
    (etc / "fslversion").write_text("6.0.7.17\n")
    assert _real_read_fsl_version() == "6.0.7.17"

    (etc / "fslversion").write_text("")
    assert _real_read_fsl_version() is None


def test_read_freesurfer_version(monkeypatch, tmp_path):
    monkeypatch.delenv("FREESURFER_HOME", raising=False)
    assert _real_read_freesurfer_version() == (None, None)

    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    monkeypatch.setenv("FREESURFER_HOME", str(fs_home))
    assert _real_read_freesurfer_version() == (None, None)

    stamp = "freesurfer-linux-ubuntu22_x86_64-8.2.0-20260314-d932c45"
    (fs_home / "build-stamp.txt").write_text(stamp + "\n")
    assert _real_read_freesurfer_version() == (stamp, "8.2.0")

    (fs_home / "build-stamp.txt").write_text("")
    assert _real_read_freesurfer_version() == (None, None)


@pytest.mark.parametrize(
    "stamp",
    [
        "freesurfer-linux-ubuntu22_x86_64-8.2.0-20260314-d932c45",
        "freesurfer-linux-centos7_x86_64-7.1.0-20200511-813297b",
        "freesurfer-linux-centos7_x86_64-7.4.1-20230614-7eb8460",
        "freesurfer-Linux-centos6_x86_64-stable-pub-v6.0.0-2beb96c",
        "freesurfer-Linux-centos6_x86_64-dev-20160310-a4b9de2",
        "freesurfer-Linux-centos4_x86_64-stable-pub-v5.3.0",
        "freesurfer-Darwin-lion-stable-pub-v5.1.0",
    ],
)
def test_freesurfer_looseversion_matches_nipype(monkeypatch, tmp_path, stamp):
    """The Nipype-free parser must agree with nipype's Info.looseversion()."""
    from nipype.interfaces.freesurfer.base import Info

    monkeypatch.setattr(Info, "version", classmethod(lambda cls: stamp))
    assert dm._freesurfer_looseversion(stamp) == str(Info.looseversion())
