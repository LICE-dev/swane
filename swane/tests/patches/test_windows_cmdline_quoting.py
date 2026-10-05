"""Windows-safe quoting of Nipype command lines.

Nipype quotes path arguments with ``shlex.quote`` (POSIX single quotes) and
runs the command line with ``shell=True``, i.e. through ``cmd.exe`` on Windows,
where single quotes are literal characters. On Windows SWANe rebinds the
``shlex`` name used by ``nipype.interfaces.base.core`` to a proxy that quotes
with double quotes (MSVCRT rules) and splits with the same rules. Windows is
simulated here without touching the global ``os.name`` (which breaks the
standard library): only ``windows_compat.is_windows`` is made to answer True.
"""

import os
import shlex
import subprocess
import sys
import textwrap

import pytest
from nipype.interfaces.base import (
    CommandLine,
    CommandLineInputSpec,
    File,
    InputMultiPath,
    core as nipype_core,
)

import swane.patches.nipype_patches as npx
from swane.patches import windows_compat
from swane.tests.patches import spawn_helpers

WIN_PATH = r"C:\Users\Name Surname\in.nii.gz"
WIN_PATH_NO_SPACE = r"C:\data\in.nii.gz"
UNC_PATH = r"\\server\share\sub dir\in.nii.gz"
TRAILING_BACKSLASH = "C:\\out dir\\"


class _PathInputSpec(CommandLineInputSpec):
    # Test-only spec: no ``exists=True`` so Windows path strings are accepted.
    in_file = File(argstr="--in %s", position=0)
    in_files = InputMultiPath(File(), argstr="%s", position=1)


class _PathCommand(CommandLine):
    input_spec = _PathInputSpec
    _cmd = "tool"


@pytest.fixture
def simulated_windows(monkeypatch):
    """Activate the Windows quoting in this process, restored afterwards."""
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    monkeypatch.setattr(nipype_core, "shlex", nipype_core.shlex)
    assert npx.install_windows_cmdline_quoting() is True
    return nipype_core


# --- quote / split primitives -------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (WIN_PATH, '"C:\\Users\\Name Surname\\in.nii.gz"'),
        (WIN_PATH_NO_SPACE, '"C:\\data\\in.nii.gz"'),
        (TRAILING_BACKSLASH, '"C:\\out dir\\\\"'),
        ('a"b', '"a\\"b"'),
        ("", '""'),
        ("plain-name.nii.gz", "plain-name.nii.gz"),
    ],
)
def test_windows_quote(value, expected):
    assert windows_compat.windows_quote(value) == expected


@pytest.mark.parametrize(
    "value",
    [WIN_PATH, WIN_PATH_NO_SPACE, UNC_PATH, TRAILING_BACKSLASH, 'a"b', "", "x"],
)
def test_windows_split_round_trips_windows_quote(value):
    line = "tool --in " + windows_compat.windows_quote(value) + " tail"
    assert windows_compat.windows_split(line) == ["tool", "--in", value, "tail"]


def test_windows_split_keeps_bare_backslash_paths():
    """An unquoted ``C:\\...`` executable (no spaces) must survive the split
    nipype runs before ``which``; POSIX shlex would eat the backslashes."""
    assert windows_compat.windows_split(r"C:\env\niimath.exe -add 1") == [
        r"C:\env\niimath.exe",
        "-add",
        "1",
    ]


@pytest.mark.parametrize("value", [WIN_PATH, WIN_PATH_NO_SPACE, TRAILING_BACKSLASH])
def test_posix_shlex_split_also_round_trips_common_paths(value):
    """Ordinary drive paths are recovered even by POSIX ``shlex.split``."""
    assert shlex.split("tool " + windows_compat.windows_quote(value)) == [
        "tool",
        value,
    ]


def test_quoted_cmdline_matches_list2cmdline_for_spaced_paths():
    """For arguments that need quoting anyway, the result is what the stdlib's
    MSVCRT quoting (``subprocess.list2cmdline``) produces."""
    for value in (WIN_PATH, TRAILING_BACKSLASH, 'a b"c'):
        assert windows_compat.windows_quote(value) == subprocess.list2cmdline([value])


# --- nipype CommandLine integration ---------------------------------------------


def test_nipype_commandline_double_quotes_paths_on_windows(simulated_windows):
    node = _PathCommand(in_file=WIN_PATH)
    assert node.cmdline == 'tool --in "C:\\Users\\Name Surname\\in.nii.gz"'
    assert windows_compat.windows_split(node.cmdline) == ["tool", "--in", WIN_PATH]
    assert shlex.split(node.cmdline) == ["tool", "--in", WIN_PATH]

    node = _PathCommand(in_file=WIN_PATH_NO_SPACE)
    assert node.cmdline == 'tool --in "C:\\data\\in.nii.gz"'


