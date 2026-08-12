import swane.utils.DependencyManager as dm


def test_check_graphviz(monkeypatch):
    # simulate graphviz not present
    monkeypatch.setattr(dm, 'is_command_available', lambda cmd: False)
    d = dm.DependencyManager()
    assert d.check_graphviz() is False

    # simulate graphviz present
    monkeypatch.setattr(dm, 'is_command_available', lambda cmd: True)
    d2 = dm.DependencyManager()
    assert d2.check_graphviz() is True


def test_need_slicer_check(monkeypatch):
    monkeypatch.setattr(dm, 'is_command_available', lambda cmd: True)
    d = dm.DependencyManager()
    # when slicer is available, need_slicer_check should be False
    assert d.need_slicer_check() is False
