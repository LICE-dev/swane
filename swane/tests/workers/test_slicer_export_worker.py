import subprocess
from swane.workers.SlicerExportWorker import SlicerExportWorker

MODULES = ["/ext/A/lib/Slicer-5.10/qt-scripted-modules", "/ext B/qt-loadable-modules"]


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
            return self._lines.pop(0) if self._lines else ""

        def close(self):
            pass

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            assert isinstance(cmd, list)
            assert not kwargs.get("shell")
            # store cmd for inspection
            self.cmd = cmd
            self.stdout = FakeStdout(["SLICERLOADER: 10\n", "SLICERLOADER: 50\n", ""])

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    w = SlicerExportWorker(
        "slicer", str(tmp_path), ".mrml", FakeConfig(), module_paths=MODULES
    )
    w.signal.export.connect(lambda msg: emitted.append(msg))
    w.run()
    # should have emitted progress messages and finally END_MSG
    assert "10" in emitted[0]
    assert emitted[-1] == SlicerExportWorker.END_MSG


def test_slicer_export_keeps_script_path_separate(monkeypatch, tmp_path):
    """The --python-script path must be a single (quoted) argument, separate from
    the threshold arguments, so an install dir containing spaces is not split by
    the shell (regression for args glued into the os.path.join path)."""
    captured = {}

    class FakeStdout:
        def readline(self):
            return ""

        def close(self):
            pass

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            assert isinstance(cmd, list)
            assert not kwargs.get("shell")
            captured["cmd"] = cmd
            self.stdout = FakeStdout()

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    w = SlicerExportWorker(
        "slicer", str(tmp_path), ".mrml", FakeConfig(), module_paths=MODULES
    )
    w.run()

    cmd = captured["cmd"]
    idx = cmd.index("--python-script")
    # the element right after --python-script is the script path on its own
    assert cmd[idx + 1].endswith("slicer_script_result.py")
    # thresholds are separate elements, not concatenated onto the path
    for flag in ("--dti_threshold", "--vein_threshold_mr", "--vein_threshold_ct"):
        assert flag in cmd
    # Slicer runs isolated from the user's settings/slicerrc/extra modules, with
    # only the recorded extension module folders, each one argv element
    assert cmd[1:idx] == [
        "--no-splash",
        "--no-main-window",
        "--disable-settings",
        "--ignore-slicerrc",
        "--additional-module-paths",
        *MODULES,
    ]


def test_slicer_export_not_started_without_module_paths(monkeypatch, tmp_path):
    """Unknown extension module folders (no full Slicer check recorded them):
    an isolated Slicer would miss SlicerFreeSurfer, so Slicer is not launched,
    and END_MSG still closes the progress dialog."""
    emitted = []

    def unexpected_popen(cmd, **kwargs):
        raise AssertionError("Slicer must not be launched")

    monkeypatch.setattr(subprocess, "Popen", unexpected_popen)
    for module_paths in (None, []):
        emitted.clear()
        w = SlicerExportWorker(
            "slicer", str(tmp_path), ".mrml", FakeConfig(), module_paths=module_paths
        )
        w.signal.export.connect(emitted.append)
        w.run()
        assert emitted == [SlicerExportWorker.END_MSG]


def test_slicer_export_emits_end_msg_when_executable_missing(monkeypatch, tmp_path):
    """A stale/missing Slicer path makes Popen raise OSError: the modal progress
    dialog is closed by END_MSG, so it must still be emitted exactly once."""
    emitted = []

    def raising_popen(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(subprocess, "Popen", raising_popen)

    w = SlicerExportWorker(
        "/stale/Slicer", str(tmp_path), ".mrml", FakeConfig(), module_paths=MODULES
    )
    w.signal.export.connect(lambda msg: emitted.append(msg))
    w.run()
    assert emitted == [SlicerExportWorker.END_MSG]


def test_slicer_export_kills_child_if_reading_fails(monkeypatch, tmp_path):
    emitted = []
    state = {"killed": False, "waited": False}

    class BadStdout:
        def readline(self):
            raise OSError("pipe broke")

        def close(self):
            pass

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            self.stdout = BadStdout()

        def poll(self):
            return None

        def kill(self):
            state["killed"] = True

        def wait(self):
            state["waited"] = True

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    w = SlicerExportWorker(
        "slicer", str(tmp_path), ".mrml", FakeConfig(), module_paths=MODULES
    )
    w.signal.export.connect(emitted.append)
    w.run()
    assert state == {"killed": True, "waited": True}
    assert emitted == [SlicerExportWorker.END_MSG]
