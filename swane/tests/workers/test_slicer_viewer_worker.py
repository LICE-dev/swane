import subprocess
from swane.workers.SlicerViewerWorker import SlicerViewerWorker


def test_slicer_viewer_invokes_popen(monkeypatch):
    calls = []
    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            calls.append((cmd, cwd))
            self.stdout = None
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    w = SlicerViewerWorker('/path/to/slicer', '/path/to/scene.mrml')
    w.run()
    assert len(calls) == 1
    assert '/path/to/slicer' in calls[0][0]
    assert '/path/to/scene.mrml' in calls[0][0]
