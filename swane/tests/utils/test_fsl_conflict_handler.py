"""Unit tests for :mod:`swane.utils.fsl_conflict_handler` (pure helpers)."""

import sys

import swane.utils.fsl_conflict_handler as fc


def test_no_conflict_when_python_outside_fsl(monkeypatch):
    monkeypatch.setattr(fc.sys, "executable", "/usr/bin/python3")
    assert fc.fsl_conflict_check() is True


def test_conflict_without_gui_falls_back_to_console(monkeypatch, capsys):
    """Under the FSL-conflicted Python but with no usable Qt, the check must not
    crash on the PyQt5 import: it prints the fix to the console and reports the
    conflict (False) instead."""
    monkeypatch.setattr(fc.sys, "executable", "/opt/fsl/bin/python3")
    # Force the in-function PyQt5 import to fail, whether or not PyQt5 is
    # installed (a ``None`` entry in sys.modules makes the import raise).
    monkeypatch.setitem(sys.modules, "PyQt5", None)
    monkeypatch.setitem(sys.modules, "PyQt5.QtWidgets", None)
    # Keep the test hermetic: no clipboard subprocess.
    monkeypatch.setattr(fc, "is_command_available", lambda *a, **k: False)
    monkeypatch.setattr(fc, "is_mac", lambda: False)

    assert fc.fsl_conflict_check() is False
    assert fc.FIX_LINE in capsys.readouterr().err


def test_check_config_file(tmp_path):
    good = tmp_path / "profile_ok"
    good.write_text("source SetUpFreeSurfer.sh\n")
    assert fc.check_config_file(str(good)) is True

    bad = tmp_path / "profile_bad"
    bad.write_text("export PATH=/usr/bin\n")
    assert fc.check_config_file(str(bad)) is False

    assert fc.check_config_file(str(tmp_path / "missing")) is False


def test_config_file_fix_appends_fix_line(tmp_path):
    profile = tmp_path / "profile"
    profile.write_text("original content\n")
    fc.config_file_fix(str(profile))
    assert fc.FIX_LINE in profile.read_text()
