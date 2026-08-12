import platform
import shutil
from swane.utils.platform_and_tools_utils import is_command_available, get_os_type, is_mac, is_linux


def test_is_command_available(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda cmd: '/usr/bin/' + cmd if cmd == 'exists' else None)
    assert is_command_available('exists') is True
    assert is_command_available('missing') is False


def test_get_os_type(monkeypatch):
    monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
    assert get_os_type() == 'mac'
    monkeypatch.setattr(platform, 'system', lambda: 'Linux')
    assert get_os_type() == 'linux'
    monkeypatch.setattr(platform, 'system', lambda: 'Windows')
    assert get_os_type() == 'other'


def test_is_mac_linux(monkeypatch):
    monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
    assert is_mac() is True and is_linux() is False
    monkeypatch.setattr(platform, 'system', lambda: 'Linux')
    assert is_linux() is True and is_mac() is False
