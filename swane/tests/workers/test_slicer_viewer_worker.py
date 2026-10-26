import subprocess
from swane.workers.SlicerViewerWorker import SlicerViewerWorker


def test_slicer_viewer_invokes_popen(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    w = SlicerViewerWorker("/path/to/slicer", "/path/to/scene.mrml")
    w.run()
    assert len(calls) == 1
    assert calls[0][0] == ["/path/to/slicer", "/path/to/scene.mrml"]
    assert not calls[0][1].get("shell")


def test_slicer_viewer_discards_stdout(monkeypatch):
    """stdout must go to DEVNULL: an undrained PIPE would fill its OS buffer and
    deadlock Slicer once it prints enough output."""
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["stdout"] = kwargs["stdout"]
            self.stdout = None

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    w = SlicerViewerWorker("/path/to/slicer", "/path/to/scene.mrml")
    w.run()
    assert captured["stdout"] is subprocess.DEVNULL
