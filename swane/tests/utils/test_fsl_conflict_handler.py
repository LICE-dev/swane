"""Unit tests for :mod:`swane.utils.fsl_conflict_handler` (pure helpers)."""

import swane.utils.fsl_conflict_handler as fc


def test_no_conflict_when_python_outside_fsl(monkeypatch):
    monkeypatch.setattr(fc.sys, "executable", "/usr/bin/python3")
    assert fc.fsl_conflict_check() is True


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
