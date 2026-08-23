import os
import subprocess
import sys

from swane.utils.platform_and_tools_utils import is_command_available, is_linux


def _data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def _desktop_file_path() -> str:
    return os.path.join(_data_home(), "applications", "swane.desktop")


def _launcher_script_path() -> str:
    return os.path.join(_data_home(), "swane", "swane-launcher.sh")


def _refresh_desktop_database(applications_dir: str) -> None:
    if is_command_available("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", applications_dir],
            capture_output=True,
            check=False,
        )


def _write_if_changed(path: str, content: str, executable: bool = False) -> bool:
    if os.path.isfile(path):
        with open(path, "r") as f:
            if f.read() == content:
                return False

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755 if executable else 0o644)
    return True


def ensure_desktop_entry(icon_path: str) -> None:
    """
    Ensure a freedesktop.org .desktop entry exists for SWANe on Linux.

    Most modern Linux desktop environments (GNOME/Wayland in particular) do not use
    the runtime QIcon set via QApplication.setWindowIcon() for the taskbar/dock icon:
    they match the running window's app id/WM_CLASS against an installed .desktop
    file and use its Icon= entry instead. Without this file the taskbar/dock shows a
    generic icon even though the window titlebar icon is correct.

    The entry's Exec= does not point directly at the SWANe executable: it points at a
    small generated launcher script (see _launcher_script_path()) that runs the real
    executable if it still exists, or otherwise removes both the script and this
    .desktop entry itself. pip has no uninstall hooks, so a file created outside of
    the package's own install records is never cleaned up by `pip uninstall`; this
    self-healing indirection is what avoids leaving a stale/broken menu entry behind
    without requiring the user to run any manual cleanup command.

    This is a no-op on non-Linux platforms and never raises: desktop integration is
    cosmetic and must not prevent SWANe from starting.

    :param icon_path: Absolute path to the SWANe icon image
    """
    if not is_linux():
        return

    try:
        exec_path = os.path.realpath(sys.argv[0])
        desktop_file = _desktop_file_path()
        launcher_script = _launcher_script_path()

        launcher_content = (
            "#!/bin/sh\n"
            f'if [ -x "{exec_path}" ]; then\n'
            f'    exec "{exec_path}"\n'
            "fi\n"
            f'rm -f "{launcher_script}" "{desktop_file}"\n'
            "if command -v notify-send >/dev/null 2>&1; then\n"
            '    notify-send "SWANe" '
            '"SWANe is no longer installed; this shortcut has been removed."\n'
            "fi\n"
        )

        desktop_content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=SWANe\n"
            "Comment=Standardized Workflow for Advanced Neuroimaging in Epilepsy\n"
            f'Exec="{launcher_script}"\n'
            f"Icon={icon_path}\n"
            "Terminal=false\n"
            "Categories=Science;\n"
            "StartupWMClass=swane\n"
        )

        changed = _write_if_changed(launcher_script, launcher_content, executable=True)
        changed = _write_if_changed(desktop_file, desktop_content) or changed

        if changed:
            _refresh_desktop_database(os.path.dirname(desktop_file))
    except Exception:
        pass


def remove_desktop_entry() -> None:
    """
    Remove the .desktop entry and launcher script installed by ensure_desktop_entry(),
    if present.

    Not required for normal cleanup: the generated launcher already self-removes both
    files the first time it is run after SWANe has been uninstalled (see
    ensure_desktop_entry()). This is only for users who want the menu entry gone
    immediately, without waiting for that next launch attempt: `swane --remove-desktop-entry`.

    This is a no-op on non-Linux platforms and never raises.
    """
    if not is_linux():
        return

    try:
        desktop_file = _desktop_file_path()
        launcher_script = _launcher_script_path()
        removed = False

        if os.path.isfile(desktop_file):
            os.remove(desktop_file)
            removed = True
        if os.path.isfile(launcher_script):
            os.remove(launcher_script)

        if removed:
            _refresh_desktop_database(os.path.dirname(desktop_file))
    except Exception:
        pass
