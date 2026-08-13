import os
import subprocess
import tempfile
import platform
from swane.workers.SlicerCheckWorker import SlicerCheckWorker


def test_find_slicer_python_linux(monkeypatch):
    # simulate find output
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, shell, stdout: type(
            "P", (), {"stdout": b"/opt/Slicer/bin/PythonSlicer\n"}
        ),
    )
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    split, rel = SlicerCheckWorker.find_slicer_python("/nonexistent")
    assert isinstance(split, list)
    assert rel == "../Slicer"


def test_patch_add_and_remove(monkeypatch, tmp_path):
    # use temp file as ~/.slicerrc.py
    slicerrc = tmp_path / ".slicerrc.py"
    slicerrc.write_text('print("hello")\n')
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(slicerrc))

    # ensure no patch initially
    assert not SlicerCheckWorker.check_patch(str(slicerrc))
    # add patch
    SlicerCheckWorker.add_slicer_startup_patch()
    content = SlicerCheckWorker.read_slicerrc(str(slicerrc))
    assert SlicerCheckWorker.BEGIN_MARKER in content
    # check_patch should now be True
    assert SlicerCheckWorker.check_patch(str(slicerrc))
    # remove patch
    SlicerCheckWorker.remove_patch(str(slicerrc))
    assert SlicerCheckWorker.BEGIN_MARKER not in SlicerCheckWorker.read_slicerrc(
        str(slicerrc)
    )


def test_run_detects_slicer_and_modules(monkeypatch, tmp_path):
    # Prepare worker
    w = SlicerCheckWorker(current_slicer_path="")
    results = []
    w.signal.slicer.connect(
        lambda cmd, ver, label, state: results.append((cmd, ver, label, state))
    )

    # monkeypatch find_slicer_python to return a fake path
    monkeypatch.setattr(
        SlicerCheckWorker,
        "find_slicer_python",
        staticmethod(lambda p: (["/fake/path/bin/PythonSlicer"], "../Slicer")),
    )
    # monkeypatch os.path.exists so that constructed cmd exists
    monkeypatch.setattr(os.path, "exists", lambda p: True)

    # monkeypatch subprocess.run to return different outputs depending on command
    def fake_run(cmd, shell, stdout):
        s = b""
        if b"--version" in str(cmd).encode():
            s = b"Slicer 5.0\n"
        elif b"slicer_script_module_install.py" in str(cmd).encode():
            s = b"MODULE FOUND\n"
        else:
            s = b""
        return type("P", (), {"stdout": s})

    monkeypatch.setattr(subprocess, "run", fake_run)

    # run should append a result
    w.run()
    assert len(results) == 1
    cmd, ver, label, state = results[0]
    assert "Slicer" in label or ver != ""
