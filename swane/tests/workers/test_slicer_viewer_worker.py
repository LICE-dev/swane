import subprocess
from swane.workers.SlicerViewerWorker import SlicerViewerWorker


def test_slicer_viewer_invokes_popen(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            calls.append((cmd, cwd, stdout))
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    w = SlicerViewerWorker("/path/to/slicer", "/path/to/scene.mrml")
    w.run()
    assert len(calls) == 1
    assert "/path/to/slicer" in calls[0][0]
    assert "/path/to/scene.mrml" in calls[0][0]


def test_slicer_viewer_discards_stdout(monkeypatch):
    """stdout must go to DEVNULL: an undrained PIPE would fill its OS buffer and
    deadlock Slicer once it prints enough output."""
    captured = {}

    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            captured["stdout"] = stdout
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    w = SlicerViewerWorker("/path/to/slicer", "/path/to/scene.mrml")
    w.run()
    assert captured["stdout"] is subprocess.DEVNULL
