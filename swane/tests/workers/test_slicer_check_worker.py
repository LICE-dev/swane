import os
import shlex
import shutil
import subprocess
import tempfile
import platform

import pytest

from swane.utils.qt_compat import QThreadPool
from swane.workers.SlicerCheckWorker import SlicerCheckWorker
from swane.utils.DependencyManager import DependencyManager, DependenceStatus


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

    install_cmd = next(c for c in commands if "slicer_script_module_install.py" in c)
    tokens = shlex.split(install_cmd)
    idx = tokens.index("--python-script")
    # the token right after --python-script is the script path on its own
    assert tokens[idx + 1].endswith("slicer_script_module_install.py")
    # modules are passed as their own argument, not glued onto the script path
    assert tokens[idx + 2] == ",".join(DependencyManager.SLICER_MODULES)


class TestSlicerCheckWorkerReal:
    """Exercises :class:`SlicerCheckWorker` against a real, installed Slicer.

    Ported from the retired ``integration/test_dependency_manager.py``
    (``test_slicer_dep``): nothing here can be faked without a real bundled
    Slicer, so it stays a heavy, opt-in test (``--run-heavy``).

    Every scenario except "simulated absence" runs against a *disposable copy*
    of the real install (``shutil.copytree`` into ``tmp_path``, never a shell
    ``cp -r`` string — this codebase already treats unquoted paths-with-spaces
    as a real risk, see ``test_module_install_command_keeps_script_path_separate``
    above), so a crash mid-test leaves at worst a leftover temp directory.

    "Simulated absence" is the one scenario that must touch the real install:
    ``SlicerCheckWorker.run()`` falls back to a full-filesystem search whenever
    a scoped ``current_slicer_path`` lookup comes up empty (see
    ``find_slicer_python``), so pointing it at a copy with the executable
    renamed away would just have it re-discover the untouched real one instead
    of reporting MISSING. The original version of this test renamed the real
    ``PythonSlicer`` with two bare ``shutil.move`` calls and no ``finally``:
    if the assertion in between raised (or ``waitSignal`` timed out), the
    restore never ran and the developer's real Slicer install was left
    permanently broken. The ``try/finally`` below guarantees the restore runs
    even then.
    """

    pytestmark = [pytest.mark.heavy, pytest.mark.requires_slicer]

    def test_slicer_detection_and_module_lifecycle(self, monkeypatch, qtbot, tmp_path):
        # conftest forces QT_QPA_PLATFORM=offscreen for the whole session so
        # swane's own headless Qt app can start; swane's QApplication is
        # already running by now, so clearing it here only affects the
        # environment inherited by the real Slicer subprocess below, whose
        # bundled Qt has no "offscreen" plugin and would otherwise crash.
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

        # --- Real presence check: read-only, never mutates the real install.
        slicer_check_worker = SlicerCheckWorker("")
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.DETECTED, "slicer presence error"

        real_slicer = blocker.args[0]
        assert os.access(real_slicer, os.W_OK) is True, "Slicer non writeable"
        slicer_dir = os.path.dirname(real_slicer)
        slicer_python = os.path.join(slicer_dir, "bin", "PythonSlicer")
        assert os.path.exists(slicer_python) is True, "PythonSlicer not found"

        # --- Simulated absence: the only scenario that must touch the real
        # install (see class docstring). Guarded so the restore always runs.
        slicer_python_bk = slicer_python + "_bk"
        shutil.move(slicer_python, slicer_python_bk)
        try:
            slicer_check_worker = SlicerCheckWorker("")
            with qtbot.waitSignal(
                slicer_check_worker.signal.slicer, timeout=2000000
            ) as blocker:
                QThreadPool.globalInstance().start(slicer_check_worker)
            assert blocker.args[3] == DependenceStatus.MISSING, "slicer absence error"
        finally:
            shutil.move(slicer_python_bk, slicer_python)
        assert os.path.exists(slicer_python), "restore of the real PythonSlicer failed"

        # --- From here on, everything runs against a disposable copy: custom
        # path detection, module uninstall/reinstall, missing module, outdated
        # version. The real install is never touched again.
        slicer_dir_copy = os.path.join(str(tmp_path), os.path.basename(slicer_dir))
        shutil.copytree(slicer_dir, slicer_dir_copy)

        found_list, _ = SlicerCheckWorker.find_slicer_python(slicer_dir_copy)
        assert found_list, "Error on duplicating Slicer"
        copy_slicer = os.path.join(slicer_dir_copy, "Slicer")
        assert os.path.exists(copy_slicer), "Error on duplicating Slicer"

        slicer_check_worker = SlicerCheckWorker(copy_slicer)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            slicer_dir_copy in blocker.args[0]
        ), "Error in specifing custom Slicer executable"
        cmd = blocker.args[0]

        # uninstall and reinstall module from the copy
        os.system(
            cmd
            + " --no-main-window --python-code 'manager = slicer.app.extensionsManagerModel();manager.scheduleExtensionForUninstall(\"SlicerFreeSurfer\");import sys;sys.exit(0)'"
        )
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.DETECTED
        ), "Cannot reinstall SlicerFreeSurfer error"

        # try to install a non-existing module
        monkeypatch.setattr(DependencyManager, "SLICER_MODULES", ["blabla"])
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Missing module not raising error"

        # outdated Slicer version
        monkeypatch.setattr(DependencyManager, "MIN_SLICER_VERSION", "1000")
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            QThreadPool.globalInstance().start(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Slicer outdated version error"
