"""Unit tests for :mod:`swane.utils.linux_desktop_integration`."""

import os
import subprocess

import pytest

import swane.utils.linux_desktop_integration as mod
from swane.utils.linux_desktop_integration import (
    ensure_desktop_entry,
    remove_desktop_entry,
)

# The entry is Linux-only; these tests simulate Linux and rely on POSIX host
# semantics (realpath of a POSIX argv[0], running the launcher with ``sh``).
posix_host = pytest.mark.skipif(
    os.name == "nt", reason="needs POSIX path semantics and a POSIX sh"
)


@pytest.fixture(autouse=True)
def _no_inherited_swane_launcher(monkeypatch):
    """Hide a SWANE_LAUNCHER inherited from the developer's shell.

    The installer's launcher exports it to SWANe and what SWANe starts; the
    tests that need one set it themselves.
    """
    monkeypatch.delenv("SWANE_LAUNCHER", raising=False)


@pytest.fixture(autouse=True)
def _no_login_shell_reexec(monkeypatch):
    """Keep the generated launcher from re-running through the developer's shell.

    A launcher run with SHELL=bash/zsh re-executes itself through that login,
    interactive shell, which would read the developer's startup files; the tests
    that exercise it point SHELL at a fake shell themselves.
    """
    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.delenv(mod.LOGIN_SHELL_MARKER, raising=False)


def test_noop_on_non_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    ensure_desktop_entry("/some/icon.png")

    assert not (tmp_path / "applications" / "swane.desktop").exists()


@posix_host
def test_writes_desktop_entry_and_launcher_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])

    ensure_desktop_entry("/opt/swane/icon.png")

    desktop_file = tmp_path / "applications" / "swane.desktop"
    launcher_script = tmp_path / "swane" / "swane-launcher.sh"
    content = desktop_file.read_text()
    assert "Name=SWANe" in content
    assert "Icon=/opt/swane/icon.png" in content
    assert "StartupWMClass=swane" in content
    assert f'Exec="{launcher_script}"' in content
    assert "MedicalSoftware" not in content
    assert "Patient" not in content and "patient" not in content

    launcher_content = launcher_script.read_text()
    assert "/usr/local/bin/swane" in launcher_content
    assert os.access(launcher_script, os.X_OK)


@posix_host
def test_uses_swane_launcher_when_set(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])
    launcher = tmp_path / "bin" / "swane"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(0o755)
    monkeypatch.setenv("SWANE_LAUNCHER", str(launcher))

    ensure_desktop_entry("/opt/swane/icon.png")

    content = (tmp_path / "data" / "swane" / "swane-launcher.sh").read_text()
    assert f'exec "{launcher}"' in content
    assert f'[ -x "{launcher}" ]' in content
    assert "/usr/local/bin/swane" not in content


@posix_host
@pytest.mark.parametrize("mode", [0o644, None])
def test_ignores_swane_launcher_when_unusable(monkeypatch, tmp_path, mode):
    """A non-executable or missing SWANE_LAUNCHER falls back to argv[0]."""
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])
    launcher = tmp_path / "bin" / "swane"
    if mode is not None:
        launcher.parent.mkdir()
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(mode)
    monkeypatch.setenv("SWANE_LAUNCHER", str(launcher))

    ensure_desktop_entry("/opt/swane/icon.png")

    content = (tmp_path / "data" / "swane" / "swane-launcher.sh").read_text()
    assert 'exec "/usr/local/bin/swane"' in content
    assert str(launcher) not in content


def test_idempotent_when_content_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])

    ensure_desktop_entry("/opt/swane/icon.png")
    desktop_file = tmp_path / "applications" / "swane.desktop"
    launcher_script = tmp_path / "swane" / "swane-launcher.sh"
    first_desktop_mtime = desktop_file.stat().st_mtime_ns
    first_launcher_mtime = launcher_script.stat().st_mtime_ns

    ensure_desktop_entry("/opt/swane/icon.png")

    assert desktop_file.stat().st_mtime_ns == first_desktop_mtime
    assert launcher_script.stat().st_mtime_ns == first_launcher_mtime


def test_rewrites_when_icon_path_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])

    ensure_desktop_entry("/opt/swane/icon.png")
    ensure_desktop_entry("/opt/swane/other-icon.png")

    desktop_file = tmp_path / "applications" / "swane.desktop"
    assert "Icon=/opt/swane/other-icon.png" in desktop_file.read_text()


def test_never_raises_on_write_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])
    # An XDG_DATA_HOME pointing at a file (not a directory) makes os.makedirs fail.
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("blocked")
    monkeypatch.setenv("XDG_DATA_HOME", str(blocked))

    ensure_desktop_entry("/opt/swane/icon.png")


@posix_host
def test_launcher_self_heals_when_real_executable_is_gone(monkeypatch, tmp_path):
    """Simulates the launcher being clicked after `pip uninstall`: the real
    executable no longer exists, so the launcher must remove itself and the
    .desktop entry instead of failing silently or leaving them behind."""
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    missing_exec = tmp_path / "uninstalled-swane-bin"
    monkeypatch.setattr(mod.sys, "argv", [str(missing_exec)])

    ensure_desktop_entry("/opt/swane/icon.png")
    desktop_file = tmp_path / "applications" / "swane.desktop"
    launcher_script = tmp_path / "swane" / "swane-launcher.sh"
    assert desktop_file.exists() and launcher_script.exists()

    subprocess.run(["sh", str(launcher_script)], check=True)

    assert not desktop_file.exists()
    assert not launcher_script.exists()


