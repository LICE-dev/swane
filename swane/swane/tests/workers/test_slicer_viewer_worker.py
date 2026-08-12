import subprocess

from swane.workers.SlicerViewerWorker import SlicerViewerWorker


def test_slicer_viewer_invokes_popen(monkeypatch):
    captured = {}

    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            captured['cmd'] = cmd
            captured['cwd'] = cwd
            captured['shell'] = shell
            captured['stdout'] = stdout

    monkeypatch.setattr(subprocess, 'Popen', FakePopen)

    worker = SlicerViewerWorker('/fake/slicer', '/path/scene.mrml')
    worker.run()

    assert '/fake/slicer /path/scene.mrml' in captured['cmd']
    assert captured['shell'] is True
