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
    assert pu.get_os_type() == "windows"
    assert pu.is_windows() is True
    assert pu.is_linux() is False
    assert pu.is_mac() is False


def test_blank_spaces_allowed_only_on_windows(monkeypatch):
    from swane.config import dependency_policy

    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
    for system, allowed in (("Windows", True), ("Linux", False), ("Darwin", False)):
        monkeypatch.setattr(pu.platform, "system", lambda: system)
        assert pu.blank_spaces_allowed() is allowed


def test_blank_spaces_rejected_on_windows_when_fsl_is_mandatory(monkeypatch):
    """A mandatory FSL means FSL tools would run, and they break on spaces."""
    from swane.config import dependency_policy

    monkeypatch.setattr(pu, "is_windows", lambda: True)
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
    assert pu.blank_spaces_allowed() is False
