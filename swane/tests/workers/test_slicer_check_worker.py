import os
import shutil
import subprocess
import tempfile
import platform

import pytest

from swane.workers.SlicerCheckWorker import SlicerCheckWorker
from swane.workers.worker_pool import start_worker
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


@pytest.fixture
def fake_macos_bundle(monkeypatch, tmp_path):
    """A minimal Slicer.app under ``tmp_path/Applications``, on "macOS"."""
    contents = tmp_path / "Applications" / "Slicer.app" / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "bin").mkdir()
    (contents / "MacOS" / "Slicer").write_text("")
    (contents / "bin" / "PythonSlicer").write_text("")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    return contents


#: The macOS and Linux search shells out to ``find``: a simulated macOS needs a
#: POSIX ``find`` (none on Windows), a simulated Linux the GNU ``-executable``
#: test (absent from the BSD ``find`` of macOS).
needs_posix_find = pytest.mark.skipif(
    platform.system() == "Windows", reason="the macOS search runs POSIX find"
)
needs_gnu_find = pytest.mark.skipif(
    platform.system() != "Linux", reason="the Linux search runs GNU find"
)


@needs_posix_find
@pytest.mark.parametrize(
    "given",
    [
        "Applications",  # the folder holding the bundle
        "Applications/Slicer.app",  # the bundle itself
        "Applications/Slicer.app/Contents/MacOS",  # the executable's folder
        "Applications/Slicer.app/Contents/MacOS/Slicer",  # the executable
    ],
)
def test_find_slicer_python_macos_accepts_any_path_in_or_above_the_bundle(
    fake_macos_bundle, tmp_path, given
):
    split, _ = SlicerCheckWorker.find_slicer_python(str(tmp_path / given))
    assert split == [str(fake_macos_bundle / "bin" / "PythonSlicer")]


@pytest.mark.skipif(platform.system() == "Windows", reason="POSIX symlinks")
def test_find_slicer_python_macos_follows_a_symlinked_launcher(
    fake_macos_bundle, tmp_path
):
    # e.g. a "Slicer" command linked into /usr/local/bin
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    (link_dir / "Slicer").symlink_to(fake_macos_bundle / "MacOS" / "Slicer")
    split, _ = SlicerCheckWorker.find_slicer_python(str(link_dir / "Slicer"))
    assert split == [str(fake_macos_bundle / "bin" / "PythonSlicer")]


@needs_gnu_find
def test_find_slicer_python_linux_follows_a_symlinked_launcher(monkeypatch, tmp_path):
    install = tmp_path / "Slicer-5.12.4-linux-amd64"
    (install / "bin").mkdir(parents=True)
    (install / "Slicer").write_text("")
    python = install / "bin" / "PythonSlicer"
    python.write_text("")
    python.chmod(0o755)
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    (link_dir / "Slicer").symlink_to(install / "Slicer")
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    split, _ = SlicerCheckWorker.find_slicer_python(str(link_dir / "Slicer"))
    assert split == [str(python)]


def test_macos_bundle_root_outside_a_bundle_is_unchanged(tmp_path):
    assert SlicerCheckWorker._macos_bundle_root(str(tmp_path)) == str(tmp_path)


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
    def fake_run(cmd, **kwargs):
        assert isinstance(cmd, list), "Slicer must be invoked with an argv list"
        assert not kwargs.get("shell"), "no shell: paths with spaces must survive"
        s = b""
        joined = " ".join(cmd)
        if "--version" in cmd:
            s = b"Slicer 5.0\n"
        elif "slicer_script_module_install.py" in joined:
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

    def fake_run(cmd, **kwargs):
        assert isinstance(cmd, list), "Slicer must be invoked with an argv list"
        assert not kwargs.get("shell"), "no shell: paths with spaces must survive"
        commands.append(cmd)
        joined = " ".join(cmd)
        if "--version" in cmd:
            s = b"Slicer 5.0\n"
        elif "slicer_script_module_install.py" in joined:
            s = b"MODULE FOUND\n"
        else:
            s = b""
        return type("P", (), {"stdout": s})

    monkeypatch.setattr(subprocess, "run", fake_run)

    w.run()

    install_cmd = next(
        c for c in commands if any("slicer_script_module_install.py" in t for t in c)
    )
    idx = install_cmd.index("--python-script")
    assert install_cmd[idx + 1].endswith("slicer_script_module_install.py")
    assert install_cmd[idx + 2] == ",".join(DependencyManager.SLICER_MODULES)


