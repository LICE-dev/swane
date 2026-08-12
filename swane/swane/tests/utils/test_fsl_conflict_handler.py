import os
import tempfile
import swane.utils.fsl_conflict_handler as fh


def test_check_config_file_and_config_fix(tmp_path):
    cfg = tmp_path / 'testcfg'
    cfg.write_text('some content')
    assert fh.check_config_file(str(cfg)) is False
    # write signature
    cfg.write_text('SetUpFreeSurfer.sh')
    assert fh.check_config_file(str(cfg)) is True

    # test config_file_fix appends FIX_LINE
    cfg2 = tmp_path / 'testcfg2'
    cfg2.write_text('start')
    fh.config_file_fix(str(cfg2))
    content = cfg2.read_text()
    assert fh.FIX_LINE in content


def test_get_config_file_prefers_shell(monkeypatch, tmp_path):
    # simulate home directory and SHELL env
    monkeypatch.setenv('SHELL', '/bin/bash')
    monkeypatch.setenv('HOME', str(tmp_path))
    # create a .profile with SetUpFreeSurfer.sh
    p = tmp_path / '.profile'
    p.write_text('SetUpFreeSurfer.sh')
    res = fh.get_config_file()
    assert str(p) in res or res == fh.strings.generic_shell_file
