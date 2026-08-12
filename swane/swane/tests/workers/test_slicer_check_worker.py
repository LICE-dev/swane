import os
import subprocess

import pytest

from swane.workers.SlicerCheckWorker import SlicerCheckWorker


def test_read_write_and_patch_cycle(tmp_path, monkeypatch):
    # Use a temporary file to act as ~/.slicerrc.py
    temp_file = tmp_path / "slicerrc.py"
    # ensure expanduser points to our temp file
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(temp_file) if p == "~/.slicerrc.py" else os.path.expanduser(p))

    # Initially file does not exist, read_slicerrc should return empty
    assert SlicerCheckWorker.read_slicerrc(str(temp_file)) == ""

    # Write content
    SlicerCheckWorker.write_slicerrc(str(temp_file), "hello world")
    assert SlicerCheckWorker.read_slicerrc(str(temp_file)) == "hello world"

    # add patch should append HIDE_ZERO_CODE
    SlicerCheckWorker.add_slicer_startup_patch()
    content = SlicerCheckWorker.read_slicerrc(str(temp_file))
    assert SlicerCheckWorker.BEGIN_MARKER in content
    assert SlicerCheckWorker.END_MARKER in content

    # check_patch should return True now
    assert SlicerCheckWorker.check_patch(str(temp_file)) is True

    # remove_patch should remove it
    SlicerCheckWorker.remove_patch(str(temp_file))
    assert SlicerCheckWorker.check_patch(str(temp_file)) is False


def test_find_slicer_python_returns_paths(monkeypatch):
    # Simulate subprocess.run returning a path
    fake_output = "/opt/Slicer/bin/PythonSlicer\n"

    class FakeCompleted:
        def __init__(self, out):
            self.stdout = out

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompleted(fake_output))

    paths, rel = SlicerCheckWorker.find_slicer_python("/")
    # Should include our path without newline
    assert any("PythonSlicer" in p for p in paths)
    assert isinstance(rel, str)
