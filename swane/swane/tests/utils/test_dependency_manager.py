import os
import shutil
import types

from swane.utils.DependencyManager import DependencyManager
from swane.config.ConfigManager import ConfigManager


class FakeConfig:
    def __init__(self, path_exists=True, version_ok=True, validator=False):
        self._path = '/nonexistent' if not path_exists else __file__
        self._version = '6.0.7' if version_ok else '0.0.1'
        self._validator = validator

    def get_slicer_path(self):
        return self._path

    def get_slicer_version(self):
        return self._version

    def get_slicer_validator(self):
        return self._validator


def test_check_slicer_version():
    assert DependencyManager.check_slicer_version('5.2.1') is True
    assert DependencyManager.check_slicer_version('0.0.1') is False
    assert DependencyManager.check_slicer_version('') is False


def test_need_slicer_check(monkeypatch):
    # config None or not global_config
    assert DependencyManager.need_slicer_check(None) is False

    # fake config with non-existing path triggers need check
    cfg = FakeConfig(path_exists=False, version_ok=False, validator=False)
    assert DependencyManager.need_slicer_check(cfg) is True

    # config with valid path and version
    cfg2 = FakeConfig(path_exists=True, version_ok=True, validator=False)
    # monkeypatch os.path.exists used in is_slicer
    monkeypatch.setattr(os.path, 'exists', lambda p: True)
    assert DependencyManager.need_slicer_check(cfg2) is False


def test_check_graphviz(monkeypatch):
    # patch shutil.which used via import
    import swane.utils.DependencyManager as dm
    monkeypatch.setattr(dm, 'which', lambda name: None)
    dep = DependencyManager.check_graphviz()
    assert dep.state is not None

    monkeypatch.setattr(dm, 'which', lambda name: '/usr/bin/dot')
    dep2 = DependencyManager.check_graphviz()
    assert dep2.state is not None
