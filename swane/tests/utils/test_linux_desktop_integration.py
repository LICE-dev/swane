"""Unit tests for :mod:`swane.utils.linux_desktop_integration`."""

import os
import subprocess

import swane.utils.linux_desktop_integration as mod
from swane.utils.linux_desktop_integration import (
    ensure_desktop_entry,
    remove_desktop_entry,
)


def test_noop_on_non_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "is_linux", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    ensure_desktop_entry("/some/icon.png")

    assert not (tmp_path / "applications" / "swane.desktop").exists()


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
