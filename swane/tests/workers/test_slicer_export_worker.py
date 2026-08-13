import subprocess
from swane.workers.SlicerExportWorker import SlicerExportWorker


class FakeConfig:
    def getfloat_safe(self, *args, **kwargs):
        return 0.5


def test_slicer_export_emits_progress(monkeypatch, tmp_path):
    emitted = []

    # fake Popen and stdout readline behavior
    class FakeStdout:
        def __init__(self, lines):
            self._lines = lines
        def readline(self):
            return self._lines.pop(0) if self._lines else ''
        def close(self):
            pass

    class FakePopen:
        def __init__(self, cmd, cwd, shell, stdout, universal_newlines):
            # store cmd for inspection
            self.cmd = cmd
            self.stdout = FakeStdout(['SLICERLOADER: 10\n', 'SLICERLOADER: 50\n', ''])
        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, 'Popen', FakePopen)

    w = SlicerExportWorker('slicer', str(tmp_path), '.mrml', FakeConfig())
    w.signal.export.connect(lambda msg: emitted.append(msg))
    w.run()
    # should have emitted progress messages and finally END_MSG
    assert '10' in emitted[0]
    assert emitted[-1] == SlicerExportWorker.END_MSG
