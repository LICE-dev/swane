"""Windows runtime shims for Nipype's MultiProc RAM probe and CommandLine runner.

Two stock Nipype code paths cannot run on Windows:

* ``nipype.utils.profiler.get_system_total_memory_gb`` reads ``/proc/meminfo``
  (Linux) or ``sysctl`` (macOS) and raises ``Exception("System platform: %s is
  not supported")`` anywhere else; ``MultiProcPlugin.__init__`` evaluates it
  eagerly as the ``memory_gb`` default, so no workflow can start;
* ``nipype.utils.subprocess.run_command`` polls the child's pipes with
  ``select.select`` for ``terminal_output="stream"`` (the CommandLine default);
  on Windows ``select`` accepts only sockets (``WinError 10038``), so every
  CommandLine node fails.

Windows is simulated without touching the global ``os.name``: only
``windows_compat.is_windows`` answers True, plus (narrowly, for the RAM probe)
``sys.platform``, which the stock probe reads at call time.
"""

import os
import sys
import types

import psutil
import pytest
from nipype.interfaces.base import CommandLine, core as nipype_core
from nipype.interfaces.base.support import Bunch
from nipype.pipeline.plugins import legacymultiproc as nipype_legacymultiproc
from nipype.pipeline.plugins import multiproc as nipype_multiproc
from nipype.utils import profiler as nipype_profiler
from nipype.utils import subprocess as nipype_subprocess

import swane.patches.nipype_patches as npx
from swane.patches import windows_compat

# On a real Windows host apply_patches() has already installed the shims at
# import, so the "stock names untouched" invariant only holds elsewhere.
posix_only = pytest.mark.skipif(
    os.name == "nt", reason="the shims are installed at import on Windows"
)

_PSUTIL_GB = psutil.virtual_memory().total / (1024.0**3)

_SCRIPT = (
    "import sys; print('out1'); print('out2'); "
    "sys.stderr.write('err1\\n'); sys.exit(%d)"
)


def _not_a_socket(*args, **kwargs):
    raise OSError(10038, "An operation was attempted on something that is not a socket")


@pytest.fixture
def windows_select(monkeypatch):
    """Make Nipype's ``select.select`` fail exactly like Windows on pipes."""
    monkeypatch.setattr(
        nipype_subprocess, "select", types.SimpleNamespace(select=_not_a_socket)
    )


@pytest.fixture
def simulated_windows(monkeypatch):
    """Install the Windows runtime shims in this process, restored afterwards."""
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    for module in (nipype_profiler, nipype_multiproc, nipype_legacymultiproc):
        monkeypatch.setattr(
            module, "get_system_total_memory_gb", module.get_system_total_memory_gb
        )
    monkeypatch.setattr(nipype_core, "run_command", nipype_core.run_command)
    monkeypatch.setattr(nipype_subprocess, "run_command", nipype_subprocess.run_command)
    assert npx.install_windows_memory_probe() is True
    assert npx.install_windows_run_command() is True


# --- 1. total RAM probe ---------------------------------------------------------


def test_stock_probe_rejects_windows(monkeypatch):
    """Root cause: the stock probe raises on any platform but linux/darwin."""
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(Exception, match="System platform"):
        npx._orig_get_system_total_memory_gb()