def test_find_slicer_python_windows_searches_localappdata(monkeypatch, tmp_path):
    install = tmp_path / "slicer.org" / "Slicer 5.8.1"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "PythonSlicer.exe").write_bytes(b"")
    (install / "Slicer.exe").write_bytes(b"")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)

    def no_find(*args, **kwargs):
        raise AssertionError("GNU find must not be used on Windows")

    monkeypatch.setattr(subprocess, "run", no_find)

    paths, rel = SlicerCheckWorker.find_slicer_python("")
    assert rel == "../Slicer.exe"
    assert paths == [str(install / "bin" / "PythonSlicer.exe")]
    slicer = os.path.abspath(os.path.join(os.path.dirname(paths[0]), rel))
    assert slicer == str(install / "Slicer.exe")


def test_find_slicer_python_windows_prefers_newest_and_user_path(monkeypatch, tmp_path):
    for version in ("Slicer 5.6.2", "Slicer 5.8.1"):
        (tmp_path / "slicer.org" / version / "bin").mkdir(parents=True)
        (tmp_path / "slicer.org" / version / "bin" / "PythonSlicer.exe").write_bytes(
            b""
        )
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths, _ = SlicerCheckWorker.find_slicer_python("")
    assert "Slicer 5.8.1" in paths[0]

    # A user-chosen install folder (or its Slicer.exe) restricts the search.
    chosen = tmp_path / "slicer.org" / "Slicer 5.6.2"
    paths, _ = SlicerCheckWorker.find_slicer_python(str(chosen))
    assert paths == [str(chosen / "bin" / "PythonSlicer.exe")]


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
        # CI exports the Slicer it installed: start from it, as the app does
        # from its recorded path (the full-filesystem search stays the
        # fallback, and is what reports MISSING below).
        start_path = os.environ.get("SWANE_SLICER_PATH", "")
        slicer_check_worker = SlicerCheckWorker(start_path)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            start_worker(slicer_check_worker)
        assert blocker.args[3] == DependenceStatus.DETECTED, "slicer presence error"

        real_slicer = blocker.args[0]
        assert os.access(real_slicer, os.W_OK) is True, "Slicer non writeable"
        real_rev = SlicerCheckWorker.read_slicer_revision(real_slicer)
        assert (
            real_rev is not None
            and len(real_rev) > 0
            and any(c.isdigit() for c in real_rev)
        ), f"Failed to read valid revision from real Slicer at {real_slicer}: {real_rev}"
        # The install root: the .app bundle on macOS (the executable is in
        # Contents/MacOS), the executable's folder elsewhere.
        if platform.system() == "Darwin":
            slicer_dir = SlicerCheckWorker._macos_bundle_root(real_slicer)
        else:
            slicer_dir = os.path.dirname(real_slicer)
        found_list, _ = SlicerCheckWorker.find_slicer_python(slicer_dir)
        assert found_list, "PythonSlicer not found"
        slicer_python = found_list[0]

        # --- Simulated absence: the only scenario that must touch the real
        # install (see class docstring). Guarded so the restore always runs.
        slicer_python_bk = slicer_python + "_bk"
        shutil.move(slicer_python, slicer_python_bk)
        try:
            slicer_check_worker = SlicerCheckWorker(start_path)
            with qtbot.waitSignal(
                slicer_check_worker.signal.slicer, timeout=2000000
            ) as blocker:
                start_worker(slicer_check_worker)
            assert blocker.args[3] == DependenceStatus.MISSING, "slicer absence error"
        finally:
            shutil.move(slicer_python_bk, slicer_python)
        assert os.path.exists(slicer_python), "restore of the real PythonSlicer failed"

        # --- From here on, everything runs against a disposable copy: custom
        # path detection, module uninstall/reinstall, missing module, outdated
        # version. The real install is never touched again.
        slicer_dir_copy = os.path.join(str(tmp_path), os.path.basename(slicer_dir))
        # symlinks=True keeps a macOS bundle's internal links intact.
        shutil.copytree(slicer_dir, slicer_dir_copy, symlinks=True)

        found_list, _ = SlicerCheckWorker.find_slicer_python(slicer_dir_copy)
        assert found_list, "Error on duplicating Slicer"
        copy_slicer = os.path.join(
            slicer_dir_copy, os.path.relpath(real_slicer, slicer_dir)
        )
        assert os.path.exists(copy_slicer), "Error on duplicating Slicer"
        assert (
            SlicerCheckWorker.read_slicer_revision(copy_slicer) == real_rev
        ), "Revision on duplicated Slicer did not match real Slicer"

        slicer_check_worker = SlicerCheckWorker(copy_slicer)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            start_worker(slicer_check_worker)
        assert (
            slicer_dir_copy in blocker.args[0]
        ), "Error in specifing custom Slicer executable"
        cmd = blocker.args[0]

        # uninstall and reinstall module from the copy (argv list: no shell
        # quoting, so it runs the same on Windows and with spaces in cmd)
        subprocess.run(
            [
                cmd,
                "--no-main-window",
                "--python-code",
                "manager = slicer.app.extensionsManagerModel();"
                'manager.scheduleExtensionForUninstall("SlicerFreeSurfer");'
                "import sys;sys.exit(0)",
            ]
        )
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            start_worker(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.DETECTED
        ), "Cannot reinstall SlicerFreeSurfer error"

        # try to install a non-existing module
        monkeypatch.setattr(DependencyManager, "SLICER_MODULES", ["blabla"])
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            start_worker(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Missing module not raising error"

        # outdated Slicer version
        monkeypatch.setattr(DependencyManager, "MIN_SLICER_VERSION", "1000")
        slicer_check_worker = SlicerCheckWorker(cmd)
        with qtbot.waitSignal(
            slicer_check_worker.signal.slicer, timeout=2000000
        ) as blocker:
            start_worker(slicer_check_worker)
        assert (
            blocker.args[3] == DependenceStatus.WARNING
        ), "Slicer outdated version error"


def _patch_found_slicer(monkeypatch):
    monkeypatch.setattr(
        SlicerCheckWorker,
        "find_slicer_python",
        staticmethod(lambda p: (["/fake/path/bin/PythonSlicer"], "../Slicer")),
    )
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(
        SlicerCheckWorker, "add_slicer_startup_patch", staticmethod(lambda: None)
    )


def test_run_version_oserror_emits_single_non_detected_result(monkeypatch):
    """Slicer path found but not executable: signal still emitted exactly once."""
    _patch_found_slicer(monkeypatch)
    results = []
    w = SlicerCheckWorker(current_slicer_path="")
    w.signal.slicer.connect(lambda *a: results.append(a))

    def raising_run(cmd, **kwargs):
        raise PermissionError(13, "Permission denied", cmd[0])

    monkeypatch.setattr(subprocess, "run", raising_run)
    w.run()
    assert len(results) == 1
    assert results[0][3] != DependenceStatus.DETECTED


def test_run_module_install_oserror_emits_single_warning(monkeypatch):
    _patch_found_slicer(monkeypatch)
    monkeypatch.setattr(
        DependencyManager, "check_slicer_version", staticmethod(lambda v: True)
    )
    results = []
    w = SlicerCheckWorker(current_slicer_path="")
    w.signal.slicer.connect(lambda *a: results.append(a))

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return type("P", (), {"stdout": b"Slicer 5.6.2\n"})
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    w.run()
    assert len(results) == 1
    assert results[0][3] != DependenceStatus.DETECTED


def test_run_version_with_crlf_is_stripped(monkeypatch):
    _patch_found_slicer(monkeypatch)
    monkeypatch.setattr(
        DependencyManager, "check_slicer_version", staticmethod(lambda v: True)
    )
    results = []
    w = SlicerCheckWorker(current_slicer_path="")
    w.signal.slicer.connect(lambda *a: results.append(a))

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return type("P", (), {"stdout": b"Slicer 5.6.2\r\n"})
        return type("P", (), {"stdout": b"MODULE FOUND\r\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    w.run()
    assert results[0][1] == "5.6.2"


# --- Cheap revalidation of what a full check recorded -----------------------

REPORT = (
    "noise\n"
    "SLICER REVISION:34045\n"
    "MODULE PATH:SlicerFreeSurfer=/ext/Extensions-34045/SlicerFreeSurfer\n"
    "MODULE PATH:SurfaceWrapSolidify=C:\\ext\\Extensions-34045\\SurfaceWrapSolidify\r\n"
    "MODULE FOUND\n"
)


def test_parse_extension_report():
    state = SlicerCheckWorker.parse_extension_report(REPORT)
    assert state["revision"] == "34045"
    assert state["paths"] == {
        "SlicerFreeSurfer": "/ext/Extensions-34045/SlicerFreeSurfer",
        "SurfaceWrapSolidify": "C:\\ext\\Extensions-34045\\SurfaceWrapSolidify",
    }
    assert SlicerCheckWorker.parse_extension_report("") == {
        "revision": "",
        "paths": {},
    }


def _state(paths):
    import json

    return json.dumps({"revision": "1", "paths": {k: str(v) for k, v in paths.items()}})


def test_extensions_state_is_valid(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    ok = _state({"A": a, "B": b})
    assert SlicerCheckWorker.extensions_state_is_valid(ok, ["A", "B"]) is True

    # an extension folder removed by the user
    b.rmdir()
    assert SlicerCheckWorker.extensions_state_is_valid(ok, ["A", "B"]) is False
    # a required module the recorded state never listed
    assert SlicerCheckWorker.extensions_state_is_valid(ok, ["A", "C"]) is False
    # nothing recorded yet / garbage / wrong shape
    for bad in ["", "not json", "{}", "[]", '{"paths": []}', None]:
        assert SlicerCheckWorker.extensions_state_is_valid(bad, ["A"]) is False


@pytest.mark.skipif(platform.system() == "Windows", reason="POSIX exec bit")
def test_is_slicer_executable_posix(tmp_path):
    exe = tmp_path / "Slicer"
    exe.write_text("x")
    exe.chmod(0o644)
    assert SlicerCheckWorker.is_slicer_executable(str(exe)) is False
    exe.chmod(0o755)
    assert SlicerCheckWorker.is_slicer_executable(str(exe)) is True
    assert SlicerCheckWorker.is_slicer_executable(str(tmp_path)) is False
    assert SlicerCheckWorker.is_slicer_executable(str(tmp_path / "gone")) is False


def test_is_slicer_executable_windows_ignores_exec_bit(monkeypatch, tmp_path):
    exe = tmp_path / "Slicer.exe"
    exe.write_text("x")
    exe.chmod(0o644)
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    assert SlicerCheckWorker.is_slicer_executable(str(exe)) is True
    assert SlicerCheckWorker.is_slicer_executable(str(tmp_path)) is False


def test_run_emits_extensions_state_before_result(monkeypatch):
    _patch_found_slicer(monkeypatch)
    monkeypatch.setattr(
        DependencyManager, "check_slicer_version", staticmethod(lambda v: True)
    )
    events = []
    w = SlicerCheckWorker(current_slicer_path="")
    w.signal.extensions.connect(lambda s: events.append(("ext", s)))
    w.signal.slicer.connect(lambda *a: events.append(("slicer", a)))

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return type("P", (), {"stdout": b"Slicer 5.6.2\n"})
        return type("P", (), {"stdout": REPORT.encode()})

    monkeypatch.setattr(subprocess, "run", fake_run)
    w.run()
    assert [e[0] for e in events] == ["ext", "slicer"]
    import json

    assert json.loads(events[0][1])["revision"] == "34045"


def test_run_does_not_emit_extensions_state_when_module_missing(monkeypatch):
    _patch_found_slicer(monkeypatch)
    monkeypatch.setattr(
        DependencyManager, "check_slicer_version", staticmethod(lambda v: True)
    )
    events = []
    w = SlicerCheckWorker(current_slicer_path="")
    w.signal.extensions.connect(lambda s: events.append(s))

    def fake_run(cmd, **kwargs):
        if "--version" in cmd:
            return type("P", (), {"stdout": b"Slicer 5.6.2\n"})
        return type("P", (), {"stdout": b"MODULE MISSING:SlicerFreeSurfer\n"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    w.run()
    assert events == []


def test_read_slicer_revision_from_ini(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ini_file = bin_dir / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Application]\nrevision = 34045\n", encoding="utf-8")
    slicer_exe = tmp_path / "Slicer"
    slicer_exe.write_text("#!/bin/sh\n", encoding="utf-8")

    from swane.workers.SlicerCheckWorker import SlicerCheckWorker

    assert SlicerCheckWorker.read_slicer_revision(str(slicer_exe)) == "34045"


def test_read_slicer_revision_from_macos_plist(tmp_path, monkeypatch):
    import plistlib
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    bundle = tmp_path / "Slicer.app"
    contents = bundle / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    plist_file = contents / "Info.plist"
    with open(plist_file, "wb") as f:
        plistlib.dump({"CFBundleVersion": "34045"}, f)

    slicer_exe = macos / "Slicer"
    slicer_exe.write_text("#!/bin/sh\n", encoding="utf-8")

    from swane.workers.SlicerCheckWorker import SlicerCheckWorker

    assert SlicerCheckWorker.read_slicer_revision(str(slicer_exe)) == "34045"


def test_read_slicer_revision_from_macos_ini_precedence(tmp_path, monkeypatch):
    import plistlib
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    bundle = tmp_path / "Slicer.app"
    contents = bundle / "Contents"
    macos = contents / "MacOS"
    contents_bin = contents / "bin"
    macos.mkdir(parents=True)
    contents_bin.mkdir(parents=True)

    # Info.plist has the marketing/build version (e.g. 5.12.4)
    plist_file = contents / "Info.plist"
    with open(plist_file, "wb") as f:
        plistlib.dump({"CFBundleVersion": "5.12.4"}, f)

    # SlicerLauncherSettings.ini has the actual numeric revision
    ini_file = contents_bin / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Application]\nrevision = 34045\n", encoding="utf-8")

    slicer_exe = macos / "Slicer"
    slicer_exe.write_text("#!/bin/sh\n", encoding="utf-8")

    from swane.workers.SlicerCheckWorker import SlicerCheckWorker

    assert SlicerCheckWorker.read_slicer_revision(str(slicer_exe)) == "34045"


def test_read_slicer_revision_missing_or_corrupt(tmp_path):
    from swane.workers.SlicerCheckWorker import SlicerCheckWorker

    assert SlicerCheckWorker.read_slicer_revision("") is None
    assert SlicerCheckWorker.read_slicer_revision(str(tmp_path / "missing")) is None

    # Corrupt / missing revision section
    ini_file = tmp_path / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Other]\nkey = val\n", encoding="utf-8")
    assert SlicerCheckWorker.read_slicer_revision(str(tmp_path / "Slicer")) is None


def test_quick_check_revision_match(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ini_file = bin_dir / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Application]\nrevision = 34045\n", encoding="utf-8")
    slicer_exe = tmp_path / "Slicer"
    slicer_exe.write_text("", encoding="utf-8")

    def forbid_subprocess(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called during quick check")

    monkeypatch.setattr(subprocess, "run", forbid_subprocess)

    from swane.workers.SlicerCheckWorker import SlicerQuickCheckWorker

    results = []
    w = SlicerQuickCheckWorker(str(slicer_exe), "34045")
    w.signal.done.connect(results.append)
    w.run()
    assert results == [True]


def test_quick_check_revision_changed(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ini_file = bin_dir / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Application]\nrevision = 34100\n", encoding="utf-8")
    slicer_exe = tmp_path / "Slicer"
    slicer_exe.write_text("", encoding="utf-8")

    from swane.workers.SlicerCheckWorker import SlicerQuickCheckWorker

    results = []
    w = SlicerQuickCheckWorker(str(slicer_exe), "34045")
    w.signal.done.connect(results.append)
    w.run()
    assert results == [False]


def test_quick_check_missing_slicer_requests_full_check(tmp_path):
    from swane.workers.SlicerCheckWorker import SlicerQuickCheckWorker

    results = []
    w = SlicerQuickCheckWorker(str(tmp_path / "nonexistent"), "34045")
    w.signal.done.connect(results.append)
    w.run()
    assert results == [False]


def test_quick_check_empty_expected_revision_requests_full_check(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ini_file = bin_dir / "SlicerLauncherSettings.ini"
    ini_file.write_text("[Application]\nrevision = 34045\n", encoding="utf-8")
    slicer_exe = tmp_path / "Slicer"
    slicer_exe.write_text("", encoding="utf-8")

    from swane.workers.SlicerCheckWorker import SlicerQuickCheckWorker

    results = []
    w = SlicerQuickCheckWorker(str(slicer_exe), "")
    w.signal.done.connect(results.append)
    w.run()
    assert results == [False]


def test_module_install_script_reports_revision_and_paths(tmp_path):
    """The script run inside Slicer prints the markers the worker parses."""
    import importlib.util
    import io
    import sys
    import types
    from contextlib import redirect_stdout

    ext_dir = tmp_path / "SlicerFreeSurfer"
    ext_dir.mkdir()

    class EM:
        interactive = True

        def extensionInstallPath(self, name):
            return str(tmp_path / name)

    fake_slicer = types.SimpleNamespace(
        app=types.SimpleNamespace(extensionsManagerModel=lambda: EM(), revision=34045),
        moduleNames=types.SimpleNamespace(SlicerFreeSurfer=True),
    )
    import swane.workers as workers_pkg

    script = os.path.join(
        os.path.dirname(workers_pkg.__file__), "slicer_script_module_install.py"
    )
    spec = importlib.util.spec_from_file_location("slicer_install_under_test", script)
    mod = importlib.util.module_from_spec(spec)
    mod.slicer = fake_slicer
    spec.loader.exec_module(mod)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.install_extensions_from_args(["x", "SlicerFreeSurfer"])
    assert rc == 0
    state = SlicerCheckWorker.parse_extension_report(buf.getvalue())
    assert state["revision"] == "34045"
    assert state["paths"] == {"SlicerFreeSurfer": str(ext_dir)}
