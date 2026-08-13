"""Unit tests for :mod:`swane.utils.platform_and_tools_utils`."""

import swane.utils.platform_and_tools_utils as pu


def test_is_command_available(monkeypatch):
    monkeypatch.setattr(pu.shutil, "which", lambda cmd: None)
    assert pu.is_command_available("whatever") is False
    monkeypatch.setattr(pu.shutil, "which", lambda cmd: "/usr/bin/whatever")
    assert pu.is_command_available("whatever") is True


def test_os_type_helpers(monkeypatch):
    monkeypatch.setattr(pu.platform, "system", lambda: "Linux")
    assert pu.get_os_type() == "linux"
    assert pu.is_linux() is True
    assert pu.is_mac() is False

    monkeypatch.setattr(pu.platform, "system", lambda: "Darwin")
    assert pu.get_os_type() == "mac"
    assert pu.is_mac() is True

    monkeypatch.setattr(pu.platform, "system", lambda: "Windows")
    assert pu.get_os_type() == "other"
    assert pu.is_linux() is False
    assert pu.is_mac() is False
