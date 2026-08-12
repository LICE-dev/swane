import os
import swane.utils.DependencyManager as dm
from swane.config.ConfigManager import ConfigManager


def test_check_graphviz(monkeypatch):
    # simulate graphviz not present
    monkeypatch.setattr(dm, 'which', lambda cmd: None)
    depend = dm.DependencyManager.check_graphviz()
    assert depend.state == dm.DependenceStatus.WARNING

    # simulate graphviz present
    monkeypatch.setattr(dm, 'which', lambda cmd: '/usr/bin/dot')
    depend2 = dm.DependencyManager.check_graphviz()
    assert depend2.state == dm.DependenceStatus.DETECTED


def test_need_slicer_check(monkeypatch, tmp_path):
    config = ConfigManager(global_base_folder=str(tmp_path))
    config.set_slicer_path('fake_slicer')
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    monkeypatch.setattr(dm.DependencyManager, 'check_slicer_version', staticmethod(lambda version: True))
    monkeypatch.setattr(config, 'get_slicer_validator', lambda: False)

    assert dm.DependencyManager.need_slicer_check(config) is False
