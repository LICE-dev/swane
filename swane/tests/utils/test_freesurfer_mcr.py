"""The Matlab Runtime environment and load check of the FreeSurfer Matlab tools.

glibc >= 2.41 refuses the R2019b MCR libraries that ask for an executable
stack: the tools always run with the execstack tunable, and the dependency
check loads the runtime in a child process with that same environment. That
the workflow gives segment_ha this environment is in the FreeSurfer matrix
snapshot (reconall_hippo).
"""

import os
import subprocess

import pytest

from swane.utils import freesurfer_mcr as mcr
from swane.utils.platform_and_tools_utils import is_linux


def test_mcr_environ_appends_the_tunable_to_the_user_tunables(monkeypatch):
    monkeypatch.delenv("GLIBC_TUNABLES", raising=False)
    assert mcr.mcr_environ() == {"GLIBC_TUNABLES": "glibc.rtld.execstack=2"}
    monkeypatch.setenv("GLIBC_TUNABLES", "glibc.malloc.check=0")
    assert mcr.mcr_environ() == {
        "GLIBC_TUNABLES": "glibc.malloc.check=0:glibc.rtld.execstack=2"
    }


def test_find_mcr_root_picks_the_newest_runtime_with_the_base_library(tmp_path):
    assert mcr.find_mcr_root(str(tmp_path)) is None
    for name in ("MCRv84", "MCRv97"):
        lib = tmp_path / name / mcr.MCR_BASE_LIBRARY
        lib.parent.mkdir(parents=True)
        lib.touch()
    (tmp_path / "MCRv99").mkdir()  # no base library: not a usable runtime
    assert mcr.find_mcr_root(str(tmp_path)) == str(tmp_path / "MCRv97")


def test_load_check_uses_the_tool_environment(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, env=kwargs["env"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(mcr.subprocess, "run", fake_run)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")
    monkeypatch.delenv("GLIBC_TUNABLES", raising=False)
    assert mcr.mcr_load_error(str(tmp_path)) is None

    assert captured["cmd"][-1] == os.path.join(str(tmp_path), mcr.MCR_BASE_LIBRARY)
    paths = captured["env"]["LD_LIBRARY_PATH"].split(os.pathsep)
    assert paths[0] == os.path.join(str(tmp_path), "runtime", "glnxa64")
    assert paths[-1] == "/existing"
    assert captured["env"]["GLIBC_TUNABLES"] == "glibc.rtld.execstack=2"


def test_load_check_reports_the_loader_message(tmp_path):
    """A real child process: the library is missing, so ctypes fails and the
    last stderr line (the loader message) comes back."""
    error = mcr.mcr_load_error(str(tmp_path))
    assert error is not None and "OSError" in error


@pytest.mark.heavy
@pytest.mark.requires_freesurfer
def test_installed_runtime_loads():
    """The installed MCR loads with the environment of the Matlab tools."""
    root = mcr.find_mcr_root(os.environ.get("FREESURFER_HOME", ""))
    if root is None or not is_linux():
        pytest.skip("needs a FreeSurfer Matlab Runtime on Linux")
    assert mcr.mcr_load_error(root) is None