def test_windows_probe_uses_psutil(simulated_windows, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    for module in (nipype_profiler, nipype_multiproc, nipype_legacymultiproc):
        assert module.get_system_total_memory_gb() == pytest.approx(_PSUTIL_GB)


def test_multiproc_plugin_starts_on_windows(simulated_windows, monkeypatch):
    """``MultiProcPlugin.__init__`` evaluates the probe as the eager default of
    ``memory_gb`` even when the caller passes it."""
    # A global sys.platform == "win32" also sends nipype's gpu_count into
    # Windows-only stdlib code (shutil.which -> _winapi); it is not under test.
    monkeypatch.setattr(nipype_multiproc, "gpu_count", lambda: 0)
    monkeypatch.setattr(sys, "platform", "win32")
    default = nipype_multiproc.MultiProcPlugin(plugin_args={"n_procs": 1})
    given = nipype_multiproc.MultiProcPlugin(
        plugin_args={"n_procs": 1, "memory_gb": 4.0}
    )
    try:
        assert default.memory_gb == pytest.approx(_PSUTIL_GB * 0.9)
        assert given.memory_gb == 4.0
    finally:
        for plugin in (default, given):
            plugin.pool.shutdown(wait=False, cancel_futures=True)


@posix_only
def test_probe_untouched_off_windows(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    assert npx.install_windows_memory_probe() is False
    for module in (nipype_profiler, nipype_multiproc, nipype_legacymultiproc):
        assert module.get_system_total_memory_gb is npx._orig_get_system_total_memory_gb


# --- 2. CommandLine "stream" output ---------------------------------------------


def _runtime(tmp_path, code):
    return Bunch(
        cmdline='"%s" -c "%s"' % (sys.executable, _SCRIPT % code),
        environ=dict(os.environ),
        cwd=str(tmp_path),
    )


def test_stock_stream_fails_on_windows_pipes(tmp_path, windows_select):
    """Root cause: the "stream" mode polls pipes with ``select.select``."""
    with pytest.raises(OSError) as err:
        npx._orig_run_command(_runtime(tmp_path, 0), output="stream")
    assert err.value.errno == 10038


@pytest.mark.parametrize("code", [0, 3])
def test_windows_stream_captures_like_linux(tmp_path, code, monkeypatch):
    # Reference: stock "stream" with the real select (Linux behaviour).
    reference = npx._orig_run_command(_runtime(tmp_path, code), output="stream")

    monkeypatch.setattr(
        nipype_subprocess, "select", types.SimpleNamespace(select=_not_a_socket)
    )
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    monkeypatch.setattr(nipype_core, "run_command", nipype_core.run_command)
    monkeypatch.setattr(nipype_subprocess, "run_command", nipype_subprocess.run_command)
    assert npx.install_windows_run_command() is True
    runtime = nipype_core.run_command(
        _runtime(tmp_path, code), output="stream", write_cmdline=True
    )

    assert runtime.returncode == reference.returncode == code
    assert runtime.stdout == reference.stdout == "out1\nout2"
    assert runtime.stderr == reference.stderr == "err1"

    def _untimed(merged):
        # "<stream> <iso timestamp>:<line>" -> (stream, line)
        return sorted(
            (row.split(" ", 1)[0], row.split(":", 3)[-1]) for row in merged.split("\n")
        )

    assert _untimed(runtime.merged) == _untimed(reference.merged)
    assert (tmp_path / "command.txt").read_text(encoding="utf-8") == _runtime(
        tmp_path, code
    ).cmdline


def test_windows_commandline_node_runs(tmp_path, simulated_windows, windows_select):
    """A real CommandLine with the default ``terminal_output="stream"``."""
    cmd = CommandLine(command=sys.executable, args='-c "%s"' % (_SCRIPT % 0))
    assert cmd.terminal_output == "stream"
    result = cmd.run(cwd=str(tmp_path))
    assert result.runtime.returncode == 0
    assert result.runtime.stdout == "out1\nout2"
    assert result.runtime.stderr == "err1"


@pytest.mark.parametrize("output", ["allatonce", "none", "file", "file_split"])
def test_windows_other_outputs_delegate_unchanged(tmp_path, simulated_windows, output):
    runtime = nipype_core.run_command(_runtime(tmp_path, 0), output=output)
    reference = npx._orig_run_command(_runtime(tmp_path, 0), output=output)
    assert (runtime.stdout, runtime.stderr, runtime.merged, runtime.returncode) == (
        reference.stdout,
        reference.stderr,
        reference.merged,
        reference.returncode,
    )


@posix_only
def test_run_command_untouched_off_windows(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    assert npx.install_windows_run_command() is False
    assert nipype_core.run_command is npx._orig_run_command
    assert nipype_subprocess.run_command is npx._orig_run_command