def test_nipype_list_of_files_matches_stock_nipype(simulated_windows):
    """Stock nipype computes quoted list elements but never uses them, so
    list-of-path ``%s`` arguments are bare on every platform; the patch keeps
    that behaviour (see the module docstring of nipype_patches)."""
    node = _PathCommand(in_files=[WIN_PATH_NO_SPACE, r"C:\data\b.nii.gz"])
    assert node.cmdline == r"tool C:\data\in.nii.gz C:\data\b.nii.gz"


def test_nipype_executable_lookup_uses_windows_split(simulated_windows):
    assert simulated_windows.shlex.split('"C:\\Program Files\\x.exe" -v')[0] == (
        r"C:\Program Files\x.exe"
    )
    assert simulated_windows.shlex.split(r"C:\env\niimath.exe -v")[0] == (
        r"C:\env\niimath.exe"
    )


@pytest.mark.skipif(
    os.name == "nt",
    reason="on real Windows the quoting proxy is installed at import time",
)
def test_posix_is_byte_identical_to_stock_nipype(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: False)
    monkeypatch.setattr(nipype_core, "shlex", nipype_core.shlex)
    assert npx.install_windows_cmdline_quoting() is False
    assert nipype_core.shlex is shlex

    node = _PathCommand(in_file="/tmp/a b/in.nii.gz", in_files=["/x/a.nii", "/y/b"])
    assert node.cmdline == "tool --in '/tmp/a b/in.nii.gz' /x/a.nii /y/b"
    assert windows_compat.cmdline_quote("/tmp/a b") == shlex.quote("/tmp/a b")
    assert windows_compat.shell_executable("/opt/a b/niimath") == "/opt/a b/niimath"


def test_shell_executable_quotes_on_windows(monkeypatch):
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    exe = r"C:\Users\Name Surname\env\Lib\site-packages\niimath\bin\niimath.exe"
    assert windows_compat.shell_executable(exe) == f'"{exe}"'
    assert windows_compat.windows_split(windows_compat.shell_executable(exe)) == [exe]


# --- installation in every process ----------------------------------------------


def test_swane_import_installs_windows_quoting_on_windows():
    """In a fresh interpreter where ``windows_compat`` sees Windows, importing
    swane must rebind nipype's ``shlex`` and quote the bundled executables."""
    code = textwrap.dedent("""
        import importlib.util, os, sys

        class _WindowsOs:
            name = "nt"

            def __getattr__(self, attr):
                return getattr(os, attr)

        spec = importlib.util.spec_from_file_location(
            "swane.patches.windows_compat", sys.argv[1]
        )
        compat = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compat)
        compat.os = _WindowsOs()
        sys.modules["swane.patches.windows_compat"] = compat

        import swane
        from nipype.interfaces.base import core

        assert core.shlex is compat.WINDOWS_SHLEX, core.shlex
        import niimath
        from swane.nipype_pipeline.interfaces.niimath import NIIMATH_CMD
        from swane.nipype_pipeline.interfaces.niimath.maths import ImageMaths

        # A real Windows path always contains backslashes, hence is quoted.
        assert NIIMATH_CMD == compat.windows_quote(niimath.bin), NIIMATH_CMD
        assert ImageMaths._cmd == NIIMATH_CMD
        print("OK")
        """)
    result = subprocess.run(
        [sys.executable, "-c", code, windows_compat.__file__],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "OK" in result.stdout


def test_spawn_pool_worker_has_nipype_patches_applied_before_tasks(
    tmp_path, monkeypatch
):
    """A MultiProc ``spawn`` worker must have applied SWANe's Nipype patches
    (including the Windows quoting install) before it runs any node."""
    from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
        MonitoredMultiProcPlugin,
    )

    monkeypatch.chdir(tmp_path)
    plugin = MonitoredMultiProcPlugin(
        plugin_args={"n_procs": 1, "memory_gb": 1.0, "mp_context": "spawn"}
    )
    try:
        state = plugin.pool.submit(spawn_helpers.worker_cmdline_quoting_state).result(
            timeout=300
        )
    finally:
        plugin.pool.shutdown(wait=True)

    assert state["patched"] is True, state
    # Linux/macOS: the install is a no-op (stock shlex); Windows: the proxy is in.
    assert state["nipype_shlex_is_stdlib"] is (os.name != "nt"), state
