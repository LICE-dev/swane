"""The Windows ``pwd`` stub that lets Nipype's plugin package import."""

import os
import subprocess
import sys
import textwrap

import pytest

from swane.patches import windows_compat


def test_stub_installed_on_windows_when_pwd_is_missing(monkeypatch):
    monkeypatch.setattr(windows_compat.os, "name", "nt")
    # A None entry makes ``import pwd`` raise ImportError, like on Windows.
    monkeypatch.setitem(sys.modules, "pwd", None)

    assert windows_compat.install_pwd_stub() is True

    import pwd

    assert getattr(pwd, "__swane_stub__", False) is True
    with pytest.raises(KeyError):
        pwd.getpwuid(0)
    with pytest.raises(KeyError):
        pwd.getpwnam("anyone")
    assert pwd.getpwall() == []


def test_stub_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(windows_compat.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "pwd", None)
    assert windows_compat.install_pwd_stub() is False
    assert sys.modules["pwd"] is None


def test_stub_never_replaces_a_real_pwd(monkeypatch):
    if os.name == "nt":
        pytest.skip("no real pwd module on Windows")
    import pwd as real_pwd

    monkeypatch.setattr(windows_compat.os, "name", "nt")
    assert windows_compat.install_pwd_stub() is False
    assert sys.modules["pwd"] is real_pwd


def test_swane_import_makes_nipype_plugins_importable_without_pwd():
    """End to end, in a fresh interpreter: with ``pwd`` unavailable (as on
    Windows), importing swane must install the stub so MultiProcPlugin imports.

    Flipping the global ``os.name`` to ``"nt"`` breaks the standard library
    itself (``shutil`` then imports the Windows-only ``nt`` module), so only
    ``windows_compat`` is made to see Windows: it is pre-loaded under its real
    module name with an ``os`` proxy whose ``name`` is ``"nt"``, and the
    ``from swane.patches.windows_compat import install_pwd_stub`` in
    ``swane/patches/__init__.py`` then picks up that pre-loaded module. The
    import therefore still proves the stub is installed before
    ``nipype.pipeline.plugins`` is imported.
    """
    code = textwrap.dedent("""
        import importlib.util, os, sys

        sys.modules["pwd"] = None  # ``import pwd`` now fails, as on Windows

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

        import swane  # swane/patches/__init__.py installs the stub first

        assert sys.modules["swane.patches.windows_compat"] is compat
        from nipype.pipeline.plugins.multiproc import MultiProcPlugin
        import pwd

        assert getattr(pwd, "__swane_stub__", False), pwd
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