def test_remove_desktop_entry_deletes_existing_files(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(mod.sys, "argv", ["/usr/local/bin/swane"])
    ensure_desktop_entry("/opt/swane/icon.png")
    desktop_file = tmp_path / "applications" / "swane.desktop"
    launcher_script = tmp_path / "swane" / "swane-launcher.sh"
    assert desktop_file.exists() and launcher_script.exists()

    remove_desktop_entry()

    assert not desktop_file.exists()
    assert not launcher_script.exists()


def test_remove_desktop_entry_noop_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    remove_desktop_entry()  # must not raise even if nothing was ever installed


def test_remove_desktop_entry_noop_on_non_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "applications").mkdir()
    desktop_file = tmp_path / "applications" / "swane.desktop"
    desktop_file.write_text("[Desktop Entry]\n")

    remove_desktop_entry()

    assert desktop_file.exists()


def _write_script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@posix_host
@pytest.mark.parametrize("shell_name", ["bash", "zsh"])
def test_launcher_runs_swane_through_login_shell(monkeypatch, tmp_path, shell_name):
    """A menu launch gets the environment of the user's shell startup files
    (e.g. FREESURFER_HOME set in ~/.bashrc): the launcher re-runs itself once
    through the login, interactive shell before starting SWANe."""
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    record = tmp_path / "record"
    target = _write_script(
        tmp_path / "bin" / "swane",
        f'echo "FREESURFER_HOME=$FREESURFER_HOME" >> "{record}"\n',
    )
    monkeypatch.setattr(mod.sys, "argv", [str(target)])
    # Fake login shell: records its flags, sets what ~/.bashrc would set and
    # runs the command string with the given $0, as bash -lic does.
    shell = _write_script(
        tmp_path / "shell" / shell_name,
        f'echo "SHELL_ARGS=$1" >> "{record}"\n'
        "FREESURFER_HOME=/opt/synthetic-freesurfer\n"
        "export FREESURFER_HOME\n"
        'exec /bin/sh -c "$2" "$3"\n',
    )
    monkeypatch.setenv("SHELL", str(shell))
    monkeypatch.delenv("FREESURFER_HOME", raising=False)

    ensure_desktop_entry("/opt/swane/icon.png")
    launcher_script = tmp_path / "data" / "swane" / "swane-launcher.sh"
    subprocess.run(["sh", str(launcher_script)], check=True, timeout=30)

    assert record.read_text().splitlines() == [
        "SHELL_ARGS=-lic",
        "FREESURFER_HOME=/opt/synthetic-freesurfer",
    ]


@posix_host
def test_launcher_runs_swane_directly_with_other_shells(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    record = tmp_path / "record"
    target = _write_script(tmp_path / "bin" / "swane", f'echo started >> "{record}"\n')
    monkeypatch.setattr(mod.sys, "argv", [str(target)])
    shell = _write_script(tmp_path / "shell" / "fish", f'echo shell >> "{record}"\n')
    monkeypatch.setenv("SHELL", str(shell))

    ensure_desktop_entry("/opt/swane/icon.png")
    launcher_script = tmp_path / "data" / "swane" / "swane-launcher.sh"
    subprocess.run(["sh", str(launcher_script)], check=True, timeout=30)

    assert record.read_text().splitlines() == ["started"]


@posix_host
def test_launch_target_runs_the_package_when_started_with_python_m(
    monkeypatch, tmp_path
):
    """Under "python -m swane" argv[0] is the non-executable __main__.py: the
    launcher must run the package with the current interpreter instead of
    deleting the entry as if SWANe had been uninstalled."""
    monkeypatch.setattr(mod, "is_linux", lambda: True)
    monkeypatch.setattr(mod, "is_command_available", lambda cmd: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    main_py = tmp_path / "site-packages" / "swane" / "__main__.py"
    main_py.parent.mkdir(parents=True)
    main_py.write_text("")
    main_py.chmod(0o644)
    record = tmp_path / "record"
    python = _write_script(
        tmp_path / "env" / "bin" / "python", f'echo "$@" > "{record}"\n'
    )
    monkeypatch.setattr(mod.sys, "argv", [str(main_py)])
    monkeypatch.setattr(mod.sys, "executable", str(python))

    assert mod._launch_target() == [str(python), "-m", "swane"]

    ensure_desktop_entry("/opt/swane/icon.png")
    launcher_script = tmp_path / "data" / "swane" / "swane-launcher.sh"
    desktop_file = tmp_path / "data" / "applications" / "swane.desktop"
    subprocess.run(["sh", str(launcher_script)], check=True, timeout=30)

    assert record.read_text() == "-m swane\n"
    assert desktop_file.exists() and launcher_script.exists()


def test_main_handles_remove_desktop_entry_flag(monkeypatch):
    """The console script ("swane") calls main() directly: the flag must be
    handled there instead of starting the GUI."""
    import swane.__main__ as main_mod

    removed = []
    monkeypatch.setattr(mod, "remove_desktop_entry", lambda: removed.append(True))
    monkeypatch.setattr("sys.argv", ["swane", "--remove-desktop-entry"])

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 0
    assert removed == [True]
