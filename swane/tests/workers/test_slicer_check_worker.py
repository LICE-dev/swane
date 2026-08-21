import os
import shlex
import subprocess
import tempfile
import platform
from swane.workers.SlicerCheckWorker import SlicerCheckWorker
from swane.utils.DependencyManager import DependencyManager


def test_find_slicer_python_linux(monkeypatch):
    # simulate find output
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, shell, stdout, timeout: type(
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


def test_patch_is_idempotent(monkeypatch, tmp_path):
    slicerrc = tmp_path / ".slicerrc.py"
    slicerrc.write_text('print("hello")\n')
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(slicerrc))

    SlicerCheckWorker.add_slicer_startup_patch()
    first = SlicerCheckWorker.read_slicerrc(str(slicerrc))
    SlicerCheckWorker.add_slicer_startup_patch()
    second = SlicerCheckWorker.read_slicerrc(str(slicerrc))
    assert first == second
    assert second.count(SlicerCheckWorker.BEGIN_MARKER) == 1


def test_patch_replaces_outdated_patch(monkeypatch, tmp_path):
    slicerrc = tmp_path / ".slicerrc.py"
    slicerrc.write_text('print("hello")\n')
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(slicerrc))

    stale = (
        SlicerCheckWorker.BEGIN_MARKER
        + "\n# stale content\n"
        + SlicerCheckWorker.END_MARKER
        + "\n"
    )
    slicerrc.write_text(slicerrc.read_text() + stale)
    assert not SlicerCheckWorker.check_patch(str(slicerrc))

    SlicerCheckWorker.add_slicer_startup_patch()
    content = SlicerCheckWorker.read_slicerrc(str(slicerrc))
    assert "stale content" not in content
    assert content.count(SlicerCheckWorker.BEGIN_MARKER) == 1
    assert SlicerCheckWorker.check_patch(str(slicerrc))


def test_patch_migrates_away_legacy_hidezero_block(monkeypatch, tmp_path):
    slicerrc = tmp_path / ".slicerrc.py"
    legacy = (
        'print("user line before")\n'
        "# === BEGIN HIDEZERO PATCH ===\n"
        "def apply_hide_zero(node):\n"
        "    pass\n"
        "# === END HIDEZERO PATCH ===\n"
        'print("user line after")\n'
    )
    slicerrc.write_text(legacy)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(slicerrc))

    SlicerCheckWorker.add_slicer_startup_patch()
    content = SlicerCheckWorker.read_slicerrc(str(slicerrc))
    assert "HIDEZERO" not in content
    assert "user line before" in content
    assert "user line after" in content
    assert SlicerCheckWorker.check_patch(str(slicerrc))


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


def test_module_install_command_keeps_script_path_separate(monkeypatch):
    """The slicer_script_module_install.py path must be a single (quoted)
    argument with the module list as a separate argument, so an install dir
    containing spaces is not split by the shell (regression for args glued into
    the os.path.join path)."""
    w = SlicerCheckWorker(current_slicer_path="")

    monkeypatch.setattr(
        SlicerCheckWorker,
        "find_slicer_python",
        staticmethod(lambda p: (["/fake/path/bin/PythonSlicer"], "../Slicer")),
    )
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    # force the version check to pass so the module-install branch is reached
    monkeypatch.setattr(
        DependencyManager, "check_slicer_version", staticmethod(lambda v: True)
    )
    # do not touch the real ~/.slicerrc.py on the success path
    monkeypatch.setattr(
        SlicerCheckWorker, "add_slicer_startup_patch", staticmethod(lambda: None)
    )

    commands = []

    def fake_run(cmd, shell, stdout):
        commands.append(cmd)
        if "--version" in cmd:
            s = b"Slicer 5.0\n"
        elif "slicer_script_module_install.py" in cmd:
            s = b"MODULE FOUND\n"
        else:
            s = b""
        return type("P", (), {"stdout": s})

    monkeypatch.setattr(subprocess, "run", fake_run)

    w.run()

    install_cmd = next(
        c for c in commands if "slicer_script_module_install.py" in c
    )
    tokens = shlex.split(install_cmd)
    idx = tokens.index("--python-script")
    # the token right after --python-script is the script path on its own
    assert tokens[idx + 1].endswith("slicer_script_module_install.py")
    # modules are passed as their own argument, not glued onto the script path
    assert tokens[idx + 2] == ",".join(DependencyManager.SLICER_MODULES)
