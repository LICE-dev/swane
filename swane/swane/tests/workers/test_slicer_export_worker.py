import subprocess

from types import SimpleNamespace

from swane.workers.SlicerExportWorker import SlicerExportWorker
from swane.tests.helpers.dicom_factory import write_minimal_dicom


def test_slicer_export_emits_progress(monkeypatch, tmp_path):
    # Prepare a fake config with getfloat_safe returning thresholds
    class FakeConfig:
        def getfloat_safe(self, key, name):
            return 0.5

    called = []

    # Fake Popen that yields lines and supports wait
    class FakeStdout:
        def __init__(self, lines):
            self._lines = lines
            self._idx = 0

        def readline(self):
            if self._idx < len(self._lines):
                val = self._lines[self._idx]
                self._idx += 1
                return val
            return ""

        def close(self):
            pass

    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            self.stdout = FakeStdout(["SLICERLOADER: 10%\n", "SLICERLOADER: 100%\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    worker = SlicerExportWorker("/fake/slicer", str(tmp_path), ".mrml", FakeConfig())

    # replace signal exporter with simple capture
    worker.signal.export.emit = lambda v: called.append(v)

    worker.run()

    assert called[-1] == worker.END_MSG
    assert any("10%" in c or "100%" in c for c in called)
